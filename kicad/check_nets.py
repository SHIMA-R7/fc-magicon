"""生成した回路図の簡易チェック: 括弧の対応と、1か所にしか現れないネットラベル(配線漏れ候補)を出す。"""
import re
from collections import Counter

s = open("FC-MAGICON.kicad_sch", encoding="utf-8").read()
depth = 0
for ch in s:
    depth += (ch == "(") - (ch == ")")
    assert depth >= 0, "閉じ括弧が多すぎる"
print("括弧の深さ(0で正常):", depth)

labels = Counter(re.findall(r'\(label "([^"]+)"', s))
print("ネット数:", len(labels))
print("1か所だけのラベル:", sorted(k for k, v in labels.items() if v == 1))
