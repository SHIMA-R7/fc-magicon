"""ロゴ(../images/logo_silk.png、白地に黒のドット絵)をシルク用の矩形の集まりにする。
    python make_silk_logo.py   (Pillow が入っている普通の Python)
  指定の幅(LOGO_W mm)に縮めたときの STEP mm 格子で黒い所を拾い、横に続く所をまとめ、
  さらに縦に同じ幅で続く所をまとめる。-> silk_logo.json([x0, y0, x1, y1] mm、ロゴの左上が原点、y は下向き)
  add_silk_art.py(KiCad の Python)がこれを裏面シルクに置く。
"""
import json
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "images", "logo_silk.png")
LOGO_W = 34.0
STEP = 0.05

im = Image.open(SRC).convert("L")
px = im.load()
xs = [x for x in range(im.width) for y in range(0, im.height, 4) if px[x, y] < 128]
ys = [y for y in range(im.height) for x in range(0, im.width, 4) if px[x, y] < 128]
x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
k = (x1 - x0 + 1) / LOGO_W              # 元画像の px / mm
logo_h = (y1 - y0 + 1) / k
nx, ny = int(LOGO_W / STEP), int(logo_h / STEP)


def dark(i, j):
    # 格子の中心を元画像で見る
    return px[int(x0 + (i + 0.5) * STEP * k), int(y0 + (j + 0.5) * STEP * k)] < 128


rows = []
for j in range(ny):
    runs, s = [], None
    for i in range(nx + 1):
        d = i < nx and dark(i, j)
        if d and s is None:
            s = i
        if not d and s is not None:
            runs.append((s, i))
            s = None
    rows.append(runs)

# 縦にまとめる: 同じ (s, e) が続く行を1つの矩形に
rects, open_ = [], {}
for j, runs in enumerate(rows + [[]]):
    cur = set(runs)
    for key in list(open_):
        if key not in cur:
            s, e = key
            rects.append([round(s * STEP, 3), round(open_.pop(key) * STEP, 3), round(e * STEP, 3), round(j * STEP, 3)])
    for key in cur:
        open_.setdefault(key, j)
json.dump({"w": LOGO_W, "h": round(logo_h, 3), "rects": rects}, open(os.path.join(HERE, "silk_logo.json"), "w"))
print(f"logo {LOGO_W} x {logo_h:.2f}mm, {len(rects)} rects")
