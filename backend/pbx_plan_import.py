# ============================================================
#  'Plan and Actual' 형태의 출하계획 엑셀에서 주차별 계획/실적을 읽는다
# ============================================================

from __future__ import annotations

import collections
import re

import week_calendar as _wcal

WEEK_RE = re.compile(r"^W\s*(\d{1,2})$", re.I)
PLAN_WORDS = {"plan", "계획", "계획수량"}
ACT_WORDS = {"actual", "실적", "출하", "출하실적"}
STOP_WORDS = {"total", "grand total", "합계", "총계", "소계", "sum"}

#: 빈 양식에 얹어 둔 예시 줄. 지우지 않고 올려도 모델이 되면 안 된다.
#: 파트넘버 · 모델명 어느 쪽에 붙어 있어도 건너뛴다.
EXAMPLE_MARKS = ("(예시)", "（예시）", "[예시]", "예시)", "↑ 여기까지 예시")
MODEL_WORDS = {"model", "모델", "모델명", "품명", "part no.", "part no", "품번"}
# 주차 블록의 세 번째 칸 — 계획을 못 채운 이유
NOTE_WORDS = {"미달사유", "사유", "비고", "미달이유", "reason", "note"}

# 품번처럼 보이는 토막. '925-800083-394', '575-B68653-XXXX', '02-429411-00'
PN_RE = re.compile(r"\b([0-9A-Za-z]{2,3}-[0-9A-Za-z]{5,6}-[0-9A-Za-z]{2,6}[A-Za-z]?)\b")


def _s(v):
    return "" if v is None else str(v).strip()


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            return int(round(v))
        except Exception:
            return None
    t = str(v).strip().replace(",", "")
    if t in ("", "-", "N/A", "n/a"):
        return None
    try:
        return int(round(float(t)))
    except Exception:
        return None


# 비교용 정규화 — 영숫자만 남기고 대문자로.
def _norm(v):
    return re.sub(r"[^0-9A-Z]", "", _s(v).upper())


# ────────────────────────────────────────────────────────── 시트 읽기

# 'W##' 이 2개 이상 있는 행 → (행번호, {열: 주차번호})
def _find_week_header(ws, max_scan=400):
    best = None
    for r in range(1, min(ws.max_row, max_scan) + 1):
        hits = {}
        for c in range(1, ws.max_column + 1):
            m = WEEK_RE.match(_s(ws.cell(r, c).value))
            if m:
                n = int(m.group(1))
                if 1 <= n <= 53:
                    hits[c] = n
        if len(hits) >= 2 and (best is None or len(hits) > len(best[1])):
            best = (r, hits)
    return best


# 주차 머리글 아래 줄 → (행번호, {주차번호: (계획열, 실적열)}, {주차번호: 사유열})
def _find_sub_header(ws, week_row, week_cols):
    for r in (week_row + 1, week_row):
        pairs, notes = {}, {}
        for c, n in sorted(week_cols.items()):
            kind = {}
            # 병합 때문에 주차 라벨은 계획 열 위에만 있다. 그 열부터 오른쪽으로 3칸.
            for off in range(0, 3):
                t = _s(ws.cell(r, c + off).value).lower()
                if t in PLAN_WORDS and "plan" not in kind:
                    kind["plan"] = c + off
                elif t in ACT_WORDS and "actual" not in kind:
                    kind["actual"] = c + off
            if "plan" in kind:
                pairs[n] = (kind["plan"], kind.get("actual"))
        if len(pairs) >= 2:
            return r, pairs, notes
    # -----------------------------------------------------------
    # 마지막 수단: Plan/Actual 글자가 아예 없는 양식
    # -----------------------------------------------------------
    # 글자로 못 가렸으면 자리로 본다 — '주차 열이 계획, 바로 오른쪽이 실적'.
    # 양식이 전부 그 모양이라 이 가정이 맞는다. 틀리면 계획과 실적이
    # 뒤바뀌어 들어가므로, 글자로 찾는 위쪽 길이 먼저다.
    pairs = {}
    for plan_col, week_no in week_cols.items():
        actual_col = plan_col + 1
        pairs[week_no] = (plan_col, actual_col)
    return week_row + 1, pairs, {}


