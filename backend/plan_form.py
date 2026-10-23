# -*- coding: utf-8 -*-
"""작성용 양식 — 한 해를 한 장에, 열두 달을 다 펼쳐 둔다.

### 왜 한 장인가

달마다 시트 한 장짜리 양식(weekly_template)은 이번 달만 보인다. 그런데
이번 주 계획을 적는 사람은 보통 "지난 달까지 얼마나 나갔더라" 를 보면서
적는다. 그걸 보려고 시트를 왔다 갔다 하거나 보드를 따로 띄워야 했다.

그래서 한 해를 한 장에 놓는다. 열두 달 주차가 **전부 펼쳐져 있다.**
지난 달을 고치고 싶으면 그 자리에 적으면 된다.

### 어느 달에 적어도 올라간다

올리는 쪽은 원래 시트 하나를 달 하나로 읽었다. 시트 이름이 '2026-10'
이면 10월 주차만 읽고 나머지는 버렸다. 그대로 두면 9월에 적은 것이
조용히 사라진다 — 적을 수 있게 생겼는데 안 먹는 칸이 제일 나쁘다.
pbx_plan_import.sheet_months_of() 가 '이 시트는 한 해를 담고 있다' 를
알아보고 열두 달을 따로 읽게 고쳤다.

### 적는 달을 따로 표시하지 않는다

2026-10-21 — 전에는 적는 달만 펼치고 나머지를 접었고, 그 달에 빨간
테두리를 둘렀다. 그런데 적는 달은 매주 바뀐다. 표시해 둬 봐야 다음
주면 틀린 표시가 되고, 지난 달을 보려면 매번 [+] 를 눌러야 했다.
열두 달을 그냥 다 펼쳐 둔다 — 어디에 적을지는 사람이 안다.

### 보고용(plan_export)과 다르다

보고용은 진행현황에 붙이는 것이라 유형별 묶음 합계가 있고 판가·재료비가
없다. 이건 올리는 양식이라 반대다. 묶음 합계 줄도 없다 — 읽는 쪽이
'합계' 글자를 만나면 표가 끝난 줄 알아서, 중간에 두면 거기서 읽기가
끊긴다. 합계는 맨 아래 한 줄뿐이다.
"""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import (Alignment, Border, Font, PatternFill,
                             Protection, Side)
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

import week_calendar as _wc
import plan_block as _pb
import weekly_template as _wt

L2 = get_column_letter

NAVY = _wt.NAVY
HEAD2 = "1E3A5F"
DEFHEAD = "7F1D1D"     # 불량 칸 머리글 — 계획·실적과 한눈에 갈리게
CALCHEAD = "6B7280"    # 자동 계산 칸의 머리글 — 남색과 눈에 띄게 다르게

# 머리글 앞에 붙는 표. 색을 못 보는 자리(흑백 인쇄 등)에서도 읽히게.
MARK_IN = "✎"          # 적는 칸
# 자동 계산 — 건드리지 마세요.
#
# 2026-10-22 — 처음에 '=' 를 썼다가 양식에 #NAME? 이 떴다. 엑셀은 '=' 로
# 시작하는 글자를 **수식으로 읽는다**. '= 월 합계' 가 '월 합계 라는 이름을
# 계산해라' 가 되어 이름이 없다고 #NAME? 을 뱉었다. 글자를 넣을 자리에
# 수식 기호를 쓰면 안 된다.
MARK_AUTO = "※"
BLUE = _wt.BLUE        # 계획
WARM = _wt.WARM        # 실적
GREY = _wt.GREY        # 수식
LOCK = _wt.LOCK        # 누구인지 — 건드리지 않는 칸
NOTEBG = _wt.NOTEBG
SUMBG = _wt.SUMBG
KFONT = _wt.KFONT
BORDER = _wt.BORDER
DASH = "-"

ROW_TITLE = 1
# 2026-10-22 — 프로젝트 현황을 맨 아래에서 **위로** 올렸다. 맨 아래에
# 두니 백 줄을 내려가야 보여서, 멈춘 프로젝트인 줄 모르고 숫자부터
# 적는 일이 생겼다. 먼저 볼 것이 먼저 있어야 한다.
ROW_PROJ = 2           # 프로젝트 현황 — 이름표 줄
ROW_PROJ2 = 3          # 프로젝트 현황 — 적는 줄 (상태 · 현황 글)
HDR_TOP = 4            # 월 이름
HDR_WEEK = 5           # 주차 · 월 합계
HDR_SUB = 6            # 계획/실적
FIRST_ROW = 7

# 적는 줄은 어느 프로젝트든 백 줄로 맞춘다. 프로젝트마다 모델 수가 달라서
# 빈 줄만 똑같이 두면 전체 줄 수가 들쭉날쭉했다 — 받는 쪽이 "몇 줄까지가
# 적는 칸인가" 를 매번 다시 봐야 했다. 모델이 백 개를 넘으면 그만큼 늘고,
# 그 밑에는 MIN_SPARE 줄을 늘 더 붙인다.
TOTAL_ROWS = 100       # 적는 줄 전체 (모델 줄 + 빈 줄)
MIN_SPARE = 8          # 모델이 백 줄을 넘어도 빈 줄은 이만큼은 둔다
# 주차 한 칸은 두 칸이다 — 계획 · 실적.
#
# 2026-10-22 — 불량 칸을 넣었다가 뺐다. 불량률은 나중에 따로 정한다.
# (어디에 둘지, 실적수량이 양품인지 총생산인지부터 정해야 한다)
# 자리 수는 이 두 상수로만 센다 — 다시 늘릴 때 여기만 고치면 된다.
SUB = ("계획", "실적")
WEEK_W = len(SUB)                 # 주차 한 칸이 먹는 열 수
#: 월 합계 칸
SUB_TOT = SUB
TOT_W = len(SUB_TOT)

