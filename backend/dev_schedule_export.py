# -*- coding: utf-8 -*-
# ============================================================
#  품목별 개발 일정 양식 내려받기
# ============================================================
from __future__ import annotations

import collections
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

FONT = "Arial"
_THIN = Side(style="thin", color="B7C0CC")
BORDER = Border(_THIN, _THIN, _THIN, _THIN)
HEAD_FILL = PatternFill("solid", fgColor="1F3864")
PROC_FILL = PatternFill("solid", fgColor="EDF2F9")
BAND_FILL = PatternFill("solid", fgColor="F7F9FC")

HEAD = ["No.", "고객사", "품목명", "파트넘버", "개발 담당 주재원", "구분"]
KINDS = ("프로세스", "계획", "실적")


# 그 사업부에서 제일 많이 쓰는 단계 묶음.
def common_steps(rows: list, fallback: list) -> list:
    c = collections.Counter()
    for r in rows:
        names = tuple(str((s or {}).get("name") or "").strip()
                      for s in (r.get("process") or [])
                      if str((s or {}).get("name") or "").strip())
        if names:
            c[names] += 1
    return list(c.most_common(1)[0][0]) if c else list(fallback)


# rows → 엑셀 한 장 (bytes).
def build(division_label: str, rows: list, fallback_steps: list) -> bytes:
    base = common_steps(rows, fallback_steps)
    # 칸 수는 제일 단계가 많은 품목에 맞춘다 — 모자라면 그 품목이 잘린다.
    width = max([len(base)] + [len(r.get("process") or []) for r in rows] or [1])
    width = max(width, 1)

    wb = Workbook()
    ws = wb.active
    ws.title = "개발 일정"

    ws["C2"] = "품목별 개발 일정 — %s" % division_label
    ws["C2"].font = Font(FONT, size=16, bold=True)
    ws["C3"] = "*고객사명은 '고객사별 품목정보' 시트와 동일하게 작성"
    ws["C3"].font = Font(FONT, size=10, color="888888")
    ws["H3"] = "*실적은 완료일로 작성"
    ws["H3"].font = Font(FONT, size=10, color="C00000")
    ws["H4"] = "*완료되었으나 날짜 확인이 어려운 경우 '완료'로 작성"
    ws["H4"].font = Font(FONT, size=10, color="C00000")

    head = HEAD + ["단계 %d" % (i + 1) for i in range(width)]
    for i, h in enumerate(head):
        c = ws.cell(5, 2 + i, h)
        c.font = Font(FONT, size=11, bold=True, color="FFFFFF")
        c.fill = HEAD_FILL
        c.border = BORDER
        c.alignment = Alignment(horizontal="center", vertical="center",
                                wrap_text=True)

    r = 6
    for n, it in enumerate(rows, 1):
        proc = it.get("process") or []
        names = [str((s or {}).get("name") or "").strip() for s in proc]
        names = [x for x in names if x] or list(base)
        for kind in KINDS:
            head_vals = [n, it.get("owner") or "", it.get("name") or "",
                         it.get("part_number") or "", it.get("dev_owner") or "",
                         kind]
            for i, v in enumerate(head_vals):
                c = ws.cell(r, 2 + i, v)
                c.font = Font(FONT, size=10, bold=(kind == "프로세스"))
                c.border = BORDER
                c.alignment = Alignment(
                    horizontal="left" if i in (1, 2) else "center",
                    vertical="center")
            for j in range(width):
                v = None
                if kind == "프로세스":
                    v = names[j] if j < len(names) else None
                elif j < len(proc):
                    st = proc[j] or {}
                    key = "expected" if kind == "계획" else "actual"
                    # 날짜가 없으면 글자로 적힌 것을 그대로 돌려준다.
                    # 안 그러면 '고객사 검토중' 이 받을 때마다 사라진다.
                    v = (str(st.get(key) or "").strip()
                         or str(st.get(key + "_note") or "").strip() or None)
                c = ws.cell(r, 2 + len(HEAD) + j, v)
                c.border = BORDER
                c.font = Font(FONT, size=9.5, bold=(kind == "프로세스"),
                              color="1F3864" if kind == "프로세스" else "000000")
                c.alignment = Alignment(horizontal="center", vertical="center",
                                        wrap_text=(kind == "프로세스"))
                if kind != "프로세스":
                    c.number_format = "yyyy-mm-dd"
            fill = PROC_FILL if kind == "프로세스" else (
                BAND_FILL if n % 2 == 0 else None)
            if fill:
                for col in range(2, 2 + len(HEAD) + width):
                    ws.cell(r, col).fill = fill
            r += 1

    r += 1
    for t, bold in (
            ("■ 적는 법", True),
            ("  · '프로세스' 줄은 단계 이름입니다. 고객사별로 다르면 그 줄만 고쳐 쓰세요.", False),
            ("  · '계획' 과 '실적' 줄의 단계 칸에만 날짜를 적습니다.", False),
            ("  · 날짜는 2026-11-30 처럼 적습니다.", False),
            ("  · 날짜를 아직 모르면 '고객사 검토중' 처럼 글자로 적어도 됩니다.", False),
            ("  · 완료됐는데 날짜를 모르면 실적 칸에 '완료' 라고 적으면 완료로 셉니다.", False),
            ("  · 아직 안 정해진 단계는 빈 칸으로 둡니다. 0 이나 - 는 적지 마세요.", False),
            ("  · 세 줄(프로세스 · 계획 · 실적)이 한 묶음입니다. 줄을 지우거나 순서를 바꾸지 마세요.", False),
            ("  · 세 줄의 고객사 · 품번은 같게 적어 주세요.", False),
            ("  · 단계를 줄이려면 뒤쪽 칸의 이름을 지우고, 늘리려면 열을 더해 머리글에 단계 N 을 적으세요.", False),
    ):
        ws.cell(r, 3, t).font = Font(FONT, size=10, bold=bold,
                                     color="000000" if bold else "666666")
        r += 1

    ws.column_dimensions["A"].width = 2
    for col, w in zip("BCDEFG", [5, 18, 30, 22, 16, 10]):
        ws.column_dimensions[col].width = w
    for j in range(width):
        ws.column_dimensions[get_column_letter(2 + len(HEAD) + j)].width = 13
    ws.row_dimensions[5].height = 30
    ws.freeze_panes = ws.cell(6, 2 + len(HEAD))

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
