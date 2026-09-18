# Run ONCE on the home PC, as Administrator, after cloning both repos and
# creating server.properties from the template. Registers the two scheduled
# tasks the deploy pipeline depends on, both running as SYSTEM so they fire
# unattended (at boot, and on schedule) without anyone logged in.
#
# NOTE: the 05:00 trigger fires at 05:00 in the machine's LOCAL time zone.
# Verify the home PC's Windows time zone is set to Moscow time before
# relying on this, or adjust the -At value to compensate.
$mcServer = "C:\Users\user\mc-server"

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

$deployAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$mcServer\run_deploy.ps1`""
$deployTrigger = New-ScheduledTaskTrigger -Daily -At "05:00"
Register-ScheduledTask -TaskName "Tancmeystery-Deploy" -Action $deployAction `
    -Trigger $deployTrigger -Principal $principal -Force

$startupAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$mcServer\ensure_server_running.ps1`""
$startupTrigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "Tancmeystery-EnsureRunning" -Action $startupAction `
    -Trigger $startupTrigger -Principal $principal -Force

Write-Output "Registered: Tancmeystery-Deploy (daily 05:00, SYSTEM), Tancmeystery-EnsureRunning (at startup, SYSTEM)"
