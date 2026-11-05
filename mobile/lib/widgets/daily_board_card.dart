// ══════════════════════════════════════════════════════════════════
//  일 보고 보드 — ESS · 블룸 (2026-10-25)
// ══════════════════════════════════════════════════════════════════
//
// 이 두 사업부는 보고 자료가 **날마다** 들어온다. 한 달치를 날짜 그대로
// 그리면 열이 31개라 폰에서 못 읽는다. 그래서 서버가 접어서 준다.
//
//     지난 주차   →  주 한 칸으로 합친 값
//     이번 주차   →  날짜 그대로 (오늘 칸은 빨간 테두리)
//     다음 주차~  →  주 한 칸
//
// 접는 규칙은 서버(daily_view.py)에 있다. 앱이 또 접으면 admin 과 다른
// 모양이 된다 — 여기서는 받은 대로 그리기만 한다.
//
// 열 구성이 주차 현황 보드와 달라서 그 위젯을 재탕하지 않는다.
// (저쪽은 '구분 × 주차', 이쪽은 '품목 · 공정 × 날짜')
import '../services/offline_store.dart';
import 'dart:convert';

import 'package:flutter/material.dart';

import '../config/app_config.dart';

const double _kHeadH = 22;    // 머리글 한 줄
const double _kRowH = 34;     // 공정 한 줄
const double _kTotalH = 30;   // 합계 줄

const Color _navy = Color(0xFF0F2C59);
const Color _navyWeek = Color(0xFF1E4A80);   // 주 합계 열 머리글
const Color _navyPrior = Color(0xFF334155);  // '이전 데이터' 열 머리글
const Color _red = Color(0xFF7F1D1D);        // 이번 주 날짜 열 머리글
const Color _line = Color(0xFFE5E7EB);
const Color _gridV = Color(0xFFEDF1F6);
const Color _gridH = Color(0xFFE6EBF1);
const Color _headLine = Color(0xFF2A4C7A);
const Color _navySum = Color(0xFF0B2240);    // 달 합계 열 머리글
const Color _sumTint = Color(0xFFEEF3FA);    // 달 합계 칸 바탕
const Color _weekTint = Color(0xFFF7F9FC);   // 주 합계 칸 바탕
const Color _todayTint = Color(0xFFFEF2F2);  // 오늘 칸 바탕
const Color _zeroInk = Color(0xFFC2CBD8);    // 안 적은 칸

class DailyBoardCard extends StatefulWidget {
  final String divisionId;
  final String? month;

  const DailyBoardCard({super.key, required this.divisionId, this.month});

  @override
  State<DailyBoardCard> createState() => _DailyBoardCardState();
}

class _DailyBoardCardState extends State<DailyBoardCard> {
  late Future<Map<String, dynamic>?> _future;

  /// 2026-10-26 — '공정 전부 보기' 는 없앴다.
  ///
  /// 품목 여덟 × 공정 셋이면 폰에서 스물넷 줄이다. 펼쳐 봐야 NCT·조립은
  /// 중간 공정이라 숫자를 따로 볼 일이 거의 없었고, 줄만 길어져서 정작
  /// 품목끼리 비교가 안 됐다. **품목 하나에 줄 하나**로 둔다 — 그 줄은
  /// 나간 수량(출하)이다.
  ///
  /// 지우지 않고 참으로 못 박는다. 되돌리려면 false 로 두고 아래
  /// _footer 의 접기 단추를 되살리면 된다.
  final bool _onlyShip = true;

  /// 보고 있는 달 ('2026-10'). 비면 서버가 이번 달로 고른다.
  ///
  /// 2026-10-26 — 보고 자료에는 12월 계획까지 들어 있다. 달을 못 고르면
  /// 그 계획을 볼 길이 없고, 반대로 기본이 가장 최근 달이면 10월에 열어도
  /// 12월이 떴다. 기본은 이번 달, 바꾸는 건 사람이.
  String _month = '';

  @override
  void initState() {
    super.initState();
    _month = widget.month ?? '';
    _future = _fetch();
  }

  void _pickMonth(String ym) {
    if (ym == _month) return;
    setState(() {
      _month = ym;
      _future = _fetch();
    });
  }

  Future<Map<String, dynamic>?> _fetch() async {
    try {
      final q = _month.isEmpty ? '' : '?month=${Uri.encodeComponent(_month)}';
      final res = await OfflineStore
          .httpGet(Uri.parse('$kApiBaseUrl/divisions/'
              '${Uri.encodeComponent(widget.divisionId)}/daily-view$q'))
          .timeout(const Duration(seconds: 10));
      if (res.statusCode != 200) return null;
      final d = jsonDecode(utf8.decode(res.bodyBytes));
      if (d is! Map<String, dynamic>) return null;
      return d;
    } catch (_) {
      return null;
    }
  }

