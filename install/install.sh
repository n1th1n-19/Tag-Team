#!/usr/bin/env bash
# Tag Team installer for macOS/Linux (replaces swap-me 0.1): ./install/install.sh [--uninstall]
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_DIR="${TAGTEAM_HOME:-$HOME/.tag-team}"
APP="$HOME_DIR/app"

say() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }
# uv and tagteam live here; a shell opened before the install doesn't have it on PATH yet.
export PATH="$HOME/.local/bin:$PATH"

remove_swap_me() {  # swap-me 0.1, the old name
  have swapme && swapme auto service uninstall >/dev/null 2>&1 || true
  if have claude; then
    claude plugin uninstall swap-me@swap-me >/dev/null 2>&1 || true
    claude plugin marketplace remove swap-me >/dev/null 2>&1 || true
  fi
  have uv && uv tool uninstall swap-me >/dev/null 2>&1 || true
  for editor in code codium cursor; do have "$editor" && "$editor" --uninstall-extension n1th1n-19.swap-me >/dev/null 2>&1 || true; done
  rm -rf "$HOME/.swap-me/app"
}

if [ "${1:-}" = "--uninstall" ]; then
  have tagteam && tagteam corner-man uninstall >/dev/null 2>&1 || true
  have tagteam && tagteam auto-update off >/dev/null 2>&1 || true
  if have claude; then
    claude plugin uninstall tag-team@tag-team >/dev/null 2>&1 || true
    claude plugin marketplace remove tag-team >/dev/null 2>&1 || true
  fi
  have uv && uv tool uninstall tag-team >/dev/null 2>&1 || true
  for editor in code codium cursor; do have "$editor" && "$editor" --uninstall-extension n1th1n-19.tag-team >/dev/null 2>&1 || true; done
  remove_swap_me
  rm -rf "$APP"
  say "Tag Team has left the building. Your match history stays in $HOME_DIR (delete it to remove that too)."
  exit 0
fi

# 1. uv (installs Python 3.12+ and the tools): a pinned release, checked against its SHA-256 before it runs.
UV_VERSION="0.12.13"
install_uv() {
  local os arch target sha tmp
  os="$(uname -s)"; arch="$(uname -m)"
  case "$arch" in x86_64|amd64) arch=x86_64 ;; aarch64|arm64) arch=aarch64 ;; *) arch=unsupported ;; esac
  case "$os" in
    Darwin) target="$arch-apple-darwin" ;;
    Linux) if ldd --version 2>&1 | grep -qi musl; then target="$arch-unknown-linux-musl"; else target="$arch-unknown-linux-gnu"; fi ;;
    *) target=unsupported ;;
  esac
  case "$target" in
    x86_64-unknown-linux-gnu)   sha=745765a3b6e360ad76743599ae5c42e9278c7edf8bbff9fc76d05bf2623a04dd ;;
    aarch64-unknown-linux-gnu)  sha=2eaa5d94f5db7b3a1a092156b9420459e42ab0217d917fe74a876309cef9b5e9 ;;
    x86_64-unknown-linux-musl)  sha=4e2bfd0c9007b1032a50e539e965fd0a6037d87ad93ae1580d220a92d4c94098 ;;
    aarch64-unknown-linux-musl) sha=f44bc1037a17889fe562fffd2002d4ed108e499fbe68b4f022af244dc7b8244f ;;
    x86_64-apple-darwin)        sha=5e287ef61cb6a9b61b3a83fef124fd143e400468a7dac794230147a810e17119 ;;
    aarch64-apple-darwin)       sha=7e6ddb9316acc00f2296c82ff4d99977870ee34b2f0ddcae9444d714db9364ed ;;
    *) say "No pinned uv build for $os/$(uname -m). Install uv yourself (https://docs.astral.sh/uv/), then re-run."; exit 1 ;;
  esac
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  say "Installing uv $UV_VERSION ($target), verified by SHA-256"
  local url="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$target.tar.gz"
  if have curl; then curl --proto '=https' --tlsv1.2 -fsSL "$url" -o "$tmp/uv.tar.gz"
  elif have wget; then wget --https-only -qO "$tmp/uv.tar.gz" "$url"
  else say "Need curl or wget to download uv."; exit 1; fi
  local got
  if have sha256sum; then got="$(sha256sum "$tmp/uv.tar.gz" | awk '{print $1}')"; else got="$(shasum -a 256 "$tmp/uv.tar.gz" | awk '{print $1}')"; fi
  if [ "$got" != "$sha" ]; then say "uv download failed its checksum ($got); nothing was installed."; exit 1; fi
  tar -xzf "$tmp/uv.tar.gz" -C "$tmp"
  mkdir -p "$HOME/.local/bin"
  install -m 0755 "$tmp/uv-$target/uv" "$tmp/uv-$target/uvx" "$HOME/.local/bin/"
  export PATH="$HOME/.local/bin:$PATH"
}
have uv || install_uv

