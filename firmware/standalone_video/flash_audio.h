#pragma once
#include <stdint.h>
#include <stdbool.h>
void flash_audio_start(const uint8_t *pcm,uint32_t samples,uint32_t rate);
uint32_t flash_audio_poll(void);
uint32_t flash_audio_div256(void);
bool flash_audio_faulted(void);
void flash_audio_stop(void);
#if FC_PLAYER_AUDIO_LOG
void flash_audio_log(void);
#endif
