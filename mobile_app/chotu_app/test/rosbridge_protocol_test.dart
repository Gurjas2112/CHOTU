import 'dart:convert';

import 'package:chotu_app/data/rosbridge_protocol.dart';
import 'package:chotu_app/models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('start / return-to-dock map onto /chotu/start_mission', () {
    final start = jsonDecode(RosbridgeProtocol.startMission('s1')) as Map<String, dynamic>;
    expect(start['op'], 'call_service');
    expect(start['service'], '/chotu/start_mission');
    expect(start['type'], 'chotu_interfaces/srv/StartMission');
    expect(start['args']['abort'], false);
    final dock = jsonDecode(RosbridgeProtocol.startMission('d1', returnToDock: true)) as Map<String, dynamic>;
    expect(dock['args']['abort'], true);
  });

  test('no-go zones use chotu_interfaces/srv/SetZones field names', () {
    final m = jsonDecode(RosbridgeProtocol.setZones('z1', [Zone(2, 2, 1, 1)])) as Map<String, dynamic>;
    expect(m['service'], '/chotu/set_zones');
    expect(m['args']['no_go'][0], {'x_min': 1.0, 'y_min': 1.0, 'x_max': 2.0, 'y_max': 2.0});
  });

  test('CleaningStatus parsing', () {
    final s = RosbridgeProtocol.parseStatus({
      'state': 'RETURN_TO_DOCK',
      'elapsed_s': 270.5,
      'time_left_s': 29.5,
      'coverage_estimate': 0.73,
      'battery_soc': 0.97,
      'suction_mode': 'ECO',
      'suction_duty': 0.55,
      'safety': 'clear',
      'last_event': 'Returning to dock (time budget)',
    }, const RobotStatus());
    expect(s.state, MissionState.returnToDock);
    expect(s.coverage, 0.73);
    expect(s.connected, isTrue);
    expect(s.binFill, const RobotStatus().binFill); // app-side field kept
  });

  test('subscribe adds throttle only when requested', () {
    expect(jsonDecode(RosbridgeProtocol.subscribe('/odom', 'nav_msgs/msg/Odometry')).containsKey('throttle_rate'),
        isFalse);
    expect(jsonDecode(RosbridgeProtocol.subscribe('/odom', 'nav_msgs/msg/Odometry', throttleMs: 100))['throttle_rate'],
        100);
  });
}
