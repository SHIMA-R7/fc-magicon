#pragma once
#include <stdint.h>
#include <stdbool.h>
#define NATIVE_PCM_RING 8192u
extern uint32_t native_pcm_replies[NATIVE_PCM_RING];
extern volatile uint32_t native_pcm_consumed;
extern volatile bool native_pcm_running;
extern volatile uint32_t native_pcm_last_reply,native_pcm_dac_writes,native_pcm_dac_errors,native_pcm_last_error;
bool native_pcm_start(const uint8_t *data,uint32_t samples,uint32_t rate,bool adpcm);
uint32_t native_pcm_poll(void); // consumed input samples, at the media's rate
bool native_pcm_faulted(void);
void native_pcm_stop(void);
uint32_t native_pcm_output_samples(void);

extern volatile uint32_t native_pcm_dac_hash,native_pcm_hash_count,native_pcm_hashes[32];
