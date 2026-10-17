# r1 + keyboard only, 2026-10-18

After gradual remote-r2 video degradation on Twin Famicom, initial CPU capture was clean (3508 selected ROM reads, zero mismatches). Restoring the exact confirmed r1 restored user-reported normal remote video. This supports comparing r2 additions separately; it does not prove which r2 change caused degradation.

`firmware/tools/build_remote_r1_keyboard.py` makes `firmware/out-standalone-video/remote-desktop-usb-r1-keyboard-20261018.uf2` without device access. It regenerates both the original video-only 6502 ROM and keyboard-enabled ROM. The original 16384-byte ROM must uniquely match the confirmed r1 at flash address 0x1000ad04. It replaces that array in place, preserving all ARM firmware, other flash payload and UF2 metadata. Exactly 74 payload bytes differ. No r2 audio buffering, statistics, idle screen, timeout or RP binary layout changes are introduced.

SHA256: 40ba51cad5ce378feb51398ad3c339d36a81ec0a1f032c9e804711830d9a9d74.

The existing actual-C + py65 driver test passes: keyboard 9 rows, controller data, seven-VBlank bank flip. Last PPU write is at most 1586 CPU cycles into NMI; full scan NMI at most 19304 cycles, below the 29700-cycle test frame budget. This checks software behavior and timing model, not electrical settling on the user's actual keyboard or long-duration real hardware video stability. Full 9-row scans remain the same as r2, intentionally allowing this one change to be compared against r1.

Use sender r2.1. First test Family BASIC keyboard in Notepad, then Blue Archive; successful Notepad input alone does not prove game acceptance. Await FC OFF / BOOTSEL readiness before flashing. Not written yet.
