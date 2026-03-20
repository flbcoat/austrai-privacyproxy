"""LLM client using LiteLLM to call Mistral models."""

import logging
import os

import litellm

from app.config import settings

logger = logging.getLogger(__name__)

# System prompt instructing the LLM to preserve all placeholders exactly
SYSTEM_PROMPT = (
    "Du bist ein hilfreicher Assistent. WICHTIG: Der Text, den du erhältst, enthält "
    "anonymisierte Platzhalter in eckigen Klammern, z.B. [PERSON_1], [AT_IBAN_1], "
    "[PHONE_NUMBER_1], [AT_UID_NR_1] usw. Du MUSST diese Platzhalter EXAKT so "
    "übernehmen, wie sie im Text erscheinen — inklusive der eckigen Klammern, der "
    "exakten Groß-/Kleinschreibung und der Nummerierung. Ändere die Platzhalter "
    "NIEMALS ab, lasse keine Klammern weg und füge keine Leerzeichen innerhalb der "
    "Klammern ein. Beantworte den Text inhaltlich normal, aber behalte alle "
    "Platzhalter unverändert bei."
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
