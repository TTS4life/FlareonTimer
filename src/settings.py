"""Keybind handling and serialisation for config.json.

Kept free of tkinter so it can be tested without a display.
"""

import json

INDENT = " " * 4

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
    "\r":     "Enter",
    "\n":     "Enter",
    "\x1b":   "Esc",
    " ":      "Space",
    "\t":     "Tab",
    "\x08":   "Backspace",
    "\x7f":   "Delete",
}


def describe(key):
    """A readable name for a keybind character."""
    if key in NAMED: return NAMED[key]

    if len(key) == 1 and key.isprintable():
        return key.upper() if key.isalpha() else key

    return repr(key)


def binding(keybinds, action):
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


def render(config):
    """Serialise in the style of the shipped config.json: nested objects align
    their keys, the top level does not, CRLF endings, no trailing newline."""
    lines = ["{"]
    names = list(config)

    for index, name in enumerate(names):
        value = config[name]
        comma = "," if index < len(names) - 1 else ""

        if isinstance(value, dict):
            keys  = list(value)
            width = max((len(f"{json.dumps(key)}:") for key in keys), default = 0)

            lines.append(f"{INDENT}{json.dumps(name)}: {{")

            for position, key in enumerate(keys):
                label = f"{json.dumps(key)}:"
                tail  = "," if position < len(keys) - 1 else ""

                lines.append(f"{INDENT * 2}{label:<{width}} {json.dumps(value[key])}{tail}")

            lines.append(f"{INDENT}}}{comma}")

        else:
            lines.append(f"{INDENT}{json.dumps(name)}: {json.dumps(value)}{comma}")

    lines.append("}")

    return "\r\n".join(lines)


def save(config, path):
    with open(path, "w", newline = "") as file_config: file_config.write(render(config))
