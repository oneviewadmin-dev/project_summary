import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/services.dart';
import 'package:mobile/services/offline_store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  HttpOverrides.global = null;
  test('저장본으로 떨어진다', () async {
    final dir = await Directory.systemTemp.createTemp('off');
    const ch = MethodChannel('plugins.flutter.io/path_provider');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(ch, (c) async => dir.path);
    // 1) 서버가 있을 때 받아서 저장
    final srv = await HttpServer.bind('127.0.0.1', 0);
    srv.listen((r) { r.response.headers.contentType = ContentType.json; r.response.write('{"v":"최신"}'); r.response.close(); });
    final port = srv.port;
    final uri = Uri.parse('http://127.0.0.1:$port/projects/cup/models');
    final a = await OfflineStore.httpGet(uri);
    expect(a.statusCode, 200);
    await srv.close(force: true);
    // 2) 서버가 꺼짐(오프라인) → 저장본
    final b = await OfflineStore.httpGet(uri);
    expect(b.statusCode, 200);
    expect(b.headers['x-from-cache'], '1');
    expect(b.body.contains('최신'), true);
    expect(OfflineStatus.isOffline, true);
    // 3) 느린 서버 → 3초 뒤 저장본
    final slow = await HttpServer.bind('127.0.0.1', port);
    slow.listen((r) async { await Future.delayed(const Duration(seconds: 6)); r.response.write('{"v":"새것"}'); await r.response.close(); });
    final sw = Stopwatch()..start();
    final c = await OfflineStore.httpGet(uri);
    expect(sw.elapsed.inSeconds < 5, true);
    expect(c.headers['x-from-cache'], '1');
    await Future.delayed(const Duration(seconds: 4));
    final d = await OfflineStore.httpGet(uri, wait: const Duration(milliseconds: 1));
    expect(d.body.contains('새것'), true, reason: '느리게 온 새 값이 저장돼서 다음엔 보여야 한다');
    await slow.close(force: true);
  });
}
