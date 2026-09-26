"""シルクを置ける空き場所(パッド・穴・既存シルクから離れた矩形)を探す。
    E:\\KiCad\\bin\\python.exe find_free_silk.py [F|B]
  0.25mm 格子で「使えない点」を塗り、大きい空き矩形を順に出す(基板の左上が原点、部品面から見た座標)。
"""
import sys

import pcbnew

SIDE = sys.argv[1] if len(sys.argv) > 1 else "B"
board = pcbnew.LoadBoard("FC-MAGICON.kicad_pcb")
OX = OY = 100.0
W, H = 90.0, 55.1                 # 本体だけ(差し込み部は除く)
G = 0.25
CLR = 0.5                         # パッドからの距離
mm = pcbnew.ToMM
nx, ny = int(W / G), int(H / G)
bad = [[False] * nx for _ in range(ny)]


def block(x0, y0, x1, y1):
    for j in range(max(0, int((y0) / G)), min(ny, int((y1) / G) + 1)):
        for i in range(max(0, int((x0) / G)), min(nx, int((x1) / G) + 1)):
            bad[j][i] = True


# 外周 1mm
block(0, 0, W, 1.0); block(0, H - 1.0, W, H); block(0, 0, 1.0, H); block(W - 1.0, 0, W, H)
layer_cu = pcbnew.B_Cu if SIDE == "B" else pcbnew.F_Cu
layer_silk = pcbnew.B_SilkS if SIDE == "B" else pcbnew.F_SilkS
for fp in board.GetFootprints():
    for p in fp.Pads():
        if p.HasHole() or p.IsOnLayer(layer_cu):
            bb = p.GetBoundingBox()
            block(mm(bb.GetLeft()) - OX - CLR, mm(bb.GetTop()) - OY - CLR, mm(bb.GetRight()) - OX + CLR, mm(bb.GetBottom()) - OY + CLR)
    for it in list(fp.GraphicalItems()) + [fp.Reference(), fp.Value()]:
        if it.GetLayer() == layer_silk and it.IsVisible() if hasattr(it, "IsVisible") else it.GetLayer() == layer_silk:
            bb = it.GetBoundingBox()
            block(mm(bb.GetLeft()) - OX - 0.2, mm(bb.GetTop()) - OY - 0.2, mm(bb.GetRight()) - OX + 0.2, mm(bb.GetBottom()) - OY + 0.2)
for d in board.GetDrawings():
    if d.GetLayer() == layer_silk:
        bb = d.GetBoundingBox()
        print("既存シルク:", d.GetClass(), getattr(d, "GetText", lambda: "")(), round(mm(bb.GetLeft()) - OX, 1), round(mm(bb.GetTop()) - OY, 1),
              round(mm(bb.GetRight()) - OX, 1), round(mm(bb.GetBottom()) - OY, 1))
        block(mm(bb.GetLeft()) - OX - 0.2, mm(bb.GetTop()) - OY - 0.2, mm(bb.GetRight()) - OX + 0.2, mm(bb.GetBottom()) - OY + 0.2)
for v in board.GetTracks():
    if v.GetClass() == "PCB_VIA":
        p = v.GetPosition(); r = mm(v.GetWidth(pcbnew.F_Cu)) / 2 + 0.3
        block(mm(p.x) - OX - r, mm(p.y) - OY - r, mm(p.x) - OX + r, mm(p.y) - OY + r)

# 最大の空き矩形を貪欲に(ヒストグラム法)何個か取り出す
found = []
for _ in range(8):
    best = (0, None)
    hgt = [0] * nx
    for j in range(ny):
        for i in range(nx):
            hgt[i] = hgt[i] + 1 if not bad[j][i] else 0
        st = []
        for i in range(nx + 1):
            h = hgt[i] if i < nx else 0
            s = i
            while st and st[-1][1] >= h:
                s, hh = st.pop()
                area = hh * (i - s)
                if area > best[0] and hh * G >= 3.0:
                    best = (area, (s, j - hh + 1, i - 1, j))
            st.append((s, h))
    if not best[1]:
        break
    i0, j0, i1, j1 = best[1]
    found.append((i0 * G, j0 * G, (i1 + 1) * G, (j1 + 1) * G))
    block(i0 * G, j0 * G, (i1 + 1) * G, (j1 + 1) * G)
for r in found:
    print(f"空き x {r[0]:5.2f}..{r[2]:5.2f}  y {r[1]:5.2f}..{r[3]:5.2f}  ({r[2]-r[0]:.1f} x {r[3]-r[1]:.1f}mm)")
