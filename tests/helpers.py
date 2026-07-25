"""Helpers shared across the test modules."""

import queue
import time

def timer(offsets, interval = 250, number_beeps = 5, variable_frame_offset = 0):
    """A timer configuration in the shape timers.json uses."""
    return {
        "offsets":               list(offsets),
        "variable_frame_offset": variable_frame_offset,
        "interval":              interval,
        "number_beeps":          number_beeps,
    }


def wait_for(events, kind, timeout = 10.0):
    """Waits for a runner event of `kind`, ignoring the ones before it."""
    deadline = time.monotonic() + timeout
    seen     = []

    while time.monotonic() < deadline:
        try: event = events.get(timeout = 0.05)
        except queue.Empty: continue

        seen.append(event["kind"])

        if event["kind"] == kind: return event

    raise AssertionError(f"timed out waiting for {kind!r}; saw {seen}")


def collect_until(events, kind, timeout = 10.0):
    """Every event up to and including the first of `kind`."""
    deadline = time.monotonic() + timeout
    seen     = []

    while time.monotonic() < deadline:
        try: event = events.get(timeout = 0.05)
        except queue.Empty: continue

        seen.append(event)

        if event["kind"] == kind: return seen

    raise AssertionError(f"timed out waiting for {kind!r}; saw {[event['kind'] for event in seen]}")


def beeps_until_finished(events, timeout = 10.0):
    """The beep events of a run that is expected to finish on its own."""
    return [event for event in collect_until(events, "finished", timeout) if event["kind"] == "beep"]
