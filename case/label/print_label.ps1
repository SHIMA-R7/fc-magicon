# カセット表面のシール(label.png、20px/mm)を A4 にカラーで2枚印刷する(予備込み)。四隅にトンボ、下に 100mm スケール
#   python make_label.py → pwsh -File print_label.ps1 [-Printer "Brother DCP-J1270N Printer"] [-Scale 1.1]
#   -Scale は印刷時の追加の倍率(ふつうは 1.0。穴まで一緒に拡大される)
#   -Paper L は L 判(89 x 127mm、ドライバーでは "3.5x5 inch")に横置きで 1 枚、トンボだけ。光沢紙に刷る時用
param([string]$Printer = "Brother DCP-J1270N Printer", [double]$Scale = 1.0, [ValidateSet("A4", "L")][string]$Paper = "A4")   # 拡大は make_label.py の SCALE で済ませてある(穴は原寸)
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile((Join-Path $PSScriptRoot "label.png"))
$LW = $img.Width / 20.0 * $Scale; $LH = $img.Height / 20.0 * $Scale   # label.png は 20px/mm

$doc = New-Object System.Drawing.Printing.PrintDocument
$doc.PrinterSettings.PrinterName = $Printer
if (-not $doc.PrinterSettings.IsValid) { throw "プリンターが見つからない: $Printer" }
$raw = if ($Paper -eq "L") { 273 } else { 9 }   # 273 = 3.5x5 inch(L 判)、9 = A4
$ps = $doc.PrinterSettings.PaperSizes | Where-Object { $_.RawKind -eq $raw } | Select-Object -First 1
if (-not $ps) { throw "用紙 $Paper がドライバーに無い" }
$doc.DefaultPageSettings.PaperSize = $ps
$doc.DefaultPageSettings.Landscape = ($Paper -eq "L")
$best = $doc.PrinterSettings.PrinterResolutions | Where-Object { $_.Kind -eq [System.Drawing.Printing.PrinterResolutionKind]::High } | Select-Object -First 1
if ($best) { $doc.DefaultPageSettings.PrinterResolution = $best }
$doc.DefaultPageSettings.Color = $true
$doc.DocumentName = "FC-MAGICON label"
$doc.add_PrintPage({
    param($s, $e)
    $gr = $e.Graphics
    $gr.PageUnit = [System.Drawing.GraphicsUnit]::Millimeter
    $gr.TranslateTransform(-$e.PageSettings.HardMarginX * 0.254, -$e.PageSettings.HardMarginY * 0.254)
    $gr.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $black = [System.Drawing.Brushes]::Black
    $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::Black), 0.15
    $mid = New-Object System.Drawing.Pen ([System.Drawing.Color]::Black), 0.3
    $f = New-Object System.Drawing.Font "Yu Gothic UI", 2.4, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Millimeter)
    $fs = New-Object System.Drawing.Font "Yu Gothic UI", 1.8, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Millimeter)
    if ($Paper -eq "L") {                                     # L 判(横 127 x 縦 88.9mm)の真ん中に 1 枚
        $ox = (127 - $LW) / 2; $oy = (88.9 - $LH) / 2
        $gr.DrawImage($img, [single]$ox, [single]$oy, [single]$LW, [single]$LH)
        foreach ($c in @(@($ox, $oy, -1, -1), @(($ox + $LW), $oy, 1, -1), @($ox, ($oy + $LH), -1, 1), @(($ox + $LW), ($oy + $LH), 1, 1))) {
            $x = $c[0]; $y = $c[1]; $sx = $c[2]; $sy = $c[3]
            $gr.DrawLine($pen, [single]($x + $sx * 1), [single]$y, [single]($x + $sx * 5), [single]$y)
            $gr.DrawLine($pen, [single]$x, [single]($y + $sy * 1), [single]$x, [single]($y + $sy * 5))
        }
        $e.HasMorePages = $false
        return
    }
    $gr.DrawString(("FC-MAGICON カセット表面シール({0:0.#} x {1:0.#}mm = シールの絵は基板の110%・穴は原寸、2枚 = 予備込み)" -f $LW, $LH), $f, $black, 15, 12)
    $gr.DrawString("白い部分(赤い破線の内側)はケースの穴。切り抜いてから貼る。", $fs, $black, 15, 17)
    foreach ($oy in 28, 100) {
        $ox = (210 - $LW) / 2
        $gr.DrawImage($img, [single]$ox, [single]$oy, [single]$LW, [single]$LH)
        # トンボ(四隅、外形から 1mm 離して 4mm)
        foreach ($c in @(@($ox, $oy, -1, -1), @(($ox + $LW), $oy, 1, -1), @($ox, ($oy + $LH), -1, 1), @(($ox + $LW), ($oy + $LH), 1, 1))) {
            $x = $c[0]; $y = $c[1]; $sx = $c[2]; $sy = $c[3]
            $gr.DrawLine($pen, [single]($x + $sx * 1), [single]$y, [single]($x + $sx * 5), [single]$y)
            $gr.DrawLine($pen, [single]$x, [single]($y + $sy * 1), [single]$x, [single]($y + $sy * 5))
        }
    }
    $rx = 55; $ry = 180
    $gr.DrawString("スケール 100mm(拡大縮小なしで印刷されたか確認)", $fs, $black, $rx, $ry - 3.5)
    $gr.DrawLine($mid, [single]$rx, [single]$ry, [single]($rx + 100), [single]$ry)
    for ($i = 0; $i -le 100; $i++) {
        $t = if ($i % 10 -eq 0) { 4 } elseif ($i % 5 -eq 0) { 2.5 } else { 1.5 }
        $gr.DrawLine($pen, [single]($rx + $i), [single]$ry, [single]($rx + $i), [single]($ry + $t))
    }
    $e.HasMorePages = $false
})
$doc.Print()
$img.Dispose()
Write-Output "送信しました: $Printer"



