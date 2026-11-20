// CPU responder preserved from the October 13 hardware baseline.
static void __not_in_flash_func(mmc3_proven_bus_loop)(void) {
    io_ro_32 *cpu_rx = &pio0->rxf[0], *ppu_rx = &pio1->rxf[0];
    io_wo_32 *cpu_tx = &pio0->txf[0], *ppu_tx = &pio1->txf[0];
#if FC_DIAG_SPLIT
    save_and_disable_interrupts();
#endif
#if FC_DIAG_CPU_ONLY
    m33_hw->demcr |= M33_DEMCR_TRCENA_BITS;
    m33_hw->dwt_ctrl |= M33_DWT_CTRL_CYCCNTENA_BITS;
#endif
    __dmb(); bus_ready = true;
    for (;;) {
        if (!pio_sm_is_rx_fifo_empty(pio0, 0)) {
            uint32_t v = *cpu_rx;
#if FC_GAME_PROVEN_MMC3
            // MMC3 ROM reads have no CPU-side register bookkeeping. Queue the
            // external-memory result immediately; even bounded diagnostics and
            // statistics here consume its setup-time margin. stat_cpu below
            // therefore counts non-ROM-read events in this profile.
            if(!wr_pending && (v&(B_RW|B_ROMSEL))==B_RW) {
                uint a=(v>>8)&0x7fff;
                *cpu_tx=0x8000ff00u|prg_map[a>>13][a&0x1fff];
                continue;
            }
#endif
#if FC_DIAG_CPU_ONLY
            uint32_t begun = m33_hw->dwt_cyccnt;
#endif
            if (!wr_pending) {
                uint32_t reply = 0x80000000u;
                if (!(v & B_RW)) {
                    reply |= 0x10000u; // write acknowledgement, never drive
                } else {
                    uint a = (v >> 8) & 0x7FFF;
                    if (!(v & B_ROMSEL))
                        reply |= 0xFF00u | prg_map[a >> 13][a & 0x1FFF];
                    else if ((a & 0x6000) == 0x6000 && wram_enabled)
                        reply |= 0xFF00u | wram[a & 0x1FFF];
                }
                // Deadline-critical acknowledgement precedes all bookkeeping.
                *cpu_tx = reply;
#if FC_DIAG_NROM_GAME
                diag_last_cpu_header = v; // one bounded snapshot, after queued response
#endif
#if FC_DIAG_CPU_ONLY
                if (diag_service_count < 32) {
                    uint32_t elapsed = m33_hw->dwt_cyccnt - begun;
                    if (elapsed > diag_service_max) diag_service_max = elapsed;
                    diag_service_count++;
                }
#if !FC_DIAG_NROM_GAME
                diag_record_cpu(v, reply);
#endif
#endif
#if FC_DIAGNOSTIC
                if (!stat_cpu) diag_first_cpu = v;
#endif
            }
            // Also consumes the second (data) sample of a write, with no reply.
#if FC_DIAG_CPU_ONLY && FC_DIAG_DIRECT_CHR
            diag_nrom_bookkeeping(v);
#else
            (void)cpu_access(v);
#endif
        }
#if !FC_DIAG_CPU_ONLY
        if (!FC_REMOTE_DMA && !pio_sm_is_rx_fifo_empty(pio1, 0))
            *ppu_tx = 0x80000000u | ppu_access(*ppu_rx);
#endif
#if !FC_DIAG_MMC3_NO_IRQ && !FC_DIAG_MMC3_GAME
        if (is_mmc3 && !pio_sm_is_rx_fifo_empty(pio2, 1)) {
            (void)pio2->rxf[1];
            mmc3_clock();
        }
#endif
    }
}
