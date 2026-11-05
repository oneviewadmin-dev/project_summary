# -*- coding: utf-8 -*-
# ============================================================
#  품목별 개발 일정 양식 읽기
# ============================================================

import datetime as _dt
import re as _re

SHEET_WORDS = ("개발 일정", "개발일정", "품목별 개발")
_STEP_RE = _re.compile(r"^\s*단계\s*(\d{1,3})\s*$")
KIND_PROC, KIND_PLAN, KIND_ACT = "프로세스", "계획", "실적"


def _s(v) -> str:
    return " ".join(str(v if v is not None else "").split())


# 품번 비교용 열쇠.
def pn_key(v) -> str:
    t = _s(v)
    if not t:
        return ""
    # 'PART NO :' 처럼 칸 이름이 앞에 붙어 오는 줄이 있다. 그걸 떼고 나면
    # 괄호 앞이 비어서, 서로 다른 품목이 같은 열쇠가 된다 (KET KOREA 3줄).
    head = _re.split(r"[(\[]", t)[0]
    head = _re.sub(r"(?i)^\s*(part\s*(no|number)?|품번|파트\s*넘버)\s*[:：]?\s*", "", head)
    key = _re.sub(r"[^0-9A-Za-z가-힣]", "", head).upper()
    if key:
        return key
    # 괄호 앞에 쓸 글자가 없으면 칸 전체로 가린다 — 괄호 안이 곧 이름이다
    return _re.sub(r"[^0-9A-Za-z가-힣]", "", t).upper()


# 계획 · 실적 한 칸 → (날짜, 글자, 탈).
def cell_value(v):
    if v is None:
        return None, "", ""
    if isinstance(v, (_dt.datetime, _dt.date)):
        return _date(v), "", ""
    t = _s(v)
    if not t:
        return None, "", ""
    d = _date(t)
    if d:
        return d, "", ""
    # 숫자-숫자-숫자 꼴인데 날짜가 안 되면 오타다. 글자로 두면 화면에
    # '2026-06-31' 이 날짜인 척 서 있게 된다 — 적은 사람에게 알린다.
    flat = _re.sub(r"\s+", "", t).replace("/", "-").replace(".", "-")
    if _re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", flat):
        return None, "", t
    return None, t, ""


# 날짜 칸 → 'YYYY-MM-DD'.
def _date(v):
    if v is None:
        return None
    if isinstance(v, _dt.datetime):
        return v.date().isoformat()
    if isinstance(v, _dt.date):
        return v.isoformat()
    t = _s(v)
    if not t:
        return None
    # '2025. 11. 30' 처럼 점 뒤에 공백이 붙어 온다. 공백을 먼저 턴다 —
    # 안 그러면 '2025- 11- 30' 이 되어 하나도 안 읽힌다.
    t = _re.sub(r"\s+", "", t).replace("/", "-").replace(".", "-")
    m = _re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        try:
            return _dt.date(int(m.group(1)), int(m.group(2)),
                            int(m.group(3))).isoformat()
        except ValueError:
            return None
    return None


def find_sheet(wb):
    for ws in wb.worksheets:
        name = _s(ws.title)
        for w in SHEET_WORDS:
            if w in name:
                return ws
    # 시트 이름이 'Sheet1' 인 파일도 온다 — 머리글로 알아본다
    for ws in wb.worksheets:
        if _find_head(ws):
            return ws
    return None


# '구분' 과 '단계 N' 이 같이 있는 줄 → (줄번호, {열: 칸이름}, 자리들).
def _find_head(ws):
    for r in range(1, min(ws.max_row, 30) + 1):
        cols, where = {}, {}
        for c in range(1, ws.max_column + 1):
            t = _s(ws.cell(r, c).value)
            if not t:
                continue
            m = _STEP_RE.match(t)
            if m:
                cols[int(m.group(1))] = c
            elif t in ("No.", "no.", "No"):
                where["no"] = c
            elif t in ("프로젝트", "고객사"):
                # 사업부마다 첫 칸 이름이 다르다 — 반도체·블룸은 '프로젝트',
                # 자동차·ESS 는 '고객사'. 한쪽만 받으면 그 칸이 통째로
                # 빈 글자가 되어 품목을 어디에 붙일지 모르게 된다.
                where["project"] = c
            elif t == "파트넘버":
                where["pn"] = c
            elif "담당" in t:
                where["owner"] = c
            elif t == "구분":
                where["kind"] = c
        if cols and "kind" in where and "pn" in where:
            return r, cols, where
    return None


