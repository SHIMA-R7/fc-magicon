// FC-MAGICON sim: ファミコン本体の音源(2A03 の APU)を真似て WAV に書く。agnes には音が無いので、ここで作る。
//   パルス 2ch(デューティ・エンベロープ・スイープ・長さ)、三角波(線形カウンター)、ノイズ。DMC(サンプル)は鳴らさない。
//   CPU の書き込みを CPU サイクルの時刻つきで受け取り、その時刻まで 1 サイクルずつ進めてから反映する。
//   出力は 44.1kHz、非線形ミキサー(nesdev の式)、本体と同じくらいの直流カット(約 90Hz)。
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "apu.h"

#define CPU_HZ 1789773.0
#define RATE 44100

static const uint8_t LEN[32] = {10, 254, 20, 2, 40, 4, 80, 6, 160, 8, 60, 10, 14, 12, 26, 14,
                                12, 16, 24, 18, 48, 20, 96, 22, 192, 24, 72, 26, 16, 28, 32, 30};
static const uint8_t DUTY[4][8] = {{0, 1, 0, 0, 0, 0, 0, 0}, {0, 1, 1, 0, 0, 0, 0, 0},
                                   {0, 1, 1, 1, 1, 0, 0, 0}, {1, 0, 0, 1, 1, 1, 1, 1}};
static const uint16_t NOISE[16] = {4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068};

typedef struct {                        // エンベロープ(パルスとノイズ)
    int start, div, decay, loop, constant, vol;
} env_t;

typedef struct {
    int enabled, duty, seq, timer, period, len;
    env_t env;
    int sw_en, sw_period, sw_neg, sw_shift, sw_reload, sw_div, ones_complement;
} pulse_t;

static pulse_t p[2];
static struct { int enabled, control, reload_val, lin, reload, timer, period, step, len; } tri;
static struct { int enabled, mode, timer, period, len; uint16_t lfsr; env_t env; } noi;
static int frame_mode, frame_cycle;
static uint64_t now;                    // 何サイクル目まで進めたか
static double acc, acc_n, next_sample = CPU_HZ / RATE, hp_prev_in, hp_prev_out;
static int16_t *buf;
static size_t nbuf, capbuf;

static void env_clock(env_t *e) {
    if (e->start) {
        e->start = 0;
        e->decay = 15;
        e->div = e->vol;
    } else if (e->div == 0) {
        e->div = e->vol;
        if (e->decay > 0) e->decay--;
        else if (e->loop) e->decay = 15;
    } else {
        e->div--;
    }
}
static int env_out(const env_t *e) { return e->constant ? e->vol : e->decay; }

static int sweep_target(const pulse_t *q) {
    int change = q->period >> q->sw_shift;
    return q->sw_neg ? q->period - change - q->ones_complement : q->period + change;
}
static int pulse_muted(const pulse_t *q) { return q->period < 8 || sweep_target(q) > 0x7FF; }

static void quarter(void) {
    env_clock(&p[0].env);
    env_clock(&p[1].env);
    env_clock(&noi.env);
    if (tri.reload) tri.lin = tri.reload_val;
    else if (tri.lin > 0) tri.lin--;
    if (!tri.control) tri.reload = 0;
}
static void half(void) {
    for (int i = 0; i < 2; i++) {
        pulse_t *q = &p[i];
        if (!q->env.loop && q->len > 0) q->len--;
        if (q->sw_div == 0 && q->sw_en && q->sw_shift && !pulse_muted(q)) q->period = sweep_target(q);
        if (q->sw_div == 0 || q->sw_reload) { q->sw_div = q->sw_period; q->sw_reload = 0; }
        else q->sw_div--;
    }
    if (!tri.control && tri.len > 0) tri.len--;
    if (!noi.env.loop && noi.len > 0) noi.len--;
}

static void step(void) {                // CPU 1 サイクル
    frame_cycle++;
    if (frame_mode == 0) {
        if (frame_cycle == 7457 || frame_cycle == 22371) quarter();
        else if (frame_cycle == 14913) { quarter(); half(); }
        else if (frame_cycle == 29829) { quarter(); half(); }
        if (frame_cycle >= 29830) frame_cycle = 0;
    } else {
        if (frame_cycle == 7457 || frame_cycle == 22371) quarter();
        else if (frame_cycle == 14913 || frame_cycle == 37281) { quarter(); half(); }
        if (frame_cycle >= 37282) frame_cycle = 0;
    }
    if (now & 1) {                      // パルスのタイマーは 2 サイクルに 1 回
        for (int i = 0; i < 2; i++) {
            pulse_t *q = &p[i];
            if (q->timer == 0) { q->timer = q->period; q->seq = (q->seq + 1) & 7; }
            else q->timer--;
        }
    }
    if (tri.timer == 0) {
        tri.timer = tri.period;
        if (tri.len > 0 && tri.lin > 0 && tri.period >= 2) tri.step = (tri.step + 1) & 31;
    } else {
        tri.timer--;
    }
    if (noi.timer == 0) {
        noi.timer = noi.period;
        int fb = (noi.lfsr & 1) ^ ((noi.lfsr >> (noi.mode ? 6 : 1)) & 1);
        noi.lfsr = (noi.lfsr >> 1) | (fb << 14);
    } else {
        noi.timer--;
    }

    int po[2];
    for (int i = 0; i < 2; i++) {
        pulse_t *q = &p[i];
        po[i] = (q->len == 0 || pulse_muted(q) || !DUTY[q->duty][q->seq]) ? 0 : env_out(&q->env);
    }
    int t = tri.step < 16 ? 15 - tri.step : tri.step - 16;
    int n = (noi.len == 0 || (noi.lfsr & 1)) ? 0 : env_out(&noi.env);
    double pulse = (po[0] + po[1]) ? 95.88 / (8128.0 / (po[0] + po[1]) + 100.0) : 0.0;
    double tnd = (t || n) ? 159.79 / (1.0 / (t / 8227.0 + n / 12241.0) + 100.0) : 0.0;
    acc += pulse + tnd;
    acc_n += 1;
    now++;
    if (now >= next_sample) {           // 44.1kHz に間引く(平均)
        next_sample += CPU_HZ / RATE;
        double x = acc / acc_n;
        acc = acc_n = 0;
        double y = 0.987 * (hp_prev_out + x - hp_prev_in);   // 直流カット(約 90Hz)
        hp_prev_in = x;
        hp_prev_out = y;
        int v = (int)(y * 40000.0);
        if (v > 32767) v = 32767;
        if (v < -32768) v = -32768;
        if (nbuf == capbuf) {
            capbuf = capbuf ? capbuf * 2 : RATE * 8;
            buf = realloc(buf, capbuf * sizeof *buf);
        }
        buf[nbuf++] = (int16_t)v;
    }
}

