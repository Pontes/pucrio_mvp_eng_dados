"""Testes do checklist LGPD de exportação."""

from __future__ import annotations

from scripts.export.lgpd_checklist import (
    TABELAS_EXPORT_TODAS,
    colunas_proibidas_encontradas,
)


def test_export_list_has_core_tables():
    assert "cadastro_pacientes_ubs" in TABELAS_EXPORT_TODAS
    assert "consultas_ubs" in TABELAS_EXPORT_TODAS
    assert "exp_profissional" in TABELAS_EXPORT_TODAS
    assert "ficha_a_ubs" in TABELAS_EXPORT_TODAS


def test_checklist_blocks_pii_names():
    assert colunas_proibidas_encontradas(["paciente_id", "cnes"]) == []
    assert "cpf" in colunas_proibidas_encontradas(["paciente_id", "cpf", "bairro"])
