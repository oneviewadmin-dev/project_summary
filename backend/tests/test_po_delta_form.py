# 양식을 다시 올려 PO 가 바뀌면, 두 화면이 같은 말을 해야 한다 (2026-10-27).
#
# Min: "PO증감 전주대비 파일 업데이트 시 처리 제대로 되어 있는지 확인"
#
# 전에는 반쪽이었다.
#   · 모델 목록 옆 ▲12 는 모델마다 적어 둔 po_log 를 본다 — 떴다.
#   · 주차 현황 보드의 PO증감 칸은 그룹 단위 po_history 만 봤다 — 비었다.
# 같은 자료인데 한쪽은 보이고 한쪽은 안 보이면, 보이는 쪽을 못 믿게 된다.
#
# 그리고 po_log 에 날짜가 없었다. PO증감은 **전주 대비**로 읽는 숫자라
# 달만 적어 두면 W42 에 늘었는지 W43 에 늘었는지가 영영 없어진다.
import ast
import datetime
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


def fn(name):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return ast.unparse(n)
    return ""


# ── 1. 양식을 올릴 때 '언제' 를 같이 적는다
apply_src = fn("admin_division_form_apply")
ok(apply_src, "admin_division_form_apply 가 없다")
ok("'date': _dt.date.today().strftime('%Y-%m-%d')" in apply_src,
   "po_log 에 날짜를 안 적는다 — 전주 대비로 묶을 수 없다")
ok("'delta': int(it['po_qty']) - int(_before)" in apply_src,
   "po_log 에 증감값을 안 적는다")

# ── 1-2. 주 1회 올리는 양식이라 기록을 넉넉히 들고 있어야 한다
#        12번이면 석 달도 못 채우는데 보드는 지난 6개월을 보여준다.
ok("if len(_log) > 60:" in apply_src,
   "po_log 를 60번까지 안 들고 있다 — 주 1회면 6개월 치가 안 남는다")

# ── 1-3. 어느 주차 것인지는 '양식' 이 말한다 (2026-10-27)
#
# Min: "주차별 계획이 있는 애들은 거기에 제일 최근에 작성된 실적이 있을
#      거 아니야. 있다고 하면 PO수량 변동이 있는지 확인해주면 되지"
#
# 올린 날로 찍으면 W43 양식을 다음 주 월요일에 올렸을 때 W44 에 숫자가
# 선다 — 그 주엔 아무 일도 없었는데 "이번 주에 PO 가 늘었네" 로 읽힌다.
ok("'week': got.get('as_of_week') or ''" in apply_src,
   "양식의 기준 주차를 po_log 에 안 적는다 — 올린 날로 찍히면 주차가 밀린다")

# ── 1-4. PO 전량 취소(0)가 반영된다 (2026-10-27)
#
# Min: "가끔 불량 생기면 PO 취소 될 경우가 생기기도 해"
#
# 전에는 `if it.get("po_qty"):` 였다. 0 이 거짓이라 전량 취소가 통째로
# 건너뛰어졌다 — 취소된 PO 558 이 화면에 그대로 남았다.
# 그렇다고 가드를 없애면 **빈 칸이 0 으로 읽혀** 한 칸만 고쳐 올린 엑셀이
# 나머지 PO 를 전부 날린다. 그래서 파서가 빈 칸을 None 으로 돌려주고,
# 여기서는 'None 이 아니면' 으로 가린다.
ok("if it.get('po_qty') is not None:" in apply_src,
   "PO 0 (전량 취소)이 반영에서 건너뛰어진다")
ok("if it.get('shipped_qty') is not None:" in apply_src,
   "출하 0 이 반영에서 건너뛰어진다")

# ── 2. 주차 현황 보드가 양식 기록(po_log)도 본다
board = fn("get_weekly_board")
ok(board, "get_weekly_board 가 없다")
ok("po_history" in board, "보드가 po_history 를 안 본다")
ok("po_log" in board, "보드가 양식 기록(po_log)을 안 본다 — "
                      "양식을 다시 올려도 PO증감 칸이 빈다")
ok("_seen_log" in board, "같은 기록을 두 번 셀 수 있다")

# ── 3. 날짜가 없는 옛 기록은 건너뛴다 (주차로 묶을 수 없다)
ok("not _e.get('date')" in board,
   "날짜 없는 옛 po_log 를 걸러내지 않는다 — 주차 묶기에서 터진다")

# ── 4. 실제로 주차로 묶이는가
#      main.py 는 통째로 import 가 안 된다(서버 의존 패키지). 그래서 필요한
#      함수 둘만 떼어내 그 자리에서 돌린다 — 집에서 쓰는 방식이다.
_ns = {}
_need = ["_month_of_week_key", "_po_delta_summary"]
for _n in ast.walk(tree):
    if isinstance(_n, ast.FunctionDef) and _n.name in _need:
        exec(compile(ast.Module([_n], []), "<main>", "exec"), _ns)
for _n in _need:
    ok(_n in _ns, "main.py 에서 %s 를 떼어내지 못했다" % _n)
