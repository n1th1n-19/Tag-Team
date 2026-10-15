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
say "Downloading $ASSET"
fetch "$BASE/$ASSET" "$TMP/$ASSET"
fetch "$BASE/SHA256SUMS.txt" "$TMP/SHA256SUMS.txt"

EXPECTED="$(awk -v f="$ASSET" '$2 == f || $2 == "*"f { print $1 }' "$TMP/SHA256SUMS.txt")"
[ -n "$EXPECTED" ] || die "No checksum for $ASSET in SHA256SUMS.txt; nothing was installed."
if have sha256sum; then GOT="$(sha256sum "$TMP/$ASSET" | awk '{print $1}')"; else GOT="$(shasum -a 256 "$TMP/$ASSET" | awk '{print $1}')"; fi
[ "$GOT" = "$EXPECTED" ] || die "$ASSET failed its checksum; nothing was installed."

if have unzip; then unzip -q "$TMP/$ASSET" -d "$TMP"
elif have python3; then python3 -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$TMP/$ASSET" "$TMP"
else die "Need unzip or python3 to unpack $ASSET."; fi
chmod +x "$TMP/tag-team/install/install.sh"

bash "$TMP/tag-team/install/install.sh" "$@"
