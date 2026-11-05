# -*- coding: utf-8 -*-
"""사업부 양식(품목정보 · 이슈사항) 읽기.

여기서 지키려는 것
  1. 다섯 사업부 양식이 전부 읽힌다 (열 구성이 둘로 갈린다)
  2. '예시)' 줄은 안 읽는다 — 양식에 본보기로 얹어 둔 줄이다
  3. 파트넘버와 품목(모델명) 자리가 뒤바뀐 양식도 제대로 읽는다
  4. 안 적은 주차와 0 을 적은 주차를 구분한다
  5. 이슈는 품번이 있든 없든 읽힌다
  6. 머리글이 한 줄 밀려도 읽힌다 (줄 번호로 찾지 않는다)
"""
import io
import os
import shutil
import sys

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
BACK = os.path.dirname(HERE)          # backend/
sys.path.insert(0, BACK)
import division_form_import as dfi      # noqa: E402

# 사업부에 나눠 준 빈 양식. 양식이 바뀌면 이 파일도 같이 갈아 끼운다.
FORMS = os.path.join(HERE, "forms")  # backend/tests/forms/ — 사업부에 나눠 준 빈 양식
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


def load(name):
    return openpyxl.load_workbook(os.path.join(FORMS, name), data_only=True)


# ── 1. 다섯 양식이 전부 읽힌다 ──────────────────────────────────
WANT = {
    "아리스타.xlsx": "프로젝트",
    "자동차.xlsx": "고객사",
    "PCB.xlsx": "고객사",
    "ESS.xlsx": "고객사",
    "네트워크.xlsx": "고객사",
}
for fname, kind in WANT.items():
    got = dfi.parse_workbook(load(fname))
    ok(got["kind"] == kind, f"{fname}: {kind}별인데 {got['kind']}별로 읽었다")
    ok(got["month"] == "2026-10", f"{fname}: 달을 {got['month']} 로 읽었다")
    ok(got["weeks"] == ["W41", "W42", "W43", "W44"],
       f"{fname}: 주차를 {got['weeks']} 로 읽었다")
    # 2026-10-26 — '예시)' 줄도 이제 읽는다. 전에는 건너뛰었는데,
    # 올려 주신 블룸 양식이 본보기 줄 자리에 진짜 품목을 적고 '예시)'
    # 글자만 안 지운 것이어서 YFP 가 통째로 사라졌다. 조용히 버리는
    # 쪽이 훨씬 나쁘다 — 읽되 '예시 표시가 있었다' 고 알린다.
    ok(all(x.get("example") for x in got["items"]),
       f"{fname}: 빈 양식인데 예시 표시가 없는 줄이 섞였다")
    ok(len(got["example_rows"]) == len(got["items"]),
       f"{fname}: 예시 줄을 알리지 않는다")
    ok(any("예시" in w for w in got["warnings"]),
       f"{fname}: 예시 줄을 읽었다고 알리지 않는다 — {got['warnings']}")


# ── 2. 채워서 올리면 읽힌다 (고객사별) ──────────────────────────
def fill_customer_form(src, dst):
    shutil.copy(os.path.join(FORMS, src), dst)
    wb = openpyxl.load_workbook(dst)
    ws = [w for w in wb.worksheets if "품목정보" in w.title][0]
    rows = [
        (10, "SDI", "SBB 1.7", "714-025898-009", "양산", "USD", 3150.4,
         "USD", 81.6, 437, 426, [(2, 1), (5, 5), (4, None), (None, None)]),
        (11, "플루언스", "Gridstack", "FL-900-11", "개발", "USD", 5200,
         "USD", 1200, 120, 88, [(10, 9), (12, 12), (0, 0), (None, None)]),
    ]
    for (r, owner, item, pn, grp, cur, price, mcur, mcost,
         po, ship, wk) in rows:
        ws.cell(r, 3, r - 9)
        ws.cell(r, 4, owner)
        ws.cell(r, 5, item)
        ws.cell(r, 6, pn)
        ws.cell(r, 7, grp)
        ws.cell(r, 8, cur)
        ws.cell(r, 9, price)
        ws.cell(r, 10, mcur)
        ws.cell(r, 11, mcost)
        ws.cell(r, 12, po)
        ws.cell(r, 13, ship)
        c = 14
        for p, a in wk:
            if p is not None:
                ws.cell(r, c, p)
            if a is not None:
                ws.cell(r, c + 1, a)
            c += 2
    iw = [w for w in wb.worksheets if "이슈" in w.title][0]
    import datetime as dt
    iw.cell(5, 2, 1)
    iw.cell(5, 3, "SDI")
    iw.cell(5, 4, "714-025898-009")
    iw.cell(5, 5, dt.date(2026, 10, 20))
    iw.cell(5, 6, "용접 치구 마모로 라인 2일 정지")
    iw.cell(6, 2, 2)
    iw.cell(6, 3, "플루언스")
    iw.cell(6, 5, "2026-10-22")
    iw.cell(6, 6, "고객사 도면 변경 통보")
    wb.save(dst)


