"""Document-adaptive context learning for identifying terms.

Uses SpaCy's existing word vectors and POS tags to find terms that make a
document identifiable — beyond what rule-based Presidio detects.

Three signals:
1. Proper nouns (PROPN) not caught by Presidio
2. SpaCy NER entities filtered by the entity type whitelist
3. Noun phrases with high vector similarity to confirmed entity centroids

Key constraint: Only flag terms that are RARE in the document. Frequent terms
are structural (part of the document's vocabulary), not identifying.

No additional models or dependencies — uses SpaCy vectors already loaded.
"""

import logging
from collections import Counter

import numpy as np

from app.models import Entity

logger = logging.getLogger(__name__)

# Cosine similarity threshold for Signal 3
SIMILARITY_THRESHOLD = 0.72

# Minimum token/term length to consider
MIN_TOKEN_LENGTH = 4

# Maximum additional terms to return (prevents over-anonymization)
MAX_ADDITIONAL_TERMS = 25

# Terms appearing more than this many times are structural, not identifying
MAX_TERM_FREQUENCY = 3

# Words that should never be flagged. Includes common German words,
# tech products, programming terms, and abbreviations.
NEVER_FLAG = {
    # Common German words that SpaCy might PROPN-tag
    "herr", "frau", "sehr", "geehrte", "geehrter", "liebe", "lieber",
    "firma", "unternehmen", "person", "name", "adresse", "telefon",
    "bitte", "danke", "freundliche", "grüße", "gruesse",
    "erstellt", "verfasst", "geschrieben", "bearbeitet",
    "dokument", "brief", "vertrag", "rechnung", "angebot",
    "beispiel", "standard", "optional", "alternative", "ergebnis",
    "tabelle", "abbildung", "anhang", "kapitel", "abschnitt",
    "deutsch", "deutsche", "deutscher", "deutsches", "deutschen",
    "oesterreichisch", "oesterreichische", "oesterreichischen",
    # Legal forms
    "gmbh", "ag", "kg", "e.u.", "ohg", "mbh", "corp", "inc", "ltd",
    # Months & days
    "januar", "februar", "märz", "maerz", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "dezember",
    "montag", "dienstag", "mittwoch", "donnerstag", "freitag",
    "samstag", "sonntag",
    # Generic locations (too common to be identifying)
    "österreich", "oesterreich", "deutschland", "schweiz", "europa",
    "wien", "berlin", "münchen", "muenchen", "zürich", "zuerich",
    "hamburg", "köln", "koeln", "frankfurt", "salzburg", "graz", "linz",
    # Financial/legal abbreviations
    "eur", "usd", "chf", "gbp", "jpy", "cny", "euro",
    "uid", "iban", "bic", "svnr", "swift", "sepa",
    "mwst", "ust", "vat", "netto", "brutto",
    "abs", "bgb", "dsgvo", "gdpr", "dsg",
    # Structural terms
    "tel", "fax", "mobil", "mail", "email",
    "nr", "nr.", "str", "str.", "plz",
    # Tech products & platforms (public knowledge, not identifying)
    "claude", "openai", "anthropic", "gemini", "mistral", "llama",
    "chatgpt", "copilot", "alexa", "siri", "cortana",
    "google", "microsoft", "apple", "amazon", "meta", "nvidia",
    "docker", "kubernetes", "linux", "windows", "macos", "android",
    "python", "javascript", "typescript", "java", "rust", "golang",
    "fastapi", "flask", "django", "express", "react", "angular", "vue",
    "spacy", "presidio", "tesseract", "ollama", "litellm", "langchain",
    "pytorch", "tensorflow", "numpy", "pandas", "scipy",
    "sqlite", "postgres", "postgresql", "mysql", "mongodb", "redis",
    "chromadb", "pinecone", "weaviate", "qdrant", "milvus",
    "github", "gitlab", "bitbucket", "jira", "confluence",
    "hetzner", "aws", "azure", "gcloud", "vercel", "netlify",
    "cloudflare", "nginx", "apache", "caddy",
    "whisper", "stable diffusion", "midjourney", "dall-e",
    # Tech terms & abbreviations
    "llm", "ner", "nlp", "ocr", "api", "sdk", "cli", "gui", "ide",
    "gpu", "cpu", "ram", "rom", "ssd", "hdd", "vps", "tls", "ssl",
    "ssh", "dns", "cdn", "dpi", "fps", "url", "uri",
    "pdf", "png", "jpg", "jpeg", "tiff", "bmp", "webp", "svg",
    "xlsx", "csv", "docx", "json", "xml", "yaml", "toml", "html",
    "rest", "graphql", "grpc", "mqtt", "websocket",
    "pip", "npm", "yarn", "cargo", "brew", "apt",
    "git", "svn", "mercurial",
    "http", "https", "ftp", "smtp", "imap",
    "regex", "pattern", "token", "embedding", "vector", "tensor",
    "prompt", "query", "response", "request", "endpoint",
    "layer", "model", "module", "plugin", "extension",
    "pipeline", "workflow", "trigger", "hook", "callback",
    "mapping", "schema", "migration", "fixture", "seed",
    "cache", "proxy", "gateway", "bridge", "adapter",
    "memory", "buffer", "queue", "stack", "heap",
    "scan", "chunk", "batch", "stream", "shard",
    "open", "source", "free", "premium", "enterprise",
    "detection", "analysis", "processing", "extraction", "generation",
    "setup", "config", "install", "deploy", "build", "test",
    "benchmark", "performance", "upgrade", "downgrade",
    "design", "core", "base", "main", "init", "auto",
    "true", "false", "null", "none", "undefined",
    "remote", "local", "global", "private", "public",
    "clone", "fork", "merge", "rebase", "commit", "push", "pull",
    # Common short words that SpaCy might PROPN-tag
    "mit", "und", "oder", "bei", "von", "fuer", "aus", "auf",
    "per", "pro", "max", "min", "neu", "alt", "gut",
    "text", "code", "data", "file", "log", "key", "tag",
}


