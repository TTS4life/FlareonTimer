"""Parsing and validation for the offsets editor.

Kept free of tkinter so it can be tested without a display, and free of
src.audio / src.io so the editor never opens an audio stream or starts the
keyboard listener. Serialisation lives in src.jsonfile.
"""

from src.jsonfile import compact

def number(text):
    """The prologue shared by every field: strip, parse, reject nonsense.

    The finite check matters: json.dumps writes inf as `Infinity`, which no
    JSON reader outside Python will accept.
    """
    stripped = text.strip()

    if not stripped: raise ValueError("is empty")

    try: value = float(stripped)
    except ValueError: raise ValueError(f"{stripped!r} is not a number") from None

    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{stripped!r} is not a finite number")

    return value


def parse(text):
    """One offset box. Raises ValueError with a message fit for the UI."""
    value = number(text)

    if value <= 0: raise ValueError(f"{compact(value)} is not above zero")

    return value


def parse_interval(text):
    value = number(text)

    if value <= 0: raise ValueError("must be above zero")

    return compact(value)


def parse_beeps(text):
    value = number(text)

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
    """Non-fatal checks. tests/test_assets.py applies the same two rules to the
    shipped file, so keep them in step."""
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
