"""Optional context check with Claude.

A statistical tokenizer picks a reading from the words around it, but it
cannot know that 辛い next to 料理 is からい (spicy) rather than つらい
(painful) if its training counts say otherwise. When this check is on, the
sentence and the analyser's candidates are sent to Claude, which returns the
reading and meaning that actually fit *this* sentence. Off by default; needs
`pip install anthropic` and an API key (ANTHROPIC_API_KEY, or `ant auth login`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

DEFAULT_MODEL = "claude-opus-5-5"

_SCHEMA = {
    "type": "object",
    "properties": {
        "reading": {"type": "string", "description": "Kana reading of the word as read in this sentence. Empty for non-Japanese."},
        "dictionary_form": {"type": "string", "description": "Dictionary form of the word as meant here."},
        "meaning": {"type": "string", "description": "Short English meaning of the word as used in this sentence (one sense, not a full dictionary entry)."},
        "note": {"type": "string", "description": "One sentence on why this reading/sense fits the context, or how the alternatives differ. Empty if nothing to say."},
        "analyser_was_right": {"type": "boolean"},
    },
    "required": ["reading", "dictionary_form", "meaning", "note", "analyser_was_right"],
    "additionalProperties": False,
}


@dataclass
class Verdict:
    reading: str
    dictionary_form: str
    meaning: str
    note: str
    analyser_was_right: bool


class AIError(RuntimeError):
    pass


def check(sentence: str, word: str, reading: str, alternatives: list[str], alt_lemmas: list[str],
          lang: str, model: str = DEFAULT_MODEL, api_key: str = "") -> Optional[Verdict]:
    try:
        import anthropic
    except ImportError as exc:
        raise AIError("pip install anthropic to use the AI context check") from exc

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    language = {"ja": "Japanese", "zh": "Chinese", "zh-tw": "Chinese", "ko": "Korean", "en": "English"}.get(lang, lang)
    lines = [
        f"A learner is mining vocabulary from {language} text they are reading.",
        f"Sentence: {sentence}",
        f"Word (as it appears): {word}",
    ]
    if lang == "ja":
        lines.append(f"The morphological analyser read it as: {reading or '(kana only)'}")
        if alternatives:
            lines.append(f"Other readings it considered plausible here: {', '.join(alternatives)}")
        if alt_lemmas:
            lines.append(f"Other dictionary forms it considered: {', '.join(alt_lemmas)}")
    lines.append(
        "Decide, from the sentence context, which reading and which sense is actually meant at this spot. "
        "Give the meaning of the word as used here, not every dictionary sense."
    )
    try:
        response = client.beta.messages.create(
            model=model,
            max_tokens=1024,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": "\n".join(lines)}],
        )
    except anthropic.AuthenticationError as exc:
        raise AIError("Anthropic API key missing or invalid (set ANTHROPIC_API_KEY or anthropic_api_key in config.json)") from exc
    except anthropic.NotFoundError as exc:
        raise AIError(f"Unknown model {model!r}") from exc
    except anthropic.RateLimitError as exc:
        raise AIError("Anthropic API rate limit hit; try again in a moment") from exc
    except anthropic.APIStatusError as exc:
        raise AIError(f"Anthropic API error: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise AIError("Could not reach the Anthropic API (network)") from exc

    if response.stop_reason == "refusal":
        return None
    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return Verdict(
        reading=data.get("reading", ""),
        dictionary_form=data.get("dictionary_form", "") or word,
        meaning=data.get("meaning", ""),
        note=data.get("note", ""),
        analyser_was_right=bool(data.get("analyser_was_right", True)),
    )
