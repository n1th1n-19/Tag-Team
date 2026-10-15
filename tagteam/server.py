"""The ring in a browser: 127.0.0.1 only, per-run secret token on every API call."""

from __future__ import annotations

import base64
import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from tagteam import accounts, art, store
from tagteam import state as state_mod

TOKEN = secrets.token_urlsafe(24)
_cache: dict = {"at": 0.0, "data": None}
_lock = threading.Lock()


def cached_state(force: bool = False) -> dict:
    with _lock:
        if force or not _cache["data"] or time.time() - _cache["at"] > 20:
            _cache["data"] = state_mod.build()
            _cache["at"] = time.time()
        return _cache["data"]


def page() -> str:
    """index.html with fonts and mascot inlined, shared by the browser ring and the editor extension."""
    web = resources.files("tagteam").joinpath("web")
    faces = ""
    for family, file in (("Press Start 2P", "PressStart2P-latin.woff2"), ("VT323", "VT323-latin.woff2")):
        data = base64.b64encode(web.joinpath("fonts", file).read_bytes()).decode()
        faces += f'@font-face {{ font-family: "{family}"; src: url(data:font/woff2;base64,{data}) format("woff2"); font-display: block; }}\n'
    return (web.joinpath("index.html").read_text(encoding="utf-8")
            .replace("/*@FONTS@*/", faces)
            .replace("/*@MASCOT@*/", web.joinpath("mascot.js").read_text(encoding="utf-8")))


def act(path: str, body: dict) -> dict:
    """Every mutating dashboard button lands here."""
    if path == "/api/switch":
        from tagteam.cli import _tag_message
        return _tag_message(accounts.switch(body.get("target") or None))
    if path == "/api/account":
        a, num = body.get("action"), str(body.get("number", ""))
        if a == "add":
            return accounts.add_current(body.get("alias") or None)
        if a == "add-token":
            return accounts.add_token(body.get("token", ""), body.get("email") or None)
        if a == "alias":
            return accounts.set_alias(num, body.get("alias") or None)
        if a in ("enable", "disable"):
            return accounts.set_enabled(num, a == "enable")
        if a == "remove":
            return accounts.remove(num)
    if path == "/api/auto":
        a = body.get("action")
        if a == "toggle":
            if not body.get("enabled") and accounts.service_installed():
                accounts.service_uninstall()
            return {"ok": True, **store.set_config(auto={"enabled": bool(body.get("enabled"))})["auto"]}
        if a == "set":
            return accounts.set_auto_setting(body["key"], body["value"])
        if a in ("preview", "once"):
            from tagteam.cli import _describe_events
            events = accounts.auto_once(dry_run=a == "preview")
            return {"ok": True, "events": events, "message": _describe_events(events)}
        if a == "service-install":
            return accounts.service_install()
        if a == "service-uninstall":
            return accounts.service_uninstall()
    if path == "/api/config":
        return {"ok": True, **store.set_config(threshold=float(body["threshold"]))}
    raise accounts.CswapError(f"unknown action {path}")


class Handler(BaseHTTPRequestHandler):
    server_version = "tagteam"

    def log_message(self, *args):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; font-src data:; img-src 'self' data:; "
                         "script-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        # Host check blocks DNS rebinding; the token blocks other local pages/users.
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost") and secrets.compare_digest(
            self.headers.get("X-Tagteam-Token", ""), TOKEN)

    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/index.html"):
            return self._send(200, page().encode("utf-8"), "text/html; charset=utf-8")
        if self.path in ("/favicon.ico", "/favicon.png"):
            return self._send(200, art.png("mascot/icon", 2), "image/png")
        if not self._authorized():
            return self._send(403, b'{"error":"forbidden"}')
        if self.path.startswith("/api/state"):
            data = cached_state(force="force=1" in self.path)
            return self._send(200, json.dumps(data, default=str).encode())
        self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        if not self._authorized():
            return self._send(403, b'{"error":"forbidden"}')
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 64_000)
            body = json.loads(self.rfile.read(length) or b"{}")
            result = act(self.path, body)
            cached_state(force=True)
            self._send(200, json.dumps(result, default=str).encode())
        except (accounts.CswapError, KeyError, ValueError) as e:
            self._send(400, json.dumps({"ok": False, "error": str(e)}).encode())


def _auto_ticker() -> None:
    """Blind tag while the ring is open; cswap's cooldown and lock make concurrent ticks safe."""
    while True:
        time.sleep(60)
        cfg = store.config()["auto"]
        if cfg.get("enabled") and not accounts.service_installed():
            try:
                if any(e.get("event") == "switch" for e in accounts.auto_once()):
                    cached_state(force=True)
            except accounts.CswapError:
                pass


def serve(port: int = 0, open_browser: bool = True) -> None:
    threading.Thread(target=_auto_ticker, daemon=True).start()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/#t={TOKEN}"
    print(f"The ring is open: {url}\n(Ctrl+C to close it)", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
