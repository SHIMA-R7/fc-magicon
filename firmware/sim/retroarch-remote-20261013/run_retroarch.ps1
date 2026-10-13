# Run isolated snapshot fixtures with the installed RetroArch executable.
$ErrorActionPreference = 'Stop'
$fcQa = Join-Path $env:TEMP 'fc-ra-remote-20261013'
New-Item -ItemType Directory -Path $fcQa -Force | Out-Null
Copy-Item (Join-Path $PSScriptRoot '*.nes'),(Join-Path $PSScriptRoot '*.srm'),(Join-Path $PSScriptRoot 'nestopia_libretro.dll'),(Join-Path $PSScriptRoot 'custom.pal') $fcQa -Force
$fcPaths = $fcQa.Replace('\','/')
$fcConfig = @"
video_driver = "gl"
audio_driver = "null"
audio_enable = "false"
video_fullscreen = "false"
video_vsync = "false"
video_gpu_screenshot = "false"
video_shader_enable = "false"
config_save_on_exit = "false"
global_core_options = "true"
sort_savefiles_enable = "false"
sort_savestates_enable = "false"
auto_overrides_enable = "false"
history_list_enable = "false"
savefile_directory = "$fcPaths"
screenshot_directory = "$fcPaths"
system_directory = "$fcPaths"
core_options_path = "$fcPaths/core-options.cfg"
"@
Set-Content (Join-Path $fcQa 'qa.cfg') $fcConfig -Encoding utf8
Set-Content (Join-Path $fcQa 'core-options.cfg') 'nestopia_blargg_ntsc_filter = "disabled"','nestopia_palette = "custom"','nestopia_overscan_v_top = "0"','nestopia_overscan_v_bottom = "0"','nestopia_overscan_h_left = "0"','nestopia_overscan_h_right = "0"' -Encoding utf8
foreach ($fcCase in @('text','youtube','color')) {
    $fcArgs=@('-v','--log-file',"$fcQa\$fcCase-log.txt",'-c',"$fcQa\qa.cfg",'-L',"$fcQa\nestopia_libretro.dll",'--sram-mode=load-nosave','--max-frames=120','--max-frames-ss',"--max-frames-ss-path=$fcQa\$fcCase-retroarch.png","$fcQa\$fcCase.nes")
    $fcProc=Start-Process 'C:\RetroArch-Win64\retroarch.exe' -ArgumentList $fcArgs -WindowStyle Hidden -PassThru
    if (-not $fcProc.WaitForExit(15000)) { throw 'RetroArch did not finish within the expected time' }
    if ($fcProc.ExitCode -ne 0) { throw "RetroArch failed: $fcCase" }
    Copy-Item "$fcQa\$fcCase-retroarch.png","$fcQa\$fcCase-log.txt" $PSScriptRoot -Force
}