if len(_ns) < len(_need):
    for b in bad:
        print("FAIL:", b)
    raise SystemExit(1)


class _M:
    pass


_m = _M()
_m._po_delta_summary = _ns["_po_delta_summary"]

today = datetime.date.today()
wk = "W%02d" % today.isocalendar()[1]
mon = "%d-%02d" % (today.year, today.month)
got = _m._po_delta_summary(
    [{"date": today.strftime("%Y-%m-%d"), "from": 100, "to": 112, "delta": 12}],
    mon, None)
weeks = {w.get("label") or w.get("key"): w.get("delta")
         for w in (got.get("weeks") or [])}
ok(got.get("weeks"), "이번 달 기록이 주차로 안 묶인다 (%s)" % got)
ok(12 in weeks.values() or any(v == 12 for v in weeks.values()),
   "증감 12 가 이번 주차에 안 들어갔다 (%s)" % got)

# 지난 달 기록은 달 한 줄로 접힌다
prev = today.replace(day=1) - datetime.timedelta(days=1)
got2 = _m._po_delta_summary(
    [{"date": prev.strftime("%Y-%m-%d"), "from": 100, "to": 90, "delta": -10}],
    mon, None)
ok(got2.get("months"), "지난 달 기록이 달 한 줄로 안 접힌다 (%s)" % got2)

# ── 7. 양식이 스스로 '몇 주차 자료' 인지 말하는가 (실제 파일로)
import glob                                  # noqa: E402
import openpyxl                               # noqa: E402

sys.path.insert(0, os.path.join(HERE, ".."))
import division_form_import as _dfi           # noqa: E402

FORMS = os.path.join(HERE, "forms", "v2")
WANT = {
    # 파일 이름에 'W43 R2' 라고 적혀 있고, 실적도 W43 까지 적혀 있다.
    # 이름을 안 믿어도 양식 속 숫자만으로 같은 답이 나온다.
    "반도체_HRVA_실제_1023.xlsx": ("semiconductor", "W43"),
    "반도체_엔클로저_실제_1023.xlsx": ("semiconductor", "W43"),
    "PCB_실제_1023.xlsx": ("pcb", "W43"),
    "아리스타_실제_1023c.xlsx": ("arista", "W42"),
    # 실적이 한 칸도 없는 양식은 빈 글자 — 그때만 올린 날로 떨어뜨린다
    "반도체_CUP_실제_1023.xlsx": ("semiconductor", ""),
    "반도체_챔버_실제_1023.xlsx": ("semiconductor", ""),
}
for fn, (div, want) in WANT.items():
    p = os.path.join(FORMS, fn)
    if not os.path.exists(p):
        bad.append("양식이 없다: %s" % fn)
        continue
    g = _dfi.parse_workbook(openpyxl.load_workbook(p, data_only=True),
                            division_id=div)
    ok(g.get("as_of_week") == want,
       "%s 의 기준 주차가 %r 여야 하는데 %r" % (fn, want, g.get("as_of_week")))

# ── 7-2. 파서가 0 과 빈 칸을 가리는가 (직접 만들어 넣어 본다)
def _mk(po, ship):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "프로젝트별 품목정보"
    for c, v in [(4, "No."), (5, "프로젝트"), (6, "파트넘버"), (8, "구분"),
                 (10, "판가"), (15, "PO수량"), (16, "실적수량")]:
        ws.cell(4, c, v)
    ws.cell(5, 10, "통화"); ws.cell(5, 11, "판가")
    ws.cell(7, 4, 1); ws.cell(7, 5, "CUP"); ws.cell(7, 6, "PN-1"); ws.cell(7, 8, "양산")
    if po is not None:
        ws.cell(7, 15, po)
    if ship is not None:
        ws.cell(7, 16, ship)
    return wb


for po, ship in [(558, 294), (0, 0), (None, None), (0, None)]:
    g = _dfi.parse_workbook(_mk(po, ship), division_id="semiconductor")
    it = (g["items"] or [{}])[0]
    ok(it.get("po_qty") == po,
       "엑셀 PO %r 를 %r 로 읽었다 — 0 과 빈 칸이 안 갈린다" % (po, it.get("po_qty")))
    ok(it.get("shipped_qty") == ship,
       "엑셀 출하 %r 를 %r 로 읽었다" % (ship, it.get("shipped_qty")))

# ── 8. 보드가 그 주차를 그대로 쓰는가
board2 = fn_src = ""
for n in ast.walk(tree):
    if isinstance(n, ast.FunctionDef) and n.name == "_po_delta_summary":
        board2 = ast.unparse(n)
ok(board2, "_po_delta_summary 가 없다")
ok("h.get('week')" in board2,
   "보드가 양식이 적어 보낸 주차를 안 본다 — 올린 날로 되돌아간다")
ok("_wcal.month_of_week(_wk)" in board2,
   "그 주차가 어느 달 것인지 달력에 안 묻는다")

if bad:
    for b in bad:
        print("FAIL:", b)
    raise SystemExit(1)
print("ok test_po_delta_form (%s / %s)" % (wk, mon))
