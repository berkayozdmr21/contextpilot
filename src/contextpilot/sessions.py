"""Explicit, acknowledged, expiring context baselines. No invisible model memory."""

import difflib
import json
import re
import secrets
import time
import math
from pathlib import Path
from .safety import state_file
from .engine import digest

TTL = 4 * 60 * 60


def session_path(root, session_id):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", session_id):
        raise ValueError("Session id must be 1–64 letters, digits, underscores or hyphens.")
    return state_file(Path(root).resolve(), "session-" + session_id + ".json")


def write(path, data):
    # Same-directory replacement; no partially written JSON on normal interruption.
    temp = path.with_name(path.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def create(root, session_id):
    path = session_path(root, session_id)
    if path.exists():
        raise ValueError("Session exists; choose a fresh id for a new chat.")
    now = time.time()
    data = {
        "schema": 1,
        "created": now,
        "expires": now + TTL,
        "generation": 0,
        "acknowledged": {},
        "pending": None,
    }
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream)
    return {
        "session": session_id,
        "expiresInSeconds": TTL,
        "instruction": "Use only in this chat. Acknowledge a receipt only after reading its pack.",
    }


def load(root, session_id):
    path = session_path(root, session_id)
    if not path.exists():
        raise ValueError("Unknown session. Create it with session-start first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("schema") != 1
        or not isinstance(data.get("acknowledged"), dict)
        or not isinstance(data.get("expires"), (int, float))
        or not math.isfinite(data["expires"])
    ):
        raise ValueError("Invalid session state; use a new session id.")
    if time.time() >= data.get("expires", 0):
        raise ValueError("Session expired. Start a new id and send full context again.")
    return data


def propose(root, session_id, index, selected):
    data = load(root, session_id)
    # Only files fully shown are acknowledged; partial windows can never suppress unseen lines.
    baseline = dict(data["acknowledged"])
    for row in selected:
        entry = index["files"][row["path"]]
        if row.get("complete"):
            if row["path"] in baseline or len(baseline) < 100:
                proposed = dict(baseline)
                proposed[row["path"]] = {"sha": entry["sha"], "text": entry["text"]}
                if sum(len(v.get("text", "")) for v in proposed.values()) <= 8_000_000:
                    baseline = proposed
    receipt = secrets.token_hex(12)
    data["pending"] = {"receipt": receipt, "generation": data["generation"], "baseline": baseline}
    write(session_path(root, session_id), data)
    return receipt


def acknowledge(root, session_id, receipt):
    data = load(root, session_id)
    pending = data.get("pending")
    if not pending or not secrets.compare_digest(str(pending.get("receipt", "")), receipt):
        raise ValueError("Receipt is stale or unknown. A newer pack may have replaced it.")
    if pending.get("generation") != data["generation"]:
        raise ValueError("Session generation changed.")
    data["acknowledged"] = pending["baseline"]
    data["pending"] = None
    data["generation"] += 1
    write(session_path(root, session_id), data)
    return {
        "session": session_id,
        "acknowledgedFiles": len(data["acknowledged"]),
        "generation": data["generation"],
    }


def delta_view(data, path, entry):
    before = data["acknowledged"].get(path)
    if not before:
        return None
    if (
        not isinstance(before, dict)
        or not isinstance(before.get("text"), str)
        or digest(before["text"]) != before.get("sha")
    ):
        raise ValueError("Session baseline fingerprint mismatch; use a new session.")
    if before.get("sha") == entry["sha"]:
        return {
            "kind": "unchanged",
            "text": "Previously acknowledged COMPLETE file unchanged; reference only.\n",
            "complete": True,
        }
    old = before.get("text", "")
    parts = difflib.unified_diff(
        old.splitlines(keepends=True),
        entry["text"].splitlines(keepends=True),
        fromfile="acknowledged/" + path,
        tofile="current/" + path,
        n=3,
    )
    diff = "".join(
        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in parts
    )
    return {"kind": "changed", "text": diff, "complete": True}
