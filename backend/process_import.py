"""개발 프로세스 일정표 엑셀 파서 (Process Schedule 형식).

표 구조 (거의 고정):
  1행 : No. | Part Number | 01 FA PO | 02 Material Order | ... | 13 Final Approval Complete | Comment
        (단계 머리글은 두 칸을 병합해서 씀)
  2행 : (빈칸) (빈칸) Planned Actual Planned Actual ...
  3행~: 순번 | 파트넘버 | 날짜들...

날짜가 아닌 값('지속 입고중', '가공전', '확인중', '-')은 완료로 보지 않고
진행중 표시 + 메모로 남긴다.
"""

import re
import datetime as _dt

# 단계 머리글에서 번호와 이름을 떼어내는 틀 — "01 FA PO" → (1, "FA PO")
STEP_HEAD_RE = re.compile(r"^(\d{1,2})\s*[.\-]?\s*(.+)$")
# 이 글자가 적혀 있으면 "아직 안 한 것" 으로 본다 (날짜가 아니므로)
NOT_DONE_TEXT = {"-", "n/a", "na", "tbd", "미정", "확인중", "확인 중"}


# ==========================================
#  셀 값을 글자로 바꾼다. 빈 칸은 빈 글자로.
# ==========================================
def _s(v):
    return "" if v is None else str(v).strip()


# ==========================================
#  셀 값이 날짜인지 본다. 날짜면 'YYYY-MM-DD', 아니면 None.
#  엑셀에 날짜가 2026.3.5 · 2026/3/5 · 26-3-5 처럼 제각각 들어오기 때문에
#  점과 빗금을 빼기표로 바꿔 한 가지 모양으로 맞춘 뒤 읽는다.
# ==========================================
def _as_date(v):
    """날짜면 'YYYY-MM-DD', 아니면 None."""
    if isinstance(v, (_dt.datetime, _dt.date)):
        d = v.date() if isinstance(v, _dt.datetime) else v
        return d.isoformat()
    t = _s(v)
    if not t:
        return None
    # ----------------------------------------------------------------------------
    #  2026.3.5 · 2026/3/5 → 2026-3-5 로 모양을 맞춘 뒤 숫자 셋을 떼어낸다
    # ----------------------------------------------------------------------------
    t2 = t.replace(".", "-").replace("/", "-")
    m = re.match(r"^(\d{2,4})-(\d{1,2})-(\d{1,2})", t2)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000                 # '26' 처럼 두 자리로 적힌 해는 2026 으로 본다
    try:
        return _dt.date(y, mo, d).isoformat()
    except Exception:
        return None


# ==========================================
#  표가 어떻게 생겼는지 먼저 알아낸다.
#  칸 위치를 코드에 박아 두면 사람이 줄 하나만 넣어도 전부 어긋난다.
#  그래서 머리글 글자를 찾아 '몇 행 몇 열인지' 를 그때그때 알아낸다.
# ==========================================
def find_layout(ws, max_scan=10):
    """(헤더행, 파트넘버열, [(단계번호, 단계명, 계획열, 실적열)], 코멘트열) 반환."""
    # ----------------------------------------------------------------------------
    #  1단계 — 위에서부터 10줄 안에서 "Part Number"(또는 파트넘버·모델)를 찾는다.
    #  그 칸이 있는 줄이 머리글 줄이다
    # ----------------------------------------------------------------------------
    head_row = None
    pn_col = None
    for r in range(1, min(ws.max_row, max_scan) + 1):
        for c in range(1, ws.max_column + 1):
            t = _s(ws.cell(row=r, column=c).value).lower()
            if t in ("part number", "partnumber", "파트넘버", "파트 넘버", "모델", "모델명"):
                head_row, pn_col = r, c
                break
        if head_row:
            break
    if head_row is None:
        return None, None, [], None

    # ----------------------------------------------------------------------------
    #  2단계 — 그 바로 아랫줄이 '계획 / 실적' 이 적힌 줄이다.
    #  단계 머리글은 두 칸을 합쳐 써서, 계획과 실적이 두 칸으로 나뉜다
    # ----------------------------------------------------------------------------
    sub_row = head_row + 1
    subs = {c: _s(ws.cell(row=sub_row, column=c).value).lower()
            for c in range(1, ws.max_column + 1)}

    # ----------------------------------------------------------------------------
    #  3단계 — 파트넘버 칸 오른쪽을 훑어 단계 13개와 코멘트 칸을 가려낸다
    # ----------------------------------------------------------------------------
    steps = []
    comment_col = None
    for c in range(pn_col + 1, ws.max_column + 1):
        label = _s(ws.cell(row=head_row, column=c).value)
        if not label:
            continue
        if label.lower().startswith("comment") or label in ("비고", "메모"):
            comment_col = c
            continue
        m = STEP_HEAD_RE.match(label)
        if not m:
            continue
        no, name = int(m.group(1)), m.group(2).strip()
        # 보통 왼쪽이 계획, 오른쪽이 실적이다. 다만 머리글이 실적 칸 위에
        # 붙어 있는 파일도 있어서, 아랫줄을 보고 한 칸 당겨 준다.
        plan_c, act_c = c, c + 1
        if subs.get(c, "").startswith("actual") or subs.get(c, "") in ("실적",):
            plan_c, act_c = c - 1, c
        steps.append((no, name, plan_c, act_c))
    steps.sort(key=lambda x: x[0])
    return head_row, pn_col, steps, comment_col


