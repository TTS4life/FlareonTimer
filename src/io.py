import msvcrt
import queue
import threading
import time

from src.constants import SLEEP

queue_inputs = queue.Queue()
queue_prints = queue.Queue()

def listener():
    while True:
        if msvcrt.kbhit():
            key = msvcrt.getwch()
            if key in ["\x00", "\xe0"]: key += msvcrt.getwch()
            queue_inputs.put(key)

def printer():
    while True:
        message = queue_prints.get()
        if message is None: break
        print(message)
        time.sleep(SLEEP)

thread_listener = threading.Thread(target = listener, daemon = True)
thread_listener.start()

thread_printer = threading.Thread(target = printer, daemon = True)
thread_printer.start()
