# シールを L 判の光沢紙に、写真の品質で 1 枚刷る(Windows PowerShell 5.1 で動かす。System.Printing を使うため)
#   powershell.exe -File print_label_photo.ps1 [-DryRun]
#   python make_label.py --px 48 --out label_print.png(約 1200dpi)を先に作っておく
# 用紙の種類(光沢紙)・品質(写真)・L 判・横置きを、この印刷だけに設定する(プリンターの既定の設定は変えない):
#   PrintTicket に設定 → DEVMODE に変換 → System.Drawing の PrinterSettings に渡す
param([string]$Printer = "Brother DCP-J1270N Printer", [switch]$DryRun)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Printing, ReachFramework, System.Drawing

$q = (New-Object System.Printing.LocalPrintServer).GetPrintQueue($Printer)
$caps = $q.GetPrintCapabilities()
$pt = $q.UserPrintTicket.Clone()
$pt.PageMediaType = [System.Printing.PageMediaType]::PhotographicGlossy
$pt.OutputQuality = [System.Printing.OutputQuality]::Photographic
$pt.OutputColor = [System.Printing.OutputColor]::Color
# L 判は PrintTicket の一覧に無い(ドライバー独自の "3.5x5 inch")ので、大きさと向きは下で PageSettings に設定する
$conv = New-Object System.Printing.Interop.PrintTicketConverter($Printer, $q.ClientPrintSchemaVersion)
$dm = $conv.ConvertPrintTicketToDevMode($pt, [System.Printing.Interop.BaseDevModeType]::UserDefault)
$h = [Runtime.InteropServices.Marshal]::AllocHGlobal($dm.Length)
[Runtime.InteropServices.Marshal]::Copy($dm, 0, $h, $dm.Length)

$img = [System.Drawing.Image]::FromFile((Join-Path $PSScriptRoot "label_print.png"))
$LW = 99.0; $LH = 60.6                                      # label_print.png の実寸(mm)
$doc = New-Object System.Drawing.Printing.PrintDocument
$doc.PrinterSettings.PrinterName = $Printer
$doc.PrinterSettings.SetHdevmode($h)
$doc.DefaultPageSettings.SetHdevmode($h)
[Runtime.InteropServices.Marshal]::FreeHGlobal($h)
$Lsize = $doc.PrinterSettings.PaperSizes | Where-Object { $_.RawKind -eq 273 } | Select-Object -First 1   # 3.5x5 inch = L 判
if (-not $Lsize) { throw "L 判(3.5x5 inch)がドライバーに無い" }
$doc.DefaultPageSettings.PaperSize = $Lsize
$doc.DefaultPageSettings.Landscape = $true
$doc.DefaultPageSettings.Color = $true
$doc.DocumentName = "FC-MAGICON label (photo)"
$pgs = $doc.DefaultPageSettings
"用紙 {0}  {1:0.0} x {2:0.0}mm  横置き {3}  カラー {4}  品質 {5}  紙の種類 {6}" -f $pgs.PaperSize.PaperName, ($pgs.PaperSize.Width * 0.254), ($pgs.PaperSize.Height * 0.254), $pgs.Landscape, $pgs.Color, $pt.OutputQuality, $pt.PageMediaType
# 実際に渡る DEVMODE を PrintTicket に戻して確かめる
Add-Type -Namespace W -Name G -MemberDefinition '[DllImport("kernel32")] public static extern System.IntPtr GlobalLock(System.IntPtr h); [DllImport("kernel32")] public static extern bool GlobalUnlock(System.IntPtr h); [DllImport("kernel32")] public static extern System.IntPtr GlobalFree(System.IntPtr h);'
$hg = $doc.PrinterSettings.GetHdevmode($doc.DefaultPageSettings)
$hd = [W.G]::GlobalLock($hg)
$p = [Runtime.InteropServices.Marshal]::ReadInt16($hd, 68) + [Runtime.InteropServices.Marshal]::ReadInt16($hd, 70)   # dmSize + dmDriverExtra
$bytes = New-Object byte[] $p
[Runtime.InteropServices.Marshal]::Copy($hd, $bytes, 0, $p)
[void][W.G]::GlobalUnlock($hg); [void][W.G]::GlobalFree($hg)
$back = $conv.ConvertDevModeToPrintTicket($bytes)
"確認(実際に渡る設定): 紙の種類 {0}  品質 {1}  向き {2}" -f $back.PageMediaType, $back.OutputQuality, $back.PageOrientation
if ($DryRun) { $img.Dispose(); return }

$doc.add_PrintPage({
    param($s, $e)
    $gr = $e.Graphics
    $gr.PageUnit = [System.Drawing.GraphicsUnit]::Millimeter
    $gr.TranslateTransform(-$e.PageSettings.HardMarginX * 0.254, -$e.PageSettings.HardMarginY * 0.254)
    $gr.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic   # 約 1200dpi から縮める
    $gr.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $pw = $e.PageBounds.Width * 0.254; $ph = $e.PageBounds.Height * 0.254                   # 横置きなら 127 x 88.9
    $ox = ($pw - $LW) / 2; $oy = ($ph - $LH) / 2
    $gr.DrawImage($img, [single]$ox, [single]$oy, [single]$LW, [single]$LH)
    $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::Black), 0.15
    foreach ($c in @(@($ox, $oy, -1, -1), @(($ox + $LW), $oy, 1, -1), @($ox, ($oy + $LH), -1, 1), @(($ox + $LW), ($oy + $LH), 1, 1))) {
        $x = $c[0]; $y = $c[1]; $sx = $c[2]; $sy = $c[3]
        $gr.DrawLine($pen, [single]($x + $sx * 1), [single]$y, [single]($x + $sx * 5), [single]$y)
        $gr.DrawLine($pen, [single]$x, [single]($y + $sy * 1), [single]$x, [single]($y + $sy * 5))
    }
    $e.HasMorePages = $false
})
$doc.Print()
$img.Dispose()
"送信しました: $Printer"
