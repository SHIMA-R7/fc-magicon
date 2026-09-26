// FC-MAGICON magicon: カセットの中身(ROM・マッパー)とバスの応答
//
// .nsf の時は NSF プレイヤーになる(下の「NSF」。ドライバーは gen_nsf_driver.py)。
//
// バスの応答はコア1の1本のループ(割り込みなし、SRAM で実行)。
//   PIO0 SM0(cpu_m2.pio) : CPU の全サイクル。$8000-$FFFF = PRG、$6000-$7FFF = WRAM、書き込みはマッパーへ
//   PIO1 SM0(ppu_chr.pio): PPU の /RD。$0000-$1FFF = CHR(A13 = 1 のネームテーブルは本体の VRAM が出す)
//   PIO2 SM0(mirror.pio) : CIRAM A10 に PPU A10 / A11 を写す(ミラーリング)
// 読み出しは「8KB(PRG)/ 1KB(CHR)ごとのポインターの表」を引くだけにして、マッパーの計算は書き込みの時だけする。
//
// CHR-RAM: PPU の書き込み(/WR)の時は AD0-7 がデータになっていてアドレスが読めないので、
//   CPU が $2006(アドレス)・$2007(データ)に書く値を横から読み、同じ所へ書き込む。$2000 の +1/+32 と、
//   $2002 の読み出し・$2005 の書き込みで切り替わる「2回目か」のフラグも真似する。
#include <string.h>
#ifdef CART_HOST                        // PC の試験台(firmware/sim)でビルドする時
#include "host_pico.h"
#else
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "hardware/pio.h"
#include "cpu_m2.pio.h"
#include "ppu_chr.pio.h"
#include "mirror.pio.h"
#endif
#include "cart.h"
#include "chr_rom.h"                    // 試験画面の PRG(chr_test と同じもの)
#include "remote_driver.h"              // 画面転送モードの 6502 プログラムとカーソル(gen_remote_driver.py)
#include "nsf_driver.h"                 // NSF プレイヤーのドライバー($5000-)・画面の土台・CHR(gen_nsf_driver.py)

#define PIN_IRQ     45                  // High で Q1 が /IRQ を Low にする
#define B_ROMSEL    (1u << 23)
#define B_RW        (1u << 24)
#define B_PPU_A13   (1u << 16)

volatile uint32_t stat_cpu, stat_ppu, stat_wr;

static uint8_t rom[ROM_MAX];            // PRG の後ろに CHR
static uint8_t chr_ram[0x2000];
static uint8_t wram[0x2000];

static uint8_t *prg, *chr;
static uint32_t prg_size, chr_size;     // chr_size は CHR-RAM の時 0x2000
static bool chr_is_ram;
static int mapper;
static bool is_remote;                  // 画面転送モード(下の「画面転送」)

static uint8_t *prg_map[4];             // $8000 / $A000 / $C000 / $E000 の 8KB
static uint8_t *chr_map[8];             // $0000〜$1FFF の 1KB ずつ

enum { MIR_H, MIR_V, MIR_0, MIR_1 };
static int mir = -1;
#ifndef CART_HOST
static uint mirror_offset;
#endif
static bool mirror_ready;               // PIO2 を設定するまでは、決めたミラーリングを覚えておくだけ

// ---- バンクの切り替え(書き込みの時だけ呼ぶので % を使ってよい) ----
static void __not_in_flash_func(prg8)(uint slot, uint bank) {
    prg_map[slot] = prg + (bank % (prg_size / 0x2000)) * 0x2000;
}
static inline uint n8(void) { return prg_size / 0x2000; }          // PRG の 8KB バンクの数
static inline uint n16(void) { return prg_size / 0x4000; }
static void __not_in_flash_func(prg16)(uint slot, uint bank) {    // slot 0 = $8000、1 = $C000(8KB 単位の % で丸まる)
    prg8(slot * 2, bank * 2);
    prg8(slot * 2 + 1, bank * 2 + 1);
}
static void __not_in_flash_func(prg32)(uint bank) {
    prg16(0, bank * 2);
    prg16(1, bank * 2 + 1);
}
static void __not_in_flash_func(chr1)(uint slot, uint bank) {
    chr_map[slot] = chr + (bank % (chr_size / 0x400)) * 0x400;
}
static void __not_in_flash_func(chr4)(uint slot, uint bank) {     // slot 0 = $0000、1 = $1000
    for (uint i = 0; i < 4; i++)
        chr1(slot * 4 + i, bank * 4 + i);
}
static void __not_in_flash_func(chr8)(uint bank) {
    chr4(0, bank * 2);
    chr4(1, bank * 2 + 1);
}

