# -*- coding: utf-8 -*-
"""일 보고 자료 접기 — 지난 주는 통치고 이번 주만 날짜로 펼친다.

ESS 와 블룸은 보고 자료가 날마다 들어온다. 한 달치를 날짜 그대로 그리면
열이 31개라 아무도 못 읽는다. 그래서 이렇게 접는다.

    지난 주차   →  주 한 칸
    이번 주차   →  날짜 그대로
    다음 주차~  →  주 한 칸

여기서 지키려는 것
  1. 두 사업부 보고자료가 다 읽힌다 (ESS 는 고객사 열이 하나 더 있다)
  2. 한 파일에 여러 달 시트가 있어도 **그 달** 시트를 고른다
  3. 이번 주만 날짜로 펼쳐진다
  4. 지난 주 칸은 그 주 날짜의 합이다
  5. 안 적은 칸(None)과 0 을 섞지 않는다
  6. '이전 데이터' 칸도 지난 기간으로 함께 앞에 선다
"""
import datetime as dt
import os
import sys

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
BACK = os.path.dirname(HERE)
sys.path.insert(0, BACK)
sys.path.insert(0, HERE)
import bloom_daily_import as bd      # noqa: E402
import daily_view as dv              # noqa: E402

FORMS = os.path.join(HERE, "forms")
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


def load(name):
    return openpyxl.load_workbook(os.path.join(FORMS, name), data_only=True)


TODAY = "2026-10-25"      # 43주차 (10/19 월 ~ 10/25 일)

# ── 1. 두 보고자료가 읽힌다 ─────────────────────────────────────
ess = bd.parse_daily(load("ESS_일보고.xlsx"), month="2026-10")
bloom = bd.parse_daily(load("블룸_일보고.xlsx"), month="2026-10")

ok(len(ess["items"]) > 0, "ESS 보고자료에서 품목을 못 읽었다")
ok(len(bloom["items"]) > 0, "블룸 보고자료에서 품목을 못 읽었다")

# ESS 는 고객사 열이 있다 — 블룸에는 없다
owners = {it.get("owner") for it in ess["items"]}
ok("SDI" in owners, f"ESS 고객사를 못 읽었다: {owners}")
ok(all(not it.get("owner") for it in bloom["items"]),
   "블룸에 없는 고객사 열을 억지로 만들었다")

# ── 2. 한 파일에 여러 달이 있어도 그 달 시트를 고른다 ───────────
#    블룸 파일에는 9·10·11·12월 네 장이 들어 있다. 뒤쪽 달은 계획만
#    있고 실적이 비어 있어서, 아무거나 고르면 이번 달이 통째로 빈다.
ok("10월" in str(ess["sheet"]), f"ESS 시트를 {ess['sheet']} 로 골랐다")
ok("10월" in str(bloom["sheet"]), f"블룸 시트를 {bloom['sheet']} 로 골랐다")
nov = bd.parse_daily(load("블룸_일보고.xlsx"), month="2026-11")
ok("11월" in str(nov["sheet"]), f"11월을 달라는데 {nov['sheet']} 를 줬다")

# ── 3. 이번 주만 날짜로 펼쳐진다 ────────────────────────────────
view = dv.build(bloom, today=TODAY)
cols = view["columns"]
days = [c for c in cols if c["kind"] == "day"]
weeks = [c for c in cols if c["kind"] == "week"]

ok(len(days) == 7, f"이번 주 날짜 칸이 {len(days)}개다 (7개여야 한다)")
ok(days[0]["date"] == "2026-10-19", f"이번 주가 {days[0]['date']} 부터다")
ok(days[-1]["date"] == "2026-10-25", f"이번 주가 {days[-1]['date']} 까지다")
ok(all(dv.week_no(d["date"]) == 43 for d in days), "이번 주가 아닌 날이 펼쳐졌다")

labels = [c["label"] for c in weeks]
ok("40주차" in labels and "41주차" in labels and "42주차" in labels,
   f"지난 주차가 안 묶였다: {labels}")
ok("44주차" in labels, f"다음 주차가 안 묶였다: {labels}")
ok("43주차" not in labels, "이번 주차가 주 한 칸으로도 또 들어갔다")

