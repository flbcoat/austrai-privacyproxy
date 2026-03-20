"""Tests for the PII detection service."""

import os
import sys
import unittest

# Ensure the backend directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set a dummy API key so config can load (detector tests don't call LLM)
os.environ.setdefault("MISTRAL_API_KEY", "test-key-not-used")

from app.models import Entity
from app.services.detector import (
    detect,
    generate_annotated_html,
    init_analyzer,
    _resolve_overlaps,
)


def setUpModule() -> None:
    """Initialize the analyzer once for all tests in this module."""
    init_analyzer()


class TestDetector(unittest.TestCase):
    """Test PII detection with Austrian text samples."""

    def test_detect_person_names(self) -> None:
        """Test that person names are detected."""
        text = "Sehr geehrter Herr Thomas Gruber, vielen Dank für Ihre Nachricht."
        entities = detect(text)
        person_entities = [e for e in entities if e.entity_type == "PERSON"]
        self.assertTrue(
            len(person_entities) > 0,
            f"Expected at least one PERSON entity, got: {entities}",
        )
        detected_texts = [e.text for e in person_entities]
        self.assertTrue(
            any("Gruber" in t for t in detected_texts),
            f"Expected 'Gruber' to be in detected persons: {detected_texts}",
        )

    def test_detect_austrian_iban(self) -> None:
        """Test that Austrian IBAN numbers are detected."""
        text = "Bitte überweisen Sie auf IBAN AT48 3200 0000 1234 5678."
        entities = detect(text)
        iban_entities = [e for e in entities if e.entity_type == "AT_IBAN"]
        self.assertTrue(
            len(iban_entities) > 0,
            f"Expected AT_IBAN entity, got: {entities}",
        )
        self.assertIn("AT48 3200 0000 1234 5678", iban_entities[0].text)

    def test_detect_austrian_uid(self) -> None:
        """Test that Austrian UID numbers are detected."""
        text = "Die UID-Nummer lautet ATU12345678."
        entities = detect(text)
        uid_entities = [e for e in entities if e.entity_type == "AT_UID_NR"]
        self.assertTrue(
            len(uid_entities) > 0,
            f"Expected AT_UID_NR entity, got: {entities}",
        )
        self.assertEqual(uid_entities[0].text, "ATU12345678")

    def test_detect_austrian_phone_international(self) -> None:
        """Test that Austrian international phone numbers are detected."""
        text = "Erreichen Sie mich unter +43 1 234 5678."
        entities = detect(text)
        phone_entities = [e for e in entities if e.entity_type == "PHONE_NUMBER"]
        self.assertTrue(
            len(phone_entities) > 0,
            f"Expected PHONE_NUMBER entity, got: {entities}",
        )

    def test_detect_austrian_firmenbuch(self) -> None:
        """Test that Austrian Firmenbuch numbers are detected."""
        text = "Die Alpentech Digital GmbH (FN 234567a) ist registriert."
        entities = detect(text)
        fb_entities = [e for e in entities if e.entity_type == "AT_FIRMENBUCH_NR"]
        self.assertTrue(
            len(fb_entities) > 0,
            f"Expected AT_FIRMENBUCH_NR entity, got: {entities}",
        )

    def test_detect_multiple_entities(self) -> None:
        """Test detection of multiple entity types in a single text."""
        text = (
            "Herr Thomas Gruber (UID: ATU12345678) bittet um Überweisung "
            "auf IBAN AT48 3200 0000 1234 5678. Tel: +43 1 234 5678."
        )
        entities = detect(text)
        entity_types = {e.entity_type for e in entities}

        self.assertIn("AT_UID_NR", entity_types, f"Missing AT_UID_NR in {entity_types}")
        self.assertIn("AT_IBAN", entity_types, f"Missing AT_IBAN in {entity_types}")
        self.assertIn("PHONE_NUMBER", entity_types, f"Missing PHONE_NUMBER in {entity_types}")

    def test_annotated_html_contains_marks(self) -> None:
        """Test that annotated HTML contains <mark> tags for detected entities."""
        text = "Kontakt: Thomas Gruber, IBAN AT48 3200 0000 1234 5678."
        entities = detect(text)
        html_output = generate_annotated_html(text, entities)

        self.assertIn("<mark", html_output)
        self.assertIn("</mark>", html_output)
        self.assertIn("data-entity=", html_output)

    def test_annotated_html_empty_entities(self) -> None:
        """Test annotated HTML with no entities returns escaped text."""
        text = "Ein einfacher Text ohne personenbezogene Daten."
        html_output = generate_annotated_html(text, [])
        self.assertNotIn("<mark", html_output)
        self.assertEqual(html_output, text)

    def test_resolve_overlaps(self) -> None:
        """Test that overlapping entities are resolved by score."""
        entities = [
            Entity(entity_type="PERSON", start=0, end=10, score=0.85, text="0123456789"),
            Entity(entity_type="LOCATION", start=5, end=15, score=0.7, text="5678901234"),
        ]
        resolved = _resolve_overlaps(entities)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].entity_type, "PERSON")

    def test_confidence_threshold_filtering(self) -> None:
        """Test that entities below confidence threshold are filtered out."""
        text = "Ein normaler Satz."
        entities = detect(text)
        for entity in entities:
            self.assertGreaterEqual(entity.score, 0.6)


if __name__ == "__main__":
    unittest.main()
