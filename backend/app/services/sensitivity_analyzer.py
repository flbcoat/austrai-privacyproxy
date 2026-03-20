"""Lokale Inhalts-Sensitivitaetsanalyse mittels Sentence Embeddings.

Verwendet paraphrase-multilingual-MiniLM-L12-v2 (~120MB) fuer Zero-Shot-
Klassifikation von Textinhalten in Sensitivitaetskategorien.
Laeuft vollstaendig auf der CPU, keine externen API-Aufrufe.
"""

import logging
import re
import time

import numpy as np
from sentence_transformers import SentenceTransformer

from app.models import SensitivityFlag, SensitivityReport

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Modell-Instanz (wird beim Start via init_sensitivity_model() geladen)
# ---------------------------------------------------------------------------
_model: SentenceTransformer | None = None
_category_embeddings: dict[str, np.ndarray] = {}

# ---------------------------------------------------------------------------
# Sensitivitaetskategorien mit deutschen Beschreibungen fuer Embedding
# ---------------------------------------------------------------------------
SENSITIVITY_CATEGORIES: dict[str, dict[str, str]] = {
    "BUSINESS_SECRET": {
        "description": (
            "Geschaeftsgeheimnis, vertrauliche Geschaeftsinformation, "
            "interne Strategie, Wettbewerbsvorteil"
        ),
        "label": "Geschaeftsgeheimnis & Vertrauliche Information",
    },
    "ARCHITECTURE": {
        "description": (
            "Softwarearchitektur, Systemdesign, technische Infrastruktur, "
            "Datenbankschema, API-Dokumentation, Deployment-Konfiguration"
        ),
        "label": "Softwarearchitektur & Systemdesign",
    },
    "CREDENTIALS": {
        "description": (
            "Passwort, Zugangsdaten, API-Key, Secret, Token, Schluessel, "
            "Private Key, Zertifikat"
        ),
        "label": "Zugangsdaten & Schluessel",
    },
    "FINANCIAL": {
        "description": (
            "Finanzbericht, Bilanz, Umsatz, Gewinn, Budget, Gehalt, "
            "Kostenkalkulation, Preiskalkulation"
        ),
        "label": "Finanzdaten & Kalkulation",
    },
    "LEGAL": {
        "description": (
            "Vertrag, Geheimhaltungsvereinbarung, NDA, Compliance, "
            "Rechtsstreit, Klage, Patent"
        ),
        "label": "Rechtliche Dokumente & Vertraege",
    },
    "HR_INTERNAL": {
        "description": (
            "Mitarbeiterbewertung, Kuendigung, Abmahnung, Personalakte, "
            "Gehaltsverhandlung, interne Beurteilung"
        ),
        "label": "Personalwesen & Interne Beurteilungen",
    },
    "MEDICAL": {
        "description": (
            "Diagnose, Befund, Therapie, Medikation, Patientenakte, "
            "Krankengeschichte"
        ),
        "label": "Medizinische Daten & Befunde",
    },
}

# ---------------------------------------------------------------------------
# Keyword-Pre-Filter (schnell, vor Embeddings)
# ---------------------------------------------------------------------------
CREDENTIAL_KEYWORDS: list[str] = [
    "vertraulich",
    "geheim",
    "intern",
    "nicht weitergeben",
    "api-key",
    "passwort",
    "password",
    "secret",
    "token",
    "private key",
]

_CREDENTIAL_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(kw) for kw in CREDENTIAL_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Schwellenwerte
# ---------------------------------------------------------------------------
SIMILARITY_THRESHOLD = 0.35
HIGH_RISK_THRESHOLD = 0.6
CHUNK_SIZE = 200


