import 'package:flutter/material.dart';

import 'app_state.dart';
import 'keys.dart';
import 'screens/connect_screen.dart';
import 'screens/history_screen.dart';
import 'screens/home_screen.dart';
import 'screens/map_screen.dart';
import 'screens/schedule_screen.dart';
import 'screens/settings_screen.dart';
import 'theme.dart';
import 'tour.dart';
import 'widgets/common.dart';

/// --dart-define=TOUR=true runs the scripted demo tour used for the recordings.
const bool kTour = bool.fromEnvironment('TOUR');

void main() {
  final app = AppController();
  runApp(ChotuApp(app: app));
  if (kTour) DemoTour(app).run();
}

class ChotuApp extends StatelessWidget {
  const ChotuApp({super.key, required this.app});
  final AppController app;

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'CHOTU',
        debugShowCheckedModeBanner: false,
        theme: chotuTheme(),
        navigatorKey: app.navigatorKey,
        builder: (context, child) => Stack(children: [
          child ?? const SizedBox.shrink(),
          TouchIndicator(position: app.touch),
          TourBadge(text: app.tourBadge),
        ]),
        home: ListenableBuilder(
          listenable: app,
          builder: (context, _) => app.robot == null ? ConnectScreen(app: app) : Shell(app: app),
        ),
      );
}

class Shell extends StatelessWidget {
  const Shell({super.key, required this.app});
  final AppController app;

  @override
  Widget build(BuildContext context) => Scaffold(
        body: IndexedStack(index: app.tab, children: [
          HomeScreen(app: app),
          MapScreen(app: app),
          ScheduleScreen(app: app),
          HistoryScreen(app: app),
          SettingsScreen(app: app),
        ]),
        bottomNavigationBar: NavigationBar(
          key: K.navBar,
          selectedIndex: app.tab,
          onDestinationSelected: app.setTab,
          destinations: const [
            NavigationDestination(icon: Icon(Icons.home_rounded), label: 'Home'),
            NavigationDestination(icon: Icon(Icons.map_rounded), label: 'Live map'),
            NavigationDestination(icon: Icon(Icons.schedule_rounded), label: 'Schedule'),
            NavigationDestination(icon: Icon(Icons.history_rounded), label: 'History'),
            NavigationDestination(icon: Icon(Icons.settings_rounded), label: 'Settings'),
          ],
        ),
      );
}
