"""
USB 直結の画面転送の速さを測る(Core2350B2 に usb_test.uf2 を書いておく。ファミコン・画面の取り込みは使わない)。
    python usb_bench.py [--port COM11] [--frames 200] [--chunk 0]
  決まった中身の画面パケット(15463 バイト)を目いっぱい送り、usb_test が FCIN で返す「受け取った枚数」で確かめる。
  --chunk N: 1 回の WriteFile を N バイトに分ける(0 = 1 枚まとめて)。
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from remote_pc import Port, find_port   # noqa: E402

FRAME = 4 + 15360 + 32 + 64 + 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--chunk", type=int, default=0)
    a = ap.parse_args()
    name = a.port or (find_port() or [None])[0]
    port = Port(name)
    pkt = b"FCFR" + bytes((i * 7) & 0xFF for i in range(FRAME - 4))
    rx = b""

    def rx_count():
        nonlocal rx
        rx += port.read(65536)
        i = rx.rfind(b"FCIN")
        n = None
        if i >= 0 and len(rx) >= i + 20:
            n = rx[i + 14] | rx[i + 15] << 8
            rx = rx[i + 20:]
        elif len(rx) > 4096:
            rx = rx[-40:]
        return n

    time.sleep(0.2)
    start = None
    while start is None:                                  # 今までに受け取った枚数(前の試験の分)
        start = rx_count()
    t0 = time.perf_counter()
    for _ in range(a.frames):
        if a.chunk:
            for k in range(0, FRAME, a.chunk):
                port.write(pkt[k:k + a.chunk])
        else:
            port.write(pkt)
        rx_count()
    t_sent = time.perf_counter() - t0
    got = start
    t_end = time.perf_counter() + 2
    while time.perf_counter() < t_end:
        n = rx_count()
        if n is not None:
            got = n
            if (got - start) & 0xFFFF >= a.frames:
                break
    dt = time.perf_counter() - t0
    done = (got - start) & 0xFFFF
    print(f"{name}: 送った {a.frames} 枚 / usb_test が受け取った {done} 枚、送るのに {t_sent:.2f} 秒")
    print(f"速さ {done * FRAME / dt / 1024:.0f} KB/秒 = 最大 {done / dt:.1f} 枚/秒")


if __name__ == "__main__":
    main()
