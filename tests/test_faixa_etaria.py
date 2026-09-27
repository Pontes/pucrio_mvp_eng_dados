"""Testes de faixa etária (10 anos)."""

from __future__ import annotations

from datetime import date

from scripts.transform.faixa_etaria import (
    faixa_etaria_dez_anos,
    faixa_etaria_from_dt_nasc,
    idade_em_anos,
    parse_data,
)


def test_parse_dmy():
    assert parse_data("15/03/1990") == date(1990, 3, 15)
    assert parse_data("1990-03-15") == date(1990, 3, 15)


def test_faixas_dez_anos():
    assert faixa_etaria_dez_anos(0) == "0-9"
    assert faixa_etaria_dez_anos(9) == "0-9"
    assert faixa_etaria_dez_anos(10) == "10-19"
    assert faixa_etaria_dez_anos(35) == "30-39"
    assert faixa_etaria_dez_anos(89) == "80-89"
    assert faixa_etaria_dez_anos(90) == "90+"
    assert faixa_etaria_dez_anos(120) == "90+"


def test_from_dt_nasc_with_competencia():
    # 01/01/1990 → em 2026-01 tem 36 anos → 30-39
    assert faixa_etaria_from_dt_nasc("01/01/1990", "2026-01") == "30-39"
    # aniversário ainda não chegou no mês
    assert idade_em_anos(date(1990, 6, 15), date(2026, 1, 31)) == 35
    assert faixa_etaria_from_dt_nasc("15/06/1990", "2026-01") == "30-39"
