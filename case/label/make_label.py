"""カセット表面に貼るシール(原寸、基板の本体部分 90 x 55.1mm と同じ位置関係)を PNG で作る。
    python make_label.py
  ・ケースの表面には、背の高い部品のための穴がある: J3・J5・J6(ピンヘッダー)、VR1、SW1・SW2、Core2350B2。
    シールはその穴を避ける(白抜き + 切り取り線)。穴の大きさは部品のコートヤード + HOLE_M。
  ・穴のまわりに、何の部品で何をするかを書く。
  ・J4 のあたりにロゴ(../../images/logo.png、黒い背景は切り落とす)。
  部品の位置は ../parts.json(dump_parts.py の出力、基板の左上が原点、y は下向き)。
  -> label.png(20px/mm、確認用)。印刷は print_label.ps1(--px 48 の label_print.png を使う)
    python make_label.py --px 48 --out label_print.png     (印刷用、約 1200dpi)
  絵(枠・文字・ロゴ)は SCALE 倍の大きさで直接描く(描いてから拡大するとぼやけるため)。穴だけ原寸。
  ロゴは元画像を目標の大きさへ縮めてから、4 色(黒・白・青・水色)に寄せ直して縁のにじみを消す。
"""
import argparse
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--px", type=float, default=20)            # 1mm あたりのピクセル
ap.add_argument("--out", default="label.png")
ARGS = ap.parse_args()
PX = ARGS.px
W, H = 90.0, 55.1             # シール = 基板の本体部分(差し込み部はスカートの中なので除く)
HOLE_M = 0.5                  # 穴は部品の枠より 0.5mm 大きく
SCALE = 1.1                   # シール(枠・文字・ロゴ)の倍率。穴は原寸のまま(2026-09-26 ユーザー指定)
BG = (0, 0, 0)
BLUE = (26, 108, 255)
LBLUE = (90, 170, 255)
WHITE = (255, 255, 255)
GRAY = (150, 160, 175)
CUT = (230, 40, 40)
LOGO = os.path.join(HERE, "..", "..", "images", "logo.png")
FB = r"C:\Windows\Fonts\BIZ-UDGothicB.ttc"
FR = r"C:\Windows\Fonts\BIZ-UDGothicR.ttc"
FM = r"C:\Windows\Fonts\consolab.ttf"

parts = {p["ref"]: p for p in json.load(open(os.path.join(HERE, "..", "parts.json"), encoding="utf-8"))}


K = PX * 1.1                  # 絵を描く時の 1mm あたりのピクセル(= PX * SCALE、下で SCALE に合わせ直す)


def mm(v):                    # 絵の座標(基板の mm を SCALE 倍した所)
    return int(round(v * K))


def mmh(v):                   # 穴の座標(原寸の mm)
    return int(round(v * PX))


def font(path, size_mm):
    return ImageFont.truetype(path, mm(size_mm))


K = PX * SCALE
img = Image.new("RGB", (mmh(W * SCALE), mmh(H * SCALE)), BG)
d = ImageDraw.Draw(img)

# 外周の青い二重線(ロゴの枠に合わせる)
d.rounded_rectangle([mm(0.6), mm(0.6), mm(W - 0.6), mm(H - 0.6)], radius=mm(2.0), outline=BLUE, width=mm(0.5))
d.rounded_rectangle([mm(1.3), mm(1.3), mm(W - 1.3), mm(H - 1.3)], radius=mm(1.5), outline=WHITE, width=mm(0.15))

# 穴
holes = {}
for ref in ("J3", "J5", "J6", "VR1", "SW1", "SW2", "P1"):  # SW1・SW2 は隣り合うので下で1つの穴にまとめる
    p = parts[ref]
    x0, x1, y0, y1 = p["x0"] - HOLE_M, p["x1"] + HOLE_M, p["y0"] - HOLE_M, p["y1"] + HOLE_M
    if ref == "P1":   # Core2350B2(25.4mm 角)とソケットを合わせた範囲
        x0, x1, y0, y1 = p["x0"] - HOLE_M, p["x1"] + HOLE_M, p["y0"] - HOLE_M, p["y1"] + HOLE_M
    y0 = max(y0, 0.0)  # 上辺にかかる穴は切り欠きになる
    holes[ref] = (x0, y0, x1, y1)
a, b = holes.pop("SW1"), holes.pop("SW2")
holes["SW"] = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
holes["SW1"], holes["SW2"] = a, b
def draw_holes(dr, ox, oy):
    """穴を白抜き + 赤い破線で描く。ox, oy = シールの左上から見た基板の左上の位置(mm)"""
    for ref, (x0, y0, x1, y1) in holes.items():
        if ref in ("SW1", "SW2"):
            continue
        x0, x1, y0, y1 = x0 + ox, x1 + ox, y0 + oy, y1 + oy
        dr.rounded_rectangle([mmh(x0), mmh(y0), mmh(x1), mmh(y1)], radius=mmh(0.6), fill=WHITE)
        # 切り取り線(細い赤の破線)
        for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
            n = max(1, int(max(abs(bx - ax), abs(by - ay)) / 0.8))
            for k in range(0, n, 2):
                t0, t1 = k / n, min(1.0, (k + 1) / n)
                dr.line([mmh(ax + (bx - ax) * t0), mmh(ay + (by - ay) * t0), mmh(ax + (bx - ax) * t1), mmh(ay + (by - ay) * t1)],
                        fill=CUT, width=max(1, mmh(0.12)))


