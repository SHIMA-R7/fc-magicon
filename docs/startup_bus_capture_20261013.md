# NEW Famicom startup bus capture — 2026-10-13

User-powered real console, USB-powered RP2350B A4, passive startup_monitor.
Captured 2048 CPU M2 cycles using PIO0 + DMA. GPIO0–46, excluding LED39,
were forced to input with OEOVER=LOW; runtime check reported zero failures.
The firmware never responds with ROM data, IRQ, CIRAM or audio output.
Flash program was backed up to
`C:/Users/Yugo/pico/work-startup-20261013/previous-program.uf2` before writing;
the separate ROM slot was not changed.

## Observed

- Before power-on: sense=0, M2=0, captured=0, output-override failures=0.
- Power-edge ISR timestamp: 501324204us since RP boot.
- First-M2 ISR timestamp: 501353218us. Difference: **29014us**.
  These are software interrupt observations, not calibrated edge timestamps.
- First four samples: reads at $00FF; next reads $0100, $01FF, $01FE.
- Sample7: **read $FFFC**; sample8: **read $FFFD**.
- Both vector data samples were $00 with no cartridge answering.
- Subsequent accesses include $0000/$0001, stack writes and $FFFE/$FFFF
  reads. This is not normal game execution: the CPU has no valid ROM response.
- Total captured: 2036 reads, 12 writes; 2013 reads in $8000–$FFFF;
  exactly two reset-vector reads in this finite capture.

## Conclusions and limits

This console reads the cartridge reset vector at startup, even with the
cartridge data outputs disabled. No broad address sweep appears in this short
capture; this does not prove absence of every startup access on other consoles
or outside the capture window. Console address/control outputs and data-bus
driving are distinct: observing an address is not evidence of data contention.

OEOVER verification establishes the diagnostic's digital output configuration.
It does not measure voltages, currents, analog contention or reverse supply,
and does not authorize a diode/power wiring change. A separate active-response
test is needed to measure the ordinary cartridge firmware's startup service.
The 29ms observation alone does not establish a universal boot-time budget.

Raw log: `firmware/sim/startup-20261013/first-power-on.log`.
Firmware: `firmware/out-direct-pio-diagnostic/startup-monitor-passive.uf2`.
