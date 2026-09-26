"""シェル(表+裏を合わせた状態)を Y(高さ)ごとに輪切りにして、X(幅)と Z(厚み)の範囲を出す。
    python slice_step.py
  Y = 0 が上端、Y = -69 が差し込む側の端(STEP の座標のまま)。
  内側の空間(基板が入る所)も知りたいので、各高さで「材料がある Z の区間」を X の中央付近で出す。
"""
import os

import cadquery as cq

SRC = os.path.join(os.environ["USERPROFILE"], "Downloads")
front = cq.importers.importStep(os.path.join(SRC, "cartouche front.stp")).val()
back = cq.importers.importStep(os.path.join(SRC, "cartouche back.stp")).val()
both = front.fuse(back)


def section(y):
    """高さ y の断面(XZ 平面)の外接範囲"""
    slab = cq.Solid.makeBox(200, 0.2, 60, cq.Vector(-100, y - 0.1, -20))
    s = both.intersect(slab)
    if s.Volume() < 1e-6:
        return None
    b = s.BoundingBox()
    return b.xmin, b.xmax, b.zmin, b.zmax


def z_runs(y, x):
    """(x, y) を通る Z 方向の線上で、材料がある区間"""
    runs, z, inside, start = [], -20.0, False, None
    while z <= 40:
        p = cq.Vector(x, y, z)
        hit = both.isInside(p, 0.01)
        if hit and not inside:
            start, inside = z, True
        if not hit and inside:
            runs.append((round(start, 1), round(z, 1)))
            inside = False
        z += 0.1
    return runs


print("  Y     X範囲              Z範囲        中央(x=0)の材料  x=40の材料")
for y in (-1, -5, -10, -20, -30, -40, -50, -55, -57, -58, -59, -60, -61, -62, -64, -66, -68):
    s = section(y)
    if not s:
        print(f"{y:5}  なし")
        continue
    print(f"{y:5}  {s[0]:7.2f}..{s[1]:6.2f}  {s[2]:5.2f}..{s[3]:5.2f}  {z_runs(y, 0)}  {z_runs(y, 40)}")
