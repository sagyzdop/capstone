"""
fake_mlx_stream.py — имитатор Raspberry Pi + MLX90640: шлёт по UDP такие же пакеты, как mlx_stream.cpp.
Нужен, чтобы проверить интерфейс (http://localhost:8765/thermal) без железа.

Запуск (на ноутбуке, рядом с запущенным интерфейсом):
    python raspberry/fake_mlx_stream.py                       # 127.0.0.1:5005, 16 кадров/с, синтетическая сцена
    python raspberry/fake_mlx_stream.py --npy interface/thermal/examples/frame_10m.npy
    python raspberry/fake_mlx_stream.py --npy recordings/thermal_….npy   # проиграть запись со страницы
    python raspberry/fake_mlx_stream.py 192.168.1.42 5005 --fps 32

Сцена: земля 8–14 °C с градиентом и текстурой, двое «людей» (+9 и +5 °C, пятна 2–4 пикселя) ходят по кадру,
горячий двигатель 70 °C в углу (детектор должен его отбросить), шум 0.3 °C.
"""
import argparse
import socket
import struct
import time

import numpy as np

HEADER = struct.Struct("<IIQff")  # magic, frame_id, timestamp_us, ta, reserved
MAGIC = 0x3039584D
H, W = 24, 32


def scene(rng: np.random.Generator):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    ground = 8 + 6 * xx / W + 1.0 * np.sin(yy / 3) * np.cos(xx / 5)
    t0 = time.time()

    def frame() -> np.ndarray:
        t = time.time() - t0
        f = ground.copy()
        for cx, cy, amp, sig in (
            (16 + 10 * np.sin(t / 4), 12 + 6 * np.sin(t / 3), 9.0, 1.1),  # стоит
            (8 + 4 * np.cos(t / 5), 18 + 2 * np.sin(t / 2), 5.0, 0.8),  # лежит, дальше
        ):
            f += amp * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sig**2))
        f[1:4, 27:30] = 70.0  # двигатель
        return (f + rng.normal(0, 0.3, f.shape)).astype(np.float32)

    return frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("host", nargs="?", default="127.0.0.1", help="IP компьютера с интерфейсом")
    ap.add_argument("port", nargs="?", type=int, default=5005)
    ap.add_argument("--fps", type=float, default=16)
    ap.add_argument("--npy", help="кадр 24×32 или запись N×24×32 в °C вместо синтетики")
    ap.add_argument("--noise", type=float, default=0.3, help="шум поверх --npy, °C")
    args = ap.parse_args()

    rng = np.random.default_rng(0)
    if args.npy:
        data = np.load(args.npy).astype(np.float32).reshape(-1, H, W)
        i = 0

        def next_frame():
            nonlocal i
            f = data[i % len(data)]
            i += 1
            return (f + rng.normal(0, args.noise, f.shape)).astype(np.float32) if len(data) == 1 else f
    else:
        next_frame = scene(rng)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"Шлю {args.fps:g} кадров/с на {args.host}:{args.port} (Ctrl+C — стоп)")
    frame_id, period, nxt = 0, 1.0 / args.fps, time.perf_counter()
    while True:
        temps = next_frame()
        pkt = HEADER.pack(MAGIC, frame_id, int(time.monotonic() * 1e6), 30.0, 0.0) + temps.astype("<f4").tobytes()
        sock.sendto(pkt, (args.host, args.port))
        frame_id += 1
        nxt += period
        time.sleep(max(0.0, nxt - time.perf_counter()))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
