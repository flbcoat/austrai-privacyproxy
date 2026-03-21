"""Rehydration service: replaces placeholders in LLM responses with original PII data."""

import re


def rehydrate(llm_response: str, mappings: dict[str, str]) -> str:
    """Replace anonymization placeholders in the LLM response with original values.

    Uses a three-pass strategy:
    1. Exact match replacement
    2. Case-insensitive match
    3. Fuzzy match (handles LLM variations like missing brackets, extra spaces)

    Processes longest placeholders first to avoid partial matches.

    Args:
        llm_response: The LLM response containing placeholders.
        mappings: Dictionary of {placeholder: original_text}.

    Returns:
        The rehydrated text with original PII values restored.
    """
    if not mappings:
        return llm_response

    result = llm_response

    # Sort placeholders by length (longest first) to avoid partial matches
    sorted_placeholders = sorted(mappings.keys(), key=len, reverse=True)

    # Pass 1: Exact match replacement
    remaining: list[str] = []
    for placeholder in sorted_placeholders:
        if placeholder in result:
            result = result.replace(placeholder, mappings[placeholder])
        else:
            remaining.append(placeholder)

    if not remaining:
        return result

    # Pass 2: Case-insensitive match
    # Use lambda for replacement to avoid regex interpretation of backslashes
    still_remaining: list[str] = []
    for placeholder in remaining:
        pattern = re.compile(re.escape(placeholder), re.IGNORECASE)
        original = mappings[placeholder]
        new_result, count = pattern.subn(lambda m, o=original: o, result)
        if count > 0:
            result = new_result
        else:
            still_remaining.append(placeholder)

    if not still_remaining:
        return result

    # Pass 3: Fuzzy match — handle LLM variations
    for placeholder in still_remaining:
        original = mappings[placeholder]
        fuzzy_pattern = _build_fuzzy_pattern(placeholder)
        try:
            compiled = re.compile(fuzzy_pattern, re.IGNORECASE)
            result = compiled.sub(lambda m, o=original: o, result)
        except re.error:
            # If the regex is invalid, skip this placeholder
            continue

    return result


def _build_fuzzy_pattern(placeholder: str) -> str:
    """Build a fuzzy regex pattern for a placeholder.

    Handles common LLM variations:
    - Missing or extra brackets: PERSON_1 instead of [PERSON_1]
    - Extra spaces inside brackets: [ PERSON_1 ]
    - Underscores replaced with spaces or hyphens
    - Brackets replaced with parentheses

    Args:
        placeholder: The original placeholder like "[PERSON_1]".

    Returns:
        A regex pattern string.
    """
    # Extract the inner content (without brackets)
    inner = placeholder.strip("[]")

    # Escape special regex chars in the inner content, then allow variations
    # Split into parts (e.g., "PERSON" and "1")
    parts = inner.split("_")

    # Build pattern where separators can be _, -, space, or nothing
    inner_pattern = r"[\s_\-]?".join(re.escape(part) for part in parts)

    # Allow optional brackets (square or round) and optional spaces inside
    pattern = (
        r"(?:"
        r"[\[\(]?\s?" + inner_pattern + r"\s?[\]\)]?"
        r")"
    )

    return pattern