# ============================================================
#  단계 이름 맞추기
# ============================================================
# 프로세스 줄은 품목마다 사람이 따로 적는다
_NUM_RE = _re.compile(r"^\s*\d{1,2}\s")


def _unify_steps(items: list, warn: list) -> None:
    by_len = {}
    for it in items:
        names = tuple(s["name"] for s in it["steps"])
        by_len.setdefault(len(names), {}).setdefault(names, []).append(it)
    for n, groups in by_len.items():
        # 이 길이에서 쓰인 틀들 — 많이 쓴 것부터
        tpls = sorted(groups.items(), key=lambda kv: -len(kv[1]))
        majors = []
        for names, its in tpls:
            # 이미 있는 큰 틀과 절반 넘게 같으면 그 틀의 변형이다
            if any(sum(a == b for a, b in zip(names, m)) * 2 > n for m in majors):
                continue
            majors.append(names)
        if not majors:
            continue
        # 틀마다 자리별 최다 이름 (변형까지 세서)
        best = {}
        for m in majors:
            members = [its for names, its in tpls
                       if max(majors, key=lambda mm: sum(a == b for a, b in zip(names, mm))) == m]
            col = []
            for i in range(n):
                cnt = {}
                for its in members:
                    for it in its:
                        nm = it["steps"][i]["name"]
                        cnt[nm] = cnt.get(nm, 0) + 1
                # 번호로 시작하는 이름을 앞세운다 ('투입 대기' 가 이기지 않게)
                col.append(sorted(cnt.items(),
                                  key=lambda kv: (not _NUM_RE.match(kv[0]), -kv[1], kv[0]))[0][0])
            best[m] = col
        for names, its in tpls:
            if names in best:
                continue
            m = max(majors, key=lambda mm: sum(a == b for a, b in zip(names, mm)))
            if sum(a == b for a, b in zip(names, m)) * 2 <= n:
                continue                      # 따로 쓰는 틀 — 건드리지 않는다
            want = best[m]
            for it in its:
                for i, st in enumerate(it["steps"]):
                    old = st["name"]
                    if old == want[i]:
                        continue
                    # 바꾸는 것은 둘뿐이다 — 번호가 같은 변형 '03 PO 접수/등록' → '03 PO 접수' 번호 없는 상태 글자 '투입 대기' → '08 생산투입' 번호 없는
                    # 이름끼리('LAIR 작성' · 'LAIR 제출')는 정말 다른 단계일 수 있다 (반도체 프로젝트마다 다르다) — 그대로 둔다
                    mo, mw = _NUM_RE.match(old), _NUM_RE.match(want[i])
                    if not mw:
                        continue
                    if mo and mo.group(0).strip() != mw.group(0).strip():
                        continue
                    st["name"] = want[i]
                    if not _NUM_RE.match(old):
                        # 상태 글자를 이름 칸에 적은 것 — 메모로 남긴다
                        if not st.get("actual_note"):
                            st["actual_note"] = old
                    warn.append("%d행 %s: 단계 %d 이름 '%s' → '%s' 로 맞췄습니다 "
                                "(다른 품목들과 같게)" % (it["row"], it["part_number"],
                                                         i + 1, old, want[i]))


