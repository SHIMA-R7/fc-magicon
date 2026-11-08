"""Upload RP2350 firmware or FCPV media through the C6 TCP/USB updater."""
import argparse
import socket
import struct
import time
import zlib
from pathlib import Path

def response(sock):
    match = bytearray()
    while True:
        value = sock.recv(1)
        if not value:
            raise ConnectionError("C6 disconnected")
        match.extend(value)
        if match[-4:] == b"FCUA":
            break
    body = bytearray()
    while len(body) < 12:
        value = sock.recv(12 - len(body))
        if not value:
            raise ConnectionError("Incomplete update response")
        body.extend(value)
    status, received, crc = struct.unpack("<III", body)
    if status >= 0x100:
        raise RuntimeError(f"RP2350 rejected update: status=0x{status:x}, received={received}, CRC={crc:08x}")
    return status, received, crc

def upload(host, port, image, media=False):
    size = len(image)
    if media:
        if not 64 <= size <= 15 * 1024 * 1024 or image[:4] != b"FCPV":
            raise ValueError("Expected an FCPV movie up to 15 MiB")
    else:
        if not 512 <= size <= 128 * 1024:
            raise ValueError("Firmware .bin must be 512 bytes to 128 KiB")
        sp, reset = struct.unpack_from("<II", image)
        if not (0x20000000 <= sp <= 0x20082000 and sp % 8 == 0 and
                reset & 1 and 0x10000000 <= (reset & ~1) < 0x10000000 + size):
            raise ValueError("Expected a raw ARM Secure firmware .bin with flash vectors")
    crc = zlib.crc32(image)
    start = time.monotonic()
    with socket.create_connection((host, port), 5) as sock:
        sock.settimeout(15)
        sock.sendall((b"FCPM" if media else b"FCUP") + struct.pack("<IIII", 2 if media else 1, size, crc, 0x100000 if media else 0))
        # A previous update's completion may still be waiting in the device.
        while True:
            status, received, actual_crc = response(sock)
            if status == 0:
                break
        if received != 0 or actual_crc != crc:
            raise RuntimeError("Invalid ready response")
        chunk_size = 4096 if media else 1024
        progress_at = 256 * 1024
        for offset in range(0, size, chunk_size):
            chunk = image[offset:offset + chunk_size]
            sock.sendall(struct.pack("<II", offset, len(chunk)) + chunk)
            if response(sock) != (1, offset + len(chunk), crc):
                raise RuntimeError("Unexpected chunk acknowledgement")
            if offset + len(chunk) >= progress_at:
                print(f"Received: {offset + len(chunk):,}/{size:,} bytes", flush=True)
                progress_at += 256 * 1024
        if response(sock) != (2, size, crc):
            raise RuntimeError("Update was not verified by RP2350")
    print(f"Verified {'media' if media else 'firmware'}: {size} bytes, CRC32 {crc:08x}, {time.monotonic() - start:.2f} s")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path)
    parser.add_argument("--host", default="fc-magicon.local")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--media", action="store_true", help="Write FCPV to flash offset 0x100000")
    args = parser.parse_args()
    upload(args.host, args.port, args.firmware.read_bytes(), media=args.media)

if __name__ == "__main__":
    main()