#: 라벨로 쓸 머리글. 앞쪽을 먼저 본다 — 모델명이 있으면 모델명을 쓴다.
NAME_WORDS = ("모델명", "모델", "model", "품명")
PN_WORDS = ("파트넘버", "파트번호", "품번", "part no.", "part no", "partno")


#: 머리글 앞에 붙는 표. 양식이 '✎ 파트넘버' 처럼 내보내므로 떼고 본다.
#: 사람이 '* 파트넘버' 처럼 제멋대로 붙여 놔도 같이 걸린다.
_HEAD_MARKS = "✎=＝*※·•-–— \t"


# 머리글 글자 → 비교용 글자. 앞뒤의 표와 공백을 떼고 소문자로.
def _head_key(v) -> str:
    t = _s(v).strip().strip(_HEAD_MARKS).strip()
    return t.lower()


# 모델 열을 머리글로 찾는다
def _find_model_col(ws, sub_row, first_week_col):
    # -----------------------------------------------------------
    # 1. 머리글을 어느 줄에서 찾을 것인가
    # -----------------------------------------------------------
    # sub_row(계획/실적이 적힌 줄) 한 줄만 보면 안 된다
    first_head_row = max(1, sub_row - 3)
    rows = []
    for r in range(first_head_row, sub_row + 1):
        rows.append(r)

    # words 에 들어 있는 머리글이 적힌 열 번호.
    def _hit(words):
        for c in range(1, first_week_col):
            for r in rows:
                # 앞에 붙은 표(✎ · * 같은 것)와 공백을 떼고 소문자로
                t = _head_key(ws.cell(r, c).value)
                if t in words:
                    return c
                # '파트 넘버' 처럼 사이에 띄어쓰기를 넣은 경우도 같이 본다
                if t.replace(" ", "") in words:
                    return c
        return None

    # 파트넘버가 먼저다 — 이 시스템에서 모델을 가르는 열쇠이기 때문이다
    pn = _hit(PN_WORDS)      # 파트넘버 열 (없으면 None)
    nm = _hit(NAME_WORDS)    # 모델명 열   (없으면 None)
    # -----------------------------------------------------------
    # 3. 각 열에 값이 실제로 몇 줄 들어 있는지 센다
    # -----------------------------------------------------------
    #    머리글이 있다고 값이 있는 건 아니다. 열은 있는데 칸이 다 비어
    #    있으면 그 열을 골라 봐야 모든 줄의 라벨이 빈 글자가 된다.
    n_pn = 0
    if pn:
        n_pn = _count_values(ws, sub_row, pn)
    n_nm = 0
    if nm:
        n_nm = _count_values(ws, sub_row, nm)
    # -----------------------------------------------------------
    # 4. 더 많이 차 있는 열을 쓴다. 같으면 파트넘버
    # -----------------------------------------------------------
    #    파트넘버가 모델을 가르는 열쇠라 같은 수면 파트넘버를 쓴다.
    if n_pn or n_nm:
        if n_pn >= n_nm:
            return pn
        return nm
    # -----------------------------------------------------------
    # 5. 둘 다 비어 있으면
    # -----------------------------------------------------------
    #    머리글이라도 있는 열을 쓰고(파트넘버 우선), 그것도 없으면
    #    '글자가 제일 많은 열' 로 떨어진다 (남의 양식용 마지막 수단).
    if pn:
        return pn
    if nm:
        return nm
    return _fallback_model_col(ws, sub_row, first_week_col)


