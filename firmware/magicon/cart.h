// FC-MAGICON magicon: カセットの中身(ROM・マッパー)とバスの応答
#pragma once
#include <stdbool.h>
#include <stdint.h>

#define ROM_MAX (384u * 1024u)          // PRG + CHR(ROM)の合計。RP2350 の SRAM に置く

typedef struct {
    int mapper;
    uint32_t prg_size, chr_size;        // chr_size = 0 なら CHR-RAM(8KB)
    bool vertical;                      // ヘッダーのミラーリング(1 = 垂直)
    bool battery;
    bool is_remote;                     // 画面転送(リモートデスクトップ)モード
    // NSF の時
    bool is_nsf, nsf_banked;
    uint8_t nsf_songs, nsf_start, nsf_exp;          // nsf_exp = 拡張音源のビット(まだ鳴らさない)
    uint16_t nsf_load, nsf_init, nsf_play;
    char nsf_title[33], nsf_artist[33], nsf_copy[33];
} cart_info_t;

// iNES / NES 2.0 または NSF("NESM")を読み込む。失敗したらエラーの文字列、成功したら NULL
const char *cart_load(const uint8_t *ines, uint32_t len, cart_info_t *info);
// ROM が無い時の試験画面(chr_test と同じ: 4色の縦縞 + 8ドットごとの格子、音)
void cart_load_fallback(cart_info_t *info);
// PIO を設定し、コア1でバスの応答を始める(本体の 5V を確かめてから呼ぶ)
void cart_start(void);

extern volatile uint32_t stat_cpu, stat_ppu, stat_wr;

// 画面転送モード(コア0 / PC の試験台から使う)
uint8_t *cart_remote_back(void);        // 裏の絵(256 x 240、2 ビット、15360 バイト)。表示待ちがある時は NULL
void cart_remote_commit(const uint8_t pal[32], const uint8_t attr[64], int cx, int cy, bool visible);
void cart_remote_io(uint8_t out[16]);   // [0] パッド、[1..9] キーボード 9 行、[15] フレームの数

#ifdef CART_HOST                        // PC の試験台(firmware/sim)用
uint32_t cart_host_cpu(uint32_t v);     // PIO0 のサンプル → 答え(0xFFFFFFFF = 答えない)
uint32_t cart_host_ppu(uint32_t v);     // PIO1 のサンプル → 答え
int cart_host_mirror(void);             // 0 = 水平、1 = 垂直、2 / 3 = 1画面
uint8_t cart_host_peek_chr(unsigned a);
#endif
const char *cart_mapper_name(int mapper);

