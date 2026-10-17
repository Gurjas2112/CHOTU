import 'package:flutter/material.dart';

import 'data/backend_api.dart';
import 'data/robot_repository.dart';
import 'models.dart';

/// App-wide state: the connected robot, the selected tab and the map editor draft.
class AppController extends ChangeNotifier {
  RobotRepository? robot;
  int tab = 0;

  /// No-go zones being drawn on the Live Map (not yet sent to the robot).
  final List<Zone> draftZones = [];
  bool editingZones = false;

  /// Where the demo tour "touches" the screen (fraction of the screen, null = hidden).
  final ValueNotifier<Offset?> touch = ValueNotifier(null);
  final GlobalKey<NavigatorState> navigatorKey = GlobalKey<NavigatorState>();

  /// Zone currently being dragged by the demo tour (drawn live on the map).
  final ValueNotifier<Zone?> liveDraft = ValueNotifier(null);

  /// Small "fast-forward" badge shown only during the recorded tour.
  final ValueNotifier<String?> tourBadge = ValueNotifier(null);

  /// Fleet backend client, only when built with --dart-define=BACKEND_URL=...
  final ChotuBackendApi? backend =
      kBackendUrl.isEmpty ? null : ChotuBackendApi(kBackendUrl, apiKey: kBackendKey);

  Future<void> attach(RobotRepository r) async {
    robot = r;
    await r.connect();
    draftZones
      ..clear()
      ..addAll(r.noGoZones);
    notifyListeners();
    await syncFromBackend();
  }

  /// Replace the local history and schedules with the backend's copy.
  Future<void> syncFromBackend() async {
    final api = backend, r = robot;
    if (api == null || r == null) return;
    try {
      final missions = await api.missions();
      final schedules = await api.schedules();
      r.history
        ..clear()
        ..addAll(missions);
      r.schedules
        ..clear()
        ..addAll(schedules);
      notifyListeners();
    } catch (e) {
      r.pushAlert(RobotAlert('backend-${DateTime.now().millisecondsSinceEpoch}', 'Backend unreachable',
          '$kBackendUrl: $e', AlertLevel.info, DateTime.now()));
    }
  }

  void setTab(int i) {
    tab = i;
    notifyListeners();
  }

  void setEditing(bool on) {
    editingZones = on;
    notifyListeners();
  }

  void addDraftZone(Zone z) {
    draftZones.add(z);
    notifyListeners();
  }

  void removeDraftZone(int i) {
    draftZones.removeAt(i);
    notifyListeners();
  }

  Future<void> applyZones() async {
    await robot?.applyNoGoZones(List.of(draftZones));
    try {
      await backend?.putZones(List.of(draftZones));
    } catch (_) {
      // the robot already has the zones; the backend copy catches up on the next apply
    }
    editingZones = false;
    notifyListeners();
  }
}
