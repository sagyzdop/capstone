"""
fake_cam_stream.py — имитатор Raspberry Pi + Logitech: отдаёт MJPEG так же, как ustreamer на Pi
(GET /stream — multipart/x-mixed-replace, GET /snapshot — один JPEG). Нужен, чтобы проверить
режим «Pi cam» в интерфейсе (http://localhost:8765/#pi) без железа.

Нужен только ffmpeg (brew install ffmpeg), Python — стандартная библиотека.

    python raspberry/fake_cam_stream.py                          # тестовая таблица 1280×720, 30 кадров/с, :8080
    python raspberry/fake_cam_stream.py --video drone.mp4        # видео по кругу, в реальном темпе
    python raspberry/fake_cam_stream.py --webcam                 # камера ноутбука (macOS, avfoundation)
    python raspberry/fake_cam_stream.py --port 8081 --fps 15

В интерфейсе: Source → Pi cam, адрес localhost:8080 → Connect.
"""
import argparse
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BOUNDARY = "boundarydonotcross"  # как у ustreamer


class Latest:
    def __init__(self):
        self.cond = threading.Condition()
        self.jpeg = b""
        self.n = 0

    def put(self, jpeg: bytes):
        with self.cond:
            self.jpeg, self.n = jpeg, self.n + 1
            self.cond.notify_all()

    def wait(self, after: int, timeout=5.0):
        with self.cond:
            self.cond.wait_for(lambda: self.n > after, timeout)
            return self.n, self.jpeg


def ffmpeg_cmd(args) -> list[str]:
    if args.video:
        src = ["-re", "-stream_loop", "-1", "-i", args.video]
    elif args.webcam:
        src = ["-f", "avfoundation", "-framerate", "30", "-video_size", "1280x720", "-i", "0"]
    else:
        src = ["-re", "-f", "lavfi", "-i", f"testsrc2=size={args.size}:rate={args.fps}"]
    w, h = args.size.split("x")
    vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,fps={args.fps}"
    return ["ffmpeg", "-loglevel", "error", *src, "-an", "-vf", vf, "-q:v", "5", "-f", "mjpeg", "pipe:1"]


def pump(cmd: list[str], latest: Latest):
    """ffmpeg пишет JPEG подряд; режем по маркерам SOI/EOI (у ffmpeg нет EXIF-миниатюр, так что это надёжно)."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    buf = b""
    while chunk := p.stdout.read(65536):
        buf += chunk
        while True:
            s = buf.find(b"\xff\xd8")
            e = buf.find(b"\xff\xd9", s + 2)
            if s < 0 or e < 0:
                break
            latest.put(buf[s : e + 2])
            buf = buf[e + 2 :]
    print(f"ffmpeg завершился (код {p.wait()})", file=sys.stderr)
    os._exit(1)  # из потока: sys.exit остановил бы только его


def handler(latest: Latest):
    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):
            sys.stderr.write(f"{self.address_string()} {fmt % a}\n")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/snapshot":
                _, jpeg = latest.wait(0)
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpeg)))
                self.end_headers()
                self.wfile.write(jpeg)
                return
            if path != "/stream":
                self.send_error(404, "есть /stream и /snapshot")
                return
            self.send_response(200)
            self.send_header("Content-Type", f"multipart/x-mixed-replace;boundary={BOUNDARY}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            n = 0
            try:
                while True:
                    n, jpeg = latest.wait(n)
                    self.wfile.write(
                        f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n".encode()
                        + jpeg
                        + b"\r\n"
                    )
            except (BrokenPipeError, ConnectionResetError):
                pass

    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--size", default="1280x720")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--video", help="видеофайл вместо тестовой таблицы")
    g.add_argument("--webcam", action="store_true", help="камера ноутбука (macOS)")
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        sys.exit("нужен ffmpeg: brew install ffmpeg")

    latest = Latest()
    threading.Thread(target=pump, args=(ffmpeg_cmd(args), latest), daemon=True).start()
    srv = ThreadingHTTPServer((args.host, args.port), handler(latest))
    srv.daemon_threads = True
    print(f"MJPEG: http://localhost:{args.port}/stream  (Ctrl+C — стоп)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