static void __not_in_flash_func(set_mirror)(int m) {
    if (m == mir)
        return;
    mir = m;
    if (!mirror_ready)
        return;
#ifndef CART_HOST
    pio_sm_set_enabled(pio2, 0, false);
    if (m == MIR_V || m == MIR_H) {
        pio_sm_set_in_pins(pio2, 0, m == MIR_V ? 36 : 37);   // PPU A10 / A11
        pio_sm_exec(pio2, 0, pio_encode_jmp(mirror_offset));
        pio_sm_set_enabled(pio2, 0, true);
    } else {
        pio_sm_exec(pio2, 0, pio_encode_set(pio_pins, m == MIR_1));
    }
#endif
}

// ---- MMC1 ----
static uint8_t m1_shift = 0x10, m1_ctrl = 0x0C, m1_chr0, m1_chr1, m1_prg;
static uint32_t cyc, m1_last_cyc;

static void __not_in_flash_func(mmc1_update)(void) {
    static const int m[4] = {MIR_0, MIR_1, MIR_V, MIR_H};
    set_mirror(m[m1_ctrl & 3]);
    uint bank = m1_prg & 0x0F;
    switch ((m1_ctrl >> 2) & 3) {
    case 0: case 1: prg32(bank >> 1); break;
    case 2: prg16(0, 0); prg16(1, bank); break;
    case 3: prg16(0, bank); prg16(1, n16() - 1); break;
    }
    if (m1_ctrl & 0x10) { chr4(0, m1_chr0); chr4(1, m1_chr1); }
    else chr8(m1_chr0 >> 1);
}

static void __not_in_flash_func(mmc1_write)(uint addr, uint d) {
    if (cyc == m1_last_cyc + 1) {       // 連続したサイクルの書き込み(INC などの読み書き)は2回目を無視
        m1_last_cyc = cyc;
        return;
    }
    m1_last_cyc = cyc;
    if (d & 0x80) {
        m1_shift = 0x10;
        m1_ctrl |= 0x0C;
        mmc1_update();
        return;
    }
    bool full = m1_shift & 1;
    m1_shift = (m1_shift >> 1) | ((d & 1) << 4);
    if (!full)
        return;
    uint v = m1_shift;
    m1_shift = 0x10;
    switch ((addr >> 13) & 3) {
    case 0: m1_ctrl = v; break;
    case 1: m1_chr0 = v; break;
    case 2: m1_chr1 = v; break;
    case 3: m1_prg = v; break;
    }
    mmc1_update();
}

// ---- MMC3 ----
static uint8_t m3_sel, m3_r[8];
static uint8_t m3_latch, m3_count;
static bool m3_reload, m3_irq_en, is_mmc3;
static uint32_t a12_low;

static void __not_in_flash_func(mmc3_update)(void) {
    if (m3_sel & 0x40) { prg8(0, n8() - 2); prg8(2, m3_r[6]); }
    else { prg8(0, m3_r[6]); prg8(2, n8() - 2); }
    prg8(1, m3_r[7]);
    prg8(3, n8() - 1);
    uint inv = (m3_sel & 0x80) ? 4 : 0;
    chr1(0 ^ inv, m3_r[0] & 0xFE); chr1(1 ^ inv, m3_r[0] | 1);
    chr1(2 ^ inv, m3_r[1] & 0xFE); chr1(3 ^ inv, m3_r[1] | 1);
    for (uint i = 0; i < 4; i++)
        chr1((4 + i) ^ inv, m3_r[2 + i]);
}

static void __not_in_flash_func(mmc3_write)(uint addr, uint d) {
    switch (addr & 0xE001) {
    case 0x8000: m3_sel = d; mmc3_update(); break;
    case 0x8001: m3_r[m3_sel & 7] = d; mmc3_update(); break;
    case 0xA000: set_mirror((d & 1) ? MIR_H : MIR_V); break;
    case 0xA001: break;                                              // WRAM の保護(無視)
    case 0xC000: m3_latch = d; break;
    case 0xC001: m3_count = 0; m3_reload = true; break;
    case 0xE000: m3_irq_en = false; gpio_put(PIN_IRQ, 0); break;     // 無効 + 受け付け
    case 0xE001: m3_irq_en = true; break;
    }
}

// PPU A12 の立ち上がり(A12 = 0 の読み出しが 8 回以上続いた後)で数える。スプライトを $1000 に置く普通の使い方で 1 ライン 1 回
static inline void __not_in_flash_func(mmc3_clock)(void) {
    if (m3_count == 0 || m3_reload) {
        m3_count = m3_latch;
        m3_reload = false;
    } else {
        m3_count--;
    }
    if (m3_count == 0 && m3_irq_en)
        gpio_put(PIN_IRQ, 1);
}

// ---- CPU の書き込み ----
static uint16_t ppu_v, ppu_t, ppu_inc = 1;
static bool ppu_w;

