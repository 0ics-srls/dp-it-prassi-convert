"""Local OCR: pages rendered by pypdfium2, one tesseract CLI call per page (no shell, argument list). No paid service.

Rule kept from the legacy: a text shorter than 200 characters is "no text" (a lone page number counted as text and put a ghost document in the corpus).
An OCR that reads nothing raises ``OcrEmpty``: the caller declares the document skipped, an empty ``text_raw`` never reaches the corpus.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pypdfium2 as pdfium

TESSERACT = "tesseract"
THRESHOLD = 200
PAGE_TIMEOUT_SEC = 120
FORM_FEED = "\x0c"
_POINTS_PER_INCH = 72


class OcrUnavailable(Exception):  # noqa: N818 - public error names of the class
    """The tesseract binary (or its language data) is not installed."""


class OcrFailed(Exception):  # noqa: N818
    """Tesseract timed out or exited with an error."""


class OcrEmpty(Exception):  # noqa: N818
    """The OCR read nothing: the document is declared skipped (``ocr_empty``)."""


def needs_ocr(text: str | None, threshold: int = THRESHOLD) -> bool:
    """True when the text layer is not a document: empty or shorter than ``threshold`` characters once stripped."""
    return len((text or "").strip()) < threshold


def _tesseract(image: Path, lang: str, dpi: int) -> str:
    argv = [TESSERACT, str(image), "stdout", "-l", lang, "--dpi", str(dpi)]
    try:
        done = subprocess.run(  # noqa: S603 - argument list, no shell
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=PAGE_TIMEOUT_SEC, check=False, shell=False
        )
    except FileNotFoundError as error:
        msg = "the tesseract binary is not installed (apt: tesseract-ocr tesseract-ocr-ita)"
        raise OcrUnavailable(msg) from error
    except subprocess.TimeoutExpired as error:
        msg = f"tesseract exceeded {PAGE_TIMEOUT_SEC} s on one page"
        raise OcrFailed(msg) from error
    if done.returncode != 0:
        msg = f"tesseract exited with {done.returncode}: {done.stderr.strip()[:300]}"
        raise OcrFailed(msg)
    return done.stdout.strip()


def ocr_pdf(path: Path, lang: str = "ita", dpi: int = 200) -> str:
    """OCR every page of the PDF; pages are joined by a form feed. Raises ``OcrEmpty`` when nothing was read."""
    document = pdfium.PdfDocument(str(path))
    pages: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="prassi-ocr-") as scratch:
            for index in range(len(document)):
                page = document[index]
                try:
                    image = page.render(scale=dpi / _POINTS_PER_INCH).to_pil()
                finally:
                    page.close()
                target = Path(scratch) / f"page-{index:04d}.png"
                image.save(target)
                pages.append(_tesseract(target, lang, dpi))
    finally:
        document.close()
    text = FORM_FEED.join(pages)
    if not text.replace(FORM_FEED, "").strip():
        msg = f"tesseract read nothing from {path.name}"
        raise OcrEmpty(msg)
    return text
