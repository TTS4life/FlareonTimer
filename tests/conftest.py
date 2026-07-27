"""Test scaffolding.

Two modules in this project do work at import time that tests must neutralise
before anything under src/ is imported:

  - src/io.py starts a msvcrt listener thread (a tight spin loop) and a printer
    thread. The printer would consume the queue_prints messages that tests want
    to assert on, so it is shut down here.
  - src/audio.py opens a real sounddevice OutputStream, which needs hardware.

Stubs are installed into sys.modules first, so the real msvcrt/sounddevice are
never touched and the suite runs without an audio device.
"""

import pathlib
import queue
import sys
import time
import types

import numpy
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# --- stub msvcrt -----------------------------------------------------------
# kbhit() sleeps so the listener thread in src/io.py idles instead of pinning a
# core for the whole test session.

def kbhit():
    time.sleep(0.01)
    return False

module_msvcrt        = types.ModuleType("msvcrt")
module_msvcrt.kbhit  = kbhit
module_msvcrt.getwch = lambda: ""

sys.modules["msvcrt"] = module_msvcrt

# --- stub sounddevice ------------------------------------------------------

class FakeOutputStream:
    def __init__(self, **kwargs):
        self.kwargs  = kwargs
        self.writes  = []
        self.started = False
        self.closed  = False

    def start(self): self.started = True
    def stop(self):  self.started = False
    def close(self): self.closed  = True

    def write(self, data): self.writes.append(numpy.array(data, copy = True))

module_sounddevice              = types.ModuleType("sounddevice")
module_sounddevice.OutputStream = FakeOutputStream

sys.modules["sounddevice"] = module_sounddevice

# --- shut down the printer thread ------------------------------------------
# printer() breaks on None, which hands queue_prints over to the tests.

import src.io

src.io.queue_prints.put(None)
src.io.thread_printer.join(timeout = 2.0)


def drain(target):
    while True:
        try: target.get_nowait()
        except queue.Empty: return


@pytest.fixture(autouse = True)
def clean_queues():
    """Every test starts with empty queues and a clean audio stream.

    main() calls stream.stop()/close() when it terminates, so the lifecycle
    flags are reset too - otherwise the first engine test would leave the
    shared stream closed for every test that follows.
    """
    import src.audio

    drain(src.io.queue_inputs)
    drain(src.io.queue_prints)

    src.audio.stream.writes.clear()
    src.audio.stream.started = True
    src.audio.stream.closed  = False

    yield

    drain(src.io.queue_inputs)
    drain(src.io.queue_prints)


@pytest.fixture
def stream():
    import src.audio
    return src.audio.stream
