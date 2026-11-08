"""Local OpenOCD remote_bitbang relay with batched SWD input over Wi-Fi."""
import argparse
import collections
import socket

def read_exact(sock, count):
    result = bytearray()
    while len(result) < count:
        chunk = sock.recv(count - len(result))
        if not chunk:
            raise ConnectionError("C6 disconnected")
        result.extend(chunk)
    if any(value not in (48, 49) for value in result):
        raise ValueError("Invalid C6 SWD samples")
    return result

def relay(local, remote):
    pending = bytearray()
    samples = collections.deque()
    output = True
    request = 0
    input_count = 0
    clocks_to_skip = 0

    def flush():
        if pending:
            remote.sendall(pending)
            pending.clear()

    while True:
        data = local.recv(8192)
        if not data:
            flush()
            return
        for command in data:
            if command in (ord("B"), ord("b")):
                continue
            if command == ord("o"):
                output = False
                input_count = 38 if request & 4 else 4
                clocks_to_skip = input_count * 2
                samples.clear()
            elif command == ord("O"):
                output = True
            if not output and command in (ord("d"), ord("f")) and clocks_to_skip:
                clocks_to_skip -= 1
                continue
            if command == ord("c") and not output and input_count:
                if not samples:
                    pending.append(ord("H") if input_count == 38 else ord("h"))
                    flush()
                    samples.extend(read_exact(remote, input_count))
                local.sendall(bytes([samples.popleft()]))
                input_count -= 1
                continue
            if output and command in (ord("f"), ord("g")):
                request = (request >> 1) | ((command - ord("f")) << 7)
            pending.append(command)
            if command == ord("Q"):
                flush()
                return
            if len(pending) >= 8192:
                flush()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--listen", type=int, default=5002)
    args = parser.parse_args()
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", args.listen))
        server.listen(1)
        server.settimeout(30)
        print("SWD relay ready", flush=True)
        local, _ = server.accept()
        with local, socket.create_connection((args.host, args.port), 5) as remote:
            local.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            remote.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            remote.settimeout(15)
            try:
                relay(local, remote)
            finally:
                try:
                    remote.sendall(b"Q")
                except OSError:
                    pass

if __name__ == "__main__":
    main()
