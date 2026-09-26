"""
FC-MAGICON 基板(ファミコン用カセット、2層、1.2mm)を組み立てる。

  KiCad付属のpythonで実行:
    E:\\KiCad\\bin\\python.exe build_pcb.py place   … 部品配置と Freerouting 用 .dsn の書き出し
    E:\\KiCad\\bin\\python.exe build_pcb.py import  … Freerouting の結果(.ses)を取り込み GND ベタを貼る

  外形: 本体 90.0 x 46.1mm + 差し込み部 78.4 x 10.7mm(スロットに刺さる所だけ規格どおり。残りは自由、ケースは3Dプリント)
  全部品を表(F)面に載せる。F面(本体の手前を向く)の端子 = 1〜30番、裏(B)面 = 31〜60番。
  Core2350B は 2x8 ピンソケット4個(風車状)で載せる。ソケットの向きは、照合済みの穴位置に合うように自動で決める。
"""
import json
import math
import os
import re
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "FC-MAGICON"
PCB = os.path.join(HERE, NAME + ".kicad_pcb")
KICAD_FP = r"E:\KiCad\share\kicad\footprints"
MM = pcbnew.FromMM

OX, OY = 100.0, 100.0          # 基板左上の座標
TOP = 9.0                      # 規格(56.8mm)より 9mm 高くする(J4 ブレイクアウト・J5 デバッグの場所)
SHIFT = 3.0                    # PLACEMENT などの y(規格基板の座標)に足す量。J4 を下辺へ移したので上へ 6mm 詰めた
W, BODY_H = 90.0, 46.1 + TOP   # 本体
TONGUE_W, TONGUE_L = 78.4, 10.7
H = BODY_H + TONGUE_L
TX0 = (W - TONGUE_W) / 2
KEEP_Y = BODY_H + 2.5          # 端子の付け根(パッド上端 = BODY_H+3.0)より少し上。ベタはここまで、端子の隙間は配線禁止

# Core2350B(25.4mm角)の左上の位置。FPCコネクタが上辺側になる向き
MOD_X, MOD_Y = 32.3, 5.0 + SHIFT
J4_Y = BODY_H - 5.1            # J4(差し込み部のすぐ上)の上の列 = カセット 31〜60番、下の列 = 1〜30番。各列が端子の真上
J5_X, J5_Y = 60.5, 3.3

# (リファレンス, 回転, 位置合わせのパッド, x, y)。パッド None はフットプリント原点。J1 以外の y は TOP だけ下へずらして置く
PLACEMENT = [
    ("J1", 0, None, W / 2, BODY_H),
    ("J2", 0, None, 7.6, 9.0),            # 3.5mm ジャック。差し込み口が左辺から外へ出る
    ("SW1", 0, "1", 18.0, 3.5),
    ("SW2", 0, "1", 18.0, 11.5),
    # 抵抗(横置き 7.62mm)左の列
    ("R7", 0, "1", 2.0, 18.0), ("R9", 0, "1", 2.0, 21.2), ("R8", 0, "1", 2.0, 24.4), ("R10", 0, "1", 2.0, 27.6),
    ("R11", 0, "1", 2.0, 30.8), ("R4", 0, "1", 2.0, 34.0), ("R5", 0, "1", 2.0, 37.2), ("R6", 0, "1", 2.0, 40.4),

    # 右の列
    ("R2", 0, "1", 13.5, 19.5), ("R3", 0, "1", 13.5, 22.7),
    # コンデンサーは足を縦に並べる(右へ寝かせるには、倒す向きと足の並びが直角でないといけない)
    ("C3", 90, "1", 14.5, 28.4), ("C4", 90, "1", 15.0, 34.0), ("Q1", 0, "1", 13.5, 39.0), ("R1", 0, "1", 13.5, 43.0),
    # 右側
    # DIP-20(SN74LVC245AN)。180°回して、出力(B側)をモジュール側の左列へ、入力(A側)を空いている右列へ向ける
    ("U2", 180, "1", 71.62, 29.36),
    ("C2", 90, "1", 78.5, 11.0),
    ("JP1", 0, None, 82.0, 15.0), ("JP2", 0, None, 82.0, 19.0), ("JP3", 0, None, 82.0, 23.0),
    ("J3", 90, "1", 27.5, -0.7),             # SWD。左上に横向き(モジュール上辺の SWD/SWCLK/BOOTSEL/RUN をまとめて左へ引く)
    ("J6", 90, "1", 40.0, -0.3),             # USB の予備ランド(VBUS/D-/D+/GND)。モジュール上辺の USB ピンの真上
    ("VR1", 0, "1", 24.6, 25.8),             # 拡張音源の音量(KVSF637AC104)。C3 の右上、モジュールの左
    ("D1", 0, "1", 60.5, 34.2), ("C1", 90, "1", 76.0, 35.2),
    ("TP1", 0, None, 62.0, 39.3), ("TP2", 0, None, 65.0, 39.3), ("TP3", 0, None, 68.0, 39.3),
    ("TP4", 0, None, 71.0, 39.3), ("TP5", 0, None, 74.0, 39.3),
]

