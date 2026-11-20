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
#include <stdatomic.h>
#ifndef FC_REMOTE_DMA
#define FC_REMOTE_DMA 0
#endif
#ifndef FC_REMOTE_FULL
#define FC_REMOTE_FULL 0
#endif
#if FC_DIAG_IMAGE
#include "static_image.h"
#endif
#ifdef CART_HOST                        // PC の試験台(firmware/sim)でビルドする時
#include "host_pico.h"
#else
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "hardware/pio.h"
#include "cpu_m2.pio.h"
#if FC_GAME_CPU_DMA
#include "cpu_rom_dma.pio.h"
static volatile uint32_t cpu_dma_update_busy,cpu_dma_fault_pc;
static volatile uint32_t cpu_dma_wram_busy,cpu_dma_read_miss,cpu_dma_write_miss;
static uint cpu_dma_data_channel[4];
#endif
#if FC_GAME_PROVEN_MMC3
#include "cpu_m2_fast.pio.h"
#endif
#include "ppu_chr.pio.h"
#include "mirror.pio.h"
#include <stdio.h>
#include "hardware/structs/m33.h"
static volatile bool bus_ready;
#if FC_DIAG_SPLIT
static void __not_in_flash_func(split_power_lost)(void);
#endif
#if FC_GAME_PROVEN_MMC3
#include "mmc3_a12_highcheck.pio.h"
#define mmc3_a12_program mmc3_a12_highcheck_program
#define mmc3_a12_program_init mmc3_a12_highcheck_program_init
#else
#include "mmc3_a12.pio.h"
#endif
#include "rd_width.pio.h"
#include "ppu_constant.pio.h"
#include "ppu_lookup.pio.h"
#include "ppu_banked.pio.h"
#include "hardware/dma.h"
#include "hardware/structs/busctrl.h"
#include "hardware/irq.h"
#if FC_DIAG_DMA_CHR || FC_REMOTE_DMA
static uint32_t diag_chr_lookup[8192] __attribute__((aligned(32768)));
static void diag_dma_chr_init(const uint8_t *source) {
    if(source)for(uint a=0;a<8192;a++)diag_chr_lookup[a]=0xff00u |
#if FC_DIAG_NROM_GAME
        source[a];
#elif FC_DIAG_IMAGE
        static_image_chr[a];
#else
        (0xffu>>(a&7));
#endif
    uint data=dma_claim_unused_channel(true), address=dma_claim_unused_channel(true);
    dma_channel_config dc=dma_channel_get_default_config(data);
    channel_config_set_transfer_data_size(&dc,DMA_SIZE_32);
    channel_config_set_read_increment(&dc,false);
    channel_config_set_write_increment(&dc,false);
    dma_channel_configure(data,&dc,&pio1->txf[0],diag_chr_lookup,1,false);
    dma_channel_config ac=dma_channel_get_default_config(address);
    channel_config_set_transfer_data_size(&ac,DMA_SIZE_32);
    channel_config_set_read_increment(&ac,false);
    channel_config_set_write_increment(&ac,false);
    channel_config_set_dreq(&ac,pio_get_dreq(pio1,0,false));
    dma_channel_configure(address,&ac,&dma_hw->ch[data].al3_read_addr_trig,
        &pio1->rxf[0],dma_encode_endless_transfer_count(),true);
}
#endif
#endif
#include "cart.h"
#if CART_EXTENDED_ROM && !defined(CART_HOST)
#include "hardware/psram.h"
#if FC_GAME_UNCACHED_PRG
#include "hardware/xip_cache.h"
#endif
#endif
#include "chr_rom.h"                    // 試験画面の PRG(chr_test と同じもの)
#if FC_REMOTE_FULL
#include "remote_full_driver.h"
#elif FC_REMOTE_DMA
#include "remote_compact_driver.h"
#else
#include "remote_driver.h"
#endif
#include "nsf_driver.h"                 // NSF プレイヤーのドライバー($5000-)・画面の土台・CHR(gen_nsf_driver.py)
#include "nsf_clock.h"
#include "nsf_expansion.h"
#include "menu_driver.h"                // ゲーム選択メニューの 6502 プログラム・画面の土台(gen_menu_driver.py)

#define PIN_IRQ     45                  // High で Q1 が /IRQ を Low にする
#define B_ROMSEL    (1u << 23)
#define B_RW        (1u << 24)
#define B_PPU_A13   (1u << 16)

volatile uint32_t stat_cpu, stat_ppu, stat_wr;
static volatile uint8_t menu_pad;
volatile uint32_t diag_first_cpu;
volatile uint32_t diag_last_cpu_header;
volatile uint32_t diag_marks, diag_mark_errors, diag_service_max, diag_service_count;
volatile uint32_t diag_ppu_service_max, diag_ppu_service_count;
static uint8_t diag_last_mark;
volatile uint32_t diag_error_count;
volatile uint32_t diag_errors[8][5]; // expected/actual, header, data, previous marker data, marker index
volatile uint32_t diag_trace_count, diag_trace_mark;
volatile uint32_t diag_trace[16][2]; // raw header and queued reply; not CPU-observed data
#if FC_GAME_BUS_TRACE && !defined(CART_HOST)
#define GAME_TRACE_CAP 256
static volatile uint32_t game_boot_trace[GAME_TRACE_CAP][2], game_boot_trace_count;
static volatile uint32_t game_last_header, game_last_reply;
static volatile uint32_t game_first_store,game_first_store_cycles;
static volatile bool game_trace_rearm;
static bool game_trace_started;
static bool game_trace_reported;
void cart_rearm_game_trace(void) { game_trace_reported=false; game_trace_rearm=true; }
void cart_log_game_bus(void) {
    printf("GAME BUS: cpu_pc=%u ppu_pc=%u late_cpu=%lu late_ppu=%lu last=%08lx reply=%08lx fc=%u M2=%u RD=%u pad=%02x\n",
        pio_sm_get_pc(pio0,0),pio_sm_get_pc(pio1,0),
        (unsigned long)(pio0->irq&1),(unsigned long)(pio1->irq&1),
        (unsigned long)game_last_header,(unsigned long)game_last_reply,
        gpio_get(46),gpio_get(25),gpio_get(40),menu_pad);
    printf("GAME STORE: first=%08lx cycles=%lu\n",(unsigned long)game_first_store,(unsigned long)game_first_store_cycles);
    if (!game_trace_reported && !game_trace_rearm && game_boot_trace_count == GAME_TRACE_CAP) {
        game_trace_reported = true;
        for (uint i=0;i<GAME_TRACE_CAP;i++)
            printf("GAME TRACE %02u: header=%08lx reply=%08lx\n",i,
                (unsigned long)game_boot_trace[i][0],(unsigned long)game_boot_trace[i][1]);
    }
}
#endif
#if FC_DIAG_CPU_ONLY
static uint32_t diag_write_header, diag_write_data, diag_previous_mark_data;
static uint32_t diag_prev_header, diag_prev_reply;
static inline __attribute__((always_inline)) void diag_record_cpu(uint32_t v, uint32_t reply) {
    if (diag_trace_count >= 16 || !diag_marks) return;
    uint32_t n = diag_trace_count;
    if (!n) {
        uint32_t a = (v >> 8) & 0x7fff;
        // Built-in loop only reads $00 and ROM $C070-$C079 (or its $8070 mirror).
        bool unexpected = (v & B_RW) && ((v & B_ROMSEL) ? a != 0 :
#if FC_DIAG_IMAGE
            ((a & 0x3fff) < STATIC_IMAGE_LOOP_START || (a & 0x3fff) >= STATIC_IMAGE_LOOP_END));
#else
            ((a & 0x3fff) < 0x70 || (a & 0x3fff) > 0x79));
#endif
        if (!unexpected) { diag_prev_header = v; diag_prev_reply = reply; return; }
        diag_trace[0][0] = diag_prev_header; diag_trace[0][1] = diag_prev_reply;
        diag_trace_mark = diag_marks;
        n = 1;
    }
    diag_trace[n][0] = v; diag_trace[n][1] = reply;
#ifndef CART_HOST
    __dmb();
#endif
    diag_trace_count = n + 1;
}
#endif

#if FC_REMOTE_DMA
static uint8_t rom[65536];              // remote-only build: two frames + driver
#else
_Alignas(8192) static uint8_t rom[ROM_MAX]; // 8KB-aligned PRG banks for direct PIO addressing
#endif
#if CART_EXTENDED_ROM
#define CART_LARGE_ROM_MAX (1024u * 1024u)
#ifdef CART_HOST
static uint8_t large_rom[CART_LARGE_ROM_MAX];
#else
static uint8_t __uninitialized_psram("cart_large_rom") large_rom[CART_LARGE_ROM_MAX];
#endif
static uint8_t *active_rom = rom;
static uint32_t active_capacity = sizeof rom;
bool __not_in_flash_func(cart_storage_selftest)(void) {
#ifndef CART_HOST
    if (!psram_check_address(large_rom) || !psram_check_address(large_rom + sizeof large_rom - 1))
        return false;
#endif
    volatile uint8_t *mem = large_rom;
    // Cover the full allocation with address-dependent data and its complement.
    for (uint pass = 0; pass < 2; pass++) {
        for (uint32_t i = 0; i < sizeof large_rom; i++)
            mem[i] = (uint8_t)((i ^ (i >> 8) ^ (i >> 16) ^ 0x5a) ^ (pass ? 0xff : 0));
        for (uint32_t i = 0; i < sizeof large_rom; i++) {
            uint8_t expected = (uint8_t)((i ^ (i >> 8) ^ (i >> 16) ^ 0x5a) ^ (pass ? 0xff : 0));
            if (mem[i] != expected) return false;
        }
    }
    return true;
}
static const char *select_rom_storage(uint32_t bytes) {
    if (bytes <= sizeof rom) { active_rom=rom; active_capacity=sizeof rom; return NULL; }
    if (bytes > sizeof large_rom) return "ROM exceeds extended storage";
#ifndef CART_HOST
    if (!psram_check_address(large_rom) || !psram_check_address(large_rom+sizeof large_rom-1))
        return "PSRAM not detected: large game unavailable";
#endif
    active_rom=large_rom; active_capacity=sizeof large_rom; return NULL;
}
// Keep sizeof(rom) as the small-storage capacity; use active_rom for data.
#else
#define active_rom rom
#define active_capacity (sizeof rom)
#endif
static uint8_t chr_ram[0x2000];
static uint8_t wram[0x2000];
// FDS prototype state. The image remains in XIP flash; the active side and
// RAM adapter PRG memory stay in SRAM for predictable bus response timing.
#define FDS_SIDE_SIZE 65500u
#define FDS_STREAM_CAP 98304u
#if CART_EXTENDED_ROM && !defined(CART_HOST)
static uint8_t __uninitialized_psram("cart_fds_bios") fds_bios[0x2000];
static uint8_t __uninitialized_psram("cart_fds_ram") fds_ram[0x8000];
static uint8_t __uninitialized_psram("cart_fds_side") fds_side[FDS_STREAM_CAP];
#else
static uint8_t fds_bios[0x2000], fds_ram[0x8000], fds_side[FDS_STREAM_CAP];
#endif
static const uint8_t *fds_image;
static uint32_t fds_image_size, fds_side_count, fds_side_index, fds_pos, fds_stream_len;
static uint16_t fds_irq_reload, fds_irq_counter;
static uint8_t fds_irq_control, fds_control, fds_data, fds_read_data, fds_status;
static uint32_t fds_delay;
static bool fds_irq_timer, fds_irq_disk, fds_motor, fds_read_mode, fds_transfer_reset;
static bool fds_disk_ready, fds_disk_irq, fds_io_enabled, fds_sound_enabled;
static bool fds_is_fds;