# ── 프로젝트 현황 — 모델 비고와 **다른 칸**이다 ──────────────────
#
# 보류 · 드롭예정이 두 층으로 있다.
#   · 프로젝트째 멈춘 것   CUP "컵 이슈 해결될 때까지 LAIR 작성 홀딩"
#     → 그 프로젝트 모델 전부의 시계가 멈춘다. 여기 적는다.
#   · 모델 하나만 멈춘 것   파워박스 VCTR-XPRSMS "드롭 예정"
#     → 그 한 줄만 멈춘다. 모델 줄의 **비고** 칸에 적는다.
# 두 개를 한 칸에 적으면 한 모델 드롭이 프로젝트 전체 드롭으로 읽힌다.
PROJ_LABEL = "프로젝트 현황"
# 고르는 말은 사람이 읽는 말로 둔다. 서버에 들어갈 때 '보류' · '드롭예정'
# 으로 되돌린다(pbx_plan_import.read_project_status).
PROJ_STATES = "진행 중,보류 중,드롭 예정"
#: 화면에 보이는 말 → 서버가 쓰는 말
PROJ_STATE_OUT = {"진행 중": "", "보류 중": "보류", "드롭 예정": "드롭예정"}
PROJ_STATE_IN = {"": "진행 중", "보류": "보류 중", "드롭예정": "드롭 예정"}
PROJ_HELP = ("[ 프로젝트 **전체**가 멈췄을 때만 적습니다. 모델 하나만 "
             "보류 · 드롭이면 그 줄의 비고 칸에 적으세요 ]")

# ── 예시 줄 — 빈 양식에만 넣는다 ─────────────────────────────────
#
# 처음 받는 사람은 '어느 칸에 어떤 모양으로' 를 모른다. 말로 적어 둔
# 안내보다 채워진 줄 한 개가 빠르다. 다만 그 줄이 진짜 모델로 올라가면
# 안 되니, 파트넘버 앞에 표를 달고 읽는 쪽이 그 표를 보면 건너뛴다.
# 지우고 쓰셔도 되고 그냥 두셔도 된다.
EX_MARK = "(예시)"
EXAMPLE = [
    # 파트넘버 · 모델명 · 유형 · 구분 · 판가 · 재료비 · PO · 실적 ·
    # 전환주차 · 비고 · {주차: (계획, 실적)}
    ("853-800575-413", "AETHER GDX", "EMA", "양산", 138.47, 96.0, 1200, 450,
     "", "", {0: (120, 110), 1: (120, 95)}),
    ("853-800575-404", "", "EMA", "개발", 96.0, 64.2, 300, 0,
     "2026-W36", "9월부터 양산 판가 적용", {0: (30, 30)}),
    ("715-156359-006", "", "HVM", "개발", 54.0, 31.5, 80, 12,
     "", "드롭 예정 — 고객 물량 취소", {}),
]



def layout(year: int, month: str) -> list:
    """달마다 자리 → [{'month','weeks','open'}, ...]

    열두 달이 **전부** 주차를 갖는다. open 은 펼쳐 둘 달 하나다.
    """
    out = []
    for i in range(1, 13):
        ym = "%04d-%02d" % (int(year), i)
        out.append({"month": ym,
                    "weeks": list(_wc.get_month_weeks(ym) or []),
                    "open": ym == str(month)})
    return out


def _head(ws, r, c, text, fill=NAVY, size=10):
    x = ws.cell(r, c, text)
    x.font = Font(name=KFONT, bold=True, size=size, color="FFFFFF")
    x.fill = PatternFill("solid", fgColor=fill)
    x.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    x.border = BORDER
    return x



