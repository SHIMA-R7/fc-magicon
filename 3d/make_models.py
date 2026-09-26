"""KiCad に 3D モデルが無い部品の代わりの箱を STEP で作る(ケース設計用の外形)。
    python make_models.py   (CadQuery が入っている普通の Python)
  -> ../kicad/3d/core2350b_board.step  Core2350B の基板(25.4mm 角、厚み 1.0mm は仮)。原点 = 基板の中心、下面
     ../kicad/3d/koa_sf6.step          KOA KVSF637A の本体(6.4 x 7.3mm はデータシート、高さ 5.0mm は仮)。原点 = フットプリント原点(①番ピン)
  KiCad の 3D は y が上向き(フットプリントの y と逆)なので、SF6 の箱は y を反転して置く。
"""
import os

import cadquery as cq

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kicad", "3d")
os.makedirs(OUT, exist_ok=True)

MOD_T = 1.0      # Core2350B の基板の厚み(仮)
SF6_H = 5.0      # SF6 の高さ(仮)

mod = cq.Workplane("XY").box(25.4, 25.4, MOD_T, centered=(True, True, False))
a = cq.Assembly().add(mod, name="core2350b", color=cq.Color(0.1, 0.35, 0.15))
a.save(os.path.join(OUT, "core2350b_board.step"), "STEP")

# フットプリント上の本体: x -0.7..5.7、y -6.2..1.1(y は下向き) -> 3D では y -1.1..6.2
sf6 = cq.Workplane("XY").box(6.4, 7.3, SF6_H, centered=False).translate((-0.7, -1.1, 0))
a = cq.Assembly().add(sf6, name="koa_sf6", color=cq.Color(0.2, 0.3, 0.7))
a.save(os.path.join(OUT, "koa_sf6.step"), "STEP")
print("->", os.path.abspath(OUT))
