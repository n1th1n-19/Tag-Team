"""Runs with `python -m pytest tests` or plain `python tests/test_tagteam.py`."""

import json
import os
import stat
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tagteam import accounts, art, cli, store, tokens  # noqa: E402


def _line(mid, req, ts, model="claude-opus-5-5", inp=10, out=20, cw=100, cw1h=40, cr=1000, cwd="/w/proj"):
    return json.dumps({
        "type": "assistant", "timestamp": ts, "requestId": req, "cwd": cwd,
        "message": {"id": mid, "model": model, "usage": {
            "input_tokens": inp, "output_tokens": out, "cache_creation_input_tokens": cw,
            "cache_creation": {"ephemeral_1h_input_tokens": cw1h}, "cache_read_input_tokens": cr}},
    })


def _env(tmp: Path):
    os.environ["TAGTEAM_HOME"] = str(tmp / "tthome")
    os.environ["CLAUDE_CONFIG_DIR"] = str(tmp / "claude")
    os.environ["HOME"] = str(tmp / "home")
    os.environ["XDG_DATA_HOME"] = str(tmp / "xdg")


def test_parse_and_cost():
    row = tokens.parse_line(_line("m1", "r1", "2026-10-01T10:00:00Z"))
    assert row[2] == "claude-opus-5-5" and row[3:8] == [10, 20, 60, 40, 1000] and row[8] == "proj"
    # opus 5.5: $4 in, $20 out, writes 1.25x/2x, reads 0.05x
    expect = (10 * 4 + 20 * 20 + 60 * 4 * 1.25 + 40 * 4 * 2 + 1000 * 4 * 0.05) / 1e6
    assert abs(tokens.row_cost(row) - expect) < 1e-12
    assert tokens.parse_line('{"type":"user","message":{"usage":{}}}') is None
    assert tokens.parse_line(_line("m", "r", "2026-10-01T10:00:00Z", model="<synthetic>")) is None
    assert tokens.price_for("claude-sonnet-4-5-20250929")[0] == 3.0  # family fallback


def test_scan_dedupes_and_is_incremental():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _env(tmp)
        proj = tmp / "claude" / "projects" / "p"
        proj.mkdir(parents=True)
        f = proj / "s.jsonl"
        # same message twice (one row per content block) + a resumed copy in another file
        f.write_text(_line("m1", "r1", "2026-10-01T10:00:00Z") + "\n" + _line("m1", "r1", "2026-10-01T10:00:00Z") + "\n")
        (proj / "resumed.jsonl").write_text(_line("m1", "r1", "2026-10-01T10:00:00Z") + "\n")
        assert len(tokens.scan()) == 1
        with open(f, "a") as fh:
            fh.write(_line("m2", "r2", "2026-10-02T10:00:00Z") + "\n")
        rows = tokens.scan()
        assert sorted(r[0][0] for r in rows) == ["m1:r1", "m2:r2"]


def test_attribution_and_buckets():
    t0 = datetime(2026, 10, 1, 12, tzinfo=timezone.utc).timestamp()
    rows = [
        ([f"a", t0 - 7200, "claude-opus-5-5", 1, 1, 0, 0, 0, ""], None),   # before tracking
        ([f"b", t0 + 60, "claude-opus-5-5", 1, 1, 0, 0, 0, ""], None),     # account 1
        ([f"c", t0 + 7200, "claude-opus-5-5", 1, 1, 0, 0, 0, ""], None),   # account 2
        ([f"d", t0 + 7200, "claude-opus-5-5", 5, 5, 0, 0, 0, ""], "3"),    # cswap run profile
    ]
    timeline = [{"ts": t0 + 3600, "account": "2"}, {"ts": t0, "account": "1"}]
    days = tokens.bucket(rows, timeline, ["1", "2", "3"])
    accts = {a: m["claude-opus-5-5"][0] for day in days.values() for a, m in day.items()}
    assert accts == {"?": 1, "1": 1, "2": 1, "3": 5}, accts
    # a single known account takes the pre-tracking history
    one = tokens.bucket(rows[:1], [], ["7"])
    assert list(next(iter(one.values()))) == ["7"]


def test_ledger_keeps_days_cleanup_deleted():
    old = {"days": {"2026-01-01": {"1": {"m": [10, 10, 0, 0, 0, 0.1, 1]}}, "2026-02-01": {"1": {"m": [5, 5, 0, 0, 0, 0.1, 1]}}}}
    fresh = {"2026-02-01": {"1": {"m": [1, 1, 0, 0, 0, 0.0, 1]}}, "2026-03-01": {"1": {"m": [2, 2, 0, 0, 0, 0.0, 1]}}}
    merged = tokens.merge_ledger(old, fresh)["days"]
    assert merged["2026-01-01"] == old["days"]["2026-01-01"]           # transcript gone, kept
    assert merged["2026-02-01"] == old["days"]["2026-02-01"]           # shrank -> keep archived
    assert merged["2026-03-01"] == fresh["2026-03-01"]                 # new day


