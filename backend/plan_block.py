"""사업부가 지금 쓰고 있는 모양 그대로 — PPT 에 붙이는 표.

2026-10-22 — 적는 시트 아래에 붙여 두다가 **다음 장**으로 뺐다.
CUP · 하바플레이트처럼 모델이 많은 프로젝트는 적는 칸만으로 한 장을 다
쓴다. 그 아래에 또 표가 붙으면 스크롤이 끝없이 길어지고, 무엇보다 같은
장을 쓰는 동안은 열 너비를 손댈 수 없었다 — 위쪽 표가 같이 찌그러져서다.
장을 나누니 이 표에 맞는 너비를 줄 수 있다.

사진으로 받은 네 프로젝트(파워박스 · 아리스타 PCB · CUP · 하바플레이트)의
표가 생김새는 조금씩 달라도 뼈대는 같았다.

    구분 │ 파트넘버 │ 모델명 │ PO수량 │ 출하실적 │ PO잔량 │
         │ 1월 계획·실적 … 12월 계획·실적 │ 이번 달 주차별 │ 이번 달 Total

여기 있는 칸은 **전부 수식**이다. 적는 장을 가리킨다. 손으로 적는 칸이
아니다 — 실적을 두 번 적지 않게 하려고 이렇게 했다.
서버도 이 장은 읽지 않는다(_is_report_sheet).
"""

from __future__ import annotations

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

# ── 사진에서 그대로 가져온 색 ────────────────────────────────────
NAVY = "1F3864"        # 머리글 · 합계 줄
BAND = "2E75B6"        # 이번 달 띠
PLUM = "70376B"        # 주차 밑의 '계획'
PLUM2 = "A6A6A6"       # 주차 밑의 '실적'
YELLOW = "FFFF00"      # 달 합계 · 이번 달 Total
GREY = "D9D9D9"        # 실적 칸
CREAM = "FDF3E3"       # 양산 묶음 왼쪽 칸
KFONT = "맑은 고딕"

_thin = Side(style="thin", color="7F7F7F")
BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
_red = Side(style="medium", color="FF0000")

SHEET_NAME = "PPT 붙이기"      # 이 표가 사는 장
TITLE_MARK = "PPT 붙이는 표"   # 읽는 쪽이 이 장을 알아보는 표시
# 왼쪽 여섯 칸 — (머리글, 너비, 적는 장에서 가져올 열)
#
# 장을 따로 쓰니 너비를 제 몫대로 줄 수 있다.
LEFT = [
    ("구분", 9, "D"),
    ("파트넘버", 19, "A"),
    ("모델명", 22, "B"),
    ("PO수량", 11, "G"),
    ("출하실적", 11, "H"),
    ("PO잔량", 11, "I"),
]


# ==========================================
#  칸 하나를 칠하고 테두리를 두른다
# ==========================================
def _cell(ws, r, c, v=None, fill=None, bold=False, color="000000",
          size=9, align="center", fmt="#,##0", red=False):
    x = ws.cell(r, c, v)
    x.font = Font(name=KFONT, size=size, bold=bold, color=color)
    if fill:
        x.fill = PatternFill("solid", fgColor=fill)
    x.border = Border(left=_red if red else _thin, right=_red if red else _thin,
                      top=_thin, bottom=_thin) if red else BORDER
    x.alignment = Alignment(horizontal=align, vertical="center",
                            wrap_text=(align == "center"))
    if fmt:
        x.number_format = fmt
    return x


