"""Runs one timer on a worker thread, so the window stays responsive.

Timing notes. The console engine in src/main.py busy-spins for the whole run,
which is fine when it owns the process. Here Tk is running too, and a pure spin
would hold the GIL against the UI thread and add jitter in both directions. So
this waits in two stages: sleep while the next beep is far away (releasing the
GIL to Tk), then busy-spin the last SPIN_MS for the same sub-millisecond
accuracy at the moment that matters. The interpreter's thread switch interval
is tightened for the duration of a run so the UI thread cannot hold the GIL for
a full 5 ms slice while the spin is waiting.

The shift and variable-frame operations are called from the Tk thread while
this thread is waiting, so `pending` is guarded by a lock. The wait loop avoids
taking that lock on every spin iteration by watching `revision`, a plain int
whose reads are atomic under the GIL.
"""

import queue
import sys
import threading
import time

from src.constants import FINISH_MS, FRAME_MS, MS_TO_NS
from src.timer     import calculate_first_offset_beep, get_offset_boundary, is_safe, shift_all
from src.timer     import shift as shift_offset

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
        self.revision = 0
        self.queued   = None

        self.interval              = 0
        self.number_beeps          = 0
        self.variable_frame_offset = 0
        self.finish_ms             = 0

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def snapshot(self):
        with self.lock:
            return {
                "name":     self.name,
                "start_ns": self.start_ns,
                "pending":  list(self.pending),
                "revision": self.revision,
            }

    def start(self, name, configuration):
        if self.running(): return False

        self.stopping.clear()

        with self.lock:
            self.name     = name
            self.start_ns = None
            self.pending  = []
            self.queued   = None

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

    # --- live adjustments, called from the UI thread -----------------------

    def shift_pending(self, delta, every):
        """Mirrors the +/-/*/_ branch of src/main.py, including its guard."""
        with self.lock:
            if self.start_ns is None: return False, "No timer is running."

            elapsed  = time.perf_counter_ns() - self.start_ns
            boundary = get_offset_boundary(self.pending, self.finish_ms, self.interval, self.number_beeps)

            if not is_safe(elapsed, boundary): return False, "Didn't shift any offset!"

            if every:
                self.pending = shift_all(self.pending, delta)
                self.variable_frame_offset += 1 if delta > 0 else -1
                message = f"All Offsets >>> {delta:+.2f}"

            else:
                if not self.pending: return False, "No offsets left to shift."

                previous        = self.pending[0]
                self.pending[0] = shift_offset(previous, delta)
                message         = f"Offset {round(previous[1])} >>> {round(self.pending[0][1])}"

            self.revision += 1

        return True, message

    def submit_variable_frame(self, frame):
        """Mirrors the variable-frame branch of src/main.py: an offset too close
        to fire is refused, and one blocked only by the next beep waits for it."""
        with self.lock:
            if self.start_ns is None: return False, "No timer is running."

            target   = (frame + self.variable_frame_offset) * FRAME_MS
            boundary = calculate_first_offset_beep(target, self.interval, self.number_beeps)
            elapsed  = time.perf_counter_ns() - self.start_ns

            if not is_safe(elapsed, boundary): return False, "Didn't append any offset!"

            offset_boundary = get_offset_boundary(self.pending, self.finish_ms, self.interval, self.number_beeps)

            if is_safe(elapsed, offset_boundary):
                self.pending.append((boundary, target))
                self.pending.sort()
                self.revision += 1

                return True, f"Variable Frame {frame} (Offset {round(target)}) appended..."

            self.queued = (boundary, target, frame)

        return True, f"Variable Frame {frame} waiting for the next beep to pass..."

    def settle_queue(self, start):
        """Appends a queued variable frame once the next beep is clear of it."""
        # Checked without the lock first: this runs every millisecond of every
        # wait, and is almost always negative. A late-arriving queue entry is
        # simply picked up on the next pass.
        if self.queued is None: return

        message = None

        with self.lock:
            if self.queued is None: return

            boundary, target, frame = self.queued
            elapsed                 = time.perf_counter_ns() - start

            if not is_safe(elapsed, boundary):
                self.queued = None
                message     = "Didn't append any offset!"

            else:
                offset_boundary = get_offset_boundary(self.pending, self.finish_ms, self.interval, self.number_beeps)

                if not is_safe(elapsed, offset_boundary): return

                self.pending.append((boundary, target))
                self.pending.sort()

                self.revision += 1
                self.queued    = None
                message        = f"Variable Frame {frame} (Offset {round(target)}) appended..."

        if message is not None: self.emit("notice", message = message)

    # --- the run -----------------------------------------------------------

    def run(self, name, configuration):
        """Wrapper so a failure in the worker reaches the window instead of
        killing the thread silently."""
        try:
            self.execute(name, configuration)

        except Exception as error:
            self.emit("failed", name = name, message = f"{type(error).__name__}: {error}")

        finally:
            with self.lock:
                self.start_ns = None
                self.pending  = []
                self.queued   = None

    def execute(self, name, configuration):
        # imported here so the sound device is only claimed once a run begins.
        # src.ui warms this up in the background when the window opens, so the
        # clock below is not delayed by opening the device on the first run.
        from src.audio import create_sequence_beeps, play_sequence_beeps

        offsets      = configuration["offsets"]
        interval     = configuration["interval"]
        number_beeps = configuration["number_beeps"]

        sequence = create_sequence_beeps(number_beeps, interval)
        initial  = [(calculate_first_offset_beep(offset, interval, number_beeps), offset) for offset in offsets]

        switch_interval = sys.getswitchinterval()
        sys.setswitchinterval(SWITCH_INTERVAL)

        try:
            start = time.perf_counter_ns()

            with self.lock:
                self.start_ns              = start
                self.pending               = list(initial)
                self.queued                = None
                self.interval              = interval
                self.number_beeps          = number_beeps
                self.variable_frame_offset = configuration.get("variable_frame_offset", 0)
                self.finish_ms             = (offsets[-1] if offsets else 0) + FINISH_MS
                self.revision             += 1

            self.emit("started", name = name)

            delays   = []
            revision = -1
            beep_ms  = 0
            target_ms = 0

            while True:
                if self.stopping.is_set():
                    self.emit("stopped", name = name)
                    return

                if revision != self.revision:
                    with self.lock:
                        revision = self.revision

                        if not self.pending: break

                        beep_ms, target_ms = self.pending[0]

                elapsed   = time.perf_counter_ns() - start
                remaining = beep_ms * MS_TO_NS - elapsed

                if remaining > 0:
                    if remaining > SPIN_MS * MS_TO_NS:
                        self.settle_queue(start)
                        time.sleep(SLEEP_S)

                    continue

                with self.lock:
                    if not self.pending or self.pending[0][0] != beep_ms:
                        revision = -1        # a shift landed; re-read and re-check
                        continue

                    self.pending.pop(0)
                    self.revision += 1

                    left = len(self.pending)

                revision = -1

                play_sequence_beeps(sequence)

                # measured before the blocking write, matching src/main.py
                target = elapsed / MS_TO_NS + interval * (number_beeps - 1)
                delay  = target - target_ms

                delays.append(delay)

                self.emit(
                    "beep",
                    name      = name,
                    target    = target,
                    planned   = target_ms,
                    delay     = delay,
                    average   = sum(delays) / len(delays),
                    remaining = left,
                )

            self.emit("finished", name = name)

        finally:
            sys.setswitchinterval(switch_interval)
