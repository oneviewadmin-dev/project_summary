# -*- coding: utf-8 -*-
"""연간수량 열과 PO 변동 칩 (2026-10-26).

### 연간수량

반도체 양식에만 있는 칸이다. 예전에는 아예 안 읽어서, 양식에 적어 올려도
화면 어디에도 안 나왔다. 다른 사업부 양식에는 없으므로 **값이 있는 모델이
하나라도 있을 때만** 열을 세운다 — 사업부 이름으로 가르면 양식이 바뀔 때
코드를 또 고쳐야 하고, 늘 비어 있는 열은 "왜 안 적혀 있지" 를 묻게 만든다.

### PO 변동

"PO 수량 변동도 보였으면 좋겠다" 는 요청인데, 그걸 낼 자료가 없었다.
양식을 올릴 때마다 전/후를 po_log 에 적어 두고, 화면에서 ▲12 · ▼8 로
보여 준다. 기록이 끝없이 쌓이면 models.json 이 무거워져서 최근 12번만 둔다.
"""
import ast
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACK = os.path.dirname(HERE)
sys.path.insert(0, BACK)

FAIL = []
def ok(c, m):
    if not c: FAIL.append(m)

# ── 1. 파서가 세 칸을 읽는다 ────────────────────────────────────
import openpyxl                                   # noqa: E402
import division_form_import as dfi                # noqa: E402

for w in ("연간수량", "분류", "비고"):
    found = any(w in str(x) for grp in (dfi.YEAR_WORDS, dfi.CLASS_WORDS, dfi.NOTE_WORDS)
                for x in grp)
    ok(found, "'%s' 를 찾는 말이 없다" % w)

f = os.path.join(HERE, "forms", "v2", "반도체.xlsx")
if os.path.exists(f):
    got = dfi.parse_workbook(openpyxl.load_workbook(f, data_only=True))
    ok(got["weeks"][0] == "W40",
       "반도체 양식은 W40 부터다: %r" % (got["weeks"][:1],))
    ok(got["items"], "반도체 양식에서 품목을 하나도 못 읽었다")
    if got["items"]:
        it = got["items"][0]
        ok("year_qty" in it, "연간수량을 안 읽는다")
        ok(it.get("note"), "비고를 안 읽는다: %r" % (it.get("note"),))

# 다른 사업부 양식에는 그 칸이 없다 → None · 빈 글자여야 한다 (0 아님)
f2 = os.path.join(HERE, "forms", "v2", "ESS.xlsx")
if os.path.exists(f2):
    g2 = dfi.parse_workbook(openpyxl.load_workbook(f2, data_only=True))
    for it in g2["items"]:
        ok(it.get("year_qty") is None,
           "연간수량 칸이 없는 양식인데 %r 로 읽었다 — 0 이면 '연간 0대' 로 "
           "읽힌다" % (it.get("year_qty"),))

# ── 2. 반영이 저장한다 + PO 변동을 적는다 ───────────────────────
SRC = io.open(os.path.join(BACK, "main.py"), encoding="utf-8").read()
tree = ast.parse(SRC)
fn = next((n for n in ast.walk(tree)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
           and n.name == "admin_division_form_apply"), None)
ok(fn is not None, "admin_division_form_apply 가 없다")
if fn:
    body = ast.unparse(fn)
    for k in ("year_qty", "dev_type", "note"):
        ok("m['%s'] = it['%s']" % (k, k) in body or 'm["%s"]' % k in body,
           "반영이 %s 를 저장하지 않는다" % k)
    ok("po_log" in body, "PO 수량이 바뀌어도 기록을 안 남긴다")
    # 2026-10-27 — 12번이었다. 양식이 주에 한 번 올라오니 12번은 석 달도
    # 못 채우는데, 보드의 PO증감 칸은 지난 6개월을 보여준다. 60번으로 늘렸다.
    # (몇 번이든 상관없지만 '안 자른다' 는 안 된다 — 끝없이 쌓인다)
    ok("del _log[:-60]" in body,
       "po_log 를 잘라내지 않는다 — models.json 이 끝없이 무거워진다")

# ── 3. 화면이 그린다 ────────────────────────────────────────────
ADM = io.open(os.path.join(BACK, "admin_v2.html"), encoding="utf-8").read()
ok("_hasYearQty" in ADM, "화면이 연간수량 열을 모른다")
ok("m.year_qty !== undefined" in ADM,
   "값이 있는 모델이 있을 때만 세우는 판단이 없다")
ok('data-field="year_qty"' in ADM, "연간수량 칸이 줄에 없다")
ok("_poDelta" in ADM and "mdl-podelta" in ADM, "PO 변동 칩이 없다")
ok("if (!log.length) return ''" in ADM,
   "기록이 없을 때 빈 칩을 그린다 — 처음 올린 모델이 그렇다")
ok("(_hasYearQty ? 3 : 2)" in ADM,
   "연간수량을 세워도 '수량' 묶음 머리글 칸 수를 안 늘렸다 — 표가 밀린다")

if FAIL:
    print("\n".join("· " + m for m in FAIL))
    raise SystemExit(1)
print("ok — 연간수량 · PO 변동")
