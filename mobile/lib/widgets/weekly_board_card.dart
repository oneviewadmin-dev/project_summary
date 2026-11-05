// 주차 현황 보드 (하바플레이트).
//
// 예전에는 엑셀 원본을 PNG 로 올려 이미지로 보여줬는데, 이제 admin 에서
// 같은 표를 데이터로 계산해 그린다. 앱도 그 계산 결과(/weekly-board)를 그대로 받아
// 동일한 모양으로 그린다.
//
// 열이 17개라 가로 스크롤이 필요하다. 열마다 폭을 고정하고, 각 열을 Column 으로
// 세워서 행 높이를 맞춘다. (Table 위젯은 셀 병합이 안 돼서 3단 머리글을 못 만든다)
import '../services/offline_store.dart';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../config/demo_board.dart';
import 'plan_actual.dart';

const double _kHeadH = 22;   // 머리글 한 줄 (x3 = 표 머리글 전체 높이)
const double _kRowH = 52;    // 데이터 행 (양산 / 개발)
const double _kTotalH = 32;  // 합계 행
const double _kSecRowH = 38; // 섹션형 데이터 행 (행이 많아 낮게)
// 계획·실적 두 칸 중 한 칸의 최소 폭. 숫자가 길면 _pairHalfW 가 늘린다.
const double _kPairHalfMin = 42;

const Color _navy = Color(0xFF0F2C59);
const Color _line = Color(0xFFE5E7EB);
const Color _red = Color(0xFFDC2626);

// 이번 달 주차 묶음은 선으로 끊지 않고 색으로 묶는다.
// 선을 그으면 남색 머리글 위에서는 안 보이거나 구멍처럼 보인다.
const Color _navyGroup = Color(0xFF1E4A80);  // 묶음 머리글 (기본보다 밝은 남색)
const Color _groupTint = Color(0xFFF4F8FE);  // 묶음 데이터 칸 (아주 옅은 파랑)
const Color _gridV = Color(0xFFEDF1F6);      // 세로 격자 (거의 안 보이게)
const Color _gridH = Color(0xFFE6EBF1);      // 가로 격자
const Color _headLine = Color(0xFF2A4C7A);   // 남색 칸끼리의 경계
const Color _zeroInk = Color(0xFFC2CBD8);    // 0 · 빈 값은 죽인다

/// 표 칸 하나. 숫자만으로는 '계획에 못 미친 칸' 을 말할 수 없다.
class _BCell {
  final String text;

  /// 마감된 주차인데 실적이 계획에 못 미쳤다
  final bool short;

  const _BCell(this.text, {this.short = false});
}

class WeeklyBoardCard extends StatefulWidget {
  /// 프로젝트 하나의 보드를 서버에서 받아 그린다.
  /// [loader] 를 주면 이 값은 쓰지 않는다.
  final String? projectKey;
  final String? month;

  /// 카드 머리글. 안 주면 '주차 현황 보드'.
  final String? title;

  /// 표를 그릴 자료를 직접 만들어 넘기는 길.
  ///
  /// 사업부 화면은 프로젝트 하나가 아니라 '프로젝트들' 을 한 표에 세운다
  /// (구분 열 = YFP · Corva KPE · 외 5종). 서버에 그런 API 가 아직 없어서
  /// 앱이 프로젝트별 보드를 받아 합쳐 만든다 — 그 결과를 여기로 넣는다.
  /// 표를 그리는 코드는 하나뿐이라 모양은 프로젝트 보드와 똑같다.
  ///
  /// 2026-11-04 — 달을 고를 수 있게 되면서 고른 달을 넘겨 받는다.
  final Future<Map<String, dynamic>?> Function(String month)? loader;

  const WeeklyBoardCard({
    super.key,
    this.projectKey,
    this.month,
    this.title,
    this.loader,
  }) : assert(projectKey != null || loader != null,
            'projectKey 나 loader 중 하나는 있어야 한다');

  @override
  State<WeeklyBoardCard> createState() => _WeeklyBoardCardState();
}

class _WeeklyBoardCardState extends State<WeeklyBoardCard> {
  late Future<Map<String, dynamic>?> _future;

  /// 보고 있는 달 'YYYY-MM'. 머리글의 달 고르기로 바꾼다 (2026-11-04).
  late String _month;

  @override
  void initState() {
    super.initState();
    final m = widget.month ?? '';
    _month = m.isNotEmpty ? m : thisMonthKey();
    _future = _fetch();
  }

  void _setMonth(String m) {
    if (m == _month) return;
    setState(() {
      _month = m;
      _future = _fetch();
    });
  }

  Future<Map<String, dynamic>?> _fetch() async {
    // 사업부 보드처럼 자료를 직접 만들어 넣는 경우
    if (widget.loader != null) return widget.loader!(_month);
    try {
      final q = '?month=${Uri.encodeComponent(_month)}';
      final res = await OfflineStore
          .httpGet(Uri.parse('$kApiBaseUrl/projects/${Uri.encodeComponent(widget.projectKey!)}/weekly-board$q'))
          .timeout(const Duration(seconds: 10));
      if (res.statusCode != 200) return null;
      final d = jsonDecode(utf8.decode(res.bodyBytes));
      if (d is! Map<String, dynamic> || d['rows'] == null) return null;
      // 숫자가 하나도 없는 사업부(블룸·자동차)는 보여주기용 예시를 채운다.
      // 엑셀이 올라와 숫자가 들어오면 이 줄은 안 탄다. (버릴 코드 —
      // app_config 의 kDemoBoardData 를 false 로)
      if (kDemoBoardData && DemoBoard.boardIsEmpty(d)) {
        DemoBoard.fillBoard(widget.projectKey ?? '', d);
      }
      return d;
    } catch (_) {
      return null;
    }
  }

