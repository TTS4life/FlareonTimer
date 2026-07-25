"""The FlareonTimer front end.

Deliberately imports nothing from src.io or src.main: those start a spin-loop
keyboard listener at import time, which would burn a core while the window is
up. src.runner claims the sound device only once a run begins.
"""

import copy
import json
import threading
import time
import tkinter

from tkinter import messagebox, ttk

from src.config    import PATH_CONFIG, PATH_TIMERS, config
from src.config    import timers as timers_in_memory
from src.constants import FRAME_MS, MS_TO_NS
from src.offsets   import compact, duplicates, lead_in, parse, parse_all, parse_beeps, parse_interval, warnings
from src.offsets   import save as save_timers
from src.runner    import Runner
from src.settings  import ACTIONS, binding, conflict, describe, usable
from src.settings  import save as save_config

COLOUR_BAD     = "#ffd6d6"
COLOUR_NEUTRAL = "white"

TICK_MS = 50

SHIFTS = ["add", "subtract", "add_all", "subtract_all"]

def format_value(value):
    return str(compact(value))


def format_elapsed(elapsed_ms):
    sign      = "-" if elapsed_ms < 0 else ""
    elapsed   = abs(elapsed_ms)
    minutes   = int(elapsed // 60_000)
    seconds   = int(elapsed // 1_000) % 60
    remainder = int(elapsed) % 1_000

    return f"{sign}{minutes:02d}:{seconds:02d}.{remainder:03d}"


def publish(timers):
    """Share saved edits with the engine, which reads src.config.timers."""
    timers_in_memory.clear()
    timers_in_memory.update(copy.deepcopy(timers))


class ScrollFrame(ttk.Frame):
    """A vertically scrolling container. Rows go into `self.body`."""

    def __init__(self, parent):
        super().__init__(parent)

        self.rowconfigure(0, weight = 1)
        self.columnconfigure(0, weight = 1)

        canvas    = tkinter.Canvas(self, highlightthickness = 0)
        scrollbar = ttk.Scrollbar(self, orient = "vertical", command = canvas.yview)

        self.body   = tkinter.Frame(canvas)
        self.canvas = canvas
        self.window = canvas.create_window((0, 0), window = self.body, anchor = "nw")

        canvas.configure(yscrollcommand = scrollbar.set)
        canvas.grid(row = 0, column = 0, sticky = "nsew")
        scrollbar.grid(row = 0, column = 1, sticky = "ns")

        self.body.bind("<Configure>", lambda event: canvas.configure(scrollregion = canvas.bbox("all")))
        canvas.bind("<Configure>",    lambda event: canvas.itemconfigure(self.window, width = event.width))
        canvas.bind("<Enter>",        lambda event: canvas.bind_all("<MouseWheel>", self.on_wheel))
        canvas.bind("<Leave>",        lambda event: canvas.unbind_all("<MouseWheel>"))

    def on_wheel(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120), "units")

    def clear(self):
        for child in self.body.winfo_children(): child.destroy()

    def to_bottom(self):
        self.update_idletasks()
        self.canvas.yview_moveto(1.0)


class TimerRow:
    """One timer on the list screen: active, name, interval, beeps, edit."""

    def __init__(self, parent, index, name, configuration, active, on_edit, on_change):
        self.name     = name
        self.interval = tkinter.StringVar(value = format_value(configuration["interval"]))
        self.beeps    = tkinter.StringVar(value = format_value(configuration["number_beeps"]))

        self.interval.trace_add("write", lambda *_: on_change())
        self.beeps.trace_add("write",    lambda *_: on_change())

        self.radio = ttk.Radiobutton(parent, text = name, value = name, variable = active)
        self.radio.grid(row = index, column = 0, sticky = "w", padx = (4, 12), pady = 3)

        self.entry_interval = tkinter.Entry(parent, textvariable = self.interval, width = 10, justify = "right")
        self.entry_interval.grid(row = index, column = 1, padx = 4)

        self.entry_beeps = tkinter.Entry(parent, textvariable = self.beeps, width = 6, justify = "right")
        self.entry_beeps.grid(row = index, column = 2, padx = 4)

        self.label_offsets = tkinter.Label(parent, anchor = "e", fg = "gray")
        self.label_offsets.grid(row = index, column = 3, sticky = "ew", padx = 8)

        self.button = ttk.Button(parent, text = "Edit offsets", command = lambda: on_edit(name))
        self.button.grid(row = index, column = 4, padx = 4)

    def texts(self):
        return self.interval.get(), self.beeps.get()

    def set_count(self, count):
        self.label_offsets.configure(text = f"{count} offsets")

    def set_enabled(self, enabled):
        """Disabled during a run: the values cannot affect a run already going,
        and it keeps focus out of these boxes so the shift keybinds work."""
        state = ["!disabled"] if enabled else ["disabled"]

        self.radio.state(state)
        self.button.state(state)

        self.entry_interval.configure(state = "normal" if enabled else "disabled")
        self.entry_beeps.configure(state    = "normal" if enabled else "disabled")

    def mark(self, interval_ok, beeps_ok):
        self.entry_interval.configure(background = COLOUR_NEUTRAL if interval_ok else COLOUR_BAD)
        self.entry_beeps.configure(background    = COLOUR_NEUTRAL if beeps_ok    else COLOUR_BAD)


class OffsetRow:
    """One offset box on the offsets screen."""

    def __init__(self, parent, value, on_remove, on_change, on_submit):
        self.frame    = tkinter.Frame(parent)
        self.variable = tkinter.StringVar(value = value)

        self.variable.trace_add("write", lambda *_: on_change())

        self.label = tkinter.Label(self.frame, width = 4, anchor = "e", fg = "gray")
        self.label.pack(side = "left")

        self.entry = tkinter.Entry(self.frame, textvariable = self.variable, width = 12, justify = "right")
        self.entry.pack(side = "left", padx = 6)
        self.entry.bind("<Return>", lambda event: on_submit())

        tkinter.Label(self.frame, text = "ms", fg = "gray").pack(side = "left")

        ttk.Button(self.frame, text = "Remove", width = 8, command = lambda: on_remove(self)).pack(side = "left", padx = 8)

    def text(self):
        return self.variable.get()

    def renumber(self, index):
        self.label.configure(text = f"{index}.")

    def mark(self, ok):
        self.entry.configure(background = COLOUR_NEUTRAL if ok else COLOUR_BAD)

    def focus(self):
        self.entry.focus_set()
        self.entry.selection_range(0, "end")

    def destroy(self):
        self.frame.destroy()


class KeybindRow:
    """One keybind on the settings tab."""

    def __init__(self, parent, index, action, label, on_capture):
        self.action = action
        self.label  = label

        tkinter.Label(parent, text = label, anchor = "w").grid(row = index, column = 0, sticky = "w", padx = (4, 20), pady = 5)

        self.button = ttk.Button(parent, width = 18, command = lambda: on_capture(action))
        self.button.grid(row = index, column = 1, sticky = "w")

    def show(self, key, capturing):
        self.button.configure(text = "Press a key..." if capturing else describe(key))


class Application(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding = 10)

        self.root   = root
        self.runner = Runner()

        with open(PATH_TIMERS) as file_timers: self.timers = json.load(file_timers)

        self.snapshot        = copy.deepcopy(self.timers)
        self.config_snapshot = copy.deepcopy(config)

        self.timer_rows  = []
        self.offset_rows = []
        self.editing     = None
        self.capturing   = None
        self.after_id    = None
        self.restarting  = False

        self.active = tkinter.StringVar(value = next(iter(self.timers), ""))

        self.grid(row = 0, column = 0, sticky = "nsew")
        self.rowconfigure(0, weight = 1)
        self.columnconfigure(0, weight = 1)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row = 0, column = 0, sticky = "nsew")

        self.tab_timers = ttk.Frame(self.notebook, padding = 8)
        self.tab_timers.rowconfigure(0, weight = 1)
        self.tab_timers.columnconfigure(0, weight = 1)

        self.build_timers_screen()
        self.build_offsets_screen()
        self.build_settings_tab()

        self.notebook.add(self.tab_timers,   text = "Timers")
        self.notebook.add(self.tab_settings, text = "Settings")

        self.build_footer()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<Control-s>", lambda event: self.on_save())
        root.bind("<Key>", self.on_key)

        self.warm_audio()
        self.show_timers()
        self.tick()

    def warm_audio(self):
        """Open the sound device up front, on a background thread.

        src.audio opens its OutputStream at import, and the runner takes its
        t=0 after that import. Doing it on the first Start would put the device
        opening between the click and the clock starting, which matters when
        the press is synced to something on screen.
        """
        def load():
            try:    import src.audio
            except Exception: pass   # reported properly when a run is started

        threading.Thread(target = load, daemon = True).start()

    # --- screens -----------------------------------------------------------

    def build_timers_screen(self):
        screen = ttk.Frame(self.tab_timers)
        screen.rowconfigure(2, weight = 1)
        screen.columnconfigure(0, weight = 1)

        header = ttk.Frame(screen)
        header.grid(row = 0, column = 0, sticky = "ew", pady = (0, 6))

        ttk.Label(header, text = "Timers", font = ("Segoe UI", 12, "bold")).pack(side = "left")

        self.button_start = ttk.Button(header, text = "Start timer", command = self.on_start)
        self.button_start.pack(side = "right")

        self.button_stop = ttk.Button(header, text = "Stop", command = self.on_stop)
        self.button_stop.pack(side = "right", padx = (0, 6))

        self.label_run = ttk.Label(screen, text = "", font = ("Consolas", 11), foreground = "green")
        self.label_run.grid(row = 1, column = 0, sticky = "w", pady = (0, 6))

        self.scroll_timers = ScrollFrame(screen)
        self.scroll_timers.grid(row = 2, column = 0, sticky = "nsew")

        ttk.Label(screen, text = "Pending offsets", foreground = "gray").grid(row = 3, column = 0, sticky = "w", pady = (10, 0))

        self.label_pending = ttk.Label(screen, text = "", font = ("Consolas", 10), wraplength = 700, justify = "left")
        self.label_pending.grid(row = 4, column = 0, sticky = "w")

        self.build_adjustments(screen)

        self.screen_timers = screen

    def build_adjustments(self, screen):
        """The live shift buttons and variable frame entry, under the offsets."""
        controls = ttk.Frame(screen)
        controls.grid(row = 5, column = 0, sticky = "ew", pady = (8, 0))

        shifts = [
            ("add",          "+1 frame"),
            ("subtract",     "-1 frame"),
            ("add_all",      "+1 all"),
            ("subtract_all", "-1 all"),
        ]

        self.buttons_shift = {}

        for action, text in shifts:
            button = ttk.Button(controls, text = text, width = 9, command = lambda a = action: self.on_shift(a))
            button.pack(side = "left", padx = (0, 4))

            self.buttons_shift[action] = button

        ttk.Label(controls, text = "Variable frame").pack(side = "left", padx = (16, 6))

        self.variable_frame = tkinter.StringVar()

        self.entry_frame = tkinter.Entry(controls, textvariable = self.variable_frame, width = 10, justify = "right")
        self.entry_frame.pack(side = "left")
        self.entry_frame.bind("<Return>", self.on_submit_frame)

        self.button_frame = ttk.Button(controls, text = "Submit", width = 9, command = self.on_submit_frame)
        self.button_frame.pack(side = "left", padx = 6)

    def build_offsets_screen(self):
        screen = ttk.Frame(self.tab_timers)
        screen.rowconfigure(1, weight = 1)
        screen.columnconfigure(0, weight = 1)

        header = ttk.Frame(screen)
        header.grid(row = 0, column = 0, sticky = "ew", pady = (0, 6))

        ttk.Button(header, text = "< Back", command = self.on_back).pack(side = "left")

        self.label_heading = ttk.Label(header, text = "", font = ("Segoe UI", 12, "bold"))
        self.label_heading.pack(side = "left", padx = 10)

        self.label_context = ttk.Label(header, text = "", foreground = "gray")
        self.label_context.pack(side = "right")

        self.scroll_offsets = ScrollFrame(screen)
        self.scroll_offsets.grid(row = 1, column = 0, sticky = "nsew")

        actions = ttk.Frame(screen)
        actions.grid(row = 2, column = 0, sticky = "w", pady = (8, 0))

        ttk.Button(actions, text = "Add offset", command = self.on_add).pack(side = "left")
        ttk.Button(actions, text = "Sort",       command = self.on_sort).pack(side = "left", padx = 6)

        self.screen_offsets = screen

    def build_settings_tab(self):
        tab = ttk.Frame(self.notebook, padding = 12)

        ttk.Label(tab, text = "Keybinds", font = ("Segoe UI", 12, "bold")).grid(
            row = 0, column = 0, columnspan = 2, sticky = "w", pady = (0, 10))

        self.keybind_rows = {}

        for index, (action, label) in enumerate(ACTIONS, start = 1):
            self.keybind_rows[action] = KeybindRow(tab, index, action, label, self.on_capture)

        ttk.Label(
            tab,
            text       = "Click a binding, then press the key you want. Click it again to cancel.\n"
                         "Start timer also stops a run in progress.",
            foreground = "gray",
            justify    = "left",
        ).grid(row = len(ACTIONS) + 1, column = 0, columnspan = 2, sticky = "w", pady = (14, 0))

        self.tab_settings = tab

        self.refresh_keybinds()

    def build_footer(self):
        footer = ttk.Frame(self)
        footer.grid(row = 1, column = 0, sticky = "ew", pady = (10, 0))
        footer.columnconfigure(0, weight = 1)

        self.label_status = ttk.Label(footer, text = "", wraplength = 660, justify = "left")
        self.label_status.grid(row = 0, column = 0, sticky = "w")

        ttk.Button(footer, text = "Save", command = self.on_save).grid(row = 0, column = 1, sticky = "e")

    def show_timers(self):
        self.editing = None
        self.screen_offsets.grid_forget()
        self.screen_timers.grid(row = 0, column = 0, sticky = "nsew")

        self.scroll_timers.clear()
        self.timer_rows = []

        if self.active.get() not in self.timers: self.active.set(next(iter(self.timers), ""))

        body = self.scroll_timers.body
        body.columnconfigure(0, weight = 1)
        body.columnconfigure(3, weight = 1)

        for column, text in enumerate(["Timer", "Interval (ms)", "Beeps", "", ""]):
            tkinter.Label(body, text = text, fg = "gray").grid(row = 0, column = column, sticky = "w", padx = 4)

        for index, (name, configuration) in enumerate(self.timers.items(), start = 1):
            row = TimerRow(body, index, name, configuration, self.active, self.on_edit, self.validate)
            row.set_count(len(configuration["offsets"]))
            self.timer_rows.append(row)

        self.refresh_controls()
        self.validate()

    def show_offsets(self, name):
        self.editing = name
        self.screen_timers.grid_forget()
        self.screen_offsets.grid(row = 0, column = 0, sticky = "nsew")

        self.label_heading.configure(text = name)

        self.scroll_offsets.clear()
        self.offset_rows = []

        for offset in self.timers[name]["offsets"]: self.add_offset_row(format_value(offset))

        self.refresh_context()
        self.validate()

    def refresh_context(self):
        configuration = self.timers[self.editing]

        self.label_context.configure(
            text = f"interval {format_value(configuration['interval'])} ms"
                   f"     {configuration['number_beeps']} beeps"
                   f"     lead-in {format_value(lead_in(configuration['interval'], configuration['number_beeps']))} ms"
        )

    def add_offset_row(self, value = ""):
        row = OffsetRow(self.scroll_offsets.body, value, self.on_remove, self.validate, self.on_add)
        row.frame.pack(fill = "x", pady = 1)

        self.offset_rows.append(row)
        self.renumber()

        return row

    def renumber(self):
        for index, row in enumerate(self.offset_rows, start = 1): row.renumber(index)

    # --- running -----------------------------------------------------------

    def tick(self):
        if not self.winfo_exists(): return

        self.drain_events()
        self.refresh_run()

        self.after_id = self.after(TICK_MS, self.tick)

    def drain_events(self):
        while not self.runner.events.empty():
            event = self.runner.events.get()
            kind  = event["kind"]

            if kind == "started":
                self.restarting = False
                self.report([], notes = [f"Running {event['name']}..."])
                self.refresh_controls()

            elif kind == "beep" and config["print_target_beep"]:
                self.report([], notes = [
                    f"Target Beep @ {round(event['target'])}"
                    f"     delay {event['delay']:+.2f} ms"
                    f"     average {event['average']:+.2f} ms"
                    f"     {event['remaining']} left"
                ])

            elif kind == "notice":
                self.report([], notes = [event["message"]])

            elif kind == "failed":
                self.report([f"{event['name']} could not run - {event['message']}"])
                self.refresh_controls()

            elif kind == "stopped" and self.restarting:
                continue   # the old run dying as part of a restart

            elif kind in ("finished", "stopped"):
                verb = "finished" if kind == "finished" else "stopped"
                self.report([], notes = [f"{event['name']} {verb}."])
                self.refresh_controls()

    def refresh_run(self):
        if not self.runner.running():
            self.label_run.configure(text = "")
            self.label_pending.configure(text = "")
            return

        state = self.runner.snapshot()

        if state["start_ns"] is None: return

        elapsed_ms = (time.perf_counter_ns() - state["start_ns"]) / MS_TO_NS
        text       = f"{state['name']}   {format_elapsed(elapsed_ms)}"

        pending = state["pending"]

        if pending:
            beep_ms, target_ms = pending[0]
            text += f"   next {round(target_ms)} ms   first beep in {(beep_ms - elapsed_ms) / 1_000:+.2f} s"

        self.label_run.configure(text = text)
        self.label_pending.configure(text = self.format_pending(pending))

    def format_pending(self, pending):
        """Whole milliseconds: a shifted offset is a fraction of a frame off a
        round number, and src/main.py reports these rounded too."""
        if not pending: return "none left"

        targets = [str(round(target)) for _, target in pending]

        return "   ".join([f"> {targets[0]}"] + targets[1:])

    def refresh_controls(self):
        running = self.runner.running() or self.restarting
        state   = ["!disabled"] if running else ["disabled"]

        self.button_start.configure(text = "Restart timer" if running else "Start timer")
        self.button_stop.state(state)

        for button in self.buttons_shift.values(): button.state(state)

        self.button_frame.state(state)

        for row in self.timer_rows: row.set_enabled(not running)

    def refresh_keybinds(self):
        for action, row in self.keybind_rows.items():
            row.show(binding(config["keybinds"], action), self.capturing == action)

    # --- committing --------------------------------------------------------

    def commit(self):
        """Fold the visible screen's values into self.timers. Returns errors."""
        if self.editing is None: return self.commit_timers()

        return self.commit_offsets()

    def commit_timers(self):
        errors = []
        values = {}

        for row in self.timer_rows:
            interval_text, beeps_text = row.texts()

            try: interval = parse_interval(interval_text)
            except ValueError as error:
                errors.append(f"{row.name} interval {error}")
                interval = None

            try: beeps = parse_beeps(beeps_text)
            except ValueError as error:
                errors.append(f"{row.name} beeps {error}")
                beeps = None

            if interval is not None and beeps is not None: values[row.name] = (interval, beeps)

        if errors: return errors

        for name, (interval, beeps) in values.items():
            self.timers[name]["interval"]     = interval
            self.timers[name]["number_beeps"] = beeps

        return []

    def commit_offsets(self):
        offsets, errors = parse_all([row.text() for row in self.offset_rows])

        if errors: return errors
        if not offsets: return ["A timer needs at least one offset."]

        repeated = duplicates(offsets)

        if repeated: return [f"Duplicate offsets: {', '.join(format_value(offset) for offset in repeated)}."]

        self.timers[self.editing]["offsets"] = [compact(offset) for offset in sorted(offsets)]

        return []

    def pending(self):
        """True when the visible widgets differ from self.timers."""
        if self.editing is not None:
            current = [format_value(offset) for offset in self.timers[self.editing]["offsets"]]
            return [row.text() for row in self.offset_rows] != current

        for row in self.timer_rows:
            configuration = self.timers[row.name]
            if row.texts() != (format_value(configuration["interval"]), format_value(configuration["number_beeps"])): return True

        return False

    def dirty(self):
        return self.pending() or self.timers != self.snapshot or config != self.config_snapshot

    def confirm_discard(self):
        if not self.dirty(): return True

        return messagebox.askyesno("Unsaved changes", "Discard the unsaved changes?", parent = self)

    # --- events ------------------------------------------------------------

    def on_key(self, event):
        if self.capturing is not None: return self.capture_key(event)

        if self.notebook.index(self.notebook.select()) != 0: return
        if self.editing is not None: return

        in_entry = isinstance(self.focus_get(), (tkinter.Entry, ttk.Entry))

        if in_entry and event.keysym not in ("Return", "Escape"): return

        keybinds = config["keybinds"]

        if   event.char == binding(keybinds, "start_restart"):  self.on_start()
        elif event.char == binding(keybinds, "previous"):       self.on_previous()
        elif event.char == binding(keybinds, "next"):           self.on_next()
        elif event.char == binding(keybinds, "variable_frame"): self.on_submit_frame()
        elif event.char in [binding(keybinds, action) for action in SHIFTS]:
            for action in SHIFTS:
                if event.char == binding(keybinds, action):
                    self.on_shift(action)
                    break

    def on_shift(self, action):
        delta = FRAME_MS if action in ("add", "add_all") else -FRAME_MS
        every = action in ("add_all", "subtract_all")

        ok, message = self.runner.shift_pending(delta, every)

        self.report([] if ok else [message], notes = [message] if ok else ())
        self.refresh_run()

    def on_submit_frame(self, event = None):
        text = self.variable_frame.get().strip()

        if not text:
            self.report(["Enter a variable frame first."])
            return "break"

        try: frame = float(text)
        except ValueError:
            self.report([f"{text!r} is not a number."])
            return "break"

        ok, message = self.runner.submit_variable_frame(frame)

        self.report([] if ok else [message], notes = [message] if ok else ())

        if ok: self.variable_frame.set("")

        self.refresh_run()

        return "break"

    def capture_key(self, event):
        action = self.capturing
        key    = event.char

        if not usable(key): return "break"   # modifiers and function keys carry no character

        clash = conflict(config["keybinds"], action, key)

        if clash:
            self.capturing = None
            self.refresh_keybinds()
            self.report([f"{describe(key)} is already bound to {clash}."])
            return "break"

        config["keybinds"][action] = key

        self.capturing = None
        self.refresh_keybinds()
        self.update_title()
        self.report([], notes = [f"{describe(key)} bound. Save to keep it."])

        return "break"

    def on_capture(self, action):
        self.capturing = None if self.capturing == action else action

        self.refresh_keybinds()

        if self.capturing is not None:
            self.report([], notes = [f"Press the key for {self.keybind_rows[action].label}..."])

    def on_previous(self):
        self.step_active(-1)

    def on_next(self):
        self.step_active(+1)

    def step_active(self, delta):
        if self.runner.running(): return

        names = list(self.timers)

        if not names: return

        try:    index = names.index(self.active.get())
        except ValueError: index = 0

        self.active.set(names[(index + delta) % len(names)])

    def on_start(self):
        if self.runner.running() or self.restarting:
            self.on_restart()
            return

        self.begin_run()

    def begin_run(self):
        errors = self.commit_timers()

        if errors:
            self.report(errors)
            return False

        name = self.active.get()

        if name not in self.timers:
            self.report(["Select a timer first."])
            return False

        self.runner.start(name, self.timers[name])
        self.refresh_controls()

        return True

    def on_restart(self):
        """Kill the run and start a fresh one.

        The worker cannot notice the stop while it is inside a blocking write,
        so the handover waits on the Tk event loop rather than joining here -
        joining would freeze the window for the length of a beep sequence.
        """
        self.restarting = True

        self.report([], notes = ["Restarting..."])
        self.runner.stop()
        self.resume_after_stop()

    def resume_after_stop(self):
        if not self.winfo_exists(): return

        if self.runner.running():
            self.after(10, self.resume_after_stop)
            return

        if not self.begin_run():
            self.restarting = False
            self.refresh_controls()

    def on_stop(self):
        self.restarting = False
        self.runner.stop()

    def on_edit(self, name):
        errors = self.commit_timers()

        if errors:
            self.report(errors)
            return

        self.show_offsets(name)

    def on_back(self):
        errors = self.commit_offsets()

        if errors and not messagebox.askyesno(
            "Discard changes",
            "\n".join(errors) + "\n\nGo back and discard these changes?",
            parent = self,
        ): return

        self.show_timers()

    def on_add(self):
        row = self.add_offset_row()

        self.scroll_offsets.to_bottom()
        row.focus()

        self.validate()

    def on_remove(self, row):
        self.offset_rows.remove(row)
        row.destroy()

        self.renumber()
        self.validate()

    def on_sort(self):
        offsets, errors = parse_all([row.text() for row in self.offset_rows])

        if errors:
            self.report(errors)
            return

        for row in self.offset_rows: row.destroy()
        self.offset_rows = []

        for offset in sorted(offsets): self.add_offset_row(format_value(offset))

        self.validate()

    def on_save(self):
        errors = self.commit()

        if errors:
            self.report(errors)
            return False

        save_timers(self.timers, PATH_TIMERS)
        publish(self.timers)
        self.snapshot = copy.deepcopy(self.timers)

        save_config(config, PATH_CONFIG)
        self.config_snapshot = copy.deepcopy(config)

        if self.editing is not None: self.refresh_context()
        else:                        [row.set_count(len(self.timers[row.name]["offsets"])) for row in self.timer_rows]

        self.report([], saved = True)
        self.update_title()

        return True

    def on_close(self):
        if not self.confirm_discard(): return

        self.restarting = False
        self.runner.stop()
        self.runner.join(timeout = 2.0)

        self.root.destroy()

    def destroy(self):
        if self.after_id is not None: self.after_cancel(self.after_id)
        super().destroy()

    # --- feedback ----------------------------------------------------------

    def validate(self):
        if self.editing is not None: notes = self.validate_offsets()
        else:                        notes = self.validate_timers()

        self.update_title()

        if not self.runner.running() and self.capturing is None: self.report([], notes = notes)

    def validate_timers(self):
        for row in self.timer_rows:
            interval_text, beeps_text = row.texts()

            interval_ok = True
            beeps_ok    = True

            try: parse_interval(interval_text)
            except ValueError: interval_ok = False

            try: parse_beeps(beeps_text)
            except ValueError: beeps_ok = False

            row.mark(interval_ok, beeps_ok)

        return []

    def validate_offsets(self):
        offsets = []

        for row in self.offset_rows:
            text = row.text().strip()

            if not text:
                row.mark(True)
                continue

            try:
                offsets.append(parse(text))
                row.mark(True)
            except ValueError:
                row.mark(False)

        configuration = self.timers[self.editing]

        return warnings(offsets, configuration["interval"], configuration["number_beeps"])

    def update_title(self):
        where  = f" - {self.editing}" if self.editing else ""
        marker = " *" if self.dirty() else ""

        self.root.title(f"FlareonTimer{where}{marker}")

    def report(self, errors, notes = (), saved = False):
        if errors:
            self.label_status.configure(text = "\n".join(errors), foreground = "red")
            return

        messages = []

        if saved: messages.append("Saved to timers.json and config.json.")
        messages.extend(notes)

        self.label_status.configure(
            text       = "  ".join(messages),
            foreground = "#b06000" if notes else "green" if saved else "gray",
        )


def run_ui():
    root = tkinter.Tk()
    root.title("FlareonTimer")
    root.minsize(760, 520)
    root.rowconfigure(0, weight = 1)
    root.columnconfigure(0, weight = 1)

    Application(root)

    root.mainloop()