# ==========================================
#  머리글 석 줄 — 달 이름 · 주차 · 계획/실적
# ==========================================
def _header(ws, r, blocks, cur):
    """r·r+1·r+2 석 줄을 채우고, 열 자리를 알려주는 표를 돌려준다."""
    c = 1

    # ----------------------------------------------------------------------------
    #  왼쪽 여섯 칸 — 석 줄을 하나로 합친다
    # ----------------------------------------------------------------------------
    for head, w, _src in LEFT:
        _cell(ws, r, c, head, NAVY, True, "FFFFFF", 10, fmt=None)
        ws.merge_cells(start_row=r, start_column=c, end_row=r + 2, end_column=c)
        for rr in (r + 1, r + 2):
            _cell(ws, rr, c, None, NAVY, fmt=None)
        ws.column_dimensions[L(c)].width = w
        c += 1

    # ----------------------------------------------------------------------------
    #  1월 ~ 12월 — 달마다 계획·실적 두 칸
    # ----------------------------------------------------------------------------
    months = {}
    for b in blocks:
        mm = int(b["month"][5:7])
        _cell(ws, r, c, "%d월" % mm, NAVY, True, "FFFFFF", 10, fmt=None)
        ws.merge_cells(start_row=r, start_column=c, end_row=r + 1,
                       end_column=c + 1)
        _cell(ws, r + 1, c + 1, None, NAVY, fmt=None)
        for j, nm in enumerate(("계획", "실적")):
            _cell(ws, r + 2, c + j, nm, NAVY, True, "FFFFFF", 8, fmt=None)
            ws.column_dimensions[L(c + j)].width = 7.5
        months[b["month"]] = c
        c += 2

    # ----------------------------------------------------------------------------
    #  이번 달 — 주차를 펼친다 (사진의 파란 띠 · 보라 머리글)
    # ----------------------------------------------------------------------------
    wk_start = c
    for wk in cur["weeks"]:
        _cell(ws, r + 1, c, wk, NAVY, True, "FFFFFF", 9, fmt=None)
        ws.merge_cells(start_row=r + 1, start_column=c, end_row=r + 1,
                       end_column=c + 1)
        _cell(ws, r + 1, c + 1, None, NAVY, fmt=None)
        _cell(ws, r + 2, c, "계획", PLUM, True, "FFFFFF", 8, fmt=None)
        _cell(ws, r + 2, c + 1, "실적", PLUM2, True, "FFFFFF", 8, fmt=None)
        ws.column_dimensions[L(c)].width = 8
        ws.column_dimensions[L(c + 1)].width = 8
        c += 2
    _cell(ws, r, wk_start, "%d월" % int(cur["month"][5:7]), BAND, True,
          "FFFFFF", 10, fmt=None)
    ws.merge_cells(start_row=r, start_column=wk_start, end_row=r,
                   end_column=c - 1)

    # ----------------------------------------------------------------------------
    #  맨 오른쪽 — 이번 달 Total (사진의 노란 두 칸)
    # ----------------------------------------------------------------------------
    tot = c
    _cell(ws, r, tot, "%d월 Total" % int(cur["month"][5:7]), BAND, True,
          "FFFFFF", 10, fmt=None)
    ws.merge_cells(start_row=r, start_column=tot, end_row=r + 1,
                   end_column=tot + 1)
    _cell(ws, r + 1, tot + 1, None, BAND, fmt=None)
    for j, nm in enumerate(("계획", "실적")):
        _cell(ws, r + 2, tot + j, nm, PLUM if j == 0 else PLUM2, True,
              "FFFFFF", 8, fmt=None)
        ws.column_dimensions[L(tot + j)].width = 9

    for rr, h in ((r, 20), (r + 1, 17), (r + 2, 16)):
        ws.row_dimensions[rr].height = h
    return {"months": months, "weeks": wk_start, "total": tot, "last": tot + 1}


# ==========================================
#  한 줄을 그린다 — 적는 칸의 src 줄을 그대로 비춘다
# ==========================================
def _row(ws, rr, src, pos, blocks, cur, ref):
    """ref 는 적는 장을 가리키는 말머리 — "'2026-10'!" 꼴."""
    for ci, (_h, _w, col) in enumerate(LEFT, start=1):
        if ci == 1:            # 구분 칸은 묶음 머리가 따로 그린다
            continue
        txt = ci <= 3
        a = "%s%s%d" % (ref, col, src)
        _cell(ws, rr, ci, '=IF(%s="","",%s)' % (a, a),
              None, ci == 2, "000000", 9, "center",
              fmt=None if txt else "#,##0")
    for ym, c in pos["months"].items():
        b = next(x for x in blocks if x["month"] == ym)
        for j in range(2):
            t = "%s%s%d" % (ref, L(b["total"] + j), src)
            _cell(ws, rr, c + j, '=IF(%s="","",%s)' % (t, t), YELLOW)
    c = pos["weeks"]
    for wc in cur["cols"]:
        for j in range(2):
            t = "%s%s%d" % (ref, L(wc + j), src)
            _cell(ws, rr, c + j, '=IF(%s="","",%s)' % (t, t),
                  None if j == 0 else GREY)
        c += 2
    for j in range(2):
        t = "%s%s%d" % (ref, L(cur["total"] + j), src)
        _cell(ws, rr, pos["total"] + j, '=IF(%s="","",%s)' % (t, t), YELLOW)
    ws.row_dimensions[rr].height = 15


