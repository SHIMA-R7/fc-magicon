# Core2350B のピン配置照合シートを A4 に印刷する(1:1 と 4倍拡大、定規チェック用スケール付き)
#   pwsh -File print_core2350b_pinmap.ps1 [-Printer "Brother DCP-J1270N Printer"] [-PdfOut out.pdf]
# ピン位置: Waveshare 寸法図(25.4mm角、外周2列、ピッチ2.54mm)とシルク、回路図(Core2350B.pdf)から。
param(
    [string]$Printer = "",
    [string]$PdfOut = ""
)
Add-Type -AssemblyName System.Drawing

# ---- 信号割り当て(gen_schematic.py と同じ) ----
$sig = @{}
for ($i = 0; $i -lt 8; $i++) { $sig["GPIO$i"] = "CPU D$i"; $sig["GPIO$(26 + $i)"] = "PPU D$i" }
for ($i = 0; $i -lt 15; $i++) { $sig["GPIO$(8 + $i)"] = "CPU A$i" }
for ($i = 0; $i -lt 5; $i++) { $sig["GPIO$(34 + $i)"] = "PPU A$(8 + $i)" }
$sig["GPIO23"] = "/ROMSEL"; $sig["GPIO24"] = "R/W"; $sig["GPIO25"] = "M2"
$sig["GPIO39"] = "(LED)"; $sig["GPIO40"] = "/RD via U2"; $sig["GPIO41"] = "/WR via U2"; $sig["GPIO42"] = "A13 via U2"
$sig["GPIO43"] = "CIRAM A10"; $sig["GPIO44"] = "AUDIO PWM"; $sig["GPIO45"] = "IRQ drv"; $sig["GPIO46"] = "5V sense"
$sig["GPIO47"] = "(PSRAM)"; $sig["VBUS"] = "+5V via D1"; $sig["3V3"] = "+3V3"; $sig["BOOTSEL"] = "SW1"; $sig["RUN"] = "SW2"
$sig["SWD"] = "J3"; $sig["SWCLK"] = "J3"

# ---- ヘッダーのピン名(回路図 Core2350B.pdf) ----
function GpioHeader($base) {
    $o = @("GND", "GPIO$base")
    for ($r = 1; $r -lt 8; $r++) { $o += "GPIO$($base + 2 * $r)"; $o += "GPIO$($base + 2 * $r - 1)" }
    return , $o
}
$P = @{
    "P1" = (GpioHeader 0); "P3" = (GpioHeader 15); "P4" = (GpioHeader 30)
    "P2" = @("GND", "GPIO45", "GPIO47", "GPIO46", "BOOTSEL", "SWD", "USB D-", "GND", "USB D+", "SWCLK", "RUN", "ADC_VREF", "3V3_EN", "GND", "VBUS", "3V3")
}
# 穴の位置(部品面から見て、FPCコネクタが上)。c=列(左0-右9), r=行(上0-下9)
# 左=P1(c0,c1 / r0-7) 下=P3(r9,r8 / c0-7) 右=P4(c9,c8 / r9-2) 上=P2(r0,r1 / c9-2)。外側=奇数ピン、内側=偶数ピン
$holes = @()
for ($k = 0; $k -lt 8; $k++) {
    $holes += , @(0, $k, "P1", (2 * $k + 1)); $holes += , @(1, $k, "P1", (2 * $k + 2))
    $holes += , @($k, 9, "P3", (2 * $k + 1)); $holes += , @($k, 8, "P3", (2 * $k + 2))
    $holes += , @(9, (9 - $k), "P4", (2 * $k + 1)); $holes += , @(8, (9 - $k), "P4", (2 * $k + 2))
    $holes += , @((9 - $k), 0, "P2", (2 * $k + 1)); $holes += , @((9 - $k), 1, "P2", (2 * $k + 2))
}
if ($holes.Count -ne 64) { throw "穴の数が64でない: $($holes.Count)" }

$doc = New-Object System.Drawing.Printing.PrintDocument
if ($PdfOut) {
    $doc.PrinterSettings.PrinterName = "Microsoft Print to PDF"
    $doc.PrinterSettings.PrintToFile = $true
    $doc.PrinterSettings.PrintFileName = $PdfOut
} elseif ($Printer) {
    $doc.PrinterSettings.PrinterName = $Printer
}
if (-not $doc.PrinterSettings.IsValid) { throw "プリンターが見つからない: $($doc.PrinterSettings.PrinterName)" }
$a4 = $doc.PrinterSettings.PaperSizes | Where-Object { $_.Kind -eq [System.Drawing.Printing.PaperKind]::A4 } | Select-Object -First 1
$doc.DefaultPageSettings.PaperSize = $a4
$doc.DefaultPageSettings.Landscape = $false
$doc.DefaultPageSettings.Color = $false
$doc.DocumentName = "Core2350B pin map"