# 양식 한 장 → 품목별 {단계 이름 · 계획일 · 실적일}.
def parse_workbook(wb) -> dict:
    ws = find_sheet(wb)
    if ws is None:
        raise ValueError("'품목별 개발 일정' 시트를 못 찾았습니다.")
    got = _find_head(ws)
    if not got:
        raise ValueError("머리글('구분' · '단계 1')을 못 찾았습니다.")
    head, step_cols, where = got
    order = [step_cols[k] for k in sorted(step_cols)]

    warn = []
    n_date, n_note = [0], [0]
    items, cur, seen = [], None, set()
    for r in range(head + 1, ws.max_row + 1):
        kind = _s(ws.cell(r, where["kind"]).value)
        if kind not in (KIND_PROC, KIND_PLAN, KIND_ACT):
            continue
        pn = _s(ws.cell(r, where["pn"]).value)
        proj = _s(ws.cell(r, where.get("project", 0) or 1).value) \
            if where.get("project") else ""
        # 프로세스 줄에만 품번 뒤에 설명이 붙어 오는 양식이 있다 (pn_key)
        key = (proj, pn_key(pn))

        if kind == KIND_PROC:
            names = [_s(ws.cell(r, c).value) for c in order]
            # 뒤쪽 빈 단계는 버린다. 머리글이 13칸이어도 세 단계만 쓰는
            # 양식이 온다 — 빈 이름을 단계로 세면 화면에 빈 칸이 늘어선다.
            while names and not names[-1]:
                names.pop()
            if not names:
                warn.append("%d행: 단계 이름이 한 칸도 없습니다." % r)
                continue
            if key in seen:
                warn.append("%d행: %s · %s 가 두 번 나옵니다." % (r, proj, pn))
            seen.add(key)
            cur = {"row": r, "project": proj, "part_number": pn,
                   "owner": _s(ws.cell(r, where["owner"]).value)
                            if where.get("owner") else "",
                   "steps": [{"name": n, "expected": None, "actual": None,
                              "expected_note": None, "actual_note": None}
                             for n in names]}
            items.append(cur)
            continue

        # 계획 · 실적 — 바로 위 프로세스 줄에 붙인다
        if cur is None:
            warn.append("%d행: '%s' 줄 위에 프로세스 줄이 없습니다 (%s · %s)."
                        % (r, kind, proj, pn))
            continue
        cur_key = (cur["project"], pn_key(cur["part_number"]))
        if cur_key != key:
            if cur_key[1] and cur_key[1] == key[1]:
                warn.append("%d행: 고객사가 위 프로세스 줄과 다릅니다 "
                            "(프로세스 '%s' · %s '%s'). 품번이 같아 같은 "
                            "품목으로 붙였습니다."
                            % (r, cur["project"], kind, proj))
            else:
                warn.append("%d행: 품번이 위 프로세스 줄과 다릅니다 "
                            "(프로세스 '%s' · %s '%s'). 세 줄의 품번을 "
                            "같게 적어 주세요." % (r, cur["part_number"], kind, pn))
                continue
        field = "expected" if kind == KIND_PLAN else "actual"
        for i, c in enumerate(order):
            d, note, bad = cell_value(ws.cell(r, c).value)
            if i >= len(cur["steps"]):
                if d or note or bad:
                    warn.append("%d행: 단계 %d 에 적힌 게 있는데 프로세스 줄에 "
                                "그 단계 이름이 없습니다." % (r, i + 1))
                continue
            if bad:
                # 버리지 않고 글자로 남긴다 — 지우면 적은 사람은 적었다고
                # 믿고 화면만 비어 있게 된다. 대신 경고로 알린다.
                warn.append("%d행 %s · 단계 %d: '%s' 는 없는 날짜입니다. "
                            "글자 그대로 두었습니다." % (r, kind, i + 1, bad))
                cur["steps"][i][field + "_note"] = bad
                continue
            cur["steps"][i][field] = d
            if note:
                cur["steps"][i][field + "_note"] = note
            n_note[0] += 1 if note else 0
            n_date[0] += 1 if d else 0

    _unify_steps(items, warn)

    return {"sheet": ws.title, "steps_max": len(order),
            "items": items, "warnings": warn,
            # 올린 사람이 '몇 칸이 들어갔나' 를 바로 보게 한다. 전에는
            # 통째로 버려도 '경고 0건' 이라 괜찮아 보였다.
            "date_cells": n_date[0], "note_cells": n_note[0]}
