# -*- coding: utf-8 -*-
# ============================================================
#  이슈 진행 / 해결
# ============================================================
from __future__ import annotations

import re

OPEN, CLOSED = "진행", "해결"

# 결과 — 미리보기와 반영이 같은 말을 쓴다
ADDED = "added"                  # 새 이슈로 들어감
DUP = "dup"                      # 이미 열려 있음 — 그대로
CLOSED_NOW = "closed"            # 열린 것을 닫음
ALREADY_CLOSED = "already_closed"  # 이미 닫혀 있음 — 그대로
NOT_REOPENED = "not_reopened"    # 닫힌 것을 '진행' 으로 올림 — 다시 안 엶
CLOSED_NEW = "closed_new"        # 열린 적 없는데 '해결' — 기록에만 남김

_LINE_RE = re.compile(r"^\s*\[(\d{4}-\d{2}-\d{2})\]\s*(.*)$")
_CLOSE_WORDS = ("해결", "완료", "종료", "닫힘", "close", "done", "resolved")


# 같은 이슈인지 볼 때 쓰는 글자 — 띄어쓰기 · 기호 · 대소문자 무시.
def norm(t) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(t or "").lower())


# 상태 칸 → '진행' | '해결'.
def status_of(raw) -> str:
    t = str(raw or "").strip().lower().replace(" ", "")
    if t and any(w in t for w in _CLOSE_WORDS):
        return CLOSED
    return OPEN


# 칸 안의 줄바꿈은 ' / ' 로.
def one_line(text) -> str:
    parts = [x.strip() for x in str(text or "").splitlines() if x.strip()]
    return " / ".join(parts)


# '[2026-11-04] 내용' → ('2026-11-04', '내용').
def split_line(line) -> tuple:
    s = str(line or "").strip()
    mo = _LINE_RE.match(s)
    if mo:
        return mo.group(1), mo.group(2).strip()
    return "", s


def make_line(date, text) -> str:
    date = str(date or "").strip()
    text = one_line(text)
    return "[%s] %s" % (date, text) if date else text


META_KEYS = ("category", "action", "person")     # 이슈 분류 · 조치사항 · 담당자 (2026-11-04)


def _meta_of(issue: dict) -> dict:
    return {k: str(issue.get(k) or "").strip() for k in META_KEYS
            if str(issue.get(k) or "").strip()}


# 모델 이슈의 분류 · 조치 · 담당자.
def _put_meta(m: dict, key: str, issue: dict) -> None:
    meta = _meta_of(issue)
    if not meta:
        return
    m.setdefault("issue_meta", {}).setdefault(key, {}).update(meta)


def _open_lines(m: dict) -> list:
    return [x for x in str(m.get("issues") or "").splitlines() if x.strip()]


def _closed_has(lst, key: str, pn: str | None = None) -> bool:
    for c in lst or []:
        if not isinstance(c, dict):
            continue
        if pn is not None and norm(c.get("part_number")) != norm(pn):
            continue
        if norm(c.get("text")) == key:
            return True
    return False


# 양식 한 줄을 모델에 반영하고 결과를 돌려준다
def apply_to_model(m: dict, issue: dict, today: str, file: str = "",
                   dry: bool = False) -> str:
    text = one_line(issue.get("text"))
    key = norm(text)
    if not key:
        return DUP
    want = status_of(issue.get("status"))
    lines = _open_lines(m)
    hit = None
    for i, ln in enumerate(lines):
        if norm(split_line(ln)[1]) == key:
            hit = i
            break
    closed = m.get("issues_closed") or []

    if want == OPEN:
        if hit is not None:
            if not dry:
                _put_meta(m, key, issue)      # 조치사항이 바뀌었으면 새 조치로
            return DUP
        if _closed_has(closed, key):
            return NOT_REOPENED
        if not dry:
            lines.append(make_line(issue.get("date"), text))
            m["issues"] = "\n".join(lines)
            _put_meta(m, key, issue)
        return ADDED

    # 해결
    if hit is not None:
        if not dry:
            d0, t0 = split_line(lines.pop(hit))
            m["issues"] = "\n".join(lines)
            meta = dict((m.get("issue_meta") or {}).pop(key, {}) or {})
            meta.update(_meta_of(issue))
            m.setdefault("issues_closed", []).append(dict({
                "date": d0 or str(issue.get("date") or ""), "text": t0,
                "closed": today, "file": file}, **meta))
        return CLOSED_NOW
    if _closed_has(closed, key):
        return ALREADY_CLOSED
    if not dry:
        m.setdefault("issues_closed", []).append({
            "date": str(issue.get("date") or ""), "text": text,
            "closed": today, "file": file})
    return CLOSED_NEW


