# Raspberry Pi: камера Logitech и MLX90640 → станция по Wi-Fi

Pi только снимает и отправляет. Детекция идёт на ноутбуке, в `interface/`.

```
Logitech USB ──► Pi: ustreamer :8080/stream (MJPEG, без перекодирования) ──Wi-Fi──► ноутбук: interface (Pi cam) → детектор
MLX90640 I2C ──► Pi: mlx_stream (UDP :5005)                              ──Wi-Fi──► ноутбук: interface /thermal
```

## 1. Сеть: два варианта

**А. Pi и ноутбук в одной сети** (роутер или точка доступа с телефона). Проще всего задать Wi-Fi ещё при записи карты в Raspberry Pi Imager (Edit settings → Wi-Fi, hostname, SSH, страна Wi-Fi). Сменить сеть потом можно так:

```bash
sudo ./webcam_setup.sh wifi MyNet 'password'
```

Pi будет виден как `raspberrypi.local` (или тот hostname, что вы задали).

**Б. Pi сам раздаёт Wi-Fi.** Для работы в поле, где нет роутера:

```bash
sudo ./webcam_setup.sh hotspot SAR-PI 'pass12345'   # пароль не короче 8 символов
```

Ноутбук подключается к сети `SAR-PI`, у Pi адрес `10.42.0.1`. Точка доступа поднимается сама при каждой загрузке. Вернуться в обычную сеть: `sudo ./webcam_setup.sh wifi ...`.

Если вы зашли на Pi по SSH через Wi-Fi, после переключения сети SSH оборвётся, это нормально. Само переключение скрипт выполняет в фоне (лог в `/var/log/wifi-switch.log`), после чего надо переподключиться уже к новой сети. Если страна Wi-Fi не задана, скрипт ставит `KZ`. Другая страна: `COUNTRY=XX sudo -E ./webcam_setup.sh ...`.

## 2. Камера

Скопировать скрипт на Pi и поставить:

```bash
scp raspberry/webcam_setup.sh pi@raspberrypi.local:~
ssh pi@raspberrypi.local
sudo ./webcam_setup.sh install
```

Скрипт ставит `ustreamer`. Сервис `webcam-stream` запускается при загрузке и перезапускается, если камеру выдернули и вставили обратно. Проверить можно в браузере ноутбука: `http://raspberrypi.local:8080/stream` (в режиме Б это `http://10.42.0.1:8080/stream`).

Камера Logitech сама сжимает кадры в MJPEG, поэтому Pi их только пересылает (`ENCODER=HW`). Нагрузка на процессор почти нулевая, подходит даже Pi Zero 2 W. Настройки лежат в `/etc/default/webcam-stream`, после правки нужно `sudo systemctl restart webcam-stream`:

| Параметр | По умолчанию | Примечание |
| --- | --- | --- |
| `RESOLUTION` | `1280x720` | C920/C922 умеют `1920x1080`. Режимы камеры: `./webcam_setup.sh status` |
| `FPS` | `30` | 720p×30 — это около 20–25 Мбит/с. Если по Wi-Fi тормозит, ставьте 15 |
| `PORT` | `8080` | |
| `DEVICE` | `/dev/v4l/by-id/usb-046d…` | находится при `install` |
| `ENCODER` | `HW` | `CPU`, если камера не отдаёт MJPEG или сервис не стартует (`journalctl -u webcam-stream`) |

## 3. На ноутбуке

```bash
cd interface && npm run dev
```

Откройте http://localhost:8765/#pi, введите адрес Pi (`raspberrypi.local:8080` или `10.42.0.1:8080`) и нажмите **Connect**. Адрес запоминается. Адрес по умолчанию задаётся при запуске: `PICAM_URL=http://10.42.0.1:8080/stream npm run dev`.

Ноутбук держит одно соединение с Pi, сколько бы вкладок ни было открыто. Сцена показывает поток плавно, а детектор берёт самый свежий кадр, без перекодирования. Дальше всё работает как в режиме Camera: модели, tiling, список найденных людей, экспорт JSON.

Проверка без Pi: `python raspberry/fake_cam_stream.py` (нужен ffmpeg), затем в интерфейсе адрес `localhost:8080`. С записью дрона: `--video drone.mp4`.

## Файлы

| Файл | Где запускается | Что делает |
| --- | --- | --- |
| `webcam_setup.sh` | Pi | ustreamer + systemd, переключение Wi-Fi / точки доступа |
| `fake_cam_stream.py` | ноутбук | имитатор камеры на Pi (MJPEG `/stream`, как у ustreamer) |
| `mlx_stream.cpp` | Pi | MLX90640 → UDP |
| `fake_mlx_stream.py` | ноутбук | имитатор MLX90640 |
| `thermal_receiver.py` | ноутбук | простой просмотр тепловизора без интерфейса |
