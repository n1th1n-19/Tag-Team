"""Updates: check GitHub for a newer release and re-run its checksum-verified installer; optional weekly auto-update."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from tagteam import __version__, store
from tagteam.accounts import _SCHTASKS, CswapError, find_exe

REPO = "n1th1n-19/Tag-Team"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
JOB = ("tag-team-update", "com.tagteam.update")


def parse_version(v: str) -> tuple[int, ...]:
    """'v0.3.0' -> (0, 3, 0); anything after a non-numeric part is ignored."""
    nums = []
    for part in v.strip().lstrip("vV").split("."):
        m = re.match(r"\d+", part)
        if not m:
            break
        nums.append(int(m.group()))
    return tuple(nums)


def _get(url: str, timeout: float = 20) -> bytes:
    if not url.startswith("https://"):
        raise CswapError(f"refusing a non-HTTPS download: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": f"tagteam/{__version__}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def check() -> dict:
    """The newest release on GitHub, and whether it's newer than this install."""
    try:
        data = json.loads(_get(LATEST_API))
    except OSError as e:
        raise CswapError(f"couldn't reach GitHub to check for updates: {e}") from e
    tag = data.get("tag_name") or ""
    newer = parse_version(tag) > parse_version(__version__)
    msg = (f"Tag Team {tag} is out (you have {__version__}). Run `tagteam update`." if newer
           else f"Tag Team {__version__} is the latest.")
    return {"ok": True, "current": __version__, "latest": tag, "updateAvailable": newer, "url": data.get("html_url"), "message": msg}


def update(force: bool = False, quiet: bool = False) -> dict:
    """Install the newest release with its own installer (checksums verified before anything runs)."""
    info = check()
    if not info["updateAvailable"] and not force:
        return info
    tag = info["latest"]
    win = sys.platform.startswith("win")
    asset = "get.ps1" if win else "get.sh"
    script = _get(f"https://github.com/{REPO}/releases/download/{tag}/{asset}")
    env = {**os.environ, "TAGTEAM_VERSION": tag}
    tmp = Path(tempfile.mkdtemp(prefix="tag-team-update-"))
    path = tmp / asset
    path.write_bytes(script)
    if win:
        # tagteam.exe is in use while this runs, so the installer finishes in its own window after we exit.
        ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        subprocess.Popen([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)], env=env,
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0), close_fds=True)
        res = {"ok": True, "current": __version__, "latest": tag, "updated": "started",
               "message": f"Updating to {tag} in a new window. Open a new terminal when it's done."}
    else:
        bash = find_exe("bash") or "/bin/bash"
        proc = subprocess.run([bash, str(path)], env=env, cwd=str(tmp),
                              stdout=subprocess.PIPE if quiet else None, stderr=subprocess.STDOUT if quiet else None, text=True)
        if proc.returncode != 0:
            raise CswapError(f"update to {tag} failed (installer exit {proc.returncode})"
                             + (f": {proc.stdout[-400:]}" if quiet and proc.stdout else ""))
        res = {"ok": True, "current": __version__, "latest": tag, "updated": True, "message": f"Updated {__version__} -> {tag.lstrip('vV')}."}
    store.append_event("update", {"from": __version__, "to": tag, "at": time.time()})
    return res


# Auto-update: a weekly scheduled job running `tagteam update --auto`.

def _job_cmd() -> list[str]:
    exe = find_exe("tagteam")
    return [exe, "update", "--auto"] if exe else [sys.executable, "-m", "tagteam", "update", "--auto"]


def _job_files() -> list[Path]:
    name, label = JOB
    if sys.platform == "darwin":
        return [Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"]
    if sys.platform.startswith("win"):
        return []
    unit = Path.home() / ".config" / "systemd" / "user"
    return [unit / f"{name}.service", unit / f"{name}.timer"]


def auto_update_status() -> dict:
    name, _ = JOB
    if sys.platform.startswith("win"):
        on = subprocess.run([_SCHTASKS, "/Query", "/TN", name], capture_output=True).returncode == 0
    else:
        on = all(p.exists() for p in _job_files())
    return {"ok": True, "enabled": on, "message": "Auto-update is on (weekly)." if on else "Auto-update is off."}


def auto_update_on() -> dict:
    name, label = JOB
    cmd = _job_cmd()
    if sys.platform == "darwin":
        import plistlib
        path = _job_files()[0]
        path.parent.mkdir(parents=True, exist_ok=True)
        logs = Path.home() / "Library" / "Logs" / "tag-team-update.log"
        path.write_bytes(plistlib.dumps({
            "Label": label, "ProgramArguments": cmd, "RunAtLoad": False,
            "StartCalendarInterval": {"Weekday": 1, "Hour": 12, "Minute": 0},
            "StandardOutPath": str(logs), "StandardErrorPath": str(logs),
        }))
        subprocess.run(["launchctl", "unload", str(path)], capture_output=True)
        proc = subprocess.run(["launchctl", "load", "-w", str(path)], capture_output=True, text=True)
    elif sys.platform.startswith("win"):
        proc = subprocess.run([_SCHTASKS, "/Create", "/F", "/SC", "WEEKLY", "/D", "MON", "/ST", "12:00", "/RL", "LIMITED",
                               "/TN", name, "/TR", subprocess.list2cmdline(cmd)], capture_output=True, text=True)
    else:
        service, timer = _job_files()
        service.parent.mkdir(parents=True, exist_ok=True)
        service.write_text("[Unit]\nDescription=Tag Team: install the newest release if there is one\n\n"
                           f"[Service]\nType=oneshot\nExecStart={subprocess.list2cmdline(cmd)}\n", encoding="utf-8")
        timer.write_text("[Unit]\nDescription=Tag Team weekly update check\n\n"
                         "[Timer]\nOnCalendar=weekly\nPersistent=true\nRandomizedDelaySec=1h\n\n"
                         "[Install]\nWantedBy=timers.target\n", encoding="utf-8")
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        proc = subprocess.run(["systemctl", "--user", "enable", "--now", f"{name}.timer"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise CswapError((proc.stderr or proc.stdout).strip()[:500] or "auto-update setup failed")
    return {"ok": True, "enabled": True,
            "message": "Auto-update is on: once a week Tag Team checks GitHub and installs a newer release (checksums verified)."}


def auto_update_off() -> dict:
    name, _ = JOB
    if sys.platform == "darwin":
        for p in _job_files():
            subprocess.run(["launchctl", "unload", "-w", str(p)], capture_output=True)
            p.unlink(missing_ok=True)
    elif sys.platform.startswith("win"):
        subprocess.run([_SCHTASKS, "/Delete", "/F", "/TN", name], capture_output=True)
    else:
        subprocess.run(["systemctl", "--user", "disable", "--now", f"{name}.timer"], capture_output=True)
        for p in _job_files():
            p.unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    return {"ok": True, "enabled": False, "message": "Auto-update is off."}
