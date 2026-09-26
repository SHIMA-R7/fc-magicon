# JLCPCB 向けのガーバー・ドリルを書き出して zip にする(ベタを塗り直し、DRC がエラー 0 のときだけ)
#   pwsh -File export_gerbers.ps1
$ErrorActionPreference = "Stop"
$cli = "E:\KiCad\bin\kicad-cli.exe"
Set-Location $PSScriptRoot
$pcb = "FC-MAGICON.kicad_pcb"
$out = Join-Path $PSScriptRoot "gerber"
if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory $out | Out-Null

& $cli pcb drc --severity-error --schematic-parity --refill-zones --exit-code-violations -o drc_release.rpt $pcb | Out-Null
if ($LASTEXITCODE -ne 0) { throw "DRC にエラーがある(drc_release.rpt を見る)" }

$layers = "F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,F.Paste,B.Paste,Edge.Cuts"
& $cli pcb export gerbers --layers $layers --subtract-soldermask -o "$out\" $pcb
if ($LASTEXITCODE -ne 0) { throw "ガーバーの書き出しに失敗" }
& $cli pcb export drill --format excellon --excellon-units mm --excellon-separate-th --generate-map --map-format gerberx2 -o "$out\" $pcb | Out-Null

$zip = Join-Path $PSScriptRoot "FC-MAGICON_gerber_r0.1.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "$out\*" -DestinationPath $zip
Get-ChildItem $out | Select-Object Name, Length
Write-Output "-> $zip"
