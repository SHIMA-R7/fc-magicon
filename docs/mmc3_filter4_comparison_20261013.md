# MMC3 A12 four-falling-edge diagnostic comparison

The real IRQ-enabled reload-generation build produces a glyph-corrupted world
map with a readable HUD. The previously playable IRQ-disabled build restores
the world map but corrupts the HUD, as in the earliest physical test.
These binaries are not otherwise proven identical, so this is evidence for
investigating the split/IRQ path, not proof of a single root cause.

The IRQ-enabled baseline log has zero latched late CPU ACK, CHR request catches
up to handled, maximum 1KiB copy 7250 cycles (~29us at 250MHz). Late world-map
samples add ~29,700 qualified A12 events/s, with approximately half of recorded
ISR-service intervals under8us. ISR timestamps are not raw A12 edge timings.
8x16 sprites and CPU PPU accesses can legitimately add clocks; the count alone
does not prove erroneous qualification. Log: `playable-baseline.log`.

Controlled trial is built from GitHub checkpoint
`854b94f618390501d7e38db1710d3ea899dc7ae9`, without the later NSF work or CPU
event tracing. The only source change is `set x, 2` -> `set x, 3` in the A12
PIO qualifier, plus a comment: require four M2 falling edges rather than three.
Existing periodic counters remain. Normal qualifier in working source remains
three, matching the documented MMC3 rule. Four is a diagnostic hypothesis,
not a standards-compliant general fix.

`tests/test_mmc3_filter4_trial.py` passes 140 ideal M2 phase cases: a repeated
eight-PPU-dot-low waveform has some accepted edges with three, none with four;
a long low interval still clocks once with four. This does not establish the
real signal's low durations, account for analog glitches, or validate gameplay.

Pico SDK2.3.1 ARM GCC15.2.1 Release options:
FC_DIAGNOSTIC/FC_DIAG_CONST_CHR/FC_DIAG_CPU_ONLY/FC_DIAG_DIRECT_CHR/
FC_DIAG_DMA_CHR/FC_DIAG_MMC3_GAME/FC_DIAG_NROM_GAME=ON;
all other diagnostic, remote and trace options default OFF.

User confirmed FC OFF. Built, flashed and verified
`magicon-mmc3-filter4-comparison.uf2`, SHA256
`8A6927D058FF64282459D10114212890CC80C704788988B36C3D37D1274303E1`.
Mario3 ROM slot unchanged. Awaiting physical world-map/HUD comparison.
