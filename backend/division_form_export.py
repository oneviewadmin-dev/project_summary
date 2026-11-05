# -*- coding: utf-8 -*-
# ============================================================
#  사업부 양식 내려받기 — 지금 등록된 내용을 채워서 준다
# ============================================================
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as _L
from openpyxl.worksheet.datavalidation import DataValidation

import division_columns as _dcol
import week_calendar as _wcal

FONT = "맑은 고딕"
NAVY, NAVY2 = "0F2C59", "1B4485"
_LN = Side(style="thin", color="BFC7D2")
BOX = Border(left=_LN, right=_LN, top=_LN, bottom=_LN)
HEAD_FILL = PatternFill("solid", fgColor=NAVY)
WEEK_FILL = PatternFill("solid", fgColor=NAVY2)
SUB_FILL = PatternFill("solid", fgColor="DCE6F1")
HAVE_FILL = PatternFill("solid", fgColor="FFFFFF")

HEAD_ROW, SUB_ROW, UNIT_ROW, DATA_ROW = 4, 5, 6, 7

# 판가 · 재료비는 머리글 하나 아래 '통화 / 값' 두 칸이다 (양식 그대로)
_PAIR = {"price": ("판가", "price_currency", "price"),
         "material_cost": ("재료비", "material_currency", "material_cost")}


def _head(ws, r, c, text, fill=HEAD_FILL, size=10):
    cell = ws.cell(r, c, text)
    cell.font = Font(FONT, size=size, bold=True, color="FFFFFF")
    cell.fill = fill
    cell.alignment = Alignment("center", "center", wrap_text=True)
    cell.border = BOX
    return cell


def _sub(ws, r, c, text):
    cell = ws.cell(r, c, text)
    cell.font = Font(FONT, size=9, bold=True, color="1F4E79")
    cell.fill = SUB_FILL
    cell.alignment = Alignment("center", "center")
    cell.border = BOX
    return cell


# '2026-10' 에서 n 달치 → ['2026-10', '2026-11'] (주차가 있는 달만).
def months_from(month: str, n: int) -> list:
    y, m = int(str(month)[:4]), int(str(month)[5:7])
    out = []
    for i in range(max(1, n)):
        yy, mm = y + (m - 1 + i) // 12, (m - 1 + i) % 12 + 1
        key = "%04d-%02d" % (yy, mm)
        wks = _wcal.get_month_weeks(key)
        if wks:
            out.append({"month": key, "weeks": wks})
    return out


# ==== 이슈사항 · 용어 시트
SIDE_ROWS = 30                     # 빈 줄 — 처음 양식과 같은 수


def _side_sheet(wb, title: str, note: str, heads: list, widths: list,
                rows: list, keys: list):
    ws = wb.create_sheet(title)
    ws.cell(2, 2, heads[0][1]).font = Font(FONT, size=15, bold=True, color="1F4E79")
    ws.cell(3, 2, note).font = Font(FONT, size=9, color="C00000")
    for j, (label, _t) in enumerate(heads[1:]):
        _head(ws, 4, 2 + j, label)
    for j, w in enumerate(widths):
        ws.column_dimensions[_L(2 + j)].width = w
    ws.row_dimensions[4].height = 26
    for i in range(max(SIDE_ROWS, len(rows))):
        r = 5 + i
        d = rows[i] if i < len(rows) else {}
        for j, k in enumerate(keys):
            cell = ws.cell(r, 2 + j)
            v = (i + 1) if (k == "_no" and d) else d.get(k)
            if v not in (None, ""):
                cell.value = v
            cell.font = Font(FONT, size=10, color="0F172A")
            cell.alignment = Alignment("center" if k in ("_no", "date") else "left",
                                       "center", wrap_text=(k in ("text", "note")))
            cell.border = BOX
    ws.freeze_panes = ws.cell(5, 2)
    return ws


