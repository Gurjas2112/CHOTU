#!/usr/bin/env bash
# Build + flash the ESP32-S3 base controller with PlatformIO.
#   bash scripts/flash_esp32.sh                 # auto-detect port
#   bash scripts/flash_esp32.sh /dev/ttyUSB0    # Linux / Pi
#   bash scripts/flash_esp32.sh COM5            # Windows (Git Bash)
set -euo pipefail
cd "$(dirname "$0")/../firmware/esp32s3_base_controller"
command -v pio >/dev/null || { echo "Install PlatformIO first:  pip install platformio"; exit 1; }
pio run -e esp32s3
if [ $# -ge 1 ]; then
  pio run -e esp32s3 -t upload --upload-port "$1"
else
  pio run -e esp32s3 -t upload
fi
echo "Flashed. Keep the robot still on the dock for ~1 s at power-on (gyro calibration)."
