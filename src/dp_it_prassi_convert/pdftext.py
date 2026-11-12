"""Text layer of a PDF through pypdfium2 (Apache-2.0/BSD). Chosen over pymupdf4llm (AGPL) by the spike of P80-05: on the born-digital fixtures it loses at
most 1.4% of the words, breaks no subject line and no estremi match, and is 10-70 times faster."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pypdfium2 as pdfium

if TYPE_CHECKING:
    from pathlib import Path

# no-break space, figure space, thin space, narrow no-break space (pdfium keeps the ones the PDF uses)
_SPACES_UNICODE = re.compile("[" + "".join(chr(code) for code in (0xA0, 0x2007, 0x2009, 0x202F)) + "]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_SPACE_RUN = re.compile(r"[ \t]+")
_TRAILING = re.compile(r"[ \t]+\n")
_BLANK_RUN = re.compile(r"\n{3,}")


class PdfUnreadable(Exception):  # noqa: N818 - the name is the declared skip reason `pdf_unreadable`
    """The file is not a PDF or cannot be parsed."""


def clean_text(raw: str) -> str:
    """Remove soft hyphens and control characters, normalise line ends, collapse whitespace runs but keep paragraphs (blank lines)."""
    text = raw.replace("­", "").replace("\r\n", "\n").replace("\r", "\n")
    text = _SPACES_UNICODE.sub(" ", text)
    text = _CONTROL.sub("", text)
    text = _SPACE_RUN.sub(" ", text)
    text = _TRAILING.sub("\n", text)
    text = _BLANK_RUN.sub("\n\n", text)
    return text.strip()


def _open(path: Path) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(str(path))
    except (pdfium.PdfiumError, OSError) as error:
        msg = f"cannot open {path.name}: {error}"
        raise PdfUnreadable(msg) from error


def page_count(path: Path) -> int:
    """Number of pages of the PDF."""
    document = _open(path)
    try:
        return len(document)
    finally:
        document.close()


def extract_text(path: Path) -> str:
    """The cleaned text layer of every page, pages joined by a blank line. A photographed page gives an empty string (see ``ocr.needs_ocr``)."""
    document = _open(path)
    try:
        pages: list[str] = []
        for page in document:
            textpage = page.get_textpage()
            try:
                pages.append(textpage.get_text_bounded())
            finally:
                textpage.close()
                page.close()
    except pdfium.PdfiumError as error:
        msg = f"cannot read {path.name}: {error}"
        raise PdfUnreadable(msg) from error
    finally:
        document.close()
    return clean_text("\n\n".join(pages))
