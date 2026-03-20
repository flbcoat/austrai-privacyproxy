"""Persistent custom terms (deny list) management.

Stores custom terms in ~/.privacyproxy/config.yaml and provides
thread-safe read/write access for use by both the CLI and the API server.
"""

import threading
from pathlib import Path

import yaml

CONFIG_DIR = Path.home() / ".privacyproxy"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

_lock = threading.Lock()


def _load_config() -> dict:
    """Load the full config from disk. Returns empty dict if file missing."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_config(config: dict) -> None:
    """Save the full config to disk, creating the directory if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


def get_custom_terms() -> list[str]:
    """Return the current list of custom deny-list terms.

    Thread-safe. Reads from ~/.privacyproxy/config.yaml.

    Returns:
        List of custom term strings.
    """
    with _lock:
        config = _load_config()
        terms = config.get("custom_terms", [])
        if isinstance(terms, list):
            return [str(t) for t in terms]
        return []


def add_terms(terms: list[str]) -> list[str]:
    """Add one or more terms to the custom deny list.

    Duplicates are ignored. Thread-safe.

    Args:
        terms: Terms to add.

    Returns:
        The updated list of all custom terms.
    """
    with _lock:
        config = _load_config()
        existing = config.get("custom_terms", [])
        if not isinstance(existing, list):
            existing = []
        existing_set = set(existing)
        for term in terms:
            term = term.strip()
            if term and term not in existing_set:
                existing.append(term)
                existing_set.add(term)
        config["custom_terms"] = existing
        _save_config(config)
        return existing


def remove_term(term: str) -> bool:
    """Remove a single term from the custom deny list.

    Thread-safe.

    Args:
        term: The term to remove.

    Returns:
        True if the term was found and removed, False otherwise.
    """
    with _lock:
        config = _load_config()
        existing = config.get("custom_terms", [])
        if not isinstance(existing, list):
            return False
        term = term.strip()
        if term in existing:
            existing.remove(term)
            config["custom_terms"] = existing
            _save_config(config)
            return True
        return False


def clear_terms() -> int:
    """Remove all custom terms.

    Thread-safe.

    Returns:
        The number of terms that were cleared.
    """
    with _lock:
        config = _load_config()
        existing = config.get("custom_terms", [])
        count = len(existing) if isinstance(existing, list) else 0
        config["custom_terms"] = []
        _save_config(config)
        return count
