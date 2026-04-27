"""Encrypted conversation storage for AUSTR.AI Chat.

Stores chat conversations and messages in SQLite, encrypted with Fernet (AES).
Uses the same encryption key as the mapping store (~/.austrai/mappings.key).
"""

import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

from .config import CONFIG_DIR

logger = logging.getLogger("austrai.conversations")

DB_PATH = CONFIG_DIR / "conversations.db"
KEY_PATH = CONFIG_DIR / "mappings.key"


class ConversationStore:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._fernet = self._load_or_create_key()
        self._init_db()

    def _load_or_create_key(self) -> Fernet:
        if KEY_PATH.exists():
            key = KEY_PATH.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            KEY_PATH.write_bytes(key)
            try:
                KEY_PATH.chmod(0o600)
            except (OSError, NotImplementedError):
                # Windows / non-POSIX filesystems ignore chmod — don't crash
                # the first-run chat setup over a cosmetic perm change.
                pass
        return Fernet(key)

    def _connect(self) -> sqlite3.Connection:
        """Open a SQLite connection with the PRAGMAs we want set on every
        connection — foreign_keys for CASCADE-Delete integrity, and a
        5-second busy_timeout so concurrent writes (z.B. SSE-Streaming +
        Sidebar-Refresh) sich nicht gegenseitig "database is locked" um
        die Ohren hauen.
        """
        conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
        conn.execute("PRAGMA foreign_keys = ON")
        # busy_timeout milliseconds — retry statt sofort zu failen.
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            # WAL-Mode: erlaubt paralleles Lesen während eines Writers,
            # löst die meisten "database is locked" Situationen. Einmal
            # gesetzt bleibt der Mode persistent in der DB-Datei.
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT 'New Chat',
                    model TEXT DEFAULT '',
                    provider TEXT DEFAULT '',
                    system_prompt TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content_encrypted BLOB NOT NULL,
                    anonymized_encrypted BLOB,
                    mappings_encrypted BLOB,
                    entity_count INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_updated ON conversations(updated_at DESC)")

    def _encrypt(self, text: str) -> bytes:
        return self._fernet.encrypt(text.encode("utf-8"))

    def _decrypt(self, data: bytes) -> str:
        return self._fernet.decrypt(data).decode("utf-8")

    # --- Conversations ---

    def create_conversation(self, title: str = "New Chat", model: str = "", provider: str = "", system_prompt: str = "") -> str:
        conv_id = str(uuid.uuid4())
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, model, provider, system_prompt, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (conv_id, title, model, provider, system_prompt, now, now),
            )
        return conv_id

    def list_conversations(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT c.*, COUNT(m.id) as message_count
                   FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id
                   GROUP BY c.id ORDER BY c.updated_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_conversation(self, conv_id: str) -> dict | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        return dict(row) if row else None

    def update_conversation(self, conv_id: str, **kwargs) -> None:
        allowed = {"title", "model", "provider", "system_prompt"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        updates["updated_at"] = time.time()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [conv_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE conversations SET {set_clause} WHERE id = ?", values)

    def delete_conversation(self, conv_id: str) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))

    # --- Messages ---

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        anonymized: str | None = None,
        mappings: dict | None = None,
        entity_count: int = 0,
    ) -> str:
        msg_id = str(uuid.uuid4())
        now = time.time()
        content_enc = self._encrypt(content)
        anon_enc = self._encrypt(anonymized) if anonymized else None
        mappings_enc = self._encrypt(json.dumps(mappings)) if mappings else None

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO messages (id, conversation_id, role, content_encrypted, anonymized_encrypted, mappings_encrypted, entity_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (msg_id, conversation_id, role, content_enc, anon_enc, mappings_enc, entity_count, now),
            )
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
        return msg_id

    def get_messages(self, conversation_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at",
                (conversation_id,),
            ).fetchall()

        messages = []
        for row in rows:
            msg = {
                "id": row[0],
                "conversation_id": row[1],
                "role": row[2],
                "content": self._decrypt(row[3]),
                "anonymized": self._decrypt(row[4]) if row[4] else None,
                "mappings": json.loads(self._decrypt(row[5])) if row[5] else None,
                "entity_count": row[6],
                "created_at": row[7],
            }
            messages.append(msg)
        return messages

    def delete_messages(self, conversation_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
