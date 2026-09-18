$java = "C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot\bin\java.exe"
Set-Location $PSScriptRoot
& $java -Xmx12G -Xms4G -jar fabric-server-launch.jar nogui
