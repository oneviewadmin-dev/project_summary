# -*- coding: utf-8 -*-
"""블룸·ESS 프로젝트 보드의 '구분' 열은 공정이다.

### 왜 이걸 세나

2026-10-25 에 제가 틀린 것이다. 블룸 프로젝트(YFP · Corva KPE …)를 눌러
들어갔을 때 뜨는 주차 현황 보드를, 반도체 표를 그대로 베껴 **양산 / 개발**
두 줄로 그렸다. 블룸에는 그런 구분이 없다.

  · 반도체 — 프로젝트 안에 모델(품번)이 있고 모델마다 양산/개발이 붙는다
  · 블룸   — 모델이 아예 없다. 프로젝트 하나가 품목 하나이고, 일 보고
             자료에 품목마다 **공정**이 적혀 온다 (YFP → NCT · 조립 · 출하)

양산/개발로 그리면 두 줄 다 0 이 뜬다. 표는 멀쩡해 보이고 테스트도 안
깨진다 — 숫자가 0 인 게 '아직 안 올라왔나 보다' 로 읽히기 때문이다.
그래서 여기서 못 박는다.

### 무엇을 보나

  1. 날짜 → 주차 묶기가 ISO 주차다 (보고 자료의 '41주차' 와 같은 번호)
  2. 보드의 줄 이름이 일 보고의 공정 이름 그대로다
  3. 양산 / 개발 이라는 말이 블룸 보드 코드에 없다
  4. 일 보고에 없는 열(PO수량 · 잔량 · 다음달)은 0 이 아니라 비워 두고,
     앱에 '그리지 마라'(hide_cols) 를 같이 보낸다
  5. get_weekly_board 가 보드 설정(_load_board_spec)보다 **먼저** 블룸을
     본다 — 순서가 바뀌면 블룸이 다시 양산/개발로 떨어진다
"""
import ast
import datetime as dt
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


