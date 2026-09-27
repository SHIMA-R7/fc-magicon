"""
PC で鳴っている音を横取りして(WASAPI のループバック)、カセットへ送る "FCAU" パケットにする。
使うのは Python に元からあるものと numpy だけ(WASAPI は ctypes で COM を呼ぶ)。
  パケット: "FCAU" + 形式 1(0 = 16 ビット PCM、1 = IMA ADPCM、2 = 8 ビット PCM)+ サンプル数 2(LE)+ 中身
    PCM:   サンプル × 2 バイト(LE)/ 8 ビットはサンプル × 1 バイト(符号付き)
    ADPCM: 最初の値 2(LE)+ 段 1 + 4 ビット × サンプル数(下位の 4 ビットが先)
  32kHz モノラル。カセット側の戻し方は firmware/magicon/audio.c
    python pcaudio.py --test       (音を鳴らして自分で録り、周波数と大きさを確かめる)
"""
import ctypes
import ctypes.wintypes as wt
import struct
import threading

import numpy as np

RATE = 32000
MAX_SAMPLES = 1024
FMT_PCM16, FMT_ADPCM, FMT_PCM8 = 0, 1, 2
FORMATS = {"pcm16": FMT_PCM16, "pcm8": FMT_PCM8, "adpcm": FMT_ADPCM}   # 1 秒あたり 64KB / 32KB / 16KB

# ---------------- WASAPI(ループバック) ----------------
ole32 = ctypes.WinDLL("ole32")


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, s):
        super().__init__()
        ole32.CLSIDFromString(ctypes.c_wchar_p("{" + s + "}"), ctypes.byref(self))


CLSID_MMDeviceEnumerator = GUID("BCDE0395-E52F-467C-8E3D-C4579291692E")
IID_IMMDeviceEnumerator = GUID("A95664D2-9614-4F35-A746-DE8DB63617E6")
IID_IAudioClient = GUID("1CB9AD4C-DBFA-4C32-B178-C2F568A703B2")
IID_IAudioCaptureClient = GUID("C8ADBD64-E71E-48A0-A4DE-185C395CD317")
KSDATAFORMAT_FLOAT = "00000003-0000-0010-8000-00AA00389B71"


class WAVEFORMATEX(ctypes.Structure):
    _pack_ = 1                                            # Windows の定義どおり 18 バイト(詰めないと後ろがずれる)
    _fields_ = [("wFormatTag", wt.WORD), ("nChannels", wt.WORD), ("nSamplesPerSec", wt.DWORD),
                ("nAvgBytesPerSec", wt.DWORD), ("nBlockAlign", wt.WORD), ("wBitsPerSample", wt.WORD),
                ("cbSize", wt.WORD)]


class WAVEFORMATEXTENSIBLE(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("Format", WAVEFORMATEX), ("wValidBitsPerSample", wt.WORD), ("dwChannelMask", wt.DWORD),
                ("SubFormat", GUID)]


def _method(obj, index, restype, *argtypes):
    """COM のメソッド(vtable の index 番目)を呼べる関数にする"""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[index])


def _check(hr, what):
    if hr < 0:
        raise OSError(f"{what} に失敗(0x{hr & 0xFFFFFFFF:08X})")


