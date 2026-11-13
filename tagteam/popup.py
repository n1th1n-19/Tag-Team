"""The ring-side island: a pill at the top of the screen that springs open with a notification.

Run as `python -m tagteam.popup KIND TITLE MESSAGE`. Prints "ok" once the window is up, so the
caller knows to skip the OS toast. Stdlib only (tkinter); the motion is real spring physics.
"""

from __future__ import annotations

import base64
import math
import os
import sys
import time

# kind -> (emoji, ring-voice title, accent)
GOLD, RED, BLUE = "#f2c14e", "#d94141", "#3f6fd1"
KINDS = {
    "approval": ("🔐", "Referee's call!", GOLD),
    "question": ("🎤", "Mic check!", BLUE),
    "plan": ("📋", "Match card ready", BLUE),
    "done": ("🏆", "And the winner is…", GOLD),
    "error": ("💥", "Down for the count", RED),
    "claude": ("🔔", "Ringside update", GOLD),
    "tagme": ("🤼", "TAG ME!", RED),
}
INK, MUTED, BLACK = "#f4f1e8", "#a9a6b8", "#000000"
PILL = (140, 40)        # compact island
OPEN = (380, 88)        # expanded island
HOLD = 5.0              # seconds the expanded island stays (hover pauses it)
FRAME_MS, DT = 16, 1 / 120


def title_for(kind: str, title: str | None = None) -> str:
    """Emoji + title: the given title, or the kind's ring-voice default. No second emoji."""
    emoji, default, _ = KINDS.get(kind, KINDS["claude"])
    title = (title or "").strip() or default
    return title if not title[:1].isascii() else f"{emoji} {title}"


class Spring:
    """Damped spring, mass 1, integrated with semi-implicit Euler (stable at small fixed dt)."""

    def __init__(self, value: float, stiffness: float, damping: float, eps: float = 0.5):
        self.value, self.target, self.velocity = float(value), float(value), 0.0
        self.k, self.c, self.eps = stiffness, damping, eps

    def to(self, target: float, stiffness: float | None = None, damping: float | None = None) -> None:
        """Retarget, keeping the current velocity, so an interrupted motion carries on without a jump."""
        self.target = float(target)
        self.k = stiffness if stiffness is not None else self.k
        self.c = damping if damping is not None else self.c

    def step(self, dt: float = DT) -> float:
        self.velocity += (-self.k * (self.value - self.target) - self.c * self.velocity) * dt
        self.value += self.velocity * dt
        return self.value

    @property
    def settled(self) -> bool:
        return abs(self.value - self.target) < self.eps and abs(self.velocity) < self.eps * 10


def _mix(a: str, b: str, t: float) -> str:
    """Color from a to b; canvas text has no alpha, so opacity is a blend toward the black pill."""
    t = max(0.0, min(1.0, t))
    pa, pb = (int(a[i:i + 2], 16) for i in (1, 3, 5)), (int(b[i:i + 2], 16) for i in (1, 3, 5))
    r, g, b = (round(x + (y - x) * t) for x, y in zip(pa, pb))
    return f"#{r:02x}{g:02x}{b:02x}"


def _pidfile():
    from tagteam import store
    path = store.home() / "cache" / "popup.pid"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _replace_previous() -> None:
    # ponytail: a new island replaces the old one; queue/morph between them if pings ever pile up.
    import signal
    try:
        path = _pidfile()
        old = int(path.read_text())
        if old != os.getpid():
            os.kill(old, signal.SIGTERM)
    except (OSError, ValueError):
        pass
    try:
        _pidfile().write_text(str(os.getpid()))
    except OSError:
        pass


