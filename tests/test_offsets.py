import json

import pytest

from src.config  import PATH_TIMERS, timers
from src.offsets import compact, duplicates, lead_in, parse, parse_all, render, save, warnings


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


class TestParse:
    @pytest.mark.parametrize("text, expected", [
        ("11289",    11289),
        ("  11289 ", 11289),
        ("11289.5",  11289.5),
        ("1e3",      1000),
    ])
    def test_accepts_numbers(self, text, expected):
        assert parse(text) == expected

    @pytest.mark.parametrize("text", ["", "   "])
    def test_rejects_empty(self, text):
        with pytest.raises(ValueError, match = "empty"): parse(text)

    @pytest.mark.parametrize("text", ["abc", "12a", "1,5", "--3"])
    def test_rejects_non_numbers(self, text):
        with pytest.raises(ValueError, match = "not a number"): parse(text)

    @pytest.mark.parametrize("text", ["0", "-1", "-11289"])
    def test_rejects_zero_and_negative(self, text):
        with pytest.raises(ValueError, match = "above zero"): parse(text)

    @pytest.mark.parametrize("text", ["inf", "-inf", "nan"])
    def test_rejects_non_finite(self, text):
        with pytest.raises(ValueError): parse(text)


class TestParseAll:
    def test_collects_values(self):
        offsets, errors = parse_all(["100", "200", "300"])

        assert offsets == [100, 200, 300]
        assert errors  == []

    def test_labels_errors_by_row(self):
        offsets, errors = parse_all(["100", "oops", "300", ""])

        assert offsets == [100, 300]
        assert len(errors) == 2
        assert errors[0].startswith("Offset 2 ")
        assert errors[1].startswith("Offset 4 ")

    def test_empty_input(self):
        assert parse_all([]) == ([], [])


class TestDuplicates:
    def test_finds_repeats(self):
        assert duplicates([100, 200, 100, 300, 200]) == [100, 200]

    def test_reports_each_repeat_once(self):
        assert duplicates([100, 100, 100]) == [100]

    def test_none(self):
        assert duplicates([100, 200, 300]) == []


class TestWarnings:
    def test_clean_configuration_is_silent(self):
        assert warnings([11289, 19895, 25018], 250, 5) == []

    def test_flags_a_lead_in_before_the_start(self):
        messages = warnings([500], 250, 5)

        assert len(messages) == 1
        assert "before the timer begins" in messages[0]

    def test_flags_offsets_closer_than_the_sequence(self):
        messages = warnings([5000, 5500], 250, 5)

        assert len(messages) == 1
        assert "closer together" in messages[0]

    def test_checks_against_sorted_order(self):
        assert warnings([25018, 11289, 19895], 250, 5) == []

    def test_single_beep_has_no_lead_in(self):
        assert warnings([100, 200], 250, 1) == []

    def test_empty(self):
        assert warnings([], 250, 5) == []


class TestLeadIn:
    @pytest.mark.parametrize("interval, number_beeps, expected", [
        (250, 5, 1000),
        (250, 1, 0),
        (100, 3, 200),
    ])
    def test_lead_in(self, interval, number_beeps, expected):
        assert lead_in(interval, number_beeps) == expected


class TestRender:
    def test_reproduces_the_shipped_file_byte_for_byte(self):
        """Guards the author's formatting: aligned keys, inline offsets, CRLF,
        no trailing newline."""
        with open(PATH_TIMERS, newline = "") as file_timers: original = file_timers.read()

        assert render(timers) == original

    def test_round_trips_through_json(self):
        assert json.loads(render(timers)) == timers

    def test_offsets_stay_inline(self):
        rendered = render({"A": {"offsets": [100, 200], "interval": 250, "number_beeps": 5}})

        assert '"offsets":      [100, 200],' in rendered

    def test_keys_are_aligned(self):
        rendered = render({"A": {"offsets": [100], "variable_frame_offset": -7}})
        lines    = [line for line in rendered.split("\r\n") if ":" in line and "A" not in line]

        columns = [len(line) - len(line.split(":", 1)[1].lstrip()) for line in lines]

        assert len(set(columns)) == 1, f"values start at differing columns: {columns}"

    def test_writes_integral_offsets_without_a_decimal(self):
        rendered = render({"A": {"offsets": [100.0, 200.5]}})

        assert "[100, 200.5]" in rendered

    def test_preserves_timer_order(self):
        rendered = render({"B": {"offsets": [1]}, "A": {"offsets": [2]}})

        assert rendered.index('"B"') < rendered.index('"A"')

    def test_empty_offsets(self):
        assert '"offsets": []' in render({"A": {"offsets": []}})


class TestSave:
    def test_writes_a_file_that_reloads_identically(self, tmp_path):
        path = tmp_path / "timers.json"

        save(timers, path)

        with open(path) as file_timers: assert json.load(file_timers) == timers

    def test_uses_crlf_without_a_trailing_newline(self, tmp_path):
        path = tmp_path / "timers.json"

        save(timers, path)

        data = path.read_bytes()

        assert b"\r\n" in data
        assert not data.endswith(b"\n")

    def test_does_not_double_up_line_endings(self, tmp_path):
        path = tmp_path / "timers.json"

        save(timers, path)

        assert b"\r\r\n" not in path.read_bytes()
