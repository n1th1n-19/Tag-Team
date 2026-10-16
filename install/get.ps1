# Tag Team one-liner (Windows): irm https://github.com/n1th1n-19/tag-team/releases/latest/download/get.ps1 | iex   (uninstall: $env:TAGTEAM_UNINSTALL=1 first)
# iex runs in the caller's session; the script block keeps our variables, preferences and return out of it.
& {
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Repo = "n1th1n-19/tag-team"
$Base = if ($env:TAGTEAM_BASE_URL) { $env:TAGTEAM_BASE_URL }
        elseif ($env:TAGTEAM_VERSION) { "https://github.com/$Repo/releases/download/$env:TAGTEAM_VERSION" }
        else { "https://github.com/$Repo/releases/latest/download" }
$HomeDir = if ($env:TAGTEAM_HOME) { $env:TAGTEAM_HOME } else { Join-Path $env:USERPROFILE ".tag-team" }
$Uninstall = $env:TAGTEAM_UNINSTALL -eq "1"
function Say($m) { Write-Host "==> $m" -ForegroundColor Yellow }
$script:StepN = 0
function Step($label) {
  $script:StepN++
  $pct = [int](100 * ($script:StepN - 1) / 3)
  $ProgressPreference = "Continue"
  Write-Progress -Activity "Tag Team Wrestling: download" -Status "$pct% - step $($script:StepN) of 3: $label" -PercentComplete $pct
  $filled = [int]($pct / 5)
  Write-Host ("[" + ("#" * $filled) + ("-" * (20 - $filled)) + "] " + "$pct%".PadLeft(4) + " $label") -ForegroundColor Yellow
}

$Local = Join-Path $HomeDir "app\install\install.ps1"
if ($Uninstall -and (Test-Path $Local)) {
  powershell -NoProfile -ExecutionPolicy Bypass -File $Local -Uninstall
  return
}

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Asset = "tag-team-windows.zip"
$Tmp = Join-Path ([IO.Path]::GetTempPath()) ("tag-team-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $Tmp | Out-Null
try {
  Step "Downloading $Asset"
  Invoke-WebRequest -UseBasicParsing -Uri "$Base/$Asset" -OutFile (Join-Path $Tmp $Asset)
  Invoke-WebRequest -UseBasicParsing -Uri "$Base/SHA256SUMS.txt" -OutFile (Join-Path $Tmp "SHA256SUMS.txt")
  Step "Checking it against SHA256SUMS.txt"
  $Expected = (Get-Content (Join-Path $Tmp "SHA256SUMS.txt") | Where-Object { ($_ -split "\s+")[1].TrimStart("*") -eq $Asset } | ForEach-Object { ($_ -split "\s+")[0] }) | Select-Object -First 1
  if (-not $Expected) { throw "No checksum for $Asset in SHA256SUMS.txt; nothing was installed." }
  $Got = (Get-FileHash -Algorithm SHA256 (Join-Path $Tmp $Asset)).Hash.ToLower()
  if ($Got -ne $Expected.ToLower()) { throw "$Asset failed its checksum; nothing was installed." }
  Step "Unpacking"
  Expand-Archive -Path (Join-Path $Tmp $Asset) -DestinationPath $Tmp -Force
  $ProgressPreference = "Continue"; Write-Progress -Activity "Tag Team Wrestling: download" -Completed; $ProgressPreference = "SilentlyContinue"
  $Installer = Join-Path $Tmp "tag-team\install\install.ps1"
  if ($Uninstall) { powershell -NoProfile -ExecutionPolicy Bypass -File $Installer -Uninstall }
  else { powershell -NoProfile -ExecutionPolicy Bypass -File $Installer }
  if ($LASTEXITCODE) { throw "The installer stopped with exit code $LASTEXITCODE." }
} finally {
  Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}
}