SRC = (BACK / "main.py").read_text(encoding="utf-8")
tree = ast.parse(SRC)
by_name = {n.name: n for n in ast.walk(tree)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

for want in ("_daily_project_board", "_bloom_step_weeks",
             "_daily_board_items", "_daily_prev_by_group",
             "_daily_board_division"):
    ok(want in by_name, "%s 가 없다" % want)

# ── 1. 날짜를 주차로 묶는 함수를 떼어 내서 직접 돌려 본다 ──────────
ns = {}
exec(compile(ast.Module(body=[by_name["_bloom_step_weeks"]], type_ignores=[]),
             "<main>", "exec"), ns)
step_weeks = ns["_bloom_step_weeks"]

step = {"days": {
    "2026-10-05": {"plan": 10, "actual": 8},     # 41주차
    "2026-10-08": {"plan": 5,  "actual": 5},     # 41주차
    "2026-10-13": {"plan": 7,  "actual": None},  # 42주차
    "2026-09-28": {"plan": 99, "actual": 99},    # 40주차 — 이번 달 밖
}}
got = step_weeks(step, ["W41", "W42", "W43"], "2026-10")
ok(got["W41"] == {"plan": 15, "actual": 13},
   "41주차가 10/05 + 10/08 로 안 묶였다: %r" % (got["W41"],))
ok(got["W42"] == {"plan": 7, "actual": 0},
   "42주차에서 실적이 빈 칸(None)인데 더해졌다: %r" % (got["W42"],))
ok(got["W43"] == {"plan": 0, "actual": 0},
   "자료가 없는 주차는 0 이어야 한다: %r" % (got["W43"],))
ok("W40" not in got,
   "이번 달 주차가 아닌 9/28 자료가 표에 들어왔다 — 합계가 틀어진다")

# 보고 자료의 '41주차' 와 번호가 같은가 (ISO)
ok(dt.date(2026, 10, 5).isocalendar()[1] == 41,
   "ISO 주차 계산이 보고 자료와 어긋난다 — 묶는 규칙을 다시 봐야 한다")

# ── 2~4. 보드를 만드는 함수를 도우미만 흉내 내서 돌려 본다 ─────────
BOARD = {"items": [{"item": "YFP", "wait_ship": 7, "wait_part": 3, "steps": [
    {"step": "NCT(박닌)",  "month_plan": 40, "month_actual": 33, "wip": 5,
     "days": {"2026-10-05": {"plan": 20, "actual": 18},
              "2026-10-13": {"plan": 20, "actual": 15}}},
    {"step": "조립(박닌)", "month_plan": 30, "month_actual": 24, "wip": 2,
     "days": {"2026-10-06": {"plan": 15, "actual": 12},
              "2026-10-14": {"plan": 15, "actual": 12}}},
    {"step": "출하",      "month_plan": 25, "month_actual": 20,
     "days": {"2026-10-07": {"plan": 12, "actual": 10},
              "2026-10-15": {"plan": 13, "actual": 10}}},
]}]}

env = {
    "_model_key_alias": lambda k: k,
    "_bloom_item_of": lambda k: "YFP" if k.startswith("bloom_") else "",
    "_BLOOM_STORE": "bloom_main",
    "_load_models": lambda: {"projects": {"bloom_main": {}}},
    "_bloom_store_months": lambda p: {"2026-10": BOARD},
    "_bloom_with_month_totals": lambda b: b,
    "_daily_board_division": lambda k: "bloom",
    "_daily_store_key": lambda d: "bloom_main",
    "_daily_board_items": lambda d, k, b: (b.get("items") or []),
    "_daily_stock_of": None,     # 아래에서 진짜 함수로 채운다
    "_daily_prev_by_group": lambda d, k, rows, prev: {},
    "_get_month_weeks": lambda m: ["W41", "W42", "W43", "W44"],
    "_week_reasons_of": lambda p, m: {},
    "_mark_board_shortfalls": lambda rows, total, weeks, month, reasons: ([], []),
    "_bloom_step_weeks": step_weeks,      # 위에서 떼어 낸 진짜 함수
}
# '늘 세 줄' 규칙은 흉내 내지 않고 진짜 코드를 쓴다 — 이 시험의 핵심이다
for _n in ("_DAILY_BOARD_ROWS", "_DAILY_PRIOR_COL", "_daily_board_rows",
           "_daily_step_group", "_daily_stock_of"):
    ok(_n in by_name or _n in SRC, "%s 가 없다" % _n)
exec(compile(ast.Module(
    body=[n for n in tree.body
          if (isinstance(n, ast.Assign)
              and getattr(n.targets[0], "id", "")
              in ("_DAILY_BOARD_ROWS", "_DAILY_PRIOR_COL"))
          or (isinstance(n, ast.FunctionDef)
              and n.name in ("_daily_board_rows", "_daily_step_group",
                             "_daily_report_rows", "_daily_stock_of"))],
    type_ignores=[]), "<main>", "exec"), env)
exec(compile(ast.Module(body=[by_name["_daily_project_board"]], type_ignores=[]),
             "<main>", "exec"), env)
d = env["_daily_project_board"]("bloom_yfp", "2026-10")

# '구분' 열은 일 보고의 공정이다
labels = [r["label"] for r in d["rows"]]
ok(labels == ["NCT(박닌)", "조립(박닌)", "출하"],
   "'구분' 열이 공정 이름이 아니다: %r" % (labels,))
ok("양산" not in labels and "개발" not in labels,
   "블룸 보드에 양산/개발 줄이 들어갔다 — 그 구분은 블룸에 없다")

ok(d["total"]["month_plan"] == 95 and d["total"]["month_actual"] == 77,
   "합계가 세 공정의 합이 아니다: %r" % (d["total"],))
ok(d["rows"][0]["weeks"]["W41"] == {"plan": 20, "actual": 18},
   "공정 줄의 주차 칸이 틀렸다: %r" % (d["rows"][0]["weeks"]["W41"],))
ok(d["total"]["weeks"]["W42"]["plan"] == 48,
   "합계 줄의 주차 칸이 세 공정의 합이 아니다: %r"
   % (d["total"]["weeks"]["W42"],))

# 합계가 출하량이 아니라는 걸 화면에 적어 보낸다.
# 안 적으면 '합계 77' 을 '77대 나갔다' 로 읽는다 (실제 출하는 20).
ok("출하" in str(d.get("note") or ""),
   "줄이 여럿인데 합계를 어떻게 읽는지 안 적어 보냈다: %r" % (d.get("note"),))

for f in ("po_qty", "remaining", "next_month_plan"):
    ok(d["rows"][0][f] is None,
       "%s 를 0 으로 채웠다 — 일 보고에 없는 숫자다. 0 은 '0개'로 읽힌다" % f)
    ok(f in (d.get("hide_cols") or []),
       "%s 를 hide_cols 에 안 적었다 — 앱이 빈 열을 그린다" % f)

# ── 1-3. 출하대기 · 구매품대기 · 공정재고 ─────────────────────────
#
# 셋 다 일 보고에 적혀 오는 '지금 쌓여 있는 것' 이다.
#   공정재고 — 공정마다 적혀 온다 → 줄마다 값
#   출하대기 · 구매품대기 — 품목에 붙는다 → 합계 줄에만 값
# 셋 다 없으면 0 이 아니라 빈 칸이어야 한다 ('대기 없음' 으로 읽히면 안 된다).
ok(d["rows"][0]["wip"] == 5 and d["rows"][1]["wip"] == 2,
   "공정재고가 줄마다 안 붙었다: %r"
   % ([r.get("wip") for r in d["rows"]],))
ok(d["rows"][2]["wip"] is None,
   "공정재고가 안 적힌 공정을 0 으로 채웠다 — '재고 없음' 으로 읽힌다")
ok(d["total"]["wip"] == 7,
   "공정재고 합계가 줄의 합이 아니다: %r" % (d["total"].get("wip"),))

ok(d["total"]["wait_ship"] == 7 and d["total"]["wait_part"] == 3,
   "출하대기 · 구매품대기가 합계 줄에 안 붙었다: %r / %r"
   % (d["total"].get("wait_ship"), d["total"].get("wait_part")))
ok(all(r.get("wait_ship") is None for r in d["rows"]),
   "품목 단위인 출하대기를 공정 줄에 붙였다 — 공정마다 그만큼 있는 것처럼 보인다")

_sc = [c.get("field") for c in (d.get("stock_cols") or [])]
ok(_sc == ["wip", "wait_ship", "wait_part"],
   "그릴 재고 열을 안 보냈거나 순서가 다르다: %r" % (_sc,))

# ── 1-4. 그 달 날짜인데 주차가 지난달 것인 자료 ───────────────────
#
# 10/01~10/04 는 10월인데 주차로는 W40 이고, W40 은 주차 배정 규칙상
# 9월 것이다. 그 달 주차(_get_month_weeks)만 세우면 그 나흘에 나간 물량이
# 표 어디에도 안 뜬다 — 2026년 10월 블룸 YFP 가 그랬다 (32대가 사라졌다).
BOARD_W40 = {"items": [{"item": "YFP", "steps": [
    {"step": "출하", "group": "출하", "month_plan": 50, "month_actual": 50,
     "days": {"2026-10-02": {"plan": 32, "actual": 32},   # W40 — 지난달 주차
              "2026-10-07": {"plan": 18, "actual": 18}}}, # W41
]}]}
env["_bloom_store_months"] = lambda p: {"2026-10": BOARD_W40}
_realweeks = env["_get_month_weeks"]
env["_get_month_weeks"] = lambda m: ["W41", "W42", "W43", "W44"]
dw = env["_daily_project_board"]("bloom_yfp", "2026-10")
ok("W40" in dw["weeks"],
   "10/02 자료가 있는데 W40 열이 안 섰다: %r — 그날 나간 물량이 표에서 "
   "사라진다" % (dw["weeks"],))
ok(dw["weeks"] == ["W40", "W41", "W42", "W43", "W44"],
   "주차 순서가 틀렸다: %r" % (dw["weeks"],))
ok(dw["total"]["weeks"]["W40"]["actual"] == 32,
   "W40 칸에 10/02 실적이 안 들어갔다: %r" % (dw["total"]["weeks"]["W40"],))
_wsum = sum(c["actual"] or 0 for c in dw["total"]["weeks"].values())
ok(_wsum == 50,
   "주차 칸을 다 더해도 월 실적(50)이 안 된다: %d — 어딘가에서 날이 "
   "빠지고 있다" % _wsum)
env["_get_month_weeks"] = _realweeks
env["_bloom_store_months"] = lambda p: {"2026-10": BOARD}

# ── 1-5. '이전 데이터' 칸 ─────────────────────────────────────────
#
# ESS 보고자료에는 '10월05일 이전 데이터' 처럼 날짜별로 안 적고 한 칸에
# 몰아 둔 기간이 있다. 날짜가 없어 어느 주차에도 못 넣는다. 빼 버리면
# 주차 칸을 다 더해도 월 합계가 안 맞는다 (2026-10 SDI 가 60대 차이).
BOARD_PR = {"items": [{"item": "SBB 1.5", "owner": "SDI", "steps": [
    {"step": "출하", "group": "출하", "month_plan": 50, "month_actual": 40,
     "prior_plan": 20, "prior_actual": 15,
     "days": {"2026-10-07": {"plan": 30, "actual": 25}}},
]}]}
env["_bloom_store_months"] = lambda p: {"2026-10": BOARD_PR}
env["_daily_board_division"] = lambda k: "bloom"   # 묶음 없이 평평하게 본다
dp = env["_daily_project_board"]("bloom_yfp", "2026-10")
ok(dp["weeks"][0] == "이전",
   "'이전 데이터' 칸이 맨 앞에 안 섰다: %r" % (dp["weeks"],))
ok(dp["total"]["weeks"]["이전"] == {"plan": 20, "actual": 15},
   "'이전' 칸에 숫자가 안 들어갔다: %r" % (dp["total"]["weeks"]["이전"],))
_p = sum(c["plan"] or 0 for c in dp["total"]["weeks"].values())
_a = sum(c["actual"] or 0 for c in dp["total"]["weeks"].values())
ok((_p, _a) == (50, 40),
   "열을 다 더해도 월 합계(50/40)가 안 된다: %s/%s — 어딘가에서 숫자가 "
   "빠지고 있다" % (_p, _a))
ok("이전" not in (dp.get("closed_weeks") or []),
   "'이전' 칸을 마감된 주차로 셌다 — 날짜가 없어 언제 끝났는지 모른다")
ok(all(x.get("week") != "이전" for x in (dp.get("shortfalls") or [])),
   "'이전' 칸을 계획 미달 주차로 셌다")

# '이전 데이터' 가 없는 자료(블룸)에는 그 칸을 안 만든다
env["_bloom_store_months"] = lambda p: {"2026-10": BOARD}
dn = env["_daily_project_board"]("bloom_yfp", "2026-10")
ok("이전" not in dn["weeks"],
   "'이전 데이터' 가 없는데 빈 칸을 세웠다: %r" % (dn["weeks"],))

# ── 2-1. 공정이 덜 적혀 온 품목도 세 줄을 다 세운다 ───────────────
#
# BOP Assy 는 일 보고에 NCT 줄이 아예 없다. 자료에 있는 것만 세우면
# 품목마다 표의 줄 수가 달라져서 옆 품목과 눈으로 못 맞춘다.
# 줄은 그 품목이 아니라 **일 보고 전체**에 적힌 공정으로 선다 — 옆 품목
# (YFP)에 NCT 가 적혀 있으니 BOP Assy 에도 NCT 줄이 선다.
BOARD2 = {"items": [
    {"item": "YFP", "steps": [
        {"step": "NCT(박닌)", "days": {}}, {"step": "조립(박닌)", "days": {}},
        {"step": "출하", "days": {}}]},
    {"item": "BOP Assy", "steps": [
        {"step": "조립(박닌)", "month_plan": 10, "month_actual": 8,
         "days": {"2026-10-05": {"plan": 10, "actual": 8}}},
        {"step": "출하", "month_plan": 9, "month_actual": 7,
         "days": {"2026-10-06": {"plan": 9, "actual": 7}}},
    ]}]}
env["_bloom_store_months"] = lambda p: {"2026-10": BOARD2}
_saved_items = env["_daily_board_items"]
env["_daily_board_items"] = lambda d, k, b: [
    it for it in (b.get("items") or []) if it["item"] == "BOP Assy"]
db = env["_daily_project_board"]("bloom_bop_assy", "2026-10")
env["_daily_board_items"] = _saved_items
ok([r["group"] for r in db["rows"]] == ["NCT", "조립", "출하"],
   "NCT 가 없는 품목에서 줄이 빠졌다: %r" % ([r["group"] for r in db["rows"]],))
nct = db["rows"][0]
ok(nct["month_plan"] is None and nct["weeks"]["W41"]["plan"] is None,
   "자료 없는 공정을 0 으로 채웠다 — 0 은 '계획 0개' 로 읽힌다: %r" % (nct,))
ok(db["total"]["month_plan"] == 19,
   "빈 줄이 섞인 합계가 틀렸다: %r" % (db["total"]["month_plan"],))

# ── 2-2. 한 공정도 안 적혀 온 품목 (SS8 · TC) ─────────────────────
BOARD3 = {"items": [{"item": "TC", "steps": []}]}
env["_bloom_store_months"] = lambda p: {"2026-10": BOARD3}
dc = env["_daily_project_board"]("bloom_tc", "2026-10")
ok([r["group"] for r in dc["rows"]] == ["NCT", "조립", "출하"],
   "자료가 하나도 없는 품목에서 표가 비었다: %r" % (dc["rows"],))
ok(dc["total"]["month_plan"] is None,
   "한 줄도 안 적혔는데 합계가 0 으로 찍혔다: %r" % (dc["total"]["month_plan"],))

# ── 2-3. 구분은 일 보고에 적힌 공정이 정한다 (2026-10-26) ─────────
#
# 박아 둔 줄(NCT · 조립 · 출하)이 아니라 '공정구분' 칸에 적힌 것을 적힌
# 순서대로 세운다. 못 보던 공정(도장)도 그 자리에 서고, 일 보고에 없는
# 공정(조립)은 빈 줄로 남지 않는다.
BOARD4 = {"items": [{"item": "YFP", "steps": [
    {"step": "NCT(박닌)", "month_plan": 5, "month_actual": 5, "days": {}},
    {"step": "도장", "group": "도장", "month_plan": 3, "month_actual": 2,
     "days": {}},
    {"step": "출하", "month_plan": 2, "month_actual": 2, "days": {}},
]}]}
env["_bloom_store_months"] = lambda p: {"2026-10": BOARD4}
dd = env["_daily_project_board"]("bloom_yfp", "2026-10")
ok([r["group"] for r in dd["rows"]] == ["NCT", "도장", "출하"],
   "구분이 일 보고에 적힌 공정 그대로가 아니다: %r"
   % ([r["group"] for r in dd["rows"]],))

# 그 달 일 보고가 없으면 가장 최근 달 일 보고의 공정으로 선다
env["_bloom_store_months"] = lambda p: {"2026-10": BOARD4}
dn11 = env["_daily_project_board"]("bloom_yfp", "2026-11")
ok([r["group"] for r in dn11["rows"]] == ["NCT", "도장", "출하"],
   "다음 달 보드가 지난 일 보고의 공정을 안 따랐다: %r"
   % ([r["group"] for r in dn11["rows"]],))

env["_bloom_store_months"] = lambda p: {"2026-10": BOARD}

# 지난달 자료가 없으면 '지난달' 열도 뺀다 ('지난달 0' 으로 읽히면 안 된다)
ok("prev_month_actual" in (d.get("hide_cols") or []),
   "지난달 자료가 없는데 '지난달' 열을 그리라고 보냈다 — 0 이 찍힌다")

# 지난달 자료가 있으면 그 열은 그린다
env["_daily_prev_by_group"] = lambda d, k, rows, prev: {
    "NCT": 12, "조립": 12, "출하": 12}
d2 = env["_daily_project_board"]("bloom_yfp", "2026-10")
ok("prev_month_actual" not in (d2.get("hide_cols") or []),
   "지난달 실적이 있는데 '지난달' 열을 빼 버렸다")
ok(d2["total"]["prev_month_actual"] == 36,
   "지난달 합계가 세 공정의 합이 아니다: %r" % (d2["total"]["prev_month_actual"],))
env["_daily_prev_by_group"] = lambda d, k, rows, prev: {}

# 품목 프로젝트가 아니면 손대지 않는다
_savedd = env["_daily_board_division"]
env["_daily_board_division"] = lambda k: ""
ok(env["_daily_project_board"]("hrva_plate", "2026-10") is None,
   "일 보고를 안 쓰는 사업부까지 이 함수가 가져갔다 — 반도체 보드를 "
   "빈 공정 표로 덮는다")
env["_daily_board_division"] = _savedd

# ── 3. ESS — 한 프로젝트가 품목을 여럿 맡는다 ─────────────────────
#
# 플루언스 하나가 품목 8종이다. 품목마다 줄을 세우면 8 × 3 = 24줄이 되어
# 못 읽는다. 공정이 같으면 한 줄로 더한다.
ESS_BOARD = {"items": [
    {"item": "SBB 1.5 (한국 함안)", "owner": "SDI",
     "wait_ship": 4, "wait_part": 1, "steps": [
        {"step": "제관/용접(수리)", "group": "제관/용접",
         "month_plan": 10, "month_actual": 9,
         "days": {"2026-10-05": {"plan": 10, "actual": 9}}},
        {"step": "조립", "group": "조립", "month_plan": 8, "month_actual": 7,
         "days": {"2026-10-05": {"plan": 8, "actual": 7}}},
        {"step": "출하", "group": "출하", "month_plan": 6, "month_actual": 5,
         "days": {"2026-10-05": {"plan": 6, "actual": 5}}},
    ]},
    {"item": "SBB 1.7 (미국 인디애나)", "owner": "SDI",
     "wait_ship": 6, "wait_part": None, "steps": [
        {"step": "제관/용접(수리)", "group": "제관/용접",
         "month_plan": 20, "month_actual": 18,
         "days": {"2026-10-06": {"plan": 20, "actual": 18}}},
        {"step": "조립", "group": "조립", "month_plan": 16, "month_actual": 14,
         "days": {"2026-10-06": {"plan": 16, "actual": 14}}},
        {"step": "출하", "group": "출하", "month_plan": 12, "month_actual": 11,
         "days": {"2026-10-06": {"plan": 12, "actual": 11}}},
    ]},
    {"item": "인버터 M10 (베트남)", "owner": "EPC POWER", "steps": [
        {"step": "출하", "group": "출하", "month_plan": 99, "month_actual": 99,
         "days": {"2026-10-06": {"plan": 99, "actual": 99}}},
    ]},
]}

env["_daily_board_division"] = lambda k: "ess"
env["_bloom_item_of"] = lambda k: ""          # ESS 는 품목 프로젝트가 아니다
env["_daily_store_key"] = lambda d: "ess_main"
env["_bloom_store_months"] = lambda p: {"2026-10": ESS_BOARD}
# 고객사 칸으로 고르는 부분만 흉내 낸다 (별칭 색인은 따로 시험한다)
env["_daily_board_items"] = lambda d, k, b: [
    it for it in (b.get("items") or [])
    if (it.get("owner") or "").lower().replace(" ", "")
       == {"sdi": "sdi", "epc_power": "epcpower"}.get(k, k)]

de = env["_daily_project_board"]("sdi", "2026-10")
# 품목마다 공정 세 줄 → SDI 는 품목 2 × 공정 3 = 여섯 줄
ok([r["group"] for r in de["rows"]]
   == ["제관/용접", "조립", "출하"] * 2,
   "ESS 보드 줄이 품목마다 제관/용접 · 조립 · 출하 가 아니다: %r"
   % ([r["group"] for r in de["rows"]],))
ok(de["total"]["month_plan"] == 30 + 24 + 18,
   "ESS 합계가 두 품목 · 세 공정의 합이 아니다: %r"
   % (de["total"]["month_plan"],))
ok(de["total"]["month_actual"] == 27 + 21 + 16,
   "ESS 실적 합계가 틀렸다: %r" % (de["total"]["month_actual"],))
ok(de["total"]["weeks"]["W41"]["actual"] == 27 + 21 + 16,
   "주차 합계가 두 품목의 합이 아니다: %r" % (de["total"]["weeks"]["W41"],))
# 다른 프로젝트 것이 섞이면 안 된다 (인버터 M10 은 EPC POWER)
ok(de["total"]["month_actual"] != 99 + 27 + 21 + 16,
   "다른 프로젝트(EPC POWER)의 품목이 SDI 보드에 섞였다")

# ESS 도 재고가 붙는다. 품목이 여럿이면 더해서 합계 줄에.
ok(de["total"]["wait_ship"] == 10,
   "ESS 출하대기가 품목 두 개의 합(4+6)이 아니다: %r"
   % (de["total"].get("wait_ship"),))
ok(de["total"]["wait_part"] == 1,
   "구매품대기에서 안 적힌 품목(None)이 0 으로 더해졌다: %r"
   % (de["total"].get("wait_part"),))
ok([c.get("field") for c in (de.get("stock_cols") or [])]
   == ["wip", "wait_ship", "wait_part"],
   "ESS 보드에 재고 열이 없다")

# ── 3-2. ESS 는 품목이 표에 다 적혀 있어야 한다 ────────────────────
#
# SDI 안에 SBB 1.5 · SBB 1.7 이 들어 있다. 다 더해 세 줄로 접으면 어느
# 품목이 밀렸는지가 안 보인다. 품목마다 묶음(section)을 만든다.
ok(de.get("layout") == "sections",
   "ESS 보드가 품목 묶음 표가 아니다: %r" % (de.get("layout"),))
ok(de.get("columns") == "week",
   "묶음 표인데 열이 주차가 아니다: %r" % (de.get("columns"),))
_names = [sec.get("name") for sec in (de.get("sections") or [])]
ok(_names == ["SBB 1.5 (한국 함안)", "SBB 1.7 (미국 인디애나)"],
   "SDI 안의 품목이 표에 안 적혔다: %r" % (_names,))
for _sec in (de.get("sections") or []):
    ok([r["group"] for r in _sec["rows"]] == ["제관/용접", "조립", "출하"],
       "품목 '%s' 묶음에 공정 세 줄이 다 없다: %r"
       % (_sec.get("name"), [r["group"] for r in _sec["rows"]]))

# 출하대기 · 구매품대기는 품목마다 한 번 (묶음 첫 줄)
_s0 = de["sections"][0]["rows"]
ok(_s0[0]["wait_ship"] == 4,
   "품목 묶음 첫 줄에 출하대기가 안 붙었다: %r" % (_s0[0].get("wait_ship"),))
ok(all(r.get("wait_ship") is None for r in _s0[1:]),
   "출하대기가 묶음 안에서 여러 줄에 붙었다 — 보는 사람이 더해 버린다")
ok(de["sections"][1]["rows"][0]["wait_ship"] == 6,
   "두 번째 품목의 출하대기가 틀렸다: %r"
   % (de["sections"][1]["rows"][0].get("wait_ship"),))

# 현황 · 비고 열은 일 보고에 없다 — 꺼서 보낸다
ok(de.get("show_status") is False and de.get("show_note") is False,
   "일 보고에 없는 현황·비고 열을 켜서 보냈다")

# 블룸은 묶음을 안 쓴다 (프로젝트 하나가 품목 하나 — 이름이 두 번 뜬다)
ok(d.get("layout") != "sections",
   "블룸까지 품목 묶음 표로 보냈다 — 제목과 같은 이름이 한 번 더 뜬다")

# 품목이 하나뿐인 프로젝트 — 줄은 그래도 세 줄
de2 = env["_daily_project_board"]("epc_power", "2026-10")
ok([r["group"] for r in de2["rows"]] == ["제관/용접", "조립", "출하"],
   "품목 하나인 ESS 프로젝트에서 줄이 빠졌다: %r"
   % ([r["group"] for r in de2["rows"]],))
ok([sec.get("name") for sec in (de2.get("sections") or [])]
   == ["인버터 M10 (베트남)"],
   "품목이 하나여도 이름은 표에 적혀야 한다: %r"
   % ([sec.get("name") for sec in (de2.get("sections") or [])],))
ok(de2["rows"][0]["month_plan"] is None,
   "자료 없는 공정을 0 으로 채웠다: %r" % (de2["rows"][0],))

# 사업부마다 줄 이름이 따로 적혀 있어야 한다
ok(set(env["_DAILY_BOARD_ROWS"]) >= {"bloom", "ess"},
   "_DAILY_BOARD_ROWS 에 블룸·ESS 가 다 있어야 한다: %r"
   % (list(env["_DAILY_BOARD_ROWS"]),))
ok("출하" in env["_DAILY_BOARD_ROWS"]["ess"],
   "ESS 줄에 출하가 없다 — 나간 수량을 볼 데가 없어진다")

# ── 3-1. 고객사 이름이 프로젝트에 붙는 길 ──────────────────────────
#
# 2026-10-26 — 전에는 config 에 박아 둔 ESS 프로젝트(sdi · fluence ·
# epc_power)에 이름이 붙는지 봤다. 이제 프로젝트는 엑셀이 만든다.
# 그래서 '지어 낸 목록' 으로 **붙이는 규칙**만 지킨다 — 똑같은 이름 ·
# 별칭 · 대소문자 · 띄어쓰기.
# 2026-10-27 — _df_keys 도 같이 떼 온다. 'TC' 처럼 줄여 적은 이름을 붙이려고
# _df_find_project 가 괄호 앞·안을 따로 보게 됐다(test_owner_alias.py).
# 안 떼 오면 NameError 로 넘어진다 — 규칙이 바뀐 게 아니라 조각이 하나 늘었다.
# 2026-11-03 — _df_typo_project 도 같이 떼 온다. 고객사 이름의 오타를
# 가장 가까운 한 곳에 붙이는 3단계가 _df_find_project 안에 생겼다
# (test_form_typo_owner.py).
_di = [n for n in tree.body if isinstance(n, ast.FunctionDef)
       and n.name in ("_df_norm", "_df_keys", "_df_digits", "_df_dam1",
                      "_df_typo_project", "_df_find_project")]
_di += [n for n in tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "_DF_TYPO_MIN_LEN"
                for t in n.targets)]