# 이슈사항 — 지금 열린 이슈('진행')를 채우고, 밑에 빈 줄.
def add_issue_sheet(wb, owner_label: str, issues: list | None = None):
    title = ("고객사별 이슈사항" if "고객사" in str(owner_label) else "프로젝트별 이슈사항")
    rows = list(issues or [])
    ws = _side_sheet(
        wb, "이슈사항",
        "*열려 있는 이슈가 채워져 있습니다. 해결된 건 상태를 '해결'로 바꿔 올리면 닫힙니다 "
        "(줄을 지워도 해결로 치지 않습니다). 새 이슈는 빈 줄에 — 상태를 비우면 '진행'.",
        [("", title), ("NO", ""), (owner_label or "고객사", ""), ("품번", ""),
         ("발생일", ""), ("이슈사항", ""), ("이슈 분류", ""), ("조치사항", ""),
         ("담당자", ""), ("상태", "")],
        [6, 16, 18, 12, 50, 10, 44, 10, 9], rows,
        ["_no", "owner", "part_number", "date", "text", "category", "action",
         "person", "status"])
    # 상태 칸은 고르게만 — 오타로 '헤결' 이 들어가면 진행으로 남는다
    # 상태 = J열 (B NO · C 고객사 · D 품번 · E 발생일 · F 이슈사항 · G 분류 ·
    #          H 조치사항 · I 담당자 · J 상태)
    last = 4 + max(SIDE_ROWS, len(rows))
    dv = DataValidation(type="list", formula1='"진행,해결"', allow_blank=True)
    dv.error = "진행 또는 해결 중에서 골라 주세요."
    dv.showErrorMessage = True
    ws.add_data_validation(dv)
    dv.add("J5:J%d" % last)
    cat = DataValidation(type="list", formula1='"납기,품질,자재,단가,신규 PO,기타"',
                         allow_blank=True, showErrorMessage=False)
    ws.add_data_validation(cat)
    cat.add("G5:G%d" % last)
    for i in range(len(rows)):
        for c in (7, 9, 10):
            ws.cell(5 + i, c).alignment = Alignment("center", "center")
    return ws


# 용어 — 등록된 것을 채워서.
def add_term_sheet(wb, terms: list):
    return _side_sheet(
        wb, "용어",
        "*이 사업부에서 쓰는 약어를 적어 주세요. 올릴 때마다 이 시트 전체로 바뀝니다 "
        "(시트를 통째로 비워서 올리면 지우지 않습니다).",
        [("", "사업부별 용어 & 약어"), ("NO", ""), ("약어", ""), ("Full Name", ""),
         ("한국어 뜻", ""), ("비고 / 확인사항", "")],
        [6, 14, 28, 26, 60], list(terms or []), ["_no", "short", "full", "ko", "note"])


# 납기 칸 (division_columns.DUE_COLS) — 'YYYY-MM-DD' 글자로 저장돼 있다
_DATE_KEYS = ("due_date", "due_revised", "made_date")


def _as_date(v):
    import datetime as _dt
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v
    try:
        return _dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return v


