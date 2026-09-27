// 画面転送モードで PC の音を鳴らす(GPIO44 の PWM → RC → VR1 → R8 → カセット端子 46 番 = 本体の音声に混ぜる)
#pragma once
#include <stdint.h>

#define AUDIO_RATE        32000         // 1 秒あたりのサンプル数(モノラル)
#define AUDIO_MAX_SAMPLES 1024          // 1 パケットのサンプル数の上限

enum { AUDIO_FMT_PCM16 = 0, AUDIO_FMT_ADPCM = 1, AUDIO_FMT_PCM8 = 2 };   // PCM8 = 符号付き 8 ビット

// PWM と DMA を用意して、無音を鳴らし始める
void audio_init(unsigned pin);
// "FCAU" の後ろ: 形式 1 + サンプル数 2(LE) + 中身。中身の長さ(バイト)を返す(形式が変なら -1)
int audio_payload_len(uint8_t fmt, uint16_t n);
// 中身を戻してリングバッファに足す
void audio_push(uint8_t fmt, uint16_t n, const uint8_t *payload);
// 鳴らし終えた所を無音で埋める(途切れた時に古い音を鳴らさないため)。ときどき呼ぶ(256ms 以内ごと)
void audio_poll(void);
