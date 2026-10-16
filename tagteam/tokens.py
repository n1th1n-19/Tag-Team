"""Token usage from Claude Code transcripts, deduped by message id and kept in a ledger that survives cleanup."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from tagteam import store

# USD per 1M tokens (input, output, cache-read multiplier); cache writes 1.25x/2x input; override in config "pricing".
PRICING: dict[str, tuple[float, float, float]] = {
    "claude-fable-5-1": (10.0, 50.0, 0.025),
    "claude-mythos-5-1": (10.0, 50.0, 0.025),
    "claude-fable-5": (10.0, 50.0, 0.1),
    "claude-mythos-5": (10.0, 50.0, 0.1),
    "claude-opus-5-5": (4.0, 20.0, 0.05),
    "claude-opus-5": (5.0, 25.0, 0.1),
    "claude-opus-4": (5.0, 25.0, 0.1),
    "claude-sonnet-5-5": (2.0, 10.0, 0.1),
    "claude-sonnet-5": (2.0, 10.0, 0.1),
    "claude-sonnet-4": (3.0, 15.0, 0.1),
    "claude-haiku-5-5": (0.10, 0.50, 0.1),
    "claude-haiku-4": (1.0, 5.0, 0.1),
    # ponytail: family fallbacks for unlisted ids; exact retired-model prices go in config "pricing".
    "claude-opus": (5.0, 25.0, 0.1),
    "claude-sonnet": (3.0, 15.0, 0.1),
    "claude-haiku": (1.0, 5.0, 0.1),
    "claude-fable": (10.0, 50.0, 0.1),
}

UNATTRIBUTED = "?"  # shown as "before the bell": usage from before tracking began
# Row = [key, ts, model, input, output, cache_write_5m, cache_write_1h, cache_read, project, session]
_IN, _OUT, _CW5, _CW1, _CR = 3, 4, 5, 6, 7
_SESSION_DIR = re.compile(r"^(\d+)-")


def price_for(model: str, overrides: dict | None = None) -> tuple[float, float, float]:
    table = {**PRICING, **{k: tuple(v) for k, v in (overrides or {}).items()}}
    for prefix in sorted(table, key=len, reverse=True):
        if model.startswith(prefix):
            return table[prefix]
    return (0.0, 0.0, 0.1)


def row_cost(row: list, overrides: dict | None = None) -> float:
    inp, out, cr_mult = price_for(row[2], overrides)
    return (
        row[_IN] * inp
        + row[_OUT] * out
        + row[_CW5] * inp * 1.25
        + row[_CW1] * inp * 2.0
        + row[_CR] * inp * cr_mult
    ) / 1_000_000


def row_total(row: list) -> int:
    return row[_IN] + row[_OUT] + row[_CW5] + row[_CW1] + row[_CR]


def parse_line(line: str) -> list | None:
    """One transcript line -> row, or None when it carries no billable usage."""
    if '"usage"' not in line:
        return None
    try:
        d = json.loads(line)
    except ValueError:
        return None
    msg = d.get("message")
    if d.get("type") != "assistant" or not isinstance(msg, dict):
        return None
    usage = msg.get("usage")
    model = msg.get("model") or ""
    if not isinstance(usage, dict) or not model or model.startswith("<"):
        return None
    ts = d.get("timestamp")
    try:
        epoch = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None
    cw = usage.get("cache_creation_input_tokens") or 0
    split = usage.get("cache_creation") or {}
    cw1 = split.get("ephemeral_1h_input_tokens") or 0
    cw5 = max(cw - cw1, 0)
    cwd = d.get("cwd") or ""
    return [
        f"{msg.get('id', '')}:{d.get('requestId', '')}",
        epoch,
        model,
        int(usage.get("input_tokens") or 0),
        int(usage.get("output_tokens") or 0),
        int(cw5),
        int(cw1),
        int(usage.get("cache_read_input_tokens") or 0),
        Path(cwd).name if cwd else "",
        str(d.get("sessionId") or ""),
    ]


def parse_title(line: str) -> tuple[str, str] | None:
    """(session id, title) from Claude Code's ai-title lines."""
    if '"ai-title"' not in line:
        return None
    try:
        d = json.loads(line)
    except ValueError:
        return None
    if d.get("type") != "ai-title" or not d.get("sessionId") or not d.get("aiTitle"):
        return None
    return str(d["sessionId"]), str(d["aiTitle"])[:120]


