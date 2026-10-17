import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../models.dart';
import 'robot_repository.dart';

/// Synthetic CHOTU for demos (no hardware). The room is the same AtomQuest
/// challenge room as ros2_ws/src/chotu_gazebo/worlds/atomquest_room.sdf and the
/// robot follows the same mission phases as chotu_core.CleaningMission:
/// undock -> 360 deg scan -> boustrophedon lanes with detours -> return -> dock.
class DemoRobotRepository extends RobotRepository {
  DemoRobotRepository() : super('CHOTU-01', 'demo://atomquest-room') {
    _seedHistory();
    _buildPath();
    _publishMap();
  }

  static const double room = 3.048;
  static const double res = 0.05;
  static const Offset dock = Offset(1.524, 0.0);
  static const Offset start = Offset(1.524, 0.19);
  static const double radius = 0.17;

  /// Simulated seconds per real second (the tour speeds the 5-minute mission up).
  double timeScale = 6.0;

  final List<Obstacle> obstacles = const [
    Obstacle.rect(Rect.fromLTRB(0.42, 1.77, 0.82, 2.07), 'box'),
    Obstacle.rect(Rect.fromLTRB(2.19, 0.82, 2.51, 1.08), 'box'),
    Obstacle.circle(Offset(0.55, 0.75), 0.13, 'bin'),
    Obstacle.rect(Rect.fromLTRB(1.88, 1.93, 2.32, 2.37), 'chair'),
  ];
  final List<Offset> cable = const [Offset(0.966, 2.447), Offset(1.30, 2.55), Offset(1.634, 2.653)];
  final List<Offset> hotspots = const [Offset(0.95, 1.30), Offset(2.0, 1.55), Offset(1.25, 0.70)];

  late Uint8List _covered;
  final List<Offset> _trail = [];
  List<Offset> _path = [];
  List<int> _lane = [];
  List<Offset> _returnPath = [];
  double _progress = 0; // metres along _path
  double _returnProgress = 0;
  double _t = 0;
  Pose _pose = const Pose(1.524, 0.19, math.pi / 2);
  Timer? _timer;
  static const int _tickMs = 50;
  bool _tangleRaised = false;
  bool _binRaised = false;
  double _stuckUntil = -1;

  @override
  bool get isDemo => true;

  // ------------------------------------------------------------------ world
  bool _blocked(double x, double y) {
    if (x < radius || y < radius || x > room - radius || y > room - radius) return true;
    for (final o in obstacles) {
      if (o.contains(x, y, radius + 0.02)) return true;
    }
    for (var i = 0; i + 1 < cable.length; i++) {
      if (_segDist(Offset(x, y), cable[i], cable[i + 1]) < radius) return true;
    }
    for (final z in noGoZones) {
      if (z.contains(x, y, radius)) return true;
    }
    return false;
  }

  static double _segDist(Offset p, Offset a, Offset b) {
    final ab = b - a;
    final t = (((p - a).dx * ab.dx + (p - a).dy * ab.dy) / ab.distanceSquared).clamp(0.0, 1.0);
    return (p - (a + ab * t)).distance;
  }

  Offset? _free(double x, double y, double prefer) {
    if (!_blocked(x, y)) return Offset(x, y);
    for (var d = 0.05; d <= 0.7; d += 0.05) {
      for (final s in [prefer, -prefer]) {
        if (!_blocked(x, y + s * d)) return Offset(x, y + s * d);
      }
    }
    return null;
  }

  void _buildPath() {
    final pts = <Offset>[];
    final lanes = <int>[];
    var k = 0;
    for (var y = 0.30; y <= room - 0.24; y += 0.22, k++) {
      final xs = <double>[];
      for (var x = 0.22; x <= room - 0.21; x += 0.03) {
        xs.add(x);
      }
      for (final x in (k.isEven ? xs : xs.reversed)) {
        final p = _free(x, y, 1.0);
        if (p != null) {
          pts.add(p);
          lanes.add(k);
        }
      }
    }
    _path = pts;
    _lane = lanes;
  }

  List<Offset> _plannedReturn(Offset from) {
    final out = <Offset>[];
    final target = Offset(start.dx, 0.45);
    final steps = ((target - from).distance / 0.03).ceil();
    for (var i = 1; i <= steps; i++) {
      final p = Offset.lerp(from, target, i / steps)!;
      final f = _free(p.dx, p.dy, -1.0);
      if (f != null) out.add(f);
    }
    out.add(start);
    return out;
  }

