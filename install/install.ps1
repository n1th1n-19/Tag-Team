# Tag Team installer for Windows (replaces swap-me 0.1): powershell -ExecutionPolicy Bypass -File install\install.ps1 [-Uninstall]
param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$Src = Split-Path -Parent $PSScriptRoot
$HomeDir = if ($env:TAGTEAM_HOME) { $env:TAGTEAM_HOME } else { Join-Path $env:USERPROFILE ".tag-team" }
$App = Join-Path $HomeDir "app"
function Say($m) { Write-Host "==> $m" -ForegroundColor Yellow }
function Have($c) { [bool](Get-Command $c -ErrorAction SilentlyContinue) }
$Editors = @("code", "codium", "cursor")

function Remove-SwapMe {
  if (Have swapme) { try { swapme auto service uninstall | Out-Null } catch {} }
  if (Have claude) { try { claude plugin uninstall swap-me@swap-me | Out-Null } catch {}; try { claude plugin marketplace remove swap-me | Out-Null } catch {} }
  if (Have uv) { try { uv tool uninstall swap-me | Out-Null } catch {} }
  foreach ($e in $Editors) { if (Have $e) { try { & $e --uninstall-extension n1th1n-19.swap-me | Out-Null } catch {} } }
  Remove-Item -Recurse -Force (Join-Path $env:USERPROFILE ".swap-me\app") -ErrorAction SilentlyContinue
}

if ($Uninstall) {
  if (Have tagteam) { try { tagteam corner-man uninstall | Out-Null } catch {} }
  if (Have claude) { try { claude plugin uninstall tag-team@tag-team | Out-Null } catch {}; try { claude plugin marketplace remove tag-team | Out-Null } catch {} }
  if (Have uv) { try { uv tool uninstall tag-team | Out-Null } catch {} }
  foreach ($e in $Editors) { if (Have $e) { try { & $e --uninstall-extension n1th1n-19.tag-team | Out-Null } catch {} } }
  Remove-SwapMe
  Remove-Item -Recurse -Force $App -ErrorAction SilentlyContinue
  Say "Tag Team has left the building. Match history stays in $HomeDir."
  exit 0
}

if (-not (Have uv)) {
  Say "Installing uv (Python tool manager from astral.sh)"
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Remove-SwapMe

Say "Setting up the ring in $App"
if ((Resolve-Path $Src).Path -ne $App) {
  Remove-Item -Recurse -Force $App -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force -Path $App | Out-Null
  Get-ChildItem -Force $Src | Where-Object { $_.Name -notin @(".git", "__pycache__", ".remember") } |
    Copy-Item -Destination $App -Recurse -Force
  Get-ChildItem (Join-Path $App "dist") -Filter *.zip -ErrorAction SilentlyContinue | Remove-Item -Force
}

Say "Signing claude-swap and tagteam"
try { uv tool install --upgrade claude-swap } catch { uv tool install claude-swap }
uv tool install --force --python 3.12 $App
try { uv tool update-shell | Out-Null } catch {}
# Move swap-me's history now (any tagteam command that reads ~/.tag-team does it).
try { & (Join-Path $env:USERPROFILE ".local\bin\tagteam.exe") tag-out-point | Out-Null } catch {}

if (Have claude) {
  Say "Bringing the tag-team plugin to Claude Code"
  try { claude plugin marketplace remove tag-team | Out-Null } catch {}
  claude plugin marketplace add $App
  claude plugin install tag-team@tag-team
} else {
  Say "Claude Code not found. Install it, then run: claude plugin marketplace add `"$App`"; claude plugin install tag-team@tag-team"
}

$Vsix = Join-Path $App "dist\tag-team.vsix"
if (Test-Path $Vsix) {
  foreach ($e in $Editors) { if (Have $e) { Say "Adding the Tag Team extension to $e"; try { & $e --install-extension $Vsix --force | Out-Null } catch {} } }
}

Write-Host @"

TAG TEAM WRESTLING is in the building.
  Claude Code:  /tag-team (the ring)   /tag-in N   /tag-out (hot tag)   /roster
  Terminal:     tagteam   tagteam tag-out   tagteam ring   tagteam rules
  Editors:      [IN] in the status bar; it turns into TAG ME when your partner is worn down.
First time? Sign the account you're logged in as:  tagteam sign --ring-name main
If the plugin can't find tagteam, set its path in /config (tag-team > tagteam command):
  $env:USERPROFILE\.local\bin\tagteam.exe
"@