static void __not_in_flash_func(ppu_reg_write)(uint addr, uint d) {
    switch (addr & 7) {
    case 0: ppu_inc = (d & 4) ? 32 : 1; break;
    case 5: ppu_w = !ppu_w; break;
    case 6:
        if (!ppu_w) ppu_t = (ppu_t & 0x00FF) | ((d & 0x3F) << 8);
        else { ppu_t = (ppu_t & 0x3F00) | d; ppu_v = ppu_t; }
        ppu_w = !ppu_w;
        break;
    case 7:
        if (chr_is_ram && ppu_v < 0x2000)
            chr_map[ppu_v >> 10][ppu_v & 0x3FF] = d;
        ppu_v = (ppu_v + ppu_inc) & 0x3FFF;
        break;
    }
}

static void __not_in_flash_func(cpu_write)(uint addr, uint d) {
    stat_wr++;                          // 本体の RAM などへの書き込みも数える(何もしない)
    if (addr >= 0x8000) {
        switch (mapper) {
        case 1: mmc1_write(addr, d); break;
        case 2: prg16(0, d); break;
        case 3: chr8(d); break;
        case 4: mmc3_write(addr, d); break;
        case 7: prg32(d & 7); set_mirror((d & 0x10) ? MIR_1 : MIR_0); break;
        }
    } else if (addr >= 0x6000) {
        switch (mapper) {
        case 87: chr8(((d & 1) << 1) | ((d >> 1) & 1)); break;           // bit0 = 上位、bit1 = 下位(入れ替わっている)
        case 184: chr4(0, d & 7); chr4(1, ((d >> 4) & 7) | 4); break;  // $1000 側はバンク 4〜7 だけ(nesdev)
        default: wram[addr & 0x1FFF] = d; break;
        }
    } else if ((addr & 0xE000) == 0x2000) {
        ppu_reg_write(addr, d);
    }
}

// ---- バスの応答(コア1) ----
// PIO から来た 1 サンプル分の処理。実機ではループの中に展開され、PC の試験台からも同じ関数を呼ぶ。
// 答え: bit0-7 = データ、bit8-15 = 方向(0xFF = 出す)。NO_REPLY = 答えない(書き込みサイクルの2回目の push)
#define NO_REPLY 0xFFFFFFFFu
static bool wr_pending;                 // 次の CPU のサンプルは書き込みデータ
static uint wr_addr;

static inline __attribute__((always_inline)) uint32_t ppu_access(uint32_t v) {
    stat_ppu++;
    if (v & B_PPU_A13) {                                      // ネームテーブル: 出さない
        a12_low++;
        return 0;
    }
    uint a = v & 0x1FFF;
    if (is_mmc3) {
        if (a & 0x1000) {
            if (a12_low >= 8)
                mmc3_clock();
            a12_low = 0;
        } else {
            a12_low++;
        }
    }
    return 0xFF00u | chr_map[a >> 10][a & 0x3FF];
}

static inline __attribute__((always_inline)) uint32_t cpu_access(uint32_t v) {
    if (wr_pending) {                                         // 書き込みサイクルの2回目の push = データ
        wr_pending = false;
        cpu_write(wr_addr, v & 0xFF);
        return NO_REPLY;
    }
    stat_cpu++;
    cyc++;
    uint a = (v >> 8) & 0x7FFF;
    if (!(v & B_RW)) {
        // PIO は書き込みなら必ず2回目を push するので、どこへの書き込みでも受け取る(cpu_write が振り分ける)
        wr_pending = true;
        wr_addr = (v & B_ROMSEL) ? a : 0x8000 | a;
        return 0;
    }
    if (!(v & B_ROMSEL))                                      // $8000-$FFFF
        return 0xFF00u | prg_map[a >> 13][a & 0x1FFF];
    if ((a & 0x6000) == 0x6000)                               // $6000-$7FFF(A15 = 0 は /ROMSEL = High で分かる)
        return 0xFF00u | wram[a & 0x1FFF];
    if ((a & 0xE007) == 0x2002)                               // 本体の RAM・PPU・APU: 出さない。$2002 / $2007 の読み出しは覚える
        ppu_w = false;
    else if ((a & 0xE007) == 0x2007)
        ppu_v = (ppu_v + ppu_inc) & 0x3FFF;
    return 0;
}

#ifndef CART_HOST
static void __not_in_flash_func(bus_loop)(void) {
    io_ro_32 *cpu_rx = &pio0->rxf[0], *ppu_rx = &pio1->rxf[0];
    io_wo_32 *cpu_tx = &pio0->txf[0], *ppu_tx = &pio1->txf[0];
    for (;;) {
        if (!pio_sm_is_rx_fifo_empty(pio1, 0))                // PPU を先に(こちらの方が間隔が短い)
            *ppu_tx = ppu_access(*ppu_rx);
        if (!pio_sm_is_rx_fifo_empty(pio0, 0)) {
            uint32_t r = cpu_access(*cpu_rx);
            if (r != NO_REPLY)
                *cpu_tx = r;
        }
    }
}
#endif