  double _len(List<Offset> pts, int upto) {
    var d = 0.0;
    for (var i = 1; i <= upto && i < pts.length; i++) {
      d += (pts[i] - pts[i - 1]).distance;
    }
    return d;
  }

  (Offset, double, int) _along(List<Offset> pts, double dist) {
    var acc = 0.0;
    for (var i = 1; i < pts.length; i++) {
      final seg = (pts[i] - pts[i - 1]).distance;
      if (acc + seg >= dist) {
        final p = Offset.lerp(pts[i - 1], pts[i], seg == 0 ? 0 : (dist - acc) / seg)!;
        final dir = pts[i] - pts[i - 1];
        return (p, math.atan2(dir.dy, dir.dx), i);
      }
      acc += seg;
    }
    final last = pts.isEmpty ? start : pts.last;
    return (last, _pose.theta, pts.length);
  }

  // ------------------------------------------------------------------ API
  @override
  Future<void> connect() async {
    await Future<void>.delayed(const Duration(milliseconds: 600));
    status = status.copyWith(
        connected: true, binFill: 0.12, brushHealth: 0.96, lastEvent: 'Connected to $robotName (demo data)');
    _timer ??= Timer.periodic(const Duration(milliseconds: _tickMs), (_) => _tick());
    notifyListeners();
  }

  @override
  void disconnect() {
    _timer?.cancel();
    _timer = null;
    status = status.copyWith(connected: false);
    notifyListeners();
  }

  @override
  Future<void> startCleaning() async {
    if (status.state.isActive) return;
    _t = 0;
    _progress = 0;
    _returnProgress = 0;
    _trail.clear();
    _covered = Uint8List((room / res).ceil() * (room / res).ceil());
    _rebuildFreeMask();
    _tangleRaised = _binRaised = false;
    _pose = Pose(start.dx, start.dy, math.pi / 2);
    status = status.copyWith(
        state: MissionState.undock, elapsed: 0, timeLeft: 300, coverage: 0, lastEvent: 'Mission start - undocking');
    notifyListeners();
  }

  @override
  Future<void> returnToDock() async {
    if (!status.state.isActive || status.state == MissionState.returnToDock) return;
    _returnPath = _plannedReturn(Offset(_pose.x, _pose.y));
    _returnProgress = 0;
    status = status.copyWith(state: MissionState.returnToDock, lastEvent: 'App: return to dock');
    notifyListeners();
  }

  @override
  Future<void> applyNoGoZones(List<Zone> zones) async {
    noGoZones = List.of(zones);
    _rebuildFreeMask();
    final lane = _currentLane();
    _buildPath();
    // resume on the same lane, nearest point
    var best = 0, bestD = 1e9;
    for (var i = 0; i < _path.length; i++) {
      if (_lane[i] < lane) continue;
      final d = (_path[i] - Offset(_pose.x, _pose.y)).distance;
      if (d < bestD) {
        bestD = d;
        best = i;
      }
      if (_lane[i] > lane) break;
    }
    _progress = _len(_path, best);
    status = status.copyWith(lastEvent: '${zones.length} no-go zone(s) applied - route re-planned');
    _publishMap();
    notifyListeners();
  }

  int _currentLane() {
    final (_, _, i) = _along(_path, _progress);
    return _lane.isEmpty ? 0 : _lane[math.min(i, _lane.length - 1)];
  }

