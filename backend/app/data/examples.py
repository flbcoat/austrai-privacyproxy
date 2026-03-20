"""Fictional Austrian example texts for the PrivacyProxy demo."""

EXAMPLES: list[dict[str, str]] = [
    {
        "title": "Geschäfts-E-Mail",
        "description": "Typische geschäftliche E-Mail mit Kontakt- und Bankdaten",
        "text": (
            "Sehr geehrter Herr Thomas Gruber,\n\n"
            "bezugnehmend auf unser Telefonat vom 15. März möchte ich Ihnen hiermit "
            "das Angebot der Innovatech Solutions GmbH (UID: ATU12345678) übermitteln. "
            "Der Gesamtbetrag von EUR 14.850,00 ist innerhalb von 30 Tagen fällig.\n\n"
            "Bitte überweisen Sie den Betrag auf folgendes Konto:\n"
            "IBAN AT48 3200 0000 1234 5678\n\n"
            "Bei Fragen erreichen Sie mich jederzeit unter +43 1 234 5678 oder "
            "per E-Mail.\n\n"
            "Mit freundlichen Grüßen,\n"
            "Maria Steinbauer\n"
            "Innovatech Solutions GmbH\n"
            "Mariahilfer Straße 45, 1060 Wien"
        ),
    },
    {
        "title": "Ärztlicher Befund",
        "description": "Medizinischer Befund mit persönlichen Gesundheitsdaten",
        "text": (
            "BEFUNDBERICHT\n\n"
            "Patient: Elisabeth Moser\n"
            "Sozialversicherungsnummer: 1234 010185\n"
            "Geburtsdatum: 01.01.1985\n"
            "Adresse: Landstraßer Hauptstraße 12/3, 1030 Wien\n\n"
            "Diagnose: Die Patientin Elisabeth Moser stellte sich am 10. März 2026 "
            "in unserer Ordination vor. Nach eingehender Untersuchung wird eine "
            "ambulante Physiotherapie (2x wöchentlich, 6 Wochen) empfohlen.\n\n"
            "Der Befund wurde an die Sozialversicherung übermittelt.\n\n"
            "Dr. Andreas Pichler\n"
            "Facharzt für Orthopädie\n"
            "Tel.: 0660 1234567"
        ),
    },
    {
        "title": "Vertragsklausel",
        "description": "Vertragsdokument mit Firmen- und Finanzdaten",
        "text": (
            "KOOPERATIONSVERTRAG\n\n"
            "Zwischen der Alpentech Digital GmbH (FN 234567a), vertreten durch "
            "Geschäftsführer Stefan Wimmer, mit Sitz in Salzburg, Getreidegasse 15, "
            '5020 Salzburg (nachfolgend \u201eAuftraggeber\u201c) und der DataVision Analytics '
            "GmbH (FN 345678b), vertreten durch Geschäftsführerin Katharina Hofer, "
            "mit Sitz in Graz, Herrengasse 28, 8010 Graz (nachfolgend "
            '\u201eAuftragnehmer\u201c) wird folgender Vertrag geschlossen:\n\n'
            "§1 Vertragsgegenstand\n"
            "Der Auftragnehmer erbringt Datenanalyse-Dienstleistungen im Umfang von "
            "maximal 500 Personentagen zum Tagessatz von EUR 1.200,00 netto.\n\n"
            "§2 Vergütung\n"
            "Die Gesamtvergütung beträgt maximal EUR 600.000,00 netto und ist auf "
            "das Konto des Auftragnehmers (IBAN AT61 1900 0000 9876 5432) zu "
            "überweisen. Die UID-Nummer des Auftragnehmers lautet ATU87654321.\n\n"
            "Salzburg, am 1. März 2026"
        ),
    },
]
