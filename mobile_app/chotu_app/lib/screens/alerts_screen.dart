import 'package:flutter/material.dart';

import '../app_state.dart';
import '../models.dart';
import '../theme.dart';
import '../widgets/common.dart';

class AlertsScreen extends StatelessWidget {
  const AlertsScreen({super.key, required this.app});
  final AppController app;

  @override
  Widget build(BuildContext context) {
    final r = app.robot!;
    return ListenableBuilder(
      listenable: r,
      builder: (context, _) => Scaffold(
        appBar: AppBar(title: const Text('Alerts')),
        body: r.alerts.isEmpty
            ? const Center(child: Text('No alerts - CHOTU is happy', style: TextStyle(color: C.dim)))
            : ListView.separated(
                padding: const EdgeInsets.all(16),
                itemCount: r.alerts.length,
                separatorBuilder: (_, __) => const SizedBox(height: 10),
                itemBuilder: (context, i) {
                  final a = r.alerts[i];
                  final col = switch (a.level) {
                    AlertLevel.critical => C.red,
                    AlertLevel.warning => C.amber,
                    AlertLevel.info => C.cyan,
                  };
                  return Opacity(
                    opacity: a.resolved ? 0.5 : 1,
                    child: GlassCard(
                      glow: a.resolved ? null : col,
                      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Icon(a.level == AlertLevel.info ? Icons.info_rounded : Icons.warning_amber_rounded, color: col),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(a.title, style: const TextStyle(fontWeight: FontWeight.w800)),
                            const SizedBox(height: 4),
                            Text(a.body, style: const TextStyle(color: C.dim, fontSize: 12)),
                            const SizedBox(height: 6),
                            Text(TimeOfDay.fromDateTime(a.time).format(context),
                                style: const TextStyle(color: C.dim, fontSize: 11)),
                          ]),
                        ),
                        if (!a.resolved) TextButton(onPressed: () => r.resolveAlert(a.id), child: const Text('Done')),
                      ]),
                    ),
                  );
                },
              ),
      ),
    );
  }
}
