# CHOTU simulation (Gazebo Fortress)

CHOTU is simulated in **Gazebo Fortress** with the same ROS 2 Humble stack that runs on the Raspberry Pi 4. Only the hardware bridge differs: `gz_sensor_adapter_node` replaces `serial_bridge_node` and publishes the same topics.

| Path | What |
|---|---|
| [`gazebo_recording/`](gazebo_recording/) | Headless recorder, 7 flow-wise screenshots, the full 229.7 s mission video and its metrics |
| `../ros2_ws/src/chotu_gazebo/worlds/atomquest_room.sdf` | 10 × 10 ft AtomQuest room, obstacles, dock and overhead camera |
| `../ros2_ws/src/chotu_bringup/launch/sim.launch.py` | Gazebo + bridge + mission manager + rosbridge |

To run it interactively with RViz: `docker compose -f docker/docker-compose.yml --profile sim up` (see `docs/SETUP.md` §B).
