"""The plan of one PDF: what the ingest step loads (plan schema v1, ``plan.schema.json``).

Order of operations: sidecar of the grab -> text layer of the PDF -> OCR when the layer is not a document (``estrazione = ocr``) -> estremi corrected by the
act itself -> norm references -> checks. A document that cannot be turned into text is NOT written with an empty ``text_raw``: the plan carries
``documento = null`` and the reason in ``skipped`` (``pdf_unreadable``, ``ocr_empty``, ``contenuto_vuoto``) - the corpus never holds a ghost.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

from dp_it_prassi_convert import estremi, meta, pdftext, riferimenti
from dp_it_prassi_convert import ocr as ocr_mod

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

PLAN_VERSION = 1
DEFAULT_ENTE = "Agenzia delle Entrate"
FORM_FEED = "\x0c"


@dataclass
class Plan:
    """One plan file."""

    documento: dict[str, Any] | None = None
    riferimenti: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"version": PLAN_VERSION, "documento": self.documento, "riferimenti": self.riferimenti, "skipped": self.skipped, "warnings": self.warnings}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=False)


def _skip(stem: str, reason: str) -> Plan:
    return Plan(skipped=[{"item_ref": stem, "reason": reason}])


def _coerenza_warnings(pdf: Path, resolved: meta.Resolved, text: str, data: date | None) -> list[str]:
    """COERENZA-DATA: a year that contradicts the date of the act is repaired from the date, and counted."""
    if data is None:
        return []
    warnings: list[str] = []
    named = meta.meta_from_name(pdf.name).anno
    if named is not None and named != data.year and resolved.fonte != "doctrib":
        warnings.append(f"coerenza-data: anno {named} della fonte riparato con la data {data.isoformat()}")
    declared = estremi.leggi(text)
    if declared is not None and declared.anno is not None and declared.anno != data.year:
        warnings.append(f"coerenza-data: anno {declared.anno} dichiarato dall'atto riparato con la data {data.isoformat()}")
    return warnings


def _source_number_disagreement(resolved: meta.Resolved, text: str, estrazione: str) -> str | None:
    """The warning when the source gives a number and the act declares another one (the source number is kept), else None."""
    if not resolved.numero_da_fonte or resolved.numero is None:
        return None
    declared = estremi.leggi(text)
    head = re.match(r"\d+", resolved.numero)
    if declared is None or (head is not None and int(head.group(0)) == declared.numero):
        return None
    return (
        f"estremi: numero {declared.numero} letto dall'atto ({estrazione}) differisce dal numero della fonte {resolved.numero}; vale quello della fonte"
    )


def build_plan(
    pdf: Path,
    *,
    fonte: str | None = None,
    ocr: Callable[[Path], str] = ocr_mod.ocr_pdf,
    extract: Callable[[Path], str] = pdftext.extract_text,
) -> Plan:
    """The plan of one PDF. ``fonte`` is the Source kind (``doctrib``) when no sidecar says it. ``OcrUnavailable`` propagates: the image is broken."""
    stem = pdf.name.removesuffix(".pdf").removesuffix(".PDF")
    try:
        text = extract(pdf)
    except pdftext.PdfUnreadable:
        return _skip(stem, "pdf_unreadable")
    estrazione = "testo"
    if ocr_mod.needs_ocr(text):
        try:
            text = pdftext.clean_text(ocr(pdf).replace(FORM_FEED, "\n\n"))
        except (ocr_mod.OcrEmpty, ocr_mod.OcrFailed):
            return _skip(stem, "ocr_empty")
        estrazione = "ocr"
    if not text.strip():
        return _skip(stem, "contenuto_vuoto")

    resolved = meta.resolve(pdf, text, fonte)
    data = date.fromisoformat(resolved.data) if resolved.data else None
    disagreement = _source_number_disagreement(resolved, text, estrazione)
    # F2: the number of the source metadata wins over the number read from the text; the act only corrects a number that came from a guess (file name, header)
    corrected = estremi.con_estremi_dell_atto(estremi.Registrato(resolved.numero, resolved.anno, data, "" if disagreement else text))
    warnings = _coerenza_warnings(pdf, resolved, text, data)
    if disagreement:
        warnings.append(disagreement)
    documento = {
        "ente": resolved.ente or DEFAULT_ENTE,
        "struttura": resolved.struttura,
        "tipo": resolved.tipo.lower(),
        "numero": corrected.numero,
        "anno": corrected.anno,
        "data": resolved.data,
        "oggetto": resolved.oggetto or None,
        "text_raw": text,
        "estrazione": estrazione,
        "fonte": resolved.fonte,
        "source_id": resolved.source_id,
        "source_url": resolved.source_url,
    }
    refs = [
        {"ord": r.ord, "descrizione": r.descrizione, "articolo": r.articolo, "comma": r.comma, "norma_urn": r.norma_urn, "via": r.via}
        for r in riferimenti.extract_riferimenti(text)
    ]
    return Plan(documento=documento, riferimenti=refs, warnings=warnings)

