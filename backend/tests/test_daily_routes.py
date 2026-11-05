# -*- coding: utf-8 -*-
"""일 보고 자료를 받는 길과 내보내는 길.

ESS 와 블룸은 보고 자료가 날마다 들어온다. 한 장에 사업부 전체가 들어
있어서 프로젝트가 아니라 **사업부 단위**로 받는다.

여기서 지키려는 것
  1. 사업부 단위 주소 세 개가 있다 (미리보기 · 반영 · 접은 표)
  2. 두 사업부만 받는다 — 자리가 없는 사업부는 분명히 거절한다
  3. 옛 블룸 주소를 지우지 않았다 (화면이 아직 그걸 부른다)
  4. 미리보기와 반영이 같은 계산을 쓴다
  5. 접는 규칙은 한 곳(daily_view)에만 있다 — 화면마다 접으면 모양이 갈린다
  6. 읽는 주소는 관리자 전용이 아니다 (앱이 봐야 한다)
"""
import ast
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

funcs = {}
for n in ast.walk(tree):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        funcs[n.name] = n


def routes_of(node):
    out = []
    for dec in node.decorator_list:
        if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
            continue
        if not (isinstance(dec.func.value, ast.Name) and dec.func.value.id == "app"):
            continue
        if dec.args and isinstance(dec.args[0], ast.Constant):
            out.append((dec.func.attr.lower(), dec.args[0].value))
    return out


by_route = {}
for f in funcs.values():
    for m, r in routes_of(f):
        by_route[r] = (m, f)

# ── 1. 주소 세 개 ───────────────────────────────────────────────
WANT = {
    "/admin/divisions/{division_id}/daily/preview": "post",
    "/admin/divisions/{division_id}/daily/apply": "post",
    "/divisions/{division_id}/daily-view": "get",
}
for r, method in WANT.items():
    ok(r in by_route, f"{r} 주소가 없다")
    if r in by_route:
        ok(by_route[r][0] == method, f"{r} 가 {by_route[r][0]} 이다 ({method} 여야 한다)")

# ── 2. 받는 사업부는 자리가 정해져 있다 ─────────────────────────
ok("_DAILY_STORE" in SRC, "사업부별 자리표(_DAILY_STORE)가 없다")
ok('"ess"' in SRC and "_BLOOM_STORE" in SRC, "ESS·블룸 자리가 안 적혀 있다")

need = funcs.get("_daily_need_store")
ok(need is not None, "_daily_need_store 문지기가 없다")
if need:
    src = ast.unparse(need)
    ok("HTTPException" in src, "자리가 없는 사업부를 그냥 통과시킨다")
    ok("400" in src, "거절할 때 400 을 쓰지 않는다")

for r in ("/admin/divisions/{division_id}/daily/preview",
          "/admin/divisions/{division_id}/daily/apply"):
    f = by_route.get(r)
    if not f:
        continue
    src = ast.unparse(f[1])
    ok("_daily_need_store" in src, f"{r} 가 사업부를 안 가린다")

# ── 3. 옛 블룸 주소를 안 지웠다 ─────────────────────────────────
for r in ("/admin/projects/{project_key}/bloom-daily",
          "/admin/projects/{project_key}/bloom-daily/preview"):
    ok(r in by_route, f"{r} 를 지웠다 — 화면이 아직 이걸 부른다")

# ── 4. 미리보기와 반영이 같은 계산을 쓴다 ───────────────────────
pv = by_route.get("/admin/divisions/{division_id}/daily/preview")
ap = by_route.get("/admin/divisions/{division_id}/daily/apply")
if pv and ap:
    for name, f in (("미리보기", pv[1]), ("반영", ap[1])):
        src = ast.unparse(f)
        ok("_bloom_parse_months" in src, f"{name} 가 파일을 안 읽는다")
        ok("_bloom_apply_months" in src, f"{name} 가 합치는 계산을 안 쓴다")
    # 미리보기는 저장하면 안 된다
    ok("_save_models" not in ast.unparse(pv[1]),
       "미리보기가 저장한다 — 눌러 보기만 해도 자료가 바뀐다")
    ok("_save_models" in ast.unparse(ap[1]), "반영이 저장하지 않는다")

# ── 5. 접는 규칙은 한 곳에만 ────────────────────────────────────
view = by_route.get("/divisions/{division_id}/daily-view")
ok(view is not None, "접은 표를 내보내는 주소가 없다")
if view:
    src = ast.unparse(view[1])
    ok("daily_view" in src, "접는 코드를 안 쓰고 직접 접는다")
    ok("build" in src, "daily_view.build 를 안 부른다")

# 접는 함수 안에서 주차를 직접 세면 안 된다.
#
# main.py 에는 '이번 주차가 몇 주차인가' 를 세는 자리가 원래 여럿 있다
# (보드의 빨간 테두리 · 알림 · 챗봇). 그건 접는 일과 상관없다.
# 여기서 막으려는 것은 **접는 규칙이 두 군데로 갈라지는 것** 하나다.
if view:
    vsrc = ast.unparse(view[1])
    ok("isocalendar" not in vsrc,
       "접어 내보내는 주소가 주차를 직접 센다 — daily_view 한 곳에 두어야 한다")
    # 설명(docstring)에 '주차' 가 나오는 건 괜찮다 — 그건 글이지 계산이 아니다.
    # 실제 코드 줄만 본다.
    body = list(view[1].body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    code_only = "\n".join(ast.unparse(x) for x in body)
    for word in ("weekday", "timedelta", "주 합계"):
        ok(word not in code_only,
           f"접는 계산('{word}')을 여기서 또 하고 있다 — daily_view 한 곳에 두어야 한다")

# ── 6. 읽는 주소는 앱도 봐야 한다 ───────────────────────────────
if view:
    src = ast.unparse(view[1])
    ok("get_admin_session" not in src,
       "접은 표를 관리자만 볼 수 있다 — 앱이 못 읽는다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for m in FAIL:
        print("  -", m)
    raise SystemExit(1)
print("전부 통과 · 일 보고 주소 %d개" % len(WANT))
