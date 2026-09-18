# Runs once at Windows startup on the home PC. Starts the server only if it
# isn't already running (covers reboots and power-outage recovery).
$mcServer = "C:\Users\user\mc-server"

$running = Get-CimInstance Win32_Process -Filter "Name='java.exe'" |
    Where-Object { $_.CommandLine -like '*fabric-server-launch.jar*' }

if (-not $running) {
    Start-Process powershell -ArgumentList '-NoExit', '-File', "$mcServer\start.ps1" `
        -WorkingDirectory $mcServer
}
