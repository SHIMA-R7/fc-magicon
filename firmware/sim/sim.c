// FC-MAGICON sim: magicon のカセットのロジック(magicon/cart.c)を PC で動かす試験台
//
//   sim.exe <game.nes | music.nsf> [オプション]
//     --native          agnes 自身のマッパーで動かす(比べる相手。.nes のマッパー 0/1/2/4 だけ)
//     --frames N        動かすフレーム数(既定 600 = 10 秒)
//     --shot-every K    K フレームごとに画面を BMP に書く(既定 60)
//     --press LIST      パッドを押す: "フレーム:ボタン:長さ,..."  ボタン = A B S(SELECT) T(START) U D L R の組み合わせ
//                       例 "120:T:5,300:R:3"
//     --out DIR         書き出す場所(既定 sim_out)
//     --wav             音を DIR/audio.wav に書く
//   DIR/hashes.txt に毎フレームの画面のハッシュを書く(native と magicon を比べるため)。
//
// magicon のモードでは、CPU の全サイクルと PPU の読み出しを、実機の PIO と同じ形の値にして cart.c に渡す
// (cart_host_cpu / cart_host_ppu)。つまり実機のファームウェアと同じコードのロジックを試す。
// 試せないのは PIO のタイミング(ナノ秒単位)だけ。
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "agnes.h"
#include "apu.h"
#include "cart.h"

bool magicon_on = true;
bool host_irq;
bool agnes_load_magicon(agnes_t *agnes);
static uint64_t n_irq_cycles;

// ---- agnes_magicon.c から呼ばれる差し込み口 ----
static uint32_t cpu_sample(uint16_t addr, bool rw, uint8_t data) {   // cpu_m2.pio が読む GPIO0-31 と同じ並び
    uint32_t v = ((uint32_t)(addr & 0x7FFF) << 8) | (1u << 25) | data;
    if (!(addr & 0x8000)) v |= 1u << 23;                          // /ROMSEL = !(A15 & M2)
    if (rw) v |= 1u << 24;
    return v;
}

int sim_cpu_read(uint16_t addr, uint64_t cycle) {
    if (magicon_on) {
        uint32_t r = cart_host_cpu(cpu_sample(addr, true, 0));
        if (((r >> 8) & 0xFF) == 0xFF) return r & 0xFF;          // カセットが出した
    }
    if (addr == 0x4015) return apu_status(cycle);
    return -1;
}

void sim_cpu_write(uint16_t addr, uint8_t val, uint64_t cycle) {
    if (addr >= 0x4000 && addr <= 0x4017) apu_write(addr, val, cycle);
    if (magicon_on) {
        cart_host_cpu(cpu_sample(addr, false, 0));                   // 1 回目: アドレス(M2 が上がった所)
        cart_host_cpu(cpu_sample(addr, false, val));                 // 2 回目: データ(M2 が下がった所)
    }
}

uint8_t sim_ppu_access(uint16_t addr) {                              // ppu_chr.pio: bit0-12 = アドレス、bit16 = A13
    uint32_t r = cart_host_ppu((addr & 0x1FFF) | ((addr & 0x2000) ? 1u << 16 : 0));
    return ((r >> 8) & 0xFF) == 0xFF ? (r & 0xFF) : 0;
}
uint8_t sim_ppu_peek(uint16_t addr) { return cart_host_peek_chr(addr & 0x1FFF); }
int sim_mirror(void) { return cart_host_mirror(); }
bool sim_irq(void) { return host_irq; }

// ---- 書き出し ----
static void write_bmp(const char *path, agnes_t *ag) {
    FILE *f = fopen(path, "wb");
    if (!f) return;
    const int W = AGNES_SCREEN_WIDTH, H = AGNES_SCREEN_HEIGHT, row = W * 3, size = 54 + row * H;
    uint8_t h[54] = {'B', 'M'};
    *(uint32_t *)(h + 2) = size; *(uint32_t *)(h + 10) = 54; *(uint32_t *)(h + 14) = 40;
    *(int32_t *)(h + 18) = W; *(int32_t *)(h + 22) = H; *(uint16_t *)(h + 26) = 1; *(uint16_t *)(h + 28) = 24;
    *(uint32_t *)(h + 34) = row * H;
    fwrite(h, 1, 54, f);
    uint8_t line[AGNES_SCREEN_WIDTH * 3];
    for (int y = H - 1; y >= 0; y--) {
        for (int x = 0; x < W; x++) {
            agnes_color_t c = agnes_get_screen_pixel(ag, x, y);
            line[x * 3] = c.b; line[x * 3 + 1] = c.g; line[x * 3 + 2] = c.r;
        }
        fwrite(line, 1, row, f);
    }
    fclose(f);
}

