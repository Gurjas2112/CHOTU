import 'package:flutter/material.dart';

import '../app_state.dart';
import '../data/backend_api.dart';
import '../theme.dart';
import '../widgets/common.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key, required this.app});
  final AppController app;

  @override
  Widget build(BuildContext context) {
    final r = app.robot!;
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        GlassCard(
          child: Column(children: [
            _row(Icons.smart_toy_rounded, 'Robot', r.robotName),
            _row(Icons.link_rounded, 'Endpoint', r.endpoint),
            _row(Icons.memory_rounded, 'Hardware', 'Raspberry Pi 4 + ESP32-S3'),
            _row(Icons.hub_rounded, 'Software', 'ROS 2 Humble - rosbridge :9090'),
            _row(Icons.cloud_sync_rounded, 'Backend', kBackendUrl.isEmpty ? 'Off (demo data)' : kBackendUrl),
            _row(Icons.air_rounded, 'Suction', 'Adaptive ECO 55 % / BOOST 100 %'),
          ]),
        ),
        const SizedBox(height: 12),
        const GlassCard(
          glow: C.amber,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Icon(Icons.emoji_events_rounded, color: C.amber),
              SizedBox(width: 8),
              Text('AtomQuest 2025', style: TextStyle(fontWeight: FontWeight.w800)),
            ]),
            SizedBox(height: 8),
            Text(
                "People's Choice Award - Top 10 finalist at the Atomberg Innovation Center.\n"
                "Team Hack O' Giants, PES Modern College of Engineering, Pune.",
                style: TextStyle(color: C.dim, fontSize: 12)),
          ]),
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: () {
            r.disconnect();
            app.robot = null;
            app.setTab(0);
          },
          icon: const Icon(Icons.link_off_rounded),
          label: const Text('Disconnect'),
        ),
        const SizedBox(height: 8),
        const Center(child: Text('CHOTU app v3.0.0', style: TextStyle(color: C.dim, fontSize: 11))),
      ]),
    );
  }

  Widget _row(IconData i, String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 7),
        child: Row(children: [
          Icon(i, size: 18, color: C.cyan),
          const SizedBox(width: 12),
          Text(k, style: const TextStyle(color: C.dim)),
          const Spacer(),
          Flexible(child: Text(v, textAlign: TextAlign.right, style: const TextStyle(fontWeight: FontWeight.w600))),
        ]),
      );
}
