"""IP-based rate limiting with per-IP and global daily limits."""

import threading
import time
from datetime import datetime, timezone

from app.config import settings


class RateLimiter:
    """Thread-safe rate limiter tracking per-IP and global request counts per day."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ip_counts: dict[str, int] = {}
        self._ip_last_request: dict[str, float] = {}
        self._global_count: int = 0
        self._current_day: str = self._get_today()

    @staticmethod
    def _get_today() -> str:
        """Get today's date string in UTC."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _reset_if_new_day(self) -> None:
        """Reset all counters if the day has changed (midnight UTC)."""
        today = self._get_today()
        if today != self._current_day:
            self._ip_counts.clear()
            self._ip_last_request.clear()
            self._global_count = 0
            self._current_day = today

    def check_rate_limit(self, ip: str) -> tuple[bool, str]:
        """Check if a request from the given IP is allowed.

        Args:
            ip: The client's IP address.

        Returns:
            Tuple of (allowed: bool, reason: str).
            If allowed is True, reason is empty.
            If allowed is False, reason describes why the request was rejected.
        """
        with self._lock:
            self._reset_if_new_day()

            now = time.time()

            # Check minimum delay between requests from same IP
            last_request = self._ip_last_request.get(ip)
            if last_request is not None:
                elapsed = now - last_request
                if elapsed < settings.MIN_REQUEST_DELAY:
                    remaining = settings.MIN_REQUEST_DELAY - elapsed
                    return (
                        False,
                        f"Zu viele Anfragen. Bitte warten Sie noch {remaining:.1f} Sekunden.",
                    )

            # Check global daily limit
            if self._global_count >= settings.RATE_LIMIT_GLOBAL:
                return (
                    False,
                    "Das tägliche Gesamtlimit wurde erreicht. Bitte versuchen Sie es morgen erneut.",
                )

            # Check per-IP daily limit
            ip_count = self._ip_counts.get(ip, 0)
            if ip_count >= settings.RATE_LIMIT_PER_IP:
                return (
                    False,
                    f"Sie haben das tägliche Limit von {settings.RATE_LIMIT_PER_IP} Anfragen erreicht. "
                    f"Bitte versuchen Sie es morgen erneut.",
                )

            # Allow the request and update counters
            self._ip_counts[ip] = ip_count + 1
            self._global_count += 1
            self._ip_last_request[ip] = now

            return (True, "")


# Global rate limiter instance
rate_limiter = RateLimiter()
