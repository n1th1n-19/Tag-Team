#!/usr/bin/env bash
# Tag Team one-liner (macOS/Linux): curl -fsSL https://github.com/n1th1n-19/tag-team/releases/latest/download/get.sh | bash [-s -- --uninstall]
set -euo pipefail

REPO="n1th1n-19/tag-team"
if [ -n "${TAGTEAM_VERSION:-}" ]; then BASE="https://github.com/$REPO/releases/download/$TAGTEAM_VERSION"
else BASE="https://github.com/$REPO/releases/latest/download"; fi
BASE="${TAGTEAM_BASE_URL:-$BASE}"
APP="${TAGTEAM_HOME:-$HOME/.tag-team}/app"

say() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
die() { say "$*"; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

if [ "${1:-}" = "--uninstall" ] && [ -f "$APP/install/install.sh" ]; then
  exec bash "$APP/install/install.sh" --uninstall
fi

case "$(uname -s)" in
  Darwin) ASSET="tag-team-macos.zip" ;;
  Linux) ASSET="tag-team-linux.zip" ;;
  *) die "Unsupported system $(uname -s). On Windows use: irm https://github.com/$REPO/releases/latest/download/get.ps1 | iex" ;;
esac

fetch() {
  if have curl; then
    if [ "${BASE#https://}" != "$BASE" ]; then curl --proto '=https' --tlsv1.2 -fsSL "$1" -o "$2"; else curl -fsSL "$1" -o "$2"; fi
  elif have wget; then wget -qO "$2" "$1"
  else die "Need curl or wget."; fi
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Progress: one animated line per step on a terminal, plain lines otherwise; step output goes to a log.
LOG="$TMP/get.log"
STEP=0
STEPS=3
TTY=0
if [ -t 1 ] && [ "${TERM:-dumb}" != dumb ]; then TTY=1; fi
WATCH=""; WATCH_SIZE=0  # while a download step runs: the file being written and its full size
pct() {  # finished steps, plus how far the current one is (by bytes when a download is being watched)
  local frac=0 size
  if [ -n "$WATCH" ] && [ "$WATCH_SIZE" -gt 0 ] && [ -f "$WATCH" ]; then
    size=$(wc -c <"$WATCH" | tr -d ' ')
    frac=$((size * 100 / WATCH_SIZE)); [ "$frac" -gt 100 ] && frac=100
  fi
  echo $((((STEP - 1) * 100 + frac) / STEPS))
}
bar() {  # bar PERCENT -> [■■■■□□□□□□□□□□□□□□□□]  20%
  local i out="" n=$(($1 / 5))
  for ((i = 0; i < 20; i++)); do if [ "$i" -lt "$n" ]; then out="${out}■"; else out="${out}□"; fi; done
  printf '[%s] %3d%%' "$out" "$1"
}
step() {  # step "label" command...
  local label="$1"
  shift
  STEP=$((STEP + 1))
  if [ "$TTY" = 0 ]; then
    say "$(bar $(((STEP - 1) * 100 / STEPS))) $label"
    "$@" >>"$LOG" 2>&1 || { tail -n 15 "$LOG" >&2; die "$label failed; nothing was installed."; }
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
    tail -n 15 "$LOG" >&2
    die "$label failed; nothing was installed."
  fi
}

download() { fetch "$BASE/$ASSET" "$TMP/$ASSET" && fetch "$BASE/SHA256SUMS.txt" "$TMP/SHA256SUMS.txt"; }
remote_size() {  # the download's size after redirects (for the percentage), 0 when unknown
  have curl || { echo 0; return; }
  curl -fsIL "$1" 2>/dev/null | awk 'tolower($1) == "content-length:" { gsub("\r", "", $2); n = $2 } END { print n + 0 }'
}
verify() {
  local expected got
  expected="$(awk -v f="$ASSET" '$2 == f || $2 == "*"f { print $1 }' "$TMP/SHA256SUMS.txt")"
  [ -n "$expected" ] || { echo "No checksum for $ASSET in SHA256SUMS.txt"; return 1; }
  if have sha256sum; then got="$(sha256sum "$TMP/$ASSET" | awk '{print $1}')"; else got="$(shasum -a 256 "$TMP/$ASSET" | awk '{print $1}')"; fi
  [ "$got" = "$expected" ] || { echo "$ASSET failed its checksum"; return 1; }
}
unpack() {
  if have unzip; then unzip -q "$TMP/$ASSET" -d "$TMP"
  elif have python3; then python3 -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$TMP/$ASSET" "$TMP"
  else echo "Need unzip or python3 to unpack $ASSET"; return 1; fi
  chmod +x "$TMP/tag-team/install/install.sh"
}

WATCH="$TMP/$ASSET"
WATCH_SIZE="$(remote_size "$BASE/$ASSET")"
step "Downloading $ASSET" download
WATCH=""
step "Checking it against SHA256SUMS.txt" verify
step "Unpacking" unpack

bash "$TMP/tag-team/install/install.sh" "$@"
