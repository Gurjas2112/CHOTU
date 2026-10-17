#!/usr/bin/env bash
# Build + test the ROS 2 workspace inside the versioned dev container.
#   bash scripts/build_ros_docker.sh
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -f docker/docker-compose.yml --profile dev build dev
docker compose -f docker/docker-compose.yml --profile dev run --rm dev bash -c "
  source /opt/ros/humble/setup.bash &&
  cd /workspace/ros2_ws &&
  rosdep update && rosdep install --from-paths src --ignore-src -y &&
  colcon build --symlink-install &&
  colcon test --packages-select chotu_base && colcon test-result --verbose"
