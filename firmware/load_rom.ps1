# .nes / .nsf を magicon のフラッシュ(8MB 目の ROM 置き場)に書き込む
#   pwsh -File load_rom.ps1 game.nes
#   pwsh -File load_rom.ps1 music.nsf      (NSF プレイヤーとして起動する)
#   pwsh -File load_rom.ps1 -Remote        (画面転送 = リモートデスクトップのモードで起動する。PC 側は tools\remote_pc.py)
#   pwsh -File load_rom.ps1 -Library D:\roms [b.nes ...] [-Remote]
#                                          (まとめて書き、起動時にゲーム選択メニューを出す。フォルダーなら中の .nes / .nsf 全部。
#                                           -Remote で「REMOTE DESKTOP」も項目に入れる。題名は titles.txt で変えられる → tools\nes_pack.py)
# Core2350B を USB でつないだ状態で使う。magicon が動いていれば picotool が自動で書き込みモードにし、書いた後に再起動する。
# 動いていない(ほかのファームウェアの)時は、BOOTSEL を押したまま RESET を押して離してから実行する。
# ファームウェア(magicon.uf2)を書き直しても、ROM 置き場は消えない。
param([switch]$Remote, [switch]$Library, [Parameter(ValueFromRemainingArguments)][string[]]$Rom)
$ErrorActionPreference = "Stop"
if (-not $Rom -and -not $Remote) { throw "ROM のファイル(-Library ならフォルダーも)か -Remote を指定する" }
$picotool = "C:\Users\Yugo\pico\picotool\picotool\picotool.exe"
$bin = Join-Path $env:TEMP "fc-magicon-rom.bin"          # picotool は日本語のパスを扱えないので ASCII の場所へ
$pack = Join-Path $PSScriptRoot "tools\nes_pack.py"
if ($Library) {
    $extra = if ($Remote) { @("--add-remote") } else { @() }
    python $pack --library $bin @extra @Rom
} elseif ($Remote) {
    python $pack --remote $bin
} else {
    python $pack $Rom[0] $bin
}
if ($LASTEXITCODE) { throw "この ROM は magicon ではまだ動かない" }
& $picotool load -v $bin -t bin -o 0x10800000 -f          # -t / -o はファイル名の後に書く(前だと picotool 2.x が受け付けない)
if ($LASTEXITCODE) {
    Write-Warning "書き込めなかった。BOOTSEL を押したまま RESET を押して離し、もう一度実行する。"
    exit 1
}
& $picotool reboot 2>$null | Out-Null                       # BOOTSEL から書いた時は、ここで magicon に戻る
Write-Output "書き込んだ。ファミコンの電源を入れ直す(またはリセット)と、このモードで起動する。"
