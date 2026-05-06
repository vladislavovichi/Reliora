from __future__ import annotations

import socket
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: port_available.py PORT", file=sys.stderr)
        return 2

    try:
        port = int(sys.argv[1])
    except ValueError:
        print(f"Invalid port: {sys.argv[1]}", file=sys.stderr)
        return 2

    if not 1 <= port <= 65535:
        print(f"Port out of range: {port}", file=sys.stderr)
        return 2

    sock: socket.socket | None = None
    try:
        sock = socket.socket()
        sock.settimeout(0.2)
        result = sock.connect_ex(("127.0.0.1", port))
    except OSError as exc:
        print(f"Unable to check port {port}: {exc}", file=sys.stderr)
        return 2
    finally:
        if sock is not None:
            sock.close()

    return 0 if result != 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
