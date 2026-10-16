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

# Progress: one animated line per step on a terminal, plain lines otherwise; each step's output goes to $LOG.
LOG="$(mktemp "${TMPDIR:-/tmp}/tag-team-install.XXXXXX")"
STEP=0
STEPS=1
TTY=0
if [ -t 1 ] && [ "${TERM:-dumb}" != dumb ]; then TTY=1; fi
WATCH=0  # 1 while a download step runs: curl's own progress bar (written to $LOG) gives that step's share
pct() {  # finished steps, plus how far the current download is
  local frac=0 last=""
  if [ "$WATCH" = 1 ]; then
    last="$(tail -c 200 "$LOG" 2>/dev/null | tr '\r' '\n' | grep -o '[0-9][0-9]*\.[0-9]%' | tail -n 1 || true)"
    [ -n "$last" ] && frac="${last%%.*}"
  fi
  echo $((((STEP - 1) * 100 + frac) / STEPS))
}
bar() {  # bar PERCENT -> [■■■■□□□□□□□□□□□□□□□□]  20%
  local i out="" n=$(($1 / 5))
  for ((i = 0; i < 20; i++)); do if [ "$i" -lt "$n" ]; then out="${out}■"; else out="${out}□"; fi; done
  printf '[%s] %3d%%' "$out" "$1"
}
fail() { say "$1 failed. The last lines of $LOG:"; tail -n 15 "$LOG" >&2; exit 1; }
step() {  # step "label" command...
  local label="$1"
  shift
  STEP=$((STEP + 1))
  if [ "$TTY" = 0 ]; then
    say "$(bar $(((STEP - 1) * 100 / STEPS))) $label"
    "$@" >>"$LOG" 2>&1 || fail "$label"
    return 0
  fi
  "$@" >>"$LOG" 2>&1 &
  local pid=$! k=0
  local frames=("▱▱▱▱▱" "▰▱▱▱▱" "▰▰▱▱▱" "▰▰▰▱▱" "▰▰▰▰▱" "▰▰▰▰▰")
  while kill -0 "$pid" 2>/dev/null; do
    printf '\r\033[K\033[1;33m%s\033[0m %s %s' "$(bar "$(pct)")" "${frames[$((k % 6))]}" "$label"
    k=$((k + 1))
    sleep 0.12
  done
  if wait "$pid"; then
    printf '\r\033[K\033[1;33m%s\033[0m \033[1;32m✓\033[0m %s\n' "$(bar $((STEP * 100 / STEPS)))" "$label"
  else
    printf '\r\033[K\033[1;33m%s\033[0m \033[1;31m✗\033[0m %s\n' "$(bar "$(pct)")" "$label"
    fail "$label"
  fi
}

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
  stop_jobs() { have tagteam || return 0; tagteam corner-man uninstall || true; tagteam auto-update off || true; }
  remove_plugin() {
    claude plugin uninstall tag-team@tag-team || true
    claude plugin marketplace remove tag-team || true
    rm -rf "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins/cache/tag-team"  # the copies Claude Code keeps of every version
  }
  remove_tool() { have uv && uv tool uninstall tag-team || true; }
  remove_extension() { "$1" --uninstall-extension n1th1n-19.tag-team || true; }
  remove_files() { remove_swap_me; rm -rf "$APP" "$APP.new"; }
  EDITORS=""
  for editor in code codium cursor; do if have "$editor"; then EDITORS="$EDITORS $editor"; fi; done
  STEPS=3
  have claude && STEPS=$((STEPS + 1))
  for editor in $EDITORS; do STEPS=$((STEPS + 1)); done
  step "Stopping the corner man and auto-update" stop_jobs
  have claude && step "Removing the tag-team plugin from Claude Code" remove_plugin
  for editor in $EDITORS; do step "Removing the Tag Team extension from $editor" remove_extension "$editor"; done
  step "Removing tagteam" remove_tool
  step "Removing the app folder" remove_files
  [ "$TTY" = 1 ] || say "$(bar 100) done"
  rm -f "$LOG"
  say "Tag Team has left the building. Your match history stays in $HOME_DIR (delete it to remove that too)."
  exit 0
fi

