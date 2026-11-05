# -*- coding: utf-8 -*-
"""엑셀을 올리는 길은 '사업부 양식' 하나다.

사업부마다 다른 양식을 쓰던 때에 업로드 주소가 스무 곳 넘게 붙었다.
양식을 한 벌로 모았으니, 그 양식이 대신하는 길은 닫혀 있어야 한다.
길이 여럿이면 담당자가 어디에 올릴지 모르고, 길마다 읽는 규칙이 달라
같은 숫자가 다르게 들어간다.

여기서 지키려는 것
  1. 사업부 양식 주소(미리보기 · 반영) 두 개가 있다
  2. 양식이 대신하는 업로드는 문지기(_form_only)가 막는다
  3. 양식이 안 담는 업로드(매출 · 매입 · 공정 …)는 열려 있어야 한다
  4. 문지기는 파일을 읽기 **전에** 선다 — 읽고 나서 막으면 보관함에
     쓸데없는 원본이 쌓인다
  5. 한 줄로 되돌릴 수 있다 (DIVISION_FORM_ONLY)
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
            out.append(dec.args[0].value)
    return out


by_route = {}
for f in funcs.values():
    for r in routes_of(f):
        by_route.setdefault(r, f)

# ── 1. 사업부 양식 주소가 있다 ──────────────────────────────────
for r in ("/admin/divisions/{division_id}/form/preview",
          "/admin/divisions/{division_id}/form/apply"):
    ok(r in by_route, f"{r} 주소가 없다")

# ── 2. 양식이 대신하는 길은 막혀 있다 ───────────────────────────
BLOCKED = {
    "/admin/projects/{project_key}/models/import": "모델 등록 양식",
    "/admin/projects/{project_key}/plan-file/preview": "주차별 계획 미리보기",
    "/admin/projects/{project_key}/plan-file/apply": "주차별 계획 반영",
    "/admin/projects/{project_key}/status-excel": "주간 현황 엑셀",
    "/admin/automotive/product-import/preview": "자동차 제품 미리보기",
    "/admin/automotive/product-import/apply": "자동차 제품 반영",
}


def first_stmts(node, n=4):
    """함수 본문의 앞쪽 몇 줄 (docstring 은 건너뛴다)."""
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return body[:n]


def calls_form_only(stmts):
    for st in stmts:
        for x in ast.walk(st):
            if isinstance(x, ast.Call) and ast.unparse(x.func) == "_form_only":
                return True
    return False


def reads_file(stmts):
    """이 줄들 안에서 파일을 읽는가."""
    for st in stmts:
        for x in ast.walk(st):
            if isinstance(x, ast.Call):
                name = ast.unparse(x.func)
                if name.endswith("_keep_upload") or name.endswith(".read") \
                        or name.endswith("_pbx_open_upload") \
                        or name.endswith("_auto_read_upload"):
                    return True
    return False


for route, label in BLOCKED.items():
    f = by_route.get(route)
    ok(f is not None, f"{route} 주소가 사라졌다")
    if f is None:
        continue
    head = first_stmts(f, 6)
    ok(calls_form_only(head),
       f"{label}({route}) 가 안 막혀 있다 — _form_only 를 첫 줄에 두어야 한다")

    # ── 4. 읽기 전에 막는가
    #    _form_only 가 나오기 전에 파일을 읽으면 안 된다.
    seen_guard = False
    read_first = False
    body = list(f.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    for st in body:
        if calls_form_only([st]):
            seen_guard = True
            break
        if reads_file([st]):
            read_first = True
            break
    ok(seen_guard and not read_first,
       f"{label}: 파일을 읽은 뒤에 막는다 — 보관함에 쓸데없는 원본이 쌓인다")

# ── 3. 양식이 안 담는 업로드는 열려 있다 ────────────────────────
OPEN = {
    "/admin/revenue/import": "매출 관리",
    "/admin/division/purchase/import-xlsx": "매입",
    "/admin/overtime/import-xlsx": "초과근무",
    "/admin/projects/{project_key}/process/import-xlsx": "공정",
    "/admin/projects/{project_key}/bloom-daily": "블룸 일일",
    "/admin/app/release": "앱 배포",
}
for route, label in OPEN.items():
    f = by_route.get(route)
    ok(f is not None, f"{route} 주소가 사라졌다")
    if f is None:
        continue
    ok(not calls_form_only(first_stmts(f, 8)),
       f"{label}({route}) 까지 막았다 — 사업부 양식에 그 내용이 없다")

# ── 5. 한 줄로 되돌릴 수 있다 ───────────────────────────────────
ok("DIVISION_FORM_ONLY = True" in SRC, "되돌릴 스위치가 없다")
guard = funcs.get("_form_only")
ok(guard is not None, "_form_only 문지기가 없다")
if guard:
    src = ast.unparse(guard)
    ok("DIVISION_FORM_ONLY" in src, "문지기가 스위치를 안 본다")
    ok("return" in src, "스위치를 꺼도 안 열린다")
    ok("403" in src, "막을 때 403 을 쓰지 않는다")
    ok("양식" in src, "어디로 가야 하는지 안 알려 준다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for m in FAIL:
        print("  -", m)
    raise SystemExit(1)
print("전부 통과 · 막은 길 %d개 · 열어 둔 길 %d개" % (len(BLOCKED), len(OPEN)))
