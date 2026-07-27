"""Validation of the shipped assets/json files.

The README tells users to hand-edit timers.json and config.json, so these guard
the shapes that src/main.py assumes at runtime.
"""

import pathlib

import pytest

from src.config import PATH_FILE, config, timers

KEYBINDS = [
    "start_restart",
    "next",
    "previous",
    "reset",
    "terminate",
    "variable_frame",
    "add",
    "subtract",
    "add_all",
    "subtract_all",
]

FIELDS = ["offsets", "variable_frame_offset", "interval", "number_beeps"]

NAMES = list(timers)


def test_at_least_one_timer():
    assert NAMES


class TestTimers:
    @pytest.mark.parametrize("name", NAMES)
    def test_has_every_field(self, name):
        assert set(FIELDS) <= set(timers[name])

    @pytest.mark.parametrize("name", NAMES)
    def test_offsets_are_a_non_empty_number_list(self, name):
        offsets = timers[name]["offsets"]

        assert isinstance(offsets, list)
        assert offsets, f"{name} has no offsets, so main() would raise on offsets_beeps[-1]"
        assert all(isinstance(offset, (int, float)) for offset in offsets)

    @pytest.mark.parametrize("name", NAMES)
    def test_offsets_are_strictly_ascending(self, name):
        offsets = timers[name]["offsets"]

        assert offsets == sorted(offsets)
        assert len(set(offsets)) == len(offsets), f"{name} repeats an offset"

    @pytest.mark.parametrize("name", NAMES)
    def test_interval_is_positive(self, name):
        assert timers[name]["interval"] > 0

    @pytest.mark.parametrize("name", NAMES)
    def test_number_beeps_is_a_positive_int(self, name):
        number_beeps = timers[name]["number_beeps"]

        assert isinstance(number_beeps, int)
        assert number_beeps >= 1

    @pytest.mark.parametrize("name", NAMES)
    def test_variable_frame_offset_is_a_number(self, name):
        assert isinstance(timers[name]["variable_frame_offset"], (int, float))

    @pytest.mark.parametrize("name", NAMES)
    def test_lead_in_fits_before_the_first_offset(self, name):
        """The first beep of a sequence must land after the timer starts."""
        configuration = timers[name]
        lead_in       = configuration["interval"] * (configuration["number_beeps"] - 1)

        assert configuration["offsets"][0] > lead_in, (
            f"{name} starts its first beep sequence at "
            f"{configuration['offsets'][0] - lead_in} ms, before the timer begins"
        )

    @pytest.mark.parametrize("name", NAMES)
    def test_sequences_do_not_overlap(self, name):
        """play_sequence_beeps blocks for the whole sequence, so offsets closer
        together than the sequence is long would fire late."""
        configuration = timers[name]
        offsets       = configuration["offsets"]
        lead_in       = configuration["interval"] * (configuration["number_beeps"] - 1)

        gaps = [(after, before, after - before) for before, after in zip(offsets, offsets[1:])]
        tight = [gap for gap in gaps if gap[2] <= lead_in]

        assert not tight, f"{name} has offsets closer than the {lead_in} ms sequence: {tight}"


class TestConfig:
    def test_fps_is_positive(self):
        assert config["fps"] > 0

    def test_beep_file_exists(self):
        path = PATH_FILE / "assets" / "sounds" / config["beep"]["name"]

        assert path.is_file()

    def test_volume_is_in_range(self):
        assert 0.0 <= config["beep"]["volume"] <= 1.0

    def test_print_target_beep_is_a_bool(self):
        assert isinstance(config["print_target_beep"], bool)

    @pytest.mark.parametrize("name", KEYBINDS)
    def test_keybind_is_present_and_non_empty(self, name):
        assert isinstance(config["keybinds"][name], str)
        assert config["keybinds"][name]

    def test_keybinds_are_distinct(self):
        """A duplicate bind would make the first matching branch win silently."""
        values = [config["keybinds"][name] for name in KEYBINDS]

        assert len(set(values)) == len(values), f"duplicate keybind in {values}"