static uint64_t frame_hash(agnes_t *ag) {
    uint64_t h = 1469598103934665603ull;
    for (int y = 0; y < AGNES_SCREEN_HEIGHT; y++)
        for (int x = 0; x < AGNES_SCREEN_WIDTH; x++) {
            agnes_color_t c = agnes_get_screen_pixel(ag, x, y);
            h = (h ^ (c.r | c.g << 8 | c.b << 16)) * 1099511628211ull;
        }
    return h;
}

typedef struct { int frame, len; char buttons[9]; } press_t;

int main(int argc, char **argv) {
    const char *rom_path = NULL, *out = "sim_out", *press_list = "";
    int frames = 600, shot_every = 60;
    bool wav = false;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--native")) magicon_on = false;
        else if (!strcmp(argv[i], "--frames") && i + 1 < argc) frames = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--shot-every") && i + 1 < argc) shot_every = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--press") && i + 1 < argc) press_list = argv[++i];
        else if (!strcmp(argv[i], "--out") && i + 1 < argc) out = argv[++i];
        else if (!strcmp(argv[i], "--wav")) wav = true;
        else rom_path = argv[i];
    }
    if (!rom_path) {
        fprintf(stderr, "usage: sim <game.nes|music.nsf> [--native] [--frames N] [--shot-every K] [--press LIST] [--out DIR] [--wav]\n");
        return 2;
    }
    FILE *f = fopen(rom_path, "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", rom_path); return 2; }
    fseek(f, 0, SEEK_END);
    long len = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *data = malloc(len);
    fread(data, 1, len, f);
    fclose(f);

    press_t press[64];
    int npress = 0;
    for (const char *p = press_list; *p && npress < 64;) {
        press_t *q = &press[npress];
        memset(q, 0, sizeof *q);
        if (sscanf(p, "%d:%8[ABSTUDLR]:%d", &q->frame, q->buttons, &q->len) == 3) npress++;
        const char *c = strchr(p, ',');
        if (!c) break;
        p = c + 1;
    }

    agnes_t *ag = agnes_make();
    apu_init();
    cart_info_t info;
    if (magicon_on) {
        const char *err = cart_load(data, (uint32_t)len, &info);
        if (err) { fprintf(stderr, "magicon: %s\n", err); return 1; }
        if (info.is_nsf)
            printf("magicon: NSF \"%s\" %d songs  load $%04X init $%04X play $%04X%s\n", info.nsf_title, info.nsf_songs,
                   info.nsf_load, info.nsf_init, info.nsf_play, info.nsf_banked ? " banked" : "");
        else
            printf("magicon: mapper %d %s  PRG %uK  CHR %s%uK\n", info.mapper, cart_mapper_name(info.mapper),
                   info.prg_size / 1024, info.chr_size ? "" : "RAM ", (info.chr_size ? info.chr_size : 0x2000) / 1024);
        agnes_load_magicon(ag);
    } else if (!agnes_load_ines_data(ag, data, len)) {
        fprintf(stderr, "agnes: cannot load (mapper not supported by agnes?)\n");
        return 1;
    }

    char path[1024];
    snprintf(path, sizeof path, "%s/hashes.txt", out);
    FILE *hf = fopen(path, "w");
    if (!hf) { fprintf(stderr, "cannot write %s (does the folder exist?)\n", path); return 2; }
    uint32_t last_wr = 0;
    for (int fr = 1; fr <= frames; fr++) {
        agnes_input_t in = {0};
        for (int i = 0; i < npress; i++) {
            if (fr >= press[i].frame && fr < press[i].frame + press[i].len) {
                for (const char *b = press[i].buttons; *b; b++) {
                    switch (*b) {
                    case 'A': in.a = true; break;      case 'B': in.b = true; break;
                    case 'S': in.select = true; break; case 'T': in.start = true; break;
                    case 'U': in.up = true; break;     case 'D': in.down = true; break;
                    case 'L': in.left = true; break;   case 'R': in.right = true; break;
                    }
                }
            }
        }
        agnes_set_input(ag, &in, NULL);
        if (!agnes_next_frame(ag)) {
            fprintf(stderr, "frame %d: CPU stopped (illegal opcode)\n", fr);
            break;
        }
        if (host_irq) n_irq_cycles++;
        fprintf(hf, "%d %016llx\n", fr, (unsigned long long)frame_hash(ag));
        if (shot_every > 0 && fr % shot_every == 0) {
            snprintf(path, sizeof path, "%s/frame%05d.bmp", out, fr);
            write_bmp(path, ag);
        }
        if (fr % 60 == 0 && magicon_on) {
            printf("  frame %5d  cart writes %u\n", fr, stat_wr - last_wr);
            last_wr = stat_wr;
        }
    }
    fclose(hf);
    if (wav) {
        snprintf(path, sizeof path, "%s/audio.wav", out);
        apu_write_wav(path);
    }
    printf("done: %d frames, audio rms %.4f\n", frames, apu_rms());
    return 0;
}

