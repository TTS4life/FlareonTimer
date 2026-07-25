"""Tests for the FlareonTimer window.

These drive the real widgets, so they need a display. Every test works against
a temporary copy of timers.json - the shipped file is never written to.
"""

import copy
import json
import queue
import shutil
import time

import pytest

tkinter = pytest.importorskip("tkinter")

import src.config
import src.settings
import src.ui


@pytest.fixture(scope = "session")
def tk_root():
    """One Tcl interpreter for the whole session.

    Creating and destroying a Tk root per test intermittently fails with
    "Can't find a usable tk.tcl", so the root is shared and only the
    Application widget is rebuilt between tests.
    """
    try: root = tkinter.Tk()
    except tkinter.TclError as error: pytest.skip(f"tk unavailable: {error}")

    root.withdraw()

    yield root

    root.destroy()


@pytest.fixture
def app(tk_root, tmp_path, monkeypatch):
    target        = tmp_path / "timers.json"
    config_target = tmp_path / "config.json"

    shutil.copyfile(src.config.PATH_TIMERS, target)
    shutil.copyfile(src.config.PATH_CONFIG, config_target)

    monkeypatch.setattr(src.ui, "PATH_TIMERS", str(target))
    monkeypatch.setattr(src.ui, "PATH_CONFIG", str(config_target))
    monkeypatch.setattr(src.ui.messagebox, "askyesno",       lambda *args, **kwargs: True)
    monkeypatch.setattr(src.ui.messagebox, "askyesnocancel", lambda *args, **kwargs: False)

    # the engine shares src.config.timers, so publish() must not leak between tests
    monkeypatch.setattr(src.ui, "timers_in_memory", copy.deepcopy(src.config.timers))

    # rebinding mutates the shared src.config.config dict in place
    original_config = copy.deepcopy(src.ui.config)

    application = src.ui.Application(tk_root)
    application.path        = target
    application.config_path = config_target

    yield application

    application.runner.stop()
    application.runner.join(timeout = 5.0)
    application.destroy()

    src.ui.config.clear()
    src.ui.config.update(original_config)


def reload(application):
    with open(application.path) as file_timers: return json.load(file_timers)


def wait_for(application, kind, timeout = 10.0):
    """Waits for a runner event. The tick loop only drains these under
    mainloop, which is not running here, so the queue is ours."""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try: event = application.runner.events.get(timeout = 0.05)
        except queue.Empty: continue

        if event["kind"] == kind: return event

    raise AssertionError(f"timed out waiting for {kind!r}")


def row_named(application, name):
    return next(row for row in application.timer_rows if row.name == name)


class TestTimerList:
    def test_starts_on_the_timer_list(self, app):
        assert app.editing is None

    def test_lists_every_timer(self, app):
        assert [row.name for row in app.timer_rows] == list(app.timers)

    def test_shows_interval_and_beeps(self, app):
        row = row_named(app, "Mudkip")

        assert row.texts() == ("250", "5")

    def test_shows_the_offset_count(self, app):
        assert row_named(app, "Mudkip").label_offsets.cget("text") == "5 offsets"

    def test_every_timer_has_an_editable_interval_and_beeps(self, app):
        for row in app.timer_rows:
            assert row.entry_interval.cget("state") == "normal"
            assert row.entry_beeps.cget("state")    == "normal"


class TestEditNavigation:
    def test_edit_opens_the_offsets_screen(self, app):
        app.on_edit("Mudkip")

        assert app.editing == "Mudkip"
        assert [row.text() for row in app.offset_rows] == ["11289", "19895", "25018", "30103", "56867"]

    def test_offsets_screen_shows_the_context(self, app):
        app.on_edit("Mudkip")

        assert "lead-in 1000 ms" in app.label_context.cget("text")

    def test_back_returns_to_the_list(self, app):
        app.on_edit("Mudkip")
        app.on_back()

        assert app.editing is None
        assert app.timer_rows

    def test_edit_carries_pending_interval_into_the_context(self, app):
        row_named(app, "Mudkip").interval.set("500")
        app.on_edit("Mudkip")

        assert "interval 500 ms" in app.label_context.cget("text")
        assert "lead-in 2000 ms" in app.label_context.cget("text")

    def test_edit_refuses_a_bad_interval(self, app):
        row_named(app, "Mudkip").interval.set("oops")
        app.on_edit("Mudkip")

        assert app.editing is None
        assert "interval" in app.label_status.cget("text")

    def test_edit_a_different_timer(self, app):
        app.on_edit("Abra")

        assert [row.text() for row in app.offset_rows] == ["7191", "20995", "23030"]


