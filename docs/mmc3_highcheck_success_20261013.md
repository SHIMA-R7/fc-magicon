# Real-hardware improvement: short A12-high rejection

User reports a major improvement: world map and HUD both correct, with residual
transition corruption and stage jitter. The photograph confirms readable map
and HUD. Not a claim of complete MMC3 compatibility or stable long-term play.

Current candidate keeps the four-M2-falling-edge diagnostic qualifier and adds
an eight-cycle NOP delay after detecting A12 rise, then checks A12 is still high
before enqueueing the counter clock. At250MHz this adds roughly32ns plus branch
overhead; it is not a calibrated analog glitch filter. Short-high pulses return
to the reset state instead of clocking. Raw A12 probing was removed at runtime
to fit the shared PIO instruction memory; CPU mapper tracing remains absent.

Before this change, the raw probe recorded512low/high pairs;441 lows were90 or91
counts (~0.72us counting-loop contribution),59 lows were6539or6540counts
(~52.3us), and7highs hadzero decrement counts. Zero counts indicate very short
highs relative to the probe's setup overhead, not a measured zero-width pulse.
The input signal's electrical origin and exact pulse widths remain unknown.

After high checking, the existing ISR counters show no under8us event intervals
in the observed session. Late samples add approximately14,400A12events/s rather
than26,000–30,000/s. IRQ assertions approximately60/s; CPU lateACK latch0;
CHR requests catch up. Maximum1KiBcopy7444cycles (~29.8us at250MHz).
This strongly supports unwanted clocks as part of the original corruption;
ISR-service times still are not raw edge timestamps.

Confirmed candidate saved separately:
`firmware/out-direct-pio-diagnostic/magicon-mmc3-highcheck-improved-confirmed.uf2`
SHA256 `109B1B4D820E5EE46FA613F1B50E60F849D6FE0315800E690BCF5E037E2D2349`.
Reproducible source difference from854b94f:
`firmware/sim/mmc3-hardware-20261013/highcheck-confirmed.patch`.
Logs: `raw-a12-probe.log`, `highcheck-comparison.log`.

Next controlled comparison: retain short-high checking but restore the specified
three-M2-falling-edge qualifier. Then separately investigate non-atomic CHR
copies and IRQ service latency if jitter remains. Do not stack unrelated changes.
