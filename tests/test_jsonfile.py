"""Tests for the shared asset-file renderer.

Both shipped files are golden: the renderer must reproduce them byte for byte,
so that saving one edit is a one-line diff rather than a reformat.
"""

import json

import pytest

from src.config   import PATH_CONFIG, PATH_TIMERS, config, timers
from src.jsonfile import compact, render, save

GOLDEN = [("timers.json", PATH_TIMERS, timers), ("config.json", PATH_CONFIG, config)]


class TestCompact:
    @pytest.mark.parametrize("value, expected", [
        (11289.0, 11289),
        (11289,   11289),
        (-4.75,   -4.75),
        (0.0,     0),
        (16.7428, 16.7428),
    ])
    def test_whole_numbers_become_ints(self, value, expected):
        result = compact(value)

        assert result == expected
        assert isinstance(result, type(expected))


class TestRender:
    @pytest.mark.parametrize("name, path, data", GOLDEN, ids = [row[0] for row in GOLDEN])
    def test_reproduces_the_shipped_file_byte_for_byte(self, name, path, data):
        with open(path, newline = "") as file_data: original = file_data.read()

        assert render(data) == original

    @pytest.mark.parametrize("name, path, data", GOLDEN, ids = [row[0] for row in GOLDEN])
    def test_round_trips_through_json(self, name, path, data):
        assert json.loads(render(data)) == data

    def test_nested_objects_align_their_keys(self):
        rendered = render({"beep": {"name": "click.wav", "volume": 1.0}})
        lines    = [line for line in rendered.split("\r\n") if line.startswith(" " * 8)]

        columns = [len(line) - len(line.split(":", 1)[1].lstrip()) for line in lines]

        assert len(set(columns)) == 1, f"values start at differing columns: {columns}"

    def test_top_level_keys_are_not_padded(self):
        rendered = render({"fps": 59.7, "print_target_beep": True})

        assert '    "fps": 59.7,' in rendered
        assert '    "print_target_beep": true' in rendered

    def test_lists_stay_inline(self):
        rendered = render({"A": {"offsets": [100, 200], "interval": 250}})

        assert '"offsets":  [100, 200],' in rendered

    def test_integral_list_values_lose_their_decimal(self):
        assert "[100, 200.5]" in render({"A": {"offsets": [100.0, 200.5]}})

    def test_escapes_control_characters(self):
        rendered = render({"keybinds": {"start_restart": "\r", "terminate": "\x1b"}})

        assert '"\\r"' in rendered
        assert '"\\u001b"' in rendered

    def test_preserves_key_order(self):
        assert render({"b": 1, "a": 2}).index('"b"') < render({"b": 1, "a": 2}).index('"a"')

    def test_empty_list(self):
        assert '"offsets": []' in render({"A": {"offsets": []}})

    def test_empty_object(self):
        assert render({"A": {}}) == '{\r\n    "A": {\r\n    }\r\n}'


class TestSave:
    @pytest.mark.parametrize("name, path, data", GOLDEN, ids = [row[0] for row in GOLDEN])
    def test_writes_a_file_that_reloads_identically(self, name, path, data, tmp_path):
        target = tmp_path / name

        save(data, target)

        with open(target) as file_data: assert json.load(file_data) == data

    @pytest.mark.parametrize("name, path, data", GOLDEN, ids = [row[0] for row in GOLDEN])
    def test_uses_crlf_without_a_trailing_newline(self, name, path, data, tmp_path):
        target = tmp_path / name

        save(data, target)

        written = target.read_bytes()

        assert b"\r\n" in written
        assert not written.endswith(b"\n")

    @pytest.mark.parametrize("name, path, data", GOLDEN, ids = [row[0] for row in GOLDEN])
    def test_does_not_double_up_line_endings(self, name, path, data, tmp_path):
        target = tmp_path / name

        save(data, target)

        assert b"\r\r\n" not in target.read_bytes()
