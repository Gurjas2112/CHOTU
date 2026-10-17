#!/usr/bin/env bash
# Native ROS 2 Humble install for WSL2 Ubuntu 22.04 (alternative to Docker).
#   wsl -d Ubuntu -- bash scripts/setup_wsl_ros2_humble.sh
# Then:  cd ros2_ws && colcon build --symlink-install && source install/setup.bash
set -euo pipefail

if [ "$(lsb_release -cs)" != "jammy" ]; then
  echo "ROS 2 Humble binaries need Ubuntu 22.04 (jammy)"; exit 1
fi

sudo apt-get update
sudo apt-get install -y software-properties-common curl gnupg lsb-release locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
sudo add-apt-repository -y universe
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

sudo apt-get update
sudo apt-get install -y ros-humble-desktop ros-humble-ros-gz ros-humble-xacro \
  ros-humble-rmw-cyclonedds-cpp ros-humble-cv-bridge ros-humble-v4l2-camera \
  python3-colcon-common-extensions python3-rosdep python3-pip python3-serial

sudo rosdep init 2>/dev/null || true
rosdep update

REPO="$(cd "$(dirname "$0")/.." && pwd)"
pip3 install --user -e "$REPO"
grep -q "source /opt/ros/humble/setup.bash" ~/.bashrc || echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
grep -q "RMW_IMPLEMENTATION" ~/.bashrc || echo "export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp" >> ~/.bashrc

cd "$REPO/ros2_ws"
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -y
colcon build --symlink-install
echo "Done. Try:  source ros2_ws/install/setup.bash && ros2 launch chotu_bringup sim.launch.py"