  // ── 숫자 그리기 ────────────────────────────────────────────────
  //
  // 안 적은 칸(null)과 0 은 다르다. 0 은 '0 이라고 적었다' 이고 null 은
  // '아직 안 적었다' 다. 가운뎃점으로 구분한다.
  String _n(dynamic v) {
    if (v == null) return '·';
    final i = (v is num) ? v.round() : int.tryParse('$v');
    if (i == null) return '·';
    final s = i.abs().toString();
    final b = StringBuffer();
    for (var k = 0; k < s.length; k++) {
      if (k > 0 && (s.length - k) % 3 == 0) b.write(',');
      b.write(s[k]);
    }
    return (i < 0 ? '-' : '') + b.toString();
  }

  /// 그릴 줄을 고른다. 접어 둔 상태면 '출하' 만.
  List<Map> _visibleRows(List rows) {
    final all = rows.cast<Map>();
    if (!_onlyShip) return all;
    final ship = <Map>[];
    for (final r in all) {
      if ('${r['step'] ?? ''}'.contains('출하')) ship.add(r);
    }
    // 출하 줄이 아예 없는 보고서면 접지 않는다 (빈 표가 뜬다)
    return ship.isEmpty ? all : ship;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>?>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState == ConnectionState.waiting) {
          return _shell(const SizedBox(
            height: 80,
            child: Center(
                child: SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2))),
          ));
        }
        final d = snap.data;
        final cols = (d?['columns'] as List?) ?? const [];
        if (d == null || cols.isEmpty) {
          // 조용히 사라지지 않고 한 줄로 알린다 — 안 그리면 '왜 없지' 가 된다
          return _shell(const Text('아직 올라온 일 보고 자료가 없습니다',
              style: TextStyle(fontSize: 12, color: Color(0xFF9CA3AF))));
        }

        final rows = _visibleRows((d['rows'] as List?) ?? const []);
        return _shell(
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: _table(d, cols, rows),
              ),
              const SizedBox(height: 8),
              _footer(d, rows.length),
            ],
          ),
          month: '${d['month'] ?? ''}',
          months: ((d['months'] as List?) ?? const [])
              .map((e) => e.toString())
              .toList(),
        );
      },
    );
  }

  // ── 표 ─────────────────────────────────────────────────────────
  Widget _table(Map d, List cols, List<Map> rows) {
    final total = (d['total'] as List?) ?? const [];
    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: _line),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _labelCol(rows),
            for (var i = 0; i < cols.length; i++)
              _valueCol(cols[i] as Map, rows, i, total),
          ],
        ),
      ),
    );
  }

  /// 왼쪽 고정 열 — 품목과 공정.
  Widget _labelCol(List<Map> rows) {
    return SizedBox(
      width: 132,
      child: Column(
        children: [
          _cell('품목 · 공정', _kHeadH * 2, head: true, align: TextAlign.left),
          for (final r in rows)
            _cell(_rowLabel(r), _kRowH, align: TextAlign.left, size: 9.5),
          _cell('합계', _kTotalH, total: true, align: TextAlign.left),
        ],
      ),
    );
  }

  String _rowLabel(Map r) {
    final item = '${r['item'] ?? ''}';
    final step = '${r['step'] ?? ''}';
    // 접어 둔 상태에서는 공정이 전부 '출하' 라 또 적을 이유가 없다
    if (_onlyShip) return item;
    return '$item\n$step';
  }

  /// 값 열 하나 — 머리글(이름 + 계획/실적) 아래로 줄이 내려간다.
  Widget _valueCol(Map col, List<Map> rows, int idx, List total) {
    final kind = '${col['kind'] ?? ''}';
    final isDay = kind == 'day';
    final isToday = col['today'] == true;

    // 2026-10-26 — 맨 끝 '10월 합계' 칸. 주차 칸과 같은 색이면 주차가
    // 하나 더 있는 줄 안다. 더 진하게 둬서 '여기서 끝' 이 보이게 한다.
    final isSum = kind == 'sum';

    Color headBg;
    if (kind == 'prior') {
      headBg = _navyPrior;
    } else if (isDay) {
      headBg = _red;
    } else if (isSum) {
      headBg = _navySum;
    } else {
      headBg = _navyWeek;
    }

    Color? bodyTint;
    if (isToday) {
      bodyTint = _todayTint;
    } else if (isSum) {
      bodyTint = _sumTint;
    } else if (!isDay) {
      bodyTint = _weekTint;
    }

    return Container(
      width: isDay ? 68 : (isSum ? 86 : 76),
      decoration: isToday
          ? const BoxDecoration(
              border: Border(
                left: BorderSide(color: Color(0xFFDC2626), width: 2),
                right: BorderSide(color: Color(0xFFDC2626), width: 2),
              ),
            )
          : null,
      child: Column(
        children: [
          _cell('${col['label'] ?? ''}', _kHeadH, head: true, bg: headBg, size: 9),
          Row(children: [
            Expanded(child: _cell('계획', _kHeadH, head: true, bg: headBg, size: 9)),
            Expanded(child: _cell('실적', _kHeadH, head: true, bg: headBg, size: 9)),
          ]),
          for (final r in rows)
            Row(children: [
              Expanded(
                  child: _cell(_n(_cellOf(r, idx)['plan']), _kRowH, tint: bodyTint)),
              Expanded(
                  child: _cell(_n(_cellOf(r, idx)['actual']), _kRowH, tint: bodyTint)),
            ]),
          Row(children: [
            Expanded(child: _cell(_n(_totalOf(total, idx)['plan']), _kTotalH, total: true)),
            Expanded(child: _cell(_n(_totalOf(total, idx)['actual']), _kTotalH, total: true)),
          ]),
        ],
      ),
    );
  }

  Map _cellOf(Map r, int i) {
    final cells = (r['cells'] as List?) ?? const [];
    if (i >= cells.length) return const {};
    return (cells[i] as Map?) ?? const {};
  }

  Map _totalOf(List total, int i) {
    if (i >= total.length) return const {};
    return (total[i] as Map?) ?? const {};
  }

  Widget _cell(String text, double h,
      {bool head = false,
      bool total = false,
      Color? bg,
      Color? tint,
      double? size,
      TextAlign align = TextAlign.center}) {
    Color back = Colors.white;
    Color fg = const Color(0xFF0F172A);
    if (head) {
      back = bg ?? _navy;
      fg = Colors.white;
    } else if (total) {
      back = _navy;
      fg = Colors.white;
    } else if (tint != null) {
      back = tint;
    }
    if (!head && !total && text == '·') fg = _zeroInk;

    return Container(
      height: h,
      width: double.infinity,
      alignment:
          align == TextAlign.left ? Alignment.centerLeft : Alignment.center,
      padding: EdgeInsets.symmetric(horizontal: align == TextAlign.left ? 9 : 5),
      decoration: BoxDecoration(
        color: back,
        border: Border(
          bottom: BorderSide(color: head || total ? _headLine : _gridH),
          right: BorderSide(color: head || total ? _headLine : _gridV),
        ),
      ),
      child: Text(
        text,
        textAlign: align,
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontSize: size ?? (head || total ? 9.5 : 10.5),
          fontWeight: head || total ? FontWeight.w800 : FontWeight.w600,
          color: fg,
          height: 1.15,
        ),
      ),
    );
  }

  // ── 표 밑: 접기/펴기와 설명 ────────────────────────────────────
  Widget _footer(Map d, int shown) {
    return Row(
      children: [
        Text('품목 $shown종 · 나간 수량(출하) 기준',
            style: const TextStyle(fontSize: 11, color: Color(0xFF9CA3AF))),
        const Spacer(),
        const Text('빨간 칸이 오늘',
            style: TextStyle(fontSize: 11, color: Color(0xFF9CA3AF))),
      ],
    );
  }

  /// '2026-10' → '10월'. 못 읽으면 적힌 그대로.
  String _monthLabel(String ym) {
    final p = ym.split('-');
    if (p.length < 2) return ym;
    final m = int.tryParse(p[1]);
    return m == null ? ym : '$m월';
  }

  Widget _shell(Widget child,
      {String month = '', List<String> months = const []}) {
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
            // 2026-10-26 — '일 보고' 는 **올리는 파일** 이름이다. 보는
            // 사람에게는 주차별 계획표라서, 화면 이름은 그렇게 적는다.
            const Text('주차별 계획',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
            if (month.isNotEmpty) ...[
              const SizedBox(width: 7),
              Text(month,
                  style: const TextStyle(fontSize: 11.5, color: Color(0xFF9CA3AF))),
            ],
          ]),
          const Padding(
            padding: EdgeInsets.only(top: 3),
            child: Text('지난 주는 주 단위로 묶고, 이번 주만 날짜로 폅니다',
                style: TextStyle(fontSize: 11, color: Color(0xFF9CA3AF))),
          ),
          // 올라와 있는 달이 둘 이상이면 골라 볼 수 있게. 보고 자료에
          // 12월 계획까지 들어 있는데 못 보면 올린 뜻이 없다.
          if (months.length > 1)
            Padding(
              padding: const EdgeInsets.only(top: 9),
              child: SizedBox(
                height: 30,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: months.length,
                  separatorBuilder: (_, _) => const SizedBox(width: 6),
                  itemBuilder: (_, i) {
                    final ym = months[i];
                    final on = ym == month;
                    return InkWell(
                      onTap: () => _pickMonth(ym),
                      borderRadius: BorderRadius.circular(6),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 11),
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: on ? const Color(0xFF0F2C59) : Colors.white,
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(
                              color: on ? const Color(0xFF0F2C59) : _line),
                        ),
                        child: Text(
                          _monthLabel(ym),
                          style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w700,
                              color: on ? Colors.white : const Color(0xFF44546F)),
                        ),
                      ),
                    );
                  },
                ),
              ),
            ),
          const SizedBox(height: 10),
          child,
        ],
      ),
    );
  }
}
