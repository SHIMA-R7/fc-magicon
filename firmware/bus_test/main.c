// FC-MAGICON bus_test — 基板が届いて最初に試すファームウェア
//
//   ・CPU バスの $8000-$FFFF に、小さなテスト ROM(test_rom.h)を返す
//   ・テスト ROM は矩形波 1ch で 440Hz を鳴らし続け、ループのたびに $8000 へ書き込む
//   ・RP2350B はその書き込みを数え、65536 回ごとにモジュールの LED(GPIO39)を反転する(約0.5秒ごと)
//   ・USB(FPC アダプター)のシリアルに、1 秒ごとに読み出し・書き込みの回数を出す
//
// 安全のため、起動直後はバスのピンを全部入力(プル無し)にし、
// 本体の 5V(GPIO46、R2/R3 の分圧)を確認するまで PIO を動かさない。
#include <stdio.h>
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "hardware/pio.h"
#include "hardware/clocks.h"
#include "hardware/vreg.h"
#include "cpu_bus.pio.h"
#include "test_rom.h"

#define PIN_ROMSEL    23
#define PIN_RW        24
#define PIN_M2        25
#define PIN_LED       39
#define PIN_FC_5V     46
#define BUS_PIN_LAST  42      // GPIO0-38 はバス、40-42 は U2 経由。いずれも入力で待つ

static volatile uint32_t n_read, n_write;
static uint8_t rom[0x8000];

// コア1: PIO が読んだアドレスに答えるだけのループ(割り込みなし)
static void __not_in_flash_func(cpu_bus_loop)(void) {
    PIO pio = pio0;
    const uint sm = 0;
    uint32_t writes = 0;
    for (;;) {
        uint32_t v = pio_sm_get_blocking(pio, sm);
        uint32_t addr = (v >> 8) & 0x7FFF;
        if (v & (1u << PIN_RW)) {                    // 読み出し: データを出す
            pio_sm_put(pio, sm, 0xFF00u | rom[addr]);
            n_read++;
        } else {                                     // 書き込み: 出さない
            pio_sm_put(pio, sm, 0);
            n_write++;
            if ((++writes & 0xFFFF) == 0)            // 1ループ約15サイクル → 約0.5秒ごとに反転
                gpio_xor_mask64(1ull << PIN_LED);
        }
    }
}

static void bus_pins_input(void) {
    for (uint p = 0; p <= BUS_PIN_LAST; p++) {
        if (p == PIN_LED) continue;
        gpio_init(p);
        gpio_set_dir(p, GPIO_IN);
        gpio_disable_pulls(p);                       // RP2350 エラッタ E9: 内部プルダウンを使わない
    }
    gpio_init(PIN_FC_5V);
    gpio_set_dir(PIN_FC_5V, GPIO_IN);
    gpio_disable_pulls(PIN_FC_5V);
}

int main(void) {
    bus_pins_input();
    gpio_init(PIN_LED);
    gpio_set_dir(PIN_LED, GPIO_OUT);

    vreg_set_voltage(VREG_VOLTAGE_1_20);             // 250MHz で回すため少し電圧を上げる
    sleep_ms(10);
    set_sys_clock_khz(250000, true);
    stdio_init_all();

    // 本体の電源が入るまで待つ(USB だけの時にバスへ出力しない)
    while (!gpio_get(PIN_FC_5V)) {
        gpio_xor_mask64(1ull << PIN_LED);
        sleep_ms(100);
        printf("waiting for Famicom 5V (GPIO46)...\n");
    }
    gpio_put(PIN_LED, 0);

    for (uint i = 0; i < sizeof rom; i++)            // 16KB/32KB どちらのイメージでも 32KB に広げる
        rom[i] = test_rom[i % sizeof test_rom];

    pio_set_gpio_base(pio0, 0);                      // CPU 用ブロックは GPIO0-31
    uint offset = pio_add_program(pio0, &cpu_bus_program);
    cpu_bus_program_init(pio0, 0, offset);
    multicore_launch_core1(cpu_bus_loop);

    printf("FC-MAGICON bus_test: serving test ROM at 250MHz\n");
    uint32_t last_r = 0, last_w = 0;
    for (;;) {
        sleep_ms(1000);
        uint32_t r = n_read, w = n_write;
        printf("reads/s %lu  writes/s %lu  5V %d\n", (unsigned long)(r - last_r), (unsigned long)(w - last_w),
               gpio_get(PIN_FC_5V));
        last_r = r;
        last_w = w;
    }
}
