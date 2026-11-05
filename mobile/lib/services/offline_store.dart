// 마지막으로 받아온 데이터를 기기에 남겨 둔다.
//
// 지금까지는 열 때마다 fly.io 에서 받아왔고, 연결이 안 되면 화면이
// 비거나 '불러오지 못했습니다' 만 떴다. 비행기 안이나 공장 안처럼
// 신호가 없는 곳에서도 마지막으로 본 내용은 바로 보여야 한다.
//
// 규칙
//  - 받아오면 저장한다 (JSON 그대로, 화면별 키).
//  - 못 받아오면 저장해 둔 걸 돌려주고 fromCache=true 로 알린다.
//  - 저장된 것도 없으면 그때만 예외를 던진다.
//  - 저장된 내용을 보여줄 때는 언제 것인지 반드시 같이 보여준다.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

/// 받아온 값 + 언제 것인지 + 저장본인지
class Cached<T> {
  final T data;
  final DateTime? savedAt;
  final bool fromCache;

  const Cached(this.data, {this.savedAt, this.fromCache = false});

  Cached<R> map<R>(R Function(T) f) =>
      Cached<R>(f(data), savedAt: savedAt, fromCache: fromCache);
}

/// 앱 전체의 연결 상태. 홈 배너가 이걸 본다.
class OfflineStatus {
  /// null = 정상. 값이 있으면 '그 시각에 저장된 내용을 보고 있다'.
  static final ValueNotifier<DateTime?> savedAt = ValueNotifier<DateTime?>(null);

  static void online() {
    if (savedAt.value != null) savedAt.value = null;
  }

  static void offline(DateTime? at) {
    savedAt.value = at ?? DateTime.fromMillisecondsSinceEpoch(0);
  }

  static bool get isOffline => savedAt.value != null;
}

class OfflineStore {
  static Directory? _dir;

  static Future<Directory?> _root() async {
    if (_dir != null) return _dir;
    try {
      final base = await getApplicationSupportDirectory();
      final d = Directory('${base.path}/offline');
      if (!await d.exists()) await d.create(recursive: true);
      _dir = d;
      return d;
    } catch (_) {
      return null; // 저장을 못 해도 앱은 돌아가야 한다
    }
  }

  static String _safe(String key) =>
      key.replaceAll(RegExp(r'[^A-Za-z0-9_.-]'), '_');

  static Future<void> save(String key, dynamic json) async {
    try {
      final d = await _root();
      if (d == null) return;
      final f = File('${d.path}/${_safe(key)}.json');
      await f.writeAsString(jsonEncode({
        'saved_at': DateTime.now().toIso8601String(),
        'data': json,
      }));
    } catch (_) {}
  }

  static Future<Cached<dynamic>?> load(String key) async {
    try {
      final d = await _root();
      if (d == null) return null;
      final f = File('${d.path}/${_safe(key)}.json');
      if (!await f.exists()) return null;
      final m = jsonDecode(await f.readAsString());
      if (m is! Map) return null;
      return Cached<dynamic>(m['data'],
          savedAt: DateTime.tryParse((m['saved_at'] ?? '').toString()),
          fromCache: true);
    } catch (_) {
      return null;
    }
  }

  /// 받아오고 저장한다. 실패하면 저장해 둔 걸 돌려준다.
  /// 둘 다 없으면 예외를 던진다 (화면이 '불러오지 못했습니다' 를 띄울 수 있게).
  ///
  /// [onFresh] 를 주면 **저장된 값을 먼저 돌려주고** 새 값은 뒤에서 받아
  /// 알려 준다. 지금까지는 앱을 열 때마다 fly.io 응답을 먼저 기다렸다.
  /// 저장된 값이 멀쩡히 있어도 홈이 빈 채로 있었고, 신호가 나쁘면 그게
  /// 8초, 20초까지 갔다. 어제 본 숫자라도 0.1초에 보이는 편이 낫다.
  static Future<Cached<dynamic>> fetch(
    String url,
    String key, {
    Duration timeout = const Duration(seconds: 8),
    void Function(Cached<dynamic>)? onFresh,
  }) async {
    if (onFresh != null) {
      final c = await load(key);
      if (c != null) {
        // 저장된 게 있으면 그걸 먼저 준다. 새 값은 따라온다.
        unawaited(_network(url, key, timeout).then((f) {
          if (f != null) {
            onFresh(f);
          } else {
            // 뒤에서 받아오다 실패했으면 배너가 그 사실을 말해야 한다.
            OfflineStatus.offline(c.savedAt);
          }
        }));
        return c;
      }
    }
    final fresh = await _network(url, key, timeout);
    if (fresh != null) return fresh;
    final c = await load(key);
    if (c != null) {
      OfflineStatus.offline(c.savedAt);
      return c;
    }
    throw const SocketException('받아오지 못했고 저장된 것도 없습니다');
  }

