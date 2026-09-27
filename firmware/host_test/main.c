// host_test: RP2350 の USB をホストにして、ESP32-C6(Wi-Fi ブリッジ)から画面転送のデータを受け取る試験。ファミコン無しで動く。
//   PC ──Wi-Fi── C6(wifi_bridge)──USB── RP2350(ここ。USB ホスト)
//   受け取り方と返す物は usb_test と同じ: "FCFR" + 15459 バイトを数えて捨て、"FCIN" を 60 回/秒返す
//   (パッド 0、キーボードは全部「押していない」= 0xFF。予備の 5 バイトに試験の結果を入れる)。
//   PC に USB でつながらないので、結果は Wi-Fi 越しに FCIN で見る(tools/host_bench.py)。
//     FCIN の 16 バイトの中身: [0] パッド [1-9] キーボード [10-11] 受け取った枚数 [12-13] 欠け・余りのあった数
//                              [14] C6 を見つけた回数 [15] フレームの数
//   配線: Core2350B2 の P2 の 7 番(USB D-)→ C6 の GPIO12、9 番(USB D+)→ C6 の GPIO13、GND どうし。
//   LED: C6 を見つけたら点灯、1 枚受け取るごとに反転。
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/vreg.h"
#include "hardware/clocks.h"
#include "tusb.h"

#define PIN_LED 39
// LED は SIO のレジスターを直接たたく(gpio_xor_mask64 / gpio_put は RP2350 では GPIO コプロセッサー命令になり、
// host_test ではその許可が無く NOCP の HardFault で止まった。2026-09-27、SWD で確認)
#define LED_TOGGLE() (sio_hw->gpio_hi_togl = 1u << (PIN_LED - 32))
#define LED_SET(on)  ((on) ? (sio_hw->gpio_hi_set = 1u << (PIN_LED - 32)) : (sio_hw->gpio_hi_clr = 1u << (PIN_LED - 32)))
#define BODY (15360 + 32 + 64 + 3)

static uint8_t cdc = 0xFF;                  // 開いている CDC の番号(0xFF = まだ)
static uint16_t frames_rx, bad;
static uint8_t mounts, vframe;
static absolute_time_t next_vblank;

// ---- 受け取ったバイトを画面パケットに区切る ----
static uint32_t match;
static int remain;                          // 今の 1 枚の残り(0 = "FCFR" を探している)
static int skipped;                         // 1 枚の終わりから次の "FCFR" までに余計に来たバイト
static bool started;                        // 1 枚目を受け取った(それより前の C6 の案内の文字は数えない)

static void parse(const uint8_t *p, int n) {
    while (n) {
        if (remain) {
            int k = n < remain ? n : remain;
            remain -= k;
            p += k;
            n -= k;
            if (!remain) {
                frames_rx++;
                LED_TOGGLE();
            }
            continue;
        }
        match = (match << 8) | *p++;
        n--;
        skipped++;
        if (match == ('F' << 24 | 'C' << 16 | 'F' << 8 | 'R')) {
            if (started && skipped != 4)    // 前の 1 枚のすぐ後に "FCFR" が来なかった = バイトが欠けたか余った
                bad++;
            started = true;
            match = 0;
            skipped = 0;
            remain = BODY;
        }
    }
}

static void send_input(void) {
    if (cdc == 0xFF || absolute_time_diff_us(next_vblank, get_absolute_time()) < 0) return;
    next_vblank = delayed_by_us(next_vblank, 16639);
    if (absolute_time_diff_us(next_vblank, get_absolute_time()) > 0)
        next_vblank = get_absolute_time();
    if (tuh_cdc_write_available(cdc) < 20) return;
    uint8_t pkt[20] = {'F', 'C', 'I', 'N', 0};
    memset(pkt + 5, 0xFF, 9);
    pkt[14] = frames_rx & 0xFF;
    pkt[15] = frames_rx >> 8;
    pkt[16] = bad & 0xFF;
    pkt[17] = bad >> 8;
    pkt[18] = mounts;
    pkt[19] = ++vframe;
    tuh_cdc_write(cdc, pkt, sizeof pkt);
    tuh_cdc_write_flush(cdc);
}

// OS 無しの TinyUSB が使う時計(ms)
uint32_t tusb_time_millis_api(void) {
    return to_ms_since_boot(get_absolute_time());
}

void tuh_cdc_mount_cb(uint8_t idx) {
    cdc = idx;
    mounts++;
    remain = 0;
    match = 0;
    started = false;
    LED_SET(1);
}

void tuh_cdc_umount_cb(uint8_t idx) {
    if (idx == cdc) cdc = 0xFF;
    LED_SET(0);
}

int main(void) {
    gpio_init(PIN_LED);
    sio_hw->gpio_hi_oe_set = 1u << (PIN_LED - 32);
    vreg_set_voltage(VREG_VOLTAGE_1_20);    // magicon と同じクロック
    sleep_ms(10);
    set_sys_clock_khz(250000, true);
    stdio_uart_init_full(uart0, 115200, 0, -1);   // printf を UART0 の TX = GPIO0 へ(ボードの定義に標準の UART ピンが無いので自分で決める)
    printf("\n[host_test] start\n");
    const tusb_rhport_init_t rh = {.role = TUSB_ROLE_HOST, .speed = TUSB_SPEED_AUTO};
    tusb_rhport_init(BOARD_TUH_RHPORT, &rh);
    next_vblank = get_absolute_time();

    static uint8_t buf[1024];
    absolute_time_t next_report = get_absolute_time();
    for (;;) {
        tuh_task();
        if (absolute_time_diff_us(next_report, get_absolute_time()) >= 0) {   // 1 秒ごとの様子(UART)
            next_report = delayed_by_ms(next_report, 1000);
            printf("[host_test] cdc=%d mounts=%u frames=%u bad=%u tx_avail=%lu rx_avail=%lu\n", cdc == 0xFF ? -1 : cdc,
                   mounts, frames_rx, bad, cdc == 0xFF ? 0ul : (unsigned long)tuh_cdc_write_available(cdc),
                   cdc == 0xFF ? 0ul : (unsigned long)tuh_cdc_read_available(cdc));
        }
        if (cdc != 0xFF) {
            uint32_t n;
            while ((n = tuh_cdc_read(cdc, buf, sizeof buf)) > 0)
                parse(buf, (int)n);
            send_input();
        }
    }
}
