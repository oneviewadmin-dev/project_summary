# -*- coding: utf-8 -*-
"""주소에 적은 { } 를 그 함수가 진짜 받는지.

### 왜 이걸 세나

2026-10-25 에 실제로 났던 일이다. 주석을 풀어쓰다가 도우미 함수를 두 개
새로 만들어 넣었는데, 하필 끼워 넣은 자리가 이랬다.

    @app.get("/projects/{project_key}/weekly-board")
    def _sum_of(items, field):        # ← 데코레이터가 여기 붙어 버렸다
        ...
    def get_weekly_board(project_key, month=None):   # ← 주소가 없어졌다

파이썬은 바로 아래 함수에 데코레이터를 붙인다. 그래서 주차 현황 보드
주소가 `_sum_of` 로 연결되고, `project_key` 를 안 받으니 모든 사업부의
보드가 통째로 안 뜬다. 코드는 멀쩡해 보이고 테스트도 안 깨졌다 —
서버를 띄워서 눌러 보기 전까지는 아무도 모른다.

### 무엇을 보나

  · 주소에 {project_key} 가 있으면 그 함수도 project_key 를 받아야 한다
  · 라우트 함수 이름이 밑줄(_)로 시작하면 안 된다 — 밑줄은 이 코드에서
    '안에서만 쓰는 도우미' 라는 뜻이다. 도우미에 주소가 붙었다는 건
    위와 같은 사고가 났다는 뜻이다
"""
import ast
import re
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


SRC = (BACK / "main.py").read_text(encoding="utf-8")
tree = ast.parse(SRC)

# ── 1. app.get / app.post … 이 붙은 함수를 모은다
routes = []
for node in ast.walk(tree):
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    for dec in node.decorator_list:
        if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
            continue
        if not (isinstance(dec.func.value, ast.Name) and dec.func.value.id == "app"):
            continue
        if dec.func.attr.lower() not in ("get", "post", "put", "patch", "delete"):
            continue
        if dec.args and isinstance(dec.args[0], ast.Constant):
            routes.append((dec.args[0].value, node))

ok(len(routes) >= 100,
   "주소를 %d개만 찾았다 — 찾는 방법이 깨진 것 같다" % len(routes))

# ── 2. 주소의 { } 를 그 함수가 받는지
for path, fn in routes:
    taken = [a.arg for a in fn.args.args] + [a.arg for a in fn.args.kwonlyargs]
    for var in re.findall(r"\{(\w+)\}", str(path)):
        ok(var in taken,
           "%s (%d번째 줄 %s) 가 {%s} 를 안 받는다 — 데코레이터가 엉뚱한 "
           "함수에 붙은 것 같다" % (path, fn.lineno, fn.name, var))

# ── 3. 도우미(_로 시작)에 주소가 붙어 있으면 사고다
for path, fn in routes:
    ok(not fn.name.startswith("_"),
       "%s 가 도우미 함수 %s 에 붙어 있다 (%d번째 줄) — 데코레이터와 "
       "라우트 함수 사이에 뭔가 끼어 들어갔다" % (path, fn.name, fn.lineno))

# ── 4. 같은 주소·같은 방식이 두 번 적혀 있으면 뒤에 적은 것만 산다
seen = {}
for node in ast.walk(tree):
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    for dec in node.decorator_list:
        if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
            continue
        if not (isinstance(dec.func.value, ast.Name) and dec.func.value.id == "app"):
            continue
        if dec.func.attr.lower() not in ("get", "post", "put", "patch", "delete"):
            continue
        if not (dec.args and isinstance(dec.args[0], ast.Constant)):
            continue
        k = (dec.func.attr.lower(), dec.args[0].value)
        if k in seen:
            FAIL.append("%s %s 가 두 번 적혀 있다 (%d번째 줄, %d번째 줄) — "
                        "뒤에 적은 것만 돌아간다"
                        % (k[0].upper(), k[1], seen[k], node.lineno))
        else:
            seen[k] = node.lineno

if FAIL:
    print("\n".join("· " + m for m in FAIL))
    raise SystemExit(1)
print("ok — 주소 %d개, 모두 제 함수에 붙어 있다" % len(routes))
