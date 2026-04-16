"""Tests for entity classification, tiered mapping store, and tiered rehydration."""

import os
import sys
import time
import unittest

# Ensure proxy core is importable
PROXY_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "proxy")
sys.path.insert(0, PROXY_DIR)

from austrai_proxy.core.models import Entity
from austrai_proxy.core.classifier import (
    ProtectionLevel,
    ENTITY_CLASSIFICATION,
    LEVEL_TTL,
    LEVEL_LABELS,
    classify_entity,
    classify_entities,
    get_max_protection_level,
)
from austrai_proxy.core.rehydrator import rehydrate, rehydrate_tiered
from austrai_proxy.core.mapping_store import MappingStore, LEVEL_TTL as STORE_LEVEL_TTL


# ---------------------------------------------------------------------------
# Classifier Tests
# ---------------------------------------------------------------------------


class TestProtectionLevel(unittest.TestCase):
    """Test the ProtectionLevel enum and classification mapping."""

    def test_enum_values(self):
        self.assertEqual(ProtectionLevel.PUBLIC, 1)
        self.assertEqual(ProtectionLevel.INTERNAL, 2)
        self.assertEqual(ProtectionLevel.CONFIDENTIAL, 3)
        self.assertEqual(ProtectionLevel.RESTRICTED, 4)

    def test_enum_ordering(self):
        self.assertTrue(ProtectionLevel.PUBLIC < ProtectionLevel.INTERNAL)
        self.assertTrue(ProtectionLevel.INTERNAL < ProtectionLevel.CONFIDENTIAL)
        self.assertTrue(ProtectionLevel.CONFIDENTIAL < ProtectionLevel.RESTRICTED)

    def test_all_entity_types_classified(self):
        """Every known entity type should have a classification."""
        known_types = {
            "PERSON", "ORGANIZATION", "ORG", "EMAIL_ADDRESS", "PHONE_NUMBER",
            "DOC_METADATA", "CUSTOM", "AT_IBAN", "IBAN_CODE", "AT_UID_NR",
            "AT_FIRMENBUCH_NR", "LOCATION", "CREDIT_CARD", "AT_SVNR",
            "CREDENTIAL", "SENSITIVE_DATA", "EU_PII",
        }
        for entity_type in known_types:
            self.assertIn(
                entity_type,
                ENTITY_CLASSIFICATION,
                f"{entity_type} missing from ENTITY_CLASSIFICATION",
            )

    def test_level_labels_complete(self):
        for level in ProtectionLevel:
            self.assertIn(level, LEVEL_LABELS)

    def test_level_ttl_complete(self):
        for level in ProtectionLevel:
            self.assertIn(level, LEVEL_TTL)

    def test_ttl_decreases_with_level(self):
        self.assertGreater(LEVEL_TTL[1], LEVEL_TTL[2])
        self.assertGreater(LEVEL_TTL[2], LEVEL_TTL[3])
        self.assertGreater(LEVEL_TTL[3], LEVEL_TTL[4])


class TestClassifyEntity(unittest.TestCase):
    """Test entity classification logic."""

    def _make_entity(self, entity_type: str) -> Entity:
        return Entity(
            entity_type=entity_type, start=0, end=10, score=0.9, text="test"
        )

    def test_person_is_internal(self):
        e = self._make_entity("PERSON")
        level = classify_entity(e)
        self.assertEqual(level, ProtectionLevel.INTERNAL)

    def test_iban_is_confidential(self):
        e = self._make_entity("AT_IBAN")
        level = classify_entity(e)
        self.assertEqual(level, ProtectionLevel.CONFIDENTIAL)

    def test_svnr_is_restricted(self):
        e = self._make_entity("AT_SVNR")
        level = classify_entity(e)
        self.assertEqual(level, ProtectionLevel.RESTRICTED)

    def test_credential_is_restricted(self):
        e = self._make_entity("CREDENTIAL")
        level = classify_entity(e)
        self.assertEqual(level, ProtectionLevel.RESTRICTED)

    def test_unknown_type_defaults_to_internal(self):
        e = self._make_entity("UNKNOWN_NEW_TYPE")
        level = classify_entity(e)
        self.assertEqual(level, ProtectionLevel.INTERNAL)

    def test_context_upgrade_medical(self):
        """In a medical document, PERSON should be upgraded from 2 to 3."""
        e = self._make_entity("PERSON")
        level = classify_entity(
            e,
            doc_risk_level="high",
            doc_sensitivity_categories={"MEDICAL"},
        )
        self.assertEqual(level, ProtectionLevel.CONFIDENTIAL)

    def test_context_upgrade_capped_at_restricted(self):
        """RESTRICTED entities should not be upgraded beyond 4."""
        e = self._make_entity("AT_SVNR")
        level = classify_entity(
            e,
            doc_risk_level="high",
            doc_sensitivity_categories={"MEDICAL"},
        )
        self.assertEqual(level, ProtectionLevel.RESTRICTED)

    def test_no_upgrade_on_low_risk(self):
        """Low-risk documents should not trigger upgrades."""
        e = self._make_entity("PERSON")
        level = classify_entity(
            e,
            doc_risk_level="low",
            doc_sensitivity_categories={"MEDICAL"},
        )
        self.assertEqual(level, ProtectionLevel.INTERNAL)

    def test_no_upgrade_on_non_sensitive_category(self):
        """Non-sensitive categories should not trigger upgrades."""
        e = self._make_entity("PERSON")
        level = classify_entity(
            e,
            doc_risk_level="high",
            doc_sensitivity_categories={"ARCHITECTURE"},
        )
        self.assertEqual(level, ProtectionLevel.INTERNAL)