// ---- NSF ----
// $8000-$FFFF = 曲のデータ(4KB × 8、$5FF8-$5FFF でバンク切り替え)、$5000-$5FFF = ドライバー(SRAM、書き込み可)、
// $6000-$7FFF = WRAM。ベクター($FFFA-$FFFF)の読み出しだけはドライバーの番地を返す。
static bool is_nsf, nsf_banked;
static uint8_t *nsf_prg[8];
static uint32_t nsf_nb;                 // 4KB バンクの数
static uint8_t nsf_vec[6];
static uint8_t drv[0x1000];

static void __not_in_flash_func(nsf_write)(uint addr, uint d) {
    stat_wr++;
    if (addr >= 0x8000)
        return;                         // ROM(拡張音源のレジスタは、ここで横取りして合成する予定)
    if (addr >= 0x6000) {
        wram[addr & 0x1FFF] = d;
    } else if (addr >= 0x5FF8) {
        if (nsf_banked)
            nsf_prg[addr - 0x5FF8] = rom + (d % nsf_nb) * 0x1000;
    } else if (addr >= 0x5000) {
        drv[addr & 0xFFF] = d;
    }
}

static inline __attribute__((always_inline)) uint32_t nsf_cpu_access(uint32_t v) {
    if (wr_pending) {
        wr_pending = false;
        nsf_write(wr_addr, v & 0xFF);
        return NO_REPLY;
    }
    stat_cpu++;
    uint a = (v >> 8) & 0x7FFF;
    if (!(v & B_RW)) {                                        // 書き込みは全部2回目を受け取る
        wr_pending = true;
        wr_addr = (v & B_ROMSEL) ? a : 0x8000 | a;
        return 0;
    }
    if (!(v & B_ROMSEL))                                      // $8000-$FFFF(ベクターはドライバーの番地)
        return 0xFF00u | (a >= 0x7FFA ? nsf_vec[a - 0x7FFA] : nsf_prg[a >> 12][a & 0xFFF]);
    if ((a & 0x6000) == 0x6000)                               // $6000-$7FFF
        return 0xFF00u | wram[a & 0x1FFF];
    if ((a & 0x7000) == 0x5000)                               // $5000-$5FFF ドライバー
        return 0xFF00u | drv[a & 0xFFF];
    return 0;
}

#ifndef CART_HOST
static void __not_in_flash_func(nsf_bus_loop)(void) {
    io_ro_32 *cpu_rx = &pio0->rxf[0], *ppu_rx = &pio1->rxf[0];
    io_wo_32 *cpu_tx = &pio0->txf[0], *ppu_tx = &pio1->txf[0];
    for (;;) {
        if (!pio_sm_is_rx_fifo_empty(pio1, 0))                // PPU: フォントとロゴ(is_mmc3 = false)
            *ppu_tx = ppu_access(*ppu_rx);
        if (!pio_sm_is_rx_fifo_empty(pio0, 0)) {
            uint32_t r = nsf_cpu_access(*cpu_rx);
            if (r != NO_REPLY)
                *cpu_tx = r;
        }
    }
}
#endif

// NSF の文字列(32 バイト、0 で終わる)を ASCII にする(漢字などは ? に)
static void nsf_str(char *dst, const uint8_t *src) {
    int n = 0;
    for (int i = 0; i < 32 && src[i]; i++)
        dst[n++] = (src[i] >= 0x20 && src[i] < 0x7F) ? src[i] : '?';
    while (n > 0 && dst[n - 1] == ' ')
        n--;
    dst[n] = 0;
}

static void nsf_put(int row, const char *s) {                  // 画面の土台に中央寄せで書く
    int len = strlen(s), col = (32 - len) / 2;
    memcpy(drv + NSFD_NT + row * 32 + col, s, len);
}

