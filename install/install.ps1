# Tag Team installer for Windows (replaces swap-me 0.1): powershell -ExecutionPolicy Bypass -File install\install.ps1 [-Uninstall]
param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$Src = Split-Path -Parent $PSScriptRoot
$HomeDir = if ($env:TAGTEAM_HOME) { $env:TAGTEAM_HOME } else { Join-Path $env:USERPROFILE ".tag-team" }
$App = Join-Path $HomeDir "app"
function Say($m) { Write-Host "==> $m" -ForegroundColor Yellow }
function Have($c) { [bool](Get-Command $c -ErrorAction SilentlyContinue) }
$Editors = @("code", "codium", "cursor")
# uv and tagteam live here; a terminal opened before the install doesn't have it on PATH yet.
$env:Path = (Join-Path $env:USERPROFILE ".local\bin") + ";" + $env:Path

function Remove-SwapMe {
  if (Have swapme) { try { swapme auto service uninstall | Out-Null } catch {} }
  if (Have claude) { try { claude plugin uninstall swap-me@swap-me | Out-Null } catch {}; try { claude plugin marketplace remove swap-me | Out-Null } catch {} }
  if (Have uv) { try { uv tool uninstall swap-me | Out-Null } catch {} }
  foreach ($e in $Editors) { if (Have $e) { try { & $e --uninstall-extension n1th1n-19.swap-me | Out-Null } catch {} } }
  Remove-Item -Recurse -Force (Join-Path $env:USERPROFILE ".swap-me\app") -ErrorAction SilentlyContinue
}

# Progress: the native progress bar plus one line per step, with the overall percentage.
$script:StepN = 0
$script:StepTotal = 1
$script:Activity = "Tag Team Wrestling"
function Step($label) {
  $script:StepN++
  $pct = [int](100 * ($script:StepN - 1) / $script:StepTotal)
  Write-Progress -Activity $script:Activity -Status "$pct% - step $($script:StepN) of $($script:StepTotal): $label" -PercentComplete $pct
  $filled = [int]($pct / 5)
  Write-Host ("[" + ("#" * $filled) + ("-" * (20 - $filled)) + "] " + "$pct%".PadLeft(4) + " $label") -ForegroundColor Yellow
}
function Done-Steps {
  Write-Host ("[" + ("#" * 20) + "] 100% done") -ForegroundColor Yellow
  Write-Progress -Activity $script:Activity -Completed
}

if ($Uninstall) {
  $script:Activity = "Tag Team Wrestling: uninstall"
  $found = @($Editors | Where-Object { Have $_ })
  $script:StepTotal = 3 + [int](Have claude) + $found.Count
  Step "Stopping the corner man and auto-update"
  if (Have tagteam) { try { tagteam corner-man uninstall | Out-Null } catch {}; try { tagteam auto-update off | Out-Null } catch {} }
  if (Have claude) {
    Step "Removing the tag-team plugin from Claude Code"
    try { claude plugin uninstall tag-team@tag-team | Out-Null } catch {}; try { claude plugin marketplace remove tag-team | Out-Null } catch {}
    $cfg = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $env:USERPROFILE ".claude" }
    Remove-Item -Recurse -Force (Join-Path $cfg "plugins\cache\tag-team") -ErrorAction SilentlyContinue
  }
  foreach ($e in $found) { Step "Removing the Tag Team extension from $e"; try { & $e --uninstall-extension n1th1n-19.tag-team | Out-Null } catch {} }
  Step "Removing tagteam"
  if (Have uv) { try { uv tool uninstall tag-team | Out-Null } catch {} }
  Step "Removing the app folder"
  Remove-SwapMe
  Remove-Item -Recurse -Force $App, "$App.new" -ErrorAction SilentlyContinue
  Done-Steps
  Say "Tag Team has left the building. Match history stays in $HomeDir."
  exit 0
}