def init_sensitivity_model() -> None:
    """Laedt das Sentence-Transformer-Modell und berechnet Kategorie-Embeddings.

    Wird beim Anwendungsstart aufgerufen (Lifespan).
    """
    global _model, _category_embeddings

    start = time.time()
    logger.info("Lade Sensitivity-Modell paraphrase-multilingual-MiniLM-L12-v2 ...")

    _model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    # Kategorie-Beschreibungen vorab kodieren
    category_names = list(SENSITIVITY_CATEGORIES.keys())
    category_texts = [
        SENSITIVITY_CATEGORIES[cat]["description"] for cat in category_names
    ]
    embeddings = _model.encode(category_texts, convert_to_numpy=True, normalize_embeddings=True)

    _category_embeddings = {
        name: embeddings[i] for i, name in enumerate(category_names)
    }

    elapsed = time.time() - start
    logger.info(
        "Sensitivity-Modell geladen in %.2fs (%d Kategorien vorberechnet).",
        elapsed,
        len(_category_embeddings),
    )


def _get_model() -> SentenceTransformer:
    """Gibt die geladene Modellinstanz zurueck."""
    if _model is None:
        raise RuntimeError("Sensitivity-Modell wurde noch nicht initialisiert.")
    return _model


def _split_into_chunks(text: str, max_len: int = CHUNK_SIZE) -> list[str]:
    """Teilt Text in Absaetze/Chunks auf (~max_len Zeichen pro Chunk).

    Versucht an Absatzgrenzen zu teilen; faellt auf Satzgrenzen zurueck.

    Args:
        text: Eingabetext.
        max_len: Maximale Zeichenanzahl pro Chunk.

    Returns:
        Liste von Textchunks.
    """
    # Zuerst an Absaetzen teilen
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    chunks: list[str] = []
    for para in paragraphs:
        if len(para) <= max_len:
            chunks.append(para)
        else:
            # Laengere Absaetze an Satzgrenzen teilen
            sentences = re.split(r"(?<=[.!?])\s+", para)
            current_chunk = ""
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 1 <= max_len:
                    current_chunk = (current_chunk + " " + sentence).strip()
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    # Falls ein einzelner Satz laenger als max_len ist, trotzdem nehmen
                    current_chunk = sentence
            if current_chunk:
                chunks.append(current_chunk)

    return chunks if chunks else [text[:max_len]]


def _keyword_prefilter(text: str) -> list[SensitivityFlag]:
    """Schneller Keyword-Pre-Filter fuer offensichtliche Zugangsdaten.

    Args:
        text: Eingabetext.

    Returns:
        Liste von SensitivityFlag-Objekten fuer Keyword-Treffer.
    """
    flags: list[SensitivityFlag] = []
    seen_excerpts: set[str] = set()

    for match in _CREDENTIAL_PATTERN.finditer(text):
        # Kontext um das Keyword extrahieren (max 200 Zeichen)
        start = max(0, match.start() - 50)
        end = min(len(text), match.end() + 150)
        excerpt = text[start:end].strip()

        if excerpt in seen_excerpts:
            continue
        seen_excerpts.add(excerpt)

        flags.append(
            SensitivityFlag(
                category="CREDENTIALS",
                label=SENSITIVITY_CATEGORIES["CREDENTIALS"]["label"],
                score=0.9,
                excerpt=excerpt[:200],
            )
        )

    return flags


def _compute_risk_level(flags: list[SensitivityFlag]) -> str:
    """Berechnet die Risikostufe basierend auf der Anzahl und Staerke der Flags.

    Args:
        flags: Liste der erkannten Sensitivity-Flags.

    Returns:
        Risikostufe: 'low', 'medium' oder 'high'.
    """
    if not flags:
        return "low"

    max_score = max(f.score for f in flags)

    if len(flags) >= 3 or max_score >= HIGH_RISK_THRESHOLD:
        return "high"
    elif len(flags) >= 1:
        return "medium"

    return "low"


