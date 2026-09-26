"""自動配線で引けなかった1本を、指定した折れ線で手で引く。先に他の銅箔との間隔を確かめ、足りなければ引かない。
    E:\\KiCad\\bin\\python.exe hand_route.py
ROUTES に (ネット, 層, 線幅mm, [(x, y), ...]) を書く(座標は基板左上からの mm)。
"""
import math

import pcbnew

import build_pcb as B

CLEAR = 0.2
ROUTES = [
    # LINE: R11 の1番(基板の左端側)から左端に沿って上がり、J2 の下を通って J2 の4番へ
    ("/LINE", "B.Cu", 0.25, [(2.0, 33.8), (0.75, 32.55), (0.75, 19.4), (12.2, 19.4), (13.3, 18.3), (13.3, 16.35)]),
]


def seg_dist(p, q, a, b):
    """線分 pq と線分 ab の最短距離"""
    def pt_seg(x, y, s, t):
        dx, dy = t[0] - s[0], t[1] - s[1]
        L = dx * dx + dy * dy
        u = 0 if L == 0 else max(0, min(1, ((x - s[0]) * dx + (y - s[1]) * dy) / L))
        return math.hypot(x - s[0] - u * dx, y - s[1] - u * dy)

    def cross(o, a_, b_):
        return (a_[0] - o[0]) * (b_[1] - o[1]) - (a_[1] - o[1]) * (b_[0] - o[0])
    if (cross(a, b, p) * cross(a, b, q) < 0) and (cross(p, q, a) * cross(p, q, b) < 0):
        return 0.0
    return min(pt_seg(*p, a, b), pt_seg(*q, a, b), pt_seg(*a, p, q), pt_seg(*b, p, q))


def mm(v):
    return pcbnew.ToMM(v)


board = pcbnew.LoadBoard(B.PCB)
obstacles = []   # (層名 or "*", 線分の端2つ, 半径)
for t in board.GetTracks():
    net = t.GetNetname()
    if t.GetClass() == "PCB_VIA":
        c = (mm(t.GetPosition().x) - B.OX, mm(t.GetPosition().y) - B.OY)
        obstacles.append(("*", net, c, c, mm(t.GetWidth(pcbnew.F_Cu)) / 2))
    else:
        obstacles.append((t.GetLayerName(), net, (mm(t.GetStart().x) - B.OX, mm(t.GetStart().y) - B.OY),
                          (mm(t.GetEnd().x) - B.OX, mm(t.GetEnd().y) - B.OY), mm(t.GetWidth()) / 2))
for f in board.GetFootprints():
    for p in f.Pads():
        c = (mm(p.GetPosition().x) - B.OX, mm(p.GetPosition().y) - B.OY)
        r = max(mm(p.GetSize().x), mm(p.GetSize().y)) / 2          # パッドは外接円で見る(安全側)
        layer = "*" if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else ("F.Cu" if p.IsOnLayer(pcbnew.F_Cu) else "B.Cu")
        obstacles.append((layer, p.GetNetname(), c, c, r))
edge_x0, edge_x1 = 0.0, B.W

ok_all = True
for net, layer, w, pts in ROUTES:
    worst = (99, None)
    for a, b in zip(pts, pts[1:]):
        for lay, onet, s, e, r in obstacles:
            if onet == net or (lay != "*" and lay != layer):
                continue
            d = seg_dist(a, b, s, e) - r - w / 2
            if d < worst[0]:
                worst = (d, (onet, s))
        for x in (a[0], b[0]):
            worst = min(worst, (x - w / 2 - edge_x0 - 0.3 + CLEAR, ("基板の端", (x, 0))))
    print(f"{net} {layer}: いちばん近い物まで {worst[0]:.3f}mm ({worst[1]})")
    if worst[0] < CLEAR:
        ok_all = False

if ok_all:
    for net, layer, w, pts in ROUTES:
        ni = board.FindNet(net)
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(B.V(*a))
            t.SetEnd(B.V(*b))
            t.SetWidth(pcbnew.FromMM(w))
            t.SetLayer(board.GetLayerID(layer))
            t.SetNet(ni)
            board.Add(t)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(B.PCB, board)
    print("引いた")
else:
    print("間隔が足りないので引かなかった")
