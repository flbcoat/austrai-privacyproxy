"""EXIF-Metadaten-Stripping fuer Bilder — Datenschutz-relevante Metadaten entfernen."""

import io
import logging
from typing import Any

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

logger = logging.getLogger(__name__)

# EXIF-Tags die auf persoenliche Daten hinweisen
PRIVACY_RELEVANT_TAGS: set[str] = {
    "GPSInfo",
    "GPSLatitude",
    "GPSLongitude",
    "GPSLatitudeRef",
    "GPSLongitudeRef",
    "GPSAltitude",
    "GPSAltitudeRef",
    "GPSTimeStamp",
    "GPSDateStamp",
    "Make",
    "Model",
    "LensMake",
    "LensModel",
    "Software",
    "DateTime",
    "DateTimeOriginal",
    "DateTimeDigitized",
    "Artist",
    "Copyright",
    "ImageDescription",
    "XPAuthor",
    "XPComment",
    "XPKeywords",
    "XPSubject",
    "XPTitle",
    "CameraSerialNumber",
    "BodySerialNumber",
    "LensSerialNumber",
    "HostComputer",
    "ImageUniqueID",
}


def _decode_gps_coordinate(
    gps_values: tuple[Any, ...],
    ref: str,
) -> float | None:
    """Konvertiert GPS-EXIF-Daten in Dezimalgrad.

    Args:
        gps_values: Tuple mit (Grad, Minuten, Sekunden) als IFDRational.
        ref: Himmelsrichtung ('N', 'S', 'E', 'W').

    Returns:
        Dezimalgrad-Wert oder None bei Fehler.
    """
    try:
        degrees = float(gps_values[0])
        minutes = float(gps_values[1])
        seconds = float(gps_values[2])
        decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        return None


def _extract_gps_info(gps_data: dict[int, Any]) -> dict[str, Any]:
    """Extrahiert GPS-Koordinaten aus EXIF-GPSInfo.

    Args:
        gps_data: Rohe GPS-EXIF-Daten (Tag-ID -> Wert).

    Returns:
        Dict mit lesbaren GPS-Informationen.
    """
    gps_info: dict[str, Any] = {}

    # Tag-IDs auf lesbare Namen mappen
    readable: dict[str, Any] = {}
    for tag_id, value in gps_data.items():
        tag_name = GPSTAGS.get(tag_id, str(tag_id))
        readable[tag_name] = value

    # Latitude
    if "GPSLatitude" in readable and "GPSLatitudeRef" in readable:
        lat = _decode_gps_coordinate(
            readable["GPSLatitude"],
            readable["GPSLatitudeRef"],
        )
        if lat is not None:
            gps_info["latitude"] = lat

    # Longitude
    if "GPSLongitude" in readable and "GPSLongitudeRef" in readable:
        lon = _decode_gps_coordinate(
            readable["GPSLongitude"],
            readable["GPSLongitudeRef"],
        )
        if lon is not None:
            gps_info["longitude"] = lon

    # Altitude
    if "GPSAltitude" in readable:
        try:
            alt = float(readable["GPSAltitude"])
            ref = readable.get("GPSAltitudeRef", 0)
            if ref == 1:
                alt = -alt
            gps_info["altitude_m"] = round(alt, 1)
        except (TypeError, ValueError):
            pass

    # Zeitstempel
    if "GPSDateStamp" in readable:
        gps_info["gps_date"] = str(readable["GPSDateStamp"])
    if "GPSTimeStamp" in readable:
        try:
            h, m, s = readable["GPSTimeStamp"]
            gps_info["gps_time"] = f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
        except (TypeError, ValueError):
            pass

    return gps_info