# uv (installs Python 3.12+ and the tools): a pinned release, checked against its SHA-256 before it runs.
$UvVersion = "0.12.13"
$UvBuilds = @{
  "AMD64" = @("x86_64-pc-windows-msvc", "a86c9dc7bad9b03f388583b7187c05fe9951c2e0d392217e8fd43d97787f6ec2")
  "ARM64" = @("aarch64-pc-windows-msvc", "1efb2654b06e7063d4ac1fc9d49a9bda9a6704d82f035b589a2751a592f14151")
}
function Install-Uv {
  $ProgressPreference = "SilentlyContinue"
  $arch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
  if (-not $UvBuilds.ContainsKey($arch)) { throw "No pinned uv build for $arch. Install uv yourself (https://docs.astral.sh/uv/), then re-run." }
  $target, $sha = $UvBuilds[$arch]
  $tmp = Join-Path ([IO.Path]::GetTempPath()) ("uv-" + [guid]::NewGuid())
  New-Item -ItemType Directory -Path $tmp | Out-Null
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $zip = Join-Path $tmp "uv.zip"
    Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-$target.zip" -OutFile $zip
    $got = (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLower()
    if ($got -ne $sha) { throw "uv download failed its checksum ($got); nothing was installed." }
    Expand-Archive -Path $zip -DestinationPath (Join-Path $tmp "x") -Force
    $bin = Join-Path $env:USERPROFILE ".local\bin"
    New-Item -ItemType Directory -Force -Path $bin | Out-Null
    Get-ChildItem -Recurse (Join-Path $tmp "x") -Include uv.exe, uvx.exe, uvw.exe | Copy-Item -Destination $bin -Force
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (($userPath -split ";") -notcontains $bin) { [Environment]::SetEnvironmentVariable("Path", "$bin;$userPath", "User") }
    $env:Path = "$bin;$env:Path"
  } finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
  }
}
$HasVsix = Test-Path (Join-Path $Src "dist\tag-team.vsix")
$script:StepTotal = 3 + [int](-not (Have uv)) + [int](Have claude) + [int]$HasVsix * @($Editors | Where-Object { Have $_ }).Count

if (-not (Have uv)) { Step "Getting uv $UvVersion (checksum-verified)"; Install-Uv }

Remove-SwapMe

Step "Setting up the ring"
if ((Resolve-Path $Src).Path -ne $App) {
  Remove-Item -Recurse -Force $App -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force -Path $App | Out-Null
  Get-ChildItem -Force $Src | Where-Object { $_.Name -notin @(".git", "__pycache__", ".remember") } |
    Copy-Item -Destination $App -Recurse -Force
  Get-ChildItem (Join-Path $App "dist") -Filter *.zip -ErrorAction SilentlyContinue | Remove-Item -Force
}

Step "Installing claude-swap and tagteam"
try { uv tool install --upgrade claude-swap } catch { uv tool install claude-swap }
uv tool install --force --python 3.12 $App
try { uv tool update-shell | Out-Null } catch {}
# Move swap-me's history now (any tagteam command that reads ~/.tag-team does it).
try { & (Join-Path $env:USERPROFILE ".local\bin\tagteam.exe") tag-out-point | Out-Null } catch {}

if (Have claude) {
  Step "Bringing the tag-team plugin to Claude Code"
  try { claude plugin marketplace remove tag-team | Out-Null } catch {}
  claude plugin marketplace add $App
  claude plugin install tag-team@tag-team
} else {
  Say "Claude Code not found. Install it, then run: claude plugin marketplace add `"$App`"; claude plugin install tag-team@tag-team"
}

$Vsix = Join-Path $App "dist\tag-team.vsix"
if (Test-Path $Vsix) {
  foreach ($e in $Editors) { if (Have $e) { Step "Adding the Tag Team extension to $e"; try { & $e --install-extension $Vsix --force | Out-Null } catch {} } }
}

# Old plugin copies Claude Code keeps, leftover update downloads.
Step "Cleaning up old versions"
try { & (Join-Path $env:USERPROFILE ".local\bin\tagteam.exe") cleanup | Out-Null } catch {}

Done-Steps
Write-Host @"

TAG TEAM WRESTLING is in the building.
  Claude Code:  /tag-team (the ring)   /tag-in N   /tag-out (hot tag)   /roster
  Terminal:     tagteam   tagteam tag-out   tagteam ring   tagteam rules
  Editors:      [IN] in the status bar; it turns into TAG ME when your partner is worn down.
First time? Sign the account you're logged in as:  tagteam sign --ring-name main
Want to hear about new releases?  tagteam update --notify on
If the plugin can't find tagteam, set its path in /config (tag-team > tagteam command):
  $env:USERPROFILE\.local\bin\tagteam.exe
"@
