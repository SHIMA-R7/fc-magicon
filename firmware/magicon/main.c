// FC-MAGICON magicon — フラッシュに書いた .nes / .nsf をファミコンで動かす(マジコン本体 + NSF プレイヤー)
//
//   ・ROM はフラッシュの 8MB 目(ROM_SLOT)に load_rom.ps1 で書く。形式は tools/nes_pack.py の
//     「"FCMG" + 長さ + 合計 + 予備(各4バイト)」の後ろに .nes をそのまま
//   ・起動したら ROM を SRAM へ写し(PRG + CHR 384KB まで)、本体の 5V を待ってからバスに出る
//   ・ROM が無い・壊れている・対応していない時は、chr_test と同じ試験画面(4色の縦縞 + 格子、音)を出す
//   ・USB シリアルに、読み込んだ ROM の情報と、1 秒ごとの CPU サイクル・PPU 読み出し・書き込みの回数を出す
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/clocks.h"
#include "hardware/vreg.h"
#include "cart.h"

#define PIN_LED        39
#define PIN_CIRAM_A10  43
#define PIN_FC_5V      46
#define BUS_PIN_LAST   42
#define ROM_SLOT       0x00800000u      // フラッシュ先頭から 8MB(ファームウェアとは重ならない)

typedef struct {
    char magic[4];                      // "FCMG"
    uint32_t len;                       // .nes の長さ
    uint32_t sum;                       // .nes のバイトの合計
    uint32_t reserved;
} slot_header_t;

static void bus_pins_input(void) {
    for (uint p = 0; p <= 46; p++) {    // GPIO47 は PSRAM の CS なので触らない
        if (p == PIN_LED)
            continue;
        gpio_init(p);
        gpio_set_dir(p, GPIO_IN);
        gpio_disable_pulls(p);          // RP2350 エラッタ E9: バスのピンでプルダウンを使わない
    }
}

static const char *load_from_flash(cart_info_t *info) {
    const slot_header_t *h = (const slot_header_t *)(XIP_BASE + ROM_SLOT);
    const uint8_t *nes = (const uint8_t *)(h + 1);
    if (memcmp(h->magic, "FCMG", 4) != 0)
        return "no ROM in flash (write one with load_rom.ps1)";
    if (h->len < 16 || h->len > 4u * 1024 * 1024)
        return "bad length in flash header";
    uint32_t sum = 0;
    for (uint32_t i = 0; i < h->len; i++)
        sum += nes[i];
    if (sum != h->sum)
        return "checksum mismatch (write the ROM again)";
    return cart_load(nes, h->len, info);
}

int main(void) {
    bus_pins_input();
    gpio_init(PIN_LED);
    gpio_set_dir(PIN_LED, GPIO_OUT);

    vreg_set_voltage(VREG_VOLTAGE_1_20);
    sleep_ms(10);
    set_sys_clock_khz(250000, true);
    stdio_init_all();

    // 本体がリセットを解く前にバスへ出られるよう、ROM の読み込みは 5V を待つ前に済ませる
    cart_info_t info;
    const char *err = load_from_flash(&info);
    if (err)
        cart_load_fallback(&info);

    while (!gpio_get(PIN_FC_5V)) {      // 本体の電源が入るまでバスへ出さない(USB だけの時に逆流させない)
        gpio_xor_mask64(1ull << PIN_LED);
        sleep_ms(100);
        printf("waiting for Famicom 5V (GPIO46)...  ROM: %s\n", err ? err : "ok");
    }
    gpio_put(PIN_LED, 1);
    cart_start();

    uint32_t lc = 0, lp = 0, lw = 0;
    for (;;) {
        sleep_ms(1000);
        uint32_t c = stat_cpu, p = stat_ppu, w = stat_wr;
        if (err)
            printf("[test screen] %s | ", err);
        else if (info.is_nsf)
            printf("[NSF \"%s\" / %s  %d songs  load $%04X init $%04X play $%04X%s%s] ", info.nsf_title, info.nsf_artist,
                   info.nsf_songs, info.nsf_load, info.nsf_init, info.nsf_play, info.nsf_banked ? "  banked" : "",
                   info.nsf_exp ? "  (expansion audio not played yet)" : "");
        else
            printf("[mapper %d %s  PRG %luK  CHR %s%luK  %s%s] ", info.mapper, cart_mapper_name(info.mapper),
                   (unsigned long)(info.prg_size / 1024), info.chr_size ? "" : "RAM ",
                   (unsigned long)((info.chr_size ? info.chr_size : 0x2000) / 1024),
                   info.vertical ? "V" : "H", info.battery ? " battery" : "");
        printf("cpu %lu/s  ppu %lu/s  writes %lu/s\n", (unsigned long)(c - lc), (unsigned long)(p - lp),
               (unsigned long)(w - lw));
        lc = c; lp = p; lw = w;
    }
}


