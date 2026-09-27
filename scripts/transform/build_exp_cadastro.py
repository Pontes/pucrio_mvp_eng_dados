"""Limpa csv_cadastro_usuario_cap → cadastro_pacientes_ubs (sem PII na saída).

Grãos:
- exp_paciente: 1 linha / paciente_id (faixa_etaria na ultima_competencia global)
- cadastro_pacientes_ubs: 1 linha / (paciente_id, cnes) — faixa por vínculo/UBS
- exp_cadastro_presenca: 1 linha / (paciente_id, cnes, competencia_extracao)

Uso:
  PYTHONPATH=. python3 -m scripts.ingest.apply_schema_vitacare_mvp \\
    --sql sql/20_schema_exp_cadastro.sql --bootstrap-database vitacare_mvp
  PYTHONPATH=. python3 -m scripts.transform.build_exp_cadastro
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.db import connect, project_root  # noqa: E402
from scripts.transform.identity import (  # noqa: E402
    IdentityResolver,
    normalize_cnes,
)
from scripts.transform.faixa_etaria import faixa_etaria_from_dt_nasc  # noqa: E402

TARGET_DB = "vitacare_mvp"
SOURCE_TABLE = "csv_cadastro_usuario_cap"
BATCH = 5000

# Colunas proibidas na saída Databricks (checklist LGPD).
COLS_PROIBIDAS_EXPORT = frozenset(
    {
        "cns",
        "cpf",
        "nome",
        "nome_social",
        "logradouro",
        "numero",
        "complemento",
        "nome_mae",
        "src_id",
        "dt_nasc",
        "data_de_nascimento",
        "dta_nasc",
    }
)

SELECT_COLS = """
    row_id, src_id, cpf, cns, cnes, estab_saude, ine,
    bairro, sexo, dt_nasc, auxilio_brasil, competencia_extracao
