"""
FC-MAGICON 画面転送(リモートデスクトップ)の PC 側。PC の画面をファミコンに映し、1コンをマウス、
ファミリーベーシックのキーボード(HVC-007)を PC のキーボードにする。
    python remote_pc.py [--port COM5] [--color] [--fps 30]
    python remote_pc.py --dry-run 60        (カセット無しで、画面の取り込み + 変換の速さだけ測る)
  カセットは load_rom.ps1 -Remote で画面転送モードにしておく。止める時は Ctrl+C。
  使うのは Python に元からあるものと Pillow・numpy だけ(COM ポート・マウス・キーは Windows の API を ctypes で呼ぶ)。

操作:
  1コン 十字キー = マウス移動(押し続けると速くなる)、A = 左クリック、B = 右クリック
        SELECT = 表示の切り替え(画面全体を縮小 ⇔ カーソルのまわりを等倍)、START = 等倍の時にカーソルを追うか止めるか
  キーボード = 同じ刻印のキー(JIS 配列の位置で送る)。STOP = Ctrl+C、GRPH = Alt、カナ = 半角/全角、DEL = BackSpace
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import os
import struct
import sys
import time
import winreg

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nesframe import encode   # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.SetProcessDPIAware()                            # 画面の座標を実際のピクセルで扱う

# ---------------- COM ポート(Win32 API) ----------------
class COMMTIMEOUTS(ctypes.Structure):
    _fields_ = [("ReadIntervalTimeout", wt.DWORD), ("ReadTotalTimeoutMultiplier", wt.DWORD),
                ("ReadTotalTimeoutConstant", wt.DWORD), ("WriteTotalTimeoutMultiplier", wt.DWORD),
                ("WriteTotalTimeoutConstant", wt.DWORD)]


class Port:
    def __init__(self, name):
        kernel32.CreateFileW.restype = wt.HANDLE
        self.h = kernel32.CreateFileW("\\\\.\\" + name, 0xC0000000, 0, None, 3, 0, None)   # 読み書き、OPEN_EXISTING
        if self.h in (None, wt.HANDLE(-1).value):
            raise OSError(f"{name} を開けない(ほかのアプリが使っている?)")
        kernel32.SetupComm(self.h, 65536, 65536)
        # 読み出しはすぐ戻る(来ている分だけ)。書き込みは 2 秒で打ち切る
        kernel32.SetCommTimeouts(self.h, ctypes.byref(COMMTIMEOUTS(0xFFFFFFFF, 0, 0, 0, 2000)))
        kernel32.EscapeCommFunction(self.h, 5)          # SETDTR(pico の USB シリアルは DTR が立つと送ってくる)

    def read(self, n=4096):
        buf = ctypes.create_string_buffer(n)
        got = wt.DWORD()
        kernel32.ReadFile(self.h, buf, n, ctypes.byref(got), None)
        return buf.raw[:got.value]

    def write(self, data):
        done = wt.DWORD()
        if not kernel32.WriteFile(self.h, data, len(data), ctypes.byref(done), None) or done.value != len(data):
            raise OSError("書き込みが止まった(カセットが受け取っていない?)")


def find_port():
    """USB シリアル(usbser)の COM ポートを探す。複数あれば最初のもの"""
    ports = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM") as k:
            for i in range(winreg.QueryInfoKey(k)[1]):
                name, value, _ = winreg.EnumValue(k, i)
                if "USBSER" in name.upper():
                    ports.append(value)
    except OSError:
        pass
    return ports


# ---------------- マウスとキー(SendInput) ----------------
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def send_mouse_button(flag):
    i = INPUT(type=0)
    i.mi = MOUSEINPUT(0, 0, 0, flag, 0, 0)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))


def send_scancode(code, up):
    """code = スキャンコード(セット 1)。0xE0xx は拡張キー"""
    i = INPUT(type=1)
    flags = 0x0008 | (0x0002 if up else 0) | (0x0001 if code > 0xFF else 0)   # SCANCODE | KEYUP | EXTENDEDKEY
    i.ki = KEYBDINPUT(0, code & 0xFF, flags, 0, 0)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))


# ファミリーベーシックのキーボードの並び(nesdev)。[行][i]: i = 0〜3 は列 0 の bit4〜1、4〜7 は列 1 の bit4〜1
KB_NAMES = [
    ["]", "[", "RETURN", "F8", "STOP", "YEN", "RSHIFT", "KANA"],
    [";", ":", "@", "F7", "^", "-", "/", "_"],
    ["K", "L", "O", "F6", "0", "P", ",", "."],
    ["J", "U", "I", "F5", "8", "9", "N", "M"],
    ["H", "G", "Y", "F4", "6", "7", "V", "B"],
    ["D", "R", "T", "F3", "4", "5", "C", "F"],
    ["A", "S", "W", "F2", "3", "E", "Z", "X"],
    ["CTR", "Q", "ESC", "F1", "2", "1", "GRPH", "LSHIFT"],
    ["LEFT", "RIGHT", "UP", "CLRHOME", "INS", "DEL", "SPACE", "DOWN"],
]
# PC のスキャンコード(セット 1、JIS 配列の位置)
SC = {
    **{c: s for c, s in zip("QWERTYUIOP", range(0x10, 0x1A))},
    **{c: s for c, s in zip("ASDFGHJKL", range(0x1E, 0x27))},
    **{c: s for c, s in zip("ZXCVBNM", range(0x2C, 0x33))},
    **{c: s for c, s in zip("1234567890", range(0x02, 0x0C))},
    "-": 0x0C, "^": 0x0D, "YEN": 0x7D, "@": 0x1A, "[": 0x1B, ";": 0x27, ":": 0x28, "]": 0x2B,
    ",": 0x33, ".": 0x34, "/": 0x35, "_": 0x73,
    "RETURN": 0x1C, "SPACE": 0x39, "ESC": 0x01, "DEL": 0x0E, "CTR": 0x1D, "LSHIFT": 0x2A, "RSHIFT": 0x36,
    "GRPH": 0x38, "KANA": 0x29,
    **{f"F{n}": 0x3A + n for n in range(1, 9)},
    "INS": 0xE052, "CLRHOME": 0xE047, "UP": 0xE048, "DOWN": 0xE050, "LEFT": 0xE04B, "RIGHT": 0xE04D,
}


def kb_pressed(rows):
    """6502 が書いた 9 バイト(下位 4 = 列 0、上位 4 = 列 1、押すと 0)→ 押されているキー名の集合"""
    s = set()
    for r in range(9):
        for i in range(8):
            bit = (3 - i) if i < 4 else (7 - (i - 4))
            if not (rows[r] >> bit) & 1:
                s.add(KB_NAMES[r][i])
    return s


# ---------------- 画面 ----------------
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class Grabber:
    """画面の一部を、Windows(GDI)に縮めさせながら 256 x 240 の絵に写す(Pillow で全画面を取ってから縮めるより速い)"""

    def __init__(self):
        # 64 ビットのハンドルを int のまま渡すと溢れるので、引数の型を決めておく
        user32.GetDC.restype, user32.GetDC.argtypes = wt.HDC, [wt.HWND]
        gdi32.CreateCompatibleDC.restype, gdi32.CreateCompatibleDC.argtypes = wt.HDC, [wt.HDC]
        gdi32.CreateDIBSection.restype = wt.HBITMAP
        gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
        gdi32.SelectObject.restype, gdi32.SelectObject.argtypes = wt.HGDIOBJ, [wt.HDC, wt.HGDIOBJ]
        gdi32.SetStretchBltMode.argtypes = [wt.HDC, ctypes.c_int]
        gdi32.SetBrushOrgEx.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        gdi32.PatBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.DWORD]
        gdi32.StretchBlt.argtypes = [wt.HDC] + [ctypes.c_int] * 4 + [wt.HDC] + [ctypes.c_int] * 4 + [wt.DWORD]
        self.screen = user32.GetDC(None)
        self.mem = gdi32.CreateCompatibleDC(self.screen)
        bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), 256, -240, 1, 32, 0, 0, 0, 0, 0, 0)
        self.bits = ctypes.c_void_p()
        self.bmp = gdi32.CreateDIBSection(self.mem, ctypes.byref(bi), 0, ctypes.byref(self.bits), None, 0)
        gdi32.SelectObject(self.mem, self.bmp)
        gdi32.SetStretchBltMode(self.mem, 4)            # HALFTONE(縮める時に平均する)
        gdi32.SetBrushOrgEx(self.mem, 0, 0, None)

    def grab(self, src, dst):
        """src = 画面の (x, y, w, h)、dst = 256 x 240 の中の (x, y, w, h)。残りは黒"""
        gdi32.PatBlt(self.mem, 0, 0, 256, 240, 0x00000042)   # BLACKNESS
        gdi32.StretchBlt(self.mem, *dst, self.screen, *src, 0x00CC0020)   # SRCCOPY
        gdi32.GdiFlush()
        raw = ctypes.string_at(self.bits, 256 * 240 * 4)
        return Image.frombuffer("RGB", (256, 240), raw, "raw", "BGRX", 0, 1)


def screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def cursor_pos():
    p = wt.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


class View:
    """どこを映すか。fit = 画面全体を 256 幅に縮める(縦横比はそのまま、上下は黒)、zoom = 256 x 240 を等倍で"""

    def __init__(self):
        self.mode, self.follow = "fit", True
        self.zx, self.zy = 0, 0
        self.g = Grabber()

    def grab(self):
        sw, sh = screen_size()
        mx, my = cursor_pos()
        if self.mode == "zoom":
            if self.follow:
                self.zx = min(max(mx - 128, 0), sw - 256)
                self.zy = min(max(my - 120, 0), sh - 240)
            img = self.g.grab((self.zx, self.zy, 256, 240), (0, 0, 256, 240))
            cx, cy = mx - self.zx, my - self.zy
        else:
            h = round(sh * 256 / sw)
            img = self.g.grab((0, 0, sw, sh), (0, (240 - h) // 2, 256, h))
            cx, cy = mx * 256 // sw, (240 - h) // 2 + my * h // sh
        visible = 0 <= cx < 256 and 0 <= cy < 240
        return img, (max(0, min(255, cx)), max(0, min(239, cy)), visible)

    def pc_pixels_per_fc_pixel(self):
        return 1.0 if self.mode == "zoom" else screen_size()[0] / 256


def frame_packet(fr, cursor):
    return b"FCFR" + fr.fb + bytes(fr.pal) + fr.attr + struct.pack("BBB", cursor[0], cursor[1], int(cursor[2]))


# ---------------- 本体 ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--color", action="store_true", help="カラー(既定は灰色 4 階調。文字が読みやすい)")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--dry-run", type=int, metavar="N", help="カセット無しで N 枚取り込んで変換し、速さを表示する")
    a = ap.parse_args()
    view = View()
    mode = "color" if a.color else "gray"

    if a.dry_run:
        for vm in ("fit", "zoom"):
            view.mode = vm
            t0 = time.perf_counter()
            tg = 0.0
            pv = None
            for _ in range(a.dry_run):
                t1 = time.perf_counter()
                img, cur = view.grab()
                tg += time.perf_counter() - t1
                pv = encode(img, mode, prev=pv if mode == "color" else None, iters=2 if pv else 4)
                frame_packet(pv, cur)
            dt = (time.perf_counter() - t0) / a.dry_run
            print(f"{vm:4} {mode}: 1 枚 {dt * 1000:.1f}ms(取り込み {tg / a.dry_run * 1000:.1f}ms)= 最大 {1 / dt:.1f} fps")
        return

    name = a.port or (find_port() or [None])[0]
    if not name:
        sys.exit("magicon の USB シリアル(COM ポート)が見つからない。--port COMx で指定する")
    port = Port(name)
    print(f"{name} を開いた。{mode}、最大 {a.fps} fps。止める時は Ctrl+C")
    rx = b""
    pad_prev, held, kb_prev, kb_seen = 0, 0, set(), False
    speed = 0.0
    sent, t_start, next_t = 0, time.perf_counter(), 0.0
    last_io = time.perf_counter()
    prev = None

    def release_all():
        """押しっぱなしのキーとマウスのボタンを離す(入力が途切れた時・止める時)"""
        nonlocal kb_prev, pad_prev
        for k in kb_prev:
            if k in SC and k != "STOP":
                send_scancode(SC[k], True)
        if pad_prev & 0x80:
            send_mouse_button(0x0004)
        if pad_prev & 0x40:
            send_mouse_button(0x0010)
        kb_prev, pad_prev = set(), 0

    try:
        while True:
            # ---- カセットからの入力 ----
            data = port.read()
            if data:
                rx += data
            if time.perf_counter() - last_io > 0.5 and (kb_prev or pad_prev):
                release_all()                                   # 0.5 秒届かない(ケーブルが抜けた等)
            if b"FCIN" in rx:
                last_io = time.perf_counter()
            while True:
                i = rx.find(b"FCIN")
                if i < 0 or len(rx) < i + 20:
                    rx = rx[max(0, len(rx) - 19):] if i < 0 else rx[i:]
                    break
                io, rx = rx[i + 4:i + 20], rx[i + 20:]
                pad = io[0]
                new = pad & ~pad_prev
                # マウス: 十字キー(押し続けると速く)
                dx = (1 if pad & 0x01 else 0) - (1 if pad & 0x02 else 0)
                dy = (1 if pad & 0x04 else 0) - (1 if pad & 0x08 else 0)
                if dx or dy:
                    held += 1
                    speed = min(1 + held * 0.25, 12) * view.pc_pixels_per_fc_pixel()
                    x, y = cursor_pos()
                    user32.SetCursorPos(int(x + dx * speed), int(y + dy * speed))
                else:
                    held = 0
                for bit, down, up in ((0x80, 0x0002, 0x0004), (0x40, 0x0008, 0x0010)):      # A = 左、B = 右
                    if (pad ^ pad_prev) & bit:
                        send_mouse_button(down if pad & bit else up)
                if new & 0x20:                                                              # SELECT
                    view.mode = "zoom" if view.mode == "fit" else "fit"
                    print("表示:", view.mode)
                if new & 0x10 and view.mode == "zoom":                                      # START
                    view.follow = not view.follow
                    print("追従:", view.follow)
                pad_prev = pad
                # キーボード(全部押されて見える = つながっていない)
                keys = kb_pressed(io[1:10])
                if len(keys) >= 72:
                    keys = set()
                elif keys and not kb_seen:
                    kb_seen = True
                for k in sorted(keys - kb_prev):
                    if k == "STOP":                                                         # STOP = Ctrl+C
                        send_scancode(0x1D, False); send_scancode(0x2E, False)
                        send_scancode(0x2E, True); send_scancode(0x1D, True)
                    elif k in SC:
                        send_scancode(SC[k], False)
                for k in sorted(kb_prev - keys):
                    if k in SC and k != "STOP":
                        send_scancode(SC[k], True)
                kb_prev = keys
            # ---- 画面 ----
            now = time.perf_counter()
            if now >= next_t:
                next_t = now + 1 / a.fps
                img, cur = view.grab()
                prev = encode(img, mode, prev=prev if mode == "color" else None, iters=2 if prev else 4)   # 組は前の画面から探す(チラつき防止)
                port.write(frame_packet(prev, cur))   # カセットが前の 1 枚を出すまで、ここで待たされる
                sent += 1
                if sent % 100 == 0:
                    print(f"{sent} 枚、{sent / (time.perf_counter() - t_start):.1f} fps")
            else:
                time.sleep(0.001)
    except KeyboardInterrupt:
        release_all()
        print("止めた")


if __name__ == "__main__":
    main()
