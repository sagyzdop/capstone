// mlx_stream.cpp — читает MLX90640 на Raspberry Pi и шлёт кадры температур по UDP.
//
// Сборка (на Pi, из любой папки; клонирует pimoroni/mlx90640-library и собирает):
//   bash raspberry/build_mlx_stream.sh
// Запуск:
//   ./mlx_stream <IP_ноутбука> [порт=5005] [частота_Гц=64]
//
// Формат пакета (little-endian), 3096 байт:
//   uint32 magic = 0x3039584D ("MX90")
//   uint32 frame_id      — счётчик кадров (по нему видно потери)
//   uint64 timestamp_us  — время снятия кадра на Pi, мкс
//   float  ta            — температура самого датчика, °C
//   float  reserved
//   float  temps[768]    — 24 строки × 32 столбца, °C

#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <chrono>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>
#include "headers/MLX90640_API.h"

#define MLX_ADDR 0x33
#define TA_SHIFT 8.0f      // рекомендация Melexis для работы на открытом воздухе
#define EMISSIVITY 0.95f

#pragma pack(push, 1)
struct Packet {
    uint32_t magic;
    uint32_t frame_id;
    uint64_t timestamp_us;
    float ta;
    float reserved;
    float temps[768];
};
#pragma pack(pop)

static uint8_t rate_code(int hz) {
    switch (hz) {
        case 1: return 0b001;  case 2: return 0b010;  case 4: return 0b011;
        case 8: return 0b100;  case 16: return 0b101; case 32: return 0b110;
        case 64: return 0b111;
        default: return 0;
    }
}

static uint64_t now_us() {
    using namespace std::chrono;
    return duration_cast<microseconds>(steady_clock::now().time_since_epoch()).count();
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Использование: %s <IP_ноутбука> [порт=5005] [частота_Гц=64]\n", argv[0]);
        return 1;
    }
    const char *dst_ip = argv[1];
    int port = argc > 2 ? atoi(argv[2]) : 5005;
    int hz   = argc > 3 ? atoi(argv[3]) : 64;
    uint8_t code = rate_code(hz);
    if (!code) { fprintf(stderr, "Частота должна быть 1,2,4,8,16,32 или 64\n"); return 1; }

    // --- UDP-сокет ---
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) { perror("socket"); return 1; }
    sockaddr_in dst{};
    dst.sin_family = AF_INET;
    dst.sin_port = htons(port);
    if (inet_pton(AF_INET, dst_ip, &dst.sin_addr) != 1) {
        fprintf(stderr, "Неверный IP: %s\n", dst_ip); return 1;
    }

    // --- Настройка датчика ---
    static uint16_t ee[832];
    static uint16_t frame[834];
    static paramsMLX90640 params;
    static Packet pkt;

    MLX90640_SetDeviceMode(MLX_ADDR, 0);       // непрерывный режим
    MLX90640_SetSubPageRepeat(MLX_ADDR, 0);
    MLX90640_SetRefreshRate(MLX_ADDR, code);
    MLX90640_SetChessMode(MLX_ADDR);           // «шахматный» режим (по умолчанию у датчика)

    if (MLX90640_DumpEE(MLX_ADDR, ee) != 0) {
        fprintf(stderr, "Не удалось прочитать EEPROM. Проверьте провода и `i2cdetect -y 1`.\n");
        return 1;
    }
    if (MLX90640_ExtractParameters(ee, &params) != 0) {
        fprintf(stderr, "Ошибка разбора калибровочных параметров.\n");
        return 1;
    }

    fprintf(stderr, "Датчик настроен: %d Гц (подкадры) → до %d полных кадров/с. Шлю на %s:%d\n",
            hz, hz / 2, dst_ip, port);

    pkt.magic = 0x3039584D;
    uint32_t frame_id = 0;
    int sent_in_sec = 0, errors = 0, consecutive = 0;
    uint64_t sec_start = now_us();

    while (true) {
        // Ждёт готовности подкадра и читает его (832 слова + служебные)
        int subpage = MLX90640_GetFrameData(MLX_ADDR, frame);
        if (subpage < 0) {
            errors++;
            if (++consecutive > 50) { fprintf(stderr, "\n50 ошибок I2C подряд, выход.\n"); return 1; }
            continue;
        }
        consecutive = 0;

        float ta = MLX90640_GetTa(frame, &params);
        // Обновляет в pkt.temps только пиксели текущего подкадра (половину «шахматки»)
        MLX90640_CalculateTo(frame, &params, EMISSIVITY, ta - TA_SHIFT, pkt.temps);
        MLX90640_BadPixelsCorrection(params.brokenPixels, pkt.temps, 1, &params);
        MLX90640_BadPixelsCorrection(params.outlierPixels, pkt.temps, 1, &params);

        // Полный кадр готов после подкадра 1 — отправляем
        if (subpage == 1) {
            pkt.frame_id = frame_id++;
            pkt.timestamp_us = now_us();
            pkt.ta = ta;
            sendto(sock, &pkt, sizeof(pkt), 0, (sockaddr *)&dst, sizeof(dst));
            sent_in_sec++;
        }

        uint64_t t = now_us();
        if (t - sec_start >= 1000000) {
            fprintf(stderr, "\rОтправлено: %2d кадров/с, Ta=%.1f°C, ошибок I2C: %d   ",
                    sent_in_sec, ta, errors);
            sent_in_sec = 0;
            sec_start = t;
        }
    }
}
