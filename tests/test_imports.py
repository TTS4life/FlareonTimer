"""The window must not drag the engine in with it.

src/audio.py opens an audio stream at import and src/io.py starts a spin-loop
keyboard listener, so importing either while the window is up would hold the
sound device and burn a core. flareontimer.py imports src.main only after the
window closes.

Checked in a subprocess because the test session imports src.io itself.
"""

import pathlib
import subprocess
import sys

import pytest

ROOT   = pathlib.Path(__file__).resolve().parent.parent
ENGINE = ["src.audio", "src.io", "src.main"]


def imported_after(statement):
    code = f"{statement}; import sys; print(','.join(m for m in {ENGINE!r} if m in sys.modules))"

    result = subprocess.run([sys.executable, "-c", code], cwd = ROOT, capture_output = True, text = True)

    assert result.returncode == 0, result.stderr

    return [name for name in result.stdout.strip().split(",") if name]


def test_importing_the_ui_leaves_the_engine_alone():
    assert imported_after("import src.ui") == []


def test_importing_the_offsets_logic_leaves_the_engine_alone():
    assert imported_after("import src.offsets") == []


def test_the_runner_claims_no_sound_device_until_it_runs():
    """src.audio opens the OutputStream at import, so the runner defers it."""
    assert imported_after("import src.runner") == []


def test_the_entry_point_defers_the_engine():
    """flareontimer.py must not import src.main at module level."""
    assert imported_after("import flareontimer") == []


def test_the_engine_is_importable_on_its_own():
    """Guards against the check above passing for the wrong reason."""
    assert imported_after("import src.main") == ["src.audio", "src.io", "src.main"]
