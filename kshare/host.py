from __future__ import annotations

import argparse
import hashlib
import hmac
import http.server
import json
import secrets
import socket
import socketserver
import threading
import time
import urllib.parse
from pathlib import Path
import http.cookies
from http.cookies import SimpleCookie

from kshare.capture import CaptureError, JpegCapture
from kshare.discover import announce_forever

COOKIE = "kshare_session"


def _local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 1))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def _make_pin(explicit: str | None) -> str:
    if explicit:
        if not (explicit.isdigit() and len(explicit) == 6):
            raise SystemExit("PIN must be 6 digits.")
        return explicit
    return f"{secrets.randbelow(1_000_000):06d}"


class HostState:
    def __init__(self, pin: str, name: str, fps: int, monitor: str | None) -> None:
        self.pin = pin
        self.name = name
        self.fps = fps
        self.monitor = monitor
        self.token = secrets.token_hex(16)
        self.capture: JpegCapture | None = None
        self.viewers = 0
        self.lock = threading.Lock()
        self.started = time.time()

    def session_ok(self, handler: http.server.BaseHTTPRequestHandler) -> bool:
        raw = handler.headers.get("Cookie", "")
        jar = SimpleCookie()
        try:
            jar.load(raw)
        except http.cookies.CookieError:
            return False
        morsel = jar.get(COOKIE)
        if morsel is None:
            return False
        return hmac.compare_digest(morsel.value, self.token)

    def ensure_capture(self) -> JpegCapture:
        with self.lock:
            if self.capture is None:
                self.capture = JpegCapture(fps=self.fps, monitor=self.monitor)
                self.capture.start()
            self.viewers += 1
            return self.capture

    def release_capture(self) -> None:
        with self.lock:
            self.viewers = max(0, self.viewers - 1)
            if self.viewers == 0 and self.capture is not None:
                self.capture.stop()
                self.capture = None


def make_handler(state: HostState):
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args) -> None:
            return

        def _send(self, code: int, body: bytes, content_type: str, extra: dict[str, str] | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if extra:
                for key, value in extra.items():
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urllib.parse.urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(200, b"KShare host. Open the Windows viewer and enter the PIN.\n", "text/plain; charset=utf-8")
                return
            if path == "/api/info":
                body = json.dumps({"name": state.name, "needPin": True}).encode()
                self._send(200, body, "application/json")
                return
            if path == "/stream":
                if not state.session_ok(self):
                    self._send(401, b"pin required", "text/plain")
                    return
                self._stream()
                return
            self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            path = urllib.parse.urlparse(self.path).path
            if path != "/api/pair":
                self._send(404, b"not found", "text/plain")
                return
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(min(length, 4096))
            try:
                pin = str(json.loads(raw.decode() or "{}").get("pin", ""))
            except json.JSONDecodeError:
                pin = ""
            digest_ok = hmac.compare_digest(
                hashlib.sha256(pin.encode()).digest(),
                hashlib.sha256(state.pin.encode()).digest(),
            )
            if not digest_ok:
                self._send(403, b'{"ok":false}', "application/json")
                return
            self._send(
                200,
                b'{"ok":true}',
                "application/json",
                {"Set-Cookie": f"{COOKIE}={state.token}; HttpOnly; SameSite=Strict; Path=/"},
            )

        def _stream(self) -> None:
            try:
                capture = state.ensure_capture()
            except CaptureError as exc:
                self._send(500, str(exc).encode(), "text/plain")
                return
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            seq = 0
            try:
                while True:
                    item = capture.wait_frame(seq, timeout=8.0)
                    if item is None:
                        if capture._procs and all(p.poll() is not None for p in capture._procs):
                            break
                        continue
                    seq, frame = item
                    header = (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
                    )
                    self.wfile.write(header + frame + b"\r\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass
            finally:
                state.release_capture()

    return Handler


def serve(args: argparse.Namespace) -> None:
    pin = _make_pin(args.pin)
    name = args.name or socket.gethostname()
    state = HostState(pin, name, args.fps, args.monitor)
    handler = make_handler(state)
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    try:
        httpd = Server(("0.0.0.0", args.port), handler)
    except OSError as exc:
        raise SystemExit(f"Cannot listen on port {args.port}: {exc}") from exc

    stop = threading.Event()
    if not args.no_discover:
        threading.Thread(
            target=announce_forever,
            args=(name, args.port, stop),
            name="kshare-announce",
            daemon=True,
        ).start()

    ip = _local_ip()
    url = f"http://{ip}:{args.port}/"
    status_path = getattr(args, "status_file", None)
    if status_path:
        path = Path(status_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"name": name, "url": url, "pin": pin, "port": args.port}))
    print(f"KShare host  {name}", flush=True)
    print(f"Open         {url}", flush=True)
    print(f"PIN          {pin}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    thread = threading.Thread(target=httpd.serve_forever, name="kshare-http", daemon=True)
    thread.start()
    try:
        while thread.is_alive():
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        stop.set()
        httpd.shutdown()
        if status_path:
            Path(status_path).unlink(missing_ok=True)
        if state.capture:
            state.capture.stop()
