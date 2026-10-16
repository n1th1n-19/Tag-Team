"""Accounts via cswap's CLI JSON contract; every change goes through cswap so its locks and token handling apply."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from tagteam import store

_SESSION_DIR = re.compile(r"^(\d+)-")


class CswapError(RuntimeError):
    pass


def find_exe(name: str) -> str | None:
    """Absolute path of a program on PATH, never one in the current directory."""
    found = shutil.which(name)
    if not found or not os.path.isabs(found):
        return None
    if os.path.dirname(os.path.realpath(found)) == os.path.realpath(os.getcwd()):
        return None
    return found


_SCHTASKS = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "schtasks.exe")


def cswap_argv() -> list[str] | None:
    exe = os.environ.get("TAGTEAM_CSWAP") or os.environ.get("SWAPME_CSWAP") or find_exe("cswap")
    if exe:
        return [exe]
    try:
        import claude_swap  # noqa: F401  (installed alongside tagteam)
        return [sys.executable, "-m", "claude_swap"]
    except ImportError:
        return None


def run_cswap(*args: str, stdin: str | None = None, timeout: float = 60) -> subprocess.CompletedProcess:
    base = cswap_argv()
    if base is None:
        raise CswapError("cswap is not installed (uv tool install claude-swap)")
    env = {**os.environ, "NO_COLOR": "1"}
    try:
        return subprocess.run([*base, *args], input=stdin if stdin is not None else "",
                              capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise CswapError(f"cswap {' '.join(args[:2])} timed out after {timeout:.0f}s")


def cswap_json(*args: str, stdin: str | None = None, timeout: float = 60) -> dict:
    proc = run_cswap(*args, stdin=stdin, timeout=timeout)
    text = proc.stdout.strip()
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        raise CswapError((proc.stderr or text or f"cswap exited {proc.returncode}").strip()[:500])
    if isinstance(data, dict) and "error" in data:
        raise CswapError(data["error"].get("message", "cswap error"))
    return data


def _plain(proc: subprocess.CompletedProcess) -> dict:
    """Result of a cswap command that has no --json mode."""
    msg = (proc.stdout + "\n" + proc.stderr).strip()
    msg = re.sub(r"\x1b\[[0-9;]*m", "", msg)
    if proc.returncode != 0:
        raise CswapError(msg[-500:] or f"cswap exited {proc.returncode}")
    return {"ok": True, "message": msg[-500:]}


def cswap_version() -> str | None:
    try:
        proc = run_cswap("--version", timeout=15)
    except CswapError:
        return None
    return proc.stdout.strip().split()[-1] if proc.returncode == 0 and proc.stdout.strip() else None


def list_accounts() -> dict:
    return cswap_json("list", "--json", timeout=45)


def current_identity() -> dict | None:
    """Live login straight from Claude Code's config (no network, no cswap)."""
    try:
        from claude_swap.paths import get_global_config_path
        path = Path(get_global_config_path())
    except Exception:
        base = os.environ.get("CLAUDE_CONFIG_DIR")
        path = Path(base) / ".claude.json" if base else Path.home() / ".claude.json"
    acct = store.read_json(path, {}).get("oauthAccount") or {}
    if not acct.get("emailAddress"):
        return None
    return {"email": acct["emailAddress"], "organizationUuid": acct.get("organizationUuid", ""),
            "organizationName": acct.get("organizationName", "")}


def live_sessions(active_number: str | None) -> list[dict]:
    """Claude Code processes running right now, grouped by the account they run as."""
    try:
        from claude_swap.process_detection import scan_sessions
    except Exception:
        return []
    out = []
    default_home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    targets = [(default_home, active_number, "default")]
    prof_root = store.cswap_backup_root() / "sessions"
    if prof_root.is_dir():
        for prof in prof_root.iterdir():
            m = _SESSION_DIR.match(prof.name)
            if m:
                targets.append((prof, m.group(1), "cswap run"))
    for home, number, kind in targets:
        try:
            sessions, _ = scan_sessions(home)
        except Exception:
            continue
        for s in sessions:
            out.append({"pid": s.pid, "account": number, "profile": kind, "cwd": s.cwd or "",
                        "kind": s.kind, "entrypoint": s.entrypoint, "status": s.status, "sessionId": getattr(s, "session_id", ""),
                        "startedAt": s.started_at})
    return out


