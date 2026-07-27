import ctypes

from src.ui import run_ui

if __name__ == "__main__":
    ctypes.windll.winmm.timeBeginPeriod(1)

    try:     run_ui()
    finally: ctypes.windll.winmm.timeEndPeriod(1)
