"""ファミコンのカセットシェル(printables 860420、表・裏の STEP)の寸法を調べる。
    python inspect_step.py
  ・外形の大きさ、面の数、平らな面の高さ(Z)の一覧、円筒面(ネジ穴・ボス)の位置と径
  ・正面・側面・上からの投影図を SVG に書き出す(形を目で見るため)
"""
import os
from collections import Counter

import cadquery as cq

SRC = os.path.join(os.environ["USERPROFILE"], "Downloads")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inspect")
os.makedirs(OUT, exist_ok=True)

for name in ("cartouche front", "cartouche back"):
    shape = cq.importers.importStep(os.path.join(SRC, name + ".stp"))
    solids = shape.solids().vals()
    bb = shape.val().BoundingBox()
    print(f"== {name}: solids {len(solids)}  bbox X {bb.xmin:.2f}..{bb.xmax:.2f} ({bb.xlen:.2f})  "
          f"Y {bb.ymin:.2f}..{bb.ymax:.2f} ({bb.ylen:.2f})  Z {bb.zmin:.2f}..{bb.zmax:.2f} ({bb.zlen:.2f})")
    faces = shape.faces().vals()
    kinds = Counter(f.geomType() for f in faces)
    print("   faces:", dict(kinds))
    # 平らな面の向きと位置(大きい面から)
    planes = []
    for f in faces:
        if f.geomType() == "PLANE":
            n = f.normalAt()
            c = f.Center()
            planes.append((f.Area(), (round(n.x, 2), round(n.y, 2), round(n.z, 2)), (round(c.x, 2), round(c.y, 2), round(c.z, 2))))
    planes.sort(reverse=True)
    print("   大きい平面(面積, 法線, 中心):")
    for p in planes[:14]:
        print("     ", p)
    cyl = []
    for f in faces:
        if f.geomType() == "CYLINDER":
            bbf = f.BoundingBox()
            c = f.Center()
            r = max(bbf.xlen, bbf.ylen, bbf.zlen)
            cyl.append((round(c.x, 1), round(c.y, 1), round(c.z, 1), round(bbf.xlen, 2), round(bbf.ylen, 2), round(bbf.zlen, 2)))
    print("   円筒面(中心, 外接箱):", len(cyl))
    for c in sorted(set(cyl))[:20]:
        print("     ", c)
    for view, d in (("front", (0, 0, 1)), ("side", (1, 0, 0)), ("top", (0, 1, 0))):
        cq.exporters.export(shape, os.path.join(OUT, f"{name.replace(' ', '_')}_{view}.svg"),
                            opt={"projectionDir": d, "showHidden": True, "width": 900, "height": 700, "marginLeft": 40,
                                 "marginTop": 40, "strokeWidth": 0.4, "showAxes": True})
print("->", OUT)
