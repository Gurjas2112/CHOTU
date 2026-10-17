import 'package:flutter/material.dart';

import '../models.dart';

/// What the UI needs from a CHOTU robot. Two sources implement it:
///  * [RosbridgeRobotRepository] - the real robot (rosbridge on the Pi 4)
///  * [DemoRobotRepository]      - synthetic demo data (used for this prototype,
///                                 no hardware has been bought yet)
abstract class RobotRepository extends ChangeNotifier {
  RobotRepository(this.robotName, this.endpoint);

  final String robotName;
  final String endpoint;

  RobotStatus status = const RobotStatus();
  MapSnapshot? map;
  final List<RobotAlert> alerts = [];
  final List<MissionReport> history = [];
  final List<CleaningSchedule> schedules = [
    CleaningSchedule(const TimeOfDay(hour: 10, minute: 30), {1, 3, 5}),
  ];
  List<Zone> noGoZones = [];

  bool get isDemo;

  Future<void> connect();
  void disconnect();
  Future<void> startCleaning();
  Future<void> returnToDock();
  Future<void> applyNoGoZones(List<Zone> zones);

  // ---- app-side state shared by both sources
  int get unresolvedAlerts => alerts.where((a) => !a.resolved).length;

  void pushAlert(RobotAlert a) {
    alerts.insert(0, a);
    notifyListeners();
  }

  void resolveAlert(String id) {
    for (final a in alerts) {
      if (a.id == id) a.resolved = true;
    }
    notifyListeners();
  }

  void addSchedule(CleaningSchedule s) {
    schedules.add(s);
    notifyListeners();
  }

  void toggleSchedule(CleaningSchedule s, bool on) {
    s.enabled = on;
    notifyListeners();
  }

  void removeSchedule(CleaningSchedule s) {
    schedules.remove(s);
    notifyListeners();
  }
}
