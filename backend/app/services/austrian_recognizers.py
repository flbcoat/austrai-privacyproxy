"""Custom Presidio recognizers for Austrian PII patterns."""

from presidio_analyzer import PatternRecognizer, Pattern


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


class AustrianSVNrRecognizer(PatternRecognizer):
    """Erkennung österreichischer Sozialversicherungsnummern."""

    def __init__(self) -> None:
        patterns = [
            Pattern(
                name="at_svnr_pattern",
                regex=r"\b\d{4}\s?\d{6}\b",
                score=0.4,
            ),
        ]
        super().__init__(
            supported_entity="AT_SVNR",
            patterns=patterns,
            name="Austrian SVNr Recognizer",
            supported_language="de",
            context=[
                "Sozialversicherungsnummer",
                "SVNr",
                "SV-Nr",
                "Versicherungsnummer",
                "SVNR",
            ],
        )


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


def get_all_austrian_recognizers() -> list[PatternRecognizer]:
    """Returns a list of all Austrian custom recognizers."""
    return [
        AustrianUIDRecognizer(),
        AustrianIBANRecognizer(),
        AustrianSVNrRecognizer(),
        AustrianPhoneRecognizer(),
        AustrianFirmenbuchRecognizer(),
    ]
