import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app_state.dart';
import 'data/demo_robot_repository.dart';
import 'keys.dart';
import 'models.dart';
import 'screens/alerts_screen.dart';
import 'screens/history_screen.dart';

/// Scripted demo tour (flutter build web --dart-define=TOUR=true).
///
/// Drives the real UI with demo data only, step by step, and announces every
/// step in the page title ("CHOTU · 05_live_map_coverage"). The recorder
/// (mobile_app/tools/record_app_demo.py) screenshots each step and records
/// the whole run as one video. A fingertip marks every simulated tap.
class DemoTour {
  DemoTour(this.app);
  final AppController app;

  void _title(String step) => SystemChrome.setApplicationSwitcherDescription(
      ApplicationSwitcherDescription(label: 'CHOTU · $step', primaryColor: 0xFF00E5FF));

  Future<void> _wait(int ms) => Future<void>.delayed(Duration(milliseconds: ms));

  Future<void> _until(bool Function() cond, {int timeoutMs = 60000}) async {
    final end = DateTime.now().add(Duration(milliseconds: timeoutMs));
    while (!cond() && DateTime.now().isBefore(end)) {
      await _wait(100);
    }
  }

  Size _screen() {
    final v = WidgetsBinding.instance.platformDispatcher.views.first;
    return v.physicalSize / v.devicePixelRatio;
  }

  Offset? _centerOf(GlobalKey k) {
    final box = k.currentContext?.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) return null;
    final size = _screen();
    final c = box.localToGlobal(box.size.center(Offset.zero));
    return Offset(c.dx / size.width, c.dy / size.height);
  }

  Future<void> _touch(Offset? p) async {
    if (p == null) return;
    app.touch.value = p;
    await _wait(550);
  }

  Future<void> _tap(GlobalKey k) async {
    await _touch(_centerOf(k));
    await _wait(150);
  }

  Future<void> _tapTab(int i) async {
    final bar = _centerOf(K.navBar);
    if (bar != null) await _touch(Offset((i + 0.5) / 5, bar.dy));
    app.setTab(i);
    await _wait(400);
  }

  /// Screenshot marker: shows the step name in the title, then holds the frame.
  Future<void> _step(String name, {int holdMs = 1600}) async {
    app.touch.value = null; // clean still: the fingertip is only shown in the video
    await _wait(450);
    _title(name);
    await _wait(holdMs);
  }

  Future<void> run() async {
    await _wait(1200);
    final repo = DemoRobotRepository()..timeScale = 1.5;
    await _step('01_connect_screen', holdMs: 2200);
    await _tap(K.connect);
    await app.attach(repo);
    await _wait(500);
    await _step('02_home_docked_ready');

    await _tap(K.clean);
    await repo.startCleaning();
    await _wait(500);
    await _step('03_cleaning_started_undock');

    await _tapTab(1);
    await _until(() => repo.status.state == MissionState.scan, timeoutMs: 8000);
    await _wait(900);
    await _step('04_live_map_360_scan');
    repo.timeScale = 6.0;
    app.tourBadge.value = 'Demo data  -  6x speed';
    await _until(() => repo.status.coverage > 0.22);
    await _step('05_live_map_coverage');

    // draw a no-go zone ("pet bowl corner", top-right) with the fingertip
    await _tap(K.editZones);
    app.setEditing(true);
    await _wait(400);
    await _step('06_no_go_edit_mode', holdMs: 1000);
    final map = K.map.currentContext?.findRenderObject() as RenderBox?;
    if (map != null) {
      final screen = _screen();
      final origin = map.localToGlobal(Offset.zero);
      final side = map.size.width;
      Offset frac(double x, double y) => Offset(
          (origin.dx + x / 3.048 * side) / screen.width, (origin.dy + (3.048 - y) / 3.048 * side) / screen.height);
      const a = Offset(2.30, 2.95), b = Offset(2.95, 2.30);
      await _touch(frac(a.dx, a.dy));
      for (var i = 1; i <= 12; i++) {
        final t = i / 12;
        final x = a.dx + (b.dx - a.dx) * t, y = a.dy + (b.dy - a.dy) * t;
        app.touch.value = frac(x, y);
        app.liveDraft.value = Zone(a.dx, a.dy, x, y);
        await _wait(90);
      }
      app.liveDraft.value = null;
      app.addDraftZone(Zone(a.dx, a.dy, b.dx, b.dy));
    }
    await _wait(500);
    await _step('07_no_go_zone_drawn');
    await _tap(K.applyZones);
    await app.applyZones();
    await _wait(900);
    await _step('08_route_replanned_around_zone');

    await _until(() => repo.alerts.isNotEmpty);
    await _tapTab(0);
    await _wait(300);
    await _step('09_home_alert_brush_tangle');
    await _tap(K.alerts);
    unawaited(app.navigatorKey.currentState!.push(MaterialPageRoute(builder: (_) => AlertsScreen(app: app))));
    await _wait(700);
    await _step('10_alerts_list');
    app.navigatorKey.currentState!.pop();
    await _wait(500);

    await _tapTab(2);
    await _step('11_schedules', holdMs: 1200);
    await _tap(K.addSchedule);
    repo.addSchedule(CleaningSchedule(const TimeOfDay(hour: 18, minute: 0), {1, 2, 3, 4, 5}, label: 'Weekday evening'));
    await _wait(500);
    await _step('12_schedule_added');

    await _tapTab(1);
    repo.timeScale = 24.0;
    app.tourBadge.value = 'Demo data  -  fast-forward 24x';
    await _until(
        () => const {MissionState.returnToDock, MissionState.docking, MissionState.docked}.contains(repo.status.state),
        timeoutMs: 90000);
    repo.timeScale = 6.0;
    app.tourBadge.value = 'Demo data  -  6x speed';
    await _wait(600);
    await _step('13_return_to_dock');
    await _until(() => repo.status.state == MissionState.docked, timeoutMs: 60000);
    await _tapTab(0);
    await _wait(500);
    await _step('14_docked_mission_complete');

    await _tapTab(3);
    await _step('15_cleaning_history');
    await _touch(const Offset(0.5, 0.17));
    unawaited(app.navigatorKey.currentState!
        .push(MaterialPageRoute(builder: (_) => ReportScreen(report: repo.history.first))));
    await _wait(700);
    await _step('16_mission_report_atomquest_score', holdMs: 2200);
    app.navigatorKey.currentState!.pop();
    await _wait(400);
    await _tapTab(4);
    await _step('17_settings_about');
    app.tourBadge.value = null;
    app.touch.value = null;
    await _wait(800);
    _title('END');
  }
}