def switch(target: str | None = None, strategy: str = "best") -> dict:
    """Tag a partner in: a number, ring name or email; "next" for the next one in line; None for the best."""
    if target == "next":  # the lineup order, skipping anyone at their limit
        target, strategy = None, "next-available"
    args = ["switch", target, "--json"] if target else ["switch", "--strategy", strategy, "--json"]
    result = cswap_json(*args, timeout=90)
    to = result.get("to") or {}
    if to.get("number") is not None:
        store.record_active(str(to["number"]), to.get("email", ""), source="switch")
    return result


def _identity(r: dict) -> tuple:
    return (r.get("email"), r.get("organizationUuid"))


def move(who: str, slot: str) -> dict:
    """Move a partner to another spot in the lineup (cswap move; an occupied spot swaps the two).
    Tag Team's history is keyed by partner number, so it's renumbered to follow each partner."""
    before = {_identity(r): str(r["number"]) for r in list_accounts().get("accounts", [])}
    res = _plain(run_cswap("move", who, str(slot)))
    after = {_identity(r): str(r["number"]) for r in list_accounts().get("accounts", [])}
    renumbered = {old: after[k] for k, old in before.items() if k in after and after[k] != old}
    if renumbered:
        store.renumber(renumbered)
    return {**res, "renumbered": renumbered}


def add_current(alias: str | None = None, slot: int | None = None) -> dict:
    args = ["add"] + (["--alias", alias] if alias else []) + (["--slot", str(slot)] if slot else [])
    # "y" answers cswap's overwrite prompt only when the user picked that slot.
    return _plain(run_cswap(*args, stdin="y\n" if slot else "", timeout=60))


def add_token(token: str, email: str | None = None, slot: int | None = None) -> dict:
    """Token goes on stdin, never argv (argv is visible to every local user)."""
    token = token.strip()
    if not token.startswith("sk-ant-"):
        raise CswapError("That contract doesn't look like a Claude token (expected sk-ant-...)")
    args = ["add-token", "-"] + (["--email", email] if email else []) + (["--slot", str(slot)] if slot else [])
    return _plain(run_cswap(*args, stdin=token + "\n", timeout=60))


def set_alias(number: str, alias: str | None) -> dict:
    args = ["alias", number, alias] if alias else ["alias", number, "--unset"]
    return _plain(run_cswap(*args, timeout=30))


def set_enabled(number: str, enabled: bool) -> dict:
    return _plain(run_cswap("enable" if enabled else "disable", number, timeout=30))


def remove(number: str) -> dict:
    return _plain(run_cswap("remove", number, stdin="y\n", timeout=60))


AUTO_KEYS = {"threshold", "cooldownSeconds", "hysteresisPct", "strategy", "includeApiKeyAccounts", "model", "intervalSeconds"}


def auto_settings() -> dict:
    data = cswap_json("config", "list", "--json", timeout=20)
    return {s["key"].split(".", 1)[1]: s["value"] for s in data.get("settings", [])
            if s["key"].startswith("autoswitch.")}


def set_auto_setting(key: str, value) -> dict:
    if key not in AUTO_KEYS:
        raise CswapError(f"unknown auto setting {key!r}")
    value = str(value).lower() if isinstance(value, bool) else str(value)
    return _plain(run_cswap("config", "set", f"autoswitch.{key}", value, timeout=20))


def auto_once(dry_run: bool = False) -> list[dict]:
    """One cswap autoswitch tick. Returns its JSON events; logs switches."""
    args = ["auto", "--once", "--json"] + (["--dry-run"] if dry_run else [])
    proc = run_cswap(*args, timeout=120)
    events = []
    for line in proc.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        events.append(ev)
        if ev.get("event") == "switch" and not ev.get("dryRun"):
            store.append_event("auto", ev)
            to = ev.get("to") or {}
            if to.get("number") is not None:
                store.record_active(str(to["number"]), to.get("email", ""), source="auto")
    return events


# Corner man: background service that blind-tags even when Claude Code is closed.

SERVICE = ("tag-team-corner-man", "com.tagteam.cornerman")
OLD_SERVICE = ("swap-me-auto", "com.swapme.auto")  # swap-me 0.1; removed on install/uninstall