POWER_NETS = ["/+5V", "/VBUS_MOD", "/+3V3", "/GND"]   # 回路図のネット名(先頭に / が付く)

# 右へ寝かせるコンデンサー: (記号, 倒した本体の長さ, 幅, 有極性)。電解 φ5×高さ11mm、セラミックは 5mm 程度
LAYDOWN = [("C1", 12.5, 6.0, True), ("C4", 12.5, 6.0, True), ("C2", 6.5, 4.5, False), ("C3", 6.5, 4.5, False)]


def hole(c, r):
    return MOD_X + 1.27 + 2.54 * c, MOD_Y + 1.27 + 2.54 * r


def socket_targets(ref):
    """照合済みのピン位置(README / print_core2350b_pinmap.ps1 と同じ)。ピン番号 -> (x, y)"""
    t = {}
    for k in range(8):
        if ref == "P1":
            t[2 * k + 1], t[2 * k + 2] = hole(0, k), hole(1, k)
        elif ref == "P3":
            t[2 * k + 1], t[2 * k + 2] = hole(k, 9), hole(k, 8)
        elif ref == "P4":
            t[2 * k + 1], t[2 * k + 2] = hole(9, 9 - k), hole(8, 9 - k)
        elif ref == "P2":
            t[2 * k + 1], t[2 * k + 2] = hole(9 - k, 0), hole(9 - k, 1)
        elif ref == "J5":
            # 回転だけで合う並びにするため、奇数番を下の列・偶数番を上の列にする
            t[2 * k + 1], t[2 * k + 2] = (J5_X + 2.54 * k, J5_Y + 2.54), (J5_X + 2.54 * k, J5_Y)
    if ref == "J4":     # 各列がカセット端子の真上: 2k+1 番 = カセット k+1 番(下の列)、2k+2 番 = カセット k+31 番(上の列)。回転だけで合う並び
        for k in range(30):
            x = W / 2 - 36.83 + 2.54 * k
            t[2 * k + 1], t[2 * k + 2] = (x, J4_Y + 2.54), (x, J4_Y)
    return t


def write_project():
    path = os.path.join(HERE, NAME + ".kicad_pro")
    pro = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    pro.setdefault("meta", {"filename": NAME + ".kicad_pro", "version": 3})
    base = {"clearance": 0.2, "track_width": 0.25, "via_diameter": 0.7, "via_drill": 0.35,
            "microvia_diameter": 0.3, "microvia_drill": 0.1, "diff_pair_width": 0.2, "diff_pair_gap": 0.25,
            "diff_pair_via_gap": 0.25, "wire_width": 6, "bus_width": 12, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)",
            "schematic_color": "rgba(0, 0, 0, 0.000)", "priority": 2147483647}
    pro["net_settings"] = {
        "classes": [dict(base, name="Default"),
                    dict(base, name="Power", track_width=0.4, via_diameter=0.7, via_drill=0.35, priority=0)],
        "meta": {"version": 4},
        "netclass_patterns": [{"netclass": "Power", "pattern": n} for n in POWER_NETS],
    }
    json.dump(pro, open(path, "w", encoding="utf-8"), indent=2)


