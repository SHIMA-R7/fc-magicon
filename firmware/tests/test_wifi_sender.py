"""Windows sender against a local mock bridge; never touches C6 or FC."""
from pathlib import Path
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from wifi_sender import sender_arguments
from remote_protocol import FRAME_BYTES


def trial(executable=None, chunked=False, disconnect=False, extra=()):
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen(1)
    port = server.getsockname()[1]
    payload = bytearray()
    failure = []
    with tempfile.TemporaryDirectory(prefix='fc-wifi-test-') as tmp:
        stop = Path(tmp) / 'stop'
        def receive():
            try:
                server.settimeout(15)
                conn, _ = server.accept()
                with conn:
                    if disconnect:
                        return
                    conn.settimeout(0.1)
                    deadline = time.monotonic() + 10
                    requested = False
                    while time.monotonic() < deadline:
                        # Fragment the return message. Input is disabled in this test.
                        msg = b'FCIN' + bytes(16)
                        if '--stop-screen' in extra:
                            diagnostic=b'FCDG'+struct.pack('<4I',100,0,0,1400)
                            conn.sendall(diagnostic[:7]);conn.sendall(diagnostic[7:])
                        conn.sendall(msg[:7])
                        conn.sendall(msg[7:])
                        try:
                            data = conn.recv(65536)
                            if not data:
                                break
                            payload.extend(data)
                        except socket.timeout:
                            pass
                        if len(payload) > 40000 and not requested:
                            stop.touch()
                            requested = True
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                pass
            except Exception as e:
                failure.append(repr(e))
            finally:
                server.close()
        worker = threading.Thread(target=receive, daemon=True)
        worker.start()
        command = ([executable, '--sender'] if executable else
                   [sys.executable, str(ROOT / 'tools/wifi_sender.py'), '--sender'])
        command += ['--tcp', '127.0.0.1', '--tcp-port', str(port), '--color', '--stretch',
                    '--fps', '8', '--audio', 'pcm8', '--seconds', '6', '--no-input',
                    '--stop-file', str(stop)]
        if chunked:
            command.append('--chunked')
        command+=list(extra)
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=25,
                                env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        worker.join(2)
        assert not failure, failure
        if disconnect:
            assert result.returncode != 0, result.stdout + result.stderr
            return dict(disconnect_exit=result.returncode)
        assert result.returncode == 0, result.stdout + result.stderr
        frames = audio = chunks = stops = 0
        position = 0
        expected_offset = 0
        while position + 4 <= len(payload):
            magic = payload[position:position+4]
            if magic == b'FCFR':
                size = 4 + FRAME_BYTES
                if position + size > len(payload):
                    break
                frames += 1
            elif magic == b'FCAU':
                if position + 7 > len(payload):
                    break
                fmt, samples = struct.unpack_from('<BH', payload, position+4)
                assert fmt == 2 and 0 < samples <= 1024
                size = 7 + samples
                if position + size > len(payload):
                    break
                audio += 1
            elif magic == b'FCCH':
                if position + 8 > len(payload):
                    break
                offset, count = struct.unpack_from('<HH', payload, position+4)
                assert offset == expected_offset and 0 < count <= 1024
                size = 8 + count
                if position + size > len(payload):
                    break
                chunks += 1
                expected_offset += count
                if expected_offset == FRAME_BYTES:
                    frames += 1
                    expected_offset = 0
            elif magic==b'FCST':
                stops+=1;size=4
            else:
                raise AssertionError((position, bytes(magic)))
            position += size
        assert frames >= 2, (len(payload), frames, result.stdout, result.stderr)
        assert position == len(payload) and expected_offset == 0, 'shutdown truncated a packet/frame'
        assert stop.exists(), 'did not exercise stop-file shutdown'
        if '--stop-screen' in extra:
            assert stops==1 and payload[-4:]==b'FCST'
            assert '音声診断:' in result.stdout,result.stdout
        return dict(frames=frames, audio_packets=audio, chunks=chunks,
                    stops=stops,bytes=len(payload), exit_code=result.returncode,
                    audio_capture_unavailable='PC の音を録れない' in result.stdout)


if __name__ == '__main__':
    settings = dict(host='127.0.0.1', fps='8', color=True, stretch=True, audio=True,
                    input=False, chunked=False)
    assert '--no-input' in sender_arguments(settings)
    for bad in ('', '-bad', 'host name'):
        try:
            sender_arguments(dict(settings, host=bad))
        except ValueError:
            pass
        else:
            raise AssertionError(bad)
    executable = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(dict(normal=trial(executable), chunked=trial(executable, True),
                          disconnect=trial(executable, disconnect=True)), indent=2))
