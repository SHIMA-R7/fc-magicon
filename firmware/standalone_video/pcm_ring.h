#pragma once
#include <stdint.h>
#include <stdbool.h>
#define PCM_RING_SIZE 8192u
typedef struct {
    const uint8_t *source;
    uint32_t length,next,consumed,index;
} pcm_ring_state;
typedef struct { uint64_t last_us; bool faulted; } pcm_refill_deadline;
static inline bool pcm_refill_on_time(pcm_refill_deadline *d,uint64_t now_us) {
    if(now_us-d->last_us>=200000u)d->faulted=true;
    d->last_us=now_us;
    return !d->faulted;
}
static inline uint32_t pcm_ring_sample(pcm_ring_state *s) {
    return s->next<s->length ? s->source[s->next++] : 128u;
}
static inline void pcm_ring_init(pcm_ring_state *s,uint32_t *ring,const uint8_t *pcm,uint32_t length) {
    *s=(pcm_ring_state){.source=pcm,.length=length};
    for(uint32_t i=0;i<PCM_RING_SIZE;i++)ring[i]=pcm_ring_sample(s);
}
// Called more often than one ring revolution; index is the next unread DMA slot.
static inline uint32_t pcm_ring_refill(pcm_ring_state *s,uint32_t *ring,uint32_t index) {
    uint32_t used=(index-s->index)&(PCM_RING_SIZE-1);
    for(uint32_t i=0;i<used;i++)ring[(s->index+i)&(PCM_RING_SIZE-1)]=pcm_ring_sample(s);
    s->consumed+=used;s->index=index;
    return s->consumed>9 ? s->consumed-9 : 0;
}