static bool __not_in_flash_func(fds_build_side)(const uint8_t *src) {
    uint32_t out = 0, in = 0;
    memset(fds_side, 0, 28300u / 8u); out = 28300u / 8u;
    while (in < FDS_SIDE_SIZE) {
        uint32_t block_len;
        switch (src[in]) {
        case 0: in++; continue;              // unused tail padding
        case 1: block_len = 56; break;
        case 2: block_len = 2; break;
        case 3: block_len = 16; break;
        case 4:
            if (in + 15 > FDS_SIDE_SIZE) return false;
            block_len = 1u + src[in + 13] + ((uint32_t)src[in + 14] << 8);
            break;
        default: return false;
        }
        if (in + block_len > FDS_SIDE_SIZE || out + block_len + 125 > FDS_STREAM_CAP) return false;
        fds_side[out++] = 0x80;
        memcpy(fds_side + out, src + in, block_len); out += block_len; in += block_len;
        fds_side[out++] = 0x4D; fds_side[out++] = 0x62; // common dump-format synthetic CRC
        memset(fds_side + out, 0, 122); out += 122;
    }
    fds_stream_len = out;
    return true;
}

static uint8_t *prg, *chr;
static uint32_t prg_size, chr_size;     // chr_size は CHR-RAM の時 0x2000
#if FC_GAME_BANKED_DMA
static uint32_t prg_bank_mask, chr_bank_mask;
static bool prg_power2, chr_power2;
#endif
static bool chr_is_ram;
static int mapper;
static bool is_remote;                  // 画面転送モード(下の「画面転送」)
static bool is_menu;                    // ゲーム選択メニュー(下の「メニュー」)
static volatile int menu_choice = -1;
static uint8_t menu_count;
static volatile uint8_t menu_request=0xff;
void cart_request_menu_pick(unsigned pick) {
    if(is_menu && pick<menu_count)menu_request=(uint8_t)pick;
}
#if FC_GAME_FAST_NROM
static uint32_t *nrom_replies;
static bool nrom_dma_active;
static void prepare_nrom_replies(const cart_info_t *info) {
    nrom_replies=NULL;
    if (info->mapper || info->is_remote || info->is_nsf || info->is_fds ||
        info->chr_size != 0x2000 || (info->prg_size != 0x4000 && info->prg_size != 0x8000)) return;
    // NROM uses at most 40KB; the unused part of its existing SRAM allocation
    // holds fully formatted CPU replies. No extra allocation or PSRAM access.
    nrom_replies=(uint32_t *)(rom+0x10000);
    for(uint a=0;a<0x8000;a++)nrom_replies[a]=0x8000ff00u|rom[a&(info->prg_size-1)];
}
#endif

_Alignas(16) static uint8_t *prg_map[4]; // $8000 / $A000 / $C000 / $E000 の 8KB
#if FC_GAME_PROVEN_MMC3 && !defined(CART_HOST)
static uint32_t __not_in_flash_func(storage_read_cycles)(volatile uint8_t *p) {
    __dmb();uint32_t start=m33_hw->dwt_cyccnt;
    volatile uint8_t value=*p;
    uint32_t ticks=m33_hw->dwt_cyccnt-start;(void)value;return ticks;
}
void __not_in_flash_func(cart_log_storage_timing)(void) {
    if(active_rom!=large_rom)return;
    m33_hw->demcr|=M33_DEMCR_TRCENA_BITS;m33_hw->dwt_ctrl|=M33_DWT_CTRL_CYCCNTENA_BITS;
    static uint32_t lo[3]={UINT32_MAX,UINT32_MAX,UINT32_MAX},hi[3]={0};
    static bool measured;
    if(!measured) {
    uint32_t irq_state=save_and_disable_interrupts();
    for(uint i=0;i<32;i++) {
        volatile uint8_t *addresses[3]={rom+i*64,large_rom+i*8192,
            (uint8_t *)((uintptr_t)large_rom+(XIP_NOCACHE_NOALLOC_BASE-XIP_BASE))+i*8192};
        for(uint kind=0;kind<3;kind++) {
            uint32_t ticks=storage_read_cycles(addresses[kind]);
            if(ticks<lo[kind])lo[kind]=ticks;if(ticks>hi[kind])hi[kind]=ticks;
        }
    }
    restore_interrupts(irq_state);
    measured=true;
    }
    printf("PRG READ CYCLES incl probe: SRAM=%lu..%lu PSRAM_cached=%lu..%lu PSRAM_uncached=%lu..%lu @250MHz\n",
        lo[0],hi[0],lo[1],hi[1],lo[2],hi[2]);
}
#endif
#if FC_GAME_BANKED_DMA || FC_DIAG_MMC3_GAME
static uint8_t *prg_bank_addresses[128];
#endif
_Alignas(32) static uint8_t *chr_map[8]; // $0000〜$1FFF の 1KB ずつ; DMA bank-pointer table

enum { MIR_H, MIR_V, MIR_0, MIR_1 };
static int mir = -1;
#ifndef CART_HOST
static uint mirror_offset;
#endif
static bool mirror_ready;               // PIO2 を設定するまでは、決めたミラーリングを覚えておくだけ

// ---- バンクの切り替え(書き込みの時だけ呼ぶので % を使ってよい) ----
static inline __attribute__((always_inline)) uint8_t *prg_address(uint bank) {
    uint8_t *result=prg+bank*0x2000;
#if CART_EXTENDED_ROM
#if FC_GAME_PRG_SRAM
    if(active_rom==large_rom && !chr_is_ram) {
        uint count=prg_size/8192,capacity=sizeof rom/8192;
        if(count<=capacity)return rom+bank*8192;
        if(bank>=count-capacity)return rom+(bank-(count-capacity))*8192;
        return result;
    }
#endif
    if (active_rom == large_rom && !chr_is_ram && chr_size + 0x4000 <= sizeof rom) {
        // Use the SRAM left after CHR for the first PRG banks and the fixed
        // final 16KB (including reset/IRQ vectors). No copying during writes.
        uint first_banks = (sizeof rom - chr_size - 0x4000) / 0x2000;
        if (bank < first_banks)
            result = rom + chr_size + bank * 0x2000;
        if (bank >= prg_size / 0x2000 - 2)
            result = rom + sizeof rom - 0x4000 + (bank - (prg_size / 0x2000 - 2)) * 0x2000;
    }
#endif
    return result;
}
static void __not_in_flash_func(prg8)(uint slot,uint bank) {
#if FC_GAME_BANKED_DMA
    bank=prg_power2?bank&prg_bank_mask:bank%(prg_size/8192);
    prg_map[slot]=prg_bank_addresses[bank];
#else
    prg_map[slot]=prg_address(bank%(prg_size/8192));
#endif
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
#if FC_GAME_BANKED_DMA
    bank = chr_power2 ? bank & chr_bank_mask : bank % (chr_size / 0x400);
    chr_map[slot] = chr + bank * 0x400;
#else
    chr_map[slot] = chr + (bank % (chr_size / 0x400)) * 0x400;
#endif
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
static bool wram_enabled = true, wram_protected;

static void __not_in_flash_func(mmc1_update)(void) {
    static const int m[4] = {MIR_0, MIR_1, MIR_V, MIR_H};
    set_mirror(m[m1_ctrl & 3]);
    wram_enabled = !(m1_prg & 0x10);
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
static volatile uint8_t m3_sel, m3_r[8];
static volatile uint8_t m3_latch, m3_count;
static volatile bool m3_irq_en;
// CPU core publishes requests; IRQ core alone acknowledges and clocks count.
static atomic_uint m3_reload_requested;
static uint32_t m3_reload_handled;
static bool is_mmc3;
static void mmc3_irq_core0_init(void);
static uint32_t a12_low;
#ifdef CART_HOST
static bool host_timed_a12,host_a12_high;
static uint64_t host_a12_low_m2;
#endif

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
#if FC_GAME_BANKED_DMA
    case 0x8000: {
        uint changed=m3_sel^d;m3_sel=d;
        if(changed&0x40) {
            uint selected=prg_power2?m3_r[6]&prg_bank_mask:m3_r[6]%n8();
            prg_map[0]=prg_bank_addresses[(d&0x40)?n8()-2:selected];
            prg_map[2]=prg_bank_addresses[(d&0x40)?selected:n8()-2];
        }
        if(changed&0x80)for(uint i=0;i<4;i++) {
            uint8_t *p=chr_map[i];chr_map[i]=chr_map[i+4];chr_map[i+4]=p;
        }
        break;
    }
    case 0x8001: {
        uint reg=m3_sel&7,inv=(m3_sel&0x80)?4:0;m3_r[reg]=d;
        if(reg<2) {
            uint bank=chr_power2?(d&0xfe)&chr_bank_mask:(d&0xfe)%(chr_size/1024);
            uint bank2=chr_power2?(d|1)&chr_bank_mask:(d|1)%(chr_size/1024);
            chr_map[(reg*2)^inv]=chr+bank*1024;
            chr_map[(reg*2+1)^inv]=chr+bank2*1024;
        } else if(reg<6) {
            uint bank=chr_power2?d&chr_bank_mask:d%(chr_size/1024);
            chr_map[(reg+2)^inv]=chr+bank*1024;
        } else {
            uint bank=prg_power2?d&prg_bank_mask:d%n8();
            prg_map[reg==6?((m3_sel&0x40)?2:0):1]=prg_bank_addresses[bank];
        }
        break;
    }
#else
    case 0x8000: m3_sel = d; mmc3_update(); break;
    case 0x8001: m3_r[m3_sel & 7] = d; mmc3_update(); break;
#endif
    case 0xA000: set_mirror((d & 1) ? MIR_H : MIR_V); break;
    case 0xA001: wram_enabled = (d & 0x80) != 0; wram_protected = (d & 0x40) != 0; break;
    case 0xC000: m3_latch = d; break;
    case 0xC001:
        atomic_store_explicit(&m3_reload_requested,
            atomic_load_explicit(&m3_reload_requested,memory_order_relaxed)+1,
            memory_order_release);
        break;
    case 0xE000: m3_irq_en = false; gpio_put(PIN_IRQ, 0); break;     // 無効 + 受け付け
    case 0xE001: m3_irq_en = true; break;
    }
}

