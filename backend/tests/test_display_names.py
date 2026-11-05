# -*- coding: utf-8 -*-
"""엑셀에 적힌 이름 → 화면에 띄울 이름 (2026-10-26).

엑셀마다 같은 곳을 다르게 적는다.

    ESS 양식   FLUENCE
    ESS 일보고 플루언스

둘 중 하나로 고르면 다른 파일이 안 붙는다. 그래서 **원문은 그대로 두고**
화면 이름만 바꾼다. 원문은 별칭으로 남아서, 다음 달에 영문으로 와도
같은 프로젝트를 찾는다.

여기 없는 이름은 적힌 그대로 둔다. 모르는 회사를 음차하면
'LAM 스파트로닉스' 처럼 오히려 못 알아본다 — 아는 것만 적는다.
"""
import ast
import io
import json
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


# ── 표가 있고, 열쇠가 소문자·공백 없음인가
CFG = os.path.join(BACK, "config", "display_names.json")
ok(os.path.exists(CFG), "표시 이름 표(config/display_names.json)가 없다")
if os.path.exists(CFG):
    names = (json.loads(io.open(CFG, encoding="utf-8").read()).get("names") or {})
    ok(names, "표가 비었다")
    bad = [k for k in names if k != "".join(k.lower().split())]
    ok(not bad, "열쇠는 소문자·공백 없이 적어야 한다: %r" % bad)
    ok(names.get("fluence") == "플루언스",
       "FLUENCE 를 플루언스로 안 띄운다 — ESS 양식과 일 보고가 안 붙는다")
    ok(names.get("texon") == "텍슨", "텍슨이 표에 없다")

# ── 찾는 함수
fn = [n for n in tree.body if isinstance(n, ast.FunctionDef)
      and n.name == "_display_name"]
ok(bool(fn), "_display_name 이 없다")
if fn and os.path.exists(CFG):
    ns = {"Path": __import__("pathlib").Path, "json": json,
          "_DISPLAY_NAMES": None,
          "__file__": os.path.join(BACK, "main.py")}
    exec(ast.unparse(fn[0]), ns)
    f = ns["_display_name"]
    ok(f("FLUENCE") == "플루언스", "대문자를 못 찾는다: %r" % f("FLUENCE"))
    ok(f("fluence") == "플루언스", "소문자를 못 찾는다")
    ok(f("Daeyoung Electric") == "대영전기", "띄어쓰기가 있는 이름을 못 찾는다")
    ok(f("없는회사") == "", "모르는 이름에 아무거나 붙였다: %r" % f("없는회사"))
    ok(f(None) == "" and f("") == "", "빈 이름에 아무거나 붙였다")

# ── 프로젝트를 만들 때 원문을 별칭으로 남기는가
mk = [n for n in tree.body if isinstance(n, ast.FunctionDef)
      and n.name == "_df_create_projects"]
ok(bool(mk), "_df_create_projects 가 없다")
if mk:
    b = ast.unparse(mk[0])
    ok("_display_name(r['owner'])" in b or '_display_name(r["owner"])' in b,
       "프로젝트 이름에 표시 이름을 안 쓴다")
    ok("_names = [r['owner']]" in b or '_names = [r["owner"]]' in b,
       "엑셀 원문을 별칭에 안 남긴다 — 다음 달에 영문으로 오면 못 붙는다")
    ok("'aliases': _names" in b or '"aliases": _names' in b,
       "별칭에 두 이름을 다 안 넣는다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — 화면에 띄울 이름")
