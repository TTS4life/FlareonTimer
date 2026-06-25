import ctypes

from src.main import main

if __name__ == "__main__":
    ctypes.windll.winmm.timeBeginPeriod(1)

    try:     main()
    finally: ctypes.windll.winmm.timeEndPeriod(1)
