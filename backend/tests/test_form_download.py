# 양식 받기 — 지금 등록된 내용을 채워서 내려준다 (2026-10-27).
#
# Min: "엑셀 양식 다운받기 버튼을 엑셀 올리기 옆에 둬서 … 10월이랑 11월
#      주차별이 보이게끔 … 이미 있는 내용들은 그대로 반영되어서 엑셀에
#      다운 받을 때 넣어서 줘"
#
# 이 기능의 전부는 **받은 파일을 그대로 다시 올릴 수 있는가** 다.
# 모양이 한 칸이라도 어긋나면 담당자가 고쳐서 올렸을 때 안 읽힌다.
# 그래서 만든 것을 파서에 도로 넣어 보는 검사를 둔다.
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import openpyxl                       # noqa: E402
import division_columns as dcol       # noqa: E402
import division_form_export as exp    # noqa: E402
import division_form_import as imp    # noqa: E402

bad = []


def ok(cond, why):
    if not cond:
        bad.append(why)


ROWS = [
    {"owner": "CUP", "part_number": "02-434103-00", "name": "", "group": "양산",
     "dev_type": "HVM", "price_currency": "USD", "price": 5557,
     "material_currency": "USD", "material_cost": 4187.24, "year_qty": 314,
     "po_qty": 558, "shipped_qty": 294, "note": "진원도 확인",
     "weekly_plan": {"2026-10": {"W43": {"plan": 5, "actual": 3}},
                     "2026-11": {"W45": {"plan": 9, "actual": 0}}}},
    {"owner": "CUP", "part_number": "853-B92561-001", "name": "", "group": "개발",
     "price_currency": "USD", "price": 9200, "po_qty": 1, "shipped_qty": 1,
     "weekly_plan": {}},
]

# ── 1. 되읽기 — 만든 양식을 파서에 도로 넣는다
for div in ("semiconductor", "pcb", "arista"):
    blob = exp.build(div, ROWS, "2026-10", 2)
    wb = openpyxl.load_workbook(io.BytesIO(blob), data_only=True)
    g = imp.parse_workbook(wb, division_id=div)
    ok(len(g["items"]) == len(ROWS),
       "%s: 만든 양식을 되읽으니 품목이 %d건 (넣은 건 %d건)"
       % (div, len(g["items"]), len(ROWS)))
    ok(not g["warnings"], "%s: 되읽기에 경고가 떴다 — %s" % (div, g["warnings"]))
    if g["items"]:
        it = g["items"][0]
        ok(it["po_qty"] == 558, "%s: PO 수량이 안 돌아왔다 (%r)" % (div, it["po_qty"]))
        ok(it["shipped_qty"] == 294, "%s: 실적수량이 안 돌아왔다" % div)
        ok(it["price"] == 5557, "%s: 판가가 안 돌아왔다 (%r)" % (div, it["price"]))
        ok(it["group"] == "양산", "%s: 구분이 안 돌아왔다 (%r)" % (div, it["group"]))
        ok(it["owner"] == "CUP", "%s: 프로젝트·고객사가 안 돌아왔다" % div)
        # 주차 — 이번 달과 다음 달 둘 다
        wk = it["weeks"] or {}
        ok(wk.get("W43") == {"plan": 5, "actual": 3},
           "%s: 이번 달 주차가 안 돌아왔다 (%s)" % (div, wk))
        ok(wk.get("W45") == {"plan": 9, "actual": 0},
           "%s: 다음 달 주차가 안 돌아왔다 — 블록을 둘 깔아 둔 뜻이 없다 (%s)"
           % (div, wk))

# ── 2. 주차 블록이 두 달치인가 (머리글 글자로 확인)
blob = exp.build("semiconductor", ROWS, "2026-10", 2)
ws = openpyxl.load_workbook(io.BytesIO(blob)).active
heads = [ws.cell(exp.HEAD_ROW, c).value for c in range(1, ws.max_column + 1)]
ok("10월 주차별 계획 · 실적" in heads, "이번 달 주차 블록이 없다")
ok("11월 주차별 계획 · 실적" in heads, "다음 달 주차 블록이 없다")

