"""
Wi-Fi ブリッジ(ESP32-C6、firmware/wifi_bridge)の速さを測る。カセットの代わりに PC が C6 の USB を受ける:
    PC ──Wi-Fi(TCP)──> C6 ──USB──> 同じ PC
    python wifi_bench.py [--frames 300] [--port COMx] [--host 192.168.x.x]
  画面転送と同じ 1 枚 15463 バイトを TCP で送り、USB から全部同じ中身で戻ってくるかと速さ(= 最大何枚/秒)を見る。
  逆向き(カセット → PC の FCIN 20 バイト、60 回/秒)も USB に書いて TCP で届くかを見る。
  C6 の COM ポートは VID 303A(Espressif)で探す。IP は C6 が USB に出す "ip=..." を読む。
"""
import argparse
import os
import random
import re
import socket
import sys
import threading
import time
import winreg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from remote_pc import Port   # noqa: E402

FRAME = 4 + 15360 + 32 + 64 + 3


def find_esp_port():
    """Espressif(VID 303A)の USB シリアルの COM ポート"""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Enum\USB") as usb:
            for i in range(winreg.QueryInfoKey(usb)[0]):
                dev = winreg.EnumKey(usb, i)
                if not dev.upper().startswith("VID_303A"):
                    continue
                with winreg.OpenKey(usb, dev) as d:
                    for j in range(winreg.QueryInfoKey(d)[0]):
                        try:
                            with winreg.OpenKey(d, winreg.EnumKey(d, j) + r"\Device Parameters") as p:
                                return winreg.QueryValueEx(p, "PortName")[0]
                        except OSError:
                            pass
    except OSError:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--host")
    ap.add_argument("--frames", type=int, default=300)
    ap.add_argument("--fps", type=float, default=0, help="この速さで送る(0 = 目いっぱい)。遅れを実際の使い方に近い条件で見る")
    a = ap.parse_args()

    name = a.port or find_esp_port()
    if not name:
        sys.exit("ESP32-C6 の COM ポートが見つからない。--port COMx で指定する")
    port = Port(name)
    print(f"{name} を開いた")

    host = a.host
    if not host:
        text, t0 = b"", time.time()
        while time.time() - t0 < 20:
            text += port.read()
            m = re.search(rb"ip=([\d.]+)", text)
            if m:
                host = m.group(1).decode()
                break
            time.sleep(0.05)
        if not host:
            sys.exit(f"C6 から IP が来ない(Wi-Fi につながっていない?)。USB に来た文字: {text[-200:]!r}")
    sock = socket.create_connection((host, 5000), timeout=5)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    print(f"{host}:5000 につないだ")
    time.sleep(0.3)
    while port.read():                                   # つながる前の案内の文字を捨てる
        pass

    rnd = random.Random(1)
    frames = [b"FCFR" + rnd.randbytes(FRAME - 4) for _ in range(8)]
    expect = b"".join(frames)
    expect2 = expect + expect                            # 1 回の読み出し(64KB 以下)が 8 枚分の境目をまたいでも比べられるように
    total = FRAME * a.frames
    t_sent = [0.0] * a.frames
    lat = []
    rev_got = bytearray()
    stop = threading.Event()

    def sender():
        for i in range(a.frames):
            if a.fps:
                while time.perf_counter() < t_start + i / a.fps:
                    time.sleep(0.0005)
            t_sent[i] = time.perf_counter()
            sock.sendall(frames[i % 8])

    def rev_reader():
        sock.settimeout(0.2)
        while not stop.is_set():
            try:
                d = sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not d:
                break
            rev_got.extend(d)

    th = threading.Thread(target=sender, daemon=True)
    tr = threading.Thread(target=rev_reader, daemon=True)
    t_start = time.perf_counter()
    th.start()
    tr.start()
    got, errors, rev_sent, next_rev = 0, 0, 0, t_start
    last_rx = time.perf_counter()
    while got < total:
        d = port.read(65536)
        now = time.perf_counter()
        if d:
            last_rx = now
            pos = got % len(expect)                      # 中身が合っているか(食い違ったかたまりを数える)
            if d != expect2[pos:pos + len(d)]:
                errors += 1
            before = got // FRAME
            got += len(d)
            for f in range(before, min(got // FRAME, a.frames)):
                lat.append(now - t_sent[f])
        elif now - last_rx > 5:
            print("5 秒間 USB に何も来ない。止める")
            break
        if now >= next_rev:                              # 逆向き: FCIN を 60 回/秒
            next_rev += 1 / 60
            port.write(b"FCIN" + bytes([rev_sent & 0xFF]) + bytes(15))
            rev_sent += 1
        if not d:
            time.sleep(0.0005)
    dt = time.perf_counter() - t_start
    time.sleep(0.3)
    stop.set()
    tr.join(1)
    sock.close()

    rate = got / dt
    print(f"届いた {got} / {total} バイト、{dt:.2f} 秒")
    print(f"速さ {rate / 1024:.0f} KB/秒 = 画面転送なら最大 {rate / FRAME:.1f} 枚/秒")
    if lat:
        lat.sort()
        print(f"1 枚の遅れ(送り始め → USB に全部届く): 中央 {lat[len(lat) // 2] * 1000:.0f}ms、最大 {lat[-1] * 1000:.0f}ms")
    print(f"中身の食い違い: {errors} 回" + ("(OK)" if errors == 0 and got == total else ""))
    ok_rev = rev_got.count(b"FCIN")
    print(f"逆向き(FCIN): 送った {rev_sent} 個、TCP に届いた {ok_rev} 個")


if __name__ == "__main__":
    main()
