import 'package:flutter/widgets.dart';

/// Keys of the controls used by widget tests and by the recorded demo tour
/// (the tour reads their on-screen position to place the fingertip).
class K {
  static final connect = GlobalKey(debugLabel: 'connect-demo');
  static final clean = GlobalKey(debugLabel: 'clean-button');
  static final dock = GlobalKey(debugLabel: 'dock-button');
  static final alerts = GlobalKey(debugLabel: 'alerts-button');
  static final editZones = GlobalKey(debugLabel: 'edit-zones');
  static final applyZones = GlobalKey(debugLabel: 'apply-zones');
  static final addSchedule = GlobalKey(debugLabel: 'add-schedule');
  static final map = GlobalKey(debugLabel: 'map-canvas');
  static final navBar = GlobalKey(debugLabel: 'nav-bar');
}