fill_customer_form("ESS.xlsx", "/tmp/_t_ess.xlsx")
got = openpyxl.load_workbook("/tmp/_t_ess.xlsx", data_only=True)
got = dfi.parse_workbook(got)

_real = [x for x in got["items"] if not x.get("example")]
ok(len(_real) == 2, f"채운 줄을 {len(_real)}건 읽었다 (2건이어야 한다)")
a, b = _real[0], _real[1]
ok(a["owner"] == "SDI", f"고객사를 '{a['owner']}' 로 읽었다")
ok(a["part_number"] == "714-025898-009", f"품번을 '{a['part_number']}' 로 읽었다")
ok(a["name"] == "SBB 1.7", f"품목을 '{a['name']}' 로 읽었다")
ok(a["group"] == "양산", f"구분을 '{a['group']}' 로 읽었다")
ok(a["po_qty"] == 437 and a["shipped_qty"] == 426, "PO·실적 수량이 틀렸다")
ok(abs((a["price"] or 0) - 3150.4) < 0.01, f"판가를 {a['price']} 로 읽었다")
ok(abs((a["material_cost"] or 0) - 81.6) < 0.01,
   f"재료비를 {a['material_cost']} 로 읽었다")
ok(a["price_currency"] == "USD", "판가 통화를 못 읽었다")
ok(b["group"] == "개발", "개발 구분을 못 읽었다")

# ── 3. 안 적은 주차와 0 을 적은 주차는 다르다 ───────────────────
ok("W43" in a["weeks"] and a["weeks"]["W43"]["plan"] == 4,
   "계획만 적은 주차를 못 읽었다")
ok("W44" not in a["weeks"],
   "아무것도 안 적은 주차를 0 으로 만들어 넣었다 — 그러면 지금 값이 지워진다")
ok(b["weeks"]["W43"] == {"plan": 0, "actual": 0},
   "사람이 0 이라고 적은 주차는 0 으로 들어가야 한다")

# ── 4. 이슈 ─────────────────────────────────────────────────────
ok(len(got["issues"]) == 2, f"이슈를 {len(got['issues'])}건 읽었다")
i0, i1 = got["issues"]
ok(i0["part_number"] == "714-025898-009", "이슈의 품번을 못 읽었다")
ok(i0["date"] == "2026-10-20", f"발생일을 '{i0['date']}' 로 읽었다")
ok("용접" in i0["text"], "이슈 내용을 못 읽었다")
ok(i1["part_number"] == "", "품번 없는 이슈를 빈 글자로 두지 않았다")
ok(i1["date"] == "2026-10-22", "글자로 적은 발생일을 못 읽었다")

