"""基板の部品の占有範囲(コートヤードの外接箱)と、裏に出る足(スルーホール)の位置を JSON に出す。
    E:\\KiCad\\bin\\python.exe dump_parts.py
  座標は基板の左上 = (0, 0)、x は右、y は下(部品面から見て)。単位 mm。-> parts.json
"""
import json
import os

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
board = pcbnew.LoadBoard(os.path.join(HERE, "..", "kicad", "FC-MAGICON.kicad_pcb"))
OX = OY = 100.0
mm = pcbnew.ToMM

parts = []
for fp in board.GetFootprints():
    ref = fp.GetReference()
    side = "B" if fp.IsFlipped() else "F"
    cy = fp.GetCourtyard(pcbnew.B_CrtYd if side == "B" else pcbnew.F_CrtYd)
    if cy.OutlineCount():
        bb = cy.BBox()
    else:
        bb = fp.GetBoundingBox(False)
    holes = []
    for p in fp.Pads():
        if p.HasHole():
            q = p.GetPosition()
            holes.append([round(mm(q.x) - OX, 3), round(mm(q.y) - OY, 3), round(mm(p.GetDrillSizeX()), 2)])
    parts.append({
        "ref": ref, "side": side, "value": fp.GetValue(), "fp": str(fp.GetFPID().GetLibItemName()),
        "x0": round(mm(bb.GetLeft()) - OX, 2), "x1": round(mm(bb.GetRight()) - OX, 2),
        "y0": round(mm(bb.GetTop()) - OY, 2), "y1": round(mm(bb.GetBottom()) - OY, 2),
        "holes": holes,
    })
parts.sort(key=lambda p: p["ref"])
with open(os.path.join(HERE, "parts.json"), "w", encoding="utf-8") as f:
    json.dump(parts, f, ensure_ascii=False, indent=1)
for p in parts:
    print(f'{p["ref"]:5} {p["side"]} {p["fp"][:28]:28} x {p["x0"]:6.2f}..{p["x1"]:6.2f}  y {p["y0"]:6.2f}..{p["y1"]:6.2f}  穴{len(p["holes"])}')
