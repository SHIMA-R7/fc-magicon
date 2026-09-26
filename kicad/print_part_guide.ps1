# FC-MAGICON 基板の部品案内図(原寸 1:1、部品面)を A4 縦に印刷する。各部品に「何用の何か」の注を引き出し線で付ける
#   E:\KiCad\bin\python.exe dump_geom.py        … 先に geom.json を作る
#   pwsh -File print_part_guide.ps1 [-Printer "Brother DCP-J1270N Printer"] [-Png preview.png]
#   -Png を付けると印刷せず、同じ絵を PNG(10px/mm)に書き出す(確認用)
param(
    [string]$Printer = "",
    [string]$Png = ""
)
Add-Type -AssemblyName System.Drawing
$g = Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot "geom.json") | ConvertFrom-Json
$BW = 90.0; $BH = 65.8
$OX = 60.0; $OY = 40.0          # 基板の左上(紙の上の mm)

# 注: 部品の記号(複数可)、左右どちらの列に出すか、文
$notes = @(
    @(@("J3"), "L", "J3  SWD(1x3)。debugprobe(Pico)で書き込み・デバッグ"),
    @(@("J2"), "L", "J2  3.5mm ステレオジャック PJ-324M。ライン出力(本体の音 + 拡張音源)。基板の左辺から約3.6mm はみ出す"),
    @(@("SW1"), "L", "SW1  BOOTSEL。押しながら USB をつなぐと書き込みモード"),
    @(@("SW2"), "L", "SW2  RESET(RP2350 の RUN)"),
    @(@("R7"), "L", "R7  0Ω。本体の音声 45番 → 46番 の素通し"),
    @(@("R2", "R3"), "L", "R2 15k / R3 22k  本体 5V の検出(分圧して GPIO46 へ)。Highになるまでバスに出力しない"),
    @(@("R9", "C3"), "L", "R9 1k / C3 10nF  拡張音源 PWM(GPIO44)の RC フィルタ"),
    @(@("VR1"), "L", "VR1  半固定 100k(KVSF637AC104)。拡張音源の音量"),
    @(@("R8"), "L", "R8  47k。拡張音源を 46番(本体へ戻る音)に混ぜる"),
    @(@("R10", "R11", "C4"), "L", "C4 10µF / R10 47k / R11 100Ω  ライン出力(J2)。C4 は直流カット(+ が SOUND_OUT 側)"),
    @(@("R4", "R5", "Q1"), "L", "Q1 2SC1815 + R4 4.7k / R5 100k  /IRQ(15番)をオープンコレクタで駆動(GPIO45)。Q1 は平らな面から E-C-B"),
    @(@("R6"), "L", "R6  10k(未実装)。本体に /IRQ のプルアップが無い時だけ"),
    @(@("R1"), "L", "R1  0Ω。CIRAM /CE(48番) ← /A13(49番)"),
    @(@("J6"), "R", "J6  USB 予備ランド(1x4)。1=5V 2=D- 3=D+ 4=GND。FPC 側と同時につながない"),
    @(@("J5"), "R", "J5  デバッグ(2x8)。/RD /WR A13(3.3V後)、CIRAM A10、PWM、/IRQ、5V検出、3V3、VBUS、ライン出力、GND"),
    @(@("C2"), "R", "C2  100nF。U2 のパスコン"),
    @(@("P1"), "R", "P1〜P4  2x8 ピンソケット x4。Core2350B2(RP2350B、25.4mm角)を載せる。高さ約14mm。USB の FPC は上辺側"),
    @(@("JP1", "JP2", "JP3"), "R", "JP1〜3  ミラーリング(1つだけハンダで閉じる)。JP1=MCU(マッパー用)、JP2=垂直(A10)、JP3=水平(A11)"),
    @(@("U2"), "R", "U2  74LVC245(DIP-20)。PPU の /RD /WR A13 を 5V→3.3V に(GPIO40〜42 は 5V 非トレラント)"),
    @(@("D1"), "R", "D1  1N4001。本体 5V → モジュールの VBUS。USB 給電時に本体へ逆流させない"),
    @(@("C1"), "R", "C1  10µF。モジュールの電源(VBUS)"),
    @(@("TP1", "TP2", "TP3", "TP4", "TP5"), "R", "TP1〜5  オシロ用。左から /RD、D0、M2、/ROMSEL、GND"),
    @(@("J4"), "R", "J4  カセット60ピン全部のブレイクアウト(2x30)。上の列 = 31〜60番、下の列 = 1〜30番。左端が 1/31番"),
    @(@("J1"), "R", "J1  カセット端子(60ピン、2.54mm)。表 = 1〜30番、裏 = 31〜60番。基板厚 1.2mm")
)

