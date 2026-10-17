// 画面転送モードの音。リングバッファ(8192 サンプル = 256ms)を DMA が 32kHz で PWM の比較値へ流し続ける。
//   ・DMA は「終わり無し」+ 読み出し側のリング(16KB 境界)で回り続けるので、CPU は書き足すだけ
//   ・間隔は DMA のタイマー: 250MHz × 4 / 31250 = 32000 回/秒
//   ・PWM は 10 ビット(1024 段)、250MHz / 1024 = 244kHz。基板の RC(R9 1k + C)と本体側で平らにする
//   ・鳴らし終えた所は audio_poll が無音(真ん中の 512)で埋める。PC からの音が途切れても古い音を繰り返さない
//   ・届いた音は 100ms 先に置く(画面のパケットの後ろで待たされても途切れないように)。PC とカセットの時計のずれは、
//     溜まり過ぎたら捨てる・足りなくなったら 100ms 先に置き直す、で吸収する
#include <string.h>
#include <stdio.h>
#include "hardware/structs/io_bank0.h"
#include "hardware/clocks.h"
#include "pico/stdlib.h"
#include "hardware/dma.h"
#include "hardware/pwm.h"
#include "audio.h"
#include "audio_fifo.pio.h"

#define RING_BITS   13
#define RING_LEN    (1u << RING_BITS)               // 8192 サンプル
#define RING_MASK   (RING_LEN - 1)
#define PWM_TOP     255
#define SILENCE     128
#define LATENCY     (AUDIO_RATE / 10)               // 100ms
#define TOO_MUCH    (AUDIO_RATE * 3 / 20)           // 150ms 以上溜まったら捨てる(Wi-Fi のむらで 200ms 超まで溜まったため。2026-09-27)

static uint32_t ring[RING_LEN] __attribute__((aligned(RING_LEN * 4)));
static int dma_ch = -1;
static uint32_t rd_abs, wr_abs, cleared_abs;        // 通し番号(鳴らした所・書いた所・無音で埋めた所)
static uint32_t last_rd_idx;
static unsigned debug_pin,debug_slice;
#ifdef FC_AUDIO_WAVE_PROBE
#include "audio_wave_probe.h"
#endif
static uint32_t debug_packets,debug_accepted;
static uint32_t debug_underruns,debug_gap,last_poll;
void audio_stats(uint32_t out[4]) {
    out[0]=debug_packets;out[1]=debug_packets-debug_accepted;out[2]=debug_underruns;out[3]=debug_gap;
}
void audio_debug_report(void) {
#ifdef FC_AUDIO_WAVE_PROBE
    static bool captured=false;
    if(!captured){captured=true;audio_wave_probe();}
#endif
    if(dma_ch<0) {puts("AUDIO: DMA not initialized");return;}
    audio_poll();
    printf("AUDIO: rx=%lu accepted=%lu played=%lu queued=%ld dma_ctrl=%08lx pwm_cc=%08lx pin_ctrl=%08lx pin_status=%08lx\n",
        (unsigned long)debug_packets,(unsigned long)debug_accepted,(unsigned long)rd_abs,
        (long)(wr_abs-rd_abs),(unsigned long)dma_hw->ch[dma_ch].ctrl_trig,
        (unsigned long)pwm_hw->slice[debug_slice].cc,
        (unsigned long)io_bank0_hw->io[debug_pin].ctrl,(unsigned long)io_bank0_hw->io[debug_pin].status);
}

static uint32_t rd_index(void) {
    return ((uintptr_t)dma_hw->ch[dma_ch].read_addr - (uintptr_t)ring) / 4 & RING_MASK;
}

void audio_init(unsigned pin) {
    debug_pin=pin;debug_slice=pwm_gpio_to_slice_num(pin);
    for (uint32_t i = 0; i < RING_LEN; i++)
#ifdef FC_AUDIO_RING_TONE
#ifdef FC_AUDIO_FIFO_TONE
        ring[i] = ((i*112u)&RING_MASK)<(RING_LEN/2) ? 192 : 64;
#else
        ring[i] = ((i*112u)&RING_MASK)<(RING_LEN/2) ? 768 : 256;
#endif
#else
        ring[i] = SILENCE;
#endif
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
    channel_config_set_high_priority(&c,false); // keep original priority for carrier-frequency comparison
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32); // explicit whole-register write, A channel only
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, false);
    channel_config_set_ring(&c, false, RING_BITS + 2); // 32KB aligned ring, unchanged sample count/rate
    channel_config_set_dreq(&c, dma_get_timer_dreq((uint)timer));
    volatile uint32_t *cc = &pwm_hw->slice[slice].cc;
