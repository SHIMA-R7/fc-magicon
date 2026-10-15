# MMC3 hardware diagnostic regression — 2026-10-13

Mario3 with the existing `magicon-mmc3-reload-generation.uf2` boots and plays,
but user reports the same lower-status-area corruption as before.

The newly built `magicon-mmc3-event-trace.uf2` failed to boot (gray screen,
also after console reset). Its event capture was never triggered.
`firmware/sim/mmc3-hardware-20261013/event-trace.log` shows CPU cycles continue
at approximately 1.79 million/s, repeated $8000=$40 / $A001=$00 writes,
CHR request=0, A12 events=0, latch=0, enable=0, and a latched late CPU ACK.
Thus these logs describe a startup regression, not the original HUD problem.
Instrumentation cost and the new build/layout are hypotheses, not proven causes.

User confirmed FC OFF. Restored and verified the exact previously playable
`magicon-mmc3-reload-generation.uf2`, SHA256
`C359CD3F064CE50A0DCFACF576266F08D74E0107A3EF199BF3D652A0DC6CC4E5`.
ROM slot still contains Mario3. The trace binary is withdrawn from hardware use.
Next capture should use the baseline firmware's existing counters first.

Pending source improvement gates CPU trace argument evaluation while inactive;
it has not been flashed or validated on hardware. Do not infer that it fixes
the diagnostic boot failure. Dumping a completed trace also pauses core0 CHR
copying and must not be treated as normal game rendering.

Host-test harness issue discovered during this work: Zig optimized builds
disabled assert, including setup calls placed inside assertions. The MMC3,
NSF and VRC6 audit files now explicitly undefine NDEBUG and were rerun with
assertions enabled; all pass. This corrects test validity, not physical timing.
