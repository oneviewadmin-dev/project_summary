# -*- coding: utf-8 -*-
"""한 칸에 품번 여러 개 · 사업부마다 읽기를 멈출 열 (2026-10-26).

블룸 양식에 이런 줄이 왔다.

    CORVA BOP ASSY | 848535        | 함체 | 양산 | ... | PO 9,204 | 실적 994
                   | 177617
                   | 173789
                   | 171981   ← 한 칸, 네 줄

네 모델이 1 set 로 나간다. 적힌 수량은 **세트 수**다. 그래서 쪼개면
안 된다 — 네 줄로 쪼개고 9,204 을 그대로 주면 합계가 네 배가 되고,
넷으로 나누면 엑셀에 없는 숫자를 만든다.
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACK = os.path.dirname(HERE)
sys.path.insert(0, BACK)

import division_columns as dc          # noqa: E402
import division_form_import as dfi     # noqa: E402

FAIL = []


def ok(c, why):
    if not c:
        FAIL.append(why)


# ── 품번 여러 개: 한 줄 = 한 품목, 품번만 잇는다
ok(dfi._pn("848535\n177617\n173789\n171981") == "848535 / 177617 / 173789 / 171981",
   "여러 줄 품번을 ' / ' 로 잇지 않는다: %r" % dfi._pn("848535\n177617\n173789\n171981"))
ok(dfi._pn("848535\r\n177617") == "848535 / 177617", "윈도우 줄바꿈(\\r\\n)을 못 읽는다")
ok(dfi._pn("  A-1  ") == "A-1", "앞뒤 공백을 안 뗀다")
ok(dfi._pn(None) == "" and dfi._pn("") == "", "빈 칸이 빈 글자가 아니다")
ok(dfi._pn("A\n\n\nB") == "A / B", "빈 줄까지 품번으로 센다")

# ── 어디까지 읽나
# 2026-10-28 — 블룸이 LAST_COL 에서 빠졌다.
#
# 새 블룸 양식에 O열부터 '10월 주차별 계획 · 실적' 이 붙었는데, N(14)에서
# 멈추는 바람에 주차 칸이 통째로 안 읽혔다. 올린 사람은 적었고 시스템은
# 못 봤다 — 화면의 '최근 업데이트' 가 전부 비어 있었다.
#
# Min: "그냥 일단은 파일에 있는 내용 그대로 반영해줘"
#
# 그래서 지금은 아무 사업부도 안 멈춘다. 틀만 지킨다 — 적힌 사업부는
# 멈추고, 안 적힌 사업부는 끝까지 읽는다.
ok(dc.LAST_COL == {}, "멈출 사업부가 생겼다 — 왜 생겼는지 여기 적고 이 줄을 고쳐라")
ok(dc.last_col("bloom") is None, "블룸이 아직 N열에서 멈춘다 — 주차 칸이 안 읽힌다")
ok(dc.last_col("ess") is None, "ESS 열을 잘랐다 — 정한 사업부만 멈춰야 한다")
ok(dc.last_col("") is None and dc.last_col(None) is None, "빈 사업부에 제한이 걸렸다")
dc.LAST_COL["__시험__"] = 14          # 틀이 도는지만 본다
ok(dc.last_col("__시험__") == 14, "LAST_COL 에 적어도 안 멈춘다 — 틀이 죽었다")
ok(dc.last_col("__시험__".upper()) == 14, "대문자로 물으면 못 찾는다")
del dc.LAST_COL["__시험__"]

_src = io.open(os.path.join(BACK, "division_form_import.py"), encoding="utf-8").read()
ok("def _lastc(ws)" in _src, "읽기를 멈추는 자리가 없다")
# 멈추라는 자리 오른쪽은 주차도 안 읽는다. 자르는 사업부가 지금은
# 없지만, 생겼을 때 주차만 몰래 살아 있으면 안 된다 — 안 읽는다고
# 해 놓고 반만 읽는 게 제일 나쁘다.
_wk = _src[_src.index("def _find_weeks"):_src.index("def _is_example_row")]
ok("_lastc(ws)" in _wk, "주차 칸 찾기가 멈출 자리를 안 본다")
ok("_MAX_COL and (plan_col" in _wk,
   "계획만 읽히는 반쪽 주차를 안 버린다 — 실적이 늘 비어 보인다")

# ── 양식 7종이 그대로 읽히는지
try:
    import openpyxl
except Exception:
    openpyxl = None
if openpyxl:
    for name, div, want_weeks in [
        # 블룸 양식 세 벌 — 전부 주차 칸(W41~W44)이 있다.
        # 2026-10-28 이전에는 여기 '0' 이라고 적혀 있었다. 양식에 주차가
        # 있는데도 N열에서 잘라서 안 읽혔고, 그 상태를 시험이 '정답' 으로
        # 지키고 있었다. 머리글 이름이 'W41' 이든 '41' 이든 똑같이 읽힌다.
        ("블룸", "bloom", 4),
        ("블룸_실제_2026-10", "bloom", 4),
        ("블룸_주차별_2026-10", "bloom", 4),
        ("반도체", "semiconductor", 5),
        ("ESS", "ess", 4), ("아리스타", "arista", 4),
    ]:
        f = os.path.join(HERE, "forms", "v2", name + ".xlsx")
        if not os.path.exists(f):
            continue
        wb = openpyxl.load_workbook(f, data_only=True)
        got = dfi.parse_workbook(wb, div)
        ok(len(got["weeks"]) == want_weeks,
           "%s 양식의 주차가 %d개여야 하는데 %r" % (name, want_weeks, got["weeks"]))

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — 품번 여러 개 · 열 제한")

# ======================================================================
#  2026-10-26 (2) — 실제로 올라온 블룸 양식 한 장
#
#  이 파일에서 세 가지가 한꺼번에 드러났다.
#    · 7~9행이 '예시)' 표시가 붙은 채 진짜 품목이었다 (YFP 가 사라졌다)
#    · 주차 머리글이 'W41' 이 아니라 그냥 '41' 이었다 (주차가 통째로 빠졌다)
#    · 품목 자료는 N열까지, 주차는 O열부터다
#  고친 뒤 이 파일이 그대로 읽히는지 늘 확인한다.
#
#  2026-10-28 — 주차를 '안 읽는 게 맞다' 고 적어 둔 줄들을 고쳤다.
#  이 양식에는 처음부터 주차 칸이 있었는데 N열에서 잘라서 못 봤다.
#  Min: "그냥 일단은 파일에 있는 내용 그대로 반영해줘"
# ======================================================================
_REAL = os.path.join(HERE, "forms", "v2", "블룸_실제_2026-10.xlsx")
if openpyxl and os.path.exists(_REAL):
    _g = dfi.parse_workbook(openpyxl.load_workbook(_REAL, data_only=True), "bloom")
    ok(len(_g["items"]) == 87, "품목을 87건 읽어야 하는데 %d건" % len(_g["items"]))
    ok(_g["weeks"] == ["W41", "W42", "W43", "W44"],
       "주차를 못 읽었다: %r" % _g["weeks"])
    ok(_g["month"] == "2026-10", "달을 %r 로 읽었다" % _g["month"])
    _by = {}
    for _it in _g["items"]:
        _by.setdefault(_it["owner"], []).append(_it)
    ok("YFP" in _by, "'예시)' 가 붙은 YFP 줄을 또 버렸다")
    if "YFP" in _by:
        _y = _by["YFP"][0]
        ok(_y["part_number"] == "937100", "YFP 품번을 %r 로 읽었다" % _y["part_number"])
        ok(_y["po_qty"] == 440 and _y["shipped_qty"] == 240,
           "YFP 수량을 PO %r · 실적 %r 로 읽었다" % (_y["po_qty"], _y["shipped_qty"]))
        # 엑셀 7행 YFP: W41 계획 8 · 실적 8, W44 계획 40 · 실적 빈 칸
        # 빈 칸은 0 이 아니라 '안 적음' 이다 — 0 은 0 이라고 적은 것.
        ok(_y["weeks"].get("W41") == {"plan": 8, "actual": 8},
           "YFP W41 을 %r 로 읽었다" % (_y["weeks"].get("W41"),))
        ok((_y["weeks"].get("W44") or {}).get("plan") == 40,
           "YFP W44 계획을 %r 로 읽었다" % (_y["weeks"].get("W44"),))
    ok(len(_g["example_rows"]) == 3,
       "'예시)' 표시가 붙은 줄 3건을 알려야 한다: %d건" % len(_g["example_rows"]))
    # 1 set 로 나가는 함체 — 쪼개지 않는다
    _bop = [x for x in _g["items"] if x["owner"] == "CORVA BOP ASSY"]
    ok(len(_bop) == 1, "1 set 줄을 %d건으로 쪼갰다" % len(_bop))
    if _bop:
        ok(_bop[0]["part_number"].count("/") == 3,
           "품번 네 개를 안 이었다: %r" % _bop[0]["part_number"])
        ok(_bop[0]["po_qty"] == 9204, "세트 수량이 바뀌었다: %r" % _bop[0]["po_qty"])

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — 실제 블룸 양식")