  // ------------------------------------------------------------------ simulation
  void _tick() {
    // fixed step per timer tick: deterministic (and drivable by widget-test fake time)
    final dt = _tickMs / 1000.0 * timeScale;
    if (!status.state.isActive) return;
    _t += dt;
    var st = status.state;
    var suction = 'ECO', duty = 0.55;
    switch (st) {
      case MissionState.undock:
        final k = (_t / 3.0).clamp(0.0, 1.0);
        _pose = Pose(start.dx, start.dy + 0.26 * k, math.pi / 2);
        if (_t >= 3.0) {
          st = MissionState.scan;
          status = status.copyWith(lastEvent: '360 deg ToF/ultrasonic mapping scan');
        }
        suction = 'OFF';
        duty = 0;
      case MissionState.scan:
        _pose = Pose(_pose.x, _pose.y, math.pi / 2 + (_t - 3.0) * 1.4);
        if (_t >= 7.5) {
          st = MissionState.cover;
          status = status.copyWith(lastEvent: 'Boustrophedon coverage: ${_lane.isEmpty ? 0 : _lane.last + 1} lanes');
        }
        suction = 'OFF';
        duty = 0;
      case MissionState.stuckRecovery:
        if (_t >= _stuckUntil) {
          st = MissionState.cover;
          status = status.copyWith(lastEvent: 'Recovered - brush reversed, cleaning resumed');
        }
        suction = 'OFF';
        duty = 0;
      case MissionState.cover:
        _progress += 0.22 * dt;
        final (p, th, i) = _along(_path, _progress);
        _pose = Pose(p.dx, p.dy, th);
        if (hotspots.any((h) => (h - p).distance < 0.3)) {
          suction = 'BOOST';
          duty = 1.0;
        }
        if (!_tangleRaised && i > _path.length * 0.45) {
          _tangleRaised = true;
          st = MissionState.stuckRecovery;
          _stuckUntil = _t + 3.0;
          pushAlert(RobotAlert(
              'tangle',
              'Side brush tangle',
              'Hair wrapped the side brush - CHOTU reversed it '
                  'automatically. Check the brush after this run.',
              AlertLevel.warning,
              DateTime.now()));
          status = status.copyWith(lastEvent: 'Brush tangle - auto reverse');
        }
        if (i >= _path.length || _t >= 268) {
          st = MissionState.returnToDock;
          _returnPath = _plannedReturn(p);
          _returnProgress = 0;
          status =
              status.copyWith(lastEvent: _t >= 268 ? 'Returning to dock (time budget)' : 'Room complete - returning');
        }
      case MissionState.returnToDock:
        _returnProgress += 0.2 * dt;
        final (p, th, i) = _along([Offset(_pose.x, _pose.y), ..._returnPath], _returnProgress);
        _pose = Pose(p.dx, p.dy, th);
        _returnProgress = 0;
        _returnPath = _returnPath.sublist(math.min(math.max(i - 1, 0), _returnPath.length));
        if (_returnPath.isEmpty || (Offset(_pose.x, _pose.y) - start).distance < 0.03) {
          st = MissionState.docking;
          _stuckUntil = _t + 3.0;
          status = status.copyWith(lastEvent: 'IR beacon locked - docking');
        }
        suction = 'OFF';
        duty = 0;
      case MissionState.docking:
        _pose = Pose(start.dx, start.dy - 0.02 * ((_stuckUntil - _t) / 3.0).clamp(0.0, 1.0), -math.pi / 2);
        if (_t >= _stuckUntil) {
          st = MissionState.docked;
          _finishReport();
        }
        suction = 'OFF';
        duty = 0;
      default:
        break;
    }
    if (duty > 0) _markCovered(_pose.x, _pose.y);
    if (_trail.isEmpty || (_trail.last - Offset(_pose.x, _pose.y)).distance > 0.02) {
      _trail.add(Offset(_pose.x, _pose.y));
    }
    final cov = _coverage();
    if (!_binRaised && cov > 0.6) {
      _binRaised = true;
      pushAlert(RobotAlert(
          'bin',
          'Dust bin 70 % full',
          'Empty the bin after this run: lift the magnetic hatch, '
              'pull the bin straight up.',
          AlertLevel.info,
          DateTime.now()));
    }
    status = status.copyWith(
      state: st,
      elapsed: _t,
      timeLeft: math.max(0, 300 - _t),
      coverage: cov,
      battery: 1.0 - 0.034 * (_t / 284),
      binFill: 0.12 + 0.6 * cov,
      brushHealth: _tangleRaised ? 0.88 : 0.96,
      suctionMode: suction,
      suctionDuty: duty,
      safety: st == MissionState.stuckRecovery ? 'bump' : 'clear',
    );
    _publishMap();
    notifyListeners();
  }

  // Coverage bookkeeping is incremental: the free-cell mask is rebuilt only when
  // no-go zones change, and each newly swept free cell bumps a counter.
  Uint8List? _freeMask;
  int _freeCount = 0, _doneCount = 0;