def learn_document(text: str, entities: list[Entity], nlp) -> list[str]:
    """Find additional identifying terms using the entities from Phase 1.

    Uses confirmed Presidio entities as training signal to discover terms
    that are semantically similar but were missed by rule-based detection.

    Args:
        text: Full document text.
        entities: Entities detected by Presidio (Phase 1).
        nlp: SpaCy nlp model instance (reuses Presidio's loaded model).

    Returns:
        List of additional terms to add as deny_list for Phase 2 detection.
    """
    doc = nlp(text)

    # Build frequency map (case-insensitive) for rarity filtering
    text_lower = text.lower()

    # Build set of character positions already covered by Phase 1
    known_spans: set[int] = set()
    for ent in entities:
        known_spans.update(range(ent.start, ent.end))

    known_texts = {e.text.lower().strip() for e in entities}

    additional: set[str] = set()

    # --- Signal 1: Proper nouns not caught by Presidio ---
    _find_uncaught_propn(doc, known_spans, known_texts, text_lower, additional)

    # --- Signal 2: SpaCy NER entities that were filtered ---
    _find_filtered_ner(doc, known_texts, text_lower, additional)

    # --- Signal 3: Embedding similarity to known entities ---
    if entities:
        _find_similar_terms(doc, entities, known_spans, known_texts, text_lower, additional)

    # Final filtering
    result = [
        t for t in additional
        if t.lower() not in NEVER_FLAG
        and len(t) >= MIN_TOKEN_LENGTH
        and _term_frequency(t, text_lower) <= MAX_TERM_FREQUENCY
    ]

    # Cap at MAX_ADDITIONAL_TERMS, prioritize by rarity (rarest first)
    if len(result) > MAX_ADDITIONAL_TERMS:
        result.sort(key=lambda t: _term_frequency(t, text_lower))
        result = result[:MAX_ADDITIONAL_TERMS]

    if result:
        logger.info(
            "Context-Learner: %d zusaetzliche Begriffe erkannt: %s",
            len(result), result[:10],
        )

    return result


def _term_frequency(term: str, text_lower: str) -> int:
    """Count case-insensitive occurrences of term in text."""
    return text_lower.count(term.lower())


# ---------------------------------------------------------------------------
# Signal 1: Proper nouns (PROPN) not caught by Presidio
# ---------------------------------------------------------------------------

