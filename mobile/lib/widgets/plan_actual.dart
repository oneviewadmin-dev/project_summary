// 계획 · 실적 색 + 달 고르기 (2026-11-04)
//
// Min: "계획이랑 실적 적힌거 색깔 다르게 해서 다 표기해주고
//       주차 현황 보드랑 주차별 매출 월 선택해서 보일 수 있게끔 해줘"
//
// 두 카드(주차 현황 보드 · 주차별 매출)가 같은 색과 같은 달 고르기를
// 쓴다. 한쪽만 파랑/초록이면 '계획이 어느 색이더라' 를 다시 읽어야 한다.
import 'package:flutter/material.dart';

/// 계획 = 파랑, 실적 = 초록. 흰 바탕용.
///
/// 2026-11-04 — Min: "계획/실적 색감이 안 이뻐". 원색 파랑 · 짙은 초록이
/// 옅은 칸 위에서 튀었다. 채도를 낮춘 남청 · 청록으로 바꾸고, 0 은 같은
/// 색을 옅게 적어 실제 숫자가 먼저 눈에 들어오게 한다.
//
// 같은 날 — Min: "계획이랑 실적 색깔 찐한걸로 바꿔줘". 진한 남색 · 진한
// 초록으로. 0 은 그대로 옅게 둔다 (실제 숫자가 먼저 보이게).
const Color kPlanInk = Color(0xFF1E40AF);
const Color kActualInk = Color(0xFF047857);

/// 0 을 적을 때 — 같은 색을 옅게 (다 표기하되 숫자가 묻히지 않게)
const Color kPlanInkSoft = Color(0xFF9DAEDB);
const Color kActualInkSoft = Color(0xFF8CC7AF);

/// 남색 · 짙은 빨강 바탕(머리글 · 합계 줄)용 — 같은 색을 밝게.
const Color kPlanInkOnDark = Color(0xFFB9CCFF);
const Color kActualInkOnDark = Color(0xFF86E3BE);

/// 'YYYY-MM' 로 이번 달
String thisMonthKey([DateTime? now]) {
  final d = now ?? DateTime.now();
  return '${d.year}-${d.month.toString().padLeft(2, '0')}';
}

/// 'YYYY-MM' 에서 n 달 옮긴 달
String shiftMonth(String ym, int n) {
  final p = ym.split('-');
  final y = int.tryParse(p.first) ?? DateTime.now().year;
  final m = int.tryParse(p.length > 1 ? p[1] : '') ?? DateTime.now().month;
  final t = DateTime(y, m + n, 1);
  return thisMonthKey(t);
}

/// 'YYYY-MM' → '11월' (올해가 아니면 '25년 12월')
String monthLabel(String ym, {DateTime? now}) {
  final p = ym.split('-');
  if (p.length < 2) return ym;
  final y = int.tryParse(p[0]) ?? 0;
  final m = int.tryParse(p[1]) ?? 0;
  final cur = (now ?? DateTime.now()).year;
  return y == cur ? '$m월' : "'${(y % 100).toString().padLeft(2, '0')}년 $m월";
}

/// 고를 수 있는 달 — 지난 12달부터 다음 2달까지, 최신이 위.
List<String> monthChoices({DateTime? now, int back = 12, int ahead = 2}) {
  final cur = thisMonthKey(now);
  return [for (var i = ahead; i >= -back; i--) shiftMonth(cur, i)];
}

/// 카드 머리글 오른쪽에 붙는 '◀ 11월 ▾ ▶'.
///
/// 화살표로 한 달씩, 가운데를 누르면 목록에서 고른다.
class MonthPickerPill extends StatelessWidget {
  const MonthPickerPill({
    super.key,
    required this.month,
    required this.onChanged,
  });

  final String month;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final choices = monthChoices();
    final i = choices.indexOf(month);
    // 목록은 최신이 위 — 이전 달은 인덱스 +1
    final canPrev = i < 0 || i < choices.length - 1;
    final canNext = i < 0 || i > 0;
    final isNow = month == thisMonthKey();
    return Container(
      height: 30,
      decoration: BoxDecoration(
        color: const Color(0xFFF3F6FA),
        borderRadius: BorderRadius.circular(15),
        border: Border.all(color: const Color(0xFFE1E7EF)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _arrow(Icons.chevron_left_rounded, canPrev,
              () => onChanged(shiftMonth(month, -1))),
          InkWell(
            onTap: () => _pick(context, choices),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Text(monthLabel(month),
                    style: TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w800,
                      color: isNow
                          ? const Color(0xFF0F2C59)
                          : const Color(0xFF156082),
                    )),
              ]),
            ),
          ),
          _arrow(Icons.chevron_right_rounded, canNext,
              () => onChanged(shiftMonth(month, 1))),
        ],
      ),
    );
  }

  Widget _arrow(IconData icon, bool on, VoidCallback tap) {
    return InkWell(
      onTap: on ? tap : null,
      borderRadius: BorderRadius.circular(15),
      child: SizedBox(
        width: 28,
        height: 30,
        child: Icon(icon,
            size: 18,
            color: on ? const Color(0xFF374151) : const Color(0xFFD1D5DB)),
      ),
    );
  }

  Future<void> _pick(BuildContext context, List<String> choices) async {
    final now = thisMonthKey();
    final got = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => SafeArea(
        child: ConstrainedBox(
          constraints: BoxConstraints(
              maxHeight: MediaQuery.of(ctx).size.height * 0.6),
          child: ListView(
            shrinkWrap: true,
            children: [
              const Padding(
                padding: EdgeInsets.fromLTRB(20, 0, 20, 8),
                child: Text('달 선택',
                    style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800)),
              ),
              for (final m in choices)
                ListTile(
                  dense: true,
                  title: Text(
                    '${m.substring(0, 4)}년 ${int.parse(m.substring(5))}월'
                    '${m == now ? '  · 이번 달' : ''}',
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: m == month ? FontWeight.w800 : FontWeight.w500,
                    ),
                  ),
                  trailing: m == month
                      ? const Icon(Icons.check_rounded,
                          size: 18, color: Color(0xFF156082))
                      : null,
                  onTap: () => Navigator.of(ctx).pop(m),
                ),
            ],
          ),
        ),
      ),
    );
    if (got != null && got != month) onChanged(got);
  }
}

/// '■ 계획  ■ 실적' 범례
class PlanActualLegend extends StatelessWidget {
  const PlanActualLegend({super.key});

  @override
  Widget build(BuildContext context) {
    Widget dot(Color c, String t) => Row(mainAxisSize: MainAxisSize.min, children: [
          Container(
            width: 9,
            height: 9,
            decoration:
                BoxDecoration(color: c, borderRadius: BorderRadius.circular(2)),
          ),
          const SizedBox(width: 5),
          Text(t,
              style: const TextStyle(
                  fontSize: 11.5,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF6B7280))),
        ]);
    return Row(mainAxisSize: MainAxisSize.min, children: [
      dot(kPlanInk, '계획'),
      const SizedBox(width: 12),
      dot(kActualInk, '실적'),
    ]);
  }
}
