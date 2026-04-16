"""Persistent encrypted Mapping Store v2 — tiered protection levels.

Extends v1 with:
- Per-level encrypted storage (each protection level stored separately)
- Level-based TTLs (RESTRICTED=5min, CONFIDENTIAL=30min, INTERNAL=1h, PUBLIC=24h)
- Audit log (who accessed what level, when)
- Backward-compatible: auto-migrates v1 sessions on first access

Storage: ~/.austrai/mappings.db (encrypted values)
"""

import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

logger = logging.getLogger("austrai.mapping_store")

DB_DIR = Path.home() / ".austrai"
DB_FILE = DB_DIR / "mappings.db"
KEY_FILE = DB_DIR / "mappings.key"
DEFAULT_TTL = 3600  # 1 hour (fallback for unclassified data)

# TTL per protection level (seconds)
LEVEL_TTL: dict[int, int] = {
    1: 86400,   # PUBLIC:       24h
    2: 3600,    # INTERNAL:     1h
    3: 1800,    # CONFIDENTIAL: 30min
    4: 300,     # RESTRICTED:   5min
}


class MappingStore:
    """Persistent encrypted mapping store with tiered protection levels.

    Each session's mappings are partitioned by protection level and stored
    with level-appropriate TTLs. RESTRICTED data (level 4) auto-expires
    after 5 minutes — even if the encrypted DB file is copied, those
    mappings are irrecoverably gone.
    """

    def __init__(self, ttl: int = DEFAULT_TTL):
        self._ttl = ttl
        self._key = self._load_or_create_key()
        self._fernet = Fernet(self._key)
        self._init_db()

    def _load_or_create_key(self) -> bytes:
        """Load encryption key from file, or create a new one."""
        import os as _os
        DB_DIR.mkdir(parents=True, exist_ok=True)
        DB_DIR.chmod(0o700)
        if KEY_FILE.exists():
            return KEY_FILE.read_bytes()
        key = Fernet.generate_key()
        # Write key file with secure permissions from the start (owner-only)
        fd = _os.open(str(KEY_FILE), _os.O_WRONLY | _os.O_CREAT | _os.O_EXCL, 0o600)
        try:
            _os.write(fd, key)
        finally:
            _os.close(fd)
        logger.info("Neuer Verschluesselungsschluessel erstellt: ~/.austrai/mappings.key")
        return key

    def _init_db(self):
        """Create the database tables if they don't exist."""
        DB_DIR.mkdir(parents=True, exist_ok=True)
        DB_DIR.chmod(0o700)
        with self._connect() as conn:
            # v1 table (kept for backward compatibility during migration)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    mappings_encrypted BLOB NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires ON sessions(expires_at)
            """)

            # v2 table: tiered by protection level
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions_v2 (
                    session_id TEXT NOT NULL,
                    protection_level INTEGER NOT NULL,
                    mappings_encrypted BLOB NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    last_accessed REAL,
                    PRIMARY KEY (session_id, protection_level)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_v2_expires
                ON sessions_v2(expires_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_v2_session
                ON sessions_v2(session_id)
            """)

            # Audit log: no PII, only session_id + action + level + count
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    max_level INTEGER,
                    entity_count INTEGER,
                    timestamp REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_session
                ON audit_log(session_id)
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(DB_FILE))

    # ------------------------------------------------------------------
    # v2 API: tiered create / get / rehydrate
    # ------------------------------------------------------------------

    def create_session(
        self,
        mappings: dict[str, str],
        level_map: dict[str, int] | None = None,
    ) -> str:
        """Store mappings partitioned by protection level.

        Args:
            mappings: {codename: original_text}
            level_map: {codename: protection_level (1-4)}.
                       If None, all mappings get level 2 (INTERNAL).

        Returns:
            session_id (UUID)
        """
        session_id = str(uuid.uuid4())
        now = time.time()

        if not level_map:
            # No classification info — store everything as INTERNAL (v1 compat)
            level_map = {k: 2 for k in mappings}

        # Partition mappings by level
        by_level: dict[int, dict[str, str]] = {}
        for codename, original in mappings.items():
            level = level_map.get(codename, 2)
            by_level.setdefault(level, {})[codename] = original

        with self._connect() as conn:
            for level, level_mappings in by_level.items():
                ttl = LEVEL_TTL.get(level, self._ttl)
                encrypted = self._fernet.encrypt(
                    json.dumps(level_mappings, ensure_ascii=False).encode()
                )
                conn.execute(
                    """INSERT INTO sessions_v2
                       (session_id, protection_level, mappings_encrypted,
                        created_at, expires_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (session_id, level, encrypted, now, now + ttl),
                )

            # Audit: session created
            total = len(mappings)
            max_level = max(by_level.keys()) if by_level else 2
            conn.execute(
                """INSERT INTO audit_log
                   (session_id, action, max_level, entity_count, timestamp)
                   VALUES (?, 'create', ?, ?, ?)""",
                (session_id, max_level, total, now),
            )

        return session_id

    def get_session(
        self,
        session_id: str,
        max_level: int = 4,
    ) -> dict[str, str] | None:
        """Retrieve mappings up to max_level. Expired levels are skipped.

        Args:
            session_id: The session UUID.
            max_level: Maximum protection level to return (1-4).
                       Default 4 = return everything.

        Returns:
            Merged mappings dict, or None if session not found.
        """
        now = time.time()
        merged: dict[str, str] = {}

        with self._connect() as conn:
            rows = conn.execute(
                """SELECT protection_level, mappings_encrypted, expires_at
                   FROM sessions_v2
                   WHERE session_id = ? AND protection_level <= ?
                   ORDER BY protection_level""",
                (session_id, max_level),
            ).fetchall()

            if not rows:
                # Fallback: check v1 table for backward compatibility
                return self._get_session_v1(session_id)

            for level, encrypted, expires_at in rows:
                if now > expires_at:
                    continue  # This level has expired
                try:
                    decrypted = self._fernet.decrypt(encrypted)
                    level_mappings = json.loads(decrypted.decode())
                    merged.update(level_mappings)
                except Exception:
                    continue

            # Update access tracking
            conn.execute(
                """UPDATE sessions_v2
                   SET access_count = access_count + 1, last_accessed = ?
                   WHERE session_id = ? AND protection_level <= ?
                     AND expires_at > ?""",
                (now, session_id, max_level, now),
            )

            # Audit: rehydrate access
            conn.execute(
                """INSERT INTO audit_log
                   (session_id, action, max_level, entity_count, timestamp)
                   VALUES (?, 'rehydrate', ?, ?, ?)""",
                (session_id, max_level, len(merged), now),
            )

        return merged if merged else None

    def get_session_tiered(
        self,
        session_id: str,
    ) -> dict[int, dict[str, str]] | None:
        """Retrieve all non-expired mappings grouped by protection level.

        Returns:
            {level: {codename: original}} or None if not found.
        """
        now = time.time()
        result: dict[int, dict[str, str]] = {}

        with self._connect() as conn:
            rows = conn.execute(
                """SELECT protection_level, mappings_encrypted, expires_at
                   FROM sessions_v2
                   WHERE session_id = ? ORDER BY protection_level""",
                (session_id,),
            ).fetchall()

            if not rows:
                return None

            for level, encrypted, expires_at in rows:
                if now > expires_at:
                    continue
                try:
                    decrypted = self._fernet.decrypt(encrypted)
                    result[level] = json.loads(decrypted.decode())
                except Exception:
                    continue

        return result if result else None

    def get_session_info(self, session_id: str) -> dict | None:
        """Get metadata about a session (levels, TTLs, expiry times).

        Returns dict with per-level info for the UI countdown display.
        """
        now = time.time()
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT protection_level, created_at, expires_at,
                          access_count, last_accessed
                   FROM sessions_v2
                   WHERE session_id = ? ORDER BY protection_level""",
                (session_id,),
            ).fetchall()

        if not rows:
            return None

        levels = {}
        for level, created_at, expires_at, access_count, last_accessed in rows:
            remaining = max(0, expires_at - now)
            levels[level] = {
                "protection_level": level,
                "created_at": created_at,
                "expires_at": expires_at,
                "remaining_seconds": round(remaining),
                "expired": remaining <= 0,
                "access_count": access_count,
                "last_accessed": last_accessed,
            }

        return {
            "session_id": session_id,
            "levels": levels,
            "max_level": max(levels.keys()),
            "any_expired": any(v["expired"] for v in levels.values()),
        }

    def get_latest_session(self) -> tuple[str, dict[str, str]] | None:
        """Get the most recent non-expired session. For CLI deanon."""
        now = time.time()
        with self._connect() as conn:
            # Find most recent session from v2
            row = conn.execute(
                """SELECT DISTINCT session_id
                   FROM sessions_v2
                   WHERE expires_at > ?
                   ORDER BY created_at DESC LIMIT 1""",
                (now,),
            ).fetchone()

        if row:
            session_id = row[0]
            mappings = self.get_session(session_id)
            if mappings:
                return session_id, mappings

        # Fallback to v1
        return self._get_latest_session_v1()

    def delete_session(self, session_id: str) -> None:
        """Delete all data for a session (both v1 and v2)."""
        now = time.time()
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions_v2 WHERE session_id = ?", (session_id,))
            conn.execute(
                """INSERT INTO audit_log
                   (session_id, action, max_level, entity_count, timestamp)
                   VALUES (?, 'delete', NULL, NULL, ?)""",
                (session_id, now),
            )

    def cleanup(self) -> int:
        """Remove all expired sessions. Returns count of removed rows."""
        now = time.time()
        with self._connect() as conn:
            c1 = conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            c2 = conn.execute("DELETE FROM sessions_v2 WHERE expires_at < ?", (now,))

            total = (c1.rowcount or 0) + (c2.rowcount or 0)

            if total:
                conn.execute(
                    """INSERT INTO audit_log
                       (session_id, action, max_level, entity_count, timestamp)
                       VALUES ('_cleanup', 'expire', NULL, ?, ?)""",
                    (total, now),
                )

            return total

    def count(self) -> int:
        """Count active (non-expired) sessions."""
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                """SELECT COUNT(DISTINCT session_id)
                   FROM sessions_v2 WHERE expires_at > ?""",
                (now,),
            ).fetchone()
            v2_count = row[0] if row else 0

            row = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE expires_at > ?",
                (now,),
            ).fetchone()
            v1_count = row[0] if row else 0

            return v2_count + v1_count

    def get_audit_log(
        self,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Retrieve audit log entries. No PII — only actions and metadata."""
        with self._connect() as conn:
            if session_id:
                rows = conn.execute(
                    """SELECT session_id, action, max_level, entity_count, timestamp
                       FROM audit_log
                       WHERE session_id = ?
                       ORDER BY timestamp DESC LIMIT ?""",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT session_id, action, max_level, entity_count, timestamp
                       FROM audit_log
                       ORDER BY timestamp DESC LIMIT ?""",
                    (limit,),
                ).fetchall()

        return [
            {
                "session_id": r[0],
                "action": r[1],
                "max_level": r[2],
                "entity_count": r[3],
                "timestamp": r[4],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # v1 backward compatibility
    # ------------------------------------------------------------------

    def _get_session_v1(self, session_id: str) -> dict[str, str] | None:
        """Retrieve from v1 table (legacy sessions before classification)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT mappings_encrypted, expires_at FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()

        if not row:
            return None

        encrypted, expires_at = row
        if time.time() > expires_at:
            self.delete_session(session_id)
            return None

        try:
            decrypted = self._fernet.decrypt(encrypted)
            return json.loads(decrypted.decode())
        except Exception:
            return None

    def _get_latest_session_v1(self) -> tuple[str, dict[str, str]] | None:
        """Get latest from v1 table."""
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                """SELECT session_id, mappings_encrypted
                   FROM sessions WHERE expires_at > ?
                   ORDER BY created_at DESC LIMIT 1""",
                (now,),
            ).fetchone()

        if not row:
            return None

        session_id, encrypted = row
        try:
            decrypted = self._fernet.decrypt(encrypted)
            return session_id, json.loads(decrypted.decode())
        except Exception:
            return None
