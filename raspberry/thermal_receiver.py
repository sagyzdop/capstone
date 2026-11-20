"""
thermal_receiver.py — приём кадров MLX90640 с Raspberry Pi по UDP и показ на экране.

Установка (на ноутбуке):  pip install numpy opencv-python
Запуск:                   python thermal_receiver.py            (порт 5005)
                          python thermal_receiver.py --port 5005 --record

Клавиши в окне:  q — выход,  r — начать/остановить запись,  f — отразить по горизонтали
Запись сохраняется в thermal_YYYYmmdd_HHMMSS.npz: temps (N×24×32, °C), frame_id, t_pi_us, t_recv
"""
import argparse
import socket
import struct
import time

import cv2
import numpy as np

HEADER = struct.Struct("<IIQff")       # magic, frame_id, timestamp_us, ta, reserved
MAGIC = 0x3039584D
PACKET_SIZE = HEADER.size + 768 * 4    # 3096 байт
SCALE = 20                             # 32×24 → 640×480


def parse(data: bytes):
    if len(data) != PACKET_SIZE:
        return None
    magic, frame_id, ts_us, ta, _ = HEADER.unpack_from(data)
    if magic != MAGIC:
        return None
    temps = np.frombuffer(data, dtype="<f4", offset=HEADER.size).reshape(24, 32)
    return frame_id, ts_us, ta, temps


def render(temps, flip, fps, lost, ta, recording):
    t = np.fliplr(temps) if flip else temps
    tmin, tmax = float(t.min()), float(t.max())
    norm = ((t - tmin) / max(tmax - tmin, 0.5) * 255).clip(0, 255).astype(np.uint8)
    img = cv2.resize(norm, (32 * SCALE, 24 * SCALE), interpolation=cv2.INTER_CUBIC)
    img = cv2.applyColorMap(img, cv2.COLORMAP_INFERNO)

    # Точка максимума
    y, x = np.unravel_index(np.argmax(t), t.shape)
    cx, cy = int((x + 0.5) * SCALE), int((y + 0.5) * SCALE)
    cv2.drawMarker(img, (cx, cy), (255, 255, 255), cv2.MARKER_CROSS, 20, 2)

    text = f"{fps:4.1f} fps  min {tmin:5.1f}C  max {tmax:5.1f}C  sensor {ta:4.1f}C  lost {lost}"
    cv2.putText(img, text, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    if recording:
        cv2.circle(img, (32 * SCALE - 18, 18), 8, (0, 0, 255), -1)
    return img


def save(buf):
    if not buf["temps"]:
        return
    name = time.strftime("thermal_%Y%m%d_%H%M%S.npz")
    np.savez_compressed(name, temps=np.stack(buf["temps"]), frame_id=np.array(buf["id"]),
                        t_pi_us=np.array(buf["ts"]), t_recv=np.array(buf["recv"]))
    print(f"Сохранено {len(buf['temps'])} кадров в {name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--record", action="store_true", help="начать запись сразу")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
    sock.bind(("0.0.0.0", args.port))
    sock.settimeout(0.5)
    print(f"Жду кадры на UDP-порту {args.port}...")

    recording = args.record
    buf = {"temps": [], "id": [], "ts": [], "recv": []}
    flip = False
    last_id = None
    lost = 0
    fps, n, t0 = 0.0, 0, time.time()
    latest = None

    while True:
        try:
            data, _ = sock.recvfrom(65535)
        except socket.timeout:
            data = None

        # Забираем всё, что накопилось, чтобы показывать самый свежий кадр
        packets = [data] if data else []
        sock.setblocking(False)
        try:
            while True:
                packets.append(sock.recvfrom(65535)[0])
        except (BlockingIOError, OSError):
            pass
        sock.settimeout(0.5)

        for p in packets:
            r = parse(p)
            if r is None:
                continue
            frame_id, ts_us, ta, temps = r
            if last_id is not None and frame_id > last_id + 1:
                lost += frame_id - last_id - 1
            last_id = frame_id
            n += 1
            latest = r
            if recording:
                buf["temps"].append(temps.copy()); buf["id"].append(frame_id)
                buf["ts"].append(ts_us); buf["recv"].append(time.time())

        now = time.time()
        if now - t0 >= 1.0:
            fps, n, t0 = n / (now - t0), 0, now

        if latest is not None:
            cv2.imshow("MLX90640", render(latest[3], flip, fps, lost, latest[2], recording))
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("f"):
            flip = not flip
        if key == ord("r"):
            if recording:
                save(buf)
                buf = {"temps": [], "id": [], "ts": [], "recv": []}
            recording = not recording

    if recording:
        save(buf)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