def build_year_form(project_label: str, year: int, month: str, models: list,
                    notes: dict = None, status_note: str = "",
                    hold: str = "") -> bytes:
    """작성용 한 해 양식 바이트.

    month        펼쳐 둘 달 ('2026-10'). 시트 이름도 이것이다.
    notes        {'2026-10': {'W41': '자재 지연'}} — 달마다 미달 사유.
    status_note  프로젝트 현황 글 (프로젝트째 멈췄을 때만).
    hold         '' · '보류' · '드롭예정'.
    """
    year = int(year)
    month = str(month).strip()
    if not _wc.get_month_weeks(month):
        raise ValueError("%s 는 주차가 없는 달입니다" % month)
    if not month.startswith("%04d-" % year):
        raise ValueError("%s 는 %d년이 아닙니다" % (month, year))
    notes = notes or {}

    models = _wt.order_models(models or [])
    cols = _wt.fixed_cols(models)
    nid = len(cols)
    # 값 칸은 '숫자 넷(판가·재료비·PO·실적) → 잔량 → 나머지(전환주차·비고)'
    # 순서로 놓는다. 잔량은 PO−실적이라 그 둘 옆에 있어야 읽힌다.
    N_NUM = 4
    val_head = _wt.VALUE[:N_NUM]
    val_tail = _wt.VALUE[N_NUM:]
    col_left = nid + N_NUM + 1                 # 잔량
    nlead = nid + len(_wt.VALUE) + 1

    blocks = layout(year, month)
    c = nlead + 1
    for b in blocks:
        b["cols"] = [c + i * WEEK_W for i in range(len(b["weeks"]))]
        b["total"] = c + len(b["weeks"]) * WEEK_W
        c = b["total"] + TOT_W
    last = c - 1
    # '미달 사유' 안내 글자를 놓을 자리 하나. 적는 달 개념이 없어졌으니
    # 주차가 있는 첫 달의 월 합계 칸에 둔다.
    cur = next(b for b in blocks if b["cols"])

    wb = Workbook()
    ws = wb.active
    ws.title = month

    body = Font(name=KFONT, size=10)
    lock_f = PatternFill("solid", fgColor=LOCK)
    plan_f = PatternFill("solid", fgColor=BLUE)
    act_f = PatternFill("solid", fgColor=WARM)
    calc_f = PatternFill("solid", fgColor=GREY)

    # ── 제목 ─────────────────────────────────────────────────────────
    ws.merge_cells(start_row=ROW_TITLE, start_column=1,
                   end_row=ROW_TITLE, end_column=last)
    t = ws.cell(ROW_TITLE, 1,
                (("%s · " % project_label) if project_label else "")
                + "%d년 주차별 계획 · 실적    " % year
                + "[ ✎ 가 붙은 칸에 적으시면 됩니다. ※ 가 붙은 회색 칸"
                  "(잔량 · 월 합계 · 맨 아래 합계 줄)은 저절로 나오니 "
                  "건드리지 마세요. 모델명은 품번과 다른 이름이 있을 때만 "
                  "적고, 없으면 비워 두시면 됩니다. "
                  "열두 달이 다 들어 있어 지난 달도 여기서 고칩니다 ]")
    t.font = Font(name=KFONT, bold=True, size=11, color="FFFFFF")
    t.fill = PatternFill("solid", fgColor=NAVY)
    t.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[ROW_TITLE].height = 26

    # ── 프로젝트 현황 — 제목 바로 밑 (가장 먼저 보게) ───────────────
    _proj_status(ws, ROW_PROJ, nlead, last, status_note, hold)

    # ── 왼쪽 머리글 ──────────────────────────────────────────────────
    # 머리글에 표를 달아 둔다. 색만으로는 흑백 인쇄에서 사라지고, 색을
    # 구분 못 하는 사람도 있다. 글자로 적어 두면 어디서 봐도 읽힌다.
    #   ✎  적는 칸      — 여기에 숫자·글자를 넣는다
    #   =  자동 계산     — 수식이다. 건드리면 그 줄만 조용히 틀어진다
    ci = 1
    for head, width, _key in cols:
        ws.merge_cells(start_row=HDR_TOP, start_column=ci,
                       end_row=HDR_SUB, end_column=ci)
        _head(ws, HDR_TOP, ci, MARK_IN + " " + head)
        ws.column_dimensions[get_column_letter(ci)].width = width
        ci += 1
    for head, width, _key, _fmt in val_head:
        ws.merge_cells(start_row=HDR_TOP, start_column=ci,
                       end_row=HDR_SUB, end_column=ci)
        _head(ws, HDR_TOP, ci, MARK_IN + " " + head, fill=HEAD2)
        ws.column_dimensions[get_column_letter(ci)].width = width
        ci += 1
    ws.merge_cells(start_row=HDR_TOP, start_column=col_left,
                   end_row=HDR_SUB, end_column=col_left)
    _head(ws, HDR_TOP, col_left, MARK_AUTO + " 잔량", fill=CALCHEAD)
    ws.column_dimensions[get_column_letter(col_left)].width = 10
    ci = col_left + 1
    for head, width, _key, _fmt in val_tail:
        ws.merge_cells(start_row=HDR_TOP, start_column=ci,
                       end_row=HDR_SUB, end_column=ci)
        _head(ws, HDR_TOP, ci, MARK_IN + " " + head, fill=HEAD2)
        ws.column_dimensions[get_column_letter(ci)].width = width
        ci += 1

    # ── 달 머리글 ────────────────────────────────────────────────────
    for b in blocks:
        c0 = b["cols"][0] if b["cols"] else b["total"]
        ws.merge_cells(start_row=HDR_TOP, start_column=c0,
                       end_row=HDR_TOP, end_column=b["total"] + TOT_W - 1)
        _head(ws, HDR_TOP, c0,
              "%d월" % int(b["month"][5:7]))
        for wk, wc in zip(b["weeks"], b["cols"]):
            ws.merge_cells(start_row=HDR_WEEK, start_column=wc,
                           end_row=HDR_WEEK, end_column=wc + 1)
            _head(ws, HDR_WEEK, wc, wk, fill=HEAD2)
            for j, s in enumerate(SUB):
                _head(ws, HDR_SUB, wc + j, s,
                      fill=DEFHEAD if s == "불량" else HEAD2)
                ws.column_dimensions[get_column_letter(wc + j)].width = 8
        ws.merge_cells(start_row=HDR_WEEK, start_column=b["total"],
                       end_row=HDR_WEEK, end_column=b["total"] + TOT_W - 1)
        _head(ws, HDR_WEEK, b["total"], MARK_AUTO + " 월 합계", fill=CALCHEAD)
        for j, s in enumerate(SUB_TOT):
            _head(ws, HDR_SUB, b["total"] + j, MARK_AUTO + " " + s,
                  fill=CALCHEAD)
            ws.column_dimensions[get_column_letter(b["total"] + j)].width = 9

    ws.row_dimensions[HDR_TOP].height = 24
    ws.row_dimensions[HDR_WEEK].height = 18
    ws.row_dimensions[HDR_SUB].height = 18

    # ── 줄 ───────────────────────────────────────────────────────────
    L = get_column_letter
    r = FIRST_ROW

    # 빈 양식에만 예시 줄을 얹는다. 모델이 이미 들어 있는 양식에 넣으면
    # 진짜 줄과 섞여 보이기만 하고, 쓰는 사람이 매번 지워야 한다.
    if not models:
        r = _example_rows(ws, r, cols, col_left, nlead, blocks, cur)

    for m in models:
        ci = 1
        for v in _wt._model_row(m, cols):
            x = ws.cell(r, ci, v)
            x.font = body
            x.fill = lock_f
            x.border = BORDER
            x.alignment = Alignment(horizontal="left", vertical="center")
            ci += 1
        vals = _wt._value_row(m)
        for v, (_h, _w, _k, fmt) in zip(vals[:N_NUM], val_head):
            x = ws.cell(r, ci, v)
            x.font = body
            x.border = BORDER
            if fmt:
                x.number_format = fmt
            x.alignment = Alignment(horizontal="right", vertical="center")
            ci += 1
        ci = col_left + 1          # 잔량 칸은 아래에서 따로 채운다
        for v, (_h, _w, _k, fmt) in zip(vals[N_NUM:], val_tail):
            x = ws.cell(r, ci, v)
            x.font = body
            x.border = BORDER
            if fmt:
                x.number_format = fmt
            x.alignment = Alignment(horizontal="left", vertical="center")
            ci += 1

        # 잔량 — 한쪽이 비어 있어도 안 깨지게 SUM 으로 뺀다
        cpo, cshp = L(nid + 3), L(nid + 4)
        x = ws.cell(r, col_left,
                    '=IF(COUNT(%s%d:%s%d)=0,"",SUM(%s%d)-SUM(%s%d))'
                    % (cpo, r, cshp, r, cpo, r, cshp, r))
        x.font = Font(name=KFONT, size=10, bold=True, color=NAVY)
        x.fill = calc_f
        x.border = BORDER
        x.number_format = "#,##0"
        x.alignment = Alignment(horizontal="right", vertical="center")

        for b in blocks:
            wk_vals = _wt.week_cells(m, b["month"])
            for wk, wc in zip(b["weeks"], b["cols"]):
                got = wk_vals.get(wk) or {}
                for j, key in enumerate(("plan", "actual")):
                    x = ws.cell(r, wc + j, got.get(key))
                    x.font = body
                    x.fill = plan_f if j == 0 else act_f
                    x.border = BORDER
                    x.number_format = "#,##0"
                    x.alignment = Alignment(horizontal="right", vertical="center")
            for j in range(2):
                refs = ",".join("%s%d" % (L(wc + j), r) for wc in b["cols"])
                x = ws.cell(r, b["total"] + j,
                            '=IF(COUNT(%s)=0,"",SUM(%s))' % (refs, refs))
                x.font = Font(name=KFONT, size=10, bold=True, color=NAVY)
                x.fill = calc_f
                x.border = BORDER
                x.number_format = "#,##0"
                x.alignment = Alignment(horizontal="right", vertical="center")
        ws.row_dimensions[r].height = 17
        r += 1

    # 새 모델 적을 빈 줄 — 모델 줄까지 합쳐 TOTAL_ROWS 줄이 되게 채운다
    spare = max(MIN_SPARE, TOTAL_ROWS - len(models))
    for _ in range(spare):
        for ci2 in range(1, last + 1):
            x = ws.cell(r, ci2)
            x.font = body
            x.border = BORDER
            x.alignment = Alignment(
                horizontal="left" if ci2 <= nid else "right", vertical="center")
        ws.row_dimensions[r].height = 17
        r += 1
    r_end = r - 1

    # ── 합계 · 미달 사유 ─────────────────────────────────────────────
    #
    # 묶음(유형별) 합계는 두지 않는다. 읽는 쪽이 '합계' 글자를 만나면 표가
    # 끝난 줄 알아서, 중간에 두면 그 아래 줄이 통째로 안 읽힌다.
    r_sum = r
    sum_f = PatternFill("solid", fgColor=SUMBG)
    sum_font = Font(name=KFONT, size=10, bold=True, color="FFFFFF")
    for ci2 in range(1, last + 1):
        x = ws.cell(r_sum, ci2)
        x.font = sum_font
        x.fill = sum_f
        x.border = BORDER
        x.number_format = "#,##0"
        x.alignment = Alignment(horizontal="right", vertical="center")
    lab = ws.cell(r_sum, 1, "합계")
    lab.alignment = Alignment(horizontal="left", vertical="center")
    for ci2 in range(nid + 3, last + 1):      # 판가·재료비는 더하지 않는다
        c2 = L(ci2)
        ws.cell(r_sum, ci2, '=IF(COUNT(%s%d:%s%d)=0,"",SUM(%s%d:%s%d))'
                % (c2, FIRST_ROW, c2, r_end, c2, FIRST_ROW, c2, r_end))
    ws.row_dimensions[r_sum].height = 20

    r_note = r_sum + 1
    note_f = PatternFill("solid", fgColor=NOTEBG)
    # 글씨를 한 호수 줄인다. 주차 칸은 좁아서(7 남짓) 10호로는 두세 글자만
    # 보이고 나머지는 잘렸다. 적어 둔 사유를 읽으려면 칸을 하나하나
    # 눌러 봐야 했다.
    note_font = Font(name=KFONT, size=9)
    for ci2 in range(1, last + 1):
        x = ws.cell(r_note, ci2)
        x.font = note_font
        x.fill = note_f
        x.border = BORDER
        # 2026-10-22 — 가운데가 아니라 **위에서부터** 쌓는다. 여러 줄이
        # 되면 가운데 정렬은 위아래가 잘려 보인다.
        x.alignment = Alignment(horizontal="left", vertical="top",
                                wrap_text=True)
    nl = ws.cell(r_note, 1, "미달 사유")
    nl.font = Font(name=KFONT, size=10, bold=True, color=NAVY)
    if nlead >= 2:
        ws.merge_cells(start_row=r_note, start_column=1,
                       end_row=r_note, end_column=nlead)
    for b in blocks:
        mn = notes.get(b["month"]) or {}
        for wk, wc in zip(b["weeks"], b["cols"]):
            ws.merge_cells(start_row=r_note, start_column=wc,
                           end_row=r_note, end_column=wc + 1)
            txt = str(mn.get(wk) or "").strip()
            if txt:
                ws.cell(r_note, wc, txt)
        ws.merge_cells(start_row=r_note, start_column=b["total"],
                       end_row=r_note, end_column=b["total"] + 1)
    x = ws.cell(r_note, cur["total"],
                "— 못 채운 주에만 · '참고:' 로 시작하면 문제로 안 셈 · "
                "'-' 는 지우기")
    x.font = Font(name=KFONT, size=9, color="94A3B8")

    # 줄 높이는 **가장 긴 사유**에 맞춘다.
    #
    # 2026-10-22 — 32 로 박아 두었더니 한 줄 반쯤에서 글자가 잘렸다.
    # 주차 칸 둘을 합쳐도 폭이 14 남짓이라 한 줄에 7~8 글자밖에 안 들어간다.
    # 적어 놓고 안 보이면 아무도 안 적는다.
    ws.row_dimensions[r_note].height = _wrap_height(
        [str((notes.get(b["month"]) or {}).get(wk) or "")
         for b in blocks for wk in b["weeks"]],
        per_line=14, low=34, high=108)

    # ── PPT 에 그대로 붙이는 표 — 다음 장에 ────────────────────────
    #
    # 2026-10-22 — 적는 장 아래에 붙여 두다가 다음 장으로 뺐다. CUP ·
    # 하바플레이트처럼 모델이 많은 프로젝트는 적는 칸만으로 한 장을 다
    # 쓴다. 그 아래 또 표가 붙으면 스크롤이 끝없이 길어지고, 같은 장을
    # 쓰는 동안은 열 너비도 못 건드렸다 — 위쪽 표가 같이 찌그러져서다.
    #
    # 주차를 펼쳐 둘 달은 '적는 달' 이다. cur 는 미달 사유 안내를 놓으려고
    # 고른 '주차가 있는 첫 달' 이라 여기 쓰면 1월이 펼쳐진다.
    tgt = next(b for b in blocks if b["month"] == month)


    # 2026-10-21 — '적는 달' 을 따로 표시하거나 나머지를 접던 것을 뺐다.
    #
    # 적는 달은 매주 바뀐다. 표시해 둬 봐야 다음 주면 틀린 표시가 되고,
    # 접어 두면 지난 달을 보려고 매번 [+] 를 눌러야 했다. 열두 달을
    # 그냥 다 펼쳐 둔다 — 적을 자리는 사람이 안다.

    # 구분은 새 줄을 적을 때 고르는 칸이다
    gi = next((i for i, c2 in enumerate(cols, start=1) if c2[2] == "group"), None)
    if gi:
        dv = DataValidation(type="list", formula1='"양산,개발"', allow_blank=True)
        ws.add_data_validation(dv)
        dv.add("%s%d:%s%d" % (L(gi), FIRST_ROW, L(gi), r_end))

    # ── 적는 칸만 열고 나머지는 잠근다 ─────────────────────────────
    #
    # 여는 자리
    #   · 모델 줄 왼쪽 — 잔량(수식)만 빼고
    #   · 달마다 주차 칸 — 월 합계 두 칸은 수식이라 뺀다
    #   · 미달 사유 줄의 주차 칸
    #   · 프로젝트 현황 두 칸
    _open = []
    L2 = get_column_letter
    for r in range(FIRST_ROW, r_end + 1):
        for c in range(1, nlead + 1):
            if c == col_left:          # 잔량 = PO − 실적
                continue
            _open.append("%s%d" % (L2(c), r))
        for b in blocks:
            for wc in b["cols"]:
                _open.append("%s%d" % (L2(wc), r))
                _open.append("%s%d" % (L2(wc + 1), r))
    for b in blocks:
        for wc in b["cols"]:
            _open.append("%s%d" % (L2(wc), r_note))
    _open.append("%s%d" % (L2(2), ROW_PROJ2))   # 상태
    _open.append("%s%d" % (L2(3), ROW_PROJ2))   # 현황 글
    _protect(ws, _open)

    ws.freeze_panes = ws.cell(FIRST_ROW, nlead + 1)
    ws.sheet_view.showGridLines = False
    # 인쇄 — 세로로는 한 장, 가로로는 필요한 만큼. 가로까지 한 장에
    # 맞추면 달을 다 펼쳤을 때 백서른 칸이 뭉개진다.
    ws.page_setup.orientation = "landscape"
    # 적는 줄이 백 줄이라 세로로 한 장에 몰아넣으면 글자가 안 보인다.
    # 세로는 필요한 만큼 넘긴다.
    ws.page_setup.fitToHeight = 0
    ws.page_setup.fitToWidth = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "%d:%d" % (HDR_TOP, HDR_SUB)
    ws.print_title_cols = "%s:%s" % (L(1), L(nlead))

    _pb.add_project_block(wb, month, project_label, blocks, tgt,
                          FIRST_ROW, models)
    _guide(wb, project_label, year, month)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ==========================================
