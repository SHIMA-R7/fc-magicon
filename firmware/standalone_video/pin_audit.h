#pragma once
#include <stdint.h>
// All FC signal GPIOs. Exclude module LED39 and PSRAM CS47.
#define FC_AUDIT_MASK (((1ull<<47)-1)&~(1ull<<39))
typedef struct { uint64_t high,low,changed,previous;uint32_t samples; } pin_audit;
static inline void pin_audit_sample(pin_audit *s,uint64_t value) {
    value&=FC_AUDIT_MASK;
    s->high|=value;s->low|=(~value)&FC_AUDIT_MASK;
    if(s->samples)s->changed|=value^s->previous;
    s->previous=value;s->samples++;
}