_ns = {}
exec(compile(ast.Module(body=_di, type_ignores=[]), "<main>", "exec"), _ns)
_idx = {}
for _n, _p in (("sdi", "ess_sdi"), ("SDI", "ess_sdi"),
               ("플루언스", "ess_fluence"), ("fluence", "ess_fluence"),
               ("epc power", "ess_epc_power")):
    _idx.setdefault(_ns["_df_norm"](_n), _p)
for _owner, _pid in (("SDI", "ess_sdi"), ("sdi", "ess_sdi"),
                     ("플루언스", "ess_fluence"), ("FLUENCE", "ess_fluence"),
                     ("EPC POWER", "ess_epc_power"), ("epc  power", "ess_epc_power")):
    ok(_ns["_df_find_project"](_owner, _idx) == _pid,
       "일 보고의 고객사 '%s' 가 %s 에 안 붙는다 (%r) — 그 프로젝트 "
       "보드가 빈 표가 된다" % (_owner, _pid, _ns["_df_find_project"](_owner, _idx)))
ok(_ns["_df_find_project"]("없는고객사", _idx) == "",
   "모르는 이름을 아무 프로젝트에나 붙였다")


# ── 4-1. 품목이 프로젝트를 갖는 길이 살아 있는가 ───────────────────
#
# 2026-10-26 — 전에는 config/projects.json 에 품목 여덟 개를 미리 적어
# 두고 '다 있는가' 를 셌다. 이제 프로젝트는 **올라온 엑셀**이 만든다.
# 미리 적어 둔 것과 엑셀에 적힌 이름이 달라지면(CORVA EFM KPE · SM)
# 화면에 '등록된 모델 없음' 짜리와 새로 생긴 것이 같이 서기 때문이다.
#
# 그래서 셀 것은 숫자가 아니라 **길**이다 — 양식이 프로젝트를 만들 때
# 일 보고 품목 이름(bloom_item)을 같이 붙이는가. 안 붙이면 새로 생긴
# 프로젝트는 일 보고를 잘라 볼 열쇠가 없어 보드가 통째로 빈다.
ok('row["bloom_item"] = r["owner"]' in SRC,
   "양식으로 만든 일 보고 프로젝트에 품목 이름을 안 붙인다")
