"""Text tokenizer: converts raw text into characters and special-key tokens.

A token is either a plain single-character string or a :class:`SpecialKey`.
``{Enter}``, ``{F5}``, ``{Win}`` and friends become special keys; unknown
``{...}`` sequences are typed literally.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum

_TOKEN_PATTERN = re.compile(r"\{([^{}]+)\}")

# Maps user-facing key names (case-insensitive) to pyautogui key names.
_SPECIAL_KEYS: dict[str, str] = {
    "enter": "enter",
    "tab": "tab",
    "space": "space",
    "backspace": "backspace",
    "delete": "delete",
    "del": "delete",
    "esc": "esc",
    "escape": "esc",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "home": "home",
    "end": "end",
    "pageup": "pageup",
    "pagedown": "pagedown",
    "win": "win",
    "windows": "win",
    **{f"f{i}": f"f{i}" for i in range(1, 13)},
}


class CapsMode(StrEnum):
    AS_IS = "as_is"
    UPPERCASE = "uppercase"
    LOWERCASE = "lowercase"
    SENTENCE_CASE = "sentence_case"


@dataclass(frozen=True, slots=True)
class SpecialKey:
    """A named special key (e.g. Enter, F5) to be pressed rather than typed."""

    name: str  # pyautogui key name


def normalize_key_name(name: str) -> str | None:
    """Return the canonical pyautogui key name for *name*, or None if unknown."""
    return _SPECIAL_KEYS.get(name.strip().lower())


def tokenize(text: str) -> list[str | SpecialKey]:
    """Split *text* into a list of single-character and :class:`SpecialKey` tokens."""
    tokens: list[str | SpecialKey] = []
    pos = 0
    for match in _TOKEN_PATTERN.finditer(text):
        tokens.extend(_char_tokens(text[pos : match.start()]))
        name = normalize_key_name(match.group(1))
        tokens.append(SpecialKey(name) if name else "{")
        if not name:  # unknown key: type the whole sequence literally
            tokens.extend(_char_tokens(match.group(0)[1:]))
        pos = match.end()
    tokens.extend(_char_tokens(text[pos:]))
    return tokens


def _char_tokens(text: str) -> Iterator[str]:
    yield from text


def apply_caps_mode(text: str, mode: CapsMode | str) -> str:
    """Transform *text* according to *mode*.

    Sentence case capitalizes the first letter after sentence boundaries
    (``.``, ``!``, ``?``, newlines) without altering the rest of the text.
    """
    match CapsMode(mode):
        case CapsMode.UPPERCASE:
            return text.upper()
        case CapsMode.LOWERCASE:
            return text.lower()
        case CapsMode.SENTENCE_CASE:
            return _sentence_case(text)
        case _:
            return text


def _sentence_case(text: str) -> str:
    chars = list(text)
    capitalize_next = True
    for i, ch in enumerate(chars):
        if capitalize_next and ch.isalpha():
            chars[i] = ch.upper()
            capitalize_next = False
        elif ch in ".!?\n":
            capitalize_next = True
    return "".join(chars)