class TestIntervalAndBeeps:
    def test_saving_writes_the_interval(self, app):
        row_named(app, "Mudkip").interval.set("300")
        app.on_save()

        assert reload(app)["Mudkip"]["interval"] == 300

    def test_saving_writes_the_beeps(self, app):
        row_named(app, "Mudkip").beeps.set("7")
        app.on_save()

        assert reload(app)["Mudkip"]["number_beeps"] == 7

    def test_beeps_stay_an_int(self, app):
        row_named(app, "Mudkip").beeps.set("7")
        app.on_save()

        assert isinstance(reload(app)["Mudkip"]["number_beeps"], int)

    def test_refuses_a_fractional_beep_count(self, app):
        original = reload(app)

        row_named(app, "Mudkip").beeps.set("2.5")
        app.on_save()

        assert reload(app) == original
        assert "whole number" in app.label_status.cget("text")

    def test_refuses_zero_beeps(self, app):
        original = reload(app)

        row_named(app, "Mudkip").beeps.set("0")
        app.on_save()

        assert reload(app) == original
        assert "at least 1" in app.label_status.cget("text")

    def test_refuses_a_zero_interval(self, app):
        original = reload(app)

        row_named(app, "Mudkip").interval.set("0")
        app.on_save()

        assert reload(app) == original
        assert "above zero" in app.label_status.cget("text")

    def test_marks_a_bad_interval(self, app):
        row_named(app, "Mudkip").interval.set("oops")

        assert row_named(app, "Mudkip").entry_interval.cget("background") == src.ui.COLOUR_BAD

    def test_one_bad_row_blocks_the_whole_save(self, app):
        original = reload(app)

        row_named(app, "Mudkip").interval.set("300")
        row_named(app, "Abra").beeps.set("oops")
        app.on_save()

        assert reload(app) == original


