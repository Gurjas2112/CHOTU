#!/usr/bin/env bash
# Source ROS 2 + the CHOTU overlay, then run the requested command.
set -e
source "/opt/ros/${ROS_DISTRO}/setup.bash"
if [ -f /opt/chotu/install/setup.bash ]; then
  source /opt/chotu/install/setup.bash
fi
exec "$@"
