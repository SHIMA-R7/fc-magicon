"""
カセットの音(firmware/magicon/audio.c)を試す: 決まった音を "FCAU" パケットにして、実際の速さ(32kHz)で送る。
    python audio_bench.py [--tcp HOST | --port COMx] [--seconds 5] [--pcm] [--freq 440]
  カセットは画面転送モード(magicon / magicon_wifi)にしておく。画面は送らない。
  既定は ADPCM(Wi-Fi と同じ)。--pcm で 16 ビット(USB 直結と同じ)。ドレミ…と音程を変えながら鳴らす。
"""
import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcaudio import RATE, FORMATS, AdpcmEncoder, packets   # noqa: E402
from remote_pc import Port, TcpPort, find_port   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tcp", nargs="?", const="fc-magicon.local")
    ap.add_argument("--port")
    ap.add_argument("--seconds", type=float, default=5)
    ap.add_argument("--pcm", action="store_true", help="--fmt pcm16 と同じ")
    ap.add_argument("--fmt", choices=["pcm16", "pcm8", "adpcm"], default="adpcm")
    ap.add_argument("--freq", type=float, default=440)
    a = ap.parse_args()
    port = TcpPort(a.tcp) if a.tcp else Port(a.port or find_port()[0])
    name = "pcm16" if a.pcm else a.fmt
    fmt = FORMATS[name]
    enc = AdpcmEncoder()
    notes = [1, 9 / 8, 5 / 4, 4 / 3, 3 / 2, 5 / 3, 15 / 8, 2]      # ドレミファソラシド
    chunk = RATE // 50                                              # 20ms ずつ
    phase, sent, t0 = 0.0, 0, time.perf_counter()
    total = int(a.seconds * RATE)
    while sent < total:
        f = a.freq * notes[(sent // (RATE // 2)) % len(notes)]      # 0.5 秒ごとに音程を変える
        t = phase + 2 * np.pi * f * np.arange(chunk) / RATE
        phase = (t[-1] + 2 * np.pi * f / RATE) % (2 * np.pi)
        x = (0.5 * np.sin(t)).astype(np.float32)
        for p in packets(x, fmt, enc):
            port.write(p)
        sent += chunk
        while time.perf_counter() < t0 + sent / RATE:              # 実際の速さに合わせる
            time.sleep(0.002)
    print(f"{sent} サンプル({sent / RATE:.1f} 秒)を {name} で送った")


if __name__ == "__main__":
    main()
