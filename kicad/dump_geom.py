"""基板の形(外形・パッド・部品の占有範囲)を geom.json に書き出す。印刷用(print_fit_check.ps1)。
    E:\\KiCad\\bin\\python.exe dump_geom.py
"""
import json
import os

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
OX, OY = 100.0, 100.0
b = pcbnew.LoadBoard(os.path.join(HERE, "FC-MAGICON.kicad_pcb"))


def mm(v):
    return round(pcbnew.ToMM(v), 3)


out = {"edges": [], "pads": [], "parts": [], "tracks": [], "vias": []}
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA":
        out["vias"].append([mm(t.GetPosition().x) - OX, mm(t.GetPosition().y) - OY, mm(t.GetWidth(pcbnew.F_Cu))])
    else:
        out["tracks"].append([mm(t.GetStart().x) - OX, mm(t.GetStart().y) - OY, mm(t.GetEnd().x) - OX,
                              mm(t.GetEnd().y) - OY, mm(t.GetWidth()), "F" if t.GetLayer() == pcbnew.F_Cu else "B"])
for d in b.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts:
        out["edges"].append([mm(d.GetStart().x) - OX, mm(d.GetStart().y) - OY, mm(d.GetEnd().x) - OX, mm(d.GetEnd().y) - OY])
for fp in b.GetFootprints():
    ref = fp.GetReference()
    for p in fp.Pads():
        bb = p.GetBoundingBox()
        out["pads"].append({"ref": ref, "num": p.GetNumber(), "x": mm(p.GetPosition().x) - OX, "y": mm(p.GetPosition().y) - OY,
                            "w": mm(bb.GetWidth()), "h": mm(bb.GetHeight()), "tht": p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH,
                            "front": p.IsOnLayer(pcbnew.F_Cu), "back": p.IsOnLayer(pcbnew.B_Cu),
                            "drill": mm(p.GetDrillSize().x)})
    if ref in ("J1",):
        continue
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox() if fp.GetCourtyard(pcbnew.F_CrtYd).OutlineCount() else fp.GetBoundingBox(False)
    out["parts"].append({"ref": ref, "value": fp.GetValue(), "x0": mm(bb.GetLeft()) - OX, "y0": mm(bb.GetTop()) - OY,
                         "x1": mm(bb.GetRight()) - OX, "y1": mm(bb.GetBottom()) - OY})
json.dump(out, open(os.path.join(HERE, "geom.json"), "w", encoding="utf-8"), indent=1)
print(len(out["edges"]), "edges", len(out["pads"]), "pads", len(out["parts"]), "parts")
