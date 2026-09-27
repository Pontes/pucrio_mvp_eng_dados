"""Testes sintéticos do mapa de profissional_id."""

from __future__ import annotations

from scripts.transform.identity import (
    ProfissionalResolver,
    normalize_conselho,
    normalize_login,
    normalize_nome,
)


def test_normalize_nome_and_login():
    assert normalize_nome("José da Silva") == "JOSE DA SILVA"
    assert normalize_login("  User.X ") == "user.x"
    assert normalize_conselho("rj", "12345") == "RJ:12345"


def test_same_cpf_different_units_same_profissional():
    r = ProfissionalResolver()
    a = r.resolve(cpf="11122233344", cns=None, login="a", nome="ANA A")
    b = r.resolve(cpf="11122233344", cns=None, login="b", nome="ANA A USB2")
    # CPF une; nome diferente pode gerar conflito de bind de nome, mas mesmo id
    assert a == b
    assert a.startswith("R")


def test_login_stable_across_months():
    r = ProfissionalResolver()
    a = r.resolve(cpf=None, cns=None, login="dr.fulano", nome="FULANO")
    b = r.resolve(cpf=None, cns=None, login="dr.fulano", nome="FULANO")
    assert a == b


def test_nome_lookup_for_consultas():
    r = ProfissionalResolver()
    rid = r.resolve(
        cpf="11122233344",
        cns="123456789012345",
        login="login1",
        nome="Maria Souza",
    )
    assert r.by_nome[normalize_nome("maria souza")] == rid