#ifdef FC_AUDIO_FIFO_TONE
    pwm_set_enabled(slice,false);
    const uint sm=2;
    pio_sm_claim(pio2,sm);
    uint offset=pio_add_program(pio2,&audio_fifo_program);
    pio_sm_config pcfg=audio_fifo_program_get_default_config(offset);
    sm_config_set_set_pins(&pcfg,pin,1);
    sm_config_set_out_shift(&pcfg,true,false,32);
    sm_config_set_fifo_join(&pcfg,PIO_FIFO_JOIN_TX);
    sm_config_set_clkdiv(&pcfg,(float)clock_get_hz(clk_sys)/(32000.0f*6206.0f));
    pio_gpio_init(pio2,pin);
    pio_sm_set_consecutive_pindirs(pio2,sm,pin,1,true);
    pio_sm_init(pio2,sm,offset,&pcfg);
    pio_sm_put(pio2,sm,255);
    channel_config_set_dreq(&c,pio_get_dreq(pio2,sm,true));
    dma_channel_configure((uint)dma_ch,&c,&pio2->txf[sm],ring,dma_encode_endless_transfer_count(),true);
    pio_sm_set_enabled(pio2,sm,true);
    puts("AUDIO FIFO PCM: PIO timed output; DMA feeds TX FIFO");
#else
    dma_channel_configure((uint)dma_ch, &c, (void *)cc, ring, dma_encode_endless_transfer_count(), true);
#endif
    last_rd_idx = rd_index();
    rd_abs = wr_abs = cleared_abs = 0;
#ifdef FC_AUDIO_RING_TONE
    puts("AUDIO RING TONE: 437.5Hz fixed PCM ring; no USB/refill/clear");
#endif
#ifdef FC_AUDIO_DIRECT_TONE
    // Diagnostic only: continuous 440Hz PWM, no sample DMA or USB pacing.
    dma_channel_abort((uint)dma_ch);
    pwm_set_enabled(slice,false);
    pwm_set_wrap(slice,32767);
    pwm_set_clkdiv(slice,(float)clock_get_hz(clk_sys)/(32768.0f*440.0f));
    pwm_set_gpio_level(pin,16384);
    pwm_set_counter(slice,0);
    pwm_set_enabled(slice,true);
    dma_ch=-1;
    puts("AUDIO DIRECT TONE: 440Hz PWM; USB/PCM/DMA bypassed");
#endif
}

void audio_poll(void) {
    if (dma_ch < 0) return;
    uint32_t now=time_us_32();
    if(last_poll && now-last_poll>debug_gap)debug_gap=now-last_poll;
    last_poll=now;
    uint32_t idx = rd_index();
    rd_abs += (idx - last_rd_idx) & RING_MASK;      // 前に見てから鳴らした数(256ms 以内に呼ばれる前提)
    last_rd_idx = idx;
#ifdef FC_AUDIO_RING_TONE
    return; // immutable diagnostic wave; retain the normal DMA and PWM settings
#endif
    while (cleared_abs != rd_abs)                  // uint32 の折返しを許す
        ring[cleared_abs++ & RING_MASK] = SILENCE;
}

static void put(int16_t s) {
    ring[wr_abs & RING_MASK] = (uint32_t)(((int32_t)s + 32768) >> 8);
    wr_abs++;
}
void audio_reset_stream(void) {
    if(dma_ch<0)return;
    audio_poll();
    for(unsigned i=0;i<RING_LEN;i++)ring[i]=SILENCE;
    wr_abs=rd_abs;cleared_abs=rd_abs;
}

// 書き始める前に、書く所が鳴らす所より先か(足りない = 途切れた → 100ms 先へ)、溜まり過ぎていないか(→ 捨てる)
static bool make_room(unsigned samples) {
    audio_poll();
    if ((int32_t)(wr_abs - rd_abs) < 64) {
        if(debug_accepted)debug_underruns++;
        wr_abs = rd_abs + LATENCY;                  // 間は audio_poll が無音にしてある
        cleared_abs = rd_abs;
        for (uint32_t a = rd_abs; a != wr_abs; a++)
            ring[a & RING_MASK] = SILENCE;
    }
    // Retain bursts while they fit, rather than discarding at just 150ms.
    return wr_abs-rd_abs+samples < RING_LEN-16;
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
#ifdef FC_AUDIO_RING_TONE
    (void)fmt;(void)n;(void)p;return;
#endif
    debug_packets++;
    if (dma_ch < 0 || !make_room(n)) return;
    debug_accepted++;
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
