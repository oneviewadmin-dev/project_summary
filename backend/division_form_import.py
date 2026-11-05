# -*- coding: utf-8 -*-
# ============================================================
#  사업부 양식(품목정보 · 이슈사항)을 읽는다
# ============================================================
from __future__ import annotations

import re
import unicodedata

import week_calendar as _wcal

# 품목정보 시트를 찾는 말
ITEM_SHEET_WORDS = ("품목정보", "품목 정보")
ISSUE_SHEET_WORDS = ("이슈사항", "이슈 사항")
TERM_SHEET_WORDS = ("용어",)
DAILY_SHEET_WORDS = ("일일 실적", "일일실적", "공정별 일일")

# 머리글 글자 → 우리가 쓰는 이름
# ============================================================
#  머리글 말
# ============================================================
OWNER_WORDS = ("프로젝트", "고객사", "project", "customer")
PN_WORDS = ("파트넘버", "파트번호", "품번", "part no", "partno",
            "p/n", "pn", "part number")
NAME_WORDS = ("모델명", "품목", "모델", "품명", "model name", "model", "item")
# 'FA / HVM' 은 양산·개발을 가르는 칸이다 (구분).
GROUP_WORDS = ("구분", "fa / hvm", "fa/hvm", "fahvm")
PO_WORDS = ("po수량", "po 수량", "po")
# 실적(내보낸 수량) 열. 사업부마다 부르는 말이 달라서 다 받는다 —
# ESS 양식은 '출하수량', 반도체 양식은 '실적수량' 이다. 한쪽만 받으면
# 다른 쪽 양식에서 이 칸이 통째로 0 으로 들어간다.
SHIP_WORDS = ("실적수량", "실적 수량", "출하실적", "출하 실적",
              "출하수량", "출하 수량", "출하완료", "출하 완료")
# 반도체 양식에만 있는 세 칸.
# 다른 사업부 양식에는 없다 — 없으면 그냥 안 읽는다.
YEAR_WORDS = ("연간수량", "연간 수량", "eau")
CLASS_WORDS = ("분류",)          # '분류 (HVM/RPM)'
NOTE_WORDS = ("비고",)
PRICE_WORDS = ("판가", "unit price")
MATERIAL_WORDS = ("재료비", "material cost")

# '예시)' 가 적힌 줄은 양식에 본보기로 얹어 둔 줄이다
EXAMPLE_MARKS = ("예시", "example")

# 주차 머리글 (W41 · w41 · W 41)
WEEK_RE = re.compile(r"^w\s*(\d{1,2})$", re.I)
# 주차를 'W41' 이 아니라 그냥 '41' 로 적어 오는 양식이 있다 (블룸 2026-10).
# 숫자만으로는 판가·수량과 구분이 안 되므로, 아래 _find_weeks 에서
# **그 아래 칸에 '계획' 이 적혀 있을 때만** 주차로 친다.
WEEK_BARE_RE = re.compile(r"^(\d{1,2})$")

PLAN_WORDS = ("계획", "plan")
ACTUAL_WORDS = ("실적", "actual")
CURRENCY_WORDS = ("통화", "currency")


# ============================================================
#  어디까지 읽나
# ============================================================
# 시트 끝까지 훑으면 품목 표 오른쪽에 적어 둔 메모가 머리글로 잡힌다.
# 블룸 양식이 그랬다. 사업부마다 멈출 자리는 division_columns 가 안다.
_MAX_COL = None

# ============================================================
#  납기 칸을 읽는 사업부인가
# ============================================================
#    다른 사업부 양식에 '납기' 머리글이 있어도 지금까지처럼 안 읽는다.
_DUE_ON = False
DUE_WORDS = (("due_date", ("요청납기", "납기일", "납기")),
             ("due_revised", ("출하변경", "변경일", "변경납기")),
             ("made_date", ("제작완료", "완료일")))


# 이 시트에서 훑을 마지막 열. 설정이 있으면 그보다 더 가지 않는다
def _lastc(ws) -> int:
    n = ws.max_column
    return min(n, _MAX_COL) if _MAX_COL else n


