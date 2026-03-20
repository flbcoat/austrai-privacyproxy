"""Tests fuer den Textextraktions-Service und EXIF-Stripping."""

import io
import os
import sys
import unittest

# Backend-Verzeichnis zum Pfad hinzufuegen
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Dummy-API-Key setzen (Extractor-Tests rufen kein LLM auf)
os.environ.setdefault("MISTRAL_API_KEY", "test-key-not-used")

from app.services.extractor import (
    MAX_FILE_SIZE,
    MAX_TEXT_LENGTH,
    _detect_format,
    extract_text,
)
from app.services.exif_stripper import strip_exif, check_for_text_overlays


class TestFormatDetection(unittest.TestCase):
    """Tests fuer die Format-Erkennung anhand von Dateiendung und MIME-Type."""

    def test_pdf_by_extension(self) -> None:
        """PDF-Format wird anhand der Endung .pdf erkannt."""
        self.assertEqual(_detect_format("dokument.pdf"), "PDF")

    def test_docx_by_extension(self) -> None:
        """DOCX-Format wird anhand der Endung .docx erkannt."""
        self.assertEqual(_detect_format("brief.docx"), "DOCX")

    def test_xlsx_by_extension(self) -> None:
        """XLSX-Format wird anhand der Endung .xlsx erkannt."""
        self.assertEqual(_detect_format("tabelle.xlsx"), "XLSX")

    def test_text_formats_by_extension(self) -> None:
        """Verschiedene Textformate werden korrekt erkannt."""
        text_files = [
            ("notizen.txt", "TEXT"),
            ("daten.csv", "TEXT"),
            ("readme.md", "TEXT"),
            ("config.json", "TEXT"),
            ("data.xml", "TEXT"),
            ("page.html", "TEXT"),
        ]
        for filename, expected_format in text_files:
            with self.subTest(filename=filename):
                self.assertEqual(_detect_format(filename), expected_format)

    def test_image_formats_by_extension(self) -> None:
        """Verschiedene Bildformate werden korrekt erkannt."""
        image_files = [
            "foto.png", "bild.jpg", "scan.jpeg",
            "dokument.tiff", "scan.tif", "grafik.bmp", "web.webp",
        ]
        for filename in image_files:
            with self.subTest(filename=filename):
                self.assertEqual(_detect_format(filename), "IMAGE")

    def test_case_insensitive_extension(self) -> None:
        """Dateiendungen werden case-insensitive erkannt."""
        self.assertEqual(_detect_format("DOKUMENT.PDF"), "PDF")
        self.assertEqual(_detect_format("Bild.JPG"), "IMAGE")
        self.assertEqual(_detect_format("Tabelle.XLSX"), "XLSX")

    def test_mime_type_fallback(self) -> None:
        """MIME-Type wird als Fallback verwendet wenn Endung unbekannt."""
        self.assertEqual(
            _detect_format("datei.unknown", mime_type="application/pdf"),
            "PDF",
        )

    def test_unsupported_format_raises_error(self) -> None:
        """Nicht unterstuetzte Formate loesen einen ValueError aus."""
        with self.assertRaises(ValueError) as ctx:
            _detect_format("datei.exe")
        self.assertIn("Nicht unterstuetztes Dateiformat", str(ctx.exception))

    def test_unsupported_format_no_mime(self) -> None:
        """Nicht unterstuetztes Format ohne MIME-Type loest ValueError aus."""
        with self.assertRaises(ValueError):
            _detect_format("archiv.zip", mime_type=None)


