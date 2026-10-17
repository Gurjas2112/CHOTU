import 'dart:convert';

import '../models.dart';

/// Pure builders/parsers for the rosbridge v2 JSON protocol used by the robot
/// (rosbridge_server on the Raspberry Pi, ws://<robot>:9090). Kept free of I/O
/// so they are unit-tested in test/rosbridge_protocol_test.dart.
class RosbridgeProtocol {
  static String subscribe(String topic, String type, {int throttleMs = 0}) => jsonEncode({
        'op': 'subscribe',
        'topic': topic,
        'type': type,
        if (throttleMs > 0) 'throttle_rate': throttleMs,
      });

  static String callService(String service, String type, Map<String, dynamic> args, String id) => jsonEncode({
        'op': 'call_service',
        'service': service,
        'type': type,
        'args': args,
        'id': id,
      });

  /// abort=false starts a mission; abort=true ends it and sends CHOTU home to the dock.
  static String startMission(String id, {bool returnToDock = false}) => callService(
      '/chotu/start_mission', 'chotu_interfaces/srv/StartMission', {'abort': returnToDock, 'time_budget_s': 0.0}, id);

  static String setZones(String id, List<Zone> zones) => callService(
      '/chotu/set_zones', 'chotu_interfaces/srv/SetZones', {'no_go': zones.map((z) => z.toRos()).toList()}, id);

  /// chotu_interfaces/msg/CleaningStatus -> RobotStatus (keeps app-only fields from [prev]).
  static RobotStatus parseStatus(Map<String, dynamic> m, RobotStatus prev) => prev.copyWith(
        state: missionStateFromRos((m['state'] ?? 'IDLE') as String),
        elapsed: (m['elapsed_s'] as num?)?.toDouble(),
        timeLeft: (m['time_left_s'] as num?)?.toDouble(),
        coverage: (m['coverage_estimate'] as num?)?.toDouble(),
        battery: (m['battery_soc'] as num?)?.toDouble(),
        suctionMode: m['suction_mode'] as String?,
        suctionDuty: (m['suction_duty'] as num?)?.toDouble(),
        safety: m['safety'] as String?,
        lastEvent: m['last_event'] as String?,
        connected: true,
      );
}
