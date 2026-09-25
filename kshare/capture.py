"""Screen capture backends.

Linux (Wayland/Hyprland, including Omarchy) uses gpu-screen-recorder.
Other desktops use ffmpeg's native grabber: x11grab, avfoundation, or gdigrab.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


class CaptureError(RuntimeError):
    pass


def _which(name: str) -> str | None:
    return shutil.which(name)


def describe_backend(monitor: str | None = None) -> str:
    system = platform.system()
    if system == "Linux" and os.environ.get("WAYLAND_DISPLAY") and _which("gpu-screen-recorder"):
        target = monitor or _default_linux_monitor() or "portal"
        return f"gpu-screen-recorder ({target})"
    if system == "Linux" and os.environ.get("DISPLAY") and _which("ffmpeg"):
        return f"ffmpeg x11grab ({os.environ.get('DISPLAY')})"
    if system == "Darwin" and _which("ffmpeg"):
        return "ffmpeg avfoundation"
    if system == "Windows" and _which("ffmpeg"):
        return "ffmpeg gdigrab"
    raise CaptureError(_missing_message())


def _missing_message() -> str:
    system = platform.system()
    if system == "Linux":
        return "Need ffmpeg, and on Wayland also gpu-screen-recorder."
    if system == "Darwin":
        return "Need ffmpeg (brew install ffmpeg). Screen Recording permission is required."
    if system == "Windows":
        return "Need ffmpeg on PATH (https://www.gyan.dev/ffmpeg/builds/)."
    return f"Unsupported system: {system}"


def _default_linux_monitor() -> str | None:
    gsr = _which("gpu-screen-recorder")
    if not gsr:
        return None
    try:
        out = subprocess.run(
            [gsr, "--list-monitors"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in out.stdout.splitlines():
        name = line.split("|", 1)[0].strip()
        if name:
            return name
    return None


class JpegCapture:
    """Yields JPEG frames from a screen grabber."""

    def __init__(self, fps: int = 15, monitor: str | None = None) -> None:
        self.fps = max(1, min(fps, 60))
        self.monitor = monitor
        self._procs: list[subprocess.Popen] = []
        self._tmpdir: tempfile.TemporaryDirectory[str] | None = None
        self._thread: threading.Thread | None = None
        self._frames: list[bytes] = []
        self._cond = threading.Condition()
        self._seq = 0
        self._closed = False
        self.backend = describe_backend(monitor)

    def start(self) -> None:
        if self._thread:
            return
        self._spawn()
        self._thread = threading.Thread(target=self._read_loop, name="kshare-capture", daemon=True)
        self._thread.start()

    def latest(self, after: int) -> tuple[int, bytes] | None:
        with self._cond:
            if self._seq > after and self._frames:
                return self._seq, self._frames[-1]
            return None

    def wait_frame(self, after: int, timeout: float = 5.0) -> tuple[int, bytes] | None:
        with self._cond:
            if self._seq <= after:
                self._cond.wait(timeout)
            if self._seq > after and self._frames:
                return self._seq, self._frames[-1]
            return None

    def stop(self) -> None:
        self._closed = True
        for proc in self._procs:
            if proc.poll() is None:
                proc.terminate()
        for proc in self._procs:
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._procs.clear()
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
            self._tmpdir = None
        with self._cond:
            self._cond.notify_all()

    def _spawn(self) -> None:
        ffmpeg = _which("ffmpeg")
        if not ffmpeg:
            raise CaptureError(_missing_message())
        system = platform.system()
        if system == "Linux" and os.environ.get("WAYLAND_DISPLAY") and _which("gpu-screen-recorder"):
            self._spawn_linux_wayland(ffmpeg)
            return
        if system == "Linux" and os.environ.get("DISPLAY"):
            self._spawn_ffmpeg(ffmpeg, ["-f", "x11grab", "-framerate", str(self.fps), "-i", os.environ["DISPLAY"]])
            return
        if system == "Darwin":
            # "1:none" is the main display without audio on typical avfoundation setups.
            self._spawn_ffmpeg(
                ffmpeg,
                ["-f", "avfoundation", "-framerate", str(self.fps), "-i", "1:none"],
            )
            return
        if system == "Windows":
            self._spawn_ffmpeg(
                ffmpeg,
                ["-f", "gdigrab", "-framerate", str(self.fps), "-i", "desktop"],
            )
            return
        raise CaptureError(_missing_message())

    def _spawn_linux_wayland(self, ffmpeg: str) -> None:
        gsr = _which("gpu-screen-recorder")
        assert gsr
        target = self.monitor or _default_linux_monitor() or "portal"
        self._tmpdir = tempfile.TemporaryDirectory(prefix="kshare-")
        fifo = str(Path(self._tmpdir.name) / "screen.mkv")
        os.mkfifo(fifo)
        # Open the read end first so gpu-screen-recorder can open the write end.
        reader = subprocess.Popen(
            [
                ffmpeg,
                "-loglevel",
                "error",
                "-fflags",
                "nobuffer",
                "-i",
                fifo,
                "-an",
                "-vf",
                "fps=" + str(self.fps),
                *self._jpeg_output(),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        writer = subprocess.Popen(
            [
                gsr,
                "-w",
                target,
                "-c",
                "mkv",
                "-f",
                str(self.fps),
                "-k",
                "h264",
                "-encoder",
                "gpu",
                "-fallback-cpu-encoding",
                "yes",
                "-cursor",
                "yes",
                "-o",
                fifo,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self._procs.extend([reader, writer])

    def _spawn_ffmpeg(self, ffmpeg: str, grab: list[str]) -> None:
        proc = subprocess.Popen(
            [ffmpeg, "-loglevel", "error", *grab, "-an", *self._jpeg_output()],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._procs.append(proc)

    def _jpeg_output(self) -> list[str]:
        return ["-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "6", "pipe:1"]

    def _read_loop(self) -> None:
        stream = self._procs[0].stdout
        if stream is None:
            return
        buf = bytearray()
        try:
            while not self._closed:
                chunk = stream.read(65536)
                if not chunk:
                    break
                buf.extend(chunk)
                self._drain(buf)
        finally:
            err = b""
            proc = self._procs[0] if self._procs else None
            if proc and proc.stderr:
                err = proc.stderr.read() or b""
            if err and not self._closed:
                sys.stderr.write(err.decode("utf-8", "replace"))
            with self._cond:
                self._cond.notify_all()

    def _drain(self, buf: bytearray) -> None:
        while True:
            start = buf.find(b"\xff\xd8")
            if start < 0:
                if len(buf) > 2:
                    del buf[:-1]
                return
            end = buf.find(b"\xff\xd9", start + 2)
            if end < 0:
                if start > 0:
                    del buf[:start]
                return
            frame = bytes(buf[start : end + 2])
            del buf[: end + 2]
            with self._cond:
                self._frames = [frame]
                self._seq += 1
                self._cond.notify_all()