# ----------------------------------------------------------
#  프로젝트 이슈 (품번이 없거나 못 찾은 것)
# ----------------------------------------------------------
def apply_to_project(proj: dict, issue: dict, today: str, file: str = "",
                     dry: bool = False) -> str:
    text = one_line(issue.get("text"))
    key = norm(text)
    if not key:
        return DUP
    pn = str(issue.get("part_number") or "").strip()
    want = status_of(issue.get("status"))
    lst = proj.get("issues") or []
    hit = None
    for i, o in enumerate(lst):
        if (isinstance(o, dict) and norm(o.get("text")) == key
                and norm(o.get("part_number")) == norm(pn)):
            hit = i
            break
    closed = proj.get("issues_closed") or []

    if want == OPEN:
        if hit is not None:
            if not dry:
                lst[hit].update(_meta_of(issue))
            return DUP
        if _closed_has(closed, key, pn):
            return NOT_REOPENED
        if not dry:
            proj.setdefault("issues", []).append(dict(
                {"date": issue.get("date") or "", "part_number": pn, "text": text},
                **_meta_of(issue)))
        return ADDED

    if hit is not None:
        if not dry:
            o = proj["issues"].pop(hit)
            meta = {k: o[k] for k in META_KEYS if o.get(k)}
            meta.update(_meta_of(issue))
            proj.setdefault("issues_closed", []).append(dict({
                "date": o.get("date") or "", "part_number": pn,
                "text": o.get("text") or text, "closed": today, "file": file}, **meta))
        return CLOSED_NOW
    if _closed_has(closed, key, pn):
        return ALREADY_CLOSED
    if not dry:
        proj.setdefault("issues_closed", []).append({
            "date": issue.get("date") or "", "part_number": pn, "text": text,
            "closed": today, "file": file})
    return CLOSED_NEW


# 한 프로젝트의 열린 이슈 → 양식 줄 [{owner, part_number, date, text, status}].
def open_rows(owner: str, proj: dict) -> list:
    out = []
    for m in (proj or {}).get("models") or []:
        if not isinstance(m, dict):
            continue
        pn = str(m.get("part_number") or m.get("id") or "")
        meta = m.get("issue_meta") or {}
        for ln in _open_lines(m):
            d, t = split_line(ln)
            if t:
                out.append(dict({"owner": owner, "part_number": pn, "date": d,
                                 "text": t, "status": OPEN}, **(meta.get(norm(t)) or {})))
    for o in (proj or {}).get("issues") or []:
        if isinstance(o, dict) and str(o.get("text") or "").strip():
            out.append(dict({"owner": owner,
                             "part_number": str(o.get("part_number") or ""),
                             "date": str(o.get("date") or ""),
                             "text": one_line(o.get("text")), "status": OPEN},
                            **{k: o[k] for k in META_KEYS if o.get(k)}))
    return out


# 결과 목록 → {added, closed, dup, not_reopened, ...} 개수.
def summary(results: list) -> dict:
    out = {ADDED: 0, CLOSED_NOW: 0, DUP: 0, ALREADY_CLOSED: 0,
           NOT_REOPENED: 0, CLOSED_NEW: 0}
    for r in results:
        out[r] = out.get(r, 0) + 1
    return out