void apu_run(uint64_t cycle) {
    while (now < cycle) step();
}

void apu_init(void) {
    memset(p, 0, sizeof p);
    memset(&tri, 0, sizeof tri);
    memset(&noi, 0, sizeof noi);
    noi.lfsr = 1;
    noi.period = NOISE[0];
    p[0].ones_complement = 1;           // パルス 1 のスイープは 1 の補数
    frame_mode = frame_cycle = 0;
}

void apu_write(uint16_t addr, uint8_t d, uint64_t cycle) {
    apu_run(cycle);
    if (addr < 0x4008) {
        pulse_t *q = &p[(addr >> 2) & 1];
        switch (addr & 3) {
        case 0: q->duty = d >> 6; q->env.loop = (d >> 5) & 1; q->env.constant = (d >> 4) & 1; q->env.vol = d & 15; break;
        case 1: q->sw_en = d >> 7; q->sw_period = (d >> 4) & 7; q->sw_neg = (d >> 3) & 1; q->sw_shift = d & 7; q->sw_reload = 1; break;
        case 2: q->period = (q->period & 0x700) | d; break;
        case 3:
            q->period = (q->period & 0xFF) | ((d & 7) << 8);
            if (q->enabled) q->len = LEN[d >> 3];
            q->seq = 0;
            q->env.start = 1;
            break;
        }
    } else if (addr == 0x4008) {
        tri.control = d >> 7;
        tri.reload_val = d & 0x7F;
    } else if (addr == 0x400A) {
        tri.period = (tri.period & 0x700) | d;
    } else if (addr == 0x400B) {
        tri.period = (tri.period & 0xFF) | ((d & 7) << 8);
        if (tri.enabled) tri.len = LEN[d >> 3];
        tri.reload = 1;
    } else if (addr == 0x400C) {
        noi.env.loop = (d >> 5) & 1; noi.env.constant = (d >> 4) & 1; noi.env.vol = d & 15;
    } else if (addr == 0x400E) {
        noi.mode = d >> 7;
        noi.period = NOISE[d & 15];
    } else if (addr == 0x400F) {
        if (noi.enabled) noi.len = LEN[d >> 3];
        noi.env.start = 1;
    } else if (addr == 0x4015) {
        p[0].enabled = d & 1; p[1].enabled = (d >> 1) & 1; tri.enabled = (d >> 2) & 1; noi.enabled = (d >> 3) & 1;
        if (!p[0].enabled) p[0].len = 0;
        if (!p[1].enabled) p[1].len = 0;
        if (!tri.enabled) tri.len = 0;
        if (!noi.enabled) noi.len = 0;
    } else if (addr == 0x4017) {
        frame_mode = d >> 7;
        frame_cycle = 0;
        if (frame_mode) { quarter(); half(); }
    }
}

uint8_t apu_status(uint64_t cycle) {
    apu_run(cycle);
    return (p[0].len > 0) | (p[1].len > 0) << 1 | (tri.len > 0) << 2 | (noi.len > 0) << 3;
}

// 鳴った音の大きさ(RMS、-1〜1 の範囲)。無音かどうかの確認用
double apu_rms(void) {
    double s = 0;
    for (size_t i = 0; i < nbuf; i++) s += (double)buf[i] * buf[i];
    return nbuf ? sqrt(s / nbuf) / 32768.0 : 0;
}

int apu_write_wav(const char *path) {
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    uint32_t data = (uint32_t)(nbuf * 2), rate = RATE, brate = RATE * 2, v32;
    uint16_t v16;
    fwrite("RIFF", 1, 4, f); v32 = 36 + data; fwrite(&v32, 4, 1, f); fwrite("WAVEfmt ", 1, 8, f);
    v32 = 16; fwrite(&v32, 4, 1, f); v16 = 1; fwrite(&v16, 2, 1, f); fwrite(&v16, 2, 1, f);
    fwrite(&rate, 4, 1, f); fwrite(&brate, 4, 1, f); v16 = 2; fwrite(&v16, 2, 1, f); v16 = 16; fwrite(&v16, 2, 1, f);
    fwrite("data", 1, 4, f); fwrite(&data, 4, 1, f); fwrite(buf, 2, nbuf, f);
    fclose(f);
    return 0;
}
