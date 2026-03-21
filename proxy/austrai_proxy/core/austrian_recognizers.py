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


class CredentialsRecognizer(EntityRecognizer):
    """Erkennt Passwörter, API Keys, Tokens, Connection Strings und andere Secrets.

    Erkennt den WERT nach typischen Labels:
    - Passwort/Password/Kennwort/PIN: der Wert danach
    - API Keys: sk-..., pk_..., api_..., key-..., token_...
    - Bearer Tokens: Bearer eyJ...
    - Connection Strings: postgres://, mysql://, mongodb://
    - Private Keys: -----BEGIN ... KEY-----
    - AWS Keys: AKIA...
    """

    # Pattern 1: Password/Kennwort in context
    PASSWORD_PATTERN = re.compile(
        r"(?:passwort|password|kennwort|pwd|pin|passphrase|secret|geheimwort|zugangscode)"
        r"[\s:=]+[\"']?(\S{4,})[\"']?",
        re.IGNORECASE,
    )

    # Pattern 2: API Keys (common prefixes)
    API_KEY_PATTERN = re.compile(
        r"\b(sk-[a-zA-Z0-9_-]{20,}|pk_[a-zA-Z0-9_-]{20,}|"
        r"api[_-][a-zA-Z0-9_-]{20,}|key[_-][a-zA-Z0-9_-]{20,}|"
        r"token[_-][a-zA-Z0-9_-]{20,}|"
        r"ghp_[a-zA-Z0-9]{36,}|"
        r"gho_[a-zA-Z0-9]{36,}|"
        r"glpat-[a-zA-Z0-9_-]{20,}|"
        r"xox[bpsa]-[a-zA-Z0-9-]{10,}|"
        r"AKIA[A-Z0-9]{16})\b",
    )

    # Pattern 3: Bearer tokens
    BEARER_PATTERN = re.compile(
        r"Bearer\s+(eyJ[a-zA-Z0-9_-]{20,}\.eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,})",
    )

    # Pattern 4: Connection strings
    CONN_STRING_PATTERN = re.compile(
        r"((?:postgres(?:ql)?|mysql|mongodb|redis|amqp|sqlite)://\S{10,})",
        re.IGNORECASE,
    )

    # Pattern 5: Private keys
    PRIVATE_KEY_PATTERN = re.compile(
        r"(-----BEGIN\s+(?:RSA\s+)?(?:PRIVATE|EC)\s+KEY-----[\s\S]{20,}?-----END\s+(?:RSA\s+)?(?:PRIVATE|EC)\s+KEY-----)",
    )

    # Pattern 6: Generic "mein X ist Y" pattern for secrets
    MY_SECRET_PATTERN = re.compile(
        r"(?:mein|my|unser)\s+(?:passwort|password|kennwort|pin|key|token|secret|zugangscode)"
        r"\s+(?:ist|is|lautet|=)\s+[\"']?(\S{4,})[\"']?",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["CREDENTIAL"],
            name="Credentials Recognizer",
            supported_language="de",
        )

    def load(self) -> None:
        pass

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts=None,
    ) -> list[RecognizerResult]:
        results = []

        for pattern in [
            self.PASSWORD_PATTERN,
            self.MY_SECRET_PATTERN,
        ]:
            for match in pattern.finditer(text):
                value = match.group(1)
                results.append(RecognizerResult(
                    entity_type="CREDENTIAL",
                    start=match.start(1),
                    end=match.start(1) + len(value),
                    score=0.9,
                ))

        for pattern in [
            self.API_KEY_PATTERN,
            self.BEARER_PATTERN,
            self.CONN_STRING_PATTERN,
            self.PRIVATE_KEY_PATTERN,
        ]:
            for match in pattern.finditer(text):
                value = match.group(1)
                results.append(RecognizerResult(
                    entity_type="CREDENTIAL",
                    start=match.start(1),
                    end=match.start(1) + len(value),
                    score=0.95,
                ))

        return results


