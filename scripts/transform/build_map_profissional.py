"""Gera profissional_id a partir de csv_listagem_login (mapa local + exp_profissional).

Regras: CPF → CNS → login → conselho → nome → orphan.
Chaves sensíveis ficam só em map_profissional_chave (não exportar).

Uso:
  PYTHONPATH=. python3 -m scripts.transform.build_map_profissional
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
from scripts.transform.identity import ProfissionalResolver  # noqa: E402

TARGET_DB = "vitacare_mvp"
SOURCE_TABLE = "csv_listagem_login"
BATCH = 2000

COLS_PROIBIDAS = frozenset(
    {
        "nome_utilizador",
        "nome",
        "cns",
        "cpf",
        "login_utilizador",
        "login",
        "email",
        "numero_conselho",
    }
)

SELECT_COLS = """
    row_id, nome_utilizador, cns, cpf, login_utilizador,
    cbo_code, cbo_desig, unidade, competencia_extracao,
    numero_conselho, uf_conselho
"""


def _apply_ddl() -> None:
    from scripts.ingest.apply_schema_vitacare_mvp import apply_schema

    apply_schema(
        project_root() / "sql" / "21_schema_map_profissional.sql",
        bootstrap_database=TARGET_DB,
    )


def _table_columns(cur: Any, table: str) -> set[str]:
    cur.execute(f"SHOW COLUMNS FROM `{table}`")
    return {r["Field"].lower() for r in cur.fetchall()}


def _select_sql(cur: Any) -> str:
    cols = _table_columns(cur, SOURCE_TABLE)
    wanted = [
        "row_id",
        "nome_utilizador",
        "cns",
        "cpf",
        "login_utilizador",
        "cbo_code",
        "cbo_desig",
        "unidade",
        "competencia_extracao",
        "numero_conselho",
        "uf_conselho",
    ]
    parts = []
    for c in wanted:
        if c == "competencia_extracao" or c == "row_id":
            parts.append(c)
        elif c in cols:
            parts.append(c)
        else:
            parts.append(f"NULL AS {c}")
    return "SELECT " + ", ".join(parts) + f" FROM `{SOURCE_TABLE}` ORDER BY competencia_extracao, row_id"


def _truncate(cur: Any) -> None:
    for table in (
        "exp_profissional",
        "fila_profissional_conflito",
        "map_profissional_chave",
    ):
        cur.execute(f"DELETE FROM `{table}`")


def _insert_many(cur: Any, sql: str, rows: list[tuple], batch: int = BATCH) -> None:
    for i in range(0, len(rows), batch):
        cur.executemany(sql, rows[i : i + batch])


def _build(cur: Any) -> tuple[ProfissionalResolver, dict[str, dict[str, Any]]]:
    resolver = ProfissionalResolver()
    profissionais: dict[str, dict[str, Any]] = {}
    cur.execute(_select_sql(cur))
    lidos = 0
    while True:
        batch = cur.fetchmany(BATCH)
        if not batch:
            break
        for row in batch:
            lidos += 1
            rid = resolver.resolve(
                cpf=row.get("cpf"),
                cns=row.get("cns"),
                login=row.get("login_utilizador"),
                nome=row.get("nome_utilizador"),
                uf_conselho=row.get("uf_conselho"),
                numero_conselho=row.get("numero_conselho"),
                row_id=int(row["row_id"]),
            )
            comp = (row.get("competencia_extracao") or "").strip()
            unidade = (row.get("unidade") or "").strip() or None
            meta = profissionais.get(rid)
            if meta is None:
                profissionais[rid] = {
                    "regra_origem": resolver.regra_origem.get(rid, "login"),
                    "cbo_code": row.get("cbo_code"),
                    "cbo_desig": row.get("cbo_desig"),
                    "unidades": {unidade} if unidade else set(),
                    "primeira": comp or None,
                    "ultima": comp or None,
                }
            else:
                if unidade:
                    meta["unidades"].add(unidade)
                if row.get("cbo_code"):
                    meta["cbo_code"] = row.get("cbo_code")
                    meta["cbo_desig"] = row.get("cbo_desig")
                if comp:
                    if meta["primeira"] is None or comp < meta["primeira"]:
                        meta["primeira"] = comp
                    if meta["ultima"] is None or comp > meta["ultima"]:
                        meta["ultima"] = comp
        if lidos % 2000 == 0:
            print(f"… processadas {lidos:,} linhas de login")

    print(
        f"Lidas={lidos:,} | profissionais={len(profissionais):,} | "
        f"conflitos={len(resolver.conflicts):,}"
    )
    return resolver, profissionais


def _persist(
    cur: Any,
    resolver: ProfissionalResolver,
    profissionais: dict[str, dict[str, Any]],
) -> None:
    map_rows = list(resolver.maps_for_persist())
    _insert_many(
        cur,
        """
        INSERT INTO map_profissional_chave
            (chave_tipo, chave_norm, profissional_id, regra_origem)
        VALUES (%s, %s, %s, %s)
        """,
        map_rows,
    )
    if resolver.conflicts:
        _insert_many(
            cur,
            """
            INSERT INTO fila_profissional_conflito
                (motivo_codigo, profissional_id_a, profissional_id_b, chave_tipo, detalhe)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [
                (
                    c.motivo_codigo,
                    c.profissional_id_a,
                    c.profissional_id_b,
                    c.chave_tipo,
                    c.detalhe,
                )
                for c in resolver.conflicts
            ],
        )
    exp_rows = [
        (
            rid,
            m["regra_origem"],
            m.get("cbo_code"),
            m.get("cbo_desig"),
            len(m["unidades"]),
            m.get("primeira"),
            m.get("ultima"),
        )
        for rid, m in profissionais.items()
    ]
    _insert_many(
        cur,
        """
        INSERT INTO exp_profissional (
            profissional_id, regra_origem, cbo_code, cbo_desig,
            qtd_unidades, primeira_competencia, ultima_competencia
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        exp_rows,
    )


def _reconcile(cur: Any) -> dict[str, Any]:
    cur.execute(f"SELECT COUNT(*) AS n FROM `{SOURCE_TABLE}`")
    bruto = int(cur.fetchone()["n"])
    cur.execute("SELECT COUNT(*) AS n FROM exp_profissional")
    n_prof = int(cur.fetchone()["n"])
    cur.execute("SELECT COUNT(*) AS n FROM map_profissional_chave")
    n_map = int(cur.fetchone()["n"])
    cur.execute("SELECT COUNT(*) AS n FROM fila_profissional_conflito")
    n_conf = int(cur.fetchone()["n"])
    cur.execute(
        """
        SELECT regra_origem, COUNT(*) AS n
        FROM exp_profissional GROUP BY regra_origem ORDER BY n DESC
        """
    )
    por_regra = {r["regra_origem"]: int(r["n"]) for r in cur.fetchall()}
    cur.execute(
        """
        SELECT chave_tipo, COUNT(*) AS n
        FROM map_profissional_chave GROUP BY chave_tipo ORDER BY n DESC
        """
    )
    por_chave = {r["chave_tipo"]: int(r["n"]) for r in cur.fetchall()}
    cols = _table_columns(cur, "exp_profissional")
    banned = sorted(cols & COLS_PROIBIDAS)

    # cobertura nome → consultas (contagem via Python, sem PII no log)
    return {
        "bruto_login": bruto,
        "profissionais": n_prof,
        "chaves_mapa": n_map,
        "conflitos": n_conf,
        "por_regra": por_regra,
        "por_chave": por_chave,
        "cols_proibidas": banned,
    }


def _cobertura_consultas_por_nome(cur: Any, resolver: ProfissionalResolver) -> dict[str, int]:
    nomes = set(resolver.by_nome.keys())
    cur.execute(
        """
        SELECT TRIM(profissional_consulta) AS nome, COUNT(*) AS n
        FROM csv_consultas_cap
        GROUP BY 1
        """
    )
    from scripts.transform.identity import normalize_nome

    total = matched = 0
    for row in cur.fetchall():
        n = int(row["n"])
        total += n
        nn = normalize_nome(row["nome"])
        if nn and nn in nomes:
            matched += n
    return {"consultas": total, "com_profissional_id_via_nome": matched}


def run(*, apply_ddl: bool = True, dry_run: bool = False) -> int:
    if apply_ddl:
        _apply_ddl()

    conn = connect(database=TARGET_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SHOW TABLES LIKE '{SOURCE_TABLE}'")
            if not cur.fetchone():
                print(
                    f"Tabela `{SOURCE_TABLE}` ausente. Importe LISTAGEM_LOGIN antes.",
                    file=sys.stderr,
                )
                return 1

            if dry_run:
                resolver, profissionais = _build(cur)
                print(
                    f"[dry-run] profissionais={len(profissionais):,} "
                    f"conflitos={len(resolver.conflicts):,}"
                )
                conn.rollback()
                return 0

            print("Limpando mapas destino…")
            _truncate(cur)
            print(f"Lendo `{SOURCE_TABLE}`…")
            resolver, profissionais = _build(cur)
            print("Persistindo…")
            _persist(cur, resolver, profissionais)
        conn.commit()

        with conn.cursor() as cur:
            stats = _reconcile(cur)
            try:
                stats["cobertura_consultas"] = _cobertura_consultas_por_nome(cur, resolver)
            except Exception as exc:
                stats["cobertura_consultas"] = {"erro": type(exc).__name__}
        print("Reconciliação:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        if stats["cols_proibidas"]:
            print("FALHA LGPD em exp_profissional", file=sys.stderr)
            return 2
        print("OK: map_profissional_chave + exp_profissional prontos.")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mapa local profissional_id a partir de csv_listagem_login"
    )
    parser.add_argument("--skip-ddl", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        return run(apply_ddl=not args.skip_ddl, dry_run=args.dry_run)
    except Exception as exc:
        print(f"Falha: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
