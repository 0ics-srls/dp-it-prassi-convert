"""convert: the `execute` action end to end on the fixture PDFs (item directories, plan files, coverage copy, metrics) and the Proc-protocol loop."""
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

import main
from dp_it_prassi_convert import ocr
from dp_it_prassi_convert.convert import CONFIG_ERROR, SYSTEM_ERROR, ConvertError, run_convert

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
GUID = "8C708965-7201-43BE-B7BE-71FF1FED384B"
ADE_ITEM = {"key": "ade:risoluzioni:2025:03|v1", "meta": {"kind": "ade", "itemId": "ade:risoluzioni:2025:03", "version": "1"}}
DOCTRIB_ITEM = {"key": "doctrib:interpello:2022-02|v1", "meta": {"kind": "doctrib", "itemId": "doctrib:interpello:2022-02", "version": "1"}}


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    base = tmp_path / "raw"
    ade = base / "ade_risoluzioni_2025_03"
    ade.mkdir(parents=True)
    shutil.copy(FIXTURES / "RIS_n_16_del_04_03_2025.pdf", ade / "RIS_n_16_del_04_03_2025.pdf")
    (ade / "_coverage.json").write_text(json.dumps({"fonte": "ade-portale", "tipo": "risoluzione", "anno": 2025, "mese": 3, "cards": 2}), encoding="utf-8")
    doctrib = base / "doctrib_interpello_2022-02"
    doctrib.mkdir(parents=True)
    shutil.copy(FIXTURES / "interpello-fotografia.pdf", doctrib / f"Interpello_2022-02-17_118__{GUID}.pdf")
    shutil.copy(FIXTURES / "interpello-doctrib.pdf", doctrib / f"Interpello_2024-12-23_269__{GUID[:-1]}0.pdf")
    return base


def fake_ocr(_path: Path) -> str:
    return "Risposta n. 118/2022 Interpello. " * 10


def params(raw: Path, tmp_path: Path, items: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {"items": items, "dirIn": str(raw), "dirOut": str(tmp_path / "plan"), **extra}


@pytest.mark.unit
def test_should_write_one_plan_per_pdf_in_the_item_directory_and_copy_the_coverage(raw: Path, tmp_path: Path) -> None:
    result = run_convert(params(raw, tmp_path, [ADE_ITEM]), lambda *_: None, ocr_fn=fake_ocr)

    plans = sorted((tmp_path / "plan" / "ade_risoluzioni_2025_03").glob("*.plan.json"))
    assert [p.name for p in plans] == ["RIS_n_16_del_04_03_2025.plan.json"]
    assert json.loads((tmp_path / "plan" / "ade_risoluzioni_2025_03" / "_coverage.json").read_text(encoding="utf-8"))["cards"] == 2
    assert result["metrics"] == {"documents": 1, "ocr": 0, "skipped": 0, "warnings": 0}
    assert result["converted"][0]["key"] == ADE_ITEM["key"]
    assert result["converted"][0]["plan"].endswith("ade_risoluzioni_2025_03")


@pytest.mark.unit
def test_should_count_ocr_documents_and_skips(raw: Path, tmp_path: Path) -> None:
    def failing(_path: Path) -> str:
        raise ocr.OcrEmpty("nothing")

    result = run_convert(params(raw, tmp_path, [DOCTRIB_ITEM], fonte="doctrib"), lambda *_: None, ocr_fn=failing)

    # the born-digital fixture is filed as number 269 and declares 267: the source number is kept and the disagreement is counted as one warning (F2)
    assert result["metrics"] == {"documents": 1, "ocr": 0, "skipped": 1, "warnings": 1}
    skipped = json.loads(next((tmp_path / "plan" / "doctrib_interpello_2022-02").glob(f"Interpello_2022-02-17_118__{GUID}.plan.json")).read_text(encoding="utf-8"))
    assert skipped["documento"] is None
    assert skipped["skipped"][0]["reason"] == "ocr_empty"

    again = run_convert(params(raw, tmp_path / "second", [DOCTRIB_ITEM]), lambda *_: None, ocr_fn=fake_ocr)
    assert again["metrics"]["ocr"] == 1


@pytest.mark.unit
def test_should_treat_null_config_keys_as_absent(raw: Path, tmp_path: Path) -> None:
    nulls = {"anni": None, "only": None, "maxDocs": None, "maxItems": None, "fonte": None, "baseUrl": None}

    result = run_convert(params(raw, tmp_path, [ADE_ITEM], **nulls), lambda *_: None, ocr_fn=fake_ocr)

    assert result["metrics"]["documents"] == 1


@pytest.mark.unit
def test_should_refuse_bad_parameters_as_config_errors(raw: Path, tmp_path: Path) -> None:
    for bad in (
        {"items": [], "dirIn": str(raw), "dirOut": str(tmp_path)},
        {"items": [{"key": "x", "meta": {"kind": "gazzetta", "itemId": "x"}}], "dirIn": str(raw), "dirOut": str(tmp_path)},
        {"items": [ADE_ITEM], "dirOut": str(tmp_path)},
        {"items": [ADE_ITEM], "dirIn": str(raw)},
    ):
        with pytest.raises(ConvertError) as caught:
            run_convert(bad, lambda *_: None, ocr_fn=fake_ocr)
        assert caught.value.code == CONFIG_ERROR


@pytest.mark.unit
def test_should_end_with_a_system_error_naming_the_failed_item_and_still_convert_the_others(raw: Path, tmp_path: Path) -> None:
    missing = {"key": "ade:circolari:2025:01|v1", "meta": {"kind": "ade", "itemId": "ade:circolari:2025:01", "version": "1"}}

    with pytest.raises(ConvertError) as caught:
        run_convert(params(raw, tmp_path, [missing, ADE_ITEM]), lambda *_: None, ocr_fn=fake_ocr)

    assert caught.value.code == SYSTEM_ERROR
    assert "ade:circolari:2025:01|v1" in str(caught.value)
    assert (tmp_path / "plan" / "ade_risoluzioni_2025_03" / "RIS_n_16_del_04_03_2025.plan.json").exists()


@pytest.mark.unit
def test_should_stop_an_item_when_tesseract_is_missing(raw: Path, tmp_path: Path) -> None:
    def unavailable(_path: Path) -> str:
        raise ocr.OcrUnavailable("tesseract")

    with pytest.raises(ConvertError) as caught:
        run_convert(params(raw, tmp_path, [DOCTRIB_ITEM]), lambda *_: None, ocr_fn=unavailable)

    assert caught.value.code == SYSTEM_ERROR
    assert "tesseract" in str(caught.value)


@pytest.mark.unit
def test_the_protocol_loop_answers_execute_terminate_and_bad_requests(raw: Path, tmp_path: Path) -> None:
    request = {"_action": "execute", "_meta": {"executionId": "e1"}, **params(raw, tmp_path, [ADE_ITEM])}
    lines = json.dumps(request) + "\n" + "not json\n" + json.dumps({"_action": "frobnicate", "_meta": {"executionId": "e"}}) + "\n"
    out = io.StringIO()

    code = main.main(io.StringIO(lines + json.dumps({"_action": "terminate", "_meta": {"executionId": "e"}}) + "\n"), out)

    events = [json.loads(line) for line in out.getvalue().splitlines()]
    assert code == 1
    assert [e["type"] for e in events if e["type"] != "progress"] == ["result", "error", "error"]
    assert events[-1]["code"] == "config_error"