static const char *nsf_load(const uint8_t *p, uint32_t len, cart_info_t *info) {
    if (len < 0x80)
        return "NSF header is too short";
    memset(info, 0, sizeof *info);
    info->is_nsf = true;
    info->nsf_songs = p[6] ? p[6] : 1;
    info->nsf_start = (p[7] >= 1 && p[7] <= info->nsf_songs) ? p[7] : 1;
    info->nsf_load = p[8] | p[9] << 8;
    info->nsf_init = p[0x0A] | p[0x0B] << 8;
    info->nsf_play = p[0x0C] | p[0x0D] << 8;
    info->nsf_exp = p[0x7B];
    nsf_str(info->nsf_title, p + 0x0E);
    nsf_str(info->nsf_artist, p + 0x2E);
    nsf_str(info->nsf_copy, p + 0x4E);
    const uint8_t *banks = p + 0x70;
    for (int i = 0; i < 8; i++)
        info->nsf_banked |= banks[i] != 0;
    uint32_t dlen = len - 0x80;
    uint32_t prog = p[0x7D] | p[0x7E] << 8 | p[0x7F] << 16;   // NSF2: 後ろにメタデータがある時の長さ
    if (p[5] >= 2 && prog && prog < dlen)
        dlen = prog;
    const uint8_t *data = p + 0x80;

    if (info->nsf_banked) {
        uint32_t pad = info->nsf_load & 0xFFF;
        nsf_nb = (pad + dlen + 0xFFF) / 0x1000;
        if (nsf_nb * 0x1000 > ROM_MAX)
            return "NSF too large (> 384KB)";
        memset(rom, 0, nsf_nb * 0x1000);
        memcpy(rom + pad, data, dlen);
        for (int i = 0; i < 8; i++)
            nsf_prg[i] = rom + (banks[i] % nsf_nb) * 0x1000;
        info->prg_size = nsf_nb * 0x1000;
    } else {
        if (info->nsf_load < 0x8000)
            return "NSF load address below $8000 is not supported";
        uint32_t n = 0x10000 - info->nsf_load;
        memset(rom, 0, 0x8000);
        memcpy(rom + (info->nsf_load - 0x8000), data, dlen < n ? dlen : n);
        nsf_nb = 8;
        for (int i = 0; i < 8; i++)
            nsf_prg[i] = rom + i * 0x1000;
        info->prg_size = 0x8000;
    }
    static const uint16_t vec[3] = {NSFD_NMI, NSFD_RESET, NSFD_IRQ};
    for (int i = 0; i < 3; i++) {
        nsf_vec[i * 2] = vec[i] & 0xFF;
        nsf_vec[i * 2 + 1] = vec[i] >> 8;
    }

    memset(drv, 0, sizeof drv);                                // ドライバー・画面の土台・値
    memcpy(drv, nsfd_code, sizeof nsfd_code);
    memcpy(drv + NSFD_NT, nsfd_nt, sizeof nsfd_nt);
    nsf_put(NSFD_ROW_TITLE, info->nsf_title[0] ? info->nsf_title : "<?>");
    nsf_put(NSFD_ROW_ARTIST, info->nsf_artist);
    nsf_put(NSFD_ROW_COPY, info->nsf_copy);
    drv[NSFD_PARAM + 0] = info->nsf_songs;
    drv[NSFD_PARAM + 1] = info->nsf_start;
    memcpy(drv + NSFD_PARAM + 8, banks, 8);
    drv[NSFD_INIT_OPERAND] = info->nsf_init & 0xFF;
    drv[NSFD_INIT_OPERAND + 1] = info->nsf_init >> 8;
    drv[NSFD_PLAY_OPERAND] = info->nsf_play & 0xFF;
    drv[NSFD_PLAY_OPERAND + 1] = info->nsf_play >> 8;

    memcpy(chr_ram, nsfd_chr, 0x1000);                         // パターンテーブル 0 と 1 に同じフォント・ロゴ
    memcpy(chr_ram + 0x1000, nsfd_chr, 0x1000);
    chr = chr_ram;
    chr_size = sizeof chr_ram;
    chr_is_ram = false;                                        // $2007 の横読みはしない
    chr8(0);
    memset(wram, 0, sizeof wram);
    is_nsf = true;
    is_remote = false;
    nsf_banked = info->nsf_banked;      // $5FF8-$5FFF の書き込みを効かせるか(PC の試験台で見つけた抜け)
    mapper = -1;
    is_mmc3 = false;
    mir = -1;
    set_mirror(MIR_V);
    return NULL;
}

// ---- 画面転送(リモートデスクトップ) ----
// PC から来た 256 x 240 ドット(2 ビット)の絵を、PPU のパターンの読み出しに直接返す(gen_remote_driver.py の説明を参照)。
//   絵: タイル行 r(0〜29)、行の中の y(0〜7)、列 c(0〜31)、面 p(0/1)の 1 バイト = fb[((r * 8 + y) * 32 + c) * 2 + p]
//   付随: パレット 32 + 属性 64 + OAM 256(カーソル)。$5D00-$5EFF で 6502 が読む
// 絵と付随は 2 組ずつ持ち、PC から 1 枚届いたら(rd_ready)、画面の最後(行 29 → 行 0 に戻った所)で表と裏を入れ替える。
#define RD_FB_SIZE (30 * 8 * 32 * 2)    // 15360
typedef struct {
    uint8_t pal[32], attr[64], oam[256];
} rd_meta_t;
static uint8_t *rd_fb_front, *rd_fb_back;                // rom[] の先頭を使う(ゲームを読まないので)
static rd_meta_t rd_meta[2], *rd_meta_front = &rd_meta[0], *rd_meta_back = &rd_meta[1];
static volatile bool rd_ready;                            // コア0: 裏が埋まった → コア1: 入れ替えたら false
static uint rd_last_trow, rd_group;                       // 今のタイル行 % 8、8 行ごとの組(0〜3)
static uint8_t rd_spr[0x1000];                            // スプライト($1000)のパターン: カーソル 4 タイル
static uint8_t rd_io[0x100];                              // $5F00-$5FFF: 6502 が書くパッド・キーボード
static const uint8_t *rd_prg;                             // 6502 のプログラム(16KB、$8000 と $C000 に同じもの)

