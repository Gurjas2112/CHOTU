import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../app_state.dart';
import '../keys.dart';
import '../models.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// Live map: coverage heat-map, robot, path, AI "avoid" cable and user no-go zones.
/// In edit mode a drag draws a no-go rectangle; "Apply" sends /chotu/set_zones.
class MapScreen extends StatefulWidget {
  const MapScreen({super.key, required this.app});
  final AppController app;

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  Offset? _dragStart;
  Offset? _dragNow;

  @override
  Widget build(BuildContext context) {
    final app = widget.app;
    final r = app.robot!;
    return ListenableBuilder(
      listenable: Listenable.merge([r, app, app.liveDraft]),
      builder: (context, _) {
        final m = r.map;
        return Scaffold(
          appBar: AppBar(title: const Text('Live map'), actions: [
            if (!app.editingZones)
              TextButton.icon(
                key: K.editZones,
                onPressed: () => app.setEditing(true),
                icon: const Icon(Icons.block_rounded, color: C.magenta),
                label: const Text('No-go zones', style: TextStyle(color: C.magenta)),
              ),
          ]),
          body: Column(children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: Row(children: [
                Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(color: stateColor(r.status.state), shape: BoxShape.circle)),
                const SizedBox(width: 8),
                Text(r.status.state.label, style: const TextStyle(fontWeight: FontWeight.w700)),
                const Spacer(),
                Text('${(r.status.coverage * 100).toStringAsFixed(0)}% cleaned',
                    style: const TextStyle(color: C.cyan, fontWeight: FontWeight.w700)),
              ]),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: m == null
                    ? const Center(child: CircularProgressIndicator())
                    : LayoutBuilder(builder: (context, box) {
                        final side = math.min(box.maxWidth, box.maxHeight);
                        final scale = side / math.max(m.width, m.height);
                        Offset toRoom(Offset p) => Offset(p.dx / scale, m.height - p.dy / scale);
                        return Center(
                          child: SizedBox(
                            key: K.map,
                            width: side,
                            height: side,
                            child: GestureDetector(
                              onPanStart: app.editingZones
                                  ? (d) => setState(() => _dragStart = _dragNow = d.localPosition)
                                  : null,
                              onPanUpdate: app.editingZones ? (d) => setState(() => _dragNow = d.localPosition) : null,
                              onPanEnd: app.editingZones
                                  ? (_) {
                                      final a = toRoom(_dragStart!), b = toRoom(_dragNow!);
                                      final z = Zone(a.dx, a.dy, b.dx, b.dy);
                                      if (z.area > 0.02) {
                                        HapticFeedback.selectionClick();
                                        app.addDraftZone(z);
                                      }
                                      setState(() => _dragStart = _dragNow = null);
                                    }
                                  : null,
                              child: CustomPaint(
                                painter: MapPainter(
                                  m,
                                  drafts: [
                                    if (app.editingZones) ...app.draftZones,
                                    if (app.liveDraft.value != null) app.liveDraft.value!,
                                  ],
                                  dragRect: _dragStart == null ? null : Rect.fromPoints(_dragStart!, _dragNow!),
                                ),
                              ),
                            ),
                          ),
                        );
                      }),
              ),
            ),
            if (app.editingZones) _zoneEditor(app) else _legend(),
          ]),
        );
      },
    );
  }

  Widget _legend() => const Padding(
        padding: EdgeInsets.fromLTRB(16, 8, 16, 16),
        child: Wrap(spacing: 14, runSpacing: 6, children: [
          _Key(color: Color(0xFF0E5566), text: 'cleaned'),
          _Key(color: C.amber, text: 'planned path'),
          _Key(color: C.magenta, text: 'AI: avoid (cable)'),
          _Key(color: Color(0xFF8A9BB8), text: 'obstacle'),
          _Key(color: C.red, text: 'no-go zone'),
        ]),
      );

  Widget _zoneEditor(AppController app) => GlassCard(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Drag on the map to draw a no-go zone', style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          Wrap(spacing: 8, children: [
            for (var i = 0; i < app.draftZones.length; i++)
              InputChip(
                label: Text('Zone ${i + 1}  ${app.draftZones[i].area.toStringAsFixed(2)} m²'),
                onDeleted: () => app.removeDraftZone(i),
              ),
          ]),
          const SizedBox(height: 6),
          Row(children: [
            TextButton(onPressed: () => app.setEditing(false), child: const Text('Cancel')),
            const Spacer(),
            FilledButton.icon(
              key: K.applyZones,
              style: FilledButton.styleFrom(backgroundColor: C.magenta),
              onPressed: () {
                HapticFeedback.mediumImpact();
                app.applyZones();
              },
              icon: const Icon(Icons.check_rounded),
              label: Text('Apply ${app.draftZones.length} zone(s)'),
            ),
          ]),
        ]),
      );
}

class _Key extends StatelessWidget {
  const _Key({required this.color, required this.text});
  final Color color;
  final String text;

  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        Container(
            width: 12, height: 12, decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(3))),
        const SizedBox(width: 5),
        Text(text, style: const TextStyle(fontSize: 11, color: C.dim)),
      ]);
}

