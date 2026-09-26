// FC-MAGICON sim: ファミコン本体の音源(APU)の真似(apu.c)
#pragma once
#include <stdint.h>

void apu_init(void);
void apu_write(uint16_t addr, uint8_t val, uint64_t cpu_cycle);
uint8_t apu_status(uint64_t cpu_cycle);          // $4015 の読み出し(長さカウンターが残っている ch のビット)
void apu_run(uint64_t cpu_cycle);                // その時刻まで進める
double apu_rms(void);
int apu_write_wav(const char *path);
