// FC-MAGICON magicon — フラッシュに書いた .nes / .nsf をファミコンで動かす(マジコン本体 + NSF プレイヤー)
//
//   ・ROM はフラッシュの 8MB 目(ROM_SLOT)に load_rom.ps1 で書く。形式は tools/nes_pack.py の
//     「"FCMG" + 長さ + 合計 + 予備(各4バイト)」の後ろに .nes をそのまま
//   ・起動したら ROM を SRAM へ写し(PRG + CHR 384KB まで)、本体の 5V を待ってからバスに出る
//   ・ROM が無い・壊れている・対応していない時は、chr_test と同じ試験画面(4色の縦縞 + 格子、音)を出す
//   ・USB シリアルに、読み込んだ ROM の情報と、1 秒ごとの CPU サイクル・PPU 読み出し・書き込みの回数を出す
//   ・MAGICON_USB_HOST = 1 でビルドすると magicon_wifi になる: 画面転送モードの USB を「ホスト」にして、
//     J6 につないだ ESP32-C6(firmware/wifi_bridge、USB Serial/JTAG = CDC)とやりとりする(PC とは Wi-Fi 越し)。
//     この時は USB シリアル(printf)も picotool の自動書き込みモードも無い。TinyUSB 0.21 が要る(build.ps1)
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/clocks.h"
#include "hardware/vreg.h"
#include "hardware/structs/sio.h"
#include "hardware/watchdog.h"
#include "cart.h"
#include "audio.h"
#if MAGICON_USB_HOST
#include "tusb.h"
#endif

#define PIN_LED        39
// LED は SIO のレジスターを直接たたく(RP2350 の gpio_xor_mask64 / gpio_put は GPIO コプロセッサー命令になり、
// host_test ではそれで NOCP の HardFault が起きた。magicon では起きていないが、同じ書き方にそろえておく)
#define LED_TOGGLE()   (sio_hw->gpio_hi_togl = 1u << (PIN_LED - 32))
#define LED_ON()       (sio_hw->gpio_hi_set = 1u << (PIN_LED - 32))
#define PIN_CIRAM_A10  43
#define PIN_AUDIO      44               // PWM → RC → VR1 → R8 → カセット端子 46 番(本体の音声に混ぜる)
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

// ---- ゲーム選択メニュー ----
// メニューで選ぶと、番号をウォッチドッグのメモ(scratch[0]、再起動しても消えない。電源が切れると消える)に残して
// 再起動し、次の起動でその ROM を読み込む。本体側はその間、本体 RAM のプログラムで 1.5 秒待っている(gen_menu_driver.py)
#define PICK_MAGIC     0xFC010000u
#define LIB_SPACE      0x00800000u      // ライブラリに使える大きさ(8MB 目からフラッシュの終わりまで)

static void reboot_with_pick(uint32_t pick) {
    watchdog_hw->scratch[0] = pick;
    watchdog_reboot(0, 0, 0);
    for (;;) tight_loop_contents();
}

// 本体の電源が切れたら(5V が 50ms 続けて無い)再起動する: 次に電源を入れた時はメニューから
static void check_power(void) {
    static bool low;
    static absolute_time_t since;
    if (gpio_get(PIN_FC_5V)) {
        low = false;
        return;
    }
    if (!low) {
        low = true;
        since = get_absolute_time();
    } else if (absolute_time_diff_us(since, get_absolute_time()) > 50000) {
        reboot_with_pick(0);
    }
}

static const char *load_entry(const lib_entry_t *e, cart_info_t *info) {
    if (e->offset > LIB_SPACE || e->len > LIB_SPACE - e->offset || e->len < 4)
        return "bad library entry";
    const uint8_t *p = (const uint8_t *)(XIP_BASE + ROM_SLOT + e->offset);
    uint32_t sum = 0;
    for (uint32_t i = 0; i < e->len; i++)
        sum += p[i];
    if (sum != e->sum)
        return "checksum mismatch in library (write it again)";
    return cart_load(p, e->len, info);
}