def _find_uncaught_propn(doc, known_spans, known_texts, text_lower, out):
    """Find proper nouns that Presidio missed."""
    for token in doc:
        if (
            token.pos_ == "PROPN"
            and not token.is_stop
            and len(token.text) >= MIN_TOKEN_LENGTH
            and token.text.lower() not in known_texts
            and token.text.lower() not in NEVER_FLAG
            and token.idx not in known_spans
            and _term_frequency(token.text, text_lower) <= MAX_TERM_FREQUENCY
        ):
            out.add(token.text)

    # Multi-token proper noun sequences (e.g., "Claude Code")
    current: list = []
    for token in doc:
        if token.pos_ == "PROPN" and not token.is_punct and not token.is_stop:
            current.append(token)
        else:
            if len(current) >= 2:
                seq = " ".join(t.text for t in current)
                if (
                    seq.lower() not in known_texts
                    and current[0].idx not in known_spans
                    and seq.lower() not in NEVER_FLAG
                    and _term_frequency(seq, text_lower) <= MAX_TERM_FREQUENCY
                ):
                    out.add(seq)
            current = []

    if len(current) >= 2:
        seq = " ".join(t.text for t in current)
        if (
            seq.lower() not in known_texts
            and current[0].idx not in known_spans
            and seq.lower() not in NEVER_FLAG
        ):
            out.add(seq)


# ---------------------------------------------------------------------------
# Signal 2: SpaCy NER entities that Presidio's type filter excluded
# ---------------------------------------------------------------------------

def _find_filtered_ner(doc, known_texts, text_lower, out):
    """Pick up SpaCy NER entities that Presidio filtered by entity type."""
    for ent in doc.ents:
        ent_text = ent.text.strip()
        if (
            ent_text.lower() not in known_texts
            and ent_text.lower() not in NEVER_FLAG
            and len(ent_text) >= MIN_TOKEN_LENGTH
            and _term_frequency(ent_text, text_lower) <= MAX_TERM_FREQUENCY
        ):
            # PER and ORG: always accept
            if ent.label_ in ("PER", "ORG"):
                out.add(ent_text)
            # MISC: accept only if ALL tokens are proper nouns (likely names)
            elif ent.label_ == "MISC":
                if all(t.pos_ == "PROPN" or t.is_punct or t.text in ("und", "and", "&")
                       for t in ent):
                    out.add(ent_text)


# ---------------------------------------------------------------------------
# Signal 3: Embedding similarity to confirmed entity centroids
# ---------------------------------------------------------------------------

def _find_similar_terms(doc, entities, known_spans, known_texts, text_lower, out):
    """Find noun phrases with high vector similarity to confirmed entities."""
    # Compute per-type centroids from confirmed entities
    type_vectors: dict[str, list] = {}
    for ent in entities:
        ent_tokens = [
            t for t in doc
            if t.idx >= ent.start and t.idx + len(t.text) <= ent.end
            and t.has_vector and t.vector_norm > 0
        ]
        for t in ent_tokens:
            type_vectors.setdefault(ent.entity_type, []).append(t.vector)

    centroids: dict[str, np.ndarray] = {}
    for etype, vectors in type_vectors.items():
        centroid = np.mean(vectors, axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroids[etype] = centroid / norm

    if not centroids:
        return

    for chunk in doc.noun_chunks:
        chunk_text = chunk.text.strip()

        if (
            chunk_text.lower() in known_texts
            or chunk_text.lower() in NEVER_FLAG
            or len(chunk_text) < MIN_TOKEN_LENGTH
            or _term_frequency(chunk_text, text_lower) > MAX_TERM_FREQUENCY
        ):
            continue

        if any(c in known_spans for c in range(chunk.start_char, chunk.end_char)):
            continue

        # Must contain at least one proper noun
        if not any(t.pos_ == "PROPN" for t in chunk):
            continue

        chunk_vecs = [
            t.vector for t in chunk
            if t.has_vector and t.vector_norm > 0 and not t.is_stop
        ]
        if not chunk_vecs:
            continue

        chunk_vec = np.mean(chunk_vecs, axis=0)
        chunk_norm = np.linalg.norm(chunk_vec)
        if chunk_norm == 0:
            continue
        chunk_vec = chunk_vec / chunk_norm

        for centroid in centroids.values():
            similarity = float(np.dot(chunk_vec, centroid))
            if similarity > SIMILARITY_THRESHOLD:
                out.add(chunk_text)
                break
