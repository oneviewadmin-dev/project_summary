import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:mobile/services/offline_store.dart';

// 사업부 묶음(/divisions/{id}/offline-bundle) 을 받아 주소별로 나눠 저장하면,
// 처음 여는 프로젝트도 오프라인에서 두 길(fetch · httpGet) 모두 저장본이 나온다.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  HttpOverrides.global = null;
  test('묶음으로 받은 것을 오프라인에서 꺼낸다', () async {
    final dir = await Directory.systemTemp.createTemp('pre');
    const ch = MethodChannel('plugins.flutter.io/path_provider');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(ch, (c) async => dir.path);
    SharedPreferences.setMockInitialValues({});
    final srv = await HttpServer.bind('127.0.0.1', 0);
    final base = 'http://127.0.0.1:${srv.port}';
    srv.listen((r) {
      final body = jsonEncode({'urls': {
        '/projects/automotive_sdi_austria/models/detail': {'models': [1, 2]},
        '/projects/automotive_sdi_austria/weekly-board?month=2026-11': {'rows': []},
      }});
      r.response.headers.set('content-type', 'application/json');
      r.response.headers.set('content-encoding', 'gzip');
      r.response.add(gzip.encode(utf8.encode(body)));
      r.response.close();
    });
    final res = await HttpClient().getUrl(Uri.parse('$base/divisions/automotive/offline-bundle')).then((q) => q.close());
    final j = jsonDecode(await res.transform(utf8.decoder).join());
    for (final e in (j['urls'] as Map).entries) {
      await OfflineStore.store('$base${e.key}', e.value);
    }
    await srv.close(force: true);
    final a = await OfflineStore.fetch('$base/projects/automotive_sdi_austria/models/detail',
        'models_automotive_sdi_austria', timeout: const Duration(seconds: 1));
    expect(a.fromCache, true);
    expect((a.data as Map)['models'], [1, 2]);
    final b = await OfflineStore.httpGet(Uri.parse('$base/projects/automotive_sdi_austria/weekly-board?month=2026-11'));
    expect(b.headers['x-from-cache'], '1');
  });
}