# 그 열에 실제로 적힌 줄이 몇 줄인가.
def _count_values(ws, sub_row, col):
    # -----------------------------------------------------------
    # 1. 어디부터 어디까지 볼 것인가
    # -----------------------------------------------------------
    # 머리글 바로 아래 줄부터 본다. 끝은 둘 중 먼저 오는 쪽이다
    first_row = sub_row + 1
    last_row = min(ws.max_row, sub_row + 400)

    n = 0                                   # 지금까지 센 줄 수
    for r in range(first_row, last_row + 1):
        # -----------------------------------------------------------
        # 2. 이 줄의 왼쪽을 통째로 한 문장으로 잇는다
        # -----------------------------------------------------------
        #    1열부터 지금 보는 열까지의 칸을 모아 한 줄로 만든다.
        #    '합계'가 이 열이 아니라 왼쪽 1열에 적혀 있을 수 있어서다.
        #      예) 1열 '합계' · 2열 빈칸 · 3열 '120'  →  "합계  120"
        left_cells = []
        for c in range(1, col + 1):
            left_cells.append(_s(ws.cell(r, c).value))
        line = " ".join(left_cells).lower()
        # -----------------------------------------------------------
        # 3. 표가 끝나는 줄인가
        # -----------------------------------------------------------
        #    STOP_WORDS('합계' · '소계' 같은 말)가 하나라도 보이면
        #    표가 거기서 끝난 것으로 보고 멈춘다.
        hit_stop = False
        for word in STOP_WORDS:
            if word in line:
                hit_stop = True
                break
        if hit_stop:
            break
        # -----------------------------------------------------------
        # 4. 이 줄의 그 칸에 진짜 값이 있는가
        # -----------------------------------------------------------
        v = _s(ws.cell(r, col).value)
        if not v:
            continue              # 빈 칸 — 안 센다
        if _is_example(v):
            continue              # '(예시)' 로 적힌 줄 — 안 센다
        n += 1                    # 여기까지 왔으면 진짜 값이다

    return n


# 머리글이 아예 없는 남의 파일용 — 글자가 제일 많은 열.
def _fallback_model_col(ws, sub_row, first_week_col):
    # 머리글로 못 찾았을 때만 여기 온다. 왼쪽 열들을 하나씩 보면서
    # '숫자가 아닌 글자'가 가장 많이 들어 있는 열을 모델 열로 본다.
    # 모델명·파트넘버는 글자이고, 수량·단가는 숫자이기 때문이다.
    best = None       # 지금까지 가장 좋은 열
    best_n = 0        # 그 열에 들어 있던 글자 칸 수

    for c in range(1, first_week_col):
        # -----------------------------------------------------------
        # 이 열에 글자 칸이 몇 개인가 (머리글 아래 40줄만 본다)
        # -----------------------------------------------------------
        last_row = min(ws.max_row, sub_row + 40)
        n = 0
        for r in range(sub_row + 1, last_row + 1):
            cell = ws.cell(r, c).value
            if not _s(cell):
                continue              # 빈 칸
            if _num(cell) is not None:
                continue              # 숫자 칸 — 모델명이 아니다
            n += 1

        if n > best_n:
            best = c
            best_n = n

    return best


