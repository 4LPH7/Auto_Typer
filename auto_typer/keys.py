"""Text tokenizer: converts raw text into characters and special-key tokens.

A token is a plain single-character string or one of three markers:

* :class:`SpecialKey` — ``{Enter}``, ``{F5}``, ``{Win}`` and friends
* :class:`KeyCombo` — ``{Ctrl+A}``, ``{Ctrl+Shift+S}``, ``{Alt+F4}``, ``{Win+R}``
* :class:`Pause` — ``{Sleep 500}`` (also ``Delay`` / ``Wait``), in milliseconds

Unknown ``{...}`` sequences are typed literally.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum

_TOKEN_PATTERN = re.compile(r"\{([^{}]+)\}")
_PAUSE_PATTERN = re.compile(r"(?:sleep|delay|wait|pause)\s+(\d+)", re.IGNORECASE)
MAX_PAUSE_MS = 60_000

# Maps user-facing key names (case-insensitive) to canonical key names.
_SPECIAL_KEYS: dict[str, str] = {
    "enter": "enter",
    "return": "enter",
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

# Modifier names allowed in a combo, mapped to their canonical form.
_MODIFIERS: dict[str, str] = {
    "ctrl": "ctrl", "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "win": "win", "windows": "win", "cmd": "win", "super": "win",
}


class CapsMode(StrEnum):
    AS_IS = "as_is"
    UPPERCASE = "uppercase"
    LOWERCASE = "lowercase"
    SENTENCE_CASE = "sentence_case"


@dataclass(frozen=True, slots=True)
class SpecialKey:
    """A named special key (e.g. Enter, F5) to be pressed rather than typed."""

    name: str  # canonical key name, see _SPECIAL_KEYS


@dataclass(frozen=True, slots=True)
class KeyCombo:
    """A key pressed while modifiers are held, e.g. Ctrl+Shift+S."""

    modifiers: tuple[str, ...]  # canonical modifier names: ctrl, alt, shift, win
    key: str  # a canonical special key name, or a single lower-case character

    @property
    def name(self) -> str:
        """The combo as the writer receives it: ``ctrl+shift+s``."""
        return "+".join((*self.modifiers, self.key))


@dataclass(frozen=True, slots=True)
class Pause:
    """A wait in the middle of the text; nothing is typed."""

    seconds: float


Token = str | SpecialKey | KeyCombo | Pause

# Special keys that separate words, like the whitespace they stand for.
_WORD_GAP_KEYS = {"enter", "tab", "space"}


def is_word_gap(token: Token) -> bool:
    """True for a token between words: whitespace, or the Enter, Tab or Space key."""
    if isinstance(token, SpecialKey):
        return token.name in _WORD_GAP_KEYS
    return isinstance(token, str) and token.isspace()


def keystrokes(tokens: Iterable[Token]) -> int:
    """How many key presses *tokens* take: one per character, key or combo."""
    return sum(0 if isinstance(t, Pause) else len(t) if isinstance(t, str) else 1 for t in tokens)


def pause_seconds(tokens: Iterable[Token]) -> float:
    """The total time *tokens* spend in ``{Sleep}`` pauses."""
    return sum(t.seconds for t in tokens if isinstance(t, Pause))


def normalize_key_name(name: str) -> str | None:
    """Return the canonical key name for *name*, or None if unknown."""
    return _SPECIAL_KEYS.get(name.strip().lower())


def parse_marker(raw: str) -> SpecialKey | KeyCombo | Pause | None:
    """Interpret the inside of a ``{...}`` marker, or None if it isn't one."""
    name = normalize_key_name(raw)
    if name:
        return SpecialKey(name)
    if match := _PAUSE_PATTERN.fullmatch(raw.strip()):
        return Pause(min(int(match.group(1)), MAX_PAUSE_MS) / 1000.0)
    parts = [part.strip().lower() for part in raw.split("+")]
    if len(parts) < 2 or not all(parts):
        return None
    *modifiers, last = parts
    if not all(m in _MODIFIERS for m in modifiers):
        return None
    key = normalize_key_name(last) or (last if len(last) == 1 else None)
    if key is None:
        return None
    return KeyCombo(tuple(dict.fromkeys(_MODIFIERS[m] for m in modifiers)), key)


def tokenize(text: str) -> list[Token]:
    """Split *text* into single characters and marker tokens."""
    tokens: list[Token] = []
    pos = 0
    for match in _TOKEN_PATTERN.finditer(text):
        tokens.extend(_char_tokens(text[pos : match.start()]))
        marker = parse_marker(match.group(1))
        if marker is None:  # unknown marker: type the whole sequence literally
            tokens.extend(_char_tokens(match.group(0)))
        else:
            tokens.append(marker)
        pos = match.end()
    tokens.extend(_char_tokens(text[pos:]))
    return tokens


def _char_tokens(text: str) -> Iterator[str]:
    yield from text


def apply_caps_mode(text: str, mode: CapsMode | str) -> str:
    """Transform *text* according to *mode*.

    Sentence case capitalizes the first letter after sentence boundaries
    (``.``, ``!``, ``?``, newlines) without altering the rest of the text.
    Markers keep working whatever the case: ``{ENTER}`` is still Enter.
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
