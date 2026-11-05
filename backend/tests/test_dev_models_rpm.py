# 개발(RPM) 품목 — 모델별로 보여주고, 사라져도 자료는 남긴다 (2026-10-27).
#
# Min: "하바플레이트 개발 같은 경우에는 기존에는 구별하기 어려웠는데
#      이제는 구분으로 나눠지니까 개발도 보여줘"
#      "개발 같은 경우에는 RPM으로 rapid production이라서 한 번 들어갔다가
#      다음주차에 없어질수도 있어서 이건 잘 데이터 저장이 되어야해"
#
# 전에는 하바플레이트 개발을 '개발 (합계)' 한 줄로 손으로 넣었다. 양식에
# '구분' 칸이 없던 시절의 임시 방편이다. 그런데 보드가 그 총계를 **먼저**
# 봐서, 양식으로 들어온 모델별 숫자가 화면에 안 떴다 —
# 10월 W43 이 모델별로는 84/74 인데 보드에는 50/0 으로 떴다.
import ast
import datetime
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

bad = []


def ok(cond, why):
    if not cond:
        bad.append(why)


src = io.open(os.path.join(HERE, "..", "main.py"), encoding="utf-8").read()
tree = ast.parse(src)

# ── 1. 보드 계산 — 모델이 숫자를 들고 있으면 모델이 정본
ns = {"_dt": datetime, "re": __import__("re")}
need = ["_norm_group", "_group_bucket", "_phase_at", "_phase_row_at",
        "_norm_phases", "_dev_models_have_weeks", "_dev_week_totals"]
for n in ast.walk(tree):
    if isinstance(n, ast.FunctionDef) and n.name in need:
        try:
            exec(compile(ast.Module([n], []), "<m>", "exec"), ns)
        except Exception:
            pass
for n in need:
    ok(n in ns, "main.py 에서 %s 를 떼어내지 못했다" % n)

if all(n in ns for n in need):
    M, W = "2026-10", ["W41", "W42", "W43", "W44"]
    grp = {"weekly_summary": {"개발": {"weeks": {
        "W41": {"plan": 42, "actual": 75}, "W43": {"plan": 50, "actual": 0}}}}}

    # (가) 모델에 숫자가 없으면 — 손으로 넣은 그룹 총계를 그대로 쓴다
    a = dict(grp); a["models"] = []
    got = ns["_dev_week_totals"](a, M, W)
    ok(got["W41"] == {"plan": 42, "actual": 75},
       "모델에 숫자가 없는데 그룹 총계를 안 쓴다 (%s)" % got["W41"])

    # (나) 모델이 숫자를 들고 있으면 — 모델별 합이 이긴다
    b = dict(grp)
    b["models"] = [{"group": "개발", "weekly_plan": {M: {
        "W41": {"plan": 36, "actual": 48}, "W43": {"plan": 84, "actual": 74}}}}]
    got = ns["_dev_week_totals"](b, M, W)
    ok(got["W43"] == {"plan": 84, "actual": 74},
       "양식으로 들어온 모델별 숫자가 묻힌다 — 그룹 총계가 이긴다 (%s)" % got["W43"])
    ok(got["W41"] == {"plan": 36, "actual": 48},
       "모델별 합이 아니다 (%s)" % got["W41"])

    # (다) 다른 달 숫자만 있으면 이 달에는 영향이 없다
    c = dict(grp)
    c["models"] = [{"group": "개발", "weekly_plan": {"2026-09": {"W39": {"plan": 9}}}}]
    got = ns["_dev_week_totals"](c, M, W)
    ok(got["W41"] == {"plan": 42, "actual": 75},
       "다른 달 모델 숫자 때문에 이 달 그룹 총계가 밀렸다 (%s)" % got["W41"])

# ── 2. 화면 — 개발도 모델별 카드로 뜬다
html = io.open(os.path.join(HERE, "..", "admin_v2.html"), encoding="utf-8").read()
ok("function _wpAllowDev(pk) { return true; }" in html,
   "아직 어떤 프로젝트의 개발을 '합계' 한 줄로 묶고 있다")
ok("pk !== 'hrva_plate'" not in html,
   "하바플레이트만 빼는 옛 규칙이 남아 있다")

# ── 3. RPM — 사라져도 자료가 남는가
fn = ""
for n in ast.walk(tree):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
            and n.name == "admin_division_form_apply":
        fn = ast.unparse(n)
ok(fn, "admin_division_form_apply 가 없다")

# 지우는 것은 사람이 켰을 때만 (기본은 안 지운다)
ok("if remove_missing and stale:" in fn,
   "양식에 없는 모델을 조건 없이 지운다 — 이번 주에 빠진 RPM 품목이 날아간다")
sig = src[src.index("async def admin_division_form_apply"):][:900]
ok("remove_missing: bool = Form(False)" in sig or "remove_missing: bool = False" in sig,
   "'양식에 없는 모델 지우기' 가 기본으로 켜져 있다 (%s)" % sig[:200])

# 주차는 그 주차 칸만 갈아 끼운다 — 양식에 없는 주차는 그대로 둔다
ok("wp.setdefault(_mon, {})[_wk] = _cell" in fn,
   "주차를 통째로 갈아 끼운다 — 지난 주 숫자가 사라진다")

# 마지막으로 양식에 실려 온 주차를 적어 둔다
ok("m['last_form'] = {'week': got.get('as_of_week')" in fn
   or '"last_form"' in fn,
   "언제까지 양식에 있었는지 안 적는다 — 남은 자료가 '진행 중' 인지 "
   "'지난주까지' 인지 가릴 수 없다")

if bad:
    for b in bad:
        print("FAIL:", b)
    raise SystemExit(1)
print("ok test_dev_models_rpm")
