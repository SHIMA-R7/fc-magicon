"""
Wi-Fi → ESP32-C6 → USB → RP2350(USB ホスト)の速さを測る。Core2350B2 に host_test.uf2、C6 に wifi_bridge を書いておく。
    python host_bench.py [--host fc-magicon.local] [--frames 300] [--fps 0]
  画面パケット(15463 バイト)を TCP で送り、host_test が FCIN で返す「受け取った枚数」「欠け・余りのあった数」を見る。
  --watch: 送らずに、host_test から届く FCIN を 1 秒ごとに表示するだけ(つながっているかの確認)。
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from remote_pc import TcpPort   # noqa: E402

FRAME = 4 + 15360 + 32 + 64 + 3


class Status:
    def __init__(self, port):
        self.port, self.rx, self.last = port, b"", None

    def poll(self):
        self.rx += self.port.read(65536)
        i = self.rx.rfind(b"FCIN")
        if i >= 0 and len(self.rx) >= i + 20:
            io = self.rx[i + 4:i + 20]
            self.last = dict(frames=io[10] | io[11] << 8, bad=io[12] | io[13] << 8, mounts=io[14], vframe=io[15])
            self.rx = self.rx[i + 20:]
        elif len(self.rx) > 8192:
            self.rx = self.rx[-40:]
        return self.last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="fc-magicon.local")
    ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--fps", type=float, default=0)
    ap.add_argument("--watch", action="store_true")
    a = ap.parse_args()
    port = TcpPort(a.host)
    st = Status(port)
    print(f"{a.host} につないだ。RP2350 からの返事を待つ…")
    t = time.time()
    while st.poll() is None:
        if time.time() - t > 5:
            sys.exit("5 秒待っても RP2350 から FCIN が来ない(C6 を USB で見つけていない? 配線と LED を確認)")
        time.sleep(0.01)
    print(f"返事あり: C6 を見つけた回数 {st.last['mounts']}、これまでに受け取った {st.last['frames']} 枚")
    if a.watch:
        while True:
            time.sleep(1)
            print(st.poll())

    pkt = b"FCFR" + bytes((i * 7) & 0xFF for i in range(FRAME - 4))
    s0 = dict(st.last)
    t0 = time.perf_counter()
    for i in range(a.frames):
        if a.fps:
            while time.perf_counter() < t0 + i / a.fps:
                time.sleep(0.0005)
        port.write(pkt)
        st.poll()
    t_end = time.perf_counter() + 3
    while time.perf_counter() < t_end:
        s = st.poll()
        if (s["frames"] - s0["frames"]) & 0xFFFF >= a.frames:
            break
        time.sleep(0.005)
    dt = time.perf_counter() - t0
    s = st.last
    done = (s["frames"] - s0["frames"]) & 0xFFFF
    bad = (s["bad"] - s0["bad"]) & 0xFFFF
    print(f"送った {a.frames} 枚 / RP2350 が受け取った {done} 枚、欠け・余り {bad} 回、{dt:.2f} 秒")
    print(f"速さ {done * FRAME / dt / 1024:.0f} KB/秒 = 最大 {done / dt:.1f} 枚/秒")
    print(f"C6 を見つけた回数 {s['mounts']}(途中で増えていたら USB が切れてつなぎ直した)")


if __name__ == "__main__":
    main()
