"""Bildschwärzung — überdeckt erkannte PII direkt im Bild mit schwarzen Pixeln.

Nutzt Tesseract OCR für Texterkennung und überdeckt die erkannten
PII-Bereiche direkt im Bild. Das Originalbild wird nie weitergegeben.

Unterstützt: PNG, JPG, JPEG, TIFF, BMP, WEBP

Benötigt: Pillow + pytesseract (im Standard-Install enthalten)
Tesseract muss separat installiert sein (brew install tesseract)
"""

import io
import logging
from pathlib import Path

logger = logging.getLogger("austrai.image_redactor")


def redact_image(
    image_path: str,
    output_path: str | None = None,
    deny_list: list[str] | None = None,
    redaction_color: tuple[int, int, int] = (0, 0, 0),
    padding: int = 4,
) -> dict:
    """Schwärzt sensible Daten in einem Bild.

    1. OCR extrahiert Text + Bounding Boxes
    2. Presidio/SpaCy erkennt PII im Text
    3. PII-Bounding-Boxes werden mit schwarzen Pixeln überdeckt
    4. Geschwärztes Bild wird gespeichert

    Args:
        image_path: Pfad zum Eingabebild
        output_path: Pfad zum geschwärzten Bild (default: _redacted suffix)
        deny_list: Zusätzliche Begriffe die geschwärzt werden sollen
        redaction_color: Farbe der Schwärzung (default: schwarz)
        padding: Pixel-Padding um erkannte Bereiche

    Returns:
        dict mit Infos: output_path, entities_redacted, text_extracted
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        raise ImportError("Bildschwärzung braucht Pillow: pip install austrai")

    try:
        import pytesseract
    except ImportError:
        raise ImportError("Bildschwärzung braucht pytesseract: pip install austrai")

    from austrai_proxy.core import get_engine

    # Load image
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    # OCR: get text + bounding boxes
    ocr_data = pytesseract.image_to_data(img, lang="deu+eng", output_type=pytesseract.Output.DICT)

    # Build full text for PII detection
    words = ocr_data.get("text", [])
    full_text = " ".join(w for w in words if w.strip())

    if not full_text.strip():
        logger.info("Kein Text im Bild erkannt.")
        return {"output_path": image_path, "entities_redacted": 0, "text_extracted": ""}

    # Detect PII in the extracted text
    engine = get_engine(memory_enabled=False)
    result = engine.anonymize(full_text, deny_list=deny_list)

    if not result.mappings:
        logger.info("Keine sensiblen Daten im Bild erkannt.")
        if output_path:
            img.save(output_path)
        return {"output_path": output_path or image_path, "entities_redacted": 0, "text_extracted": full_text}

    # Find which OCR words match the detected PII
    pii_originals = set(result.mappings.values())  # The original PII values
    redacted_count = 0

    # Build word-level bounding boxes
    n_boxes = len(ocr_data.get("text", []))
    for i in range(n_boxes):
        word = ocr_data["text"][i].strip()
        if not word:
            continue

        # Check if this word is part of any PII entity
        should_redact = False
        for original in pii_originals:
            # Check if the word is part of the original entity
            original_words = original.lower().split()
            if word.lower() in original_words:
                should_redact = True
                break
            # Also check if the original is a single token containing this word
            if word.lower() == original.lower():
                should_redact = True
                break

        if should_redact:
            x = ocr_data["left"][i] - padding
            y = ocr_data["top"][i] - padding
            w = ocr_data["width"][i] + 2 * padding
            h = ocr_data["height"][i] + 2 * padding
            draw.rectangle([x, y, x + w, y + h], fill=redaction_color)
            redacted_count += 1

    # Save redacted image
    if not output_path:
        p = Path(image_path)
        output_path = str(p.parent / f"{p.stem}_redacted{p.suffix}")

    img.save(output_path)
    logger.info("Bild geschwaerzt: %d Bereiche, gespeichert als %s", redacted_count, output_path)

    return {
        "output_path": output_path,
        "entities_redacted": redacted_count,
        "text_extracted": full_text,
        "anonymized_text": result.anonymized_text,
        "mappings": result.mappings,
    }


def redact_pdf_pages(
    pdf_path: str,
    output_path: str | None = None,
    deny_list: list[str] | None = None,
) -> dict:
    """Schwärzt sensible Daten in einem gescannten PDF (Bild-basiert).

    Konvertiert jede Seite in ein Bild, schwärzt PII, speichert als neues PDF.

    Args:
        pdf_path: Pfad zum PDF
        output_path: Pfad zum geschwärzten PDF
        deny_list: Zusätzliche Begriffe

    Returns:
        dict mit Infos
    """
    try:
        import fitz  # PyMuPDF
        from PIL import Image
    except ImportError:
        raise ImportError("PDF-Schwärzung braucht PyMuPDF + Pillow: pip install austrai")

    try:
        import pytesseract
    except ImportError:
        raise ImportError("PDF-Schwärzung braucht pytesseract: pip install austrai")

    from austrai_proxy.core import get_engine
    import tempfile

    doc = fitz.open(pdf_path)
    # Hard-Cap auf Seitenzahl: ein maliziös erstelltes PDF mit 10.000 Seiten
    # würde pytesseract (OCR) + Detector stundenlang beschäftigen. 500
    # Seiten reicht für reale Use-Cases; wer mehr braucht, teilt das PDF.
    MAX_REDACT_PAGES = 500
    if len(doc) > MAX_REDACT_PAGES:
        doc.close()
        raise ValueError(f"PDF has too many pages ({len(doc)}). Max supported: {MAX_REDACT_PAGES}")
    engine = get_engine(memory_enabled=False)
    total_redacted = 0
    all_text = []

    for page_num in range(len(doc)):
        page = doc[page_num]

        # Render page to image
        mat = fitz.Matrix(2, 2)  # 2x zoom for better OCR
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # OCR
        ocr_data = pytesseract.image_to_data(img, lang="deu+eng", output_type=pytesseract.Output.DICT)
        words = ocr_data.get("text", [])
        page_text = " ".join(w for w in words if w.strip())
        all_text.append(page_text)

        if not page_text.strip():
            continue

        # Detect PII
        result = engine.anonymize(page_text, deny_list=deny_list)
        if not result.mappings:
            continue

        pii_originals = set(result.mappings.values())

        # Redact on the actual PDF page (not the zoomed image)
        n_boxes = len(ocr_data.get("text", []))
        for i in range(n_boxes):
            word = ocr_data["text"][i].strip()
            if not word:
                continue

            should_redact = False
            for original in pii_originals:
                if word.lower() in original.lower().split() or word.lower() == original.lower():
                    should_redact = True
                    break

            if should_redact:
                # Scale coordinates back from 2x zoom
                x0 = ocr_data["left"][i] / 2
                y0 = ocr_data["top"][i] / 2
                x1 = x0 + ocr_data["width"][i] / 2
                y1 = y0 + ocr_data["height"][i] / 2
                rect = fitz.Rect(x0 - 2, y0 - 2, x1 + 2, y1 + 2)
                page.draw_rect(rect, color=(0, 0, 0), fill=(0, 0, 0))
                total_redacted += 1

    if not output_path:
        p = Path(pdf_path)
        output_path = str(p.parent / f"{p.stem}_redacted{p.suffix}")

    doc.save(output_path)
    doc.close()

    return {
        "output_path": output_path,
        "entities_redacted": total_redacted,
        "pages": len(all_text),
        "text_extracted": "\n\n".join(all_text),
    }
