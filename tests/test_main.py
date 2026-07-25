"""Integration tests for the engine loop.

main() talks to the outside world only through queue_inputs and queue_prints,
so the tests drive it exactly the way the keyboard listener would: push a key,
assert on what it prints back.
"""

import queue
import threading
import time

import pytest

import src.main

from src.config import config
from src.io     import queue_inputs, queue_prints
from src.main   import main

KEYS = config["keybinds"]


def timer(offsets, interval = 250, number_beeps = 5, variable_frame_offset = 0):
    return {
        "offsets":               offsets,
        "variable_frame_offset": variable_frame_offset,
        "interval":              interval,
        "number_beeps":          number_beeps,
    }


class Harness:
    def __init__(self):
        self.messages = []
        self.thread   = threading.Thread(target = main, daemon = True)

    def send(self, *keys):
        for key in keys: queue_inputs.put(key)

    def wait_for(self, needle, timeout = 10.0):
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            try: message = queue_prints.get(timeout = 0.05)
            except queue.Empty: continue

            if message is None: continue

            self.messages.append(message)
            if needle in message: return message

        raise AssertionError(f"timed out waiting for {needle!r}; saw {self.messages}")

    def stop(self, timeout = 10.0):
        self.send(KEYS["terminate"])
        self.thread.join(timeout)


@pytest.fixture
def engine(monkeypatch):
    harnesses = []

    def start(timers, finish_ms = 100):
        monkeypatch.setattr(src.main, "timers", timers)
        monkeypatch.setattr(src.main, "FINISH_MS", finish_ms)

        harness = Harness()
        harnesses.append(harness)
        harness.thread.start()

        return harness

    yield start

    for harness in harnesses:
        harness.stop()
        assert not harness.thread.is_alive(), "engine thread did not terminate; later tests would be corrupted"


class TestStartup:
    def test_announces_the_first_timer(self, engine):
        harness = engine({"A": timer([5000])})

        harness.wait_for("Offsets of A: [5000]")
        harness.wait_for("Press ENTER to start the timer...")

    def test_terminate_before_starting_exits(self, engine):
        harness = engine({"A": timer([5000])})

        harness.wait_for("Press ENTER")
        harness.send(KEYS["terminate"])
        harness.wait_for("Timer terminated...")

        harness.thread.join(timeout = 5.0)
        assert not harness.thread.is_alive()

    def test_start_acknowledges(self, engine):
        harness = engine({"A": timer([5000])})

        harness.wait_for("Press ENTER")
        harness.send(KEYS["start_restart"])
        harness.wait_for("Timer started...")


class TestNavigation:
    def test_next_advances(self, engine):
        harness = engine({"A": timer([5000]), "B": timer([6000])})

        harness.wait_for("Offsets of A")
        harness.send(KEYS["next"])
        harness.wait_for("Next timer...")
        harness.wait_for("Offsets of B")

    def test_reset_returns_to_the_first_timer(self, engine):
        harness = engine({"A": timer([5000]), "B": timer([6000])})

        harness.wait_for("Offsets of A")
        harness.send(KEYS["next"])
        harness.wait_for("Offsets of B")

        harness.send(KEYS["reset"])
        harness.wait_for("Timer reset...")
        harness.wait_for("Offsets of A")

    def test_terminate_during_a_run(self, engine):
        harness = engine({"A": timer([5000])})

        harness.wait_for("Press ENTER")
        harness.send(KEYS["start_restart"])
        harness.wait_for("Timer started...")

        harness.send(KEYS["terminate"])
        harness.wait_for("Timer terminated...")

    def test_restart_while_running(self, engine):
        harness = engine({"A": timer([5000])})

        harness.wait_for("Press ENTER")
        harness.send(KEYS["start_restart"])
        harness.wait_for("Timer started...")

        harness.send(KEYS["start_restart"])
        harness.wait_for("Timer restarted...")


