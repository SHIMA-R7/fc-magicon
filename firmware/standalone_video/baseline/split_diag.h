// NROM diagnostic only: core0 PPU, core1 CPU, no USB IRQ while serving.
// Included by cart.c so the same ROM/maps are used. Not a production mapper mode.
#include "../power_guard.h"
static void __not_in_flash_func(split_ppu_loop)(void) {
    save_and_disable_interrupts();
    m33_hw->demcr |= M33_DEMCR_TRCENA_BITS;
    m33_hw->dwt_ctrl |= M33_DWT_CTRL_CYCCNTENA_BITS;
    __dmb(); bus_ready = true;
    for (;;) {
        if (!gpio_get(46)) split_power_lost();
        if (!pio_sm_is_rx_fifo_empty(pio1, 0)) {
            uint32_t begun = m33_hw->dwt_cyccnt;
            uint32_t v = pio1->rxf[0];
            uint a = v & 0x1FFF;
#if FC_DIAG_CONST_CHR
            // Both bitplanes all 1: solid colour 3 within each palette region.
            // Never drive nametable reads; CIRAM still supplies those.
            pio1->txf[0] = (v & B_PPU_A13) ? 0x80000000u : 0x8000FFFFu;
#else
            pio1->txf[0] = 0x80000000u | ((v & B_PPU_A13) ? 0 :
                (0xFF00u | chr_map[a >> 10][a & 0x3FF]));
#endif
            stat_ppu++;
            if (diag_ppu_service_count < 32) {
                uint32_t elapsed = m33_hw->dwt_cyccnt - begun;
                if (elapsed > diag_ppu_service_max) diag_ppu_service_max = elapsed;
                diag_ppu_service_count++;
            }
        }
    }
}
static void __not_in_flash_func(split_power_lost)(void) {
    // Isolate outputs before recording results; both cores have IRQs disabled.
    for (uint p=0; p<=45; p++) {
        if (p==39) continue;
        hw_write_masked(&io_bank0_hw->io[p].ctrl,
            GPIO_OVERRIDE_LOW << IO_BANK0_GPIO0_CTRL_OEOVER_LSB,
            IO_BANK0_GPIO0_CTRL_OEOVER_BITS);
    }
    pio0->ctrl=0; pio1->ctrl=0; pio2->ctrl=0;
    watchdog_hw->scratch[2]=stat_cpu;
    watchdog_hw->scratch[3]=stat_ppu;
    uint lo=255, hi=0;
    uint missed=pio1->irq & 1;
    while (!pio_sm_is_rx_fifo_empty(pio2,1)) {
        uint32_t x=pio2->rxf[1];
        uint width=x==UINT32_MAX ? 255 : 31-x;
        if (width<lo) lo=width;
        if (width>hi) hi=width;
    }
    // SDK watchdog_enable overwrites scratch[4]; never store diagnostics there.
    watchdog_hw->scratch[5]=(diag_mark_errors & 0xFFFF)|(lo<<16)|(hi<<24);
    watchdog_hw->scratch[6]=pio_sm_get_pc(pio0,0)|(pio_sm_get_pc(pio1,0)<<8)|
        ((diag_ppu_service_max & 0x7FFF)<<16)|(missed<<31);
    watchdog_hw->scratch[7]=diag_marks;
    watchdog_hw->scratch[1]=0x53504C54u;
    fc_power_lost(46,0);
}
