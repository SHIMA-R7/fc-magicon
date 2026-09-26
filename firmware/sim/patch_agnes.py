"""
agnes(agnes/agnes.c、MIT)に、magicon の cart.c をつなぐ差し込み口を足して agnes_magicon.c を作る。
    python patch_agnes.py
  magicon_on = true の時:
    ・CPU の読み書きは全部 sim.c の sim_cpu_read / sim_cpu_write を通す(カセットは全サイクルを見ている。$2002/$2007 の横読みのため)
      $4020 以上はカセットの答えだけを使い、agnes のマッパーは使わない
    ・PPU の $0000-$1FFF の読み出しは sim_ppu_access(= カセットの PIO1)。ネームテーブルの読み出しも A13 = 1 で流す(MMC3 の A12 を数えるため)
    ・スプライトの絵は agnes が 1 ドットごとに読むので、実機と同じ 257〜320 ドット目の読み出しを別に流し、絵を描く読み出しは数えない
    ・PPU の $0000-$1FFF への書き込みはカセットに届けない(実機の magicon は /WR ではアドレスが読めないため、$2006/$2007 の横読みで作る)
    ・ミラーリングはカセット(GPIO43 → CIRAM A10)の値、/IRQ はカセット(GPIO45)の値
  音(APU)は agnes に無いので、$4000-$4017 の書き込みを sim.c の APU に渡す(どちらのモードでも)。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
s = open(os.path.join(HERE, "agnes", "agnes.c"), encoding="utf-8").read()


def rep(old, new, count=1):
    global s
    assert s.count(old) == count, (old, s.count(old))
    s = s.replace(old, new)


rep('#endif /* _MSC_VER */\n\n#include "agnes.h"\n', '''#endif /* _MSC_VER */

#include "agnes.h"

/* ---- FC-MAGICON sim: magicon の cart.c をつなぐ差し込み口(patch_agnes.py が足した) ---- */
extern bool magicon_on;
int sim_cpu_read(uint16_t addr, uint64_t cycle);        /* -1 = カセットは出さない(本体側に任せる) */
void sim_cpu_write(uint16_t addr, uint8_t val, uint64_t cycle);
uint8_t sim_ppu_access(uint16_t addr);                  /* PPU バスの読み出し(数える) */
uint8_t sim_ppu_peek(uint16_t addr);                    /* 絵を描くだけ(数えない) */
int sim_mirror(void);                                   /* cart.c のミラーリング: 0 水平 1 垂直 2/3 1画面 */
bool sim_irq(void);
''')

# CPU の書き込み
rep('''void cpu_write8(cpu_t *cpu, uint16_t addr, uint8_t val) {
    agnes_t *agnes = cpu->agnes;
''', '''void cpu_write8(cpu_t *cpu, uint16_t addr, uint8_t val) {
    agnes_t *agnes = cpu->agnes;

    sim_cpu_write(addr, val, cpu->cycles);              /* magicon と APU */
    if (magicon_on && addr >= 0x4020) {
        return;
    }
''')
# CPU の読み出し
rep('''uint8_t cpu_read8(cpu_t *cpu, uint16_t addr) {
    agnes_t *agnes = cpu->agnes;

    uint8_t res = 0;
''', '''uint8_t cpu_read8(cpu_t *cpu, uint16_t addr) {
    agnes_t *agnes = cpu->agnes;

    int ext = sim_cpu_read(addr, cpu->cycles);          /* magicon(全サイクル)と APU の $4015 */
    if (ext >= 0) {
        return (uint8_t)ext;
    }
    if (magicon_on && addr >= 0x4020) {
        return (uint8_t)(addr >> 8);                    /* カセットが出さない = オープンバス */
    }
    uint8_t res = 0;
''')

# PPU の読み書き
rep('''    } else if (addr < 0x2000) { // $0000 - $1FFF
        res = mapper_read(ppu->agnes, addr);
    } else { // $2000 - $3EFF
        uint16_t mirrored_addr = mirror_address(ppu, addr);
        res = ppu->nametables[mirrored_addr];
    }''', '''    } else if (addr < 0x2000) { // $0000 - $1FFF
        res = magicon_on ? sim_ppu_access(addr) : mapper_read(ppu->agnes, addr);
    } else { // $2000 - $3EFF
        if (magicon_on) {
            sim_ppu_access(addr);                       /* A13 = 1 の読み出しもカセットには見える */
        }
        uint16_t mirrored_addr = mirror_address(ppu, addr);
        res = ppu->nametables[mirrored_addr];
    }''')
rep('''    } else if (addr < 0x2000) { // $0000 - $1FFF
        mapper_write(ppu->agnes, addr, val);''', '''    } else if (addr < 0x2000) { // $0000 - $1FFF
        if (!magicon_on) {                              /* magicon には /WR のアドレスは見えない */
            mapper_write(ppu->agnes, addr, val);
        }''')
# ミラーリングは読み書きどちらでもカセットの値を使う(mirror_address は読み書きの両方から呼ばれる)
rep('''static uint16_t mirror_address(ppu_t *ppu, uint16_t addr) {
    switch (ppu->agnes->mirroring_mode)''', '''static uint16_t mirror_address(ppu_t *ppu, uint16_t addr) {
    if (magicon_on) {
        static const mirroring_mode_t m[4] = {MIRRORING_MODE_HORIZONTAL, MIRRORING_MODE_VERTICAL,
                                              MIRRORING_MODE_SINGLE_LOWER, MIRRORING_MODE_SINGLE_UPPER};
        int mi = sim_mirror();
        ppu->agnes->mirroring_mode = m[(mi >= 0 && mi < 4) ? mi : 0];
    }
    switch (ppu->agnes->mirroring_mode)''')# スプライトの絵(1 ドットごと)は数えない
rep('''        uint8_t lo_byte = ppu_read8(ppu, offset);
        uint8_t hi_byte = ppu_read8(ppu, offset + 8);''', '''        uint8_t lo_byte = magicon_on ? sim_ppu_peek(offset) : ppu_read8(ppu, offset);
        uint8_t hi_byte = magicon_on ? sim_ppu_peek(offset + 8) : ppu_read8(ppu, offset + 8);''')
# 実機と同じスプライトの読み出し(257〜320)と、ラインの最後のネームテーブル読み出し(337, 339)
rep('''    if (ppu->dot == 257) {
        // v: |_...|.F..| |...E|DCBA| = t: |_...|.F..| |...E|DCBA|''', '''    if (magicon_on && ppu->dot >= 257 && ppu->dot <= 320) {
        int slot = (ppu->dot - 257) / 8, ph = (ppu->dot - 257) & 7;
        if (ph == 0 || ph == 2) {
            sim_ppu_access(0x2000);                     /* 使われないネームテーブル・属性の読み出し */
        } else if (ph == 4 || ph == 6) {
            unsigned tile = 0xFF, table = ppu->ctrl.sprite_table_addr;
            if (ppu->dot > 257 && slot < ppu->sprite_ixs_count) {
                tile = ppu->sprites[slot].tile_num;
            }
            if (ppu->ctrl.use_8x16_sprites) {
                table = (tile & 1) ? 0x1000 : 0x0000;
                tile &= 0xFE;
            }
            sim_ppu_access((uint16_t)(table + tile * 16 + (ph == 6 ? 8 : 0)));
        }
    }
    if (magicon_on && (ppu->dot == 337 || ppu->dot == 339)) {
        sim_ppu_access(0x2000 | (ppu->regs.v & 0x0fff));
    }

    if (ppu->dot == 257) {
        // v: |_...|.F..| |...E|DCBA| = t: |_...|.F..| |...E|DCBA|''')
# /IRQ
rep('''bool agnes_tick(agnes_t *agnes, bool *out_new_frame) {
    int cpu_cycles = cpu_tick(&agnes->cpu);''', '''bool agnes_tick(agnes_t *agnes, bool *out_new_frame) {
    if (magicon_on && sim_irq()) {
        cpu_trigger_irq(&agnes->cpu);                   /* /IRQ はレベル。I フラグが立っていれば agnes が無視する */
    }
    int cpu_cycles = cpu_tick(&agnes->cpu);''')
# magicon で起動する入口
rep('''void agnes_set_input(agnes_t *agn, const agnes_input_t *input_1, const agnes_input_t *input_2) {''',
    '''/* magicon: マッパーは使わない(gamepack.mapper = 255 で agnes のマッパーはすべて何もしない) */
bool agnes_load_magicon(agnes_t *agnes) {
    agnes->gamepack.mapper = 255;
    agnes->mirroring_mode = MIRRORING_MODE_HORIZONTAL;
    cpu_init(&agnes->cpu, agnes);
    ppu_init(&agnes->ppu, agnes);
    return true;
}

void agnes_set_input(agnes_t *agn, const agnes_input_t *input_1, const agnes_input_t *input_2) {''')

s = "/* agnes_magicon.c: patch_agnes.py が agnes/agnes.c(MIT、https://github.com/kgabis/agnes)から作ったもの。手で直さない */\n" + s
open(os.path.join(HERE, "agnes_magicon.c"), "w", encoding="utf-8").write(s)
print("-> agnes_magicon.c")


