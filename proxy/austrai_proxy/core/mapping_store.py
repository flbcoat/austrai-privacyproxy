"""Persistent encrypted Mapping Store — SQLite + Fernet (AES-128-CBC).

Replaces the in-memory SessionStore with a persistent, encrypted database.
Mappings survive process restarts. Sessions expire after TTL.

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
DEFAULT_TTL = 3600  # 1 hour


class MappingStore:
    """Persistent encrypted mapping store using SQLite + Fernet."""

    def __init__(self, ttl: int = DEFAULT_TTL):
        self._ttl = ttl
        self._key = self._load_or_create_key()
        self._fernet = Fernet(self._key)
        self._init_db()

    def _load_or_create_key(self) -> bytes:
        """Load encryption key from file, or create a new one."""
        DB_DIR.mkdir(parents=True, exist_ok=True)
        if KEY_FILE.exists():
            return KEY_FILE.read_bytes()
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
        KEY_FILE.chmod(0o600)
        logger.info("Neuer Verschluesselungsschluessel erstellt: %s", KEY_FILE)
        return key

    def _init_db(self):
        """Create the database table if it doesn't exist."""
        DB_DIR.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
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

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(DB_FILE))

    def create_session(self, mappings: dict[str, str]) -> str:
        """Store mappings and return a session ID."""
        session_id = str(uuid.uuid4())
        now = time.time()
        encrypted = self._fernet.encrypt(json.dumps(mappings, ensure_ascii=False).encode())

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, mappings_encrypted, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (session_id, encrypted, now, now + self._ttl),
            )
        return session_id

    def get_session(self, session_id: str) -> dict[str, str] | None:
        """Retrieve mappings for a session. Returns None if expired or not found."""
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

    def get_latest_session(self) -> tuple[str, dict[str, str]] | None:
        """Get the most recent non-expired session. For CLI deanon."""
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_id, mappings_encrypted FROM sessions WHERE expires_at > ? ORDER BY created_at DESC LIMIT 1",
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

    def delete_session(self, session_id: str) -> None:
        """Delete a specific session."""
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    def cleanup(self) -> int:
        """Remove all expired sessions. Returns count of removed sessions."""
        now = time.time()
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
            return cursor.rowcount

    def count(self) -> int:
        """Count active (non-expired) sessions."""
        now = time.time()
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM sessions WHERE expires_at > ?", (now,)).fetchone()
            return row[0] if row else 0
