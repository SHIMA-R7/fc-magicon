"""シェルの中で基板の位置を決めている部分(リブ・ピン・棚)の寸法を正確に測る。
    python measure_step.py
  標準のファミコン基板(ref/cart-dimensions/HVC-TGROM-01)には、
  本体の下端から 23.2〜25.2mm の高さに、左右の切り欠き(深さ 4.5mm)と中央右寄りの穴(5×2mm)がある。
  シェル側のリブとピンがそこに入るので、そこから基板の位置を逆算する。
"""
import os

import cadquery as cq

SRC = os.path.join(os.environ["USERPROFILE"], "Downloads")
front = cq.importers.importStep(os.path.join(SRC, "cartouche front.stp")).val()
back = cq.importers.importStep(os.path.join(SRC, "cartouche back.stp")).val()


def bbox_in(shape, x0, x1, y0, y1, z0, z1, label):
    box = cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))
    s = shape.intersect(box)
    if s.Volume() < 1e-6:
        print(f"{label:28} なし")
        return None
    b = s.BoundingBox()
    print(f"{label:28} X {b.xmin:7.2f}..{b.xmax:7.2f}  Y {b.ymin:7.2f}..{b.ymax:7.2f}  Z {b.zmin:5.2f}..{b.zmax:5.2f}")
    return b


# 表側(front): 左右のリブ、中央のピン、下のリブ、下の棚、上のフック
bbox_in(front, -52, -38, -36, -28, 2.05, 13, "front 左リブ")
bbox_in(front, 38, 52, -36, -28, 2.05, 13, "front 右リブ")
bbox_in(front, 2, 10, -36, -28, 2.05, 13, "front 中央ピン")
bbox_in(front, -30, 30, -60, -50, 2.05, 13, "front 下リブ(中央)")
bbox_in(front, -51, -40, -62, -50, 2.05, 13, "front 下リブ(左端)")
bbox_in(front, -51.4, -46, -63, -58, 2.05, 13, "front 左の棚")
bbox_in(front, -34, -28, -8, -1.2, 2.05, 13, "front 上のフック左")
bbox_in(front, 28, 34, -8, -1.2, 2.05, 13, "front 上のフック右")
bbox_in(front, -46, -40, -70, -62, 2.05, 13, "front 左下スカートの内側")
# 裏側(back): 基板を押さえるピン、下のリブ
bbox_in(back, -35, -27, -36, -28, 8, 14.0, "back ピン左")
bbox_in(back, 27, 35, -36, -28, 8, 14.0, "back ピン右")
bbox_in(back, -30, 30, -60, -50, 8, 14.0, "back 下リブ(中央)")
bbox_in(back, -53, -40, -70, -50, 8, 14.0, "back 左下")
# 外形の段(スカート)
bbox_in(front.fuse(back), -60, 60, -70, -62.5, -1, 17, "スカート(差し込む部分)")
bbox_in(front.fuse(back), -60, 60, -62, -1, -1, 17, "胴")
