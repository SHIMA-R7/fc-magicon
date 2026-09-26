"""
画面転送(リモートデスクトップ)モードを PC の試験台(sim.exe)で確かめる。
    python test_remote.py [--out DIR]
  1. 試験用の絵(色の帯・文字・基板の写真)を tools/nesframe.py で 1 枚にする(灰色 4 階調 / カラーの 2 通り)
  2. sim.exe で画面転送モードを動かし、その 1 枚を渡して、ファミコンの画面(BMP)を
     nesframe が計算した「見えるはずの絵」とドット単位で比べる(カーソルの所は除く)
  3. カーソル(スプライト)が指定の位置に出ているか
  4. パッドとファミリーベーシックのキーボード(--keys)を押し、6502 が $5F00- に書いた値が合っているか
"""
import argparse
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from nesframe import encode, write_frame   # noqa: E402

SIM = os.path.join(HERE, "sim.exe")


def test_image():
    img = Image.new("RGB", (256, 240), (240, 240, 235))
    d = ImageDraw.Draw(img)
    for i, c in enumerate([(220, 30, 30), (240, 160, 20), (240, 230, 40), (40, 170, 60), (30, 90, 220), (140, 50, 180)]):
        d.rectangle([i * 42, 0, i * 42 + 41, 23], fill=c)
    f = ImageFont.truetype(r"C:\Windows\Fonts\BIZ-UDGothicR.ttc", 12)
    d.text((6, 30), "FC-MAGICON remote desktop テスト", font=f, fill=(0, 0, 0))
    d.text((6, 46), "C:\\> dir   Hello, Famicom! 0123456789", font=f, fill=(20, 20, 120))
    photo = Image.open(os.path.join(HERE, "..", "..", "images", "board_front.png")).convert("RGB")
    photo = photo.crop((250, 190, 1750, 1300)).resize((256, 176))
    img.paste(photo, (0, 64))
    return img


def run(args):
    r = subprocess.run([SIM] + args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.environ.get("TEMP", "."), "claude", "sim", "remote"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rd = os.path.join(a.out, "remote.bin")
    open(rd, "wb").write(b"FCRD")                                  # 画面転送モードの印(load_rom.ps1 -Remote と同じ)
    img = test_image()
    img.save(os.path.join(a.out, "source.png"))
    ok = True
    for mode in ("gray", "color"):
        fr = encode(img, mode)
        fr.preview.save(os.path.join(a.out, f"expect_{mode}.png"))
        cur = (120, 100, True)
        fpath = os.path.join(a.out, f"frame_{mode}.bin")
        write_frame(fpath, fr, cur)
        out = os.path.join(a.out, mode)
        os.makedirs(out, exist_ok=True)
        rc, log = run([rd, "--frames", "60", "--shot-every", "60", "--out", out, "--remote-frame", fpath, "--remote-at", "20"])
        shot = os.path.join(out, "frame00060.bmp")
        if rc or not os.path.exists(shot):
            print(f"{mode}: sim が失敗 rc={rc}\n{log}")
            ok = False
            continue
        got = np.asarray(Image.open(shot).convert("RGB"), dtype=np.int32)
        exp = np.asarray(fr.preview, dtype=np.int32)
        diff = (got != exp).any(-1)
        cx, cy = cur[0], cur[1]
        diff_nc = diff.copy()
        diff_nc[cy:cy + 16, cx:cx + 16] = False                    # カーソルの所は比べない
        n = int(diff_nc.sum())
        print(f"{mode}: 画面の違い {n} ドット(カーソルの所を除く){'  OK' if n == 0 else '  NG'}")
        ok &= n == 0
        cur_px = int(diff[cy:cy + 16, cx:cx + 16].sum())
        print(f"{mode}: カーソルの所で絵と違うドット {cur_px}(矢印が描かれていれば 0 より大){'  OK' if cur_px > 20 else '  NG'}")
        ok &= cur_px > 20
        Image.fromarray(np.concatenate([exp, got], axis=1).astype(np.uint8)).save(os.path.join(a.out, f"compare_{mode}.png"))

    # パッドとキーボード
    rc, log = run([rd, "--frames", "40", "--shot-every", "0", "--out", a.out,
                   "--press", "10:AR:4", "--keys", "20:A:3,26:LSHIFT+1:3,32:RETURN+SPACE:3"])
    lines = [l for l in log.splitlines() if "pad" in l]
    for l in lines:
        print("  " + l.strip())
    want = [("81", ""), ("00", "A"), ("00", "1 LSHIFT"), ("00", "RETURN SPACE")]   # パッド 81 = A(bit7)+ →(bit0)
    seen = [(m.group(1), m.group(2).strip()) for m in (re.search(r"pad (\w\w)\s+keys \[(.*)\]", l) for l in lines) if m]
    for p, k in want:
        hit = any(sp == p and sk == k for sp, sk in seen)
        print(f"入力 pad {p} keys [{k}] {'OK' if hit else 'NG'}")
        ok &= hit
    print("全部 OK" if ok else "NG あり")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

