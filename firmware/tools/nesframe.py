"""
PC の画像を、magicon の画面転送モードの 1 枚(256 x 240、2 ビット + パレット 32 + 属性 64)にする。
  from nesframe import encode, write_frame
  frame = encode(img, mode="gray" | "color")      # img = PIL.Image(RGB、256 x 240)
  frame.fb(15360 バイト)、frame.pal(32)、frame.attr(64)、frame.preview(ファミコンで見える絵、PIL.Image)

色:
  gray  = 全体で 黒・濃い灰・薄い灰・白 の 4 階調(文字がいちばん読みやすい)
  color = 背景の 1 色(いちばん多い色。上下の黒い帯は数えない)+ 3 色 x 4 組のパレット。16 x 16 ドットごとに 4 組のどれかを選ぶ
          組の中身: その組の区画でよく使われる色を候補に、3 つの枠を 1 つずつ入れ替えて誤差が減る時だけ採る
          区画の割り当て: 上下左右の区画と違う組には罰点(SMOOTH)を足して、16 ドットのまだら模様を減らす
          ディザ(Bayer 4 x 4)で 4 色の中間を点の混ぜ方で出す。動画では前の画面の組から探す(prev、チラつき防止)
          (2026-09-27 に比べた結果: 境目の段差 1.45 → 1.26、誤差はほぼ同じ。「ディザの中間色も出せる」として組を探す _mix は写真で悪くなったので使わない)
          色の近さは CIELAB の距離で測る(RGB の距離だと暗い緑が茶色に寄る)
ファミコンの色(RGB)は agnes(sim/agnes/agnes.c)の表を使う(PC の試験台の画面とドット単位で比べられるように)。
"""
import os
import re
import struct

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))


def _nes_colors():
    src = open(os.path.join(HERE, "..", "sim", "agnes", "agnes.c"), encoding="utf-8").read()
    body = src[src.index("g_colors[64]"):]
    body = body[:body.index("};")]
    cols = re.findall(r"\{0x([0-9a-f]{2}), 0x([0-9a-f]{2}), 0x([0-9a-f]{2}), 0x([0-9a-f]{2})\}", body)
    return np.array([[int(r, 16), int(g, 16), int(b, 16)] for r, g, b, _ in cols], dtype=np.int32)


NES = _nes_colors()                               # 64 色


def lab(rgb):
    """RGB(0〜255)→ CIELAB"""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]])
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


NES_LAB = lab(NES)
# 使う色: $0D(黒より黒い)と $xE/$xF(黒の重複)を除く。黒は $0F
USABLE = [i for i in range(64) if (i & 0x0F) < 0x0D and i != 0x0D] + [0x0F]
GRAY = [0x0F, 0x00, 0x10, 0x30]


