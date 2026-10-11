"""Tests for the tokenizer and caps-mode transformations."""

import pytest

from auto_typer.keys import CapsMode, SpecialKey, apply_caps_mode, normalize_key_name, tokenize


class TestTokenize:
    def test_plain_text_becomes_single_chars(self):
        assert tokenize("abc") == ["a", "b", "c"]

    def test_enter_and_tab_become_special_keys(self):
        tokens = tokenize("a{Enter}b{Tab}c")
        assert tokens == ["a", SpecialKey("enter"), "b", SpecialKey("tab"), "c"]

    def test_function_keys(self):
        assert tokenize("{F5}") == [SpecialKey("f5")]

    def test_all_supported_keys(self):
        names = ["Enter", "Tab", "Space", "Backspace", "Delete", "Esc", "Up", "Down",
                 "Left", "Right", "Home", "End", "PageUp", "PageDown", "Win",
                 *(f"F{i}" for i in range(1, 13))]
        for name in names:
            assert tokenize("{" + name + "}") == [SpecialKey(name.lower())]

    def test_key_names_case_insensitive(self):
        assert tokenize("{enter}{ENTER}{Enter}") == [SpecialKey("enter")] * 3

    def test_unknown_key_typed_literally(self):
        tokens = tokenize("a{Nope}b")
        assert tokens == ["a", "{", "N", "o", "p", "e", "}", "b"]

    def test_unmatched_braces_typed_literally(self):
        assert tokenize("a{b") == ["a", "{", "b"]
        assert tokenize("a}b") == ["a", "}", "b"]

    def test_angle_brackets_typed_normally(self):
        assert tokenize("<>") == ["<", ">"]

    def test_empty_text(self):
        assert tokenize("") == []

    def test_adjacent_special_keys(self):
        assert tokenize("{Enter}{Enter}") == [SpecialKey("enter"), SpecialKey("enter")]


class TestNormalizeKeyName:
    @pytest.mark.parametrize("raw,expected", [
        ("enter", "enter"), ("ENTER", "enter"), (" F5 ", "f5"),
        ("windows", "win"), ("del", "delete"), ("escape", "esc"),
        ("bogus", None),
    ])
    def test_normalization(self, raw, expected):
        assert normalize_key_name(raw) == expected


class TestCapsMode:
    def test_as_is_unchanged(self):
        assert apply_caps_mode("Hello World", CapsMode.AS_IS) == "Hello World"

    def test_uppercase(self):
        assert apply_caps_mode("Hello", CapsMode.UPPERCASE) == "HELLO"

    def test_lowercase(self):
        assert apply_caps_mode("HeLLo", CapsMode.LOWERCASE) == "hello"

    def test_sentence_case_preserves_rest_of_text(self):
        # The old implementation used str.capitalize(), which lowercased
        # everything after the first character.
        assert apply_caps_mode("hello WORLD. more TEXT!", CapsMode.SENTENCE_CASE) == \
            "Hello WORLD. More TEXT!"

    def test_sentence_case_after_newlines_and_punctuation(self):
        assert apply_caps_mode("first\nsecond?third!fourth", CapsMode.SENTENCE_CASE) == \
            "First\nSecond?Third!Fourth"

    def test_accepts_raw_strings(self):
        assert apply_caps_mode("abc", "uppercase") == "ABC"
