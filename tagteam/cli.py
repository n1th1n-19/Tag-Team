"""tagteam: your Claude accounts are a tag team. See each account's usage and tag the right one in."""

from __future__ import annotations

import argparse
import csv
import getpass
import json
import os
import re
import sys
from datetime import date

from tagteam import __version__, accounts, art, store, tokens
from tagteam import state as state_mod

# Match-history heat, cold canvas to hot gold.
HEAT = [(59, 63, 82), (107, 58, 58), (168, 58, 58), (217, 65, 65), (242, 193, 78)]

from tagteam.rules import RULES  # noqa: E402


def fmt_tokens(n: float) -> str:
    for unit, size in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(n) >= size:
            return f"{n / size:.1f}{unit}"
    return str(int(n))


BARS_SOURCE = "life bars: all of Claude on each account, from Anthropic"
HISTORY_SOURCE = "Claude Code on this computer only"


def score_note(lifetime: dict) -> str:
    """Where SCORE comes from, and how much of it is cache reads (the same context re-read every turn)."""
    total = lifetime.get("total") or 0
    if not total:
        return HISTORY_SOURCE
    reads = lifetime.get("cacheRead") or 0
    return f"{HISTORY_SOURCE} · {reads / total:.0%} cache reads · {fmt_tokens(total - reads)} fresh"


def score(n: int) -> str:
    return f"{int(n):015,d}"


