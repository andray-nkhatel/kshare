"""LAN announcement so other machines can find a host without typing an IP."""

from __future__ import annotations

import json
import socket
import threading
import time

DISCOVER_PORT = 47331
MAGIC = "kshare-announce-v1"


def _broadcast_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    return sock


def announce_forever(name: str, http_port: int, stop: threading.Event) -> None:
    payload = json.dumps(
        {"magic": MAGIC, "name": name, "port": http_port}
    ).encode("utf-8")
    sock = _broadcast_socket()
    try:
        while not stop.is_set():
            try:
                sock.sendto(payload, ("255.255.255.255", DISCOVER_PORT))
            except OSError:
                pass
            if stop.wait(2.0):
                break
    finally:
        sock.close()


def listen(seconds: float = 3.0) -> list[dict[str, str]]:
    sock = _broadcast_socket()
    sock.settimeout(0.5)
    try:
        sock.bind(("", DISCOVER_PORT))
    except OSError:
        return []
    found: dict[str, dict[str, str]] = {}
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            try:
                data, addr = sock.recvfrom(4096)
            except TimeoutError:
                continue
            except OSError:
                break
            try:
                msg = json.loads(data.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                continue
            if msg.get("magic") != MAGIC:
                continue
            host = addr[0]
            port = int(msg["port"])
            found[f"{host}:{port}"] = {
                "name": str(msg.get("name") or host),
                "url": f"http://{host}:{port}/",
            }
    finally:
        sock.close()
    return list(found.values())