#  프로젝트 현황 — 프로젝트째 멈췄을 때만 적는 두 줄
# ==========================================
# ==========================================
#  글자가 몇 줄이 되는지 보고 줄 높이를 정한다
# ==========================================
def _wrap_height(texts, per_line, low, high):
    """칸 폭에 맞춰 접었을 때 가장 긴 글이 몇 줄인지로 높이를 낸다.

    엑셀은 '자동 줄 높이' 를 합친 칸에는 안 걸어 준다. 합친 칸이 바로
    미달 사유와 프로젝트 현황이라, 높이를 안 정해 주면 둘째 줄부터
    잘려서 안 보인다. 적어 놓고 안 보이면 아무도 안 적는다.

    per_line  그 폭에 한 줄로 들어가는 글자 수 (한글 기준, 넉넉히 잡는다)
    low/high  너무 납작하거나 한 장을 다 먹지 않게 막는 울타리
    """
    n = 1
    for t in texts or []:
        t = str(t or "")
        if not t:
            continue
        for part in t.splitlines() or [""]:
            n = max(n, -(-len(part) // max(1, per_line)))
        n = max(n, len(t.splitlines()))
    return max(low, min(high, 15 * n + 8))


# ==========================================
#  예시 줄 — 빈 양식에 채워진 줄 몇 개를 얹는다
# ==========================================
def _example_rows(ws, r, cols, col_left, nlead, blocks, cur):
    """r 줄부터 예시를 적고 그 다음 줄 번호를 돌려준다.

    읽는 쪽은 파트넘버가 '(예시)' 로 시작하면 건너뛴다. 그래서 지우지
    않고 올려도 모델로 만들어지지 않는다.
    """
    ex_font = Font(name=KFONT, size=10, italic=True, color="94A3B8")
    ex_fill = PatternFill("solid", fgColor="FFFDF2")
    nid = len(cols)

    for pn, nm, dt, grp, price, mcost, po, sh, sw, note, weeks in EXAMPLE:
        vals = ["%s %s" % (EX_MARK, pn), nm, dt, grp,
                price, mcost, po, sh]
        # 왼쪽 네 칸 + 숫자 네 칸 → 잔량 → 전환주차 · 비고
        order = vals[:nid] + vals[nid:nid + 4] + [None] + [sw, note]
        ci = 1
        for v in order:
            if ci == col_left:                 # 잔량은 수식이 이미 들어간다
                ci += 1
                continue
            x = ws.cell(r, ci, v)
            x.font = ex_font
            x.fill = ex_fill
            x.border = BORDER
            x.alignment = Alignment(
                horizontal="left" if ci <= nid or ci > nid + 5 else "right",
                vertical="center")
            ci += 1
        x = ws.cell(r, col_left,
                    '=IF(COUNT(%s%d:%s%d)=0,"",SUM(%s%d)-SUM(%s%d))'
                    % (L2(nid + 3), r, L2(nid + 4), r,
                       L2(nid + 3), r, L2(nid + 4), r))
        x.font = ex_font
        x.fill = ex_fill
        x.border = BORDER
        x.alignment = Alignment(horizontal="right", vertical="center")

        # 이번 달 주차 몇 칸만 채운다 — 나머지 달은 비워 둔다
        for i, (plan, act) in (weeks or {}).items():
            if i >= len(cur["cols"]):
                continue
            for j, v in enumerate((plan, act)):
                y = ws.cell(r, cur["cols"][i] + j, v)
                y.font = ex_font
                y.fill = ex_fill
                y.border = BORDER
                y.number_format = "#,##0"
                y.alignment = Alignment(horizontal="right", vertical="center")
        ws.row_dimensions[r].height = 17
        r += 1

    # 예시가 어디서 끝나는지 한 줄로 말해 준다
    g = ws.cell(r, 1, "↑ 여기까지 예시입니다. 지우고 쓰셔도 되고, 그냥 두셔도 "
                      "올라가지 않습니다 (파트넘버에 '(예시)' 가 붙은 줄은 "
                      "읽지 않습니다)")
    g.font = Font(name=KFONT, size=9, italic=True, color="B45309")
    g.alignment = Alignment(horizontal="left", vertical="center")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=nlead)
    for c in range(1, nlead + 1):
        ws.cell(r, c).fill = PatternFill("solid", fgColor="FFFBEB")
    ws.row_dimensions[r].height = 19
    return r + 1


def _proj_status(ws, r, nlead, last, note="", hold="", wide_to=None):
    """r · r+1 두 줄을 놓고 마지막 줄 번호를 돌려준다.

    모델 줄의 비고와 **다른 칸**이다. 비고는 그 모델 하나만 멈춘 것이고
    여기는 프로젝트 전체가 멈춘 것이다. 둘을 한 칸에 적으면 모델 하나
    드롭이 프로젝트 전체 드롭으로 읽힌다.
    """
    # 글 칸을 왼쪽 열들 폭에만 맞춰 두면 한 줄에 열 몇 글자다. CUP 현황은
    # 세 줄짜리라 거기서 잘렸다. 첫 달 주차 칸까지 끌어와 폭을 벌린다
    # (2026-10-22). 그 아래는 빈 줄이라 가려지는 것도 없다.
    wide = max(6, min(wide_to or (nlead + 10), last))

    # ----------------------------------------------------------------------------
    #  머리 줄 — 이름표 · 안내
    # ----------------------------------------------------------------------------
    h = ws.cell(r, 1, PROJ_LABEL)
    h.font = Font(name=KFONT, bold=True, size=11, color="FFFFFF")
    h.fill = PatternFill("solid", fgColor=NAVY)
    h.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    h.border = BORDER
    for c in range(2, wide + 1):
        x = ws.cell(r, c)
        x.fill = PatternFill("solid", fgColor=NAVY)
        x.border = BORDER
    g = ws.cell(r, 2, PROJ_HELP.replace("**", ""))
    g.font = Font(name=KFONT, size=9, color="C7D2E5")
    g.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=wide)
    ws.row_dimensions[r].height = 22

    # ----------------------------------------------------------------------------
    #  적는 줄 — 상태 한 칸 + 글 한 칸
    # ----------------------------------------------------------------------------
    rr = r + 1
    lab = ws.cell(rr, 1, "상태")
    lab.font = Font(name=KFONT, bold=True, size=10, color=NAVY)
    lab.alignment = Alignment(horizontal="center", vertical="center")
    lab.fill = PatternFill("solid", fgColor=LOCK)
    lab.border = BORDER

    # 서버가 쓰는 말('' · 보류 · 드롭예정) → 사람이 읽는 말
    st = ws.cell(rr, 2, PROJ_STATE_IN.get(str(hold or "").strip(), "진행 중"))
    st.font = Font(name=KFONT, bold=True, size=10)
    st.alignment = Alignment(horizontal="center", vertical="center")
    st.fill = PatternFill("solid", fgColor=BLUE)
    st.border = BORDER
    dv = DataValidation(type="list", formula1='"%s"' % PROJ_STATES,
                        allow_blank=True)
    ws.add_data_validation(dv)
    dv.add("%s%d" % (get_column_letter(2), rr))

    tx = ws.cell(rr, 3, str(note or ""))
    tx.font = Font(name=KFONT, size=10)
    tx.alignment = Alignment(horizontal="left", vertical="top",
                             wrap_text=True, indent=1)
    tx.fill = PatternFill("solid", fgColor=BLUE)
    for c in range(3, wide + 1):
        ws.cell(rr, c).border = BORDER
    ws.merge_cells(start_row=rr, start_column=3, end_row=rr, end_column=wide)

    # 합친 칸은 엑셀이 높이를 자동으로 안 잡아 준다. 글 길이를 보고 정한다.
    ws.row_dimensions[rr].height = _wrap_height(
        [note], per_line=_wide_chars(ws, 3, wide), low=34, high=160)
    return rr


