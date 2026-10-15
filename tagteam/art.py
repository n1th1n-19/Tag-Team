"""The mascot, from the Figma export in web/mascot.js: PNG icons and a terminal banner."""

from __future__ import annotations

import json
import struct
import zlib
from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=1)
def mascot() -> dict:
    """{'palette': {key: '#rrggbb'}, 'frames': {name: [row, ...]}} parsed from mascot.js."""
    text = resources.files("tagteam").joinpath("web/mascot.js").read_text(encoding="utf-8")
    start = text.index("const MASCOT = ") + len("const MASCOT = ")
    return json.loads(text[start:text.index(";\n", start)])


def _rgb(hex_: str) -> tuple[int, int, int]:
    return int(hex_[1:3], 16), int(hex_[3:5], 16), int(hex_[5:7], 16)


def png(name: str = "mascot/icon", scale: int = 4) -> bytes:
    """RGBA PNG of a frame, each art pixel a scale x scale block (stdlib only)."""
    m = mascot()
    rows = m["frames"][name]
    w, h = len(rows[0]) * scale, len(rows) * scale
    raw = bytearray()
    for row in rows:
        line = bytearray([0])
        for ch in row:
            px = bytes((0, 0, 0, 0)) if ch == "." else bytes((*_rgb(m["palette"][ch]), 255))
            line += px * scale
        raw += bytes(line) * scale

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")


def banner(name: str = "mascot/icon", color: bool = True) -> list[str]:
    """Terminal art: two art rows per line with '▀' (fg = top pixel, bg = bottom pixel)."""
    m = mascot()
    rows = [r for r in m["frames"][name] if r.strip(".")]
    if len(rows) % 2:
        rows.append("." * len(rows[0]))
    lines = []
    for top, bottom in zip(rows[::2], rows[1::2]):
        out = ""
        for a, b in zip(top, bottom):
            if not color:
                out += " " if a == b == "." else "█" if a != "." and b != "." else "▀" if a != "." else "▄"
                continue
            if a == b == ".":
                out += " "
            elif b == ".":
                out += "\x1b[38;2;%d;%d;%dm▀\x1b[0m" % _rgb(m["palette"][a])
            elif a == ".":
                out += "\x1b[38;2;%d;%d;%dm▄\x1b[0m" % _rgb(m["palette"][b])
            else:
                out += "\x1b[38;2;%d;%d;%dm\x1b[48;2;%d;%d;%dm▀\x1b[0m" % (*_rgb(m["palette"][a]), *_rgb(m["palette"][b]))
        lines.append(out.rstrip())
    return lines