class TestClassifyEntities(unittest.TestCase):
    """Test batch classification."""

    def test_sets_protection_level_on_entities(self):
        entities = [
            Entity(entity_type="PERSON", start=0, end=5, score=0.9, text="test"),
            Entity(entity_type="AT_SVNR", start=10, end=20, score=0.95, text="1234"),
        ]
        classify_entities(entities)
        self.assertEqual(entities[0].protection_level, ProtectionLevel.INTERNAL)
        self.assertEqual(entities[1].protection_level, ProtectionLevel.RESTRICTED)

    def test_get_max_protection_level(self):
        entities = [
            Entity(entity_type="PERSON", start=0, end=5, score=0.9, text="a"),
            Entity(entity_type="AT_IBAN", start=10, end=20, score=0.95, text="b"),
        ]
        classify_entities(entities)
        self.assertEqual(get_max_protection_level(entities), ProtectionLevel.CONFIDENTIAL)

    def test_get_max_empty(self):
        self.assertEqual(get_max_protection_level([]), ProtectionLevel.PUBLIC)


# ---------------------------------------------------------------------------
# Tiered Rehydration Tests
# ---------------------------------------------------------------------------


class TestRehydrateTiered(unittest.TestCase):
    """Test tiered rehydration with access control."""

    def test_full_access(self):
        """With max_level=4, everything should be restored."""
        tiered = {
            2: {"Arion": "Thomas Gruber"},
            4: {"[AT_SVNR_1]": "1234 120478"},
        }
        result, count, redacted = rehydrate_tiered(
            "Arion hat SVNr [AT_SVNR_1].", tiered, max_level=4
        )
        self.assertEqual(result, "Thomas Gruber hat SVNr 1234 120478.")
        self.assertEqual(count, 2)
        self.assertEqual(redacted, [])

    def test_partial_access(self):
        """With max_level=2, only INTERNAL data should be restored."""
        tiered = {
            2: {"Arion": "Thomas Gruber"},
            4: {"[AT_SVNR_1]": "1234 120478"},
        }
        result, count, redacted = rehydrate_tiered(
            "Arion hat SVNr [AT_SVNR_1].", tiered, max_level=2
        )
        self.assertIn("Thomas Gruber", result)
        self.assertIn("[AT_SVNR_1]", result)
        self.assertEqual(count, 1)
        self.assertIn("AT_SVNR", redacted)

    def test_no_access(self):
        """With max_level=1, nothing should be restored if all are level 2+."""
        tiered = {
            2: {"Arion": "Thomas Gruber"},
            3: {"[AT_IBAN_1]": "AT48 3200 0000 1234 5678"},
        }
        result, count, redacted = rehydrate_tiered(
            "Arion, IBAN [AT_IBAN_1]", tiered, max_level=1
        )
        self.assertIn("Arion", result)
        self.assertIn("[AT_IBAN_1]", result)
        self.assertEqual(count, 0)

    def test_empty_mappings(self):
        result, count, redacted = rehydrate_tiered("Hello", {}, max_level=4)
        self.assertEqual(result, "Hello")
        self.assertEqual(count, 0)
        self.assertEqual(redacted, [])


# ---------------------------------------------------------------------------
# Tiered MappingStore Tests
# ---------------------------------------------------------------------------