# ==========================================
#  바깥에서 부르는 입구. 엑셀을 받아 '파트넘버마다 13단계 진행 상태' 를 돌려준다.
#  
#    완료   = 실적 날짜가 적혀 있다
#    진행중 = 계획 날짜는 있는데 실적 자리에 '가공전' 같은 글자가 적혀 있다
#    빈칸   = 아직 아무것도 없다
# ==========================================
def parse_process_schedule(wb, sheet_name=None):
    ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else None
    # ----------------------------------------------------------------------------
    #  시트를 지정하지 않았으면, 단계가 5개 이상 보이는 시트를 찾아 쓴다.
    #  (한 파일에 다른 표가 여러 장 있을 수 있다)
    # ----------------------------------------------------------------------------
    layout = None
    if ws is not None:
        layout = find_layout(ws)
    else:
        for name in wb.sheetnames:
            cand = wb[name]
            lay = find_layout(cand)
            if lay[0] is not None and len(lay[2]) >= 5:
                ws, layout = cand, lay
                break
    if ws is None or layout is None or layout[0] is None or not layout[2]:
        return {"sheet": None, "steps": [], "rows": []}

    # ----------------------------------------------------------------------------
    #  머리글 두 줄 아래부터가 실제 자료다. 줄마다 13단계를 읽는다
    # ----------------------------------------------------------------------------
    head_row, pn_col, steps, comment_col = layout
    rows = []
    for r in range(head_row + 2, ws.max_row + 1):
        pn = _s(ws.cell(row=r, column=pn_col).value)
        if not pn or pn.lower() in ("total", "합계"):
            continue          # 빈 줄과 합계 줄은 모델이 아니다
        cells = []
        notes = []
        for no, name, pc, ac in steps:
            raw_p = ws.cell(row=r, column=pc).value if pc >= 1 else None
            raw_a = ws.cell(row=r, column=ac).value if ac >= 1 else None
            exp = _as_date(raw_p)
            act = _as_date(raw_a)
            status = ""
            if act:
                status = "완료"
            else:
                for raw in (raw_a, raw_p):
                    t = _s(raw)
                    if t and t.lower() not in NOT_DONE_TEXT and _as_date(raw) is None:
                        notes.append(f"{no:02d} {name}: {t}")
                        # 계획일이 잡혀 있을 때만 '진행중'으로 본다.
                        # 계획도 없는데 코멘트만 있다고 진행중으로 표시하지 않는다.
                        if exp:
                            status = "진행중"
                        break
            cells.append({
                "no": no,
                "name": name,
                "expected": exp or "",
                "actual": act or "",
                "status": status,
            })
        rows.append({
            "part_number": pn,
            "steps": cells,
            "comment": _s(ws.cell(row=r, column=comment_col).value) if comment_col else "",
            "notes": notes,
        })

    return {
        "sheet": ws.title,
        "steps": [{"no": n, "name": nm} for n, nm, _, _ in steps],
        "rows": rows,
    }
