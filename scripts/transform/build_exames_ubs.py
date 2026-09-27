"""Limpa csv_exames → exames_ubs (sem PII).

Campos essenciais: paciente_id, profissional_id (solicitante), unidade, exame,
data da requisição, CBO/categoria, valor tabelado, CID, competência.
Remove: nome do paciente, CPF, CNS, DNV, prontuário, nome do profissional.

Uso:
  PYTHONPATH=. python3 -m scripts.transform.build_exames_ubs
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
)

TARGET_DB = "vitacare_mvp"
SOURCE = "csv_exames"
DEST = "exames_ubs"
BATCH = 5000

COLS_PROIBIDAS = frozenset(
    {
        "cpf",
        "cns",
        "cns_do_paciente",
        "nome",
        "nome_do_paciente",
        "nome_do_profissional_solicitante",
        "dnv",
        "n_m_prontu_rio",
        "logradouro",
        "numero",
        "complemento",
        "nome_mae",
        "login",
        "email",
        "data_de_nascimento",  # idade via join com cadastro
    }
)


def _apply_ddl() -> None:
    from scripts.ingest.apply_schema_vitacare_mvp import apply_schema

    apply_schema(
        project_root() / "sql" / "23_schema_exames_ubs.sql",
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
) -> str | None:
    n_cpf = normalize_cpf(row.get("cpf"))
    if n_cpf and n_cpf in by_cpf:
        return by_cpf[n_cpf]
    n_cns = normalize_cns(row.get("cns_do_paciente"))
    if n_cns and n_cns in by_cns:
        return by_cns[n_cns]
    return None


def _build_and_insert(
    conn: Any,
    by_cpf: dict[str, str],
    by_cns: dict[str, str],
    by_nome: dict[str, str],
) -> dict[str, int]:
    # Cursores separados: INSERT no mesmo cursor do SELECT interrompe o fetch.
    with conn.cursor() as wcur:
        wcur.execute(f"DELETE FROM `{DEST}`")
    read_cur = conn.cursor()
    write_cur = conn.cursor()
    try:
        read_cur.execute(
            """
            SELECT row_id, carga_id, linha_origem, competencia_extracao,
                   ap, cnes, unidade_de_saude, nome_do_profissional_solicitante,
                   cbo, categoria_profissional, codigo_da_requisicao,
                   cpf, cns_do_paciente, sexo,
                   data_da_requisicao, codigo_da_tabela, nome_do_exame,
                   valor_do_exame, cid_ativo
            FROM csv_exames
            ORDER BY competencia_extracao, row_id
            """
        )
        sql = f"""
            INSERT INTO `{DEST}` (
                paciente_id, profissional_id, cnes, unidade_de_saude, ap, sexo,
                data_da_requisicao, codigo_da_tabela, nome_do_exame, valor_do_exame,
                cid_ativo, cbo, categoria_profissional, codigo_da_requisicao,
                competencia_extracao, carga_id, linha_origem
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        stats = {
            "lidas": 0,
            "com_paciente": 0,
            "com_profissional": 0,
            "sem_paciente": 0,
            "sem_profissional": 0,
        }
        buf: list[tuple] = []
        while True:
            batch = read_cur.fetchmany(BATCH)
            if not batch:
                break
            for row in batch:
                stats["lidas"] += 1
                pid = _resolve_paciente(row, by_cpf, by_cns)
                nn = normalize_nome(row.get("nome_do_profissional_solicitante"))
                rid = by_nome.get(nn) if nn else None
                if pid:
                    stats["com_paciente"] += 1
                else:
                    stats["sem_paciente"] += 1
                if rid:
                    stats["com_profissional"] += 1
                else:
                    stats["sem_profissional"] += 1
                buf.append(
                    (
                        pid,
                        rid,
                        normalize_cnes(row.get("cnes")),
                        row.get("unidade_de_saude"),
                        row.get("ap"),
                        row.get("sexo"),
                        row.get("data_da_requisicao"),
                        row.get("codigo_da_tabela"),
                        row.get("nome_do_exame"),
                        row.get("valor_do_exame"),
                        row.get("cid_ativo"),
                        row.get("cbo"),
                        row.get("categoria_profissional"),
                        row.get("codigo_da_requisicao"),
                        (row.get("competencia_extracao") or "").strip(),
                        row.get("carga_id"),
                        row.get("linha_origem"),
                    )
                )
                if len(buf) >= BATCH:
                    write_cur.executemany(sql, buf)
                    buf.clear()
            if stats["lidas"] % 100_000 == 0:
                print(f"… processadas {stats['lidas']:,} linhas de exame")
        if buf:
            write_cur.executemany(sql, buf)
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
            for needed in ("map_paciente_chave", "map_profissional_chave", SOURCE):
                cur.execute(f"SHOW TABLES LIKE '{needed}'")
                if not cur.fetchone():
                    print(f"Tabela obrigatória ausente: {needed}", file=sys.stderr)
                    return 1

            print("Carregando mapas locais…")
            by_cpf, by_cns = _load_paciente_maps(cur)
            by_nome = _load_prof_by_nome(cur)
            print(
                f"Mapas: cpf={len(by_cpf):,} cns={len(by_cns):,} "
                f"nome_prof={len(by_nome):,}"
            )
            if dry_run:
                print("[dry-run] mapas OK; sem gravar")
                conn.rollback()
                return 0

            print(f"Lendo `{SOURCE}` e gravando `{DEST}`…")
            stats = _build_and_insert(conn, by_cpf, by_cns, by_nome)
            print("Stats:", stats)
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
        print(f"OK: `{DEST}` pronta (sem nome/CPF/CNS do paciente ou profissional).")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera exames_ubs a partir do bruto")
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
