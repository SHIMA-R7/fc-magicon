#pragma once
#include <stdint.h>
#include <stdbool.h>
bool cart_video_stage(const uint8_t record[5152]);
bool cart_video_pending(void);
uint8_t cart_video_vblank(void);
uint8_t cart_video_readback_status(void);
uint8_t cart_video_diag_byte(unsigned index);
void cart_nt_stress_ack(uint8_t sequence);
bool cart_nt_cpu_source(uint8_t request,uint8_t pattern,uint8_t bank);
#if FC_PLAYER_BOOT_LOG
void cart_boot_log(void);
#endif