static const char *load_library(cart_info_t *info) {
    const lib_header_t *lh = (const lib_header_t *)(XIP_BASE + ROM_SLOT);
    const lib_entry_t *e = (const lib_entry_t *)(lh + 1);
    if (lh->count == 0 || lh->count > LIB_MAX_ITEMS)
        return "bad library header";
    uint32_t pick = watchdog_hw->scratch[0];
    watchdog_hw->scratch[0] = 0;
    if ((pick & 0xFFFF0000u) == PICK_MAGIC && (pick & 0xFFFF) < lh->count)
        return load_entry(&e[pick & 0xFFFF], info);
    if (lh->count == 1)
        return load_entry(&e[0], info);
    cart_load_menu(e, (int)lh->count, info);
    return NULL;
}

static const char *load_from_flash(cart_info_t *info) {
    const slot_header_t *h = (const slot_header_t *)(XIP_BASE + ROM_SLOT);
    const uint8_t *nes = (const uint8_t *)(h + 1);
    if (memcmp(h->magic, "FCLB", 4) == 0)
        return load_library(info);
    if (memcmp(h->magic, "FCMG", 4) != 0)
        return "no ROM in flash (write one with load_rom.ps1)";
    if (h->len < 4 || h->len > 4u * 1024 * 1024)        // 4 = 画面転送モードの印 "FCRD"
        return "bad length in flash header";
    uint32_t sum = 0;
    for (uint32_t i = 0; i < h->len; i++)
        sum += nes[i];
    if (sum != h->sum)
        return "checksum mismatch (write the ROM again)";
    return cart_load(nes, h->len, info);
}

// ---- 画面転送モードの USB のやりとり(コア0) ----
//   PC → カセット: "FCFR" + 絵 15360 + パレット 32 + 属性 64 + カーソル x, y, visible(3)
//                  絵は裏の画面へ直接読み込む。表示待ちの 1 枚がある間は読まない(PC 側がそこで待たされる)
//                  "FCAU" + 形式 1(0 = 16 ビット PCM、1 = IMA ADPCM)+ サンプル数 2(LE)+ 中身 = PC の音(32kHz モノラル)
//   カセット → PC: "FCIN" + パッド 1 + キーボード 9 行 + 予備 5 + 6502 のフレームの数 1(= 16)
//                  6502 のフレームの数が変わるたびに(約 60 回/秒)
//   通り道は USB シリアル(magicon、PC 直結)か、USB ホストで開いた C6 の CDC(magicon_wifi)
#if MAGICON_USB_HOST
static uint8_t cdc = 0xFF;              // 開いている C6 の CDC の番号(0xFF = まだ)

void tuh_cdc_mount_cb(uint8_t idx) { cdc = idx; }
void tuh_cdc_umount_cb(uint8_t idx) { if (idx == cdc) cdc = 0xFF; }
uint32_t tusb_time_millis_api(void) { return to_ms_since_boot(get_absolute_time()); }   // OS 無しの TinyUSB の時計

static void usb_poll(void) { tuh_task(); }

static int read_exact(uint8_t *buf, int len, uint32_t timeout_ms) {
    int got = 0;
    absolute_time_t until = make_timeout_time_ms(timeout_ms);
    while (got < len) {
        tuh_task();
        if (cdc != 0xFF) {
            uint32_t n = tuh_cdc_read(cdc, buf + got, (uint32_t)(len - got));
            got += (int)n;
            if (n) continue;
        }
        if (time_reached(until)) break;
    }
    return got;
}

static void write_packet(const uint8_t *p, int len) {
    // 入り切らない時は捨てる(次のフレームでまた送る)
    if (cdc == 0xFF || tuh_cdc_write_available(cdc) < (uint32_t)len) return;
    tuh_cdc_write(cdc, p, (uint32_t)len);
    tuh_cdc_write_flush(cdc);
}
#else
static void usb_poll(void) {}

static int read_exact(uint8_t *buf, int len, uint32_t timeout_ms) {
    int got = 0;
    absolute_time_t until = make_timeout_time_ms(timeout_ms);
    while (got < len) {
        int n = stdio_get_until((char *)buf + got, len - got, until);
        if (n <= 0) return got;         // PICO_ERROR_TIMEOUT
        got += n;
    }
    return got;
}

static void write_packet(const uint8_t *p, int len) {
    stdio_put_string((const char *)p, len, false, false);
}
#endif

