# bom.csv(python bom.py で作る)を A4 縦 1枚の表にして印刷する。左端はチェック欄
#   pwsh -File print_bom.ps1 [-Printer "Brother DCP-J1270N Printer"] [-PdfOut out.pdf]
param(
    [string]$Printer = "",
    [string]$PdfOut = ""
)
Add-Type -AssemblyName System.Drawing
$rows = Import-Csv (Join-Path $PSScriptRoot "bom.csv") -Encoding utf8

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
$doc.DocumentName = "FC-MAGICON parts list"

$doc.add_PrintPage({
    param($s, $e)
    $gr = $e.Graphics
    $gr.PageUnit = [System.Drawing.GraphicsUnit]::Millimeter
    $gr.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAlias
    $gr.TranslateTransform(-$e.PageSettings.HardMarginX * 0.254, -$e.PageSettings.HardMarginY * 0.254)
    $black = [System.Drawing.Brushes]::Black
    $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::Black), 0.2
    $light = New-Object System.Drawing.Pen ([System.Drawing.Color]::Gray), 0.1
    $fT = New-Object System.Drawing.Font "Yu Gothic UI", 5.0, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Millimeter)
    $fH = New-Object System.Drawing.Font "Yu Gothic UI", 3.0, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Millimeter)
    $fB = New-Object System.Drawing.Font "Yu Gothic UI", 2.9, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Millimeter)
    $fN = New-Object System.Drawing.Font "Yu Gothic UI", 2.3, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Millimeter)
    $vc = New-Object System.Drawing.StringFormat
    $vc.LineAlignment = [System.Drawing.StringAlignment]::Center

    $x0 = 14; $y = 12
    $gr.DrawString("FC-MAGICON rev0.1 パーツリスト", $fT, $black, $x0, $y)
    $gr.DrawString((Get-Date -Format "yyyy-MM-dd") + "  / 基板 90×65.8mm 2層 1.2mm", $fB, $black, 128, $y + 2)
    $y += 11
    # 列: チェック, 部品, 数, 記号, メモ
    $cols = @(@("✓", 8), @("部品", 58), @("数", 8), @("記号", 20), @("メモ", 88))
    $rowH = 7.4
    $x = $x0
    foreach ($c in $cols) {
        $gr.DrawString($c[0], $fH, $black, [System.Drawing.RectangleF]::new($x + 1, $y, $c[1] - 1, $rowH), $vc)
        $x += $c[1]
    }
    $W = ($cols | ForEach-Object { $_[1] } | Measure-Object -Sum).Sum
    $gr.DrawLine($pen, [single]$x0, [single]($y + $rowH), [single]($x0 + $W), [single]($y + $rowH))
    $y += $rowH
    foreach ($r in $rows) {
        $vals = @("", $r.'部品', $r.'数', $r.'記号', $r.'メモ')
        $x = $x0
        for ($i = 0; $i -lt $cols.Count; $i++) {
            $w = $cols[$i][1]
            if ($i -eq 0) {
                $gr.DrawRectangle($pen, [single]($x + 2), [single]($y + 2), [single]3.4, [single]3.4)
            } else {
                $font = if ($i -eq 4) { $fN } else { $fB }
                $rect = [System.Drawing.RectangleF]::new($x + 1, $y + 0.2, $w - 1.5, $rowH - 0.4)
                $gr.DrawString($vals[$i], $font, $black, $rect, $vc)
            }
            $x += $w
        }
        $y += $rowH
        $gr.DrawLine($light, [single]$x0, [single]$y, [single]($x0 + $W), [single]$y)
    }
    $y += 4
    $notes = @(
        "・C1/C4 は + 側を四角いパッドに。4個のコンデンサーは足を曲げて右へ寝かせる(シルクの枠)。",
        "・JP1〜JP3(CIRAM A10)はどれか1つだけはんだで閉じる。TP1〜TP5 は部品なし(テストポイント)。",
        "・発注: JLCPCB、厚み1.2mm、金メッキ端子(Gold fingers)、差し込み側45°面取り。"
    )
    foreach ($n in $notes) { $gr.DrawString($n, $fN, $black, $x0, [single]$y); $y += 4.5 }
    $e.HasMorePages = $false
})
$doc.Print()
Write-Output "送信しました: $($doc.PrinterSettings.PrinterName) $PdfOut"