static inline __attribute__((always_inline)) uint32_t remote_ppu_access(uint32_t v) {
    stat_ppu++;
    if (v & B_PPU_A13)
        return 0;                                             // ネームテーブル・属性: 本体の VRAM が出す
    uint a = v & 0x1FFF;
    if (a & 0x1000)
        return 0xFF00u | rd_spr[a & 0xFFF];                   // スプライト(カーソル)
    uint tile = a >> 4, trow = tile >> 5;
    if (trow != rd_last_trow) {
        if (trow == 0) {
            if (rd_last_trow == 7) {
                rd_group++;                                   // 行 7 → 8、15 → 16、23 → 24
            } else {                                          // 行 29 → 0: 1 枚描き終わった
                rd_group = 0;
                if (rd_ready) {
                    uint8_t *f = rd_fb_front; rd_fb_front = rd_fb_back; rd_fb_back = f;
                    rd_meta_t *m = rd_meta_front; rd_meta_front = rd_meta_back; rd_meta_back = m;
                    rd_ready = false;
                }
            }
        }
        rd_last_trow = trow;
    }
    uint row = rd_group * 8 + trow;
    if (row > 29)
        row = 29;
    return 0xFF00u | rd_fb_front[((row * 8 + (a & 7)) * 32 + (tile & 31)) * 2 + ((a >> 3) & 1)];
}

static void __not_in_flash_func(remote_write)(uint addr, uint d) {
    stat_wr++;
    if ((addr & 0xFF00) == 0x5F00)
        rd_io[addr & 0xFF] = d;
}

static inline __attribute__((always_inline)) uint32_t remote_cpu_access(uint32_t v) {
    if (wr_pending) {
        wr_pending = false;
        remote_write(wr_addr, v & 0xFF);
        return NO_REPLY;
    }
    stat_cpu++;
    uint a = (v >> 8) & 0x7FFF;
    if (!(v & B_RW)) {
        wr_pending = true;
        wr_addr = (v & B_ROMSEL) ? a : 0x8000 | a;
        return 0;
    }
    if (!(v & B_ROMSEL))                                      // $8000-$FFFF: 6502 のプログラム
        return 0xFF00u | rd_prg[a & 0x3FFF];
    switch (a & 0x7F00) {
    case 0x5D00: return 0xFF00u | ((a & 0xFF) < 32 ? rd_meta_front->pal[a & 0x1F] : rd_meta_front->attr[((a & 0xFF) - 32) & 63]);
    case 0x5E00: return 0xFF00u | rd_meta_front->oam[a & 0xFF];
    case 0x5F00: return 0xFF00u | rd_io[a & 0xFF];
    }
    return 0;
}

#ifndef CART_HOST
static void __not_in_flash_func(remote_bus_loop)(void) {
    io_ro_32 *cpu_rx = &pio0->rxf[0], *ppu_rx = &pio1->rxf[0];
    io_wo_32 *cpu_tx = &pio0->txf[0], *ppu_tx = &pio1->txf[0];
    for (;;) {
        if (!pio_sm_is_rx_fifo_empty(pio1, 0))
            *ppu_tx = remote_ppu_access(*ppu_rx);
        if (!pio_sm_is_rx_fifo_empty(pio0, 0)) {
            uint32_t r = remote_cpu_access(*cpu_rx);
            if (r != NO_REPLY)
                *cpu_tx = r;
        }
    }
}
#endif

static void rd_default_meta(rd_meta_t *m) {
    static const uint8_t pal[32] = {0x0F, 0x00, 0x10, 0x30, 0x0F, 0x00, 0x10, 0x30, 0x0F, 0x00, 0x10, 0x30, 0x0F, 0x00, 0x10, 0x30,
                                    0x0F, 0x30, 0x0F, 0x0F, 0x0F, 0x30, 0x0F, 0x0F, 0x0F, 0x30, 0x0F, 0x0F, 0x0F, 0x30, 0x0F, 0x0F};
    memcpy(m->pal, pal, 32);                                  // 背景 = 黒・濃い灰・薄い灰・白、カーソル = 白 + 黒のふち
    memset(m->attr, 0, sizeof m->attr);
    memset(m->oam, 0xF0, sizeof m->oam);                      // スプライトは全部画面の外
}