class TestBeeps:
    def test_beep_fires_and_reports_the_target(self, engine, stream):
        # first beep at 1200 - 250 * 4 = 200 ms
        harness = engine({"A": timer([1200])})

        harness.wait_for("Press ENTER")
        harness.send(KEYS["start_restart"])

        message = harness.wait_for("Target Beep @")
        target  = float(message.split("@")[1])

        assert 1_150 <= target <= 1_500, f"target beep landed at {target} ms, expected ~1200"
        assert stream.writes, "no audio was written for the beep sequence"

    def test_delay_is_reported_every_ten_beeps(self, engine):
        # single-beep sequences fire exactly on the offset, so ten land in ~1 s
        offsets = [100 * i for i in range(1, 11)]
        harness = engine({"A": timer(offsets, number_beeps = 1)})

        harness.wait_for("Press ENTER")
        harness.send(KEYS["start_restart"])

        message = harness.wait_for("Delay:")
        delay   = float(message.split(":")[1])

        assert abs(delay) < 50, f"delay of {delay} ms is implausible for a stubbed stream"

    def test_one_write_per_offset(self, engine, stream):
        offsets = [100, 200, 300]
        harness = engine({"A": timer(offsets, number_beeps = 1)})

        harness.wait_for("Press ENTER")
        harness.send(KEYS["start_restart"])
        harness.wait_for("Offsets of A", timeout = 10.0)  # the run finished and looped back

        assert len(stream.writes) == len(offsets)


class TestShifting:
    def test_add_shifts_the_next_offset_by_one_frame(self, engine):
        harness = engine({"A": timer([3000])})

        harness.wait_for("Press ENTER")
        harness.send(KEYS["start_restart"], KEYS["add"])

        message = harness.wait_for("Offset 3000 >>>")

        assert message.split(">>>")[1].strip() == "3017"

    def test_subtract_shifts_the_other_way(self, engine):
        harness = engine({"A": timer([3000])})

        harness.wait_for("Press ENTER")
        harness.send(KEYS["start_restart"], KEYS["subtract"])

        message = harness.wait_for("Offset 3000 >>>")

        assert message.split(">>>")[1].strip() == "2983"

    def test_add_all_reports_the_delta(self, engine):
        harness = engine({"A": timer([3000, 5000])})

        harness.wait_for("Press ENTER")
        harness.send(KEYS["start_restart"], KEYS["add_all"])

        assert harness.wait_for("All Offsets >>>").endswith("+16.74")

    def test_subtract_all_reports_the_delta(self, engine):
        harness = engine({"A": timer([3000, 5000])})

        harness.wait_for("Press ENTER")
        harness.send(KEYS["start_restart"], KEYS["subtract_all"])

        assert harness.wait_for("All Offsets >>>").endswith("-16.74")

    def test_shift_is_rejected_inside_the_buffer(self, engine):
        # first beep at 1100 - 1000 = 100 ms, which is already inside BUFFER_MS
        harness = engine({"A": timer([1100])})

        harness.wait_for("Press ENTER")
        harness.send(KEYS["start_restart"], KEYS["add"])

        harness.wait_for("Didn't shift any offset!")


class TestVariableFrame:
    def test_appends_an_offset(self, engine, monkeypatch):
        # 300 frames -> ~5023 ms, far enough out to clear the buffer
        monkeypatch.setattr("builtins.input", lambda prompt = "": "300")

        harness = engine({"A": timer([5000])})

        harness.wait_for("Press ENTER")
        harness.send(KEYS["start_restart"], KEYS["variable_frame"])

        message = harness.wait_for("appended")

        assert "Variable Frame 300.0" in message
        assert "Offset 5023" in message

    def test_rejects_an_offset_inside_the_buffer(self, engine, monkeypatch):
        # 10 frames -> ~167 ms, whose lead-in is already in the past
        monkeypatch.setattr("builtins.input", lambda prompt = "": "10")

        harness = engine({"A": timer([5000])})

        harness.wait_for("Press ENTER")
        harness.send(KEYS["start_restart"], KEYS["variable_frame"])

        harness.wait_for("Didn't append any offset!")
