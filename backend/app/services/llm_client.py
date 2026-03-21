"""LLM client using LiteLLM to call Mistral models."""

import logging
import os

import litellm

from app.config import settings

logger = logging.getLogger(__name__)

# System prompt — simpler now because codenames look like real names.
# The LLM only needs special instruction for bracket references.
SYSTEM_PROMPT = (
    "Du bist ein hilfreicher Assistent. Der Text enthaelt Referenz-Codes "
    "in eckigen Klammern (z.B. [AT_IBAN_1], [PHONE_NUMBER_1]). "
    "Uebernimm diese EXAKT wie sie erscheinen — inklusive der eckigen "
    "Klammern und der Nummerierung. Aendere sie NIEMALS ab."
)


async def call_llm(anonymized_text: str, user_prompt: str) -> str:
    """Call the Mistral LLM via LiteLLM with the anonymized text.

    Args:
        anonymized_text: The anonymized text containing placeholders.
        user_prompt: Additional user instructions for the LLM.

    Returns:
        The LLM's response text, or an error message string on failure.
    """
    # Set the API key for Mistral via environment variable (LiteLLM reads it)
    os.environ["MISTRAL_API_KEY"] = settings.MISTRAL_API_KEY

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"{user_prompt}\n\n---\n\n{anonymized_text}",
        },
    ]

    try:
        response = await litellm.acompletion(
            model=settings.MISTRAL_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=2000,
        )

        content = response.choices[0].message.content
        if content is None:
            logger.warning("LLM-Antwort enthielt keinen Content.")
            return "[Fehler: Leere Antwort vom Sprachmodell]"

        return content.strip()

    except Exception as e:
        logger.error("Fehler beim LLM-Aufruf: %s", str(e), exc_info=True)
        return f"[Fehler beim Sprachmodell-Aufruf: {type(e).__name__}]"
