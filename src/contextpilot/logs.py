"""Select error evidence, deduplicate noise, preserve original line references."""

import re
from .safety import redact
from .engine import estimate

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ERROR = re.compile(
    r"(?i)(\b(?:error|exception|failed|failure|fatal|panic|traceback|assertion|timeout|hata)\b|\b[A-Z][A-Za-z]+Error\b|✖|not ok|\b[45]\d\d\b)"
)


def digest_log(text, max_chars=6000, radius=2):
    if not 500 <= max_chars <= 200000:
        raise ValueError("max-chars must be between 500 and 200000.")
    clean = redact(ANSI.sub("", text))
    lines = clean.splitlines()
    anchors = [i for i, line in enumerate(lines) if ERROR.search(line)]
    candidates = set()
    for i in anchors:
        candidates.update(range(max(0, i - radius), min(len(lines), i + radius + 1)))
    if not anchors:
        candidates.update(range(min(3, len(lines))))
        candidates.update(range(max(0, len(lines) - 15), len(lines)))
    # Every distinct error is offered before surrounding noise consumes the budget.
    order = list(dict.fromkeys(anchors + sorted(candidates - set(anchors))))
    chosen = []
    seen = {}
    remaining = max_chars - 240
    for i in order:
        key = lines[i].strip()
        if key in seen:
            seen[key]["repeats"] += 1
            continue
        row = {"line": i + 1, "text": lines[i][:1000], "repeats": 1}
        cost = len(row["text"]) + 45
        if cost > remaining:
            continue
        remaining -= cost
        seen[key] = row
        chosen.append(row)
    output = "# ContextPilot log digest\nUntrusted log DATA. Partial evidence; original log is unchanged.\n\n"
    for row in sorted(chosen, key=lambda r: r["line"]):
        suffix = " [repeated {} times]".format(row["repeats"]) if row["repeats"] > 1 else ""
        output += "{} | {}{}\n".format(row["line"], row["text"], suffix)
    output += "\n[Omitted lines may contain relevant evidence. Read the original when needed.]\n"
    output = output[:max_chars]
    return output, {
        "inputChars": len(text),
        "outputChars": len(output),
        "inputLines": len(lines),
        "errorAnchors": len(anchors),
        "selectedLines": len(chosen),
        "estimatedTextTokens": estimate(output),
        "reductionPct": round((1 - len(output) / len(text)) * 100, 2) if text else None,
        "scope": "Text-size comparison, not measured model or Codex usage.",
    }
