"""The ring bell: a short brass "ding" made with the stdlib, struck once per ding a notification calls for.

`ring(dings)` plays it without blocking: a detached `python -m tagteam.bell N`, which uses the
platform's own player (winsound, afplay, pw-play/paplay/aplay). Run directly to hear it.
"""

from __future__ import annotations

import io
import math
import struct
import sys
import wave

RATE = 22050
# Inharmonic partials of a struck bell (ratio, loudness, decay per second): the "brass" in the ding.
PARTIALS = ((1.0, 1.0, 3.2), (2.76, 0.45, 5.5), (5.40, 0.25, 9.0), (8.93, 0.12, 14.0))
BASE_HZ, STRIKE_GAP, TAIL = 1046.5, 0.16, 0.9   # C6, a referee's quick double-strike, then let it ring
# How many strikes each kind gets: the bell says what happened before you look.
DINGS = {"approval": 2, "question": 2, "plan": 2, "done": 3, "error": 1, "claude": 1, "tagme": 3}


def wav(dings: int = 1) -> bytes:
    """16-bit mono WAV of the bell struck `dings` times."""
    dings = max(1, min(5, int(dings)))
    length = int(RATE * (STRIKE_GAP * (dings - 1) + TAIL))
    samples = [0.0] * length
    for d in range(dings):
        start = int(RATE * STRIKE_GAP * d)
        for i in range(length - start):
            t = i / RATE
            attack = min(1.0, t / 0.002)  # 2ms: a strike, not a click
            v = sum(a * math.exp(-k * t) * math.sin(2 * math.pi * BASE_HZ * r * t) for r, a, k in PARTIALS)
            samples[start + i] += attack * v
    peak = max(1e-9, max(abs(s) for s in samples))
    frames = b"".join(struct.pack("<h", int(s / peak * 0.6 * 32767)) for s in samples)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)
    return out.getvalue()


def path(dings: int):
    """The cached WAV for `dings` strikes (made once)."""
    from tagteam import store
    p = store.home() / "cache" / f"bell-{dings}.wav"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(wav(dings))
    return p


def play(file: str) -> bool:
    """Play a WAV and wait for it; True if some player took it."""
    import shutil
    import subprocess
    if sys.platform.startswith("win"):
        import winsound
        winsound.PlaySound(file, winsound.SND_FILENAME)
        return True
    players = [["afplay", file]] if sys.platform == "darwin" else [["pw-play", file], ["paplay", file], ["aplay", "-q", file]]
    for argv in players:
        if shutil.which(argv[0]):
            try:
                if subprocess.run(argv, capture_output=True, timeout=10, check=False).returncode == 0:
                    return True
            except (OSError, subprocess.SubprocessError):
                continue
    return False


def ring(kind: str) -> None:
    """Strike the bell for a notification kind, in the background; never raises."""
    import subprocess
    try:
        file = str(path(DINGS.get(kind, 1)))
        subprocess.Popen([sys.executable, "-m", "tagteam.bell", file], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=not sys.platform.startswith("win"),
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:  # noqa: BLE001, S110 - a missing sound must never cost the notification
        pass


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "2"
    sys.exit(0 if play(arg if not arg.isdigit() else str(path(int(arg)))) else 1)