  /// 네트워크에서만 받아 저장한다. 실패하면 null — 여기서는 저장본을
  /// 보지 않는다. 저장본으로 떨어질지는 부르는 쪽이 정한다.
  static Future<Cached<dynamic>?> _network(
      String url, String key, Duration timeout) async {
    try {
      final res = await http.get(Uri.parse(url)).timeout(timeout);
      if (res.statusCode != 200) throw HttpException('HTTP ${res.statusCode}');
      final data = jsonDecode(utf8.decode(res.bodyBytes));
      await save(key, data);
      OfflineStatus.online();
      return Cached<dynamic>(data, savedAt: DateTime.now());
    } catch (_) {
      return null;
    }
  }

  // ── http.get 대신 쓰는 GET (2026-11-05) ────────────────────────────
  //
  // Min: "오프라인이여도 제일 최신에 retrieve 한 데이터를 flutter app 에
  //      반영 될 수 있게끔 … 앱 킬 때마다 로딩하는데 시간도 걸리고 오프라인
  //      되면 아예 데이터들이 안 들어오니까"
  //
  // 홈은 위의 fetch(onFresh) 로 저장본부터 보여 주는데, 사업부 · 프로젝트 ·
  // 모델 · 주차 보드 화면은 http.get 을 바로 불러서 저장본이 아예 없었다.
  // 그래서 오프라인이면 빈 화면, 서버가 깨어나는 동안은 빙글빙글이었다.
  //
  // http.get 자리에 그대로 끼우면 된다 (돌려주는 것도 http.Response).
  //   · 받으면 저장한다 (주소마다 한 벌)
  //   · 못 받으면(오프라인 · 서버 오류) 저장본을 200 으로 돌려준다
  //   · [wait] 안에 답이 없으면 저장본부터 돌려주고, 받던 것은 끝까지 받아
  //     저장해 둔다 — 다음에 열 때는 그게 보인다
  //   · 저장본도 없으면 끝까지 기다린다 (처음 여는 화면)
  static Future<http.Response> httpGet(Uri uri,
      {Duration wait = const Duration(seconds: 3)}) async {
    final key = _urlKey(uri);
    final net = http.get(uri).then((res) async {
      if (res.statusCode == 200) {
        await _saveRaw(key, res.bodyBytes);
        OfflineStatus.online();
      }
      return res;
    });
    try {
      final res = await net.timeout(wait);
      if (res.statusCode == 200) return res;
      final c = await _loadRaw(key);     // 서버 오류면 저장본이 낫다
      return c ?? res;
    } on TimeoutException {
      final c = await _loadRaw(key);
      if (c == null) return net;         // 처음 여는 화면 — 끝까지 기다린다
      // 받던 것은 끝까지 받아 저장한다. 실패해도 조용히.
      unawaited(net.then((_) {}, onError: (_) {}));
      return c;
    } catch (_) {
      final c = await _loadRaw(key);
      if (c == null) rethrow;
      final at = DateTime.tryParse(c.headers['x-saved-at'] ?? '');
      OfflineStatus.offline(at);
      return c;
    }
  }

