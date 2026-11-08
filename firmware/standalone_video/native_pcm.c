#include "pico/stdlib.h"
#include "hardware/sync.h"
#include "native_pcm.h"
#include "pcm_ring.h"
uint32_t native_pcm_replies[NATIVE_PCM_RING];
volatile uint32_t native_pcm_consumed;
volatile bool native_pcm_running;
volatile uint32_t native_pcm_last_reply,native_pcm_dac_writes,native_pcm_dac_errors,native_pcm_last_error;
volatile uint32_t native_pcm_dac_hash,native_pcm_hash_count,native_pcm_hashes[32];
static pcm_ring_state decoder;
static uint32_t refill_index,input_samples,output_length;
static bool fault;

static uint32_t next_reply(void) {
    uint sum=0;
    for(unsigned i=0;i<4;i++)sum+=pcm_ring_sample(&decoder);
    // Bit30 is a software-only marker, ignored by the CPU PIO's 16 output bits.
    return 0xc000ff00u|((sum+2u)>>3);
}
bool native_pcm_start(const uint8_t *data,uint32_t samples,uint32_t rate,bool adpcm) {
    if(rate!=32000 || !samples)return false;
    native_pcm_running=false;__dmb();
    decoder=(pcm_ring_state){.source=data,.length=samples,.adpcm=adpcm};
    native_pcm_consumed=0;refill_index=0;input_samples=samples;
    output_length=(samples+3u)/4u;fault=false;
    native_pcm_dac_hash=2166136261u;native_pcm_hash_count=0;
    native_pcm_last_reply=64;native_pcm_dac_writes=0;native_pcm_dac_errors=0;native_pcm_last_error=0;
    for(unsigned i=0;i<NATIVE_PCM_RING;i++)native_pcm_replies[i]=next_reply();
    __dmb();native_pcm_running=true;
    return true;
}
uint32_t native_pcm_poll(void) {
    uint32_t consumed=native_pcm_consumed;
    if(consumed-refill_index>=NATIVE_PCM_RING) {
        fault=true;native_pcm_running=false;
    } else {
        while(refill_index<consumed) {
            native_pcm_replies[refill_index&(NATIVE_PCM_RING-1)]=next_reply();
            refill_index++;
        }
        if(consumed>=output_length)native_pcm_running=false;
    }
    return consumed>=output_length?input_samples:consumed*4u;
}
bool native_pcm_faulted(void){return fault;}
void native_pcm_stop(void){native_pcm_running=false;}
uint32_t native_pcm_output_samples(void){return native_pcm_consumed;}
