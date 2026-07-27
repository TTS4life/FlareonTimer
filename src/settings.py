"""Keybind handling for config.json.

Kept free of tkinter so it can be tested without a display. Serialisation
lives in src.jsonfile.
"""

# the keybinds the window exposes, in the order the settings tab shows them
ACTIONS = [
    ("start_restart",  "Start timer"),
    ("previous",       "Previous timer"),
    ("next",           "Next timer"),
    ("add",            "Offset +1 frame"),
    ("subtract",       "Offset -1 frame"),
    ("add_all",        "All offsets +1 frame"),
    ("subtract_all",   "All offsets -1 frame"),
    ("variable_frame", "Submit variable frame"),
]

# config.json shipped without a "previous" bind, so the window supplies one
FALLBACKS = {"previous": "p"}

NAMED = {
    "\r":   "Enter",
    "\n":   "Enter",
    "\x1b": "Esc",
    " ":    "Space",
    "\t":   "Tab",
    "\x08": "Backspace",
    "\x7f": "Delete",
}


def describe(key):
    """A readable name for a keybind character."""
    if key in NAMED: return NAMED[key]

    if len(key) == 1 and key.isprintable():
        return key.upper() if key.isalpha() else key

    return repr(key)


def binding(keybinds, action):
    """The key bound to `action`, or "" when nothing is. Callers must not treat
    "" as a match - a modifier keypress also carries no character."""
    return keybinds.get(action, FALLBACKS.get(action, ""))


def usable(key):
    """Whether a keypress can be stored as a bind."""
    return bool(key) and (key in NAMED or (len(key) == 1 and key.isprintable()))


def conflict(keybinds, action, key):
    """The action already using `key`, or None. Guards the distinctness that
    src/main.py relies on to tell its branches apart."""
    for name, value in keybinds.items():
        if name != action and value == key: return name

    return None
