"""Mirror to a Horion board that announces itself as KShare-####.

The board speaks DIAL on port 8008 and Cast on port 8009. Its mirroring
app is 674A0243: a WebRTC OFFER answers with a UDP port, and the screen
is H.264 RTP payload type 96 sent to that port.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

APP_ID = "674A0243"
NS_CONN = "urn:x-cast:com.google.cast.tp.connection"
NS_RECV = "urn:x-cast:com.google.cast.receiver"
NS_HEART = "urn:x-cast:com.google.cast.tp.heartbeat"
NS_WEBRTC = "urn:x-cast:com.google.cast.webrtc"


def _enc_str(field: int, text: str) -> bytes:
    raw = text.encode()
    out = bytes([(field << 3) | 2])
    n = len(raw)
    if n < 128:
        out += bytes([n])
    else:
        out += bytes([(n & 0x7F) | 0x80, n >> 7])
    return out + raw


def _enc_var(field: int, value: int) -> bytes:
    return bytes([(field << 3) | 0, value & 0x7F])


def _frame(source: str, dest: str, namespace: str, payload: str) -> bytes:
    body = (
        _enc_var(1, 0)
        + _enc_str(2, source)
        + _enc_str(3, dest)
        + _enc_str(4, namespace)
        + _enc_var(5, 0)
        + _enc_str(6, payload)
    )
    return struct.pack(">I", len(body)) + body


def _read_json(sock: ssl.SSLSocket, timeout: float = 5) -> dict:
    sock.settimeout(timeout)
    header = b""
    while len(header) < 4:
        chunk = sock.recv(4 - len(header))
        if not chunk:
            raise ConnectionError("board closed the Cast connection")
        header += chunk
    size = struct.unpack(">I", header)[0]
    buf = b""
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise ConnectionError("board closed the Cast connection")
        buf += chunk
    start = buf.find(b"{")
    if start < 0:
        return {}
    return json.loads(buf[start:].decode())


def _local_ips() -> list[str]:
    ips: list[str] = []
    try:
        out = subprocess.run(["ip", "-4", "-j", "addr"], capture_output=True, text=True, check=False)
        data = json.loads(out.stdout or "[]")
        for iface in data:
            if iface.get("ifname") in {"lo", "docker0"} or str(iface.get("ifname", "")).startswith("br-"):
                continue
            for addr in iface.get("addr_info") or []:
                local = addr.get("local")
                if local and not local.startswith("127."):
                    ips.append(local)
    except (OSError, json.JSONDecodeError):
        pass
    return ips


def _gateway() -> str | None:
    try:
        out = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, check=False)
    except OSError:
        return None
    parts = (out.stdout or "").split()
    if "via" in parts:
        return parts[parts.index("via") + 1]
    return None


def _dial_name(ip: str) -> str | None:
    url = f"http://{ip}:8008/ssdp/device-desc.xml"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            root = ET.fromstring(response.read())
    except (OSError, ET.ParseError):
        return None
    for node in root.iter():
        if node.tag.endswith("friendlyName") and node.text:
            return node.text.strip()
    return None


def find_board() -> tuple[str, str] | None:
    """Return (ip, friendly name) for a KShare board on this LAN."""
    seen: list[str] = []
    gateway = _gateway()
    if gateway:
        seen.append(gateway)
    for ip in _local_ips():
        parts = ip.split(".")
        if len(parts) == 4:
            seen.append(".".join(parts[:3] + ["230"]))
            seen.append(".".join(parts[:3] + ["1"]))
    checked: set[str] = set()
    for ip in seen:
        if ip in checked:
            continue
        checked.add(ip)
        name = _dial_name(ip)
        if name and ("kshare" in name.lower() or "horion" in name.lower()):
            return ip, name
    return None


class BoardSession:
    def __init__(self, ip: str, fps: int, monitor: str | None) -> None:
        self.ip = ip
        self.fps = fps
        self.monitor = monitor
        self.sock: ssl.SSLSocket | None = None
        self.session_id = ""
        self.procs: list[subprocess.Popen] = []
        self.tmpdir: tempfile.TemporaryDirectory[str] | None = None
        self._stop = threading.Event()

    def start(self) -> int:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        raw = socket.create_connection((self.ip, 8009), 5)
        sock = ctx.wrap_socket(raw)
        self.sock = sock
        sock.sendall(_frame("sender-0", "receiver-0", NS_CONN, json.dumps({"type": "CONNECT", "origin": {}})))
        sock.sendall(_frame("sender-0", "receiver-0", NS_RECV, json.dumps({"type": "GET_STATUS", "requestId": 1})))
        status = _read_json(sock)
        running = (status.get("status") or {}).get("applications") or []
        if running:
            sock.sendall(_frame(
                "sender-0", "receiver-0", NS_RECV,
                json.dumps({"type": "STOP", "sessionId": running[0].get("sessionId", "")}),
            ))
            time.sleep(0.3)
        sock.sendall(_frame(
            "sender-0", "receiver-0", NS_RECV,
            json.dumps({"type": "LAUNCH", "appId": APP_ID, "requestId": 4}),
        ))
        transport = ""
        for _ in range(6):
            data = _read_json(sock)
            apps = (data.get("status") or {}).get("applications") or []
            if apps and apps[0].get("appId") == APP_ID:
                transport = apps[0]["transportId"]
                self.session_id = apps[0]["sessionId"]
                break
        if not transport:
            raise ConnectionError("the board did not open its mirroring app")
        sock.sendall(_frame("sender-0", transport, NS_CONN, json.dumps({"type": "CONNECT"})))
        ssrc = 112233
        offer = {
            "type": "OFFER",
            "seqNum": 1,
            "offer": {
                "castMode": "mirroring",
                "supportedStreams": [{
                    "index": 0,
                    "type": "video",
                    "codecName": "h264",
                    "rtpProfile": "",
                    "rtpPayloadType": 96,
                    "ssrc": ssrc,
                    "bitRate": 4000000,
                    "maxFrameRate": str(self.fps),
                    "resolutions": [{"width": 1280, "height": 720}],
                }],
            },
        }
        sock.sendall(_frame("sender-0", transport, NS_WEBRTC, json.dumps(offer)))
        answer = _read_json(sock)
        port = (answer.get("answer") or {}).get("udpPort")
        if answer.get("result") != "ok" or not port:
            raise ConnectionError("the board refused the mirror offer")
        self._start_rtp(int(port), ssrc)
        return int(port)

    def _start_rtp(self, port: int, ssrc: int) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise ConnectionError("ffmpeg is not installed")
        rtp = [
            "-an", "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-pix_fmt", "yuv420p", "-profile:v", "baseline", "-g", str(self.fps * 2),
            "-f", "rtp", "-payload_type", "96", "-ssrc", str(ssrc),
            f"rtp://{self.ip}:{port}",
        ]
        if platform.system() == "Linux" and os.environ.get("WAYLAND_DISPLAY") and shutil.which("gpu-screen-recorder"):
            target = self.monitor or _linux_monitor() or "portal"
            self.tmpdir = tempfile.TemporaryDirectory(prefix="kshare-board-")
            fifo = str(Path(self.tmpdir.name) / "screen.mkv")
            os.mkfifo(fifo)
            reader = subprocess.Popen(
                [ffmpeg, "-loglevel", "error", "-fflags", "nobuffer", "-i", fifo, *rtp],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            writer = subprocess.Popen(
                [
                    "gpu-screen-recorder", "-w", target, "-c", "mkv", "-f", str(self.fps),
                    "-k", "h264", "-encoder", "gpu", "-fallback-cpu-encoding", "yes",
                    "-cursor", "yes", "-o", fifo,
                ],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            self.procs.extend([reader, writer])
            return
        grab: list[str]
        if platform.system() == "Linux" and os.environ.get("DISPLAY"):
            grab = ["-f", "x11grab", "-framerate", str(self.fps), "-i", os.environ["DISPLAY"]]
        elif platform.system() == "Darwin":
            grab = ["-f", "avfoundation", "-framerate", str(self.fps), "-i", "1:none"]
        elif platform.system() == "Windows":
            grab = ["-f", "gdigrab", "-framerate", str(self.fps), "-i", "desktop"]
        else:
            raise ConnectionError("this desktop has no screen capture tool")
        self.procs.append(subprocess.Popen(
            [ffmpeg, "-loglevel", "error", *grab, *rtp],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        ))

    def pump(self) -> None:
        assert self.sock is not None
        while not self._stop.wait(5):
            try:
                self.sock.sendall(_frame("sender-0", "receiver-0", NS_HEART, json.dumps({"type": "PING"})))
            except OSError:
                break
            if self.procs and all(proc.poll() is not None for proc in self.procs):
                break

    def close(self) -> None:
        self._stop.set()
        if self.sock is not None and self.session_id:
            try:
                self.sock.sendall(_frame(
                    "sender-0", "receiver-0", NS_RECV,
                    json.dumps({"type": "STOP", "sessionId": self.session_id}),
                ))
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        for proc in self.procs:
            if proc.poll() is None:
                proc.terminate()
        for proc in self.procs:
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.procs.clear()
        if self.tmpdir is not None:
            self.tmpdir.cleanup()
            self.tmpdir = None


def _linux_monitor() -> str | None:
    gsr = shutil.which("gpu-screen-recorder")
    if not gsr:
        return None
    try:
        out = subprocess.run([gsr, "--list-monitors"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in out.stdout.splitlines():
        name = line.split("|", 1)[0].strip()
        if name:
            return name
    return None


def mirror_board(ip: str, name: str, fps: int, monitor: str | None, status_file: str | None) -> None:
    session = BoardSession(ip, fps, monitor)
    if status_file:
        path = Path(status_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"sharing": True, "name": name, "pin": "", "url": f"cast://{ip}"}))
    print(f"Mirroring to {name} at {ip}", flush=True)
    try:
        port = session.start()
        print(f"RTP port {port}", flush=True)
        session.pump()
    finally:
        session.close()
        if status_file:
            Path(status_file).unlink(missing_ok=True)
