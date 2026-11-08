param(
    [Parameter(Mandatory=$true)][string]$Elf,
    [string]$C6Host = 'fc-magicon.local',
    [string]$OpenOcd = "$env:USERPROFILE/pico/openocd/bin/openocd.exe",
    [string]$Scripts = "$env:USERPROFILE/pico/openocd/openocd/scripts",
    [string]$Python = 'python',
    [switch]$HoldTarget,
    [switch]$ProbeOnly
)
$ErrorActionPreference = 'Stop'
if ($C6Host -notmatch '^[A-Za-z0-9.-]+$') { throw 'Invalid C6 host' }
$path = (Resolve-Path -LiteralPath $Elf).Path.Replace('\','/')
if ([IO.Path]::GetExtension($path) -ne '.elf' -or $path -match '[{}]') {
    throw 'Specify the RP2350 ELF firmware file'
}
# FC power must be OFF throughout halt, flash programming and reset.
$relayScript = Join-Path $PSScriptRoot 'c6_swd_relay.py'
$pythonExe = (Get-Command $Python -ErrorAction Stop).Source
$relayLog = Join-Path ([IO.Path]::GetTempPath()) ("fc-swd-" + [guid]::NewGuid().ToString('N'))
$relay = Start-Process $pythonExe -ArgumentList @('-u', ('"{0}"' -f $relayScript), '--host', $C6Host) -WindowStyle Hidden -RedirectStandardOutput "$relayLog.out" -RedirectStandardError "$relayLog.err" -PassThru
try {
    $deadline = (Get-Date).AddSeconds(10)
    do {
        $relay.Refresh()
        if ($relay.HasExited) { throw (Get-Content "$relayLog.err" -Raw) }
        if ((Get-Content "$relayLog.out" -Raw -ErrorAction SilentlyContinue) -match 'SWD relay ready') { break }
        if ((Get-Date) -gt $deadline) { throw 'SWD relay startup timed out' }
        Start-Sleep -Milliseconds 100
    } while ($true)
    $ocdArguments = @('-s', $Scripts, '-c', 'set C6_HOST 127.0.0.1; set C6_PORT 5002', '-f', "$PSScriptRoot/c6_swd.cfg")
    if ($ProbeOnly) {
        $ocdArguments += @('-c', 'init; targets; shutdown')
    } else {
        $reset = if ($HoldTarget) { "" } else { "reset" }
        $ocdArguments += @('-c', "program {$path} verify $reset exit")
    }
    & $OpenOcd @ocdArguments
    if ($LASTEXITCODE) { throw "OpenOCD failed ($LASTEXITCODE). Relay log: $relayLog.err" }
} finally {
    $relay.Refresh()
    if (-not $relay.HasExited) { Stop-Process -Id $relay.Id -ErrorAction SilentlyContinue }
}