  /// 화면에 띄울 '못 불러옴' 글 — 'SocketException: …' 을 그대로 보여 주지 않는다.
  static String errorText(Object? e) {
    final t = '$e';
    if (e is SocketException || t.contains('SocketException') || t.contains('저장된 것도 없습니다')) {
      return '오프라인 · 아직 받아 두지 못한 화면입니다';
    }
    return '불러오지 못했습니다. 잠시 뒤 다시 열어 주세요.';
  }

  /// 미리 받아 두기 — 받기만 하고 저장한다. 못 받아도 저장본 · 배너를
  /// 건드리지 않는다 (offline_prefetch.dart). 받았으면 true.
  static Future<bool> warm(String url,
      {Duration timeout = const Duration(seconds: 25)}) async {
    try {
      final res = await http.get(Uri.parse(url)).timeout(timeout);
      if (res.statusCode != 200) return false;
      await store(url, jsonDecode(utf8.decode(res.bodyBytes)));
      return true;
    } catch (_) {
      return false;
    }
  }

  /// 주소 하나의 값을 저장한다 — 그 주소를 여는 화면이 어느 길(fetch · httpGet)
  /// 로 읽든 찾게 두 자리에 다 둔다.
  static Future<void> store(String url, dynamic data) async {
    final uri = Uri.parse(url);
    await _saveRaw(_urlKey(uri), utf8.encode(jsonEncode(data)));   // httpGet() 이 읽는 자리
    final key = _fetchKeyOf(uri);
    if (key != null) await save(key, data);                        // fetch() 가 읽는 자리
  }

  // fetch() 로 읽는 화면의 저장 이름 (project_overview_screen.dart 와 같아야 한다)
  static String? _fetchKeyOf(Uri uri) {
    final m = RegExp(r'^/projects/([^/]+)/(models/detail|weekly-plan)$').firstMatch(uri.path);
    if (m == null || uri.query.isNotEmpty) return null;
    final pk = Uri.decodeComponent(m.group(1)!);
    return m.group(2) == 'models/detail' ? 'models_$pk' : 'weekly_plan_$pk';
  }

  // 주소 → 파일 이름. 주소가 길어 파일 이름 한계를 넘지 않게 짧은 지문을 붙인다.
  static String _urlKey(Uri uri) {
    final s = uri.toString();
    var h = 0x811c9dc5;                  // FNV-1a 32비트
    for (final c in utf8.encode(s)) {
      h ^= c;
      h = (h * 0x01000193) & 0xffffffff;
    }
    final path = _safe(uri.path);
    final head = path.length > 60 ? path.substring(path.length - 60) : path;
    return 'get_${head}_${h.toRadixString(16)}';
  }

  static Future<void> _saveRaw(String key, List<int> body) async {
    try {
      final d = await _root();
      if (d == null) return;
      await File('${d.path}/$key.json').writeAsString(jsonEncode({
        'saved_at': DateTime.now().toIso8601String(),
        'body': utf8.decode(body, allowMalformed: true),
      }));
    } catch (_) {}
  }

  static Future<http.Response?> _loadRaw(String key) async {
    try {
      final d = await _root();
      if (d == null) return null;
      final f = File('${d.path}/$key.json');
      if (!await f.exists()) return null;
      final m = jsonDecode(await f.readAsString());
      if (m is! Map) return null;
      return http.Response.bytes(utf8.encode((m['body'] ?? '').toString()), 200,
          headers: {
            'content-type': 'application/json; charset=utf-8',
            'x-from-cache': '1',
            'x-saved-at': (m['saved_at'] ?? '').toString(),
          });
    } catch (_) {
      return null;
    }
  }

  /// 저장된 것 중 가장 오래된 시각. 배너 문구에 쓴다.
  static String describe(DateTime? at) {
    if (at == null || at.millisecondsSinceEpoch == 0) return '저장된 내용';
    final now = DateTime.now();
    final sameDay =
        at.year == now.year && at.month == now.month && at.day == now.day;
    final hh = at.hour.toString().padLeft(2, '0');
    final mm = at.minute.toString().padLeft(2, '0');
    return sameDay
        ? '오늘 $hh:$mm 기준'
        : '${at.month}/${at.day} $hh:$mm 기준';
  }
}
