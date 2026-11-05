# -*- coding: utf-8 -*-
"""주차별 계획에 세울 줄을 사업부가 고른다 (2026-10-26).

아리스타는 품목이 90줄인데 주차 계획을 세우는 건 **렉(랙)** 일곱 줄뿐이다.
샷시 74줄까지 같이 세우면 주차 표가 아흔 줄이 되어 아무도 못 읽는다.

거르는 건 **사업부 화면의 보드 하나**다 (프로젝트를 한 줄씩 세우는 표).
  · 사업부 보드  — 렉이 든 프로젝트 7개만
  · 프로젝트 보드 — 그 프로젝트의 양산 · 개발 전부 (반도체와 같다)
  · 모델 목록 · 매출 — 90줄 전부

2026-10-26 — 한 번 프로젝트 보드에까지 걸었다가 Baja-Peninsula-90W 의
보드가 통째로 0 이 됐다. 그 모델은 샷시라 렉 조건에 안 맞아 다 걸러졌다.
밑의 '모델별 주차 계획' 에는 숫자가 있는데 위 보드만 0 이었다.

조심할 것
  · 조건에 맞는 줄이 **하나도 없으면 거르지 않는다.** 조건이 바뀌었거나
    아직 안 적은 것인데, 빈 표를 띄우면 "자료가 사라졌다" 가 된다.
  · 조건은 서버 한 곳(division_columns.WEEKLY_ONLY)이 들고 있다.
    화면이 따로 적어 두면 보드와 모델별 표가 서로 다른 줄을 센다.
"""
import ast
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACK = os.path.dirname(HERE)
sys.path.insert(0, BACK)

import division_columns as dc          # noqa: E402

SRC = io.open(os.path.join(BACK, "main.py"), encoding="utf-8").read()
tree = ast.parse(SRC)
FAIL = []


def ok(c, why):
    if not c:
        FAIL.append(why)


# ── 규칙이 한 곳에 있다
ok(dc.weekly_only("arista") == {"dev_type": ["렉"]},
   "아리스타 주차 계획 조건이 렉이 아니다: %r" % dc.weekly_only("arista"))
for d in ("pcb", "semiconductor", "ess", "bloom", "network", "automotive"):
    ok(dc.weekly_only(d) == {},
       "%s 에까지 조건이 걸렸다: %r" % (d, dc.weekly_only(d)))
ok("weekly_only" in dc.columns_for("arista"),
   "화면이 받는 열 구성에 조건이 안 실린다 — 화면이 따로 적게 된다")

# ── 거르는 함수
_WANT = ("_weekly_filtered", "_weekly_match", "_weekly_rule_live")
fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)
       and n.name in _WANT}
for _n in _WANT:
    ok(_n in fns, "%s 가 없다" % _n)
if len(fns) == len(_WANT):
    ns = {"_cl": type("C", (), {
              "get_project": staticmethod(
                  lambda pid: {"arista_monstro": {"division_id": "arista"},
                               "chamber": {"division_id": "semiconductor"}}.get(pid)),
              "get_projects": staticmethod(
                  lambda division_id=None, visible_only=True:
                      [{"id": "arista_monstro"}])}),
          "_dcol": dc,
          "_load_models": lambda: {"projects": {
              "arista_monstro": {"models": [{"id": "a", "dev_type": "렉"}]}}},
          "print": print}
    for _n in _WANT:
        exec(ast.unparse(fns[_n]), ns)
    f = ns["_weekly_filtered"]
    proj = {"models": [
        {"id": "a", "dev_type": "렉"},
        {"id": "b", "dev_type": "샷시"},
        {"id": "c", "dev_type": "캐스팅"},
        {"id": "d", "dev_type": "렉"},
    ], "weekly_summary": {"양산": {}}}
    got = f("arista_monstro", proj)
    ok([m["id"] for m in got["models"]] == ["a", "d"],
       "렉만 안 남겼다: %r" % [m["id"] for m in got["models"]])
    ok(got.get("weekly_summary") == proj["weekly_summary"],
       "프로젝트의 다른 값까지 잃었다")
    ok(len(proj["models"]) == 4, "원본을 건드렸다")

    # 반도체는 거르지 않는다
    ok(f("chamber", proj)["models"] is proj["models"],
       "조건이 없는 사업부에서 모델을 갈아끼웠다")

    # 사업부 어딘가에 렉이 있으면, 렉이 없는 프로젝트는 빈 줄이다.
    # (여기서 포기하면 그 프로젝트가 샷시 숫자를 그대로 띄운다)
    none_rack = {"models": [{"id": "x", "dev_type": "샷시"}]}
    ok(f("arista_monstro", none_rack)["models"] == [],
       "렉이 없는 프로젝트가 샷시 숫자를 띄운다")

    # 사업부 전체에 한 줄도 없으면 거르지 않는다 (빈 표를 띄우지 않는다)
    ns["_load_models"] = lambda: {"projects": {
        "arista_monstro": {"models": [{"id": "x", "dev_type": "샷시"}]}}}
    for _n in _WANT:
        exec(ast.unparse(fns[_n]), ns)
    ok(ns["_weekly_filtered"]("arista_monstro", none_rack)["models"]
       is none_rack["models"],
       "사업부 전체에 조건이 안 맞는데도 빈 표를 띄운다")

