// 캘린더 일정 (/calendar/events) — 2026-11-04
//
// 캘린더는 옛 주간보고 카드(/dashboard)의 글자 속에서 '(11-07)' 같은
// 날짜를 찾아 일정을 만들고 있었다. 그 카드 86장 중 날짜가 잡히는 카드가
// 0장이라 캘린더가 통째로 비어 있었다.
// Min: "캘린더랑 일정들이랑 연결 되어 있어?" → "연결 부탁할게"
//
// 이제 서버가 운영 자료(개발 단계 예정·실적일, 주차 계획)에서 모아 준다.
// 지연·임박 판정은 홈과 같은 함수를 써서 '일정 지연' 숫자가 갈리지 않는다.
//
// 실패해도 화면은 떠야 하므로 예외 대신 empty 를 돌려준다 — 그러면 화면이
// 예전 방식(/dashboard)으로 떨어진다. 이 주소가 없는 옛 서버에 붙을 때다.
import '../config/app_config.dart';
import '../models/calendar_event.dart';
import 'offline_store.dart';

class CalendarFeed {
  /// 날짜가 있는 일정
  final List<CalendarEvent> events;

  /// 홈은 지연으로 세는데 달력에 놓을 날짜가 없는 것
  /// (양산품 비고에 '지연' 이라고 적힌 것). 빼면 홈 숫자와 갈린다.
  final List<CalendarEvent> undated;

  final bool loaded;

  const CalendarFeed(
      {required this.events, required this.undated, required this.loaded});

  static const CalendarFeed empty =
      CalendarFeed(events: [], undated: [], loaded: false);
}

class CalendarService {
  static Future<CalendarFeed> fetch() async {
    try {
      final got = await OfflineStore.fetch(
        '$kApiBaseUrl/calendar/events',
        'calendar_events',
        timeout: const Duration(seconds: 15),
      );
      final j = got.data;
      if (j is! Map || j['events'] is! List) return CalendarFeed.empty;
      List<CalendarEvent> read(dynamic v) => ((v as List?) ?? const [])
          .whereType<Map>()
          .map(CalendarEvent.fromServer)
          .whereType<CalendarEvent>()
          .toList();
      return CalendarFeed(
        events: read(j['events']),
        undated: read(j['undated']),
        loaded: true,
      );
    } catch (_) {
      return CalendarFeed.empty;
    }
  }
}
