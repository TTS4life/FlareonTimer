"""Writing the asset files back in the exact style they ship in.

json.dump would reformat both of them: it uses LF, adds a trailing newline,
pads nothing, and splits lists across lines. timers.json and config.json are
hand-maintained and tracked in git, so saving one offset should be a one-line
diff, not a rewrite of the file.

Both files follow the same two rules, so one renderer covers them:
  - keys inside a nested object are padded so the values line up
  - top-level keys are not padded
"""

import json

INDENT = " " * 4

def compact(value):
    """Whole numbers stay ints so timers.json does not churn to floats."""
    return int(value) if float(value).is_integer() else float(value)


def render_value(value):
    """Lists stay on one line, with their numbers compacted."""
    if isinstance(value, list): return "[" + ", ".join(json.dumps(compact(item)) for item in value) + "]"

    return json.dumps(value)


def render(data):
    lines = ["{"]
    names = list(data)

    for index, name in enumerate(names):
        value = data[name]
        comma = "," if index < len(names) - 1 else ""

        if isinstance(value, dict):
            keys  = list(value)
            width = max((len(f"{json.dumps(key)}:") for key in keys), default = 0)

            lines.append(f"{INDENT}{json.dumps(name)}: {{")

            for position, key in enumerate(keys):
                label = f"{json.dumps(key)}:"
                tail  = "," if position < len(keys) - 1 else ""

                lines.append(f"{INDENT * 2}{label:<{width}} {render_value(value[key])}{tail}")

            lines.append(f"{INDENT}}}{comma}")

        else:
            lines.append(f"{INDENT}{json.dumps(name)}: {render_value(value)}{comma}")

    lines.append("}")

    return "\r\n".join(lines)


def save(data, path):
    with open(path, "w", newline = "") as file_data: file_data.write(render(data))
