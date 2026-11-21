#!/usr/bin/env bash
# webcam_setup.sh — Logitech USB-камера на Raspberry Pi -> MJPEG по Wi-Fi на станцию (ноутбук с interface/).
#
# На Pi (Raspberry Pi OS Bookworm, NetworkManager):
#   sudo ./webcam_setup.sh install                        # ustreamer + автозапуск: http://<pi>:8080/stream
#   sudo ./webcam_setup.sh wifi SAR-MODEM pass1234        # Pi всегда подключается к модему (можно настроить заранее)
#   sudo ./webcam_setup.sh wifi SAR-MODEM pass1234 192.168.8.50/24   # то же, с постоянным адресом Pi
#   sudo ./webcam_setup.sh hotspot SAR-PI pass1234        # запасной вариант: Pi сам раздаёт Wi-Fi, Pi = 10.42.0.1
#   ./webcam_setup.sh status                              # камера, сеть, адреса
#
# Настройки камеры: /etc/default/webcam-stream (RESOLUTION, FPS, PORT, DEVICE, ENCODER), затем
#   sudo systemctl restart webcam-stream
# Кодирования на Pi нет: Logitech сама отдаёт MJPEG, ustreamer только пересылает кадры (ENCODER=HW).
set -euo pipefail

CONF=/etc/default/webcam-stream
UNIT=/etc/systemd/system/webcam-stream.service
HOTSPOT=sar-hotspot
MODEM=sar-modem
IFACE=${IFACE:-wlan0}

die() { echo "✖ $*" >&2; exit 1; }
need_root() { [[ $EUID -eq 0 ]] || die "запустите через sudo"; }

find_camera() {
  # стабильный путь Logitech (vendor 046d), не зависит от порядка /dev/videoN
  local p
  for p in /dev/v4l/by-id/usb-046d*-video-index0 /dev/v4l/by-id/usb-*-video-index0; do
    [[ -e $p ]] && { echo "$p"; return; }
  done
  echo /dev/video0
}

cmd_install() {
  need_root
  apt-get update
  apt-get install -y ustreamer v4l-utils
  local dev; dev=$(find_camera)
  [[ -e $dev ]] || echo "! камера не найдена (lsusb | grep -i logitech). Ставлю с DEVICE=$dev, поправьте в $CONF"

  if [[ ! -f $CONF ]]; then
    cat >"$CONF" <<EOF
# Logitech webcam -> ustreamer. Режимы камеры: v4l2-ctl -d \$DEVICE --list-formats-ext
DEVICE=$dev
RESOLUTION=1280x720
FPS=30
PORT=8080
# HW: готовый MJPEG с камеры, без перекодирования. CPU: если камера не умеет MJPEG (медленнее)
ENCODER=HW
EOF
  fi

  cat >"$UNIT" <<'EOF'
[Unit]
Description=Logitech webcam MJPEG stream (ustreamer)
After=network.target

[Service]
EnvironmentFile=/etc/default/webcam-stream
ExecStart=/usr/bin/ustreamer --device=${DEVICE} --format=MJPEG --encoder=${ENCODER} --resolution=${RESOLUTION} --desired-fps=${FPS} --host=0.0.0.0 --port=${PORT}
Restart=always
RestartSec=2
DynamicUser=yes
SupplementaryGroups=video

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now webcam-stream
  sleep 2
  systemctl --no-pager --lines=5 status webcam-stream || true
  echo
  show_urls
}

# Переключение сети рвёт SSH, если вы зашли по Wi-Fi: выполняем его отвязанным от сессии
detached() {
  if [[ -n ${SSH_CONNECTION:-} ]]; then
    echo "! SSH оборвётся. Переключаю в фоне, лог: /var/log/wifi-switch.log"
    nohup setsid bash -c "$1" >/var/log/wifi-switch.log 2>&1 </dev/null &
  else
    bash -c "$1"
  fi
}

ensure_wifi_on() {
  rfkill unblock wifi || true
  if ! iw reg get 2>/dev/null | grep -q "country [A-Z][A-Z]"; then
    # без страны Wi-Fi на Pi заблокирован; поменяйте COUNTRY, если вы не в Казахстане
    raspi-config nonint do_wifi_country "${COUNTRY:-KZ}" || true
    echo "Страна Wi-Fi: ${COUNTRY:-KZ} (COUNTRY=XX sudo -E $0 ... чтобы сменить)"
  fi
}

