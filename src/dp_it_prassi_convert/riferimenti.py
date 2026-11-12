"""Anchored extraction of the norm references an act of prassi cites (P80-09).

The legacy regex took generic fragments ("legge", "decreto"): 6,547 rows, none with a URN, so ``su_norma`` was dead. Here a reference is emitted only when it is
anchored: (1) "<tipo> <d> <mese> <yyyy>, n. <N>" (also "<tipo> n. <N> del <d> <mese> <yyyy>"), (2) "<tipo> n. <N> del <yyyy>" / "<tipo> n. <N>/<yyyy>",
(3) a named act (TUIR, decreto IVA, Statuto del contribuente), (4) an article ("art. 19", "articolo 11, comma 2", "artt. 5 e 6") that precedes one of those
acts within 80 characters in the same clause - the article attaches to the act, never to a generic noun. The raw citation is always kept; the URN only when it
is unambiguous. All quantifiers are bounded, so a 400 KB text is scanned in linear time.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, replace

from dp_it_prassi_convert.meta import MONTHS
from dp_it_prassi_convert.urn import fiscal_act_by_number, try_map_fiscal, try_map_urn

MAX_RIFERIMENTI = 60
MAX_GAP = 80
MAX_PLAUSIBLE_ARTICLE = 999  # "articoli 8 e 1020" is "10" with a footnote mark "20" glued by the PDF text layer
MAX_PLAUSIBLE_NUMBER = 1500  # acts of a year are numbered well below this; a larger number is a footnote mark glued to the number
_MONTH = "|".join(MONTHS)
_TIPO = (
    r"decreto[\s-]+legislativo|d\.\s?lgs\.?|decreto[\s-]+legge|d\.\s?l\.|"
    r"decreto\s+del\s+presidente\s+della\s+repubblica|d\.?\s?p\.?\s?r\b\.?|legge"
)
_FLAGS = re.IGNORECASE
_NUMBER = r"n\s?[.°]\s?(?P<n>\d{1,4})"
_DATE = rf"(?P<g>\d{{1,2}})\s?°?\s+(?P<m>{_MONTH})\s+(?P<a>\d{{4}})"
_P_DATED = re.compile(rf"\b(?P<tipo>{_TIPO})\s{{1,3}}(?:del\s+)?{_DATE}\s?,?\s{{0,3}}{_NUMBER}", _FLAGS)
_P_NUMBER_DATED = re.compile(rf"\b(?P<tipo>{_TIPO})\s{{1,3}}{_NUMBER}\s{{1,3}}del\s+{_DATE}", _FLAGS)
_P_NUMBER_YEAR = re.compile(rf"\b(?P<tipo>{_TIPO})\s{{1,3}}{_NUMBER}\s?(?:/\s?|\s{{1,3}}del\s+)(?P<y>\d{{4}})\b", _FLAGS)
_ALIASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bT\.?U\.?I\.?R\b\.?", _FLAGS), "tuir"),
    (re.compile(r"\btesto\s+unico\s+delle\s+imposte\s+sui\s+redditi\b", _FLAGS), "tuir"),
    (re.compile(r"\b(?:decreto|d\.?\s?p\.?\s?r\b\.?)\s{1,3}IVA\b", _FLAGS), "decreto iva"),
    (re.compile(r"\bstatuto\s+(?:dei\s+diritti\s+)?del\s+contribuente\b", _FLAGS), "statuto del contribuente"),
)
_SUFFIX = r"(?:-(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies))?"
_ARTICLE_NUMBER = rf"\d{{1,4}}{_SUFFIX}"
_ARTICLE = re.compile(
    rf"\b(?:artt?\.|articol[oi])\s{{0,2}}(?P<list>{_ARTICLE_NUMBER}(?:\s{{0,2}}(?:,|e|ed)\s{{0,2}}{_ARTICLE_NUMBER}){{0,4}})"
    rf"(?:\s{{0,2}},?\s{{0,2}}comm[ai]\s{{1,2}}(?:da\s{{1,2}})?(?P<comma>\d{{1,3}})(?:\s{{0,2}}(?:,|e|ed|a)\s{{0,2}}\d{{1,3}}){{0,3}})?",
    _FLAGS,
)
_ARTICLE_TOKEN = re.compile(_ARTICLE_NUMBER, _FLAGS)
_DIGIT = re.compile(r"[0-9]")
_SENTENCE_END = re.compile(r"[.!?]\s+[A-ZÀ-Ý]")
_TIPO_NAMES = {
    "legge": "legge",
    "d.lgs": "decreto legislativo",
    "d. lgs": "decreto legislativo",
    "decreto legislativo": "decreto legislativo",
    "d.l": "decreto-legge",
    "d. l": "decreto-legge",
    "decreto legge": "decreto-legge",
    "decreto-legge": "decreto-legge",
    "d.p.r": "d.p.r.",
    "dpr": "d.p.r.",
    "decreto del presidente della repubblica": "d.p.r.",
}


@dataclass(frozen=True)
class Riferimento:
    """One cited norm: the raw citation, the article/comma it points to and the URN when it is unambiguous."""

    ord: int
    descrizione: str
    articolo: str | None
    comma: str | None
    norma_urn: str | None
    via: str


@dataclass(frozen=True)
class _Act:
    start: int
    end: int
    base_urn: str | None
    via: str
    tipo: str = ""
    numero: str = ""
    year: int | None = None
    date: str = ""


def _canonical_tipo(raw: str) -> str:
    key = re.sub(r"[\s-]+", " ", raw.lower()).strip().rstrip(".")
    key = key.replace("decreto legge", "decreto-legge") if key == "decreto legge" else key
    key = re.sub(r"\s+", "", key) if key.startswith(("d.", "dp")) else key
    return _TIPO_NAMES.get(key) or _TIPO_NAMES.get(key.replace(" ", ""), "legge")


def _acts(text: str) -> list[_Act]:
    found: list[_Act] = []
    for pattern in (_P_DATED, _P_NUMBER_DATED):
        for match in pattern.finditer(text):
            tipo = _canonical_tipo(match.group("tipo"))
            data = f"{int(match.group('g')):02d}/{MONTHS[match.group('m').lower()]:02d}/{match.group('a')}"
            found.append(_Act(match.start(), match.end(), None, "numero_data", tipo, match.group("n"), int(match.group("a")), data))
    found.extend(
        _Act(m.start(), m.end(), None, "numero_anno", _canonical_tipo(m.group("tipo")), m.group("n"), int(m.group("y"))) for m in _P_NUMBER_YEAR.finditer(text)
    )
    for pattern, alias in _ALIASES:
        found.extend(_Act(m.start(), m.end(), try_map_fiscal(alias), "alias") for m in pattern.finditer(text))
    # overlapping matches: the earliest wins, the longest on a tie (a dated citation beats the same words read as number/year)
    found.sort(key=lambda a: (a.start, -(a.end - a.start)))
    kept: list[_Act] = []
    for act in found:
        if kept and act.start < kept[-1].end:
            continue
        kept.append(act)
    return _resolve(kept)


def _resolve(acts: list[_Act]) -> list[_Act]:
    """Give every citation its URN. A footnote mark glued to a number ("n. 2851" for 285) is repaired from another citation of the same dated act,
    implausible numbers get no URN, and "n. 445 del 2000" takes the URN of the dated citation of the same act found elsewhere in the text."""
    dated = [a for a in acts if a.via == "numero_data"]
    numbers_by_act: dict[tuple[str, str], set[str]] = {}
    for act in dated:
        numbers_by_act.setdefault((act.tipo, act.date), set()).add(act.numero)

    def number_of(act: _Act) -> str:
        siblings = numbers_by_act.get((act.tipo, act.date), set())
        shorter = act.numero[:-1]
        return shorter if len(act.numero) > 1 and shorter in siblings else act.numero

    by_number_year: dict[tuple[str, str, int], str] = {}
    resolved: dict[int, _Act] = {}
    for act in dated:
        numero = number_of(act)
        urn = try_map_urn(act.tipo, act.date, numero, None) if int(numero) <= MAX_PLAUSIBLE_NUMBER else None
        resolved[act.start] = replace(act, numero=numero, base_urn=urn)
        if urn is not None and act.year is not None:
            by_number_year[(act.tipo, numero, act.year)] = urn
    out: list[_Act] = []
    for act in acts:
        if act.via == "numero_data":
            out.append(resolved[act.start])
        elif act.via == "numero_anno" and act.year is not None:
            urn = fiscal_act_by_number(act.tipo, act.numero, act.year) or by_number_year.get((act.tipo, act.numero, act.year))
            out.append(replace(act, base_urn=urn))
        else:
            out.append(act)
    return out


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" ,;")


def extract_riferimenti(text: str) -> list[Riferimento]:
    """The anchored references of the text in reading order, deduplicated by (urn or citation, articolo, comma), at most ``MAX_RIFERIMENTI``."""
    if not text:
        return []
    acts = _acts(text)
    starts = [a.start for a in acts]
    taken: set[int] = set()
    entries: list[tuple[int, str, str | None, str | None, str | None, str]] = []

    articles = list(_ARTICLE.finditer(text))
    for index, article in enumerate(articles):
        position = bisect.bisect_left(starts, article.end())
        if position >= len(acts) or position in taken:
            continue
        act = acts[position]
        gap = text[article.end() : act.start]
        next_article_start = articles[index + 1].start() if index + 1 < len(articles) else len(text) + 1
        if len(gap) > MAX_GAP or act.start > next_article_start or ";" in gap or _SENTENCE_END.search(gap) or _DIGIT.search(gap):
            continue
        taken.add(position)
        tokens = [t for t in (m.group(0).lower() for m in _ARTICLE_TOKEN.finditer(article.group("list"))) if int(t.split("-")[0]) <= MAX_PLAUSIBLE_ARTICLE]
        comma = article.group("comma") if len(tokens) == 1 else None
        citation = _clean(text[article.start() : act.end])
        entries.extend(
            (article.start(), citation, token, comma, act.base_urn + f"~art{token}" if act.base_urn else None, act.via) for token in tokens
        )

    for position, act in enumerate(acts):
        if position not in taken:
            entries.append((act.start, _clean(text[act.start : act.end]), None, None, act.base_urn, act.via))

    entries.sort(key=lambda e: e[0])
    seen: set[tuple[str, str | None, str | None]] = set()
    refs: list[Riferimento] = []
    for _, citation, articolo, comma, norma_urn, via in entries:
        key = (norma_urn or citation.lower(), articolo, comma)
        if key in seen:
            continue
        seen.add(key)
        refs.append(Riferimento(len(refs), citation, articolo, comma, norma_urn, via))
        if len(refs) == MAX_RIFERIMENTI:
            break
    return refs
