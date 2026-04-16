"""Entity-level data classification with 4-tier protection levels.

Classifies each detected PII entity into a protection level (1-4) based on
its type and the document's sensitivity context. Higher levels get shorter
TTLs in the mapping vault and restricted re-identification access.

Protection Levels:
    1 — PUBLIC:       Publicly known info (company in imprint)
    2 — INTERNAL:     Name, email, phone
    3 — CONFIDENTIAL: IBAN, UID, address, company register
    4 — RESTRICTED:   SVNr, credentials, medical, financial
"""

from enum import IntEnum

from .models import Entity


class ProtectionLevel(IntEnum):
    """Four-tier data classification aligned with ISO 27001 / DSGVO."""

    PUBLIC = 1
    INTERNAL = 2
    CONFIDENTIAL = 3
    RESTRICTED = 4


LEVEL_LABELS: dict[int, str] = {
    ProtectionLevel.PUBLIC: "Oeffentlich",
    ProtectionLevel.INTERNAL: "Intern",
    ProtectionLevel.CONFIDENTIAL: "Vertraulich",
    ProtectionLevel.RESTRICTED: "Streng Vertraulich",
}

LEVEL_LABELS_EN: dict[int, str] = {
    ProtectionLevel.PUBLIC: "Public",
    ProtectionLevel.INTERNAL: "Internal",
    ProtectionLevel.CONFIDENTIAL: "Confidential",
    ProtectionLevel.RESTRICTED: "Restricted",
}

# Default protection level per entity type.
# Can be upgraded by document context (see classify_entity).
ENTITY_CLASSIFICATION: dict[str, ProtectionLevel] = {
    # Level 2 — INTERNAL
    "PERSON": ProtectionLevel.INTERNAL,
    "ORGANIZATION": ProtectionLevel.INTERNAL,
    "ORG": ProtectionLevel.INTERNAL,
    "EMAIL_ADDRESS": ProtectionLevel.INTERNAL,
    "PHONE_NUMBER": ProtectionLevel.INTERNAL,
    "DOC_METADATA": ProtectionLevel.INTERNAL,
    "CUSTOM": ProtectionLevel.INTERNAL,

    # Level 3 — CONFIDENTIAL
    "AT_IBAN": ProtectionLevel.CONFIDENTIAL,
    "IBAN_CODE": ProtectionLevel.CONFIDENTIAL,
    "AT_UID_NR": ProtectionLevel.CONFIDENTIAL,
    "AT_FIRMENBUCH_NR": ProtectionLevel.CONFIDENTIAL,
    "LOCATION": ProtectionLevel.CONFIDENTIAL,
    "CREDIT_CARD": ProtectionLevel.CONFIDENTIAL,

    # Level 4 — RESTRICTED
    "AT_SVNR": ProtectionLevel.RESTRICTED,
    "CREDENTIAL": ProtectionLevel.RESTRICTED,
    "SENSITIVE_DATA": ProtectionLevel.RESTRICTED,
    "EU_PII": ProtectionLevel.RESTRICTED,
    "MEDICAL_CONDITION": ProtectionLevel.RESTRICTED,
    "PASSPORT_NUMBER": ProtectionLevel.RESTRICTED,

    # Level 3 — CONFIDENTIAL (semantic types)
    "DATE_OF_BIRTH": ProtectionLevel.CONFIDENTIAL,
    "IP_ADDRESS": ProtectionLevel.CONFIDENTIAL,
    "LICENSE_PLATE": ProtectionLevel.CONFIDENTIAL,
}

# TTL per protection level (seconds).
# RESTRICTED data expires after 5 minutes — even if the encrypted DB
# is copied, those mappings are irrecoverably gone.
LEVEL_TTL: dict[int, int] = {
    ProtectionLevel.PUBLIC: 86400,       # 24h
    ProtectionLevel.INTERNAL: 3600,      # 1h  (current default)
    ProtectionLevel.CONFIDENTIAL: 1800,  # 30min
    ProtectionLevel.RESTRICTED: 300,     # 5min
}

# Sensitivity categories that trigger a +1 upgrade for all entities
# in the same document (a name in a medical report is more sensitive
# than a name in a marketing email).
_HIGH_RISK_CATEGORIES = frozenset({
    "MEDICAL", "HR_INTERNAL", "CREDENTIALS", "LEGAL",
})


def classify_entity(
    entity: Entity,
    doc_risk_level: str | None = None,
    doc_sensitivity_categories: set[str] | None = None,
) -> int:
    """Determine the protection level for a single entity.

    Args:
        entity: The detected PII entity.
        doc_risk_level: Risk level from SensitivityReport ('low'/'medium'/'high').
        doc_sensitivity_categories: Set of flagged category names (e.g. {'MEDICAL'}).

    Returns:
        Protection level as int (1-4).
    """
    base_level = ENTITY_CLASSIFICATION.get(entity.entity_type, ProtectionLevel.INTERNAL)

    # Context-based upgrade: if the document is high-risk and contains
    # sensitive categories, bump every entity up by one level.
    if doc_risk_level == "high" and doc_sensitivity_categories:
        if doc_sensitivity_categories & _HIGH_RISK_CATEGORIES:
            return min(int(base_level) + 1, ProtectionLevel.RESTRICTED)

    return int(base_level)


def classify_entities(
    entities: list[Entity],
    doc_risk_level: str | None = None,
    doc_sensitivity_categories: set[str] | None = None,
) -> list[Entity]:
    """Classify all entities and set their protection_level field in-place.

    Returns the same list for chaining convenience.
    """
    for entity in entities:
        entity.protection_level = classify_entity(
            entity,
            doc_risk_level=doc_risk_level,
            doc_sensitivity_categories=doc_sensitivity_categories,
        )
    return entities


def get_max_protection_level(entities: list[Entity]) -> int:
    """Return the highest protection level among the given entities."""
    if not entities:
        return ProtectionLevel.PUBLIC
    return max(e.protection_level for e in entities)