class EUDataProtectionRecognizer(PatternRecognizer):
    """Erkennt EU-weit relevante personenbezogene Daten (DSGVO Art. 4 + Art. 9).

    Abgedeckt:
    - IP-Adressen (IPv4 + IPv6)
    - Deutsche/EU IBANs (DE, AT, CH, etc.)
    - Kreditkartennummern (Visa, Mastercard, Amex)
    - Geburtsdaten in verschiedenen Formaten
    - KFZ-Kennzeichen (AT, DE)
    - Passnummern
    - Steuernummern (DE)
    """

    def __init__(self) -> None:
        patterns = [
            # IPv4
            Pattern("ipv4", r"\b(?:\d{1,3}\.){3}\d{1,3}\b", 0.6),
            # IPv6 (simplified)
            Pattern("ipv6", r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b", 0.8),
            # EU IBANs (2 letter country + 2 check + up to 30 alphanumeric)
            Pattern("eu_iban", r"\b[A-Z]{2}\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?[\d\s]{0,10}\b", 0.85),
            # Credit cards (Visa, MC, Amex)
            Pattern("visa", r"\b4\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", 0.8),
            Pattern("mastercard", r"\b5[1-5]\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", 0.8),
            Pattern("amex", r"\b3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}\b", 0.8),
            # Birth dates (DD.MM.YYYY, DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD)
            Pattern("birthdate_de", r"\b(?:0[1-9]|[12]\d|3[01])\.(?:0[1-9]|1[0-2])\.\d{4}\b", 0.65),
            Pattern("birthdate_iso", r"\b\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b", 0.65),
            # AT license plates (W 12345X, G 1234 AB)
            Pattern("at_plate", r"\b[A-Z]{1,2}\s?\d{1,5}\s?[A-Z]{1,3}\b", 0.4),
            # DE license plates (M AB 1234)
            Pattern("de_plate", r"\b[A-ZÄÖÜ]{1,3}\s?[A-Z]{1,2}\s?\d{1,4}[EH]?\b", 0.4),
            # DE Steuernummer (11 digits with optional slashes)
            Pattern("de_steuer", r"\b\d{2,3}/?\.?\d{3,4}/?\.?\d{4,5}\b", 0.3),
            # Passport numbers (AT: 1 letter + 7 digits, DE: various)
            Pattern("passport_at", r"\b[A-Z]\d{7}\b", 0.4),
        ]
        super().__init__(
            supported_entity="EU_PII",
            patterns=patterns,
            name="EU Data Protection Recognizer",
            supported_language="de",
            context=[
                "IP", "Adresse", "IP-Adresse", "IBAN", "Konto", "Kreditkarte",
                "Visa", "Mastercard", "Geburtsdatum", "geboren", "geb.",
                "Kennzeichen", "Nummernschild", "Steuer", "Steuernummer",
                "Pass", "Reisepass", "Ausweis",
            ],
        )


class SensitiveDataRecognizer(EntityRecognizer):
    """Erkennt DSGVO Art. 9 besonders schuetzenswerte Daten im Kontext.

    Besondere Kategorien personenbezogener Daten:
    - Gesundheitsdaten (Diagnosen, Medikamente, Krankheiten)
    - Religionszugehoerigkeit
    - Politische Meinung / Parteimitgliedschaft
    - Gewerkschaftszugehoerigkeit
    - Ethnische Herkunft
    - Sexuelle Orientierung
    - Biometrische/genetische Daten
    """

    # Patterns that capture the VALUE after a sensitive keyword
    HEALTH_PATTERN = re.compile(
        r"(?:diagnose|befund|krankheit|erkrankung|medikament|therapie|behandlung|symptom|allergie)"
        r"[:\s]+[\"']?([A-Za-zÄÖÜäöüß][\w\s\-\.]{3,60}?)(?:[,\.\n]|$)",
        re.IGNORECASE,
    )

    RELIGION_PATTERN = re.compile(
        r"(?:religion|konfession|glaube|glaubensbekenntnis|religionszugehoerigkeit)"
        r"[:\s]+[\"']?([A-Za-zÄÖÜäöüß][\w\s\-]{2,30}?)(?:[,\.\n]|$)",
        re.IGNORECASE,
    )

    POLITICAL_PATTERN = re.compile(
        r"(?:partei|parteimitglied|politische\s+(?:meinung|ueberzeugung|orientierung))"
        r"[:\s]+[\"']?([A-Za-zÄÖÜäöüß][\w\s\-]{2,40}?)(?:[,\.\n]|$)",
        re.IGNORECASE,
    )

    ETHNICITY_PATTERN = re.compile(
        r"(?:ethni(?:e|sche\s+herkunft)|abstammung|nationalitaet|staatsangehoerigkeit)"
        r"[:\s]+[\"']?([A-Za-zÄÖÜäöüß][\w\s\-]{2,30}?)(?:[,\.\n]|$)",
        re.IGNORECASE,
    )

    UNION_PATTERN = re.compile(
        r"(?:gewerkschaft|gewerkschaftsmitglied(?:schaft)?|betriebsrat)"
        r"[:\s]+[\"']?([A-Za-zÄÖÜäöüß][\w\s\-]{2,40}?)(?:[,\.\n]|$)",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["SENSITIVE_DATA"],
            name="DSGVO Art.9 Sensitive Data Recognizer",
            supported_language="de",
        )

    def load(self) -> None:
        pass

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts=None,
    ) -> list[RecognizerResult]:
        results = []

        for pattern in [
            self.HEALTH_PATTERN,
            self.RELIGION_PATTERN,
            self.POLITICAL_PATTERN,
            self.ETHNICITY_PATTERN,
            self.UNION_PATTERN,
        ]:
            for match in pattern.finditer(text):
                value = match.group(1).strip()
                if len(value) >= 3:
                    results.append(RecognizerResult(
                        entity_type="SENSITIVE_DATA",
                        start=match.start(1),
                        end=match.start(1) + len(value),
                        score=0.85,
                    ))

        return results


