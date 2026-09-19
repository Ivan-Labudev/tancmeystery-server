# Runs once at Windows startup on the home PC. Starts the server only if it
# isn't already running (covers reboots and power-outage recovery).
$mcServer = $PSScriptRoot

$running = Get-CimInstance Win32_Process -Filter "Name='java.exe'" |
    Where-Object { $_.CommandLine -like '*fabric-server-launch.jar*' }

if (-not $running) {
    # Explicit -ExecutionPolicy Bypass: the machine policy is Undefined (= Restricted), so do not rely on the
    # child inheriting Bypass from the scheduled task's own command line.
    Start-Process powershell -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "$mcServer\start.ps1" `
        -WorkingDirectory $mcServer -WindowStyle Hidden
}
