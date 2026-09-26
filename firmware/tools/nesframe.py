"""
PC の画像を、magicon の画面転送モードの 1 枚(256 x 240、2 ビット + パレット 32 + 属性 64)にする。
  from nesframe import encode, write_frame
  frame = encode(img, mode="gray" | "color")      # img = PIL.Image(RGB、256 x 240)
  frame.fb(15360 バイト)、frame.pal(32)、frame.attr(64)、frame.preview(ファミコンで見える絵、PIL.Image)

色:
  gray  = 全体で 黒・濃い灰・薄い灰・白 の 4 階調(文字がいちばん読みやすい)
  color = 背景の 1 色(いちばん多い色)+ 3 色 x 4 組のパレット。16 x 16 ドットごとに 4 組のどれかを選ぶ
          (各点をファミコンの色に寄せ → 組を決めて区画を割り当て → 組を選び直す、を数回)
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


def encode(img, mode="gray", iters=4):
    a = np.asarray(img.convert("RGB").resize((256, 240)), dtype=np.int32)
    if mode == "gray":
        lum = (a[..., 0] * 299 + a[..., 1] * 587 + a[..., 2] * 114) // 1000
        levels = NES[GRAY].mean(1)                              # 4 階調の明るさ
        idx = np.abs(lum[..., None] - levels[None, None, :]).argmin(-1)
        pal = GRAY * 8
        pal[17:20] = [0x30, 0x0F, 0x0F]                          # スプライト(カーソル): 白 + 黒のふち
        return Frame(idx, pal, bytes(64))

    # 各点をファミコンの色に(Lab の距離。RGB 各 5 ビットの表を引く)
    q = ((a[..., 0] >> 3) << 10) | ((a[..., 1] >> 3) << 5) | (a[..., 2] >> 3)
    near = NEAR_LUT[q]                                          # 240 x 256 の色番号
    al = LAB_LUT[q]                                             # 各点の Lab
    counts = np.bincount(near.ravel(), minlength=64)
    bg = int(counts.argmax())
    # 区画(16 x 16)ごとの色の数
    block_id = (np.arange(240)[:, None] // 16) * 16 + (np.arange(256)[None, :] // 16)
    hist = np.bincount((block_id * 64 + near).ravel(), minlength=240 * 64).reshape(15, 16, 64).astype(np.int64)
    hist[..., bg] = 0
    # 最初の 4 組: 全体で多い色から 3 色ずつ
    order = np.argsort(-hist.reshape(-1, 64).sum(0))
    pals = [list(order[k * 3:k * 3 + 3]) for k in range(4)]
    dist = ((NES_LAB[:, None, :] - NES_LAB[None, :, :]) ** 2).sum(-1)   # 色どうしの距離(Lab)
    for _ in range(iters):
        # 区画ごとに誤差のいちばん小さい組を選ぶ
        err = np.zeros((15, 16, 4))
        for k, p in enumerate(pals):
            opts = [bg] + [int(c) for c in p]
            per_color = dist[:, opts].min(1)                    # 各色を、この組で表した時の誤差
            err[..., k] = (hist * per_color[None, None, :]).sum(-1)
        choice = err.argmin(-1)
        # 組を選び直す: 割り当てられた区画で多い上位 3 色
        for k in range(4):
            h = hist[choice == k].sum(0) if (choice == k).any() else np.zeros(64)
            top = [int(c) for c in np.argsort(-h)[:3] if h[c] > 0]
            pals[k] = (top + [bg, bg, bg])[:3]
    pal = []
    for k in range(4):
        pal += [bg] + [int(c) for c in pals[k]]
    pal += [bg, 0x30, 0x0F, 0x0F] * 4                           # スプライト(カーソル)
    # 各点を、その区画の組の 4 色のどれかに
    bp = np.repeat(np.repeat(choice, 16, 0), 16, 1)
    idx = np.zeros((240, 256), dtype=np.int32)
    best = np.full((240, 256), np.inf)
    for j in range(4):
        cj = np.array([pal[k * 4 + j] for k in range(4)])[bp]  # この点の組の j 番目の色
        e = ((al - NES_LAB[cj]) ** 2).sum(-1)
        better = e < best
        idx[better] = j
        best[better] = e[better]
    return Frame(idx, pal, attr_of(choice))


def write_frame(path, frame, cursor=(0, 0, False)):
    """sim.exe --remote-frame 用: fb 15360 + pal 32 + attr 64 + カーソル x, y, visible(各 1 バイト)"""
    with open(path, "wb") as f:
        f.write(frame.fb + bytes(frame.pal) + frame.attr + struct.pack("BBB", cursor[0] & 255, cursor[1] & 255, int(cursor[2])))
