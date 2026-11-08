"""Forward one OpenOCD remote_bitbang connection through the C6 UART."""
import argparse
import socket
import threading
import serial

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM12")
    ap.add_argument("--listen", type=int, default=5002)
    args = ap.parse_args()
    with serial.Serial(port=None, baudrate=115200, timeout=.05, write_timeout=3) as uart:
        uart.port = args.port
        uart.dtr = False
        uart.rts = False
        uart.open()
        uart.reset_input_buffer()
        uart.write(bytes([2]))
        line = bytearray()
        for _ in range(100):
            line.extend(uart.read(128))
            if b"SWD READY" in line:
                break
        else:
            raise RuntimeError("C6 did not enter SWD UART mode")
        print("SWD UART ready", flush=True)
        with socket.socket() as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("127.0.0.1", args.listen))
            server.listen(1)
            server.settimeout(10)
            stop = threading.Event()
            try:
                client, _ = server.accept()
                with client:
                    client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    client.settimeout(.1)
                    def receive():
                        try:
                            while not stop.is_set():
                                data = uart.read(1)
                                if uart.in_waiting:
                                    data += uart.read(uart.in_waiting)
                                if data:
                                    client.sendall(data)
                        except OSError:
                            stop.set()
                    worker = threading.Thread(target=receive, daemon=True)
                    worker.start()
                    while not stop.is_set():
                        try:
                            data = client.recv(4096)
                        except TimeoutError:
                            continue
                        if not data:
                            break
                        uart.write(data)
                    stop.set()
                    worker.join(1)
            finally:
                stop.set()
                uart.write(b"Q")
if __name__ == "__main__":
    main()