# ==========================================
#  합계 줄 — 사진의 남색 띠
# ==========================================
def _sum_row(ws, rr, label, rows, pos, size=9):
    """rows 는 더할 줄 번호들. 흩어져 있어도 된다."""
    for ci in range(1, pos["last"] + 1):
        _cell(ws, rr, ci, None, NAVY, True, "FFFFFF", size)
    x = ws.cell(rr, 1, label)
    x.alignment = Alignment(horizontal="center", vertical="center")
    ws.merge_cells(start_row=rr, start_column=1, end_row=rr, end_column=3)
    if rows:
        for ci in range(4, pos["last"] + 1):
            ref = ",".join("%s%d" % (L(ci), r) for r in rows)
            ws.cell(rr, ci, '=IF(COUNT(%s)=0,"",SUM(%s))' % (ref, ref))
    ws.row_dimensions[rr].height = 18


# ==========================================
#  적는 칸 밑에 'PPT 에 그대로 붙일' 표를 그린다
# ==========================================
def add_project_block(wb, src_sheet, label, blocks, cur, first_row, models):
    """적는 장 옆에 'PPT 붙이기' 장을 만들고 표를 그린다 → 만든 장.

    빈 줄은 두지 않는다. 모델이 있는 줄만, 양산 · 개발로 묶어서 그린다 —
    PPT 에 범위를 끌어 복사해 붙이는 것이 이 표의 용도다.

    wb          워크북
    src_sheet   적는 장 이름 ('2026-10'). 수식이 이 장을 가리킨다.
    models      적는 칸에 적힌 순서 그대로의 모델 목록
    first_row   적는 칸의 첫 줄 (models[0] 이 여기 있다)
    """
    ws = wb.create_sheet(SHEET_NAME)
    ws.sheet_view.showGridLines = False
    # 장 이름에 '-' 가 들어 있어서 따옴표를 꼭 씌워야 한다. 안 씌우면
    # 엑셀이 '2026 빼기 10' 으로 읽어 온 표가 #NAME? 로 깨진다.
    ref = "'%s'!" % str(src_sheet).replace("'", "''")
    r = 1

    # ----------------------------------------------------------------------------
    #  제목 한 줄
    # ----------------------------------------------------------------------------
    t = ws.cell(r, 1, "%s%s — '%s' 장에 적으시면 여기가 따라옵니다"
                % (("%s · " % label) if label else "", TITLE_MARK, src_sheet))
    t.font = Font(name=KFONT, bold=True, size=11, color=NAVY)
    t.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[r].height = 22

    pos = _header(ws, r + 1, blocks, cur)
    rr = r + 4

    # ----------------------------------------------------------------------------
    #  양산 → 개발 순서로 묶는다 (사진의 왼쪽 세로 칸)
    # ----------------------------------------------------------------------------
    groups, order = {}, []
    for i, m in enumerate(models or []):
        g = str((m or {}).get("group") or "").strip() or "미지정"
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(first_row + i)
    order.sort(key=lambda g: {"양산": 0, "개발": 1}.get(g, 2))

    all_rows = []
    for g in order:
        srcs = groups[g]
        top = rr
        for src in srcs:
            _row(ws, rr, src, pos, blocks, cur, ref)
            all_rows.append(rr)
            rr += 1
        # 묶음 이름을 왼쪽 칸에 세로로 한 번
        _cell(ws, top, 1, g, NAVY, True, "FFFFFF", 10, fmt=None)
        if rr - 1 > top:
            ws.merge_cells(start_row=top, start_column=1, end_row=rr - 1,
                           end_column=1)
            for x in range(top + 1, rr):
                _cell(ws, x, 1, None, NAVY, fmt=None)
        _sum_row(ws, rr, "합계", list(range(top, rr)), pos)
        rr += 1

    # ----------------------------------------------------------------------------
    #  맨 아래 총 합계 — 묶음 합계를 또 더하지 않도록 줄을 집어서 더한다
    # ----------------------------------------------------------------------------
    _sum_row(ws, rr, "총 합계", all_rows, pos, size=10)

    # 쓰는 사람에게 한 줄 — 여기는 적는 자리가 아니다
    g = ws.cell(rr + 2, 1,
                "이 장은 보기 · 복사용입니다. 칸이 전부 수식이라 적어도 "
                "올라가지 않습니다. 표를 끌어 복사해 PPT 에 붙이세요.")
    g.font = Font(name=KFONT, size=9, color="94A3B8")
    # 머리글 석 줄(2~4)과 왼쪽 여섯 칸을 고정해 둔다. freeze_panes 는
    # **합쳐지지 않은** 칸이어야 한다 — 머리글 칸은 석 줄이 합쳐져 있어서
    # 거기를 가리키면 양식이 통째로 안 만들어진다.
    ws.freeze_panes = "%s%d" % (L(len(LEFT) + 1), 5)
    return ws
