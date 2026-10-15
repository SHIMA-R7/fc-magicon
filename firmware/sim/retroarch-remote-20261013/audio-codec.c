#include <stdint.h>
#include <stdbool.h>
#include "../../magicon/audio.h"
static int dma_ch=1;static int16_t *output;static unsigned used;
static bool make_room(void){return true;}
static void put(int16_t s){output[used++]=s;}
static const int16_t step_table[89] = {
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107,
    118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963,
    1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894,
    6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794,
    32767};
static const int8_t index_table[16] = {-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8};

int audio_payload_len(uint8_t fmt, uint16_t n) {
    if (n == 0 || n > AUDIO_MAX_SAMPLES) return -1;
    if (fmt == AUDIO_FMT_PCM16) return 2 * n;
    if (fmt == AUDIO_FMT_ADPCM) return 3 + (n + 1) / 2;    // 最初の値 2 + 段 1 + 4 ビット × n
    if (fmt == AUDIO_FMT_PCM8) return n;
    return -1;
}

void audio_push(uint8_t fmt, uint16_t n, const uint8_t *p) {
    if (dma_ch < 0 || !make_room()) return;
    if (fmt == AUDIO_FMT_PCM16) {
        for (uint16_t i = 0; i < n; i++)
            put((int16_t)(p[2 * i] | p[2 * i + 1] << 8));
    } else if (fmt == AUDIO_FMT_PCM8) {
        for (uint16_t i = 0; i < n; i++)
            put((int16_t)((int8_t)p[i] * 256));
    } else {
        int32_t pred = (int16_t)(p[0] | p[1] << 8);
        int idx = p[2] > 88 ? 88 : p[2];
        const uint8_t *d = p + 3;
        for (uint16_t i = 0; i < n; i++) {
            uint8_t code = (i & 1) ? d[i >> 1] >> 4 : d[i >> 1] & 15;
            int step = step_table[idx];
            int diff = step >> 3;
            if (code & 4) diff += step;
            if (code & 2) diff += step >> 1;
            if (code & 1) diff += step >> 2;
            pred += (code & 8) ? -diff : diff;
            if (pred > 32767) pred = 32767;
            if (pred < -32768) pred = -32768;
            idx += index_table[code];
            if (idx < 0) idx = 0;
            if (idx > 88) idx = 88;
            put((int16_t)pred);
        }
    }
}

__declspec(dllexport) unsigned decode(uint8_t fmt,uint16_t n,const uint8_t*p,int16_t*out){output=out;used=0;if(audio_payload_len(fmt,n)<0)return 0;audio_push(fmt,n,p);return used;}
