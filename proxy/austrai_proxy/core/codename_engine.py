"""Codename Engine: generates consistent, non-reversible codenames for PII.

Uses abstract fictional names instead of foreign-language translations or
bracket placeholders. Codenames are:
- LLM-friendly (look like proper nouns, processed naturally)
- Not reversible (no language to translate back from, not real names)
- Consistent within a session (same input -> same codename)
- Meaningless without the local mapping table
"""

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Codename pools — fictional, pronounceable, not real names in any language
# ---------------------------------------------------------------------------

PERSON_POOL = [
    "Arion", "Brynn", "Cael", "Dara", "Eryx", "Fael", "Gwyn", "Hale",
    "Ilan", "Jael", "Kael", "Lior", "Mael", "Nyra", "Orin", "Penn",
    "Quinn", "Rael", "Soren", "Tarn", "Ulla", "Vale", "Wren", "Xael",
    "Yael", "Zeph", "Alix", "Bron", "Cyra", "Dex", "Eira", "Fenn",
    "Gael", "Hart", "Iona", "Juno", "Kyro", "Lyra", "Mira", "Neva",
]

ORG_POOL = [
    "Nexon Corp", "Velar AG", "Talon GmbH", "Prism Group", "Helix AG",
    "Corvus GmbH", "Aether Corp", "Zenith AG", "Vortex GmbH", "Apex Group",
    "Cipher AG", "Dynex Corp", "Embark GmbH", "Forge AG", "Glint Corp",
    "Ivory GmbH", "Kinex AG", "Lumin Corp", "Nova GmbH", "Onyx Group",
    "Pulse AG", "Quasar Corp", "Rune GmbH", "Synth AG", "Titan Corp",
]

CUSTOM_POOL = [
    "Projekt Nox", "Vorhaben Vex", "Initiative Lux", "Programm Zar",
    "Konzept Dyn", "Entwurf Orx", "Plan Kyr", "Schema Tyr",
    "Modell Fen", "Protokoll Ash", "Rahmen Sol", "Leitfaden Pax",
    "Ansatz Vyn", "Methode Rex", "Verfahren Kor", "Strategie Bel",
]

# Maps entity type -> pool key (shared indexing prevents collisions)
_TYPE_TO_POOL: dict[str, str] = {
    "PERSON": "PERSON",
    "DOC_METADATA": "PERSON",
    "ORGANIZATION": "ORG",
    "ORG": "ORG",
    "CUSTOM": "CUSTOM",
}

_POOLS: dict[str, list[str]] = {
    "PERSON": PERSON_POOL,
    "ORG": ORG_POOL,
    "CUSTOM": CUSTOM_POOL,
}

# Entity types that get [TYPE_N] bracket format (structured data that
# LLMs tend to "correct" when given fake values)
BRACKET_TYPES = {
    "AT_IBAN", "IBAN_CODE", "AT_UID_NR", "AT_SVNR",
    "AT_FIRMENBUCH_NR", "PHONE_NUMBER", "CREDIT_CARD",
    "EMAIL_ADDRESS", "LOCATION", "CREDENTIAL",
    "EU_PII", "SENSITIVE_DATA",
}


@dataclass
class CodeNameEngine:
    """Per-session codename generator with consistent mappings.

    Usage:
        engine = CodeNameEngine()
        name = engine.get_codename("PERSON", "Thomas Gruber")  # -> "Arion"
        name = engine.get_codename("PERSON", "Thomas Gruber")  # -> "Arion" (same)
        name = engine.get_codename("PERSON", "Maria Huber")    # -> "Brynn" (next)
        mappings = engine.get_mappings()  # {"Arion": "Thomas Gruber", ...}
    """

    _assigned: dict[str, str] = field(default_factory=dict)
    _reverse: dict[str, str] = field(default_factory=dict)
    _pool_indices: dict[str, int] = field(default_factory=dict)
    _bracket_counters: dict[str, int] = field(default_factory=dict)

    def get_codename(self, entity_type: str, original_text: str) -> str:
        """Get a consistent codename for the given entity.

        Same original_text always returns the same codename within a session.
        Different original_texts always get different codenames.
        """
        key = original_text.strip().lower()

        # Consistency: return existing codename for known input
        if key in self._assigned:
            return self._assigned[key]

        if entity_type in BRACKET_TYPES:
            # Structured data -> bracket format [AT_IBAN_1]
            self._bracket_counters.setdefault(entity_type, 0)
            self._bracket_counters[entity_type] += 1
            codename = f"[{entity_type}_{self._bracket_counters[entity_type]}]"
        else:
            pool_key = _TYPE_TO_POOL.get(entity_type)
            if pool_key and pool_key in _POOLS:
                pool = _POOLS[pool_key]
                idx = self._pool_indices.get(pool_key, 0)
                if idx < len(pool):
                    codename = pool[idx]
                else:
                    # Pool exhausted -> append counter
                    codename = f"{pool[idx % len(pool)]}-{idx // len(pool) + 1}"
                self._pool_indices[pool_key] = idx + 1
            else:
                # Unknown entity type -> bracket format
                self._bracket_counters.setdefault(entity_type, 0)
                self._bracket_counters[entity_type] += 1
                codename = f"[{entity_type}_{self._bracket_counters[entity_type]}]"

        self._assigned[key] = codename
        self._reverse[codename] = original_text.strip()
        return codename

    def get_mappings(self) -> dict[str, str]:
        """Get the complete codename->original mapping for rehydration."""
        return dict(self._reverse)