#if FC_DIAG_MMC3_GAME
#include "mmc3_trace.h"
static volatile uint32_t m3_chr_request;
static volatile uint32_t m3_last_write, m3_write_count;
static uint32_t m3_prg_mask;
static volatile uint32_t m3_a12_events,m3_irq_assertions,m3_chr_copy_max,m3_chr_copies;
static volatile uint32_t m3_a12_short,m3_a12_mid,m3_a12_line,m3_a12_gap;
static inline __attribute__((always_inline)) void mmc3_chr_changed(void) {
    m3_chr_request++;
#ifndef CART_HOST
    __dmb();__sev();
#endif
}
// Fast path for power-of-two MMC3 ROM sizes (Mario3: 32 PRG/128 CHR banks).
static inline __attribute__((always_inline)) void mmc3_fast_prg(void) {
    uint mask=(prg_size>>13)-1;
    uint switched=(m3_r[6]&0x3f)&mask;
    prg_map[0]=prg+(((m3_sel&0x40)?mask-1:switched)<<13);
    prg_map[2]=prg+(((m3_sel&0x40)?switched:mask-1)<<13);
}
static inline __attribute__((always_inline)) void mmc3_fast_chr(uint reg) {
    uint inv=(m3_sel&0x80)?4:0, mask=(chr_size>>10)-1;
    if(reg<2) {
        uint slot=reg*2, bank=m3_r[reg]&0xfe;
        chr_map[slot^inv]=chr+((bank&mask)<<10);
        chr_map[(slot+1)^inv]=chr+(((bank+1)&mask)<<10);
    } else chr_map[(reg+2)^inv]=chr+((m3_r[reg]&mask)<<10);
}
static void __attribute__((noinline)) __not_in_flash_func(mmc3_game_write)(uint addr,uint d) {
    m3_last_write=(addr<<8)|d;m3_write_count++;
    M3_TRACE_CPU(1,(addr<<8)|d,((uint32_t)m3_sel<<24)|((uint32_t)m3_count<<16)|((uint32_t)m3_latch<<8)|m3_irq_en);
    switch(addr&0xe001) {
    case 0x8000: {
        uint changed=m3_sel^d;m3_sel=d;
        if(changed&0x40) {
            uint8_t *previous=prg_map[0];prg_map[0]=prg_map[2];prg_map[2]=previous;
        }
        if(changed&0x80)mmc3_chr_changed();
        break;
    }
    case 0x8001: {
        uint reg=m3_sel&7;m3_r[reg]=d;
        if(reg>=6) {
            if(reg==7)prg_map[1]=prg_bank_addresses[(d&0x3f)&m3_prg_mask];
            else prg_map[(m3_sel>>5)&2]=prg_bank_addresses[(d&0x3f)&m3_prg_mask];
        } else mmc3_chr_changed();
        break;
    }
    default:mmc3_write(addr,d);break;
    }
}
// DMA lanes must receive the new PRG source during M2 low. Keep counters and
// tracing outside this update; the returned mask tells the observer which
// lane registers need publication. Host tests compare this with full mapping.
static inline __attribute__((always_inline)) uint mmc3_dma_write(uint addr,uint d) {
    switch(addr&0xe001) {
    case 0x8000: {
        uint changed=m3_sel^d;m3_sel=d;
        if(changed&0x40){uint8_t *p=prg_map[0];prg_map[0]=prg_map[2];prg_map[2]=p;}
        if(changed&0x80)mmc3_chr_changed();
        return (changed&0x40)?5:0;
    }
    case 0x8001: {
        uint reg=m3_sel&7;m3_r[reg]=d;
        if(reg>=6){uint slot=reg==7?1:(m3_sel>>5)&2;
            prg_map[slot]=prg_bank_addresses[(d&0x3f)&m3_prg_mask];return 1u<<slot;}
        mmc3_chr_changed();return 0;
    }
    default:mmc3_write(addr,d);return 0;
    }
}
#ifndef CART_HOST
static volatile bool m3_report_due;
static struct repeating_timer m3_report_timer;
static bool mmc3_report_tick(struct repeating_timer *timer) {
    (void)timer;m3_report_due=true;__sev();return true;
}
static void __not_in_flash_func(mmc3_chr_background_loop)(void) {
    m33_hw->demcr|=M33_DEMCR_TRCENA_BITS;
    m33_hw->dwt_ctrl|=M33_DWT_CTRL_CYCCNTENA_BITS;
    const uint8_t *cached[8];
    for(uint slot=0;slot<8;slot++)cached[slot]=NULL; // do not miss writes during PIO startup
    uint32_t seen=UINT32_MAX;
    add_repeating_timer_ms(1000,mmc3_report_tick,NULL,&m3_report_timer);
    for(;;) {
#if FC_MMC3_TRACE
        if(getchar_timeout_us(0)=='t')m3_trace_begin();
        if(m3_trace_pending && (int32_t)(time_us_32()-m3_trace_end)>=0) {
            if(atomic_exchange_explicit(&m3_trace_active,0,memory_order_acq_rel))sleep_us(10);
            m3_trace_dump();
        }
#endif
        if(m3_report_due) {
            m3_report_due=false;
#if FC_GAME_CPU_DMA
            printf("CPU DMA: update_busy=%lu pc=%u/%u/%u/%u late=%lu wram_busy=%lu read_miss=%lu write_miss=%lu fault_pc=%lu\n",
                (unsigned long)cpu_dma_update_busy,pio0->sm[0].addr,pio0->sm[1].addr,
                pio0->sm[2].addr,pio0->sm[3].addr,(unsigned long)(pio0->irq&1),
                (unsigned long)cpu_dma_wram_busy,(unsigned long)cpu_dma_read_miss,
                (unsigned long)cpu_dma_write_miss,(unsigned long)cpu_dma_fault_pc);
            printf("CPU DMA addresses: %08lx/%08lx/%08lx/%08lx base=%08lx/%08lx/%08lx/%08lx\n",
                (unsigned long)dma_hw->ch[cpu_dma_data_channel[0]].read_addr,
                (unsigned long)dma_hw->ch[cpu_dma_data_channel[1]].read_addr,
                (unsigned long)dma_hw->ch[cpu_dma_data_channel[2]].read_addr,
                (unsigned long)dma_hw->ch[cpu_dma_data_channel[3]].read_addr,
                (unsigned long)prg_map[0],(unsigned long)prg_map[1],
                (unsigned long)prg_map[2],(unsigned long)prg_map[3]);
#endif
            printf("MMC3: cpu=%lu wr=%lu last_header=%08lx mapper_writes=%lu last_write=%06lx select=%02x chr_request=%lu IRQcount=%u latch=%u enable=%u IRQpin=%u lateACK=%lu pcCPU=%u pcPPU=%u R6=%u R7=%u\n",
                (unsigned long)stat_cpu,(unsigned long)stat_wr,(unsigned long)diag_last_cpu_header,
                (unsigned long)m3_write_count,(unsigned long)m3_last_write,m3_sel,
                (unsigned long)m3_chr_request,m3_count,m3_latch,m3_irq_en,gpio_get(PIN_IRQ),
                (unsigned long)(pio0->irq&1),pio_sm_get_pc(pio0,0),pio_sm_get_pc(pio1,0),m3_r[6],m3_r[7]);
            printf("MMC3 timing: A12_events=%lu IRQ_asserts=%lu CHR_copies=%lu max_1K_copy_cycles=%lu request=%lu handled=%lu\n",
                (unsigned long)m3_a12_events,(unsigned long)m3_irq_assertions,
                (unsigned long)m3_chr_copies,(unsigned long)m3_chr_copy_max,
                (unsigned long)m3_chr_request,(unsigned long)seen);
            printf("MMC3 A12 intervals: under8us=%lu under40us=%lu under80us=%lu longer=%lu\n",
                (unsigned long)m3_a12_short,(unsigned long)m3_a12_mid,
                (unsigned long)m3_a12_line,(unsigned long)m3_a12_gap);
        }
        uint32_t requested=m3_chr_request;
        if(requested==seen){__wfe();continue;}
        __dmb();
        for(uint reg=0;reg<6;reg++)mmc3_fast_chr(reg);
        for(uint slot=0;slot<8;slot++) {
            __dmb();
            const uint8_t *source=*(const uint8_t *volatile *)&chr_map[slot];
            if(source!=cached[slot]) {
                M3_TRACE_0(true,3,(slot<<24)|((uint32_t)(source-chr)&0xffffff),requested);
                uint32_t begun=m33_hw->dwt_cyccnt;
                // All CHR bank bases are 1 KiB aligned. Expand four bytes per
                // load to reduce source reads and loop overhead on shared SRAM.
                uint32_t *target=&diag_chr_lookup[slot*1024];
                for(uint i=0;i<1024;i+=4) {
                    uint32_t packed;
                    memcpy(&packed,source+i,sizeof(packed));
                    target[i+0]=0xff00u|(packed&0xffu);
                    target[i+1]=0xff00u|((packed>>8)&0xffu);
                    target[i+2]=0xff00u|((packed>>16)&0xffu);
                    target[i+3]=0xff00u|(packed>>24);
                }
                __dmb();cached[slot]=source;
                uint32_t elapsed=m33_hw->dwt_cyccnt-begun;
                if(elapsed>m3_chr_copy_max)m3_chr_copy_max=elapsed;
                m3_chr_copies++;
                M3_TRACE_0(true,4,(slot<<24)|(elapsed&0xffffff),requested);
            }
        }
        seen=requested;
    }
}
#endif
#endif

// PPU A12 の立ち上がり(A12 = 0 の読み出しが 8 回以上続いた後)で数える。スプライトを $1000 に置く普通の使い方で 1 ライン 1 回
static inline void __not_in_flash_func(mmc3_clock_snapshot)(uint32_t requested) {
    if (m3_count == 0 || requested != m3_reload_handled) {
        m3_count = m3_latch;
        m3_reload_handled = requested;
    } else {
        m3_count--;
    }
    if (m3_count == 0 && m3_irq_en)
#if FC_DIAG_MMC3_NO_IRQ
        gpio_put(PIN_IRQ, 0); // comparison only: count normally, suppress external IRQ
#else
        gpio_put(PIN_IRQ, 1);
#endif
}
static inline void __not_in_flash_func(mmc3_clock)(void) {
    mmc3_clock_snapshot(atomic_load_explicit(&m3_reload_requested,memory_order_acquire));
}

#if FC_DIAG_MMC3_GAME && !defined(CART_HOST)
static void __not_in_flash_func(mmc3_a12_core0_irq)(void) {
    static uint32_t previous;
    while(!pio_sm_is_rx_fifo_empty(pio2,1)) {
        (void)pio2->rxf[1];
        uint32_t now=time_us_32();
        if(previous) {
            uint32_t interval=now-previous;
            if(interval<8)m3_a12_short++;
            else if(interval<40)m3_a12_mid++;
            else if(interval<80)m3_a12_line++;
            else m3_a12_gap++;
        }
        previous=now;
        m3_a12_events++;
        bool was_asserted=gpio_get(PIN_IRQ);
        uint8_t before=m3_count;
        mmc3_clock();
        __dmb();
        if(!m3_irq_en)gpio_put(PIN_IRQ,0); // respect a simultaneous CPU-side disable
        if(!was_asserted && gpio_get(PIN_IRQ))m3_irq_assertions++;
        if(before<=2 || !was_asserted && gpio_get(PIN_IRQ))
            M3_TRACE_0(false,2,((uint32_t)before<<24)|((uint32_t)m3_count<<16)|((uint32_t)m3_latch<<8)|gpio_get(PIN_IRQ),m3_a12_events);
    }
}
static void mmc3_irq_core0_init(void) {
    irq_set_exclusive_handler(PIO2_IRQ_0,mmc3_a12_core0_irq);
    irq_set_priority(PIO2_IRQ_0,PICO_HIGHEST_IRQ_PRIORITY);
    irq_set_priority(USBCTRL_IRQ,0x80);
    pio_set_irq0_source_enabled(pio2,pis_sm1_rx_fifo_not_empty,true);
    irq_set_enabled(PIO2_IRQ_0,true);
}
#endif

// ---- CPU の書き込み ----
static uint16_t ppu_v, ppu_t, ppu_inc = 1;
static bool ppu_w;