def transcript_roots() -> list[tuple[Path, str | None]]:
    """(projects dir, account hint). cswap `run` profiles pin their slot."""
    homes = {Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"),
             Path.home() / ".claude"}
    roots: list[tuple[Path, str | None]] = [(h / "projects", None) for h in homes]
    sessions = store.cswap_backup_root() / "sessions"
    if sessions.is_dir():
        for prof in sessions.iterdir():
            m = _SESSION_DIR.match(prof.name)
            if m and (prof / "projects").is_dir():
                roots.append((prof / "projects", m.group(1)))
    return roots


SCAN_VERSION = 2  # rows gained the session id; older caches are rebuilt


def scan(cache_path: Path | None = None, titles: dict | None = None) -> list[tuple[list, str | None]]:
    """All deduped rows with account hints; files that only grew are read from their last offset.
    Session titles are collected into ``titles`` when given."""
    cache_path = cache_path or store.home() / "cache" / "scan.json"
    cache = store.read_json(cache_path, {})
    files = cache.get("files", {}) if cache.get("v") == SCAN_VERSION else {}
    seen_paths = set()
    out: dict[str, tuple[list, str | None]] = {}
    for root, hint in transcript_roots():
        if not root.is_dir():
            continue
        for path in root.rglob("*.jsonl"):
            key = str(path)
            seen_paths.add(key)
            try:
                st = path.stat()
            except OSError:
                continue
            entry = files.get(key)
            if entry and entry["size"] == st.st_size and entry["mtime"] == st.st_mtime_ns:
                rows, named = entry["rows"], entry.get("titles", {})
            else:
                start = entry["size"] if entry and st.st_size > entry["size"] else 0
                rows = entry["rows"] if start else []
                named = dict(entry.get("titles", {})) if start else {}
                try:
                    with open(path, "rb") as f:
                        f.seek(start)
                        for raw in f:
                            line = raw.decode("utf-8", "replace")
                            row = parse_line(line)
                            if row:
                                rows.append(row)
                            elif (t := parse_title(line)):
                                named[t[0]] = t[1]
                except OSError:
                    continue
                files[key] = {"size": st.st_size, "mtime": st.st_mtime_ns, "rows": rows, "titles": named}
            if titles is not None:
                titles.update(named)
            for row in rows:
                if row[0] not in out or row[1] < out[row[0]][0][1]:
                    out[row[0]] = (row, hint)
    cache["files"] = {k: v for k, v in files.items() if k in seen_paths}
    cache["v"] = SCAN_VERSION
    store.write_json(cache_path, cache)
    return list(out.values())


def attribute(ts: float, timeline: list[dict], fallback: str) -> str:
    """Account active at ``ts``: the last timeline entry at or before it."""
    acct = fallback
    for entry in timeline:  # sorted by ts
        if entry["ts"] > ts:
            break
        acct = str(entry["account"])
    return acct


def bucket(rows: list[tuple[list, str | None]], timeline: list[dict],
           known_accounts: list[str], pricing: dict | None = None) -> dict:
    """{day: {account: {model: [input, output, cw5, cw1, cr, cost, messages]}}}"""
    timeline = sorted(timeline, key=lambda e: e["ts"])
    fallback = known_accounts[0] if len(known_accounts) == 1 else UNATTRIBUTED
    days: dict = {}
    for row, hint in rows:
        acct = hint or attribute(row[1], timeline, fallback)
        day = date.fromtimestamp(row[1]).isoformat()
        cell = days.setdefault(day, {}).setdefault(acct, {}).setdefault(row[2], [0, 0, 0, 0, 0, 0.0, 0])
        for i, idx in enumerate((_IN, _OUT, _CW5, _CW1, _CR)):
            cell[i] += row[idx]
        cell[5] = round(cell[5] + row_cost(row, pricing), 6)
        cell[6] += 1
    return days


def _day_total(day: dict) -> int:
    return sum(sum(c[:5]) for models in day.values() for c in models.values())