class TestOffsetRows:
    def test_add_appends_an_empty_box(self, app):
        app.on_edit("Mudkip")
        before = len(app.offset_rows)

        app.on_add()

        assert len(app.offset_rows) == before + 1
        assert app.offset_rows[-1].text() == ""

    def test_remove_drops_the_box(self, app):
        app.on_edit("Mudkip")
        app.on_remove(app.offset_rows[1])

        assert [row.text() for row in app.offset_rows] == ["11289", "25018", "30103", "56867"]

    def test_boxes_are_renumbered(self, app):
        app.on_edit("Mudkip")
        app.on_remove(app.offset_rows[0])

        assert [row.label.cget("text") for row in app.offset_rows] == ["1.", "2.", "3.", "4."]

    def test_saving_writes_an_added_offset(self, app):
        app.on_edit("Mudkip")
        app.on_add()
        app.offset_rows[-1].variable.set("70000")
        app.on_save()

        assert reload(app)["Mudkip"]["offsets"] == [11289, 19895, 25018, 30103, 56867, 70000]

    def test_saving_writes_a_removed_offset(self, app):
        app.on_edit("Mudkip")
        app.on_remove(app.offset_rows[0])
        app.on_save()

        assert reload(app)["Mudkip"]["offsets"] == [19895, 25018, 30103, 56867]

    def test_offsets_sort_on_save(self, app):
        app.on_edit("Mudkip")
        app.on_add()
        app.offset_rows[-1].variable.set("15000")
        app.on_save()

        offsets = reload(app)["Mudkip"]["offsets"]

        assert offsets == sorted(offsets)
        assert 15000 in offsets

    def test_sort_reorders_the_boxes(self, app):
        app.on_edit("Mudkip")
        app.on_add()
        app.offset_rows[-1].variable.set("15000")
        app.on_sort()

        assert [row.text() for row in app.offset_rows][:3] == ["11289", "15000", "19895"]

    def test_marks_a_bad_offset(self, app):
        app.on_edit("Mudkip")
        app.offset_rows[0].variable.set("oops")

        assert app.offset_rows[0].entry.cget("background") == src.ui.COLOUR_BAD

    def test_empty_box_is_not_marked_bad(self, app):
        app.on_edit("Mudkip")
        app.on_add()

        assert app.offset_rows[-1].entry.cget("background") == src.ui.COLOUR_NEUTRAL

    def test_warns_about_offsets_that_are_too_close(self, app):
        app.on_edit("Mudkip")
        app.offset_rows[1].variable.set("11500")

        assert "closer together" in app.label_status.cget("text")

    def test_refuses_duplicates(self, app):
        original = reload(app)

        app.on_edit("Mudkip")
        app.offset_rows[1].variable.set("11289")
        app.on_save()

        assert reload(app) == original
        assert "Duplicate" in app.label_status.cget("text")

    def test_refuses_an_empty_box(self, app):
        original = reload(app)

        app.on_edit("Mudkip")
        app.on_add()
        app.on_save()

        assert reload(app) == original
        assert "is empty" in app.label_status.cget("text")

    def test_refuses_to_save_no_offsets(self, app):
        original = reload(app)

        app.on_edit("Mudkip")
        for row in list(app.offset_rows): app.on_remove(row)
        app.on_save()

        assert reload(app) == original
        assert "at least one offset" in app.label_status.cget("text")


class TestPersistence:
    def test_other_timers_are_untouched(self, app):
        original = reload(app)

        app.on_edit("Mudkip")
        app.on_remove(app.offset_rows[0])
        app.on_save()

        saved = reload(app)

        assert list(saved) == list(original)
        for name in original:
            if name != "Mudkip": assert saved[name] == original[name]

    def test_variable_frame_offset_is_untouched(self, app):
        original = reload(app)["Wingull/Poochyena"]["variable_frame_offset"]

        row_named(app, "Mudkip").interval.set("300")
        app.on_save()

        assert reload(app)["Wingull/Poochyena"]["variable_frame_offset"] == original

    def test_file_formatting_is_kept(self, app):
        app.on_save()

        data = app.path.read_bytes()

        assert b"\r\n" in data
        assert not data.endswith(b"\n")
        assert b'"offsets":               [' in data

    def test_saving_publishes_to_the_engine(self, app):
        """The engine reads src.config.timers, so saved edits must land there."""
        row_named(app, "Mudkip").interval.set("300")
        app.on_save()

        assert src.ui.timers_in_memory["Mudkip"]["interval"] == 300

    def test_editing_does_not_publish_before_saving(self, app):
        row_named(app, "Mudkip").interval.set("300")

        assert src.ui.timers_in_memory["Mudkip"]["interval"] == 250


class TestDirtyState:
    def test_clean_on_open(self, app):
        assert app.dirty() is False

    def test_interval_edit_marks_dirty(self, app):
        row_named(app, "Mudkip").interval.set("300")

        assert app.dirty() is True

    def test_offset_edit_marks_dirty(self, app):
        app.on_edit("Mudkip")
        app.offset_rows[0].variable.set("11290")

        assert app.dirty() is True

    def test_clean_after_saving(self, app):
        row_named(app, "Mudkip").interval.set("300")
        app.on_save()

        assert app.dirty() is False

    def test_stays_dirty_across_screens(self, app):
        app.on_edit("Mudkip")
        app.on_add()
        app.offset_rows[-1].variable.set("70000")
        app.on_back()

        assert app.dirty() is True