static void __not_in_flash_func(ppu_reg_write)(uint addr, uint d) {
    switch (addr & 7) {
    case 0:
        ppu_inc = (d & 4) ? 32 : 1;
        ppu_t = (ppu_t & ~0x0C00) | ((d & 3) << 10);
        break;
    case 5:
        if (!ppu_w) ppu_t = (ppu_t & ~0x001F) | (d >> 3);
        else ppu_t = (ppu_t & ~0x73E0) | ((d & 7) << 12) | ((d & 0xF8) << 2);
        ppu_w = !ppu_w; break;
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
    if (fds_is_fds) {
        if (addr >= 0x6000 && addr < 0xE000) { fds_ram[addr - 0x6000] = (uint8_t)d; return; }
        if (addr >= 0x4020 && addr <= 0x4026) {
            switch (addr) {
            case 0x4020: fds_irq_reload = (fds_irq_reload & 0xFF00) | (uint8_t)d; break;
            case 0x4021: fds_irq_reload = (fds_irq_reload & 0x00FF) | ((uint16_t)(uint8_t)d << 8); break;
            case 0x4022: fds_irq_control = (uint8_t)d; fds_irq_counter = fds_irq_reload; fds_irq_timer = (d & 2) && fds_io_enabled; break;
            case 0x4023:
                fds_io_enabled = d & 1; fds_sound_enabled = d & 2;
                if (!fds_io_enabled) { fds_irq_timer = false; fds_irq_disk = false; gpio_put(PIN_IRQ, 0); }
                break;
            case 0x4024: fds_data = (uint8_t)d; fds_status = 0; fds_irq_disk = false; gpio_put(PIN_IRQ, fds_irq_timer); break;
            case 0x4025:
                fds_motor = d & 1; fds_transfer_reset = d & 2; fds_read_mode = d & 4;
                set_mirror((d & 8) ? MIR_H : MIR_V);
                fds_disk_ready = d & 0x40; fds_disk_irq = d & 0x80;
                fds_status = 0; fds_irq_disk = false; gpio_put(PIN_IRQ, fds_irq_timer);
                if (fds_motor && !fds_delay) { fds_delay = 50000; fds_pos = 0; }
                break;
            case 0x4026: fds_control = (uint8_t)d; break;
            }
            return;
        }
        if (addr >= 0x4040 && addr <= 0x4092) return; // FDS audio register emulation is a follow-up
    }
    if (addr >= 0x8000) {
#if FC_DIAG_CPU_ONLY
        if (addr == 0x8000 && mapper == 0) {
            if (diag_marks && d != (uint8_t)(diag_last_mark + 1)) {
                diag_mark_errors++;
                uint32_t n = diag_error_count;
                if (n < 8) {
                    diag_errors[n][0] = ((uint32_t)(uint8_t)(diag_last_mark + 1) << 8) | d;
                    diag_errors[n][1] = diag_write_header;
                    diag_errors[n][2] = diag_write_data;
                    diag_errors[n][3] = diag_previous_mark_data;
                    diag_errors[n][4] = diag_marks;
#ifndef CART_HOST
                    __dmb();
#endif
                    diag_error_count = n + 1; // publish only complete records; never overwrite
                }
            }
            diag_previous_mark_data = diag_write_data;
            diag_last_mark = d; diag_marks++;
        }
#endif
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
        default: if (wram_enabled && !wram_protected) wram[addr & 0x1FFF] = d; break;
        }
    } else if ((addr & 0xE000) == 0x2000) {
        ppu_reg_write(addr, d);
    } else if (addr == MENUD_SELECT && is_menu) {
        if (d < menu_count) menu_choice = d;
    }
}

// ---- バスの応答(コア1) ----
// PIO から来た 1 サンプル分の処理。実機ではループの中に展開され、PC の試験台からも同じ関数を呼ぶ。
// 答え: bit0-7 = データ、bit8-15 = 方向(0xFF = 出す)。NO_REPLY = 答えない(書き込みサイクルの2回目の push)
#define NO_REPLY 0xFFFFFFFFu
static bool wr_pending;                 // 次の CPU のサンプルは書き込みデータ
static uint wr_addr;

static inline __attribute__((always_inline)) void fds_tick(void) {
    if (fds_irq_timer) {
        if (!fds_irq_counter) {
            fds_irq_timer = (fds_irq_control & 1) != 0;
            fds_irq_counter = fds_irq_reload;
            gpio_put(PIN_IRQ, 1);
        } else fds_irq_counter--;
    }
    if (!fds_motor || fds_transfer_reset || !fds_side_count) return;
    if (fds_delay) { fds_delay--; return; }
    static uint16_t byte_clock;
    if (++byte_clock < 150) return;
    byte_clock = 0;
    if (fds_pos >= fds_stream_len) { fds_motor = false; return; }
    if (fds_read_mode) {
        fds_read_data = fds_side[fds_pos++];
        fds_status |= 2;
        if (fds_disk_irq) { fds_irq_disk = true; gpio_put(PIN_IRQ, 1); }
    } else {
        // Keep writes in the active side buffer. Persistent export is a later
        // step; the source image in flash is never modified in place.
        fds_side[fds_pos++] = fds_data;
        fds_status |= 2;
        if (fds_disk_irq) { fds_irq_disk = true; gpio_put(PIN_IRQ, 1); }
    }
}

static inline __attribute__((always_inline)) uint32_t ppu_access(uint32_t v) {
    stat_ppu++;
    if (v & B_PPU_A13) {                                      // ネームテーブル: 出さない
        a12_low++;
        return 0;
    }
    uint a = v & 0x1FFF;
    // Host simulator has no continuous pin timing; physical IRQ edges come
    // from PIO2 SM1, not from this legacy host-only approximation.
#ifdef CART_HOST
    if (is_mmc3 && !host_timed_a12) {
        if (a & 0x1000) {
            if (a12_low >= 8)
                mmc3_clock();
            a12_low = 0;
        } else {
            a12_low++;
        }
    }
#endif
    return 0xFF00u | chr_map[a >> 10][a & 0x3FF];
}

static inline __attribute__((always_inline)) uint32_t cpu_access(uint32_t v) {
    if (wr_pending) {                                         // 書き込みサイクルの2回目の push = データ
        wr_pending = false;
#if FC_DIAG_CPU_ONLY
        diag_write_data = v;
#endif
        cpu_write(wr_addr, v & 0xFF);
        return NO_REPLY;
    }
    stat_cpu++;
    cyc++;
    if (fds_is_fds) fds_tick();
    uint a = (v >> 8) & 0x7FFF;
    if (!(v & B_RW)) {
#if FC_DIAG_CPU_ONLY
        diag_write_header = v;
#endif
        // PIO は書き込みなら必ず2回目を push するので、どこへの書き込みでも受け取る(cpu_write が振り分ける)
        wr_pending = true;
        wr_addr = (v & B_ROMSEL) ? a : 0x8000 | a;
        return 0;
    }
    if (fds_is_fds) {
        if (a >= 0x6000 && a < 0xE000) return 0xFF00u | fds_ram[a - 0x6000];
        if (a >= 0xE000) return 0xFF00u | fds_bios[a - 0xE000];
        if (a >= 0x4040 && a <= 0x4092 && fds_sound_enabled) return 0xFF00u;
        if (fds_io_enabled && a == 0x4030) {
            uint8_t r = (fds_irq_timer ? 1 : 0) | (fds_status & 2);
            fds_status = 0; fds_irq_timer = false; fds_irq_disk = false; gpio_put(PIN_IRQ, 0);
            return 0xFF00u | r;
        }
        if (fds_io_enabled && a == 0x4031) {
            fds_status = 0; fds_irq_disk = false; gpio_put(PIN_IRQ, fds_irq_timer);
            return 0xFF00u | fds_read_data;
        }
        if (fds_io_enabled && a == 0x4032)
            return 0xFF00u | ((!fds_side_count ? 1 : 0) | ((!fds_motor || fds_delay) ? 2 : 0) | (!fds_side_count ? 4 : 0));
        if (fds_io_enabled && a == 0x4033) return 0xFF00u | 0x80;
        return 0;
    }
    if (!(v & B_ROMSEL))                                      // $8000-$FFFF
        return 0xFF00u | prg_map[a >> 13][a & 0x1FFF];
    if(is_menu && a==0x5ff3)return 0xff00u|menu_request;
    if ((a & 0x6000) == 0x6000)                               // $6000-$7FFF(A15 = 0 は /ROMSEL = High で分かる)
        return wram_enabled ? (0xFF00u | wram[a & 0x1FFF]) : 0;
    if ((a & 0xE007) == 0x2002)                               // 本体の RAM・PPU・APU: 出さない。$2002 / $2007 の読み出しは覚える
        ppu_w = false;
    else if ((a & 0xE007) == 0x2007)
        ppu_v = (ppu_v + ppu_inc) & 0x3FFF;
    return 0;
}

#if FC_GAME_FAST_NROM
static inline __attribute__((always_inline)) void nrom_bookkeeping(uint32_t v) {
    if(wr_pending) {
        wr_pending=false;stat_wr++;
        if(wr_addr>=0x6000 && wr_addr<0x8000 && wram_enabled && !wram_protected)
            wram[wr_addr&0x1fff]=(uint8_t)v;
        if(is_menu && wr_addr==MENUD_SELECT && (uint8_t)v<menu_count)
            menu_choice=(uint8_t)v;
        if(is_menu && wr_addr==0x5ff1) menu_pad=(uint8_t)v;
        return;
    }
    stat_cpu++;
    if(!(v&B_RW)) {
        wr_pending=true;
        wr_addr=((v>>8)&0x7fff)|((v&B_ROMSEL)?0:0x8000);
    }
}
#endif

#if FC_GAME_BANKED_DMA
// Games with CHR-ROM need no PPU-register shadow. Keep the first instruction
// after a CPU write free of the generic FDS/NSF/PPU dispatch cost.
static inline __attribute__((always_inline)) void game_bookkeeping(uint32_t v) {
    if(wr_pending) {
        wr_pending=false;stat_wr++;
        uint addr=wr_addr,d=(uint8_t)v;
        if(addr>=0x8000) {
            switch(mapper) {
            case 1:mmc1_write(addr,d);break;
            case 2:prg16(0,d);break;
            case 3:chr8(d);break;
            case 4:mmc3_write(addr,d);break;
            case 7:prg32(d&7);set_mirror((d&0x10)?MIR_1:MIR_0);break;
            }
        } else if(addr>=0x6000) {
            if(mapper==87)chr8(((d&1)<<1)|((d>>1)&1));
            else if(mapper==184){chr4(0,d&7);chr4(1,((d>>4)&7)|4);}
            else if(wram_enabled&&!wram_protected)wram[addr&0x1fff]=d;
        } else if(chr_is_ram && (addr&0xe000)==0x2000)ppu_reg_write(addr,d);
        else if(is_menu) {
            if(addr==MENUD_SELECT && d<menu_count)menu_choice=d;
            else if(addr==0x5ff1)menu_pad=d;
        }
        return;
    }
    stat_cpu++;cyc++;
    uint a=(v>>8)&0x7fff;
    if(!(v&B_RW)){wr_pending=true;wr_addr=a|((v&B_ROMSEL)?0:0x8000);}
    else if(chr_is_ram && (v&B_ROMSEL)) {
        if((a&0xe007)==0x2002)ppu_w=false;
        else if((a&0xe007)==0x2007)ppu_v=(ppu_v+ppu_inc)&0x3fff;
    }
}
#endif

#if FC_DIAG_CPU_ONLY
// Dedicated to the built-in NROM/constant-CHR diagnostic. No mapper, WRAM or
// PPU-register emulation: those are unnecessary for this diagnostic ROM.
static inline __attribute__((always_inline)) void diag_nrom_bookkeeping(uint32_t v) {
    if (wr_pending) {
        wr_pending = false;
        stat_wr++;
#if FC_DIAG_NROM_GAME
        if(wr_addr>=0x6000 && wr_addr<0x8000 && wram_enabled && !wram_protected)
            wram[wr_addr&0x1fff]=(uint8_t)v;
#if FC_DIAG_MMC3_GAME
        else if(wr_addr>=0x8000)mmc3_game_write(wr_addr,(uint8_t)v);
        else if(wr_addr>=0x2000 && wr_addr<0x4000 &&
            ((wr_addr&7)==0 || (wr_addr&7)==1 || (wr_addr&7)==5 || (wr_addr&7)==6))
            M3_TRACE_CPU(5,(wr_addr<<8)|(v&255),stat_cpu);
#endif
#else
        if (wr_addr == 0x8000) {
            uint8_t d = v;
            if (diag_marks && d != (uint8_t)(diag_last_mark + 1)) diag_mark_errors++;
            diag_last_mark = d;
            diag_marks++;
        }
#endif
        return;
    }
    stat_cpu++;
    if (!(v & B_RW)) {
        wr_pending = true;
        wr_addr = ((v >> 8) & 0x7fff) | ((v & B_ROMSEL) ? 0 : 0x8000);
    }
}
#endif

#ifndef CART_HOST
#if FC_GAME_BANKED_DMA
static void __attribute__((noinline)) __not_in_flash_func(game_store)(uint addr,uint d) {
    if(addr>=0x8000) {
        switch(mapper) {
        case 1:mmc1_write(addr,d);break;
        case 2:prg16(0,d);break;
        case 3:chr8(d);break;
        case 4:mmc3_write(addr,d);break;
        case 7:prg32(d&7);set_mirror((d&0x10)?MIR_1:MIR_0);break;
        }
    } else if(mapper==87)chr8(((d&1)<<1)|((d>>1)&1));
    else if(mapper==184){chr4(0,d&7);chr4(1,((d>>4)&7)|4);}
    else if(wram_enabled&&!wram_protected)wram[addr&0x1fff]=d;
}

