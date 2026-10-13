"""Optional chunked screen packets; audio can run between chunks."""
import struct

FRAME_BYTES = 15360 + 32 + 64 + 3
CHUNK_BYTES = 1024

def frame_chunks(packet):
    if len(packet) != FRAME_BYTES + 4 or packet[:4] != b'FCFR':
        raise ValueError('expected one complete FCFR packet')
    payload = memoryview(packet)[4:]
    return [b'FCCH' + struct.pack('<HH', offset, len(payload[offset:offset + CHUNK_BYTES]))
            + payload[offset:offset + CHUNK_BYTES].tobytes()
            for offset in range(0, FRAME_BYTES, CHUNK_BYTES)]