# 파트넘버 칸 → 한 글자.
def _pn(v) -> str:
    t = _s(v)
    if not t:
        return ""
    parts = [p.strip() for p in re.split(r"[\r\n]+", t) if p.strip()]
    return " / ".join(parts)


# 셀 값 → 줄바꿈 없는 한 줄.
def _one_line(v) -> str:
    t = _s(v)
    if not t:
        return ""
    return re.sub(r"\s+", " ", t)


# 셀 값 → 다듬은 글자. None 은 빈 글자.
def _s(v) -> str:
    if v is None:
        return ""
    return unicodedata.normalize("NFC", str(v)).strip()


# 머리글 비교용 — 공백과 줄바꿈을 떼고 소문자로.
def _key(v) -> str:
    t = _s(v).lower()
    t = re.sub(r"[\s ]+", "", t)
    return t


# 다듬은 글자 안에 words 중 하나라도 들어 있는가.
def _has_word(text: str, words) -> bool:
    for w in words:
        if _key(w) in text:
            return True
    return False


# 숫자 칸 → 숫자. 못 읽으면 None.
def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    t = _s(v).replace(",", "")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


# 수량 칸 → 정수. 못 읽으면 0.
def _int(v) -> int:
    n = _num(v)
    if n is None:
        return 0
    return int(round(n))


# 수량 칸 → 정수, **빈 칸은 None**.
def _int_or_none(v):
    n = _num(v)
    return None if n is None else int(round(n))


# ============================================================
#  시트 찾기
# ============================================================
def find_sheet(wb, words):
    for ws in wb.worksheets:
        title = _key(ws.title)
        for w in words:
            if _key(w) in title:
                return ws
    return None


# ============================================================
#  품목정보 — 머리글 찾기
# ============================================================
def _find_header_row(ws, limit=40):
    last = min(ws.max_row, limit)
    loose = None
    for r in range(1, last + 1):
        hit = False
        has_name = False
        for c in range(1, min(_lastc(ws), 14) + 1):
            t = _key(ws.cell(r, c).value)
            if not t:
                continue
            if t in ("no.", "no", "번호"):
                hit = True
            elif _has_word(t, OWNER_WORDS) or _has_word(t, PN_WORDS):
                has_name = True
        if hit and has_name:
            return r
        if hit and loose is None:
            loose = r
    # 이름 칸이 같이 없는 'No.' 줄뿐이면 그거라도 쓴다 — 옛 양식 중에
    # 머리글이 'No.' 하나뿐인 장이 있을 수 있다.
    return loose


