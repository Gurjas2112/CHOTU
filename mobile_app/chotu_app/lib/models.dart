import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';

/// Mirrors chotu_core.mission_fsm.MissionState (the strings come from /chotu/status).
enum MissionState { idle, undock, scan, cover, spotClean, stuckRecovery, returnToDock, docking, docked, aborted }

MissionState missionStateFromRos(String s) {
  switch (s) {
    case 'UNDOCK':
      return MissionState.undock;
    case 'SCAN':
      return MissionState.scan;
    case 'COVER':
      return MissionState.cover;
    case 'SPOT_CLEAN':
      return MissionState.spotClean;
    case 'STUCK_RECOVERY':
      return MissionState.stuckRecovery;
    case 'RETURN_TO_DOCK':
      return MissionState.returnToDock;
    case 'DOCKING':
      return MissionState.docking;
    case 'DOCKED':
      return MissionState.docked;
    case 'ABORTED':
      return MissionState.aborted;
    default:
      return MissionState.idle;
  }
}

extension MissionStateUi on MissionState {
  String get label => const {
        MissionState.idle: 'Ready on dock',
        MissionState.undock: 'Undocking',
        MissionState.scan: 'Mapping the room',
        MissionState.cover: 'Cleaning',
        MissionState.spotClean: 'Spot cleaning',
        MissionState.stuckRecovery: 'Freeing itself',
        MissionState.returnToDock: 'Returning to dock',
        MissionState.docking: 'Docking',
        MissionState.docked: 'Docked - mission done',
        MissionState.aborted: 'Stopped',
      }[this]!;

  bool get isActive => this != MissionState.idle && this != MissionState.docked && this != MissionState.aborted;
}

class RobotStatus {
  const RobotStatus({
    this.state = MissionState.idle,
    this.elapsed = 0,
    this.timeLeft = 300,
    this.coverage = 0,
    this.battery = 1,
    this.binFill,
    this.brushHealth,
    this.suctionMode = 'OFF',
    this.suctionDuty = 0,
    this.safety = 'clear',
    this.lastEvent = '',
    this.connected = false,
  });

  final MissionState state;
  final double elapsed;
  final double timeLeft;
  final double coverage;
  final double battery;
  /// Not reported by the robot's CleaningStatus (no bin-level or brush-wear sensor yet):
  /// null = not measured. Only the demo robot fills these in.
  final double? binFill;
  final double? brushHealth;
  final String suctionMode;
  final double suctionDuty;
  final String safety;
  final String lastEvent;
  final bool connected;

  RobotStatus copyWith({
    MissionState? state,
    double? elapsed,
    double? timeLeft,
    double? coverage,
    double? battery,
    double? binFill,
    double? brushHealth,
    String? suctionMode,
    double? suctionDuty,
    String? safety,
    String? lastEvent,
    bool? connected,
  }) =>
      RobotStatus(
        state: state ?? this.state,
        elapsed: elapsed ?? this.elapsed,
        timeLeft: timeLeft ?? this.timeLeft,
        coverage: coverage ?? this.coverage,
        battery: battery ?? this.battery,
        binFill: binFill ?? this.binFill,
        brushHealth: brushHealth ?? this.brushHealth,
        suctionMode: suctionMode ?? this.suctionMode,
        suctionDuty: suctionDuty ?? this.suctionDuty,
        safety: safety ?? this.safety,
        lastEvent: lastEvent ?? this.lastEvent,
        connected: connected ?? this.connected,
      );
}

class Pose {
  const Pose(this.x, this.y, this.theta);
  final double x, y, theta;
}

/// Axis-aligned no-go rectangle in room metres (chotu_interfaces/msg/Zone).
class Zone {
  Zone(double ax, double ay, double bx, double by)
      : x0 = math.min(ax, bx),
        y0 = math.min(ay, by),
        x1 = math.max(ax, bx),
        y1 = math.max(ay, by);

  final double x0, y0, x1, y1;

  bool contains(double x, double y, [double margin = 0]) =>
      x >= x0 - margin && x <= x1 + margin && y >= y0 - margin && y <= y1 + margin;

  double get area => (x1 - x0) * (y1 - y0);

  Map<String, double> toRos() => {'x_min': x0, 'y_min': y0, 'x_max': x1, 'y_max': y1};
}

/// Obstacle footprint known to the app (from /map or the demo world).
class Obstacle {
  const Obstacle.rect(this.rect, this.label)
      : center = null,
        radius = 0;
  const Obstacle.circle(Offset c, this.radius, this.label)
      : center = c,
        rect = null;

  final Rect? rect;
  final Offset? center;
  final double radius;
  final String label;

  bool contains(double x, double y, double margin) {
    if (rect != null) return rect!.inflate(margin).contains(Offset(x, y));
    return (Offset(x, y) - center!).distance <= radius + margin;
  }
}

class MapSnapshot {
  MapSnapshot({
    required this.width,
    required this.height,
    required this.res,
    required this.covered,
    required this.trail,
    required this.robot,
    required this.obstacles,
    required this.cable,
    required this.plan,
    required this.noGo,
    required this.dock,
  });

  final double width, height, res;
  final Uint8List covered; // 1 = swept, row-major, y-up
  final List<Offset> trail;
  final Pose? robot;
  final List<Obstacle> obstacles;
  final List<Offset> cable; // AI-vision "avoid" polyline
  final List<Offset> plan;
  final List<Zone> noGo;
  final Offset dock;

  int get nx => (width / res).ceil();
  int get ny => (height / res).ceil();
}

enum AlertLevel { info, warning, critical }

class RobotAlert {
  RobotAlert(this.id, this.title, this.body, this.level, this.time, {this.resolved = false});
  final String id, title, body;
  final AlertLevel level;
  final DateTime time;
  bool resolved;
}

class CleaningSchedule {
  CleaningSchedule(this.time, this.days, {this.enabled = true, this.label = 'Full room'});
  TimeOfDay time;
  Set<int> days; // 1 = Monday ... 7 = Sunday
  bool enabled;
  String label;
}

class MissionReport {
  MissionReport({
    required this.date,
    required this.durationS,
    required this.coverage,
    required this.debrisG,
    required this.energyWh,
    required this.docked,
    required this.rubric,
    this.noGoZones = 0,
  });

  final DateTime date;
  final double durationS, coverage, debrisG, energyWh;
  final bool docked;
  final Map<String, double> rubric; // AtomQuest criteria -> points
  final int noGoZones;

  double get score => rubric.values.fold(0.0, (a, b) => a + b);
}

/// AtomQuest 2025 rubric weights (chotu_core/scoring.py).
const rubricWeights = {
  'Completion time': 20.0,
  'Efficiency': 25.0,
  'Autonomy': 20.0,
  'Battery': 15.0,
  'Aesthetics': 5.0,
  'Bin removal': 10.0,
  'Cost': 5.0,
};
