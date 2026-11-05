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

  // 프로젝트 목록 줄에 뜨는 이번 달 매출 (달러). 0 이면 매출 예시는 안 띄운다.
  final int revenue;      // 실적
  final int planRevenue;  // 계획

  const DemoRow({
    required this.po,
    required this.actual,
    required this.prev,
    required this.weekPlan,
    required this.nextPlan,
    this.revenue = 0,
    this.planRevenue = 0,
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
      'auto_stellantis': DemoRow(po: 18600, actual: 13020, prev: 1840, weekPlan: 1450,
          nextPlan: 1700, revenue: 486000, planRevenue: 620000),
      'auto_kefico':     DemoRow(po: 12400, actual: 9176,  prev: 1210, weekPlan: 940,
          nextPlan: 1080, revenue: 312000, planRevenue: 350000),
      'auto_schaeffler': DemoRow(po: 7300,  actual: 4818,  prev: 720,  weekPlan: 580,
          nextPlan: 640,  revenue: 164000, planRevenue: 230000),
      'auto_valeo':      DemoRow(po: 5100,  actual: 3672,  prev: 480,  weekPlan: 400,
          nextPlan: 450,  revenue: 125000, planRevenue: 140000),
      'auto_high_pressure_casting':
                         DemoRow(po: 3400,  actual: 2142,  prev: 300,  weekPlan: 260,
          nextPlan: 310,  revenue: 72000,  planRevenue: 110000),
      'auto_low_pressure_casting':
                         DemoRow(po: 2200,  actual: 1584,  prev: 210,  weekPlan: 170,
          nextPlan: 200,  revenue: 54000,  planRevenue: 62000),
      'auto_etc':        DemoRow(po: 860,   actual: 516,   prev: 70,   weekPlan: 66,
          nextPlan: 80,   revenue: 18000,  planRevenue: 30000),
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

  /// 프로젝트 키만 보고 어느 사업부인지. (auto_ → 자동차, bloom_ → 블룸)
  static String divisionOf(String projectKey) {
    final k = projectKey.toLowerCase();
    for (final d in rows.keys) {
      if (rows[d]!.containsKey(k)) return d;
    }
    if (k.startsWith('auto_')) return 'automotive';
    if (k.startsWith('bloom_')) return 'bloom';
    return '';
  }

  static DemoRow? find(String projectKey) {
    final d = divisionOf(projectKey);
    return d.isEmpty ? null : of(d, projectKey.toLowerCase());
  }

  /// 매출 예시가 있는 사업부인가 (프로젝트 목록 줄에 띄울 값이 있는지).
  static bool hasRevenue(String divisionId) =>
      (rows[divisionId] ?? const {}).values.any((r) => r.planRevenue > 0);

  // ==== 프로젝트 하나의 주차 현황 보드를 예시로 채운다 ====
  //
  // 사업부 보드는 '구분' 열이 프로젝트지만(division_board_service),
  // 프로젝트 안으로 들어가면 반도체와 똑같이 양산 / 개발 두 줄이다.
  // 서버가 주는 달·주차·마감 주차는 그대로 두고 숫자만 넣는다.
  //
  // 양산 7 : 개발 3 으로 나눈다. 두 줄 다 0 이면 표가 무슨 줄인지
  // 설명이 안 되고, 개발만 있으면 양산 전환 전처럼 보인다.
  static bool fillBoard(String projectKey, Map<String, dynamic> d) {
    final demo = find(projectKey);
    if (demo == null || demo.po <= 0) return false;

    final weeks = (d['weeks'] as List? ?? const []).map((e) => '$e').toList();
    final closed =
        (d['closed_weeks'] as List? ?? const []).map((e) => '$e').toList();
    final rows0 = (d['rows'] as List? ?? const []).cast<Map>();
    if (weeks.isEmpty || rows0.isEmpty) return false;

    const share = [0.7, 0.3];   // 양산 : 개발
    final shortWeeks = <String>[];

    for (var i = 0; i < rows0.length; i++) {
      final sh = share[i % share.length];
      final r = rows0[i];
      final po = (demo.po * sh).round();
      final act = (demo.actual * sh).round();
      r['po_qty'] = po;
      r['actual_total'] = act;
      r['remaining'] = po - act;
      r['prev_month_actual'] = (demo.prev * sh).round();
      r['next_month_plan'] = (demo.nextPlan * sh).round();

      var mPlan = 0;
      var mAct = 0;
      var nthClosed = 0;
      final wk = (r['weeks'] as Map?) ?? const {};
      for (var k = 0; k < weeks.length; k++) {
        final slot = wk[weeks[k]] as Map?;
        if (slot == null) continue;
        final plan = (demo.weekPlan * sh * weekShape[k % weekShape.length]).round();
        var actual = 0;
        if (closed.contains(weeks[k])) {
          actual = (plan * closedRate[nthClosed % closedRate.length]).round();
          if (actual < plan && !shortWeeks.contains(weeks[k])) {
            shortWeeks.add(weeks[k]);
          }
          nthClosed++;
        }
        slot['plan'] = plan;
        slot['actual'] = actual;
        mPlan += plan;
        mAct += actual;
      }
      r['month_plan'] = mPlan;
      r['month_actual'] = mAct;
    }

    // ---- 합계 줄 다시 더하기
    final t = (d['total'] as Map?) ?? {};
    for (final f in const ['po_qty', 'actual_total', 'remaining',
        'prev_month_actual', 'month_plan', 'month_actual', 'next_month_plan']) {
      var sum = 0;
      for (final r in rows0) {
        sum += _i(r[f]);
      }
      t[f] = sum;
    }
    final tw = (t['weeks'] as Map?) ?? const {};
    final shorts = <Map<String, dynamic>>[];
    for (final w in weeks) {
      final slot = tw[w] as Map?;
      if (slot == null) continue;
      var plan = 0;
      var actual = 0;
      for (final r in rows0) {
        final c = ((r['weeks'] as Map?) ?? const {})[w] as Map?;
        plan += _i(c?['plan']);
        actual += _i(c?['actual']);
      }
      slot['plan'] = plan;
      slot['actual'] = actual;
      if (closed.contains(w) && plan > 0 && actual < plan) {
        shorts.add({
          'week': w,
          'plan': plan,
          'actual': actual,
          'short': plan - actual,
          'rate': (actual / plan * 100).round(),
          'kind': '',
          'reason': shortReason,
        });
      }
    }
    d['shortfalls'] = shorts;
    d['demo'] = true;
    return true;
  }

  /// 보드가 통째로 0 인가 (예시를 끼울 자리인지).
  static bool boardIsEmpty(Map<String, dynamic> d) {
    final t = (d['total'] as Map?) ?? const {};
    for (final f in const ['po_qty', 'actual_total', 'month_plan',
        'month_actual']) {
      if (_i(t[f]) != 0) return false;
    }
    final wk = (t['weeks'] as Map?) ?? const {};
    for (final c in wk.values) {
      final m = (c as Map?) ?? const {};
      if (_i(m['plan']) != 0 || _i(m['actual']) != 0) return false;
    }
    return true;
  }

  static int _i(dynamic v) {
    if (v is num) return v.round();
    return int.tryParse('$v') ?? 0;
  }
}
