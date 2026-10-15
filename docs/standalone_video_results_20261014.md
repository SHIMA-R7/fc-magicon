# Standalone PV player: PC-side implementation / verification

## Current result

- Full 99s PV converted to 792 frames at 8fps. Shot palettes are held across
  95 detected scenes, with bounded per-block palette hysteresis. Pattern fitting
  limits each frame to 256 tiles. All packed CHR/NT/palette reconstructions match
  the encoder's expected RGB, including all 792 full-clip frames.
- Saved-media size **7,248,448 bytes** (4,080,384 video + 3,168,000 PCM8 + 64 header).
  The 8MiB media slot has **1,140,160 bytes** left. Audio gain20, source peak1371,
  zero clipping during quantisation. No claim of higher colour fidelity from packing.
- Complete firmware/media UF2 is prepared, but **not flashed**. User cannot operate
  the console now. Nothing in this work has changed OTP or the connected device.

## Firmware

`firmware/standalone_video` has a standalone main loop, FCPV parser, CRC32 check,
flash-to-SRAM audio ring, and a snapshot of the working atomic-display cartridge
engine. The baseline came from `C:/Users/Yugo/pico/work-remote-audit-20261014/magicon`
and was copied into the repository for reproducibility; current NSF/MMC3 sources
are not replaced. The snapshot adds `cart_video_stage` to bypass tile conversion.

The built-in 6502 program runs before full media CRC checking. A failed header/CRC
keeps the loading screen and flashes the module LED; it does not start audio or
dereference unvalidated frame pointers. Media is bounded to the final 8MiB.

Video stages hidden CHR and NT, then flips NT/CHR/palette together after seven
VBlank periods. The actual C cartridge plus py65 execution passed **all 792 frames**:
visible CHR/NT/palette stay intact until flip, pending stages cannot be overwritten,
and the maximum NMI is **1779 CPU cycles** against the **2273-cycle** NTSC budget.
PIO bandwidth and real analogue video timing remain unmeasured for this firmware.

Audio uses the previously successful PIO2 SM2 PWM program with a local 8192-word
SRAM DMA ring. PCM8 is unsigned (silence128), unlike the old USB PCM8 signed format.
The actual C ring was tested over multiple wraps, then beyond EOF for silence.
Neither the decoder nor playback loop needs a USB host. Optional USB CDC allows
picotool recovery; connection wait and post-connect delay are explicitly zero.

The quantised PIO divider is 322/256 at 250MHz, giving approximately
32026.7103 samples/s. Thus 99s of 32000Hz source samples plays in about98.9174s
(~82.6ms faster). Video is scheduled from the same consumed-audio cursor so this
does not accumulate A/V drift. A model of real NTSC VBlank cadence, seven-VBlank
ACK and this DAC rate gave maximum A/V presentation error8.55ms over99s for4/8fps.
This is **modelled**, not measured on hardware; FIFO/DMA stalls and input timing
are not proved by that test.

PIO instruction usage checked from generated headers: PIO0 CPU31; PIO1 CHR24;
PIO2 mirror1 + width probe7 + audio11 =19 of32 instructions.

Build: Pico SDK2.3.1, ARM GCC15.2.1, Release. Run
`firmware/standalone_video/build.ps1`. It copies sources to an ASCII build path,
does not recursively delete directories, and produces the player-only UF2.
`tools/make_standalone_uf2.py` uses official picotool `uf2 convert/combine`, retains
the RP2350-E10 ignored absolute block, then verifies firmware payload preservation
and reconstructs every saved-media byte from the final combined UF2.

## Artifacts

- `firmware/out-standalone-video/pv-30s-4fps-standalone-20261014.uf2`
  SHA256 `d63cef9e72ef9677ce43e36f70b72bf0e746ddf86002c5bc3f32cd51c33e3b7d`.
- `firmware/out-standalone-video/pv-full-99s-8fps-standalone-20261014.uf2`
  SHA256 `4a26a2e140f156fe4c32b19e8c0a5a5f2aa79346cd557d3b72da052752341ec0`.
- `firmware/sim/standalone-video-20261014/comparison-full-99s-8fps.mp4`
  99s,1280x664,25,211,144B. Left: full-colour original24fps. Right: RGB reconstructed
  from final FCPV CHR/NT/palette records at8fps. Audio: saved PCM8 transcoded toAAC.
  The banner states PC reconstruction / Twin Famicom not yet verified.
  The encoded20s frame and contact sheet were visually inspected. Decoded audio
  duration99.008s, peak27040, RMS5383.28; the output contains non-silent audio.
- Full-clip C/6502/ring/scheduling evidence:
  `firmware/sim/standalone-video-20261014/pv-full-99s-8fps.tests.json`.

Derived media and the source PV are local verification artifacts, not publication
materials. Large temporary raw RGB can be regenerated from the local source video.

## Remaining real-console gate

First test the 30s4fps version on the Twin Famicom, then full99s8fps. Confirm picture,
sound, EOF, startup/restart and power-off behaviour. The user must switch FC off
before firmware/media writing. PC-disconnected operation can initially use a USB
charger to power RP before FC; it does not require changing D1 or proving an
FC-only cold boot. FC-only power via D1, unpowered5V input exposure, and USB-side
reverse-current protection remain separate electrical checks. Do not claim the
overall goal complete based on PC tests or the comparison video.

## Follow-up audit: late audio refill and missing display acknowledgements

The original ring index only detected progress modulo8192; a foreground pause
of a whole revolution could therefore miss an underrun and replay stale samples.
The player now checks a monotonic service deadline before reading the index.
A gap of200ms or more latches a fault, aborts audio DMA, disables its PIO SM, and
switches GPIO44 to a steady50% PWM carrier for silence. The serving core and
power-loss guard remain active. It never attempts to resume an uncertain stream.
This handles a detected stall after core0 resumes; it does not promise that
software can mute while core0 itself is halted. Actual analogue muting is unverified.

The actual shared C deadline logic passes199999us gaps, faults at200000us, and
stays faulted after subsequent timely polls. All792-frame tests and the firmware
build were rerun successfully. GPIO44/PWM transition is build-checked, not hardware
tested. No normal-playback timings or comparison-video pixels changed.

LED fault codes (short flashes, then a long pause) and optional USB message:

| Code | Meaning |
|---|---|
| 1 | No6502 VBlank heartbeat within2s |
| 2 | Media header orCRC mismatch |
| 3 | Initial video frame not acknowledged within2s |
| 4 | Audio refill service gap >=200ms |
| 5 | A pending playback frame not acknowledged within500ms |

The combinedUF2 hashes above were updated for this revision. Both were rebuilt
with official picotool and their embedded media reconstructed/compared again.
Neither has been written to the device.
