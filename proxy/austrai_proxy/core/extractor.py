"""Text extraction from files — PDF, DOCX, XLSX, TXT, images.

Heavy dependencies (PyMuPDF, python-docx, etc.) are optional.
Install with: pip install austrai[docs]
"""

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("austrai.extractor")


@dataclass
class ExtractionResult:
    text: str = ""
    format: str = "UNKNOWN"
    pages: int = 1
    warnings: list[str] = field(default_factory=list)


def extract_from_file(file_path: str) -> ExtractionResult:
    """Extract text from a file. Auto-detects format by extension."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {file_path}")

    suffix = path.suffix.lower()
    file_bytes = path.read_bytes()

    if suffix == ".pdf":
        return _extract_pdf(file_bytes)
    elif suffix == ".docx":
        return _extract_docx(file_bytes)
    elif suffix == ".xlsx":
        return _extract_xlsx(file_bytes)
    elif suffix in (".txt", ".csv", ".md", ".json", ".xml", ".html", ".log", ".yaml", ".yml"):
        return _extract_text(file_bytes, suffix.lstrip(".").upper())
    elif suffix in (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"):
        return _extract_image(file_bytes)
    else:
        try:
            return _extract_text(file_bytes, suffix.lstrip(".").upper())
        except Exception:
            raise ValueError(f"Dateiformat '{suffix}' nicht unterstuetzt.")


def _extract_pdf(data: bytes) -> ExtractionResult:
    try:
        import fitz
    except ImportError:
        raise ImportError("PDF-Support braucht PyMuPDF: pip install austrai[docs]")
    doc = fitz.open(stream=data, filetype="pdf")
    pages = [page.get_text() for page in doc]
    return ExtractionResult(text="\n\n".join(pages), format="PDF", pages=len(pages))


def _extract_docx(data: bytes) -> ExtractionResult:
    try:
        from docx import Document
    except ImportError:
        raise ImportError("DOCX-Support braucht python-docx: pip install austrai[docs]")
    doc = Document(io.BytesIO(data))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return ExtractionResult(text="\n".join(paragraphs), format="DOCX", pages=1)


def _extract_xlsx(data: bytes) -> ExtractionResult:
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise ImportError("XLSX-Support braucht openpyxl: pip install austrai[docs]")
    wb = load_workbook(io.BytesIO(data), read_only=True)
    parts = []
    for sheet in wb.worksheets:
        rows = []
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            parts.append(f"[{sheet.title}]\n" + "\n".join(rows))
    return ExtractionResult(text="\n\n".join(parts), format="XLSX", pages=len(wb.worksheets))


def _extract_text(data: bytes, fmt: str) -> ExtractionResult:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    return ExtractionResult(text=text, format=fmt, pages=1)


def _extract_image(data: bytes) -> ExtractionResult:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        raise ImportError("Bild-OCR braucht Tesseract + Pillow: pip install austrai[docs]")
    img = Image.open(io.BytesIO(data))
    text = pytesseract.image_to_string(img, lang="deu+eng")
    return ExtractionResult(text=text, format="IMAGE", pages=1)