# 시트 하나 → {'month','weeks',[rows]} 또는 None.
def parse_sheet(ws, month=None):
    hdr = _find_week_header(ws)
    if not hdr:
        return None
    week_row, week_cols = hdr
    sub_row, pairs, notes = _find_sub_header(ws, week_row, week_cols)
    if not pairs:
        return None
    model_col = _find_model_col(ws, sub_row, min(week_cols))
    if not model_col:
        return None
    # -----------------------------------------------------------
    # 달을 지정해 부른 경우 (한 표가 두 달에 걸쳐 있을 때)
    # -----------------------------------------------------------
    # 예) 한 시트에 W40(9월)과 W41~W44(10월)가 같이 있다. 10월을 달라고
    #     부르면 W41~W44 만 떼어 읽는다. 안 그러면 9월이 통째로 버려진다.
    if month:
        # -----------------------------------------------------------
        # 1. 그 달이 가진 주차 목록 (예: 10월 → W41 W42 W43 W44)
        # -----------------------------------------------------------
        try:
            own_m = set(_wcal.get_month_weeks(month))
        except Exception:
            own_m = set()
        if not own_m:
            return None              # 달력을 못 읽었다
        # -----------------------------------------------------------
        # 2. 이 표에 그 달 주차가 하나라도 있는가
        # -----------------------------------------------------------
        has_any = False
        for n in pairs:
            if f"W{n:02d}" in own_m:
                has_any = True
                break
        if not has_any:
            return None              # 이 시트는 그 달과 무관하다
        # -----------------------------------------------------------
        # 3. 그 달 주차만 남긴다
        # -----------------------------------------------------------
        only_this_month = {}
        for n, v in pairs.items():
            if f"W{n:02d}" in own_m:
                only_this_month[n] = v

        return _rows_of(ws, sub_row, model_col, month, only_this_month, notes)

    # 이 시트가 어느 달 자료인가.
    #
    # 1) 시트 이름이 'YYYY-MM' 이면 그걸 쓴다. OneView 가 내려주는 양식이
    #    그렇게 적는다. 주차 번호만 보면 연도를 알 수 없어서, 2027-03 처럼
    #    해가 넘어간 달은 올해(2026) W09 로 읽혀 통째로 버려졌다.
    #    이름을 그냥 믿지는 않는다 — 그 달이 실제로 가진 주차인지 맞춰 본다.
    # 2) 아니면 예전처럼 주차 번호로 투표한다 (남이 만든 파일들).
    month = ""
    m_name = re.match(r"^\s*(\d{4})-(\d{1,2})\s*$", _s(ws.title))
    if m_name:
        cand = "%04d-%02d" % (int(m_name.group(1)), int(m_name.group(2)))
        try:
            own_c = set(_wcal.get_month_weeks(cand))
        except Exception:
            own_c = set()
        # 이름이 말하는 달이 실제로 이 표의 주차를 갖고 있는지 맞춰 본다.
        # 이름만 믿으면, 이름이 틀린 파일에서 엉뚱한 달로 들어간다.
        if own_c:
            for n in pairs:
                if f"W{n:02d}" in own_c:
                    month = cand
                    break
    if not month:
        votes = collections.Counter()
        for n in pairs:
            mo = _wcal.month_of_week(f"W{n:02d}")
            if mo:
                votes[mo] += 1
        if not votes:
            return None
        month = votes.most_common(1)[0][0]
    # -----------------------------------------------------------
    # 그 달이 실제로 가진 주차만 남긴다
    # -----------------------------------------------------------
    #    투표로 정한 달이라도, 표에는 옆 달 주차가 섞여 있을 수 있다.
    #    남겨 두면 10월 자료에 9월 숫자가 섞여 들어간다.
    own = set(_wcal.get_month_weeks(month))
    kept = {}
    for n, v in pairs.items():
        if f"W{n:02d}" in own:
            kept[n] = v
    pairs = kept
    if not pairs:
        return None
    return _rows_of(ws, sub_row, model_col, month, pairs, notes)


# ============================================================
#  예시 줄인가 — 빈 양식에 얹어 둔 본보기
# ============================================================
def _is_example(label) -> bool:
    t = str(label or "").strip()

    # EXAMPLE_MARKS = ('(예시)', '[예시]', '↑ 여기까지 예시' …)
    # 표가 맨 앞에 붙기도 하고(= '(예시) 챔버'), 중간에 들어가기도 한다
    # (= '챔버 (예시)'). 두 경우를 다 본다.
    for mark in EXAMPLE_MARKS:
        if t.startswith(mark):
            return True
        if mark in t:
            return True
    return False