# ── 5. 파트넘버·품목 자리가 뒤바뀐 양식 (아리스타) ──────────────
shutil.copy(os.path.join(FORMS, "아리스타.xlsx"), "/tmp/_t_ar.xlsx")
wb = openpyxl.load_workbook("/tmp/_t_ar.xlsx")
ws = wb["프로젝트별 품목정보"]
ws.cell(10, 4, "PCB")
ws.cell(10, 5, "713-312133-006")     # 파트넘버가 먼저
ws.cell(10, 6, "BANFF")              # 모델명이 뒤
ws.cell(10, 7, "양산")
ws.cell(10, 12, 437)
wb.save("/tmp/_t_ar.xlsx")
ar = dfi.parse_workbook(openpyxl.load_workbook("/tmp/_t_ar.xlsx", data_only=True))
_arr = [x for x in ar["items"] if not x.get("example")]
ok(len(_arr) == 1, f"아리스타 양식에서 {len(_arr)}건 읽었다")
if _arr:
    it = _arr[0]
    ok(it["part_number"] == "713-312133-006",
       f"품번을 '{it['part_number']}' 로 읽었다 — 품목과 자리가 바뀌었다")
    ok(it["name"] == "BANFF", f"모델명을 '{it['name']}' 로 읽었다")

# ── 6. 머리글이 몇 번째 줄에 있든 읽힌다 ───────────────────────
#    줄 번호로 찾으면 양식을 조금만 손봐도 통째로 안 읽힌다.
#    (이미 만들어진 양식에 insert_rows 를 쓰면 병합된 머리글이 날아가서
#     파일 자체가 깨진다 — 그래서 시트를 직접 만들어 본다)
for head_row in (3, 7, 11):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "고객사별 품목정보"
    ws.cell(head_row, 3, "No.")
    ws.cell(head_row, 4, "고객사")
    ws.cell(head_row, 5, "품목 (있을 시)")
    ws.cell(head_row, 6, "파트넘버")
    ws.cell(head_row, 7, "구분")
    ws.cell(head_row, 8, "판가")
    ws.cell(head_row, 10, "재료비")
    ws.cell(head_row, 12, "PO수량")
    ws.cell(head_row, 13, "실적수량")
    ws.cell(head_row + 1, 8, "통화")
    ws.cell(head_row + 1, 9, "판가")
    ws.cell(head_row + 1, 10, "통화")
    ws.cell(head_row + 1, 11, "재료비")
    ws.cell(head_row + 1, 14, "W41")
    ws.cell(head_row + 1, 16, "W42")
    ws.cell(head_row + 2, 14, "계획")
    ws.cell(head_row + 2, 15, "실적")
    ws.cell(head_row + 2, 16, "계획")
    ws.cell(head_row + 2, 17, "실적")
    d = head_row + 3
    ws.cell(d, 4, "SDI")
    ws.cell(d, 5, "SBB 1.7")
    ws.cell(d, 6, "714-025898-009")
    ws.cell(d, 7, "양산")
    ws.cell(d, 12, 437)
    ws.cell(d, 14, 2)
    ws.cell(d, 15, 1)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    sh = dfi.parse_workbook(openpyxl.load_workbook(buf, data_only=True))
    _shr = [x for x in sh["items"] if not x.get("example")]
    ok(len(_shr) == 1,
       f"머리글이 {head_row}행일 때 {len(_shr)}건 읽었다 (1건이어야 한다)")
    if _shr:
        it = _shr[0]
        ok(it["part_number"] == "714-025898-009",
           f"머리글 {head_row}행: 품번을 '{it['part_number']}' 로 읽었다")
        ok(it["po_qty"] == 437, f"머리글 {head_row}행: PO 를 {it['po_qty']} 로 읽었다")
        ok(it["weeks"].get("W41") == {"plan": 2, "actual": 1},
           f"머리글 {head_row}행: 주차를 {it['weeks']} 로 읽었다")

# ── 7. 품목정보 시트가 없으면 분명히 알린다 ─────────────────────
wb = openpyxl.Workbook()
wb.active.title = "엉뚱한 시트"
try:
    dfi.parse_workbook(wb)
    ok(False, "품목정보 시트가 없는데 그냥 읽었다")
except ValueError as e:
    ok("품목정보" in str(e), f"안내 글이 불친절하다: {e}")

