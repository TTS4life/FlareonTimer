import numpy
import pytest

import src.audio

from src.audio import beep, channels, create_sequence_beeps, play_sequence_beeps, samplerate


def samples_for(interval):
    return int(interval / 1_000 * samplerate)


def slice_at(buffer, start, length):
    return buffer[start:start + length]


class TestStream:
    def test_opened_from_the_beep_file(self, stream):
        assert stream.kwargs["samplerate"] == samplerate
        assert stream.kwargs["channels"]   == channels
        assert stream.kwargs["dtype"]      == "float32"

    def test_started_at_import(self, stream):
        assert stream.started is True


class TestCreateSequenceBeeps:
    @pytest.mark.parametrize("number_beeps, interval", [(5, 250), (1, 250), (2, 1000), (3, 500)])
    def test_length(self, number_beeps, interval):
        buffer = create_sequence_beeps(number_beeps, interval)

        assert len(buffer) == samples_for(interval) * (number_beeps - 1) + len(beep)

    def test_single_beep_is_just_the_sample(self):
        buffer = create_sequence_beeps(1, 250)

        assert len(buffer) == len(beep)
        assert numpy.allclose(buffer, beep)

    def test_dtype_is_float32(self):
        assert create_sequence_beeps(5, 250).dtype == numpy.float32

    def test_beeps_land_on_the_interval(self):
        """With a gap wider than the sample, each beep is an untouched copy."""
        number_beeps = 4
        interval     = 1_000

        buffer  = create_sequence_beeps(number_beeps, interval)
        samples = samples_for(interval)

        assert samples > len(beep), "interval must exceed the sample for this test to mean anything"

        for i in range(number_beeps):
            assert numpy.allclose(slice_at(buffer, i * samples, len(beep)), beep)

    def test_gaps_between_beeps_are_silent(self):
        interval = 1_000
        buffer   = create_sequence_beeps(2, interval)
        samples  = samples_for(interval)

        assert numpy.allclose(slice_at(buffer, len(beep), samples - len(beep)), 0.0)

    def test_overlapping_beeps_sum(self):
        """A short interval makes copies overlap, and they add rather than
        overwrite - the buffer is built with `+=`."""
        interval = max(1, int(len(beep) / samplerate * 1_000 / 4))
        samples  = samples_for(interval)
        buffer   = create_sequence_beeps(4, interval)

        assert samples < len(beep), "interval must be under the sample length here"

        # the first sample of copy two lands on top of copy one
        assert numpy.allclose(buffer[samples], beep[samples] + beep[0])
        assert not numpy.allclose(slice_at(buffer, samples, len(beep)), beep), "no overlap happened"

    def test_shape_matches_the_channel_count(self):
        buffer = create_sequence_beeps(3, 250)

        if channels > 1: assert buffer.shape[1] == channels
        else:            assert buffer.ndim == 1


class TestPlaySequenceBeeps:
    def test_writes_to_the_stream(self, stream):
        buffer = create_sequence_beeps(5, 250)

        play_sequence_beeps(buffer, volume = 1.0)

        assert len(stream.writes) == 1
        assert numpy.allclose(stream.writes[0], buffer)

    def test_scales_by_volume(self, stream):
        buffer = create_sequence_beeps(5, 250)

        play_sequence_beeps(buffer, volume = 0.25)

        assert numpy.allclose(stream.writes[0], buffer * 0.25)

    def test_silent_at_zero_volume(self, stream):
        play_sequence_beeps(create_sequence_beeps(5, 250), volume = 0.0)

        assert numpy.allclose(stream.writes[0], 0.0)

    def test_volume_defaults_to_the_config_value(self, stream):
        from src.config import config

        buffer = create_sequence_beeps(2, 250)

        play_sequence_beeps(buffer)

        assert numpy.allclose(stream.writes[0], buffer * config["beep"]["volume"])

    def test_each_call_writes_once(self, stream):
        buffer = create_sequence_beeps(2, 250)

        play_sequence_beeps(buffer)
        play_sequence_beeps(buffer)
        play_sequence_beeps(buffer)

        assert len(stream.writes) == 3
