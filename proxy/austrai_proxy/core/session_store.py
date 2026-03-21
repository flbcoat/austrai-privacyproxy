"""In-memory session store with TTL for anonymization mappings."""

import threading
import time
import uuid




class SessionStore:
    """Thread-safe in-memory session store with automatic TTL expiration."""

    def __init__(self, ttl: int | None = None) -> None:
        self._store: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._ttl = ttl if ttl is not None else 1800

    def create_session(self, mappings: dict[str, str]) -> str:
        """Create a new session with the given mappings.

        Args:
            mappings: Dictionary of placeholder -> original text.

        Returns:
            A unique session ID (UUID4).
        """
        session_id = str(uuid.uuid4())
        with self._lock:
            self._store[session_id] = {
                "mappings": mappings,
                "created_at": time.time(),
            }
        return session_id

    def get_session(self, session_id: str) -> dict[str, str] | None:
        """Retrieve mappings for a session if it has not expired.

        Args:
            session_id: The session UUID.

        Returns:
            The mappings dict, or None if the session does not exist or has expired.
        """
        with self._lock:
            session = self._store.get(session_id)
            if session is None:
                return None
            if time.time() - session["created_at"] > self._ttl:
                del self._store[session_id]
                return None
            return session["mappings"]

    def cleanup(self) -> int:
        """Remove all expired sessions.

        Returns:
            Number of sessions removed.
        """
        now = time.time()
        removed = 0
        with self._lock:
            expired_keys = [
                sid
                for sid, data in self._store.items()
                if now - data["created_at"] > self._ttl
            ]
            for key in expired_keys:
                del self._store[key]
                removed += 1
        return removed

    @property
    def size(self) -> int:
        """Current number of stored sessions."""
        with self._lock:
            return len(self._store)


# Global session store instance