# ── 8. 주차 칸이 없는 양식도 품목은 읽는다 ──────────────────────
#
# 2026-10-26 — ESS 2026-10 양식에는 주차 블록이 아예 없다. 예전에는
# 품목 13건을 다 읽고도 "어느 달인지 알 수 없습니다" 로 반영이 통째로
# 막혔다. 올린 사람은 왜 안 되는지 알 길이 없었다.
#
# 달이 필요한 것은 주차별 계획을 어느 달 칸에 넣을까 뿐이다. 판가 ·
# PO수량 · 출하수량 · 구분은 달과 상관없다.
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "고객사별 품목정보"
for c, t in ((3, "No."), (4, "고객사"), (5, "품목명"), (6, "파트넘버"),
             (7, "구분"), (8, "판가"), (12, "PO수량"), (13, "출하수량")):
    ws.cell(5, c, t)
ws.cell(6, 8, "통화")
ws.cell(6, 9, "판가")
for c, v in ((3, 1), (4, "SDI"), (5, "SBB 1.5UL (한국)"), (7, "양산"),
             (8, "USD"), (9, 24000), (12, 947), (13, 883)):
    ws.cell(8, c, v)
buf = io.BytesIO()
wb.save(buf)
buf.seek(0)
nw = dfi.parse_workbook(openpyxl.load_workbook(buf, data_only=True))

ok(len(nw["items"]) == 1,
   "주차 칸이 없다고 품목까지 못 읽었다: %d건" % len(nw["items"]))
if nw["items"]:
    it = nw["items"][0]
    ok(it["owner"] == "SDI" and it["name"] == "SBB 1.5UL (한국)",
       "고객사·품목명을 잘못 읽었다: %r / %r" % (it["owner"], it["name"]))
    ok(it["po_qty"] == 947, "PO수량을 %r 로 읽었다" % (it["po_qty"],))
    # '출하수량' — ESS 양식의 말. 반도체 양식은 '실적수량' 이다.
    # 한쪽만 받으면 다른 쪽 양식에서 이 칸이 통째로 0 이 된다.
    ok(it["shipped_qty"] == 883,
       "'출하수량' 열을 못 읽었다 (%r) — 실적이 0 으로 들어간다"
       % (it["shipped_qty"],))
    ok(it["price"] == 24000, "판가를 %r 로 읽었다" % (it["price"],))
ok(nw["month"] == "", "주차가 없는데 달을 정했다: %r" % (nw["month"],))
ok(any("주차" in w for w in nw["warnings"]),
   "주차 칸이 없다는 안내가 없다: %r" % (nw["warnings"],))

# ── 9. 반영 주소가 주차 없다고 막지 않는다 ───────────────────────
import ast as _ast
_src = io.open(os.path.join(BACK, "main.py"), encoding="utf-8").read()
_tree = _ast.parse(_src)
_fn = next((n for n in _ast.walk(_tree)
            if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))
            and n.name == "admin_division_form_apply"), None)
ok(_fn is not None, "admin_division_form_apply 가 없다")
if _fn:
    _body = _ast.unparse(_fn)
    ok("어느 달인지 알 수 없습니다" not in _body,
       "주차가 없다고 반영을 400 으로 막는 코드가 남아 있다 — 주차 칸이 "
       "없는 양식은 품목을 하나도 못 넣는다")
    # 2026-10-26 — 전에는 '양식의 달' 하나에 주차를 전부 몰아넣었고,
    # 이 자리는 그 달이 빈 글자일 때만 막으면 됐다. 반도체 양식이
    # 올라오면서 그 방식 자체가 틀렸다 — 주차 칸이 W40~W44 다섯이고
    # W40 은 9월, W41~W44 는 10월 것이다. 한 달로 몰아넣으면 어느
    # 쪽이든 절반이 보드에 안 뜬다. 이제 주차마다 달력에 묻는다.
    ok("_wcal.month_of_week(_wk) or month" in _body,
       "주차마다 달을 묻지 않는다 — 양식 달 하나로 몰아넣으면 W40 처럼 "
       "달이 걸치는 주차에서 숫자가 샌다")
    ok("if not _mon:" in _body,
       "달을 못 정한 주차를 안 걸러낸다 — weekly_plan 이 '' 달에 쌓인다")