# 머리글을 다 찾은 뒤 실제 줄을 읽는다
def _rows_of(ws, sub_row, model_col, month, pairs, notes=None):
    notes = notes or {}
    rows = []
    for r in range(sub_row + 1, ws.max_row + 1):
        # -----------------------------------------------------------
        # 1. 이 줄의 라벨 (모델명 또는 파트넘버)
        # -----------------------------------------------------------
        #    칸 안에서 줄바꿈한 경우가 있어 공백으로 바꿔 한 줄로 만든다
        label = _s(ws.cell(r, model_col).value).replace("\n", " ").strip()
        # -----------------------------------------------------------
        # 2. 표가 끝났는지 먼저 본다
        # -----------------------------------------------------------
        #    라벨 칸이 비어 있어도 왼쪽 어딘가에 '합계'가 있으면 거기서
        #    표가 끝난 것이다. 양식은 '합계'를 1열에 적는다.
        left_cells = []
        for c in range(1, model_col + 1):
            left_cells.append(_s(ws.cell(r, c).value))
        line = " ".join(left_cells).lower()
        hit_stop = False
        for word in STOP_WORDS:
            if word in line:
                hit_stop = True
                break
        if hit_stop:
            break
        # -----------------------------------------------------------
        # 3. 읽을 줄이 아닌 경우는 건너뛴다
        # -----------------------------------------------------------
        if not label:
            continue              # 라벨이 없는 빈 줄
        if _is_example(label):
            continue              # 양식에 얹어 둔 예시 줄
        weeks, any_val = {}, False
        for n, (pc, ac) in sorted(pairs.items()):
            p = _num(ws.cell(r, pc).value)
            a = _num(ws.cell(r, ac).value) if ac else None
            weeks[f"W{n:02d}"] = {"plan": p or 0, "actual": a or 0}
            if p is not None or a is not None:
                any_val = True
        if not any_val:
            continue
        rows.append({"row": r, "label": label, "weeks": weeks})

    return {
        "sheet": ws.title,
        "month": month,
        "weeks": [f"W{n:02d}" for n in sorted(pairs)],
        "rows": rows,
        "week_notes": _week_notes(ws, sub_row, model_col, pairs),
    }


# ============================================================
#  프로젝트 현황 — 프로젝트째 멈췄는가
# ============================================================
PROJ_LABEL = "프로젝트 현황"
#: 양식에서 고르는 말 → 서버가 쓰는 말.
#: 2026-10-22 — 고르는 말을 '진행 중 · 보류 중 · 드롭 예정' 으로 바꿨다.
#: 띄어쓰기를 떼고 보니 옛 말('진행' · '보류')도 그대로 걸린다.
PROJ_STATE_OUT = {
    "진행중": "", "진행": "", "해제": "", "없음": "",
    "보류중": "보류", "보류": "보류", "홀딩": "보류", "홀드": "보류",
    "드롭예정": "드롭예정", "드롭": "드롭예정",
}
PROJ_STATES = tuple(PROJ_STATE_OUT)


# 양식 아래의 '프로젝트 현황' 두 줄 → {'hold','note'} 또는 None.
def read_project_status(ws):
    for r in range(1, min(ws.max_row, 1000) + 1):
        if _s(ws.cell(r, 1).value) != PROJ_LABEL:
            continue
        raw = _s(ws.cell(r + 1, 2).value).replace(" ", "")
        note = _s(ws.cell(r + 1, 3).value)
        # 빈 칸과 '진행' 은 다르다. 빈 칸은 '안 건드렸다' 이고
        # '진행' 은 '풀어 달라' 다. 섞으면 상태 칸을 안 본 사람이 올릴
        # 때마다 멈춰 세운 프로젝트가 조용히 풀린다.
        blank = raw == ""
        if raw in PROJ_STATE_OUT:
            hold = PROJ_STATE_OUT[raw]
        else:
            hold = ""              # 알 수 없는 글자는 안 고른 것으로 본다
            blank = True
        return {"hold": hold, "note": note, "blank": blank}
    return None


