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


class DateOfBirthRecognizer(PatternRecognizer):
    """Erkennt Geburtsdaten in verschiedenen Formaten.

    Unterstützt europäische (DD.MM.YYYY / DD/MM/YYYY), ISO (YYYY-MM-DD) und
    US-Formate (MM/DD/YYYY). Die US- und europäischen Slash-Varianten
    überlappen sich strukturell — der Recognizer markiert sie gleich, die
    Interpretation (Monat vs. Tag zuerst) klärt die spätere Anonymisierung
    über den Typ-Code [DATE_OF_BIRTH_N].
    """

    def __init__(self) -> None:
        patterns = [
            # European D.M.Y
            Pattern("birthdate_eu_dot", r"\b(?:0[1-9]|[12]\d|3[01])\.(?:0[1-9]|1[0-2])\.\d{4}\b", 0.65),
            # European / international D/M/Y or M/D/Y (US) — same shape
            Pattern("birthdate_slash", r"\b(?:0[1-9]|1[0-2])/(?:0[1-9]|[12]\d|3[01])/\d{4}\b", 0.55),
            Pattern("birthdate_slash_eu", r"\b(?:0[1-9]|[12]\d|3[01])/(?:0[1-9]|1[0-2])/\d{4}\b", 0.55),
            # ISO
            Pattern("birthdate_iso", r"\b\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b", 0.65),
        ]
        super().__init__(
            supported_entity="DATE_OF_BIRTH",
            patterns=patterns,
            name="Date of Birth Recognizer",
            supported_language="de",
            context=["Geburtsdatum", "geboren", "geb.", "date of birth", "birth date", "birthday", "DOB", "born"],
        )


