import pytest

import src.constants

from src.config    import config
from src.constants import BUFFER_MS, FINISH_MS, FPS, FRAME_MS, MS_TO_NS, SLEEP


def test_fps_comes_from_config():
    assert FPS == config["fps"]


def test_frame_ms_is_one_frame():
    assert FRAME_MS == pytest.approx(1_000 / FPS)


def test_frame_ms_matches_gba_hardware():
    """The shipped fps is the GBA refresh rate, so a frame is ~16.74 ms."""
    assert FRAME_MS == pytest.approx(16.7427, abs = 1e-3)


def test_sleep_is_one_frame_in_seconds():
    assert SLEEP == pytest.approx(1 / FPS)
    assert SLEEP == pytest.approx(FRAME_MS / 1_000)


def test_ms_to_ns():
    assert MS_TO_NS == 1_000_000


def test_buffer_and_finish():
    assert BUFFER_MS == 250
    assert FINISH_MS == 60_000


def test_buffer_covers_at_least_one_frame():
    """The edit guard has to be wider than a frame or a shift could land late."""
    assert BUFFER_MS > FRAME_MS
