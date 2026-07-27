import pytest

from src.config   import config
from src.settings import ACTIONS, FALLBACKS, binding, conflict, describe, usable


class TestDescribe:
    @pytest.mark.parametrize("key, expected", [
        ("\r",   "Enter"),
        ("\n",   "Enter"),
        ("\x1b", "Esc"),
        (" ",    "Space"),
        ("\t",   "Tab"),
        ("n",    "N"),
        ("p",    "P"),
        ("+",    "+"),
        ("_",    "_"),
    ])
    def test_readable_names(self, key, expected):
        assert describe(key) == expected

    def test_letters_are_upper_cased(self):
        assert describe("v") == "V"

    def test_unknown_control_characters_fall_back_to_repr(self):
        assert describe("\x01") == repr("\x01")


class TestUsable:
    @pytest.mark.parametrize("key", ["n", "+", "\r", "\x1b", " "])
    def test_accepts_bindable_keys(self, key):
        assert usable(key) is True

    @pytest.mark.parametrize("key", ["", "\x01", "ab"])
    def test_rejects_unbindable_keys(self, key):
        assert usable(key) is False

    def test_rejects_the_empty_char_of_a_modifier(self):
        """Shift and the function keys arrive with no character."""
        assert usable("") is False


class TestBinding:
    def test_reads_a_configured_bind(self):
        assert binding({"next": "n"}, "next") == "n"

    def test_falls_back_when_missing(self):
        assert binding({}, "previous") == FALLBACKS["previous"]

    def test_missing_and_unknown_gives_empty(self):
        assert binding({}, "nonsense") == ""


class TestConflict:
    def test_finds_the_action_already_using_a_key(self):
        keybinds = {"next": "n", "reset": "r"}

        assert conflict(keybinds, "previous", "r") == "reset"

    def test_ignores_the_action_being_rebound(self):
        keybinds = {"next": "n"}

        assert conflict(keybinds, "next", "n") is None

    def test_none_when_free(self):
        keybinds = {"next": "n", "reset": "r"}

        assert conflict(keybinds, "previous", "p") is None


class TestActions:
    def test_exposes_every_window_bind(self):
        assert [action for action, _ in ACTIONS] == [
            "start_restart",
            "previous",
            "next",
            "add",
            "subtract",
            "add_all",
            "subtract_all",
            "variable_frame",
        ]

    def test_every_action_has_a_label(self):
        assert all(label for _, label in ACTIONS)
        assert len({label for _, label in ACTIONS}) == len(ACTIONS), "labels must be distinct"

    def test_every_action_resolves_against_the_shipped_config(self):
        for action, _ in ACTIONS:
            assert binding(config["keybinds"], action), f"{action} has no bind"