static void rd_text(uint8_t *fb, int row, int col, const char *s) {   // NSF のフォント(色 3 = 白)で絵に字を書く
    for (; *s && col < 32; s++, col++)
        for (int y = 0; y < 8; y++) {
            uint8_t g = nsfd_chr[(uint8_t)*s * 16 + y];
            fb[((row * 8 + y) * 32 + col) * 2] = g;
            fb[((row * 8 + y) * 32 + col) * 2 + 1] = g;
        }
}

static const char *remote_load(cart_info_t *info) {
    memset(info, 0, sizeof *info);
    info->is_remote = true;
    rd_prg = remote_prg;
    rd_fb_front = rom;
    rd_fb_back = rom + RD_FB_SIZE;
    memset(rom, 0, 2 * RD_FB_SIZE);
    rd_text(rd_fb_front, 12, 8, "FC-MAGICON REMOTE");
    rd_text(rd_fb_front, 15, 9, "WAITING FOR PC...");
    rd_default_meta(&rd_meta[0]);
    rd_default_meta(&rd_meta[1]);
    rd_meta_front = &rd_meta[0];
    rd_meta_back = &rd_meta[1];
    rd_ready = false;
    rd_last_trow = rd_group = 0;
    memset(rd_spr, 0, sizeof rd_spr);
    memcpy(rd_spr, remote_spr_chr, sizeof remote_spr_chr);
    memset(rd_io, 0xFF, sizeof rd_io);
    rd_io[0] = 0;
    is_remote = true;
    is_nsf = false;
    mapper = -1;
    is_mmc3 = false;
    mir = -1;
    set_mirror(MIR_V);                                        // どれでもよい(ネームテーブルは 2 画面とも同じ並び)
    return NULL;
}

// コア0(USB)から使う。裏の絵を返す(まだ表示待ちの 1 枚がある時は NULL)
uint8_t *cart_remote_back(void) { return rd_ready ? NULL : rd_fb_back; }
// 裏の絵を書き終えたら、パレット 32・属性 64・カーソル(x, y、visible)を付けて渡す。次の画面の切れ目で表示される
void cart_remote_commit(const uint8_t pal[32], const uint8_t attr[64], int cx, int cy, bool visible) {
    rd_meta_t *m = rd_meta_back;
    memcpy(m->pal, pal, 32);
    memcpy(m->attr, attr, 64);
    memset(m->oam, 0xF0, sizeof m->oam);
    if (visible) {
        for (int i = 0; i < 4; i++) {
            int y = cy + (i >> 1) * 8, x = cx + (i & 1) * 8;
            if (y > 239 || x > 255) continue;
            m->oam[i * 4] = (uint8_t)(y - 1);                // スプライトの Y は 1 ライン遅れて表示される
            m->oam[i * 4 + 1] = (uint8_t)i;
            m->oam[i * 4 + 2] = 0;
            m->oam[i * 4 + 3] = (uint8_t)x;
        }
    }
#ifndef CART_HOST
    __dmb();
#endif
    rd_ready = true;
}
// 6502 が書いたパッド・キーボード: [0] パッド、[1..9] キーボード 9 行、[15] フレームの数
void cart_remote_io(uint8_t out[16]) { memcpy(out, rd_io, 16); }

// ---- 読み込み ----
const char *cart_mapper_name(int m) {
    switch (m) {
    case 0: return "NROM";
    case 1: return "MMC1";
    case 2: return "UxROM";
    case 3: return "CNROM";
    case 4: return "MMC3";
    case 7: return "AxROM";
    case 87: return "Jaleco J87";
    case 184: return "Sunsoft-1";
    default: return "?";
    }
}

static void reset_map(const cart_info_t *info) {
    is_nsf = false;
    is_remote = false;
    mapper = info->mapper;
    is_mmc3 = mapper == 4;
    prg = rom;
    prg_size = info->prg_size;
    chr_is_ram = info->chr_size == 0;
    chr = chr_is_ram ? chr_ram : rom + prg_size;
    chr_size = chr_is_ram ? sizeof chr_ram : info->chr_size;
    prg16(0, 0);
    prg16(1, n16() - 1);                // 最後の 16KB を $C000(リセットベクター)。NROM-128 は同じ 16KB が2回
    chr8(0);
    mir = -1;
    switch (mapper) {
    case 1: m1_shift = 0x10; m1_ctrl = 0x0C; mmc1_update(); break;
    case 4:
        m3_sel = 0;
        memcpy(m3_r, (const uint8_t[8]){0, 2, 4, 5, 6, 7, 0, 1}, 8);
        m3_irq_en = m3_reload = false;
        mmc3_update();
        break;
    case 7: prg32(0); break;
    }
    if (mir < 0)
        set_mirror(info->vertical ? MIR_V : MIR_H);
}

