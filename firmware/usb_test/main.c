// usb_test: 画面転送の USB の速さを、ファミコン無し(Core2350B2 だけ)で測る。
//   magicon の画面転送モード(remote_loop)と同じ読み方で "FCFR" + 15459 バイトを受け取り、中身は捨てる。
//   入力は 6502 の代わりに 60 回/秒 "FCIN" を返す(パッド 0、キーボードは全部「押していない」= 0xFF、最後の 1 バイトはフレームの数)。
//   PC 側はそのまま python tools/remote_pc.py で動き、表示される fps が USB の速さになる(何も押されない)。
//   予備の 5 バイトの先頭 2 バイトに、受け取った枚数(下位・上位)を入れる。LED は 1 枚ごとに反転。
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/vreg.h"
#include "hardware/clocks.h"

#define PIN_LED 39

static uint8_t back[15360];
static uint8_t meta[32 + 64 + 3];

static int read_exact(uint8_t *buf, int len, uint32_t timeout_ms) {
    int got = 0;
    absolute_time_t until = make_timeout_time_ms(timeout_ms);
    while (got < len) {
        int n = stdio_get_until((char *)buf + got, len - got, until);
        if (n <= 0) return got;
        got += n;
    }
    return got;
}

static uint16_t frames_rx;
static uint8_t vframe;
static absolute_time_t next_vblank;

static void send_input(void) {
    if (absolute_time_diff_us(next_vblank, get_absolute_time()) < 0) return;
    next_vblank = delayed_by_us(next_vblank, 16639);     // NTSC の 1 フレーム(約 60.1 回/秒)
    uint8_t pkt[20] = {'F', 'C', 'I', 'N', 0};
    memset(pkt + 5, 0xFF, 9);                             // キーボード 9 行: 押していない
    pkt[14] = frames_rx & 0xFF;
    pkt[15] = frames_rx >> 8;
    pkt[19] = ++vframe;
    stdio_put_string((const char *)pkt, sizeof pkt, false, false);
}

int main(void) {
    gpio_init(PIN_LED);
    gpio_set_dir(PIN_LED, GPIO_OUT);
    vreg_set_voltage(VREG_VOLTAGE_1_20);                  // magicon と同じクロック
    sleep_ms(10);
    set_sys_clock_khz(250000, true);
    stdio_init_all();
    next_vblank = get_absolute_time();

    uint32_t match = 0;
    uint8_t c;
    for (;;) {
        send_input();
        if (read_exact(&c, 1, 1) != 1) continue;
        match = (match << 8) | c;
        if (match != ('F' << 24 | 'C' << 16 | 'F' << 8 | 'R')) continue;
        match = 0;
        if (read_exact(back, sizeof back, 500) != (int)sizeof back) continue;
        if (read_exact(meta, sizeof meta, 500) != (int)sizeof meta) continue;
        frames_rx++;
        gpio_xor_mask64(1ull << PIN_LED);
    }
}