cmd_hotspot() {
  need_root
  local ssid=${1:-} pass=${2:-}
  [[ -n $ssid && ${#pass} -ge 8 ]] || die "использование: sudo $0 hotspot <SSID> <пароль от 8 символов>"
  command -v nmcli >/dev/null || die "нужен NetworkManager (Raspberry Pi OS Bookworm и новее)"
  ensure_wifi_on
  nmcli con delete "$HOTSPOT" >/dev/null 2>&1 || true
  nmcli con add type wifi ifname "$IFACE" con-name "$HOTSPOT" ssid "$ssid" autoconnect yes \
    connection.autoconnect-priority 100 \
    802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 \
    ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv6.method disabled \
    wifi-sec.key-mgmt wpa-psk wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.group ccmp wifi-sec.psk "$pass" >/dev/null
  echo "Точка доступа «$ssid» включена и будет подниматься при загрузке."
  echo "Ноутбук: подключитесь к «$ssid», в интерфейсе Pi cam -> 10.42.0.1:8080"
  detached "nmcli con up $HOTSPOT"
}

cmd_wifi() {
  need_root
  local ssid=${1:-} pass=${2:-} ip=${3:-} gw=${4:-}
  [[ -n $ssid ]] || die "использование: sudo $0 wifi <SSID> [пароль] [IP/маска [шлюз]]"
  [[ -z $pass || ${#pass} -ge 8 ]] || die "пароль WPA — от 8 символов"
  command -v nmcli >/dev/null || die "нужен NetworkManager (Raspberry Pi OS Bookworm и новее)"
  ensure_wifi_on

  # Сохранённый профиль: сеть не обязана быть видна сейчас, Pi подключится, когда модем появится.
  # autoconnect-retries 0 — пробовать бесконечно (модем в поле часто включается позже Pi),
  # priority 50 — модем важнее других сохранённых сетей
  local args=(type wifi ifname "$IFACE" con-name "$MODEM" ssid "$ssid" autoconnect yes
    connection.autoconnect-priority 50 connection.autoconnect-retries 0)
  [[ -n $pass ]] && args+=(wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$pass")
  if [[ -n $ip ]]; then
    [[ $ip == */* ]] || ip+=/24
    [[ -n $gw ]] || gw=${ip%.*}.1   # 192.168.8.50/24 -> шлюз 192.168.8.1
    args+=(ipv4.method manual ipv4.addresses "$ip" ipv4.gateway "$gw" ipv4.dns "$gw")
  fi
  nmcli con delete "$MODEM" >/dev/null 2>&1 || true
  nmcli con add "${args[@]}" >/dev/null
  nmcli con modify "$HOTSPOT" connection.autoconnect no >/dev/null 2>&1 || true

  local port=8080
  [[ -f $CONF ]] && port=$(. "$CONF"; echo "${PORT:-8080}")
  echo "Профиль «$ssid» сохранён: Pi будет подключаться к нему при каждой загрузке."
  echo "Адрес Pi для интерфейса: $(hostname).local:$port${ip:+  или  ${ip%/*}:$port}"
  detached "nmcli con down $HOTSPOT >/dev/null 2>&1; sleep 1; nmcli dev wifi rescan ifname $IFACE >/dev/null 2>&1; sleep 3
    if nmcli --wait 20 con up $MODEM; then nmcli -g IP4.ADDRESS dev show $IFACE
    else echo '! Сейчас сеть не видна. Pi подключится сама, когда модем включится.'; fi"
}

show_urls() {
  local port=8080
  [[ -f $CONF ]] && port=$(. "$CONF"; echo "${PORT:-8080}")
  echo "Поток камеры (вводить в интерфейсе, Source -> Pi cam):"
  echo "  $(hostname).local:$port"
  local ip
  for ip in $(hostname -I); do [[ $ip == *.* ]] && echo "  $ip:$port"; done
  echo "Проверка в браузере: http://$(hostname).local:$port/stream"
}

cmd_status() {
  echo "== камера"; (lsusb | grep -i -E "logitech|046d") || echo "Logitech не найдена в lsusb"
  [[ -f $CONF ]] && { . "$CONF"; v4l2-ctl -d "$DEVICE" --list-formats-ext 2>/dev/null | grep -E "MJPG|Size" | head -12 || true; }
  echo "== сервис"; systemctl is-active webcam-stream 2>/dev/null || true
  echo "== сеть"; nmcli -t -f NAME,TYPE,DEVICE con show --active 2>/dev/null || ip -br addr
  show_urls
}

case ${1:-} in
  install) cmd_install ;;
  hotspot) shift; cmd_hotspot "$@" ;;
  wifi) shift; cmd_wifi "$@" ;;
  status) cmd_status ;;
  *) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