ok("_daily_store_key(division_id)" in SRC,
   "일 보고 사업부인지 안 보고 품목 이름을 붙인다 — 반도체에까지 붙는다")

# ── 5. get_weekly_board 가 보드 설정보다 먼저 블룸을 본다 ──────────
gwb = by_name.get("get_weekly_board")
ok(gwb is not None, "get_weekly_board 가 없다")
if gwb:
    src = ast.unparse(gwb)
    i_bloom = src.find("_daily_project_board")
    i_spec = src.find("_load_board_spec")
    ok(i_bloom >= 0, "get_weekly_board 가 블룸 보드를 안 부른다")
    ok(i_spec < 0 or i_bloom < i_spec,
       "블룸을 보드 설정(_load_board_spec) 뒤에 본다 — 순서가 바뀌면 "
       "블룸이 다시 양산/개발 두 줄로 떨어진다")

if FAIL:
    print("\n".join("· " + m for m in FAIL))
    raise SystemExit(1)
print("ok — 블룸·ESS 보드는 공정별로 그린다")

# ======================================================================
#  일 보고에 없는 프로젝트는 빈 보드다 (2026-10-26)
#
#  양식으로 'SM' 프로젝트가 생겼는데 일 보고 자료에는 SM 이라는 품목이
#  없었다. 그때 '못 고르면 다 보여 준다' 로 두었더니, SM 에 들어가면
#  블룸 품목 여덟 개가 통째로 떴다 — 남의 자료다.
#
#  없으면 비운다. 비운 이유는 화면이 따로 말한다.
# ======================================================================
_sl = [n for n in tree.body if isinstance(n, ast.FunctionDef)
       and n.name == "_daily_slice_by_project"]
