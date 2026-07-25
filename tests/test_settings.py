import json

import pytest

from src.config   import PATH_CONFIG, config
from src.settings import ACTIONS, FALLBACKS, binding, conflict, describe, render, save, usable


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
    def test_exposes_the_three_window_binds(self):
        assert [action for action, _ in ACTIONS] == ["start_restart", "previous", "next"]

    def test_labels_are_set(self):
        assert [label for _, label in ACTIONS] == ["Start timer", "Previous timer", "Next timer"]

    def test_every_action_resolves_against_the_shipped_config(self):
        for action, _ in ACTIONS:
            assert binding(config["keybinds"], action), f"{action} has no bind"


class TestRender:
    def test_reproduces_the_shipped_file_byte_for_byte(self):
        with open(PATH_CONFIG, newline = "") as file_config: original = file_config.read()

        assert render(config) == original

    def test_round_trips_through_json(self):
        assert json.loads(render(config)) == config

    def test_nested_objects_align_their_keys(self):
        rendered = render({"beep": {"name": "click.wav", "volume": 1.0}})
        lines    = [line for line in rendered.split("\r\n") if line.startswith(" " * 8)]

        columns = [len(line) - len(line.split(":", 1)[1].lstrip()) for line in lines]

        assert len(set(columns)) == 1, f"values start at differing columns: {columns}"

    def test_top_level_keys_are_not_padded(self):
        rendered = render({"fps": 59.7, "print_target_beep": True})

        assert '    "fps": 59.7,' in rendered
        assert '    "print_target_beep": true' in rendered

    def test_escapes_control_characters_the_same_way(self):
        rendered = render({"keybinds": {"start_restart": "\r", "terminate": "\x1b"}})

        assert '"\\r"' in rendered
        assert '"\\u001b"' in rendered

    def test_preserves_key_order(self):
        rendered = render({"b": 1, "a": 2})

        assert rendered.index('"b"') < rendered.index('"a"')


class TestSave:
    def test_writes_a_file_that_reloads_identically(self, tmp_path):
        path = tmp_path / "config.json"

        save(config, path)

        with open(path) as file_config: assert json.load(file_config) == config

    def test_uses_crlf_without_a_trailing_newline(self, tmp_path):
        path = tmp_path / "config.json"

        save(config, path)

        data = path.read_bytes()

        assert b"\r\n" in data
        assert not data.endswith(b"\n")

    def test_does_not_double_up_line_endings(self, tmp_path):
        path = tmp_path / "config.json"

        save(config, path)

        assert b"\r\r\n" not in path.read_bytes()
