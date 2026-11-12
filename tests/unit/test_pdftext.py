"""PDF text layer through pypdfium2 (P80-05, spike result in tasks/80-dp-it-prassi/notes.md)."""
from __future__ import annotations

from pathlib import Path

import pytest

from dp_it_prassi_convert import pdftext
from dp_it_prassi_convert.ocr import needs_ocr

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "formula"),
    [
        ("Circolare_n_9_del_24_06_2025.pdf", "CIRCOLARE N."),
        ("RIS_n_16_del_04_03_2025.pdf", "RISOLUZIONE N."),
        ("Risoluzione_n._29_2025.pdf", "RISOLUZIONE N."),
        ("CIRCOLARE_TASSAZIONE_AUTO_USO_PROMISCUO_n._10_del_3_luglio_2025.pdf", "CIRCOLARE N."),
    ],
)
def test_should_give_text_with_the_number_formula_when_the_pdf_is_born_digital(name: str, formula: str) -> None:
    text = pdftext.extract_text(FIXTURES / name)

    assert not needs_ocr(text)
    assert formula in text.upper()


@pytest.mark.unit
def test_should_give_text_when_the_pdf_is_a_doctrib_interpello() -> None:
    text = pdftext.extract_text(FIXTURES / "interpello-doctrib.pdf")

    assert len(text) > 1000
    assert "interpello" in text.lower()


@pytest.mark.unit
@pytest.mark.parametrize("name", ["interpello-fotografia.pdf", "interpello-fotografia-con-numero-pagina.pdf"])
def test_should_count_a_photo_pdf_as_no_text_even_with_a_lone_page_number(name: str) -> None:
    text = pdftext.extract_text(FIXTURES / name)

    assert len(text.strip()) < 200
    assert needs_ocr(text)


@pytest.mark.unit
def test_should_clean_soft_hyphens_control_characters_and_whitespace_runs_but_keep_paragraphs() -> None:
    dirty = "con­tri\x07buente   paga \t\n\n\n\n\nx\r\ny"

    assert pdftext.clean_text(dirty) == "contribuente paga\n\nx\ny"


@pytest.mark.unit
def test_should_raise_a_declared_error_when_the_file_is_not_a_pdf(tmp_path: Path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"this is not a pdf")

    with pytest.raises(pdftext.PdfUnreadable):
        pdftext.extract_text(broken)


@pytest.mark.unit
def test_should_page_count_match_the_document() -> None:
    assert pdftext.page_count(FIXTURES / "interpello-fotografia.pdf") >= 1
