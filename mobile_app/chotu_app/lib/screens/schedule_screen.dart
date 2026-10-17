import 'package:flutter/material.dart';

import '../app_state.dart';
import '../keys.dart';
import '../models.dart';
import '../theme.dart';
import '../widgets/common.dart';

const _days = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

class ScheduleScreen extends StatelessWidget {
  const ScheduleScreen({super.key, required this.app});
  final AppController app;

  @override
  Widget build(BuildContext context) {
    final r = app.robot!;
    return ListenableBuilder(
      listenable: r,
      builder: (context, _) => Scaffold(
        appBar: AppBar(title: const Text('Schedules')),
        floatingActionButton: FloatingActionButton.extended(
          key: K.addSchedule,
          backgroundColor: C.cyan,
          foregroundColor: C.bg,
          onPressed: () async {
            final t = await showTimePicker(context: context, initialTime: const TimeOfDay(hour: 18, minute: 0));
            if (t != null) r.addSchedule(CleaningSchedule(t, {1, 2, 3, 4, 5}, label: 'Weekday evening'));
          },
          icon: const Icon(Icons.add_alarm_rounded),
          label: const Text('Add'),
        ),
        body: ListView(padding: const EdgeInsets.all(16), children: [
          const Text('CHOTU leaves the dock, cleans for up to 5 minutes and returns - even when you are out.',
              style: TextStyle(color: C.dim, fontSize: 12)),
          const SizedBox(height: 12),
          for (final s in r.schedules) ...[
            ScheduleCard(schedule: s, onToggle: (v) => r.toggleSchedule(s, v), onDelete: () => r.removeSchedule(s)),
            const SizedBox(height: 10),
          ],
        ]),
      ),
    );
  }
}

class ScheduleCard extends StatelessWidget {
  const ScheduleCard({super.key, required this.schedule, required this.onToggle, required this.onDelete});
  final CleaningSchedule schedule;
  final ValueChanged<bool> onToggle;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) => GlassCard(
        glow: schedule.enabled ? C.cyan : null,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Text(schedule.time.format(context),
                style: TextStyle(fontSize: 32, fontWeight: FontWeight.w800, color: schedule.enabled ? C.text : C.dim)),
            const SizedBox(width: 10),
            Text(schedule.label, style: const TextStyle(color: C.dim)),
            const Spacer(),
            Switch(value: schedule.enabled, onChanged: onToggle),
          ]),
          const SizedBox(height: 8),
          Row(children: [
            for (var d = 1; d <= 7; d++)
              Container(
                margin: const EdgeInsets.only(right: 6),
                width: 30,
                height: 30,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: schedule.days.contains(d) ? C.cyan.withOpacity(0.2) : Colors.transparent,
                  border: Border.all(color: schedule.days.contains(d) ? C.cyan : C.stroke),
                ),
                child: Text(_days[d - 1],
                    style: TextStyle(fontSize: 12, color: schedule.days.contains(d) ? C.cyan : C.dim)),
              ),
            const Spacer(),
            IconButton(onPressed: onDelete, icon: const Icon(Icons.delete_outline_rounded, color: C.dim)),
          ]),
        ]),
      );
}