# 머리글 줄에서 각 칸이 무엇인지 가린다 → {이름: 열번호}
def _map_columns(ws, head_row):
    cols = {}
    # '구분' 이 붙은 칸은 여럿일 수 있다 (아리스타: 구분 1 · 구분 2).
    # 다 모아 두고 아래에서 **값을 보고** 가린다.
    group_cands = []
    for c in range(1, _lastc(ws) + 1):
        t = _key(ws.cell(head_row, c).value)
        if not t:
            continue

        # 납기 칸 — 다른 말보다 먼저 본다. '출하 변경일 (고객사 승인)' 에는
        # '고객사' 가, '제작 완료일' 에는 '완료' 가 들어 있다.
        if _DUE_ON:
            _hit = None
            for _k, _ws in DUE_WORDS:
                if _k not in cols and any(w in t for w in _ws):
                    _hit = _k
                    break
            if _hit:
                cols[_hit] = c
                continue

        # 국내 / 해외 — '구분' 이라고 쓰면 양산/개발 칸과 겹친다
        # 자동차는 '고객 묶음'
        if "region" not in cols and ("국내" in t or "해외" in t or "묶음" in t
                                     or t in ("지역", "region")):
            cols["region"] = c
            continue

        # 순서가 중요하다. '파트넘버' 가 '품목' 보다 먼저 걸려야
        # 고객사별 양식(품목 → 파트넘버)에서 두 칸이 뒤바뀌지 않는다.
        if "owner" not in cols and _has_word(t, OWNER_WORDS):
            cols["owner"] = c
        elif "part_number" not in cols and _has_word(t, PN_WORDS):
            cols["part_number"] = c
        elif "name" not in cols and _has_word(t, NAME_WORDS):
            cols["name"] = c
        elif _has_word(t, GROUP_WORDS):
            group_cands.append(c)
        elif "ship_head" not in cols and _has_word(t, SHIP_WORDS):
            cols["ship_head"] = c
        elif "po_head" not in cols and _has_word(t, PO_WORDS):
            cols["po_head"] = c
        elif "price_head" not in cols and _has_word(t, PRICE_WORDS):
            cols["price_head"] = c
        elif "material_head" not in cols and _has_word(t, MATERIAL_WORDS):
            cols["material_head"] = c
        elif "year_qty" not in cols and _has_word(t, YEAR_WORDS):
            cols["year_qty"] = c
        elif "dev_type" not in cols and _has_word(t, CLASS_WORDS):
            cols["dev_type"] = c
        elif "note" not in cols and _has_word(t, NOTE_WORDS):
            cols["note"] = c
    # -----------------------------------------------------------
    # '구분' 이 둘인 양식
    # -----------------------------------------------------------
    # 아리스타 양식에는 '구분 1(시트메탈/렉/샷시/캐스팅/하드웨어)' 과 '구분 2(양산/개발)' 가 나란히 있다
    if group_cands:
        def _looks_group(col):
            hit = 0
            for r in range(head_row + 1, min(head_row + 40, ws.max_row) + 1):
                if _key(ws.cell(r, col).value) in ("양산", "개발"):
                    hit += 1
            return hit

        best = sorted(group_cands, key=lambda c: (-_looks_group(c), c))[0]
        if _looks_group(best) <= 0:
            best = group_cands[0]       # 값으로 못 가리면 왼쪽부터 (옛 동작)
        cols["group"] = best
        rest = [c for c in group_cands if c != best]
        # 양식에 '분류' 칸이 따로 있으면 그쪽이 먼저다 (반도체 양식)
        if "dev_type" not in cols and rest:
            cols["dev_type"] = rest[0]
    return cols


# 합친 머리글 아래 줄에서 '통화' 와 '금액' 자리를 찾는다
def _pair_under(ws, row, start, width=3):
    cur = None
    val = None
    for off in range(0, width):
        c = start + off
        t = _key(ws.cell(row, c).value)
        if not t:
            continue
        if cur is None and _has_word(t, CURRENCY_WORDS):
            cur = c
        elif val is None:
            val = c
    return cur, val


# ==== 양식 머리글에 적힌 달을 읽는다 ('10월 주차별 계획 · 실적')
def _month_in_head(ws, head_row, week_names) -> str:
    want = 0
    for row in (head_row, head_row - 1):
        if row < 1:
            continue
        for c in range(1, _lastc(ws) + 1):
            t = _s(ws.cell(row, c).value)
            if "주차" not in t:
                continue
            m = re.search(r"(\d{1,2})\s*월", t)
            if m:
                want = int(m.group(1))
                break
        if want:
            break
    if not (1 <= want <= 12):
        return ""
    # 연도 — 주차들이 속한 달 중에 같은 월이 있으면 그 연도를 쓴다.
    for w in week_names:
        got = _wcal.month_of_week(w) or ""
        if got[5:7] == "%02d" % want:
            return got
    # 걸치는 주 하나뿐이라 못 맞으면, 아무 주차의 연도를 빌린다.
    for w in week_names:
        got = _wcal.month_of_week(w) or ""
        if got:
            return "%s-%02d" % (got[:4], want)
    return ""