# '미달 사유' 줄 → {'W41': '자재 지연', ...}
def _week_notes(ws, sub_row, model_col, pairs):
    out = {}

    # 라벨('미달 사유')이 1열에 있을 수도, 2~4열에 있을 수도 있다.
    # 그래서 왼쪽 네 칸까지는 무조건 같이 본다.
    wide = max(model_col, 4)

    for r in range(sub_row + 1, ws.max_row + 1):
        # -----------------------------------------------------------
        # 1. 이 줄이 '미달 사유' 줄인가
        # -----------------------------------------------------------
        # 왼쪽 칸들을 붙여 한 덩어리로 만들고, 공백을 전부 떼고 NOTE_WORDS('미달사유' · '사유' · '비고' …)와 맞춰 본다
        head_cells = []
        for c in range(1, wide + 1):
            head_cells.append(_s(ws.cell(r, c).value))
        head = "".join(head_cells)
        head_key = re.sub(r"\s+", "", head).lower()
        if head_key not in NOTE_WORDS:
            continue
        # -----------------------------------------------------------
        # 2. 찾았으면 주차마다 그 칸의 글을 가져온다
        # -----------------------------------------------------------
        #    사유는 계획 칸(pc) 자리에 적는다 — 실적 칸은 비워 둔다.
        for n, (pc, _ac) in pairs.items():
            txt = _s(ws.cell(r, pc).value).replace("\n", " ").strip()
            if txt:
                out[f"W{n:02d}"] = txt

        # 사유 줄은 하나뿐이다. 찾았으면 더 내려갈 이유가 없다.
        break

    return out


# 시트 하나가 걸친 달을 **전부** → [parsed, ...] (이른 달부터).
def parse_sheet_all(ws):
    hdr = _find_week_header(ws)
    if not hdr:
        return []
    week_row, week_cols = hdr
    sub_row, pairs, _notes = _find_sub_header(ws, week_row, week_cols)
    if not pairs:
        return []
    months = []
    for n in pairs:
        mo = _wcal.month_of_week(f"W{n:02d}")
        if mo and mo not in months:
            months.append(mo)
    out = []
    for mo in sorted(months):
        got = parse_sheet(ws, month=mo)
        if got and got["rows"]:
            out.append(got)
    return out


# 한 시트가 한 해를 통째로 담고 있으면 그 달들 → ['2026-01', ...]
def sheet_months_of(ws):
    hdr = _find_week_header(ws)
    if not hdr:
        return []
    week_row, week_cols = hdr
    _sub_row, pairs, _notes = _find_sub_header(ws, week_row, week_cols)
    if not pairs:
        return []
    m = re.match(r"^\s*(\d{4})-(\d{1,2})\s*$", _s(ws.title))
    if not m:
        return []
    year, mm = int(m.group(1)), int(m.group(2))
    if not (1 <= mm <= 12):
        return []
    # ── 1. 시트 이름이 말하는 달이 가진 주차
    own = set(_wcal.get_month_weeks("%04d-%02d" % (year, mm)) or [])

    # ── 2. 이 표에 실제로 들어 있는 주차
    have = set()
    for n in pairs:
        have.add(f"W{n:02d}")

    # ── 3. 표의 주차가 전부 그 달 안에 있으면 볼 것 없다
    #    (have <= own 은 '표의 주차가 그 달 주차에 모두 들어간다'는 뜻)
    if not own or have <= own:
        return []

    # ── 4. 걸쳐 있다 — 그 해 열두 달 중 이 표와 겹치는 달을 모은다
    #    예) 표에 W40·W41~44 가 있으면 9월과 10월 둘 다 나온다
    out = []
    for i in range(1, 13):
        ym = "%04d-%02d" % (year, i)
        weeks_of_month = set(_wcal.get_month_weeks(ym) or [])
        if weeks_of_month & have:      # 겹치는 주차가 하나라도 있으면
            out.append(ym)
    return out


#: 우리 양식이 곁들여 내보내는 장. 읽지 않는다.
#: 'PPT 붙이기' 장은 전부 수식이라 적는 장과 똑같은 숫자를 들고 있다.
#: 그대로 읽으면 같은 달이 두 번 들어와 실적이 두 배로 보인다.
REPORT_SHEETS = ("PPT 붙이기", "PPT 붙이는 표", "작성 안내")


# 보기 · 복사용 장인가 — 적는 장이 아니다
def _is_report_sheet(ws) -> bool:
    t = str(getattr(ws, "title", "") or "").strip()
    if t in REPORT_SHEETS:
        return True
    # 이름을 바꿔 놔도 첫 칸의 표시로 알아본다
    try:
        head = str(ws.cell(1, 1).value or "")
    except Exception:
        return False
    return "PPT 붙이는 표" in head