# 열 순서 — 지난 주 → 이번 주 날짜 → 다음 주
kinds = [c["kind"] for c in cols]
first_day = kinds.index("day")
last_day = len(kinds) - 1 - kinds[::-1].index("day")
ok(all(k == "day" for k in kinds[first_day:last_day + 1]),
   "이번 주 날짜 사이에 다른 칸이 끼었다")
ok(all(c.get("past") for c in cols[:first_day] if c["kind"] == "week"),
   "이번 주 앞에 다음 주차가 왔다")

# ── 4. 지난 주 칸은 그 주 날짜의 합이다 ─────────────────────────
#    Corva KPE 의 NCT 공정으로 직접 더해 맞춰 본다.
target = None
for it in bloom["items"]:
    if it["item"].startswith("Corva"):
        for st in it["steps"]:
            if st["step"].startswith("NCT"):
                target = st
                break
ok(target is not None, "맞춰 볼 공정을 못 찾았다")

if target:
    w41 = None
    for c in cols:
        if c.get("label") == "41주차":
            w41 = c
    ok(w41 is not None, "41주차 칸이 없다")
    want_plan = 0
    want_actual = 0
    for ds in w41["dates"]:
        cell = target["days"].get(ds) or {}
        want_plan += (cell.get("plan") or 0)
        want_actual += (cell.get("actual") or 0)

    row = None
    for r in view["rows"]:
        if r["item"].startswith("Corva") and r["step"].startswith("NCT"):
            row = r
    got = row["cells"][cols.index(w41)]
    ok(got["plan"] == want_plan,
       f"41주차 계획이 {got['plan']} 인데 날짜 합은 {want_plan} 이다")
    ok(got["actual"] == want_actual,
       f"41주차 실적이 {got['actual']} 인데 날짜 합은 {want_actual} 이다")

# ── 5. 안 적은 칸과 0 을 섞지 않는다 ────────────────────────────
#    하루도 안 적힌 주차는 0 이 아니라 '비어 있음' 이어야 한다.
blank = dv.fold_row({}, cols)
ok(all(c["plan"] is None and c["actual"] is None for c in blank),
   "아무것도 안 적힌 줄이 0 으로 채워졌다")

half = dv.fold_row({"2026-10-05": {"plan": 0, "actual": None}}, cols)
i41 = [i for i, c in enumerate(cols) if c.get("label") == "41주차"][0]
ok(half[i41]["plan"] == 0, "사람이 적은 0 이 사라졌다")
ok(half[i41]["actual"] is None, "안 적은 실적이 0 이 됐다")

# ── 6. '이전 데이터' 칸 (ESS 에만 있다) ─────────────────────────
ev = dv.build(ess, today=TODAY)
prior = [c for c in ev["columns"] if c["kind"] == "prior"]
ok(len(prior) == 1, f"ESS '이전 데이터' 칸이 {len(prior)}개다")
if prior:
    ok(ev["columns"][0]["kind"] == "prior", "'이전 데이터' 가 맨 앞이 아니다")
    ok("이전" in prior[0]["label"], f"칸 이름이 '{prior[0]['label']}' 이다")
    # 값이 실제로 들어갔는지 — SBB 1.7 제관/용접 은 12/12 로 적혀 있다
    got = None
    for r in ev["rows"]:
        if r["item"].startswith("SBB 1.7") and r["step"].startswith("제관"):
            got = r["cells"][0]
    ok(got and got["plan"] == 12 and got["actual"] == 12,
       f"'이전 데이터' 값이 안 들어갔다: {got}")

ok(len([c for c in ev["columns"] if c["kind"] == "day"]) == 7,
   "ESS 도 이번 주는 7일이어야 한다")

# ── 7. 열이 31개에서 열몇 개로 줄었다 ───────────────────────────
ok(len(cols) <= 13, f"접었는데도 열이 {len(cols)}개다")
ok(len(bloom["dates"]) >= 28, "원본은 한 달치 날짜를 다 갖고 있어야 한다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for m in FAIL:
        print("  -", m)
    raise SystemExit(1)
print("전부 통과 · 일 보고 접기 검사 7묶음 · 열 %d개 → %d개"
      % (len(bloom["dates"]), len(cols)))
