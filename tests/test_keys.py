"""Tests for the tokenizer and caps-mode transformations."""

import pytest

from auto_typer.keys import (
    CapsMode,
    KeyCombo,
    Pause,
    SpecialKey,
    apply_caps_mode,
    keystrokes,
    normalize_key_name,
    parse_marker,
    pause_seconds,
    tokenize,
)


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

    def test_non_ascii_text_is_kept(self):
        assert tokenize("café — 你好 🙂") == list("café — 你好 🙂")


class TestCombos:
    def test_ctrl_letter(self):
        assert tokenize("{Ctrl+A}") == [KeyCombo(("ctrl",), "a")]

    def test_several_modifiers_in_given_order(self):
        assert tokenize("{Shift+Ctrl+S}") == [KeyCombo(("shift", "ctrl"), "s")]

    def test_special_key_with_modifier(self):
        assert tokenize("{Alt+F4}") == [KeyCombo(("alt",), "f4")]
        assert tokenize("{Win+R}") == [KeyCombo(("win",), "r")]
        assert tokenize("{Ctrl+Enter}") == [KeyCombo(("ctrl",), "enter")]

    def test_modifier_aliases_and_spacing(self):
        assert tokenize("{ Control + c }") == [KeyCombo(("ctrl",), "c")]
        assert tokenize("{Windows+d}") == [KeyCombo(("win",), "d")]

    def test_name_is_what_the_writer_receives(self):
        assert KeyCombo(("ctrl", "shift"), "s").name == "ctrl+shift+s"

    @pytest.mark.parametrize("raw", ["{Ctrl+}", "{+A}", "{Ctrl++}", "{Foo+A}", "{Ctrl+ab}", "{A+B}"])
    def test_malformed_combo_typed_literally(self, raw):
        assert tokenize(raw) == list(raw)

    def test_combo_is_not_a_word_gap_but_counts_a_keystroke(self):
        tokens = tokenize("a{Ctrl+V}b")
        assert keystrokes(tokens) == 3


class TestPause:
    def test_sleep_in_milliseconds(self):
        assert tokenize("a{Sleep 500}b") == ["a", Pause(0.5), "b"]

    @pytest.mark.parametrize("word", ["Delay", "Wait", "pause", "SLEEP"])
    def test_pause_aliases(self, word):
        assert tokenize("{" + word + " 250}") == [Pause(0.25)]

    def test_pause_is_capped(self):
        assert tokenize("{Sleep 999999}") == [Pause(60.0)]

    def test_pause_without_a_number_is_literal(self):
        assert tokenize("{Sleep}") == list("{Sleep}")
        assert tokenize("{Sleep abc}") == list("{Sleep abc}")

    def test_pause_counts_no_keystrokes(self):
        tokens = tokenize("ab{Sleep 100}c{Sleep 400}")
        assert keystrokes(tokens) == 3
        assert pause_seconds(tokens) == 0.5


class TestNormalizeKeyName:
    @pytest.mark.parametrize("raw,expected", [
        ("enter", "enter"), ("ENTER", "enter"), (" F5 ", "f5"),
        ("windows", "win"), ("del", "delete"), ("escape", "esc"), ("return", "enter"),
        ("bogus", None),
    ])
    def test_normalization(self, raw, expected):
        assert normalize_key_name(raw) == expected

    def test_parse_marker_rejects_plain_words(self):
        assert parse_marker("Nope") is None


class TestCapsMode:
    def test_as_is_unchanged(self):
        assert apply_caps_mode("Hello World", CapsMode.AS_IS) == "Hello World"

    def test_uppercase(self):
        assert apply_caps_mode("Hello", CapsMode.UPPERCASE) == "HELLO"

    def test_lowercase(self):
        assert apply_caps_mode("HeLLo", CapsMode.LOWERCASE) == "hello"

    def test_markers_survive_case_changes(self):
        assert tokenize(apply_caps_mode("a{Enter}{Ctrl+s}{Sleep 10}", CapsMode.UPPERCASE)) == [
            "A", SpecialKey("enter"), KeyCombo(("ctrl",), "s"), Pause(0.01)
        ]

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
