// 서버 자료가 바뀌었는지만 묻는다.
//
// 관리자가 엑셀을 올리면 임원진 화면이 알아서 바뀌게 하려고 둔다.
// 전체를 자주 받아오면 통신량이 수십 배가 되니, 이 한 줄(60바이트쯤)만
// 자주 묻고 값이 달라진 때에만 화면을 다시 받는다.
//
//   GET /data-version  ->  {"version":"a1b2…","updated_at":"2026-10-13T…"}
//
// 못 받아오면 null 을 돌려준다. 신호가 나쁜 걸 '자료가 바뀌었다' 로
// 읽으면 안 된다 — 전체 새로고침이 계속 돌아간다.
import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

class DataVersionService {
  static const String _baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://project-summary-mkoo.fly.dev',
  );

  /// 자료 버전 한 줄. 실패하면 null.
  static Future<String?> fetch() async {
    try {
      final r = await http
          .get(Uri.parse('$_baseUrl/data-version'))
          .timeout(const Duration(seconds: 8));
      if (r.statusCode != 200) return null;
      final d = jsonDecode(r.body);
      if (d is! Map) return null;
      final v = d['version'];
      if (v is! String || v.isEmpty) return null;
      return v;
    } catch (_) {
      return null;
    }
  }
}
