// 전사 잔업·특근을 받아온다.
//
//   GET /overtime/week?w=&kind=&scope=   전사 한 주 + 사업부 순위
//   GET /overtime/week/{div}?w=          사업부 한 곳 + 요일별
//
// 아직 한 주도 안 올렸으면 has_data=false 로 와서 홈 카드가 통째로 빠진다.
import '../models/overtime.dart';
import 'offline_store.dart';

class OvertimeService {
  static const String _baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://project-summary-mkoo.fly.dev',
  );

  static String _q(Map<String, String> p) {
    final parts = <String>[];
    p.forEach((k, v) {
      if (v.trim().isNotEmpty) {
        parts.add('$k=${Uri.encodeQueryComponent(v.trim())}');
      }
    });
    return parts.isEmpty ? '' : '?${parts.join('&')}';
  }

  static Future<OvertimeWeek> fetchWeek({
    String week = '',
    String kind = 'overtime',
    String scope = 'total',
    void Function(OvertimeWeek)? onFresh,
  }) async {
    final qs = _q({'w': week, 'kind': kind, 'scope': scope});
    try {
      // onFresh 를 주면 저장본을 먼저 주고 새 값이 따라온다.
      // 2026-11-03 — 전에는 이게 없어서, 서버가 8초 안에 답을 못 하면
      // 저장본으로 떨어진 채 그대로 머물렀다. 43주차가 올라왔는데
      // 카드는 41주차를 들고 있던 이유다.
      final got = await OfflineStore.fetch(
        '$_baseUrl/overtime/week$qs',
        'overtime_week_${week}_${kind}_$scope',
        onFresh: onFresh == null
            ? null
            : (c) {
                final d = c.data;
                if (d is Map) {
                  onFresh(OvertimeWeek.fromJson(d.cast<String, dynamic>()));
                }
              },
      );
      final d = got.data;
      if (d is! Map) return OvertimeWeek.empty;
      return OvertimeWeek.fromJson(d.cast<String, dynamic>());
    } catch (_) {
      // 붙지 않는 서버에서도 화면은 카드만 빠진다.
      return OvertimeWeek.empty;
    }
  }

  static Future<OvertimeDivision> fetchDivision(
    String division, {
    String week = '',
  }) async {
    final id = division.trim();
    if (id.isEmpty) return OvertimeDivision.empty;
    final qs = _q({'w': week});
    try {
      final got = await OfflineStore.fetch(
        '$_baseUrl/overtime/week/${Uri.encodeComponent(id)}$qs',
        'overtime_div_${id}_$week',
      );
      final d = got.data;
      if (d is! Map) return OvertimeDivision.empty;
      return OvertimeDivision.fromJson(d.cast<String, dynamic>());
    } catch (_) {
      return OvertimeDivision.empty;
    }
  }
}