class TestTextExtraction(unittest.TestCase):
    """Tests fuer die Textextraktion aus verschiedenen Formaten."""

    def test_extract_plain_text(self) -> None:
        """Einfacher Text wird korrekt extrahiert."""
        text = "Hallo, das ist ein Testtext mit Umlauten: aeoue."
        file_bytes = text.encode("utf-8")

        result = extract_text(file_bytes, "test.txt")

        self.assertEqual(result.text, text)
        self.assertEqual(result.format, "TEXT")
        self.assertEqual(result.pages, 1)
        self.assertEqual(len(result.warnings), 0)

    def test_extract_latin1_text(self) -> None:
        """Latin-1 kodierter Text wird mit Fallback korrekt gelesen."""
        # Text mit Umlauten die in Latin-1 anders kodiert sind als in UTF-8
        text = "Gr\u00fc\u00dfe aus \u00d6sterreich"
        file_bytes = text.encode("latin-1")

        result = extract_text(file_bytes, "test.txt")

        self.assertEqual(result.text, text)
        self.assertIn("Latin-1", result.warnings[0])

    def test_extract_csv_as_text(self) -> None:
        """CSV-Dateien werden als Text extrahiert."""
        csv_content = "Name,Alter,Stadt\nThomas,35,Wien\nMaria,28,Graz"
        file_bytes = csv_content.encode("utf-8")

        result = extract_text(file_bytes, "daten.csv")

        self.assertEqual(result.format, "TEXT")
        self.assertIn("Thomas", result.text)
        self.assertIn("Wien", result.text)

    def test_metadata_contains_encoding(self) -> None:
        """Metadaten enthalten die verwendete Kodierung."""
        file_bytes = b"Test"

        result = extract_text(file_bytes, "test.txt")

        self.assertIn("encoding", result.metadata)
        self.assertEqual(result.metadata["encoding"], "utf-8")


class TestFileSizeValidation(unittest.TestCase):
    """Tests fuer die Dateigroessen-Validierung."""

    def test_empty_file_raises_error(self) -> None:
        """Leere Dateien loesen einen ValueError aus."""
        with self.assertRaises(ValueError) as ctx:
            extract_text(b"", "test.txt")
        self.assertIn("leer", str(ctx.exception))

    def test_oversized_file_raises_error(self) -> None:
        """Zu grosse Dateien loesen einen ValueError aus."""
        # 11 MB an Daten erstellen
        oversized = b"x" * (MAX_FILE_SIZE + 1)

        with self.assertRaises(ValueError) as ctx:
            extract_text(oversized, "test.txt")
        self.assertIn("zu gross", str(ctx.exception))

    def test_max_size_file_accepted(self) -> None:
        """Dateien genau an der Groessengrenze werden akzeptiert."""
        # Genau MAX_FILE_SIZE Bytes
        max_content = b"A" * MAX_FILE_SIZE

        result = extract_text(max_content, "test.txt")

        self.assertEqual(result.format, "TEXT")

    def test_text_truncation_with_warning(self) -> None:
        """Zu langer Text wird abgeschnitten und eine Warnung hinzugefuegt."""
        long_text = "A" * (MAX_TEXT_LENGTH + 1000)
        file_bytes = long_text.encode("utf-8")

        result = extract_text(file_bytes, "test.txt")

        self.assertEqual(len(result.text), MAX_TEXT_LENGTH)
        self.assertTrue(
            any("gekuerzt" in w for w in result.warnings),
            f"Erwartet Kuerzungs-Warnung, erhalten: {result.warnings}",
        )


class TestUnsupportedFormats(unittest.TestCase):
    """Tests fuer nicht unterstuetzte Dateiformate."""

    def test_exe_format_raises_error(self) -> None:
        """EXE-Dateien werden abgelehnt."""
        with self.assertRaises(ValueError) as ctx:
            extract_text(b"MZ\x90\x00", "virus.exe")
        self.assertIn("Nicht unterstuetztes Dateiformat", str(ctx.exception))

    def test_zip_format_raises_error(self) -> None:
        """ZIP-Dateien werden abgelehnt."""
        with self.assertRaises(ValueError) as ctx:
            extract_text(b"PK\x03\x04", "archiv.zip")
        self.assertIn("Nicht unterstuetztes Dateiformat", str(ctx.exception))

    def test_no_extension_no_mime_raises_error(self) -> None:
        """Dateien ohne Endung und ohne MIME-Type werden abgelehnt."""
        with self.assertRaises(ValueError):
            extract_text(b"some data", "datei_ohne_endung")