@pytest.fixture
def closed(app, monkeypatch):
    """Records window closes instead of performing them - the Tcl interpreter
    is shared across the session and must survive each test."""
    calls = []
    monkeypatch.setattr(app.root, "destroy", lambda: calls.append(True))
    return calls


def make_quick(app, name, offsets = (200,)):
    """Shrinks a timer so a test run finishes in a fraction of a second."""
    app.timers[name]["offsets"]      = list(offsets)
    app.timers[name]["number_beeps"] = 1
    row_named(app, name).beeps.set("1")


class TestActiveTimer:
    def test_defaults_to_the_first_timer(self, app):
        assert app.active.get() == "Mudkip"

    def test_every_row_has_a_radio_for_its_own_timer(self, app):
        assert [str(row.radio.cget("value")) for row in app.timer_rows] == list(app.timers)

    def test_all_radios_share_one_variable(self, app):
        app.active.set("Abra")

        assert app.active.get() == "Abra"
        assert len({str(row.radio.cget("variable")) for row in app.timer_rows}) == 1

    def test_active_survives_leaving_and_returning(self, app):
        app.active.set("Abra")
        app.on_edit("Mudkip")
        app.on_back()

        assert app.active.get() == "Abra"

    def test_falls_back_when_the_active_timer_is_gone(self, app):
        app.active.set("Abra")
        del app.timers["Abra"]
        app.show_timers()

        assert app.active.get() == "Mudkip"


class TestStarting:
    def test_starts_the_active_timer(self, app):
        make_quick(app, "Abra")
        app.active.set("Abra")
        app.on_start()

        assert wait_for(app, "started")["name"] == "Abra"

    def test_does_not_close_the_window(self, app, closed):
        make_quick(app, "Abra")
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "finished")

        assert closed == []

    def test_runs_to_completion(self, app):
        make_quick(app, "Abra", offsets = (150, 300))
        app.active.set("Abra")
        app.on_start()

        assert wait_for(app, "finished")["name"] == "Abra"

    def test_uses_unsaved_interval_and_beeps_edits(self, app):
        """Starting picks up what is in the boxes, without needing a save."""
        app.timers["Mudkip"]["offsets"] = [3000]
        row_named(app, "Mudkip").interval.set("500")
        row_named(app, "Mudkip").beeps.set("5")

        app.on_start()
        wait_for(app, "started")

        # lead-in is 500 * 4, so the sequence starts at 1000 ms
        assert app.runner.snapshot()["pending"][0] == (1000, 3000)

    def test_a_bad_interval_blocks_the_start(self, app):
        row_named(app, "Mudkip").interval.set("oops")
        app.on_start()

        assert app.runner.running() is False
        assert "interval" in app.label_status.cget("text")

    def test_starting_does_not_write_the_file(self, app):
        original = reload(app)

        make_quick(app, "Abra")
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "finished")

        assert reload(app) == original


class TestStopping:
    def test_stop_ends_the_run(self, app):
        app.timers["Abra"]["offsets"] = [60_000]
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "started")

        app.on_stop()

        assert wait_for(app, "stopped")["name"] == "Abra"

    def test_the_stop_button_is_what_stops(self, app):
        """Start doubles as Restart while running, so Stop has its own button."""
        app.timers["Abra"]["offsets"] = [60_000]
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "started")

        app.on_stop()

        assert wait_for(app, "stopped")["name"] == "Abra"
        assert app.restarting is False

    def test_closing_stops_the_runner(self, app, closed):
        app.timers["Abra"]["offsets"] = [60_000]
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "started")

        app.on_close()

        assert app.runner.running() is False
        assert closed == [True]


