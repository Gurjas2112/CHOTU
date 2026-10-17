#!/usr/bin/env bash
# Record a full CHOTU mission in Gazebo Fortress, headless (Xvfb + Mesa llvmpipe).
#
# From the repo root on the host (Windows Git Bash / Linux):
#   docker build -f docker/Dockerfile --target dev -t chotu/dev:3.0.0 .
#   MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W 2>/dev/null || pwd)":/workspace \
#       chotu/dev:3.0.0 bash /workspace/bot_simulation/gazebo_recording/run_gazebo_recording.sh
set -eo pipefail
OUT=/workspace/bot_simulation/gazebo_recording
source /opt/ros/humble/setup.bash
cd /workspace/ros2_ws
colcon build --build-base /tmp/build --install-base /tmp/install > /tmp/colcon.log 2>&1 \
  || { tail -40 /tmp/colcon.log; exit 1; }
source /tmp/install/setup.bash
export LIBGL_ALWAYS_SOFTWARE=1 PYTHONPATH=/workspace:${PYTHONPATH}

xvfb-run -a -s "-screen 0 1280x720x24" ros2 launch chotu_bringup sim.launch.py > /tmp/sim.log 2>&1 &
SIM_PID=$!
trap 'kill ${SIM_PID} 2>/dev/null || true; pkill -f "ign gazebo" || true' EXIT
python3 "${OUT}/record_gazebo.py" --out "${OUT}"
echo "--- last sim log lines"
grep -E "Mission|DOCK|ERROR" /tmp/sim.log | tail -15 || true
