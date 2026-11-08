param([Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference = 'Stop'
$firmware = Split-Path $PSScriptRoot -Parent
$repo = Split-Path $firmware -Parent
$run = Join-Path $firmware ('out-wifi-sender\win11-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $run -Force | Out-Null
& $Python -m PyInstaller --noconfirm --onedir --console --name FC-MAGICON-WiFi `
    --distpath "$run\dist" --workpath "$run\build" --specpath $run `
    --add-data "$firmware\sim\agnes\agnes.c;sim/agnes" `
    --add-data "$firmware\sim\agnes\LICENSE;sim/agnes" `
    "$PSScriptRoot\wifi_sender.py"
if ($LASTEXITCODE) { throw 'PyInstaller failed' }
$app = Join-Path $run 'dist\FC-MAGICON-WiFi'
Copy-Item -LiteralPath "$repo\docs\fmv_wifi_sender_20261015.md" -Destination "$app\README-JA.md"
Copy-Item -LiteralPath "$repo\LICENSE" -Destination "$app\LICENSE-FC-MAGICON.txt"
& $Python -m pip freeze | Set-Content -LiteralPath "$app\build-dependencies.txt" -Encoding utf8
$sourceRoot = Join-Path $app 'source'
$sources = Join-Path $sourceRoot 'firmware\tools'
New-Item -ItemType Directory -Path $sources -Force | Out-Null
foreach ($name in @('wifi_sender.py','remote_pc.py','remote_protocol.py','nesframe.py','pcaudio.py','build_wifi_sender.ps1','package_wifi_licenses.py')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $sources
}
New-Item -ItemType Directory -Path "$sourceRoot\firmware\tests", "$sourceRoot\firmware\wifi_bridge" -Force | Out-Null
Copy-Item -LiteralPath "$firmware\tests\test_wifi_sender.py" -Destination "$sourceRoot\firmware\tests"
Copy-Item -LiteralPath "$firmware\wifi_bridge\wifi_bridge.ino", "$firmware\wifi_bridge\wifi_secrets.example.h" -Destination "$sourceRoot\firmware\wifi_bridge"
New-Item -ItemType Directory -Path "$sourceRoot\firmware\sim\agnes", "$sourceRoot\docs" -Force | Out-Null
Copy-Item -LiteralPath "$firmware\sim\agnes\agnes.c", "$firmware\sim\agnes\LICENSE" -Destination "$sourceRoot\firmware\sim\agnes"
Copy-Item -LiteralPath "$repo\docs\fmv_wifi_sender_20261015.md" -Destination "$sourceRoot\docs"
Copy-Item -LiteralPath "$repo\LICENSE" -Destination $sourceRoot
& $Python "$PSScriptRoot\package_wifi_licenses.py" $app
if ($LASTEXITCODE) { throw 'License packaging failed' }
$zip = Join-Path $run 'FC-MAGICON-WiFi-Win11.zip'
Compress-Archive -LiteralPath $app -DestinationPath $zip
Get-FileHash -LiteralPath $zip -Algorithm SHA256 | Format-List
Write-Output "APP=$app"
Write-Output "ZIP=$zip"
