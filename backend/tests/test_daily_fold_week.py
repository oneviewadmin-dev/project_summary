# -*- coding: utf-8 -*-
"""일 보고 보드 — 지난 주는 주 단위, 이번 주만 날짜 (2026-10-26).

    이번 주차가 W44 면   W41 · W42 · W43 은 '41주차' 한 칸씩
                        W44 는 10/26 · 10/27 … 하루씩

왜 이렇게 접나
    한 달치를 날짜 그대로 그리면 열이 서른 개를 넘어 아무도 못 읽는다.
    지난주는 '그 주에 얼마나 했나' 만 알면 되고, 손이 가는 건 이번 주뿐이다.

조심할 것
    · 이번 주 자료가 아직 없어도 **이번 달을 보고 있으면** 칸은 선다.
      10/26(월)에 10월을 보면 자료는 10/24 까지라, 안 세우면 이번 주가
      통째로 안 보여서 "왜 없지" 가 된다.
    · 지난 달을 보면 이번 주가 그 달에 없다 — 그때는 자료에 있는 주차
      중 오늘과 가장 가까운 주를 편다.
    · 빈 칸(None)과 0 은 다르다. 한 주를 더할 때 적힌 날이 하나도 없으면
      None 이어야 한다 — 0 으로 두면 '안 적음' 이 '0 이라고 적음' 이 된다.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import daily_view as dv          # noqa: E402

FAIL = []


def ok(c, why):
    if not c:
        FAIL.append(why)


OCT = ["2026-10-%02d" % i for i in range(1, 25)]      # 10/1 ~ 10/24 (W40~W43)

cols = dv.build_columns(OCT, "2026-10-26", "2026-10")
# 맨 끝 '월 합계' 칸은 따로 본다 (아래 '월 합계' 묶음)
ok(cols and cols[-1]["kind"] == "sum", "맨 끝 합계 칸이 없다")
cols = [c for c in cols if c["kind"] != "sum"]
kinds = [(c["kind"], c["label"]) for c in cols]

ok([k for k, _ in kinds[:4]] == ["week"] * 4,
   "지난 주차를 주 단위로 안 접었다: %r" % kinds[:4])
ok([l for _, l in kinds[:4]] == ["40주차", "41주차", "42주차", "43주차"],
   "주차 이름이 보고 자료('40주차')와 다르다: %r" % [l for _, l in kinds[:4]])
ok(all(k == "day" for k, _ in kinds[4:]),
   "이번 주차를 날짜로 안 펼쳤다: %r" % kinds[4:])
ok([l for _, l in kinds[4:]][0].startswith("10/26"),
   "이번 주 첫 칸이 10/26 이 아니다: %r" % kinds[4:5])
ok(len(kinds[4:]) == 6, "10/26~10/31 여섯 칸이어야 한다: %d칸" % len(kinds[4:]))

# 2026-10-26 — 날짜로 펴는 건 '이번 달' 뿐이다.
#
# 지난 달은 이미 끝났고 다음 달은 아직 계획뿐이라, 날짜로 펼 이유가 없다.
# 전에는 '자료에 있는 주차 중 오늘과 가장 가까운 주' 를 폈는데, 9월을
# 열면 9월 마지막 주만 뜬금없이 날짜로 펴져서 설명할 말이 없었다.
for _m, _ds in (("2026-09", ["2026-09-%02d" % i for i in range(1, 31)]),
                ("2026-11", ["2026-11-%02d" % i for i in range(1, 21)])):
    cs = [c for c in dv.build_columns(_ds, "2026-10-26", _m)
          if c["kind"] != "sum"]
    ok(cs and all(c["kind"] == "week" for c in cs),
       "%s 을 열었더니 날짜로 편 주가 있다: %r"
       % (_m, [c["label"] for c in cs if c["kind"] != "week"]))

# 한 주를 더할 때 — 안 적은 날만 있으면 None
w = [c for c in cols if c["kind"] == "week"][0]
cells = dv.fold_row({}, [w])
ok(cells[0] == {"plan": None, "actual": None},
   "아무것도 안 적은 주를 0 으로 만들었다: %r" % cells[0])
cells = dv.fold_row({w["dates"][0]: {"plan": 10, "actual": 0}}, [w])
ok(cells[0] == {"plan": 10, "actual": 0},
   "사람이 0 이라고 적은 날을 안 적음으로 바꿨다: %r" % cells[0])
cells = dv.fold_row({w["dates"][0]: {"plan": 10, "actual": 4},
                     w["dates"][1]: {"plan": 5, "actual": 6}}, [w])
ok(cells[0] == {"plan": 15, "actual": 10}, "주 합계가 틀렸다: %r" % cells[0])

# 화면이 서버가 접어 준 열을 쓰는가
import io  # noqa: E402
_adm = io.open(os.path.join(os.path.dirname(HERE), "backend", "admin_v2.html")
               if False else os.path.join(os.path.dirname(HERE), "admin_v2.html"),
               encoding="utf-8").read()
ok("d.columns || []" in _adm, "화면이 서버가 접어 준 열(columns)을 안 쓴다")
ok("st.cells && st.cells[ci]" in _adm, "화면이 접은 칸(cells)을 안 읽는다")
_main = io.open(os.path.join(os.path.dirname(HERE), "main.py"), encoding="utf-8").read()
ok('out["columns"] = cols' in _main, "서버가 접은 열을 안 내려준다")
ok("_dv.fold_row(_st.get(\"days\")" in _main, "서버가 공정 줄을 안 접는다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — 주/일 접기")

# ======================================================================
#  보는 달과 접는 기준이 어긋나면 안 된다 (2026-10-26)
#
#  /divisions/{id}/daily-view 가 달을 안 넘겨서, 12월 보드를 열어도
#  오늘(10/26)의 주가 날짜로 펴졌다. 12월 표에 10/26 칸이 섰다.
#  그리고 기본이 '가장 최근 달' 이라, 보고 자료에 12월 계획이 들어 있으면
#  10월에 열어도 제목이 2026-12 로 떴다. 기본은 이번 달이다.
# ======================================================================
_main = io.open(os.path.join(os.path.dirname(HERE), "main.py"), encoding="utf-8").read()
ok("_dv.build(boards[mon], today or None, mon)" in _main,
   "daily-view 가 어느 달을 보는지 안 알려준다 — 다른 달 날짜가 열로 선다")
ok("mon = _now if _now in boards else sorted(boards)[-1]" in _main,
   "기본 달이 '이번 달' 이 아니다 — 12월 계획이 들어오면 10월에 12월이 뜬다")

_dvsrc = io.open(os.path.join(os.path.dirname(HERE), "daily_view.py"), encoding="utf-8").read()
ok('def build(parsed: dict, today=None, month="")' in _dvsrc,
   "build 가 달을 안 받는다")
ok("build_columns(parsed.get(\"dates\") or [], today, month)" in _dvsrc,
   "build 가 받은 달을 안 넘긴다")

# 12월 보드를 10월에 열면 날짜로 편 주가 없어야 한다
_c = [c for c in dv.build_columns(["2026-12-%02d" % i for i in range(1, 20)],
                                  "2026-10-26", "2026-12")
      if c["kind"] != "sum"]
ok(_c and all(x["kind"] == "week" for x in _c),
   "12월 보드에 날짜 칸이 섰다: %r" % [x["label"] for x in _c if x["kind"] != "week"])

# 앱 화면 이름 · 달 고르기
_card = io.open(os.path.join(os.path.dirname(os.path.dirname(HERE)),
                             "mobile", "lib", "widgets", "daily_board_card.dart"),
                encoding="utf-8").read()
ok("const Text('주차별 계획'," in _card, "앱 카드 이름이 아직 '일 보고' 다")
ok("void _pickMonth(String ym)" in _card, "앱에서 달을 고를 수가 없다")
ok("if (months.length > 1)" in _card, "달이 하나뿐일 때도 고르는 줄을 그린다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
# 지난 달 표에 이번 달 날짜가 섞이면 안 된다 (9월을 10/26 에 열기)
_c9 = [c for c in dv.build_columns(["2026-09-%02d" % i for i in range(1, 31)] +
                                   ["2026-10-0%d" % i for i in range(1, 5)],
                                   "2026-10-26", "2026-09")
       if c["kind"] != "sum"]
ok(_c9 and all(x["kind"] == "week" for x in _c9),
   "9월 표에 날짜 칸이 섰다: %r" % [x["label"] for x in _c9 if x["kind"] != "week"])

# 앱 — 공정은 안 펼친다 (품목 하나에 줄 하나)
ok("공정 전부 보기 ($all줄)" not in _card,
   "'공정 전부 보기' 단추가 아직 있다")
ok("final bool _onlyShip = true;" in _card,
   "품목 한 줄로 못 박아 두지 않았다")

# ── 맨 끝 '월 합계' 칸 (2026-10-26)
#    주차가 다섯이면 "이 달에 몇 개냐" 를 눈으로 다섯 번 더해야 했다.
#    더하는 날짜는 표에 선 날짜 전부여야 한다 — 따로 세면 가로로 더한
#    값과 안 맞는다.
_c10 = dv.build_columns(["2026-10-%02d" % i for i in range(1, 30)],
                        "2026-10-26", "2026-10")
ok(_c10 and _c10[-1]["kind"] == "sum", "맨 끝에 합계 칸이 없다")
if _c10 and _c10[-1]["kind"] == "sum":
    _sum = _c10[-1]
    ok(_sum["label"] == "10월 합계", "합계 칸 이름이 %r" % _sum["label"])
    _rest = sorted({d for c in _c10[:-1] for d in c["dates"]})
    ok(_sum["dates"] == _rest,
       "합계가 더하는 날짜가 표에 선 날짜와 다르다 (%d개 vs %d개)"
       % (len(_sum["dates"]), len(_rest)))
    ok(all(c["kind"] != "sum" for c in _c10[:-1]), "합계 칸이 둘이다")
_cell = dv.fold_row({"2026-10-01": {"plan": 10, "actual": 4},
                     "2026-10-02": {"plan": 5, "actual": None}}, [_c10[-1]])
ok(_cell[0] == {"plan": 15, "actual": 4}, "합계 칸 숫자가 틀렸다: %r" % _cell[0])

_card2 = io.open(os.path.join(os.path.dirname(os.path.dirname(HERE)),
                              "mobile", "lib", "widgets", "daily_board_card.dart"),
                 encoding="utf-8").read()
ok("kind == 'sum'" in _card2, "앱이 합계 칸을 따로 안 그린다")
_adm3 = io.open(os.path.join(os.path.dirname(HERE), "admin_v2.html"),
                encoding="utf-8").read()
ok("bd-sum" in _adm3, "admin 이 합계 칸을 따로 안 그린다")

print("ok — 보는 달과 접는 기준")