def test_heatmap_grid_levels_streaks():
    today = date(2026, 10, 15)  # a Thursday
    days = {f"2026-10-{d:02d}": {"1": {"m": [0, n, 0, 0, 0, 0.0, 1]}} for d, n in [(10, 1), (12, 10), (13, 100), (14, 1000)]}
    hm = tokens.heatmap(days, None, today)
    assert len(hm["cells"]) == 53 * 7
    assert date.fromisoformat(hm["start"]).weekday() == 6            # grid starts on a Sunday
    by = {c["date"]: c for c in hm["cells"]}
    assert by["2026-10-14"]["level"] == 4 and by["2026-10-11"]["level"] == 0
    assert hm["streak"] == 3            # 12,13,14 (today empty doesn't break it)
    assert hm["longestStreak"] == 3 and hm["activeDays"] == 4
    assert all(c["future"] for c in hm["cells"] if c["date"] > "2026-10-15")
    assert tokens.monthly(days, None, today)[-1] == {"month": "2026-10", "total": 1111, "output": 1111, "cost": 0.0}


def test_switch_through_fake_cswap_records_timeline():
    if sys.platform.startswith("win"):
        return  # the fake cswap is a shell script
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _env(tmp)
        fake = tmp / "cswap"
        fake.write_text("#!/bin/sh\necho \"$@\" >> \"$TAGTEAM_HOME/argv.log\"\n"
                        "echo '{\"schemaVersion\":1,\"switched\":true,\"from\":{\"number\":1,\"email\":\"a@x\"},"
                        "\"to\":{\"number\":2,\"email\":\"b@x\"},\"message\":\"Switched to Account-2 (b@x)\",\"warnings\":[]}'\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        os.environ["TAGTEAM_CSWAP"] = str(fake)
        Path(os.environ["TAGTEAM_HOME"]).mkdir(parents=True)
        try:
            res = accounts.switch("2")
            assert res["switched"] and res["to"]["number"] == 2
            assert store.timeline()[-1]["account"] == "2"
            accounts.switch(None)  # best
            log = (Path(os.environ["TAGTEAM_HOME"]) / "argv.log").read_text().splitlines()
            assert log == ["switch 2 --json", "switch --strategy best --json"], log
            try:
                accounts.add_token("not-a-token")
                raise AssertionError("bad token accepted")
            except accounts.CswapError:
                pass
        finally:
            del os.environ["TAGTEAM_CSWAP"]


def test_swap_me_history_moves_to_tag_team():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        for k in ("TAGTEAM_HOME", "SWAPME_HOME"):
            os.environ.pop(k, None)
        os.environ["HOME"] = str(tmp)
        old = tmp / ".swap-me"
        (old / "cache").mkdir(parents=True)
        (old / "ledger.json").write_text('{"days": {"2026-01-01": {}}}')
        (old / "timeline.jsonl").write_text('{"ts": 1, "account": "1"}\n')
        home = store.home()
        assert home == tmp / ".tag-team" and not old.exists()
        assert store.read_json(home / "ledger.json", {}) == {"days": {"2026-01-01": {}}}
        assert store.timeline() == [{"ts": 1, "account": "1"}]
        # the old env var still points somewhere explicit
        os.environ["SWAPME_HOME"] = str(tmp / "custom")
        assert store.home() == tmp / "custom"
        del os.environ["SWAPME_HOME"]
        # the installer made ~/.tag-team/app first: history still merges in, nothing overwritten
        new2 = tmp / "merge"
        (new2 / "app").mkdir(parents=True)
        old.mkdir(); (old / "app").mkdir(); (old / "timeline.jsonl").write_text("x\n"); (old / "app" / "old.txt").write_text("old")
        store.migrate(old, new2)
        assert (new2 / "timeline.jsonl").read_text() == "x\n" and not (new2 / "app" / "old.txt").exists() and not old.exists()
        # copy path (cross-device): copied, verified, old removed
        old.mkdir(); (old / "ledger.json").write_text("{}")
        new = tmp / "elsewhere"
        real_rename = os.rename
        calls = []
        def fake_rename(a, b):
            calls.append(a)
            if Path(a) == old or Path(a).parent == old:
                raise OSError("cross-device")
            return real_rename(a, b)
        os.rename = fake_rename
        try:
            store.migrate(old, new)
        finally:
            os.rename = real_rename
        assert (new / "ledger.json").read_text() == "{}" and not old.exists()


def test_mascot_from_figma():
    m = art.mascot()
    for name, rows in m["frames"].items():
        assert len({len(r) for r in rows}) == 1, name
        assert set("".join(rows)) <= set(m["palette"]) | {"."}, name
    png = art.png("mascot/icon", 4)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and int.from_bytes(png[16:20], "big") == 128
    assert len(art.banner(color=False)) >= 10
    assert "tag" in cli.RULES.lower() and "apron" in cli.RULES


def test_programs_in_the_current_folder_are_never_run():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
        for folder in (d, other):
            exe = Path(folder) / "tt-probe"
            exe.write_text("#!/bin/sh\n")
            exe.chmod(0o755)
        saved_path, saved_cwd = os.environ.get("PATH", ""), os.getcwd()
        try:
            os.chdir(d)
            os.environ["PATH"] = f"{d}{os.pathsep}."
            assert accounts.find_exe("tt-probe") is None
            os.environ["PATH"] = other
            assert accounts.find_exe("tt-probe") == str(Path(other) / "tt-probe")
        finally:
            os.environ["PATH"] = saved_path
            os.chdir(saved_cwd)


def test_ring_token_never_in_browser_argv():
    from tagteam import server
    url = "http://127.0.0.1:1234/#t=secret-token"
    uri = server._launcher(url)
    path = Path(uri.removeprefix("file://"))
    assert "secret-token" not in uri
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.dumps(url) in path.read_text()
    path.unlink()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
