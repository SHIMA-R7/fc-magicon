"""回路図の接続だけを変えた時に、配線済みの基板のパッドのネットをネットリストに合わせる。
    E:\\KiCad\\bin\\python.exe sync_nets.py
変わったパッドと、そのパッドに付いていた古いネットを表示する(古いネットの配線は build_pcb.py reroute で消して引き直す)。
"""
import pcbnew

import build_pcb as B

_, padnets = B.parse_netlist()
board = pcbnew.LoadBoard(B.PCB)
nets = dict(board.GetNetsByName().items())
nets = {str(k): v for k, v in nets.items()}
old = set()
for f in board.GetFootprints():
    for pad in f.Pads():
        n = padnets.get((f.GetReference(), pad.GetNumber()))
        if n and pad.GetNetname() != n:
            if n not in nets:
                ni = pcbnew.NETINFO_ITEM(board, n)
                board.Add(ni)
                nets[n] = ni
            print(f"{f.GetReference()}.{pad.GetNumber()}: {pad.GetNetname()} -> {n}")
            old.add(pad.GetNetname())
            pad.SetNet(nets[n])
pcbnew.SaveBoard(B.PCB, board)
print("古いネット:", " ".join(sorted(o.lstrip("/") for o in old)))
