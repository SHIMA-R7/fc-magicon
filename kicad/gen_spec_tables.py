"""ネットリスト(FC-MAGICON.net)から仕様書用の表(Markdown)を作る → ../docs/_tables.md
    python gen_spec_tables.py
カセット端子・GPIO・J4・J5 の表は、手で書き写さずここから作る。
"""
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
net = open(os.path.join(HERE, "FC-MAGICON.net"), encoding="utf-8").read()

# ネット名 -> [(部品, ピン, ピン名)]
nodes = defaultdict(list)
for block in re.findall(r'\(net\s+\(code "\d+"\)\s+\(name "([^"]*)"\)(.*?)\n\t\t\)', net, re.S):
    name, body = block
    for ref, pin, fn in re.findall(r'\(node\s+\(ref "([^"]+)"\)\s+\(pin "([^"]+)"\)(?:\s+\(pinfunction "([^"]*)"\))?', body):
        nodes[name.lstrip("/")].append((ref, pin, fn))
pin_net = {(r, p): n for n, lst in nodes.items() for r, p, _ in lst}
pin_fn = {(r, p): re.sub(r"_\d+$", "", f) for lst in nodes.values() for r, p, f in lst}   # KiCad が付ける _ピン番号 を外す


def clean(n):
    return n.replace("~{", "/").replace("}", "")


def others(netname, exclude):
    if netname == "GND":
        return "GND(全部品共通)"
    out = []
    for r, p, f in nodes.get(netname, []):
        if r in exclude:
            continue
        if r.startswith("P"):
            f = re.sub(r"_\d+$", "", f)
            out.append(f"{r}-{p}({f})" if f else f"{r}-{p}")
        else:
            out.append(f"{r}.{p}")
    return ", ".join(sorted(set(out))) or "—"


lines = []
# ---- カセット端子
FACE = lambda n: "表(手前)" if n <= 30 else "裏(奥)"
lines += ["### カセット端子 J1(60ピン)", "",
          "| 番 | 面 | 信号 | つながる先 |", "|---:|---|---|---|"]
for n in range(1, 61):
    nm = pin_net.get(("J1", str(n)), "")
    nm = "" if nm.startswith("unconnected") else nm.lstrip("/")
    dest = others(nm, {"J1", "J4"}) if nm else "—"
    lines.append(f"| {n} | {FACE(n)} | {clean(nm) or '(なし)'} | {dest} |")
lines.append("")

# ---- GPIO
lines += ["### Core2350B のピン(ヘッダー P1〜P4)", "",
          "| ヘッダー-ピン | モジュールのピン | 信号 | つながる先 |", "|---|---|---|---|"]
rows = []
for ref in ("P1", "P3", "P4", "P2"):
    for pin in range(1, 17):
        fn = pin_fn.get((ref, str(pin)), "")
        nm = pin_net.get((ref, str(pin)), "")
        nm = "" if nm.startswith("unconnected") else nm.lstrip("/")
        dest = others(nm, {"P1", "P2", "P3", "P4", "J4", "J5"}) if nm else "—"
        m = re.match(r"GPIO(\d+)", fn or "")
        key = (0, int(m.group(1))) if m else (1, ref, pin)
        rows.append((key, f"| {ref}-{pin} | {fn or '?'} | {clean(nm) or '(未接続)'} | {dest} |"))
lines += [r for _, r in sorted(rows)] + [""]

# ---- J4
lines += ["### J4 ブレイクアウト(2x30)", "",
          "列 k(左から 1〜30)の下の列 = カセット k 番、上の列 = カセット k+30 番。", "",
          "| 列 | 下の列(ヘッダー番号) | カセット番・信号 | 上の列(ヘッダー番号) | カセット番・信号 |", "|---:|---:|---|---:|---|"]
for k in range(30):
    a = pin_net.get(("J4", str(2 * k + 1)), "").lstrip("/")
    b = pin_net.get(("J4", str(2 * k + 2)), "").lstrip("/")
    lines.append(f"| {k + 1} | {2 * k + 1} | {k + 1}: {clean(a)} | {2 * k + 2} | {k + 31}: {clean(b)} |")
lines.append("")

# ---- J5
lines += ["### J5 デバッグ(2x8)", "", "| ピン | 信号 | つながる先 |", "|---:|---|---|"]
for p in range(1, 17):
    nm = pin_net.get(("J5", str(p)), "").lstrip("/")
    lines.append(f"| {p} | {clean(nm)} | {others(nm, {'J5', 'J4'})} |")
lines.append("")

# ---- 周辺部品のピン
lines += ["### 周辺部品の接続", "", "| 部品-ピン | 信号 |", "|---|---|"]
for ref in ("U2", "Q1", "D1", "C1", "C2", "C3", "C4", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11",
            "JP1", "JP2", "JP3", "SW1", "SW2", "J2", "J3", "TP1", "TP2", "TP3", "TP4", "TP5"):
    pins = sorted({p for (r, p) in pin_net if r == ref}, key=lambda s: int(s) if s.isdigit() else 0)
    for p in pins:
        nm = pin_net[(ref, p)]
        nm = "(未接続)" if nm.startswith("unconnected") else clean(nm.lstrip("/"))
        fn = clean(pin_fn.get((ref, p), ""))
        lines.append(f"| {ref}-{p}{' (' + fn + ')' if fn and not fn.isdigit() else ''} | {nm} |")
lines.append("")

os.makedirs(os.path.join(HERE, "..", "docs"), exist_ok=True)
open(os.path.join(HERE, "..", "docs", "_tables.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("nets", len(nodes), "-> docs/_tables.md", len(lines), "lines")
