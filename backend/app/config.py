"""Application configuration with dual-source support.

Load order:
1. Environment variables / .env file (Docker, direct env)
2. ~/.privacyproxy/config.yaml fallback (CLI / pip install)

This ensures backward compatibility with the existing Docker setup
while also supporting the CLI configuration file.
"""

import os
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings

# ---------------------------------------------------------------------------
# Pre-load from ~/.privacyproxy/config.yaml into env vars (if not already set)
# ---------------------------------------------------------------------------

_CLI_CONFIG_FILE = Path.home() / ".privacyproxy" / "config.yaml"


def _preload_cli_config() -> None:
    """Read ~/.privacyproxy/config.yaml and set env vars for any values
    not already provided by the environment or .env file.

    This runs once at import time so that pydantic-settings can pick up
    the values from the environment.
    """
    if not _CLI_CONFIG_FILE.exists():
        return

    try:
        import yaml
        with open(_CLI_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return
    except Exception:
        return

    _yaml_to_env = {
        "mistral_api_key": "MISTRAL_API_KEY",
        "model": "MISTRAL_MODEL",
        "confidence_threshold": "CONFIDENCE_THRESHOLD",
    }

    for yaml_key, env_key in _yaml_to_env.items():
        value = data.get(yaml_key)
        if value is not None and env_key not in os.environ:
            os.environ[env_key] = str(value)

    # Custom terms
    terms = data.get("custom_terms")
    if isinstance(terms, list) and terms and "CUSTOM_TERMS" not in os.environ:
        os.environ["CUSTOM_TERMS"] = ",".join(str(t) for t in terms)

    # Local LLM settings
    local_llm = data.get("local_llm")
    if isinstance(local_llm, dict):
        if local_llm.get("enabled") and "LOCAL_LLM_ENABLED" not in os.environ:
            os.environ["LOCAL_LLM_ENABLED"] = "true"
        if local_llm.get("model_path") and "LOCAL_LLM_MODEL_PATH" not in os.environ:
            os.environ["LOCAL_LLM_MODEL_PATH"] = str(local_llm["model_path"])


# Run the preload before Settings is instantiated
_preload_cli_config()


# ---------------------------------------------------------------------------
# Settings class
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    MISTRAL_API_KEY: str = ""
    MISTRAL_MODEL: str = "mistral/mistral-small-latest"
    ALLOWED_ORIGINS: str = "https://austr.ai,https://www.austr.ai,http://localhost:4321"
    RATE_LIMIT_PER_IP: int = 20
    RATE_LIMIT_GLOBAL: int = 200
    MIN_REQUEST_DELAY: float = 1.0
    MAX_TEXT_LENGTH: int = 2000
    SESSION_TTL: int = 1800
    CONFIDENCE_THRESHOLD: float = 0.6

    # New: custom terms from config
    CUSTOM_TERMS: list[str] = []

    # New: local LLM settings
    LOCAL_LLM_ENABLED: bool = False
    LOCAL_LLM_MODEL_PATH: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
