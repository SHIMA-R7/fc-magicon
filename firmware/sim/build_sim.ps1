# FC-MAGICON sim(PC の試験台)をビルドする
#   pwsh -File build_sim.ps1        → firmware\sim\sim.exe
# Zig(C コンパイラーとして使う、C:\Users\Yugo\pico\zig)でビルドする。日本語のパスを避けて C:\Users\Yugo\pico\work\sim で。
$ErrorActionPreference = "Stop"
$zig = (Get-ChildItem C:\Users\Yugo\pico\zig -Recurse -Filter zig.exe | Select-Object -First 1).FullName
python (Join-Path $PSScriptRoot "patch_agnes.py")
if ($LASTEXITCODE) { throw "patch_agnes.py に失敗" }
$work = "C:\Users\Yugo\pico\work\sim"
if (Test-Path $work) { Remove-Item $work -Recurse -Force }
New-Item -ItemType Directory $work | Out-Null
Copy-Item "$PSScriptRoot\*.c", "$PSScriptRoot\*.h", "$PSScriptRoot\agnes\agnes.h" $work
Copy-Item "$PSScriptRoot\..\magicon\cart.c", "$PSScriptRoot\..\magicon\cart.h", "$PSScriptRoot\..\magicon\nsf_driver.h", "$PSScriptRoot\..\chr_test\chr_rom.h" $work
Push-Location $work
& $zig cc -O2 -std=gnu11 -DCART_HOST -Wall -Wno-unused-function -I. -o sim.exe sim.c apu.c agnes_magicon.c cart.c
$rc = $LASTEXITCODE
Pop-Location
if ($rc) { throw "ビルドに失敗" }
Copy-Item "$work\sim.exe" $PSScriptRoot -Force
Write-Output "-> $PSScriptRoot\sim.exe"