# 시트 하나에서 읽어 낸 달들 → [parsed, ...]
def _sheet_parts(ws):
    if _is_report_sheet(ws):
        return []
    out = []
    for mo in (sheet_months_of(ws) or []):
        try:
            got = parse_sheet(ws, month=mo)
        except Exception:
            got = None
        if got and got["rows"]:
            out.append(got)
    if out:
        return out
    try:
        got = parse_sheet(ws)
    except Exception:
        got = None
    return [got] if (got and got["rows"]) else []


# 워크북에서 쓸 만한 시트를 모두 읽어 월별로 돌려준다
def parse(wb, month=None):
    found = []
    for ws in wb.worksheets:
        found.extend(_sheet_parts(ws))
    if not found:
        return None
    if month:
        # 하바처럼 주차별 스냅샷이 34장 들어 있으면 같은 달 시트가 여럿이다
        cands = []
        for i, g in enumerate(found):
            if g["month"] == month:
                cands.append((i, g))
        if not cands:
            return None

        # ── 2. 줄이 많은 쪽, 같으면 뒤쪽(최신) 시트를 쓴다
        #    key 의 (줄 수, 시트 순서) 로 오름차순 정렬하고 맨 뒤를 집는다.
        #    줄이 많은 시트가 더 채워진 스냅샷이고, 줄 수가 같으면 나중에
        #    만든 시트가 최신이다.
        cands.sort(key=lambda x: (len(x[1]["rows"]), x[0]))
        newest = cands[-1]
        return newest[1]

    # ── 달을 안 정했으면: 달이 늦은 쪽, 같으면 줄이 많은 쪽
    found.sort(key=lambda g: (g["month"], len(g["rows"])))
    return found[-1]


# 어떤 달 자료가 들어 있는지만 훑는다
def sheet_months(wb):
    out = []
    for ws in wb.worksheets:
        for got in _sheet_parts(ws):
            out.append({"sheet": got["sheet"], "month": got["month"],
                        "weeks": got["weeks"], "rows": len(got["rows"])})
    return out


# ────────────────────────────────────────────────────────── 모델 맞추기

