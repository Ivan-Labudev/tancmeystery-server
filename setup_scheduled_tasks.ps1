# Run ONCE on the home PC, as Administrator, after cloning both repos and
# creating server.properties from the template. Registers the two scheduled
# tasks the deploy pipeline depends on, both running as SYSTEM so they fire
# unattended (at boot, and on schedule) without anyone logged in.
#
# NOTE: the 05:00 trigger fires at 05:00 in the machine's LOCAL time zone.
# Verify the home PC's Windows time zone is set to Moscow time before
# relying on this, or adjust the -At value to compensate.
$mcServer = $PSScriptRoot

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# The registration default stops a task after 72 hours and refuses to run on battery. Neither is wanted for an
# unattended server PC (a UPS-backed desktop reports itself as "on battery" during an outage).
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew

$deployAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$mcServer\run_deploy.ps1`""
$deployTrigger = New-ScheduledTaskTrigger -Daily -At "05:00"
Register-ScheduledTask -TaskName "Tancmeystery-Deploy" -Action $deployAction `
    -Trigger $deployTrigger -Principal $principal -Settings $settings -Force

$startupAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$mcServer\ensure_server_running.ps1`""
$startupTrigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "Tancmeystery-EnsureRunning" -Action $startupAction `
    -Trigger $startupTrigger -Principal $principal -Settings $settings -Force

Write-Output "Registered: Tancmeystery-Deploy (daily 05:00, SYSTEM), Tancmeystery-EnsureRunning (at startup, SYSTEM)"
