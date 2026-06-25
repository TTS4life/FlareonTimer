import threading
import time

from src.audio     import create_sequence_beeps, play_sequence_beeps, stream
from src.config    import config, timers
from src.constants import FINISH_MS, FRAME_MS, MS_TO_NS, SLEEP
from src.io        import queue_inputs, queue_prints
from src.timer     import calculate_first_offset_beep, get_offset_boundary, is_safe, shift, shift_all

def main():
    delays = []

    while True:
        reset     = False
        terminate = False

        for name, configuration in timers.items():
            finish         = None
            timer_started  = False
            timer_finished = False

            thread_variable_frame = None
            variable_frame_active = False

            while not timer_finished:
                offsets               = configuration["offsets"]
                variable_frame_offset = configuration["variable_frame_offset"]
                interval              = configuration["interval"]
                number_beeps          = configuration["number_beeps"]

                offsets_beeps  = [(calculate_first_offset_beep(offset, interval, number_beeps), offset) for offset in offsets]
                sequence_beeps = create_sequence_beeps(number_beeps, interval)

                keybinds = config["keybinds"]

                if not timer_started:
                    queue_prints.put(f"Offsets of {name}: {offsets}")
                    queue_prints.put(f"Press ENTER to start the timer...")

                    while True:
                        if not queue_inputs.empty():
                            key = queue_inputs.get()

                            if key == keybinds["start_restart"]:
                                queue_prints.put("Timer started...")
                                finish = offsets_beeps[-1][1] + FINISH_MS
                                timer_started = True
                                break

                            if key == keybinds["next"]:
                                queue_prints.put(f"Next timer...")
                                timer_finished = True
                                break

                            if key == keybinds["reset"]:
                                queue_prints.put(f"Timer reset...")
                                reset          = True
                                timer_finished = True
                                break

                            if key == keybinds["terminate"]:
                                queue_prints.put(f"Timer terminated...")
                                terminate      = True
                                timer_finished = True
                                break

                if timer_finished: continue

                start = time.perf_counter_ns()

                while True:
                    current = time.perf_counter_ns()
                    elapsed = current - start

                    if not queue_inputs.empty():
                        key = queue_inputs.get()

                        if key == keybinds["start_restart"]:
                            queue_prints.put(f"Timer restarted...")
                            if thread_variable_frame is not None: thread_variable_frame.join()
                            break

                        if key == keybinds["next"]:
                            queue_prints.put(f"Next timer...")
                            timer_finished = True
                            if thread_variable_frame is not None: thread_variable_frame.join()
                            break

                        if key == keybinds["reset"]:
                            queue_prints.put(f"Timer reset...")
                            reset          = True
                            timer_finished = True
                            if thread_variable_frame is not None: thread_variable_frame.join()
                            break

                        if key == keybinds["terminate"]:
                            queue_prints.put(f"Timer terminated...")
                            terminate      = True
                            timer_finished = True
                            if thread_variable_frame is not None: thread_variable_frame.join()
                            break

                        if key == keybinds["variable_frame"]:
                            if not variable_frame_active:
                                variable_frame_active = True

                                def variable_frame():
                                    nonlocal variable_frame_active

                                    variable_frame = float(input("Variable Frame: "))
                                    variable_frame_ms = (variable_frame + variable_frame_offset) * FRAME_MS
                                    variable_frame_ms_boundary = calculate_first_offset_beep(variable_frame_ms, interval, number_beeps)

                                    while True:
                                        current_updated = time.perf_counter_ns()
                                        elapsed_updated = current_updated - start

                                        if not is_safe(elapsed_updated, variable_frame_ms_boundary):
                                            queue_prints.put(f"Didn't append any offset!")
                                            break

                                        offset_boundary = get_offset_boundary(offsets_beeps, finish, interval, number_beeps)

                                        if is_safe(elapsed_updated, offset_boundary):
                                            offsets_beeps.append((variable_frame_ms_boundary, variable_frame_ms))
                                            queue_prints.put(f"Variable Frame {variable_frame} (Offset {round(variable_frame_ms)}) appended...")
                                            break

                                        time.sleep(SLEEP)

                                    offsets_beeps.sort()
                                    variable_frame_active = False

                                thread_variable_frame = threading.Thread(target = variable_frame, daemon = True)
                                thread_variable_frame.start()

                        if key in [keybinds["add"], keybinds["subtract"], keybinds["add_all"], keybinds["subtract_all"]]:
                            offset_boundary = get_offset_boundary(offsets_beeps, finish, interval, number_beeps)

                            if is_safe(elapsed, offset_boundary):
                                delta = FRAME_MS if key in [keybinds["add"], keybinds["add_all"]] else -FRAME_MS

                                if key in [keybinds["add"], keybinds["subtract"]]:
                                    old_offsets_beeps = offsets_beeps[0]
                                    offsets_beeps[0] = shift(offsets_beeps[0], delta)
                                    queue_prints.put(f"Offset {round(old_offsets_beeps[1])} >>> {round(offsets_beeps[0][1])}")

                                if key in [keybinds["add_all"], keybinds["subtract_all"]]:
                                    offsets_beeps = shift_all(offsets_beeps, delta)
                                    variable_frame_offset += 1 if key == "*" else -1
                                    queue_prints.put(f"All Offsets >>> {delta:+.2f}")

                            else: queue_prints.put(f"Didn't shift any offset!")

                    if offsets_beeps:
                        if elapsed >= offsets_beeps[0][0] * MS_TO_NS:
                            play_sequence_beeps(sequence_beeps)

                            target_offset = (elapsed / MS_TO_NS) + interval * (number_beeps - 1)

                            if config["print_target_beep"]:
                                queue_prints.put(f"Target Beep @ {round(target_offset)}")

                            delays.append(target_offset - offsets_beeps[0][1])
                            
                            if len(delays) % 10 == 0:
                                average = sum(delays) / len(delays)
                                queue_prints.put(f"Delay: {average:+.2f}")

                            current_updated = time.perf_counter_ns()
                            elapsed         = current_updated - start

                            offsets_beeps.pop(0)

                    if thread_variable_frame is not None and not thread_variable_frame.is_alive():
                        thread_variable_frame = None

                    if elapsed > finish * MS_TO_NS:
                        timer_finished = True
                        break

            if thread_variable_frame is not None: thread_variable_frame.join()
            if reset or terminate: break

        if terminate: break

    queue_inputs.put(None)
    queue_prints.put(None)

    stream.stop()
    stream.close()
