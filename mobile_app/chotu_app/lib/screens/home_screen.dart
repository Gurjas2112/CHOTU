import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../app_state.dart';
import '../keys.dart';
import '../models.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'alerts_screen.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key, required this.app});
  final AppController app;

  @override
  Widget build(BuildContext context) {
    final r = app.robot!;
    return ListenableBuilder(
      listenable: r,
      builder: (context, _) {
        final s = r.status;
        return Scaffold(
          appBar: AppBar(
            title: Row(children: [
              Text(r.robotName),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                    color: (s.connected ? C.green : C.red).withOpacity(0.15), borderRadius: BorderRadius.circular(10)),
                child: Text(s.connected ? (r.isDemo ? 'DEMO DATA' : 'ONLINE') : 'OFFLINE',
                    style: TextStyle(fontSize: 10, color: s.connected ? C.green : C.red, letterSpacing: 1)),
              ),
            ]),
            actions: [
              IconButton(
                key: K.alerts,
                onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => AlertsScreen(app: app))),
                icon: Badge(
                  isLabelVisible: r.unresolvedAlerts > 0,
                  label: Text('${r.unresolvedAlerts}'),
                  child: const Icon(Icons.notifications_rounded),
                ),
              ),
            ],
          ),
          body: ListView(padding: const EdgeInsets.fromLTRB(18, 4, 18, 24), children: [
            Center(child: StatusRing(status: s)),
            const SizedBox(height: 6),
            Center(
              child: Text(
                s.state.isActive
                    ? '${(s.elapsed ~/ 60)}:${(s.elapsed % 60).floor().toString().padLeft(2, '0')} elapsed  -  '
                        '${s.timeLeft.toStringAsFixed(0)} s left'
                    : (s.lastEvent.isEmpty ? 'Ready' : s.lastEvent),
                style: const TextStyle(color: C.dim, fontSize: 12),
              ),
            ),
            const SizedBox(height: 16),
            Row(children: [
              Expanded(
                child: FilledButton.icon(
                  key: K.clean,
                  style: FilledButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      backgroundColor: C.cyan,
                      foregroundColor: C.bg),
                  onPressed: s.state.isActive
                      ? null
                      : () {
                          HapticFeedback.mediumImpact();
                          r.startCleaning();
                        },
                  icon: const Icon(Icons.play_arrow_rounded),
                  label: const Text('Clean room', style: TextStyle(fontWeight: FontWeight.w800)),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: OutlinedButton.icon(
                  key: K.dock,
                  style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      foregroundColor: C.amber,
                      side: const BorderSide(color: C.amber)),
                  onPressed: s.state.isActive
                      ? () {
                          HapticFeedback.lightImpact();
                          r.returnToDock();
                        }
                      : null,
                  icon: const Icon(Icons.home_rounded),
                  label: const Text('Dock'),
                ),
              ),
            ]),
            const SizedBox(height: 16),
            GridView.count(
              crossAxisCount: 2,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              mainAxisSpacing: 12,
              crossAxisSpacing: 12,
              childAspectRatio: 1.6,
              children: [
                StatTile(
                    icon: Icons.battery_charging_full_rounded,
                    label: 'BATTERY',
                    value: '${(s.battery * 100).toStringAsFixed(0)} %',
                    fraction: s.battery,
                    color: C.green),
                StatTile(
                    icon: Icons.delete_outline_rounded,
                    label: 'DUST BIN',
                    value: '${(s.binFill * 100).toStringAsFixed(0)} %',
                    fraction: s.binFill,
                    color: s.binFill > 0.7 ? C.amber : C.cyan),
                StatTile(
                    icon: Icons.air_rounded,
                    label: 'SUCTION',
                    value: s.suctionMode == 'OFF' ? 'Off' : '${s.suctionMode} ${(s.suctionDuty * 100).round()}%',
                    fraction: s.suctionDuty,
                    color: s.suctionMode == 'BOOST' ? C.magenta : C.cyan),
                StatTile(
                    icon: Icons.cyclone_rounded,
                    label: 'SIDE BRUSH',
                    value: '${(s.brushHealth * 100).toStringAsFixed(0)} %',
                    fraction: s.brushHealth,
                    color: C.amber),
              ],
            ),
            const SizedBox(height: 14),
            GlassCard(
              child: Row(children: [
                Icon(Icons.shield_rounded, color: s.safety == 'clear' ? C.green : C.red),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('Safety layer', style: TextStyle(fontWeight: FontWeight.w700)),
                    Text(s.lastEvent.isEmpty ? 'All sensors nominal' : s.lastEvent,
                        style: const TextStyle(color: C.dim, fontSize: 12)),
                  ]),
                ),
                Text(s.safety.toUpperCase(),
                    style: TextStyle(color: s.safety == 'clear' ? C.green : C.red, fontWeight: FontWeight.w800)),
              ]),
            ),
          ]),
        );
      },
    );
  }
}