static void send_input(uint8_t *last_frame) {
    uint8_t io[16];
    cart_remote_io(io);
    if (io[15] == *last_frame) return;
    *last_frame = io[15];
    uint8_t pkt[20] = {'F', 'C', 'I', 'N'};
    memcpy(pkt + 4, io, 16);
    write_packet(pkt, sizeof pkt);
}

static void __attribute__((noreturn)) remote_loop(void) {
    static uint8_t meta[32 + 64 + 3];
    static uint8_t au[2 * AUDIO_MAX_SAMPLES];
    uint8_t last_frame = 0, c;
    uint32_t match = 0;
    for (;;) {
        send_input(&last_frame);
        audio_poll();
        check_power();
        // "FCFR" / "FCAU" を探す(途中から読み始めても合うように 1 バイトずつ)
        if (read_exact(&c, 1, 1) != 1) continue;
        match = (match << 8) | c;
        if (match == ('F' << 24 | 'C' << 16 | 'A' << 8 | 'U')) {
            match = 0;
            uint8_t h[3];
            if (read_exact(h, 3, 100) != 3) continue;
            uint16_t n = (uint16_t)(h[1] | h[2] << 8);
            int len = audio_payload_len(h[0], n);
            if (len < 0 || read_exact(au, len, 100) != len) continue;
            audio_push(h[0], n, au);
            continue;
        }
        if (match != ('F' << 24 | 'C' << 16 | 'F' << 8 | 'R')) continue;
        match = 0;
        uint8_t *back;
        while (!(back = cart_remote_back())) {           // 前の 1 枚がまだ表示されていない
            send_input(&last_frame);
            audio_poll();
            usb_poll();
            sleep_us(200);
        }
        if (read_exact(back, 15360, 500) != 15360) continue;
        if (read_exact(meta, sizeof meta, 500) != (int)sizeof meta) continue;
        cart_remote_commit(meta, meta + 32, meta[96], meta[97], meta[98]);
        LED_TOGGLE();                                     // 1 枚ごとに LED を反転
    }
}

int main(void) {
    bus_pins_input();
    gpio_init(PIN_LED);
    gpio_set_dir(PIN_LED, GPIO_OUT);

    vreg_set_voltage(VREG_VOLTAGE_1_20);
    sleep_ms(10);
    set_sys_clock_khz(250000, true);
#if MAGICON_USB_HOST
    const tusb_rhport_init_t rh = {.role = TUSB_ROLE_HOST, .speed = TUSB_SPEED_AUTO};
    tusb_rhport_init(0, &rh);           // J6 の C6 を待つ(つながるまでの手続きは usb_poll = tuh_task で進む)
#else
    stdio_init_all();
#endif

    // 本体がリセットを解く前にバスへ出られるよう、ROM の読み込みは 5V を待つ前に済ませる
    cart_info_t info;
    const char *err = load_from_flash(&info);
    if (err)
        cart_load_fallback(&info);

    while (!gpio_get(PIN_FC_5V)) {      // 本体の電源が入るまでバスへ出さない(USB だけの時に逆流させない)
        LED_TOGGLE();
        for (int i = 0; i < 100; i++) {
            usb_poll();
            sleep_ms(1);
        }
        printf("waiting for Famicom 5V (GPIO46)...  ROM: %s\n", err ? err : "ok");
    }
    LED_ON();
    cart_start();
    if (!err && info.is_remote) {
        audio_init(PIN_AUDIO);          // PC の音(無音から鳴らし始める)
        remote_loop();                  // 戻らない
    }

    uint32_t lc = 0, lp = 0, lw = 0;
    for (;;) {
        for (int i = 0; i < 1000; i++) {
            usb_poll();
            check_power();
            if (info.is_menu && cart_menu_choice() >= 0)
                reboot_with_pick(PICK_MAGIC | (uint32_t)cart_menu_choice());   // 選ばれた ROM で起動し直す
            sleep_ms(1);
        }
        uint32_t c = stat_cpu, p = stat_ppu, w = stat_wr;
        if (err)
            printf("[test screen] %s | ", err);
        else if (info.is_menu)
            printf("[game select menu] ");
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