"""


def _apply_ddl(sql_path: Path) -> None:
    from scripts.ingest.apply_schema_vitacare_mvp import apply_schema

    apply_schema(sql_path, bootstrap_database=TARGET_DB)


def _truncate_targets(cur: Any) -> None:
    # Ordem: filhos sem FK formal, depois mapas.
    for table in (
        "exp_cadastro_presenca",
        "cadastro_pacientes_ubs",
        "exp_paciente",
        "fila_identidade_conflito",
        "map_paciente_chave",
    ):
        cur.execute(f"DELETE FROM `{table}`")


def _fetch_batches(cur: Any):
    cur.execute(
        f"""
        SELECT {SELECT_COLS}
        FROM `{SOURCE_TABLE}`
        ORDER BY competencia_extracao, row_id
        """
    )
    while True:
        rows = cur.fetchmany(BATCH)
        if not rows:
            break
        yield rows


def _build_in_memory(cur: Any) -> tuple[
    IdentityResolver,
    dict[tuple[str, str], dict[str, Any]],
    set[tuple[str, str, str]],
    dict[str, dict[str, Any]],
]:
    """Resolve identidade e agrega vínculo/presença sem materializar PII em disco."""
    resolver = IdentityResolver()
    # (paciente_id, cnes) → attrs + comps
    vinculos: dict[tuple[str, str], dict[str, Any]] = {}
    presencas: set[tuple[str, str, str]] = set()
    pacientes: dict[str, dict[str, Any]] = {}

    lidos = 0
    sem_cnes = 0

    for batch in _fetch_batches(cur):
        for row in batch:
            lidos += 1
            pid = resolver.resolve(
                cpf=row.get("cpf"),
                cns=row.get("cns"),
                src_id=row.get("src_id"),
                row_id=int(row["row_id"]),
            )
            cnes = normalize_cnes(row.get("cnes"))
            comp = (row.get("competencia_extracao") or "").strip()
            if not cnes or not comp:
                sem_cnes += 1
                continue

            key = (pid, cnes)
            prev = vinculos.get(key)
            estab = row.get("estab_saude")
            faixa = faixa_etaria_from_dt_nasc(row.get("dt_nasc"), comp)
            attrs = {
                "estab_saude": estab,
                "ine": row.get("ine"),
                "bairro": row.get("bairro"),
                "sexo": row.get("sexo"),
                "faixa_etaria": faixa,
                "auxilio_brasil": row.get("auxilio_brasil"),
            }
            if prev is None:
                vinculos[key] = {
                    **attrs,
                    "primeira_competencia": comp,
                    "ultima_competencia": comp,
                    "comps": {comp},
                }
            else:
                if comp < prev["primeira_competencia"]:
                    prev["primeira_competencia"] = comp
                if comp >= prev["ultima_competencia"]:
                    prev["ultima_competencia"] = comp
                    prev.update(attrs)
                prev["comps"].add(comp)

            presencas.add((pid, cnes, comp))

            pmeta = pacientes.get(pid)
            if pmeta is None:
                pacientes[pid] = {
                    "regra_origem": resolver.regra_origem.get(pid, "src_id"),
                    "unidades": {cnes},
                    "primeira": comp,
                    "ultima": comp,
                    "faixa_etaria": faixa,
                }
            else:
                pmeta["unidades"].add(cnes)
                if comp < pmeta["primeira"]:
                    pmeta["primeira"] = comp
                if comp >= pmeta["ultima"]:
                    pmeta["ultima"] = comp
                    pmeta["faixa_etaria"] = faixa

        if lidos % 100_000 == 0:
            print(f"… processadas {lidos:,} linhas brutas")

    print(
        f"Lidas={lidos:,} | pacientes={len(pacientes):,} | "
        f"vinculos={len(vinculos):,} | presencas={len(presencas):,} | "
        f"sem_cnes_ou_comp={sem_cnes:,} | conflitos={len(resolver.conflicts):,}"
    )
    return resolver, vinculos, presencas, pacientes


def _insert_many(cur: Any, sql: str, rows: list[tuple], batch: int = BATCH) -> None:
    for i in range(0, len(rows), batch):
        cur.executemany(sql, rows[i : i + batch])


def _persist(
    cur: Any,
    resolver: IdentityResolver,
    vinculos: dict[tuple[str, str], dict[str, Any]],
    presencas: set[tuple[str, str, str]],
    pacientes: dict[str, dict[str, Any]],
) -> None:
    map_rows = [
        (tipo, chave, pid, regra)
        for tipo, chave, pid, regra in resolver.maps_for_persist()
    ]
    _insert_many(
        cur,
        """
        INSERT INTO map_paciente_chave
            (chave_tipo, chave_norm, paciente_id, regra_origem)
        VALUES (%s, %s, %s, %s)
        """,
        map_rows,
    )

    conflict_rows = [
        (
            c.motivo_codigo,
            c.paciente_id_a,
            c.paciente_id_b,
            c.chave_tipo,
            c.detalhe,
        )
        for c in resolver.conflicts
    ]
    if conflict_rows:
        _insert_many(
            cur,
            """
            INSERT INTO fila_identidade_conflito
                (motivo_codigo, paciente_id_a, paciente_id_b, chave_tipo, detalhe)
            VALUES (%s, %s, %s, %s, %s)
            """,
            conflict_rows,
        )

    pac_rows = [
        (
            pid,
            meta["regra_origem"],
            len(meta["unidades"]),
            meta["primeira"],
            meta["ultima"],
            meta.get("faixa_etaria"),
        )
        for pid, meta in pacientes.items()
    ]
    _insert_many(
        cur,
        """
        INSERT INTO exp_paciente
            (paciente_id, regra_origem, qtd_unidades, primeira_competencia,
             ultima_competencia, faixa_etaria)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        pac_rows,
    )

    vin_rows = [
        (
            pid,
            cnes,
            v.get("estab_saude"),
            v.get("ine"),
            v.get("bairro"),
            v.get("sexo"),
            v.get("faixa_etaria"),
            v.get("auxilio_brasil"),
            v["primeira_competencia"],
            v["ultima_competencia"],
            len(v["comps"]),
        )
        for (pid, cnes), v in vinculos.items()
    ]
    _insert_many(
        cur,
        """
        INSERT INTO cadastro_pacientes_ubs (
            paciente_id, cnes, estab_saude, ine, bairro, sexo, faixa_etaria,
            auxilio_brasil, primeira_competencia, ultima_competencia, qtd_competencias
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        vin_rows,
    )

    pre_rows = list(presencas)
    _insert_many(
        cur,
        """
        INSERT INTO exp_cadastro_presenca
            (paciente_id, cnes, competencia_extracao)
        VALUES (%s, %s, %s)
        """,
        pre_rows,
    )


def _reconcile(cur: Any) -> dict[str, Any]:
    cur.execute(f"SELECT COUNT(*) AS n FROM `{SOURCE_TABLE}`")
    bruto = int(cur.fetchone()["n"])
    cur.execute("SELECT COUNT(*) AS n FROM exp_paciente")
    n_pac = int(cur.fetchone()["n"])
    cur.execute("SELECT COUNT(*) AS n FROM cadastro_pacientes_ubs")
    n_vin = int(cur.fetchone()["n"])
    cur.execute("SELECT COUNT(*) AS n FROM exp_cadastro_presenca")
    n_pre = int(cur.fetchone()["n"])
    cur.execute("SELECT COUNT(*) AS n FROM fila_identidade_conflito")
    n_conf = int(cur.fetchone()["n"])
    cur.execute(
        """
        SELECT regra_origem, COUNT(*) AS n
        FROM exp_paciente GROUP BY regra_origem ORDER BY n DESC
        """
    )
    por_regra = {r["regra_origem"]: int(r["n"]) for r in cur.fetchall()}
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM exp_paciente WHERE qtd_unidades > 1
        """
    )
    multi = int(cur.fetchone()["n"])

    # Checklist: nenhuma coluna proibida nas tabelas de saída
    banned_found: dict[str, list[str]] = {}
    for table in ("exp_paciente", "cadastro_pacientes_ubs", "exp_cadastro_presenca"):
        cur.execute(f"SHOW COLUMNS FROM `{table}`")
        cols = {r["Field"].lower() for r in cur.fetchall()}
        hit = sorted(cols & COLS_PROIBIDAS_EXPORT)
        if hit:
            banned_found[table] = hit

    return {
        "bruto": bruto,
        "pacientes": n_pac,
        "cadastro_pacientes_ubs": n_vin,
        "presencas": n_pre,
        "conflitos": n_conf,
        "por_regra": por_regra,
        "multi_unidade": multi,
        "cols_proibidas": banned_found,
    }


