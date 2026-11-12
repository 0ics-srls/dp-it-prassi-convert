"""URN:NIR mappers: ports of the legacy NormaUrnMapper.TryMap and FiscalNormaRefMapper.TryMap.

The ``try_map_urn`` rules are the ones of dp-it-giurisprudenza-convert (norme.py): the Corte costituzionale registries and the prassi references must join the
same it-normativa URNs, and a shared golden file (tests/fixtures/urn-golden.json) keeps the two classes in step. Unknown or incomplete input gives None; the
raw citation is preserved upstream regardless. The article token is kept whole (``~art19-bis``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

_KNOWN_TYPES = {
    "legge": "legge",
    "decreto legislativo": "decreto.legislativo",
    "decreto-legge": "decreto.legge",
    "decreto legge": "decreto.legge",
    "d.p.r.": "decreto.del.presidente.della.repubblica",
    "decreto del presidente della repubblica": "decreto.del.presidente.della.repubblica",
}
_DPR = "decreto.del.presidente.della.repubblica"


@dataclass(frozen=True)
class FiscalAct:
    """A well-known fiscal act recognised by alias or by number and year."""

    kind: str
    date: str
    numero: str
    anno: int
    aliases: tuple[str, ...]

    @property
    def base_urn(self) -> str:
        """URN of the whole act, without article."""
        return f"urn:nir:stato:{self.kind}:{self.date};{self.numero}"


FISCAL_ACTS: tuple[FiscalAct, ...] = (
    FiscalAct(_DPR, "1986-12-22", "917", 1986, ("tuir",)),
    FiscalAct(_DPR, "1972-10-26", "633", 1972, ("decreto iva", "iva")),
    FiscalAct(_DPR, "1986-04-26", "131", 1986, ("imposta di registro", "registro")),
    FiscalAct(_DPR, "1973-09-29", "600", 1973, ("accertamento",)),
    FiscalAct("legge", "2000-07-27", "212", 2000, ("statuto del contribuente", "statuto contribuente")),
)
_ARTICLE_IN_TEXT = re.compile(r"art(?:icolo)?\.?\s*(\d+)", re.IGNORECASE)
_NUM_ANNO = re.compile(r"(\d{1,4})\s*/\s*(\d{4})")
_KIND_OF_TIPO = {"d.p.r.": _DPR, "decreto del presidente della repubblica": _DPR, "legge": "legge"}


def try_map_urn(descrizione: str | None, data: str | None, numero: str | None, articolo: str | None) -> str | None:
    """Best-effort URN:NIR of an act given its type, date (dd/MM/yyyy), number and optional article."""
    if not descrizione or not descrizione.strip():
        return None
    kind = _KNOWN_TYPES.get(descrizione.strip().lower())
    if kind is None or not numero or not numero.strip() or not data or not data.strip():
        return None
    try:
        date = datetime.strptime(data.strip(), "%d/%m/%Y").date()  # noqa: DTZ007 - a calendar date, no time zone involved
    except ValueError:
        return None
    urn = f"urn:nir:stato:{kind}:{date.isoformat()};{numero.strip()}"
    if articolo and articolo.strip():
        urn += f"~art{articolo.strip()}"
    return urn


def try_map_fiscal(descrizione: str | None, articolo: str | None = None) -> str | None:
    """Port of FiscalNormaRefMapper.TryMap: a free-text reference (alias or "n/anno") plus an optional article to a URN of a well-known fiscal act."""
    if not descrizione or not descrizione.strip():
        return None
    article = articolo
    if not article or not article.strip():
        found = _ARTICLE_IN_TEXT.search(descrizione)
        article = found.group(1) if found else None

    act: FiscalAct | None = None
    number_year = _NUM_ANNO.search(descrizione)
    if number_year:
        numero, anno = number_year.group(1), int(number_year.group(2))
        act = next((a for a in FISCAL_ACTS if a.numero == numero and a.anno == anno), None)
    if act is None:
        low = descrizione.lower()
        act = next((a for a in FISCAL_ACTS if any(alias in low for alias in a.aliases)), None)
    if act is None:
        return None
    return act.base_urn + (f"~art{article.strip()}" if article and article.strip() else "")


def fiscal_act_by_number(kind: str, numero: str, anno: int) -> str | None:
    """URN of the fiscal act with this number and year when the citation type matches ("d.p.r." or "legge"), else None."""
    wanted = _KIND_OF_TIPO.get(kind.lower())
    if wanted is None:
        return None
    act = next((a for a in FISCAL_ACTS if a.numero == numero and a.anno == anno and a.kind == wanted), None)
    return act.base_urn if act else None
