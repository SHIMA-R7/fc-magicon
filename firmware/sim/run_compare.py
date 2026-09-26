"""
いくつもの ROM を magicon(cart.c)と agnes 自身のマッパー(native)の両方で動かし、画面を毎フレーム比べる。
    python run_compare.py ROM... [--frames N] [--out DIR]
  ・同じパッド入力(START を何回か押してゲームを始め、A・→ を押す)を両方に与える
  ・agnes が対応していないマッパー(3 CNROM、7 AxROM)は magicon だけで動かし、画面を見る
  ・結果: DIR/report.txt と、ROM ごとの一覧画像 DIR/<名前>.png(上 = magicon、下 = native)
  ROM は手元で吸い出したもの。リポジトリには入れない。
"""
import argparse
import os
import subprocess
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.path.join(HERE, "sim.exe")
PRESS = "150:T:5,300:T:5,420:A:5,520:T:5,650:A:10,700:R:120,900:A:10,1000:T:5,1100:A:5"
AGNES_MAPPERS = {0, 1, 2, 4}


def header(path):
    d = open(path, "rb").read(16)
    if d[:4] != b"NES\x1a":
        return None
    return (d[6] >> 4) | (d[7] & 0xF0)


def run(rom, mode, frames, out, every):
    os.makedirs(out, exist_ok=True)
    cmd = [SIM, rom, "--frames", str(frames), "--out", out, "--press", PRESS, "--shot-every", str(every), "--wav"]
    if mode == "native":
        cmd.append("--native")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    hashes = {}
    hp = os.path.join(out, "hashes.txt")
    if os.path.exists(hp):
        for line in open(hp):
            f, h = line.split()
            hashes[int(f)] = h
    return r.returncode, (r.stdout + r.stderr).strip().splitlines(), hashes


def sheet(name, dirs, frames_list, path):
    rows = [d for d in dirs if d]
    W = Image.new("RGB", (len(frames_list) * 260, len(rows) * 244), (40, 40, 40))
    for r, d in enumerate(rows):
        for c, fr in enumerate(frames_list):
            p = os.path.join(d, f"frame{fr:05d}.bmp")
            if os.path.exists(p):
                W.paste(Image.open(p), (c * 260, r * 244))
    W.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("roms", nargs="+")
    ap.add_argument("--frames", type=int, default=1200)
    ap.add_argument("--out", default=os.path.join(os.environ.get("TEMP", "."), "claude", "sim", "compare"))
    a = ap.parse_args()
    every = 60
    report = []
    for rom in a.roms:
        name = os.path.splitext(os.path.basename(rom))[0]
        mapper = header(rom)
        base = os.path.join(a.out, name)
        rc, log_m, h_m = run(rom, "magicon", a.frames, base + "_magicon", every)
        info = next((l for l in log_m if l.startswith("magicon")), log_m[-1] if log_m else "")
        rms_m = next((l.split()[-1] for l in log_m if l.startswith("done")), "?")
        line = f"{name:10} {info}"
        dirs = [base + "_magicon", None]
        if rc != 0:
            line += f"  ! magicon error: {log_m[-1] if log_m else rc}"
        elif mapper in AGNES_MAPPERS:
            rc2, log_n, h_n = run(rom, "native", a.frames, base + "_native", every)
            rms_n = next((l.split()[-1] for l in log_n if l.startswith("done")), "?")
            diff = [f for f in sorted(h_m) if h_n.get(f) != h_m[f]]
            dirs[1] = base + "_native"
            if not diff:
                line += f"  | 画面 {len(h_m)} フレームすべて一致  音 rms {rms_m} / {rms_n}"
            else:
                line += f"  | 画面が違う: {len(diff)} フレーム(最初 {diff[0]})  音 rms {rms_m} / {rms_n}"
        else:
            line += f"  | (agnes は非対応のマッパー。magicon だけ)  音 rms {rms_m}"
        stuck = len(set(h_m.values())) <= 2
        if stuck:
            line += "  ! 画面がほとんど変わらない"
        report.append(line)
        print(line, flush=True)
        sheet(name, dirs, [60, 240, 480, 720, 960, 1200], os.path.join(a.out, name + ".png"))
    open(os.path.join(a.out, "report.txt"), "w", encoding="utf-8").write("\n".join(report) + "\n")


if __name__ == "__main__":
    main()
