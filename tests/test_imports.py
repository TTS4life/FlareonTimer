"""The window must not drag the engine in with it.

src/audio.py opens an audio stream at import and src/io.py starts a spin-loop
keyboard listener, so importing either while the window is up would hold the
sound device and burn a core. flareontimer.py imports src.main only after the
window closes, and src.runner imports src.audio only once a run begins.

Checked in subprocesses because the test session imports src.io itself. They
are spawned together rather than one per test - the interpreter startups
dominate and are independent.
"""

import pathlib
import subprocess
import sys

from concurrent.futures import ThreadPoolExecutor

import pytest

ROOT   = pathlib.Path(__file__).resolve().parent.parent
ENGINE = ["src.audio", "src.io", "src.main"]

CASES = {
    "src.ui":       [],
    "src.offsets":  [],
    "src.settings": [],
    "src.runner":   [],
    "src.jsonfile": [],
    "flareontimer": [],
    "src.main":     ENGINE,   # negative control: this one must pull all three
}


def engine_modules_after(statement):
    code = f"import {statement}; import sys; print(','.join(m for m in {ENGINE!r} if m in sys.modules))"

    result = subprocess.run([sys.executable, "-c", code], cwd = ROOT, capture_output = True, text = True)

    assert result.returncode == 0, result.stderr

    return [name for name in result.stdout.strip().split(",") if name]


@pytest.fixture(scope = "module")
def imported():
    with ThreadPoolExecutor(max_workers = len(CASES)) as pool:
        return dict(zip(CASES, pool.map(engine_modules_after, CASES)))


@pytest.mark.parametrize("module", [name for name in CASES if name != "src.main"])
def test_module_leaves_the_engine_alone(module, imported):
    assert imported[module] == [], f"{module} pulled in {imported[module]}"


def test_the_engine_is_importable_on_its_own(imported):
    """Guards against the checks above passing for the wrong reason."""
    assert imported["src.main"] == ENGINE
