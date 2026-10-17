# Mission telemetry published by chotu_navigation/mission_manager_node at 5 Hz
std_msgs/Header header
string state                 # IDLE UNDOCK SCAN COVER SPOT_CLEAN STUCK_RECOVERY RETURN_TO_DOCK DOCKING DOCKED
float32 elapsed_s
float32 time_left_s
float32 coverage_estimate    # 0..1, robot's own swept-area estimate
uint32 waypoints_total
uint32 waypoints_done
uint32 waypoints_skipped
uint32 recoveries
uint32 replans
float32 suction_duty         # 0..1
string suction_mode          # OFF ECO BOOST
string safety                # clear slow blocked bump cliff
float32 battery_soc
string last_event