def _color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _rgb(text: str, rgb: tuple[int, int, int], on: bool) -> str:
    return f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m{text}\x1b[0m" if on else text


def life_bar(pct: float | None, color: bool, width: int = 20) -> str:
    """Fighting-game life bar: full when fresh, drains as the limit is used."""
    if pct is None:
        return "?" * width
    left = max(0.0, 100.0 - pct)
    filled = round(left / 100 * width)
    rgb = (95, 194, 90) if left > 50 else (240, 145, 58) if left > 10 else (217, 65, 65)
    return _rgb("█" * filled, rgb, color) + _rgb("░" * (width - filled), (90, 95, 115), color)


def heatmap_text(hm: dict, color: bool) -> str:
    """Match history: 7 rows (Sun..Sat) x 53 weeks, GitHub-style, hot cells gold."""
    cells = hm["cells"]
    weeks = [cells[i:i + 7] for i in range(0, len(cells), 7)]
    head = [" "] * (5 + 2 * len(weeks) + 3)
    last = None
    for i, w in enumerate(weeks):
        m = date.fromisoformat(w[0]["date"]).strftime("%b")
        if m != last and all(ch == " " for ch in head[5 + 2 * i - 1:5 + 2 * i + 3]):
            head[5 + 2 * i:5 + 2 * i + 3] = m
        last = m
    head = "".join(head)
    lines = [head.rstrip()]
    glyphs = " ░▒▓█"
    for dow in range(7):
        row = f"{ {1: 'Mon', 3: 'Wed', 5: 'Fri'}.get(dow, ''):<4} "
        for w in weeks:
            c = w[dow]
            if c["future"]:
                row += "  "
            elif color:
                row += _rgb("■", HEAT[c["level"]], True) + " "
            else:
                row += (glyphs[c["level"]] if c["level"] else "·") + " "
        lines.append(row.rstrip())
    legend = "Cold " + ("".join(_rgb("■ ", h, True) for h in HEAT) if color else "· ░ ▒ ▓ █ ") + "Hot"
    lines.append(" " * max(0, len(head) - 20) + legend)
    return "\n".join(lines)


def print_ring_card(s: dict, account: str = "all") -> None:
    color = _color()
    bold = (lambda t: f"\x1b[1m{t}\x1b[0m") if color else (lambda t: t)
    gold = lambda t: _rgb(t, (242, 193, 78), color)  # noqa: E731
    tok = s["tokens"]
    hm = tok["heatmap"].get(account) or tok["heatmap"]["all"]
    t = tok["totals"].get(account) or tok["totals"]["all"]
    act = s["active"]

    title = [
        "",
        gold(bold("TAG TEAM WRESTLING")),
        "your Claude accounts are a tag team",
        "",
        bold("IN THE RING: ") + (act["label"] or "nobody") + ("" if act["managed"] or not act["label"] else "  (not signed)"),
        gold("SCORE ") + bold(score(t["lifetime"]["total"])) + "  career tokens",
        score_note(t["lifetime"]),
        f"purse ${t['lifetime']['cost']:,.2f} (API-price estimate)",
    ]
    banner = art.banner(color=color) if sys.stdout.encoding and "utf" in sys.stdout.encoding.lower() else []
    for i in range(max(len(banner), len(title))):
        left = banner[i] if i < len(banner) else ""
        visible = len(re.sub(r"\x1b\[[0-9;]*m", "", left))
        print(f"{left}{' ' * (34 - visible)}{title[i] if i < len(title) else ''}".rstrip())
    print()
    print(f"TONIGHT {fmt_tokens(t['today']['total'])} (${t['today']['cost']:.2f})  ·  "
          f"THIS MONTH {fmt_tokens(t['month']['total'])} (${t['month']['cost']:.2f})  ·  "
          f"SHOW STREAK {hm['streak']} (best {hm['longestStreak']})  ·  "
          f"MAIN EVENT {hm['busiest']['date'] + ' ' + fmt_tokens(hm['busiest']['total']) if hm['busiest'] else '-'}  ·  "
          f"LAST HOUR {fmt_tokens(tok['burnPerHour'])}")
    print()
    print(bold(f"MATCH HISTORY  {fmt_tokens(hm['yearTotal'])} tokens in the last year") + f"  ({HISTORY_SOURCE})")
    print(heatmap_text(hm, color))
    print()
    if tok.get("matches"):
        names = {str(r["number"]): r["label"] for r in s["accounts"]}
        print(bold("MATCH CARDS") + "  (sessions, last 7 days)")
        for m in tok["matches"][:5]:
            live = gold("LIVE ") if m.get("live") else "     "
            mins = max(1, round((m["end"] - m["start"]) / 60))
            print(f" {live}{(m['title'] or m['project'] or 'untitled')[:38]:<38} {names.get(m['account'], m['account'])[:10]:<10} "
                  f"{f'{mins // 60}h {mins % 60:02d}m' if mins >= 60 else f'{mins}m':>7}  {fmt_tokens(m['total']):>6} ({fmt_tokens(m['fresh'])} fresh)  ${m['cost']:.2f}")
        print()
    print(bold("ROSTER") + f"  ({BARS_SOURCE})")
    for r in s["accounts"]:
        u = r.get("usage") or r.get("lastGoodUsage") or {}
        five = (u.get("fiveHour") or {}).get("pct")
        seven = (u.get("sevenDay") or {}).get("pct")
        badge = "[IN]   " if r.get("active") else "[BENCH]" if r.get("disabled") else "[APRON]"
        cursor = gold("▶") if r.get("active") else " "
        ko = "  " + _rgb("K.O.", (217, 65, 65), color) if (five or 0) >= 100 or (seven or 0) >= 100 else ""
        live = f"  {r['liveSessions']} in progress" if r.get("liveSessions") else ""
        if five is None and seven is None:
            bars = f"{r.get('usageStatus', '?').replace('_', ' '):<56}"
        else:
            bars = f"STAMINA {life_bar(five, color)} {five or 0:>3.0f}%  ENDURANCE {life_bar(seven, color, 12)} {seven or 0:>3.0f}%"
        print(f" {cursor} {badge} {r['number']:>2} {r['label'][:16]:<16} {bars}  tonight {fmt_tokens(r['tokens']['today']['total']):>6}{live}{ko}")
    for a in s["alerts"]:
        if a["kind"] == "near-limit":
            tip = f"  TAG ME → `tagteam tag-out`" + (f" ({a['suggest']['label']} is fresh, {a['suggest']['pct']:.0f}%)" if a.get("suggest") else "")
            print("\n" + _rgb(f"⚠ {a['message']}.", (240, 145, 58), color) + tip)
        else:
            print(f"\n{'⬆' if a['kind'] == 'update' else '⚠'} {a['message']}")
    for chk in s["setup"]:
        if not chk["ok"]:
            print(f"□ {chk['label']}")


def statusline(s: dict) -> str:
    act = s["active"]
    row = next((r for r in s["accounts"] if r.get("active")), None)
    parts = [f"[IN] {act['label'] or 'nobody'}"]
    if row:
        u = row.get("usage") or row.get("lastGoodUsage") or {}
        if u.get("fiveHour"):
            left = max(0, 100 - u["fiveHour"]["pct"])
            parts.append("▮" * round(left / 20) + "▯" * (5 - round(left / 20)) + f" stamina {u['fiveHour']['pct']:.0f}%")
        if u.get("sevenDay"):
            parts.append(f"endurance {u['sevenDay']['pct']:.0f}%")
    parts.append(f"tonight {fmt_tokens(s['tokens']['totals']['all']['today']['total'])}")
    if s["auto"].get("enabled"):
        parts.append("blind tag")
    if any(a["kind"] == "near-limit" for a in s["alerts"]):
        parts.append("TAG ME!")
    return " · ".join(parts)


def emit(data, as_json: bool, human=None) -> None:
    if as_json:
        print(json.dumps(data, default=str))
    elif human:
        human(data)
    else:
        print(data.get("message") if isinstance(data, dict) and "message" in data else json.dumps(data, indent=2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tagteam", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"tagteam {__version__}")
    sub = p.add_subparsers(dest="cmd", metavar="COMMAND")

    def cmd(name, help_, **kw):
        sp = sub.add_parser(name, help=help_, **kw)
        sp.add_argument("--json", action="store_true", help="machine-readable output")
        return sp

    rc = cmd("ring-card", "the report: who's in the ring, roster, match history (default)")
    rc.add_argument("--account", default="all")
    ti = cmd("tag-in", "tag a partner into the ring (number, ring name, email, 'best', or 'next' in line)")
    ti.add_argument("partner", nargs="?", default="best")
    to = cmd("tag-out", "hot tag: hand off to the partner with the most stamina left")
    to.add_argument("--next", action="store_true", help="tag the next partner in line instead (skips anyone at their limit)")
    mv = cmd("move", "move a partner to another spot in the lineup; their match history moves with them")
    mv.add_argument("partner", help="number, ring name or email")
    mv.add_argument("slot", type=int, help="the spot to move to (an occupied spot swaps the two)")
    cmd("roster", "list your partners and their stamina")
    sg = cmd("sign", "sign a partner: save the current Claude Code login (or --contract for a token)")
    sg.add_argument("--ring-name")
    sg.add_argument("--slot", type=int)
    sg.add_argument("--contract", action="store_true", help="sign by contract: a setup-token or API key, read from stdin")
    sg.add_argument("--email", help="with --contract: a label email for the partner")
    rn = cmd("ring-name", "give a partner a ring name (or clear it)")
    rn.add_argument("partner")
    rn.add_argument("name", nargs="?")
    for verb, what in (("bench", "leave a partner out of blind tags"), ("unbench", "put a benched partner back"),
                       ("release", "release a partner from the roster")):
        a = cmd(verb, what)
        a.add_argument("partner")
        if verb == "release":
            a.add_argument("--yes", action="store_true")
    bt = cmd("blind-tag", "automatic tagging: on | off | status | preview | once | set KEY VALUE")
    bt.add_argument("action", nargs="?", default="status", choices=["on", "off", "status", "preview", "once", "set"])
    bt.add_argument("key", nargs="?", choices=sorted(accounts.AUTO_KEYS))
    bt.add_argument("value", nargs="?")
    cm = cmd("corner-man", "keep blind-tagging with Claude Code closed: install | uninstall | status")
    cm.add_argument("action", choices=["install", "uninstall", "status", "run"])
    rg = cmd("ring", "open the ring (browser dashboard)")
    rg.add_argument("--port", type=int, default=0)
    rg.add_argument("--no-open", action="store_true")
    cmd("rules", "how the match works: the wrestling words explained")
    ex = cmd("export", "export match history (daily usage per partner and model)")
    ex.add_argument("--csv", action="store_true")
    ex.add_argument("-o", "--output")
    cf = cmd("tag-out-point", "show or set the %% of stamina used that raises TAG ME")
    cf.add_argument("percent", nargs="?", type=float)
    cmd("state", "everything as JSON (what the ring draws)")
    cmd("statusline", "one line for Claude Code's statusLine setting")
    cmd("record", "note who's in the ring (hook helper)")
    up = cmd("update", "install the newest Tag Team release (CLI, Claude Code plugin, editor extension)")
    up.add_argument("--check", action="store_true", help="only say whether a newer release exists")
    up.add_argument("--force", action="store_true", help="reinstall even if you're on the latest")
    up.add_argument("--auto", action="store_true", help=argparse.SUPPRESS)
    up.add_argument("--notify", choices=["on", "off"], help="show a notice when a new release is out (checks GitHub once a day; off unless you turn it on)")
    cmd("cleanup", "remove old plugin copies and leftover downloads (runs after every install and update)")
    au = cmd("auto-update", "check for and install new releases once a week: on | off | status")
    au.add_argument("action", nargs="?", default="status", choices=["on", "off", "status"])
    return p


def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    as_json = getattr(args, "json", False)
    try:
        return _dispatch(p, args, as_json)
    except accounts.CswapError as e:
        emit({"ok": False, "error": str(e)}, as_json, lambda d: print(f"error: {d['error']}", file=sys.stderr))
        return 1


def legacy_main() -> int:
    """`swapme` from swap-me 0.1 keeps working for one version."""
    print("swap-me is now Tag Team Wrestling: use `tagteam` (see `tagteam rules`).", file=sys.stderr)
    return main()


def _dispatch(p, args, as_json: bool) -> int:
    c = args.cmd
    if c in (None, "ring-card"):
        emit(state_mod.build(), as_json, lambda d: print_ring_card(d, getattr(args, "account", "all")))
    elif c == "state":
        print(json.dumps(state_mod.build(), default=str))
    elif c == "statusline":
        if not sys.stdin.isatty():
            sys.stdin.read()  # Claude Code pipes session JSON; not needed
        print(statusline(state_mod.build()))
    elif c == "tag-in":
        res = accounts.switch(None if args.partner == "best" else args.partner)
        emit(_tag_message(res), as_json)
    elif c == "tag-out":
        emit(_tag_message(accounts.switch("next" if args.next else None)), as_json)
    elif c == "move":
        emit(accounts.move(args.partner, args.slot), as_json)
    elif c == "roster":
        s = state_mod.build()
        emit(s["accounts"], as_json, lambda rows: [print(
            f"{'[IN]   ' if r['active'] else '[BENCH]' if r.get('disabled') else '[APRON]'} {r['number']:>2} {r['label']:<16} "
            f"stamina {((r.get('usage') or r.get('lastGoodUsage') or {}).get('fiveHour') or {}).get('pct', 0):>3.0f}%  {r['email']}")
            for r in rows])
    elif c == "sign":
        if args.contract:
            token = sys.stdin.readline() if not sys.stdin.isatty() else getpass.getpass("Contract (token, hidden): ")
            res = accounts.add_token(token, args.email, args.slot)
        else:
            res = accounts.add_current(args.ring_name, args.slot)
        res["message"] = "Signed to the roster. " + res.get("message", "")
        emit(res, as_json)
    elif c == "ring-name":
        emit(accounts.set_alias(args.partner, args.name), as_json)
    elif c in ("bench", "unbench"):
        emit(accounts.set_enabled(args.partner, c == "unbench"), as_json)
    elif c == "release":
        if not args.yes and not as_json:
            if input(f"Release partner {args.partner} from the roster? [y/N] ").strip().lower() != "y":
                print("Still on the roster.")
                return 1
        emit(accounts.remove(args.partner), as_json)
    elif c == "blind-tag":
        return _blind_tag(p, args, as_json)
    elif c == "corner-man":
        if args.action == "run":
            accounts.auto_run_forever()
            return 0
        res = (accounts.service_install() if args.action == "install" else accounts.service_uninstall()
               if args.action == "uninstall" else {"installed": accounts.service_installed(),
                                                   "path": str(accounts.service_path())})
        emit(res, as_json)
    elif c == "ring":
        from tagteam import server
        server.serve(port=args.port, open_browser=not args.no_open)
    elif c == "rules":
        emit({"rules": RULES}, as_json, lambda d: print(d["rules"]))
    elif c == "record":
        row = next((r for r in accounts.list_accounts().get("accounts", []) if r.get("active")), None)
        if row:
            store.record_active(str(row["number"]), row.get("email", ""), source="hook")
        emit({"ok": True, "active": row and row["number"]}, as_json, lambda d: None)
    elif c == "export":
        rows = tokens.export_rows(store.read_json(store.home() / "ledger.json", {}).get("days", {}))
        out = open(args.output, "w", newline="", encoding="utf-8") if args.output else sys.stdout
        if args.csv and rows:
            w = csv.DictWriter(out, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        else:
            json.dump(rows, out, indent=2)
        if args.output:
            out.close()
            print(f"wrote {len(rows)} rows to {args.output}")
    elif c == "update":
        from tagteam import updater
        if args.notify:
            store.set_config(updateCheck=args.notify == "on")
            emit({"ok": True, "updateCheck": args.notify == "on",
                  "message": "You'll see a notice when a new release is out." if args.notify == "on" else "Update notices are off."}, as_json)
        elif args.check:
            emit(updater.check(), as_json)
        else:
            emit(updater.update(force=args.force, quiet=args.auto), as_json)
    elif c == "cleanup":
        from tagteam import updater
        emit(updater.cleanup(), as_json)
    elif c == "auto-update":
        from tagteam import updater
        emit({"on": updater.auto_update_on, "off": updater.auto_update_off, "status": updater.auto_update_status}[args.action](), as_json)
    elif c == "tag-out-point":
        if args.percent is None:
            emit({"tagOutPoint": store.config()["threshold"]}, as_json)
        else:
            cfg = store.set_config(threshold=args.percent)
            emit({"ok": True, "tagOutPoint": cfg["threshold"], "message": f"TAG ME shows at {cfg['threshold']:.0f}% stamina used"}, as_json)
    return 0


def _tag_message(res: dict) -> dict:
    to, frm = res.get("to") or {}, res.get("from") or {}
    if res.get("switched"):
        res["message"] = f"TAG! Account-{frm.get('number')} tags out, {to.get('email', '?')} (#{to.get('number')}) is in the ring."
    else:
        res["message"] = f"{to.get('email', '?')} (#{to.get('number')}) is already in the ring."
    return res


def _blind_tag(p, args, as_json: bool) -> int:
    a = args.action
    if a == "status":
        res = {**store.config()["auto"], "cornerMan": accounts.service_installed(), "settings": accounts.auto_settings(),
               "recent": store.tail_events("auto", 10)}
    elif a == "on":
        res = {"ok": True, **store.set_config(auto={"enabled": True})["auto"],
               "message": "Blind tag on: partners tag themselves out before they're worn down, while Claude Code is open. "
                          "`tagteam corner-man install` keeps it going when it's closed."}
    elif a == "off":
        if accounts.service_installed():
            accounts.service_uninstall()
        res = {"ok": True, **store.set_config(auto={"enabled": False})["auto"], "message": "Blind tag off: you'll be asked before every tag."}
    elif a in ("once", "preview"):
        events = accounts.auto_once(dry_run=a == "preview")
        res = {"ok": True, "events": events, "message": _describe_events(events)}
    elif a == "set":
        if not args.key or args.value is None:
            p.error("usage: tagteam blind-tag set KEY VALUE")
        res = accounts.set_auto_setting(args.key, args.value)
    else:
        return 2
    emit(res, as_json)
    return 0


def _describe_events(events: list[dict]) -> str:
    for ev in events:
        kind = ev.get("event")
        if kind == "switch":
            src = (ev.get("from") or {}).get("number")
            dst = ev.get("to") or {}
            verb = "Would blind-tag" if ev.get("dryRun") else "Blind tag!"
            return f"{verb} #{src} → {dst.get('email', '')} (#{dst.get('number')}) [{ev.get('trigger')}]"
        if kind == "no-switch":
            return f"No tag needed: {ev.get('reason')}" + (f" ({ev['detail']})" if ev.get("detail") else "")
        if kind == "all-exhausted":
            return "The whole roster is down for the count"
        if kind == "error":
            return f"Blind tag error: {ev.get('message') or ev}"
    return "No call from the corner"


if __name__ == "__main__":
    sys.exit(main())
