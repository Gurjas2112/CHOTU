"""Real robot bring-up on the Raspberry Pi 4.

    ros2 launch chotu_bringup robot.launch.py                 # base + mission + vision
    ros2 launch chotu_bringup robot.launch.py vision:=false   # without YOLO
    ros2 service call /chotu/start_mission chotu_interfaces/srv/StartMission "{abort: false}"
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    params = os.path.join(get_package_share_directory("chotu_bringup"), "config", "chotu_params.yaml")
    desc = os.path.join(get_package_share_directory("chotu_description"), "launch", "description.launch.py")
    auto_start = ParameterValue(LaunchConfiguration("auto_start"), value_type=bool)
    return LaunchDescription([
        # rosbridge = the robot's app API (Flutter app connects to ws://<pi>:9090)
        Node(package="rosbridge_server", executable="rosbridge_websocket", name="rosbridge",
             output="screen"),
        DeclareLaunchArgument("port", default_value="/dev/ttyUSB0"),
        DeclareLaunchArgument("vision", default_value="true"),
        DeclareLaunchArgument("auto_start", default_value="false"),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(desc)),
        Node(package="chotu_base", executable="serial_bridge_node", name="chotu_serial_bridge",
             parameters=[params, {"port": LaunchConfiguration("port")}], output="screen"),
        Node(package="chotu_navigation", executable="mission_manager_node", name="chotu_mission_manager",
             parameters=[params, {"auto_start": auto_start}], output="screen"),
        Node(package="chotu_perception", executable="yolo_detector_node", name="chotu_yolo_detector",
             parameters=[params], output="screen", condition=IfCondition(LaunchConfiguration("vision"))),
        Node(package="v4l2_camera", executable="v4l2_camera_node", name="camera",
             parameters=[{"image_size": [640, 480], "video_device": "/dev/video0"}],
             remappings=[("image_raw", "camera/image_raw")],
             condition=IfCondition(LaunchConfiguration("vision"))),
    ])
