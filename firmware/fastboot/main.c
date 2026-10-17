// Early CPU responder + RAM waiting bootstrap, initially NROM / CHR-ROM only.
// Software OE control does NOT isolate externally driven 5V on an unpowered RP2350.
#include <stdio.h>
#include <string.h>
#include "pico/multicore.h"
#include "hardware/clocks.h"
#include "../power_guard.h"
#include "cpu_m2.pio.h"
#include "ppu_chr.pio.h"
#include "mirror.pio.h"
#include "boot_protocol.h"
#include "nrom_image.h"

static uint8_t prg[32768], chr[8192];
static fc_boot_state boot;
static atomic_bool worker_ready;
static volatile uint32_t reads, late_cpu, late_ppu;

static void isolate(void) {
    for (uint p=0; p<=46; ++p) {
        if (p==39) continue;
        // Override first: even a peripheral configured later cannot drive a pin.
        gpio_set_oeover(p, GPIO_OVERRIDE_LOW);
        gpio_init(p);
        gpio_set_dir(p, GPIO_IN);
        gpio_disable_pulls(p);
        gpio_set_oeover(p, GPIO_OVERRIDE_LOW);
    }
}

static void __not_in_flash_func(serve)(void) {
    save_and_disable_interrupts();
    bool write_pending=false;
    uint16_t write_addr=0;
    atomic_store_explicit(&worker_ready, true, memory_order_release);
    for (;;) {
        if (!pio_sm_is_rx_fifo_empty(pio0,0)) {
            uint32_t h=pio_sm_get(pio0,0);
            if (write_pending) {
                fc_boot_write(&boot,write_addr,(uint8_t)h);
                write_pending=false;
            } else {
                uint16_t a=((h>>8)&0x7fff) | ((h&(1u<<23)) ? 0 : 0x8000);
                if (h&(1u<<24)) {
                    uint32_t answer=0x10000; // nonzero ACK, data pins stay input
                    if (!(h&(1u<<23))) {
                        answer=0xff00u | fc_boot_read(&boot,a,prg);
                        ++reads;
                    }
                    pio_sm_put(pio0,0,answer);
                } else {
                    write_addr=a;
                    write_pending=true;
                    pio_sm_put(pio0,0,0); // acknowledge write; never drive data
                }
            }
        }
        if (!pio_sm_is_rx_fifo_empty(pio1,0)) {
            uint32_t a=pio_sm_get(pio1,0);
            pio_sm_put(pio1,0,(a&(1u<<16)) ? 0x10000 : (0xff00u|chr[a&0x1fff]));
        }
        if (pio0->irq&1) { ++late_cpu; pio0->irq=1; }
        if (pio1->irq&1) { ++late_ppu; pio1->irq=1; }
    }
}

// Accept exactly an FCMG-wrapped iNES mapper0 game; fail closed for all others.
static const char *load_nrom(bool *vertical) {
    const uint8_t *slot=(const uint8_t *)(XIP_BASE+0x00800000u);
    return fc_load_nrom_image(slot,0x00800000u,prg,chr,vertical);
}

int main(void) {
    uint64_t entered=time_us_64();
    isolate();
    fc_boot_init(&boot);
    atomic_init(&worker_ready,false);
    // Nominal clock/voltage: no 250MHz overclock or fixed voltage-settling delay.
    set_sys_clock_khz(150000,true);
    pio_set_gpio_base(pio0,0);
    cpu_m2_program_init(pio0,0,pio_add_program(pio0,&cpu_m2_program));
    multicore_launch_core1(serve);
    while (!atomic_load_explicit(&worker_ready,memory_order_acquire)) tight_loop_contents();
    // USB stays responsive when FC is off, but never delays the FC-on cold path.
    bool usb_prepared=!gpio_get(46);
    if (usb_prepared) stdio_init_all();
    fc_wait_power();
    fc_arm_power_guard();
    for (uint p=0;p<8;p++) gpio_set_oeover(p,GPIO_OVERRIDE_NORMAL);
    pio_sm_set_enabled(pio0,0,true);
    uint64_t responding=time_us_64();
    bool vertical=false;
    const char *err=load_nrom(&vertical);
    if (!err) {
        pio_set_gpio_base(pio1,16);
        pio_set_gpio_base(pio2,16);
        ppu_chr_program_init(pio1,0,pio_add_program(pio1,&ppu_chr_program));
        mirror_program_init(pio2,0,pio_add_program(pio2,&mirror_program));
        // SDK converts absolute GPIO number to PIO2's window.
        pio_sm_set_in_pins(pio2,0,vertical ? 36u : 37u);
        for (uint p=26;p<34;p++) gpio_set_oeover(p,GPIO_OVERRIDE_NORMAL);
        gpio_set_oeover(43,GPIO_OVERRIDE_NORMAL);
        pio_sm_set_enabled(pio1,0,true);
        atomic_store_explicit(&boot.ready,true,memory_order_release);
    }
    if (!usb_prepared) stdio_init_all();
    printf("fastboot: main-to-CPU-responder %llu us (bootrom/runtime excluded); %s\n",
           (unsigned long long)(responding-entered),err ? err : "NROM ready");
    for (;;) {
        sleep_ms(1000);
        printf("fastboot: waiting=%u ready=%u reads=%lu late_cpu=%lu late_ppu=%lu\n",
            atomic_load(&boot.waiting),atomic_load(&boot.ready),
            (unsigned long)reads,(unsigned long)late_cpu,(unsigned long)late_ppu);
    }
}
