"""
remote_pc.py の KeyboardBridge(ファミリーベーシックのキーボード → PC のキー)を、実際にはキーを送らずに確かめる。
    python test_keyboard_bridge.py
  6502 が $5F01-$5F09 に書く 9 バイト(押すと 0)を作って 1 フレームずつ渡し、PC に送るはずのスキャンコードを記録して比べる。
"""
import sys

from remote_pc import KB_NAMES, SC, KeyboardBridge, kb_pressed


def rows_of(keys):
    """押しているキーの集合 → 6502 が書く 9 バイト(下位 4 ビット = 列 0 の bit1〜4、上位 4 ビット = 列 1、押すと 0)"""
    rows = [0xFF] * 9
    for r in range(9):
        for i in range(8):
            if KB_NAMES[r][i] in keys:
                bit = (3 - i) if i < 4 else (7 - (i - 4))
                rows[r] &= ~(1 << bit)
    return bytes(rows)


log = []
kb = KeyboardBridge(lambda code, up: log.append((code, "up" if up else "down")))


def frames(keys, n=1):
    for _ in range(n):
        kb.update(kb_pressed(rows_of(keys)))


ok = True


def check(name, want):
    global ok
    good = log == want
    print(f"{'OK' if good else 'NG'}  {name}" + ("" if good else f"\n    want {want}\n    got  {log}"))
    ok &= good
    log.clear()


# 9 バイトの並びが往復で一致するか(72 キー全部)
bad = [k for row in KB_NAMES for k in row if kb_pressed(rows_of({k})) != {k}]
print(f"{'OK' if not bad else 'NG'}  72 キーの並び(往復) {bad or ''}")
ok &= not bad

frames(set(), 3)
check("何も押さない", [])
frames({"A"}, 1)
check("A を 1 フレームだけ(チャタリング扱いで送らない)", [])
frames(set(), 2)
frames({"A"}, 2)
check("A を 2 フレーム続けて押すと送る", [(SC["A"], "down")])
frames(set(), 2)
check("A を離す", [(SC["A"], "up")])
frames({"LSHIFT"}, 2); frames(set(), 2)
check("SHIFT はトグル(押して離しても ON のまま)", [(0x2A, "down")])
frames({"1"}, 2); frames(set(), 2)
check("SHIFT ON のまま 1", [(SC["1"], "down"), (SC["1"], "up")])
frames({"RETURN"}, 2); frames(set(), 2)
check("RETURN で SHIFT が戻る", [(SC["RETURN"], "down"), (0x2A, "up"), (SC["RETURN"], "up")])
frames({"GRPH"}, 2); frames(set(), 2); frames({"GRPH"}, 2); frames(set(), 2)
check("GRPH(Alt)は押すたびに ON / OFF", [(0x38, "down"), (0x38, "up")])
frames({"STOP"}, 2); frames(set(), 2)
check("STOP は BackSpace", [(0x0E, "down"), (0x0E, "up")])
frames({"_", "YEN", "@", "KANA"}, 2); frames(set(), 2)
# 同じフレームのキーは KB_NAMES の順(行 0 の YEN・KANA → 行 1 の @・_)に送る
check("JIS の記号(_ ¥ @)とカナ(半角/全角)", [(0x7D, "down"), (0x29, "down"), (0x1A, "down"), (0x73, "down"),
                                          (0x7D, "up"), (0x29, "up"), (0x1A, "up"), (0x73, "up")])
frames({"CTR"}, 2); frames({"CTR", "Q"}, 2)
frames(set(), 3)
check("CTR(トグル)+ Q", [(0x1D, "down"), (SC["Q"], "down"), (SC["Q"], "up")])
all_keys = {k for row in KB_NAMES for k in row}
frames(all_keys, 3)
check("全部押されて見える = キーボード無し(何も送らない)", [])
frames({"UP"}, 2)
kb.release_all()
check("止めた時・途切れた時は全部離す(トグルの CTR も)", [(SC["UP"], "down"), (SC["UP"], "up"), (0x1D, "up")])
print("全部 OK" if ok else "NG あり")
sys.exit(0 if ok else 1)
