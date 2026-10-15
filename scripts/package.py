"""Build dist/tag-team-{macos,linux,windows}.zip and dist/tag-team.vsix. Run from anywhere: python scripts/package.py"""

import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", ".claude", "__pycache__", ".venv", ".playwright-mcp", ".remember", ".claude-plugin/types"}
INSTALL = {
    "macos": "Open Terminal in this folder and run:\n\n    ./install/install.sh\n",
    "linux": "Open a terminal in this folder and run:\n\n    ./install/install.sh\n",
    "windows": "Open PowerShell in this folder and run:\n\n    powershell -ExecutionPolicy Bypass -File install\\install.ps1\n",
}


def files():
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT).as_posix()
        if path.is_file() and not any(rel == s or rel.startswith(s + "/") or f"/{s}/" in f"/{rel}" for s in SKIP):
            yield path, rel


def build_vsix(dist: Path) -> None:
    """The editor extension, with the dashboard page bundled. Needs Node (npx)."""
    if not shutil.which("npx"):
        print("skipping tag-team.vsix (Node.js/npx not found)")
        return
    ext = ROOT / "vscode"
    sys.path.insert(0, str(ROOT))
    from tagteam import art, server  # the ring page with fonts + Figma mascot inlined, and the icon
    (ext / "media").mkdir(exist_ok=True)
    (ext / "media" / "index.html").write_text(server.page(), encoding="utf-8")
    (ext / "media" / "icon.png").write_bytes(art.png("mascot/icon", 4))
    subprocess.run(["npx", "--yes", "@vscode/vsce@3.2.1", "package", "--no-dependencies", "-o", str(dist / "tag-team.vsix")],
                   cwd=ext, check=True, shell=False)


def build_docs_assets() -> None:
    """The download page (GitHub Pages, /docs) gets the same fonts, mascot and icon."""
    sys.path.insert(0, str(ROOT))
    from tagteam import art
    assets = ROOT / "docs" / "assets"
    assets.mkdir(exist_ok=True)
    web = ROOT / "tagteam" / "web"
    for f in ["mascot.js", "fonts/PressStart2P-latin.woff2", "fonts/VT323-latin.woff2", "fonts/OFL-PressStart2P.txt", "fonts/OFL-VT323.txt"]:
        shutil.copy(web / f, assets / Path(f).name)
    (assets / "icon.png").write_bytes(art.png("mascot/icon", 2))


def main() -> None:
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    build_docs_assets()
    build_vsix(dist)
    for osname, howto in INSTALL.items():
        out = dist / f"tag-team-{osname}.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for path, rel in files():
                if rel.startswith("dist/") and rel != "dist/tag-team.vsix":
                    continue
                info = zipfile.ZipInfo(f"tag-team/{rel}")
                info.external_attr = (0o755 if rel.endswith(".sh") else 0o644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, path.read_bytes())
            z.writestr("tag-team/INSTALL.txt", f"Tag Team Wrestling for {osname}\n\n{howto}\nThen, in Claude Code, type /tag-team. In VS Code, click [IN] in the status bar.\n")
        print(f"{out.relative_to(ROOT)}  {out.stat().st_size // 1024} KB")
    for name in ("get.sh", "get.ps1"):
        shutil.copy(ROOT / "install" / name, dist / name)
    assets = sorted(p for p in dist.iterdir() if p.suffix in (".zip", ".vsix", ".sh", ".ps1"))
    (dist / "SHA256SUMS.txt").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in assets))
    print("dist/SHA256SUMS.txt  " + ", ".join(p.name for p in assets))


if __name__ == "__main__":
    main()
