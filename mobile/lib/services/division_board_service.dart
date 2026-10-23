// ══════════════════════════════════════════════════════════════════
//  사업부 주차 현황 보드 (2026-10-23)
// ══════════════════════════════════════════════════════════════════
//
// 프로젝트 화면의 보드는 '구분' 열이 양산 / 개발 이다.
//   YFP → 양산 · 개발 · 합계
//
// 사업부 화면의 보드는 '구분' 열이 프로젝트다.
//   블룸 → YFP · Corva KPE · 외 5종 · 합계
//
// 어느 프로젝트를 이름으로 세울지는 사람이 고른다(admin). 고르지 않은
// 나머지는 '외 N종' 한 줄로 합친다. 일곱 줄을 다 세우면 어느 것이 중요한
// 프로젝트인지 표가 말해 주지 않기 때문이다.
//
// 서버에는 아직 사업부 단위 보드 API 가 없다. 그래서 프로젝트별 보드
// (/projects/{key}/weekly-board)를 한꺼번에 받아, 각 보드의 '합계' 줄을
// 그 프로젝트의 한 줄로 쓴다. 나중에 서버가 /divisions/{id}/weekly-board
// 를 주면 이 파일만 그 호출로 바꾸면 되고, 화면은 그대로다.
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../config/demo_board.dart';

/// 보드 한 줄이 될 프로젝트.
class BoardProject {
  final String key;
  final String label;

  const BoardProject(this.key, this.label);
}

class DivisionBoardService {
  // ---- 한 줄(프로젝트)에 들어가는 숫자 칸 이름
  static const _flat = [
    'po_qty',
    'actual_total',
    'remaining',
    'prev_month_actual',
    'month_plan',
    'month_actual',
    'next_month_plan',
  ];

  /// 사업부 보드 한 장을 만든다.
  ///
  /// [picked] 가 비어 있으면 프로젝트를 전부 이름으로 세운다.
  /// (아무것도 고르지 않았는데 '외 7종' 한 줄만 뜨면 표가 아무 말도 못 한다)
  static Future<Map<String, dynamic>?> fetch({
    required String divisionId,
    required List<BoardProject> projects,
    List<String> picked = const [],
    String? month,
  }) async {
    if (projects.isEmpty) return null;

    // ---- 프로젝트별 보드를 한꺼번에 받는다
    final boards = await Future.wait(
      projects.map((p) => _one(p.key, month)),
    );

    // ---- 받아진 것만 남긴다 (한 프로젝트가 실패해도 표는 그린다)
    final got = <String, Map<String, dynamic>>{};
    for (var i = 0; i < projects.length; i++) {
      final b = boards[i];
      if (b != null) got[projects[i].key] = b;
    }
    if (got.isEmpty) return null;

    final base = got.values.first;
    final weeks = (base['weeks'] as List? ?? const []).map((e) => '$e').toList();

    // ---- 이름으로 세울 프로젝트 / '외 N종' 으로 합칠 프로젝트
    final named = <BoardProject>[];
    final rest = <BoardProject>[];
    for (final p in projects) {
      if (!got.containsKey(p.key)) continue;
      final isPicked = picked.isEmpty || picked.contains(p.key);
      (isPicked ? named : rest).add(p);
    }

    final rows = <Map<String, dynamic>>[];
    for (final p in named) {
      rows.add(_rowOf(p.label, [got[p.key]!], weeks));
    }
    if (rest.isNotEmpty) {
      rows.add(_rowOf(
        '외 ${rest.length}종',
        rest.map((p) => got[p.key]!).toList(),
        weeks,
      ));
    }

    var total = _rowOf('합계', got.values.toList(), weeks);
    final closed =
        (base['closed_weeks'] as List? ?? const []).map((e) => '$e').toList();

    // ---- 서버가 이 사업부에 0 만 주는 동안에는 보여주기용 예시를 채운다.
    //      숫자 한 개라도 들어오면 이 줄은 저절로 안 타고 진짜 값이 뜬다.
    //      (버릴 코드 — app_config 의 kDemoBoardData 를 false 로 두면 끝)
    var demo = false;
    if (kDemoBoardData &&
        DemoBoard.has(divisionId) &&
        _isAllZero(total)) {
      _fillDemo(divisionId, named, rest, rows, weeks, closed);
      total = _rowOf('합계', const [], weeks);   // 빈 틀에 다시 더한다
      _addInto(total, rows, weeks);
      demo = true;
    }

    return {
      'demo': demo,
      'division_board': true,
      'month': base['month'],
      'weeks': weeks,
      'prev_month': base['prev_month'],
      'next_month': base['next_month'],
      'current_week': base['current_week'],
      'closed_weeks': closed,
      // PO증감은 프로젝트별 이력이라 합치면 뜻이 없어진다 — 비워 둔다.
      'po_delta': const {'months': [], 'weeks': []},
      'rows': rows,
      'total': total,
      'shortfalls': _shortfalls(total, weeks, closed, demo: demo),
      'week_reasons': const {},
    };
  }

