"""Publish CHOTU's URDF on /robot_description (+ optional RViz)."""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    share = get_package_share_directory("chotu_description")
    xacro_file = os.path.join(share, "urdf", "chotu.urdf.xacro")
    use_sim_time = LaunchConfiguration("use_sim_time")
    return LaunchDescription([
        DeclareLaunchArgument("use_sim_time", default_value="false"),
        DeclareLaunchArgument("rviz", default_value="false"),
        Node(package="robot_state_publisher", executable="robot_state_publisher",
             parameters=[{"robot_description": ParameterValue(Command(["xacro ", xacro_file]), value_type=str),
                          "use_sim_time": use_sim_time}]),
        Node(package="rviz2", executable="rviz2", arguments=["-d", os.path.join(share, "rviz", "chotu.rviz")],
             condition=IfCondition(LaunchConfiguration("rviz")),
             parameters=[{"use_sim_time": use_sim_time}]),
    ])