# 2. Old name out. Its history (~/.swap-me) moves to ~/.tag-team the first time tagteam runs.
remove_swap_me

# 3. Stable copy, so deleting the downloaded folder doesn't break the plugin.
say "Setting up the ring in $APP"
mkdir -p "$APP"
if [ "$SRC" != "$APP" ]; then
  rm -rf "$APP.new" && mkdir -p "$APP.new"
  (cd "$SRC" && tar --exclude=.git --exclude='dist/*.zip' --exclude='__pycache__' --exclude=.remember -cf - .) | (cd "$APP.new" && tar -xf -)
  rm -rf "$APP" && mv "$APP.new" "$APP"
fi

# 4. claude-swap (cswap) and tagteam on PATH.
say "Signing claude-swap and tagteam"
uv tool install --upgrade claude-swap >/dev/null 2>&1 || uv tool install claude-swap
uv tool install --force --python 3.12 "$APP"
uv tool update-shell >/dev/null 2>&1 || true
# Move swap-me's history now (any tagteam command that reads ~/.tag-team does it).
TAGTEAM="$(command -v tagteam || echo "$HOME/.local/bin/tagteam")"
"$TAGTEAM" tag-out-point >/dev/null 2>&1 || true

# 5. The Claude Code plugin.
if have claude; then
  say "Bringing the tag-team plugin to Claude Code"
  claude plugin marketplace remove tag-team >/dev/null 2>&1 || true
  claude plugin marketplace add "$APP"
  claude plugin install tag-team@tag-team
else
  say "Claude Code not found. Install it, then run: claude plugin marketplace add \"$APP\" && claude plugin install tag-team@tag-team"
fi

# 6. Editor extension: status bar, TAG ME, the ring (VS Code, VSCodium, Cursor).
VSIX="$APP/dist/tag-team.vsix"
if [ ! -f "$VSIX" ] && have npx; then (cd "$APP" && python3 scripts/package.py >/dev/null 2>&1) || true; fi
if [ -f "$VSIX" ]; then
  for editor in code codium cursor; do
    if have "$editor"; then say "Adding the Tag Team extension to $editor"; "$editor" --install-extension "$VSIX" --force >/dev/null || true; fi
  done
fi

cat <<MSG

TAG TEAM WRESTLING is in the building.
  Claude Code:  /tag-team     the ring          /tag-out   hot tag to the freshest partner
                /tag-in N     tag a partner in  /roster    ring card in the chat
  Terminal:     tagteam               ring card (mascot, roster, match history)
                tagteam tag-out       hot tag
                tagteam ring          the ring in your browser
                tagteam rules         how the match works
  Editors:      [IN] in the status bar; it turns into TAG ME when your partner is worn down.
First time? Sign the account you're logged in as:  tagteam sign --ring-name main
Optional status line: add  "statusLine": {"type": "command", "command": "tagteam statusline"}  to ~/.claude/settings.json
MSG