  String _n(dynamic v) {
    final i = (v is num) ? v.round() : int.tryParse('$v');
    if (i == null) return '-';
    final s = i.abs().toString();
    final b = StringBuffer();
    for (var k = 0; k < s.length; k++) {
      if (k > 0 && (s.length - k) % 3 == 0) b.write(',');
      b.write(s[k]);
    }
    return (i < 0 ? '-' : '') + b.toString();
  }

  /// 주차 칸 하나를 [계획, 실적] 두 칸으로.
  ///
  /// 2026-11-04 — Min: "계획이랑 실적 적힌거 색깔 다르게 해서 다 표기해주고"
  /// 전에는 아직 안 온 주의 실적을 가운뎃점(·)으로 비우고 0 을 회색으로
  /// 죽였다. 이제 모든 칸에 숫자를 적고, 계획은 파랑 · 실적은 초록으로
  /// 가른다. 미달 표시(▼)는 마감된 주에만 붙으니 0 이 미달로 읽히지 않는다.
  List<_BCell> _weekPair(dynamic cell, String week, String nowWeek) {
    final m = (cell is Map) ? cell : const {};
    final short = (m['short'] is num) && (m['short'] as num) > 0;
    return [
      _BCell(_n(m['plan'] ?? 0)),
      _BCell(_n(m['actual'] ?? 0), short: short),
    ];
  }