# ==== 주차들이 '가장 많이' 속한 달
#
# 달이 적혀 있지 않은 양식의 차선책. 다섯 주차 중 넷이 10월이면 10월이다.
def _month_by_vote(week_names) -> str:
    vote = {}
    for w in week_names:
        got = _wcal.month_of_week(w) or ""
        if got:
            vote[got] = vote.get(got, 0) + 1
    if not vote:
        return ""
    # 표가 같으면 이른 달 — 늘 같은 답이 나와야 한다.
    return sorted(vote.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


# 주차 열을 찾는다 → [(주차이름, 계획열, 실적열), …]
def _find_weeks(ws, sub_row, unit_row):
    out = []
    # -----------------------------------------------------------
    # 멈추라는 자리에서 멈춘다
    # -----------------------------------------------------------
    # 블룸은 N열까지가 양식에서 읽을 전부다
    for c in range(1, _lastc(ws) + 1):
        t = _s(ws.cell(sub_row, c).value)
        key = _key(t)
        m = WEEK_RE.match(key)
        bare = None
        if not m:
            bare = WEEK_BARE_RE.match(key)
            if not bare:
                continue
            n = int(bare.group(1))
            if not (1 <= n <= 53):
                continue
        num = int(m.group(1)) if m else int(bare.group(1))
        week = "W%02d" % num

        plan_col = None
        actual_col = None
        for off in range(0, 3):
            u = _key(ws.cell(unit_row, c + off).value)
            if plan_col is None and _has_word(u, PLAN_WORDS):
                plan_col = c + off
            elif actual_col is None and _has_word(u, ACTUAL_WORDS):
                actual_col = c + off

        # 숫자만 적힌 칸은 아래에 '계획' 이 있을 때만 주차로 친다.
        # 안 그러면 판가 4230 · PO수량 12 같은 숫자가 전부 주차가 된다.
        if bare and plan_col is None:
            continue
        if plan_col is None:
            plan_col = c
            actual_col = c + 1

        # 멈추라는 자리를 넘어가는 주차는 통째로 버린다. 반쪽(계획만)
        # 읽으면 실적이 늘 비어 보여서, 안 적은 건지 0 인지 알 수 없다.
        if _MAX_COL and (plan_col > _MAX_COL or
                         (actual_col and actual_col > _MAX_COL)):
            continue

        out.append((week, plan_col, actual_col))
    return out


# 양식에 본보기로 얹어 둔 '예시)' 줄인가.
def _is_example_row(ws, r, head_row):
    for c in range(1, 6):
        if _has_word(_key(ws.cell(r, c).value), EXAMPLE_MARKS):
            return True
    return False


# ============================================================
#  품목정보 읽기
# ============================================================
def parse_items(ws) -> tuple:
    warnings = []

    head_row = _find_header_row(ws)
    if head_row is None:
        return [], "", [], ["품목정보 시트에서 'No.' 머리글을 찾지 못했습니다"], [], ""

    sub_row = head_row + 1      # 통화 · 판가 · W41 …
    unit_row = head_row + 2     # 계획 · 실적

    cols = _map_columns(ws, head_row)
    if "owner" not in cols:
        warnings.append("'프로젝트' 또는 '고객사' 열을 찾지 못했습니다")

    # 판가 · 재료비는 합친 머리글이라 아래 줄에서 자리를 다시 찾는다
    price_cur = price_val = None
    if "price_head" in cols:
        price_cur, price_val = _pair_under(ws, sub_row, cols["price_head"])
    material_cur = material_val = None
    if "material_head" in cols:
        material_cur, material_val = _pair_under(ws, sub_row,
                                                 cols["material_head"])

    weeks = _find_weeks(ws, sub_row, unit_row)
    week_names = []
    for w, _p, _a in weeks:
        week_names.append(w)
    # -----------------------------------------------------------
    # 어느 달 자료인가
    # -----------------------------------------------------------
    # 전에는 '첫 주차가 속한 달' 하나로 정했다
    month = ""
    if week_names:
        month = _month_in_head(ws, head_row, week_names) or \
            _month_by_vote(week_names)
    if not month:
        # 주차 칸이 아예 없는 양식도 있다 (ESS 2026-10).
        if _MAX_COL:
            # 일부러 안 읽는 것이다 (블룸). '칸이 없다' 고 하면
            # 있는데 왜 그러냐고 묻게 된다.
            warnings.append(
                "이 사업부 양식은 %d번째 열까지만 읽습니다 — 주차별 계획은 "
                "일 보고 자료로 들어옵니다" % _MAX_COL)
        else:
            warnings.append("주차별 계획 칸이 없습니다 — 품목 정보만 반영합니다")

    items = []
    example_rows = []
    for r in range(unit_row + 1, ws.max_row + 1):
        # -----------------------------------------------------------
        # '예시)' 줄도 읽는다
        # -----------------------------------------------------------
        # 전에는 건너뛰었다. 그런데 올려 주신 블룸 양식을 보니 본보기 줄 세 개(7~9행) 자리에 **진짜 품목**을 적어 넣고 왼쪽 '예시)' 글자만 안 지우셨다 —
        # YFP · CORVA EFM KPE · CORVA EFM KPE PB.
        _ex = _is_example_row(ws, r, head_row)

        owner = _s(ws.cell(r, cols["owner"]).value) if "owner" in cols else ""
        pn = _pn(ws.cell(r, cols["part_number"]).value) if "part_number" in cols else ""
        name = _one_line(ws.cell(r, cols["name"]).value) if "name" in cols else ""

        # 셋 다 비어 있으면 빈 줄이다
        if not owner and not pn and not name:
            continue
        # 이름도 품번도 없으면 어느 모델인지 알 수 없다
        if not pn and not name:
            warnings.append("%d행: 파트넘버도 품목명도 없어 건너뜁니다" % r)
            continue

        group = _s(ws.cell(r, cols["group"]).value) if "group" in cols else ""
        if group not in ("양산", "개발"):
            group = "양산"

        wk = {}
        for w, pc, ac in weeks:
            plan = _num(ws.cell(r, pc).value)
            actual = _num(ws.cell(r, ac).value) if ac else None
            if plan is None and actual is None:
                continue          # 그 주는 아예 안 적었다 — 0 과 다르다
            wk[w] = {"plan": int(round(plan or 0)),
                     "actual": int(round(actual or 0))}

        item = {
            "row": r,
            "owner": owner,
            "part_number": pn,
            "name": name,
            "group": group,
            # 0 과 빈 칸을 가린다 — PO 전량 취소(0)와 '안 적음'(빈 칸)은 다르다
            "po_qty": (_int_or_none(ws.cell(r, cols["po_head"]).value)
                       if "po_head" in cols else None),
            "shipped_qty": (_int_or_none(ws.cell(r, cols["ship_head"]).value)
                            if "ship_head" in cols else None),
            "price": _num(ws.cell(r, price_val).value) if price_val else None,
            "price_currency": _s(ws.cell(r, price_cur).value) if price_cur else "",
            "material_cost": _num(ws.cell(r, material_val).value) if material_val else None,
            "material_currency": _s(ws.cell(r, material_cur).value) if material_cur else "",
            # 반도체 양식에만 있는 칸. 없는 양식에서는 None · 빈 글자다 —
            # 0 으로 두면 '연간 0대' 로 읽힌다.
            "year_qty": (_int(ws.cell(r, cols["year_qty"]).value)
                         if "year_qty" in cols else None),
            "dev_type": _s(ws.cell(r, cols["dev_type"]).value) if "dev_type" in cols else "",
            "note": _s(ws.cell(r, cols["note"]).value) if "note" in cols else "",
            "weeks": wk,
            "example": _ex,
        }
        if "region" in cols:
            item["region"] = _s(ws.cell(r, cols["region"]).value)
        # 납기 칸 — 칸이 있으면 빈칸도 넘긴다 (지운 날짜는 지워져야 한다)
        for _k in ("due_date", "due_revised", "made_date"):
            if _k in cols:
                _v = _due_text(ws.cell(r, cols[_k]).value)
                item[_k] = _v
                if _v and not _ISO_RE.match(_v):
                    warnings.append("%d행 %s: 날짜로 못 읽었습니다 ('%s') — 2026-11-14 처럼 적어 주세요"
                                    % (r, {"due_date": "고객 요청 납기일", "due_revised": "출하 변경일",
                                           "made_date": "제작 완료일"}[_k], _v))
                    item[_k] = ""
        items.append(item)
        if _ex:
            example_rows.append({"row": r, "owner": owner,
                                 "part_number": pn, "name": name})

    if example_rows:
        warnings.append(
            "'예시)' 표시가 붙은 줄 %d건도 읽었습니다 — 본보기 줄이면 "
            "엑셀에서 지우고 다시 올려 주세요" % len(example_rows))
    # -----------------------------------------------------------
    # 이 양식은 몇 주차 자료인가
    # -----------------------------------------------------------
    # 양식이 스스로 말해 준다 — **실적이 적힌 마지막 주차**가 그 양식의 기준 주차다
    as_of_week = ""
    _best = -1
    for it in items:
        for w, cell in (it.get("weeks") or {}).items():
            if not isinstance(cell, dict):
                continue
            if cell.get("actual") in (None, 0):
                continue          # 0 은 '실적 없음' 이 아니라 '0 이라고 적음'
            try:                  # 이지만 주차를 가리는 데는 쓰지 않는다
                n = int(str(w).upper().lstrip("W"))
            except Exception:
                continue
            if n > _best:
                _best, as_of_week = n, "W%02d" % n

    return items, month, week_names, warnings, example_rows, as_of_week


# ============================================================
#  이슈사항 읽기
# ============================================================
def parse_issues(ws) -> tuple:
    warnings = []
    if ws is None:
        return [], warnings

    head_row = _find_header_row(ws)
    if head_row is None:
        return [], ["이슈사항 시트에서 'NO' 머리글을 찾지 못했습니다"]

    cols = {}
    for c in range(1, ws.max_column + 1):
        t = _key(ws.cell(head_row, c).value)
        if not t:
            continue
        if "owner" not in cols and _has_word(t, OWNER_WORDS):
            cols["owner"] = c
        elif "part_number" not in cols and _has_word(t, PN_WORDS):
            cols["part_number"] = c
        elif "category" not in cols and "분류" in t:
            cols["category"] = c          # '이슈 분류' — 이슈사항보다 먼저 본다
        elif "action" not in cols and ("조치" in t or "action" in t):
            cols["action"] = c
        elif "person" not in cols and ("담당" in t or "owner" == t):
            cols["person"] = c
        elif "status" not in cols and ("상태" in t or "status" in t):
            # 진행 / 해결 — issue_status 가 읽는다
            cols["status"] = c
        elif "date" not in cols and ("발생일" in t or "일자" in t or "date" in t):
            cols["date"] = c
        elif "text" not in cols and ("이슈" in t or "내용" in t):
            cols["text"] = c

    if "text" not in cols:
        return [], ["이슈사항 시트에서 '이슈사항' 열을 찾지 못했습니다"]

    issues = []
    for r in range(head_row + 1, ws.max_row + 1):
        text = _s(ws.cell(r, cols["text"]).value)
        if not text:
            continue          # 내용이 없으면 이슈가 아니다

        issues.append({
            "row": r,
            "owner": _s(ws.cell(r, cols["owner"]).value) if "owner" in cols else "",
            "part_number": _pn(ws.cell(r, cols["part_number"]).value) if "part_number" in cols else "",
            "date": _date_text(ws.cell(r, cols["date"]).value) if "date" in cols else "",
            "text": text,
            # 비우면 '' — 진행으로 친다 (상태 칸이 없는 옛 양식도 그대로 읽힌다)
            "status": _s(ws.cell(r, cols["status"]).value) if "status" in cols else "",
            # 칸이 없는 옛 양식은 빈 글자
            "category": _s(ws.cell(r, cols["category"]).value) if "category" in cols else "",
            "action": _s(ws.cell(r, cols["action"]).value) if "action" in cols else "",
            "person": _s(ws.cell(r, cols["person"]).value) if "person" in cols else "",
        })
    return issues, warnings


_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# 납기 칸 → 'YYYY-MM-DD'.
def _due_text(v) -> str:
    t = _date_text(v)
    if not t or _ISO_RE.match(t[:10]):
        return t[:10]
    import datetime as _dt
    m = re.findall(r"(\d{1,2})/(\d{1,2})", t)
    if not m:
        return t
    y = _dt.date.today().year
    prev = None
    out = None
    for mo, d in m:
        try:
            cur = _dt.date(y, int(mo), int(d))
        except ValueError:
            continue
        while prev and cur < prev:
            cur = cur.replace(year=cur.year + 1)
        prev = out = cur
    return out.isoformat() if out else t


# 발생일 칸 → 'YYYY-MM-DD'.
def _date_text(v) -> str:
    try:
        import datetime as _dt
        if isinstance(v, (_dt.datetime, _dt.date)):
            return v.strftime("%Y-%m-%d")
    except Exception:
        pass
    return _s(v)


# ============================================================
#  양식 한 권 읽기
# ============================================================
def parse_terms(ws) -> tuple:
    warnings = []
    if ws is None:
        return [], warnings

    head_row = _find_header_row(ws)
    if head_row is None:
        return [], warnings      # 용어는 없어도 그만이다

    cols = {}
    for c in range(1, ws.max_column + 1):
        t = _key(ws.cell(head_row, c).value)
        if not t:
            continue
        if "short" not in cols and ("약어" in t or "abbr" in t):
            cols["short"] = c
        elif "full" not in cols and ("fullname" in t or "풀네임" in t):
            cols["full"] = c
        elif "ko" not in cols and ("한국어" in t or "뜻" in t):
            cols["ko"] = c
        elif "note" not in cols and ("비고" in t or "확인" in t):
            cols["note"] = c

    if "short" not in cols:
        return [], warnings

    terms = []
    for r in range(head_row + 1, ws.max_row + 1):
        short = _one_line(ws.cell(r, cols["short"]).value)
        if not short:
            continue          # 약어가 없으면 용어가 아니다
        terms.append({
            "row": r,
            "short": short,
            "full": _one_line(ws.cell(r, cols["full"]).value) if "full" in cols else "",
            "ko": _one_line(ws.cell(r, cols["ko"]).value) if "ko" in cols else "",
            "note": _s(ws.cell(r, cols["note"]).value) if "note" in cols else "",
        })
    return terms, warnings


# 공정별 일일 실적 시트 → (rows, dates, warnings)
def parse_daily(ws) -> tuple:
    warnings = []
    if ws is None:
        return [], [], warnings

    head_row = _find_header_row(ws)
    if head_row is None:
        return [], [], warnings

    date_row = head_row + 1
    unit_row = head_row + 2

    cols = {}
    for c in range(1, ws.max_column + 1):
        t = _key(ws.cell(head_row, c).value)
        if not t:
            continue
        if "owner" not in cols and _has_word(t, OWNER_WORDS):
            cols["owner"] = c
        elif "name" not in cols and _has_word(t, NAME_WORDS):
            cols["name"] = c
        elif "part_number" not in cols and _has_word(t, PN_WORDS):
            cols["part_number"] = c
        elif "step" not in cols and t.startswith("공정") and "재고" not in t:
            cols["step"] = c
        elif "ship_wait" not in cols and "출하대기" in t:
            cols["ship_wait"] = c
        elif "buy_wait" not in cols and "구매품대기" in t:
            cols["buy_wait"] = c
        elif "stock" not in cols and "공정재고" in t:
            cols["stock"] = c
    # -----------------------------------------------------------
    # 날짜 칸 — 적혀 있는 만큼. 개수를 정해 두지 않는다.
    # -----------------------------------------------------------
    pairs = []          # [(날짜, 계획열, 실적열), …]
    for c in range(1, ws.max_column + 1):
        d = _date_text(ws.cell(date_row, c).value)
        if not d:
            continue
        plan_c, act_c = c, c + 1
        if not _has_word(_key(ws.cell(unit_row, c).value), PLAN_WORDS):
            continue        # 아래에 '계획' 이 없으면 날짜 칸이 아니다
        if not _has_word(_key(ws.cell(unit_row, c + 1).value), ACTUAL_WORDS):
            act_c = None
        pairs.append((d, plan_c, act_c))

    dates = [d for d, _p, _a in pairs]

    rows = []
    for r in range(unit_row + 1, ws.max_row + 1):
        name = _one_line(ws.cell(r, cols["name"]).value) if "name" in cols else ""
        step = _one_line(ws.cell(r, cols["step"]).value) if "step" in cols else ""
        pn = _pn(ws.cell(r, cols["part_number"]).value) if "part_number" in cols else ""
        if not (name or step or pn):
            continue
        days = {}
        for d, pc, ac in pairs:
            plan = _num(ws.cell(r, pc).value)
            act = _num(ws.cell(r, ac).value) if ac else None
            if plan is None and act is None:
                continue        # 둘 다 안 적었으면 그 날 칸은 만들지 않는다
            days[d] = {"plan": plan, "actual": act}
        rows.append({
            "row": r,
            "owner": _s(ws.cell(r, cols["owner"]).value) if "owner" in cols else "",
            "name": name,
            "part_number": pn,
            "step": step,
            "ship_wait": _num(ws.cell(r, cols["ship_wait"]).value) if "ship_wait" in cols else None,
            "buy_wait": _num(ws.cell(r, cols["buy_wait"]).value) if "buy_wait" in cols else None,
            "stock": _num(ws.cell(r, cols["stock"]).value) if "stock" in cols else None,
            "days": days,
            "example": _is_example_row(ws, r, head_row),
        })
    return rows, dates, warnings


# 사업부 양식 한 권 → 품목과 이슈.
def parse_workbook(wb, division_id: str = "") -> dict:
    global _MAX_COL, _DUE_ON
    try:
        import division_columns as _dc
        _MAX_COL = _dc.last_col(division_id)
        _DUE_ON = bool(_dc.due_cols(division_id))
    except Exception:
        _MAX_COL = None
        _DUE_ON = False

    item_ws = find_sheet(wb, ITEM_SHEET_WORDS)
    if item_ws is None:
        raise ValueError("'품목정보' 시트가 없습니다. 사업부 양식이 맞는지 확인해 주세요.")

    items, month, weeks, warn1, example_rows, as_of_week = parse_items(item_ws)
    issues, warn2 = parse_issues(find_sheet(wb, ISSUE_SHEET_WORDS))
    # 양식 다섯 장 중 나머지 둘. 없어도 그만이라 경고하지 않는다.
    terms, warn3 = parse_terms(find_sheet(wb, TERM_SHEET_WORDS))
    daily, daily_dates, warn4 = parse_daily(find_sheet(wb, DAILY_SHEET_WORDS))

    # 엑셀이 '프로젝트별' 인지 '고객사별' 인지 — 화면 안내에 쓴다
    kind = "고객사" if "고객사" in _s(item_ws.title) else "프로젝트"

    return {
        "sheet": item_ws.title,
        "kind": kind,
        "month": month,
        "weeks": weeks,
        # 실적이 적힌 마지막 주차 = 이 양식의 기준 주차. 없으면 빈 글자.
        "as_of_week": as_of_week,
        "items": items,
        "issues": issues,
        # 사업부별 용어 사전 (양식 '용어' 시트). 비어 있는 게 보통이다.
        "terms": terms,
        # 양식 안의 공정별 일일 실적. 블룸·ESS 는 따로 파일로도 받는다.
        "daily": daily,
        "daily_dates": daily_dates,
        # '예시)' 가 붙은 채로 올라온 줄. 화면이 반영 전에 보여 준다.
        "example_rows": example_rows,
        "warnings": warn1 + warn2 + warn3 + warn4,
    }
