# 주차 현황 보드 · 주차별 매출 — 달 고르기와 계획/실적 색 (2026-11-04)
#   python3 backend/tests/test_board_month_colors.py
#
# Min: "계획이랑 실적 적힌거 색깔 다르게 해서 다 표기해주고
#       주차 현황 보드랑 주차별 매출 월 선택해서 보일 수 있게끔 해줘"
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
LIB = ROOT / "mobile" / "lib"
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


pa = (LIB / "widgets/plan_actual.dart").read_text(encoding="utf-8")
wb = (LIB / "widgets/weekly_board_card.dart").read_text(encoding="utf-8")
wr = (LIB / "widgets/weekly_revenue_card.dart").read_text(encoding="utf-8")
po = (LIB / "screens/project_overview_screen.dart").read_text(encoding="utf-8")
dp = (LIB / "screens/division_projects_screen.dart").read_text(encoding="utf-8")

# ── 한 곳에서 정한 색을 두 카드가 같이 쓴다
for n in ("kPlanInk", "kActualInk", "kPlanInkOnDark", "kActualInkOnDark"):
    ok("const Color %s" % n in pa, "%s 가 plan_actual.dart 에 없다" % n)
ok("class MonthPickerPill" in pa, "달 고르기 위젯이 없다")

# ── 보드: 모든 칸에 숫자 (가운뎃점으로 비우지 않는다), 계획/실적 색
_wp = wb[wb.find("List<_BCell> _weekPair("):]
_wp = _wp[:_wp.find("\n  }\n")]
ok("'·'" not in _wp, "아직 안 온 주의 실적을 · 로 비운다 — 다 표기해야 한다")
ok(wb.count("role: 'plan'") >= 6 and wb.count("role: 'actual'") >= 6,
   "계획/실적 칸에 색 구분(role)이 다 안 붙었다")
ok("kPlanInk" in wb and "kActualInk" in wb, "보드가 계획/실적 색을 안 쓴다")
ok("PlanActualLegend()" in wb, "보드에 계획/실적 범례가 없다")
# 미달(▼) 칸은 계획/실적 색보다 먼저 칠하면 안 된다 — 빨강이 이긴다
_c = wb[wb.find("Widget _cell("):]
ok(_c.find("role == 'plan'") < _c.find("if (short) {"), "미달 표시가 계획/실적 색에 덮인다")

# ── 보드: 달 고르기 — 머리글에, 사업부 보드도 고른 달로 받는다
ok("MonthPickerPill(month: _month, onChanged: _setMonth)" in wb, "보드에 달 고르기가 없다")
ok("Function(String month)? loader" in wb and "widget.loader!(_month)" in wb,
   "사업부 보드가 고른 달을 못 받는다")
ok("'?month=${Uri.encodeComponent(_month)}'" in wb, "프로젝트 보드가 고른 달로 안 받는다")
ok("loader: (month) => DivisionBoardService.fetch(" in dp and "month: month," in dp,
   "사업부 화면이 보드에 고른 달을 안 넘긴다")

# ── 주차별 매출: 달 고르기 · 색
ok("MonthPickerPill(" in wr and "onMonthChanged" in wr, "주차별 매출에 달 고르기가 없다")
ok("AppColors.statusGray," not in wr, "매출 그래프 계획 막대가 아직 회색이다")
ok("color: kPlanInk" in wr and "color: kActualInk" in wr, "매출 그래프가 계획/실적 색을 안 쓴다")
ok("TextSpan(text: p[0], style: const TextStyle(color: kPlanInk))" in wr,
   "매출 표의 '계획 / 실적' 숫자 색이 안 갈린다")
ok("fetchWeeklyRevenue(widget.projectKey, month: month)" in po, "프로젝트 화면이 고른 달로 매출을 안 받는다")
ok("future: fetchWeeklyRevenue(widget.projectKey)," not in po,
   "build 마다 매출을 새로 받는다 — 달을 바꿔도 이번 달로 돌아간다")
ok("onMonthChanged: _setRevMonth" in po, "프로젝트 화면이 달 바꾸기를 안 잇는다")
# 자료 없는 달에서도 고르기가 남아야 되돌아간다
_e = po[po.find("if (rev == null) {"):]
_e = _e[:_e.find("_lastRev = rev;")]
ok("MonthPickerPill(" in _e, "자료 없는 달에서 달 고르기가 사라진다")

# ── const 목록 안에 달 고르기를 넣으면 컴파일이 안 된다 (2.3.69 때 한 번 겪음)
for name, src in (("weekly_board_card", wb), ("weekly_revenue_card", wr),
                  ("project_overview_screen", po)):
    for mo in re.finditer(r"const \[", src):
        seg = src[mo.end():mo.end() + 600]
        ok("MonthPickerPill(" not in seg.split("]")[0],
           "%s: const 목록 안에 MonthPickerPill" % name)

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — 보드 · 매출: 달 고르기, 계획 파랑 · 실적 초록")
