"""Tests marked ``ocr`` need the tesseract binary: skipped on a developer machine without it, mandatory inside Dockerfile.test (REQUIRE_TESSERACT=1)."""
from __future__ import annotations

import os
import shutil

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:  # noqa: ARG001
    if shutil.which("tesseract") is not None:
        return
    required = os.environ.get("REQUIRE_TESSERACT") == "1"
    # inside the test image a missing binary is a failure, not a skip
    marker = pytest.mark.usefixtures("_tesseract_required") if required else pytest.mark.skip(reason="tesseract is not installed (runs inside Dockerfile.test)")
    for item in items:
        if "ocr" in item.keywords:
            item.add_marker(marker)


@pytest.fixture
def _tesseract_required() -> None:
    pytest.fail("REQUIRE_TESSERACT=1 but the tesseract binary is not on PATH")
