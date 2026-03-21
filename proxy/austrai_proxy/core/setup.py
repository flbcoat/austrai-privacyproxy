"""First-run setup: auto-download SpaCy model if missing."""

import logging
import subprocess
import sys

logger = logging.getLogger("austrai.setup")

DEFAULT_MODEL = "de_core_news_lg"


def ensure_spacy_model(model_name: str = DEFAULT_MODEL) -> bool:
    """Check if SpaCy model is installed, download if missing. Returns True if ready."""
    try:
        import spacy
        spacy.load(model_name)
        return True
    except OSError:
        pass

    logger.info("SpaCy-Modell '%s' wird heruntergeladen (einmalig, ~500 MB)...", model_name)
    print(f"\n  AUSTR.AI: Lade Sprachmodell '{model_name}' herunter (einmalig, ~500 MB)...")
    print("  Das kann ein paar Minuten dauern.\n")

    try:
        subprocess.check_call(
            [sys.executable, "-m", "spacy", "download", model_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        print(f"  ✓ Sprachmodell '{model_name}' installiert.\n")
        return True
    except subprocess.CalledProcessError as e:
        logger.error("SpaCy-Modell konnte nicht heruntergeladen werden: %s", e)
        print(f"  ✗ Download fehlgeschlagen. Manuell installieren:")
        print(f"    python -m spacy download {model_name}\n")
        return False