  // ==== 프로젝트 보드 한 장 받기 ====
  static Future<Map<String, dynamic>?> _one(String key, String? month) async {
    try {
      final q = (month == null || month.isEmpty)
          ? ''
          : '?month=${Uri.encodeComponent(month)}';
      final res = await http
          .get(Uri.parse(
              '$kApiBaseUrl/projects/${Uri.encodeComponent(key)}/weekly-board$q'))
          .timeout(const Duration(seconds: 10));
      if (res.statusCode != 200) return null;
      final d = jsonDecode(utf8.decode(res.bodyBytes));
      if (d is! Map<String, dynamic> || d['total'] == null) return null;
      return d;
    } catch (_) {
      return null;
    }
  }

  // ==== 보드 여러 장의 '합계' 줄을 더해 한 줄로 ====
  //
  // 프로젝트 보드의 total 이 그 프로젝트의 양산+개발 합이다. 그래서
  // total 만 더하면 프로젝트 한 줄이 되고, 여럿을 더하면 '외 N종' 이 된다.
  static Map<String, dynamic> _rowOf(
      String label, List<Map<String, dynamic>> boards, List<String> weeks) {
    final row = <String, dynamic>{'label': label};
    for (final f in _flat) {
      row[f] = 0;
    }
    final wk = <String, Map<String, dynamic>>{};
    for (final w in weeks) {
      wk[w] = {'plan': 0, 'actual': 0, 'closed': false};
    }

    for (final b in boards) {
      final t = (b['total'] as Map?) ?? const {};
      for (final f in _flat) {
        row[f] = (row[f] as int) + _i(t[f]);
      }
      final tw = (t['weeks'] as Map?) ?? const {};
      for (final w in weeks) {
        final c = (tw[w] as Map?) ?? const {};
        final slot = wk[w]!;
        slot['plan'] = (slot['plan'] as int) + _i(c['plan']);
        slot['actual'] = (slot['actual'] as int) + _i(c['actual']);
        // 한 프로젝트라도 마감된 주면 마감으로 본다 (주차 마감은 달력이다)
        if (c['closed'] == true) slot['closed'] = true;
      }
    }

    row['weeks'] = wk;
    return row;
  }

  // ==== 미달: 마감된 주인데 합계 실적이 합계 계획에 못 미친 주 ====
  //
  // 사유는 프로젝트마다 적는 것이라 사업부 합계에는 붙일 사유가 없다.
  // 비워 두면 화면에 '사유 미입력' 으로 뜬다 — 지어내지 않는다.
  static List<Map<String, dynamic>> _shortfalls(
      Map<String, dynamic> total, List<String> weeks, List<String> closed,
      {bool demo = false}) {
    final out = <Map<String, dynamic>>[];
    final tw = (total['weeks'] as Map?) ?? const {};
    for (final w in weeks) {
      if (!closed.contains(w)) continue;
      final c = (tw[w] as Map?) ?? const {};
      final plan = _i(c['plan']);
      final act = _i(c['actual']);
      if (plan <= 0 || act >= plan) continue;
      out.add({
        'week': w,
        'plan': plan,
        'actual': act,
        'short': plan - act,
        'rate': (act / plan * 100).round(),
        'kind': '',
        'reason': demo ? DemoBoard.shortReason : '',
      });
    }
    return out;
  }