# ==========================================
#  합친 칸의 폭이 한글 몇 글자인가
# ==========================================
def _wide_chars(ws, c_from, c_to):
    """엑셀 열 너비는 반각 글자 수다. 한글은 두 칸을 먹으니 반으로 본다."""
    w = 0.0
    for c in range(c_from, c_to + 1):
        d = ws.column_dimensions.get(get_column_letter(c))
        w += (d.width if d is not None and d.width else 8.43)
    return max(8, int(w / 2) - 2)


# ==========================================
#  수식 칸을 잠근다 — 지금은 꺼 두었다
# ==========================================
#
# 잔량 · 월 합계 · 합계 줄 · 아래 PPT 표는 전부 수식이다. 손으로 덮어쓰면
# 그 줄만 조용히 틀린 숫자가 된다. 그래서 한 번 잠가 봤는데, 쓰는 쪽에서
# 시트 보호가 거치적거린다는 말이 나왔다 (2026-10-22). 끈다.
#
# 코드는 지우지 않는다 — 지우면 되살릴 자리를 잊는다. 다시 걸려면
# PROTECT_SHEET 를 True 로 둔다. 칸마다 '여는 칸 · 잠그는 칸' 을 가르는
# 셈은 그대로 살아 있다.
#
# 잠그더라도 암호는 걸지 않는다. 암호를 걸면 적을 자리를 늘리고 싶을 때
# 아무도 못 열고, 암호를 어딘가 적어 두게 된다. 자물쇠가 아니라 난간이다.
PROTECT_SHEET = False


