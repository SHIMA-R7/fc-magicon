# FC-MAGICON 基板の現物合わせシートを A4 に原寸で印刷する(表面と裏面、定規チェック用スケール付き)
#   E:\KiCad\bin\python.exe dump_geom.py        … 先に geom.json を作る
#   pwsh -File print_fit_check.ps1 [-Printer "Brother DCP-J1270N Printer"] [-PdfOut out.pdf]
param(
    [string]$Printer = "",
    [string]$PdfOut = ""
)
Add-Type -AssemblyName System.Drawing
$g = Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot "geom.json") | ConvertFrom-Json
$BW = 90.0; $BH = 65.8; $STD_TOP = $BH - 56.8     # 規格の基板(56.8mm)なら上端はここ

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
$doc.DocumentName = "FC-MAGICON fit check"

$doc.add_PrintPage({
    param($s, $e)
    $gr = $e.Graphics
    $gr.PageUnit = [System.Drawing.GraphicsUnit]::Millimeter
    $gr.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $gr.TranslateTransform(-$e.PageSettings.HardMarginX * 0.254, -$e.PageSettings.HardMarginY * 0.254)
    $black = [System.Drawing.Brushes]::Black
    $gray = [System.Drawing.Brushes]::Gray
    $thin = New-Object System.Drawing.Pen ([System.Drawing.Color]::Black), 0.12
    $mid = New-Object System.Drawing.Pen ([System.Drawing.Color]::Black), 0.3
    $gpen = New-Object System.Drawing.Pen ([System.Drawing.Color]::Gray), 0.15
    $dash = New-Object System.Drawing.Pen ([System.Drawing.Color]::Black), 0.25
    $dash.DashStyle = [System.Drawing.Drawing2D.DashStyle]::Dash
    $fT = New-Object System.Drawing.Font "Yu Gothic UI", 4.2, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Millimeter)
    $fM = New-Object System.Drawing.Font "Yu Gothic UI", 2.6, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Millimeter)
    $fS = New-Object System.Drawing.Font "Yu Gothic UI", 1.9, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Millimeter)
    $fX = New-Object System.Drawing.Font "Arial", 1.3, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Millimeter)
    $center = New-Object System.Drawing.StringFormat
    $center.Alignment = [System.Drawing.StringAlignment]::Center

    $gr.DrawString("FC-MAGICON rev0.1  配線済み 実寸シート(原寸 1:1)", $fT, $black, 12, 8)
    $gr.DrawString("拡大縮小なしで印刷。先に下の100mmスケールを定規で測ってから切り抜いてください。", $fM, $black, 12, 15)

    function Draw-Board($ox, $oy, $back) {
        $MapX = { param($v) if ($back) { $ox + $BW - $v } else { $ox + $v } }
        foreach ($l in $g.edges) {
            $gr.DrawLine($mid, [single](& $MapX $l[0]), [single]($oy + $l[1]), [single](& $MapX $l[2]), [single]($oy + $l[3]))
        }
        # 配線(その面の銅箔だけ、実寸の線幅で薄く)とビア
        $side = if ($back) { "B" } else { "F" }
        foreach ($t in $g.tracks) {
            if ($t[5] -ne $side) { continue }
            $tp = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(150, 150, 150)), ([single]$t[4])
            $tp.StartCap = [System.Drawing.Drawing2D.LineCap]::Round; $tp.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $gr.DrawLine($tp, [single](& $MapX $t[0]), [single]($oy + $t[1]), [single](& $MapX $t[2]), [single]($oy + $t[3]))
            $tp.Dispose()
        }
        foreach ($v in $g.vias) {
            $vx = & $MapX $v[0]
            $gr.FillEllipse($gray, [single]($vx - $v[2] / 2), [single]($oy + $v[1] - $v[2] / 2), [single]$v[2], [single]$v[2])
        }
        # 規格の基板の上端(ここより上が延長部分)
        $gr.DrawLine($dash, [single]$ox, [single]($oy + $STD_TOP), [single]($ox + $BW), [single]($oy + $STD_TOP))
        # 部品の占有範囲(表面図だけ実線、裏面図は薄く)
        foreach ($p in $g.parts) {
            $x0 = & $MapX $p.x0; $x1 = & $MapX $p.x1
            if ($x0 -gt $x1) { $t = $x0; $x0 = $x1; $x1 = $t }
            $pen = if ($back) { $gpen } else { $thin }
            $gr.DrawRectangle($pen, [single]$x0, [single]($oy + $p.y0), [single]($x1 - $x0), [single]($p.y1 - $p.y0))
            if (-not $back -and $p.ref -notmatch '^P[234]$') {
                $gr.DrawString($p.ref, $fX, $black, [single](($x0 + $x1) / 2), [single]($oy + ($p.y0 + $p.y1) / 2 - 0.7), $center)
            }
        }
        foreach ($p in $g.pads) {
            $x = & $MapX $p.x; $y = $oy + $p.y
            if ($p.tht) {
                $d = [math]::Min($p.w, $p.h)
                $gr.DrawEllipse($thin, [single]($x - $d / 2), [single]($y - $d / 2), [single]$d, [single]$d)
                $gr.FillEllipse($black, [single]($x - $p.drill / 2), [single]($y - $p.drill / 2), [single]$p.drill, [single]$p.drill)
            } elseif (($back -and $p.back) -or (-not $back -and $p.front)) {
                $gr.FillRectangle($gray, [single]($x - $p.w / 2), [single]($y - $p.h / 2), [single]$p.w, [single]$p.h)
            }
        }
    }

    $oy = 30
    $ox1 = 12; $ox2 = 110
    Draw-Board $ox1 $oy $false
    Draw-Board $ox2 $oy $true
    $gr.DrawString("表面(部品面・本体の手前・端子1〜30番)", $fM, $black, $ox1, $oy - 5)
    $gr.DrawString("裏面(本体の奥・端子31〜60番)  左右反転", $fM, $black, $ox2, $oy - 5)
    foreach ($v in @(@($ox1, "30", "1"), @($ox2, "31", "60"))) {
        $gr.DrawString($v[1], $fS, $black, [single]($v[0] + 82.3), [single]($oy + $BH + 0.8))
        $gr.DrawString($v[2], $fS, $black, [single]($v[0] + 6.5), [single]($oy + $BH + 0.8))
    }
    $gr.DrawString("J2(3.5mmジャック)は左辺から約3.6mm外へ出る", $fS, $black, $ox1, $oy + $BH + 4)
    $gr.DrawString("点線 = 規格のカセット基板(56.8mm)の上端", $fS, $black, $ox1, $oy + $BH + 7)

    # 注意書き
    $ny = 112
    $notes = @(
        "■ 使い方",
        "・外形線(太線)で切り抜き、表面図と裏面図を厚紙の表裏に貼る(差し込み部の位置を必ず合わせる)。",
        "・基板は厚さ1.2mm。厚紙は1.2mm以下にすること。厚いものを押し込むと本体のコネクタを傷める。",
        "・本体の電源は切ったまま。紙の繊維がコネクタに残らないよう、端子部は軽く差す程度でよい。",
        "■ 見てほしい所",
        "・灰色の線 = その面の配線(実寸の線幅)。灰色の点 = ビア。",
        "・J4(2x30、カセット60ピン全部)は差し込み部のすぐ上。本体に入る高さなら、ピンは立てずにランドとして使う。",
        "・J5(2x8、デバッグ)・SWD(J3)は上辺。本体のフタや周りの出っ張りに当たらないか。",
        "・Core2350B(25.4mm角、ソケットで約13mm高くなる)と 3.5mmジャック J2 が、本体に当たらないか。",
        "・コンデンサー4個の右の枠 = 足を曲げて寝かせる場所。倒した時に何かに当たらないか。"
    )
    for ($i = 0; $i -lt $notes.Count; $i++) { $gr.DrawString($notes[$i], $fS, $black, 12, [single]($ny + $i * 4.2)) }

    # スケール
    $rx = 30; $ry = 160
    $gr.DrawString("スケール 100mm(0と100の線の間を定規で測る)", $fS, $black, $rx, $ry - 4)
    $gr.DrawLine($mid, [single]$rx, [single]$ry, [single]($rx + 100), [single]$ry)
    for ($i = 0; $i -le 100; $i++) {
        $t = if ($i % 10 -eq 0) { 4 } elseif ($i % 5 -eq 0) { 2.5 } else { 1.5 }
        $gr.DrawLine($thin, [single]($rx + $i), [single]$ry, [single]($rx + $i), [single]($ry + $t))
        if ($i % 10 -eq 0) { $gr.DrawString("$i", $fX, $black, [single]($rx + $i - 0.7), [single]($ry + 4.3)) }
    }
    $gr.DrawString("紙は印刷で0.3%程度伸縮する。100mm が 99.7〜100.3mm なら十分。", $fS, $black, $rx, $ry + 8)
    $e.HasMorePages = $false
})
$doc.Print()
Write-Output "送信しました: $($doc.PrinterSettings.PrinterName) $PdfOut"