# 사업부 양식을 만들어 바이트로 돌려준다 — 품목정보 · 이슈사항 · 용어.
def build(division_id: str, rows: list, month: str, n_month: int = 2,
          terms: list | None = None, issues: list | None = None) -> bytes:
    spec = _dcol.columns_for(division_id)
    # -----------------------------------------------------------
    # 주차 칸을 안 읽는 사업부는 그리지도 않는다
    # -----------------------------------------------------------
    # 읽지도 않을 칸을 양식에 그려 주면 담당자가 거기 적는다
    blocks = [] if _dcol.last_col(division_id) else months_from(month, n_month)
    sheet_name = ("고객사별 품목정보" if spec["shape"] == "고객사형"
                  else "프로젝트별 품목정보")

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    ws.cell(2, 4, sheet_name).font = Font(FONT, size=15, bold=True, color="1F4E79")
    note = "*이미 등록된 내용을 채워 둔 양식입니다. 고칠 곳만 고쳐서 그대로 다시 올려 주세요."
    if not blocks:
        note += "  (이 사업부의 주차별 계획은 일 보고 자료로 들어옵니다)"
    ws.cell(3, 4, note).font = Font(FONT, size=9, color="C00000")
    # -----------------------------------------------------------
    # 왼쪽 고정 칸
    # -----------------------------------------------------------
    cols = []                      # [(열번호, key)]
    c = 4
    _head(ws, HEAD_ROW, c, "No."); cols.append((c, "_no")); c += 1
    _head(ws, HEAD_ROW, c, spec["owner_label"]); cols.append((c, "owner")); c += 1
    # 묶음 칸 — 고객사를 묶어 보여 주는 사업부만
    #   PCB · 네트워크 '국내/해외' · 자동차 '고객 묶음'
    region_col = None
    _gcol = _dcol.group_col(division_id)
    if _gcol:
        _head(ws, HEAD_ROW, c, _gcol["header"]); cols.append((c, "region"))
        region_col = c
        c += 1
    if spec["primary"] == "part_number":
        _head(ws, HEAD_ROW, c, "파트넘버"); cols.append((c, "part_number")); c += 1
        _head(ws, HEAD_ROW, c, spec["name_label"]); cols.append((c, "name")); c += 1
    else:
        _head(ws, HEAD_ROW, c, spec["name_label"]); cols.append((c, "name")); c += 1
        _head(ws, HEAD_ROW, c, "파트넘버"); cols.append((c, "part_number")); c += 1

    for col in spec["columns"]:
        k = col["key"]
        if k in _PAIR:
            label, cur_key, val_key = _PAIR[k]
            _head(ws, HEAD_ROW, c, label)
            ws.merge_cells(start_row=HEAD_ROW, start_column=c,
                           end_row=HEAD_ROW, end_column=c + 1)
            _sub(ws, SUB_ROW, c, "통화"); _sub(ws, SUB_ROW, c + 1, label)
            cols.append((c, cur_key)); cols.append((c + 1, val_key))
            c += 2
        else:
            _head(ws, HEAD_ROW, c, col["label"].split(" ·")[0])
            cols.append((c, k)); c += 1
    # -----------------------------------------------------------
    # 주차 블록 (달마다 하나)
    # -----------------------------------------------------------
    week_cols = []                 # [(열번호, 달, 주차)]
    for b in blocks:
        start = c
        _head(ws, HEAD_ROW, c, "%d월 주차별 계획 · 실적" % int(b["month"][5:7]), WEEK_FILL)
        for wk in b["weeks"]:
            _sub(ws, SUB_ROW, c, wk)
            ws.merge_cells(start_row=SUB_ROW, start_column=c,
                           end_row=SUB_ROW, end_column=c + 1)
            _sub(ws, UNIT_ROW, c, "계획"); _sub(ws, UNIT_ROW, c + 1, "실적")
            week_cols.append((c, b["month"], wk))
            c += 2
        if c > start:
            ws.merge_cells(start_row=HEAD_ROW, start_column=start,
                           end_row=HEAD_ROW, end_column=c - 1)

    last_col = c - 1
    for cc in range(4, last_col + 1):
        for rr in (HEAD_ROW, SUB_ROW, UNIT_ROW):
            if ws.cell(rr, cc).value is None:
                ws.cell(rr, cc).border = BOX
    # -----------------------------------------------------------
    # 자료
    # -----------------------------------------------------------
    for i, m in enumerate(rows or []):
        r = DATA_ROW + i
        wp = m.get("weekly_plan") or {}
        for cc, key in cols:
            v = (i + 1) if key == "_no" else m.get(key)
            cell = ws.cell(r, cc)
            if v not in (None, ""):
                cell.value = _as_date(v) if key in _DATE_KEYS else v
            if key in _DATE_KEYS:
                cell.number_format = "yyyy-mm-dd"
            cell.font = Font(FONT, size=10, color="0F172A")
            cell.alignment = Alignment(
                "left" if key in ("owner", "part_number", "name", "note") else "center",
                "center")
            cell.border = BOX
        for cc, mon, wk in week_cols:
            cellv = ((wp.get(mon) or {}).get(wk) or {})
            for off, field in ((0, "plan"), (1, "actual")):
                cell = ws.cell(r, cc + off)
                got = cellv.get(field)
                if got not in (None, ""):
                    cell.value = got
                cell.font = Font(FONT, size=10, color="0F172A")
                cell.alignment = Alignment("center", "center")
                cell.border = BOX
    # -----------------------------------------------------------
    # 폭
    # -----------------------------------------------------------
    for cc, key in cols:
        ws.column_dimensions[_L(cc)].width = {
            "_no": 5, "owner": 16, "part_number": 18, "name": 18,
            "note": 24, "group": 9, "dev_type": 11,
            "due_date": 12, "due_revised": 13, "made_date": 12,
            "region": 14,
        }.get(key, 12)
    if region_col:
        from openpyxl.worksheet.datavalidation import DataValidation as _DV
        _dv = _DV(type="list", formula1='"%s"' % ",".join(_gcol["choices"]),
                  allow_blank=True, showErrorMessage=False)   # 새 묶음(해외 · 일본 등)도 적을 수 있게
        ws.add_data_validation(_dv)
        _dv.add("%s%d:%s%d" % (_L(region_col), DATA_ROW, _L(region_col),
                               DATA_ROW + len(rows or []) + 300))
    for cc, _m, _w in week_cols:
        ws.column_dimensions[_L(cc)].width = 8
        ws.column_dimensions[_L(cc + 1)].width = 8
    ws.row_dimensions[HEAD_ROW].height = 30
    ws.freeze_panes = ws.cell(DATA_ROW, week_cols[0][0] if week_cols else 4)

    add_issue_sheet(wb, spec["owner_label"], issues)
    add_term_sheet(wb, terms)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