def _protect(ws, open_cells):
    """open_cells 에 든 칸만 열고 나머지는 잠근 뒤 시트를 보호한다.

    PROTECT_SHEET 가 False 면 아무것도 안 한다 — 칸 잠금 표시도 안 남긴다.
    표시만 남겨 두면 나중에 누가 시트 보호를 켰을 때 이유를 모른 채
    절반만 잠긴 파일이 된다.
    """
    if not PROTECT_SHEET:
        return
    locked = Protection(locked=True)
    free = Protection(locked=False)
    for row in ws.iter_rows():
        for c in row:
            c.protection = locked
    for ref in open_cells:
        ws[ref].protection = free
    ws.protection.sheet = True
    # 잠긴 칸도 **고를 수는 있어야** 한다. 2026-10-22 에 고르는 것까지
    # 막았더니 시트가 통째로 죽은 것처럼 보였고, 무엇보다 맨 아래 PPT 표를
    # 끌어서 복사할 수가 없었다 — 그 표의 존재 이유가 복사인데.
    # 고르기 · 복사는 되고, 적기만 안 된다.
    ws.protection.selectLockedCells = True
    ws.protection.selectUnlockedCells = True
    ws.protection.formatCells = False
    ws.protection.insertRows = False
    ws.protection.deleteRows = False