  void _rebuildFreeMask() {
    final n = (room / res).ceil();
    final mask = Uint8List(n * n);
    var free = 0, done = 0;
    for (var iy = 0; iy < n; iy++) {
      for (var ix = 0; ix < n; ix++) {
        final x = (ix + 0.5) * res, y = (iy + 0.5) * res;
        if (x < 0.12 || y < 0.12 || x > room - 0.12 || y > room - 0.12) continue;
        if (obstacles.any((o) => o.contains(x, y, 0.0)) || noGoZones.any((z) => z.contains(x, y))) continue;
        mask[iy * n + ix] = 1;
        free++;
        if (_covered.length == n * n && _covered[iy * n + ix] == 1) done++;
      }
    }
    _freeMask = mask;
    _freeCount = free;
    _doneCount = done;
  }

  void _markCovered(double x, double y) {
    if (_freeMask == null) _rebuildFreeMask();
    final n = (room / res).ceil();
    final r = (0.12 / res).ceil();
    final cx = (x / res).floor(), cy = (y / res).floor();
    for (var dy = -r; dy <= r; dy++) {
      for (var dx = -r; dx <= r; dx++) {
        if (dx * dx + dy * dy > r * r) continue;
        final ix = cx + dx, iy = cy + dy;
        if (ix < 0 || iy < 0 || ix >= n || iy >= n) continue;
        final i = iy * n + ix;
        if (_covered[i] == 0) {
          _covered[i] = 1;
          if (_freeMask![i] == 1) _doneCount++;
        }
      }
    }
  }

  double _coverage() {
    if (_freeMask == null) _rebuildFreeMask();
    return _freeCount == 0 ? 0 : _doneCount / _freeCount;
  }

  void _publishMap() {
    final n = (room / res).ceil();
    if (_trail.isEmpty) _covered = Uint8List(n * n);
    final ahead = <Offset>[];
    if (status.state == MissionState.returnToDock) {
      ahead.addAll(_returnPath);
    } else if (status.state.isActive && _path.isNotEmpty) {
      final (_, _, i) = _along(_path, _progress);
      ahead.addAll(_path.sublist(math.min(i, _path.length), math.min(i + 40, _path.length)));
    }
    map = MapSnapshot(
      width: room,
      height: room,
      res: res,
      covered: _covered,
      trail: List.of(_trail),
      robot: _pose,
      obstacles: obstacles,
      cable: cable,
      plan: ahead,
      noGo: noGoZones,
      dock: dock,
    );
  }

  void _finishReport() {
    final cov = _coverage();
    final rubric = <String, double>{
      'Completion time': 20 * (1 - 0.4 * math.min(1.0, _t / 300)),
      // w/w pick-up, not area: ~80 % of the debris under the nozzle is collected (bot_simulation model)
      'Efficiency': 25 * math.min(1.0, cov * 0.8),
      'Autonomy': 20.0,
      'Battery': 15.0,
      'Aesthetics': 4.0,
      'Bin removal': 9.0,
      'Cost': 1.8,
    };
    history.insert(
        0,
        MissionReport(
          date: DateTime.now(),
          durationS: _t,
          coverage: cov,
          debrisG: 55 * math.min(1.0, cov * 0.8),
          energyWh: 3.37 * _t / 282,
          docked: true,
          rubric: rubric,
          noGoZones: noGoZones.length,
        ));
    status = status.copyWith(lastEvent: 'Docked at ${_t.toStringAsFixed(0)} s - charging');
  }

  void _seedHistory() {
    final now = DateTime.now();
    final past = [
      (2, 281.9, 0.714, 37.9, 79.3),
      (4, 285.5, 0.746, 41.2, 82.6),
      (7, 283.0, 0.751, 40.6, 82.3),
    ];
    for (final (days, dur, cov, g, score) in past) {
      final scale = score / 79.3;
      history.add(MissionReport(
        date: now.subtract(Duration(days: days, hours: 3)),
        durationS: dur,
        coverage: cov,
        debrisG: g,
        energyWh: 3.37 * dur / 282,
        docked: true,
        rubric: {
          'Completion time': 12.5,
          'Efficiency': 17.1 * scale,
          'Autonomy': 20.0,
          'Battery': 15.0,
          'Aesthetics': 4.0,
          'Bin removal': 9.0,
          'Cost': 1.8,
        },
      ));
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}
