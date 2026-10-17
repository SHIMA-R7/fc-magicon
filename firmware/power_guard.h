// Firmware protection only: cannot protect an unpowered RP2350 from 5V inputs.
#pragma once
#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "hardware/irq.h"
#include "hardware/watchdog.h"
#include "hardware/structs/io_bank0.h"
#include "hardware/structs/sio.h"
#include "hardware/regs/io_bank0.h"
#include "hardware/sync.h"

// Core 0 never returns from this handler. Core 1 may still process queued data,
// but OE overrides isolate every external output, including PIO and PWM.
static void __not_in_flash_func(fc_power_lost)(uint gpio, uint32_t events) {
    (void)gpio; (void)events;
    for (uint p = 0; p <= 45; ++p) {
#if !FC_PLAYER_A9_REMAP
        if (p == 39) continue; // module LED; GPIO47 is PSRAM CS
#endif
        hw_write_masked(&io_bank0_hw->io[p].ctrl,
            GPIO_OVERRIDE_LOW << IO_BANK0_GPIO0_CTRL_OEOVER_LSB,
            IO_BANK0_GPIO0_CTRL_OEOVER_BITS);
    }
    pio0->ctrl = 0;
    pio1->ctrl = 0;
    pio2->ctrl = 0;
    watchdog_hw->scratch[0] = 0; // restart at library menu
    watchdog_enable(50, true);
    for (;;) tight_loop_contents(); // never resume USB/audio or bus setup
}

static void fc_wait_power(void) {
    // No printf/USB waits on the path from power detection to bus start.
    uint64_t next_led = time_us_64() + 100000;
    while (!gpio_get(46)) {
        if (time_us_64() >= next_led) {
#if !FC_PLAYER_A9_REMAP
            sio_hw->gpio_hi_togl = 1u << (39 - 32);
#endif
            next_led = time_us_64() + 100000;
        }
        sleep_us(10);
    }
}

static void fc_arm_power_guard(void) {
    // Call before bus/output configuration, after initializing GPIO46. A stale edge or a low level
    // fails closed; turning power back on requires a fresh boot.
    irq_set_priority(IO_IRQ_BANK0, PICO_HIGHEST_IRQ_PRIORITY);
    gpio_set_irq_enabled_with_callback(46, GPIO_IRQ_EDGE_FALL, true, fc_power_lost);
    if (!gpio_get(46)) fc_power_lost(46, 0);
}
