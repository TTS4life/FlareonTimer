"""Runs one timer on a worker thread, so the window stays responsive.

Timing notes. The console engine in src/main.py busy-spins for the whole run,
which is fine when it owns the process. Here Tk is running too, and a pure spin
would hold the GIL against the UI thread and add jitter in both directions. So
this waits in two stages: sleep while the next beep is far away (releasing the
GIL to Tk), then busy-spin the last SPIN_MS for the same sub-millisecond
accuracy at the moment that matters. The interpreter's thread switch interval
is tightened for the duration of a run so the UI thread cannot hold the GIL for
a full 5 ms slice while the spin is waiting.
"""

import queue
import sys
import threading
import time

from src.constants import MS_TO_NS
from src.timer     import calculate_first_offset_beep

SPIN_MS         = 15      # busy-wait window before each beep
SLEEP_S         = 0.001   # granularity while far from the next beep
SWITCH_INTERVAL = 0.001   # GIL slice while a run is in progress


class Runner:
    def __init__(self):
        self.events   = queue.Queue()
        self.lock     = threading.Lock()
        self.stopping = threading.Event()
        self.thread   = None

        self.name     = None
        self.start_ns = None
        self.pending  = []

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def snapshot(self):
        with self.lock:
            return {"name": self.name, "start_ns": self.start_ns, "pending": list(self.pending)}

    def start(self, name, configuration):
        if self.running(): return False

        self.stopping.clear()

        with self.lock:
            self.name     = name
            self.start_ns = None
            self.pending  = []

        self.thread = threading.Thread(target = self.run, args = (name, dict(configuration)), daemon = True)
        self.thread.start()

        return True

    def stop(self):
        self.stopping.set()

    def join(self, timeout = None):
        if self.thread is not None: self.thread.join(timeout)

    def emit(self, kind, **payload):
        payload["kind"] = kind
        self.events.put(payload)

    def wait_until(self, start, target_ns):
        """Returns the elapsed ns once the target passes, or None if stopped."""
        while True:
            if self.stopping.is_set(): return None

            elapsed   = time.perf_counter_ns() - start
            remaining = target_ns - elapsed

            if remaining <= 0:                 return elapsed
            if remaining > SPIN_MS * MS_TO_NS: time.sleep(SLEEP_S)

    def run(self, name, configuration):
        # imported here so the sound device is only claimed once a run begins
        from src.audio import create_sequence_beeps, play_sequence_beeps

        offsets      = configuration["offsets"]
        interval     = configuration["interval"]
        number_beeps = configuration["number_beeps"]

        sequence = create_sequence_beeps(number_beeps, interval)
        pending  = [(calculate_first_offset_beep(offset, interval, number_beeps), offset) for offset in offsets]

        switch_interval = sys.getswitchinterval()
        sys.setswitchinterval(SWITCH_INTERVAL)

        try:
            start = time.perf_counter_ns()

            with self.lock:
                self.start_ns = start
                self.pending  = list(pending)

            self.emit("started", name = name)

            delays = []

            while pending:
                beep_ms, target_ms = pending[0]

                elapsed = self.wait_until(start, beep_ms * MS_TO_NS)

                if elapsed is None:
                    self.emit("stopped", name = name)
                    return

                play_sequence_beeps(sequence)

                # measured before the blocking write, matching src/main.py
                target = elapsed / MS_TO_NS + interval * (number_beeps - 1)
                delay  = target - target_ms

                delays.append(delay)
                pending.pop(0)

                with self.lock: self.pending = list(pending)

                self.emit(
                    "beep",
                    name      = name,
                    target    = target,
                    planned   = target_ms,
                    delay     = delay,
                    average   = sum(delays) / len(delays),
                    remaining = len(pending),
                )

            self.emit("finished", name = name)

        finally:
            sys.setswitchinterval(switch_interval)

            with self.lock:
                self.start_ns = None
                self.pending  = []
