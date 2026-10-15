#pragma once
#include <stdatomic.h>
#include "vrc6_audio.h"
// SPSC queue: core1 records writes; core0 renders. Overflow latches silence.
#define NSF_EVENT_COUNT 256u
typedef struct { uint32_t cycle; uint8_t reg,data; } nsf_event_t;
typedef struct {
    nsf_event_t event[NSF_EVENT_COUNT];
    _Atomic uint32_t head,tail,fault;
    vrc6_audio_t chip;
    uint32_t cycle, sample_fraction;
} nsf_expansion_t;
static inline void nsf_expansion_init(nsf_expansion_t *s) {
    memset(s,0,sizeof *s);vrc6_reset(&s->chip);
}
static inline void nsf_expansion_write(nsf_expansion_t *s,uint32_t cycle,uint8_t reg,uint8_t data) {
    uint32_t h=atomic_load_explicit(&s->head,memory_order_relaxed);
    if(h-atomic_load_explicit(&s->tail,memory_order_acquire)==NSF_EVENT_COUNT){
        atomic_store_explicit(&s->fault,1,memory_order_release);return;
    }
    s->event[h&(NSF_EVENT_COUNT-1)]=(nsf_event_t){cycle,reg,data};
    atomic_store_explicit(&s->head,h+1,memory_order_release);
}
static inline unsigned nsf_expansion_render(nsf_expansion_t *s,uint32_t available,int16_t *out,unsigned count) {
    unsigned n=0;
    for(;n<count;n++) {
        uint32_t f=s->sample_fraction+1789773u, ticks=f/32000u;
        if((int32_t)(available-s->cycle)<(int32_t)ticks)break;
        s->sample_fraction=f%32000u;
        unsigned sum=0;
        uint32_t t=atomic_load_explicit(&s->tail,memory_order_relaxed);
        uint32_t h=atomic_load_explicit(&s->head,memory_order_acquire);
        for(unsigned k=0;k<ticks;k++) {
            while(t!=h) {
                nsf_event_t e=s->event[t&(NSF_EVENT_COUNT-1)];
                if((int32_t)(e.cycle-s->cycle)>0)break;
                if(e.reg==255)vrc6_reset(&s->chip);else vrc6_write(&s->chip,e.reg,e.data);
                atomic_store_explicit(&s->tail,++t,memory_order_release);
            }
            sum+=vrc6_tick(&s->chip);++s->cycle;
        }
        // Linear DAC, box-average before downsampling; hardware AC coupling removes DC.
        out[n]=atomic_load_explicit(&s->fault,memory_order_acquire)?0:(int16_t)(sum*400u/ticks);
    }
    return n;
}
