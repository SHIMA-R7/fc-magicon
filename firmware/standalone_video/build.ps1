param([switch]$Desktop,[switch]$ColdBoot,[switch]$Readback,[switch]$ChrReadback,[switch]$FrameReadback,[switch]$PaletteReadback,[switch]$PaletteCapability,[switch]$PaletteLog,[switch]$FastReads,[switch]$NtLog,[switch]$NtStress,[switch]$PinAudit,[switch]$CpuWindow,[switch]$PpuSettle,[switch]$LocalSettle,[switch]$StageCpu,[switch]$PageSamples,[switch]$NoPpu,[switch]$AddressProbe,[switch]$LocalProbe,[switch]$A9Remap,[switch]$BootLog,[switch]$DirectBoot,[switch]$AudioLog)
if($Desktop){$A9Remap=$true;$ColdBoot=$true;$FastReads=$true}
if($AudioLog){
    if($BootLog -or $DirectBoot){throw 'AudioLog preserves normal startup; do not combine with BootLog or DirectBoot'}
    $A9Remap=$true;$ColdBoot=$true;$FastReads=$true
}
if($DirectBoot){$BootLog=$true;$ColdBoot=$true;$FastReads=$true}
if($BootLog){$A9Remap=$true}
if($A9Remap -and ($Readback -or $NtStress -or $PinAudit -or $CpuWindow -or $LocalSettle -or $NoPpu -or $AddressProbe -or $LocalProbe -or $PaletteLog -or $NtLog)){throw 'A9Remap currently supports video playback only'}
if ($LocalProbe) { if ($StageCpu -or $PageSamples -or $CpuWindow) { throw 'LocalProbe cannot use CPU source modes' }; $AddressProbe = $true; $LocalSettle = $true }
if ($AddressProbe) { $NoPpu = $true }
if ($NoPpu -and -not $LocalProbe) { $PageSamples = $true }
if ($PageSamples) { $StageCpu = $true }
if ($StageCpu) { if ($LocalSettle) { throw 'StageCpu cannot use LocalSettle' }; $PpuSettle = $true; $CpuWindow = $true }
if ($LocalSettle) { if ($CpuWindow) { throw 'LocalSettle cannot use CpuWindow' }; $PpuSettle = $true; $PinAudit = $true }
if ($PpuSettle -and -not $LocalSettle) { $CpuWindow = $true }
if ($CpuWindow) { $PinAudit = $true }
if ($PinAudit) { $NtStress = $true }
if ($NtStress -and ($Readback -or $PaletteLog -or $NtLog -or $ChrReadback -or $FrameReadback -or $PaletteReadback -or $PaletteCapability)) { throw 'NT stress is a separate diagnostic mode' }
if ($NtLog) { $PaletteLog = $true }
if ($PaletteLog) { $PaletteReadback = $true }
if ($PaletteCapability) { $Readback = $true }
if ($PaletteReadback) { $FrameReadback = $true }
if ($ChrReadback -or $FrameReadback) { $Readback = $true }
if ($ChrReadback -and $FrameReadback) { throw 'Select one readback mode' }
$ErrorActionPreference = 'Stop'
$sdkRoot = 'C:\Users\Yugo\pico'
$work = "$sdkRoot\work-standalone-video-20261014"
if ($ColdBoot) { $work = "$sdkRoot\work-standalone-video-cold-20261014" }
if ($Readback) { $work += '-readback' }
if ($ChrReadback) { $work += '-chr' }
if ($FrameReadback) { $work += '-frames' }
if ($PaletteReadback) { $work += '-palette' }
if ($PaletteCapability) { $work += '-capability' }
if ($PaletteLog) { $work += '-log' }
if ($FastReads) { $work += '-fastreads' }
if ($NtLog) { $work += '-ntlog' }
if ($NtStress) { $work += '-ntstress' }
if ($PinAudit) { $work += '-pins' }
if ($CpuWindow) { $work += '-cpuwindow' }
if ($PpuSettle) { $work += '-settled' }
if ($LocalSettle) { $work += '-local' }
if ($StageCpu) { $work += '-staged' }
if ($PageSamples) { $work += '-samples' }
if ($NoPpu) { $work += '-noppu' }
if ($AddressProbe) { $work = "$sdkRoot\work-nt-address-20261015" }
if ($LocalProbe) { $work = "$sdkRoot\work-nt-local-address-20261015" }
if ($A9Remap) { $work = "$sdkRoot\work-player-a9-39-20261016" }
if ($BootLog) { $work = "$sdkRoot\work-player-bootlog-20261016" }
if ($DirectBoot) { $work = "$sdkRoot\work-player-direct-20261016" }
if ($AudioLog) { $work = "$sdkRoot\work-player-audio-log-deferred-20261017" }
if($Desktop){$work = "C:\Users\Yugo\pico\work-desktop-usb-20261017"}
$firmware = Split-Path -Parent $PSScriptRoot
$env:PATH = "$sdkRoot\gcc\xpack-arm-none-eabi-gcc-15.2.1-1.1\bin;$sdkRoot\cmake\cmake-4.4.3-windows-x86_64\bin;$sdkRoot\ninja;" + $env:PATH
$env:PICO_SDK_PATH = "$sdkRoot/pico-sdk/pico-sdk-2.3.1"
$env:PICO_TOOLCHAIN_PATH = "$sdkRoot/gcc/xpack-arm-none-eabi-gcc-15.2.1-1.1"
New-Item -ItemType Directory -Force $work | Out-Null
Copy-Item "$firmware\CMakeLists.txt", "$firmware\power_guard.h" -Destination $work
Copy-Item "$firmware\boards", $PSScriptRoot -Destination $work -Recurse -Force
if ($ColdBoot) { Copy-Item "$firmware\fastboot" -Destination $work -Recurse -Force }
$desktopFlag = if ($Desktop) { 'ON' } else { 'OFF' }
$coldFlag = if ($ColdBoot) { 'ON' } else { 'OFF' }
$readbackFlag = if ($Readback) { 'ON' } else { 'OFF' }
$chrReadbackFlag = if ($ChrReadback) { 'ON' } else { 'OFF' }
$frameReadbackFlag = if ($FrameReadback) { 'ON' } else { 'OFF' }
$paletteReadbackFlag = if ($PaletteReadback) { 'ON' } else { 'OFF' }
$capabilityFlag = if ($PaletteCapability) { 'ON' } else { 'OFF' }
$paletteLogFlag = if ($PaletteLog) { 'ON' } else { 'OFF' }
$fastReadsFlag = if ($FastReads) { 'ON' } else { 'OFF' }
$ntStressFlag = if ($NtStress) { 'ON' } else { 'OFF' }
$pinAuditFlag = if ($PinAudit) { 'ON' } else { 'OFF' }
$cpuWindowFlag = if ($CpuWindow) { 'ON' } else { 'OFF' }
$ppuSettleFlag = if ($PpuSettle) { 'ON' } else { 'OFF' }
$stageCpuFlag = if ($StageCpu) { 'ON' } else { 'OFF' }
$pageSamplesFlag = if ($PageSamples) { 'ON' } else { 'OFF' }
$noPpuFlag = if ($NoPpu) { 'ON' } else { 'OFF' }
$addressProbeFlag = if ($AddressProbe) { 'ON' } else { 'OFF' }
$a9RemapFlag = if ($A9Remap) { 'ON' } else { 'OFF' }
$bootLogFlag = if ($BootLog) { 'ON' } else { 'OFF' }
$directBootFlag = if ($DirectBoot) { 'ON' } else { 'OFF' }
$audioLogFlag = if ($AudioLog) { 'ON' } else { 'OFF' }
cmake -G Ninja -S $work -B "$work\build" -DCMAKE_BUILD_TYPE=Release -DFC_STANDALONE_VIDEO_ONLY=ON `
    "-DFC_REMOTE_DESKTOP=$desktopFlag" `
    "-DFC_PLAYER_COLD_BOOT=$coldFlag" `
    "-DFC_PLAYER_READBACK=$readbackFlag" `
    "-DFC_PLAYER_CHR_READBACK=$chrReadbackFlag" `
    "-DFC_PLAYER_FRAME_READBACK=$frameReadbackFlag" `
    "-DFC_PLAYER_PALETTE_READBACK=$paletteReadbackFlag" `
    "-DFC_PLAYER_PALETTE_CAPABILITY=$capabilityFlag" `
    "-DFC_PLAYER_PALETTE_LOG=$paletteLogFlag" `
    "-DFC_PLAYER_FAST_READS=$fastReadsFlag" `
    "-DFC_PLAYER_NT_STRESS=$ntStressFlag" `
    "-DFC_PLAYER_PIN_AUDIT=$pinAuditFlag" `
    "-DFC_PLAYER_CPU_WINDOW=$cpuWindowFlag" `
    "-DFC_PLAYER_PPU_SETTLE=$ppuSettleFlag" `
    "-DFC_PLAYER_CPU_STAGE=$stageCpuFlag" `
    "-DFC_PLAYER_PAGE_SAMPLES=$pageSamplesFlag" `
    "-DFC_PLAYER_NO_PPU=$noPpuFlag" `
    "-DFC_PLAYER_ADDRESS_PROBE=$addressProbeFlag" `
    "-DFC_PLAYER_A9_REMAP=$a9RemapFlag" `
    "-DFC_PLAYER_BOOT_LOG=$bootLogFlag" `
    "-DFC_PLAYER_DIRECT_BOOT=$directBootFlag" `
    "-DFC_PLAYER_AUDIO_LOG=$audioLogFlag" `
    "-Dpicotool_DIR=$sdkRoot/picotool/picotool" "-Dpioasm_DIR=$sdkRoot/pico-sdk-tools/pioasm"
