"""The ``execute`` action: per item, the grab output (``<dirIn>/<itemId as a name>/*.pdf`` with sidecars) becomes ``<stem>.plan.json`` files in the same item
directory under ``dirOut`` (plan schema v1), plus a copy of the grab's ``_coverage.json``. A failing item does not stop the others: the run ends with one
``system_error`` listing the failed keys. Sample filters of the Source (``only``, ``maxDocs``, ``maxItems``) were applied by the grab: nothing to trim here."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dp_it_prassi_convert import ocr as ocr_mod
from dp_it_prassi_convert import plan as plan_mod

if TYPE_CHECKING:
    from collections.abc import Callable

CONFIG_ERROR = "config_error"
SYSTEM_ERROR = "system_error"
KIND_ADE, KIND_DOCTRIB = "ade", "doctrib"
KINDS = (KIND_ADE, KIND_DOCTRIB)
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class ConvertError(Exception):
    """A run-level failure carrying one of the protocol error codes."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def safe_name(item_id: str) -> str:
    """Directory name of an item id (identical to the grab class)."""
    return _UNSAFE.sub("_", item_id.replace(" ", "-"))


def _validate_items(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list) or not items:
        raise ConvertError(CONFIG_ERROR, "items must be a non-empty array")
    for entry in items:
        meta = entry.get("meta") if isinstance(entry, dict) else None
        if not isinstance(entry, dict) or not entry.get("key") or not isinstance(meta, dict):
            raise ConvertError(CONFIG_ERROR, f"item needs a key and a meta: {entry!r}")
        if meta.get("kind") not in KINDS or not isinstance(meta.get("itemId"), str) or not meta["itemId"]:
            raise ConvertError(CONFIG_ERROR, f"item {entry['key']}: meta.kind must be one of {list(KINDS)} and meta.itemId is required")
    return items


def _convert_item(entry: dict[str, Any], dir_in: Path, dir_out: Path, ocr_fn: Callable[[Path], str]) -> dict[str, int]:
    item_name = safe_name(entry["meta"]["itemId"])
    source = dir_in / item_name
    if not source.is_dir():
        msg = f"no grab output for the item at {source}"
        raise ConvertError(SYSTEM_ERROR, msg)
    target = dir_out / item_name
    target.mkdir(parents=True, exist_ok=True)
    fonte = "doctrib" if entry["meta"]["kind"] == KIND_DOCTRIB else None
    counts = {"documents": 0, "ocr": 0, "skipped": 0, "warnings": 0}
    for pdf in sorted(source.glob("*.pdf")):
        try:
            plan = plan_mod.build_plan(pdf, fonte=fonte, ocr=ocr_fn)
        except ocr_mod.OcrUnavailable:
            raise
        except Exception as error:  # noqa: BLE001 - one broken PDF must not stop the others; the reason is declared
            plan = plan_mod.Plan(skipped=[{"item_ref": pdf.stem, "reason": "convert_failed"}], warnings=[f"{pdf.name}: {type(error).__name__}"])
        (target / f"{pdf.name.removesuffix('.pdf')}.plan.json").write_text(plan.to_json(), encoding="utf-8")
        if plan.documento is not None:
            counts["documents"] += 1
            counts["ocr"] += 1 if plan.documento["estrazione"] == "ocr" else 0
        counts["skipped"] += len(plan.skipped)
        counts["warnings"] += len(plan.warnings)
    coverage = source / "_coverage.json"
    if coverage.is_file():
        shutil.copyfile(coverage, target / "_coverage.json")
    return counts


def run_convert(
    raw_params: dict[str, Any], on_progress: Callable[[int, str], None], ocr_fn: Callable[[Path], str] | None = None,
) -> dict[str, Any]:
    """Converts every item; if any failed raises ConvertError(system_error) naming the keys, after the others were written."""
    params = {name: value for name, value in raw_params.items() if value is not None}  # the Host resolves an undeclared Source config key to null
    items = _validate_items(params.get("items"))
    dir_in, dir_out = params.get("dirIn"), params.get("dirOut")
    if not isinstance(dir_in, str) or not dir_in or not isinstance(dir_out, str) or not dir_out:
        raise ConvertError(CONFIG_ERROR, "dirIn and dirOut are required")
    reader = ocr_fn or ocr_mod.ocr_pdf
    totals = {"documents": 0, "ocr": 0, "skipped": 0, "warnings": 0}
    converted: list[dict[str, Any]] = []
    failures: list[str] = []
    for position, entry in enumerate(items):
        try:
            counts = _convert_item(entry, Path(dir_in), Path(dir_out), reader)
        except (ConvertError, ocr_mod.OcrUnavailable) as error:
            failures.append(f"{entry['key']} ({error})")
        else:
            for name, value in counts.items():
                totals[name] += value
            converted.append({"key": entry["key"], "plan": str(Path(dir_out) / safe_name(entry["meta"]["itemId"])), "meta": entry["meta"]})
        on_progress(int((position + 1) * 100 / len(items)), f"{position + 1}/{len(items)} {entry['key']}")
    if failures:
        msg = f"{len(failures)} of {len(items)} items failed: {'; '.join(failures)}"
        raise ConvertError(SYSTEM_ERROR, msg)
    return {"dirOut": dir_out, "converted": converted, "metrics": totals}
