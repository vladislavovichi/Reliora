import argparse
import socket
import sys


def check_port_available(port: int) -> int:
    if not 1 <= port <= 65535:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="port_available.py",
        description="Exit 0 when a local TCP port is available, 1 when it is busy.",
    )
    parser.add_argument("port", type=int)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error(f"port out of range: {args.port}")

    return check_port_available(args.port)


if __name__ == "__main__":
    raise SystemExit(main())
