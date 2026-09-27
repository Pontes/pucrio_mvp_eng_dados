"""Faixa etária em intervalos de 10 anos (LGPD: sem data de nascimento na saída)."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime

_DMY = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def parse_data(value: str | None) -> date | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    m = _DMY.match(s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    m = _ISO.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    for fmt in ("%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def ref_date_from_competencia(competencia: str | None) -> date | None:
    """Último dia do mês YYYY-MM (referência para idade no cadastro)."""
    if not competencia:
        return None
    s = str(competencia).strip()
    if len(s) < 7 or s[4] != "-":
        return None
    try:
        y, m = int(s[:4]), int(s[5:7])
        last = calendar.monthrange(y, m)[1]
        return date(y, m, last)
    except ValueError:
        return None


def idade_em_anos(nascimento: date, referencia: date) -> int | None:
    if nascimento > referencia:
        return None
    years = referencia.year - nascimento.year
    if (referencia.month, referencia.day) < (nascimento.month, nascimento.day):
        years -= 1
    return years if years >= 0 else None


def faixa_etaria_dez_anos(idade: int | None) -> str | None:
    """0-9, 10-19, …, 80-89, 90+."""
    if idade is None or idade < 0:
        return None
    if idade >= 90:
        return "90+"
    low = (idade // 10) * 10
    return f"{low}-{low + 9}"


def faixa_etaria_from_dt_nasc(
    dt_nasc: str | None,
    competencia_ref: str | None,
) -> str | None:
    born = parse_data(dt_nasc)
    ref = ref_date_from_competencia(competencia_ref)
    if born is None or ref is None:
        return None
    return faixa_etaria_dez_anos(idade_em_anos(born, ref))
