"""Custom Presidio recognizers for Austrian PII patterns."""

import re
from typing import Optional

from presidio_analyzer import PatternRecognizer, Pattern, EntityRecognizer
from presidio_analyzer import RecognizerResult


class AustrianUIDRecognizer(PatternRecognizer):
    """Erkennung österreichischer UID-Nummern (Umsatzsteuer-Identifikationsnummer)."""

    def __init__(self) -> None:
        patterns = [
            Pattern(
                name="at_uid_pattern",
                regex=r"\bATU\d{8}\b",
                score=0.9,
            ),
        ]
        super().__init__(
            supported_entity="AT_UID_NR",
            patterns=patterns,
            name="Austrian UID Recognizer",
            supported_language="de",
            context=["UID", "UID-Nummer", "Umsatzsteuer", "ATU", "UID-Nr"],
        )


class AustrianIBANRecognizer(PatternRecognizer):
    """Erkennung österreichischer IBAN-Nummern."""

    def __init__(self) -> None:
        patterns = [
            Pattern(
                name="at_iban_pattern",
                regex=r"\bAT\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b",
                score=0.95,
            ),
        ]
        super().__init__(
            supported_entity="AT_IBAN",
            patterns=patterns,
            name="Austrian IBAN Recognizer",
            supported_language="de",
            context=["IBAN", "Konto", "Bankverbindung", "Kontonummer", "Überweisung"],
        )


class AustrianSVNrRecognizer(EntityRecognizer):
    """Erkennung österreichischer Sozialversicherungsnummern.

    Verwendet einen custom analyze()-Ansatz statt PatternRecognizer,
    weil die SVNr (4+6 Ziffern) zu generisch ist und einen Kontext-Prefix braucht.
    """

    SVNR_PATTERN = re.compile(r"\b(\d{4}\s?\d{6})\b")
    SVNR_PREFIXES = re.compile(
        r"(?:SVNr|SVNR|SV-Nr|SV-Nummer|Versicherungsnummer|Sozialversicherungsnummer)"
        r"[.:\s]*$",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["AT_SVNR"],
            name="Austrian SVNr Recognizer",
            supported_language="de",
        )

    def load(self) -> None:
        pass

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts=None,
    ) -> list[RecognizerResult]:
        results = []
        for match in self.SVNR_PATTERN.finditer(text):
            prefix = text[:match.start()]
            if self.SVNR_PREFIXES.search(prefix):
                results.append(
                    RecognizerResult(
                        entity_type="AT_SVNR",
                        start=match.start(),
                        end=match.end(),
                        score=0.95,
                    )
                )
        return results


class AustrianPhoneRecognizer(PatternRecognizer):
    """Erkennung österreichischer Telefonnummern."""

    def __init__(self) -> None:
        patterns = [
            Pattern(
                name="at_phone_international",
                regex=r"\+43\s?\d{1,4}[\s/\-]?\d{3,}[\s/\-]?\d{0,}",
                score=0.85,
            ),
            Pattern(
                name="at_phone_local",
                regex=r"\b0\d{1,4}[\s/\-]?\d{3,}[\s/\-]?\d{0,}",
                score=0.7,
            ),
        ]
        super().__init__(
            supported_entity="PHONE_NUMBER",
            patterns=patterns,
            name="Austrian Phone Recognizer",
            supported_language="de",
            context=["Telefon", "Tel", "Handy", "Mobil", "Rufnummer", "erreichbar", "anrufen"],
        )


class AustrianFirmenbuchRecognizer(PatternRecognizer):
    """Erkennung österreichischer Firmenbuchnummern."""

    def __init__(self) -> None:
        patterns = [
            Pattern(
                name="at_firmenbuch_pattern",
                regex=r"\bFN\s?\d{5,6}\s?[a-z]\b",
                score=0.9,
            ),
        ]
        super().__init__(
            supported_entity="AT_FIRMENBUCH_NR",
            patterns=patterns,
            name="Austrian Firmenbuch Recognizer",
            supported_language="de",
            context=["Firmenbuch", "Firmenbuchnummer", "FN", "Firmenbuch-Nr", "Handelsregister"],
        )


class DocumentMetadataRecognizer(EntityRecognizer):
    """Erkennung von Dokument-Metadaten wie 'Erstellt fuer', 'Auftraggeber:', etc.

    Erkennt den WERT nach typischen Dokumentlabels, nicht das Label selbst.
    Zum Beispiel: Bei 'Auftraggeber: Max Mustermann GmbH' wird
    'Max Mustermann GmbH' als DOC_METADATA erkannt.
    """

    METADATA_PATTERN = re.compile(
        r"(?:erstellt\s+f[uü]r|Auftraggeber|Kunde|im\s+Auftrag\s+von|"
        r"Ansprechpartner|Empf[aä]nger|Projektleiter|Bearbeiter)"
        r"[:\s]+(.+?)(?:\n|$)",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["DOC_METADATA"],
            name="Document Metadata Recognizer",
            supported_language="de",
        )

    def load(self) -> None:
        pass

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts=None,
    ) -> list[RecognizerResult]:
        results = []
        for match in self.METADATA_PATTERN.finditer(text):
            value = match.group(1).strip()
            if not value or len(value) < 2:
                continue
            # Position des Werts (group 1), nicht des gesamten Matches
            value_start = match.start(1)
            value_end = match.start(1) + len(value)
            results.append(
                RecognizerResult(
                    entity_type="DOC_METADATA",
                    start=value_start,
                    end=value_end,
                    score=0.85,
                )
            )
        return results


def get_all_austrian_recognizers() -> list[EntityRecognizer]:
    """Returns a list of all Austrian custom recognizers."""
    return [
        AustrianUIDRecognizer(),
        AustrianIBANRecognizer(),
        AustrianSVNrRecognizer(),
        AustrianPhoneRecognizer(),
        AustrianFirmenbuchRecognizer(),
        DocumentMetadataRecognizer(),
    ]