ok(bool(_sl), "_daily_slice_by_project 가 없다")
if _sl:
    _b = ast.unparse(_sl[0])
    ok("if not picked:" not in _b,
       "한 줄도 못 골랐다고 통째로 돌려준다 — 남의 자료가 뜬다")
    ok("_daily_slice_by_project(board, _key) or board" not in SRC,
       "부르는 쪽이 'or board' 로 못 고른 걸 다 보여준다")

    _ns2 = {"_cl": type("C", (), {"get_project": staticmethod(
        lambda pid: {"bloom_sm": {"id": "bloom_sm", "label": "SM"},
                     "bloom_yfp": {"id": "bloom_yfp", "label": "YFP"}}.get(pid))})}
    _ns2["_norm_label"] = lambda x: "".join(str(x or "").lower().split())
    exec(_b, _ns2)
    _board = {"items": [{"item": "YFP"}, {"item": "Corva KPE"}, {"item": "SL7"}]}
    _got = _ns2["_daily_slice_by_project"](_board, "bloom_sm")
    ok(isinstance(_got, dict) and _got["items"] == [],
       "일 보고에 없는 프로젝트(SM)에 남의 품목이 떴다: %r" % (_got or {}).get("items"))
    _got2 = _ns2["_daily_slice_by_project"](_board, "bloom_yfp")
    ok(isinstance(_got2, dict) and [x["item"] for x in _got2["items"]] == ["YFP"],
       "제 품목(YFP)을 못 골랐다: %r" % (_got2 or {}).get("items"))
    ok(len(_board["items"]) == 3, "원본 보드를 건드렸다")

_adm2 = (BACK / "admin_v2.html").read_text(encoding="utf-8")
ok("d.no_match" in _adm2,
   "화면이 '자료가 없다' 와 '내 이름이 거기 없다' 를 안 가른다")
ok("이 프로젝트는 일 보고 자료에 없습니다" in _adm2,
   "왜 비었는지 안 적어 준다 — 올린 사람은 업로드가 실패한 줄 안다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — 일 보고에 없는 프로젝트는 비운다")