class MapPainter extends CustomPainter {
  MapPainter(this.m, {this.drafts = const [], this.dragRect});
  final MapSnapshot m;
  final List<Zone> drafts;
  final Rect? dragRect;

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.width / math.max(m.width, m.height);
    Offset px(double x, double y) => Offset(x * s, (m.height - y) * s);
    final room = Rect.fromLTWH(0, 0, m.width * s, m.height * s);
    canvas.drawRRect(
        RRect.fromRectAndRadius(room, const Radius.circular(10)), Paint()..color = const Color(0xFF0D1422));
    final grid = Paint()
      ..color = const Color(0xFF16233A)
      ..strokeWidth = 1;
    for (var v = 0.0; v <= m.width + 1e-6; v += 0.25) {
      canvas.drawLine(px(v, 0), px(v, m.height), grid);
      canvas.drawLine(px(0, v), px(m.width, v), grid);
    }
    // coverage heat-map
    if (m.covered.isNotEmpty) {
      final cell = Paint()..color = const Color(0xFF0E5566);
      // one rectangle per horizontal run of swept cells (~60x fewer draw calls)
      final nx = m.nx, ny = m.covered.length ~/ nx;
      for (var iy = 0; iy < ny; iy++) {
        var ix = 0;
        while (ix < nx) {
          if (m.covered[iy * nx + ix] == 0) {
            ix++;
            continue;
          }
          final start = ix;
          while (ix < nx && m.covered[iy * nx + ix] == 1) {
            ix++;
          }
          final y = iy * m.res;
          canvas.drawRect(Rect.fromPoints(px(start * m.res, y + m.res), px(ix * m.res, y)), cell);
        }
      }
    }
    // trail
    if (m.trail.length > 1) {
      final path = Path()..moveTo(px(m.trail.first.dx, m.trail.first.dy).dx, px(m.trail.first.dx, m.trail.first.dy).dy);
      for (final p in m.trail.skip(1)) {
        final q = px(p.dx, p.dy);
        path.lineTo(q.dx, q.dy);
      }
      canvas.drawPath(
          path,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1.2
            ..color = C.cyan.withOpacity(0.55));
    }
    // obstacles
    final obs = Paint()..color = const Color(0xFF3A4660);
    final obsEdge = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2
      ..color = C.dim;
    for (final o in m.obstacles) {
      if (o.rect != null) {
        final r = Rect.fromPoints(px(o.rect!.left, o.rect!.top), px(o.rect!.right, o.rect!.bottom));
        canvas.drawRRect(RRect.fromRectAndRadius(r, const Radius.circular(3)), obs);
        if (o.label != 'map') canvas.drawRRect(RRect.fromRectAndRadius(r, const Radius.circular(3)), obsEdge);
      } else {
        canvas.drawCircle(px(o.center!.dx, o.center!.dy), o.radius * s, obs);
        canvas.drawCircle(px(o.center!.dx, o.center!.dy), o.radius * s, obsEdge);
      }
    }
    // AI-vision "avoid": power cable
    if (m.cable.length > 1) {
      final p = Path()..moveTo(px(m.cable.first.dx, m.cable.first.dy).dx, px(m.cable.first.dx, m.cable.first.dy).dy);
      for (final c in m.cable.skip(1)) {
        p.lineTo(px(c.dx, c.dy).dx, px(c.dx, c.dy).dy);
      }
      canvas.drawPath(
          p,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 10
            ..strokeCap = StrokeCap.round
            ..color = C.magenta.withOpacity(0.25));
      canvas.drawPath(
          p,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 3
            ..strokeCap = StrokeCap.round
            ..color = C.magenta);
    }
    // no-go zones (applied + drafts)
    void zone(Zone z, bool draft) {
      final r = Rect.fromPoints(px(z.x0, z.y0), px(z.x1, z.y1));
      canvas.drawRect(r, Paint()..color = C.red.withOpacity(draft ? 0.12 : 0.2));
      canvas.drawRect(
          r,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2
            ..color = C.red.withOpacity(draft ? 0.7 : 1));
    }

    for (final z in m.noGo) {
      zone(z, false);
    }
    for (final z in drafts) {
      zone(z, true);
    }
    if (dragRect != null) {
      canvas.drawRect(dragRect!, Paint()..color = C.red.withOpacity(0.15));
      canvas.drawRect(
          dragRect!,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2
            ..color = C.red);
    }
    // planned path
    if (m.plan.length > 1) {
      final paint = Paint()
        ..color = C.amber
        ..strokeWidth = 2;
      for (var i = 0; i + 1 < m.plan.length; i += 2) {
        canvas.drawLine(px(m.plan[i].dx, m.plan[i].dy), px(m.plan[i + 1].dx, m.plan[i + 1].dy), paint);
      }
    }
    // dock
    final d = px(m.dock.dx, m.dock.dy);
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromCenter(center: d.translate(0, -5), width: 0.3 * s, height: 10), const Radius.circular(3)),
        Paint()..color = C.green);
    // robot
    final rb = m.robot;
    if (rb != null) {
      final c = px(rb.x, rb.y);
      final rr = 0.153 * s;
      canvas.drawCircle(c, rr + 6, Paint()..color = C.cyan.withOpacity(0.15));
      canvas.drawCircle(c, rr, Paint()..color = const Color(0xFF14324A));
      canvas.drawCircle(
          c,
          rr,
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2.5
            ..color = C.cyan);
      final h = c + Offset(math.cos(rb.theta), -math.sin(rb.theta)) * rr;
      canvas.drawLine(
          c,
          h,
          Paint()
            ..color = Colors.white
            ..strokeWidth = 2.5);
    }
  }

  @override
  bool shouldRepaint(MapPainter oldDelegate) => true;
}