class TestRunControls:
    def test_both_run_buttons_are_live_while_running(self, app):
        app.timers["Abra"]["offsets"] = [60_000]
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "started")
        app.refresh_controls()

        assert app.button_start.cget("text") == "Restart timer"
        assert "disabled" not in app.button_stop.state()

    def test_rows_are_disabled_while_running(self, app):
        app.timers["Abra"]["offsets"] = [60_000]
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "started")
        app.refresh_controls()

        assert all("disabled" in row.radio.state() for row in app.timer_rows)
        assert all("disabled" in row.button.state() for row in app.timer_rows)

    def test_rows_are_enabled_again_afterwards(self, app):
        make_quick(app, "Abra")
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "finished")
        app.runner.join(timeout = 5.0)
        app.refresh_controls()

        assert all("disabled" not in row.radio.state() for row in app.timer_rows)
        assert app.button_start.cget("text") == "Start timer"

    def test_run_panel_is_blank_when_idle(self, app):
        app.refresh_run()

        assert app.label_run.cget("text") == ""

    def test_run_panel_shows_the_running_timer(self, app):
        app.timers["Abra"]["offsets"] = [60_000]
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "started")
        app.refresh_run()

        text = app.label_run.cget("text")

        assert "Abra" in text
        assert "next 60000 ms" in text

    def test_beep_events_reach_the_status_line(self, app):
        make_quick(app, "Abra")
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "finished")

        app.runner.events.put({"kind": "beep", "name": "Abra", "target": 200.0,
                               "planned": 200, "delay": 0.4, "average": 0.4, "remaining": 0})
        app.drain_events()

        assert "Target Beep @ 200" in app.label_status.cget("text")


def press(app, char, keysym = ""):
    event        = tkinter.Event()
    event.char   = char
    event.keysym = keysym
    event.widget = app

    return app.on_key(event)


def bind_for(action):
    return src.settings.binding(src.ui.config["keybinds"], action)


class TestHotkeys:
    def test_start_keybind_starts(self, app):
        make_quick(app, "Abra")
        app.active.set("Abra")

        press(app, bind_for("start_restart"), "Return")

        assert wait_for(app, "started")["name"] == "Abra"

    def test_start_keybind_stops_a_running_timer(self, app):
        app.timers["Abra"]["offsets"] = [60_000]
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "started")

        press(app, bind_for("start_restart"), "Return")

        assert wait_for(app, "stopped")["name"] == "Abra"

    def test_next_moves_the_active_timer_down(self, app):
        press(app, bind_for("next"))

        assert app.active.get() == "Zigzagoon"

    def test_previous_moves_the_active_timer_up(self, app):
        app.active.set("Zigzagoon")

        press(app, bind_for("previous"))

        assert app.active.get() == "Mudkip"

    def test_next_wraps_at_the_end(self, app):
        app.active.set(list(app.timers)[-1])

        press(app, bind_for("next"))

        assert app.active.get() == "Mudkip"

    def test_previous_wraps_at_the_start(self, app):
        press(app, bind_for("previous"))

        assert app.active.get() == list(app.timers)[-1]

    def test_navigation_is_ignored_while_running(self, app):
        app.timers["Abra"]["offsets"] = [60_000]
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "started")

        press(app, bind_for("next"))

        assert app.active.get() == "Abra"

    def test_hotkeys_are_ignored_on_the_offsets_screen(self, app):
        app.on_edit("Mudkip")

        press(app, bind_for("start_restart"), "Return")

        assert app.runner.running() is False

    def test_hotkeys_are_ignored_on_the_settings_tab(self, app):
        app.notebook.select(app.tab_settings)

        press(app, bind_for("next"))

        assert app.active.get() == "Mudkip"


def pump(app, predicate, timeout = 10.0):
    """Drives the Tk event loop until `predicate` holds.

    The restart handover is scheduled with `after`, which never fires without
    a running mainloop, so tests have to turn the loop over themselves.
    """
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        app.root.update()

        if predicate(): return True

        time.sleep(0.01)

    return False


