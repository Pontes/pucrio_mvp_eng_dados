"""Limpa csv_ficha_a_v2_ext → ficha_a_ubs (colunas essenciais apenas).

Mantém: paciente_id, unidade/equipe/CNES/INE, datas de cadastro,
situação, óbito, sexo, raça/cor, nacionalidade, peso, altura, escolaridade,
competencia_extracao.

Uso:
  PYTHONPATH=. python3 -m scripts.transform.build_ficha_a_ubs
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
)

TARGET_DB = "vitacare_mvp"
SOURCE = "csv_ficha_a_v2_ext"
DEST = "ficha_a_ubs"
BATCH = 2000

COLS_PROIBIDAS = frozenset(
    {
        "n_cpf",
        "cpf",
        "n_cns_da_pessoa_cadastrada",
        "cns",
        "nis",
        "n_dnv",
        "nome",
        "nome_da_pessoa_cadastrada",
        "nome_social",
        "nome_da_mae",
        "logradouro",
        "telefone_contato",
        "email_contato",
        "data_de_nascimento",
        "orientacao_sexual",
        "identidade_genero",
    }
)

# Colunas da fonte (exceto paciente_id / cnes derivados).
KEEP_SRC = [
    "numero_cnes_unidade",
    "nome_unidade_de_saude",
    "nome_equipe_de_saude",
    "codigo_da_equipe_de_saude",
    "codigo_ine_equipe_de_saude",
    "data_cadastro",
    "data_ultima_atualizacao_do_cadastro",
    "situacao_usuario",
    "obito",
    "sexo",
    "raca_cor",
    "nacionalidade",
    "peso",
    "altura",
    "escolaridade",
]

INSERT_COLS = [
    "paciente_id",
    "cnes",
    "nome_unidade_de_saude",
    "nome_equipe_de_saude",
    "codigo_da_equipe_de_saude",
    "codigo_ine_equipe_de_saude",
    "data_cadastro",
    "data_ultima_atualizacao_do_cadastro",
    "situacao_usuario",
    "obito",
    "sexo",
    "raca_cor",
    "nacionalidade",
    "peso",
    "altura",
    "escolaridade",
    "competencia_extracao",
]


def _apply_ddl() -> None:
    from scripts.ingest.apply_schema_vitacare_mvp import apply_schema

    apply_schema(
        project_root() / "sql" / "26_schema_ficha_a_ubs.sql",
        bootstrap_database=TARGET_DB,
    )


def _load_paciente_maps(cur: Any) -> tuple[dict[str, str], dict[str, str]]:
    by_cpf: dict[str, str] = {}
    by_cns: dict[str, str] = {}
    cur.execute(
        """
        SELECT chave_tipo, chave_norm, paciente_id
        FROM map_paciente_chave
        WHERE chave_tipo IN ('cpf', 'cns')
        """
    )
    while True:
        rows = cur.fetchmany(BATCH)
        if not rows:
            break
        for r in rows:
            if r["chave_tipo"] == "cpf":
                by_cpf[r["chave_norm"]] = r["paciente_id"]
            else:
                by_cns[r["chave_norm"]] = r["paciente_id"]
    return by_cpf, by_cns


def _resolve_paciente(
    row: dict[str, Any],
    by_cpf: dict[str, str],
    by_cns: dict[str, str],
) -> str | None:
    n_cpf = normalize_cpf(row.get("n_cpf"))
    if n_cpf and n_cpf in by_cpf:
        return by_cpf[n_cpf]
    n_cns = normalize_cns(row.get("n_cns_da_pessoa_cadastrada"))
    if n_cns and n_cns in by_cns:
        return by_cns[n_cns]
    return None


def _clip(value: Any, max_len: int | None) -> Any:
    if value is None or max_len is None:
        return value
    s = str(value)
    return s if len(s) <= max_len else s[:max_len]


def _column_limits(cur: Any) -> dict[str, int | None]:
    cur.execute(f"SHOW COLUMNS FROM `{DEST}`")
    limits: dict[str, int | None] = {}
    for r in cur.fetchall():
        typ = (r["Type"] or "").lower()
        name = r["Field"]
        if typ.startswith("varchar(") or typ.startswith("char("):
            limits[name] = int(typ.split("(")[1].split(")")[0])
        else:
            limits[name] = None
    return limits


def _build_and_insert(
    conn: Any,
    by_cpf: dict[str, str],
    by_cns: dict[str, str],
) -> dict[str, int]:
    with conn.cursor() as wcur:
        wcur.execute(f"DELETE FROM `{DEST}`")
        limits = _column_limits(wcur)

    select_cols = [
        "row_id",
        "n_cpf",
        "n_cns_da_pessoa_cadastrada",
        "competencia_extracao",
    ] + KEEP_SRC
    col_sql = ", ".join(f"`{c}`" for c in select_cols)
    placeholders = ", ".join(["%s"] * len(INSERT_COLS))
    insert_sql = (
        f"INSERT INTO `{DEST}` ("
        + ", ".join(f"`{c}`" for c in INSERT_COLS)
        + f") VALUES ({placeholders})"
    )

    read_cur = conn.cursor()
    write_cur = conn.cursor()
    try:
        read_cur.execute(
            f"SELECT {col_sql} FROM `{SOURCE}` ORDER BY row_id"
        )
        stats = {"lidas": 0, "com_paciente": 0, "sem_paciente": 0}
        buf: list[tuple] = []
        while True:
            batch = read_cur.fetchmany(BATCH)
            if not batch:
                break
            for row in batch:
                stats["lidas"] += 1
                pid = _resolve_paciente(row, by_cpf, by_cns)
                if pid:
                    stats["com_paciente"] += 1
                else:
                    stats["sem_paciente"] += 1
                raw = [
                    pid,
                    normalize_cnes(row.get("numero_cnes_unidade")),
                    row.get("nome_unidade_de_saude"),
                    row.get("nome_equipe_de_saude"),
                    row.get("codigo_da_equipe_de_saude"),
                    row.get("codigo_ine_equipe_de_saude"),
                    row.get("data_cadastro"),
                    row.get("data_ultima_atualizacao_do_cadastro"),
                    row.get("situacao_usuario"),
                    row.get("obito"),
                    row.get("sexo"),
                    row.get("raca_cor"),
                    row.get("nacionalidade"),
                    row.get("peso"),
                    row.get("altura"),
                    row.get("escolaridade"),
                    (row.get("competencia_extracao") or "").strip(),
                ]
                values = tuple(
                    _clip(v, limits.get(col)) for col, v in zip(INSERT_COLS, raw)
                )
                buf.append(values)
                if len(buf) >= BATCH:
                    write_cur.executemany(insert_sql, buf)
                    buf.clear()
            if stats["lidas"] % 100_000 == 0:
                print(f"… processadas {stats['lidas']:,} fichas")
        if buf:
            write_cur.executemany(insert_sql, buf)
        return stats
    finally:
        read_cur.close()
        write_cur.close()


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
            for needed in ("map_paciente_chave", SOURCE):
                cur.execute(f"SHOW TABLES LIKE '{needed}'")
                if not cur.fetchone():
                    print(f"Tabela ausente: {needed}", file=sys.stderr)
                    return 1
            cur.execute(f"SELECT COUNT(*) AS n FROM `{SOURCE}`")
            n_src = int(cur.fetchone()["n"])
            if n_src == 0:
                print(f"`{SOURCE}` vazia.", file=sys.stderr)
                return 1
            print("Carregando mapas…")
            by_cpf, by_cns = _load_paciente_maps(cur)
            print(f"Mapas: cpf={len(by_cpf):,} cns={len(by_cns):,} | bruto={n_src:,}")
            if dry_run:
                conn.rollback()
                return 0

        print(f"Lendo `{SOURCE}` → `{DEST}` (colunas reduzidas)…")
        stats = _build_and_insert(conn, by_cpf, by_cns)
        print("Stats:", stats)
        conn.commit()

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS n FROM `{DEST}`")
            n = int(cur.fetchone()["n"])
            banned = _lgpd_ok(cur)
            cur.execute(f"SHOW COLUMNS FROM `{DEST}`")
            cols = [r["Field"] for r in cur.fetchall()]
            cur.execute(
                f"SELECT COUNT(*) AS n FROM `{DEST}` WHERE paciente_id IS NOT NULL"
            )
            n_pac = int(cur.fetchone()["n"])
        print(f"Colunas finais: {cols}")
        print(
            f"Reconciliação: bruto={stats['lidas']:,} {DEST}={n:,} "
            f"com_paciente={n_pac:,} cols_proibidas={banned}"
        )
        if banned or n != stats["lidas"]:
            return 2
        print("OK: ficha_a_ubs reduzida.")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera ficha_a_ubs reduzida a partir de csv_ficha_a_v2_ext"
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
