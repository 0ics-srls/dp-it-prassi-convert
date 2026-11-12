"""Estremi (number and year) that an act of prassi DECLARES about itself (port of EstremiDichiarati / ConEstremiDellAtto of the branch-53 legacy).

The act is the oracle of its own number: an interpello opens with "Risposta n. 118/2022" and a circolare with "CIRCOLARE N. 3/E", and that is its number -
the file name is only a hint. The number must follow the formula immediately: the subject of every interpello cites "legge 27 luglio 2000, n. 212" and that
number is the LAW, not the act. An act that declares nothing is not accused (1,509 legacy interpelli carry no formula).

ONE pattern lives here and is exposed as ``PATTERN_SQL`` so that the SQL control of the ingest tests uses the very same regular expression.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date  # noqa: TC003 - dataclass field type

# Risposta n. 118/2022, CIRCOLARE N. 3/E, Prot. n. 120706/2023, Interpello n. 3. The asterisks are markdown noise of the PDF conversion.
PATTERN_SQL = r"(?:Risposta|CIRCOLARE|RISOLUZIONE|Interpello|Prot\.)\s*n\.?\s*\*{0,2}\s*(\d{1,7})\s*(?:/\s*(\d{4}|[A-Z]))?"
_ESTREMI = re.compile(PATTERN_SQL, re.IGNORECASE)
_YEAR_DIGITS = 4


@dataclass(frozen=True)
class EstremiAtto:
    """The number (and the year, when printed next to it) an act declares."""

    numero: int
    anno: int | None


@dataclass(frozen=True)
class Registrato:
    """What the grab and the file name registered about a document, before the act corrects it."""

    numero: str | None
    anno: int | None
    data: date | None
    text_raw: str


def leggi(text: str | None) -> EstremiAtto | None:
    """The declared estremi of the act, or None when it declares none."""
    if not text or not text.strip():
        return None
    match = _ESTREMI.search(text)
    if match is None:
        return None
    suffix = match.group(2)
    anno = int(suffix) if suffix is not None and len(suffix) == _YEAR_DIGITS else None
    return EstremiAtto(numero=int(match.group(1)), anno=anno)


def anno_coerente(data: date | None, anno_registrato: int | None) -> int | None:
    """The year of the date when the act has a date, else what was registered."""
    return data.year if data is not None else anno_registrato


def anno_dell_atto(dichiarati: EstremiAtto | None, data: date | None, anno_registrato: int | None) -> int | None:
    """The year of the act: the DATE wins, then the year declared next to the number, then the registered one.

    The interpello of 18 June 2021 headed "Risposta n. 417/2020" is a typo of the Agency; a date is a fact of the act and does not suffer typos.
    """
    if data is not None:
        return data.year
    if dichiarati is not None and dichiarati.anno is not None:
        return dichiarati.anno
    return anno_registrato


def con_estremi_dell_atto(registrato: Registrato) -> Registrato:
    """Correct number and year from the act itself. Two independent rules: the number only when the act declares it, the year whenever a date exists."""
    dichiarati = leggi(registrato.text_raw)
    numero = registrato.numero if dichiarati is None else str(dichiarati.numero)
    anno = anno_dell_atto(dichiarati, registrato.data, registrato.anno)
    if numero == registrato.numero and anno == registrato.anno:
        return registrato
    return replace(registrato, numero=numero, anno=anno)
