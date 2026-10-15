#pragma once
#include <stdint.h>
#include <stdbool.h>
// NTSC 2A03 clock, in Hz. Fractional periods are carried between calls.
typedef struct { uint32_t whole, fraction, carry, remaining; bool active, ready; } nsf_clock_t;
static inline void nsf_clock_reload(nsf_clock_t *c) {
    c->remaining = c->whole;
    c->carry += c->fraction;
    if (c->carry >= 1000000u) { c->carry -= 1000000u; ++c->remaining; }
}
static inline void nsf_clock_init(nsf_clock_t *c, uint16_t us) {
    uint64_t n = (uint64_t)us * 1789773u;
    *c = (nsf_clock_t){.whole=n/1000000u, .fraction=n%1000000u};
}
static inline void nsf_clock_start(nsf_clock_t *c, bool active) {
    c->active=active; c->ready=false; c->carry=0; nsf_clock_reload(c);
}
static inline void nsf_clock_tick(nsf_clock_t *c) {
    if(c->active && --c->remaining == 0) { c->ready=true; nsf_clock_reload(c); }
}
static inline uint8_t nsf_clock_take(nsf_clock_t *c) {
    uint8_t r=c->ready; c->ready=false; return r;
}