def sexpr(text):
    tokens = re.findall(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+', text)
    stack, cur = [], []
    for t in tokens:
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            done, cur = cur, stack.pop()
            cur.append(done)
        else:
            cur.append(t[1:-1] if t.startswith('"') else t)
    return cur[0]


def child(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def parse_netlist():
    root = sexpr(open(os.path.join(HERE, NAME + ".net"), encoding="utf-8").read())
    comps = {}
    for c in child(child(root, "components")[0], "comp"):
        comps[child(c, "ref")[0][1]] = (child(c, "value")[0][1], child(c, "footprint")[0][1])
    pads = {}
    for n in child(child(root, "nets")[0], "net"):
        name = child(n, "name")[0][1]          # 回路図と照合できるよう、先頭の / は残す
        for node in child(n, "node"):
            pads[(child(node, "ref")[0][1], child(node, "pin")[0][1])] = name
    return comps, pads


def load_fp(fpid):
    lib, name = fpid.split(":")
    path = os.path.join(HERE, lib + ".pretty") if lib == NAME else os.path.join(KICAD_FP, lib + ".pretty")
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        raise RuntimeError(f"フットプリントが見つからない: {fpid}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def pad_pos(fp, num):
    for p in fp.Pads():
        if p.GetNumber() == num:
            return p.GetPosition()
    raise KeyError(num)


def V(x, y):
    return pcbnew.VECTOR2I(MM(OX + x), MM(OY + y))


def fit_socket(fp, ref):
    """ピン1〜16が照合済みの穴位置に来る回転を探して置く。"""
    tgt = socket_targets(ref)
    for rot in (0, 90, 180, 270):
        fp.SetOrientationDegrees(rot)
        p1 = pad_pos(fp, "1")
        fp.Move(pcbnew.VECTOR2I(MM(OX + tgt[1][0]) - p1.x, MM(OY + tgt[1][1]) - p1.y))
        err = max(math.hypot(pcbnew.ToMM(pad_pos(fp, str(n)).x) - OX - x, pcbnew.ToMM(pad_pos(fp, str(n)).y) - OY - y)
                  for n, (x, y) in tgt.items())
        if err < 0.01:
            return rot
    raise RuntimeError(f"{ref}: 穴位置に合う向きが無い")


def outline(board):
    pts = [(0, 0), (W, 0), (W, BODY_H), (W - TX0, BODY_H), (W - TX0, H), (TX0, H), (TX0, BODY_H), (0, BODY_H)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(x1, y1))
        s.SetEnd(V(x2, y2))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.1))
        board.Add(s)


def rule_area(board, pts, fills=False, layer=None):
    ka = pcbnew.ZONE(board)
    ka.SetIsRuleArea(True)
    ka.SetDoNotAllowTracks(True)
    ka.SetDoNotAllowVias(True)
    ka.SetDoNotAllowZoneFills(not fills)
    ka.SetDoNotAllowPads(False)
    ka.SetDoNotAllowFootprints(False)
    ls = pcbnew.LSET()
    for l in ([layer] if layer is not None else [pcbnew.F_Cu, pcbnew.B_Cu]):
        ls.AddLayer(l)
    ka.SetLayerSet(ls)
    ol = ka.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(MM(OX + x), MM(OY + y))
    board.Add(ka)


def text(board, s, x, y, size=1.0, layer=pcbnew.F_SilkS, thick=0.15, top=True):
    """y は SHIFT を足す前の座標(top=False なら基板上辺からの実座標)"""
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(V(x, y + SHIFT if top else y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
    t.SetTextThickness(MM(thick))
    if layer in (pcbnew.B_SilkS,):
        t.SetMirrored(True)
    board.Add(t)


def place():
    write_project()
    comps, padnets = parse_netlist()
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    board.GetDesignSettings().SetBoardThickness(MM(1.2))
    nets = {}
    for net in sorted(set(padnets.values())):
        ni = pcbnew.NETINFO_ITEM(board, net)
        board.Add(ni)
        nets[net] = ni
    outline(board)

    placed = {r for r, *_ in PLACEMENT} | {"P1", "P2", "P3", "P4", "J4", "J5"}
    missing = set(comps) - placed
    if missing:
        raise RuntimeError(f"配置が決まっていない部品: {sorted(missing)}")

    def add(ref):
        value, fpid = comps[ref]
        fp = load_fp(fpid)
        fp.SetReference(ref)
        fp.SetValue(value)
        board.Add(fp)
        return fp

    for ref, rot, anchor, x, y in PLACEMENT:
        y = y if ref == "J1" else y + SHIFT
        fp = add(ref)
        fp.SetPosition(V(x, y))
        fp.SetOrientationDegrees(rot)
        if anchor:
            p = pad_pos(fp, anchor)
            t = V(x, y)
            fp.Move(pcbnew.VECTOR2I(t.x - p.x, t.y - p.y))
    for ref in ("J4", "J5"):
        print(f"  {ref}: 回転 {fit_socket(add(ref), ref)}°")
    for ref in ("P1", "P2", "P3", "P4"):
        fp = add(ref)
        rot = fit_socket(fp, ref)
        print(f"  {ref}: 回転 {rot}°")
        # 4個は風車状に隙間なく並ぶので、個々のシルク・コートヤードは消して、モジュール全体の外形を1つだけ描く
        for item in list(fp.GraphicalItems()):
            if item.GetLayer() in (pcbnew.F_SilkS, pcbnew.F_CrtYd, pcbnew.F_Fab):
                fp.Remove(item)
        fp.Reference().SetVisible(False)
        if ref == "P1":
            for layer, m, width in ((pcbnew.F_SilkS, 0.3, 0.15), (pcbnew.F_Fab, 0.0, 0.1)):
                s = pcbnew.PCB_SHAPE(fp)
                s.SetShape(pcbnew.SHAPE_T_RECTANGLE)
                s.SetStart(V(MOD_X - m, MOD_Y - m))
                s.SetEnd(V(MOD_X + 25.4 + m, MOD_Y + 25.4 + m))
                s.SetLayer(layer)
                s.SetWidth(MM(width))
                fp.Add(s)
            # モジュール上のFPCコネクタの位置(向きの目印)
            s = pcbnew.PCB_SHAPE(fp)
            s.SetShape(pcbnew.SHAPE_T_RECTANGLE)
            s.SetStart(V(MOD_X + 15.3, MOD_Y + 4.9))
            s.SetEnd(V(MOD_X + 19.7, MOD_Y + 8.6))
            s.SetLayer(pcbnew.F_SilkS)
            s.SetWidth(MM(0.15))
            fp.Add(s)

    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net = padnets.get((fp.GetReference(), pad.GetNumber()))
            if net:
                pad.SetNet(nets[net])
        f = fp.Reference()
        f.SetTextSize(pcbnew.VECTOR2I(MM(0.9), MM(0.9)))
        f.SetTextThickness(MM(0.13))

    # 端子部: パッドには上(付け根側)からだけ入れる。端子の隙間・両脇・先端は配線・ビア・ベタ禁止
    j1 = board.FindFootprintByReference("J1")
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        xs = sorted((pcbnew.ToMM(p.GetBoundingBox().GetLeft()) - OX, pcbnew.ToMM(p.GetBoundingBox().GetRight()) - OX)
                    for p in j1.Pads() if p.IsOnLayer(layer))
        edges = [TX0 - 0.5] + [v for a, b in xs for v in (a, b)] + [W - TX0 + 0.5]
        for x0, x1 in zip(edges[0::2], edges[1::2]):
            rule_area(board, [(x0, KEEP_Y), (x1, KEEP_Y), (x1, H + 0.5), (x0, H + 0.5)], layer=layer)
        bottom = max(pcbnew.ToMM(p.GetBoundingBox().GetBottom()) - OY for p in j1.Pads())
        rule_area(board, [(TX0 - 0.5, bottom), (W - TX0 + 0.5, bottom), (W - TX0 + 0.5, H + 0.5), (TX0 - 0.5, H + 0.5)], layer=layer)
    # モジュールの下(ソケットの内側)は部品を置かないだけで、配線は通してよい

    j1 = board.FindFootprintByReference("J1")
    j1.SetAllowSolderMaskBridges(True)     # 金メッキ端子はレジストを抜いているので、端子間のレジスト無しは意図どおり
    for item in list(j1.GraphicalItems()):  # 端子の番号は J4 の列番号で分かるので、J4 と重なる表面のシルク番号は消す
        if item.GetLayer() == pcbnew.F_SilkS and isinstance(item, pcbnew.PCB_TEXT):
            j1.Remove(item)

    # コンデンサーは足を曲げて右へ寝かせられるよう、倒した本体が載る範囲をコートヤード(部品禁止)にしてシルクで描く
    for ref, length, width, polar in LAYDOWN:
        lay_down(board.FindFootprintByReference(ref), length, width, polar)

    # シルク
    text(board, "FC-MAGICON rev0.1", W / 2, 40.5, 1.2)
    text(board, "Core2350B", MOD_X + 12.7, MOD_Y + 16.0, 1.0, top=False)
    text(board, "FPC", MOD_X + 17.5, MOD_Y + 10.0, 0.8, top=False)
    # J4 ブレイクアウトの列番号(上の列 = カセット 31〜60番、下の列 = 1〜30番)
    board.FindFootprintByReference("J4").Reference().SetVisible(False)
    for k in (0, 9, 14, 19, 24, 29):        # 5/35 は R1 と重なるので省く
        text(board, f"{k + 1}/{k + 31}", W / 2 - 36.83 + 2.54 * k, J4_Y - 2.3, 0.8, top=False)
    text(board, "31-60", 3.6, J4_Y, 0.8, top=False)
    text(board, "1-30", 3.6, J4_Y + 2.54, 0.8, top=False)
    board.FindFootprintByReference("J5").Reference().SetVisible(False)
    text(board, "J5", J5_X - 2.4, J5_Y + 1.27, 0.8, top=False)
    text(board, "BOOTSEL", 28.2, 5.75, 0.8)
    text(board, "RESET", 27.6, 13.75, 0.8)
    for s, y in (("MCU", 15.0), ("V(A10)", 19.0), ("H(A11)", 23.0)):
        text(board, s, 86.8, y, 0.8)
    text(board, "CIRAM A10: close ONE", 82.0, 26.3, 0.8)
    text(board, "/RD D0 M2 /RS GND", 68.0, 41.5, 0.8)
    j3 = board.FindFootprintByReference("J3")
    j3.Reference().SetVisible(False)
    for s, n in (("CLK", "1"), ("GND", "2"), ("DIO", "3")):
        p = pad_pos(j3, n)
        text(board, s, pcbnew.ToMM(p.x) - OX, pcbnew.ToMM(p.y) - OY + 2.4, 0.8, top=False)
    label_j6(board)

    text(board, "LINE OUT", 7.6, 15.8, 0.8)
    for ref in ("SW1", "SW2"):
        board.FindFootprintByReference(ref).Reference().SetVisible(False)   # BOOTSEL / RESET の文字で代える
    text(board, "FC-MAGICON  pins 31-60 side (rear)", W / 2, 42.0, 1.0, pcbnew.B_SilkS)
    text(board, "PCB 1.2mm / gold fingers / 45deg bevel", W / 2, 44.0, 0.8, pcbnew.B_SilkS)

    tidy_refs(board)

    ds = board.GetDesignSettings()
    ds.m_TrackMinWidth = MM(0.15)     # Freerouting が IC の足の間で 0.19mm 程度に細らせる。JLCPCB の下限は 0.127mm
    ds.m_ViasMinSize = MM(0.6)
    ds.m_MinThroughDrill = MM(0.3)
    ds.m_CopperEdgeClearance = MM(0.3)
    pcbnew.SaveBoard(PCB, board)
    pcbnew.ExportSpecctraDSN(board, os.path.join(HERE, NAME + ".dsn"))
    print("配置して保存:", PCB)


def add_zone(board, layer, net):
    z = pcbnew.ZONE(board)
    ls = pcbnew.LSET()
    ls.AddLayer(layer)
    z.SetLayerSet(ls)
    z.SetNet(board.FindNet(net))
    assert z.GetNetCode() > 0, net
    ol = z.Outline()
    ol.NewOutline()
    m = 0.3
    for x, y in ((m, m), (W - m, m), (W - m, BODY_H - m), (W - TX0 - m, BODY_H - m), (W - TX0 - m, KEEP_Y),
                 (TX0 + m, KEEP_Y), (TX0 + m, BODY_H - m), (m, BODY_H - m)):
        ol.Append(MM(OX + x), MM(OY + y))
    z.SetLocalClearance(MM(0.25))
    z.SetMinThickness(MM(0.2))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(MM(0.3))
    z.SetThermalReliefSpokeWidth(MM(0.5))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)   # どこにもつながらないベタの島は消す
    board.Add(z)
    return z


def add_stitching_vias(board, zones, pitch=2.5, via_d=0.6, drill=0.3):
    gnd = board.FindNet("/GND")
    polys = [z.GetFilledPolysList(z.GetFirstLayer()) for z in zones]
    margin = via_d / 2 + 0.3
    count = 0
    y = 1.5
    while y < BODY_H - 1.0:
        x = 1.5
        while x < W - 1.0:
            ok = all(poly.Contains(V(x + margin * math.cos(math.pi * k / 4), y + margin * math.sin(math.pi * k / 4)))
                     for poly in polys for k in range(8)) and all(poly.Contains(V(x, y)) for poly in polys)
            if ok:
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(V(x, y))
                v.SetWidth(MM(via_d))
                v.SetDrill(MM(drill))
                v.SetNet(gnd)
                board.Add(v)
                count += 1
            x += pitch
        y += pitch
    return count


def label_j6(board):
    """USB の予備ランド J6 のシルク(各ピンの名前と、同時につながない注意)"""
    j6 = board.FindFootprintByReference("J6")
    j6.Reference().SetVisible(False)
    for s, n in (("5V", "1"), ("D-", "2"), ("D+", "3"), ("G", "4")):
        p = pad_pos(j6, n)
        text(board, s, pcbnew.ToMM(p.x) - OX, pcbnew.ToMM(p.y) - OY + 2.4, 0.8, top=False)
    p = pad_pos(j6, "4")
    text(board, "USB", pcbnew.ToMM(p.x) - OX + 3.3, pcbnew.ToMM(p.y) - OY, 0.8, top=False)


def lay_down(fp, length, width, polar):
    """足の右端から右へ length、足の並びの中心から上下 width/2 を、倒した本体の置き場にする。"""
    pads = list(fp.Pads())
    x0 = max(pcbnew.ToMM(p.GetBoundingBox().GetRight()) for p in pads) - OX + 0.3
    ys = [pcbnew.ToMM(p.GetPosition().y) - OY for p in pads]
    xs = [pcbnew.ToMM(p.GetPosition().x) - OX for p in pads]
    cy = (min(ys) + max(ys)) / 2
    # 元のコートヤード(立てた時の本体)と倒した本体を合わせた長方形1つにする(コートヤードは閉じた形1つでないといけない)
    old = [it for it in fp.GraphicalItems() if it.GetLayer() == pcbnew.F_CrtYd]
    bx0 = min(pcbnew.ToMM(it.GetBoundingBox().GetLeft()) for it in old) - OX
    by0 = min(pcbnew.ToMM(it.GetBoundingBox().GetTop()) for it in old) - OY
    by1 = max(pcbnew.ToMM(it.GetBoundingBox().GetBottom()) for it in old) - OY
    for it in old:
        fp.Remove(it)
    for layer, (sx, sy, ex, ey), w in (
            (pcbnew.F_CrtYd, (min(bx0, min(xs) - 1.0), min(by0, cy - width / 2 - 0.25),
                              x0 + length + 0.25, max(by1, cy + width / 2 + 0.25)), 0.05),
            (pcbnew.F_SilkS, (x0, cy - width / 2, x0 + length, cy + width / 2), 0.12)):
        s = pcbnew.PCB_SHAPE(fp)
        s.SetShape(pcbnew.SHAPE_T_RECTANGLE)
        s.SetStart(V(sx, sy))
        s.SetEnd(V(ex, ey))
        s.SetLayer(layer)
        s.SetWidth(MM(w))
        fp.Add(s)
    t = pcbnew.PCB_TEXT(fp)
    t.SetText("+ lay ->" if polar else "->")      # セラミックは枠が小さいので矢印だけ
    t.SetPosition(V(x0 + length / 2 - 1.0, cy))
    t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(pcbnew.VECTOR2I(MM(0.8), MM(0.8)))
    t.SetTextThickness(MM(0.12))
    fp.Add(t)


def tidy_refs(board):
    """抵抗・電解コンデンサ・トランジスタの部品番号を本体の中央に置き、隣の部品のシルクと重ならないようにする。"""
    lay = {r: length for r, length, *_ in LAYDOWN}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pads = list(fp.Pads())
        cx = sum(p.GetPosition().x for p in pads) // len(pads)
        cy = sum(p.GetPosition().y for p in pads) // len(pads)
        f = fp.Reference()
        if re.fullmatch(r"R\d+|U2", ref):          # 抵抗・DIPは本体の中央
            f.SetPosition(pcbnew.VECTOR2I(cx, cy))
            f.SetTextAngleDegrees(90 if ref == "U2" else 0)
        elif ref in lay:                           # 寝かせるコンデンサー: 電解は倒した本体の枠の右端、小さいセラミックは枠の上
            right = max(p.GetBoundingBox().GetRight() for p in pads)
            f.SetPosition(pcbnew.VECTOR2I(right + MM(0.3 + lay[ref] - 1.4), cy))
            f.SetTextAngleDegrees(0)
        elif ref == "Q1":                          # トランジスタは右隣(上は C4 を寝かせる場所)
            f.SetPosition(pcbnew.VECTOR2I(max(p.GetBoundingBox().GetRight() for p in pads) + MM(1.6), cy))
        else:
            continue
        f.SetTextSize(pcbnew.VECTOR2I(MM(0.8), MM(0.8)))


def prep_reroute():
    """配線済みの基板から、ベタ・行き止まりのビア(スティッチング用を含む)と、指定したネットの配線を消して .dsn に書き出す。
    Freerouting は残った配線を活かしたまま、足りない所だけを配線する。
        E:\\KiCad\\bin\\python.exe build_pcb.py reroute [ネット名 ...]
    """
    board = pcbnew.LoadBoard(PCB)
    rip = {"/" + n for n in sys.argv[2:]}   # ネット名は先頭の / を付けずに渡す
    zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
    tracks = list(board.GetTracks())       # 消す前に一覧を取っておく(消した後に取り直すと SWIG の参照が壊れる)
    ends = {}
    for t in tracks:
        if t.GetClass() != "PCB_VIA":
            for p in (t.GetStart(), t.GetEnd()):
                ends.setdefault((t.GetNetname(), p.x, p.y), set()).add(t.GetLayer())
    removed = {"tracks": 0, "vias": 0}
    for t in tracks:
        is_via = t.GetClass() == "PCB_VIA"
        if t.GetNetname() in rip or (is_via and len(ends.get((t.GetNetname(), t.GetPosition().x, t.GetPosition().y), ())) < 2):
            board.Delete(t)              # 片面にしか配線がないビア = 行き止まり、またはスティッチング用
            removed["vias" if is_via else "tracks"] += 1
    for z in zones:
        board.Delete(z)
    pcbnew.SaveBoard(PCB, board)
    pcbnew.ExportSpecctraDSN(board, os.path.join(HERE, NAME + ".dsn"))
    print("消した:", removed, "-> .dsn を書き出した")


def import_ses():
    board = pcbnew.LoadBoard(PCB)
    tidy_refs(board)
    ses = os.path.join(HERE, NAME + ".ses")
    if not pcbnew.ImportSpecctraSES(board, ses):
        raise RuntimeError("SESの取り込みに失敗")
    board.GetDesignSettings().m_MinResolvedSpokes = 1
    for z in list(board.Zones()):
        if not z.GetIsRuleArea():
            board.Remove(z)
    zones = [add_zone(board, pcbnew.F_Cu, "/GND"), add_zone(board, pcbnew.B_Cu, "/GND")]
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    n = add_stitching_vias(board, zones)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(PCB, board)
    print(f"配線 {len(board.GetTracks())} 本、GNDスティッチングビア {n} 個 -> {PCB}")


if __name__ == "__main__":
    {"place": place, "import": import_ses, "reroute": prep_reroute}[sys.argv[1]]()