def strip_exif(image_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    """Entfernt EXIF-Metadaten aus einem Bild und gibt extrahierte Metadaten zurueck.

    Args:
        image_bytes: Rohbild-Bytes.

    Returns:
        Tuple aus (bereinigte_bild_bytes, extrahierte_metadaten).
        extrahierte_metadaten enthaelt: GPS-Koordinaten, Kameramodell,
        Zeitstempel, Software, etc. — sofern vorhanden.
    """
    extracted_metadata: dict[str, Any] = {}

    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        logger.warning("Bild konnte nicht geoeffnet werden fuer EXIF-Stripping: %s", e)
        return image_bytes, {"error": f"Bild konnte nicht gelesen werden: {type(e).__name__}"}

    # EXIF-Daten auslesen (sofern vorhanden)
    exif_data = img.getexif()

    if exif_data:
        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, str(tag_id))

            if tag_name == "GPSInfo":
                gps_info = _extract_gps_info(value if isinstance(value, dict) else {})
                if gps_info:
                    extracted_metadata["gps"] = gps_info
            elif tag_name in PRIVACY_RELEVANT_TAGS:
                try:
                    extracted_metadata[tag_name] = str(value)
                except Exception:
                    extracted_metadata[tag_name] = "<nicht lesbar>"

        # IFD-Daten (z.B. EXIF-Sub-IFD) ebenfalls pruefen
        for ifd_key in exif_data.get_ifd(0x8769) if 0x8769 in exif_data else {}:
            tag_name = TAGS.get(ifd_key, str(ifd_key))
            if tag_name in PRIVACY_RELEVANT_TAGS:
                try:
                    extracted_metadata[tag_name] = str(exif_data.get_ifd(0x8769)[ifd_key])
                except Exception:
                    pass

    # Bild ohne EXIF-Daten speichern
    output = io.BytesIO()
    original_format = img.format or "PNG"

    # Fuer JPEG: Qualitaet beibehalten
    save_kwargs: dict[str, Any] = {}
    if original_format.upper() in ("JPEG", "JPG"):
        save_kwargs["quality"] = 95
        save_kwargs["optimize"] = True
    elif original_format.upper() == "PNG":
        save_kwargs["optimize"] = True
    elif original_format.upper() == "WEBP":
        save_kwargs["quality"] = 95

    try:
        # Bild ohne EXIF speichern (exif=b"" entfernt alle EXIF-Daten)
        img.save(output, format=original_format, exif=b"", **save_kwargs)
    except TypeError:
        # Manche Formate unterstuetzen den exif-Parameter nicht
        img.save(output, format=original_format, **save_kwargs)

    clean_bytes = output.getvalue()

    if extracted_metadata:
        tag_count = len(extracted_metadata)
        has_gps = "gps" in extracted_metadata
        logger.info(
            "EXIF-Stripping: %d datenschutz-relevante Tags entfernt%s.",
            tag_count,
            " (inkl. GPS-Koordinaten)" if has_gps else "",
        )

    return clean_bytes, extracted_metadata


def check_for_text_overlays(image_bytes: bytes) -> bool:
    """Einfache Heuristik: Prueft ob ein Bild moeglicherweise Text-Overlays enthaelt.

    Basiert auf der Analyse von Kontrasten und Farbverteilung.
    Ein hoher Anteil an reinem Schwarz/Weiss in Kombination mit scharfen
    Kanten kann auf Text-Overlays hindeuten.

    Args:
        image_bytes: Rohbild-Bytes.

    Returns:
        True wenn Text-Overlays vermutet werden, sonst False.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        # In Graustufen konvertieren
        gray = img.convert("L")
        pixels = list(gray.getdata())
        total = len(pixels)
        if total == 0:
            return False

        # Anteil sehr heller (>250) und sehr dunkler (<5) Pixel
        very_dark = sum(1 for p in pixels if p < 5)
        very_bright = sum(1 for p in pixels if p > 250)

        dark_ratio = very_dark / total
        bright_ratio = very_bright / total

        # Heuristik: Wenn >5% sehr dunkel UND >5% sehr hell
        # (typisch fuer schwarzen Text auf hellem Hintergrund)
        return dark_ratio > 0.05 and bright_ratio > 0.05
    except Exception:
        return False