  // ==== 전부 0 인가 ====
  static bool _isAllZero(Map<String, dynamic> row) {
    for (final f in _flat) {
      if ((row[f] as int? ?? 0) != 0) return false;
    }
    final wk = (row['weeks'] as Map?) ?? const {};
    for (final c in wk.values) {
      final m = (c as Map?) ?? const {};
      if (_i(m['plan']) != 0 || _i(m['actual']) != 0) return false;
    }
    return true;
  }

  // ==== 줄들을 하나로 더한다 (합계 다시 만들기) ====
  static void _addInto(Map<String, dynamic> total,
      List<Map<String, dynamic>> rows, List<String> weeks) {
    for (final r in rows) {
      for (final f in _flat) {
        total[f] = (total[f] as int) + (r[f] as int? ?? 0);
      }
      final rw = (r['weeks'] as Map?) ?? const {};
      final tw = (total['weeks'] as Map?) ?? const {};
      for (final w in weeks) {
        final src = (rw[w] as Map?) ?? const {};
        final dst = tw[w] as Map?;
        if (dst == null) continue;   // const {} 에 쓰면 터진다
        dst['plan'] = _i(dst['plan']) + _i(src['plan']);
        dst['actual'] = _i(dst['actual']) + _i(src['actual']);
        if (src['closed'] == true) dst['closed'] = true;
      }
    }
  }

  // ==== 보여주기용 예시 숫자 채우기 (버릴 코드) ====
  //
  // 서버가 주는 달·주차·마감 주차는 그대로 두고 숫자만 넣는다. 그래서
  // 달이 바뀌면 예시도 그 달 주차로 따라 움직인다.
  //
  // 마감된 주는 실적을 채우고(두 번째 마감 주차는 일부러 계획에 못 미치게
  // 둬서 미달 표시와 사유가 어떻게 보이는지 같이 보여준다), 아직 안 온
  // 주는 실적을 0 으로 둔다 — 화면이 그걸 가운뎃점으로 그린다.
  static void _fillDemo(
      String divisionId,
      List<BoardProject> named,
      List<BoardProject> rest,
      List<Map<String, dynamic>> rows,
      List<String> weeks,
      List<String> closed) {
    List<DemoRow> pick(List<BoardProject> ps) => [
          for (final p in ps)
            DemoBoard.of(divisionId, p.key) ??
                const DemoRow(po: 0, actual: 0, prev: 0, weekPlan: 0,
                    nextPlan: 0),
        ];

    // rows 는 [이름 세운 프로젝트…] + (있으면) [외 N종] 순서다
    final groups = <List<DemoRow>>[
      for (final p in named) pick([p]),
      if (rest.isNotEmpty) pick(rest),
    ];

    for (var i = 0; i < rows.length && i < groups.length; i++) {
      final g = groups[i];
      final po = g.fold<int>(0, (a, d) => a + d.po);
      final act = g.fold<int>(0, (a, d) => a + d.actual);
      final wp = g.fold<int>(0, (a, d) => a + d.weekPlan);
      final row = rows[i];
      row['po_qty'] = po;
      row['actual_total'] = act;
      row['remaining'] = po - act;
      row['prev_month_actual'] = g.fold<int>(0, (a, d) => a + d.prev);
      row['next_month_plan'] = g.fold<int>(0, (a, d) => a + d.nextPlan);

      var mPlan = 0;
      var mAct = 0;
      var nthClosed = 0;
      final wk = (row['weeks'] as Map?) ?? const {};
      for (var k = 0; k < weeks.length; k++) {
        final w = weeks[k];
        final slot = wk[w] as Map?;
        if (slot == null) continue;   // const {} 에 쓰면 터진다
        final shape = DemoBoard.weekShape[k % DemoBoard.weekShape.length];
        final plan = (wp * shape).round();
        var actual = 0;
        if (closed.contains(w)) {
          final rate = DemoBoard
              .closedRate[nthClosed % DemoBoard.closedRate.length];
          actual = (plan * rate).round();
          nthClosed++;
        }
        slot['plan'] = plan;
        slot['actual'] = actual;
        mPlan += plan;
        mAct += actual;
      }
      row['month_plan'] = mPlan;
      row['month_actual'] = mAct;
    }
  }

  static int _i(dynamic v) {
    if (v is num) return v.round();
    return int.tryParse('$v') ?? 0;
  }
}
