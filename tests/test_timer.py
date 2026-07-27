import pytest

from src.constants import BUFFER_MS, MS_TO_NS
from src.timer     import calculate_first_offset_beep, get_offset_boundary, is_safe, shift, shift_all


class TestCalculateFirstOffsetBeep:
    @pytest.mark.parametrize("offset, interval, number_beeps, expected", [
        (11289, 250, 5, 10289),   # the shipped Mudkip configuration
        (1000,  250, 1, 1000),    # a single beep fires exactly on the target
        (1000,  250, 2, 750),
        (1000,  100, 5, 600),
        (0,     250, 5, -1000),   # offsets below the lead-in go negative
    ])
    def test_lead_in(self, offset, interval, number_beeps, expected):
        assert calculate_first_offset_beep(offset, interval, number_beeps) == expected

    @pytest.mark.parametrize("offset", [7241, 11289, 56867, 115755])
    def test_last_beep_lands_on_target(self, offset):
        """The point of the lead-in: beep number `number_beeps` hits the offset."""
        interval     = 250
        number_beeps = 5

        first = calculate_first_offset_beep(offset, interval, number_beeps)

        assert first + interval * (number_beeps - 1) == offset


class TestGetOffsetBoundary:
    def test_uses_first_pending_beep(self):
        offsets_beeps = [(10289, 11289), (18895, 19895)]

        assert get_offset_boundary(offsets_beeps, 99999, 250, 5) == 10289

    def test_falls_back_when_no_offsets_remain(self):
        """With nothing pending the boundary is derived from the finish time."""
        assert get_offset_boundary([], 5000, 250, 5) == 4000

    def test_ignores_fallback_while_offsets_remain(self):
        offsets_beeps = [(300, 1300)]

        assert get_offset_boundary(offsets_beeps, 5000, 250, 5) == 300


class TestIsSafe:
    def test_elapsed_is_nanoseconds_and_boundary_is_milliseconds(self):
        """is_safe mixes units deliberately; guard against a regression."""
        assert is_safe(100 * MS_TO_NS, 1000) is True
        assert is_safe(100, 1000) is True

    @pytest.mark.parametrize("elapsed_ns, expected", [
        (749_999_999, True),   # one nanosecond inside the buffer
        (750_000_000, False),  # exactly on it: the comparison is strict
        (750_000_001, False),
    ])
    def test_boundary_is_exclusive(self, elapsed_ns, expected):
        assert is_safe(elapsed_ns, 1000) is expected

    def test_buffer_is_subtracted(self):
        boundary = 1000
        cutoff   = (boundary - BUFFER_MS) * MS_TO_NS

        assert is_safe(cutoff - 1, boundary) is True
        assert is_safe(cutoff,     boundary) is False

    def test_never_safe_when_boundary_is_inside_the_buffer(self):
        """An offset closer than BUFFER_MS can never be edited, even at t=0."""
        assert is_safe(0, BUFFER_MS)     is False
        assert is_safe(0, BUFFER_MS - 1) is False
        assert is_safe(0, BUFFER_MS + 1) is True


class TestShift:
    def test_moves_both_halves(self):
        assert shift((10289, 11289), 16.7428) == pytest.approx((10305.7428, 11305.7428))

    def test_negative_delta(self):
        assert shift((10289, 11289), -16.7428) == pytest.approx((10272.2572, 11272.2572))

    def test_preserves_the_lead_in_gap(self):
        """Shifting must not change the beep-to-target distance."""
        offsets = (10289, 11289)
        gap     = offsets[1] - offsets[0]

        shifted = shift(offsets, 16.7428)

        assert shifted[1] - shifted[0] == pytest.approx(gap)

    def test_zero_delta_is_identity(self):
        assert shift((10289, 11289), 0) == (10289, 11289)


class TestShiftAll:
    def test_moves_every_entry(self):
        offsets_beeps = [(10289, 11289), (18895, 19895), (24018, 25018)]

        shifted = shift_all(offsets_beeps, 10)

        assert shifted == [(10299, 11299), (18905, 19905), (24028, 25028)]

    def test_preserves_length_and_order(self):
        offsets_beeps = [(100, 1100), (200, 1200), (300, 1300)]

        shifted = shift_all(offsets_beeps, -5)

        assert len(shifted) == len(offsets_beeps)
        assert shifted == sorted(shifted)

    def test_empty(self):
        assert shift_all([], 10) == []

    def test_leaves_the_original_untouched(self):
        offsets_beeps = [(10289, 11289)]

        shift_all(offsets_beeps, 10)

        assert offsets_beeps == [(10289, 11289)]
