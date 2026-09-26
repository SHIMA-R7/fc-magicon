"""ハードウェア仕様書を組み立てる(ふつうのpythonで実行)。
    python build_spec.py
  hardware_spec_body.md(手で書く本文)+ 部品表(../kicad/bom.csv)+ 付録の表(_tables.md、kicad/gen_spec_tables.py が作る)
  → hardware_spec.md と、印刷用の hardware_spec.html(A4)
"""
import csv
import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
body = open(os.path.join(HERE, "hardware_spec_body.md"), encoding="utf-8").read()
tables = open(os.path.join(HERE, "_tables.md"), encoding="utf-8").read()
bom_rows = list(csv.reader(open(os.path.join(HERE, "..", "kicad", "bom.csv"), encoding="utf-8-sig")))

bom = ["## 13. 部品表", "", "| 部品 | 数 | 記号 | フットプリント | メモ |", "|---|---:|---|---|---|"]
for r in bom_rows[1:]:
    bom.append("| " + " | ".join(c.replace("|", "/") for c in r) + " |")
md = body.rstrip() + "\n\n" + "\n".join(bom) + "\n\n## 付録. ピン・接続の一覧(ネットリストから自動生成)\n\n" + tables
md += "\n## ファイル\n\n" + "\n".join([
    "| ファイル | 内容 |", "|---|---|",
    "| kicad/gen_schematic.py | 回路図を生成(FC-MAGICON.kicad_sch) |",
    "| kicad/gen_footprints.py | カセット端子のフットプリントを生成 |",
    "| kicad/build_pcb.py | 部品配置(place)、配線の取り込みとベタ(import)、一部の配線やり直し(reroute) |",
    "| kicad/route.py | Freerouting で自動配線 |",
    "| kicad/export_gerbers.ps1 | DRC を確認してガーバーと zip を出力 |",
    "| kicad/bom.py / print_bom.ps1 | 部品表の作成と印刷 |",
    "| kicad/print_fit_check.ps1 | 実寸の現物合わせシートを印刷 |",
    "| kicad/gen_spec_tables.py / docs/build_spec.py | この仕様書を作る |",
]) + "\n"
open(os.path.join(HERE, "hardware_spec.md"), "w", encoding="utf-8").write(md)


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    return s


out, lines, i = [], md.splitlines(), 0
while i < len(lines):
    ln = lines[i]
    if ln.startswith("```"):
        j = i + 1
        while not lines[j].startswith("```"):
            j += 1
        out.append("<pre>" + html.escape("\n".join(lines[i + 1:j])) + "</pre>")
        i = j + 1
        continue
    m = re.match(r"^(#{1,3}) (.*)", ln)
    if m:
        out.append(f"<h{len(m.group(1))}>{inline(m.group(2))}</h{len(m.group(1))}>")
        i += 1
        continue
    if ln.startswith("|"):
        rows = []
        while i < len(lines) and lines[i].startswith("|"):
            rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
            i += 1
        head, rest = rows[0], [r for r in rows[1:] if not re.fullmatch(r"[-:| ]+", "|".join(r))]
        t = ["<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"]
        t += ["<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rest]
        out.append("".join(t) + "</tbody></table>")
        continue
    if re.match(r"^(- |\d+\. )", ln):
        tag = "ol" if re.match(r"^\d+\. ", ln) else "ul"
        items = []
        while i < len(lines) and re.match(r"^(- |\d+\. |   \S)", lines[i]):
            if re.match(r"^(- |\d+\. )", lines[i]):
                items.append(re.sub(r"^(- |\d+\. )", "", lines[i]))
            else:
                items[-1] += " " + lines[i].strip()
            i += 1
        out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
        continue
    if ln.strip():
        para = [ln]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||- |\d+\. |```)", lines[i]):
            para.append(lines[i])
            i += 1
        out.append("<p>" + inline(" ".join(para)) + "</p>")
        continue
    i += 1

css = """
@page { size: A4; margin: 14mm 12mm; }
body { font-family: 'Yu Gothic UI', 'Meiryo', sans-serif; font-size: 9.5pt; line-height: 1.45; color: #000; }
h1 { font-size: 17pt; border-bottom: 2px solid #000; padding-bottom: 2mm; }
h2 { font-size: 12.5pt; border-bottom: 1px solid #000; margin-top: 7mm; page-break-after: avoid; }
h3 { font-size: 10.5pt; margin-top: 5mm; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 2mm 0 3mm; font-size: 8.5pt; }
th, td { border: 1px solid #888; padding: 0.8mm 1.5mm; vertical-align: top; }
th { background: #eee; }
tr { page-break-inside: avoid; }
pre { font-family: 'MS Gothic', monospace; font-size: 7.5pt; line-height: 1.25; border: 1px solid #888; padding: 2mm; }
code { font-family: Consolas, monospace; font-size: 8.5pt; }
"""
page = f"<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>FC-MAGICON ハードウェア仕様書</title><style>{css}</style></head><body>{''.join(out)}</body></html>"
open(os.path.join(HERE, "hardware_spec.html"), "w", encoding="utf-8").write(page)
print("->", os.path.join(HERE, "hardware_spec.md"), "/ hardware_spec.html")