def _generate_summary(flags: list[SensitivityFlag], risk_level: str) -> str:
    """Erzeugt eine menschenlesbare Zusammenfassung auf Deutsch.

    Args:
        flags: Liste der erkannten Sensitivity-Flags.
        risk_level: Berechnete Risikostufe.

    Returns:
        Deutsche Zusammenfassung als String.
    """
    if not flags:
        return "Keine sensiblen Inhalte erkannt."

    risk_labels = {
        "low": "Gering",
        "medium": "Mittel",
        "high": "Hoch",
    }

    # Eindeutige Kategorien sammeln
    categories = list(dict.fromkeys(f.label for f in flags))
    cat_text = ", ".join(categories)

    risk_label = risk_labels.get(risk_level, risk_level)

    return (
        f"Risikostufe: {risk_label}. "
        f"{len(flags)} sensible(r) Inhalt(e) erkannt in den Kategorien: {cat_text}. "
        f"Bitte pruefen Sie, ob dieser Text an ein externes Sprachmodell gesendet werden soll."
    )


def analyze_sensitivity(text: str) -> SensitivityReport:
    """Analysiert Text auf inhaltliche Sensitivitaet.

    Fuehrt einen schnellen Keyword-Pre-Filter durch, gefolgt von
    Embedding-basierter Aehnlichkeitsanalyse gegen vordefinierte
    Sensitivitaetskategorien.

    Args:
        text: Eingabetext zur Analyse.

    Returns:
        SensitivityReport mit Flags, Risikostufe und Zusammenfassung.
    """
    if not text or not text.strip():
        return SensitivityReport(
            is_sensitive=False,
            risk_level="low",
            flags=[],
            summary="Kein Text zur Analyse vorhanden.",
        )

    model = _get_model()

    # Phase 1: Keyword-Pre-Filter
    keyword_flags = _keyword_prefilter(text)

    # Phase 2: Embedding-basierte Analyse
    chunks = _split_into_chunks(text)
    embedding_flags: list[SensitivityFlag] = []

    if chunks and _category_embeddings:
        # Alle Chunks auf einmal kodieren (effizienter)
        chunk_embeddings = model.encode(
            chunks, convert_to_numpy=True, normalize_embeddings=True,
        )

        # Kategorie-Embedding-Matrix aufbauen
        cat_names = list(_category_embeddings.keys())
        cat_matrix = np.stack([_category_embeddings[name] for name in cat_names])

        # Kosinus-Aehnlichkeit: (num_chunks x embedding_dim) @ (embedding_dim x num_categories)
        # Da beide normalisiert sind, ist das Skalarprodukt = Kosinus-Aehnlichkeit
        similarities = chunk_embeddings @ cat_matrix.T

        # Flags fuer Chunks oberhalb des Schwellenwerts erzeugen
        seen_chunk_cat: set[tuple[int, str]] = set()
        for chunk_idx in range(len(chunks)):
            for cat_idx, cat_name in enumerate(cat_names):
                sim_score = float(similarities[chunk_idx, cat_idx])
                if sim_score > SIMILARITY_THRESHOLD:
                    key = (chunk_idx, cat_name)
                    if key not in seen_chunk_cat:
                        seen_chunk_cat.add(key)
                        embedding_flags.append(
                            SensitivityFlag(
                                category=cat_name,
                                label=SENSITIVITY_CATEGORIES[cat_name]["label"],
                                score=round(sim_score, 3),
                                excerpt=chunks[chunk_idx][:200],
                            )
                        )

    # Flags zusammenfuehren und deduplizieren
    all_flags = keyword_flags + embedding_flags

    # Nach Score absteigend sortieren
    all_flags.sort(key=lambda f: f.score, reverse=True)

    # Risikostufe berechnen
    risk_level = _compute_risk_level(all_flags)

    # Zusammenfassung erzeugen
    summary = _generate_summary(all_flags, risk_level)

    return SensitivityReport(
        is_sensitive=len(all_flags) > 0,
        risk_level=risk_level,
        flags=all_flags,
        summary=summary,
    )