class FirstNameRecognizer(EntityRecognizer):
    """Erkennt alleinstehende Vornamen anhand einer Namensliste.

    SpaCy erkennt Vornamen ohne Nachnamen oft nicht als PERSON.
    Diese Recognizer-Klasse verwendet eine Liste der haeufigsten
    deutschen/oesterreichischen Vornamen.
    """

    # Top 200 häufigste deutschsprachige Vornamen
    FIRST_NAMES = {
        # Weiblich
        "anna", "maria", "laura", "julia", "sarah", "sabine", "petra",
        "claudia", "monika", "andrea", "katharina", "elisabeth", "christine",
        "stefanie", "barbara", "nicole", "sandra", "martina", "susanne",
        "gabriele", "birgit", "angelika", "heike", "eva", "karin",
        "renate", "ursula", "ingrid", "helga", "silvia", "sonja",
        "lisa", "lena", "sophie", "emma", "mia", "hannah", "leonie",
        "marie", "johanna", "franziska", "verena", "diana", "melanie",
        "nadine", "simone", "jasmin", "manuela", "daniela", "cornelia",
        "doris", "margit", "anja", "tanja", "heidi", "ilse", "herta",
        "gisela", "gertrude", "brigitte", "irmgard", "hildegard",
        "rosa", "theresia", "margarete", "frieda", "paula", "nina",
        # Männlich
        "thomas", "michael", "andreas", "peter", "stefan", "markus",
        "christian", "martin", "daniel", "wolfgang", "robert", "johannes",
        "alexander", "bernhard", "franz", "josef", "karl", "helmut",
        "gerhard", "werner", "manfred", "hans", "heinz", "herbert",
        "walter", "georg", "rudolf", "friedrich", "wilhelm", "ernst",
        "heinrich", "otto", "klaus", "dieter", "horst", "jürgen",
        "rainer", "uwe", "frank", "bernd", "matthias", "florian",
        "sebastian", "david", "lukas", "felix", "tobias", "simon",
        "philipp", "benjamin", "maximilian", "moritz", "leon", "paul",
        "jakob", "elias", "noah", "jonas", "luca", "nico", "tim",
        "jan", "max", "oliver", "patrick", "christoph", "dominik",
        "mario", "rene", "harald", "günter", "leopold", "erich",
        "erwin", "alois", "alfred", "hermann", "oskar", "hubert",
    }

    # Context words that increase confidence
    CONTEXT_WORDS = re.compile(
        r"(?:herr|frau|dr\.|prof\.|mag\.|ing\.|kollege|kollegin|freund|freundin|"
        r"mitarbeiter|mitarbeiterin|kunde|kundin|patient|patientin|chef|chefin|"
        r"liebe[r]?|geschätzte[r]?)",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["PERSON"],
            name="First Name Recognizer",
            supported_language="de",
        )

    def load(self) -> None:
        pass

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts=None,
    ) -> list[RecognizerResult]:
        results = []

        # Tokenize by whitespace, check each capitalized word
        words = text.split()
        pos = 0
        for word in words:
            start = text.find(word, pos)
            clean = word.strip(".,;:!?\"'()[]{}").lower()

            if clean in self.FIRST_NAMES and word[0].isupper():
                # Base score — above default threshold (0.6)
                score = 0.65

                # Boost if preceded by context (Herr, Frau, Dr., etc.)
                before = text[max(0, start - 30):start]
                if self.CONTEXT_WORDS.search(before):
                    score = 0.85

                # Boost if followed by another capitalized word (likely surname)
                next_idx = start + len(word)
                remaining = text[next_idx:].lstrip()
                if remaining and remaining[0].isupper():
                    score = 0.8

                results.append(RecognizerResult(
                    entity_type="PERSON",
                    start=start,
                    end=start + len(word.strip(".,;:!?\"'()[]{}")) ,
                    score=score,
                ))

            pos = start + len(word)

        return results


def get_all_austrian_recognizers() -> list[EntityRecognizer]:
    """Returns a list of all custom recognizers."""
    return [
        AustrianUIDRecognizer(),
        AustrianIBANRecognizer(),
        AustrianSVNrRecognizer(),
        AustrianPhoneRecognizer(),
        AustrianFirmenbuchRecognizer(),
        DocumentMetadataRecognizer(),
        CredentialsRecognizer(),
        EUDataProtectionRecognizer(),
        SensitiveDataRecognizer(),
        FirstNameRecognizer(),
    ]
