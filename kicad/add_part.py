"""配線済みの基板に、あとから部品を1つ足す(今の配線を活かし、重なる所だけ配線し直す準備をする)。
    E:\\KiCad\\bin\\python.exe add_part.py J6
  1. ネットリスト(FC-MAGICON.net)に合わせて、足りないネットを作る
  2. build_pcb.py の PLACEMENT どおりに部品を置き、パッドにネットを付ける(既存部品のパッドのネットも更新)
  3. 部品の占有範囲(+0.4mm)に掛かる配線のネットを表示する → build_pcb.py reroute にそのまま渡す
"""
import sys

import pcbnew

import build_pcb as B

ref = sys.argv[1]
comps, padnets = B.parse_netlist()
board = pcbnew.LoadBoard(B.PCB)
nets = {n.GetNetname(): n for n in board.GetNetsByName().values()}
for name in sorted(set(padnets.values()) - set(nets)):
    ni = pcbnew.NETINFO_ITEM(board, name)
    board.Add(ni)
    nets[name] = ni

row = next(r for r in B.PLACEMENT if r[0] == ref)
_, rot, anchor, x, y = row
value, fpid = comps[ref]
fp = B.load_fp(fpid)
fp.SetReference(ref)
fp.SetValue(value)
board.Add(fp)
fp.SetPosition(B.V(x, y + B.SHIFT))
fp.SetOrientationDegrees(rot)
if anchor:
    p = B.pad_pos(fp, anchor)
    t = B.V(x, y + B.SHIFT)
    fp.Move(pcbnew.VECTOR2I(t.x - p.x, t.y - p.y))
for f in board.GetFootprints():
    for pad in f.Pads():
        n = padnets.get((f.GetReference(), pad.GetNumber()))
        if n and pad.GetNetname() != n:
            pad.SetNet(nets[n])
if ref == "J6":
    B.label_j6(board)

box = fp.GetBoundingBox(False)
box.Inflate(pcbnew.FromMM(0.4))
hit = set()
for t in board.GetTracks():
    if t.GetBoundingBox().Intersects(box) and t.GetNetname() not in {pad.GetNetname() for pad in fp.Pads()}:
        hit.add(t.GetNetname())
pcbnew.SaveBoard(B.PCB, board)
print("置いた:", ref, [(p.GetNumber(), round(pcbnew.ToMM(p.GetPosition().x) - B.OX, 2), round(pcbnew.ToMM(p.GetPosition().y) - B.OY, 2),
                        p.GetNetname()) for p in fp.Pads()])
print("重なる配線のネット:", " ".join(sorted(n.lstrip("/") for n in hit)))
