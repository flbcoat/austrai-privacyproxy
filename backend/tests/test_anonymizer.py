"""Tests for the anonymization service."""

import os
import sys
import unittest

# Ensure the backend directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set a dummy API key so config can load
os.environ.setdefault("MISTRAL_API_KEY", "test-key-not-used")

from app.models import Entity
from app.services.anonymizer import anonymize


class TestAnonymizer(unittest.TestCase):
    """Test anonymization with placeholder replacement."""

    def test_single_entity_anonymization(self) -> None:
        """Test anonymization of a single entity."""
        text = "Thomas Gruber hat angerufen."
        entities = [
            Entity(entity_type="PERSON", start=0, end=13, score=0.9, text="Thomas Gruber"),
        ]
        anonymized, mappings = anonymize(text, entities)

        self.assertEqual(anonymized, "[PERSON_1] hat angerufen.")
        self.assertEqual(mappings["[PERSON_1]"], "Thomas Gruber")

    def test_multiple_entities_same_type(self) -> None:
        """Test anonymization of multiple entities of the same type."""
        text = "Thomas Gruber und Maria Steinbauer sind Kollegen."
        entities = [
            Entity(entity_type="PERSON", start=0, end=13, score=0.9, text="Thomas Gruber"),
            Entity(entity_type="PERSON", start=18, end=34, score=0.85, text="Maria Steinbauer"),
        ]
        anonymized, mappings = anonymize(text, entities)

        self.assertEqual(anonymized, "[PERSON_1] und [PERSON_2] sind Kollegen.")
        self.assertEqual(mappings["[PERSON_1]"], "Thomas Gruber")
        self.assertEqual(mappings["[PERSON_2]"], "Maria Steinbauer")

    def test_multiple_entity_types(self) -> None:
        """Test anonymization of different entity types."""
        text = "Thomas Gruber, IBAN AT48 3200 0000 1234 5678, ATU12345678."
        entities = [
            Entity(entity_type="PERSON", start=0, end=13, score=0.9, text="Thomas Gruber"),
            Entity(entity_type="AT_IBAN", start=20, end=44, score=0.95, text="AT48 3200 0000 1234 5678"),
            Entity(entity_type="AT_UID_NR", start=46, end=57, score=0.9, text="ATU12345678"),
        ]
        anonymized, mappings = anonymize(text, entities)

        self.assertIn("[PERSON_1]", anonymized)
        self.assertIn("[AT_IBAN_1]", anonymized)
        self.assertIn("[AT_UID_NR_1]", anonymized)
        self.assertEqual(len(mappings), 3)

    def test_overlapping_entities_resolved(self) -> None:
        """Test that overlapping entities are resolved (highest score wins)."""
        text = "ATU12345678 ist die Nummer."
        entities = [
            Entity(entity_type="AT_UID_NR", start=0, end=11, score=0.95, text="ATU12345678"),
            Entity(entity_type="LOCATION", start=0, end=5, score=0.6, text="ATU12"),
        ]
        anonymized, mappings = anonymize(text, entities)

        self.assertEqual(anonymized, "[AT_UID_NR_1] ist die Nummer.")
        self.assertEqual(len(mappings), 1)

    def test_empty_entities(self) -> None:
        """Test anonymization with no entities returns original text."""
        text = "Ein ganz normaler Satz."
        anonymized, mappings = anonymize(text, [])

        self.assertEqual(anonymized, text)
        self.assertEqual(len(mappings), 0)

    def test_position_preservation(self) -> None:
        """Test that replacing from end preserves positions correctly."""
        text = "A Thomas B Maria C"
        entities = [
            Entity(entity_type="PERSON", start=2, end=8, score=0.9, text="Thomas"),
            Entity(entity_type="PERSON", start=11, end=16, score=0.85, text="Maria"),
        ]
        anonymized, mappings = anonymize(text, entities)

        self.assertEqual(anonymized, "A [PERSON_1] B [PERSON_2] C")

    def test_mappings_are_bidirectional(self) -> None:
        """Test that mappings correctly map placeholder to original text."""
        text = "IBAN AT48 3200 0000 1234 5678 gehört Thomas Gruber."
        entities = [
            Entity(entity_type="AT_IBAN", start=5, end=29, score=0.95, text="AT48 3200 0000 1234 5678"),
            Entity(entity_type="PERSON", start=37, end=50, score=0.9, text="Thomas Gruber"),
        ]
        anonymized, mappings = anonymize(text, entities)

        # Verify we can reconstruct parts of the original from mappings
        for placeholder, original in mappings.items():
            self.assertIn(placeholder, anonymized)
            self.assertIn(original, text)


if __name__ == "__main__":
    unittest.main()
