"""Capture the user's biased C6 GPIO0 input via the UART diagnostic.

Requires pyserial. Saves original unsigned 12-bit ADC words, metadata, and
DC-removed 16-bit WAV (fixed x16 scale, no automatic loudness normalization).
Example: python capture_fc_mic.py --port COM12 --out recording --tone tone.wav
"""
import argparse
import json
import math
from pathlib import Path
import struct
import time
import wave

import serial


def read_exact(port, size, deadline):
    data = bytearray()
    while len(data) < size and time.monotonic() < deadline:
        data.extend(port.read(size - len(data)))
    if len(data) != size:
        raise RuntimeError(f"Truncated diagnostic packet: {len(data)}/{size} bytes")
    return bytes(data)


def capture(port_name, milliseconds=2000, tone=None):
    if not 100 <= milliseconds <= 2000:
        raise ValueError("Capture duration must be 100..2000 ms")
    port = serial.Serial()
    port.port, port.baudrate, port.timeout = port_name, 115200, .2
    port.dtr = port.rts = False
    with port:
        port.reset_input_buffer()
        if tone:
            import winsound
            winsound.PlaySound(str(tone), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
            time.sleep(.2)
        try:
            port.write(b"\x03MIC1 " + str(milliseconds).encode() + b"\n")
            port.flush()
            deadline = time.monotonic() + milliseconds / 1000 + 15
            while time.monotonic() < deadline:
                line = port.readline()
                if line.startswith(b"MIC1 ERROR"):
                    raise RuntimeError(line.decode(errors="replace").strip())
                if line.startswith(b"MIC1 {"):
                    meta = json.loads(line[5:])
                    break
            else:
                raise RuntimeError("No microphone diagnostic response")
            count = meta["samples"]
            if meta["rate"] != 16000 or not 1 <= count <= 32000 or meta["bytes"] != count * 2:
                raise RuntimeError("Invalid microphone packet dimensions")
            raw = read_exact(port, meta["bytes"], deadline)
            footer = read_exact(port, len(b"\nMIC1 END\n"), deadline)
            if footer != b"\nMIC1 END\n":
                raise RuntimeError("Missing diagnostic packet footer")
            h = 2166136261
            for b in raw:
                h = ((h ^ b) * 16777619) & 0xffffffff
            if h != meta["fnv1a"]:
                raise RuntimeError("Microphone packet checksum mismatch")
            if meta["overflow"]:
                raise RuntimeError("ADC overflow: recording timing is invalid")
            return meta, raw
        finally:
            if tone:
                winsound.PlaySound(None, 0)


def save(stem, meta, raw):
    stem = Path(stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    samples = struct.unpack("<" + "H" * meta["samples"], raw)
    if any(x > 4095 for x in samples):
        raise RuntimeError("ADC words outside 12-bit range")
    mean = sum(samples) / len(samples)
    centered = [x - mean for x in samples]
    rms = math.sqrt(sum(x * x for x in centered) / len(centered))
    meta = dict(meta, mean_raw=mean, rms_raw=rms,
                wav_scale=16, measured_wall_rate=meta["samples"] * 1e6 / meta["capture_us"])
    pcm = b"".join(struct.pack("<h", max(-32768, min(32767, round(x * 16)))) for x in centered)
    stem.with_suffix(".u16le").write_bytes(raw)
    stem.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    with wave.open(str(stem.with_suffix(".wav")), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(meta["rate"]); w.writeframes(pcm)
    return meta


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--ms", type=int, default=2000)
    p.add_argument("--tone", type=Path)
    a = p.parse_args()
    m, b = capture(a.port, a.ms, a.tone)
    print(json.dumps(save(a.out, m, b)))
