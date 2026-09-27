"""Limpa csv_consultas_cap → consultas_ubs (sem PII).

Campos essenciais: paciente_id, profissional_id, unidade/cnes/ine, data/hora,
cbo_presc, competencia_extracao. Remove CPF, CNS, src_id e nome do profissional.

Uso:
  PYTHONPATH=. python3 -m scripts.transform.build_consultas_ubs
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
    normalize_cnes,
    normalize_cns,
    normalize_cpf,
    normalize_nome,
    normalize_src_id,
)

TARGET_DB = "vitacare_mvp"
SOURCE = "csv_consultas_cap"
DEST = "consultas_ubs"
BATCH = 5000

COLS_PROIBIDAS = frozenset(
    {
        "cns",
        "cpf",
        "src_id",
        "nome",
        "nome_social",
        "profissional_consulta",
        "logradouro",
        "numero",
        "complemento",
        "nome_mae",
        "login",
        "email",
    }
)


def _apply_ddl() -> None:
    from scripts.ingest.apply_schema_vitacare_mvp import apply_schema

    apply_schema(
        project_root() / "sql" / "22_schema_consultas_ubs.sql",
        bootstrap_database=TARGET_DB,
    )


def _load_paciente_maps(cur: Any) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    by_cpf: dict[str, str] = {}
    by_cns: dict[str, str] = {}
    by_src: dict[str, str] = {}
    cur.execute(
        """
        SELECT chave_tipo, chave_norm, paciente_id
        FROM map_paciente_chave
        WHERE chave_tipo IN ('cpf', 'cns', 'src_id')
        """
    )
    while True:
        rows = cur.fetchmany(BATCH)
        if not rows:
            break
        for r in rows:
            tipo = r["chave_tipo"]
            chave = r["chave_norm"]
            pid = r["paciente_id"]
            if tipo == "cpf":
                by_cpf[chave] = pid
            elif tipo == "cns":
                by_cns[chave] = pid
            else:
                by_src[chave] = pid
    return by_cpf, by_cns, by_src


def _load_prof_by_nome(cur: Any) -> dict[str, str]:
    by_nome: dict[str, str] = {}
    cur.execute(
        """
        SELECT chave_norm, profissional_id
        FROM map_profissional_chave
        WHERE chave_tipo = 'nome'
        """
    )
    while True:
        rows = cur.fetchmany(BATCH)
        if not rows:
            break
        for r in rows:
            by_nome[r["chave_norm"]] = r["profissional_id"]
    return by_nome


def _resolve_paciente(
    row: dict[str, Any],
    by_cpf: dict[str, str],
    by_cns: dict[str, str],
    by_src: dict[str, str],
) -> str | None:
    n_cpf = normalize_cpf(row.get("cpf"))
    if n_cpf and n_cpf in by_cpf:
        return by_cpf[n_cpf]
    n_cns = normalize_cns(row.get("cns"))
    if n_cns and n_cns in by_cns:
        return by_cns[n_cns]
    n_src = normalize_src_id(row.get("src_id"))
    if n_src and n_src in by_src:
        return by_src[n_src]
    return None


def _build_rows(
    cur: Any,
    by_cpf: dict[str, str],
    by_cns: dict[str, str],
    by_src: dict[str, str],
    by_nome: dict[str, str],
) -> tuple[list[tuple], dict[str, int]]:
    cur.execute(
        """
        SELECT row_id, carga_id, linha_origem, competencia_extracao,
               ap, unidade, src_id, cns, cpf, cnes, ine,
               dt_consulta, hora_consulta, profissional_consulta, cbo_presc
        FROM csv_consultas_cap
        ORDER BY competencia_extracao, row_id
        """
    )
    out: list[tuple] = []
    stats = {
        "lidas": 0,
        "com_paciente": 0,
        "com_profissional": 0,
        "sem_paciente": 0,
        "sem_profissional": 0,
    }
    while True:
        batch = cur.fetchmany(BATCH)
        if not batch:
            break
        for row in batch:
            stats["lidas"] += 1
            pid = _resolve_paciente(row, by_cpf, by_cns, by_src)
            nn = normalize_nome(row.get("profissional_consulta"))
            rid = by_nome.get(nn) if nn else None
            if pid:
                stats["com_paciente"] += 1
            else:
                stats["sem_paciente"] += 1
            if rid:
                stats["com_profissional"] += 1
            else:
                stats["sem_profissional"] += 1
            out.append(
                (
                    pid,
                    rid,
                    normalize_cnes(row.get("cnes")),
                    row.get("unidade"),
                    row.get("ine"),
                    row.get("ap"),
                    row.get("dt_consulta"),
                    row.get("hora_consulta"),
                    row.get("cbo_presc"),
                    (row.get("competencia_extracao") or "").strip(),
                    row.get("carga_id"),
                    row.get("linha_origem"),
                )
            )
        if stats["lidas"] % 100_000 == 0:
            print(f"… processadas {stats['lidas']:,} consultas")
    return out, stats


def _persist(cur: Any, rows: list[tuple]) -> None:
    cur.execute(f"DELETE FROM `{DEST}`")
    sql = f"""
        INSERT INTO `{DEST}` (
            paciente_id, profissional_id, cnes, unidade, ine, ap,
            dt_consulta, hora_consulta, cbo_presc, competencia_extracao,
            carga_id, linha_origem
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    for i in range(0, len(rows), BATCH):
        cur.executemany(sql, rows[i : i + BATCH])


def _lgpd_ok(cur: Any) -> list[str]:
    cur.execute(f"SHOW COLUMNS FROM `{DEST}`")
    cols = {r["Field"].lower() for r in cur.fetchall()}
    return sorted(cols & COLS_PROIBIDAS)


def run(*, apply_ddl: bool = True, dry_run: bool = False) -> int:
    if apply_ddl:
        _apply_ddl()

    conn = connect(database=TARGET_DB)
    try:
        with conn.cursor() as cur:
            for needed in ("map_paciente_chave", "map_profissional_chave", SOURCE):
                cur.execute(f"SHOW TABLES LIKE '{needed}'")
                if not cur.fetchone():
                    print(f"Tabela obrigatória ausente: {needed}", file=sys.stderr)
                    return 1

            print("Carregando mapas locais…")
            by_cpf, by_cns, by_src = _load_paciente_maps(cur)
            by_nome = _load_prof_by_nome(cur)
            print(
                f"Mapas: cpf={len(by_cpf):,} cns={len(by_cns):,} "
                f"src={len(by_src):,} nome_prof={len(by_nome):,}"
            )
            print(f"Lendo `{SOURCE}`…")
            rows, stats = _build_rows(cur, by_cpf, by_cns, by_src, by_nome)
            print("Stats leitura:", stats)
            if dry_run:
                conn.rollback()
                return 0
            print(f"Persistindo `{DEST}`…")
            _persist(cur, rows)
        conn.commit()

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS n FROM `{DEST}`")
            n = int(cur.fetchone()["n"])
            banned = _lgpd_ok(cur)
            cur.execute(
                f"SELECT COUNT(*) AS n FROM `{DEST}` WHERE paciente_id IS NOT NULL"
            )
            n_pac = int(cur.fetchone()["n"])
            cur.execute(
                f"SELECT COUNT(*) AS n FROM `{DEST}` WHERE profissional_id IS NOT NULL"
            )
            n_prof = int(cur.fetchone()["n"])
        print(
            f"Reconciliação: bruto={stats['lidas']:,} {DEST}={n:,} "
            f"com_paciente={n_pac:,} com_profissional={n_prof:,} "
            f"cols_proibidas={banned}"
        )
        if banned:
            print("FALHA LGPD", file=sys.stderr)
            return 2
        if n != stats["lidas"]:
            print("FALHA reconciliação de contagem", file=sys.stderr)
            return 3
        print(f"OK: `{DEST}` pronta (sem CPF/CNS/nome do profissional).")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera consultas_ubs a partir do bruto")
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