const char *cart_load(const uint8_t *p, uint32_t len, cart_info_t *info) {
    if (len >= 4 && memcmp(p, "FCRD", 4) == 0)             // 画面転送モード(load_rom.ps1 -Remote)
        return remote_load(info);
    if (len >= 5 && memcmp(p, "NESM\x1A", 5) == 0)
        return nsf_load(p, len, info);
    if (len < 16 || memcmp(p, "NES\x1A", 4) != 0)
        return "not an iNES / NSF file";
    bool nes2 = (p[7] & 0x0C) == 0x08;
    uint32_t prg_n = p[4], chr_n = p[5];
    if (nes2) {
        prg_n |= (p[9] & 0x0F) << 8;
        chr_n |= (p[9] & 0xF0) << 4;
    }
    memset(info, 0, sizeof *info);
    info->mapper = (p[6] >> 4) | (p[7] & 0xF0);
    info->prg_size = prg_n * 0x4000;
    info->chr_size = chr_n * 0x2000;
    info->vertical = p[6] & 1;
    info->battery = p[6] & 2;
    uint32_t off = 16 + ((p[6] & 4) ? 512 : 0);       // トレーナーは読み飛ばす
    if (info->prg_size == 0)
        return "PRG size is 0";
    if (info->prg_size + info->chr_size > ROM_MAX)
        return "ROM too large (PRG + CHR > 384KB)";
    if (off + info->prg_size + info->chr_size > len)
        return "file is shorter than the header says";
    if (!strcmp(cart_mapper_name(info->mapper), "?"))
        return "mapper not supported";
    memcpy(rom, p + off, info->prg_size + info->chr_size);
    reset_map(info);
    return NULL;
}

void cart_load_fallback(cart_info_t *info) {
    memset(info, 0, sizeof *info);
    info->prg_size = 0x8000;
    info->chr_size = 0x2000;
    for (uint32_t i = 0; i < 0x8000; i++)
        rom[i] = chr_test_rom[i % sizeof chr_test_rom];
    uint8_t *c = rom + 0x8000;          // タイル t = 下位2ビットの色、上辺と左端は色1
    for (uint t = 0; t < 256; t++) {
        for (uint r = 0; r < 8; r++) {
            uint8_t p0 = (t & 1) ? 0xFF : 0x00, p1 = (t & 2) ? 0xFF : 0x00;
            if (r == 0) { p0 = 0xFF; p1 = 0x00; }
            else { p0 |= 0x80; p1 &= 0x7F; }
            c[t * 16 + r] = c[0x1000 + t * 16 + r] = p0;
            c[t * 16 + 8 + r] = c[0x1000 + t * 16 + 8 + r] = p1;
        }
    }
    reset_map(info);
}

#ifndef CART_HOST
void cart_start(void) {
    gpio_init(PIN_IRQ);
    gpio_put(PIN_IRQ, 0);
    gpio_set_dir(PIN_IRQ, GPIO_OUT);
    pio_set_gpio_base(pio0, 0);                              // CPU: GPIO0-31
    pio_set_gpio_base(pio1, 16);                             // PPU: GPIO16-47
    pio_set_gpio_base(pio2, 16);                             // ミラーリング: GPIO43
    mirror_offset = pio_add_program(pio2, &mirror_program);
    mirror_program_init(pio2, 0, mirror_offset);
    mirror_ready = true;
    int m = mir;
    mir = -1;
    set_mirror(m);                                           // reset_map で決めたミラーリングを PIO に反映
    ppu_chr_program_init(pio1, 0, pio_add_program(pio1, &ppu_chr_program));
    cpu_m2_program_init(pio0, 0, pio_add_program(pio0, &cpu_m2_program));
    multicore_launch_core1(is_remote ? remote_bus_loop : is_nsf ? nsf_bus_loop : bus_loop);
}
#else
// PC の試験台から呼ぶ入口(PIO のサンプルと同じ形の値を渡し、答えを受け取る)
uint32_t cart_host_cpu(uint32_t v) { return is_remote ? remote_cpu_access(v) : is_nsf ? nsf_cpu_access(v) : cpu_access(v); }
uint32_t cart_host_ppu(uint32_t v) { return is_remote ? remote_ppu_access(v) : ppu_access(v); }
int cart_host_mirror(void) { return mir; }
uint8_t cart_host_peek_chr(uint a) {
    if (is_remote)                      // 画面転送: スプライトだけ(背景は位置を数える読み出しで描く)
        return (a & 0x1000) ? rd_spr[a & 0xFFF] : 0;
    return chr_map[(a >> 10) & 7][a & 0x3FF];
}   // 数えない読み出し(絵を描くだけの時)
#endif



