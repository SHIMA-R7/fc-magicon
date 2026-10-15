# NSF player fixes and first VRC6 implementation — 2026-10-13

Changes were implemented in two stages: base NSF corrections, then VRC6.
No cartridge was flashed. No real Famicom audio or bus timing was measured.

## Base player

- PLAY uses an NTSC M2-cycle timer derived from the NSF microsecond period,
  defaulting to 16639us. Fractional CPU cycles carry between periods, rather
  than rounding each period independently. The driver polls a one-bit due
  latch at $5F02; overdue intervals coalesce rather than creating an unbounded
  backlog. $5F03 arms/disarms the timer after INIT. PLAY runs in the main loop;
  NMI handles the UI. A very short specified period does not guarantee that
  the NSF program can finish within it.
- START is explicitly STOP / RESTART FROM BEGINNING. It disables the real APU,
  then re-runs INIT when restarted. Real length counters and DMC state cannot
  be restored by merely writing $0F to $4015. A/track change still restart.
- STOP and track changes can abandon a non-returning PLAY through the NMI UI,
  resetting the stack; there is no attempted mid-instruction resume.
- Song numbers are three digits, including the 255 -> 1 wrap case.
- Initial bank restoration before INIT is retained. Out-of-range banks return
  an SRAM zero page of 4KB, rather than wrapping into an unrelated bank.
- Reject unsupported versions, zero songs, PAL-only/reserved regions, NSF2
  execution flags, INIT/PLAY outside the supported ROM window, load below
  $8000, oversized address-space data and truncated NSF2 program length.
  NSF2 with zero flags may use its explicit program length; annotations are
  ignored. NSFe remains unsupported. The PC packer has matching checks.
- NSF CPU service is now checked before PPU service. This is not proof that
  either bus deadline is met; physical timing still needs verification.

## VRC6 (experimental)

Independent C synthesis follows the documented [VRC6 audio registers](https://www.nesdev.org/wiki/VRC6_audio).
Two 16-step pulse oscillators, the 14-step saw accumulator, enable/phase reset,
constant-volume mode, halt and 16x/256x frequency scaling are implemented.
Samples average the per-CPU-cycle linear DAC values before downsampling to
32kHz. This is a functional model, not a calibrated replica of analog filtering.

Core1 captures NSF writes at $9000-$9003, $A000-$A002 and $B000-$B002 into a
256-event SPSC queue with M2-cycle timestamps. Core0 produces audio only up to
a published completed cycle (published every 64 headers). It never assumes a
future register write. Queue overflow latches silence and reports an error;
reboot is required. STOP/track initialization resets the expansion chip.

The local synthesis path uses the existing GPIO44 PWM/DMA output, with 64
samples (2ms) initial lead and a 128-sample (4ms) queue ceiling, replacing the
PC-stream's 100ms buffering policy for this mode only. These are software ring
settings, not measured end-to-end audio latency or synchronization.

Only the NSF VRC6 flag alone is accepted. Other expansion chips and combined
chip flags remain rejected. This does not implement VRC6 game mappers 24/26.
PWM level, DC coupling, relative APU volume, clock accuracy, aliasing and bus
response under synthesis load still require hardware measurements.

## Validation

- `magicon/test_nsf_driver.py`: generated 6502 code in py65; INIT, RAM clearing,
  bank restoration, buttons, STOP/restart, 255-song display/wrap; periods 8333,
  16639, 19997 and 33333us; non-returning PLAY stop/track change. All pass.
  This test's cartridge/timer are a Python model, not the physical firmware.
- `tests/audit_nsf.c`: actual cart.c loader and M2-header function; unsupported
  formats/bounds/banks; fractional timer across 479 period values × 1000
  intervals; real cartridge write -> VRC6 sample and STOP reset. All pass.
- `tests/audit_vrc6.c`: independent expected duty counts/saw steps, mode/halt,
  scaling priority, event timing, counter wrap, overflow silence. All pass.
  Two seconds of synthesis took ~0.014s on this Windows host; this is not an
  RP2350 performance measurement, and not a comparison with a reference emulator.
- `tests/test_nsf_local_audio.py`: actual audio.c ring with only DMA consumption
  simulated; initial lead, sample values, queue ceiling and underrun recovery.
  Pass. Existing mapper/cart audit passes.
- Pico SDK 2.3.1 / ARM GCC 15.2.1 Release build of ordinary magicon succeeds.
  Diagnostics and remote-DMA are disabled for this candidate.

Candidate: `firmware/out-direct-pio-diagnostic/magicon-nsf-vrc6-experimental.uf2`.
Earlier pre-VRC6 checkpoint: `magicon-nsf-base-fixed.uf2` (before the later
non-returning PLAY UI fix). Neither has been flashed. Candidate does not replace
the currently installed remote desktop firmware until explicitly tested.

No downloaded soundtrack has yet been tested in this session. INIT must return;
NSF2 IRQ/non-returning INIT features are rejected rather than emulated.