def run(*, apply_ddl: bool = True, dry_run: bool = False) -> int:
    sql_path = project_root() / "sql" / "20_schema_exp_cadastro.sql"
    if apply_ddl:
        _apply_ddl(sql_path)

    conn = connect(database=TARGET_DB)
    try:
        with conn.cursor() as cur:
            if dry_run:
                resolver, vinculos, presencas, pacientes = _build_in_memory(cur)
                print(
                    f"[dry-run] pacientes={len(pacientes):,} "
                    f"vinculos={len(vinculos):,} "
                    f"presencas={len(presencas):,} "
                    f"conflitos={len(resolver.conflicts):,}"
                )
                conn.rollback()
                return 0

            print("Limpando tabelas destino…")
            _truncate_targets(cur)
            print(f"Lendo `{SOURCE_TABLE}` e resolvendo identidade…")
            resolver, vinculos, presencas, pacientes = _build_in_memory(cur)
            print("Persistindo mapas e tabelas exp_*…")
            _persist(cur, resolver, vinculos, presencas, pacientes)
        conn.commit()

        with conn.cursor() as cur:
            stats = _reconcile(cur)
        print("Reconciliação:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        if stats["cols_proibidas"]:
            print("FALHA LGPD: colunas proibidas em exp_*", file=sys.stderr)
            return 2
        print("OK: cadastro_pacientes_ubs pronta para export (sem CPF/CNS/nome/endereço).")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera paciente_id e tabelas exp_* a partir do cadastro bruto"
    )
    parser.add_argument(
        "--skip-ddl",
        action="store_true",
        help="Não reaplica sql/20_schema_exp_cadastro.sql",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Processa em memória sem gravar",
    )
    args = parser.parse_args()
    try:
        return run(apply_ddl=not args.skip_ddl, dry_run=args.dry_run)
    except Exception as exc:
        print(f"Falha: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
