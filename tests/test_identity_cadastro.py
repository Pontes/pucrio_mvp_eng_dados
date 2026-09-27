"""Testes sintéticos das regras de paciente_id (sem PII real)."""

from __future__ import annotations

from scripts.export.lgpd_checklist import colunas_proibidas_encontradas
from scripts.transform.identity import (
    IdentityResolver,
    normalize_cns,
    normalize_cpf,
)


def test_normalize_cpf_valid_and_invalid():
    assert normalize_cpf("123.456.789-09") == "12345678909"
    assert normalize_cpf("00000000000") is None
    assert normalize_cpf("123") is None
    assert normalize_cpf(None) is None


def test_normalize_cns():
    assert normalize_cns("123456789012345") == "123456789012345"
    assert normalize_cns("000000000000000") is None
    assert normalize_cns("123") is None


def test_same_cpf_different_units_same_paciente():
    r = IdentityResolver()
    a = r.resolve(cpf="11122233344", cns=None, src_id="SRC_A")
    b = r.resolve(cpf="11122233344", cns=None, src_id="SRC_B")
    assert a == b
    assert r.regra_origem[a] == "cpf"


def test_cns_only_then_cpf_links():
    r = IdentityResolver()
    a = r.resolve(cpf=None, cns="123456789012345", src_id="S1")
    b = r.resolve(cpf="11122233344", cns="123456789012345", src_id="S2")
    assert a == b


def test_neither_doc_uses_src_id():
    r = IdentityResolver()
    a = r.resolve(cpf=None, cns=None, src_id="LOCAL_99")
    b = r.resolve(cpf=None, cns=None, src_id="LOCAL_99")
    c = r.resolve(cpf=None, cns=None, src_id="LOCAL_100")
    assert a == b
    assert a != c
    assert r.regra_origem[a] == "src_id"


def test_orphan_row_unique():
    r = IdentityResolver()
    a = r.resolve(cpf=None, cns=None, src_id=None, row_id=1)
    b = r.resolve(cpf=None, cns=None, src_id=None, row_id=2)
    assert a != b
    assert r.regra_origem[a] == "orphan_row"


def test_conflict_when_keys_point_different_patients():
    r = IdentityResolver()
    p1 = r.resolve(cpf="11122233344", cns=None, src_id="A")
    p2 = r.resolve(cpf=None, cns="123456789012345", src_id="B")
    assert p1 != p2
    # Linha tenta unir CPF de p1 com CNS de p2 → conflito registrado
    p3 = r.resolve(cpf="11122233344", cns="123456789012345", src_id="C")
    assert p3 in {p1, p2}
    assert len(r.conflicts) >= 1


def test_lgpd_checklist_exp_cols():
    ok = {"paciente_id", "cnes", "bairro", "primeira_competencia"}
    assert colunas_proibidas_encontradas(ok) == []
    bad = ok | {"cpf", "nome_mae"}
    assert colunas_proibidas_encontradas(bad) == ["cpf", "nome_mae"]
