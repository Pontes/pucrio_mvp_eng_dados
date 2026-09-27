"""Regras de identidade para paciente_id / profissional_id."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

_DIGITS = re.compile(r"\D+")


def only_digits(value: str | None) -> str:
    if value is None:
        return ""
    return _DIGITS.sub("", str(value).strip())


def normalize_cpf(value: str | None) -> str | None:
    """CPF com 11 dígitos; rejeita sequências inválidas óbvias."""
    d = only_digits(value)
    if len(d) != 11:
        return None
    if d == d[0] * 11:
        return None
    return d


def normalize_cns(value: str | None) -> str | None:
    """CNS com 15 dígitos; rejeita zeros/repetição total."""
    d = only_digits(value)
    if len(d) != 15:
        return None
    if d == d[0] * 15:
        return None
    return d


def normalize_src_id(value: str | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"none", "null", "nan"}:
        return None
    return s


def normalize_cnes(value: str | None) -> str | None:
    d = only_digits(value)
    if not d:
        s = (str(value).strip() if value is not None else "")
        return s or None
    return d


def normalize_nome(value: str | None) -> str | None:
    """Nome normalizado só para mapa local (lookup); não é chave preferencial."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s).upper()
    return s or None


def normalize_login(value: str | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s or s in {"none", "null", "nan"}:
        return None
    return s


def normalize_conselho(uf: str | None, numero: str | None) -> str | None:
    u = (str(uf).strip().upper() if uf is not None else "")
    n = only_digits(numero)
    if not u or not n:
        return None
    return f"{u}:{n}"


@dataclass
class IdentityConflict:
    motivo_codigo: str
    paciente_id_a: str | None
    paciente_id_b: str | None
    chave_tipo: str | None
    detalhe: str | None = None


@dataclass
class IdentityResolver:
    """Resolve paciente_id por CPF → CNS → src_id → orphan_row.

    Não une por nome. Conflitos vão para fila sem descartar a linha.
    """

    _next: int = 1
    by_cpf: dict[str, str] = field(default_factory=dict)
    by_cns: dict[str, str] = field(default_factory=dict)
    by_src: dict[str, str] = field(default_factory=dict)
    regra_origem: dict[str, str] = field(default_factory=dict)
    conflicts: list[IdentityConflict] = field(default_factory=list)

    def _new_id(self, regra: str) -> str:
        pid = f"P{self._next:06d}"
        self._next += 1
        self.regra_origem[pid] = regra
        return pid

    def _prefer(self, candidates: Iterable[str]) -> str:
        ordered = list(dict.fromkeys(candidates))
        if len(ordered) == 1:
            return ordered[0]

        def rank(pid: str) -> int:
            regra = self.regra_origem.get(pid, "")
            return {"cpf": 0, "cns": 1, "src_id": 2, "orphan_row": 3}.get(regra, 9)

        ordered.sort(key=rank)
        winner = ordered[0]
        for other in ordered[1:]:
            self.conflicts.append(
                IdentityConflict(
                    motivo_codigo="Q_IDENTIDADE_CANDIDATOS_MULTIPLOS",
                    paciente_id_a=winner,
                    paciente_id_b=other,
                    chave_tipo=None,
                    detalhe="mesma linha aponta para paciente_id distintos",
                )
            )
        return winner

    def _bind(self, store: dict[str, str], key: str, pid: str, chave_tipo: str) -> None:
        existing = store.get(key)
        if existing is None:
            store[key] = pid
            return
        if existing != pid:
            self.conflicts.append(
                IdentityConflict(
                    motivo_codigo="Q_CHAVE_JA_MAPEADA",
                    paciente_id_a=existing,
                    paciente_id_b=pid,
                    chave_tipo=chave_tipo,
                    detalhe="chave já associada a outro paciente_id",
                )
            )

    def resolve(
        self,
        *,
        cpf: str | None,
        cns: str | None,
        src_id: str | None,
        row_id: int | None = None,
    ) -> str:
        n_cpf = normalize_cpf(cpf)
        n_cns = normalize_cns(cns)
        n_src = normalize_src_id(src_id)

        candidates: list[str] = []
        if n_cpf and n_cpf in self.by_cpf:
            candidates.append(self.by_cpf[n_cpf])
        if n_cns and n_cns in self.by_cns:
            candidates.append(self.by_cns[n_cns])
        if n_src and n_src in self.by_src:
            candidates.append(self.by_src[n_src])

        if candidates:
            pid = self._prefer(candidates)
        elif n_cpf:
            pid = self._new_id("cpf")
        elif n_cns:
            pid = self._new_id("cns")
        elif n_src:
            pid = self._new_id("src_id")
        else:
            pid = self._new_id("orphan_row")
            if row_id is not None:
                self._bind(self.by_src, f"orphan:{row_id}", pid, "orphan_row")

        if n_cpf:
            self._bind(self.by_cpf, n_cpf, pid, "cpf")
        if n_cns:
            self._bind(self.by_cns, n_cns, pid, "cns")
        if n_src:
            self._bind(self.by_src, n_src, pid, "src_id")

        return pid

    def maps_for_persist(self) -> list[tuple[str, str, str, str]]:
        rows: list[tuple[str, str, str, str]] = []
        for cpf, pid in self.by_cpf.items():
            rows.append(("cpf", cpf, pid, self.regra_origem.get(pid, "cpf")))
        for cns, pid in self.by_cns.items():
            rows.append(("cns", cns, pid, self.regra_origem.get(pid, "cns")))
        for src, pid in self.by_src.items():
            tipo = "orphan_row" if src.startswith("orphan:") else "src_id"
            rows.append((tipo, src, pid, self.regra_origem.get(pid, tipo)))
        return rows


@dataclass
class ProfissionalConflict:
    motivo_codigo: str
    profissional_id_a: str | None
    profissional_id_b: str | None
    chave_tipo: str | None
    detalhe: str | None = None


@dataclass
class ProfissionalResolver:
    """Resolve profissional_id (R######) por CPF → CNS → login → conselho → nome → orphan.

    O nome entra como chave fraca (necessária para ligar consultas).
    """

    _next: int = 1
    by_cpf: dict[str, str] = field(default_factory=dict)
    by_cns: dict[str, str] = field(default_factory=dict)
    by_login: dict[str, str] = field(default_factory=dict)
    by_conselho: dict[str, str] = field(default_factory=dict)
    by_nome: dict[str, str] = field(default_factory=dict)
    regra_origem: dict[str, str] = field(default_factory=dict)
    conflicts: list[ProfissionalConflict] = field(default_factory=list)

    def _new_id(self, regra: str) -> str:
        rid = f"R{self._next:06d}"
        self._next += 1
        self.regra_origem[rid] = regra
        return rid

    def _prefer(self, candidates: Iterable[str]) -> str:
        ordered = list(dict.fromkeys(candidates))
        if len(ordered) == 1:
            return ordered[0]

        def rank(rid: str) -> int:
            regra = self.regra_origem.get(rid, "")
            return {
                "cpf": 0,
                "cns": 1,
                "login": 2,
                "conselho": 3,
                "nome": 4,
                "orphan_row": 5,
            }.get(regra, 9)

        ordered.sort(key=rank)
        winner = ordered[0]
        for other in ordered[1:]:
            self.conflicts.append(
                ProfissionalConflict(
                    motivo_codigo="Q_IDENTIDADE_CANDIDATOS_MULTIPLOS",
                    profissional_id_a=winner,
                    profissional_id_b=other,
                    chave_tipo=None,
                    detalhe="mesma linha aponta para profissional_id distintos",
                )
            )
        return winner

    def _bind(self, store: dict[str, str], key: str, rid: str, chave_tipo: str) -> None:
        existing = store.get(key)
        if existing is None:
            store[key] = rid
            return
        if existing != rid:
            self.conflicts.append(
                ProfissionalConflict(
                    motivo_codigo="Q_CHAVE_JA_MAPEADA",
                    profissional_id_a=existing,
                    profissional_id_b=rid,
                    chave_tipo=chave_tipo,
                    detalhe="chave já associada a outro profissional_id",
                )
            )

    def resolve(
        self,
        *,
        cpf: str | None,
        cns: str | None,
        login: str | None,
        nome: str | None,
        uf_conselho: str | None = None,
        numero_conselho: str | None = None,
        row_id: int | None = None,
    ) -> str:
        n_cpf = normalize_cpf(cpf)
        n_cns = normalize_cns(cns)
        n_login = normalize_login(login)
        n_conselho = normalize_conselho(uf_conselho, numero_conselho)
        n_nome = normalize_nome(nome)

        candidates: list[str] = []
        if n_cpf and n_cpf in self.by_cpf:
            candidates.append(self.by_cpf[n_cpf])
        if n_cns and n_cns in self.by_cns:
            candidates.append(self.by_cns[n_cns])
        if n_login and n_login in self.by_login:
            candidates.append(self.by_login[n_login])
        if n_conselho and n_conselho in self.by_conselho:
            candidates.append(self.by_conselho[n_conselho])
        if n_nome and n_nome in self.by_nome:
            candidates.append(self.by_nome[n_nome])

        if candidates:
            rid = self._prefer(candidates)
        elif n_cpf:
            rid = self._new_id("cpf")
        elif n_cns:
            rid = self._new_id("cns")
        elif n_login:
            rid = self._new_id("login")
        elif n_conselho:
            rid = self._new_id("conselho")
        elif n_nome:
            rid = self._new_id("nome")
        else:
            rid = self._new_id("orphan_row")
            if row_id is not None:
                self._bind(self.by_login, f"orphan:{row_id}", rid, "orphan_row")

        if n_cpf:
            self._bind(self.by_cpf, n_cpf, rid, "cpf")
        if n_cns:
            self._bind(self.by_cns, n_cns, rid, "cns")
        if n_login:
            self._bind(self.by_login, n_login, rid, "login")
        if n_conselho:
            self._bind(self.by_conselho, n_conselho, rid, "conselho")
        if n_nome:
            self._bind(self.by_nome, n_nome, rid, "nome")

        return rid

    def maps_for_persist(self) -> list[tuple[str, str, str, str]]:
        rows: list[tuple[str, str, str, str]] = []
        for cpf, rid in self.by_cpf.items():
            rows.append(("cpf", cpf, rid, self.regra_origem.get(rid, "cpf")))
        for cns, rid in self.by_cns.items():
            rows.append(("cns", cns, rid, self.regra_origem.get(rid, "cns")))
        for login, rid in self.by_login.items():
            tipo = "orphan_row" if login.startswith("orphan:") else "login"
            rows.append((tipo, login, rid, self.regra_origem.get(rid, tipo)))
        for conselho, rid in self.by_conselho.items():
            rows.append(
                ("conselho", conselho, rid, self.regra_origem.get(rid, "conselho"))
            )
        for nome, rid in self.by_nome.items():
            rows.append(("nome", nome, rid, self.regra_origem.get(rid, "nome")))
        return rows