class LoopbackCapture:
    """既定の再生デバイスで鳴っている音を録る。read() はその時までに溜まった分を float32 モノラル(元の周波数)で返す"""
    def __init__(self):
        ole32.CoInitializeEx(None, 0)                     # COINIT_MULTITHREADED
        enum = ctypes.c_void_p()
        _check(ole32.CoCreateInstance(ctypes.byref(CLSID_MMDeviceEnumerator), None, 23,     # CLSCTX_ALL
                                      ctypes.byref(IID_IMMDeviceEnumerator), ctypes.byref(enum)), "CoCreateInstance")
        dev = ctypes.c_void_p()
        _check(_method(enum, 4, ctypes.HRESULT, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(
            enum, 0, 0, ctypes.byref(dev)), "GetDefaultAudioEndpoint")   # eRender, eConsole
        self.client = ctypes.c_void_p()
        _check(_method(dev, 3, ctypes.HRESULT, ctypes.POINTER(GUID), wt.DWORD, ctypes.c_void_p,
                       ctypes.POINTER(ctypes.c_void_p))(dev, ctypes.byref(IID_IAudioClient), 23, None,
                                                        ctypes.byref(self.client)), "Activate")
        pwfx = ctypes.POINTER(WAVEFORMATEX)()
        _check(_method(self.client, 8, ctypes.HRESULT, ctypes.POINTER(ctypes.POINTER(WAVEFORMATEX)))(
            self.client, ctypes.byref(pwfx)), "GetMixFormat")
        wfx = pwfx.contents
        self.rate, self.channels, self.bits = wfx.nSamplesPerSec, wfx.nChannels, wfx.wBitsPerSample
        self.block = wfx.nBlockAlign
        if wfx.wFormatTag == 3:                           # WAVE_FORMAT_IEEE_FLOAT
            self.is_float = True
        elif wfx.wFormatTag == 0xFFFE:                    # WAVE_FORMAT_EXTENSIBLE
            ext = ctypes.cast(pwfx, ctypes.POINTER(WAVEFORMATEXTENSIBLE)).contents
            buf = ctypes.create_unicode_buffer(64)
            ole32.StringFromGUID2(ctypes.byref(ext.SubFormat), buf, 64)
            self.is_float = buf.value.strip("{}").upper() == KSDATAFORMAT_FLOAT
        else:
            self.is_float = False
        _check(_method(self.client, 3, ctypes.HRESULT, ctypes.c_int, wt.DWORD, ctypes.c_longlong, ctypes.c_longlong,
                       ctypes.POINTER(WAVEFORMATEX), ctypes.c_void_p)(
            self.client, 0, 0x00020000, 2_000_000, 0, pwfx, None), "Initialize")   # 共有、ループバック、200ms
        self.cap = ctypes.c_void_p()
        _check(_method(self.client, 14, ctypes.HRESULT, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(
            self.client, ctypes.byref(IID_IAudioCaptureClient), ctypes.byref(self.cap)), "GetService")
        self._get = _method(self.cap, 3, ctypes.HRESULT, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.UINT),
                            ctypes.POINTER(wt.DWORD), ctypes.c_void_p, ctypes.c_void_p)
        self._release = _method(self.cap, 4, ctypes.HRESULT, wt.UINT)
        self._next = _method(self.cap, 5, ctypes.HRESULT, ctypes.POINTER(wt.UINT))
        _check(_method(self.client, 10, ctypes.HRESULT)(self.client), "Start")

    def read(self):
        chunks = []
        n = wt.UINT()
        while True:
            _check(self._next(self.cap, ctypes.byref(n)), "GetNextPacketSize")
            if n.value == 0:
                break
            data, frames, flags = ctypes.c_void_p(), wt.UINT(), wt.DWORD()
            _check(self._get(self.cap, ctypes.byref(data), ctypes.byref(frames), ctypes.byref(flags), None, None),
                   "GetBuffer")
            count = frames.value * self.channels
            if flags.value & 2 or not data.value:         # AUDCLNT_BUFFERFLAGS_SILENT
                x = np.zeros(count, np.float32)
            elif self.is_float:
                x = np.ctypeslib.as_array(ctypes.cast(data, ctypes.POINTER(ctypes.c_float)), (count,)).copy()
            elif self.bits == 16:
                x = np.ctypeslib.as_array(ctypes.cast(data, ctypes.POINTER(ctypes.c_int16)), (count,)) / 32768.0
            else:
                x = np.ctypeslib.as_array(ctypes.cast(data, ctypes.POINTER(ctypes.c_int32)), (count,)) / 2147483648.0
            self._release(self.cap, frames)
            chunks.append(x.reshape(-1, self.channels).mean(axis=1).astype(np.float32))
        return np.concatenate(chunks) if chunks else np.zeros(0, np.float32)


# ---------------- 周波数の変換(元の周波数 → 32kHz) ----------------
class Resampler:
    """つなぎ目で途切れないよう、前の端を覚えて直線で補間する。前に 3 点の移動平均で高い音を少し落とす(折り返し対策)"""
    def __init__(self, src_rate, dst_rate=RATE):
        self.step = src_rate / dst_rate
        self.pos = 0.0                                    # 次に取る位置(前の塊の最後の 1 点を 0 とする)
        self.tail = np.zeros(2, np.float32)

    def process(self, x):
        if len(x) == 0:
            return np.zeros(0, np.float32)
        buf = np.concatenate([self.tail, x])
        smooth = np.convolve(buf, np.array([0.25, 0.5, 0.25], np.float32), mode="same")
        t = np.arange(self.pos + 1, len(buf) - 1, self.step)      # 補間に前後 1 点ずつ要る
        out = np.interp(t, np.arange(len(buf)), smooth).astype(np.float32)
        self.pos = (t[-1] + self.step - (len(buf) - 2)) if len(t) else self.pos - (len(buf) - 2)
        self.tail = buf[-2:]
        return out


# ---------------- IMA ADPCM ----------------
STEP = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97,
        107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
        876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871,
        5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
        27086, 29794, 32767]
INDEX = [-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8]


