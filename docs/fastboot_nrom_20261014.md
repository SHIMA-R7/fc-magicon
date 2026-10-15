# Early-response bootstrap experiment — 2026-10-14

## Scope

`firmware/fastboot` is a separate firmware target (`FC_FASTBOOT_ONLY=ON`).
It does not replace the current remote-video/PIO-audio or MMC3 firmware.
No device has been flashed and no OTP bits have been programmed for this work.
The target accepts a single FCMG-wrapped NTSC iNES mapper0 image with 16/32KB PRG
and 8KB CHR-ROM at the existing 8MB ROM slot. FCLB, FCRD, NSF, MMC3,
NES2, trainers, battery flags and CHR-RAM are rejected, leaving the FC waiting.

## Startup sequence

1. Force external-pin output enables LOW, input direction, no pulls. Preserve
   module LED39 / PSRAM47. Initialise GPIO46 as the FC power sense input.
2. Use nominal 150MHz at the default voltage, avoiding the existing 250MHz
   voltage change + fixed 10ms sleep. This trades bus-response margin for
   a simpler initial power-up; 150MHz CPU/PPU timing is NOT yet verified on hardware.
3. Prepare the CPU PIO and SRAM-resident core1 responder before reading the game.
   With FC off, USB can initialise while data pins remain isolated. With FC on,
   USB initialisation is deferred until the responder has started.
4. Wait for FC power, arm the existing falling-edge power guard, then release
   only CPU D0–7 to peripheral-controlled direction. CPU PIO gates direction on
   a selected ROM read and releases it at M2 falling. Late replies are discarded.
5. Serve a 48-byte bootstrap at $8000, reset vector $8000. It disables NMI,
   rendering and APU/DMC, initialises the stack, copies 15 bytes to FC RAM $0200,
   then jumps there. The RAM code acknowledges its copy via write $FFF1=$A5
   and polls $FFF0 until the game is prepared.
6. Core0 validates checksum/header/length/reset vector, copies PRG/CHR, sets up
   CHR/mirroring PIO behind output overrides, and release-publishes readiness.
   The first ready read returns 1 and switches core1 to the game PRG. Execution
   is still in FC RAM, so the subsequent `JMP ($FFFC)` uses the game's reset vector.
   Mailbox addresses cease being intercepted after the switch. No IRQ pulse
   or ROM-vector patching is needed. A later CPU reset uses the game's own vector.
7. On FC power loss the guard forces external OE overrides LOW, stops PIO and
   reboots after 50ms. Core1 cannot undo these overrides. A failed image never
   publishes readiness or enables the PPU/mirroring outputs.

IRQ remains masked during handoff. The bootstrap does not substitute for the
game's PPU startup wait/initialisation. NMI/IRQ vectors during the bootstrap
point to a RAM RTI; that RAM exists only after the copy, so this does not claim
recovery from an unexpected NMI before the early NMI-disable instruction.

## Verification

`firmware/tests/test_fastboot.py` compiles the actual C protocol and NROM loader
with Zig, then connects them to py65 executing the generated 6502 program.
Passed: readiness before/after the FC reaches RAM, long waiting without readiness,
handoff to the actual game vector, mailbox removal, unchanged game IRQ/NMI vectors,
CPU reset after handoff, 16/32KB NROM and mirroring flag, rejected invalid images.
`firmware/tests/test_power_guard.py` passed existing falling-edge and low-level
arming tests against the actual guard header.

Pico SDK 2.3.1 / ARM GCC 15.2 Release build succeeded. The ELF places the serving
loop and bootstrap byte array in SRAM; the serving loop has no function calls.
These checks do not measure cold power-up time, PIO deadlines, voltages or current.
The USB log's main-to-responder timestamp excludes boot ROM and C runtime; with
USB-first power it also includes waiting for the FC to be switched on.

## Electrical limits / next hardware measurement

This is not electrical isolation. An unpowered RP2350 cannot execute this program,
and disabling its outputs does not block FC-driven 5V inputs. GPIO46 is a digital
FC power indication, not proof that either supply is within its analogue limits.
The falling-edge handler also has finite interrupt/detection latency.

Before claiming FC-only/D1 startup safe, measure FC5V, RP IOVDD/3V3, M2 and CPU data
direction across startup/shutdown/brownout. The first CPU response must precede
the actual reset-vector read on each target console. Confirm supply/input limits
and USB-side reverse-current protection independently. If bus deadlines fail at
150MHz, do not declare the boot solution working merely because the protocol
emulates correctly. Keep the previous known-working firmware for recovery.

An OTP version should be considered only after this rewritable implementation
and the electrical power path are validated. OTP is not needed for the current
experiment and cannot fix the unpowered-input issue.
