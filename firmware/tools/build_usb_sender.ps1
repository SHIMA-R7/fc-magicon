param([Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference='Stop'
$firmware=Split-Path $PSScriptRoot -Parent
$repo=Split-Path $firmware -Parent
$run=Join-Path $firmware ('out-usb-sender\win11-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force $run | Out-Null
& $Python -c "import sys;sys.path.insert(0,r'$PSScriptRoot');from tile_fit_native import load_native;load_native()"
if($LASTEXITCODE){throw 'Native tile fitter build failed'}
$native=Get-ChildItem 'C:/Users/Yugo/pico/work-video-quality-20261017' -Filter 'tilefit-*.dll' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Copy-Item -LiteralPath $native.FullName -Destination "$run\tilefit.dll"
& $Python -m PyInstaller --noconfirm --onedir --console --name FC-MAGICON-USB `
    --distpath "$run\dist" --workpath "$run\build" --specpath $run `
    --add-data "$firmware\sim\agnes\agnes.c;sim/agnes" `
    --add-data "$firmware\sim\agnes\LICENSE;sim/agnes" `
    --add-binary "$run\tilefit.dll;." "$PSScriptRoot\usb_sender.py"
if($LASTEXITCODE){throw 'PyInstaller failed'}
$app=Join-Path $run 'dist\FC-MAGICON-USB'
Copy-Item -LiteralPath "$repo\docs\fmv_usb_sender_r2_20261017.md" -Destination "$app\README-JA.md"
Copy-Item -LiteralPath "$repo\LICENSE" -Destination "$app\LICENSE-FC-MAGICON.txt"
$sources=Join-Path $app 'source\firmware\tools'
New-Item -ItemType Directory -Force $sources,"$app\source\firmware\sim\agnes" | Out-Null
foreach($name in @('usb_sender.py','remote_pc.py','remote_protocol.py','nesframe.py','pcaudio.py','tile_fit_native.py','tile_fit_native.c','tile_seams.py','scene_palette.py','nano_mouse.py','build_usb_sender.ps1')){
    Copy-Item -LiteralPath "$PSScriptRoot\$name" -Destination $sources
}
Copy-Item -LiteralPath "$firmware\sim\agnes\agnes.c","$firmware\sim\agnes\LICENSE" -Destination "$app\source\firmware\sim\agnes"
Copy-Item -LiteralPath "$repo\LICENSE" -Destination "$app\source"
Copy-Item -LiteralPath "$firmware\nano_sfc_mouse" -Destination $app -Recurse
Copy-Item -LiteralPath "$repo\docs\nano_sfc_mouse_20261018.md" -Destination "$app\README-NANO-JA.md"
& $Python "$PSScriptRoot\package_wifi_licenses.py" $app
if($LASTEXITCODE){throw 'License packaging failed'}
$zip=Join-Path $run 'FC-MAGICON-USB-Win11.zip'
Compress-Archive -LiteralPath $app -DestinationPath $zip
Write-Output "APP=$app"
Write-Output "ZIP=$zip"
