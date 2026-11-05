# 사업부 매출 실적을 '그 달' 로 가른다 (2026-10-27).
#
# 전에는 판가 × 출하 **누계** 하나뿐이었다. 그래서 매출 관리에서 달을
# 10월로 골라도 숫자가 안 바뀌었다 — 고르는 칸이 있는데 아무 일도 안
# 일어나면 고장 난 것으로 읽힌다.
#
# 이제 주차별 실적이 있으면 달로 가른다.
#
# 2026-11-03 — '없으면 누계' 를 뺐다. 누계는 달과 상관없는 값이라, 11월
# 3일에 11월 실적이 $1187만으로 떴다 (자동차는 10월도 11월도 똑같이
# $253만 5,913). 출처 글자로 구분된다고 적어 뒀지만 앱에는 그 글자가
# 안 뜬다 — 보는 사람에게는 그냥 '그 달 실적' 이다.
#   Min: "왜 누계로 되는거야...누구 마음대로"
# 그 달 자료가 없으면 0 이다. 누계는 '연간 누적' 자리에만 선다.
import ast
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

ns = {}
need = ["_as_money", "_div_actual_money", "_div_plan_money", "_div_model_money"]
for n in ast.walk(tree):
    if isinstance(n, ast.FunctionDef) and n.name in need:
        exec(compile(ast.Module([n], []), "<main>", "exec"), ns)
for n in need:
    ok(n in ns, "main.py 에서 %s 를 떼어내지 못했다" % n)

if len(ns) >= len(need):
    act, plan, cum = ns["_div_actual_money"], ns["_div_plan_money"], ns["_div_model_money"]
    models = [
        {"price": 100, "shipped_qty": 50,
         "weekly_plan": {"2026-10": {"W41": {"plan": 5, "actual": 3},
                                     "W42": {"plan": 2, "actual": 0}},
                         "2026-09": {"W40": {"plan": 9, "actual": 9}}}},
        {"price": 200, "shipped_qty": 10,
         "weekly_plan": {"2026-10": {"W43": {"plan": 1, "actual": 2}}}},
        {"price": 500, "shipped_qty": 4},
    ]
    ok(act(models, "2026-10") == 700, "10월 실적이 700 이어야 한다 (%r)" % act(models, "2026-10"))
    ok(act(models, "2026-09") == 900, "9월 실적이 900 이어야 한다 (%r)" % act(models, "2026-09"))
    ok(plan(models, "2026-10") == 900, "10월 계획이 900 이어야 한다 (%r)" % plan(models, "2026-10"))
    ok(cum(models) == 9000, "누계가 9000 이어야 한다 (%r)" % cum(models))

    # 주차 자료가 아예 없는 달은 None — 0 으로 주면 '그 달에 하나도 안
    # 나갔다' 로 읽히는데, 사실은 주차별로 안 적는 사업부일 뿐이다.
    ok(act(models, "2026-12") is None, "주차 자료가 없는 달이 0 으로 나온다")
    ok(act([], "2026-10") is None, "모델이 없는데 숫자가 나온다")

    # 0 이라고 적은 것은 0 이다 (안 적은 것과 다르다)
    z = [{"price": 100, "weekly_plan": {"2026-10": {"W41": {"plan": 5, "actual": 0}}}}]
    ok(act(z, "2026-10") == 0, "실적 0 을 '안 적음' 으로 읽는다 (%r)" % act(z, "2026-10"))

# ── 쓰는 자리
rows = ""
for n in ast.walk(tree):
    if isinstance(n, ast.FunctionDef) and n.name == "_home_division_rows":
        rows = ast.unparse(n)
ok("_div_actual_money(models, month)" in rows, "홈 관리 줄이 달별 실적을 안 쓴다")
ok("'판가 × 그 달 실적'" in rows, "출처를 안 적는다 — 누계인지 월별인지 모른다")
# 주차 자료가 없으면 0 이다 — 누계로 돌아가면 안 된다 (2026-11-03)
ok("'판가 × 출하 (누계)'" not in rows, "아직 누계로 돌아간다")
ok("(actual, a_src) = (0.0, '')" in rows,
   "그 달 자료가 없을 때 0 으로 안 둔다")

view = ""
for n in ast.walk(tree):
    if isinstance(n, ast.FunctionDef) and n.name == "_div_revenue_view":
        view = ast.unparse(n)
ok("_div_actual_money(ms, month)" in view,
   "프로젝트별 줄이 누계라 합계와 안 맞는다 — 더해도 안 맞으면 어느 쪽이 틀렸는지 찾게 된다")

# 반도체·블룸은 원본이 따로다. 건드리면 안 된다.
ok("rv.get('actual')" in rows or 'rv.get("actual")' in rows,
   "반도체 실적이 주간보고에서 안 온다")
ok("done_usd" in rows, "블룸 실적이 보고자료에서 안 온다")

if bad:
    for b in bad:
        print("FAIL:", b)
    raise SystemExit(1)
print("ok test_division_month_revenue")