def _service_cmd() -> list[str]:
    exe = find_exe("tagteam")
    return [exe, "corner-man", "run"] if exe else [sys.executable, "-m", "tagteam", "corner-man", "run"]


def service_path(service: tuple[str, str] = SERVICE) -> Path:
    name, label = service
    if sys.platform == "darwin":
        return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    if sys.platform.startswith("win"):
        return Path(name)  # a Task Scheduler task name, not a file
    return Path.home() / ".config" / "systemd" / "user" / f"{name}.service"


def _remove_service(service: tuple[str, str]) -> None:
    name, _ = service
    if sys.platform == "darwin":
        path = service_path(service)
        subprocess.run(["launchctl", "unload", "-w", str(path)], capture_output=True)
        path.unlink(missing_ok=True)
    elif sys.platform.startswith("win"):
        subprocess.run([_SCHTASKS, "/Delete", "/F", "/TN", name], capture_output=True)
    else:
        subprocess.run(["systemctl", "--user", "disable", "--now", f"{name}.service"], capture_output=True)
        service_path(service).unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)


def service_install() -> dict:
    if service_installed(OLD_SERVICE):
        _remove_service(OLD_SERVICE)
    name, label = SERVICE
    cmd = _service_cmd()
    if sys.platform == "darwin":
        import plistlib
        path = service_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        logs = Path.home() / "Library" / "Logs" / "tag-team-corner-man.log"
        path.write_bytes(plistlib.dumps({
            "Label": label, "ProgramArguments": cmd, "RunAtLoad": True,
            "KeepAlive": True, "StandardOutPath": str(logs), "StandardErrorPath": str(logs),
        }))
        subprocess.run(["launchctl", "unload", str(path)], capture_output=True)
        proc = subprocess.run(["launchctl", "load", "-w", str(path)], capture_output=True, text=True)
    elif sys.platform.startswith("win"):
        line = subprocess.list2cmdline(cmd)
        proc = subprocess.run([_SCHTASKS, "/Create", "/F", "/SC", "ONLOGON", "/RL", "LIMITED",
                               "/TN", name, "/TR", line], capture_output=True, text=True)
        if proc.returncode == 0:
            subprocess.run([_SCHTASKS, "/Run", "/TN", name], capture_output=True)
    else:
        path = service_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "[Unit]\nDescription=Tag Team corner man: blind-tags your Claude accounts before one is worn down\n\n"
            f"[Service]\nExecStart={subprocess.list2cmdline(cmd)}\nRestart=on-failure\nRestartSec=30\n\n"
            "[Install]\nWantedBy=default.target\n", encoding="utf-8")
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        proc = subprocess.run(["systemctl", "--user", "enable", "--now", f"{name}.service"],
                              capture_output=True, text=True)
    if proc.returncode != 0:
        raise CswapError((proc.stderr or proc.stdout).strip()[:500] or "corner man install failed")
    store.set_config(auto={"enabled": True, "mode": "always"})
    return {"ok": True, "message": f"Corner man is in your corner: blind tags keep working with Claude Code closed ({service_path()})"}


def service_uninstall() -> dict:
    for service in (SERVICE, OLD_SERVICE):
        if service_installed(service):
            _remove_service(service)
    store.set_config(auto={"mode": "session"})
    return {"ok": True, "message": "Corner man sent home"}


def service_installed(service: tuple[str, str] = SERVICE) -> bool:
    if sys.platform.startswith("win"):
        return subprocess.run([_SCHTASKS, "/Query", "/TN", service[0]], capture_output=True).returncode == 0
    return service_path(service).exists()


def auto_run_forever() -> None:
    """The service body: cswap's own loop, every event mirrored to auto.jsonl."""
    base = cswap_argv()
    if base is None:
        raise CswapError("cswap is not installed")
    proc = subprocess.Popen([*base, "auto", "--json"], stdout=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    for line in proc.stdout:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("event") in ("switch", "all-exhausted", "account-quarantined", "error"):
            store.append_event("auto", ev)
        if ev.get("event") == "switch":
            to = ev.get("to") or {}
            if to.get("number") is not None:
                store.record_active(str(to["number"]), to.get("email", ""), source="auto")
    sys.exit(proc.wait())
