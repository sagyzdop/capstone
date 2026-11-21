#!/usr/bin/env bash
# Builds ./mlx_stream on the Raspberry Pi. Works from any folder:
#   bash raspberry/build_mlx_stream.sh
set -euo pipefail
cd "$(dirname "$0")"
[ -d mlx90640-library ] || git clone https://github.com/pimoroni/mlx90640-library.git
sudo apt-get install -y libi2c-dev
make -C mlx90640-library libMLX90640_API.a I2C_MODE=LINUX   # library only, skips the demos that need libav/SDL
g++ -O2 -std=c++11 -Imlx90640-library mlx_stream.cpp mlx90640-library/libMLX90640_API.a -o mlx_stream
echo "built: $(pwd)/mlx_stream"