class TestMappingStoreV2(unittest.TestCase):
    """Test the v2 tiered mapping store."""

    def setUp(self):
        """Use a fresh in-memory-like store for each test."""
        # Override DB path to a temp location
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        import austrai_proxy.core.mapping_store as ms
        self._orig_db_dir = ms.DB_DIR
        self._orig_db_file = ms.DB_FILE
        self._orig_key_file = ms.KEY_FILE
        ms.DB_DIR = __import__("pathlib").Path(self._tmpdir)
        ms.DB_FILE = ms.DB_DIR / "test_mappings.db"
        ms.KEY_FILE = ms.DB_DIR / "test_mappings.key"
        self.store = MappingStore()

    def tearDown(self):
        import shutil
        import austrai_proxy.core.mapping_store as ms
        ms.DB_DIR = self._orig_db_dir
        ms.DB_FILE = self._orig_db_file
        ms.KEY_FILE = self._orig_key_file
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_create_and_get_session(self):
        mappings = {"Arion": "Thomas", "[AT_IBAN_1]": "AT48 3200"}
        level_map = {"Arion": 2, "[AT_IBAN_1]": 3}
        sid = self.store.create_session(mappings, level_map)

        # Full access
        result = self.store.get_session(sid, max_level=4)
        self.assertIsNotNone(result)
        self.assertEqual(result["Arion"], "Thomas")
        self.assertEqual(result["[AT_IBAN_1]"], "AT48 3200")

    def test_tiered_access_control(self):
        mappings = {"Arion": "Thomas", "[AT_SVNR_1]": "1234"}
        level_map = {"Arion": 2, "[AT_SVNR_1]": 4}
        sid = self.store.create_session(mappings, level_map)

        # Level 2 access: only Arion
        result = self.store.get_session(sid, max_level=2)
        self.assertIsNotNone(result)
        self.assertIn("Arion", result)
        self.assertNotIn("[AT_SVNR_1]", result)

        # Level 4 access: both
        result = self.store.get_session(sid, max_level=4)
        self.assertIn("Arion", result)
        self.assertIn("[AT_SVNR_1]", result)

    def test_get_session_tiered(self):
        mappings = {"A": "a", "B": "b", "C": "c"}
        level_map = {"A": 2, "B": 3, "C": 4}
        sid = self.store.create_session(mappings, level_map)

        tiered = self.store.get_session_tiered(sid)
        self.assertIsNotNone(tiered)
        self.assertEqual(tiered[2], {"A": "a"})
        self.assertEqual(tiered[3], {"B": "b"})
        self.assertEqual(tiered[4], {"C": "c"})

    def test_session_info(self):
        mappings = {"A": "a", "B": "b"}
        level_map = {"A": 2, "B": 4}
        sid = self.store.create_session(mappings, level_map)

        info = self.store.get_session_info(sid)
        self.assertIsNotNone(info)
        self.assertEqual(info["session_id"], sid)
        self.assertEqual(info["max_level"], 4)
        self.assertIn(2, info["levels"])
        self.assertIn(4, info["levels"])
        self.assertGreater(info["levels"][2]["remaining_seconds"], 0)

    def test_no_level_map_defaults_to_internal(self):
        mappings = {"X": "y"}
        sid = self.store.create_session(mappings)  # No level_map

        tiered = self.store.get_session_tiered(sid)
        self.assertIn(2, tiered)
        self.assertEqual(tiered[2], {"X": "y"})

    def test_audit_log(self):
        mappings = {"A": "a"}
        level_map = {"A": 2}
        sid = self.store.create_session(mappings, level_map)
        self.store.get_session(sid)

        log = self.store.get_audit_log(session_id=sid)
        self.assertGreaterEqual(len(log), 2)
        actions = [entry["action"] for entry in log]
        self.assertIn("create", actions)
        self.assertIn("rehydrate", actions)

    def test_cleanup(self):
        """Cleanup should not crash and should return a count."""
        count = self.store.cleanup()
        self.assertIsInstance(count, int)

    def test_count(self):
        self.store.create_session({"A": "a"}, {"A": 2})
        self.store.create_session({"B": "b"}, {"B": 3})
        self.assertGreaterEqual(self.store.count(), 2)

    def test_delete_session(self):
        sid = self.store.create_session({"A": "a"}, {"A": 2})
        self.store.delete_session(sid)
        result = self.store.get_session(sid)
        self.assertIsNone(result)

    def test_latest_session(self):
        self.store.create_session({"old": "1"}, {"old": 2})
        self.store.create_session({"new": "2"}, {"new": 2})
        latest = self.store.get_latest_session()
        self.assertIsNotNone(latest)
        sid, mappings = latest
        self.assertIn("new", mappings)


if __name__ == "__main__":
    unittest.main()
