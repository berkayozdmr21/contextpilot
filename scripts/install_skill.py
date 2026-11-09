"""Self-contained skill install; explicit updates verify ownership and require a backup."""

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
from pathlib import Path


def fingerprint(data):
    return hashlib.sha256(data).hexdigest()


def checked(destination, relative):
    p = Path(relative)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError("Unsafe installed manifest path.")
    target = destination / p
    for current in (
        destination,
        *[destination / Path(*p.parts[: i + 1]) for i in range(len(p.parts))],
    ):
        if current.is_symlink() or (
            current.exists()
            and getattr(current.lstat(), "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024)
        ):
            raise ValueError("Refusing a linked installation path.")
    return target


def install(destination, update=False, backup=None):
    root = Path(__file__).resolve().parents[1]
    destination = Path(destination).expanduser().absolute()
    if destination.name != "contextpilot":
        raise ValueError("Destination folder must be named contextpilot.")
    payload = {}
    for p in (root / "skills/contextpilot").rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            payload[p.relative_to(root / "skills/contextpilot").as_posix()] = p.read_bytes()
    for p in (root / "src/contextpilot").glob("*.py"):
        payload["scripts/contextpilot/" + p.name] = p.read_bytes()
    version = re.search(
        r'__version__\s*=\s*"([^\"]+)"', (root / "src/contextpilot/__init__.py").read_text()
    ).group(1)
    old = {}
    exists = destination.exists() or destination.is_symlink()
    if exists and not update:
        raise ValueError(
            "Destination already exists. Use --update with --backup for a verified update."
        )
    if update:
        if not exists or not backup:
            raise ValueError(
                "Update requires an existing install and an explicit --backup destination."
            )
        manifest_path = checked(destination, "installation.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        old = manifest.get("files", {})
        if not old:
            raise ValueError("No owned installation manifest found.")
        for name, sha in old.items():
            p = checked(destination, name)
            if not p.is_file() or fingerprint(p.read_bytes()) != sha:
                raise ValueError(
                    "Installed file was changed locally; refusing to overwrite: " + name
                )
        for name in payload:
            p = checked(destination, name)
            if name not in old and p.exists():
                raise ValueError("Unowned file blocks update: " + name)
        backup = Path(backup).expanduser().absolute()
        if backup.exists() or backup == destination or destination in backup.parents:
            raise ValueError("Backup must be a new directory outside the installed skill.")
        backup.mkdir(parents=True)
        for name in [*old, "installation.json"]:
            target = backup / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(checked(destination, name), target)
    else:
        destination.mkdir(parents=True)
    written = []
    try:
        for name, content in payload.items():
            target = checked(destination, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + "." + secrets.token_hex(6) + ".tmp")
            try:
                temp.write_bytes(content)
                temp.replace(target)
                written.append(name)
            finally:
                if temp.exists():
                    temp.unlink()
        hashes = {**old, **{name: fingerprint(content) for name, content in payload.items()}}
        manifest_target = checked(destination, "installation.json")
        manifest_temp = manifest_target.with_name("installation." + secrets.token_hex(6) + ".tmp")
        try:
            manifest_temp.write_text(
                json.dumps({"version": version, "files": hashes}, indent=2), encoding="utf-8"
            )
            manifest_temp.replace(manifest_target)
        finally:
            if manifest_temp.exists():
                manifest_temp.unlink()
    except Exception:
        for name in reversed(written):
            target = checked(destination, name)
            if name in old:
                shutil.copyfile(backup / name, target)
            elif target.is_file():
                target.unlink()
        raise
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    parser.add_argument("--destination", default=str(home / "skills/contextpilot"))
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--backup", help="New backup directory outside the installed skill")
    args = parser.parse_args()
    try:
        print(install(args.destination, args.update, args.backup))
    except (ValueError, OSError) as e:
        parser.exit(2, str(e) + "\n")
