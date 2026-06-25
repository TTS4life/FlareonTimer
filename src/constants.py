from src.config import config

FPS      = config["fps"]
FRAME_MS = 1_000 / FPS
SLEEP    = 1 / FPS

BUFFER_MS = 250
FINISH_MS = 60_000

MS_TO_NS = 1_000_000
