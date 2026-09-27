# ESP32-C6 の Wi-Fi ブリッジをビルドして書く。
#   pwsh -File build_bridge.ps1              ビルドして C6 に書く(COM ポートは VID 303A で探す)
#   pwsh -File build_bridge.ps1 -Port COM9   COM ポートを指定
#   pwsh -File build_bridge.ps1 -CheckOnly   書かずにビルドだけ(wifi_secrets.h が無ければ見本の値で)
# 開発環境は C:\Users\Yugo\esp(arduino-cli 1.5.1 + Arduino-ESP32 3.3.12 の C6 に要る分だけ。2026-09-27 に GitHub から導入)。
# パスに日本語が入るとビルドできないので、C:\Users\Yugo\esp\work にコピーしてからビルドする。
param([string]$Port, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$esp = 'C:\Users\Yugo\esp'
$cli = "$esp\arduino-cli.exe"
$cfg = "$esp\arduino-cli.yaml"
if (-not (Test-Path $cfg)) {
    @"
directories:
  data: $esp\arduino15
  downloads: $esp\dl
  user: $esp\sketchbook
board_manager:
  additional_urls:
    - https://github.com/espressif/arduino-esp32/releases/download/3.3.12/package_esp32_index.json
"@ | Set-Content $cfg -Encoding utf8
}
$work = "$esp\work\wifi_bridge"
New-Item -ItemType Directory -Force $work | Out-Null
Copy-Item "$PSScriptRoot\wifi_bridge.ino" $work -Force
if (Test-Path "$PSScriptRoot\wifi_secrets.h") {
    Copy-Item "$PSScriptRoot\wifi_secrets.h" $work -Force
} elseif ($CheckOnly) {
    Copy-Item "$PSScriptRoot\wifi_secrets.example.h" "$work\wifi_secrets.h" -Force
    Write-Host 'wifi_secrets.h が無いので見本の値でビルドする(このままでは Wi-Fi につながらない)'
} else {
    throw 'wifi_secrets.h が無い。wifi_secrets.example.h を写して SSID とパスワードを書く'
}
$fqbn = 'esp32:esp32:esp32c6:CDCOnBoot=cdc,FlashSize=4M,FlashMode=dio,FlashFreq=40'   # このボード(C6 N4)は QIO/80MHz だとパーティションテーブルを読み違えて起動しない
& $cli --config-file $cfg compile --fqbn $fqbn --output-dir "$esp\work\out" $work
if ($LASTEXITCODE) { throw 'ビルド失敗' }
if ($CheckOnly) { return }
if (-not $Port) {
    $usb = Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Enum\USB' | Where-Object PSChildName -like 'VID_303A*'
    foreach ($u in $usb) {
        foreach ($i in Get-ChildItem $u.PSPath) {
            $p = (Get-ItemProperty "$($i.PSPath)\Device Parameters" -ErrorAction SilentlyContinue).PortName
            if ($p) { $Port = $p }
        }
    }
}
if (-not $Port) { throw 'C6 の COM ポートが見つからない。-Port COMx で指定する' }
& $cli --config-file $cfg upload --fqbn $fqbn -p $Port --input-dir "$esp\work\out" $work
if ($LASTEXITCODE) { throw '書き込み失敗' }
