"""Configuration management for AUSTR.AI."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_DIR = Path.home() / ".austrai"
CONFIG_FILE = CONFIG_DIR / "proxy.yaml"
DEFAULT_PORT = 8282


@dataclass
class ProxyConfig:
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    mistral_api_key: str = ""
    google_api_key: str = ""
    port: int = DEFAULT_PORT
    deny_list: list[str] = field(default_factory=list)
    confidence_threshold: float = 0.6
    spacy_model: str = "de_core_news_lg"

    @classmethod
    def load(cls) -> "ProxyConfig":
        """Load config from file, env vars override file values."""
        config = cls()

        if CONFIG_FILE.exists():
            try:
                data = yaml.safe_load(CONFIG_FILE.read_text()) or {}
                config.anthropic_api_key = data.get("anthropic_api_key", "")
                config.openai_api_key = data.get("openai_api_key", "")
                config.mistral_api_key = data.get("mistral_api_key", "")
                config.google_api_key = data.get("google_api_key", "")
                config.port = data.get("port", DEFAULT_PORT)
                config.deny_list = data.get("deny_list", [])
                config.confidence_threshold = data.get("confidence_threshold", 0.6)
                config.spacy_model = data.get("spacy_model", "de_core_news_lg")
            except Exception:
                pass

        # Env vars override file
        if os.environ.get("ANTHROPIC_API_KEY"):
            config.anthropic_api_key = os.environ["ANTHROPIC_API_KEY"]
        if os.environ.get("OPENAI_API_KEY"):
            config.openai_api_key = os.environ["OPENAI_API_KEY"]
        if os.environ.get("MISTRAL_API_KEY"):
            config.mistral_api_key = os.environ["MISTRAL_API_KEY"]
        if os.environ.get("GOOGLE_API_KEY"):
            config.google_api_key = os.environ["GOOGLE_API_KEY"]
        if os.environ.get("AUSTRAI_PORT"):
            config.port = int(os.environ["AUSTRAI_PORT"])

        return config

    def save(self) -> None:
        """Save config to file."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "anthropic_api_key": self.anthropic_api_key,
            "openai_api_key": self.openai_api_key,
            "mistral_api_key": self.mistral_api_key,
            "google_api_key": self.google_api_key,
            "port": self.port,
            "deny_list": self.deny_list,
            "confidence_threshold": self.confidence_threshold,
            "spacy_model": self.spacy_model,
        }
        CONFIG_FILE.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True))
        CONFIG_FILE.chmod(0o600)
