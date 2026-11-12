"""Anchored extraction of norm references (P80-09). The legacy regex emitted 6,547 rows with 0 URNs; this one emits only references that carry a number/date or a
named act, attaches an article to the act it belongs to, and keeps the raw citation even when the URN is unknown."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from dp_it_prassi_convert import pdftext, riferimenti

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
STATUTO = "urn:nir:stato:legge:2000-07-27;212"
DPR633 = "urn:nir:stato:decreto.del.presidente.della.repubblica:1972-10-26;633"
TUIR = "urn:nir:stato:decreto.del.presidente.della.repubblica:1986-12-22;917"
DLGS241 = "urn:nir:stato:decreto.legislativo:1997-07-09;241"


@pytest.mark.unit
def test_should_map_the_law_cited_in_the_subject_to_the_statuto_and_not_to_a_bare_number() -> None:
    refs = riferimenti.extract_riferimenti("OGGETTO: Interpello articolo 11, comma 2, legge 27 luglio 2000, n. 212 - disapplicazione")

    assert [(r.norma_urn, r.articolo, r.comma) for r in refs] == [(f"{STATUTO}~art11", "11", "2")]
    assert refs[0].via == "numero_data"
    assert "legge 27 luglio 2000, n. 212" in refs[0].descrizione


@pytest.mark.unit
def test_should_attach_the_article_to_the_named_act() -> None:
    refs = riferimenti.extract_riferimenti("La detrazione prevista dall'art. 19 del decreto IVA spetta, come chiarito dall'articolo 17 del TUIR.")

    assert [(r.norma_urn, r.articolo, r.via) for r in refs] == [(f"{DPR633}~art19", "19", "alias"), (f"{TUIR}~art17", "17", "alias")]
    assert refs[0].descrizione.startswith("art. 19")


@pytest.mark.unit
def test_should_keep_article_suffixes_whole_and_map_decree_forms() -> None:
    text = (
        "Ai sensi dell'articolo 19-bis del d.P.R. 26 ottobre 1972, n. 633, e del decreto legislativo 9 luglio 1997, n. 241, "
        "nonche del d.lgs. n. 241 del 1997."
    )

    refs = riferimenti.extract_riferimenti(text)
    urns = [r.norma_urn for r in refs]

    assert f"{DPR633}~art19-bis" in urns
    assert DLGS241 in urns
    assert next(r for r in refs if r.norma_urn == f"{DPR633}~art19-bis").articolo == "19-bis"


@pytest.mark.unit
def test_should_keep_the_raw_citation_when_the_act_is_not_in_the_known_table() -> None:
    refs = riferimenti.extract_riferimenti("Si veda la legge n. 244 del 2007 e la legge 30 dicembre 2023, n. 213.")

    by_via = {r.via: r for r in refs}
    assert by_via["numero_anno"].norma_urn is None
    assert "legge n. 244 del 2007" in by_via["numero_anno"].descrizione
    assert by_via["numero_data"].norma_urn == "urn:nir:stato:legge:2023-12-30;213"


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "la legge",
        "il decreto",
        "Come previsto dalla legge e dal decreto in materia, la norma si applica.",
        "Il decreto ministeriale chiarisce che la legge non e retroattiva.",
        "articolo 5 della Costituzione",
        "ai sensi dell'art. 5 del regolamento comunale",
        "",
    ],
)
def test_should_emit_nothing_for_generic_phrases(text: str) -> None:
    assert riferimenti.extract_riferimenti(text) == []


@pytest.mark.unit
def test_should_not_attach_an_article_to_an_act_that_is_too_far_away() -> None:
    gap = " e altre considerazioni che non hanno alcun legame con la norma richiamata piu avanti nel periodo, " * 2
    refs = riferimenti.extract_riferimenti(f"Vedi l'art. 19{gap}d.P.R. 26 ottobre 1972, n. 633.")

    assert [(r.norma_urn, r.articolo) for r in refs] == [(DPR633, None)]


@pytest.mark.unit
def test_should_dedupe_and_keep_the_order_of_the_text() -> None:
    text = "Art. 17 del TUIR. Poi l'art. 17 del TUIR. Poi il d.P.R. 22 dicembre 1986, n. 917."

    refs = riferimenti.extract_riferimenti(text)

    assert [r.ord for r in refs] == list(range(len(refs)))
    assert [(r.norma_urn, r.articolo) for r in refs] == [(f"{TUIR}~art17", "17"), (TUIR, None)]


@pytest.mark.unit
def test_riferimenti_cap_and_determinism() -> None:
    text = " ".join(f"legge {1 + n % 28} gennaio 2000, n. {n}." for n in range(1, 200))

    first = riferimenti.extract_riferimenti(text)
    second = riferimenti.extract_riferimenti(text)

    assert first == second
    assert len(first) == riferimenti.MAX_RIFERIMENTI == 60
    assert [r.ord for r in first] == list(range(60))


@pytest.mark.unit
def test_should_finish_a_400_kb_text_within_two_seconds() -> None:
    paragraph = "Il contribuente ha chiesto chiarimenti sull'applicazione della disciplina, art. 5, comma 3, senza indicare la fonte. " * 8
    text = (paragraph + "\n") * 400

    started = time.perf_counter()
    riferimenti.extract_riferimenti(text)

    assert len(text) > 350_000
    assert time.perf_counter() - started < 2.0


@pytest.mark.unit
def test_should_match_the_reviewed_golden_on_the_real_fixtures(capsys: pytest.CaptureFixture[str]) -> None:
    golden = json.loads((FIXTURES / "riferimenti-golden.json").read_text(encoding="utf-8"))
    recall_lines = []
    for name, expected in golden["fixtures"].items():
        text = pdftext.extract_text(FIXTURES / name)
        refs = riferimenti.extract_riferimenti(text)
        urns = {r.norma_urn for r in refs if r.norma_urn}

        # precision: every URN the extractor emits has been reviewed against the text of the act
        assert urns <= set(expected["reviewed_urns"]), f"{name}: unreviewed URNs {sorted(urns - set(expected['reviewed_urns']))}"
        # recall on the URNs a reader can see in the act (golden minimum)
        assert set(expected["must_find"]) <= urns, f"{name}: missing {sorted(set(expected['must_find']) - urns)}"
        recall_lines.append(f"{name}: {len(refs)} refs, {len(urns)} distinct URNs, must_find {len(expected['must_find'])}")
    with capsys.disabled():
        print("\n[recall report]", *recall_lines, sep="\n  ")