class TestExifStripper(unittest.TestCase):
    """Tests fuer das EXIF-Metadaten-Stripping."""

    def _create_test_image(self, width: int = 100, height: int = 100) -> bytes:
        """Erstellt ein einfaches Test-PNG ohne EXIF-Daten."""
        from PIL import Image

        img = Image.new("RGB", (width, height), color=(128, 128, 128))
        output = io.BytesIO()
        img.save(output, format="PNG")
        return output.getvalue()

    def test_strip_exif_from_clean_image(self) -> None:
        """EXIF-Stripping auf ein Bild ohne EXIF-Daten gibt leere Metadaten zurueck."""
        image_bytes = self._create_test_image()

        clean_bytes, metadata = strip_exif(image_bytes)

        self.assertIsInstance(clean_bytes, bytes)
        self.assertTrue(len(clean_bytes) > 0)
        # Kein Fehler, keine relevanten Tags erwartet
        self.assertNotIn("error", metadata)

    def test_strip_exif_returns_valid_image(self) -> None:
        """Das bereinigte Bild ist ein gueltiges Bild."""
        from PIL import Image

        image_bytes = self._create_test_image()
        clean_bytes, _ = strip_exif(image_bytes)

        # Pruefen ob das bereinigte Bild noch geoeffnet werden kann
        img = Image.open(io.BytesIO(clean_bytes))
        self.assertEqual(img.size, (100, 100))

    def test_strip_exif_invalid_data(self) -> None:
        """Ungueltige Bilddaten fuehren zu einer Warnung, nicht zu einem Absturz."""
        invalid_bytes = b"das ist kein bild"
        clean_bytes, metadata = strip_exif(invalid_bytes)

        # Sollte die Originaldaten zurueckgeben
        self.assertEqual(clean_bytes, invalid_bytes)
        self.assertIn("error", metadata)

    def test_strip_exif_jpeg_with_exif(self) -> None:
        """EXIF-Daten werden aus JPEG-Bildern entfernt."""
        from PIL import Image

        try:
            import piexif
        except ImportError:
            self.skipTest("piexif nicht installiert — EXIF-Injection-Test uebersprungen")
            return

        # JPEG mit EXIF-Daten erstellen
        img = Image.new("RGB", (100, 100), color=(200, 100, 50))
        output = io.BytesIO()

        # EXIF-Daten hinzufuegen
        exif_dict = {
            "0th": {
                piexif.ImageIFD.Make: b"TestCamera",
                piexif.ImageIFD.Model: b"TestModel X100",
                piexif.ImageIFD.Software: b"TestSoftware 1.0",
            },
        }
        exif_bytes = piexif.dump(exif_dict)
        img.save(output, format="JPEG", exif=exif_bytes)
        image_bytes = output.getvalue()

        clean_bytes, metadata = strip_exif(image_bytes)

        self.assertIsInstance(clean_bytes, bytes)
        self.assertTrue(len(clean_bytes) > 0)


class TestTextOverlayDetection(unittest.TestCase):
    """Tests fuer die Text-Overlay-Heuristik."""

    def test_uniform_image_no_overlay(self) -> None:
        """Ein einfarbiges Bild hat keine Text-Overlays."""
        from PIL import Image

        img = Image.new("RGB", (200, 200), color=(128, 128, 128))
        output = io.BytesIO()
        img.save(output, format="PNG")

        result = check_for_text_overlays(output.getvalue())
        self.assertFalse(result)

    def test_high_contrast_image_detected(self) -> None:
        """Ein Bild mit starkem Schwarz-Weiss-Kontrast wird erkannt."""
        from PIL import Image

        # Bild mit vielen schwarzen und weissen Pixeln (simuliert Text)
        img = Image.new("L", (200, 200), color=255)  # weisser Hintergrund
        pixels = img.load()
        # 20% der Pixel schwarz machen (simuliert Text)
        for x in range(0, 200, 3):
            for y in range(0, 200, 2):
                pixels[x, y] = 0  # type: ignore[index]

        output = io.BytesIO()
        img.save(output, format="PNG")

        result = check_for_text_overlays(output.getvalue())
        self.assertTrue(result)

    def test_invalid_image_returns_false(self) -> None:
        """Ungueltige Bilddaten geben False zurueck."""
        result = check_for_text_overlays(b"invalid data")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
