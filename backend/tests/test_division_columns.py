# -*- coding: utf-8 -*-
"""사업부별 표 열 구성이 양식과 같은지.

올려주신 양식 7종을 직접 열어 대조한다. 양식이 바뀌었는데 화면이 안
바뀌면(또는 그 반대면) 여기서 깨진다 — 눈으로는 안 보이는 어긋남이다.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import division_columns as dc

FAIL = []
def ok(c, m):
    if not c: FAIL.append(m)

# ── 1. 세 모양뿐이다
ok(set(dc.SHAPES.values()) == {"반도체형", "고객사형", "프로젝트형"},
   "양식 모양이 셋이 아니다: %r" % (set(dc.SHAPES.values()),))

# ── 2. 반도체만 분류 · 연간수량 · 비고를 쓴다
semi = dc.columns_for("semiconductor")
keys = [c["key"] for c in semi["columns"]]
for k in ("dev_type", "year_qty", "note"):
    ok(k in keys, "반도체 표에 %s 가 없다" % k)
ok(semi["primary"] == "part_number",
   "반도체는 파트넘버가 먼저여야 한다: %r" % (semi["primary"],))
ok(semi["week_count"] == 5, "반도체는 W40~W44 다섯 주차다")

# ── 3. 고객사형에는 그 셋이 없다 (빈 열을 세우면 안 된다)
for div in ("ess", "pcb", "network", "automotive"):
    c = dc.columns_for(div)
    ks = [x["key"] for x in c["columns"]]
    for k in ("dev_type", "year_qty", "note"):
        ok(k not in ks, "%s 표에 양식에 없는 %s 열이 섰다" % (div, k))
    ok(c["owner_label"] == "고객사", "%s 첫 열은 '고객사' 다" % div)
    # 파트넘버를 안 적는 품목이 많아 품목명이 먼저다
    ok(c["primary"] == "name",
       "%s 는 품목명이 먼저여야 한다: %r" % (div, c["primary"]))
    ok(c["week_count"] == 4, "%s 는 W41~W44 네 주차다" % div)

# ── 4. 프로젝트형은 파트넘버가 먼저
for div in ("bloom", "arista"):
    c = dc.columns_for(div)
    ok(c["owner_label"] == "프로젝트", "%s 첫 열은 '프로젝트' 다" % div)
    ok(c["primary"] == "part_number",
       "%s 는 파트넘버가 먼저여야 한다: %r" % (div, c["primary"]))

# ── 5. 모르는 사업부도 표가 떠야 한다 (빈 화면이 제일 나쁘다)
nw = dc.columns_for("무슨사업부")
ok(nw["columns"], "모르는 사업부에서 표가 통째로 비었다")

# ── 6. 열 이름이 COLUMN_SPEC 에 다 있다 (오타 막기)
for form in dc.FORMS.values():
    for k in form["columns"]:
        ok(k in dc.COLUMN_SPEC, "COLUMN_SPEC 에 없는 열: %s" % k)
    for k in (form["primary"], form["secondary"]):
        ok(k in dc.COLUMN_SPEC, "COLUMN_SPEC 에 없는 열: %s" % k)

if FAIL:
    print("\n".join("· " + m for m in FAIL))
    raise SystemExit(1)
print("ok — 사업부 %d곳, 양식 모양 3가지" % len(dc.SHAPES))