class Island:
    def __init__(self, kind: str, title: str, message: str):
        import tkinter as tk
        from tkinter import font as tkfont

        from tagteam import art

        self.tk = tk
        self.emoji, _, self.accent = KINDS.get(kind, KINDS["claude"])
        title = title_for(kind, title)
        # Tk 8.6 can't draw (or crashes on) characters outside the BMP; X11 Tk draws color emoji as blanks.
        if tk.TkVersion < 8.7 or sys.platform.startswith("linux"):
            title = "".join(ch for ch in title if ord(ch) <= 0xFFFF).strip()
        self.title, self.message = title, message
        root = self.root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        if sys.platform.startswith("win"):
            key = "#010203"
            root.attributes("-transparentcolor", key)
        elif sys.platform == "darwin":
            key = "systemTransparent"
            root.attributes("-transparent", True)
        else:
            # ponytail: X11 Tk has no per-pixel alpha, so the pill's corners show black (same as the pill);
            # a GTK4 + layer-shell path would round them, when gi is around.
            key = BLACK
        # Square corners show on X11, so keep the curve tight there; true pills where corners are see-through.
        self.round_pill, self.round_open = (12, 16) if key == BLACK else (PILL[1] / 2, 28)
        root.config(bg=key)
        self.canvas = tk.Canvas(root, bg=key, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        families = set(tkfont.families(root))
        if "Press Start 2P" in families:
            self.title_font = tkfont.Font(root, family="Press Start 2P", size=10)
        else:
            self.title_font = tkfont.nametofont("TkFixedFont", root).copy()
            self.title_font.configure(size=12, weight="bold")
        self.body_font = tkfont.nametofont("TkDefaultFont", root).copy()
        self.body_font.configure(size=11)
        # Grow the island to fit the message: up to 3 lines beside the mascot.
        self.text_x = 14 + 64 + 12
        lines = min(3, max(1, -(-self.body_font.measure(message) // (OPEN[0] - self.text_x - 16))))
        self.open_h = max(OPEN[1], 44 + lines * self.body_font.metrics("linespace") + 18)
        self.icon_small = tk.PhotoImage(data=base64.b64encode(art.png("mascot/icon", 1)))
        self.icon_big = tk.PhotoImage(data=base64.b64encode(art.png("mascot/icon", 2)))

        # Height lands first, width wobbles after it; radius and content follow on their own springs.
        self.w = Spring(0, 260, 20)
        self.h = Spring(PILL[1], 320, 26)
        self.r = Spring(self.round_pill, 300, 30)
        self.alpha = Spring(0, 220, 30, eps=0.01)
        self.w.to(PILL[0])
        self.phase, self.phase_at, self.left, self.hover = "pill", time.monotonic(), HOLD, False
        self.last = time.monotonic()
        root.bind("<Button-1>", lambda e: self.close())
        root.bind("<Enter>", lambda e: setattr(self, "hover", True))
        root.bind("<Leave>", lambda e: setattr(self, "hover", False))
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        self.screen_w = root.winfo_screenwidth()

    def show(self) -> None:
        self.place()
        self.root.deiconify()
        self.root.update()
        print("ok", flush=True)
        try:  # the caller stops reading after "ok"; nothing else goes to its pipe
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, 1)
        except OSError:
            pass
        self.root.after(FRAME_MS, self.tick)
        self.root.mainloop()

    def close(self) -> None:
        if self.phase in ("close", "vanish"):
            return
        self.phase = "close"
        # Critically damped (c = 2·√k): back to the pill with no bounce.
        self.w.to(PILL[0], 400, 40)
        self.h.to(PILL[1], 400, 40)
        self.r.to(self.round_pill, 400, 40)
        self.alpha.to(0, 400, 40)

    def tick(self) -> None:
        now = time.monotonic()
        elapsed, self.last = now - self.last, now
        for _ in range(2):
            for s in (self.w, self.h, self.r, self.alpha):
                s.step()
        if self.phase == "pill" and (self.w.settled or now - self.phase_at > 0.35):
            self.phase = "open"
            self.w.to(OPEN[0])
            self.h.to(self.open_h)
            self.r.to(self.round_open)
        elif self.phase == "open":
            if self.w.value > OPEN[0] * 0.85:
                self.alpha.to(1)
            if self.alpha.value > 0.5 and not self.hover:
                self.left -= elapsed
            if self.left <= 0:
                self.close()
        elif self.phase == "close" and self.w.settled and self.h.settled:
            self.phase = "vanish"
            self.w.to(0, 400, 40)
        elif self.phase == "vanish" and self.w.value < 2:
            self.root.destroy()
            return
        self.place()
        self.draw(now)
        self.root.after(FRAME_MS, self.tick)

    def place(self) -> None:
        w, h = max(1, round(self.w.value)), max(1, round(self.h.value))
        self.root.geometry(f"{w}x{h}+{(self.screen_w - w) // 2}+8")

    def draw(self, now: float) -> None:
        c = self.canvas
        c.delete("all")
        w, h = max(2.0, self.w.value), max(2.0, self.h.value)
        r = max(1.0, min(self.r.value, h / 2, w / 2))
        self.capsule(1, 1, w - 1, h - 1, r)
        a = self.alpha.value
        if a < 0.15:  # compact: mascot left, pulsing dot right
            c.create_image(4 + r * 0.2, h / 2, image=self.icon_small, anchor="w")
            pulse = 4 + 1.5 * (1 + math.sin(now * 6))
            if w > 70:
                c.create_oval(w - 18 - pulse, h / 2 - pulse, w - 18 + pulse, h / 2 + pulse, fill=self.accent, outline="")
            return
        c.create_image(14, h / 2, image=self.icon_big, anchor="w")
        x = self.text_x
        c.create_text(x, 14, text=self.title, anchor="nw", fill=_mix(BLACK, INK, a), font=self.title_font)
        c.create_text(x, 40, text=self.message, anchor="nw", fill=_mix(BLACK, MUTED, a), font=self.body_font,
                      width=max(10, w - x - 16))
        bar = (w - x - 24) * max(0.0, self.left / HOLD)
        if bar > 1:
            c.create_rectangle(x, h - 12, x + bar, h - 9, fill=_mix(BLACK, self.accent, a), outline="")

    def capsule(self, x1: float, y1: float, x2: float, y2: float, r: float) -> None:
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
               x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        self.canvas.create_polygon(pts, smooth=True, fill=BLACK, outline=self.accent, width=2)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: python -m tagteam.popup KIND TITLE MESSAGE", file=sys.stderr)
        return 2
    try:
        island = Island(*argv)
    except Exception as exc:  # noqa: BLE001 - no tkinter, no display: the caller falls back to the OS toast
        print(f"no island: {exc}", file=sys.stderr)
        return 1
    _replace_previous()
    island.show()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