# 1. uv (installs Python 3.12+ and the tools): a pinned release, checked against its SHA-256 before it runs.
UV_VERSION="0.12.13"
install_uv() (  # a subshell, so its cleanup trap can't leak into the rest of the install
  os="" arch="" target="" sha="" tmp=""
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
  trap 'rm -rf "$tmp"' EXIT
  url="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$target.tar.gz"
  if have curl; then curl --proto '=https' --tlsv1.2 -fsSL --connect-timeout 20 --retry 3 --speed-limit 1024 --speed-time 30 "$url" -o "$tmp/uv.tar.gz"
  elif have wget; then wget --https-only -qO "$tmp/uv.tar.gz" --timeout=30 --tries=3 "$url"
  else say "Need curl or wget to download uv."; exit 1; fi
  got=""
  if have sha256sum; then got="$(sha256sum "$tmp/uv.tar.gz" | awk '{print $1}')"; else got="$(shasum -a 256 "$tmp/uv.tar.gz" | awk '{print $1}')"; fi
  if [ "$got" != "$sha" ]; then say "uv download failed its checksum ($got); nothing was installed."; exit 1; fi
  tar -xzf "$tmp/uv.tar.gz" -C "$tmp"
  mkdir -p "$HOME/.local/bin"
  install -m 0755 "$tmp/uv-$target/uv" "$tmp/uv-$target/uvx" "$HOME/.local/bin/"
)
# 2-3. Old name out (its history in ~/.swap-me moves to ~/.tag-team the first time tagteam runs), then a
# stable copy of the app, so deleting the downloaded folder doesn't break the plugin.
setup_ring() {
  remove_swap_me
  mkdir -p "$APP"
  if [ "$SRC" != "$APP" ]; then
    rm -rf "$APP.new" && mkdir -p "$APP.new"
    (cd "$SRC" && tar --exclude=.git --exclude='dist/*.zip' --exclude='__pycache__' --exclude=.remember -cf - .) | (cd "$APP.new" && tar -xf -)
    rm -rf "$APP" && mv "$APP.new" "$APP"
  fi
}

# 4. claude-swap (cswap) and tagteam on PATH; then move swap-me's history (any tagteam command that reads ~/.tag-team does it).
sign_tools() {
  uv tool install --upgrade claude-swap || uv tool install claude-swap
  uv tool install --force --python 3.12 "$APP"
  uv tool update-shell || true
  "$(command -v tagteam || echo "$HOME/.local/bin/tagteam")" tag-out-point || true
}

# 5. The Claude Code plugin.
add_plugin() {
  claude plugin marketplace remove tag-team || true
  claude plugin marketplace add "$APP"
  claude plugin install tag-team@tag-team
}

# 6. Editor extension: status bar, TAG ME, the ring (VS Code, VSCodium, Cursor).
add_extension() { "$1" --install-extension "$VSIX" --force; }

# 7. Old plugin copies Claude Code keeps, leftover update downloads (tagteam cleanup).
tidy() { "$(command -v tagteam || echo "$HOME/.local/bin/tagteam")" cleanup || true; }

VSIX="$APP/dist/tag-team.vsix"
[ -f "$SRC/dist/tag-team.vsix" ] && VSIX_SRC="$SRC/dist/tag-team.vsix" || VSIX_SRC=""
EDITORS=""
for editor in code codium cursor; do if have "$editor"; then EDITORS="$EDITORS $editor"; fi; done
STEPS=3
have uv || STEPS=$((STEPS + 1))
have claude && STEPS=$((STEPS + 1))
if [ -n "$VSIX_SRC" ] || have npx; then for editor in $EDITORS; do STEPS=$((STEPS + 1)); done; fi

have uv || step "Getting uv $UV_VERSION (checksum-verified)" install_uv
step "Setting up the ring" setup_ring
step "Installing claude-swap and tagteam" sign_tools
if have claude; then
  step "Bringing the tag-team plugin to Claude Code" add_plugin
fi
if [ ! -f "$VSIX" ] && have npx; then (cd "$APP" && python3 scripts/package.py >>"$LOG" 2>&1) || true; fi
if [ -f "$VSIX" ]; then
  for editor in $EDITORS; do step "Adding the Tag Team extension to $editor" add_extension "$editor"; done
fi
step "Cleaning up old versions" tidy
[ "$TTY" = 1 ] || say "$(bar 100) done"
have claude || say "Claude Code not found. Install it, then run: claude plugin marketplace add \"$APP\" && claude plugin install tag-team@tag-team"
rm -f "$LOG"

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
Want to hear about new releases?  tagteam update --notify on
Optional status line: add  "statusLine": {"type": "command", "command": "tagteam statusline"}  to ~/.claude/settings.json
MSG