class TestRestart:
    def running_app(self, app, offsets = (60_000,)):
        app.timers["Abra"]["offsets"] = list(offsets)
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "started")
        return app

    def test_button_reads_restart_while_running(self, app):
        self.running_app(app)
        app.refresh_controls()

        assert app.button_start.cget("text") == "Restart timer"

    def test_button_reads_start_when_idle(self, app):
        app.refresh_controls()

        assert app.button_start.cget("text") == "Start timer"

    def test_stop_button_is_disabled_when_idle(self, app):
        app.refresh_controls()

        assert "disabled" in app.button_stop.state()

    def test_stop_button_is_enabled_while_running(self, app):
        self.running_app(app)
        app.refresh_controls()

        assert "disabled" not in app.button_stop.state()

    def test_restart_starts_a_fresh_run(self, app):
        self.running_app(app)
        first = app.runner.snapshot()["start_ns"]

        app.on_start()   # the button doubles as Restart while running

        assert pump(app, lambda: app.runner.running()
                              and app.runner.snapshot()["start_ns"] not in (None, first))

    def test_restart_resets_the_pending_offsets(self, app):
        self.running_app(app, offsets = (60_000, 70_000))
        app.on_shift("add")

        assert app.runner.snapshot()["pending"][0][1] != 60_000

        app.on_start()
        pump(app, lambda: app.runner.running() and app.runner.snapshot()["pending"])

        assert app.runner.snapshot()["pending"][0][1] == 60_000, "the shift should not survive a restart"

    def test_restart_leaves_exactly_one_run_going(self, app):
        self.running_app(app)

        app.on_start()
        pump(app, lambda: not app.restarting)

        assert app.runner.running() is True
        assert app.restarting is False

    def test_the_keybind_restarts(self, app):
        self.running_app(app)
        first = app.runner.snapshot()["start_ns"]

        press(app, bind_for("start_restart"), "Return")

        assert pump(app, lambda: app.runner.running()
                              and app.runner.snapshot()["start_ns"] not in (None, first))

    def test_the_keybind_still_starts_when_idle(self, app):
        make_quick(app, "Abra")
        app.active.set("Abra")

        press(app, bind_for("start_restart"), "Return")

        assert wait_for(app, "started")["name"] == "Abra"

    def test_controls_stay_live_across_the_handover(self, app):
        """The window must not flick back to its idle state mid-restart."""
        self.running_app(app)

        app.on_restart()
        app.refresh_controls()

        assert app.restarting is True
        assert app.button_start.cget("text") == "Restart timer"
        assert "disabled" not in app.button_stop.state()

    def test_stop_button_ends_the_run(self, app):
        self.running_app(app)

        app.on_stop()

        assert wait_for(app, "stopped")["name"] == "Abra"
        assert app.restarting is False

    def test_stop_during_a_restart_cancels_it(self, app):
        self.running_app(app)

        app.on_restart()
        app.on_stop()
        pump(app, lambda: not app.runner.running(), timeout = 5.0)

        assert app.restarting is False

    def test_restart_of_a_finished_run_just_starts(self, app):
        make_quick(app, "Abra")
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "finished")
        app.runner.join(timeout = 5.0)

        app.on_start()

        assert wait_for(app, "started")["name"] == "Abra"


