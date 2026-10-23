// ══════════════════════════════════════════════════════════════════
//  보여주기용 예시 숫자 — 버릴 코드 (2026-10-23)
// ══════════════════════════════════════════════════════════════════
//
// 블룸·자동차는 주차별 계획이 아직 엑셀로 안 올라와서 서버가 전부 0 을
// 돌려준다. 표는 맞게 떴는데 칸이 다 0 이면 "이게 뭘 보여주는 표인지"
// 설명이 안 된다. 그래서 보고용으로 숫자를 채워 둔다.
//
// ⚠ 이 파일의 숫자는 전부 **지어낸 것**이다. 실제 실적이 아니다.
//    그래서 이 숫자로 그린 표에는 화면에 '예시' 딱지가 붙는다
//    (weekly_board_card.dart 의 demo 표시). 딱지를 떼면 안 된다 —
//    떼는 순간 회의실에서 진짜 숫자로 읽힌다.
//
// 버리는 방법
//   엑셀이 올라오기 시작하면 app_config.dart 의 kDemoBoardData 를
//   false 로 두면 끝이다. 이 파일도 같이 지우면 된다. 서버 쪽에는
//   아무것도 심지 않았다 — 운영 데이터는 손대지 않았다.
//
// 어떻게 섞이나
//   서버가 주는 달·주차·마감 주차는 그대로 쓰고, 숫자만 갈아 넣는다.
//   그래서 11월이 되면 예시도 11월 주차로 따라 움직인다.

/// 프로젝트 한 줄의 예시 숫자.
class DemoRow {
  final int po;        // PO 수량
  final int actual;    // 누적 출하 실적
  final int prev;      // 지난달 실적
  final int weekPlan;  // 한 주 계획 (주차마다 조금씩 흔든다)
  final int nextPlan;  // 다음달 계획

  const DemoRow({
    required this.po,
    required this.actual,
    required this.prev,
    required this.weekPlan,
    required this.nextPlan,
  });
}

class DemoBoard {
  // ---- 사업부별 예시. 없는 사업부는 예시를 안 띄운다.
  static const Map<String, Map<String, DemoRow>> rows = {
    'bloom': {
      'bloom_yfp':       DemoRow(po: 2480, actual: 1710, prev: 240, weekPlan: 190, nextPlan: 220),
      'bloom_corva_kpe': DemoRow(po: 1340, actual: 1052, prev: 160, weekPlan: 110, nextPlan: 130),
      'bloom_sl7':       DemoRow(po: 620,  actual: 418,  prev: 60,  weekPlan: 55,  nextPlan: 70),
      'bloom_tc':        DemoRow(po: 410,  actual: 322,  prev: 40,  weekPlan: 35,  nextPlan: 45),
      'bloom_wdm':       DemoRow(po: 280,  actual: 196,  prev: 25,  weekPlan: 24,  nextPlan: 30),
      'bloom_bop':       DemoRow(po: 150,  actual: 96,   prev: 12,  weekPlan: 14,  nextPlan: 18),
      'bloom_bop_assy':  DemoRow(po: 96,   actual: 61,   prev: 8,   weekPlan: 9,   nextPlan: 12),
    },
    'automotive': {
      'auto_stellantis': DemoRow(po: 18600, actual: 13020, prev: 1840, weekPlan: 1450, nextPlan: 1700),
      'auto_kefico':     DemoRow(po: 12400, actual: 9176,  prev: 1210, weekPlan: 940,  nextPlan: 1080),
      'auto_schaeffler': DemoRow(po: 7300,  actual: 4818,  prev: 720,  weekPlan: 580,  nextPlan: 640),
      'auto_valeo':      DemoRow(po: 5100,  actual: 3672,  prev: 480,  weekPlan: 400,  nextPlan: 450),
      'auto_high_pressure_casting':
                         DemoRow(po: 3400,  actual: 2142,  prev: 300,  weekPlan: 260,  nextPlan: 310),
      'auto_low_pressure_casting':
                         DemoRow(po: 2200,  actual: 1584,  prev: 210,  weekPlan: 170,  nextPlan: 200),
      'auto_etc':        DemoRow(po: 860,   actual: 516,   prev: 70,   weekPlan: 66,   nextPlan: 80),
    },
  };

  /// 주차마다 계획을 조금씩 흔든다. 네 주가 같은 숫자면 만든 표로 보인다.
  static const List<double> weekShape = [0.9, 1.15, 1.0, 0.95];

  /// 마감된 주의 실적 비율. 두 번째 마감 주차는 계획에 못 미치게 둬서
  /// '미달 표시(빨간 칸)와 사유' 가 어떻게 보이는지 같이 보여준다.
  static const List<double> closedRate = [1.02, 0.86];

  /// 못 채운 주에 붙는 예시 사유.
  static const String shortReason =
      '(예시) 고객사 도장 라인 점검으로 2일 출하 중단 — 다음 주에 나눠 출하';

  static bool has(String divisionId) => rows.containsKey(divisionId);

  static DemoRow? of(String divisionId, String projectKey) =>
      rows[divisionId]?[projectKey];
}
