# -*- coding: utf-8 -*-
"""블룸·ESS 의 주차별 매출 (2026-10-26).

왜 $0 이었나
    매출은 수량 × 판가인데, 수량을 **모델의 주차별 계획**에서만 찾았다.
    블룸 양식은 품목 정보(판가 · PO)까지만 읽고 주차 숫자는 일 보고
    자료가 싣고 온다. 그래서 모델에는 주차가 한 칸도 없었고, 매출이
    매주 $0 으로 떴다.

이제 나눠 받는다
    수량   일 보고 자료의 **출하** 공정 — 나간 수량이 곧 매출이다
    판가   사업부 양식 (그 프로젝트 모델의 판가, 여럿이면 평균)

조심할 것
    · 안 적은 주와 0 을 적은 주는 다르다. 안 적은 주는 아예 넣지 않는다.
    · 다른 달 날짜가 섞여 들어오면 그 달 매출이 부풀어 오른다.
    · 출하가 아닌 공정(NCT · 조립)은 세지 않는다 — 두 번 세게 된다.
"""
import ast
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACK = os.path.dirname(HERE)
sys.path.insert(0, BACK)

SRC = io.open(os.path.join(BACK, "main.py"), encoding="utf-8").read()
tree = ast.parse(SRC)
FAIL = []


def ok(c, why):
    if not c:
        FAIL.append(why)


by = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
ok("_daily_unit_price" in by, "판가를 내는 자리가 없다")
ok("_daily_ship_weeks" in by, "일 보고에서 출하 수량을 뽑는 자리가 없다")

# ── 판가: 평균. 빈 값 · 0 은 안 센다.
if "_daily_unit_price" in by:
    ns = {}
    exec(ast.unparse(by["_daily_unit_price"]), ns)
    f = ns["_daily_unit_price"]
    ok(f({"models": [{"price": 3230}]}) == 3230, "모델 하나짜리 판가가 틀렸다")
    ok(f({"models": [{"price": "3,230"}]}) == 3230, "쉼표 붙은 판가를 못 읽는다")
    ok(f({"models": [{"price": 100}, {"price": 300}]}) == 200,
       "모델 여럿일 때 평균이 아니다")
    ok(f({"models": [{"price": 100}, {"price": 0}, {"price": ""}]}) == 100,
       "판가가 빈 모델까지 평균에 넣었다 — 매출이 반토막 난다")
    ok(f({"models": []}) == 0.0, "모델이 없는데 판가가 나왔다")

# ── 매출 계산이 양산 칸에 들어가는가
if "get_weekly_revenue" in by:
    b = ast.unparse(by["get_weekly_revenue"])
    ok("_daily_ship_weeks" in b, "매출이 일 보고 수량을 안 본다")
    ok("_daily_unit_price" in b, "매출이 양식 판가를 안 본다")
    ok("not p and (not a)" in b or "if not p and not a:" in b,
       "안 적은 주를 0 으로 넣는다 — 안 적음과 0 이 같아진다")

# ── 출하만 센다 · 그 달만 센다
if "_daily_ship_weeks" in by:
    b2 = ast.unparse(by["_daily_ship_weeks"])
    ok("'출하'" in b2 or '"출하"' in b2,
       "출하 말고 다른 공정까지 세고 있다 — 같은 수량을 두 번 센다")
    ok("strftime('%Y-%m') != month" in b2 or 'strftime("%Y-%m") != month' in b2,
       "다른 달 날짜를 걸러내지 않는다")
    ok("isocalendar()" in b2, "ISO 주차로 안 묶는다 — 보고 자료의 '41주차' 와 어긋난다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — 일 보고 매출")

# ======================================================================
#  ESS — 고객사 칸으로 고른다 (2026-10-26)
#
#  ESS 일 보고에는 품목 왼쪽에 고객사 열이 따로 있다. 품목 이름은
#  'SBB 1.5 (한국 함안)' 처럼 고객사가 안 들어가 있어서, 이름만 뒤지면
#  SDI 프로젝트가 한 줄도 못 고르고 보드가 통째로 빈다.
# ======================================================================
_sl2 = [n for n in tree.body if isinstance(n, ast.FunctionDef)
        and n.name == "_daily_slice_by_project"]
ok(bool(_sl2), "_daily_slice_by_project 가 없다")
if _sl2:
    _b3 = ast.unparse(_sl2[0])
    ok("get('owner')" in _b3 or 'get("owner")' in _b3,
       "고객사 칸을 안 본다 — ESS 보드가 통째로 빈다")
    _ns3 = {"_cl": type("C", (), {"get_project": staticmethod(
        lambda pid: {"ess_sdi": {"id": "ess_sdi", "label": "SDI"},
                     "ess_fluence": {"id": "ess_fluence", "label": "FLUENCE",
                                     "aliases": ["플루언스"]}}.get(pid))})}
    _ns3["_norm_label"] = lambda x: "".join(str(x or "").lower().split())
    exec(_b3, _ns3)
    _bd = {"items": [
        {"owner": "SDI", "item": "SBB 1.5 (한국 함안)"},
        {"owner": "SDI", "item": "SBB 1.7 (미국 인디애나)"},
        {"owner": "플루언스", "item": "GSP5000 (베트남)"},
        {"owner": "EPC POWER", "item": "인버터 M10 (베트남)"},
    ]}
    _g1 = _ns3["_daily_slice_by_project"](_bd, "ess_sdi")
    ok([x["item"] for x in _g1["items"]] ==
       ["SBB 1.5 (한국 함안)", "SBB 1.7 (미국 인디애나)"],
       "SDI 품목을 못 골랐다: %r" % [x["item"] for x in _g1["items"]])
    # 양식은 FLUENCE, 일 보고는 플루언스 — 별칭이 있어야 붙는다
    _g2 = _ns3["_daily_slice_by_project"](_bd, "ess_fluence")
    ok([x["item"] for x in _g2["items"]] == ["GSP5000 (베트남)"],
       "별칭(플루언스)으로 못 붙였다: %r" % [x["item"] for x in _g2["items"]])

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — ESS 고객사 고르기")
