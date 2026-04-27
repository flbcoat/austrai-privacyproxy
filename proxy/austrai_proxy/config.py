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
    allow_list: list[str] = field(default_factory=list)
    confidence_threshold: float = 0.6
    spacy_model: str = "de_core_news_sm"
    default_provider: str = ""
    default_model: str = ""
    ollama_url: str = "http://localhost:11434"
    lmstudio_url: str = "http://localhost:1234"

    # Advanced mode (opt-in). Basic users never see the following fields in
    # the UI; they stay at default. Power users enable advanced_mode in
    # Settings > Erweitert to expose reasoning/temperature/slash-commands.
    #
    # auto_route is retained for backward compat in stored configs, but the
    # field is no longer surfaced in the UI and the chat send path ignores
    # it. See project_austrai_pivot_skills_kb_plan.md (25.04.2026 pivot).
    advanced_mode: bool = False
    auto_route: bool = False
    slash_commands: bool = False   # opt-in flag; aliases below apply only when on
    # User-defined alias map: { "opus": {provider, model}, ... }. Curated
    # defaults below ship as a starting point; user can add, edit, delete.
    # Special model value "__local__" picks the first configured local
    # provider (lmstudio > ollama) at send time, so the alias keeps
    # working even when the local model name changes.
    slash_aliases: dict = field(default_factory=lambda: {
        "opus":   {"provider": "anthropic", "model": "claude-opus-4-7"},
        "sonnet": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
        "haiku": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        "lokal": {"provider": "lmstudio", "model": "__local__"},
    })
    reasoning_effort: str = "medium"   # "off" | "low" | "medium" | "high"
    temperature: float = 1.0
    top_p: float = 1.0
    max_tokens: int = 2048   # conservative default; raise via Advanced for long answers

    @classmethod
    def load(cls) -> "ProxyConfig":
        """Load config from file, env vars override file values."""
        config = cls()

        if CONFIG_FILE.exists():
            try:
                data = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
                config.anthropic_api_key = data.get("anthropic_api_key", "")
                config.openai_api_key = data.get("openai_api_key", "")
                config.mistral_api_key = data.get("mistral_api_key", "")
                config.google_api_key = data.get("google_api_key", "")
                config.port = data.get("port", DEFAULT_PORT)
                config.deny_list = data.get("deny_list", [])
                config.allow_list = data.get("allow_list", [])
                config.confidence_threshold = data.get("confidence_threshold", 0.6)
                config.spacy_model = data.get("spacy_model", "de_core_news_lg")
                config.default_provider = data.get("default_provider", "")
                config.default_model = data.get("default_model", "")
                config.ollama_url = data.get("ollama_url", "http://localhost:11434")
                config.lmstudio_url = data.get("lmstudio_url", "http://localhost:1234")
                config.advanced_mode = bool(data.get("advanced_mode", False))
                config.auto_route = bool(data.get("auto_route", False))
                config.slash_commands = bool(data.get("slash_commands", False))
                if isinstance(data.get("slash_aliases"), dict):
                    cleaned = {}
                    for k, v in data["slash_aliases"].items():
                        if isinstance(k, str) and isinstance(v, dict):
                            cleaned[k.strip().lower()] = {
                                "provider": str(v.get("provider", "")),
                                "model": str(v.get("model", "")),
                            }
                    if cleaned:
                        config.slash_aliases = cleaned
                config.reasoning_effort = data.get("reasoning_effort", "medium")
                config.temperature = float(data.get("temperature", 1.0))
                config.top_p = float(data.get("top_p", 1.0))
                config.max_tokens = int(data.get("max_tokens", 4096))
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
            "allow_list": self.allow_list,
            "confidence_threshold": self.confidence_threshold,
            "spacy_model": self.spacy_model,
            "default_provider": self.default_provider,
            "default_model": self.default_model,
            "ollama_url": self.ollama_url,
            "lmstudio_url": self.lmstudio_url,
            "advanced_mode": self.advanced_mode,
            "auto_route": self.auto_route,
            "slash_commands": self.slash_commands,
            "slash_aliases": self.slash_aliases,
            "reasoning_effort": self.reasoning_effort,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }
        CONFIG_FILE.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
        # POSIX-Permissions: Windows silently accepts chmod but doesn't enforce
        # the mode. If chmod raises (some networked filesystems), swallow it —
        # the write succeeded, which is what matters.
        try:
            CONFIG_FILE.chmod(0o600)
        except (OSError, NotImplementedError):
            pass
