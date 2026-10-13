param([switch]$Diagnostic)
$ErrorActionPreference = 'Stop'
$toolRoot = 'C:\Users\Yugo\pico'
$gccDir = (Get-ChildItem -LiteralPath "$toolRoot\gcc" -Directory | Select-Object -First 1).FullName
$cmakeDir = (Get-ChildItem -LiteralPath "$toolRoot\cmake" -Directory | Select-Object -First 1).FullName
$env:PATH = "$gccDir\bin;$cmakeDir\bin;$toolRoot\ninja;$toolRoot\pico-sdk-tools;$toolRoot\picotool\picotool;" + $env:PATH
$env:PICO_SDK_PATH = "$toolRoot/pico-sdk/pico-sdk-2.3.1"
$env:PICO_TOOLCHAIN_PATH = $gccDir
$buildRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('fc-magicon-protected-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $buildRoot | Out-Null
Copy-Item -Path "$PSScriptRoot\*" -Destination $buildRoot -Recurse -Exclude out,build,build_host
$outputDir = Join-Path $PSScriptRoot $(if ($Diagnostic) { 'out-diagnostic' } else { 'out-protected' })
$diagArg = if ($Diagnostic) { '-DFC_DIAGNOSTIC=ON' } else { '-DFC_DIAGNOSTIC=OFF' }
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
Remove-Item Env:PICO_TINYUSB_PATH -ErrorAction SilentlyContinue
cmake -G Ninja -B "$buildRoot/build" -S $buildRoot -DCMAKE_BUILD_TYPE=Release $diagArg "-Dpicotool_DIR=$toolRoot/picotool/picotool" "-Dpioasm_DIR=$toolRoot/pico-sdk-tools/pioasm"
if ($LASTEXITCODE) { throw 'Device configure failed' }
cmake --build "$buildRoot/build" --target magicon bus_test chr_test
if ($LASTEXITCODE) { throw 'Device build failed' }
$env:PICO_TINYUSB_PATH = "$toolRoot/tinyusb-0.21.0"
cmake -G Ninja -B "$buildRoot/build_host" -S $buildRoot -DCMAKE_BUILD_TYPE=Release $diagArg -DFC_TUSB021=ON "-Dpicotool_DIR=$toolRoot/picotool/picotool" "-Dpioasm_DIR=$toolRoot/pico-sdk-tools/pioasm"
if ($LASTEXITCODE) { throw 'Host configure failed' }
cmake --build "$buildRoot/build_host" --target magicon_wifi
if ($LASTEXITCODE) { throw 'Host build failed' }
Remove-Item Env:PICO_TINYUSB_PATH
Get-ChildItem -LiteralPath "$buildRoot/build","$buildRoot/build_host" -Recurse -Filter *.uf2 | Copy-Item -Destination $outputDir -Force
Get-ChildItem -LiteralPath $outputDir -Filter *.uf2 | Get-FileHash -Algorithm SHA256
Write-Output "Build directory retained: $buildRoot"