class IPAddressRecognizer(PatternRecognizer):
    """Erkennt IP-Adressen (IPv4 + IPv6)."""

    def __init__(self) -> None:
        patterns = [
            Pattern("ipv4", r"\b(?:\d{1,3}\.){3}\d{1,3}\b", 0.6),
            Pattern("ipv6", r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b", 0.8),
        ]
        super().__init__(
            supported_entity="IP_ADDRESS",
            patterns=patterns,
            name="IP Address Recognizer",
            supported_language="de",
            context=["IP", "IP-Adresse", "Server", "Host"],
        )


class LicensePlateRecognizer(PatternRecognizer):
    """Erkennt KFZ-Kennzeichen (AT, DE)."""

    def __init__(self) -> None:
        patterns = [
            Pattern("at_plate", r"\b[A-Z]{1,2}\s?\d{1,5}\s?[A-Z]{1,3}\b", 0.4),
            Pattern("de_plate", r"\b[A-ZÄÖÜ]{1,3}\s?[A-Z]{1,2}\s?\d{1,4}[EH]?\b", 0.4),
        ]
        super().__init__(
            supported_entity="LICENSE_PLATE",
            patterns=patterns,
            name="License Plate Recognizer",
            supported_language="de",
            context=["Kennzeichen", "Nummernschild", "Fahrzeug", "PKW", "KFZ"],
        )


class PassportRecognizer(PatternRecognizer):
    """Erkennt Passnummern (AT: 1 Buchstabe + 7 Ziffern)."""

    def __init__(self) -> None:
        patterns = [
            Pattern("passport_at", r"\b[A-Z]\d{7}\b", 0.4),
        ]
        super().__init__(
            supported_entity="PASSPORT_NUMBER",
            patterns=patterns,
            name="Passport Recognizer",
            supported_language="de",
            context=["Pass", "Reisepass", "Ausweis", "Passport"],
        )


class EUDataProtectionRecognizer(PatternRecognizer):
    """Erkennt verbleibende EU-weite PII (IBANs, Kreditkarten, Steuernummern).

    Geburtsdaten, IP-Adressen, Kennzeichen und Paesse sind in eigene
    semantische Recognizer ausgelagert.
    """

    def __init__(self) -> None:
        patterns = [
            # EU IBANs (2 letter country + 2 check + up to 30 alphanumeric)
            Pattern("eu_iban", r"\b[A-Z]{2}\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?[\d\s]{0,10}\b", 0.85),
            # Credit cards (Visa, MC, Amex)
            Pattern("visa", r"\b4\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", 0.8),
            Pattern("mastercard", r"\b5[1-5]\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", 0.8),
            Pattern("amex", r"\b3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}\b", 0.8),
            # DE Steuernummer (11 digits with optional slashes)
            Pattern("de_steuer", r"\b\d{2,3}/?\.?\d{3,4}/?\.?\d{4,5}\b", 0.3),
        ]
        super().__init__(
            supported_entity="EU_PII",
            patterns=patterns,
            name="EU Data Protection Recognizer",
            supported_language="de",
            context=["IBAN", "Konto", "Kreditkarte", "Visa", "Mastercard", "Steuer", "Steuernummer"],
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

    # ~2200 häufigste Vornamen für DACH-Raum und Migrationsgruppen
    FIRST_NAMES = {
        # =====================================================================
        # DEUTSCH/ÖSTERREICHISCH — Weiblich (alle Altersgruppen)
        # =====================================================================
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
        "viktoria", "carolina", "marlene", "magdalena", "veronika",
        "agnes", "adelheid", "hedwig", "elfriede", "waltraud", "edeltraud",
        "roswitha", "lieselotte", "hannelore", "anneliese", "rosemarie",
        "waltraut", "gertrud", "marianne", "christiane", "ulrike",
        "dagmar", "gudrun", "sigrid", "margret", "elke", "gabi",
        "jutta", "ute", "kerstin", "bettina", "silke", "katrin",
        "iris", "astrid", "marion", "beate", "edith", "ilona",
        "erika", "ruth", "anita", "rita", "gerlinde", "heidemarie",
        "inge", "christa", "trude", "erna", "irene", "hilde",
        "karoline", "josefine", "leopoldine", "antonia", "carina",
        "corinna", "denise", "elisa", "emilia", "fiona", "gloria",
        "henriette", "irma", "karla", "klara", "konstanze", "leonore",
        "lina", "luise", "mathilde", "nora", "ottilie", "regina",
        "renata", "rosalia", "selma", "sigrun", "valentina", "wanda",
        "wilhelmine", "berta", "dorothea", "hedda", "hermine", "ida",
        "kunigunde", "notburga", "walburga", "zenzi", "theresa",
        "michaela", "alexandra", "caroline", "charlotte", "dorothee",
        "eleonore", "felicitas", "frederike", "greta", "ines", "janina",
        "jessica", "judith", "kristina", "larissa", "lea", "lorena",
        "lucia", "madeleine", "margareta", "miriam", "natalie", "natascha",
        "patrizia", "ramona", "raphaela", "rebecca", "ronja", "svenja",
        "tamara", "tatjana", "tina", "vanessa", "vivien", "yvonne",
        "amelie", "annika", "catarina", "celine", "chiara", "elena",
        "elina", "ella", "emily", "fabienne", "felicia", "frida",
        "greta", "hanna", "helena", "isabel", "isabella", "jana",
        "jaqueline", "jennifer", "jolanda", "josefa", "karoline",
        "katja", "lara", "leni", "lilli", "lotte", "luisa",
        "maja", "mara", "marina", "marlies", "marta", "meike",
        "mila", "milena", "nele", "olivia", "pia", "romy",
        "sara", "stella", "susanna", "vera", "zoe",
        "alina", "carla", "daria", "elli", "elsa", "erla",
        "flora", "gabi", "gerda", "gretel", "gundi", "heidi",
        "ilka", "ira", "johanna", "jule", "kathi", "kira",
        "lilli", "lisbeth", "lore", "luzia", "maren", "marit",
        "merle", "minna", "mirjam", "nadia", "nele", "nelli",
        "rosina", "senta", "suse", "thea", "trudi", "ursel",
        "walli", "wendelin", "wiebke", "wiltrud", "xenia",
        # =====================================================================
        # DEUTSCH/ÖSTERREICHISCH — Männlich (alle Altersgruppen)
        # =====================================================================
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
        "adalbert", "albert", "anton", "armin", "arnold", "artur",
        "august", "balthasar", "bertram", "bruno", "carl", "clemens",
        "conrad", "cornelius", "detlef", "dietmar", "dietrich", "dirk",
        "edmund", "eduard", "egon", "ekkehard", "emil", "engelbert",
        "eugen", "ewald", "fabian", "ferdinand", "florentinus", "folkert",
        "fridolin", "fritz", "gabriel", "gerd", "gernot", "gottfried",
        "gregor", "guido", "gustav", "hartmut", "hartwig", "heiko",
        "helge", "henning", "henryk", "holger", "hubertus", "hugo",
        "ignaz", "ingolf", "joachim", "jochen", "jörg", "joris",
        "jost", "jürg", "justus", "karsten", "kaspar", "konrad",
        "kurt", "lars", "laurenz", "leander", "leonard", "leonhard",
        "lorenz", "lothar", "ludwig", "magnus", "marius", "mathias",
        "matthäus", "norbert", "olaf", "ortwin", "otmar", "pascal",
        "pius", "quirin", "ralf", "reinhard", "reinhold", "reiner",
        "richard", "roland", "rolf", "roman", "rupert", "sascha",
        "severin", "siegfried", "siegmund", "sigurd", "silvester",
        "stanislaus", "sven", "theo", "theobald", "theodor", "thorsten",
        "tilo", "torsten", "udo", "ulrich", "valentin", "victor",
        "vinzenz", "volker", "volkmar", "waldo", "wenzel", "wernher",
        "willibald", "willy", "winfried", "xaver", "yannick",
        "adrian", "axel", "bastian", "boris", "carlo", "claus",
        "dario", "dennis", "edgar", "elmar", "erik", "erhard",
        "fabio", "falko", "gero", "goran", "hannes", "ingo",
        "ivan", "jens", "kai", "kilian", "knut", "lennart",
        "linus", "lorenz", "malte", "marco", "marcel", "marko",
        "mike", "nils", "olaf", "peer", "rafael", "raoul",
        "robin", "steffen", "swen", "thilo", "timo", "tristan",
        "ulf", "willi", "wolfram", "benno", "burkhard", "egbert",
        "gunther", "hansjörg", "ingo", "joerg", "manhart", "ottokar",
        "raimund", "ruprecht", "sigbert", "wendel", "wigbert",
        "aaron", "benedikt", "cedric", "emilian", "finnian", "hendrik",
        "konstantin", "leopold", "matteo", "nikolaus", "oswald",
        "quentin", "raphael", "samuel", "valerian", "wendelin",
        "arno", "bodo", "claus", "egbert", "friedhelm", "guntram",
        "hagen", "ingo", "jost", "korbinian", "lenz", "nikolai",
        "ottfried", "roderich", "tankred", "ullrich", "wilfried",
        # =====================================================================
        # TÜRKISCH — Weiblich (häufigste Vornamen in AT/DE)
        # =====================================================================
        "ayse", "fatma", "emine", "hatice", "zeynep", "elif", "meryem",
        "zehra", "havva", "sultan", "hanife", "merve", "esra", "kubra",
        "hacer", "halime", "huriye", "gulsum", "semiha", "mediha",
        "sevim", "nuray", "tulay", "gulten", "songul", "melek",
        "aysel", "aysun", "filiz", "sevgi", "leyla", "derya",
        "pinar", "ozlem", "ebru", "sibel", "asli", "burcu", "canan",
        "dilek", "hulya", "mine", "nazan", "nesrin", "nihal",
        "nurcan", "nurhayat", "oya", "seda", "seher", "selma",
        "serpil", "sevda", "seyhan", "sumeyye", "suleyman", "yasemin",
        "yeliz", "yildiz", "zeliha", "zuhal", "zubeyde", "azra",
        "beren", "betul", "birsen", "cemile", "deniz", "duriye",
        "fadime", "funda", "gamze", "gonca", "gulizar", "gulnur",
        "handan", "hediye", "irmak", "kadriye", "kevser", "kezban",
        "meltem", "muberra", "mukaddes", "munevver", "nalan", "nazli",
        "nergis", "neslihan", "nilgun", "nurgul", "ozge", "pembe",
        "perihan", "rabia", "remziye", "rukiye", "sabiha", "safiye",
        "samiye", "saniye", "serap", "sirin", "turkan", "ulku",
        "umut", "vildan", "yagmur", "yesim", "zahide", "zeynab",
        "zumrut", "tugba", "busra", "irem", "defne", "ecrin",
        "ela", "eylul", "ece", "nehir", "ada", "belinay",
        "miray", "asya", "ceren", "dilan", "gizem", "ilknur",
        "ipek", "nihan", "reyhan", "senem", "simge", "tuğçe",
        "alev", "arzu", "ayla", "bahar", "belgin", "berna",
        "cigdem", "damla", "ece", "elvan", "esin", "feride",
        "fikret", "fusun", "gaye", "gonul", "hale", "hicran",
        "inci", "jale", "lale", "muazzez", "muge", "nermin",
        "nuran", "rengin", "sevil", "suheyla", "sukran", "tansu",
        "tuba", "umran", "yonca", "zekiye", "zeren",
        # =====================================================================
        # TÜRKISCH — Männlich (häufigste Vornamen in AT/DE)
        # =====================================================================
        "mehmet", "mustafa", "ahmet", "ali", "hasan", "huseyin",
        "ibrahim", "ismail", "osman", "yusuf", "murat", "omer",
        "suleyman", "recep", "halil", "cemal", "kemal", "kadir",
        "ramazan", "hakan", "erkan", "serkan", "volkan", "gokhan",
        "burak", "emre", "fatih", "cem", "baris", "umut",
        "onur", "tolga", "sinan", "koray", "selim", "erdem",
        "arda", "tuncay", "ilhan", "adem", "engin", "levent",
        "metin", "nuri", "orhan", "ozgur", "sahin", "selcuk",
        "tarik", "taner", "ufuk", "ugur", "vedat", "yakup",
        "yasin", "zafer", "zeki", "abdullah", "bayram", "bekir",
        "bilal", "cengiz", "cuneyt", "dursun", "ekrem", "erdogan",
        "erol", "ferhat", "fikri", "hamza", "hikmet", "irfan",
        "kazim", "mahir", "muharrem", "munir", "necati", "nihat",
        "ridvan", "rustu", "sedat", "sukru", "tahir", "temel",
        "timur", "yavuz", "yilmaz", "yuksel",
        "alp", "alparslan", "alperen", "anil", "ata", "atakan",
        "baran", "batuhan", "berat", "berkay", "bilge", "can",
        "cihan", "dogan", "doruk", "ege", "emir", "emirhan",
        "eren", "erhan", "eyup", "furkan", "gokce", "gorkem",
        "haluk", "hamit", "haydar", "hayri", "ilker", "kaan",
        "kenan", "kursat", "lutfi", "malik", "melih", "mert",
        "mesut", "mithat", "muhammed", "nedim", "necmettin",
        "nevzat", "oguz", "oktan", "ozan", "polat", "rasim",
        "remzi", "riza", "ruhi", "sabri", "sadik", "sami",
        "semih", "serdar", "serif", "sevket", "taha", "talha",
        "tarkan", "taylan", "tuncer", "turan", "turhan", "utku",
        "vural", "yalcin", "yaman", "yunus",
        # =====================================================================
        # SERBISCH / KROATISCH / BOSNISCH — Weiblich
        # =====================================================================
        "ana", "marija", "jelena", "ivana", "milica", "dragana",
        "tatjana", "vesna", "snezana", "gordana", "zorica", "slavica",
        "ljiljana", "mirjana", "jasmina", "biljana", "branka",
        "danka", "darinka", "danica", "desanka", "dijana", "dusanka",
        "svetlana", "violeta", "jovana", "katarina", "kristina",
        "marina", "mirela", "nada", "natalija", "natasa", "nevena",
        "nikolina", "olga", "petra", "radmila", "ruzica", "sandra",
        "sanja", "silvana", "slobodanka", "sladjana", "suzana",
        "tamara", "tanja", "tijana", "valentina", "vera", "vanja",
        "vida", "zagorka", "zeljka", "zlata", "zorana", "zivka",
        "aleksandra", "bojana", "borjana", "bozena", "brankica",
        "cvijeta", "daniela", "dubravka", "dunja", "edita",
        "emina", "enisa", "fata", "gorica", "irena", "ivanka",
        "jasna", "katica", "lana", "lidija", "ljubica", "ljuba",
        "maja", "marica", "meliha", "milanka", "milena", "mira",
        "mirna", "nadja", "nela", "renata", "senka", "slavka",
        "snezica", "stana", "stanka", "stefanija", "tanja",
        "teodora", "vedrana", "vesela", "visnja", "zdravka",
        "amra", "aida", "aldijana", "almasa", "amela", "amina",
        "azra", "belma", "bisera", "dzenana", "dzenita", "edina",
        "elma", "elvira", "esma", "hana", "hanka", "hasiba",
        "hedija", "jasminka", "lejla", "mediha", "merima",
        "mirsada", "naida", "nejra", "nerma", "nermina", "ramiza",
        "razija", "sabina", "sabira", "saida", "samra", "sanela",
        "sejla", "selma", "semira", "suada", "seherzada", "zaklina",
        "zemina", "zerina", "zineta", "zumreta",
        # =====================================================================
        # SERBISCH / KROATISCH / BOSNISCH — Männlich
        # =====================================================================
        "aleksandar", "bojan", "branko", "darko", "dejan", "dragan",
        "drazen", "dusan", "goran", "igor", "ivan", "jovan", "marko",
        "milan", "milos", "miroslav", "mladen", "nemanja", "nenad",
        "nikola", "novak", "predrag", "radovan", "sasa", "sinisa",
        "slobodan", "srdjan", "stefan", "stojan", "tomislav", "vladimir",
        "vojislav", "vuk", "zarko", "zeljko", "zivadin", "zoran",
        "zlatan", "zdravko", "zvonko", "bratislav", "cedomir",
        "dalibor", "danilo", "dimitrije", "djordje", "djuro",
        "dobrivoje", "dragoslav", "dusko", "gradimir", "grgur",
        "hrvoje", "ilija", "josip", "krsto", "kresimir", "lazar",
        "luka", "ljubomir", "marinko", "matija", "mato", "mirko",
        "miodrag", "milorad", "nebojsa", "ognjen", "pavle", "petar",
        "rade", "ranko", "ratko", "samir", "savo", "senad",
        "simo", "srecko", "stevo", "tihomir", "todor", "velimir",
        "veso", "vinko", "vladan", "vojkan", "vukasin", "zivan",
        "adnan", "admir", "alen", "almir", "amar", "amer",
        "armin", "damir", "dino", "edin", "emir", "ermin",
        "esad", "fadil", "haris", "harun", "husein", "irfan",
        "jasmin", "kemal", "kenan", "meho", "miralem", "muamer",
        "muhamed", "nermin", "nihad", "omer", "rasim", "safet",
        "sead", "semir", "sulejman", "vahid", "vedad", "zlatan",
        # =====================================================================
        # ENGLISCH / INTERNATIONAL — Weiblich
        # =====================================================================
        "alice", "amanda", "amber", "amy", "angela", "ann", "anne",
        "ashley", "audrey", "becky", "beth", "betty", "bonnie",
        "brenda", "brittany", "brooke", "candice", "carol", "caroline",
        "catherine", "charlotte", "chelsea", "cheryl", "chloe",
        "christina", "claire", "courtney", "crystal", "cynthia",
        "daisy", "deborah", "debra", "donna", "dorothy", "eileen",
        "elaine", "eleanor", "elizabeth", "ellen", "emily", "emma",
        "erica", "erin", "evelyn", "faith", "fiona", "florence",
        "frances", "georgia", "grace", "haley", "harper", "harriet",
        "heather", "helen", "holly", "irene", "iris", "ivy",
        "jacqueline", "jade", "jane", "janet", "janice", "jean",
        "jenna", "jenny", "jessica", "jill", "joan", "joanna",
        "jocelyn", "jordan", "josephine", "joyce", "judy", "julie",
        "june", "karen", "kate", "katherine", "kathleen", "kathryn",
        "katie", "kayla", "kelly", "kimberly", "kristen", "kristin",
        "lauren", "leah", "lillian", "lily", "linda", "lindsay",
        "lois", "lorraine", "lucy", "lynn", "madison", "margaret",
        "margo", "martha", "mary", "maureen", "megan", "melissa",
        "michelle", "mildred", "miranda", "molly", "morgan",
        "nancy", "natasha", "nicola", "nicole", "norma", "olive",
        "paige", "pamela", "patricia", "pauline", "penelope",
        "phyllis", "rachel", "rebecca", "roberta", "rose", "rosemary",
        "ruby", "ruth", "sally", "samantha", "sarah", "scarlett",
        "sharon", "sheila", "shirley", "sienna", "sophia", "stacy",
        "stephanie", "susan", "sylvia", "taylor", "teresa", "tiffany",
        "tracy", "valerie", "vanessa", "victoria", "violet", "virginia",
        "vivian", "wendy", "whitney", "winifred", "zara", "zoe",
        "abigail", "addison", "alexandra", "alexis", "allison",
        "anna", "aria", "ariana", "autumn", "avery", "bella",
        "brianna", "brooklyn", "camila", "claire", "clara",
        "eleanor", "elena", "ella", "eva", "evelyn", "gabriella",
        "gianna", "hannah", "harper", "hazel", "isla", "kaylee",
        "kennedy", "kinsley", "layla", "lillian", "luna", "lydia",
        "mackenzie", "madeline", "maya", "naomi", "natalie", "nora",
        "nova", "penelope", "piper", "quinn", "riley", "sadie",
        "savannah", "scarlett", "skylar", "stella", "willow",
        # =====================================================================
        # ENGLISCH / INTERNATIONAL — Männlich
        # =====================================================================
        "adam", "alan", "albert", "alex", "andrew", "anthony",
        "archie", "arthur", "austin", "barry", "ben", "benjamin",
        "blake", "bob", "brad", "bradley", "brandon", "brent",
        "brian", "bruce", "bryan", "caleb", "calvin", "cameron",
        "carl", "carter", "chad", "charles", "charlie", "chase",
        "chester", "chris", "christopher", "clarence", "clark",
        "clifford", "clyde", "cody", "cole", "colin", "connor",
        "craig", "curtis", "dale", "damian", "dan", "danny",
        "darren", "darryl", "dean", "derek", "desmond", "devin",
        "donald", "douglas", "drew", "duncan", "dustin", "dwight",
        "dylan", "earl", "eddie", "edward", "edwin", "elliot",
        "eric", "ethan", "eugene", "evan", "frank", "fred",
        "frederick", "gabriel", "garrett", "gary", "gavin", "gene",
        "geoffrey", "gerald", "glen", "gordon", "graham", "grant",
        "greg", "gregory", "guy", "harold", "harry", "harvey",
        "henry", "howard", "hugh", "hunter", "ian", "isaac",
        "jack", "jackson", "jacob", "jake", "james", "jamie",
        "jason", "jay", "jeff", "jeffrey", "jeremy", "jerome",
        "jesse", "jim", "joe", "joel", "john", "johnny",
        "jonathan", "jordan", "joseph", "joshua", "juan", "justin",
        "keith", "kenneth", "kevin", "kyle", "lance", "larry",
        "lawrence", "lee", "leo", "leonard", "liam", "lloyd",
        "logan", "louis", "lucas", "luke", "malcolm", "marcus",
        "mark", "marshall", "martin", "mason", "matt", "matthew",
        "max", "melvin", "miles", "mitchell", "nathan", "nathaniel",
        "neil", "nelson", "nicholas", "nick", "noah", "noel",
        "norman", "oliver", "oscar", "owen", "patrick", "paul",
        "perry", "peter", "philip", "pierce", "ralph", "randall",
        "randy", "ray", "raymond", "reginald", "rex", "richard",
        "rick", "riley", "rob", "robert", "rodney", "roger",
        "ronald", "ross", "roy", "russell", "ryan", "sam",
        "samuel", "scott", "sean", "seth", "shane", "sheldon",
        "spencer", "stanley", "stephen", "steve", "stuart", "ted",
        "terry", "theodore", "timothy", "todd", "tom", "tony",
        "travis", "trevor", "troy", "tyler", "victor", "vincent",
        "wade", "wallace", "warren", "wayne", "wesley", "william",
        "wyatt", "xavier", "zachary",
        "aiden", "alexander", "asher", "axel", "beckett", "brayden",
        "brooks", "carson", "cooper", "declan", "easton", "elijah",
        "emmett", "ezra", "finn", "grayson", "greyson", "harrison",
        "hayden", "hudson", "jace", "jaxon", "kai", "kayden",
        "landon", "leo", "lincoln", "maverick", "miles", "parker",
        "roman", "ryder", "sawyer", "silas", "theodore", "weston",
        # =====================================================================
        # ARABISCH — Weiblich (häufig in AT/DE)
        # =====================================================================
        "aisha", "amina", "amira", "basma", "dalia", "dalal",
        "dina", "farah", "farida", "fatima", "hafsa", "hala",
        "hana", "huda", "iman", "jamila", "khadija", "laila",
        "lamia", "lina", "lubna", "maha", "malak", "mariam",
        "mona", "nadia", "nadira", "nawal", "noura", "rania",
        "reem", "rima", "ruba", "saba", "sahar", "salam",
        "salma", "samira", "sana", "sawsan", "shadya", "shaima",
        "suha", "sumaya", "tahira", "wafa", "widad", "yasmin",
        "yusra", "zahra", "zainab", "zineb",
        "aaliyah", "abeer", "afaf", "afra", "alia", "asma",
        "bushra", "duaa", "ghada", "habiba", "halima", "hanaa",
        "hayat", "hind", "houda", "ihsan", "inaam", "inas",
        "isra", "jinan", "karima", "kenza", "latifa", "leena",
        "majda", "maram", "manal", "munira", "nabila", "nada",
        "naima", "najat", "najla", "nargis", "nasreen", "noor",
        "rabab", "rahma", "raja", "rajaa", "rana", "rawda",
        "rim", "rola", "roqaya", "ruqia", "sabiha", "sadiya",
        "safaa", "safia", "sajida", "salwa", "samia", "sara",
        "siham", "soumaya", "souad", "taghreed", "warda", "wisam",
        "yara", "zakia", "zeinab",
        # =====================================================================
        # ARABISCH — Männlich (häufig in AT/DE)
        # =====================================================================
        "abdallah", "abdul", "abdulaziz", "abdulkarim", "abdulrahman",
        "adel", "ahmad", "ahmed", "akram", "amin", "amir",
        "anwar", "ayoub", "aziz", "badr", "bassam", "bilal",
        "farid", "faris", "fawzi", "fouad", "habib", "hafez",
        "hamid", "hani", "hassan", "hussein", "idris", "imad",
        "isam", "jamal", "jamil", "kamal", "karim", "khalid",
        "khalil", "khaled", "laith", "maher", "mahmoud", "majid",
        "mansour", "marwan", "mazin", "mohamed", "mohammed", "mohannad",
        "moussa", "murad", "nabil", "nader", "nadir", "nasir",
        "nasser", "omar", "osama", "qasim", "rabi", "rachid",
        "rafik", "ramadan", "rami", "rashid", "riad", "ridha",
        "saad", "sabri", "saddam", "said", "salah", "salim",
        "samir", "sami", "sharif", "sultan", "taher", "tarek",
        "tawfiq", "walid", "yasser", "yousef", "youssef", "ziad",
        "abdelhak", "abdelkader", "abdellatif", "abderrahim",
        "adham", "amjad", "anas", "ashraf", "aws", "ayman",
        "bakr", "bashar", "chakib", "driss", "ehab", "elias",
        "emad", "essam", "ghassan", "hamdan", "hamza", "haroun",
        "hatim", "hicham", "hisham", "ibrahim", "ihab", "ilyas",
        "issam", "issa", "jalal", "jawad", "jihad", "joud",
        "kareem", "lotfi", "mahdi", "mounir", "mustafa", "naeem",
        "naji", "nassim", "nizar", "qais", "rached", "rafat",
        "saeed", "saleh", "soufiane", "sufyan", "suhail", "tamer",
        "tariq", "wael", "wasim", "yassin", "yousri", "zakaria",
        "zakariya", "zuhair",
        # =====================================================================
        # POLNISCH (weitere Migrationsgruppe in AT/DE) — Weiblich
        # =====================================================================
        "agnieszka", "aleksandra", "alicja", "anna", "barbara",
        "beata", "bozena", "celina", "danuta", "dorota", "edyta",
        "elzbieta", "ewa", "grazyna", "halina", "iwona", "izabela",
        "jadwiga", "janina", "joanna", "jolanta", "justyna",
        "kamila", "karolina", "katarzyna", "krystyna", "lucyna",
        "magdalena", "malgorzata", "mariola", "marta", "monika",
        "natalia", "patrycja", "paulina", "renata", "stanislawa",
        "sylwia", "teresa", "urszula", "wanda", "wioletta",
        "zofia", "zuzanna",
        # =====================================================================
        # POLNISCH — Männlich
        # =====================================================================
        "adam", "andrzej", "arkadiusz", "bartosz", "bogdan",
        "cezary", "dariusz", "dawid", "dominik", "filip",
        "grzegorz", "henryk", "jacek", "jakub", "janusz", "jaroslaw",
        "jerzy", "kamil", "kazimierz", "krzysztof", "lech",
        "leszek", "lukasz", "maciej", "marcin", "marek", "mariusz",
        "mateusz", "michal", "miroslaw", "norbert", "pawel",
        "piotr", "przemyslaw", "radoslaw", "rafal", "robert",
        "ryszard", "sebastian", "slawomir", "stanislaw", "szymon",
        "tadeusz", "tomasz", "waldemar", "wieslaw", "witold",
        "wojciech", "zbigniew", "zdzislaw", "zenon",
        # =====================================================================
        # UNGARISCH (Nachbarland, relevant für AT) — Weiblich
        # =====================================================================
        "agnes", "aniko", "borbala", "csilla", "dora", "edit",
        "eniko", "erika", "erzsebet", "eszter", "eva", "fruzsina",
        "gabriella", "hajnalka", "ildiko", "ibolya", "judit",
        "julianna", "katalin", "klara", "krisztina", "margit",
        "maria", "monika", "noemi", "orsolya", "piroska", "reka",
        "rita", "szilvia", "timea", "tunde", "virag", "zita",
        "zsanett", "zsofia", "zsuzsanna",
        # =====================================================================
        # UNGARISCH — Männlich
        # =====================================================================
        "akos", "andras", "antal", "arpad", "attila", "balazs",
        "bela", "csaba", "denes", "erno", "ferenc", "gabor",
        "gergely", "gergo", "gyorgy", "gyula", "imre", "istvan",
        "janos", "jozsef", "kalman", "karoly", "kristof", "laszlo",
        "levente", "lorinc", "marton", "mate", "miklos", "norbert",
        "pal", "peter", "sandor", "szabolcs", "tamas", "tibor",
        "viktor", "vilmos", "zoltan", "zsolt",
        # =====================================================================
        # RUMÄNISCH (Migrationsgruppe in AT) — Weiblich
        # =====================================================================
        "adelina", "alina", "ana", "anca", "andreea", "camelia",
        "carmen", "catalina", "cristina", "dana", "elena", "florina",
        "gabriela", "georgiana", "ioana", "irina", "laura", "loredana",
        "luminita", "madalina", "mihaela", "nicoleta", "oana",
        "raluca", "roxana", "simona", "stefania", "valentina",
        # =====================================================================
        # RUMÄNISCH — Männlich
        # =====================================================================
        "adrian", "alexandru", "andrei", "bogdan", "ciprian",
        "claudiu", "cosmin", "cristian", "danut", "dragos",
        "florin", "george", "gheorghe", "ion", "ionut", "iulian",
        "lucian", "marian", "mihai", "mircea", "ovidiu", "paul",
        "petru", "radu", "razvan", "sergiu", "sorin", "stefan",
        "vasile", "vlad",
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
        # Semantic recognizers (split from former monolithic EUDataProtectionRecognizer)
        DateOfBirthRecognizer(),
        IPAddressRecognizer(),
        LicensePlateRecognizer(),
        PassportRecognizer(),
        EUDataProtectionRecognizer(),  # remaining: IBANs, credit cards, tax numbers
        SensitiveDataRecognizer(),
        FirstNameRecognizer(),
    ]
