# 개발품(RPM)이 양식에서 빠져도 자료를 잃지 않는다 (2026-10-27).
#
# Min: "개발 같은 경우에는 RPM으로 rapid production이라서 한 번 들어갔다가
#      다음주차에 없어질수도 있어 이건 이슈가 있지 않는 이상 그냥 개발이
#      끝나서 사라질 수도 있는거라 이건 잘 데이터 저장이 되어야해"
#
# 세 가지를 지킨다.
#   1) 양식에서 빠졌다고 지우지 않는다 (지우면 주차별 계획·실적이 통째로 사라진다)
#   2) 언제부터 안 보이는지 적어 둔다 — 안 그러면 끝난 것과 도는 것이 섞인다
#   3) 다시 나타나면 그 표시를 뗀다 (RPM 은 들어왔다 나갔다 한다)
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
apply_src = ""
for n in ast.walk(tree):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
            and n.name == "admin_division_form_apply":
        apply_src = ast.unparse(n)
ok(apply_src, "admin_division_form_apply 가 없다")

# ── 1. 기본은 '안 지움'
ok("if remove_missing and stale:" in apply_src,
   "양식에 없는 모델을 사람 확인 없이 지운다")
sig = src[src.index("async def admin_division_form_apply"):][:900]
ok("remove_missing: bool = Form(False)" in sig or "remove_missing: bool = Form(default=False)" in sig,
   "'양식에 없는 모델 지우기' 가 기본으로 켜져 있다 — 개발품이 조용히 사라진다")

# ── 2. 빠진 때를 적는다
ok("'missing_since'" in apply_src,
   "양식에서 빠진 모델에 아무 표시도 안 남긴다 — 끝난 것과 도는 것이 섞인다")
ok("if not m.get('missing_since')" in apply_src,
   "빠진 때를 매번 덮어쓴다 — '언제부터' 가 늘 오늘이 된다")

# ── 3. 다시 나타나면 뗀다
ok("m.pop('missing_since', None)" in apply_src,
   "다시 올라온 모델의 '빠짐' 표시를 안 뗀다 — RPM 은 들어왔다 나갔다 한다")
ok("m['last_form'] = " in apply_src,
   "양식에 나온 때를 안 적는다 — 마지막으로 언제 돌았는지 알 수 없다")

# ── 4. 빠진 줄에도 주차별 계획은 그대로 남아야 한다
#      (지우는 코드가 weekly_plan 을 건드리지 않는가)
i = apply_src.find("if remove_missing and stale:")
blk = apply_src[i:i + 900]
ok("weekly_plan" not in blk, "지우는 자리에서 주차별 계획을 건드린다")

# ── 5. 화면이 갈라 보여 준다
html = io.open(os.path.join(HERE, "..", "admin_v2.html"), encoding="utf-8").read()
ok("function _mdlGone(m)" in html, "모델 목록이 '양식에서 빠짐' 을 안 그린다")
ok("'.mdl-gone {" in html or "'.mdl-gone{" in html, "그 표시에 모양이 없다")
ok("#B91C1C" not in html.split(".mdl-gone")[1][:200],
   "빠진 줄을 빨갛게 그린다 — 문제가 아니라 개발이 끝난 것이다")

# ── 6. 개발도 모델별로 보인다 (합계 한 줄로 묶지 않는다)
ok("function _wpAllowDev(pk) { return true; }" in html,
   "아직 어떤 프로젝트는 개발을 '개발 (합계)' 한 줄로 묶는다")

if bad:
    for b in bad:
        print("FAIL:", b)
    raise SystemExit(1)
print("ok test_rpm_keep")
