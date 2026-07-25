"""Parsing, validation and serialisation for the offsets editor.

Kept free of tkinter so it can be tested without a display, and free of
src.audio / src.io so the editor never opens an audio stream or starts the
keyboard listener.
"""

import json

INDENT_TIMER = " " * 4
INDENT_FIELD = " " * 8

def compact(value):
    """Whole numbers stay ints so timers.json does not churn to floats."""
    return int(value) if float(value).is_integer() else float(value)


def parse(text):
    """Parse one offset box. Raises ValueError with a message fit for the UI."""
    stripped = text.strip()

    if not stripped: raise ValueError("is empty")

    try: value = float(stripped)
    except ValueError: raise ValueError(f"{stripped!r} is not a number") from None

    if value != value or value in (float("inf"), float("-inf")): raise ValueError(f"{stripped!r} is not a finite number")
    if value <= 0: raise ValueError(f"{compact(value)} is not above zero")

    return value


def parse_interval(text):
    stripped = text.strip()

    if not stripped: raise ValueError("is empty")

    try: value = float(stripped)
    except ValueError: raise ValueError(f"{stripped!r} is not a number") from None

    if value <= 0: raise ValueError("must be above zero")

    return compact(value)


def parse_beeps(text):
    stripped = text.strip()

    if not stripped: raise ValueError("is empty")

    try: value = float(stripped)
    except ValueError: raise ValueError(f"{stripped!r} is not a number") from None

    if not value.is_integer(): raise ValueError("must be a whole number")
    if value < 1:              raise ValueError("must be at least 1")

    return int(value)


def parse_all(texts):
    """Returns (offsets, errors). Errors are labelled by 1-based row."""
    offsets = []
    errors  = []

    for index, text in enumerate(texts, start = 1):
        try: offsets.append(parse(text))
        except ValueError as error: errors.append(f"Offset {index} {error}")

    return offsets, errors


def duplicates(offsets):
    seen     = set()
    repeated = []

    for offset in offsets:
        if offset in seen and offset not in repeated: repeated.append(offset)
        seen.add(offset)

    return repeated


def lead_in(interval, number_beeps):
    return interval * (number_beeps - 1)


def warnings(offsets, interval, number_beeps):
    """Non-fatal checks, mirroring the ones in tests/test_assets.py."""
    messages = []
    ordered  = sorted(offsets)
    lead     = lead_in(interval, number_beeps)

    if ordered and ordered[0] <= lead:
        messages.append(
            f"First offset {compact(ordered[0])} ms would start its beep sequence "
            f"at {compact(ordered[0] - lead)} ms, before the timer begins."
        )

    tight = [(before, after) for before, after in zip(ordered, ordered[1:]) if after - before <= lead]

    if tight:
        pairs = ", ".join(f"{compact(before)} to {compact(after)}" for before, after in tight)
        messages.append(f"Offsets closer together than the {compact(lead)} ms beep sequence: {pairs}.")

    return messages


def render(timers):
    """Serialise in the exact style of the shipped timers.json: aligned keys,
    offsets inline, CRLF endings and no trailing newline."""
    lines = ["{"]
    names = list(timers)

    for index, name in enumerate(names):
        configuration = timers[name]
        keys          = list(configuration)
        width         = max(len(f"{json.dumps(key)}:") for key in keys)

        lines.append(f"{INDENT_TIMER}{json.dumps(name)}: {{")

        for position, key in enumerate(keys):
            value = configuration[key]

            if key == "offsets": rendered = "[" + ", ".join(json.dumps(compact(offset)) for offset in value) + "]"
            else:                rendered = json.dumps(value)

            label = f"{json.dumps(key)}:"
            comma = "," if position < len(keys) - 1 else ""

            lines.append(f"{INDENT_FIELD}{label:<{width}} {rendered}{comma}")

        lines.append(f"{INDENT_TIMER}}}" + ("," if index < len(names) - 1 else ""))

    lines.append("}")

    return "\r\n".join(lines)


def save(timers, path):
    with open(path, "w", newline = "") as file_timers: file_timers.write(render(timers))
