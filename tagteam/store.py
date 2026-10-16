"""Tag Team's own files under ~/.tag-team (override with TAGTEAM_HOME)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_CONFIG = {
    "threshold": 90,          # the tag-out point: % of 5h/7d stamina that raises TAG ME
    "auto": {"enabled": False, "mode": "session"},   # mode: session | always
    "pricing": {},            # model-prefix -> [input $/M, output $/M, cache-read multiplier]
    "updateCheck": False,     # opt-in: ask GitHub once a day whether a new release is out (tagteam update --notify on)
}


def home() -> Path:
    env = os.environ.get("TAGTEAM_HOME") or os.environ.get("SWAPME_HOME")
    if env:
        return Path(env)
    new, old = Path.home() / ".tag-team", Path.home() / ".swap-me"
    if old.is_dir():
        migrate(old, new)
    return new


def migrate(old: Path, new: Path) -> None:
    """Move swap-me's data into ~/.tag-team: rename, or copy-verify-delete across devices; never overwrites."""
    if not new.exists():
        try:
            os.rename(old, new)
            return
        except OSError:
            pass
    new.mkdir(parents=True, exist_ok=True)
    for item in list(old.iterdir()):
        dest = new / item.name
        if dest.exists():
            continue
        try:
            os.rename(item, dest)
        except OSError:
            tmp = dest.with_name(dest.name + ".migrating")
            shutil.rmtree(tmp, ignore_errors=True) if tmp.is_dir() else tmp.unlink(missing_ok=True)
            if item.is_dir():
                shutil.copytree(item, tmp, symlinks=True)
                if {p.relative_to(item) for p in item.rglob("*")} != {p.relative_to(tmp) for p in tmp.rglob("*")}:
                    shutil.rmtree(tmp, ignore_errors=True)
                    raise OSError(f"could not copy {item} to {dest}; nothing was changed")
            else:
                shutil.copy2(item, tmp)
            os.rename(tmp, dest)
    shutil.rmtree(old, ignore_errors=True)


def cswap_backup_root() -> Path:
    """cswap's data dir. Reuses cswap's own resolver when it is importable."""
    try:
        from claude_swap.paths import get_backup_root
        return Path(get_backup_root())
    except Exception:
        if sys.platform.startswith("linux"):
            base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
            return Path(base) / "claude-swap"
        return Path.home() / ".claude-swap-backup"


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> None:
    """Atomic write, 0600 (mkstemp creates it private, so there's no window)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def config() -> dict:
    data = read_json(home() / "config.json", {})
    merged = {**DEFAULT_CONFIG, **data}
    merged["auto"] = {**DEFAULT_CONFIG["auto"], **data.get("auto", {})}
    return merged


def set_config(**changes) -> dict:
    cfg = config()
    for key, value in changes.items():
        if key == "auto":
            cfg["auto"].update(value)
        else:
            cfg[key] = value
    write_json(home() / "config.json", cfg)
    return cfg


def timeline() -> list[dict]:
    path = home() / "timeline.jsonl"
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    return out


def record_active(account: str | None, email: str = "", source: str = "seen", ts: float | None = None) -> None:
    """Append to the who-was-active-when log, only when the account changed."""
    if not account:
        return
    entries = timeline()
    if entries and str(entries[-1].get("account")) == str(account):
        return
    path = home() / "timeline.jsonl"
    _append(path, {"ts": ts or time.time(), "account": str(account), "email": email, "source": source})


def append_event(name: str, event: dict) -> None:
    _append(home() / f"{name}.jsonl", event)


def _append(path: Path, entry: dict) -> None:
    """Append one JSON line to a private (0600) log."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def tail_events(name: str, limit: int = 20) -> list[dict]:
    path = home() / f"{name}.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out
