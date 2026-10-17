import 'package:chotu_app/app_state.dart';
import 'package:chotu_app/data/demo_robot_repository.dart';
import 'package:chotu_app/keys.dart';
import 'package:chotu_app/main.dart';
import 'package:chotu_app/models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('connect to the demo robot, start cleaning, see progress', (tester) async {
    tester.view.physicalSize = const Size(430 * 3, 932 * 3);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
    final app = AppController();
    await tester.pumpWidget(ChotuApp(app: app));
    expect(find.text('CHOTU-01'), findsOneWidget);

    await tester.tap(find.byKey(K.connect));
    await tester.pump(const Duration(milliseconds: 700));
    await tester.pump();
    expect(find.text('Ready on dock'), findsOneWidget);
    expect(find.text('DEMO DATA'), findsOneWidget);

    final repo = app.robot! as DemoRobotRepository..timeScale = 40;
    await tester.tap(find.byKey(K.clean));
    await tester.pump();
    expect(repo.status.state, MissionState.undock);

    for (var i = 0; i < 20; i++) {
      await tester.pump(const Duration(milliseconds: 100)); // 2 s x 40 = 80 simulated s
    }
    expect(repo.status.state.isActive, isTrue);
    expect(repo.status.coverage, greaterThan(0));

    await tester.tap(find.text('Live map'));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byKey(K.map), findsOneWidget);
    repo.disconnect();
  });

  test('no-go zone is respected by the demo route', () async {
    final repo = DemoRobotRepository();
    final zone = Zone(2.3, 2.3, 2.95, 2.95);
    await repo.applyNoGoZones([zone]);
    final m = repo.map!;
    expect(m.noGo, hasLength(1));
    repo.dispose();
  });

  test('zone normalises corners and reports area', () {
    final z = Zone(2.0, 1.0, 1.0, 2.0);
    expect(z.x0, 1.0);
    expect(z.y1, 2.0);
    expect(z.area, closeTo(1.0, 1e-9));
    expect(z.contains(1.5, 1.5), isTrue);
    expect(z.contains(0.5, 1.5), isFalse);
  });
}
