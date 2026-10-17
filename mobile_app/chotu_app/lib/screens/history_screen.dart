import 'package:flutter/material.dart';

import '../app_state.dart';
import '../models.dart';
import '../theme.dart';
import '../widgets/common.dart';

class HistoryScreen extends StatelessWidget {
  const HistoryScreen({super.key, required this.app});
  final AppController app;

  @override
  Widget build(BuildContext context) {
    final r = app.robot!;
    return ListenableBuilder(
      listenable: r,
      builder: (context, _) => Scaffold(
        appBar: AppBar(title: const Text('Cleaning history')),
        body: ListView(padding: const EdgeInsets.all(16), children: [
          for (final rep in r.history) ...[
            InkWell(
              borderRadius: BorderRadius.circular(20),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => ReportScreen(report: rep))),
              child: GlassCard(
                child: Row(children: [
                  _ScoreBadge(score: rep.score),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(_date(rep.date), style: const TextStyle(fontWeight: FontWeight.w800)),
                      const SizedBox(height: 4),
                      Text(
                          '${(rep.coverage * 100).toStringAsFixed(0)}% covered  -  ${rep.debrisG.toStringAsFixed(1)} g debris  -  '
                          '${rep.durationS.toStringAsFixed(0)} s',
                          style: const TextStyle(color: C.dim, fontSize: 12)),
                    ]),
                  ),
                  Icon(rep.docked ? Icons.check_circle_rounded : Icons.error_rounded,
                      color: rep.docked ? C.green : C.red),
                ]),
              ),
            ),
            const SizedBox(height: 10),
          ],
        ]),
      ),
    );
  }
}

String _date(DateTime d) {
  const m = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return '${d.day} ${m[d.month - 1]}  ${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
}

class _ScoreBadge extends StatelessWidget {
  const _ScoreBadge({required this.score});
  final double score;

  @override
  Widget build(BuildContext context) => SizedBox(
        width: 54,
        height: 54,
        child: Stack(alignment: Alignment.center, children: [
          CircularProgressIndicator(value: score / 100, strokeWidth: 5, color: C.cyan, backgroundColor: C.stroke),
          Text(score.toStringAsFixed(0), style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 17)),
        ]),
      );
}

/// Mission report with the AtomQuest rubric (same criteria as chotu_core/scoring.py).
class ReportScreen extends StatelessWidget {
  const ReportScreen({super.key, required this.report});
  final MissionReport report;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Mission report')),
        body: ListView(padding: const EdgeInsets.all(16), children: [
          GlassCard(
            glow: report.docked ? C.green : C.red,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(report.docked ? 'RETURNED TO DOCK' : 'NOT DOCKED',
                  style:
                      TextStyle(color: report.docked ? C.green : C.red, fontWeight: FontWeight.w800, letterSpacing: 1)),
              const SizedBox(height: 6),
              Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                Text(report.score.toStringAsFixed(1),
                    style: const TextStyle(fontSize: 52, fontWeight: FontWeight.w900, color: C.cyan, height: 1)),
                const Padding(
                    padding: EdgeInsets.only(bottom: 8, left: 6),
                    child: Text('/ 100  AtomQuest score', style: TextStyle(color: C.dim))),
              ]),
            ]),
          ),
          const SizedBox(height: 12),
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 12,
            crossAxisSpacing: 12,
            childAspectRatio: 1.6,
            children: [
              StatTile(
                  icon: Icons.timer_rounded,
                  label: 'TIME',
                  value: '${report.durationS.toStringAsFixed(0)} s',
                  fraction: report.durationS / 300,
                  color: C.cyan),
              StatTile(
                  icon: Icons.grid_on_rounded,
                  label: 'COVERAGE',
                  value: '${(report.coverage * 100).toStringAsFixed(1)} %',
                  fraction: report.coverage,
                  color: C.cyan),
              StatTile(
                  icon: Icons.scale_rounded,
                  label: 'DEBRIS',
                  value: '${report.debrisG.toStringAsFixed(1)} g',
                  fraction: report.debrisG / 55,
                  color: C.green),
              StatTile(
                  icon: Icons.bolt_rounded,
                  label: 'ENERGY',
                  value: '${report.energyWh.toStringAsFixed(2)} Wh',
                  fraction: report.energyWh / 5,
                  color: C.amber),
            ],
          ),
          const SizedBox(height: 12),
          GlassCard(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('RUBRIC', style: TextStyle(fontSize: 11, color: C.dim, letterSpacing: 1.4)),
              const SizedBox(height: 8),
              for (final e in report.rubric.entries)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 5),
                  child: Row(children: [
                    SizedBox(width: 120, child: Text(e.key, style: const TextStyle(fontSize: 12))),
                    Expanded(
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(4),
                        child: LinearProgressIndicator(
                            value: e.value / (rubricWeights[e.key] ?? 1),
                            minHeight: 8,
                            color: C.cyan,
                            backgroundColor: C.stroke),
                      ),
                    ),
                    SizedBox(
                        width: 58,
                        child: Text('${e.value.toStringAsFixed(1)}/${rubricWeights[e.key]!.toStringAsFixed(0)}',
                            textAlign: TextAlign.right, style: const TextStyle(fontSize: 12, color: C.dim))),
                  ]),
                ),
            ]),
          ),
        ]),
      );
}
