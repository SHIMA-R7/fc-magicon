#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stdatomic.h>
#include "boot_rom.h"

// Core0 fills PRG/CHR before release-publishing ready. Core1 owns game_active.
typedef struct {
    atomic_bool ready, waiting;
    bool game_active;
} fc_boot_state;

static inline void fc_boot_init(fc_boot_state *s) {
    atomic_init(&s->ready, false);
    atomic_init(&s->waiting, false);
    s->game_active = false;
}
static inline void fc_boot_write(fc_boot_state *s, uint16_t addr, uint8_t data) {
    if (!s->game_active && addr == 0xfff1 && data == 0xa5)
        atomic_store_explicit(&s->waiting, true, memory_order_release);
}
static inline uint8_t fc_boot_read(fc_boot_state *s, uint16_t addr, const uint8_t *prg) {
    if (s->game_active) return prg[addr & 0x7fff];
    if (addr == 0xfff0) {
        if (atomic_load_explicit(&s->waiting, memory_order_acquire) &&
            atomic_load_explicit(&s->ready, memory_order_acquire)) {
            s->game_active = true;
            return 1;
        }
        return 0;
    }
    if (addr == 0xfffc) return 0;
    if (addr == 0xfffd) return 0x80;
    // NMI / IRQ go to an RTI in the copied RAM code, not uninitialised PRG.
    if (addr == 0xfffa || addr == 0xfffe) return 0x0e;
    if (addr == 0xfffb || addr == 0xffff) return 2;
    uint16_t offset = addr & 0x7fff;
    return offset < sizeof fc_boot_code ? fc_boot_code[offset] : 0xea;
}