$doc.add_PrintPage({
    param($s, $e)
    $gr = $e.Graphics
    $gr.PageUnit = [System.Drawing.GraphicsUnit]::Millimeter
    $gr.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $gr.TranslateTransform(-$e.PageSettings.HardMarginX * 0.254, -$e.PageSettings.HardMarginY * 0.254)
    $black = [System.Drawing.Brushes]::Black
    $thin = New-Object System.Drawing.Pen ([System.Drawing.Color]::Black), 0.12
    $mid = New-Object System.Drawing.Pen ([System.Drawing.Color]::Black), 0.3
    $fT = New-Object System.Drawing.Font "Yu Gothic UI", 4.2, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Millimeter)
    $fM = New-Object System.Drawing.Font "Yu Gothic UI", 2.6, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Millimeter)
    $fS = New-Object System.Drawing.Font "Yu Gothic UI", 1.9, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Millimeter)
    $fPin = New-Object System.Drawing.Font "Arial", 1.55, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Millimeter)
    $fSig = New-Object System.Drawing.Font "Arial", 1.3, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Millimeter)
    $center = New-Object System.Drawing.StringFormat
    $center.Alignment = [System.Drawing.StringAlignment]::Center

    $gr.DrawString("Waveshare Core2350B ピン配置 照合シート(FC-MAGICON)", $fT, $black, 15, 10)
    $gr.DrawString("拡大縮小なしで印刷。先に下の100mmスケールを定規で測ってから照合してください。", $fM, $black, 15, 17)
    $gr.DrawString("向き: 部品面(RP2350Bが見える面)を上、FPCコネクタを上辺にして置いた状態。", $fM, $black, 15, 21.5)

    # ---- 1:1 図(実物を重ねる用)
    $ox = 22; $oy = 36
    $gr.DrawRectangle($mid, [single]$ox, [single]$oy, [single]25.4, [single]25.4)
    foreach ($h in $holes) {
        $x = $ox + 1.27 + 2.54 * $h[0]; $y = $oy + 1.27 + 2.54 * $h[1]
        $gr.DrawEllipse($thin, [single]($x - 0.8), [single]($y - 0.8), [single]1.6, [single]1.6)
        if ($P[$h[2]][$h[3] - 1] -eq "GND") { $gr.FillEllipse($black, [single]($x - 0.4), [single]($y - 0.4), [single]0.8, [single]0.8) }
    }
    # FPCの位置(目安。寸法図の写真から x=15.3-19.7mm, y=4.5-8.6mm)
    $gr.DrawRectangle($thin, [single]($ox + 15.3), [single]($oy + 4.5), [single]4.4, [single]4.1)
    $gr.DrawString("1:1(25.4mm角)", $fS, $black, $ox, $oy + 26.5)
    $gr.DrawString("黒点=GND", $fS, $black, $ox, $oy + 29.5)
    $gr.DrawString("小枠=FPCコネクタ(目安)",$fS, $black, $ox + 32, $oy + 2)
    $gr.DrawString("実物を部品面を上にしてこの上に置き、", $fS, $black, $ox + 32, $oy + 6)
    $gr.DrawString("外形・穴位置が合うか確認する。", $fS, $black, $ox + 32, $oy + 9)
    $gr.DrawString("拡大図の太字=シルク/回路図のピン名、細字=この基板での割り当て。", $fS, $black, $ox + 32, $oy + 14)
    $gr.DrawString("括弧の P1-P4 はヘッダー番号・ピン番号(回路図の表記)。", $fS, $black, $ox + 32, $oy + 17)
    $gr.DrawString("★ シルクの表記と太字が1つでも違ったら、そのピンを教えてください。", $fS, $black, $ox + 32, $oy + 21)

    # ---- 4倍拡大図
    $S = 4.0; $ex = 33; $ey = 76; $cell = 2.54 * $S
    $gr.DrawRectangle($mid, [single]$ex, [single]$ey, [single](25.4 * $S), [single](25.4 * $S))
    # グループの境界(風車状)
    foreach ($grp in @(@(0, 0, 2, 8, "P1"), @(0, 8, 8, 2, "P3"), @(8, 2, 2, 8, "P4"), @(2, 0, 8, 2, "P2"))) {
        $gr.DrawRectangle($mid, [single]($ex + $grp[0] * $cell), [single]($ey + $grp[1] * $cell), [single]($grp[2] * $cell), [single]($grp[3] * $cell))
    }
    $gr.DrawString("P1(左)", $fM, $black, [single]($ex - 17), [single]($ey + 40))
    $gr.DrawString("P3(下)", $fM, $black, [single]($ex + 40), [single]($ey + 25.4 * $S + 1.5))
    $gr.DrawString("P4(右)", $fM, $black, [single]($ex + 25.4 * $S + 1.5), [single]($ey + 60))
    $gr.DrawString("P2(上)", $fM, $black, [single]($ex + 60), [single]($ey - 5))
    $gr.DrawRectangle($thin, [single]($ex + 15.3 * $S), [single]($ey + 4.5 * $S), [single](4.4 * $S), [single](4.1 * $S))
    $gr.DrawString("FPC", $fS, $black, [single]($ex + 17.5 * $S - 2), [single]($ey + 6.2 * $S))
    foreach ($h in $holes) {
        $cx = $ex + ($h[0] + 0.5) * $cell; $cy = $ey + ($h[1] + 0.5) * $cell
        $name = $P[$h[2]][$h[3] - 1]
        $gr.DrawEllipse($thin, [single]($cx - 1.2), [single]($cy - 3.6), [single]2.4, [single]2.4)
        if ($name -eq "GND") { $gr.FillEllipse($black, [single]($cx - 0.6), [single]($cy - 3.0), [single]1.2, [single]1.2) }
        $short = $name -replace "^GPIO", "GP"
        $gr.DrawString($short, $fPin, $black, [single]$cx, [single]($cy - 1.2), $center)
        $a = $sig[$name]
        if ($a) { $gr.DrawString($a, $fSig, $black, [single]$cx, [single]($cy + 0.5), $center) }
        $gr.DrawString("$($h[2])-$($h[3])", $fSig, $black, [single]$cx, [single]($cy + 2.2), $center)
    }

    # ---- スケール
    $rx = 55; $ry = 196
    $gr.DrawString("スケール 100mm(0と100の線の間を定規で測る)", $fS, $black, $rx, $ry - 4)
    $gr.DrawLine($mid, [single]$rx, [single]$ry, [single]($rx + 100), [single]$ry)
    for ($i = 0; $i -le 100; $i++) {
        $t = if ($i % 10 -eq 0) { 4 } elseif ($i % 5 -eq 0) { 2.5 } else { 1.5 }
        $gr.DrawLine($thin, [single]($rx + $i), [single]$ry, [single]($rx + $i), [single]($ry + $t))
        if ($i % 10 -eq 0) { $gr.DrawString("$i", $fSig, $black, [single]($rx + $i - 0.7), [single]($ry + 4.3)) }
    }

    # ---- 注記
    $ny = 210
    $notes = @(
        "・GPIO0-38 は 5V トレラント。GPIO40-47(ADC兼用)は 5V 非トレラント → U2(74LVC245)経由か出力専用にしている。",
        "・GP39 は基板上のLED(470Ω)、GP47 は基板上PSRAMのCS。どちらもバスには使わない。",
        "・USB D+/D-・3V3_EN・ADC_VREF は未使用(USBはモジュール付属のFPCアダプタを使う)。",
        "・VBUS にはカセット端子30/31番の+5VをD1(1N5819)経由で入れる。3V3 はモジュールのLDO出力を U2 に使う。",
        "・ピン位置の出典: Waveshare Core2350B 寸法図(25.4mm角・外周2列・2.54mmピッチ)、シルク、回路図 Core2350B.pdf。",
        "・紙は印刷で0.3%程度伸縮する。100mm が 99.7〜100.3mm なら十分。"
    )
    for ($i = 0; $i -lt $notes.Count; $i++) { $gr.DrawString($notes[$i], $fS, $black, 15, [single]($ny + $i * 4)) }
    $e.HasMorePages = $false
})
$doc.Print()
Write-Output "送信しました: $($doc.PrinterSettings.PrinterName) $PdfOut"
