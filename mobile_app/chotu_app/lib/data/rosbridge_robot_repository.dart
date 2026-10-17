import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models.dart';
import 'robot_repository.dart';
import 'rosbridge_protocol.dart';

/// The real robot: rosbridge_server on the Raspberry Pi 4 (ws://<robot-ip>:9090),
/// started by chotu_bringup/robot.launch.py. No extra backend server is needed.
class RosbridgeRobotRepository extends RobotRepository {
  RosbridgeRobotRepository(String url) : super('CHOTU', url);

  WebSocketChannel? _ch;
  StreamSubscription<dynamic>? _sub;
  int _id = 0;
  final List<Offset> _trail = [];
  Pose? _pose;
  List<Offset> _plan = [];
  Uint8List _occ = Uint8List(0);
  double _w = 3.048, _h = 3.048, _res = 0.05;

  @override
  bool get isDemo => false;

  @override
  Future<void> connect() async {
    final ch = WebSocketChannel.connect(Uri.parse(endpoint));
    await ch.ready;
    _ch = ch;
    _sub = ch.stream.listen(_onMessage, onDone: () {
      status = status.copyWith(connected: false, lastEvent: 'Connection closed');
      notifyListeners();
    });
    ch.sink.add(RosbridgeProtocol.subscribe('/chotu/status', 'chotu_interfaces/msg/CleaningStatus', throttleMs: 200));
    ch.sink.add(RosbridgeProtocol.subscribe('/odom', 'nav_msgs/msg/Odometry', throttleMs: 100));
    ch.sink.add(RosbridgeProtocol.subscribe('/chotu/plan', 'nav_msgs/msg/Path', throttleMs: 500));
    ch.sink.add(RosbridgeProtocol.subscribe('/map', 'nav_msgs/msg/OccupancyGrid', throttleMs: 1000));
    status = status.copyWith(connected: true, lastEvent: 'Connected to $endpoint');
    notifyListeners();
  }

  @override
  void disconnect() {
    _sub?.cancel();
    _ch?.sink.close();
    _ch = null;
    status = status.copyWith(connected: false);
    notifyListeners();
  }

  String _nextId(String what) => '$what-${_id++}';

  @override
  Future<void> startCleaning() async => _ch?.sink.add(RosbridgeProtocol.startMission(_nextId('start')));

  @override
  Future<void> returnToDock() async =>
      _ch?.sink.add(RosbridgeProtocol.startMission(_nextId('dock'), returnToDock: true));

  @override
  Future<void> applyNoGoZones(List<Zone> zones) async {
    noGoZones = List.of(zones);
    _ch?.sink.add(RosbridgeProtocol.setZones(_nextId('zones'), zones));
    notifyListeners();
  }

  void _onMessage(dynamic raw) {
    final m = jsonDecode(raw as String) as Map<String, dynamic>;
    if (m['op'] != 'publish') return;
    final msg = m['msg'] as Map<String, dynamic>;
    switch (m['topic']) {
      case '/chotu/status':
        final prev = status.state;
        status = RosbridgeProtocol.parseStatus(msg, status);
        if (status.state == MissionState.docked && prev != MissionState.docked) {
          pushAlert(RobotAlert('done-${DateTime.now().millisecondsSinceEpoch}', 'Mission complete',
              'CHOTU is back on the dock.', AlertLevel.info, DateTime.now()));
        }
      case '/odom':
        final p = msg['pose']['pose'];
        final q = p['orientation'];
        final yaw = 2 * math.atan2((q['z'] as num).toDouble(), (q['w'] as num).toDouble());
        _pose = Pose((p['position']['x'] as num).toDouble(), (p['position']['y'] as num).toDouble(), yaw);
        final o = Offset(_pose!.x, _pose!.y);
        if (_trail.isEmpty || (_trail.last - o).distance > 0.02) _trail.add(o);
      case '/chotu/plan':
        _plan = [
          for (final ps in (msg['poses'] as List))
            Offset((ps['pose']['position']['x'] as num).toDouble(), (ps['pose']['position']['y'] as num).toDouble())
        ];
      case '/map':
        final info = msg['info'];
        _res = (info['resolution'] as num).toDouble();
        _w = (info['width'] as num) * _res;
        _h = (info['height'] as num) * _res;
        _occ = Uint8List.fromList([for (final v in (msg['data'] as List)) (v as num) > 60 ? 1 : 0]);
    }
    map = MapSnapshot(
      width: _w,
      height: _h,
      res: _res,
      covered: Uint8List(0),
      trail: List.of(_trail),
      robot: _pose,
      obstacles: _occupiedAsObstacles(),
      cable: const [],
      plan: _plan,
      noGo: noGoZones,
      dock: const Offset(1.524, 0.0),
    );
    notifyListeners();
  }

  List<Obstacle> _occupiedAsObstacles() {
    if (_occ.isEmpty) return const [];
    final nx = (_w / _res).round();
    return [
      for (var i = 0; i < _occ.length; i++)
        if (_occ[i] == 1) Obstacle.rect(Rect.fromLTWH((i % nx) * _res, (i ~/ nx) * _res, _res, _res), 'map'),
    ];
  }
}
