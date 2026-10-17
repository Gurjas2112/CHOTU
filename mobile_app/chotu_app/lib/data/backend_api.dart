import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../models.dart';

/// Fleet backend (backend/ in this repo). Off unless the app is built with
///   --dart-define=BACKEND_URL=http://<host>:8000 [--dart-define=BACKEND_KEY=...] [--dart-define=ROBOT_ID=chotu-01]
/// Live control still goes straight to the robot over rosbridge; the backend adds
/// fleet-wide mission history, schedules that survive a re-flash, and no-go zone storage.
const String kBackendUrl = String.fromEnvironment('BACKEND_URL');
const String kBackendKey = String.fromEnvironment('BACKEND_KEY');
const String kBackendRobot = String.fromEnvironment('ROBOT_ID', defaultValue: 'chotu-01');

class BackendException implements Exception {
  BackendException(this.message);
  final String message;
  @override
  String toString() => message;
}

class ChotuBackendApi {
  ChotuBackendApi(this.baseUrl, {this.apiKey = '', this.robotId = kBackendRobot, http.Client? client})
      : _http = client ?? http.Client();

  final String baseUrl;
  final String apiKey;
  final String robotId;
  final http.Client _http;

  Map<String, String> get _headers =>
      {'content-type': 'application/json', if (apiKey.isNotEmpty) 'X-API-Key': apiKey};

  Uri _u(String path, [Map<String, String>? q]) =>
      Uri.parse('${baseUrl.replaceAll(RegExp(r'/+$'), '')}/api/v1$path').replace(queryParameters: q);

  Future<dynamic> _get(Uri u) async {
    final r = await _http.get(u, headers: _headers).timeout(const Duration(seconds: 6));
    if (r.statusCode != 200) throw BackendException('GET ${u.path} -> HTTP ${r.statusCode}');
    return jsonDecode(r.body);
  }

  /// Newest first, as served by GET /api/v1/missions.
  Future<List<MissionReport>> missions({int limit = 20}) async {
    final page = await _get(_u('/missions', {'robot_id': robotId, 'limit': '$limit'})) as Map<String, dynamic>;
    return [for (final m in page['items'] as List) parseMission(m as Map<String, dynamic>)];
  }

  Future<List<CleaningSchedule>> schedules() async {
    final rows = await _get(_u('/robots/$robotId/schedules')) as List;
    return [for (final s in rows) parseSchedule(s as Map<String, dynamic>)];
  }

  /// Stores the zones fleet-side; the backend also forwards them to the robot's /chotu/set_zones.
  Future<void> putZones(List<Zone> zones) async {
    final body = jsonEncode([for (final z in zones) zoneToJson(z)]);
    final r = await _http.put(_u('/robots/$robotId/zones'), headers: _headers, body: body)
        .timeout(const Duration(seconds: 6));
    if (r.statusCode != 200) throw BackendException('PUT zones -> HTTP ${r.statusCode}');
  }

  void close() => _http.close();

  // ---- JSON <-> app models (pure, unit-tested)

  /// Backend rubric keys (chotu_core/scoring.py) -> the labels the app shows.
  static const rubricLabels = {
    'completion_time': 'Completion time',
    'efficiency': 'Efficiency',
    'autonomy': 'Autonomy',
    'battery': 'Battery',
    'aesthetics': 'Aesthetics',
    'container': 'Bin removal',
    'cost': 'Cost',
  };

  static MissionReport parseMission(Map<String, dynamic> m) => MissionReport(
        date: DateTime.parse(m['started_at'] as String).toLocal(),
        durationS: (m['duration_s'] as num).toDouble(),
        coverage: (m['coverage'] as num).toDouble(),
        debrisG: (m['debris_g'] as num).toDouble(),
        energyWh: (m['energy_wh'] as num).toDouble(),
        docked: m['docked'] as bool,
        rubric: {
          for (final e in (m['rubric'] as Map<String, dynamic>).entries)
            rubricLabels[e.key] ?? e.key: (e.value as num).toDouble(),
        },
        noGoZones: (m['no_go_zones'] as num?)?.toInt() ?? 0,
      );

  static CleaningSchedule parseSchedule(Map<String, dynamic> s) {
    final hm = (s['time'] as String).split(':');
    return CleaningSchedule(
      TimeOfDay(hour: int.parse(hm[0]), minute: int.parse(hm[1])),
      {for (final d in s['days'] as List) (d as num).toInt()},
      enabled: s['enabled'] as bool? ?? true,
      label: s['label'] as String? ?? 'Full room',
    );
  }

  static Map<String, Object> zoneToJson(Zone z, [String label = '']) =>
      {'label': label, 'x0': z.x0, 'y0': z.y0, 'x1': z.x1, 'y1': z.y1};
}