function Draw-Sheet($gr) {
    $gr.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $gr.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAlias
    $black = [System.Drawing.Brushes]::Black
    $gray = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(160, 160, 160))
    $thin = New-Object System.Drawing.Pen ([System.Drawing.Color]::Black), 0.12
    $mid = New-Object System.Drawing.Pen ([System.Drawing.Color]::Black), 0.3
    $lead = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(90, 90, 90)), 0.12
    $dot = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::Black)
    $fT = New-Object System.Drawing.Font "Yu Gothic UI", 4.2, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Millimeter)
    $fM = New-Object System.Drawing.Font "Yu Gothic UI", 2.4, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Millimeter)
    $fN = New-Object System.Drawing.Font "Yu Gothic UI", 1.9, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Millimeter)
    $fX = New-Object System.Drawing.Font "Arial", 1.3, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Millimeter)
    $center = New-Object System.Drawing.StringFormat
    $center.Alignment = [System.Drawing.StringAlignment]::Center

    $gr.DrawString("FC-MAGICON rev0.2  部品案内図(原寸 1:1、部品面 = 本体の手前)", $fT, $black, 8, 8)
    $gr.DrawString("拡大縮小なしで印刷。下の 100mm スケールで倍率を確認できる。", $fM, $black, 8, 15)

    # 基板: 外形、部品の枠、パッド
    foreach ($l in $g.edges) {
        $gr.DrawLine($mid, [single]($OX + $l[0]), [single]($OY + $l[1]), [single]($OX + $l[2]), [single]($OY + $l[3]))
    }
    $parts = @{}
    foreach ($p in $g.parts) {
        $parts[$p.ref] = $p
        $gr.DrawRectangle($thin, [single]($OX + $p.x0), [single]($OY + $p.y0), [single]($p.x1 - $p.x0), [single]($p.y1 - $p.y0))
    }
    foreach ($p in $g.pads) {
        $x = $OX + $p.x; $y = $OY + $p.y
        if ($p.tht) {
            $d = [math]::Min($p.w, $p.h)
            $gr.DrawEllipse($thin, [single]($x - $d / 2), [single]($y - $d / 2), [single]$d, [single]$d)
        } elseif ($p.front) {
            $gr.FillRectangle($gray, [single]($x - $p.w / 2), [single]($y - $p.h / 2), [single]$p.w, [single]$p.h)
        }
    }
    foreach ($p in $g.parts) {
        if ($p.ref -match '^P[234]$') { continue }
        $gr.DrawString($p.ref, $fX, $black, [single]($OX + ($p.x0 + $p.x1) / 2), [single]($OY + ($p.y0 + $p.y1) / 2 - 0.7), $center)
    }
    # J1(カセット端子)は geom.json の部品に無いので、差し込み部の枠を代わりに使う
    if (-not $parts.ContainsKey("J1")) { $parts["J1"] = [pscustomobject]@{ ref = "J1"; x0 = 5.8; x1 = 84.2; y0 = 55.1; y1 = 65.8 } }
    # Core2350B の外形(P1 の枠 = モジュールの 25.4mm 角)を太線で
    $m = $parts["P1"]
    $gr.DrawRectangle($mid, [single]($OX + $m.x0 + 0.37), [single]($OY + $m.y0 + 0.38), [single]25.4, [single]25.4)
    $gr.DrawString("Core2350B2", $fM, $black, [single]($OX + ($m.x0 + $m.x1) / 2), [single]($OY + ($m.y0 + $m.y1) / 2 - 1.5), $center)

    # 注: 部品の高さ順に並べ、重ならないように下へ送る
    $colW = 50.0
    foreach ($side in "L", "R") {
        $items = foreach ($n in $notes) {
            if ($n[1] -ne $side) { continue }
            $ty = ($n[0] | ForEach-Object { ($parts[$_].y0 + $parts[$_].y1) / 2 } | Measure-Object -Average).Average
            $sz = $gr.MeasureString($n[2], $fN, [single]$colW)
            [pscustomobject]@{ refs = $n[0]; text = $n[2]; ty = $OY + $ty; h = $sz.Height }
        }
        $items = $items | Sort-Object ty
        $y = 24.0
        foreach ($it in $items) {
            $it | Add-Member y ([math]::Max($y, $it.ty - $it.h / 2))
            $y = $it.y + $it.h + 1.6
        }
        # 下にはみ出したら全体を上へ詰める(上限は 24mm)
        $over = $y - 165
        if ($over -gt 0) { foreach ($it in $items) { $it.y = [math]::Max(24.0, $it.y - $over) } }
        foreach ($it in $items) {
            $tx = if ($side -eq "L") { 6.0 } else { $OX + $BW + 4.0 }
            $gr.DrawString($it.text, $fN, $black, (New-Object System.Drawing.RectangleF ([single]$tx), ([single]$it.y), ([single]$colW), ([single]($it.h + 1))))
            $ax = if ($side -eq "L") { $tx + $colW + 0.5 } else { $tx - 0.5 }
            $ay = $it.y + 1.2
            foreach ($r in $it.refs) {
                $p = $parts[$r]
                $px = $OX + ($p.x0 + $p.x1) / 2; $py = $OY + ($p.y0 + $p.y1) / 2
                if ($r -eq "P1") { $px = $OX + $p.x1 - 3; $py = $OY + $p.y0 + 4 }
                if ($r -eq "J2") { $px = $OX + $p.x0 + 2 }
                $gr.DrawLine($lead, [single]$ax, [single]$ay, [single]$px, [single]$py)
                $gr.FillEllipse($dot, [single]($px - 0.45), [single]($py - 0.45), [single]0.9, [single]0.9)
            }
        }
    }

    # 裏面(本体の奥側から見た図 = 左右反転)。部品は無く、スルーホールの足と端子 31〜60番だけ
    $BY = 128.0
    $MX = { param($v) $OX + $BW - $v }
    $gr.DrawString("裏面(本体の奥側から見た図、左右反転)。部品は無し。スルーホールの足が約1.5〜2mm 出る", $fM, $black, 8, [single]($BY - 12))
    foreach ($l in $g.edges) {
        $gr.DrawLine($mid, [single](& $MX $l[0]), [single]($BY + $l[1]), [single](& $MX $l[2]), [single]($BY + $l[3]))
    }
    $lgray = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(170, 170, 170)), 0.12
    $gtext = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(120, 120, 120))
    foreach ($p in $g.parts) {
        $x0 = & $MX $p.x1; $x1 = & $MX $p.x0
        $gr.DrawRectangle($lgray, [single]$x0, [single]($BY + $p.y0), [single]($x1 - $x0), [single]($p.y1 - $p.y0))
        if ($p.ref -notmatch '^P[234]$') {
            $gr.DrawString($p.ref, $fX, $gtext, [single](($x0 + $x1) / 2), [single]($BY + ($p.y0 + $p.y1) / 2 - 0.7), $center)
        }
    }
    $fingers = @()
    foreach ($p in $g.pads) {
        $x = & $MX $p.x; $y = $BY + $p.y
        if ($p.tht) {
            $d = [math]::Min($p.w, $p.h)
            $gr.DrawEllipse($thin, [single]($x - $d / 2), [single]($y - $d / 2), [single]$d, [single]$d)
        } elseif ($p.back) {
            $gr.FillRectangle($gray, [single]($x - $p.w / 2), [single]($y - $p.h / 2), [single]$p.w, [single]$p.h)
            $fingers += $x
        }
    }
    # 端子の番号(右端 = 31番、左端 = 60番)
    $fingers = $fingers | Sort-Object -Descending
    for ($i = 0; $i -lt $fingers.Count; $i++) {
        $gr.DrawString("$(31 + $i)", $fX, $black, [single]$fingers[$i], [single]($BY + $BH + 0.6), $center)
    }
    # 端子の信号(README のピン表と同じ。50番は PPU A0〜A7 のどれかで、この基板では未接続)
    $legend = @(
        "裏の端子: 31 +5V / 32 M2 / 33〜35 CPU A12〜A14 / 36〜43 CPU D7〜D0 / 44 /ROMSEL / 45 本体からの音声 / 46 本体へ戻す音声",
        "47 PPU /WR / 48 CIRAM /CE(R1 で 49番へ) / 49 /A13 / 50 未接続 / 51〜55 PPU A8〜A12 / 56 PPU A13 / 57〜60 PPU AD7〜AD4"
    )
    for ($i = 0; $i -lt $legend.Count; $i++) { $gr.DrawString($legend[$i], $fN, $black, 8, [single]($BY + $BH + 4 + $i * 3.4)) }

    # 補足
    $ny = 222
    $foot = @(
        "・枠 = 部品が占める範囲(コンデンサー C1〜C4 は足を曲げて右へ寝かせる分を含む)。丸 = スルーホール。",
        "・Core2350B2 は 2x8 のピンソケット 4個に挿す(モジュール側には 2x8 ピンヘッダー 4個)。基板面からの高さは約14mm。",
        "・J3・J4・J5・J6 はランドだけ用意。使う時にピンヘッダー/ソケットを立てる(ケースに入れるなら高さに注意)。",
        "・電源: 本体の 5V(30・31番)→ D1 → モジュールの VBUS。USB 単独でも動くが、その時はバスに出力しない(5V 検出で判定)。"
    )
    for ($i = 0; $i -lt $foot.Count; $i++) { $gr.DrawString($foot[$i], $fN, $black, 8, [single]($ny + $i * 3.6)) }

    # スケール
    $rx = 55; $ry = 245
    $gr.DrawString("スケール 100mm", $fN, $black, $rx, $ry - 3.5)
    $gr.DrawLine($mid, [single]$rx, [single]$ry, [single]($rx + 100), [single]$ry)
    for ($i = 0; $i -le 100; $i++) {
        $t = if ($i % 10 -eq 0) { 4 } elseif ($i % 5 -eq 0) { 2.5 } else { 1.5 }
        $gr.DrawLine($thin, [single]($rx + $i), [single]$ry, [single]($rx + $i), [single]($ry + $t))
        if ($i % 10 -eq 0) { $gr.DrawString("$i", $fX, $black, [single]($rx + $i - 0.7), [single]($ry + 4.3)) }
    }
}