# ── 3. 주차를 안 읽는 사업부에는 주차 칸을 주지 않는다
#
#      읽지도 않을 칸을 그려 주면 담당자가 거기 적는다. 적어도 안
#      들어가고, 올린 사람은 왜 안 들어갔는지 모른다.
#
#      2026-10-28 — 전에는 블룸이 그런 사업부라고 적혀 있었다. 그런데
#      블룸 양식에는 처음부터 주차 칸이 있었고, N열에서 잘라서 못 읽은
#      것뿐이었다. 이제 자르는 사업부가 하나도 없으니, 규칙만 가짜
#      사업부로 지킨다 — 블룸은 아래 4번에서 주차를 **받아야** 한다.
#      Min: "그냥 일단은 파일에 있는 내용 그대로 반영해줘"
ok(dcol.LAST_COL == {}, "멈출 사업부가 생겼다 — 왜 생겼는지 적고 이 검사를 고쳐라")
dcol.LAST_COL["bloom"] = 14
try:
    bws = openpyxl.load_workbook(io.BytesIO(exp.build("bloom", ROWS, "2026-10", 2))).active
    bh = [str(bws.cell(exp.HEAD_ROW, c).value or "") for c in range(1, bws.max_column + 1)]
    ok(not any("주차별" in h for h in bh),
       "열을 자르는 사업부에 주차 칸을 그렸다 — 적어도 안 읽힌다 (%s)" % bh)
finally:
    dcol.LAST_COL.pop("bloom", None)

# 자르지 않는 지금의 블룸은 주차 칸을 받아야 한다 — 양식에 있는 칸이다
bws2 = openpyxl.load_workbook(io.BytesIO(exp.build("bloom", ROWS, "2026-10", 2))).active
bh2 = [str(bws2.cell(exp.HEAD_ROW, c).value or "") for c in range(1, bws2.max_column + 1)]
ok(any("주차별" in h for h in bh2),
   "블룸 양식에 주차 칸이 없다 — 받는 양식에는 있는데 주는 양식에 없다 (%s)" % bh2)

# ── 4. 사업부마다 열이 다르다 (division_columns 를 따른다)
sh = [str(ws.cell(exp.HEAD_ROW, c).value or "") for c in range(1, ws.max_column + 1)]
ok("연간수량" in sh, "반도체 양식에 연간수량이 없다")
pws = openpyxl.load_workbook(io.BytesIO(exp.build("pcb", ROWS, "2026-10", 2))).active
ph = [str(pws.cell(exp.HEAD_ROW, c).value or "") for c in range(1, pws.max_column + 1)]
ok("연간수량" not in ph, "고객사형 양식에 없는 칸(연간수량)을 세웠다")
ok("고객사" in ph, "고객사형인데 머리글이 '고객사' 가 아니다")

# ── 5. 품목이 하나도 없어도 빈 양식이 나온다 (새 사업부)
blank = exp.build("semiconductor", [], "2026-10", 2)
bws2 = openpyxl.load_workbook(io.BytesIO(blank)).active
ok(bws2.cell(exp.HEAD_ROW, 4).value == "No.", "빈 양식에 머리글이 없다")

# ── 6. 창구와 단추
msrc = io.open(os.path.join(HERE, "..", "main.py"), encoding="utf-8").read()
ok('@app.get("/admin/divisions/{division_id}/form/download")' in msrc,
   "양식 받는 창구가 없다")
ok("get_admin_session" in msrc.split('@app.get("/admin/divisions/{division_id}/form/download")')[1][:900],
   "아무나 사업부 자료를 받아 갈 수 있다")
html = io.open(os.path.join(HERE, "..", "admin_v2.html"), encoding="utf-8").read()
ok('id="mdl-form-get"' in html, "'양식 받기' 단추가 없다")
ok(html.index('id="mdl-form-get"') < html.index('id="mdl-form-toggle"'),
   "'양식 받기' 가 '엑셀 올리기' 옆이 아니다")
ok("window._divFormGetBind" in html, "단추에 고리를 안 걸었다")
ok("if (window._divFormGetBind) window._divFormGetBind();" in html,
   "화면을 그릴 때 고리를 안 건다 — 눌러도 아무 일이 없다")

if bad:
    for b in bad:
        print("FAIL:", b)
    raise SystemExit(1)
print("ok test_form_download")
