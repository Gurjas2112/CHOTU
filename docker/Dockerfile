# syntax=docker/dockerfile:1.7
# =============================================================================
# CHOTU - multi-stage ROS 2 image (dev / build / runtime / perception)
#
# Follows "The Complete Guide to Docker for ROS 2 (2026 Edition)":
#   * official ROS images as the base, ROS distro as a build ARG
#   * dependency layer (package.xml + rosdep) cached separately from sources
#   * heavy dev image (desktop, Gazebo, gdb) separated from a slim runtime image
#   * non-root user, explicit device access at run time (no --privileged)
#   * images are tagged with versions, never just :latest (see docker-compose.yml)
#
#   docker build -f docker/Dockerfile --target dev     -t chotu/dev:2.0.0 .
#   docker build -f docker/Dockerfile --target runtime -t chotu/runtime:2.0.0 .
#   docker buildx build -f docker/Dockerfile --target runtime \
#       --platform linux/arm64 -t <registry>/chotu/runtime:2.0.0 --push .   # Raspberry Pi 4
# =============================================================================
ARG ROS_DISTRO=humble

# ----------------------------------------------------------------------------- base
FROM ros:${ROS_DISTRO}-ros-base AS base
ARG ROS_DISTRO
ENV ROS_DISTRO=${ROS_DISTRO} \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
SHELL ["/bin/bash", "-c"]
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-pip python3-numpy python3-serial python3-opencv python3-pytest \
        ros-${ROS_DISTRO}-rmw-cyclonedds-cpp \
        ros-${ROS_DISTRO}-xacro ros-${ROS_DISTRO}-robot-state-publisher \
        ros-${ROS_DISTRO}-tf2-ros ros-${ROS_DISTRO}-cv-bridge ros-${ROS_DISTRO}-v4l2-camera \
    && rm -rf /var/lib/apt/lists/*
# chotu_core: the hardware-independent autonomy library shared with the simulator
WORKDIR /opt/chotu/src
COPY pyproject.toml README.md ./
COPY chotu_core ./chotu_core
RUN pip3 install --no-cache-dir .

# ----------------------------------------------------------------------------- deps
FROM base AS deps
WORKDIR /ws
# only package manifests -> this layer is re-used until a dependency changes
COPY ros2_ws/src/chotu_interfaces/package.xml src/chotu_interfaces/package.xml
COPY ros2_ws/src/chotu_description/package.xml src/chotu_description/package.xml
COPY ros2_ws/src/chotu_base/package.xml src/chotu_base/package.xml
COPY ros2_ws/src/chotu_perception/package.xml src/chotu_perception/package.xml
COPY ros2_ws/src/chotu_navigation/package.xml src/chotu_navigation/package.xml
COPY ros2_ws/src/chotu_bringup/package.xml src/chotu_bringup/package.xml
COPY ros2_ws/src/chotu_gazebo/package.xml src/chotu_gazebo/package.xml
RUN apt-get update && rosdep update --rosdistro ${ROS_DISTRO} \
    && rosdep install --from-paths src --ignore-src -y --rosdistro ${ROS_DISTRO} \
    && rm -rf /var/lib/apt/lists/*

# ----------------------------------------------------------------------------- build
FROM deps AS build
COPY ros2_ws/src /ws/src
RUN source /opt/ros/${ROS_DISTRO}/setup.bash \
    && colcon build --merge-install --install-base /opt/chotu/install \
         --cmake-args -DCMAKE_BUILD_TYPE=Release \
    && colcon test --merge-install --install-base /opt/chotu/install --packages-select chotu_base \
    && colcon test-result --verbose

# ----------------------------------------------------------------------------- runtime (robot)
FROM deps AS runtime
COPY --from=build /opt/chotu/install /opt/chotu/install
COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/cyclonedds.xml /opt/chotu/cyclonedds.xml
ENV CYCLONEDDS_URI=file:///opt/chotu/cyclonedds.xml
RUN chmod +x /entrypoint.sh \
    && useradd -m -s /bin/bash -G dialout,video chotu \
    && mkdir -p /opt/chotu/models && chown -R chotu /opt/chotu/models
USER chotu
WORKDIR /home/chotu
ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "chotu_bringup", "robot.launch.py"]

# ----------------------------------------------------------------------------- perception (YOLOv8n)
FROM runtime AS perception
USER root
# CPU wheels on the Pi (arm64); CUDA wheels on x86_64 - run with --gpus all on the RTX 3060
RUN pip3 install --no-cache-dir "ultralytics==8.3.40"
USER chotu
CMD ["ros2", "run", "chotu_perception", "yolo_detector_node", "--ros-args", "--params-file", \
     "/opt/chotu/install/share/chotu_bringup/config/chotu_params.yaml"]

# ----------------------------------------------------------------------------- dev (workstation)
FROM osrf/ros:${ROS_DISTRO}-desktop AS dev
ARG ROS_DISTRO
ENV ROS_DISTRO=${ROS_DISTRO} DEBIAN_FRONTEND=noninteractive RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
SHELL ["/bin/bash", "-c"]
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-pip python3-colcon-common-extensions python3-rosdep python3-serial python3-opencv \
        python3-pytest gdb git vim less \
        ros-${ROS_DISTRO}-rmw-cyclonedds-cpp ros-${ROS_DISTRO}-ros-gz \
        ros-${ROS_DISTRO}-xacro ros-${ROS_DISTRO}-cv-bridge ros-${ROS_DISTRO}-v4l2-camera \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md /opt/chotu/src/
COPY chotu_core /opt/chotu/src/chotu_core
RUN pip3 install --no-cache-dir -e /opt/chotu/src matplotlib
WORKDIR /workspace
# live-edit chotu_core from the bind-mounted repo instead of the baked copy
ENV PYTHONPATH=/workspace
RUN echo "source /opt/ros/${ROS_DISTRO}/setup.bash" >> /root/.bashrc \
    && echo "[ -f /workspace/ros2_ws/install/setup.bash ] && source /workspace/ros2_ws/install/setup.bash" >> /root/.bashrc
CMD ["bash"]