if ($LASTEXITCODE) { throw 'standalone configure failed' }
cmake --build "$work\build" --target magicon_standalone_video
if ($LASTEXITCODE) { throw 'standalone build failed' }
$output = "$firmware\out-standalone-video"
New-Item -ItemType Directory -Force $output | Out-Null
$filename = if ($ColdBoot) { 'player-firmware-cold-20261014.uf2' } else { 'player-firmware-20261014.uf2' }
if ($Readback) { $filename = 'player-firmware-readback-cold-20261014.uf2' }
if ($ChrReadback) { $filename = 'player-firmware-chr-readback-cold-20261014.uf2' }
if ($FrameReadback) { $filename = 'player-firmware-frame-readback-cold-20261014.uf2' }
if ($PaletteReadback) { $filename = 'player-firmware-palette-readback-cold-20261014.uf2' }
if ($PaletteCapability) { $filename = 'player-firmware-palette-capability-cold-20261014.uf2' }
if ($PaletteLog) { $filename = 'player-firmware-palette-log-cold-20261014.uf2' }
if ($FastReads) { $filename = $filename.Replace('-20261014.uf2','-fast-20261014.uf2') }
if ($NtLog) { $filename = $filename.Replace('palette-log','palette-nt-log') }
if ($NtStress) { $filename = 'nt-stress-cold-fast-20261014.uf2' }
if ($PinAudit) { $filename = 'pin-audit-cold-fast-20261015.uf2' }
if ($CpuWindow) { $filename = 'cpu-window-pin-audit-cold-fast-20261015.uf2' }
if ($PpuSettle) { $filename = 'cpu-window-settled-cold-fast-20261015.uf2' }
if ($LocalSettle) { $filename = 'nt-local-settled-cold-fast-20261015.uf2' }
if ($StageCpu) { $filename = 'cpu-staged-settled-cold-fast-20261015.uf2' }
if ($PageSamples) { $filename = 'cpu-page-samples-cold-fast-20261015.uf2' }
if ($NoPpu) { $filename = 'cpu-page-samples-no-ppu-cold-fast-20261015.uf2' }
if ($AddressProbe) { $filename = 'cpu-nt-address-probe-cold-fast-20261015.uf2' }
if ($LocalProbe) { $filename = 'local-nt-address-probe-cold-fast-20261015.uf2' }
if ($A9Remap) { $filename = 'player-a9-gpio39-cold-fast-20261016.uf2' }
if ($BootLog) { $filename = 'player-a9-gpio39-boottrace-20261016.uf2' }
if ($DirectBoot) { $filename = 'player-a9-gpio39-direct-20261016.uf2' }
if ($AudioLog) { $filename = 'player-a9-gpio39-audio-log-deferred-20261017.uf2' }
if($Desktop){$filename = 'remote-desktop-usb-a9-gpio39-20261017-r2.uf2'}
Copy-Item "$work\build\standalone_video\magicon_standalone_video.uf2" -Destination "$output\$filename"
Write-Output "$output\$filename"