#if FC_GAME_BUS_TRACE
static void __attribute__((noinline)) __not_in_flash_func(game_record)(uint32_t v,uint32_t reply) {
    if(game_trace_rearm){game_boot_trace_count=0;game_trace_started=false;game_trace_rearm=false;}
    uint n=game_boot_trace_count;
    if(n<GAME_TRACE_CAP && (!is_mmc3||game_trace_started||!(v&(B_ROMSEL|B_RW)))) {
        game_trace_started=true;
        game_boot_trace[n][0]=v;game_boot_trace[n][1]=reply;
        __dmb();game_boot_trace_count=n+1;
    }
}
#endif

static void __not_in_flash_func(game_bus_loop)(void) {
    save_and_disable_interrupts();
    m33_hw->demcr|=M33_DEMCR_TRCENA_BITS;
    m33_hw->dwt_ctrl|=M33_DWT_CTRL_CYCCNTENA_BITS;
    __dmb();bus_ready=true;
    for(;;) {
        if(pio_sm_is_rx_fifo_empty(pio0,0)) {
            if(is_mmc3&&!pio_sm_is_rx_fifo_empty(pio2,1)){
                (void)pio2->rxf[1];mmc3_clock();
            }
            continue;
        }
        uint32_t h=pio0->rxf[0];
        if(wr_pending) {
            wr_pending=false;stat_wr++;
            uint a=wr_addr,d=(uint8_t)h;
            if(a>=0x6000) {
#if FC_GAME_BUS_TRACE
                if(!game_first_store) {
                    uint32_t t=m33_hw->dwt_cyccnt;game_store(a,d);
                    game_first_store_cycles=m33_hw->dwt_cyccnt-t;
                    game_first_store=(a<<8)|d;
                } else
#endif
                game_store(a,d);
            }
            else if(chr_is_ram&&(a&0xe000)==0x2000)ppu_reg_write(a,d);
            else if(is_menu) {
                if(a==MENUD_SELECT&&d<menu_count)menu_choice=d;
                else if(a==0x5ff1)menu_pad=d;
            }
            continue;
        }
        uint a=(h>>8)&0x7fff;
        uint32_t reply=0x80000000u;
        if(!(h&B_RW))reply|=0x10000u;
        else if(!(h&B_ROMSEL))reply=nrom_replies?nrom_replies[a]:
            (0x8000ff00u|prg_map[a>>13][a&0x1fff]);
        else if(a>=0x6000&&wram_enabled)reply|=0xff00u|wram[a&0x1fff];
        else if(is_menu&&a==0x5ff3)reply|=0xff00u|menu_request;
        pio0->txf[0]=reply;
        stat_cpu++;cyc++;
        if(!(h&B_RW)){wr_pending=true;wr_addr=a|((h&B_ROMSEL)?0:0x8000);}
        else if(chr_is_ram&&(h&B_ROMSEL)) {
            if((a&0xe007)==0x2002)ppu_w=false;
            else if((a&0xe007)==0x2007)ppu_v=(ppu_v+ppu_inc)&0x3fff;
        }
#if FC_GAME_BUS_TRACE
        if(game_boot_trace_count<GAME_TRACE_CAP||game_trace_rearm)game_record(h,reply);
        if(!(stat_cpu&4095u)){game_last_header=h;game_last_reply=reply;}
#endif
    }
}
#endif
#if FC_GAME_PROVEN_MMC3
#include "mmc3_proven_bus.h"
#endif
#if FC_GAME_CPU_DMA
#include "cpu_rom_dma.h"
#endif
static void __not_in_flash_func(bus_loop)(void) {
    io_ro_32 *cpu_rx = &pio0->rxf[0], *ppu_rx = &pio1->rxf[0];
    io_wo_32 *cpu_tx = &pio0->txf[0], *ppu_tx = &pio1->txf[0];
#if FC_DIAG_SPLIT
    save_and_disable_interrupts();
#endif
#if FC_DIAG_CPU_ONLY
    m33_hw->demcr |= M33_DEMCR_TRCENA_BITS;
    m33_hw->dwt_ctrl |= M33_DWT_CTRL_CYCCNTENA_BITS;
#endif
    __dmb(); bus_ready = true;
    for (;;) {
        if (!pio_sm_is_rx_fifo_empty(pio0, 0)) {
#if FC_DIAG_CPU_ONLY
            uint32_t begun = m33_hw->dwt_cyccnt;
#endif
            uint32_t v = *cpu_rx;
#if FC_GAME_FAST_ACK
            // PRG reads have no mapper side effects. Queue their answer before
            // dispatching generic PPU/WRAM/mapper bookkeeping, as in the proven
            // video driver. Keep cycle accounting for MMC1 write filtering.
            if(!wr_pending && (v&(B_RW|B_ROMSEL))==B_RW) {
                uint a=(v>>8)&0x7fff;
                uint32_t reply=nrom_replies?nrom_replies[a]:
                    (0x8000ff00u|prg_map[a>>13][a&0x1fff]);
                *cpu_tx=reply;
#if FC_GAME_BUS_TRACE
                if(game_trace_rearm){game_boot_trace_count=0;game_trace_started=false;game_trace_rearm=false;}
                uint32_t tn=game_boot_trace_count;
                if(tn<GAME_TRACE_CAP && (!is_mmc3 || game_trace_started || !(v&B_ROMSEL))) {
                    game_trace_started=true;
                    game_boot_trace[tn][0]=v;game_boot_trace[tn][1]=reply;
                    __dmb();game_boot_trace_count=tn+1;
                }
                if(!(stat_cpu&4095u)){game_last_header=v;game_last_reply=reply;}
#endif
                stat_cpu++;cyc++;
                continue;
            }
#endif
            if (!wr_pending) {
                uint32_t reply = 0x80000000u;
                if (!(v & B_RW)) {
                    reply |= 0x10000u; // write acknowledgement, never drive
                } else {
                    uint a = (v >> 8) & 0x7FFF;
                    if (!(v & B_ROMSEL))
#if FC_GAME_FAST_NROM
                        reply=nrom_replies ? nrom_replies[a] : (reply|0xFF00u|prg_map[a>>13][a&0x1fff]);
#else
                        reply |= 0xFF00u | prg_map[a >> 13][a & 0x1FFF];
#endif
                    else if (is_menu && a==0x5ff3)
                        reply|=0xff00u|menu_request;
                    else if ((a & 0x6000) == 0x6000 && wram_enabled)
                        reply |= 0xFF00u | wram[a & 0x1FFF];
                }
                // Deadline-critical acknowledgement precedes all bookkeeping.
                *cpu_tx = reply;
#if FC_GAME_BUS_TRACE
                if(game_trace_rearm){game_boot_trace_count=0;game_trace_started=false;game_trace_rearm=false;}
                uint32_t trace_n=game_boot_trace_count;
                if(trace_n<GAME_TRACE_CAP && (!is_mmc3 || game_trace_started || !(v&B_ROMSEL))) {
                    game_trace_started=true;
                    game_boot_trace[trace_n][0]=v;game_boot_trace[trace_n][1]=reply;
                    __dmb();game_boot_trace_count=trace_n+1;
                }
                if(!(stat_cpu&4095u)){game_last_header=v;game_last_reply=reply;}
#endif
#if FC_DIAG_NROM_GAME
                diag_last_cpu_header = v; // one bounded snapshot, after queued response
#endif
#if FC_DIAG_CPU_ONLY
                if (diag_service_count < 32) {
                    uint32_t elapsed = m33_hw->dwt_cyccnt - begun;
                    if (elapsed > diag_service_max) diag_service_max = elapsed;
                    diag_service_count++;
                }
#if !FC_DIAG_NROM_GAME
                diag_record_cpu(v, reply);
#endif
#endif
#if FC_DIAGNOSTIC
                if (!stat_cpu) diag_first_cpu = v;
#endif
            }
            // Also consumes the second (data) sample of a write, with no reply.
#if FC_DIAG_CPU_ONLY && FC_DIAG_DIRECT_CHR
#if FC_GAME_PROVEN_MMC3
            if(!is_mmc3) {
                if(nrom_replies)nrom_bookkeeping(v);
                else (void)cpu_access(v);
            } else
#endif
            diag_nrom_bookkeeping(v);
#else
#if FC_GAME_BANKED_DMA
            if(!fds_is_fds)game_bookkeeping(v);else
#elif FC_GAME_FAST_NROM
            if(nrom_replies)nrom_bookkeeping(v);else
#endif
            (void)cpu_access(v);
#endif
        }
#if !FC_DIAG_CPU_ONLY || FC_GAME_PROVEN_MMC3
        if (!FC_REMOTE_DMA &&
#if FC_GAME_PROVEN_MMC3
            !is_mmc3 &&
#endif
#if FC_GAME_FAST_NROM
            !nrom_dma_active &&
#endif
            !pio_sm_is_rx_fifo_empty(pio1, 0))
            *ppu_tx = 0x80000000u | ppu_access(*ppu_rx);
#endif
#if !FC_DIAG_MMC3_NO_IRQ && !FC_DIAG_MMC3_GAME
        if (is_mmc3 && !pio_sm_is_rx_fifo_empty(pio2, 1)) {
            (void)pio2->rxf[1];
            mmc3_clock();
        }
#endif
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
static nsf_clock_t nsf_clock;
static nsf_expansion_t nsf_expansion;
static bool nsf_has_vrc6;
static _Atomic uint32_t nsf_completed_cycle;
static uint8_t nsf_empty_bank[4096]; // SRAM: do not introduce XIP latency into CPU replies
static uint8_t *nsf_bank(uint d) {
    return d < nsf_nb ? active_rom + d * 4096 : (uint8_t *)nsf_empty_bank;
}

static void __not_in_flash_func(nsf_write)(uint addr, uint d) {
    stat_wr++;
    if (addr == 0x5F03) {
        nsf_clock_start(&nsf_clock, d != 0);
        if(!d && nsf_has_vrc6)nsf_expansion_write(&nsf_expansion,stat_cpu,255,0);
        return;
    }
    if(nsf_has_vrc6) {
        int reg=vrc6_register(addr);
        if(reg>=0){nsf_expansion_write(&nsf_expansion,stat_cpu,(uint8_t)reg,(uint8_t)d);return;}
    }
    if (addr >= 0x8000)
        return;                         // ROM(拡張音源のレジスタは、ここで横取りして合成する予定)
    if (addr >= 0x6000) {
        wram[addr & 0x1FFF] = d;
    } else if (addr >= 0x5FF8) {
        if (nsf_banked)
            nsf_prg[addr - 0x5FF8] = nsf_bank(d);
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
    nsf_clock_tick(&nsf_clock); // exactly once per M2 header, never the write-data sample
    if(nsf_has_vrc6 && !(stat_cpu&63))
        atomic_store_explicit(&nsf_completed_cycle,stat_cpu-1,memory_order_release);
    uint a = (v >> 8) & 0x7FFF;
    if (!(v & B_RW)) {                                        // 書き込みは全部2回目を受け取る
        wr_pending = true;
        wr_addr = (v & B_ROMSEL) ? a : 0x8000 | a;
        return 0;
    }
    if (!(v & B_ROMSEL))                                      // $8000-$FFFF(ベクターはドライバーの番地)
        return 0xFF00u | (a >= 0x7FFA ? nsf_vec[a - 0x7FFA] : nsf_prg[a >> 12][a & 0xFFF]);
    if (a == 0x5F02) return 0xFF00u | nsf_clock_take(&nsf_clock);
    if ((a & 0x6000) == 0x6000)                               // $6000-$7FFF
        return 0xFF00u | wram[a & 0x1FFF];
    if ((a & 0x7000) == 0x5000)                               // $5000-$5FFF ドライバー
        return 0xFF00u | drv[a & 0xFFF];
    return 0;
}

#ifndef CART_HOST
#if FC_GAME_BANKED_DMA
static uint32_t chr_dma_sink;
static void banked_dma_start(void) {
    ppu_banked_program_init(pio1,0,pio_add_program(pio1,&ppu_banked_program),(uint32_t)chr_map);
    uint offset=dma_claim_unused_channel(true),address=dma_claim_unused_channel(true);
    uint pointer=dma_claim_unused_channel(true),sum=dma_claim_unused_channel(true),data=dma_claim_unused_channel(true);
    dma_channel_config c=dma_channel_get_default_config(offset);
    channel_config_set_transfer_data_size(&c,DMA_SIZE_32);
    channel_config_set_read_increment(&c,false);channel_config_set_write_increment(&c,false);
    channel_config_set_dreq(&c,pio_get_dreq(pio1,0,false));channel_config_set_chain_to(&c,address);
    dma_channel_configure(offset,&c,&dma_hw->sniff_data,&pio1->rxf[0],1,false);
    c=dma_channel_get_default_config(address);
    channel_config_set_transfer_data_size(&c,DMA_SIZE_32);
    channel_config_set_read_increment(&c,false);channel_config_set_write_increment(&c,false);
    channel_config_set_dreq(&c,pio_get_dreq(pio1,0,false));
    dma_channel_configure(address,&c,&dma_hw->ch[pointer].al3_read_addr_trig,&pio1->rxf[0],1,false);
    c=dma_channel_get_default_config(pointer);
    channel_config_set_transfer_data_size(&c,DMA_SIZE_32);
    channel_config_set_read_increment(&c,false);channel_config_set_write_increment(&c,false);
    channel_config_set_sniff_enable(&c,true);channel_config_set_chain_to(&c,sum);
    dma_channel_configure(pointer,&c,&chr_dma_sink,chr_map,1,false);
    c=dma_channel_get_default_config(sum);
    channel_config_set_transfer_data_size(&c,DMA_SIZE_32);
    channel_config_set_read_increment(&c,false);channel_config_set_write_increment(&c,false);
    dma_channel_configure(sum,&c,&dma_hw->ch[data].al3_read_addr_trig,&dma_hw->sniff_data,1,false);
    c=dma_channel_get_default_config(data);
    channel_config_set_transfer_data_size(&c,DMA_SIZE_8);
    channel_config_set_read_increment(&c,false);channel_config_set_write_increment(&c,false);
    channel_config_set_chain_to(&c,offset);
    dma_channel_configure(data,&c,&pio1->txf[0],chr_map[0],1,false);
    dma_sniffer_enable(pointer,DMA_SNIFF_CTRL_CALC_VALUE_SUM,false);
    nrom_dma_active=true;
    dma_start_channel_mask(1u<<offset);
}
#endif
#if FC_GAME_FAST_NROM
static void nrom_dma_start(void) {
    // Reuse spare NROM SRAM after the CPU reply table. The PIO lookup uses
    // a 32KB-aligned address table, exactly as the proven video responder does.
    uintptr_t address=((uintptr_t)(rom+0x30000)+32767u)&~(uintptr_t)32767u;
    uint32_t *table=(uint32_t *)address;
    for(uint a=0;a<8192;a++)table[a]=0xff00u|chr[a];
    ppu_lookup_program_init(pio1,0,pio_add_program(pio1,&ppu_lookup_program),(uint32_t)address);
    uint data=dma_claim_unused_channel(true), addr=dma_claim_unused_channel(true);
    dma_channel_config dc=dma_channel_get_default_config(data);
    channel_config_set_transfer_data_size(&dc,DMA_SIZE_32);
    channel_config_set_read_increment(&dc,false);channel_config_set_write_increment(&dc,false);
    dma_channel_configure(data,&dc,&pio1->txf[0],table,1,false);
    dma_channel_config ac=dma_channel_get_default_config(addr);
    channel_config_set_transfer_data_size(&ac,DMA_SIZE_32);
    channel_config_set_read_increment(&ac,false);channel_config_set_write_increment(&ac,false);
    channel_config_set_dreq(&ac,pio_get_dreq(pio1,0,false));
    dma_channel_configure(addr,&ac,&dma_hw->ch[data].al3_read_addr_trig,
        &pio1->rxf[0],dma_encode_endless_transfer_count(),true);
    nrom_dma_active=true;
}
#endif
static void __not_in_flash_func(nsf_bus_loop)(void) {
    __dmb(); bus_ready = true;
    io_ro_32 *cpu_rx = &pio0->rxf[0], *ppu_rx = &pio1->rxf[0];
    io_wo_32 *cpu_tx = &pio0->txf[0], *ppu_tx = &pio1->txf[0];
    for (;;) {
        if (!pio_sm_is_rx_fifo_empty(pio0, 0)) {
            uint32_t r = nsf_cpu_access(*cpu_rx);
            if (r != NO_REPLY)
                *cpu_tx = r | 0x80000000u | (wr_pending ? 0x10000u : 0);
        }
        if (!pio_sm_is_rx_fifo_empty(pio1, 0))
            *ppu_tx = 0x80000000u | ppu_access(*ppu_rx);
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
    if (p[5] != 1 && p[5] != 2) return "unsupported NSF version";
    if (p[5] == 2 && p[0x7C]) return "NSF2 execution flags are not supported";
    if (!p[6]) return "NSF has zero songs";
    if ((p[0x7A] & 3) == 1) return "PAL-only NSF is not supported on NTSC FC";
    if (p[0x7A] & 0xFC) return "unsupported NSF region flags";
    if (p[0x7B] & ~1u) return "only VRC6 expansion audio is supported";
    info->is_nsf = true;
    info->nsf_songs = p[6] ? p[6] : 1;
    info->nsf_start = (p[7] >= 1 && p[7] <= info->nsf_songs) ? p[7] : 1;
    info->nsf_load = p[8] | p[9] << 8;
    info->nsf_init = p[0x0A] | p[0x0B] << 8;
    info->nsf_play = p[0x0C] | p[0x0D] << 8;
    if (info->nsf_init < 0x8000 || info->nsf_play < 0x8000 ||
        info->nsf_init >= 0xFFFA || info->nsf_play >= 0xFFFA)
        return "unsupported NSF INIT/PLAY address";
    uint16_t period = p[0x6E] | p[0x6F] << 8;
    nsf_clock_init(&nsf_clock, period ? period : 16639);
    info->nsf_exp = p[0x7B];
    nsf_str(info->nsf_title, p + 0x0E);
    nsf_str(info->nsf_artist, p + 0x2E);
    nsf_str(info->nsf_copy, p + 0x4E);
    const uint8_t *banks = p + 0x70;
    for (int i = 0; i < 8; i++)
        info->nsf_banked |= banks[i] != 0;
    uint32_t dlen = len - 0x80;
    if (!dlen) return "NSF has no program data";
    uint32_t prog = p[0x7D] | p[0x7E] << 8 | p[0x7F] << 16;   // NSF2: 後ろにメタデータがある時の長さ
    if (p[5] == 2 && prog > dlen) return "truncated NSF2 program";
    if (p[5] >= 2 && prog && prog < dlen)
        dlen = prog;
    const uint8_t *data = p + 0x80;

    if (info->nsf_banked) {
        if (info->nsf_load < 0x8000) return "NSF load address below $8000 is not supported";
        uint32_t pad = info->nsf_load & 0xFFF;
        nsf_nb = (pad + dlen + 0xFFF) / 0x1000;
        if (nsf_nb * 0x1000 > active_capacity)
            return "NSF too large (> 384KB)";
        memset(active_rom, 0, nsf_nb * 0x1000);
        memcpy(active_rom + pad, data, dlen);
        for (int i = 0; i < 8; i++)
            nsf_prg[i] = nsf_bank(banks[i]);
        info->prg_size = nsf_nb * 0x1000;
    } else {
        if (info->nsf_load < 0x8000)
            return "NSF load address below $8000 is not supported";
        uint32_t n = 0x10000 - info->nsf_load;
        if (dlen > n) return "NSF program exceeds address space";
        memset(active_rom, 0, 0x8000);
        memcpy(active_rom + (info->nsf_load - 0x8000), data, dlen < n ? dlen : n);
        nsf_nb = 8;
        for (int i = 0; i < 8; i++)
            nsf_prg[i] = active_rom + i * 0x1000;
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
    nsf_has_vrc6 = p[0x7B] == 1;
    nsf_expansion_init(&nsf_expansion);nsf_expansion.cycle=stat_cpu;
    atomic_store(&nsf_completed_cycle,stat_cpu);
    is_remote = false;
    is_menu = false;
    nsf_banked = info->nsf_banked;      // $5FF8-$5FFF の書き込みを効かせるか(PC の試験台で見つけた抜け)
    mapper = -1;
    is_mmc3 = false;
    mir = -1;
    set_mirror(MIR_V);
    return NULL;
}

unsigned cart_nsf_audio(int16_t *out,unsigned count) {
    return nsf_has_vrc6 ? nsf_expansion_render(&nsf_expansion,
        atomic_load_explicit(&nsf_completed_cycle,memory_order_acquire),out,count) : 0;
}
uint32_t cart_nsf_audio_fault(void) { return atomic_load(&nsf_expansion.fault); }

// ---- 画面転送(リモートデスクトップ) ----
// PC から来た 256 x 240 ドット(2 ビット)の絵を、PPU のパターンの読み出しに直接返す(gen_remote_driver.py の説明を参照)。
//   絵: タイル行 r(0〜29)、行の中の y(0〜7)、列 c(0〜31)、面 p(0/1)の 1 バイト = fb[((r * 8 + y) * 32 + c) * 2 + p]
//   付随: パレット 32 + 属性 64 + OAM 256(カーソル)。$5D00-$5EFF で 6502 が読む
// 絵と付随は 2 組ずつ持ち、PC から 1 枚届いたら(rd_ready)、画面の最後(行 29 → 行 0 に戻った所)で表と裏を入れ替える。
#define RD_FB_SIZE (30 * 8 * 32 * 2)    // 15360
typedef struct {
    uint8_t pal[32], attr[64], oam[256];
} rd_meta_t;
static uint8_t *rd_fb_front, *rd_fb_back;                // active_rom[] の先頭を使う(ゲームを読まないので)
static rd_meta_t rd_meta[2], *rd_meta_front = &rd_meta[0], *rd_meta_back = &rd_meta[1];
static volatile bool rd_ready;                            // コア0: 裏が埋まった → コア1: 入れ替えたら false
static uint rd_last_trow, rd_group;                       // 今のタイル行 % 8、8 行ごとの組(0〜3)
static uint8_t rd_spr[0x1000];                            // スプライト($1000)のパターン: カーソル 4 タイル
static uint8_t rd_io[0x100];                              // $5F00-$5FFF: 6502 が書くパッド・キーボード
static const uint8_t *rd_prg;                             // 6502 のプログラム(16KB、$8000 と $C000 に同じもの)
#if FC_REMOTE_FULL
#include "remote_full.h"
#endif

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
#if FC_REMOTE_FULL
    if((a&0x7c00)==0x6000)return 0xff00u|rd_nt[a&1023];
#endif
    switch (a & 0x7F00) {
    case 0x5D00: return 0xFF00u | ((a & 0xFF) < 32 ? rd_meta_front->pal[a & 0x1F] : rd_meta_front->attr[((a & 0xFF) - 32) & 63]);
    case 0x5E00: return 0xFF00u | rd_meta_front->oam[a & 0xFF];
    case 0x5F00: return 0xFF00u | rd_io[a & 0xFF];
    }
    return 0;
}

#ifndef CART_HOST
static void __not_in_flash_func(remote_bus_loop)(void) {
    __dmb(); bus_ready = true;
    io_ro_32 *cpu_rx = &pio0->rxf[0], *ppu_rx = &pio1->rxf[0];
    io_wo_32 *cpu_tx = &pio0->txf[0], *ppu_tx = &pio1->txf[0];
    for (;;) {
        if (!FC_REMOTE_DMA && !pio_sm_is_rx_fifo_empty(pio1, 0))
            *ppu_tx = 0x80000000u | remote_ppu_access(*ppu_rx);
        if (!pio_sm_is_rx_fifo_empty(pio0, 0)) {
            uint32_t r = remote_cpu_access(*cpu_rx);
            if (r != NO_REPLY)
                *cpu_tx = r | 0x80000000u | (wr_pending ? 0x10000u : 0);
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
    // Keep deadline-critical 6502 reads in SRAM, as in the working game path.
    memcpy(active_rom+2*RD_FB_SIZE,remote_prg,sizeof remote_prg);
    rd_prg = active_rom+2*RD_FB_SIZE;
    rd_fb_front = active_rom;
    rd_fb_back = active_rom + RD_FB_SIZE;
    memset(active_rom, 0, 2 * RD_FB_SIZE);
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
#if FC_REMOTE_FULL
    memset(rd_cached_valid,0,sizeof rd_cached_valid);
#endif
#if FC_REMOTE_DMA
    // Initial DMA table is built before enabling either bus.
    for(uint a=0;a<8192;a++)diag_chr_lookup[a]=0xff00u;
    for(uint a=0;a<4096;a++)diag_chr_lookup[4096+a]=0xff00u|rd_spr[a];
#endif
    memset(rd_io, 0xFF, sizeof rd_io);
    rd_io[0] = 0;
    is_remote = true;
    is_nsf = false;
    is_menu = false;
    mapper = -1;
    is_mmc3 = false;
    mir = -1;
    set_mirror(MIR_V);                                        // どれでもよい(ネームテーブルは 2 画面とも同じ並び)
#if FC_REMOTE_DMA
    memcpy(rd_fb_back,rd_fb_front,RD_FB_SIZE);
    cart_remote_commit(rd_meta_front->pal,rd_meta_front->attr,0,0,false);
#endif
    return NULL;
}

// コア0(USB)から使う。裏の絵を返す(まだ表示待ちの 1 枚がある時は NULL)
uint8_t *cart_remote_back(void) { return rd_ready ? NULL : rd_fb_back; }
// 裏の絵を書き終えたら、パレット 32・属性 64・カーソル(x, y、visible)を付けて渡す。次の画面の切れ目で表示される
void cart_remote_commit(const uint8_t pal[32], const uint8_t attr[64], int cx, int cy, bool visible) {
#if FC_REMOTE_FULL
    remote_full_convert(rd_fb_back);
    // The last NT chunk also carries all 64 per-16x16 palette attributes.
    memcpy(rd_nt+960,attr,64);
#elif FC_REMOTE_DMA
    // Grayscale trial: sample 256x240 into 128x120, 240 unique tiles.
    // In-place CHR updates can tear; they cannot delay a bus response.
    for(uint ty=0;ty<15;ty++)for(uint tx=0;tx<16;tx++)
        for(uint y=0;y<8;y++)for(uint p=0;p<2;p++) {
            uint8_t bits=0;
            for(uint x=0;x<8;x++) {
                uint sx=(tx*8+x)*2,sy=(ty*8+y)*2;
                uint8_t b=rd_fb_back[(sy*32+(sx>>3))*2+p];
                bits|=((b>>(7-(sx&7)))&1u)<<(7-x);
            }
            diag_chr_lookup[(ty*16+tx)*16+y+p*8]=0xff00u|bits;
        }
    cx=64+cx/2;cy=56+cy/2;
#endif
    rd_meta_t *m = rd_meta_back;
    memcpy(m->pal, pal, 32);
    memcpy(m->attr, attr, 64);
#if FC_REMOTE_DMA && !FC_REMOTE_FULL
    memset(m->attr,0,64);
#endif
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
#if FC_REMOTE_DMA
    rd_meta_t *old=rd_meta_front;rd_meta_front=rd_meta_back;rd_meta_back=old;
    rd_ready=false;
#else
    rd_ready = true;
#endif
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
    case 20: return "FDS";
    case 87: return "Jaleco J87";
    case 184: return "Sunsoft-1";
    default: return "?";
    }
}

static void reset_map(const cart_info_t *info) {
#ifdef CART_HOST
    host_timed_a12=false;host_a12_high=false;host_a12_low_m2=0;
#endif
    wr_pending = false; ppu_v = ppu_t = 0; ppu_w = false; ppu_inc = 1;
    cyc = 0; m1_last_cyc = UINT32_MAX - 1;
    m1_chr0 = m1_chr1 = m1_prg = 0;
    m3_latch = m3_count = 0; a12_low = 0; gpio_put(PIN_IRQ, 0);
    wram_enabled = true; wram_protected = false;
    memset(wram, 0, sizeof wram); memset(chr_ram, 0, sizeof chr_ram);
    is_nsf = false;
    is_remote = false;
    is_menu = false;
    fds_is_fds = info->is_fds;
    fds_irq_timer = fds_irq_disk = false;
    fds_motor = fds_read_mode = fds_transfer_reset = false;
    fds_disk_ready = fds_disk_irq = fds_io_enabled = fds_sound_enabled = false;
    fds_irq_reload = fds_irq_counter = 0;
    fds_irq_control = fds_control = fds_data = fds_read_data = fds_status = 0;
    fds_delay = fds_pos = 0;
    gpio_put(PIN_IRQ, 0);
    mapper = info->mapper;
    is_mmc3 = mapper == 4;
    prg = active_rom;
#if FC_GAME_UNCACHED_PRG && !defined(CART_HOST)
    if(active_rom==large_rom)
        prg=(uint8_t *)((uintptr_t)active_rom+(XIP_NOCACHE_NOALLOC_BASE-XIP_BASE));
#endif
    prg_size = info->prg_size;
#if FC_DIAG_MMC3_GAME
    m3_prg_mask=(prg_size>>13)-1;
#endif
    chr_is_ram = info->chr_size == 0;
    chr = chr_is_ram ? chr_ram : active_rom + prg_size;
#if CART_EXTENDED_ROM
    // PPU reads have the tighter deadline. Large games keep their entire CHR
    // ROM in internal SRAM, with PRG in PSRAM, so bank changes stay immediate.
    if (!chr_is_ram && active_rom == large_rom && !FC_GAME_PRG_SRAM) chr = rom;
#endif
    chr_size = chr_is_ram ? sizeof chr_ram : info->chr_size;
#if FC_DIAG_MMC3_GAME
    for(uint bank=0;bank<prg_size/8192;bank++)prg_bank_addresses[bank]=prg_address(bank);
#endif
#if FC_GAME_BANKED_DMA
    prg_bank_mask=prg_size/8192-1;chr_bank_mask=chr_size/1024-1;
    prg_power2=!(prg_bank_mask&(prg_bank_mask+1));
    chr_power2=!(chr_bank_mask&(chr_bank_mask+1));
    for(uint bank=0;bank<=prg_bank_mask;bank++)prg_bank_addresses[bank]=prg_address(bank);
#endif
    prg16(0, 0);
    prg16(1, n16() - 1);                // 最後の 16KB を $C000(リセットベクター)。NROM-128 は同じ 16KB が2回
    chr8(0);
    mir = -1;
    switch (mapper) {
    case 1: m1_shift = 0x10; m1_ctrl = 0x0C; mmc1_update(); break;
    case 4:
        m3_sel = 0;
        for(uint i=0;i<8;i++)m3_r[i]=(const uint8_t[8]){0, 2, 4, 5, 6, 7, 0, 1}[i];
        m3_irq_en = false;
        atomic_store_explicit(&m3_reload_requested,0,memory_order_relaxed);
        m3_reload_handled=0;
        mmc3_update();
        break;
    case 7: prg32(0); break;
    }
    if (mir < 0)
        set_mirror(info->vertical ? MIR_V : MIR_H);
#if FC_GAME_FAST_NROM
    prepare_nrom_replies(info);
#endif
}

const char *cart_load(const uint8_t *p, uint32_t len, cart_info_t *info) {
    if (len >= 4 && memcmp(p, "FCRD", 4) == 0)             // 画面転送モード(load_rom.ps1 -Remote)
        return remote_load(info);
    if (len >= 16 && memcmp(p, "FCFD", 4) == 0) {
        uint32_t version, disk_len, sides;
        memcpy(&version, p + 4, 4); memcpy(&disk_len, p + 8, 4); memcpy(&sides, p + 12, 4);
        if (version != 1 || !sides || sides > 64 || disk_len != sides * FDS_SIDE_SIZE ||
            len != 16u + 0x2000u + disk_len)
            return "bad FDS payload header";
        memset(info, 0, sizeof *info);
        info->mapper = 20; info->prg_size = 0x8000; info->chr_size = 0; info->is_fds = true;
        memcpy(fds_bios, p + 16, sizeof fds_bios);
        fds_image = p + 16 + sizeof fds_bios; fds_image_size = disk_len;
        fds_side_count = sides; fds_side_index = 0; fds_pos = 0;
        if (!fds_build_side(fds_image)) return "unsupported or oversized FDS side format";
        memset(fds_ram, 0, sizeof fds_ram);
        reset_map(info);
        return NULL;
    }
    if (len >= 5 && memcmp(p, "NESM\x1A", 5) == 0)
        return nsf_load(p, len, info);
    if (len < 16 || memcmp(p, "NES\x1A", 4) != 0)
        return "not an iNES / NSF file";
    bool nes2 = (p[7] & 0x0C) == 0x08;
    if (p[6] & 8) return "four-screen VRAM not supported";
    if (nes2 && (p[8] || p[10] || p[11] || p[12] || p[13] || p[14] || p[15]))
        return "NES 2.0 extensions not supported";
    if (nes2 && ((p[9] & 15) == 15 || (p[9] >> 4) == 15))
        return "NES 2.0 exponent size not supported";
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
    #if CART_EXTENDED_ROM
    const char *storage_error=select_rom_storage(info->prg_size + info->chr_size);
    if(storage_error)return storage_error;
#else
    if (info->prg_size + info->chr_size > active_capacity)
        return "ROM too large (PRG + CHR > 384KB)";
#endif
    if (off + info->prg_size + info->chr_size > len)
        return "file is shorter than the header says";
    if (!strcmp(cart_mapper_name(info->mapper), "?"))
        return "mapper not supported";
    memcpy(active_rom, p + off, info->prg_size + info->chr_size);
#if CART_EXTENDED_ROM
    if (active_rom == large_rom) {
        if (info->chr_size > sizeof rom) return "large game CHR exceeds SRAM";
        if (memcmp(active_rom, p + off, info->prg_size + info->chr_size))
            return "PSRAM ROM verification failed";
#if FC_GAME_UNCACHED_PRG && !defined(CART_HOST)
        // Publish any dirty PSRAM cache lines before using the uncached alias.
        xip_cache_clean_range((uintptr_t)active_rom-XIP_BASE,info->prg_size+info->chr_size);
#endif
#if FC_GAME_PRG_SRAM
        if(info->chr_size) {
            uint count=info->prg_size/8192,capacity=sizeof rom/8192;
            for(uint bank=0;bank<count;bank++) {
                if(count<=capacity)memcpy(rom+bank*8192,p+off+bank*8192,8192);
                else if(bank>=count-capacity)
                    memcpy(rom+(bank-(count-capacity))*8192,p+off+bank*8192,8192);
            }
        }
#else
        memcpy(rom, p + off + info->prg_size, info->chr_size);
        if (info->chr_size + 0x4000 <= sizeof rom) {
            uint32_t first = sizeof rom - info->chr_size - 0x4000;
            if (first > info->prg_size) first = info->prg_size;
            memcpy(rom + info->chr_size, p + off, first);
            memcpy(rom + sizeof rom - 0x4000, p + off + info->prg_size - 0x4000, 0x4000);
        }
#endif
    }
#endif
    reset_map(info);
    return NULL;
}

void cart_load_fallback(cart_info_t *info) {
#if CART_EXTENDED_ROM
    (void)select_rom_storage(0xA000);
#endif
    memset(info, 0, sizeof *info);
    info->prg_size = 0x8000;
    info->chr_size = 0x2000;
    for (uint32_t i = 0; i < 0x8000; i++)
        active_rom[i] =
#if FC_DIAG_IMAGE
            static_image_prg[i % sizeof static_image_prg];
#else
            chr_test_rom[i % sizeof chr_test_rom];
#endif
#if FC_DIAG_CPU_ONLY
    // Silence the known test ROM's APU enable; preserve its CPU test loop.
    for (uint i=0; i+4<0x8000; i++)
        if (!memcmp(active_rom+i, (const uint8_t[]){0xA9,1,0x8D,0x15,0x40},5)) active_rom[i+1]=0;
#if FC_DIAG_DIRECT_CHR && !FC_DIAG_IMAGE
    // Built-in ROM listing: paltab at $C07B, mirrored at $807B.
    // All four attribute palettes identical: black/white/gray/black.
    // This removes the old coloured-block layout as a visual ambiguity.
    for (uint bank=0; bank<2; bank++)
        for (uint k=0; k<16; k++)
            active_rom[bank*0x4000 + 0x7b + k] =
#if FC_DIAG_DMA_CHR
                (k%4==3)?0x30:0x0f;
#else
                (const uint8_t[]){0x0f,0x30,0x10,0x0f}[k%4];
#endif
#endif
#endif
    uint8_t *c = active_rom + 0x8000;          // タイル t = 下位2ビットの色、上辺と左端は色1
    for (uint t = 0; t < 256; t++) {
        for (uint r = 0; r < 8; r++) {
            uint8_t p0 = (t & 1) ? 0xFF : 0x00, p1 = (t & 2) ? 0xFF : 0x00;
            if (r == 0) { p0 = 0xFF; p1 = 0x00; }
            else { p0 |= 0x80; p1 &= 0x7F; }
            c[t * 16 + r] = c[0x1000 + t * 16 + r] = p0;
            c[t * 16 + 8 + r] = c[0x1000 + t * 16 + 8 + r] = p1;
        }
    }
#if FC_DIAG_IMAGE
    memcpy(c,static_image_chr,8192);
#endif
    reset_map(info);
}

// ---- メニュー ----
// NROM(PRG 32KB + CHR 8KB)を組み立てる。配置は gen_menu_driver.py の説明のとおり。CHR は NSF プレイヤーのフォントとロゴ
void cart_load_menu(const lib_entry_t *e, int count, cart_info_t *info) {
#if CART_EXTENDED_ROM
    (void)select_rom_storage(0xA000);
#endif
    if (count > LIB_MAX_ITEMS)
        count = LIB_MAX_ITEMS;
    memset(active_rom, 0xFF, 0x8000);
    active_rom[MENUD_COUNT] = (uint8_t)count;
    for (int i = 0; i < count; i++) {
        uint32_t at = MENUD_TITLE_ADDR + i * MENUD_TITLE_LEN;
        active_rom[MENUD_PTR_LO + i] = at & 0xFF;
        active_rom[MENUD_PTR_HI + i] = at >> 8;
        uint8_t *t = active_rom + MENUD_TITLES + i * MENUD_TITLE_LEN;
        memset(t, ' ', MENUD_TITLE_LEN);
        for (int k = 0; k < MENUD_TITLE_LEN && k < (int)sizeof e[i].name && e[i].name[k]; k++) {
            char c = e[i].name[k];
            t[k] = (c >= 0x20 && c < 0x7F) ? c : '?';
        }
    }
    memcpy(active_rom + MENUD_NT, menud_nt, sizeof menud_nt);
    memcpy(active_rom + MENUD_CODE, menud_code, sizeof menud_code);     // ベクターまで入っている
    memcpy(active_rom + 0x8000, nsfd_chr, 0x1000);
    memcpy(active_rom + 0x9000, nsfd_chr, 0x1000);
    memset(info, 0, sizeof *info);
    info->prg_size = 0x8000;
    info->chr_size = 0x2000;
    info->vertical = true;
    info->is_menu = true;
    reset_map(info);
    is_menu = true;
    menu_count = (uint8_t)count;
    menu_request = 0xff;
    menu_choice = -1;
}

int cart_menu_choice(void) { return menu_choice; }

#ifndef CART_HOST
#if FC_DIAG_SPLIT
#include "split_diag.h"
#endif
#if FC_DIAG_LIVE
#include "hardware/irq.h"
#include "live_diag.h"
#endif
void cart_start(void) {
#if FC_DIAG_MMC3_GAME
    // Prioritize deadline-critical CPU/PPU access over core0's CHR-table copies.
    busctrl_hw->priority=
#if !FC_GAME_CPU_DMA
        BUSCTRL_BUS_PRIORITY_PROC1_BITS |
#endif
        BUSCTRL_BUS_PRIORITY_DMA_R_BITS | BUSCTRL_BUS_PRIORITY_DMA_W_BITS;
    while(!(busctrl_hw->priority_ack&BUSCTRL_BUS_PRIORITY_ACK_BITS))tight_loop_contents();
#endif
#if FC_DIAGNOSTIC
    puts("diag: cart_start entered");
#endif
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
#if FC_DIAG_SPLIT || FC_DIAG_LIVE || FC_DIAG_DIRECT_CHR
    if(!is_mmc3)rd_width_program_init(pio2,1,pio_add_program(pio2,&rd_width_program));
#endif
#if !FC_DIAG_MMC3_NO_IRQ
    if (is_mmc3)
        mmc3_a12_program_init(pio2, 1, pio_add_program(pio2, &mmc3_a12_program));
#if FC_DIAG_MMC3_GAME
    if(is_mmc3)mmc3_irq_core0_init();
#endif
#endif
#if FC_GAME_FAST_NROM
    if(nrom_replies)nrom_dma_start();
#if FC_GAME_BANKED_DMA
    else if(!is_nsf && !is_remote && !fds_is_fds)banked_dma_start();
#endif
    else {
#endif
#if FC_REMOTE_DMA
    ppu_lookup_program_init(pio1,0,pio_add_program(pio1,&ppu_lookup_program),(uint32_t)diag_chr_lookup);
    diag_dma_chr_init(NULL);
#elif FC_DIAG_DIRECT_CHR
#if FC_GAME_PROVEN_MMC3
    if(!is_mmc3) {
        ppu_chr_program_init(pio1,0,pio_add_program(pio1,&ppu_chr_program));
    } else {
#endif
#if FC_DIAG_DMA_CHR
    ppu_lookup_program_init(pio1,0,pio_add_program(pio1,&ppu_lookup_program),(uint32_t)diag_chr_lookup);
    diag_dma_chr_init(chr);
#else
    ppu_constant_program_init(pio1,0,pio_add_program(pio1,&ppu_constant_program));
#endif
#if FC_GAME_PROVEN_MMC3
    }
#endif
#else
    ppu_chr_program_init(pio1, 0, pio_add_program(pio1, &ppu_chr_program));
#endif
#if FC_GAME_FAST_NROM
    }
#endif
#if FC_GAME_PROVEN_MMC3
#if FC_GAME_CPU_DMA
    if(is_mmc3)cpu_rom_dma_start();
    else
#endif
    if(is_mmc3)cpu_m2_fast_program_init(pio0,0,pio_add_program(pio0,&cpu_m2_fast_program));
    else
#endif
    cpu_m2_program_init(pio0, 0, pio_add_program(pio0, &cpu_m2_program));
#if FC_DIAGNOSTIC
    puts("diag: PIO configured, starting core1");
#endif
    bus_ready = false;
#if FC_DIAG_SPLIT
    save_and_disable_interrupts();
    multicore_launch_core1(bus_loop);
#else
    multicore_launch_core1(is_remote ? remote_bus_loop : is_nsf ? nsf_bus_loop :
#if FC_GAME_CPU_DMA
        is_mmc3 ? cpu_dma_io_loop :
#endif
#if FC_GAME_PROVEN_MMC3
        is_mmc3 ? mmc3_proven_bus_loop :
#endif
#if FC_GAME_BANKED_DMA
        !fds_is_fds ? game_bus_loop :
#endif
        bus_loop);
#endif
    while (!bus_ready) tight_loop_contents();
    __dmb();
#if FC_DIAG_LIVE && !FC_DIAG_DIRECT_CHR
    live_ppu_irq_init();
#endif
#if !FC_DIAG_CPU_ONLY || FC_DIAG_SPLIT || FC_DIAG_LIVE || FC_DIAG_DIRECT_CHR
    pio_sm_set_enabled(pio1, 0, true);
#endif
#if FC_GAME_CPU_DMA
    if(is_mmc3)pio_set_sm_mask_enabled(pio0,15,true);
    else
#endif
    pio_sm_set_enabled(pio0, 0, true);
#if FC_DIAG_SPLIT
    split_ppu_loop(); // core0 PPU-only, core1 uses proven CPU-only service
#endif
#if FC_DIAGNOSTIC
    puts("diag: core1 ready, bus PIO enabled");
#endif
#if FC_DIAG_MMC3_GAME
    // Foreground on core0; core1 serves CPU and qualified A12 events.
#if FC_GAME_PROVEN_MMC3
    if(is_mmc3)
#endif
    mmc3_chr_background_loop();
#endif
}
#else
// PC の試験台から呼ぶ入口(PIO のサンプルと同じ形の値を渡し、答えを受け取る)
uint32_t cart_host_cpu(uint32_t v) {
#if FC_GAME_BANKED_DMA
    if(!is_nsf && !is_remote && !fds_is_fds) {
        if(wr_pending){game_bookkeeping(v);return NO_REPLY;}
        uint a=(v>>8)&0x7fff;uint32_t reply=0;
        if(v&B_RW) {
            if(!(v&B_ROMSEL))reply=0xff00|prg_map[a>>13][a&0x1fff];
            else if(a>=0x6000&&wram_enabled)reply=0xff00|wram[a&0x1fff];
            else if(is_menu&&a==0x5ff3)reply=0xff00|menu_request;
        }
        game_bookkeeping(v);return reply;
    }
#endif
#if FC_DIAG_MMC3_GAME
    if(!chr_is_ram) {
    if(wr_pending) {
        diag_nrom_bookkeeping(v);
        // Host comparison has instantaneous CHR mapping, no core0-copy timing.
        for(uint reg=0;reg<6;reg++)mmc3_fast_chr(reg);
        return NO_REPLY;
    }
    if(!(v&B_RW)){diag_nrom_bookkeeping(v);return 0;}
    }
#endif
    return is_remote ? remote_cpu_access(v) : is_nsf ? nsf_cpu_access(v) : cpu_access(v);
}
uint32_t cart_host_ppu(uint32_t v) { return is_remote ? remote_ppu_access(v) : ppu_access(v); }
void cart_host_a12_address(uint16_t addr,uint64_t ppu_ticks) {
    host_timed_a12=true;
    if(!is_mmc3)return;
    bool high=(addr&0x1000)!=0;
    uint64_t m2=ppu_ticks/3;
    if(!high && host_a12_high)host_a12_low_m2=m2;
    if(high && !host_a12_high && m2-host_a12_low_m2>=3)mmc3_clock();
    host_a12_high=high;
}
int cart_host_mirror(void) { return mir; }
uint8_t cart_host_peek_chr(uint a) {
    if (is_remote)                      // 画面転送: スプライトだけ(背景は位置を数える読み出しで描く)
        return (a & 0x1000) ? rd_spr[a & 0xFFF] : 0;
    return chr_map[(a >> 10) & 7][a & 0x3FF];
}   // 数えない読み出し(絵を描くだけの時)
#endif
