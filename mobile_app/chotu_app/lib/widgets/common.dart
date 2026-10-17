import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models.dart';
import '../theme.dart';

class GlassCard extends StatelessWidget {
  const GlassCard({super.key, required this.child, this.padding = const EdgeInsets.all(16), this.glow});
  final Widget child;
  final EdgeInsets padding;
  final Color? glow;

  @override
  Widget build(BuildContext context) => Container(
        padding: padding,
        decoration: BoxDecoration(
          gradient: const LinearGradient(
              colors: [C.surfaceHi, C.surface], begin: Alignment.topLeft, end: Alignment.bottomRight),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: (glow ?? C.stroke).withOpacity(glow == null ? 1 : 0.6)),
          boxShadow: glow == null ? null : [BoxShadow(color: glow!.withOpacity(0.18), blurRadius: 24)],
        ),
        child: child,
      );
}

class StatTile extends StatelessWidget {
  const StatTile(
      {super.key,
      required this.icon,
      required this.label,
      required this.value,
      required this.fraction,
      required this.color});
  final IconData icon;
  final String label, value;
  final double fraction;
  final Color color;

  @override
  Widget build(BuildContext context) => GlassCard(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
        child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(children: [
                Icon(icon, size: 16, color: color),
                const SizedBox(width: 6),
                Text(label, style: const TextStyle(fontSize: 11, color: C.dim, letterSpacing: 0.6)),
              ]),
              FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(value, style: TextStyle(fontSize: 19, fontWeight: FontWeight.w800, color: color)),
              ),
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                    value: fraction.clamp(0.0, 1.0), minHeight: 5, color: color, backgroundColor: C.stroke),
              ),
            ]),
      );
}

Color stateColor(MissionState s) => switch (s) {
      MissionState.cover || MissionState.spotClean => C.cyan,
      MissionState.scan || MissionState.undock => C.magenta,
      MissionState.returnToDock || MissionState.docking => C.amber,
      MissionState.stuckRecovery => C.red,
      MissionState.docked => C.green,
      _ => C.dim,
    };

/// Animated ring: coverage arc + a pulse while CHOTU is working.
class StatusRing extends StatefulWidget {
  const StatusRing({super.key, required this.status, this.size = 230});
  final RobotStatus status;
  final double size;

  @override
  State<StatusRing> createState() => _StatusRingState();
}

class _StatusRingState extends State<StatusRing> with SingleTickerProviderStateMixin {
  late final AnimationController _a = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat();

  @override
  void dispose() {
    _a.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.status;
    final col = stateColor(s.state);
    return SizedBox(
      width: widget.size,
      height: widget.size,
      child: AnimatedBuilder(
        animation: _a,
        builder: (_, __) => CustomPaint(
          painter: _RingPainter(s.coverage, col, s.state.isActive ? _a.value : 0),
          child: Center(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Icon(_icon(s.state), color: col, size: 30),
              const SizedBox(height: 4),
              Text('${(s.coverage * 100).toStringAsFixed(0)}%',
                  style: const TextStyle(fontSize: 46, fontWeight: FontWeight.w900, color: C.text, height: 1.0)),
              const Text('ROOM CLEANED', style: TextStyle(fontSize: 10, color: C.dim, letterSpacing: 1.6)),
              const SizedBox(height: 6),
              Text(s.state.label, style: TextStyle(fontSize: 13, color: col, fontWeight: FontWeight.w700)),
            ]),
          ),
        ),
      ),
    );
  }

  IconData _icon(MissionState s) => switch (s) {
        MissionState.docked || MissionState.idle => Icons.ev_station_rounded,
        MissionState.returnToDock || MissionState.docking => Icons.home_rounded,
        MissionState.scan => Icons.radar_rounded,
        MissionState.stuckRecovery => Icons.warning_amber_rounded,
        _ => Icons.cleaning_services_rounded,
      };
}

class _RingPainter extends CustomPainter {
  _RingPainter(this.value, this.color, this.pulse);
  final double value, pulse;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    final r = size.width / 2 - 14;
    if (pulse > 0) {
      canvas.drawCircle(
          c,
          r + 4 + 10 * pulse,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2
            ..color = color.withOpacity(0.35 * (1 - pulse)));
    }
    canvas.drawCircle(
        c,
        r,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 12
          ..color = C.stroke);
    final rect = Rect.fromCircle(center: c, radius: r);
    final sweep = 2 * math.pi * value.clamp(0.0, 1.0);
    // gradient arc drawn as short segments: identical on every renderer
    // (the HTML web renderer does not support SweepGradient on stroked arcs)
    const segments = 64;
    final n = value <= 0 ? 0 : math.max(1, (segments * value.clamp(0.0, 1.0)).ceil());
    for (var k = 0; k < n; k++) {
      final a0 = -math.pi / 2 + sweep * k / n;
      final t = n == 1 ? 1.0 : k / (n - 1);
      canvas.drawArc(
          rect,
          a0,
          sweep / n + 0.01,
          false,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 12
            ..strokeCap = k == 0 || k == n - 1 ? StrokeCap.round : StrokeCap.butt
            ..color = Color.lerp(color.withOpacity(0.45), color, t)!);
    }
    // tick marks
    for (var i = 0; i < 60; i++) {
      final a = i / 60 * 2 * math.pi;
      final p1 = c + Offset(math.cos(a), math.sin(a)) * (r - 16);
      final p2 = c + Offset(math.cos(a), math.sin(a)) * (r - (i % 5 == 0 ? 22 : 19));
      canvas.drawLine(
          p1,
          p2,
          Paint()
            ..color = C.stroke
            ..strokeWidth = 1.2);
    }
  }

  @override
  bool shouldRepaint(_RingPainter oldDelegate) =>
      oldDelegate.value != value || oldDelegate.pulse != pulse || oldDelegate.color != color;
}

/// Fingertip shown during the recorded demo tour.
class TouchIndicator extends StatelessWidget {
  const TouchIndicator({super.key, required this.position});
  final ValueNotifier<Offset?> position;

  @override
  Widget build(BuildContext context) => IgnorePointer(
        child: ValueListenableBuilder<Offset?>(
          valueListenable: position,
          builder: (context, p, _) {
            if (p == null) return const SizedBox.shrink();
            final size = MediaQuery.sizeOf(context);
            return Stack(children: [
              AnimatedPositioned(
                duration: const Duration(milliseconds: 380),
                curve: Curves.easeOutCubic,
                left: p.dx * size.width - 22,
                top: p.dy * size.height - 22,
                child: Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Colors.white.withOpacity(0.28),
                    border: Border.all(color: Colors.white.withOpacity(0.85), width: 2),
                  ),
                ),
              ),
            ]);
          },
        ),
      );
}

/// "Demo data - 24x" badge for the recorded tour.
class TourBadge extends StatelessWidget {
  const TourBadge({super.key, required this.text});
  final ValueNotifier<String?> text;

  @override
  Widget build(BuildContext context) => IgnorePointer(
        child: ValueListenableBuilder<String?>(
          valueListenable: text,
          builder: (context, t, _) => t == null
              ? const SizedBox.shrink()
              : Align(
                  alignment: Alignment.topCenter,
                  child: Material(
                    color: Colors.transparent,
                    child: Container(
                      height: 16,
                      width: double.infinity,
                      alignment: Alignment.center,
                      color: C.amber.withOpacity(0.18),
                      child: Text(t,
                          style: const TextStyle(
                              color: C.amber, fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 0.6)),
                    ),
                  ),
                ),
        ),
      );
}
