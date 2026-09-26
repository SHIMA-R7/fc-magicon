"""シェルの断面の輪郭を PNG にする(形を目で見るため)。
    python raster_step.py
  XY 断面(Z を固定、正面から見た形)と XZ 断面(Y を固定、上から見た厚み方向)。
  OCC の section で切り口の線を取り、matplotlib で描く。目盛りは 1mm、太線は 10mm。
"""
import os

import cadquery as cq
import matplotlib
import OCP.BRepAlgoAPI as BA

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SRC = os.path.join(os.environ["USERPROFILE"], "Downloads")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inspect")
os.makedirs(OUT, exist_ok=True)
front = cq.Workplane().add(cq.importers.importStep(os.path.join(SRC, "cartouche front.stp")).val())
back = cq.Workplane().add(cq.importers.importStep(os.path.join(SRC, "cartouche back.stp")).val())


def section_lines(shape, origin, normal):
    """origin を通り normal に垂直な面でシェルを切った線(点列のリスト)"""
    face = cq.Face.makePlane(400, 400, basePnt=cq.Vector(*origin), dir=cq.Vector(*normal))
    op = BA.BRepAlgoAPI_Section(shape.val().wrapped, face.wrapped)
    op.Build()
    res = cq.Shape.cast(op.Shape())
    out = []
    for e in res.Edges():
        n = max(2, int(e.Length() / 0.2))
        out.append([e.positionAt(k / n) for k in range(n + 1)])
    return out


def draw(name, parts, origin, normal, ax_u, ax_v, lim_u, lim_v):
    fig, ax = plt.subplots(figsize=((lim_u[1] - lim_u[0]) / 8, (lim_v[1] - lim_v[0]) / 8), dpi=100)
    for shp, col in parts:
        for pts in section_lines(shp, origin, normal):
            ax.plot([getattr(p, ax_u) for p in pts], [getattr(p, ax_v) for p in pts], color=col, lw=0.8)
    ax.set_xlim(*lim_u)
    ax.set_ylim(*lim_v)
    ax.set_aspect("equal")
    ax.set_xticks(range(int(lim_u[0]), int(lim_u[1]) + 1, 10))
    ax.set_yticks(range(int(lim_v[0]), int(lim_v[1]) + 1, 10))
    ax.set_xticks(range(int(lim_u[0]), int(lim_u[1]) + 1), minor=True)
    ax.set_yticks(range(int(lim_v[0]), int(lim_v[1]) + 1), minor=True)
    ax.grid(which="major", color="#99f", lw=0.6)
    ax.grid(which="minor", color="#ddf", lw=0.3)
    ax.set_title(name)
    fig.savefig(os.path.join(OUT, name + ".png"), bbox_inches="tight")
    plt.close(fig)
    print("->", name)


for z in (1, 3, 5, 8, 11):
    draw(f"xy_front_z{z}", [(front, "k")], (0, 0, z), (0, 0, 1), "x", "y", (-56, 56), (-72, 2))
for z in (9, 13, 15):
    draw(f"xy_back_z{z}", [(back, "b")], (0, 0, z), (0, 0, 1), "x", "y", (-56, 56), (-72, 2))
for y in (-10, -30, -50, -57, -61, -66):
    draw(f"xz_y{-y}", [(front, "k"), (back, "b")], (0, y, 0), (0, 1, 0), "x", "z", (-56, 56), (-2, 18))
for x in (0, 30, 44, 50):
    draw(f"yz_x{x}", [(front, "k"), (back, "b")], (x, 0, 0), (1, 0, 0), "y", "z", (-72, 2), (-2, 18))