# ── 10. 양식에 없는 옛 모델을 지울 수 있다 ──────────────────────
#
# 2026-10-26 — 반영이 더하고 고치기만 해서, 양식에서 뺀 줄이 화면에
# 그대로 남았다. 모델은 엑셀로만 바꾸게 해 둔 터라(MODELS_READONLY)
# 화면에서 지울 길도 없어 아예 막혔다 — ESS 에 옛 SBB 두 줄이 그랬다.
#
# 2026-10-26 (2) — 체크박스는 없앴다. 올린 엑셀이 곧 그 사업부의
# 목록이다. 빠진 줄이 화면에 계속 남으면 엑셀과 화면이 달라지고,
# 어느 쪽이 맞는지 아무도 모르게 된다. 대신 안전장치는 둘 남긴다.
#   · 미리보기에서 '지워질 모델' 을 먼저 보여 주고 반영을 누르게 한다
#   · 양식에 나온 프로젝트만 본다 (옆 프로젝트는 안 건드린다)
_fn2 = next((n for n in _ast.walk(_tree)
             if isinstance(n, _ast.FunctionDef) and n.name == "_df_stale_models"),
            None)
ok(_fn2 is not None,
   "_df_stale_models 가 없다 — 양식에서 뺀 줄을 지울 길이 없다")
if _fn2:
    _ns = {}
    exec(compile(_ast.Module(body=[_fn2], type_ignores=[]), "<main>", "exec"), _ns)
    _stale = _ns["_df_stale_models"]
    _m1 = {"id": "A", "name": "SBB 1.5"}
    _m2 = {"id": "B", "name": "SBB 1.7"}
    _m3 = {"id": "C", "name": "옆 프로젝트 모델"}
    _data = {"projects": {"sdi": {"models": [_m1, _m2]},
                          "fluence": {"models": [_m3]}}}
    # 양식이 sdi 의 A 만 건드렸다 → B 만 '양식에 없는 모델'
    _got = _stale(_data, {"sdi": {id(_m1)}})
    ok([x["id"] for x in _got] == ["B"],
       "양식에 없는 모델을 잘못 골랐다: %r" % ([x["id"] for x in _got],))
    ok(all(x["project_key"] != "fluence" for x in _got),
       "양식에 한 줄도 없는 프로젝트(fluence)의 모델까지 지우려 한다 — "
       "사업부 파일 한 장으로 옆 프로젝트가 비어 버린다")

_fn3 = next((n for n in _ast.walk(_tree)
             if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))
             and n.name == "admin_division_form_apply"), None)
if _fn3:
    _args = [a.arg for a in _fn3.args.args] + [a.arg for a in _fn3.args.kwonlyargs]
    ok("remove_missing" in _args,
       "반영 주소가 remove_missing 을 안 받는다")
    _b = _ast.unparse(_fn3)
    ok("if remove_missing and stale" in _b,
       "remove_missing 을 안 보고 지우고 있다 — 끄고 올릴 길이 없어진다")

_adm = io.open(os.path.join(BACK, "admin_v2.html"), encoding="utf-8").read()
ok("divform-remove" not in _adm,
   "admin 에 '지우기' 체크가 아직 있다 — 엑셀이 곧 목록이라 고를 것이 없다")
ok("if (step === 'apply') fd.append('remove_missing', 'true');" in _adm,
   "admin 이 반영할 때 remove_missing 을 늘 보내지 않는다")
ok("d.stale" in _adm, "admin 이 '지워질 모델' 목록을 안 띄운다")
ok("id=\"divform-apply\"" in _adm, "미리보기 밑에 반영 단추가 없다")
ok("주차별 계획' 탭에서 양식을 받아 그 줄을 지우고" not in _adm,
   "삭제를 막는 안내가 아직 '주차별 계획 탭' 을 가리킨다 — 그 경로는 "
   "모델을 지우지 않아서 따라가도 안 된다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for m in FAIL:
        print("  -", m)
    raise SystemExit(1)
print("전부 통과 · 사업부 양식 검사 10묶음 · 양식 %d종" % len(WANT))
