"""Tests for the single-timer runner.

conftest stubs sounddevice, so play_sequence_beeps returns immediately instead
of blocking for the length of the sequence. Timings here are therefore about
when the runner *decides* to fire, which is what the delay figure measures.
"""

import queue
import time

import pytest

from src.runner import SPIN_MS, Runner


def timer(offsets, interval = 250, number_beeps = 5):
    return {"offsets": offsets, "interval": interval, "number_beeps": number_beeps, "variable_frame_offset": 0}


@pytest.fixture
def runner():
    instance = Runner()

    yield instance

    instance.stop()
    instance.join(timeout = 5.0)


def collect(runner, kind, timeout = 10.0):
    """Waits for an event of `kind`, returning it. Ignores earlier events."""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try: event = runner.events.get(timeout = 0.05)
        except queue.Empty: continue

        if event["kind"] == kind: return event

    raise AssertionError(f"timed out waiting for {kind!r}")


def collect_all(runner, until, timeout = 10.0):
    events   = []
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try: event = runner.events.get(timeout = 0.05)
        except queue.Empty: continue

        events.append(event)
        if event["kind"] == until: return events

    raise AssertionError(f"timed out waiting for {until!r}; saw {[e['kind'] for e in events]}")


class TestLifecycle:
    def test_not_running_before_start(self, runner):
        assert runner.running() is False

    def test_start_reports_running(self, runner):
        runner.start("A", timer([2000]))

        assert runner.running() is True

    def test_emits_started_then_finished(self, runner):
        runner.start("A", timer([300], number_beeps = 1))

        kinds = [event["kind"] for event in collect_all(runner, "finished")]

        assert kinds == ["started", "beep", "finished"]

    def test_finishes_and_clears_state(self, runner):
        runner.start("A", timer([300], number_beeps = 1))
        collect(runner, "finished")
        runner.join(timeout = 2.0)

        assert runner.running() is False
        assert runner.snapshot()["start_ns"] is None

    def test_start_is_refused_while_running(self, runner):
        runner.start("A", timer([5000]))

        assert runner.start("B", timer([5000])) is False

    def test_stop_ends_the_run(self, runner):
        runner.start("A", timer([60_000]))
        collect(runner, "started")

        runner.stop()
        event = collect(runner, "stopped")

        assert event["name"] == "A"
        runner.join(timeout = 2.0)
        assert runner.running() is False

    def test_can_restart_after_stopping(self, runner):
        runner.start("A", timer([60_000]))
        collect(runner, "started")
        runner.stop()
        runner.join(timeout = 5.0)

        assert runner.start("B", timer([300], number_beeps = 1)) is True
        assert collect(runner, "finished")["name"] == "B"


class TestBeeps:
    def test_one_beep_event_per_offset(self, runner):
        runner.start("A", timer([200, 400, 600], number_beeps = 1))

        events = collect_all(runner, "finished")
        beeps  = [event for event in events if event["kind"] == "beep"]

        assert len(beeps) == 3

    def test_writes_audio_for_each_offset(self, runner, stream):
        runner.start("A", timer([200, 400], number_beeps = 1))
        collect(runner, "finished")

        assert len(stream.writes) == 2

    def test_reports_the_planned_target(self, runner):
        runner.start("A", timer([1200]))

        event = collect(runner, "beep")

        assert event["planned"] == 1200

    def test_counts_down_remaining(self, runner):
        runner.start("A", timer([200, 400, 600], number_beeps = 1))

        events = [event for event in collect_all(runner, "finished") if event["kind"] == "beep"]

        assert [event["remaining"] for event in events] == [2, 1, 0]

    def test_lead_in_is_applied(self, runner):
        """With 5 beeps at 250 ms the sequence starts 1000 ms before the target."""
        runner.start("A", timer([1200], interval = 250, number_beeps = 5))
        collect(runner, "started")

        pending = runner.snapshot()["pending"]

        assert pending[0] == (200, 1200)


class TestAccuracy:
    def test_beep_lands_close_to_the_target(self, runner):
        runner.start("A", timer([1200]))

        event = collect(runner, "beep")

        assert abs(event["delay"]) < 5, f"delay of {event['delay']:.2f} ms is too large"

    def test_delay_stays_small_across_several_beeps(self, runner):
        offsets = [200, 400, 600, 800, 1000]
        runner.start("A", timer(offsets, number_beeps = 1))

        events = [event for event in collect_all(runner, "finished") if event["kind"] == "beep"]
        worst  = max(abs(event["delay"]) for event in events)

        assert worst < 5, f"worst delay {worst:.2f} ms exceeds a quarter frame"

    def test_never_fires_early(self, runner):
        """A beep must never land before its offset."""
        offsets = [200, 400, 600, 800, 1000]
        runner.start("A", timer(offsets, number_beeps = 1))

        events = [event for event in collect_all(runner, "finished") if event["kind"] == "beep"]

        assert all(event["delay"] >= 0 for event in events), [event["delay"] for event in events]

    def test_average_is_the_running_mean(self, runner):
        offsets = [200, 400, 600]
        runner.start("A", timer(offsets, number_beeps = 1))

        events = [event for event in collect_all(runner, "finished") if event["kind"] == "beep"]
        delays = [event["delay"] for event in events]

        assert events[-1]["average"] == pytest.approx(sum(delays) / len(delays))


class TestSnapshot:
    def test_exposes_the_name_and_start(self, runner):
        runner.start("Mudkip", timer([5000]))
        collect(runner, "started")

        state = runner.snapshot()

        assert state["name"] == "Mudkip"
        assert state["start_ns"] is not None

    def test_pending_shrinks_as_beeps_fire(self, runner):
        runner.start("A", timer([200, 400, 600], number_beeps = 1))
        collect(runner, "started")

        assert len(runner.snapshot()["pending"]) == 3

        collect(runner, "beep")
        assert len(runner.snapshot()["pending"]) == 2

    def test_does_not_mutate_the_caller_configuration(self, runner):
        configuration = timer([200], number_beeps = 1)
        original      = dict(configuration)

        runner.start("A", configuration)
        collect(runner, "finished")

        assert configuration == original


class TestStopResponsiveness:
    def test_stop_returns_quickly_during_a_long_wait(self, runner):
        runner.start("A", timer([60_000]))
        collect(runner, "started")

        begin = time.monotonic()
        runner.stop()
        runner.join(timeout = 5.0)
        taken = time.monotonic() - begin

        assert not runner.running()
        assert taken < 1.0, f"stop took {taken:.2f}s"

    def test_spin_window_is_short_enough_to_stay_responsive(self):
        assert SPIN_MS <= 50
