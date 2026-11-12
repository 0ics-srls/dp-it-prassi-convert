"""Plan files: one `<stem>.plan.json` per PDF (plan schema v1), the order of operations, OCR, skips, warnings and determinism."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from dp_it_prassi_convert import ocr, plan

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SCHEMA = json.loads((Path(__file__).resolve().parent.parent.parent / "plan.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
GUID = "8C708965-7201-43BE-B7BE-71FF1FED384B"
OCR_TEXT = "Risposta n. 118/2022 Interpello articolo 11 della legge 27 luglio 2000, n. 212. " * 6


def fake_ocr(_path: Path) -> str:
    return OCR_TEXT


def empty_ocr(_path: Path) -> str:
    raise ocr.OcrEmpty("nothing read")


def copy_fixture(name: str, tmp_path: Path, as_name: str | None = None) -> Path:
    target = tmp_path / (as_name or name)
    shutil.copy(FIXTURES / name, target)
    return target


def write_sidecar(pdf: Path, **fields: Any) -> None:
    Path(str(pdf) + ".meta.json").write_text(json.dumps(fields), encoding="utf-8")


def build(pdf: Path, **kwargs: Any) -> dict[str, Any]:
    result = plan.build_plan(pdf, ocr=kwargs.pop("ocr", fake_ocr), **kwargs).to_dict()
    VALIDATOR.validate(result)
    return result


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "tipo", "numero", "anno", "data"),
    [
        ("Circolare_n_9_del_24_06_2025.pdf", "circolare", "9", 2025, "2025-06-24"),
        ("RIS_n_16_del_04_03_2025.pdf", "risoluzione", "16", 2025, "2025-03-04"),
        ("Risoluzione_n._29_2025.pdf", "risoluzione", "29", 2025, "2025-04-11"),
        ("CIRCOLARE_TASSAZIONE_AUTO_USO_PROMISCUO_n._10_del_3_luglio_2025.pdf", "circolare", "10", 2025, "2025-07-03"),
    ],
)
def test_should_plan_a_born_digital_pdf_with_text_estremi_and_references(name: str, tipo: str, numero: str, anno: int, data: str) -> None:
    result = build(FIXTURES / name)

    doc = result["documento"]
    assert (doc["tipo"], doc["numero"], doc["anno"], doc["data"]) == (tipo, numero, anno, data)
    assert doc["estrazione"] == "testo"
    assert doc["fonte"] == "ade-portale"
    assert doc["source_id"] == Path(name).stem
    assert doc["ente"] == "Agenzia delle Entrate"
    assert len(doc["text_raw"]) > 1000
    assert result["riferimenti"], "a circolare cites norms"
    assert result["skipped"] == []


@pytest.mark.unit
def test_should_take_the_identity_of_a_doctrib_pdf_from_the_sidecar_and_lower_case_the_tipo(tmp_path: Path) -> None:
    pdf = copy_fixture("interpello-doctrib.pdf", tmp_path, f"Interpello_2024-12-23_269__{GUID}.pdf")
    write_sidecar(pdf, kind="doctrib", tipo="Interpello", titolo="IVA - Trattamento applicabile", numero="269", data="2024-12-23", struttura="Direzione Centrale",
                  ente="Agenzia delle Entrate", sourceUrl=f"https://def.finanze.it/DocTribFrontend/getPrassiDetail.do?id={{{GUID}}}", fonte="doctrib", sourceId=GUID)

    doc = build(pdf)["documento"]

    assert (doc["tipo"], doc["fonte"], doc["source_id"]) == ("interpello", "doctrib", GUID)
    assert (doc["numero"], doc["anno"], doc["data"]) == ("267", 2024, "2024-12-23"), "the act declares Risposta n. 267/2024: the act is the oracle of its own number"
    assert doc["struttura"] == "Direzione Centrale"
    assert doc["source_url"].endswith(f"id={{{GUID}}}")
    assert doc["oggetto"] == "IVA - Trattamento applicabile"


@pytest.mark.unit
def test_should_take_the_doctrib_identity_from_the_file_name_when_the_sidecar_is_missing(tmp_path: Path) -> None:
    pdf = copy_fixture("interpello-doctrib.pdf", tmp_path, f"Interpello_2024-12-23_269__{GUID}.pdf")

    doc = build(pdf, fonte="doctrib")["documento"]

    assert (doc["tipo"], doc["source_id"], doc["numero"], doc["anno"]) == ("interpello", GUID, "267", 2024)


@pytest.mark.unit
@pytest.mark.parametrize("name", ["interpello-fotografia.pdf", "interpello-fotografia-con-numero-pagina.pdf"])
def test_should_read_a_photo_pdf_through_ocr_and_declare_it(name: str, tmp_path: Path) -> None:
    pdf = copy_fixture(name, tmp_path, f"Interpello_2022-02-17_118__{GUID}.pdf")

    result = build(pdf, fonte="doctrib")

    assert result["documento"]["estrazione"] == "ocr"
    assert result["documento"]["numero"] == "118"
    assert result["documento"]["text_raw"].strip()


@pytest.mark.unit
def test_should_skip_a_photo_pdf_whose_ocr_reads_nothing_and_never_write_empty_text(tmp_path: Path) -> None:
    pdf = copy_fixture("interpello-fotografia.pdf", tmp_path)

    result = build(pdf, ocr=empty_ocr)

    assert result["documento"] is None
    assert result["skipped"] == [{"item_ref": "interpello-fotografia", "reason": "ocr_empty"}]


@pytest.mark.unit
def test_should_skip_a_corrupt_pdf_as_unreadable(tmp_path: Path) -> None:
    pdf = tmp_path / "Circolare_n_1_del_01_01_2025.pdf"
    pdf.write_bytes(b"not a pdf")

    result = build(pdf)

    assert result["documento"] is None
    assert result["skipped"] == [{"item_ref": "Circolare_n_1_del_01_01_2025", "reason": "pdf_unreadable"}]


@pytest.mark.unit
def test_should_let_a_missing_tesseract_binary_stop_the_item(tmp_path: Path) -> None:
    pdf = copy_fixture("interpello-fotografia.pdf", tmp_path)

    def unavailable(_path: Path) -> str:
        raise ocr.OcrUnavailable("tesseract")

    with pytest.raises(ocr.OcrUnavailable):
        plan.build_plan(pdf, ocr=unavailable)


@pytest.mark.unit
def test_should_not_call_ocr_for_a_born_digital_pdf() -> None:
    def forbidden(_path: Path) -> str:
        msg = "ocr must not run for a pdf with a text layer"
        raise AssertionError(msg)

    assert plan.build_plan(FIXTURES / "RIS_n_16_del_04_03_2025.pdf", ocr=forbidden).documento is not None


@pytest.mark.unit
def test_should_repair_a_year_that_contradicts_the_date_and_count_the_warning(tmp_path: Path) -> None:
    pdf = copy_fixture("RIS_n_16_del_04_03_2025.pdf", tmp_path, "Circolare_10bis_art_119_dl_34_2020.pdf")
    write_sidecar(pdf, kind="ade", tipo="circolare", numero="3", data="2023-02-08", fonte="ade-portale", sourceId="Circolare_10bis_art_119_dl_34_2020")

    result = plan.build_plan(pdf, ocr=fake_ocr).to_dict()

    assert result["documento"]["anno"] == 2023
    assert len(result["warnings"]) == 1
    assert result["warnings"][0].startswith("coerenza-data")


@pytest.mark.unit
def test_should_produce_the_same_plan_on_a_second_run() -> None:
    pdf = FIXTURES / "Circolare_n_9_del_24_06_2025.pdf"

    first = plan.build_plan(pdf, ocr=fake_ocr).to_json()
    second = plan.build_plan(pdf, ocr=fake_ocr).to_json()

    assert first == second


@pytest.mark.unit
def test_should_validate_every_fixture_plan_against_the_schema() -> None:
    for pdf in sorted(FIXTURES.glob("*.pdf")):
        result = plan.build_plan(pdf, ocr=fake_ocr).to_dict()
        VALIDATOR.validate(result)
        if result["documento"] is not None:
            assert result["documento"]["text_raw"].strip()


@pytest.mark.unit
def test_the_schema_refuses_empty_text_a_bad_estrazione_and_a_mixed_case_tipo() -> None:
    good = plan.build_plan(FIXTURES / "RIS_n_16_del_04_03_2025.pdf", ocr=fake_ocr).to_dict()
    for field, value in (("text_raw", ""), ("estrazione", "scansione"), ("tipo", "Interpello")):
        broken = json.loads(json.dumps(good))
        broken["documento"][field] = value
        assert list(VALIDATOR.iter_errors(broken)), field


@pytest.mark.ocr
def test_should_read_the_real_photo_pdf_with_the_real_binary(tmp_path: Path) -> None:
    pdf = copy_fixture("interpello-fotografia.pdf", tmp_path)

    result = plan.build_plan(pdf).to_dict()

    VALIDATOR.validate(result)
    assert result["documento"]["estrazione"] == "ocr"
    assert len(result["documento"]["text_raw"]) > 200
