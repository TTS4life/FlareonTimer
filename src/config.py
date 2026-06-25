import json
import pathlib
import sys

def get_path():
    if getattr(sys, "frozen", False): return pathlib.Path(sys.executable).parent / "_internal"
    else:                             return pathlib.Path(__file__).resolve().parent.parent

PATH_FILE = get_path()

PATH_TIMERS = str(PATH_FILE / "assets" / "json" / "timers.json")
PATH_CONFIG = str(PATH_FILE / "assets" / "json" / "config.json")

with open(PATH_TIMERS, "r") as file_timers: timers = json.load(file_timers)
with open(PATH_CONFIG, "r") as file_config: config = json.load(file_config)
