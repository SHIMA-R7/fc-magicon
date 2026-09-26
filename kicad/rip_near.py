"""部品の近くだけ配線を剥がして .dsn を書き出す(build_pcb.py reroute の部分版)。
    E:\\KiCad\\bin\\python.exe rip_near.py R1
  ・その部品のパッドのネット: 全部消す(Freerouting が引き直す)
  ・ほかのネット: パッドとのすき間が 0.3mm 未満の線とビアだけ消す(本体の下を通るだけの線や、手で引いた +5V を残すため)
  ・ベタと、行き止まりのビアも消す(import でベタとスティッチングを作り直す)
  あとは route.py → build_pcb.py import。
"""
import os
import sys

import pcbnew

import build_pcb as B

ref = sys.argv[1]
board = pcbnew.LoadBoard(B.PCB)
fp = board.FindFootprintByReference(ref)
pads = [(p.GetPosition().x, p.GetPosition().y, max(p.GetSize().x, p.GetSize().y) / 2, p.GetNetname()) for p in fp.Pads()]
own = {p[3] for p in pads}
CLR = pcbnew.FromMM(0.3)


def seg_dist(ax, ay, bx, by, px, py):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    k = 0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return ((ax + k * dx - px) ** 2 + (ay + k * dy - py) ** 2) ** 0.5


def too_close(t):
    """パッドとのすき間が CLR 未満(本体の下を通るだけの線は残す)"""
    if t.GetClass() == "PCB_VIA":
        a = b = t.GetPosition()
    else:
        a, b = t.GetStart(), t.GetEnd()
    half = t.GetWidth(pcbnew.F_Cu) / 2 if t.GetClass() == "PCB_VIA" else t.GetWidth() / 2
    return any(seg_dist(a.x, a.y, b.x, b.y, px, py) < r + half + CLR for px, py, r, _ in pads)


tracks = list(board.GetTracks())
gone = set()
for t in tracks:
    if t.GetNetname() in own or too_close(t):
        gone.add(t.m_Uuid.AsString())
# 残る線の端点で、行き止まりのビアを探す
ends = {}
for t in tracks:
    if t.GetClass() != "PCB_VIA" and t.m_Uuid.AsString() not in gone:
        for p in (t.GetStart(), t.GetEnd()):
            ends.setdefault((t.GetNetname(), p.x, p.y), set()).add(t.GetLayer())
n = {"tracks": 0, "vias": 0}
nets = set()
for t in tracks:
    is_via = t.GetClass() == "PCB_VIA"
    dead_via = is_via and len(ends.get((t.GetNetname(), t.GetPosition().x, t.GetPosition().y), ())) < 2
    if t.m_Uuid.AsString() in gone or dead_via:
        if not dead_via or t.GetNetname() != "/GND":
            nets.add(t.GetNetname())
        board.Delete(t)
        n["vias" if is_via else "tracks"] += 1
for z in [z for z in board.Zones() if not z.GetIsRuleArea()]:
    board.Delete(z)
pcbnew.SaveBoard(B.PCB, board)
pcbnew.ExportSpecctraDSN(board, os.path.join(B.HERE, B.NAME + ".dsn"))
print("消した:", n, "ネット:", " ".join(sorted(x.lstrip("/") for x in nets)))
