"""KiCad の DRC/ERC レポートを種類ごとに数え、指定した種類の中身を表示する。
    python drc_summary.py drc.rpt [種類 ...]
"""
import re
import sys
from collections import Counter

lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
show = set(sys.argv[2:])
count = Counter()
for i, line in enumerate(lines):
    m = re.match(r"^\[(\w+)\]", line)
    if not m:
        continue
    kind = m.group(1)
    count[kind] += 1
    if kind in show:
        body = []
        for nxt in lines[i + 1:i + 5]:
            if nxt.startswith("["):
                break
            body.append(nxt.strip())
        print(f"{kind}: {line.split(':', 1)[1].strip()} | " + " | ".join(b for b in body if b.startswith("@")))
for kind, n in count.most_common():
    print(f"{n:5d} {kind}")
