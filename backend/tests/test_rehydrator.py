"""Tests for the rehydration service."""

import os
import sys
import unittest

# Ensure the backend directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set a dummy API key so config can load
os.environ.setdefault("MISTRAL_API_KEY", "test-key-not-used")

from app.services.rehydrator import rehydrate, _build_fuzzy_pattern


class TestRehydrator(unittest.TestCase):
    """Test rehydration with exact, case-insensitive, and fuzzy matching."""

    def test_exact_match(self) -> None:
        """Test exact placeholder replacement."""
        llm_response = "Sehr geehrter [PERSON_1], Ihre IBAN [AT_IBAN_1] wurde bestätigt."
        mappings = {
            "[PERSON_1]": "Thomas Gruber",
            "[AT_IBAN_1]": "AT48 3200 0000 1234 5678",
        }
        result = rehydrate(llm_response, mappings)

        self.assertEqual(
            result,
            "Sehr geehrter Thomas Gruber, Ihre IBAN AT48 3200 0000 1234 5678 wurde bestätigt.",
        )

    def test_case_insensitive_match(self) -> None:
        """Test case-insensitive placeholder replacement."""
        llm_response = "Kontakt: [person_1] unter [phone_number_1]."
        mappings = {
            "[PERSON_1]": "Maria Steinbauer",
            "[PHONE_NUMBER_1]": "+43 1 234 5678",
        }
        result = rehydrate(llm_response, mappings)

        self.assertEqual(result, "Kontakt: Maria Steinbauer unter +43 1 234 5678.")

    def test_fuzzy_match_missing_brackets(self) -> None:
        """Test fuzzy matching when LLM drops brackets."""
        llm_response = "Lieber PERSON_1, bitte kontaktieren Sie PHONE_NUMBER_1."
        mappings = {
            "[PERSON_1]": "Stefan Wimmer",
            "[PHONE_NUMBER_1]": "+43 660 1234567",
        }
        result = rehydrate(llm_response, mappings)

        self.assertIn("Stefan Wimmer", result)
        self.assertIn("+43 660 1234567", result)

    def test_fuzzy_match_extra_spaces(self) -> None:
        """Test fuzzy matching when LLM adds spaces inside brackets."""
        llm_response = "Die UID [ AT_UID_NR_1 ] ist gültig."
        mappings = {
            "[AT_UID_NR_1]": "ATU12345678",
        }
        result = rehydrate(llm_response, mappings)

        self.assertIn("ATU12345678", result)

    def test_empty_mappings(self) -> None:
        """Test rehydration with no mappings returns original text."""
        llm_response = "Eine normale Antwort ohne Platzhalter."
        result = rehydrate(llm_response, {})

        self.assertEqual(result, llm_response)

    def test_multiple_same_placeholder(self) -> None:
        """Test that a placeholder used multiple times in the response gets replaced."""
        llm_response = "[PERSON_1] hat bestätigt. Wir danken [PERSON_1]."
        mappings = {"[PERSON_1]": "Elisabeth Moser"}
        result = rehydrate(llm_response, mappings)

        self.assertEqual(result, "Elisabeth Moser hat bestätigt. Wir danken Elisabeth Moser.")

    def test_longest_placeholder_first(self) -> None:
        """Test that longer placeholders are processed before shorter ones."""
        llm_response = "[PERSON_1] und [PERSON_10] waren anwesend."
        mappings = {
            "[PERSON_1]": "Anna",
            "[PERSON_10]": "Bernhard",
        }
        result = rehydrate(llm_response, mappings)

        self.assertEqual(result, "Anna und Bernhard waren anwesend.")

    def test_fuzzy_match_parentheses(self) -> None:
        """Test fuzzy matching when LLM uses parentheses instead of brackets."""
        llm_response = "Kontakt: (PERSON_1) ist erreichbar."
        mappings = {
            "[PERSON_1]": "Katharina Hofer",
        }
        result = rehydrate(llm_response, mappings)

        self.assertIn("Katharina Hofer", result)

    def test_build_fuzzy_pattern(self) -> None:
        """Test that fuzzy patterns are valid regex."""
        import re

        pattern = _build_fuzzy_pattern("[PERSON_1]")
        compiled = re.compile(pattern, re.IGNORECASE)

        # Should match various forms
        self.assertIsNotNone(compiled.search("[PERSON_1]"))
        self.assertIsNotNone(compiled.search("PERSON_1"))
        self.assertIsNotNone(compiled.search("PERSON 1"))
        self.assertIsNotNone(compiled.search("(PERSON_1)"))

    def test_preserves_surrounding_text(self) -> None:
        """Test that text around placeholders is preserved."""
        llm_response = "Anfang [PERSON_1] Mitte [AT_IBAN_1] Ende."
        mappings = {
            "[PERSON_1]": "Test Person",
            "[AT_IBAN_1]": "AT00 0000 0000 0000 0000",
        }
        result = rehydrate(llm_response, mappings)

        self.assertEqual(result, "Anfang Test Person Mitte AT00 0000 0000 0000 0000 Ende.")


if __name__ == "__main__":
    unittest.main()