  String _mon(String? ym) {
    if (ym == null || !ym.contains('-')) return '';
    final m = int.tryParse(ym.split('-')[1]);
    return m == null ? '' : '$m월';
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>?>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState == ConnectionState.waiting) {
          return _shell(const SizedBox(
            height: 90,
            child: Center(child: SizedBox(
                width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))),
          ));
        }
        final d = snap.data;
        if (d == null) {
          // 서버가 아직 보드 API 를 모르면 조용히 사라지지 말고 한 줄로 알린다
          return _shell(const Text('주차 현황을 불러오지 못했습니다',
              style: TextStyle(fontSize: 12, color: Color(0xFF9CA3AF))));
        }
        final demo = d['demo'] == true;
        return _shell(
          _boardBody(d),
          demo: demo,
        );
      },
    );
  }

  /// 카드 안에 들어가는 표와 그 밑 설명. (예시 딱지는 _shell 이 붙인다)
  Widget _boardBody(Map<String, dynamic> d) {
    return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // 표 폭이 화면보다 훨씬 넓다(약 980px). 가로 스크롤만으로는
              // 오른쪽에 주차가 더 있다는 걸 모른다. 오른쪽 끝을 흐리게 해서
              // 이어진다는 걸 보이고, 탭하면 전체를 확대해서 본다.
              // 표를 어떻게 읽어야 하는지 서버가 한 줄로 적어 보내면 맨 위에
              // 단다. 블룸이 그런 경우다 — 합계가 공정을 다 더한 값이라
              // 출하량이 아닌데, 안 적으면 '72대 나갔다' 로 읽힌다.
              _boardNote(d),
              const Padding(
                padding: EdgeInsets.only(bottom: 8),
                child: PlanActualLegend(),
              ),
              Stack(
                children: [
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: _table(d),
                  ),
                  Positioned(
                    top: 0,
                    bottom: 0,
                    right: 0,
                    child: IgnorePointer(
                      child: Container(
                        width: 22,
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.centerRight,
                            end: Alignment.centerLeft,
                            colors: [
                              Colors.white,
                              Colors.white.withValues(alpha: 0),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
              _shortfallNote(d),
              const SizedBox(height: 10),
              InkWell(
                onTap: () => _openZoom(d),
                borderRadius: BorderRadius.circular(8),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 5, horizontal: 6),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: const [
                      Icon(Icons.zoom_out_map_rounded,
                          size: 15, color: Color(0xFF156082)),
                      SizedBox(width: 5),
                      Text('전체 크게 보기',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF156082),
                          )),
                    ],
                  ),
                ),
              ),
            ],
    );
  }

  // ── 표 위: 이 표를 어떻게 읽나 (서버가 적어 보낼 때만) ───────────
  Widget _boardNote(Map<String, dynamic> d) {
    final t = '${d['note'] ?? ''}'.trim();
    if (t.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 9),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.info_outline_rounded,
              size: 13, color: Color(0xFF9CA3AF)),
          const SizedBox(width: 5),
          Expanded(
            child: Text(t,
                style: const TextStyle(
                    fontSize: 11, height: 1.45, color: Color(0xFF6B7280))),
          ),
        ],
      ),
    );
  }

  // ── 표 밑: 계획에 못 미친 주와 그 사유 ───────────────────────────
  //
  // 표에서는 합계 칸이 빨갛게 ▼ 로 '어느 주가' 를 말하고, 여기서 '왜' 를
  // 말한다. 미달은 합계 기준이다 — 품목별로 따지지 않는다.
  // 미달이 늘 문제인 것은 아니다 — 엔클로저는 매출을 맞추려고 일부러 덜
  // 출하하기도 한다. 그런 주는 admin 에서 '참고' 로 적어 두면 회색으로
  // 내려가고 문제로 세지 않는다. 아무것도 안 적혀 있으면 '사유 미입력'.
  /// 2026-10-26 — 보드 밑의 '계획 미달' 칸은 안 그린다.
  ///
  /// 표에서 이미 합계 칸이 빨갛게 ▼ 로 어느 주가 모자랐는지 말한다.
  /// 그 밑에 같은 주를 또 상자로 늘어놓으니, 주차가 셋만 모자라도
  /// 보드보다 그 칸이 길어져서 정작 표를 못 봤다.
  ///
  /// 지우지 않고 끈다. 사유를 다시 띄우려면 false 로 두면 된다.
  final bool _hideShortfall = true;

  Widget _shortfallNote(Map<String, dynamic> d) {
    if (_hideShortfall) return const SizedBox.shrink();
    final shorts = (d['shortfalls'] as List? ?? const []).cast<Map>();
    if (shorts.isEmpty) {
      final closed = (d['closed_weeks'] as List? ?? const []);
      if (closed.isEmpty) return const SizedBox.shrink();
      return Padding(
        padding: const EdgeInsets.only(top: 10),
        child: Row(children: [
          const Icon(Icons.check_circle_outline,
              size: 14, color: Color(0xFF059669)),
          const SizedBox(width: 5),
          Text('마감된 ${closed.length}개 주차 모두 계획을 채웠습니다',
              style: const TextStyle(fontSize: 11.5, color: Color(0xFF059669))),
        ]),
      );
    }

    // 주차별로 묶는다. 사유는 주 단위로 적는다.
    final byWeek = <String, List<Map>>{};
    for (final e in shorts) {
      byWeek.putIfAbsent('${e['week']}', () => []).add(e);
    }
    final weeks = byWeek.keys.toList()..sort();

    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Icon(Icons.trending_down_rounded, size: 14, color: Color(0xFF991B1B)),
          SizedBox(width: 5),
          Text('계획 미달',
              style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF991B1B))),
        ]),
        for (final w in weeks) _shortWeekBlock(w, byWeek[w]!),
      ]),
    );
  }

  Widget _shortWeekBlock(String week, List<Map> items) {
    final kind = '${items.first['kind'] ?? ''}';
    final reason = '${items.first['reason'] ?? ''}'.trim();
    final isNote = kind == '참고';
    final tint = isNote ? const Color(0xFF6B7280) : const Color(0xFF991B1B);
    final soft = isNote ? const Color(0xFFF3F4F6) : const Color(0xFFFEE2E2);
    return Container(
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.fromLTRB(10, 8, 10, 9),
      decoration: BoxDecoration(
        color: isNote ? const Color(0xFFFAFBFC) : const Color(0xFFFFF7F7),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
            color: isNote ? _line : const Color(0xFFFCA5A5)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text(week,
              style: const TextStyle(
                  fontSize: 11.5,
                  fontWeight: FontWeight.w800,
                  color: Color(0xFF0F172A))),
          const SizedBox(width: 6),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
            decoration: BoxDecoration(
                color: soft, borderRadius: BorderRadius.circular(6)),
            child: Text(reason.isEmpty ? '사유 미입력' : kind,
                style: TextStyle(
                    fontSize: 9.5, fontWeight: FontWeight.w800, color: tint)),
          ),
        ]),
        for (final e in items)
          Padding(
            padding: const EdgeInsets.only(top: 3),
            child: Text(
                '합계 ${e['plan']} → ${e['actual']}'
                '  (${e['short']}대 부족 · ${e['rate']}%)',
                style: const TextStyle(
                    fontSize: 11, height: 1.3, color: Color(0xFF4B5563))),
          ),
        Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Text(
              reason.isEmpty ? '왜 못 채웠는지 아직 적히지 않았습니다' : reason,
              style: TextStyle(
                  fontSize: 11.5,
                  height: 1.35,
                  fontStyle: reason.isEmpty ? FontStyle.italic : FontStyle.normal,
                  color: reason.isEmpty
                      ? const Color(0xFF9CA3AF)
                      : const Color(0xFF111827))),
        ),
      ]),
    );
  }

  // 표 전체를 화면 가득 펼쳐 손가락으로 확대·이동해 본다.
  // 폰을 가로로 눕히면 주차가 거의 다 들어온다.
  void _openZoom(Map<String, dynamic> d) {
    showDialog<void>(
      context: context,
      barrierColor: Colors.black.withValues(alpha: 0.82),
      builder: (ctx) => Dialog.fullscreen(
        backgroundColor: const Color(0xFFF8FAFC),
        child: SafeArea(
          child: Column(
            children: [
              Row(
                children: [
                  const SizedBox(width: 16),
                  Expanded(
                    child: Text('${widget.title ?? '주차 현황 보드'} · ${monthLabel(_month)}',
                        style: const TextStyle(
                            fontSize: 15, fontWeight: FontWeight.w800)),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close_rounded),
                    onPressed: () => Navigator.of(ctx).pop(),
                  ),
                ],
              ),
              const Padding(
                padding: EdgeInsets.fromLTRB(16, 0, 16, 8),
                child: Row(
                  children: [
                    Icon(Icons.pinch_rounded, size: 13, color: Color(0xFF9CA3AF)),
                    SizedBox(width: 5),
                    Expanded(
                      child: Text('손가락으로 확대·이동할 수 있어요. 폰을 눕히면 더 넓게 보입니다.',
                          style: TextStyle(
                              fontSize: 11.5, color: Color(0xFF6B7280))),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: InteractiveViewer(
                  constrained: false,
                  minScale: 0.4,
                  maxScale: 4.0,
                  boundaryMargin: const EdgeInsets.all(120),
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: _table(d),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _shell(Widget child, {bool demo = false}) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: _line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Text(widget.title ?? '주차 현황 보드',
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
            // 지어낸 숫자로 그린 표라는 걸 표에 붙여 둔다. 이 딱지가 없으면
            // 회의실에서 진짜 실적으로 읽힌다 — 떼면 안 된다.
            if (demo) ...[
              const SizedBox(width: 7),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                decoration: BoxDecoration(
                  color: const Color(0xFFFFF7ED),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: const Color(0xFFFDBA74)),
                ),
                child: const Text('예시',
                    style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w800,
                        color: Color(0xFF9A3412))),
              ),
            ],
            const Spacer(),
            // 달 고르기 — 불러오는 동안에도 그대로 둔다
            MonthPickerPill(month: _month, onChanged: _setMonth),
          ]),
          if (demo)
            const Padding(
              padding: EdgeInsets.only(top: 4),
              child: Text('지어낸 숫자입니다. 실제 실적이 아닙니다 — 엑셀이 올라오면 바뀝니다.',
                  style: TextStyle(fontSize: 11, color: Color(0xFF9A3412))),
            ),
          const SizedBox(height: 10),
          child,
        ],
      ),
    );
  }

  // ── 표 ────────────────────────────────────────────────────────────
  // 백엔드가 두 가지 모양을 돌려준다.
  //   layout: 'sections'  프로젝트별 행 구성 (챔버 — 기존/내재화/Dep 챔버)
  //   그 외                양산/개발 두 줄 + 주차 (하바플레이트)
  Widget _table(Map<String, dynamic> d) {
    final t = (d['layout'] ?? '') == 'sections'
        ? _sectionTable(d)
        : _weekTable(d);
    // 각진 표 하나가 카드 안에 박혀 있으면 붙여 넣은 것처럼 보인다.
    // 카드와 같은 곡률로 깎고 바깥선을 한 겹 두른다.
    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: _line),
        ),
        child: t,
      ),
    );
  }

  // ── 섹션형 (구분 | 행 | 현황 | PO | 실적 | 잔량 | 월… | 비고) ──────
  Widget _sectionTable(Map<String, dynamic> d) {
    final byWeek = (d['columns'] ?? 'month') == 'week';
    final months = (d['months'] as List? ?? const []).map((e) => '$e').toList();
    final weeks = (d['weeks'] as List? ?? const []).map((e) => '$e').toList();
    final nowMon = (d['current_month'] ?? '').toString();  // 이번 달 = 빨간 테두리
    final nowWeek = (d['current_week'] ?? '').toString();  // 이번 주차 = 빨간 테두리
    final showStatus = d['show_status'] != false;
    final sections = (d['sections'] as List? ?? const []).cast<Map>();
    final total = (d['total'] as Map?) ?? const {};

    final flat = <Map>[];
    for (final sec in sections) {
      flat.addAll((sec['rows'] as List? ?? const []).cast<Map>());
    }
    // 비고 열: 프로젝트가 끄지 않았고(show_note) 실제로 적힌 게 있을 때만 그린다
    final hasNote = d['show_note'] != false &&
        flat.any((r) => '${r['note'] ?? ''}'.trim().isNotEmpty);
    // 섹션 이름이 하나도 없으면(파워박스처럼 평면) 구분 열을 따로 두지 않고
    // 행 이름 열의 머리글을 '구분'으로 쓴다.
    final hasSec = sections.any((s) => '${s['name'] ?? ''}'.trim().isNotEmpty);

    // 주차 모드는 머리글이 3단(월 / 주차 / 계획·실적), 월 모드는 2단이다.
    final headSpan = byWeek ? 3 : 2;

    List<String> col(String f) => [...flat.map((r) => _n(r[f])), _n(total[f])];

    // ── 서버가 빼라고 적어 보낸 열 (블룸 · ESS — 일 보고에 없는 숫자)
    //    자세한 까닭은 _weekTable 의 같은 자리에 적어 두었다.
    final hide =
        (d['hide_cols'] as List? ?? const []).map((e) => '$e').toSet();
    bool show(String c) => !hide.contains(c);

    // 계획·실적 칸 폭 (주차형일 때만 쓰인다)
    final pairW = _pairHalfW([
      for (final w in weeks) ...[
        for (final r in flat) _weekPair((r['weeks'] as Map?)?[w], w, nowWeek),
        _weekPair((total['weeks'] as Map?)?[w], w, nowWeek),
      ],
      for (final r in flat)
        [_BCell(_n(r['month_plan'])), _BCell(_n(r['month_actual']))],
      [_BCell(_n(total['month_plan'])), _BCell(_n(total['month_actual']))],
    ]);

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 구분 — 섹션 이름을 한 칸으로 묶어 세로로 이어 보이게 한다
        if (hasSec)
          SizedBox(
            // 2026-10-25 — 74 였다. ESS 품목 이름이 'SBB 1.5 (한국 함안)'
            // 처럼 길어서 두 줄로도 잘렸다.
            width: 104,
            child: Column(
              children: [
                _cell('구분', _kHeadH * headSpan, head: true, align: TextAlign.left),
                for (final sec in sections)
                  // 재고가 있으면 이름 밑에 한 줄 더 (프레임 'CEFEM BE / 재고 79')
                  _cell(
                      sec['stock'] == null
                          ? '${sec['name']}'
                          : '${sec['name']}\n재고 ${sec['stock']}',
                      _kSecRowH * ((sec['rows'] as List? ?? const []).length),
                      align: TextAlign.left, bold: true, size: 10,
                      maxLines: 3),
                _cell('', _kTotalH, total: true),
              ],
            ),
          ),
        SizedBox(
          width: hasSec ? 84 : 96,
          child: Column(
            children: [
              _cell(hasSec ? '' : '구분', _kHeadH * headSpan,
                  head: true, align: TextAlign.left),
              for (final r in flat)
                _cell('${r['label']}', _kSecRowH,
                    align: TextAlign.left, bold: true, size: 10.5),
              _cell('${d['total_label'] ?? '합계'}', _kTotalH,
                  total: true, align: TextAlign.left),
            ],
          ),
        ),
        if (showStatus)
          SizedBox(
            width: 52,
            child: Column(
              children: [
                _cell('현황', _kHeadH * headSpan, head: true),
                for (final r in flat) _cell('${r['status'] ?? ''}', _kSecRowH, size: 10),
                _cell('', _kTotalH, total: true),
              ],
            ),
          ),
        if (show('po_qty'))
          _numCol2('PO 수량', col('po_qty'), 62, span: headSpan),
        _numCol2('실적', col('actual_total'), 56, span: headSpan),
        if (show('remaining'))
          _numCol2('잔량', col('remaining'), 56, span: headSpan),
        // ── 재고 열 — 서버가 적어 보낼 때만 (블룸 · ESS)
        //    공정재고는 공정마다, 출하대기 · 구매품대기는 품목마다 한 번.
        for (final c in (d['stock_cols'] as List? ?? const []).cast<Map>())
          _numCol2('${c['label'] ?? ''}', col('${c['field']}'), 50,
              span: headSpan),
        for (final mon in months)
          _numCol2(
            _mon(mon),
            [
              ...flat.map((r) => _n(((r['months'] as Map?)?[mon] as Map?)?['plan'])),
              _n(((total['months'] as Map?)?[mon] as Map?)?['plan']),
            ],
            52,
            isNow: mon == nowMon,
            span: headSpan,
          ),
        if (byWeek) ...[
          if (show('prev_month_actual'))
            _numCol2(_mon('${d['prev_month']}'), col('prev_month_actual'), 46,
                span: headSpan),
          // 주차 묶음 — 위에 달을 얹고, 선 대신 색으로 묶는다.
          IntrinsicWidth(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _cell(_mon('${d['month']}'), _kHeadH, head: true, group: true),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    for (final w in weeks)
                      _secPairCol(w, [
                        ...flat.map((r) =>
                            _weekPair((r['weeks'] as Map?)?[w], w, nowWeek)),
                        _weekPair((total['weeks'] as Map?)?[w], w, nowWeek),
                      ], w == nowWeek,
                          titleH: _kHeadH, group: true, halfW: pairW),
                  ],
                ),
              ],
            ),
          ),
          _secPairCol('${_mon('${d['month']}')} 합계', [
            ...flat.map((r) =>
                [_BCell(_n(r['month_plan'])), _BCell(_n(r['month_actual']))]),
            [_BCell(_n(total['month_plan'])), _BCell(_n(total['month_actual']))],
          ], false, halfW: pairW),
          if (show('next_month_plan') &&
              (d['next_month'] ?? '').toString().isNotEmpty)
            _numCol2(_mon('${d['next_month']}'), col('next_month_plan'), 46,
                span: headSpan),
        ],
        if (hasNote)
          SizedBox(
            // 메모가 한두 줄짜리 문장이라 150 이면 대부분 잘렸다.
            width: 190,
            child: Column(
              children: [
                _cell('비고', _kHeadH * headSpan, head: true),
                for (final r in flat)
                  _cell('${r['note'] ?? ''}', _kSecRowH,
                      align: TextAlign.left, size: 9.5, maxLines: 3),
                _cell('', _kTotalH, total: true),
              ],
            ),
          ),
      ],
    );
  }

  // 섹션형 머리글은 2단이라 별도 (주차형은 3단)
  // isNow = 이번 달 열. 주차형의 이번 주차와 같게 빨간 테두리를 두른다.
  Widget _numCol2(String title, List<String> values, double w,
      {bool isNow = false, int span = 2}) {
    return Container(
      width: w,
      decoration: isNow
          ? const BoxDecoration(
              border: Border(
                left: BorderSide(color: _red, width: 2),
                right: BorderSide(color: _red, width: 2),
              ),
            )
          : null,
      child: Column(
        children: [
          _cell(title, _kHeadH * span, head: true, redHead: isNow),
          for (var i = 0; i < values.length - 1; i++)
            _cell(values[i], _kSecRowH, tint: isNow),
          _cell(values.last, _kTotalH, total: true, redHead: isNow),
        ],
      ),
    );
  }

  // 섹션형의 계획/실적 두 칸 열 (머리글 3단: 제목 / 주차 / 계획·실적)
  Widget _secPairCol(String title, List<List<_BCell>> values, bool isNow,
      {double titleH = _kHeadH * 2, bool group = false, double? halfW}) {
    return Container(
      width: math.max(76.0, (halfW ?? _kPairHalfMin) * 2),
      decoration: isNow
          ? const BoxDecoration(
              border: Border(
                left: BorderSide(color: _red, width: 2),
                right: BorderSide(color: _red, width: 2),
              ),
            )
          : null,
      child: Column(
        children: [
          _cell(title, titleH, head: true, redHead: isNow, group: group),
          Row(children: [
            Expanded(child: _cell('계획', _kHeadH,
                head: true, redHead: isNow, group: group, role: 'plan')),
            Expanded(child: _cell('실적', _kHeadH,
                head: true, redHead: isNow, group: group, role: 'actual')),
          ]),
          for (var i = 0; i < values.length - 1; i++)
            Row(children: [
              Expanded(child: _cell(values[i][0].text, _kSecRowH,
                  tint: isNow, group: group, role: 'plan')),
              Expanded(child: _cell(values[i][1].text, _kSecRowH,
                  tint: isNow, group: group, short: values[i][1].short,
                  role: 'actual')),
            ]),
          Row(children: [
            Expanded(child: _cell(values.last[0].text, _kTotalH,
                total: true, redHead: isNow, role: 'plan')),
            Expanded(child: _cell(values.last[1].text, _kTotalH,
                total: true, redHead: isNow, short: values.last[1].short,
                role: 'actual')),
          ]),
        ],
      ),
    );
  }

  Widget _weekTable(Map<String, dynamic> d) {
    final weeks = (d['weeks'] as List? ?? const []).map((e) => '$e').toList();
    final now = (d['current_week'] ?? '').toString();
    final rows = (d['rows'] as List? ?? const []).cast<Map>();
    final total = (d['total'] as Map?) ?? const {};
    final delta = (d['po_delta'] as Map?) ?? const {};

    // ── 그리지 말라고 서버가 찍어 보낸 열 (2026-10-25)
    //
    // 사업부마다 들어오는 자료가 다르다. 블룸 일 보고에는 PO 수량도,
    // 잔량도, 다음달 계획도 없다. 전에는 그런 열에 0 이 찍혔는데,
    // 0 은 화면에서 'PO 가 0개' 로 읽힌다 — 사실은 '그런 숫자를 안 받는다'
    // 이다. '-' 로 둬도 빈 열이 네 개 서서 표가 넓어지기만 한다.
    //
    // 그래서 서버가 hide_cols 로 열 이름을 적어 보내면 그 열은 아예 안
    // 그린다. 적어 보내지 않으면(반도체·자동차) 지금까지와 똑같다.
    final hide = (d['hide_cols'] as List? ?? const [])
        .map((e) => '$e')
        .toSet();
    bool show(String col) => !hide.contains(col);

    List<String> col(String field) => [
          ...rows.map((r) => _n(r[field])),
          _n(total[field]),
        ];

    // PO증감은 양산·개발 두 행에 걸친 한 칸이라 이력이 쌓이면 넘친다.
    // 글자를 잘라내는 대신 데이터 행 높이를 이력에 맞춰 늘린다.
    final nRows = rows.isEmpty ? 1 : rows.length;
    // PO증감 열을 안 그리면 그만큼 줄을 늘릴 이유도 없다.
    final rowH = show('po_delta')
        ? math.max(_kRowH, _deltaNeedH(delta) / nRows)
        : _kRowH;
    final monLabel = _mon(d['month'] as String?);
    // 계획·실적 칸은 표 안에서 가장 긴 숫자에 맞춰 한꺼번에 넓힌다.
    final pairW = _pairHalfW([
      for (final w in weeks) ...[
        for (final r in rows) _weekPair((r['weeks'] as Map?)?[w], w, now),
        _weekPair((total['weeks'] as Map?)?[w], w, now),
      ],
      for (final r in rows)
        [_BCell(_n(r['month_plan'])), _BCell(_n(r['month_actual']))],
      [_BCell(_n(total['month_plan'])), _BCell(_n(total['month_actual']))],
    ]);

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _labelCol(rows, rowH, totalLabel: '${d['total_label'] ?? '합계'}'),
        if (show('po_qty')) _numCol('PO 수량', col('po_qty'), 62, rowH),
        _numCol('실적', col('actual_total'), 58, rowH),
        // ── 재고 열 — 서버가 적어 보낼 때만 그린다 (블룸 · ESS)
        //
        // 공정재고는 공정마다 적혀 와서 줄마다 값이 있고, 출하대기 ·
        // 구매품대기는 품목 단위라 합계 줄에만 값이 있다. 값이 없는 칸은
        // _n 이 '-' 로 그린다 — 0 으로 채우면 '대기 없음' 으로 읽힌다.
        for (final c in (d['stock_cols'] as List? ?? const []).cast<Map>())
          _numCol('${c['label'] ?? ''}', col('${c['field']}'), 50, rowH),
        if (show('remaining')) _numCol('잔량', col('remaining'), 54, rowH),
        if (show('prev_month_actual'))
          _numCol(_mon(d['prev_month'] as String?), col('prev_month_actual'), 46,
              rowH),
        // 주차는 어느 달 것인지 한 줄 얹고, 앞뒤를 굵은 선으로 끊는다.
        _weekGroup(monLabel, weeks, rows, total, now, rowH, pairW),
        _pairCol('$monLabel 합계', [
          ...rows.map((r) =>
              [_BCell(_n(r['month_plan'])), _BCell(_n(r['month_actual']))]),
          [_BCell(_n(total['month_plan'])), _BCell(_n(total['month_actual']))],
        ], false, rowH, halfW: pairW),
        if (show('next_month_plan'))
          _numCol(_mon(d['next_month'] as String?), col('next_month_plan'), 46,
              rowH),
        if (show('po_delta')) _deltaCol(delta, rowH * nRows),
      ],
    );
  }

  /// 주차 묶음. 위에 달을 한 줄 얹어 '8월' 열과 눈으로 끊어 준다.
  Widget _weekGroup(String monLabel, List<String> weeks, List<Map> rows,
      Map total, String now, double rowH, [double? halfW]) {
    return IntrinsicWidth(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _cell(monLabel, _kHeadH, head: true, group: true),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final w in weeks)
                _pairCol(w, [
                  ...rows.map((r) => _weekPair((r['weeks'] as Map?)?[w], w, now)),
                  _weekPair((total['weeks'] as Map?)?[w], w, now),
                ], now == w, rowH, titleH: _kHeadH, group: true, halfW: halfW),
            ],
          ),
        ],
      ),
    );
  }

  /// PO증감 칸이 잘리지 않으려면 몇 픽셀이 필요한가.
  static double _deltaNeedH(Map delta) {
    final months = (delta['months'] as List? ?? const []).length;
    final wks = (delta['weeks'] as List? ?? const []).length;
    if (months + wks == 0) return 0;
    // 한 줄 = 8.5 * 1.42 → 줄 높이는 정수로 올라가 13, 구분선 5,
    // 위아래 여백 6, 반올림 여유 2.
    return (months + wks) * 13.0 + ((months > 0 && wks > 0) ? 5 : 0) + 8;
  }

  // 구분 열 (머리글은 빈 칸, 3단 높이)
  //
  // totalLabel — 맨 아랫줄에 달 이름. 보통은 '합계' 다.
  //   줄이 하나뿐인 보드(블룸: 출하 한 줄)는 서버가 그 줄을 아랫줄로
  //   올리고 이름을 '출하' 로 보낸다. 안 그러면 '출하 10' 밑에 '합계 10'
  //   이 똑같이 한 번 더 찍혀서, 다른 숫자인 줄 알고 들여다보게 된다.
  Widget _labelCol(List<Map> rows, double rowH, {String totalLabel = '합계'}) {
    return SizedBox(
      width: 128,
      child: Column(
        children: [
          _cell('구분', _kHeadH * 3, head: true, align: TextAlign.left),
          for (final r in rows)
            _cell('${r['label']}', rowH,
                align: TextAlign.left, bold: true, size: 9.5),
          _cell(totalLabel, _kTotalH, total: true, align: TextAlign.left),
        ],
      ),
    );
  }

  // 한 칸짜리 숫자 열
  Widget _numCol(String title, List<String> values, double w, double rowH) {
    return SizedBox(
      width: w,
      child: Column(
        children: [
          _cell(title, _kHeadH * 3, head: true),
          for (var i = 0; i < values.length - 1; i++) _cell(values[i], rowH),
          _cell(values.last, _kTotalH, total: true),
        ],
      ),
    );
  }

  // 계획/실적 두 칸짜리 열 (주차 또는 월 합계)
  Widget _pairCol(String title, List<List<_BCell>> values, bool isNow,
      double rowH,
      {double titleH = _kHeadH * 2, bool group = false, double? halfW}) {
    final border = isNow
        ? const Border(
            left: BorderSide(color: _red, width: 2),
            right: BorderSide(color: _red, width: 2))
        : null;
    return Container(
      width: math.max(84.0, (halfW ?? _kPairHalfMin) * 2),
      decoration: BoxDecoration(border: border),
      child: Column(
        children: [
          _cell(title, titleH, head: true, redHead: isNow, group: group),
          Row(children: [
            Expanded(child: _cell('계획', _kHeadH,
                head: true, redHead: isNow, group: group, role: 'plan')),
            Expanded(child: _cell('실적', _kHeadH,
                head: true, redHead: isNow, group: group, role: 'actual')),
          ]),
          for (var i = 0; i < values.length - 1; i++)
            Row(children: [
              Expanded(child: _cell(values[i][0].text, rowH,
                  tint: isNow, group: group, role: 'plan')),
              Expanded(child: _cell(values[i][1].text, rowH,
                  tint: isNow, group: group, short: values[i][1].short,
                  role: 'actual')),
            ]),
          Row(children: [
            Expanded(child: _cell(values.last[0].text, _kTotalH,
                total: true, redHead: isNow, role: 'plan')),
            Expanded(child: _cell(values.last[1].text, _kTotalH,
                total: true, redHead: isNow, short: values.last[1].short,
                role: 'actual')),
          ]),
        ],
      ),
    );
  }

  // PO증감 — 양산/개발 두 행에 걸친 한 칸
  Widget _deltaCol(Map delta, double bodyH) {
    final months = (delta['months'] as List? ?? const []).cast<Map>();
    final wks = (delta['weeks'] as List? ?? const []).cast<Map>();
    final lines = <Widget>[
      for (final m in months) _deltaLine(_mon('${m['key']}'), m['delta']),
      if (wks.isNotEmpty && months.isNotEmpty)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 2),
          child: Divider(height: 1, color: Color(0xFFCBD5E1)),
        ),
      for (final w in wks) _deltaLine('${w['key']}', w['delta']),
    ];
    return SizedBox(
      width: 92,
      child: Column(
        children: [
          _cell('PO증감', _kHeadH * 3, head: true),
          Container(
            width: double.infinity,
            height: bodyH,
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
            decoration: const BoxDecoration(
              border: Border(bottom: BorderSide(color: _line), right: BorderSide(color: _line)),
            ),
            child: ClipRect(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: lines.isEmpty
                    ? <Widget>[
                        const Text('-',
                            style: TextStyle(fontSize: 9, color: Color(0xFF94A3B8)))
                      ]
                    : lines,
              ),
            ),
          ),
          _cell('', _kTotalH, total: true),
        ],
      ),
    );
  }

  Widget _deltaLine(String label, dynamic v) {
    final n = (v is num) ? v.round() : 0;
    return Text('$label: ${_n(n.abs())} ${n >= 0 ? '▲' : '▼'}',
        maxLines: 1,
        overflow: TextOverflow.clip,
        style: TextStyle(
          fontSize: 8.5,
          height: 1.42,
          fontWeight: FontWeight.w700,
          color: n >= 0 ? const Color(0xFFB91C1C) : const Color(0xFF1D4ED8),
        ));
  }

  /// 0 · - · · 처럼 '아무것도 없음' 을 뜻하는 칸
  // ==== 계획·실적 두 칸의 한 칸 폭을 숫자 길이에 맞춰 구한다
  //
  // 2026-10-26 — 전에는 76 / 84 로 고정이었다. 좌우 여백 12 를 빼면 한 칸에
  // 글자 자리가 26~30px 뿐이라, 다섯 자리까지만 들어갔다. PCB 처럼 수량이
  // 큰 사업부에서 120,380 이 '120,3' / '80' 으로 두 줄로 끊겼다.
  // 계획·실적을 같은 폭으로 맞추려고 좁힌 것이므로, 좁히는 대신 둘 다
  // 한 줄에 들어갈 만큼 넓힌다. 표 전체에서 가장 긴 숫자 하나를 기준으로
  // 삼아, 주차 열마다 폭이 달라져 표가 들쭉날쭉해지는 일도 막는다.
  static double _pairHalfW(List<List<_BCell>> values) {
    var need = _kPairHalfMin;
    for (final row in values) {
      for (final c in row) {
        // +16 = 좌우 여백 12 + 굵은 글씨(w700) 여유. 13 이면 CURIE 의
        // '1,740' 이 '1,74 / 0' 으로 끊겼다 (2026-11-04).
        final w = _textW(c.short ? '${c.text} ▼' : c.text, 10.5) + 16;
        if (w > need) need = w;
      }
    }
    // 아무리 길어도 한 칸이 화면을 다 먹지는 않게 한다.
    // 80 = 일곱 자리 + 쉼표 둘 + ' ▼' 가 겨우 들어가는 폭.
    return math.min(need, 80.0);
  }

  // 숫자 글꼴은 tabularFigures 라 자리폭이 같다. 쉼표 · 공백 · ▼ 만 따로 센다.
  static double _textW(String t, double fs) {
    var w = 0.0;
    for (final ch in t.split('')) {
      if (ch == ',' || ch == '.') {
        w += fs * 0.32;
      } else if (ch == ' ') {
        w += fs * 0.28;
      } else if (ch == '-' || ch == '·') {
        w += fs * 0.42;
      } else if (ch == '▼' || ch == '▲') {
        w += fs;
      } else {
        w += fs * 0.64;
      }
    }
    return w;
  }

  static bool _isZero(String t) {
    final v = t.replaceAll(RegExp(r'[\s,\$]'), '');
    return v.isEmpty || v == '0' || v == '-' || v == '·';
  }

  Widget _cell(String text, double h,
      {bool head = false,
      bool total = false,
      bool redHead = false,
      bool tint = false,
      bool short = false,
      bool bold = false,
      bool group = false,
      double? size,
      int maxLines = 2,
      String role = '',
      TextAlign align = TextAlign.center}) {
    Color bg = group ? _groupTint : Colors.white;
    Color fg = const Color(0xFF0F172A);
    if (head) {
      bg = redHead
          ? const Color(0xFF7F1D1D)
          : (group ? _navyGroup : _navy);
      fg = Colors.white;
    } else if (total) {
      bg = redHead ? const Color(0xFF7F1D1D) : _navy;
      fg = Colors.white;
    } else if (tint) {
      bg = const Color(0xFFFEF2F2);
    } else if (role.isEmpty && _isZero(text)) {
      // 0 과 · 이 절반인 표다. 다 검게 찍으면 실제 숫자가 안 보인다.
      fg = _zeroInk;
    }
    // 계획 = 파랑 · 실적 = 초록 (2026-11-04). 짙은 바탕에서는 밝은 색.
    // 0 도 같은 색으로 적는다 — 굵기만 낮춘다.
    final roleZero = role.isNotEmpty && !head && _isZero(text);
    if (role == 'plan') {
      fg = (head || total)
          ? kPlanInkOnDark.withValues(alpha: roleZero && total ? 0.6 : 1)
          : (roleZero ? kPlanInkSoft : kPlanInk);
    } else if (role == 'actual') {
      fg = (head || total)
          ? kActualInkOnDark.withValues(alpha: roleZero && total ? 0.6 : 1)
          : (roleZero ? kActualInkSoft : kActualInk);
    }
    // 마감된 주인데 계획에 못 미친 칸. 숫자만 보면 지나친다.
    //
    // 미달은 합계 기준이라 이 표시는 합계 행에 붙는다. 합계 행은 남색
    // 바탕에 흰 글씨라, 연한 빨강을 깔면 아무것도 안 보인다 — 칸을
    // 통째로 빨갛게 만든다.
    if (short) {
      if (total) {
        bg = const Color(0xFFB91C1C);
        fg = Colors.white;
      } else if (!head) {
        bg = const Color(0xFFFEE2E2);
        fg = const Color(0xFF991B1B);
      }
    }
    return Container(
      height: h,
      width: double.infinity,
      alignment: align == TextAlign.left ? Alignment.centerLeft : Alignment.center,
      // 좌우 4px 이면 글자가 구분선에 붙어 읽기 힘들다.
      // 가운데 정렬 칸은 6px, 왼쪽 정렬(구분 열)은 10px 을 준다.
      padding: EdgeInsets.symmetric(
          horizontal: align == TextAlign.left ? 10 : 6),
      decoration: BoxDecoration(
        color: bg,
        border: Border(
          bottom: BorderSide(color: head || total ? _headLine : _gridH),
          right: BorderSide(color: head || total ? _headLine : _gridV),
        ),
      ),
      child: Text(short ? '$text ▼' : text,
          textAlign: align,
          maxLines: maxLines,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: size ?? (head || total ? 9.5 : 10.5),
            fontWeight: head || total || bold || short
                ? FontWeight.w800
                : (roleZero ? FontWeight.w500 : (role.isNotEmpty ? FontWeight.w700 : FontWeight.w600)),
            color: fg,
            height: 1.15,
            // 숫자가 세로로 줄이 맞아야 크기 비교가 된다
            fontFeatures: const [FontFeature.tabularFigures()],
          )),
    );
  }
}
