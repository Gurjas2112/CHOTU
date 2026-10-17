import 'dart:convert';

import 'package:chotu_app/data/backend_api.dart';
import 'package:chotu_app/models.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

// First row of backend/sample_data/missions.json (digital-twin seed 10).
const _mission = '''
{"id":"m-0001","robot_id":"chotu-01","room_id":"atomquest-arena","started_at":"2026-09-01T10:30:00Z",
 "ended_at":"2026-09-01T10:34:44Z","trigger":"app","source":"digital_twin","sim_seed":10,"docked":true,
 "duration_s":284.8,"coverage":0.6203,"debris_g":28.1,"debris_spawned_g":55.0,"energy_wh":3.263,
 "avg_power_w":41.25,"eco_energy_saving_pct":15.5,"collisions":2,"cable_incidents":1,"recoveries":18,
 "dock_error_m":0.027,"efficiency_by_type":{"dust":0.674},
 "rubric":{"completion_time":12.41,"efficiency":12.22,"autonomy":13.8,"battery":15.0,"aesthetics":4.0,
           "container":9.0,"cost":1.76},"score":68.2,"no_go_zones":1}''';

void main() {
  test('mission JSON maps onto the app report and rubric labels', () {
    final r = ChotuBackendApi.parseMission(jsonDecode(_mission) as Map<String, dynamic>);
    expect(r.durationS, 284.8);
    expect(r.coverage, 0.6203);
    expect(r.docked, true);
    expect(r.noGoZones, 1);
    expect(r.rubric.keys.toSet(), rubricWeights.keys.toSet());
    expect(r.rubric['Bin removal'], 9.0);
    expect(r.score, closeTo(68.2, 0.01));
  });

  test('schedule JSON maps onto CleaningSchedule', () {
    final s = ChotuBackendApi.parseSchedule(
        {'id': 's-001', 'robot_id': 'chotu-01', 'time': '07:05', 'days': [1, 3, 5], 'label': 'Morning', 'enabled': false});
    expect(s.time.hour, 7);
    expect(s.time.minute, 5);
    expect(s.days, {1, 3, 5});
    expect(s.enabled, false);
    expect(s.label, 'Morning');
  });

  test('client sends the API key and the robot filter', () async {
    late http.Request seen;
    final api = ChotuBackendApi('http://fleet.local:8000/', apiKey: 'k1', robotId: 'chotu-02',
        client: MockClient((req) async {
      seen = req;
      return http.Response('{"total":1,"limit":20,"offset":0,"items":[$_mission]}', 200);
    }));
    final ms = await api.missions();
    expect(ms, hasLength(1));
    expect(seen.url.toString(), 'http://fleet.local:8000/api/v1/missions?robot_id=chotu-02&limit=20');
    expect(seen.headers['X-API-Key'], 'k1');
  });

  test('zones use the backend field names', () {
    expect(ChotuBackendApi.zoneToJson(Zone(2, 2, 1, 1), 'Rug'),
        {'label': 'Rug', 'x0': 1.0, 'y0': 1.0, 'x1': 2.0, 'y1': 2.0});
  });
}
