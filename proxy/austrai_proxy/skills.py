"""AUSTR.AI Skills.

Skills are user-defined "profis" that bundle a system-prompt with a
recommended model. They live as .md files with YAML-frontmatter in
~/.austrai/skills/. The chat send-path injects the system-prompt before
the LLM call; it goes through the same anonymisation pipeline as the
user message, so even if a skill body contains PII it never reaches the
LLM in plain text.

Skill schema:

    ---
    name: Rechts-Skill
    description: Anwalt für Mietrecht in Wien
    recommended_provider: anthropic
    recommended_model: claude-sonnet-4-6
    recommended_temperature: 0.3
    ---
    Du bist ein erfahrener Anwalt für Mietrecht in Wien...

The recommended_* fields are non-binding hints. The user can override
them via the chat header, in which case the skill stays active but
runs on whatever model/temperature the user picked.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from .config import CONFIG_DIR

logger = logging.getLogger("austrai.skills")

SKILLS_DIR = CONFIG_DIR / "skills"

# Slug rules: lowercase, alphanumeric plus hyphen/underscore, 1-64 chars.
# Mirrored client-side so users get immediate validation feedback.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass
class Skill:
    slug: str
    name: str = ""
    description: str = ""
    recommended_provider: str = ""
    recommended_model: str = ""
    recommended_temperature: Optional[float] = None
    system_prompt: str = ""

    def to_public_dict(self) -> dict:
        """Public JSON shape returned by /chat/api/skills."""
        return {
            "slug": self.slug,
            "name": self.name or self.slug,
            "description": self.description,
            "recommended_provider": self.recommended_provider,
            "recommended_model": self.recommended_model,
            "recommended_temperature": self.recommended_temperature,
            "system_prompt": self.system_prompt,
        }


def _ensure_dir() -> None:
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)


def _path_for(slug: str) -> Path:
    return SKILLS_DIR / f"{slug}.md"


def is_valid_slug(slug: str) -> bool:
    return bool(_SLUG_RE.match(slug or ""))


def _parse_md(text: str) -> tuple[dict, str]:
    """Split a YAML-frontmatter .md file into (frontmatter_dict, body_str).

    Tolerant: missing or malformed frontmatter returns ({}, full_text)
    rather than raising — a skill without metadata still has a usable body.
    """
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end > 0:
            try:
                fm = yaml.safe_load(text[4:end]) or {}
                if not isinstance(fm, dict):
                    fm = {}
            except yaml.YAMLError:
                fm = {}
            body = text[end + 4 :].lstrip("\n")
            return fm, body
    return {}, text


def _serialize(skill: Skill) -> str:
    fm = {
        "name": skill.name,
        "description": skill.description,
        "recommended_provider": skill.recommended_provider,
        "recommended_model": skill.recommended_model,
    }
    if skill.recommended_temperature is not None:
        fm["recommended_temperature"] = float(skill.recommended_temperature)
    head = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    body = (skill.system_prompt or "").strip() + "\n"
    return f"---\n{head}---\n{body}"


def list_skills() -> list[Skill]:
    """Return all parseable skills sorted by name (case-insensitive)."""
    _ensure_dir()
    skills: list[Skill] = []
    for path in SKILLS_DIR.glob("*.md"):
        slug = path.stem
        if not is_valid_slug(slug):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Failed to read skill %s: %s", slug, e)
            continue
        fm, body = _parse_md(text)
        skills.append(Skill(
            slug=slug,
            name=str(fm.get("name", slug)),
            description=str(fm.get("description", "")),
            recommended_provider=str(fm.get("recommended_provider", "")),
            recommended_model=str(fm.get("recommended_model", "")),
            recommended_temperature=(
                float(fm["recommended_temperature"])
                if isinstance(fm.get("recommended_temperature"), (int, float))
                else None
            ),
            system_prompt=body.strip(),
        ))
    skills.sort(key=lambda s: (s.name or s.slug).lower())
    return skills


def get_skill(slug: str) -> Optional[Skill]:
    if not is_valid_slug(slug):
        return None
    path = _path_for(slug)
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm, body = _parse_md(text)
    return Skill(
        slug=slug,
        name=str(fm.get("name", slug)),
        description=str(fm.get("description", "")),
        recommended_provider=str(fm.get("recommended_provider", "")),
        recommended_model=str(fm.get("recommended_model", "")),
        recommended_temperature=(
            float(fm["recommended_temperature"])
            if isinstance(fm.get("recommended_temperature"), (int, float))
            else None
        ),
        system_prompt=body.strip(),
    )


def save_skill(skill: Skill) -> None:
    """Persist a skill to disk. Caller is responsible for slug validation."""
    if not is_valid_slug(skill.slug):
        raise ValueError(f"Invalid skill slug: {skill.slug!r}")
    _ensure_dir()
    _path_for(skill.slug).write_text(_serialize(skill), encoding="utf-8")


def delete_skill(slug: str) -> bool:
    if not is_valid_slug(slug):
        return False
    path = _path_for(slug)
    if not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError as e:
        logger.warning("Failed to delete skill %s: %s", slug, e)
        return False
