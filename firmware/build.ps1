# FC-MAGICON ファームウェアをビルドする
#   pwsh -File build.ps1            → C:\Users\Yugo\pico\work\fc-magicon にコピーしてビルドし、.uf2 を firmware\out へ
# 道具(C:\Users\Yugo\pico): xPack arm-none-eabi-gcc 15.2、CMake 4.4.3、Ninja 1.13.2、pico-sdk 2.3.1(+ TinyUSB)、picotool/pioasm
# パスに日本語が入るとビルドが失敗するので、ASCII のフォルダへコピーしてからビルドする。
$ErrorActionPreference = "Stop"
$root = "C:\Users\Yugo\pico"
$gcc = (Get-ChildItem "$root\gcc" -Directory | Select-Object -First 1).FullName
$cmake = (Get-ChildItem "$root\cmake" -Directory | Select-Object -First 1).FullName
$env:PATH = "$gcc\bin;$cmake\bin;$root\ninja;$root\pico-sdk-tools;$root\picotool\picotool;" + $env:PATH
$env:PICO_SDK_PATH = (Get-ChildItem "$root\pico-sdk" -Directory | Select-Object -First 1).FullName -replace '\\', '/'
$env:PICO_TOOLCHAIN_PATH = $gcc

$work = "$root\work\fc-magicon"
if (Test-Path $work) { Remove-Item $work -Recurse -Force }
New-Item -ItemType Directory $work | Out-Null
Copy-Item "$PSScriptRoot\*" $work -Recurse -Exclude out, build
Set-Location $work
cmake -G Ninja -B build -S . -DCMAKE_BUILD_TYPE=Release `
    -Dpicotool_DIR="$root/picotool/picotool" -Dpioasm_DIR="$root/pico-sdk-tools/pioasm"
if ($LASTEXITCODE) { throw "cmake の設定に失敗" }
cmake --build build
if ($LASTEXITCODE) { throw "ビルドに失敗" }

# host_test だけ TinyUSB 0.21.0(C:\Users\Yugo\pico\tinyusb-0.21.0、2026-09-27 に GitHub から導入)でビルドする
$env:PICO_TINYUSB_PATH = "$root/tinyusb-0.21.0" -replace '\\', '/'
cmake -G Ninja -B build_host -S . -DCMAKE_BUILD_TYPE=Release -DFC_HOST_TEST=ON `
    -Dpicotool_DIR="$root/picotool/picotool" -Dpioasm_DIR="$root/pico-sdk-tools/pioasm"
if ($LASTEXITCODE) { throw "cmake の設定に失敗(host_test)" }
cmake --build build_host
if ($LASTEXITCODE) { throw "ビルドに失敗(host_test)" }
Remove-Item Env:\PICO_TINYUSB_PATH
Get-ChildItem build_host -Recurse -Filter *.uf2 | Copy-Item -Destination "$PSScriptRoot\out" -Force
New-Item -ItemType Directory -Force "$PSScriptRoot\out" | Out-Null
Get-ChildItem build -Recurse -Filter *.uf2 | Copy-Item -Destination "$PSScriptRoot\out" -Force
Get-ChildItem "$PSScriptRoot\out" | Select-Object Name, Length