class TestLiveAdjustments:
    def running_app(self, app, offsets = (20_000,)):
        app.timers["Abra"]["offsets"] = list(offsets)
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "started")
        return app

    def test_buttons_exist_for_every_shift(self, app):
        assert list(app.buttons_shift) == ["add", "subtract", "add_all", "subtract_all"]

    def test_shift_buttons_are_disabled_when_idle(self, app):
        app.refresh_controls()

        assert all("disabled" in button.state() for button in app.buttons_shift.values())
        assert "disabled" in app.button_frame.state()

    def test_shift_buttons_are_enabled_while_running(self, app):
        self.running_app(app)
        app.refresh_controls()

        assert all("disabled" not in button.state() for button in app.buttons_shift.values())
        assert "disabled" not in app.button_frame.state()

    def test_add_shifts_the_next_offset(self, app):
        self.running_app(app)

        app.on_shift("add")

        assert app.runner.snapshot()["pending"][0][1] == pytest.approx(20_000 + src.ui.FRAME_MS)
        assert "20000 >>> 20017" in app.label_status.cget("text")

    def test_subtract_shifts_the_other_way(self, app):
        self.running_app(app)

        app.on_shift("subtract")

        assert app.runner.snapshot()["pending"][0][1] == pytest.approx(20_000 - src.ui.FRAME_MS)

    def test_add_all_shifts_every_offset(self, app):
        self.running_app(app, offsets = (20_000, 30_000))

        before = app.runner.snapshot()["pending"]
        app.on_shift("add_all")
        after = app.runner.snapshot()["pending"]

        assert all(new[1] - old[1] == pytest.approx(src.ui.FRAME_MS) for old, new in zip(before, after))
        assert "All Offsets" in app.label_status.cget("text")

    def test_shift_reports_a_refusal(self, app):
        self.running_app(app, offsets = (1100,))

        app.on_shift("add")

        assert "Didn't shift any offset!" in app.label_status.cget("text")
        assert str(app.label_status.cget("foreground")) == "red"

    def test_pending_display_tracks_a_shift(self, app):
        self.running_app(app)

        app.on_shift("add")
        app.refresh_run()

        assert "20017" in app.label_pending.cget("text")

    def test_pending_display_marks_the_next_offset(self, app):
        self.running_app(app, offsets = (20_000, 30_000))
        app.refresh_run()

        assert app.label_pending.cget("text").startswith("> 20000")

    def test_pending_display_is_blank_when_idle(self, app):
        app.refresh_run()

        assert app.label_pending.cget("text") == ""


class TestVariableFrameField:
    def running_app(self, app, offsets = (20_000,)):
        app.timers["Abra"]["offsets"] = list(offsets)
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "started")
        return app

    def test_submitting_appends_an_offset(self, app):
        self.running_app(app)

        app.variable_frame.set("300")
        app.on_submit_frame()

        assert len(app.runner.snapshot()["pending"]) == 2
        assert "appended" in app.label_status.cget("text")

    def test_the_field_clears_after_a_submit(self, app):
        self.running_app(app)

        app.variable_frame.set("300")
        app.on_submit_frame()

        assert app.variable_frame.get() == ""

    def test_an_empty_field_is_reported(self, app):
        self.running_app(app)

        app.on_submit_frame()

        assert "Enter a variable frame" in app.label_status.cget("text")

    def test_a_non_numeric_field_is_reported(self, app):
        self.running_app(app)

        app.variable_frame.set("oops")
        app.on_submit_frame()

        assert "not a number" in app.label_status.cget("text")
        assert app.variable_frame.get() == "oops", "a bad value should stay for editing"

    def test_negative_frames_are_accepted(self, app):
        self.running_app(app)

        app.variable_frame.set("-5")
        app.on_submit_frame()

        assert "not a number" not in app.label_status.cget("text")

    def test_submitting_with_no_run_is_reported(self, app):
        app.variable_frame.set("300")
        app.on_submit_frame()

        assert "No timer is running" in app.label_status.cget("text")

    def test_keybind_submits(self, app):
        self.running_app(app)

        app.variable_frame.set("300")
        press(app, bind_for("variable_frame"))

        assert len(app.runner.snapshot()["pending"]) == 2

    def test_return_in_the_field_does_not_also_start(self, app):
        """The field's Return handler must stop the event reaching on_key."""
        assert app.on_submit_frame() == "break"


class TestShiftHotkeys:
    def running_app(self, app, offsets = (20_000,)):
        app.timers["Abra"]["offsets"] = list(offsets)
        app.active.set("Abra")
        app.on_start()
        wait_for(app, "started")
        return app

    @pytest.mark.parametrize("action, sign", [("add", 1), ("subtract", -1)])
    def test_shift_keybinds_move_the_next_offset(self, app, action, sign):
        self.running_app(app)

        press(app, bind_for(action))

        assert app.runner.snapshot()["pending"][0][1] == pytest.approx(20_000 + sign * src.ui.FRAME_MS)

    @pytest.mark.parametrize("action, sign", [("add_all", 1), ("subtract_all", -1)])
    def test_shift_all_keybinds_move_everything(self, app, action, sign):
        self.running_app(app, offsets = (20_000, 30_000))

        press(app, bind_for(action))

        pending = app.runner.snapshot()["pending"]

        assert pending[0][1] == pytest.approx(20_000 + sign * src.ui.FRAME_MS)
        assert pending[1][1] == pytest.approx(30_000 + sign * src.ui.FRAME_MS)

    def test_rebound_shift_key_works(self, app):
        app.on_capture("add")
        press(app, "k")

        self.running_app(app)
        press(app, "k")

        assert app.runner.snapshot()["pending"][0][1] == pytest.approx(20_000 + src.ui.FRAME_MS)