def text(xy, s, f, fill=WHITE, anchor="la"):
    d.text((mm(xy[0]), mm(xy[1])), s, font=f, fill=fill, anchor=anchor)


def tag(xy, name, desc, anchor="l", w_name=None):
    """部品名(青い札)+ 説明(白)。anchor l = 左寄せ、r = 右寄せ、c = 中央"""
    fn, fd = font(FM, 1.9), font(FB, 1.55)
    x, y = xy
    nb = d.textbbox((0, 0), name, font=fn)
    nw = (nb[2] - nb[0]) / K + 1.0
    lines = desc.split("\n")
    dw = max((d.textbbox((0, 0), s, font=fd)[2]) / K for s in lines)
    tw = max(nw, dw)
    if anchor == "r":
        x -= tw
    elif anchor == "c":
        x -= tw / 2
    d.rectangle([mm(x), mm(y), mm(x + nw), mm(y + 2.5)], fill=BLUE)
    text((x + 0.5, y + 1.25), name, fn, WHITE, "lm")
    for i, s in enumerate(lines):
        text((x, y + 3.0 + i * 2.05), s, fd, WHITE)


# 部品の説明
tag((holes["P1"][2] + 1.6, 16.2), "CORE2350B2", "RP2350B + 2MB PSRAM\nPRG/CHRをリアルタイム応答\nNSF再生・PC画面転送\nUSB(FPC)は上へ")
tag((holes["SW1"][0] - 1.0, 5.0), "BOOTSEL", "押しながらUSBを\nつなぐと書き込み", "r")
tag((holes["SW2"][0] - 1.0, 13.6), "RESET", "RP2350を\nリセット", "r")
tag((holes["VR1"][0] - 1.0, 22.6), "VOLUME", "拡張音源の\n音量(100kΩ)", "r")
tag((holes["J3"][0] - 0.8, 1.6), "SWD", "", "r")
tag((holes["J6"][2] + 0.8, 1.6), "USB", "")
tag((holes["J5"][0] + 1.0, 10.8), "DEBUG", "")   # 拡大しても J5 の穴(原寸)に掛からない高さ
text((holes["J5"][0] + 9.8, 10.9), "内部信号 2x8", font(FB, 1.45), WHITE)
text((holes["J5"][0] + 9.8, 12.8), "/RD /WR A13 A10 /IRQ", font(FB, 1.3), GRAY)
# J2(3.5mm ジャック)は左の側面にある
text((2.4, 30.0), "◀", font(FB, 2.0), LBLUE)
text((5.2, 30.0), "LINE OUT", font(FM, 2.0), LBLUE)
text((2.4, 32.8), "3.5mm ステレオ(左側面)", font(FB, 1.45), WHITE)
text((2.4, 35.0), "本体の音 + 拡張音源", font(FB, 1.45), GRAY)

# 右下: 機能の一覧
fx, fy = 60.0, 30.5
for i, (a, b) in enumerate((("PRG/CHR", "NROM/UNROM/CNROM/MMC1/3"), ("NSF", "拡張音源は46番へミックス"), ("SCREEN", "PC → FC 画面転送"))):
    text((fx, fy + i * 3.3), a, font(FM, 1.8), LBLUE)
    text((fx + 9.6, fy + i * 3.3 + 0.15), b, font(FB, 1.4), WHITE)

# ロゴ: 黒い背景を切り落として J4 のあたり(下辺寄り)に置く
logo = Image.open(LOGO).convert("RGB")
px = logo.load()
xs, ys = [], []
for yy in range(0, logo.height, 2):
    for xx in range(0, logo.width, 2):
        r, g, b = px[xx, yy]
        if r + g + b > 120:
            xs.append(xx)
            ys.append(yy)
logo = logo.crop((min(xs) - 4, min(ys) - 4, max(xs) + 5, max(ys) + 5))
LW = 76.0
lh = LW * logo.height / logo.width
logo = logo.resize((mm(LW), mm(lh)), Image.LANCZOS)   # 縮めてから 4 色に寄せ直す(縁のにじみを消す)
# 色の薄い(灰色の)縁は白か黒だけに寄せる(青に寄ると白い文字の縁に水色のふちが出る)。色のある所だけ青・水色へ
import numpy as np
a = np.asarray(logo).astype(np.int32)
PAL4 = np.array([(0, 0, 0), (255, 255, 255), (26, 108, 255), (90, 170, 255)])
dist = ((a[:, :, None, :] - PAL4[None, None, :, :]) ** 2).sum(-1)
idx = dist.argmin(-1)
sat = a.max(-1) - a.min(-1)
gray = sat < 90
idx[gray] = np.where(a[gray].mean(-1) > 128, 1, 0)
logo = Image.fromarray(PAL4[idx].astype(np.uint8))
ly = 48.9 - lh / 2
img.paste(logo, (mm((W - LW) / 2), mm(ly)))
text((W / 2, ly - 1.2), "rev0.2   FAMICOM CARTRIDGE", font(FM, 1.5), GRAY, "md")

# 穴は原寸のまま、基板の中心 = シールの中心 になる位置に開ける
OFF_X, OFF_Y = (W * SCALE - W) / 2, (H * SCALE - H) / 2
draw_holes(ImageDraw.Draw(img), OFF_X, OFF_Y)
out = os.path.join(HERE, ARGS.out)
img.save(out, dpi=(PX * 25.4, PX * 25.4))
print("->", out, img.size, f"{W * SCALE:.1f} x {H * SCALE:.1f}mm  穴のずらし {OFF_X:.2f}, {OFF_Y:.2f}mm")




