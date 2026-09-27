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
    bool is_menu;                       // ゲーム選択メニュー
    // NSF の時
    bool is_nsf, nsf_banked;
    uint8_t nsf_songs, nsf_start, nsf_exp;          // nsf_exp = 拡張音源のビット(まだ鳴らさない)
    uint16_t nsf_load, nsf_init, nsf_play;
    char nsf_title[33], nsf_artist[33], nsf_copy[33];
} cart_info_t;

// iNES / NES 2.0 または NSF("NESM")を読み込む。失敗したらエラーの文字列、成功したら NULL
const char *cart_load(const uint8_t *ines, uint32_t len, cart_info_t *info);

// ---- ライブラリ(フラッシュの ROM 置き場に複数の ROM。tools/nes_pack.py --library が作る) ----
//   "FCLB" + 項目の数 + 全体の長さ + 予備 の後ろに項目(64 バイト)が並び、中身は置き場の先頭からの位置に置く。
//   中身は 1 本だけの時(load_rom.ps1 game.nes)と同じ: .nes / .nsf / "FCRD"(画面転送)
typedef struct { char magic[4]; uint32_t count, total, reserved; } lib_header_t;
typedef struct { char name[48]; uint32_t offset, len, sum, reserved; } lib_entry_t;
#define LIB_MAX_ITEMS 127

// ゲーム選択メニュー(NROM としてその場で組み立てる。プログラムは gen_menu_driver.py)
void cart_load_menu(const lib_entry_t *entries, int count, cart_info_t *info);
// メニューで選ばれた番号(まだなら -1)。本体側が $5FF0 に書く
int cart_menu_choice(void);
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

