"""Metadata of a prassi PDF: what the grab knows (sidecar), the file name, the header of the act (port of the lexcrps-prassi-extract functions).

Order of trust: sidecar written by the grab > file name > header of the act. The type of a document is not in the PDF: it is in the page it came from.
The identity (``source_id``) is the PDF stem for the AdE portal and the DocTrib GUID for interpelli.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

MONTHS: dict[str, int] = {
    m: i
    for i, m in enumerate(
        ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"], 1
    )
}
_MONTH_ALT = "|".join(MONTHS)
MAX_OGGETTO = 500
_DOCTRIB_NAME = re.compile(r"^(?P<tipo>[^_]+)_(?P<data>\d{4}-\d{2}-\d{2})_(?P<numero>[^_]+)__(?P<guid>[0-9A-Fa-f-]{36})$")
_NUM_N = re.compile(r"n[.°_ +]*(\d{1,3})(?!\d)")
_NUM_AFTER_TIPO = re.compile(r"(?:circolare|risoluzione|provvedimento)[ _+]+(\d{1,3})(?!\d)")
_DATE_WORDS = re.compile(r"(\d{1,2})[ _](" + _MONTH_ALT + r")[ _](\d{4})")
_DATE_NUMERIC = re.compile(r"(\d{1,2})[._](\d{1,2})[._](\d{4})")
_YEAR_ALONE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
_HEADER_NUM = re.compile(r"(?:circolare|risoluzione|provvedimento)\s+n[.°]?\s*(\d{1,3})(?:\s*/\s*([A-Za-z]))?", re.IGNORECASE)
_DATELINE_WORDS = re.compile(r"roma[,.\s]+(\d{1,2})°?\s*(" + _MONTH_ALT + r")\s+(20\d{2})")
_DATELINE_NUMERIC = re.compile(r"roma[,.\s]+(\d{1,2})[/.](\d{1,2})[/.](20\d{2})")
_DATELINE_YEAR = re.compile(r"roma[,.\s]+\d{1,2}°?\s*\S+\s+(20\d{2})")
_HEADER_CHARS = 1500


@dataclass(frozen=True)
class NameMeta:
    """Best-effort metadata read from a file name."""

    tipo: str
    numero: str | None
    anno: int | None
    data: str | None


@dataclass(frozen=True)
class HeaderMeta:
    """Metadata read from the dateline and number formula at the top of the act."""

    numero: str | None
    anno: int | None
    data: str | None


@dataclass(frozen=True)
class SidecarMeta:
    """What the grab wrote next to the PDF (``<file>.meta.json``). Every field is optional."""

    kind: str | None
    tipo: str | None
    numero: str | None
    anno: int | None
    data: str | None
    titolo: str | None
    source_url: str | None
    source_id: str | None
    struttura: str | None
    fonte: str | None
    ente: str | None


@dataclass(frozen=True)
class DoctribName:
    """Identity read from ``{tipo}_{yyyy-MM-dd}_{numero|nd}__{guid}.pdf``."""

    tipo: str
    numero: str | None
    anno: int
    data: str
    source_id: str


@dataclass(frozen=True)
class Resolved:
    """The metadata of one document after the three sources have been merged."""

    tipo: str
    numero: str | None
    anno: int | None
    data: str | None
    oggetto: str
    source_id: str
    source_url: str | None
    struttura: str | None
    fonte: str
    ente: str | None


def _iso(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def meta_from_name(name: str) -> NameMeta:
    """Type, number, year and date parsed from the file name."""
    low = name.lower()
    if "circolare" in low or low.startswith("circ"):
        tipo = "circolare"
    elif "provvedimento" in low or low.startswith("provv"):
        tipo = "provvedimento"
    elif "ris" in low:
        tipo = "risoluzione"
    else:
        tipo = "ignoto"

    num_match = _NUM_N.search(low) or _NUM_AFTER_TIPO.search(low)
    numero = num_match.group(1) if num_match else None

    data: str | None = None
    words = _DATE_WORDS.search(low)
    if words:
        data = _iso(int(words.group(3)), MONTHS[words.group(2)], int(words.group(1)))
    else:
        numeric = _DATE_NUMERIC.search(low)
        if numeric:
            data = _iso(int(numeric.group(3)), int(numeric.group(2)), int(numeric.group(1)))

    # a year NOT embedded in a longer digit run: "22072019" is 22-07-2019 and must not yield "2072"
    year = _YEAR_ALONE.search(low)
    return NameMeta(tipo=tipo, numero=numero, anno=int(year.group(1)) if year else None, data=data)


def meta_from_text(text: str) -> HeaderMeta:
    """Number and date from the header of the act. Conservative: the date is read only from the "Roma," dateline, never from the body."""
    head = text[:_HEADER_CHARS]
    numero: str | None = None
    number = _HEADER_NUM.search(head)
    if number:
        numero = number.group(1) + ("/" + number.group(2).upper() if number.group(2) else "")

    low = head.lower()
    data: str | None = None
    anno: int | None = None
    words = _DATELINE_WORDS.search(low)
    if words:
        data = _iso(int(words.group(3)), MONTHS[words.group(2)], int(words.group(1)))
        anno = int(words.group(3))
    else:
        numeric = _DATELINE_NUMERIC.search(low)
        if numeric:
            data = _iso(int(numeric.group(3)), int(numeric.group(2)), int(numeric.group(1)))
            anno = int(numeric.group(3))
        else:
            # the year of the dateline is reliable even when the month is mangled by the conversion ("20 0ttobre 2025"); the date stays unknown
            year = _DATELINE_YEAR.search(low)
            if year:
                anno = int(year.group(1))
    return HeaderMeta(numero=numero, anno=anno, data=data)


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def meta_from_sidecar(pdf_path: Path | str) -> SidecarMeta | None:
    """The sidecar of the grab, or None when it is missing or unreadable (a broken sidecar never stops the extraction)."""
    path = Path(str(pdf_path) + ".meta.json")
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if not isinstance(raw, dict):
        return None
    tipo = _text(raw.get("tipo"))
    numero = raw.get("numero")
    data = _text(raw.get("data"))
    anno = int(data[:4]) if data is not None and len(data) >= 4 and data[:4].isdigit() else None  # noqa: PLR2004
    return SidecarMeta(
        kind=_text(raw.get("kind")),
        tipo=tipo.lower() if tipo else None,
        numero=str(numero) if numero is not None and str(numero).strip() else None,
        anno=anno,
        data=data,
        titolo=_text(raw.get("titolo")),
        source_url=_text(raw.get("sourceUrl")),
        source_id=_text(raw.get("sourceId")),
        struttura=_text(raw.get("struttura")),
        fonte=_text(raw.get("fonte")),
        ente=_text(raw.get("ente")),
    )


def meta_doctrib(name: str) -> DoctribName:
    """Identity from the DocTrib file name written by the grab; raises ValueError for any other name."""
    match = _DOCTRIB_NAME.match(Path(name).stem)
    if not match:
        msg = f"doctrib file name not recognised: {name}"
        raise ValueError(msg)
    numero = match.group("numero")
    data = match.group("data")
    return DoctribName(
        tipo=match.group("tipo").lower(),
        numero=None if numero == "nd" else numero,
        anno=int(data[:4]),
        data=data,
        source_id=match.group("guid"),
    )


def oggetto(text: str) -> str:
    """Subject: the "OGGETTO:" line, else the first non-empty line, at most 500 characters."""
    for line in text.splitlines():
        if "oggetto" in line.lower():
            cleaned = re.sub(r"[#*_>`]", "", line).strip()
            found = re.search(r"oggetto\s*[:\-]?\s*(.*)", cleaned, re.IGNORECASE)
            subject = found.group(1).strip() if found and found.group(1).strip() else cleaned
            return subject[:MAX_OGGETTO]
    for line in text.splitlines():
        cleaned = re.sub(r"[#*_>`]", "", line).strip()
        if cleaned:
            return cleaned[:MAX_OGGETTO]
    return ""


def resolve(pdf_path: Path | str, text: str, fonte: str | None = None) -> Resolved:
    """Merge sidecar, file name and header into the metadata of one document; ``fonte`` is the Source kind when the sidecar does not say."""
    path = Path(pdf_path)
    sidecar = meta_from_sidecar(path)
    declared_fonte = (sidecar.fonte if sidecar else None) or fonte
    is_doctrib = declared_fonte == "doctrib" or (sidecar is not None and sidecar.kind == "doctrib")

    if is_doctrib:
        try:
            named: DoctribName | None = meta_doctrib(path.name)
        except ValueError:
            named = None
        if named is None and (sidecar is None or sidecar.source_id is None):
            msg = f"doctrib document without identity: {path.name}"
            raise ValueError(msg)
        tipo = (sidecar.tipo if sidecar else None) or (named.tipo if named else "interpello")
        numero = (sidecar.numero if sidecar else None) or (named.numero if named else None)
        data = (sidecar.data if sidecar else None) or (named.data if named else None)
        anno = (sidecar.anno if sidecar else None) or (named.anno if named else None)
        source_id = (sidecar.source_id if sidecar else None) or (named.source_id if named else path.stem)
        subject = (sidecar.titolo if sidecar else None) or oggetto(text)
        return Resolved(tipo.lower(), numero, anno, data, subject, source_id, sidecar.source_url if sidecar else None,
                        sidecar.struttura if sidecar else None, "doctrib", sidecar.ente if sidecar else None)

    name = meta_from_name(path.name)
    tipo = (sidecar.tipo if sidecar and sidecar.tipo else None) or name.tipo
    numero = (sidecar.numero if sidecar else None) or name.numero
    anno = (sidecar.anno if sidecar else None) or name.anno
    data = (sidecar.data if sidecar else None) or name.data
    if numero is None or anno is None or data is None:
        header = meta_from_text(text)
        numero = numero or header.numero
        anno = anno or header.anno
        data = data or header.data
    source_id = (sidecar.source_id if sidecar else None) or path.stem
    subject = oggetto(text) or ((sidecar.titolo if sidecar else None) or "")
    return Resolved(tipo.lower(), numero, anno, data, subject, source_id, sidecar.source_url if sidecar else None,
                    sidecar.struttura if sidecar else None, declared_fonte or "ade-portale", sidecar.ente if sidecar else None)
