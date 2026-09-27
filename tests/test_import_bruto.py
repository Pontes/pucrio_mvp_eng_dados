"""Testes sintéticos da importação bruta (sem PII real)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.db import connect, load_env
from scripts.ingest.import_bruto import (
    TARGET_DB,
    competencia_from_name,
    import_csv,
    normalize_sql_column,
    parse_arquivo,
    resolve_tabela,
    sha256_file,
    unique_columns,
)


@pytest.fixture()
def vitacare_mvp_ready() -> bool:
    load_env()
    if not os.getenv("MYSQL_USER"):
        return False
    try:
        conn = connect(database=TARGET_DB)
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE 'carga_arquivo'")
            ok = cur.fetchone() is not None
        conn.close()
        return ok
    except Exception:
        return False


def test_competencia_from_name():
    assert (
        competencia_from_name("Marica_LISTAGEM_CONSULTAS_CAP_2025-09.csv")
        == "2025-09"
    )


def test_parse_arquivo():
    tipo, comp = parse_arquivo(Path("Marica_SUBPAV_MENSAL_EXAMES_2026-01.csv"))
    assert tipo == "SUBPAV_MENSAL_EXAMES"
    assert comp == "2026-01"


def test_normalize_sql_column():
    assert normalize_sql_column("UNIDADE DE SAUDE") == "unidade_de_saude"
    assert normalize_sql_column("1ABC") == "c_1abc"
    assert normalize_sql_column("carga_id") == "src_carga_id"


def test_unique_columns_collision():
    cols = unique_columns(["AP", "ap", "AP "])
    assert cols[0] == "ap"
    assert cols[1] == "ap_2"
    assert cols[2] == "ap_3"


def test_resolve_tabela_ficha_a():
    assert resolve_tabela("SUB_PAV_FICHA_A_V2", 61) == (
        "csv_ficha_a_v2",
        "ficha_a_v2",
    )
    assert resolve_tabela("SUB_PAV_FICHA_A_V2", 161) == (
        "csv_ficha_a_v2_ext",
        "ficha_a_v2_ext",
    )
    assert resolve_tabela("LISTAGEM_CONSULTAS_CAP", 11)[0] == "csv_consultas_cap"


def test_sha256_stable(tmp_path: Path):
    p = tmp_path / "a.csv"
    p.write_text("x\n", encoding="utf-8")
    assert sha256_file(p) == sha256_file(p)


def test_import_synthetic_bruto(tmp_path: Path, vitacare_mvp_ready: bool):
    if not vitacare_mvp_ready:
        pytest.skip("MySQL/schema vitacare_mvp indisponível")

    # 3 cols → tabela isolada csv_ficha_a_v2_c3 (não polui tabelas reais)
    content = (
        "COL_A;COL_B;COL_C\n"
        "v1;v2;v3\n"
        "only_two_fields;x\n"
        "a;b;c\n"
    )
    path = tmp_path / "Marica_SUB_PAV_FICHA_A_V2_2099-01.csv"
    path.write_text(content, encoding="utf-8")

    result = import_csv(path, database=TARGET_DB, batch_size=10)
    assert result.skipped is False
    assert result.tabela == "csv_ficha_a_v2_c3"
    assert result.qtd_lidas == 3
    assert result.qtd_aceitas == 2
    assert result.qtd_rejeitadas == 1
    assert result.qtd_lidas == result.qtd_aceitas + result.qtd_rejeitadas

    again = import_csv(path, database=TARGET_DB, batch_size=10)
    assert again.skipped is True
    assert again.carga_id == result.carga_id

    conn = connect(database=TARGET_DB)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM csv_ficha_a_v2_c3 WHERE carga_id = %s",
                (result.carga_id,),
            )
            assert int(cur.fetchone()["n"]) == 2
            cur.execute(
                "DELETE FROM linha_rejeitada WHERE carga_id = %s",
                (result.carga_id,),
            )
            cur.execute(
                "DELETE FROM csv_ficha_a_v2_c3 WHERE carga_id = %s",
                (result.carga_id,),
            )
            cur.execute(
                "DELETE FROM carga_arquivo WHERE carga_id = %s",
                (result.carga_id,),
            )
            cur.execute("DROP TABLE IF EXISTS csv_ficha_a_v2_c3")
        conn.commit()
    finally:
        conn.close()


def test_dry_run_no_write(tmp_path: Path):
    path = tmp_path / "Marica_LISTAGEM_CONSULTAS_CAP_2099-02.csv"
    path.write_text("AP;UNIDADE;ID\na;b;c\n", encoding="utf-8")
    result = import_csv(path, dry_run=True)
    assert result.dry_run is True
    assert result.qtd_lidas == 1
    assert result.carga_id == 0
