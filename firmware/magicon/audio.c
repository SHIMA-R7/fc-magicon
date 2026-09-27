// 画面転送モードの音。リングバッファ(8192 サンプル = 256ms)を DMA が 32kHz で PWM の比較値へ流し続ける。
//   ・DMA は「終わり無し」+ 読み出し側のリング(16KB 境界)で回り続けるので、CPU は書き足すだけ
//   ・間隔は DMA のタイマー: 250MHz × 4 / 31250 = 32000 回/秒
//   ・PWM は 10 ビット(1024 段)、250MHz / 1024 = 244kHz。基板の RC(R9 1k + C)と本体側で平らにする
//   ・鳴らし終えた所は audio_poll が無音(真ん中の 512)で埋める。PC からの音が途切れても古い音を繰り返さない
//   ・届いた音は 100ms 先に置く(画面のパケットの後ろで待たされても途切れないように)。PC とカセットの時計のずれは、
//     溜まり過ぎたら捨てる・足りなくなったら 100ms 先に置き直す、で吸収する
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/dma.h"
#include "hardware/pwm.h"
#include "audio.h"

#define RING_BITS   13
#define RING_LEN    (1u << RING_BITS)               // 8192 サンプル
#define RING_MASK   (RING_LEN - 1)
#define PWM_TOP     1023
#define SILENCE     512
#define LATENCY     (AUDIO_RATE / 10)               // 100ms
#define TOO_MUCH    (AUDIO_RATE * 3 / 20)           // 150ms 以上溜まったら捨てる(Wi-Fi のむらで 200ms 超まで溜まったため。2026-09-27)

static uint16_t ring[RING_LEN] __attribute__((aligned(RING_LEN * 2)));
static int dma_ch = -1;
static uint32_t rd_abs, wr_abs, cleared_abs;        // 通し番号(鳴らした所・書いた所・無音で埋めた所)
static uint32_t last_rd_idx;

static uint32_t rd_index(void) {
    return ((uintptr_t)dma_hw->ch[dma_ch].read_addr - (uintptr_t)ring) / 2 & RING_MASK;
}

void audio_init(unsigned pin) {
    for (uint32_t i = 0; i < RING_LEN; i++)
        ring[i] = SILENCE;
    gpio_set_function(pin, GPIO_FUNC_PWM);
    uint slice = pwm_gpio_to_slice_num(pin);
    pwm_config pc = pwm_get_default_config();
    pwm_config_set_wrap(&pc, PWM_TOP);
    pwm_init(slice, &pc, true);
    pwm_set_gpio_level(pin, SILENCE);

    int timer = dma_claim_unused_timer(true);
    dma_timer_set_fraction((uint)timer, 4, 31250);  // 250MHz × 4 / 31250 = 32kHz
    dma_ch = dma_claim_unused_channel(true);
    dma_channel_config c = dma_channel_get_default_config((uint)dma_ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_16);   // 比較値の A(下位 16 ビット)。B 側の GPIO45 は PWM ではない
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, false);
    channel_config_set_ring(&c, false, RING_BITS + 1);         // 読み出しを 16KB で折り返す
    channel_config_set_dreq(&c, dma_get_timer_dreq((uint)timer));
    volatile uint32_t *cc = &pwm_hw->slice[slice].cc;
    dma_channel_configure((uint)dma_ch, &c, (void *)cc, ring, dma_encode_endless_transfer_count(), true);
    last_rd_idx = rd_index();
    rd_abs = wr_abs = cleared_abs = 0;
}

void audio_poll(void) {
    if (dma_ch < 0) return;
    uint32_t idx = rd_index();
    rd_abs += (idx - last_rd_idx) & RING_MASK;      // 前に見てから鳴らした数(256ms 以内に呼ばれる前提)
    last_rd_idx = idx;
    while (cleared_abs < rd_abs)                    // 鳴らし終えた所を無音に
        ring[cleared_abs++ & RING_MASK] = SILENCE;
}

static void put(int16_t s) {
    ring[wr_abs & RING_MASK] = (uint16_t)(((int32_t)s + 32768) >> 6);   // -32768..32767 → 0..1023
    wr_abs++;
}

// 書き始める前に、書く所が鳴らす所より先か(足りない = 途切れた → 100ms 先へ)、溜まり過ぎていないか(→ 捨てる)
static bool make_room(void) {
    audio_poll();
    if (wr_abs < rd_abs + 64) {
        wr_abs = rd_abs + LATENCY;                  // 間は audio_poll が無音にしてある
        if (cleared_abs < rd_abs) cleared_abs = rd_abs;
        for (uint32_t a = rd_abs; a < wr_abs; a++)
            ring[a & RING_MASK] = SILENCE;
    }
    return wr_abs - rd_abs < TOO_MUCH;
}

// ---- IMA ADPCM(4 ビット) ----
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
