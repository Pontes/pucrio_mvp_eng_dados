"""Limpa csv_acompanhamento_diab/hiper → acompanhamento_*_ubs (sem PII).

Remove: nome, CPF, CNS (num_sus), prontuário, DNV, data de nascimento.
Mantém: paciente_id, unidade, área/microárea, indicadores clínicos, competência.

Uso:
  PYTHONPATH=. python3 -m scripts.transform.build_acompanhamento_ubs
  PYTHONPATH=. python3 -m scripts.transform.build_acompanhamento_ubs --somente diab
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
BATCH = 5000

COLS_PROIBIDAS = frozenset(
    {
        "nome",
        "cpf",
        "cns",
        "num_sus",
        "num_pront",
        "dnv",
        "dta_nasc",
        "data_de_nascimento",
        "logradouro",
        "numero",
        "complemento",
        "nome_mae",
        "login",
        "email",
    }
)

DIAB = {
    "source": "csv_acompanhamento_diab",
    "dest": "acompanhamento_diab_ubs",
    "select": """
        SELECT row_id, carga_id, linha_origem, competencia_extracao,
               nome, num_sus, cnes, unidade, num_pront, dnv, cpf, dta_nasc,
               area_familia, microarea_familia,
               ta_min_2, ta_max_2, ta_data_2, hba1c, hba1c_data,
               exame_pe_esq, exame_pe_dir, exame_pes_data,
               ldl, ldl_data, hdl, hdl_data,
               colesterol_total, colesterol_total_data,
               triglicerideos, triglicerideos_data,
               microalbuminuria, microalbuminuria_data,
               encaminhamento_oftalm_data,
               esq_acuidade_visual, esq_acuidade_visual_data,
               dir_acuidade_visual, dir_acuidade_visual_data,
               dir_retinavis, dir_retinavis_data,
               esq_retinavis, esq_retinavis_data,
               dir_retinopatia, dir_retinopatia_data,
               esq_retinopatia, esq_retinopatia_data,
               ult_cons_med, qtd_cons_diab_12meses
        FROM csv_acompanhamento_diab
        ORDER BY competencia_extracao, row_id
    """,
    "insert": """
        INSERT INTO acompanhamento_diab_ubs (
            paciente_id, cnes, unidade, area_familia, microarea_familia,
            ta_min_2, ta_max_2, ta_data_2, hba1c, hba1c_data,
            exame_pe_esq, exame_pe_dir, exame_pes_data,
            ldl, ldl_data, hdl, hdl_data,
            colesterol_total, colesterol_total_data,
            triglicerideos, triglicerideos_data,
            microalbuminuria, microalbuminuria_data,
            encaminhamento_oftalm_data,
            esq_acuidade_visual, esq_acuidade_visual_data,
            dir_acuidade_visual, dir_acuidade_visual_data,
            dir_retinavis, dir_retinavis_data,
            esq_retinavis, esq_retinavis_data,
            dir_retinopatia, dir_retinopatia_data,
            esq_retinopatia, esq_retinopatia_data,
            ult_cons_med, qtd_cons_diab_12meses,
            competencia_extracao, carga_id, linha_origem
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s, %s
        )
    """,
    "row_fn": "diab",
}

HIPER = {
    "source": "csv_acompanhamento_hiper",
    "dest": "acompanhamento_hiper_ubs",
    "select": """
        SELECT row_id, carga_id, linha_origem, competencia_extracao,
               nome, num_sus, cnes, unidade, num_pront, dnv, cpf, dta_nasc,
               area_familia, microarea_familia,
               ta_min_2, ta_max_2, ta_data_2, data_ultima_consulta,
               microalbuminuria, microalbuminuria_data,
               colesterol_total, colesterol_total_data,
               hdl, hdl_data, triglicerideos, triglicerideos_data,
               proteinuria, proteinuria_data
        FROM csv_acompanhamento_hiper
        ORDER BY competencia_extracao, row_id
    """,
    "insert": """
        INSERT INTO acompanhamento_hiper_ubs (
            paciente_id, cnes, unidade, area_familia, microarea_familia,
            ta_min_2, ta_max_2, ta_data_2, data_ultima_consulta,
            microalbuminuria, microalbuminuria_data,
            colesterol_total, colesterol_total_data,
            hdl, hdl_data, triglicerideos, triglicerideos_data,
            proteinuria, proteinuria_data,
            competencia_extracao, carga_id, linha_origem
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s
        )
    """,
    "row_fn": "hiper",
}


def _apply_ddl() -> None:
    from scripts.ingest.apply_schema_vitacare_mvp import apply_schema

    apply_schema(
        project_root() / "sql" / "25_schema_acompanhamento_ubs.sql",
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
    n_cpf = normalize_cpf(row.get("cpf"))
    if n_cpf and n_cpf in by_cpf:
        return by_cpf[n_cpf]
    # NUM_SUS na fonte costuma ser CNS
    n_cns = normalize_cns(row.get("num_sus"))
    if n_cns and n_cns in by_cns:
        return by_cns[n_cns]
    return None


def _tuple_diab(row: dict[str, Any], pid: str | None) -> tuple:
    return (
        pid,
        normalize_cnes(row.get("cnes")),
        row.get("unidade"),
        row.get("area_familia"),
        row.get("microarea_familia"),
        row.get("ta_min_2"),
        row.get("ta_max_2"),
        row.get("ta_data_2"),
        row.get("hba1c"),
        row.get("hba1c_data"),
        row.get("exame_pe_esq"),
        row.get("exame_pe_dir"),
        row.get("exame_pes_data"),
        row.get("ldl"),
        row.get("ldl_data"),
        row.get("hdl"),
        row.get("hdl_data"),
        row.get("colesterol_total"),
        row.get("colesterol_total_data"),
        row.get("triglicerideos"),
        row.get("triglicerideos_data"),
        row.get("microalbuminuria"),
        row.get("microalbuminuria_data"),
        row.get("encaminhamento_oftalm_data"),
        row.get("esq_acuidade_visual"),
        row.get("esq_acuidade_visual_data"),
        row.get("dir_acuidade_visual"),
        row.get("dir_acuidade_visual_data"),
        row.get("dir_retinavis"),
        row.get("dir_retinavis_data"),
        row.get("esq_retinavis"),
        row.get("esq_retinavis_data"),
        row.get("dir_retinopatia"),
        row.get("dir_retinopatia_data"),
        row.get("esq_retinopatia"),
        row.get("esq_retinopatia_data"),
        row.get("ult_cons_med"),
        row.get("qtd_cons_diab_12meses"),
        (row.get("competencia_extracao") or "").strip(),
        row.get("carga_id"),
        row.get("linha_origem"),
    )


def _tuple_hiper(row: dict[str, Any], pid: str | None) -> tuple:
    return (
        pid,
        normalize_cnes(row.get("cnes")),
        row.get("unidade"),
        row.get("area_familia"),
        row.get("microarea_familia"),
        row.get("ta_min_2"),
        row.get("ta_max_2"),
        row.get("ta_data_2"),
        row.get("data_ultima_consulta"),
        row.get("microalbuminuria"),
        row.get("microalbuminuria_data"),
        row.get("colesterol_total"),
        row.get("colesterol_total_data"),
        row.get("hdl"),
        row.get("hdl_data"),
        row.get("triglicerideos"),
        row.get("triglicerideos_data"),
        row.get("proteinuria"),
        row.get("proteinuria_data"),
        (row.get("competencia_extracao") or "").strip(),
        row.get("carga_id"),
        row.get("linha_origem"),
    )


def _build_one(
    conn: Any,
    cfg: dict[str, Any],
    by_cpf: dict[str, str],
    by_cns: dict[str, str],
) -> dict[str, int]:
    dest = cfg["dest"]
    with conn.cursor() as wcur:
        wcur.execute(f"DELETE FROM `{dest}`")
    read_cur = conn.cursor()
    write_cur = conn.cursor()
    make_tuple = _tuple_diab if cfg["row_fn"] == "diab" else _tuple_hiper
    try:
        read_cur.execute(cfg["select"])
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
                buf.append(make_tuple(row, pid))
                if len(buf) >= BATCH:
                    write_cur.executemany(cfg["insert"], buf)
                    buf.clear()
            if stats["lidas"] % 50_000 == 0:
                print(f"… {dest}: {stats['lidas']:,}")
        if buf:
            write_cur.executemany(cfg["insert"], buf)
        return stats
    finally:
        read_cur.close()
        write_cur.close()


def _lgpd_ok(cur: Any, table: str) -> list[str]:
    cur.execute(f"SHOW COLUMNS FROM `{table}`")
    cols = {r["Field"].lower() for r in cur.fetchall()}
    return sorted(cols & COLS_PROIBIDAS)


def run(*, apply_ddl: bool = True, somente: str | None = None) -> int:
    if apply_ddl:
        _apply_ddl()

    targets = []
    if somente in (None, "diab"):
        targets.append(DIAB)
    if somente in (None, "hiper"):
        targets.append(HIPER)

    conn = connect(database=TARGET_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE 'map_paciente_chave'")
            if not cur.fetchone():
                print("map_paciente_chave ausente", file=sys.stderr)
                return 1
            for cfg in targets:
                cur.execute(f"SHOW TABLES LIKE '{cfg['source']}'")
                if not cur.fetchone():
                    print(f"Fonte ausente: {cfg['source']}", file=sys.stderr)
                    return 1
            print("Carregando mapas…")
            by_cpf, by_cns = _load_paciente_maps(cur)
            print(f"Mapas: cpf={len(by_cpf):,} cns={len(by_cns):,}")

        all_stats: dict[str, dict[str, int]] = {}
        for cfg in targets:
            print(f"Processando {cfg['source']} → {cfg['dest']}…")
            all_stats[cfg["dest"]] = _build_one(conn, cfg, by_cpf, by_cns)
            print("  ", all_stats[cfg["dest"]])
        conn.commit()

        with conn.cursor() as cur:
            for cfg in targets:
                dest = cfg["dest"]
                cur.execute(f"SELECT COUNT(*) AS n FROM `{dest}`")
                n = int(cur.fetchone()["n"])
                banned = _lgpd_ok(cur, dest)
                cur.execute(
                    f"SELECT COUNT(*) AS n FROM `{dest}` WHERE paciente_id IS NOT NULL"
                )
                n_pac = int(cur.fetchone()["n"])
                print(
                    f"Reconciliação {dest}: bruto={all_stats[dest]['lidas']:,} "
                    f"tabela={n:,} com_paciente={n_pac:,} cols_proibidas={banned}"
                )
                if banned or n != all_stats[dest]["lidas"]:
                    return 2
        print("OK: acompanhamento diab/hiper limpos.")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera acompanhamento_diab_ubs e acompanhamento_hiper_ubs"
    )
    parser.add_argument("--skip-ddl", action="store_true")
    parser.add_argument(
        "--somente",
        choices=["diab", "hiper"],
        default=None,
        help="Processa só uma das fontes",
    )
    args = parser.parse_args()
    try:
        return run(apply_ddl=not args.skip_ddl, somente=args.somente)
    except Exception as exc:
        print(f"Falha: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
