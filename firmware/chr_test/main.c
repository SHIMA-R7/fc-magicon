// FC-MAGICON chr_test — PPU 側(CHR)の応答を確かめるファームウェア
//
//   ・CPU バス: テスト ROM(chr_rom.h)を返す。ROM はパレットとネームテーブルを書いて背景を表示し、音を鳴らす
//   ・PPU バス: パターンテーブル $0000-$1FFF の読み出しに、ここで作った CHR を返す
//       タイル t = 下位2ビットの色で塗り、上辺(1行目)と左端(1列目)は色1の格子線
//       → 画面に「4色の縦縞 + 8ドットごとの格子」が出れば、/RD 直前に AD0-7 から読む下位アドレスは正しい
//   ・CIRAM A10(GPIO43)は Low に固定(JP1 を閉じた場合は1画面ミラー。JP2/JP3 の場合は関係ない)
//
// 応答はコア1が CPU と PPU の両方の FIFO を見て返す(割り込みなし)。PPU を優先する。
// USB シリアルに 1 秒ごとの CPU・PPU の読み出し回数を出す(PPU は表示中およそ 530 万回/秒の見込み)。
#include <stdio.h>
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "hardware/pio.h"
#include "hardware/clocks.h"
#include "hardware/vreg.h"
#include "cpu_bus.pio.h"
#include "ppu_chr.pio.h"
#include "chr_rom.h"

#define PIN_RW        24
#define PIN_LED       39
#define PIN_CIRAM_A10 43
#define PIN_FC_5V     46
#define BUS_PIN_LAST  42

static volatile uint32_t n_cpu, n_ppu, n_ppu_nt;
static uint8_t prg[0x8000];
static uint8_t chr[0x2000];

static void __not_in_flash_func(bus_loop)(void) {
    PIO cpu = pio0, ppu = pio1;
    uint32_t writes = 0;
    for (;;) {
        if (!pio_sm_is_rx_fifo_empty(ppu, 0)) {              // PPU を先に(こちらの方が速い)
            uint32_t v = ppu->rxf[0];
            if (v & (1u << 16)) {                            // A13 = 1: ネームテーブル(本体の VRAM が出す)
                ppu->txf[0] = 0;
                n_ppu_nt++;
            } else {
                ppu->txf[0] = 0xFF00u | chr[v & 0x1FFF];     // AD0-7 + A8-12 = 13 ビットのアドレス
                n_ppu++;
            }
        }
        if (!pio_sm_is_rx_fifo_empty(cpu, 0)) {
            uint32_t v = cpu->rxf[0];
            if (v & (1u << PIN_RW)) {
                cpu->txf[0] = 0xFF00u | prg[(v >> 8) & 0x7FFF];
                n_cpu++;
            } else {
                cpu->txf[0] = 0;
                if ((++writes & 0xFFFF) == 0)
                    gpio_xor_mask64(1ull << PIN_LED);
            }
        }
    }
}

static void make_chr(void) {
    for (uint t = 0; t < 256; t++) {
        for (uint r = 0; r < 8; r++) {
            uint8_t p0 = (t & 1) ? 0xFF : 0x00;
            uint8_t p1 = (t & 2) ? 0xFF : 0x00;
            if (r == 0) { p0 = 0xFF; p1 = 0x00; }             // 上辺は色1
            else { p0 |= 0x80; p1 &= 0x7F; }                 // 左端も色1
            chr[t * 16 + r] = p0;                             // パターンテーブル 0
            chr[t * 16 + 8 + r] = p1;
        }
    }
    for (uint i = 0; i < 0x1000; i++)
        chr[0x1000 + i] = chr[i];                             // パターンテーブル 1 も同じ
}

static void bus_pins_input(void) {
    for (uint p = 0; p <= BUS_PIN_LAST; p++) {
        if (p == PIN_LED) continue;
        gpio_init(p);
        gpio_set_dir(p, GPIO_IN);
        gpio_disable_pulls(p);                                // RP2350 エラッタ E9
    }
    for (uint p = PIN_CIRAM_A10; p <= PIN_FC_5V; p++) {
        gpio_init(p);
        gpio_set_dir(p, GPIO_IN);
        gpio_disable_pulls(p);
    }
}

int main(void) {
    bus_pins_input();
    gpio_init(PIN_LED);
    gpio_set_dir(PIN_LED, GPIO_OUT);

    vreg_set_voltage(VREG_VOLTAGE_1_20);
    sleep_ms(10);
    set_sys_clock_khz(250000, true);
    stdio_init_all();

    while (!gpio_get(PIN_FC_5V)) {                           // 本体の電源が入るまでバスへ出さない
        gpio_xor_mask64(1ull << PIN_LED);
        sleep_ms(100);
        printf("waiting for Famicom 5V (GPIO46)...\n");
    }
    gpio_put(PIN_LED, 0);
    gpio_put(PIN_CIRAM_A10, 0);
    gpio_set_dir(PIN_CIRAM_A10, GPIO_OUT);                   // 1画面ミラー(JP1 を閉じた時だけ効く)

    for (uint i = 0; i < sizeof prg; i++)
        prg[i] = chr_test_rom[i % sizeof chr_test_rom];
    make_chr();

    pio_set_gpio_base(pio0, 0);                              // CPU: GPIO0-31
    pio_set_gpio_base(pio1, 16);                             // PPU: GPIO16-47
    ppu_chr_program_init(pio1, 0, pio_add_program(pio1, &ppu_chr_program));
    cpu_bus_program_init(pio0, 0, pio_add_program(pio0, &cpu_bus_program));
    multicore_launch_core1(bus_loop);

    printf("FC-MAGICON chr_test: CPU+PPU at 250MHz\n");
    uint32_t lc = 0, lp = 0, ln = 0;
    for (;;) {
        sleep_ms(1000);
        uint32_t c = n_cpu, p = n_ppu, n = n_ppu_nt;
        printf("cpu reads/s %lu  ppu chr/s %lu  ppu nt/s %lu\n",
               (unsigned long)(c - lc), (unsigned long)(p - lp), (unsigned long)(n - ln));
        lc = c; lp = p; ln = n;
    }
}