class TestSettingsTab:
    def test_has_a_row_per_action(self, app):
        assert list(app.keybind_rows) == [action for action, _ in src.settings.ACTIONS]

    def test_covers_every_live_adjustment(self, app):
        for action in ["add", "subtract", "add_all", "subtract_all", "variable_frame"]:
            assert action in app.keybind_rows

    def test_shows_the_configured_binds(self, app):
        assert app.keybind_rows["start_restart"].button.cget("text") == "Enter"
        assert app.keybind_rows["next"].button.cget("text")          == "N"
        assert app.keybind_rows["previous"].button.cget("text")      == "P"

    def test_clicking_begins_capture(self, app):
        app.on_capture("next")

        assert app.capturing == "next"
        assert app.keybind_rows["next"].button.cget("text") == "Press a key..."

    def test_clicking_again_cancels_capture(self, app):
        app.on_capture("next")
        app.on_capture("next")

        assert app.capturing is None
        assert app.keybind_rows["next"].button.cget("text") == "N"

    def test_capturing_rebinds(self, app):
        app.on_capture("next")
        press(app, "k")

        assert src.ui.config["keybinds"]["next"] == "k"
        assert app.capturing is None
        assert app.keybind_rows["next"].button.cget("text") == "K"

    def test_the_new_bind_works_immediately(self, app):
        app.on_capture("next")
        press(app, "k")

        press(app, "k")

        assert app.active.get() == "Zigzagoon"

    def test_capture_ignores_keys_with_no_character(self, app):
        app.on_capture("next")

        press(app, "", "Shift_L")

        assert app.capturing == "next", "a modifier should not end the capture"
        assert src.ui.config["keybinds"]["next"] == "n"

    def test_capture_refuses_a_key_already_bound(self, app):
        app.on_capture("next")

        press(app, src.ui.config["keybinds"]["reset"])

        assert src.ui.config["keybinds"]["next"] == "n"
        assert "already bound to reset" in app.label_status.cget("text")
        assert app.capturing is None

    def test_capture_allows_rebinding_to_the_same_key(self, app):
        app.on_capture("next")
        press(app, "n")

        assert src.ui.config["keybinds"]["next"] == "n"

    def test_rebinding_marks_dirty(self, app):
        app.on_capture("next")
        press(app, "k")

        assert app.dirty() is True

    def test_saving_writes_config_json(self, app):
        app.on_capture("next")
        press(app, "k")
        app.on_save()

        with open(app.config_path) as file_config: saved = json.load(file_config)

        assert saved["keybinds"]["next"] == "k"

    def test_saving_keeps_config_formatting(self, app):
        app.on_save()

        data = app.config_path.read_bytes()

        assert b"\r\n" in data
        assert not data.endswith(b"\n")
        assert b'"start_restart":  "\\r"' in data

    def test_saving_leaves_the_other_config_keys_alone(self, app):
        with open(app.config_path) as file_config: original = json.load(file_config)

        app.on_capture("next")
        press(app, "k")
        app.on_save()

        with open(app.config_path) as file_config: saved = json.load(file_config)

        assert saved["fps"]               == original["fps"]
        assert saved["beep"]              == original["beep"]
        assert saved["print_target_beep"] == original["print_target_beep"]
        assert saved["keybinds"]["reset"] == original["keybinds"]["reset"]

    def test_clean_after_saving(self, app):
        app.on_capture("next")
        press(app, "k")
        app.on_save()

        assert app.dirty() is False
