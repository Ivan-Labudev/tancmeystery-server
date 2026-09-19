param([switch]$DryRun)

# Finds a Java 17+ runtime on any machine instead of hardcoding one install path:
#   1. JAVA_HOME   2. java.exe on PATH   3. usual JDK folders under Program Files (newest first)
# Java 17 itself is preferred (what Fabric 1.20.1 is tested with); a newer JDK is used only if no 17 exists.
# `.\start.ps1 -DryRun` prints the Java it would use and exits without starting the server.
function Find-Java {
    $candidates = @()
    if ($env:JAVA_HOME) { $candidates += (Join-Path $env:JAVA_HOME "bin\java.exe") }
    $onPath = Get-Command java.exe -ErrorAction SilentlyContinue
    if ($onPath) { $candidates += $onPath.Source }
    foreach ($root in @("$env:ProgramFiles\Eclipse Adoptium", "$env:ProgramFiles\Java", "$env:ProgramFiles\Microsoft")) {
        if (Test-Path $root) {
            $candidates += Get-ChildItem $root -Directory -Filter "jdk*" |
                Sort-Object Name -Descending |
                ForEach-Object { Join-Path $_.FullName "bin\java.exe" }
        }
    }

    $found = @()
    foreach ($c in ($candidates | Select-Object -Unique)) {
        if (Test-Path $c) {
            $major = [Diagnostics.FileVersionInfo]::GetVersionInfo($c).ProductMajorPart
            if ($major -ge 17) { $found += [PSCustomObject]@{ Path = $c; Major = $major } }
        }
    }
    $best = $found | Where-Object { $_.Major -eq 17 } | Select-Object -First 1
    if (-not $best) { $best = $found | Select-Object -First 1 }
    return $best
}

$java = Find-Java
if (-not $java) {
    Write-Error "Java 17+ not found. Install Temurin 17 (https://adoptium.net/temurin/releases/?version=17) or set JAVA_HOME."
    exit 1
}
Write-Output "Using Java $($java.Major): $($java.Path)"
if ($DryRun) { exit 0 }

Set-Location $PSScriptRoot
& $java.Path -Xmx12G -Xms4G -jar fabric-server-launch.jar nogui
