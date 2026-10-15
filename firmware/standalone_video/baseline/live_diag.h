// NROM diagnostic only: core1 CPU; core0 high-priority PPU IRQ + USB.
// Does not prove timing margins. Uses constant FF CHR to isolate output timing.
static void __not_in_flash_func(live_ppu_irq)(void) {
    if (pio_sm_is_rx_fifo_empty(pio1,0)) return;
    uint32_t begun=m33_hw->dwt_cyccnt;
    uint32_t v=pio1->rxf[0];
    pio1->txf[0]=(v&B_PPU_A13)?0x80000000u:0x8000FFFFu;
    stat_ppu++;
    if (diag_ppu_service_count<32) {
        uint32_t elapsed=m33_hw->dwt_cyccnt-begun;
        if (elapsed>diag_ppu_service_max) diag_ppu_service_max=elapsed;
        diag_ppu_service_count++;
    }
}
static void live_ppu_irq_init(void) {
    m33_hw->demcr|=M33_DEMCR_TRCENA_BITS;
    m33_hw->dwt_ctrl|=M33_DWT_CTRL_CYCCNTENA_BITS;
    irq_set_exclusive_handler(PIO1_IRQ_0,live_ppu_irq);
    irq_set_priority(PIO1_IRQ_0,PICO_HIGHEST_IRQ_PRIORITY);
    irq_set_priority(USBCTRL_IRQ,0x80);
    pio_set_irq0_source_enabled(pio1,pis_sm0_rx_fifo_not_empty,true);
    irq_set_enabled(PIO1_IRQ_0,true);
}