def merge_ledger(ledger: dict, fresh: dict) -> dict:
    """Fresh scan wins per day unless it shrank, since a lower total means deleted transcripts."""
    days = dict(ledger.get("days", {}))
    for day, data in fresh.items():
        if day not in days or _day_total(data) >= _day_total(days[day]):
            days[day] = data
    return {"days": days}


def _sum_cells(cells) -> dict:
    t = {"input": 0, "output": 0, "cacheWrite": 0, "cacheRead": 0, "total": 0, "cost": 0.0, "messages": 0}
    for c in cells:
        t["input"] += c[0]
        t["output"] += c[1]
        t["cacheWrite"] += c[2] + c[3]
        t["cacheRead"] += c[4]
        t["total"] += c[0] + c[1] + c[2] + c[3] + c[4]
        t["cost"] += c[5]
        t["messages"] += c[6]
    t["cost"] = round(t["cost"], 4)
    return t


def _cells(days: dict, day_filter, account: str | None):
    for day, accts in days.items():
        if not day_filter(day):
            continue
        for acct, models in accts.items():
            if account is None or acct == account:
                yield from models.values()


def totals(days: dict, account: str | None, today: date) -> dict:
    t, m = today.isoformat(), today.isoformat()[:7]
    return {
        "today": _sum_cells(_cells(days, lambda d: d == t, account)),
        "month": _sum_cells(_cells(days, lambda d: d.startswith(m), account)),
        "lifetime": _sum_cells(_cells(days, lambda d: True, account)),
        "since": min(days) if days else None,
    }


def heatmap(days: dict, account: str | None, today: date) -> dict:
    """GitHub-style year grid: 53 full weeks ending this Saturday, Sunday-first."""
    end = today + timedelta(days=(5 - today.weekday()) % 7)  # next Saturday (or today)
    start = end - timedelta(days=53 * 7 - 1)
    cells = []
    d = start
    while d <= end:
        iso = d.isoformat()
        s = _sum_cells(_cells({iso: days[iso]}, lambda x: True, account)) if iso in days else None
        cells.append({
            "date": iso,
            "total": s["total"] if s else 0,
            "output": s["output"] if s else 0,
            "cost": s["cost"] if s else 0.0,
            "future": d > today,
        })
        d += timedelta(days=1)
    nonzero = sorted(c["total"] for c in cells if c["total"] > 0)
    # GitHub levels: 0 = none, 1-4 = quartiles of the active days.
    levels = [nonzero[int((len(nonzero) - 1) * q)] for q in (0.25, 0.5, 0.75)] if nonzero else [0, 0, 0]
    for c in cells:
        v = c["total"]
        c["level"] = 0 if v == 0 else 1 + sum(v > lv for lv in levels)
    past = [c for c in cells if not c["future"]]
    streak = 0
    for c in reversed(past):
        if c["total"] == 0:
            if c["date"] == today.isoformat() and streak == 0:
                continue  # today not started yet doesn't break the streak
            break
        streak += 1
    longest = run = 0
    for c in past:
        run = run + 1 if c["total"] else 0
        longest = max(longest, run)
    busiest = max(past, key=lambda c: c["total"], default=None)
    return {
        "start": start.isoformat(),
        "cells": cells,
        "levels": levels,
        "yearTotal": sum(c["total"] for c in past),
        "yearCost": round(sum(c["cost"] for c in past), 2),
        "activeDays": sum(1 for c in past if c["total"]),
        "streak": streak,
        "longestStreak": longest,
        "busiest": {"date": busiest["date"], "total": busiest["total"]} if busiest and busiest["total"] else None,
    }


def monthly(days: dict, account: str | None, today: date, months: int = 12) -> list[dict]:
    out = []
    y, m = today.year, today.month
    for _ in range(months):
        key = f"{y:04d}-{m:02d}"
        s = _sum_cells(_cells(days, lambda d, key=key: d.startswith(key), account))
        out.append({"month": key, "total": s["total"], "output": s["output"], "cost": s["cost"]})
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return list(reversed(out))


def by_model(days: dict, account: str | None, since: str = "") -> list[dict]:
    agg: dict[str, list] = {}
    for day, accts in days.items():
        if day < since:
            continue
        for acct, models in accts.items():
            if account is not None and acct != account:
                continue
            for model, c in models.items():
                agg.setdefault(model, []).append(c)
    rows = [{"model": k, **_sum_cells(v)} for k, v in agg.items()]
    return sorted(rows, key=lambda r: r["total"], reverse=True)