def _guide(wb, label, year, month):
    g = wb.create_sheet("작성 안내")
    g.column_dimensions["A"].width = 20
    g.column_dimensions["B"].width = 86
    g.merge_cells("A1:B1")
    t = g.cell(1, 1, "%s%d년 작성용 — 어디에 적나"
               % (("%s · " % label) if label else "", year))
    t.font = Font(name=KFONT, bold=True, size=12, color="FFFFFF")
    t.fill = PatternFill("solid", fgColor=NAVY)
    t.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    g.row_dimensions[1].height = 26

    rows = [
        ("장이 셋입니다", "'%s' 는 적는 장(한 해 열두 달이 가로로), "
                      "'PPT 붙이기' 는 보기 · 복사용, 이 '작성 안내' 는 "
                      "읽는 장입니다. 적는 것은 첫 장 하나뿐입니다." % month),
        ("열두 달", "1월부터 12월까지 다 펼쳐져 있습니다. 지난 달도 여기서 고치면 "
                 "그대로 들어갑니다."),
        ("✎ 와 ※", "머리글 앞의 ✎ 는 적는 칸, ※ 는 자동 계산 칸입니다. "
                  "※ 칸(잔량 · 월 합계 · 맨 아래 합계 줄)은 수식이라 "
                  "손으로 숫자를 넣으면 수식이 날아가고 그 줄만 틀어집니다. "
                  "색이 안 보이는 흑백 인쇄에서도 읽히라고 글자로 달았습니다."),
        ("적는 칸", "주차 칸(계획·실적)과 왼쪽의 ✎ 칸들입니다."),
        ("모델명", "품번과 **다른 이름**이 있을 때만 적습니다. 챔버 · CUP · "
                "하바플레이트처럼 품번이 곧 이름인 프로젝트는 "
                "**비워 두시면 됩니다** — 파트넘버 칸만 채우면 그 줄이 "
                "누구인지 서버가 압니다. 억지로 품번을 두 번 적지 마세요."),
        ("빈 칸", "한 줄에 숫자가 하나라도 있으면 그 줄의 **그 달** 주차 칸은 전부 "
                "파일대로 들어갑니다. 비운 칸은 0 이 됩니다. 한 줄을 통째로 "
                "비워 두면 그 줄은 손대지 않습니다."),
        ("판가·재료비·PO", "비어 있던 칸만 채웁니다. 이미 값이 있는 칸은 그대로 둡니다 — "
                       "덮어쓰려면 올릴 때 미리보기에서 고르세요."),
        ("새 모델", "빈 줄에 적으면 새로 만들어집니다. **파트넘버**와 "
                 "**구분(양산/개발)** 은 꼭 적어 주세요 — 이 둘만 있으면 "
                 "됩니다. 적는 줄은 어느 프로젝트든 %d 줄입니다."
                 % TOTAL_ROWS),
        ("미달 사유", "맨 아래 줄입니다. 계획을 못 채운 주에만 그 주 칸에 적으시면 "
                   "됩니다. 일부러 덜 출하한 주처럼 문제가 아닌 것은 "
                   "'참고:' 로 시작해 적으시면 지연으로 세지 않습니다. "
                   "이미 적힌 사유를 지우려면 '-' 한 글자만 남기세요 — "
                   "빈 칸은 '그대로 둬라' 라서 지워지지 않습니다. "
                   "관리자 웹에서는 더 이상 적지 않습니다."),

        (PROJ_LABEL, "'미달 사유' 아래 두 줄입니다. 프로젝트 **전체**가 멈췄을 "
                     "때만 적습니다 (진행 · 보류 · 드롭예정). 모델 하나만 "
                     "보류 · 드롭이면 여기가 아니라 그 줄의 비고 칸에 "
                     "적으세요 — 여기 적으면 프로젝트 전체가 멈춘 것으로 "
                     "읽혀서, 그 프로젝트 모델 전부가 지연 집계에서 빠집니다."),
        ("수식 칸", "잔량 · 월 합계 · 합계 줄 · 맨 아래 PPT 표는 수식입니다. "
                  "잠가 두지 않았으니 고칠 수는 있지만, 손으로 덮어쓰면 그 "
                  "줄만 숫자가 틀어지고 나중에 왜 안 맞는지 찾기 어렵습니다. "
                  "건드리지 마세요."),
        ("PPT 붙이기 장", "둘째 장입니다. 지금 쓰시던 모양 그대로 보여 주는 "
                        "표인데, 전부 수식이라 이 장에 적으시면 저절로 "
                        "채워집니다. 거기에는 적지 마세요 — 서버도 그 장은 "
                        "읽지 않습니다. 표를 끌어 복사해 PPT 에 붙이시면 "
                        "됩니다."),
    ]
    r = 3
    for k, v in rows:
        a = g.cell(r, 1, k)
        a.font = Font(name=KFONT, bold=True, size=10, color=NAVY)
        a.alignment = Alignment(horizontal="left", vertical="top")
        b = g.cell(r, 2, v)
        b.font = Font(name=KFONT, size=10)
        b.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        g.row_dimensions[r].height = 30
        r += 1
    g.sheet_view.showGridLines = False
    g.protection.sheet = PROTECT_SHEET   # 읽는 장이지만 같이 껐다 끈다
    return g