class AdpcmEncoder:
    """パケットごとに最初の値と段を載せるので、途中のパケットが抜けてもカセット側は崩れない"""
    def __init__(self):
        self.pred, self.index = 0, 0

    def encode(self, s):
        head = struct.pack("<hB", self.pred, self.index)
        pred, index = self.pred, self.index
        out = bytearray((len(s) + 1) // 2)
        for i, v in enumerate(s.tolist()):
            step = STEP[index]
            diff = v - pred
            code = 0
            if diff < 0:
                code, diff = 8, -diff
            d = step >> 3
            if diff >= step:
                code |= 4
                diff -= step
                d += step
            if diff >= step >> 1:
                code |= 2
                diff -= step >> 1
                d += step >> 1
            if diff >= step >> 2:
                code |= 1
                d += step >> 2
            pred = max(-32768, min(32767, pred - d if code & 8 else pred + d))
            index = max(0, min(88, index + INDEX[code]))
            out[i >> 1] |= code << 4 if i & 1 else code
        self.pred, self.index = pred, index
        return head + bytes(out)


def adpcm_decode(payload, n):
    """カセット側(audio.c)と同じ戻し方。試験用"""
    pred, index = struct.unpack_from("<hB", payload)
    out = np.zeros(n, np.int32)
    for i in range(n):
        code = payload[3 + (i >> 1)] >> 4 if i & 1 else payload[3 + (i >> 1)] & 15
        step = STEP[index]
        d = step >> 3
        if code & 4:
            d += step
        if code & 2:
            d += step >> 1
        if code & 1:
            d += step >> 2
        pred = max(-32768, min(32767, pred - d if code & 8 else pred + d))
        index = max(0, min(88, index + INDEX[code]))
        out[i] = pred
    return out


# ---------------- パケットにする ----------------
def packets(samples, fmt, adpcm):
    """float32(-1..1)の 32kHz → "FCAU" パケットの並び"""
    s = np.clip(samples * 32767, -32768, 32767).astype(np.int16)
    out = []
    for k in range(0, len(s), MAX_SAMPLES):
        part = s[k:k + MAX_SAMPLES]
        if fmt == FMT_PCM16:
            body = part.astype("<i2").tobytes()
        elif fmt == FMT_PCM8:
            body = np.clip((part.astype(np.int32) + 128) >> 8, -128, 127).astype(np.int8).tobytes()   # 四捨五入
        else:
            body = adpcm.encode(part)
        out.append(b"FCAU" + struct.pack("<BH", fmt, len(part)) + body)
    return out


class AudioSender(threading.Thread):
    """20ms ごとに録った音を FCAU パケットにして send(パケット)へ渡す"""
    def __init__(self, send, fmt, volume=1.0):
        super().__init__(daemon=True)
        self.send, self.fmt, self.volume = send, fmt, volume
        self.cap = LoopbackCapture()
        self.rs = Resampler(self.cap.rate)
        self.adpcm = AdpcmEncoder()
        self.stop = threading.Event()
        self.start()

    def run(self):
        while not self.stop.wait(0.02):
            x = self.rs.process(self.cap.read())
            if len(x):
                for p in packets(x * self.volume, self.fmt, self.adpcm):
                    self.send(p)


def _self_test():
    """ADPCM の往復と、ループバックで自分が鳴らした 1kHz を録れるかを確かめる"""
    import os
    import tempfile
    import time
    import wave
    import winsound
    t = np.arange(RATE) / RATE
    tone = (0.5 * np.sin(2 * np.pi * 440 * t) + 0.2 * np.sin(2 * np.pi * 3000 * t)).astype(np.float32)
    enc = AdpcmEncoder()
    got = []
    for p in packets(tone, FMT_ADPCM, enc):
        n = struct.unpack_from("<H", p, 5)[0]
        got.append(adpcm_decode(p[7:], n))
    dec = np.concatenate(got) / 32768.0
    snr = 10 * np.log10(np.sum(tone ** 2) / np.sum((tone - dec) ** 2))
    print(f"ADPCM の往復: SN 比 {snr:.1f}dB(パケット {len(got)} 個)")

    cap = LoopbackCapture()
    print(f"再生デバイスの形式: {cap.rate}Hz {cap.channels}ch {cap.bits}bit {'float' if cap.is_float else 'int'}")
    path = os.path.join(tempfile.gettempdir(), "fc_magicon_tone.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        tt = np.arange(48000 * 2) / 48000
        w.writeframes((0.3 * np.sin(2 * np.pi * 1000 * tt) * 32767).astype("<i2").tobytes())
    winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)          # 小さめの 1kHz を 2 秒
    time.sleep(0.5)
    cap.read()
    rs = Resampler(cap.rate)
    parts = []
    for _ in range(50):                                   # 本番と同じく 20ms ごとに読む(ループバックの溜めは 200ms)
        time.sleep(0.02)
        parts.append(rs.process(cap.read()))
    y = np.concatenate(parts)
    winsound.PlaySound(None, 0)
    if len(y) < RATE // 2:
        print(f"録れた量が少ない({len(y)} サンプル)。音が出ていない / ミュート?")
        return
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    peak = np.argmax(spec) * RATE / len(y)
    print(f"ループバック: {len(y)} サンプル(32kHz にして)、いちばん強い周波数 {peak:.0f}Hz、"
          f"大きさ(RMS){np.sqrt(np.mean(y ** 2)):.3f}")


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        _self_test()