def by_project(rows: list[tuple[list, str | None]], since_ts: float, limit: int = 8) -> list[dict]:
    agg: dict[str, int] = {}
    for row, _ in rows:
        if row[1] >= since_ts:
            agg[row[8] or "(unknown)"] = agg.get(row[8] or "(unknown)", 0) + row_total(row)
    top = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [{"project": k, "total": v} for k, v in top]


def by_session(rows: list[tuple[list, str | None]], timeline: list[dict], fallback: str, titles: dict,
               pricing: dict | None, since_ts: float, limit: int = 10) -> list[dict]:
    """Recent matches: one Claude Code session each (subagents included), newest first."""
    timeline = sorted(timeline, key=lambda e: e["ts"])
    agg: dict[str, dict] = {}
    for row, hint in rows:
        sid = row[9] if len(row) > 9 else ""
        if not sid:
            continue
        m = agg.setdefault(sid, {"id": sid, "title": titles.get(sid, ""), "project": row[8], "start": row[1], "end": row[1],
                                 "total": 0, "cacheRead": 0, "cost": 0.0, "messages": 0, "hint": hint, "models": {}})
        m["start"], m["end"] = min(m["start"], row[1]), max(m["end"], row[1])
        m["total"] += row_total(row)
        m["cacheRead"] += row[_CR]
        m["cost"] += row_cost(row, pricing)
        m["messages"] += 1
        m["models"][row[2]] = m["models"].get(row[2], 0) + row_total(row)
        m["hint"] = m["hint"] or hint
    out = sorted((m for m in agg.values() if m["end"] >= since_ts), key=lambda m: m["end"], reverse=True)[:limit]
    for m in out:
        m["account"] = m.pop("hint") or attribute(m["start"], timeline, fallback)
        m["model"] = max(m.pop("models").items(), key=lambda kv: kv[1])[0]
        m["fresh"] = m["total"] - m["cacheRead"]
        m["cost"] = round(m["cost"], 4)
    return out


def burn_rate(rows: list[tuple[list, str | None]], now: float) -> int:
    """Tokens in the last 60 minutes."""
    return sum(row_total(r) for r, _ in rows if r[1] >= now - 3600)


def compute(timeline: list[dict], known_accounts: list[str], pricing: dict | None = None,
            today: date | None = None, now: float | None = None) -> dict:
    """Scan, merge into the ledger, and build every view the UIs draw."""
    today = today or date.today()
    now = now or time.time()
    titles: dict = {}
    rows = scan(titles=titles)
    fresh = bucket(rows, timeline, known_accounts, pricing)
    ledger_path = store.home() / "ledger.json"
    ledger = merge_ledger(store.read_json(ledger_path, {}), fresh)
    store.write_json(ledger_path, ledger)
    days = ledger["days"]
    accounts = sorted({a for accts in days.values() for a in accts} | set(known_accounts))
    views = {None: "all", **{a: a for a in accounts}}
    return {
        "totals": {k: totals(days, a, today) for a, k in views.items()},
        "heatmap": {k: heatmap(days, a, today) for a, k in views.items()},
        "monthly": {k: monthly(days, a, today) for a, k in views.items()},
        "models": by_model(days, None, (today - timedelta(days=30)).isoformat()),
        "projects": by_project(rows, now - 30 * 86400),
        "burnPerHour": burn_rate(rows, now),
        "matches": by_session(rows, timeline, known_accounts[0] if len(known_accounts) == 1 else UNATTRIBUTED,
                              titles, pricing, now - 7 * 86400),
    }


def export_rows(days: dict) -> list[dict]:
    out = []
    for day in sorted(days):
        for acct, models in sorted(days[day].items()):
            for model, c in sorted(models.items()):
                out.append({"date": day, "account": acct, "model": model, "input": c[0], "output": c[1],
                            "cacheWrite": c[2] + c[3], "cacheRead": c[4], "total": sum(c[:5]),
                            "cost": round(c[5], 4), "messages": c[6]})
    return out
