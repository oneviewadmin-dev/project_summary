// ============================================================
//  오프라인용으로 미리 받아 두기
// ============================================================
// 저장본은 '한 번 열어 본 화면' 에만 생겼다. 그래서 처음 여는 프로젝트
// (BOP ASSY · SDI AUSTRIA)는 오프라인이면 비었다. 온라인일 때 사업부마다
// 화면 자료를 한 번에 받아(서버 /divisions/{id}/offline-bundle) 주소별로
// 나눠 저장한다 — 사업부 여덟 번이면 모든 프로젝트 화면이 채워진다.
//   · 앱을 켤 때 · 다시 앞으로 올 때 (30분에 한 번까지)
//   · 사업부끼리는 동시에 받는다
//   · 서버가 묶음을 모르면(옛 서버) 프로젝트마다 따로 받는다
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../config/app_config.dart';
import '../models/division.dart';
import '../widgets/plan_actual.dart';
import 'offline_store.dart';

class OfflinePrefetch {
  static bool _running = false;
  static const _kLast = 'offline_prefetch_at';
  static const Duration every = Duration(minutes: 30);

  static Future<void> run(List<Division> divisions, {bool force = false}) async {
    if (_running) return;
    _running = true;
    try {
      final prefs = await SharedPreferences.getInstance();
      final last = DateTime.tryParse(prefs.getString(_kLast) ?? '');
      if (!force && last != null && DateTime.now().difference(last) < every) return;
      final month = thisMonthKey();
      final done = await Future.wait([for (final d in divisions) _division(d, month)]);
      // 하나라도 받았으면 '받았다' 로 친다 (오프라인이면 다음에 다시)
      if (done.any((x) => x)) {
        await prefs.setString(_kLast, DateTime.now().toIso8601String());
      }
    } catch (_) {
      // 미리 받기는 덤이다 — 실패해도 앱은 그대로
    } finally {
      _running = false;
    }
  }

  // 사업부 하나 — 묶음으로 받아 주소마다 저장한다
  static Future<bool> _division(Division d, String month) async {
    try {
      final res = await http
          .get(Uri.parse('$kApiBaseUrl/divisions/${Uri.encodeComponent(d.id)}'
              '/offline-bundle?month=${Uri.encodeComponent(month)}'))
          .timeout(const Duration(seconds: 90));
      if (res.statusCode == 404) return await _oneByOne(d, month);   // 옛 서버
      if (res.statusCode != 200) return false;
      final j = jsonDecode(utf8.decode(res.bodyBytes));
      final urls = (j is Map ? j['urls'] : null);
      if (urls is! Map) return false;
      for (final e in urls.entries) {
        await OfflineStore.store('$kApiBaseUrl${e.key}', e.value);
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  // 옛 서버 — 프로젝트마다 화면이 부르는 주소를 그대로 받는다
  static Future<bool> _oneByOne(Division d, String month) async {
    var any = false;
    for (final p in d.projects) {
      final base = '$kApiBaseUrl/projects/${p.id}';
      if (!await OfflineStore.warm('$base/models/detail')) continue;
      any = true;
      for (final u in [
        '$base/weekly-plan', '$base/issues/summary', '$base/models',
        '$base/process-steps',
        '$base/weekly-board?month=${Uri.encodeComponent(month)}',
        '$base/weekly-revenue?month=$month',
      ]) {
        await OfflineStore.warm(u);
      }
    }
    return any;
  }
}
