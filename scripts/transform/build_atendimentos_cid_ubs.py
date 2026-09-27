"""Limpa csv_atendimento_cid_param_bio → atendimentos_cid_ubs (sem PII).

Remove: nomes, CPF/CNS/NIS do paciente, CNS e nome do profissional, data de
nascimento, orientação sexual e identidade de gênero (dados sensíveis LGPD).
Mantém: CIDs/CIAP, sinais vitais, unidade, tipo, CBO, paciente_id/profissional_id.

Profissional: CNS do profissional → mapa; senão nome normalizado.

Uso:
  PYTHONPATH=. python3 -m scripts.transform.build_atendimentos_cid_ubs
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
SOURCE = "csv_atendimento_cid_param_bio"
DEST = "atendimentos_cid_ubs"
BATCH = 2000

COLS_PROIBIDAS = frozenset(
    {
        "cpf",
        "cpf_paciente",
        "cns",
        "cns_paciente",
        "numero_cns_profissional",
        "nis",
        "nis_paciente",
        "nome",
        "nome_paciente",
        "nome_social_paciente",
        "nome_profissional",
        "data_nasc_paciente",
        "orientacao_sexual_paciente",
        "identidade_genero",
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
        project_root() / "sql" / "24_schema_atendimentos_cid_ubs.sql",
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


def _load_prof_maps(cur: Any) -> tuple[dict[str, str], dict[str, str]]:
    by_cns: dict[str, str] = {}
    by_nome: dict[str, str] = {}
    cur.execute(
        """
        SELECT chave_tipo, chave_norm, profissional_id
        FROM map_profissional_chave
        WHERE chave_tipo IN ('cns', 'nome')
        """
    )
    while True:
        rows = cur.fetchmany(BATCH)
        if not rows:
            break
        for r in rows:
            if r["chave_tipo"] == "cns":
                by_cns[r["chave_norm"]] = r["profissional_id"]
            else:
                by_nome[r["chave_norm"]] = r["profissional_id"]
    return by_cns, by_nome


def _resolve_paciente(
    row: dict[str, Any],
    by_cpf: dict[str, str],
    by_cns: dict[str, str],
) -> str | None:
    n_cpf = normalize_cpf(row.get("cpf_paciente"))
    if n_cpf and n_cpf in by_cpf:
        return by_cpf[n_cpf]
    n_cns = normalize_cns(row.get("cns_paciente"))
    if n_cns and n_cns in by_cns:
        return by_cns[n_cns]
    return None


def _build_and_insert(
    conn: Any,
    by_cpf: dict[str, str],
    by_cns_pac: dict[str, str],
    by_cns_prof: dict[str, str],
    by_nome: dict[str, str],
) -> dict[str, int]:
    with conn.cursor() as wcur:
        wcur.execute(f"DELETE FROM `{DEST}`")
    read_cur = conn.cursor()
    write_cur = conn.cursor()
    try:
        read_cur.execute(
            f"""
            SELECT *
            FROM `{SOURCE}`
            ORDER BY competencia_extracao, row_id
            """
        )
        sql = f"""
            INSERT INTO `{DEST}` (
                paciente_id, profissional_id, cnes, unidade, ine, nome_equipe, ap,
                tipo_atendimento, cbo_profissional, data_consulta,
                sexo_paciente, raca, paciente_temporario, paciente_situacao_rua,
                cid_01, cid_consulta_diagnostico_01, estado_cid_consulta_01,
                cid_02, cid_consulta_diagnostico_02, estado_cid_consulta_02,
                cid_03, cid_consulta_diagnostico_03, estado_cid_consulta_03,
                cid_04, cid_consulta_diagnostico_04, estado_cid_consulta_04,
                cid_05, cid_consulta_diagnostico_05, estado_cid_consulta_05,
                ciap_consulta_01, ciap_consulta_02, ciap_consulta_03,
                ciap_consulta_04, ciap_consulta_05,
                peso, altura, pa_max, pa_min, temperatura, sat_02,
                competencia_extracao, carga_id, linha_origem
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s
            )
        """
        stats = {
            "lidas": 0,
            "com_paciente": 0,
            "com_profissional": 0,
            "sem_paciente": 0,
            "sem_profissional": 0,
            "prof_via_cns": 0,
            "prof_via_nome": 0,
        }
        buf: list[tuple] = []
        while True:
            batch = read_cur.fetchmany(BATCH)
            if not batch:
                break
            for row in batch:
                stats["lidas"] += 1
                pid = _resolve_paciente(row, by_cpf, by_cns_pac)
                n_cns_p = normalize_cns(row.get("numero_cns_profissional"))
                if n_cns_p and n_cns_p in by_cns_prof:
                    rid = by_cns_prof[n_cns_p]
                    stats["prof_via_cns"] += 1
                else:
                    nn = normalize_nome(row.get("nome_profissional"))
                    rid = by_nome.get(nn) if nn else None
                    if rid:
                        stats["prof_via_nome"] += 1
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
                        normalize_cnes(row.get("numero_cnes_da_unidade")),
                        row.get("unidade"),
                        row.get("numero_ine_equipe"),
                        row.get("nome_equipe"),
                        row.get("ap"),
                        row.get("tipo_atendimento"),
                        row.get("cbo_profissional"),
                        row.get("data_consulta"),
                        row.get("sexo_paciente"),
                        row.get("raca"),
                        row.get("paciente_temporario"),
                        row.get("paciente_situacao_rua"),
                        row.get("cid_01"),
                        row.get("cid_consulta_diagnostico_01"),
                        row.get("estado_cid_consulta_01"),
                        row.get("cid_02"),
                        row.get("cid_consulta_diagnostico_02"),
                        row.get("estado_cid_consulta_02"),
                        row.get("cid_03"),
                        row.get("cid_consulta_diagnostico_03"),
                        row.get("estado_cid_consulta_03"),
                        row.get("cid_04"),
                        row.get("cid_consulta_diagnostico_04"),
                        row.get("estado_cid_consulta_04"),
                        row.get("cid_05"),
                        row.get("cid_consulta_diagnostico_05"),
                        row.get("estado_cid_consulta_05"),
                        row.get("ciap_consulta_01"),
                        row.get("ciap_consulta_02"),
                        row.get("ciap_consulta_03"),
                        row.get("ciap_consulta_04"),
                        row.get("ciap_consulta_05"),
                        row.get("peso"),
                        row.get("altura"),
                        row.get("pa_max"),
                        row.get("pa_min"),
                        row.get("temperatura"),
                        row.get("sat_02"),
                        (row.get("competencia_extracao") or "").strip(),
                        row.get("carga_id"),
                        row.get("linha_origem"),
                    )
                )
                if len(buf) >= BATCH:
                    write_cur.executemany(sql, buf)
                    buf.clear()
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
            print("Carregando mapas…")
            by_cpf, by_cns_pac = _load_paciente_maps(cur)
            by_cns_prof, by_nome = _load_prof_maps(cur)
            print(
                f"Mapas: cpf={len(by_cpf):,} cns_pac={len(by_cns_pac):,} "
                f"cns_prof={len(by_cns_prof):,} nome_prof={len(by_nome):,}"
            )
            if dry_run:
                conn.rollback()
                return 0

        print(f"Lendo `{SOURCE}` → `{DEST}`…")
        stats = _build_and_insert(
            conn, by_cpf, by_cns_pac, by_cns_prof, by_nome
        )
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
            print("FALHA reconciliação", file=sys.stderr)
            return 3
        print(f"OK: `{DEST}` pronta.")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera atendimentos_cid_ubs a partir do bruto"
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
