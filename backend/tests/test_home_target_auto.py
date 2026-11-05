# 홈 관리 — 타겟은 자동으로 채우고, 고치는 건 매출 관리에서 (2026-10-27).
#
# Min:
#   "만약에 내가 타겟을 적지 않은 이상 그냥 그 달 계획 다 합쳐서 타겟으로"
#   "파란 박스에 있는거 수정 못 하게 해줘 수정은 매출 관리에서"
#   "매출 없는 애들은?"  (앱 홈 미리보기에 두 줄만 떠 있었다)
#   "사업부 왼쪽에 있는거 왜 이렇게 회색으로 보이냐 전 색깔로 돌려주고"
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

# ── 1. 그 달 계획을 더해 타겟으로 쓴다
#      main.py 는 통째로 import 가 안 되므로(서버 의존 패키지) 필요한
#      함수 둘만 떼어내 그 자리에서 돌린다.
ns = {}
need = ["_as_money", "_div_plan_money"]
for n in ast.walk(tree):
    if isinstance(n, ast.FunctionDef) and n.name in need:
        exec(compile(ast.Module([n], []), "<main>", "exec"), ns)
for n in need:
    ok(n in ns, "main.py 에서 %s 를 떼어내지 못했다" % n)

if len(ns) >= len(need):
    plan = ns["_div_plan_money"]
    models = [
        # 10월에 계획 3 + 2 = 5개, 판가 100 → 500
        {"price": 100, "weekly_plan": {"2026-10": {"W41": {"plan": 3, "actual": 1},
                                                   "W42": {"plan": 2, "actual": 0}},
                                       # 다른 달은 안 센다
                                       "2026-09": {"W40": {"plan": 99, "actual": 0}}}},
        # 판가에 쉼표가 섞여 와도 읽는다. 계획 2개 × 1,250 = 2500
        {"price": "1,250", "weekly_plan": {"2026-10": {"W43": {"plan": 2}}}},
        # 계획이 없는 모델은 안 센다
        {"price": 9999, "weekly_plan": {"2026-10": {"W41": {"plan": 0}}}},
        # 주차 계획 자체가 없는 모델
        {"price": 500},
    ]
    got = plan(models, "2026-10")
    ok(got == 2500 + 500, "그 달 계획 합계가 3000 이어야 하는데 %r" % got)
    ok(plan(models, "2026-11") == 0, "계획이 없는 달인데 금액이 나온다")
    ok(plan([], "2026-10") == 0, "모델이 없는데 금액이 나온다")

# ── 2. 손으로 적은 타겟이 늘 먼저다 (계산이 사람 숫자를 덮으면 안 된다)
rows = ""
for n in ast.walk(tree):
    if isinstance(n, ast.FunctionDef) and n.name == "_home_division_rows":
        rows = ast.unparse(n)
ok(rows, "_home_division_rows 가 없다")
ok("_div_plan_money(models, month)" in rows, "그 달 계획을 타겟으로 안 쓴다")
ok("'그 달 계획 합계'" in rows, "타겟 출처를 안 적는다 — 어디서 온 숫자인지 모른다")
i_manual = rows.find("'직접 입력'")
i_auto = rows.find("_div_plan_money(models, month)")
ok(0 <= i_manual < i_auto,
   "계산한 타겟이 직접 입력한 타겟보다 먼저 온다 — 사람이 적은 값을 덮는다")

# ── 3. 화면
html = io.open(os.path.join(HERE, "..", "admin_v2.html"), encoding="utf-8").read()

# 홈 관리에는 타겟 입력칸이 없다
ok("'<input class=\"ha-tgt\"" not in html and "<input class=\\'ha-tgt" not in html,
   "홈 관리에 타겟 입력칸이 남아 있다 — 고치는 자리가 두 군데가 된다")
ok("매출 관리</b>에서 넣어 주세요" in html,
   "어디서 고치는지 안 알려준다")
ok("'.ha-tgt { width:120px" in html,
   "타겟 입력칸 CSS 를 지웠다 — 되살릴 때 모양이 깨진다")

# 앱 홈 미리보기는 사업부를 전부 세운다
ok("var divs = (_st.divisions || []);" in html,
   "미리보기가 자료 없는 사업부를 뺀다 — 블룸이 어디 갔는지 알 수 없다")

# 사이드바 사업부 상자를 흐리게 하던 것을 되돌렸다
ok("body.scope-all .biz-box{ opacity:1; }" in html,
   "전사 화면에서 사업부 메뉴가 여전히 흐리다 — 잠긴 것처럼 읽힌다")
ok("body.scope-all .biz-box{ opacity:.45; }" not in html,
   "흐리게 하던 옛 규칙이 남아 있다")

if bad:
    for b in bad:
        print("FAIL:", b)
    raise SystemExit(1)
print("ok test_home_target_auto")
