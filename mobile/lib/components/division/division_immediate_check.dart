// 사업부 상세 화면의 "이 사업부 즉시 확인" 섹션.
//
// 이 사업부 카드 가운데 상태가 RED / ORANGE 인 것만 모아, 마감이 가까운
// 순으로 세운 목록이다. 고르고 정렬하는 일은 여기서 하지 않는다 —
// division_projects_screen.dart 의 _computeData() 가 다 해서 items 로 넘긴다.
// 이 파일은 받은 것을 그리기만 한다.
//
// 한 줄은  [우선순위 배지] [상태 배지]  ... D-day  >  로 되어 있고
// 그 아래 한 줄 요약, 필요하면 작은 글씨로 부연이 붙는다.
import 'package:flutter/material.dart';
import '../../design/design.dart';

/// 얼마나 급한가. 상태(지연/주의)와는 다른 축이다.
///
///   high(최우선) — 지연(RED)인데 마감이 오늘이거나 내일인 것
///   mid (중간)   — 그 밖의 전부 (지연이지만 아직 여유가 있거나, 주의)
///
/// 판정은 _immPriorityOf() 에 있다. 여기서는 결과만 받는다.
enum ImmediatePriority { high, mid }

/// 즉시 확인 한 줄에 필요한 값 묶음.
class DivisionImmediateItem {
  /// 급한 정도. 배지 글자와 색이 이 값으로 갈린다.
  final ImmediatePriority priority;

  /// 마감까지 남은 날. "D-day" · "D-3" · "D+5" · 마감일이 없으면 "-".
  /// 날짜 계산은 _dueTextFrom() 에서 끝내고 여기엔 글자만 온다.
  final String dueText;

  /// 한 줄 요약. "프로젝트 이름 · 무슨 일" 모양으로 만들어서 넘긴다.
  /// 카드에 적힌 요약이 없으면 본문 첫 줄을 다듬어 쓴다 (_headlineOf).
  final String headline;

  /// 부연 한 줄. 없으면 그 줄을 아예 그리지 않는다.
  final String? detail;

  /// 서버의 RED / ORANGE / GREEN 을 사람이 읽는 말로 바꾼 것 —
  /// 지연 / 주의 / 정상. priority 와 헷갈리기 쉬운데 다른 값이다.
  /// 같은 "지연"이라도 마감이 멀면 priority 는 중간이 된다.
  final String status;

  final VoidCallback? onTap;

  DivisionImmediateItem({
    required this.priority,
    required this.dueText,
    required this.headline,
    this.detail,
    required this.status,
    this.onTap,
  });
}

class DivisionImmediateCheckSection extends StatelessWidget {
  /// 맨 아래 "OOO 이슈 모두 보기" 에 들어가는 짧은 사업부 이름. 예) "반도체"
  final String divisionShortLabel;

  /// 걸린 것 전부. 화면에는 앞의 3건만 그리고, 머리글의 "N건" 은
  /// 이 목록 전체를 센다. 둘이 다른 것은 의도한 것이다 —
  /// 몇 건인지는 알려 주되 폰 화면을 목록으로 채우지는 않는다.
  final List<DivisionImmediateItem> items;

  /// 누르면 즉시 확인 화면(전체 목록)으로 간다.
  final VoidCallback onTapSeeAll;

  const DivisionImmediateCheckSection({
    super.key,
    required this.divisionShortLabel,
    required this.items,
    required this.onTapSeeAll,
  });

  @override
  Widget build(BuildContext context) {
    // 3건까지만. 나머지는 "모두 보기" 로 넘긴다.
    final visibleItems = items.take(3).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(Icons.error, color: Color(0xFFFF0000), size: 16),
            const SizedBox(width: 6),
            Text(
              '이 사업부 즉시 확인',
              style: AppText.bodyStrong.copyWith(
                fontSize: 14,
                color: AppColors.headerNavy,
              ),
            ),
            const Spacer(),
            Text(
              '${items.length}건',
              style: AppText.caption.copyWith(
                fontSize: 12,
                color: const Color(0xFFFF0000),
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: const Color(0xFFFF0000), width: 1.2),
          ),
          child: Column(
            children: [
              for (int i = 0; i < visibleItems.length; i++) ...[
                _ImmediateRow(item: visibleItems[i]),
                if (i < visibleItems.length - 1)
                  const Divider(height: 14, color: Color(0xFFEEF1F5)),
              ],
              const SizedBox(height: 8),
              InkWell(
                onTap: onTapSeeAll,
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        '$divisionShortLabel 이슈 모두 보기',
                        style: AppText.caption.copyWith(
                          fontSize: 12,
                          color: const Color(0xFFFF0000),
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(width: 4),
                      const Icon(Icons.chevron_right,
                          size: 14, color: Color(0xFFFF0000)),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ImmediateRow extends StatelessWidget {
  final DivisionImmediateItem item;
  const _ImmediateRow({required this.item});

  @override
  Widget build(BuildContext context) {
    // 여기 두 색은 홈의 상태 신호등(지연·특이사항·집중관리)과 다른 체계다.
    // 상태가 아니라 "얼마나 급한가" 를 칠하는 자리라 일부러 따로 둔다.
    // 신호등 색을 바꿀 때 여기까지 같이 바꾸지 않아도 된다.
    final priorityColor = item.priority == ImmediatePriority.high
        ? const Color(0xFFFF0000)   // 최우선
        : const Color(0xFFE97132);  // 중간
    final priorityLabel =
        item.priority == ImmediatePriority.high ? '최우선' : '중간';

    return InkWell(
      onTap: item.onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                _Badge(text: priorityLabel, color: priorityColor),
                const SizedBox(width: 6),
                _Badge(
                  text: item.status,
                  color: const Color(0xFF7C8594),
                  filled: false,
                ),
                const Spacer(),
                Text(
                  item.dueText,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    color: priorityColor,
                  ),
                ),
                const SizedBox(width: 2),
                const Icon(Icons.chevron_right,
                    size: 14, color: Color(0xFF7C8594)),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              item.headline,
              style: AppText.bodyStrong.copyWith(
                fontSize: 13,
                color: AppColors.headerNavy,
              ),
            ),
            if (item.detail != null && item.detail!.trim().isNotEmpty) ...[
              const SizedBox(height: 2),
              Text(
                item.detail!,
                style: AppText.caption.copyWith(
                  fontSize: 11,
                  color: const Color(0xFF7C8594),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// 작은 알약 배지. filled=true 면 색을 채우고(우선순위),
/// false 면 테두리만 그린다(상태).
class _Badge extends StatelessWidget {
  final String text;
  final Color color;
  final bool filled;
  const _Badge({required this.text, required this.color, this.filled = true});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: filled ? color : Colors.transparent,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w700,
          color: filled ? Colors.white : color,
        ),
      ),
    );
  }
}