if ($Png) {
    $bmp = New-Object System.Drawing.Bitmap 2100, 2970
    $bmp.SetResolution(254, 254)   # 10px/mm
    $gr = [System.Drawing.Graphics]::FromImage($bmp)
    $gr.Clear([System.Drawing.Color]::White)
    $gr.PageUnit = [System.Drawing.GraphicsUnit]::Millimeter
    Draw-Sheet $gr
    $bmp.Save($Png, [System.Drawing.Imaging.ImageFormat]::Png)
    Write-Output "-> $Png"
    return
}

$doc = New-Object System.Drawing.Printing.PrintDocument
if ($Printer) { $doc.PrinterSettings.PrinterName = $Printer }
if (-not $doc.PrinterSettings.IsValid) { throw "プリンターが見つからない: $($doc.PrinterSettings.PrinterName)" }
$a4 = $doc.PrinterSettings.PaperSizes | Where-Object { $_.Kind -eq [System.Drawing.Printing.PaperKind]::A4 } | Select-Object -First 1
$doc.DefaultPageSettings.PaperSize = $a4
$doc.DefaultPageSettings.Landscape = $false
$doc.DefaultPageSettings.Color = $false
$doc.DocumentName = "FC-MAGICON part guide"
$doc.add_PrintPage({
    param($s, $e)
    $e.Graphics.PageUnit = [System.Drawing.GraphicsUnit]::Millimeter
    $e.Graphics.TranslateTransform(-$e.PageSettings.HardMarginX * 0.254, -$e.PageSettings.HardMarginY * 0.254)
    Draw-Sheet $e.Graphics
    $e.HasMorePages = $false
})
$doc.Print()
Write-Output "送信しました: $($doc.PrinterSettings.PrinterName)"