# ── 프로젝트 보드는 거르지 않는다
gwb = [n for n in tree.body if isinstance(n, ast.FunctionDef)
       and n.name == "get_weekly_board"]
ok(bool(gwb), "get_weekly_board 가 없다")
if gwb:
    b = ast.unparse(gwb[0])
    ok("_weekly_filtered" not in b,
       "프로젝트 보드까지 걸렀다 — 렉이 없는 프로젝트의 보드가 통째로 0 이 된다")

# ── 매출은 거르지 않는다 (매출은 샷시에서도 나온다)
rev = [n for n in tree.body if isinstance(n, ast.FunctionDef)
       and n.name == "get_weekly_revenue"]
if rev:
    ok("_weekly_filtered" not in ast.unparse(rev[0]),
       "매출까지 걸렀다 — 샷시 매출이 통째로 사라진다")

# ── 화면도 같은 조건을 쓴다
ADM = io.open(os.path.join(BACK, "admin_v2.html"), encoding="utf-8").read()
# 프로젝트 안의 '모델별 주차 계획' 도 거르지 않는다 — 위 보드와 아래 표가
# 같은 줄을 세야 숫자가 맞는다.
ok("_wpModels = window._wpOnlyRows(_wpModels);" not in ADM,
   "모델별 주차 계획까지 걸렀다 — 위 보드와 아래 표가 다른 줄을 센다")
ok("window._wpOnlyRows" in ADM, "거르는 길을 지웠다 — 되살릴 자리가 없다")

# ── 사업부 보드는 서버가 한 장으로 만든다
ok("/divisions/{division_id}/weekly-board" in SRC,
   "사업부 보드 주소가 없다 — 앱이 프로젝트를 하나씩 받아 제가 고르게 된다")
gdb = [n for n in tree.body if isinstance(n, ast.FunctionDef)
       and n.name == "get_division_weekly_board"]
ok(bool(gdb), "get_division_weekly_board 가 없다")
if gdb:
    b2 = ast.unparse(gdb[0])
    ok("_weekly_match(proj, want)" in b2, "조건에 맞는 프로젝트만 세우지 않는다")
    ok("_weekly_rule_live" in b2,
       "사업부 전체에 조건이 안 맞을 때 줄이 통째로 사라진다")
    # 2026-10-26 — 앞뒤 달을 안 실어 보내면 '지난달 실적' 열 머리글이
    # 비어서, 잔량과 W41 사이에 이름 없는 칸이 하나 선다.
    ok("'prev_month': prev" in b2 and "'next_month': nxt" in b2,
       "앞뒤 달을 안 실어 보낸다 — 지난달 열 머리글이 빈다")
    ok("prev = '%d-12' % (_y - 1) if _m == 1" in b2 or "_m == 1" in b2,
       "1월의 지난달(작년 12월)을 안 따진다")

MOB = os.path.join(os.path.dirname(BACK), "mobile", "lib")
_svc = io.open(os.path.join(MOB, "services", "division_board_service.dart"),
               encoding="utf-8").read()
ok("_divisionBoard(divisionId, month)" in _svc, "앱이 사업부 보드 주소를 안 쓴다")
ok("if (one != null) return one;" in _svc, "받아 놓고 안 쓴다")
_cfg = io.open(os.path.join(MOB, "config", "app_config.dart"), encoding="utf-8").read()
ok("kDivisionBoardOn = {'arista'}" in _cfg, "아리스타 사업부 보드를 안 켰다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — 주차별 계획에 세울 줄")
