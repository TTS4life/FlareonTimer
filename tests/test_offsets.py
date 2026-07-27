import pytest

from src.offsets import duplicates, lead_in, number, parse, parse_all, parse_beeps, parse_interval, warnings


class TestNumber:
    @pytest.mark.parametrize("text, expected", [
        ("11289",    11289),
        ("  11289 ", 11289),
        ("11289.5",  11289.5),
        ("1e3",      1000),
        ("-5",       -5),
        ("0",        0),
    ])
    def test_accepts_finite_numbers(self, text, expected):
        assert number(text) == expected

    @pytest.mark.parametrize("text", ["", "   "])
    def test_rejects_empty(self, text):
        with pytest.raises(ValueError, match = "empty"): number(text)

    @pytest.mark.parametrize("text", ["abc", "12a", "1,5", "--3"])
    def test_rejects_non_numbers(self, text):
        with pytest.raises(ValueError, match = "not a number"): number(text)

    @pytest.mark.parametrize("text", ["inf", "-inf", "nan", "Infinity"])
    def test_rejects_non_finite(self, text):
        """json.dumps writes these as Infinity/NaN, which is not valid JSON."""
        with pytest.raises(ValueError, match = "not a finite number"): number(text)


class TestParse:
    @pytest.mark.parametrize("text, expected", [("11289", 11289), ("11289.5", 11289.5), ("1e3", 1000)])
    def test_accepts_offsets(self, text, expected):
        assert parse(text) == expected

    @pytest.mark.parametrize("text", ["0", "-1", "-11289"])
    def test_rejects_zero_and_negative(self, text):
        with pytest.raises(ValueError, match = "above zero"): parse(text)

    @pytest.mark.parametrize("text", ["inf", "nan"])
    def test_rejects_non_finite(self, text):
        with pytest.raises(ValueError): parse(text)


class TestParseInterval:
    @pytest.mark.parametrize("text, expected", [("250", 250), (" 250 ", 250), ("250.0", 250), ("12.5", 12.5)])
    def test_accepts_and_compacts(self, text, expected):
        result = parse_interval(text)

        assert result == expected
        assert isinstance(result, type(expected))

    @pytest.mark.parametrize("text", ["0", "-250"])
    def test_rejects_zero_and_negative(self, text):
        with pytest.raises(ValueError, match = "above zero"): parse_interval(text)

    @pytest.mark.parametrize("text", ["inf", "nan"])
    def test_rejects_non_finite(self, text):
        """Without this these reach the file as Infinity / NaN."""
        with pytest.raises(ValueError, match = "not a finite number"): parse_interval(text)

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match = "empty"): parse_interval("")


class TestParseBeeps:
    @pytest.mark.parametrize("text, expected", [("5", 5), (" 5 ", 5), ("5.0", 5), ("1", 1)])
    def test_accepts_whole_numbers(self, text, expected):
        result = parse_beeps(text)

        assert result == expected
        assert isinstance(result, int)

    @pytest.mark.parametrize("text", ["2.5", "0.5"])
    def test_rejects_fractions(self, text):
        with pytest.raises(ValueError, match = "whole number"): parse_beeps(text)

    @pytest.mark.parametrize("text", ["0", "-1"])
    def test_rejects_below_one(self, text):
        with pytest.raises(ValueError, match = "at least 1"): parse_beeps(text)

    @pytest.mark.parametrize("text", ["inf", "nan"])
    def test_rejects_non_finite(self, text):
        with pytest.raises(ValueError, match = "not a finite number"): parse_beeps(text)


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


class TestLeadIn:
    @pytest.mark.parametrize("interval, number_beeps, expected", [(250, 5, 1000), (250, 1, 0), (100, 3, 200)])
    def test_lead_in(self, interval, number_beeps, expected):
        assert lead_in(interval, number_beeps) == expected


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