def _luts():
    """RGB 各 5 ビット(32768 通り)→ いちばん近いファミコンの色、と Lab の表(速くするため 1 回だけ作る)"""
    v = (np.arange(32) * 255 // 31)
    rgb = np.stack(np.meshgrid(v, v, v, indexing="ij"), -1).reshape(-1, 3)   # (r << 10) | (g << 5) | b の順
    lab_all = lab(rgb)
    cand = NES_LAB[USABLE]
    near = np.empty(len(rgb), dtype=np.int64)
    for s in range(0, len(rgb), 4096):
        d = ((lab_all[s:s + 4096, None, :] - cand[None, :, :]) ** 2).sum(-1)
        near[s:s + 4096] = np.array(USABLE)[d.argmin(-1)]
    return near, lab_all


NEAR_LUT, LAB_LUT = _luts()


class Frame:
    def __init__(self, idx, pal, attr):
        self.idx, self.pal, self.attr = idx, pal, attr          # idx = 240 x 256 の 0〜3
        self.fb = pack(idx)
        self.preview = render(idx, pal, attr)


def pack(idx):
    """0〜3 の 240 x 256 を、fb[((行 * 8 + y) * 32 + 列) * 2 + 面] の並びにする"""
    b0 = np.packbits((idx & 1).astype(np.uint8), axis=1)         # 240 x 32(左が MSB)
    b1 = np.packbits((idx >> 1).astype(np.uint8), axis=1)
    return np.stack([b0, b1], axis=-1).reshape(-1).tobytes()     # (y, 列, 面) = (行 * 8 + y, 列, 面)


def attr_of(block_pal):
    """16 x 16 区画ごとのパレット番号(15 x 16)→ 属性テーブル 64 バイト"""
    attr = bytearray(64)
    for by in range(15):
        for bx in range(16):
            q = ((by & 1) << 1) | (bx & 1)
            attr[(by // 2) * 8 + bx // 2] |= (int(block_pal[by, bx]) & 3) << (q * 2)
    return bytes(attr)


def render(idx, pal, attr):
    """ファミコンで見える絵(属性とパレットを使って色を付ける)"""
    bp = np.zeros((15, 16), dtype=np.int32)
    for by in range(15):
        for bx in range(16):
            bp[by, bx] = (attr[(by // 2) * 8 + bx // 2] >> ((((by & 1) << 1) | (bx & 1)) * 2)) & 3
    pix_pal = np.repeat(np.repeat(bp, 16, 0), 16, 1)             # 240 x 256
    color_ix = np.where(idx == 0, pal[0], np.array(pal)[(pix_pal * 4 + idx)])
    return Image.fromarray(NES[color_ix].astype(np.uint8))


# 規則的なディザ(Bayer 4 x 4)。場所で決まる -0.5〜+0.5 のずれ。誤差拡散と違い、絵が少し動いても点の並びが変わらない
BAYER = np.tile((np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) + 0.5) / 16 - 0.5, (60, 64))
DITHER_RGB = 48                                             # カラーのずれの幅(RGB の 0〜255 で)
DITHER_GRAY = 64                                            # 灰色のずれの幅(明るさ。4 階調の間隔くらい)


MIX_COST = 20                                               # ディザで 2 色を混ぜて出す色の、ぴったりの色に対する割増し(Lab の距離の 2 乗)
SMOOTH = 40                                                 # 隣の区画と違う組を選ぶ罰点(1 点あたり Lab の距離の 2 乗に換算。0 = そろえない)


def _seg_table():
    """SEG[c, i, j] = 色 c から「色 i と色 j を結ぶ線」(ディザで混ぜて出せる色)までの距離の 2 乗 + MIX_COST。
    SEG[c, i, i] は色 i そのものまでの距離の 2 乗。組の良し悪しを何度も測るので、最初に 1 回だけ作る"""
    P = NES_LAB
    d = P[None, :, :] - P[:, None, :]                          # d[i, j] = P[j] - P[i]
    L = (d * d).sum(-1)
    rel = P[:, None, :] - P[None, :, :]                        # rel[c, i] = P[c] - P[i]
    t = np.einsum("cik,ijk->cij", rel, d) / np.where(L > 0, L, 1)[None]
    t = np.clip(t, 0, 1)
    proj = P[None, :, None, :] + t[..., None] * d[None]       # [c, i, j]
    seg = ((P[:, None, None, :] - proj) ** 2).sum(-1) + MIX_COST
    pt = ((P[:, None, :] - P[None, :, :]) ** 2).sum(-1)        # [c, i]
    idx = np.arange(64)
    seg[:, idx, idx] = pt
    return seg, pt


def _palette_err(opts, dither):
    """64 色それぞれを、この組(背景 + 3 色)で表した時の誤差。ディザありなら 2 色を結ぶ線上の色も出せるとする"""
    o = np.asarray(opts)
    if dither:
        return SEG[:, o][:, :, o].reshape(64, -1).min(1)
    return PT[:, o].min(1)


SEG, PT = _seg_table()


def _smooth_choice(err, lam, rounds=4):
    """区画ごとの組を選ぶ。上下左右の区画と違う組には lam の罰点を足して、まだら模様を減らす"""
    choice = err.argmin(-1)
    if lam <= 0:
        return choice
    for _ in range(rounds):
        pen = np.zeros_like(err)
        for axis, shift in ((0, 1), (0, -1), (1, 1), (1, -1)):
            nb = np.roll(choice, shift, axis)
            valid = np.ones_like(choice, dtype=bool)          # 端では回り込んだ隣を数えない
            if axis == 0:
                valid[0 if shift == 1 else -1, :] = False
            else:
                valid[:, 0 if shift == 1 else -1] = False
            for k in range(4):
                pen[..., k] += lam * (valid & (nb != k))
        choice = (err + pen).argmin(-1)
    return choice


def _search_palettes(hist_all, bg, dither, lam, iters, init, legacy=False, mix=True):
    """背景 bg のもとで 4 組(3 色ずつ)と区画の割り当てを探す。戻り値 = (組, 割り当て 15 x 16, 総コスト)
    組の中身は、その組の区画でよく使われる色を候補に、3 つの枠を 1 つずつ入れ替えて誤差が減る時だけ採る(ディザの中間色も含めて測る)。
    legacy = 以前のやり方(上位 3 色、点の距離だけ)。比べる時だけ使う"""
    hist = hist_all.copy()
    hist[..., bg] = 0
    if init is not None:
        pals = [list(p) for p in init]
    else:
        order = np.argsort(-hist.reshape(-1, 64).sum(0))
        pals = [([int(c) for c in order[k * 3:k * 3 + 3]] + [bg] * 3)[:3] for k in range(4)]
    d = dither and mix and not legacy

    def block_err(p):                                           # 区画ごとの誤差(15 x 16)
        return (hist * _palette_err([bg] + p, d)[None, None, :]).sum(-1)

    for _ in range(iters):
        err = np.stack([block_err(p) for p in pals], -1)
        choice = _smooth_choice(err, lam)                       # 隣の区画とそろえる(違う組を選ぶと罰点)
        for k in range(4):
            mask = choice == k
            if legacy:
                h = hist[mask].sum(0) if mask.any() else np.zeros(64)
                pals[k] = ([int(c) for c in np.argsort(-h)[:3] if h[c] > 0] + [bg] * 3)[:3]
                continue
            if not mask.any():                                  # 使われていない組: いちばん合っていない区画の色で作り直す
                worst = np.unravel_index(np.take_along_axis(err, choice[..., None], -1)[..., 0].argmax(), (15, 16))
                h = hist[worst]
                pals[k] = ([int(c) for c in np.argsort(-h)[:3] if h[c] > 0] + [bg] * 3)[:3]
                continue
            hk = hist[mask]                                     # この組の区画の色の数(n x 64)
            tot = hk.sum(0)
            cand = [int(c) for c in np.argsort(-tot)[:8] if tot[c] > 0]
            best = float((hk @ _palette_err([bg] + pals[k], d)).sum())
            improved = True
            while improved:
                improved = False
                for s in range(3):
                    for c in cand:
                        if c in pals[k] or c == bg:
                            continue
                        trial = pals[k][:s] + [c] + pals[k][s + 1:]
                        e = float((hk @ _palette_err([bg] + trial, d)).sum())
                        if e < best - 1e-6:
                            best, pals[k], improved = e, trial, True
    err = np.stack([block_err(p) for p in pals], -1)
    choice = _smooth_choice(err, lam)
    cost = float(np.take_along_axis(err, choice[..., None], -1).sum())
    cost += lam * ((choice[1:] != choice[:-1]).sum() + (choice[:, 1:] != choice[:, :-1]).sum())
    return pals, choice, cost


def encode(img, mode="gray", iters=4, dither=None, smooth=None, prev=None, _bg_mode="nobar", _legacy=False, _mix=False):
    """dither: None = カラーはあり・灰色はなし(文字を読みやすく)。smooth: 隣の区画とそろえる強さ(None = SMOOTH)
    prev: 前の画面の Frame(組をそこから探し始める。動画でパレットが毎回変わってチラつくのを防ぐ)"""
    if dither is None:
        dither = mode == "color"
    a = np.asarray(img.convert("RGB").resize((256, 240)), dtype=np.int32)
    if mode == "gray":
        lum = (a[..., 0] * 299 + a[..., 1] * 587 + a[..., 2] * 114) / 1000
        if dither:
            lum = lum + BAYER * DITHER_GRAY
        levels = NES[GRAY].mean(1)                              # 4 階調の明るさ
        idx = np.abs(lum[..., None] - levels[None, None, :]).argmin(-1)
        pal = GRAY * 8
        pal[17:20] = [0x30, 0x0F, 0x0F]                          # スプライト(カーソル): 白 + 黒のふち
        fr = Frame(idx, pal, bytes(64))
        fr.pals = None
        return fr

    # 各点をファミコンの色に(Lab の距離。RGB 各 5 ビットの表を引く)
    q = ((a[..., 0] >> 3) << 10) | ((a[..., 1] >> 3) << 5) | (a[..., 2] >> 3)
    near = NEAR_LUT[q]                                          # 240 x 256 の色番号
    al = LAB_LUT[q]                                             # 各点の Lab
    # 区画(16 x 16)ごとの色の数
    block_id = (np.arange(240)[:, None] // 16) * 16 + (np.arange(256)[None, :] // 16)
    hist_all = np.bincount((block_id * 64 + near).ravel(), minlength=240 * 64).reshape(15, 16, 64).astype(np.int64)
    lam = (SMOOTH if smooth is None else smooth) * 256
    # 共通の背景の色: 上下の黒い帯(画面全体を縮めた時)は数えずに、多い色から
    content = ~(a == 0).all(-1).all(-1)                         # 全部黒の行 = 帯
    counts = np.bincount(near[content].ravel(), minlength=64) if content.any() else np.bincount(near.ravel(), minlength=64)
    if _bg_mode == "freq":
        cands = [int(np.bincount(near.ravel(), minlength=64).argmax())]
    elif _bg_mode == "best4" and prev is None:
        cands = [int(c) for c in np.argsort(-counts)[:4] if counts[c] > 0]
    elif prev is not None:
        cands = [prev.pal[0]]                                   # 動画では前の画面と同じ背景(チラつかないように)
    else:
        cands = [int(counts.argmax())]
    best_run = None
    for bg in cands:
        init = [list(p) for p in prev.pals] if prev is not None else None
        run = _search_palettes(hist_all, bg, dither, lam, iters if len(cands) == 1 else 2, init, _legacy, _mix)
        if best_run is None or run[2] < best_run[2]:
            best_run = run + (bg,)
    pals, choice, _, bg = best_run
    if len(cands) > 1:                                          # 背景を決めてから、もう少し探す
        pals, choice, _ = _search_palettes(hist_all, bg, dither, lam, iters, pals, _legacy, _mix)
    pal = []
    for k in range(4):
        pal += [bg] + [int(c) for c in pals[k]]
    pal += [bg, 0x30, 0x0F, 0x0F] * 4                           # スプライト(カーソル)
    # 各点を、その区画の組の 4 色のどれかに(ディザありなら、場所で決まるずれを足してから選ぶ → 4 色の中間を点の混ぜ方で出す)
    if dither:
        ad = np.clip(a + (BAYER * DITHER_RGB)[..., None], 0, 255).astype(np.int32)
        al = LAB_LUT[((ad[..., 0] >> 3) << 10) | ((ad[..., 1] >> 3) << 5) | (ad[..., 2] >> 3)]
    bp = np.repeat(np.repeat(choice, 16, 0), 16, 1)
    idx = np.zeros((240, 256), dtype=np.int32)
    best = np.full((240, 256), np.inf)
    for j in range(4):
        cj = np.array([pal[k * 4 + j] for k in range(4)])[bp]  # この点の組の j 番目の色
        e = ((al - NES_LAB[cj]) ** 2).sum(-1)
        better = e < best
        idx[better] = j
        best[better] = e[better]
    fr = Frame(idx, pal, attr_of(choice))
    fr.pals = pals
    return fr


def write_frame(path, frame, cursor=(0, 0, False)):
    """sim.exe --remote-frame 用: fb 15360 + pal 32 + attr 64 + カーソル x, y, visible(各 1 バイト)"""
    with open(path, "wb") as f:
        f.write(frame.fb + bytes(frame.pal) + frame.attr + struct.pack("BBB", cursor[0] & 255, cursor[1] & 255, int(cursor[2])))
