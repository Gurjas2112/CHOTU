"""Gazebo (Fortress) simulation of the AtomQuest challenge room.

    ros2 launch chotu_bringup sim.launch.py            # gz + bridge + mission (auto start)
    ros2 launch chotu_bringup sim.launch.py rviz:=true vision:=false
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    bringup = get_package_share_directory("chotu_bringup")
    params = os.path.join(bringup, "config", "chotu_params.yaml")
    world = os.path.join(get_package_share_directory("chotu_gazebo"), "worlds", "atomquest_room.sdf")
    desc = os.path.join(get_package_share_directory("chotu_description"), "launch", "description.launch.py")
    gz = os.path.join(get_package_share_directory("ros_gz_sim"), "launch", "gz_sim.launch.py")
    sim_time = {"use_sim_time": True}
    return LaunchDescription([
        DeclareLaunchArgument("rviz", default_value="false"),
        DeclareLaunchArgument("vision", default_value="true"),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(gz),
                                 launch_arguments={"gz_args": f"-r {world}"}.items()),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(desc),
                                 launch_arguments={"use_sim_time": "true",
                                                   "rviz": LaunchConfiguration("rviz")}.items()),
        Node(package="ros_gz_sim", executable="create", output="screen",
             arguments=["-topic", "robot_description", "-name", "chotu",
                        "-x", "1.524", "-y", "0.19", "-z", "0.02", "-Y", "1.5708"]),
        Node(package="ros_gz_bridge", executable="parameter_bridge", output="screen",
             parameters=[{"config_file": os.path.join(bringup, "config", "gz_bridge.yaml")}]),
        Node(package="chotu_base", executable="gz_sensor_adapter_node", parameters=[sim_time], output="screen"),
        Node(package="chotu_perception", executable="yolo_detector_node", name="chotu_yolo_detector",
             parameters=[params, sim_time], output="screen", condition=IfCondition(LaunchConfiguration("vision"))),
        TimerAction(period=5.0, actions=[
            Node(package="chotu_navigation", executable="mission_manager_node", name="chotu_mission_manager",
                 parameters=[params, sim_time, {"auto_start": True}], output="screen")]),
    ])
