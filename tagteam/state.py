"""The one snapshot every surface draws: `tagteam state --json`."""

from __future__ import annotations

import time
from datetime import datetime

from tagteam import __version__, accounts, art, store, tokens, updater
from tagteam.rules import RULES

SCHEMA_VERSION = 1


def peak_pct(row: dict) -> float | None:
    usage = row.get("usage") or row.get("lastGoodUsage") or {}
    pcts = [w.get("pct") for w in (usage.get("fiveHour"), usage.get("sevenDay")) if w]
    pcts += [w.get("pct") for w in usage.get("scoped") or []]
    pcts = [p for p in pcts if isinstance(p, (int, float))]
    return max(pcts) if pcts else None


def label(row: dict) -> str:
    return row.get("alias") or row.get("email", "").split("@")[0] or f"Account-{row.get('number')}"


def _seed_timeline(active: str, email: str) -> None:
    """First run: cswap's sequence.json says when the current account became active."""
    if store.timeline():
        return
    seq = store.read_json(store.cswap_backup_root() / "sequence.json", {})
    ts = None
    try:
        ts = datetime.fromisoformat(str(seq.get("lastUpdated", "")).replace("Z", "+00:00")).timestamp()
    except ValueError:
        pass
    store.record_active(active, email, source="seed", ts=ts)


def best_candidate(rows: list[dict], threshold: float) -> dict | None:
    """Most headroom among switchable, measured, under-threshold accounts."""
    pool = [r for r in rows if not r.get("active") and not r.get("disabled")
            and r.get("usageStatus") == "ok" and (r.get("peakPct") is not None) and r["peakPct"] < threshold]
    return min(pool, key=lambda r: r["peakPct"], default=None)


def build() -> dict:
    cfg = store.config()
    threshold = float(cfg.get("threshold", 90))
    errors: list[str] = []
    version = accounts.cswap_version()
    listing: dict = {}
    if version:
        try:
            listing = accounts.list_accounts()
        except accounts.CswapError as e:
            errors.append(str(e))
    rows = listing.get("accounts", [])
    identity = accounts.current_identity()
    active_row = next((r for r in rows if r.get("active")), None)
    if active_row:
        _seed_timeline(str(active_row["number"]), active_row.get("email", ""))
        store.record_active(str(active_row["number"]), active_row.get("email", ""))

    known = [str(r["number"]) for r in rows]
    tok = tokens.compute(store.timeline(), known, cfg.get("pricing"))
    sessions = accounts.live_sessions(str(active_row["number"]) if active_row else None)
    live_ids = {s["sessionId"] for s in sessions if s.get("sessionId")}
    for m in tok["matches"]:
        m["live"] = m["id"] in live_ids

    for r in rows:
        num = str(r["number"])
        r["label"] = label(r)
        r["peakPct"] = peak_pct(r)
        r["nearLimit"] = r["peakPct"] is not None and r["peakPct"] >= threshold
        r["tokens"] = tok["totals"].get(num) or tokens.totals({}, num, datetime.now().date())
        r["liveSessions"] = sum(1 for s in sessions if s["account"] == num)

    best = best_candidate(rows, threshold)
    alerts = []
    if active_row and active_row["nearLimit"]:
        alerts.append({
            "kind": "near-limit", "account": active_row["number"], "pct": active_row["peakPct"],
            "ko": active_row["peakPct"] >= 100,
            "message": (f"{active_row['label']} is down for the count ({active_row['peakPct']:.0f}%)" if active_row["peakPct"] >= 100
                        else f"{active_row['label']} is worn down ({active_row['peakPct']:.0f}%)"),
            "suggest": {"number": best["number"], "label": best["label"], "pct": best["peakPct"]} if best else None,
        })
    for r in rows:
        exp = r.get("loginExpiresAt")
        if exp:
            try:
                left = datetime.fromisoformat(exp.replace("Z", "+00:00")).timestamp() - time.time()
            except ValueError:
                continue
            if left < 3 * 86400:
                alerts.append({"kind": "login-expiring", "account": r["number"],
                               "message": f"{r['label']}'s contract (login) runs out in {max(left, 0) / 3600:.0f}h. Log in again and re-sign them"})
        if r.get("usageStatus") == "relogin_required":
            alerts.append({"kind": "relogin", "account": r["number"],
                           "message": f"{r['label']} is injured: their saved login is dead. Log in again and re-sign them"})
    new = updater.cached_check()
    if new and new["available"]:
        alerts.append({"kind": "update", "account": None, "latest": new["latest"],
                       "message": f"Tag Team {new['latest']} is out (you have {__version__}). Run `tagteam update` to get it"})

    unmanaged = identity is not None and active_row is None
    setup = [
        {"id": "cswap", "ok": bool(version), "label": "claude-swap in the locker room" + (f" ({version})" if version else " (not installed)"),
         "fix": "uv tool install claude-swap"},
        {"id": "managed", "ok": not unmanaged and identity is not None,
         "label": "Your current login is signed to the roster" if not unmanaged else f"Your current login {identity['email']} isn't signed yet",
         "fix": "save-current"},
        {"id": "two", "ok": len(rows) >= 2,
         "label": f"{len(rows)} partners on the roster" if len(rows) >= 2 else f"{len(rows)} partner signed. Sign one more to tag",
         "fix": "login-another"},
    ]

    try:
        auto_settings = accounts.auto_settings() if version else {}
    except accounts.CswapError:
        auto_settings = {}

    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": time.time(),
        "threshold": threshold,
        "cswap": {"installed": bool(version), "version": version},
        "errors": errors,
        "active": {
            "number": active_row["number"] if active_row else None,
            "label": active_row["label"] if active_row else (identity or {}).get("email"),
            "email": (identity or {}).get("email"),
            "managed": active_row is not None,
        },
        "accounts": rows,
        "best": {"number": best["number"], "label": best["label"], "pct": best["peakPct"]} if best else None,
        "sessions": sessions,
        "tokens": tok,
        "alerts": alerts,
        "setup": setup,
        "rules": RULES,
        "mascot": {"palette": art.mascot()["palette"], "icon": art.mascot()["frames"]["mascot/icon"]},
        "auto": {**cfg["auto"], "serviceInstalled": accounts.service_installed(),
                 "settings": auto_settings, "recent": store.tail_events("auto", 15)},
    }