# 등록된 모델과 엑셀 라벨을 맞춘다
class Matcher:

    def __init__(self, models):
        self.by_id = {}
        self.by_name = collections.defaultdict(list)
        self.prefix = []          # ('575B68653', model) — 뒤가 X 로 채워진 계열 품번
        for m in models:
            raw_id, raw_name = _s(m.get("id")), _s(m.get("name"))
            # 파트넘버 칸. '파트넘버로 찾는다' 고 적어 두고 정작 이 칸을
            # 안 보고 있었다 — id·모델명만 봤다.
            raw_pn = _s(m.get("part_number"))
            # 별칭 — 같은 물건을 거래처마다 다른 품번으로 부른다.
            # 복사본 엑셀의 853-800575-009 가 우리 714-025898-009 다.
            alts = []
            for a in (m.get("aliases") or []):
                a = _s(a)
                if a:
                    alts.append(a)

            # ── 이 모델을 가리킬 수 있는 글자를 전부 모아 한 덩어리로
            #    색인을 넓게 깔아 두는 이유: 엑셀마다 같은 물건을 다르게
            #    적는다. 이름으로 적기도 하고 품번으로 적기도 한다.
            blob = " ".join([raw_id, raw_name, raw_pn] + alts)

            # ── 1. 통째로 쓰는 열쇠 (id · 파트넘버 · 별칭)
            for one in [raw_id, raw_pn] + alts:
                self._add_id(_norm(one), m)

            # ── 2. 글자 덩어리 안에서 '품번처럼 생긴 토막'을 뽑아 열쇠로
            #    예) 'AETHER GDX 925-800083-394' → '925-800083-394'
            for pn in PN_RE.findall(blob):
                self._add_id(_norm(pn), m)

            # ── 3. 6~9자리 숫자도 열쇠로 (하이픈 없이 적는 엑셀이 있다)
            for d in re.findall(r"\b\d{6,9}\b", blob):
                self._add_id(_norm(d), m)

            # ── 4. 모델명은 따로 모아 둔다 (품번이 안 맞을 때 쓰는 길)
            n = _norm(raw_name)
            if n:
                self.by_name[n].append(m)
        self.prefix.sort(key=lambda t: -len(t[0]))

    def _add_id(self, key, m):
        if not key:
            return
        self.by_id.setdefault(key, m)
        if key.endswith("X") and len(key.rstrip("X")) >= 8:
            self.prefix.append((key.rstrip("X"), m))

    def _by_id(self, key):
        if not key:
            return None, None
        if key in self.by_id:
            return self.by_id[key], "품번"
        for p, m in self.prefix:
            if key.startswith(p):
                return m, "품번(계열)"
        # -----------------------------------------------------------
        # 3. X 자리를 아무 글자로 쳐 주고 맞춰 본다
        # -----------------------------------------------------------
        #    계열 품번을 'KIYO GX 575-B68653-XXXX' 처럼 끝을 X 로 적어 두는
        #    경우가 있다. 그 X 자리는 무엇이 와도 같은 물건으로 본다.
        #    글자 수가 같아야 자리끼리 맞출 수 있으니 길이부터 본다.
        for rk, m in self.by_id.items():
            if len(key) != len(rk):
                continue
            same = True
            for a, b in zip(key, rk):
                if a == b:
                    continue          # 같은 글자
                if a == "X" or b == "X":
                    continue          # 한쪽이 X — 아무 글자나 된다
                same = False
                break
            if same:
                return m, "품번(X)"

        return None, None

    # → (모델, 어떻게 찾았는지) · 못 찾으면 (None, 사유)
    def match(self, text, group=None):
        t = _s(text).replace("\n", " ")
        if not t:
            return None, "빈칸"
        # -----------------------------------------------------------
        # 1. 품번으로 먼저 찾는다
        # -----------------------------------------------------------
        #    라벨 안에 품번처럼 생긴 토막이 있으면 그걸로 맞춰 본다.
        #    품번이 이름보다 믿을 만하다 — 이름은 같은 게 여럿 있다.
        for pn in PN_RE.findall(t):
            m, how = self._by_id(_norm(pn))
            if m:
                return m, how
        # -----------------------------------------------------------
        # 2. 품번으로 못 찾았으면 이름으로
        # -----------------------------------------------------------
        #    라벨에서 품번·괄호·하이픈·숫자를 지워 '이름만' 남긴다.
        #      예) 'AETHER GDX 925-800083-394 (2차)' → 'AETHER GDX'
        rest = PN_RE.sub(" ", t)              # 품번 토막 제거
        rest = re.sub(r"[()/\-]", " ", rest)  # 괄호 · 빗금 · 하이픈 제거
        rest = re.sub(r"\b\d+\b", " ", rest) # 남은 숫자 제거
        cands = self.by_name.get(_norm(rest), [])
        # -----------------------------------------------------------
        # 3. 이름이 같은 모델이 여럿이면 같은 구분(양산/개발)으로 좁힌다
        # -----------------------------------------------------------
        #    좁혔는데 하나도 안 남으면 좁히기 전 목록을 그대로 쓴다.
        #    구분이 안 적힌 모델까지 버리면 멀쩡한 줄을 놓친다.
        if group:
            same_group = []
            for c in cands:
                if c.get("group") == group:
                    same_group.append(c)
            if same_group:
                cands = same_group
        # -----------------------------------------------------------
        # 4. 결과 판정
        # -----------------------------------------------------------
        if len(cands) == 1:
            return cands[0], "이름"
        if len(cands) > 1:
            # 둘 이상이면 고르지 않는다. 엉뚱한 모델에 숫자를 넣는 것보다
            # '못 찾았다' 고 말하고 사람이 보게 하는 편이 낫다.
            return None, f"이름 중복 {len(cands)}종"
        # -----------------------------------------------------------
        # 5. 마지막으로 라벨 전체를 열쇠로 한 번 더
        # -----------------------------------------------------------
        m, how = self._by_id(_norm(t))
        if m:
            return m, how
        return None, "등록 안 됨"
