# Runs nightly via Task Scheduler (05:00 local time on the home PC, which must
# be set to Moscow time zone). Pulls both repos with --ff-only (never
# auto-merges); if either pull fails or nothing changed, deploy.py is not run.
$ErrorActionPreference = "Stop"

$mcServer = "C:\Users\user\mc-server"
$modpack = "C:\Users\user\tancmeystery-modpack"
$logFile = Join-Path $mcServer "logs\deploy.log"

function Write-Log($msg) {
    New-Item -ItemType Directory -Force -Path (Split-Path $logFile) | Out-Null
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $logFile -Value $line
    Write-Output $line
}

function Pull-Repo($path) {
    Set-Location $path
    $before = git rev-parse HEAD
    # No 2>&1 here: merging stderr into the success stream under
    # $ErrorActionPreference = "Stop" turns git's normal progress output
    # (printed even on a successful pull) into a terminating exception in
    # Windows PowerShell 5.1. $LASTEXITCODE alone is the reliable signal.
    git pull --ff-only | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "git pull --ff-only failed in $path"
    }
    $after = git rev-parse HEAD
    return [PSCustomObject]@{ Path = $path; Before = $before; After = $after; Changed = ($before -ne $after) }
}

try {
    $serverResult = Pull-Repo $mcServer
    $modpackResult = Pull-Repo $modpack
} catch {
    Write-Log "ERROR during git pull: $_"
    exit 1
}

if (-not $serverResult.Changed -and -not $modpackResult.Changed) {
    Write-Log "No changes in mc-server or tancmeystery-modpack, skipping deploy"
    exit 0
}

Write-Log ("Changes detected (mc-server {0}->{1}, modpack {2}->{3}), running deploy.py" -f `
    $serverResult.Before.Substring(0,7), $serverResult.After.Substring(0,7), `
    $modpackResult.Before.Substring(0,7), $modpackResult.After.Substring(0,7))

Set-Location $mcServer
python deploy.py
