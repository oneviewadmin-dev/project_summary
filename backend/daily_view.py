# -*- coding: utf-8 -*-
# ============================================================
#  일 보고 자료를 화면에 띄울 모양으로 접는다
# ============================================================
from __future__ import annotations

import datetime as _dt

WEEKDAY_KR = ("월", "화", "수", "목", "금", "토", "일")


# '2026-10-19' → date.
def _d(s):
    if isinstance(s, _dt.date):
        return s
    return _dt.date.fromisoformat(str(s)[:10])


# 그 날짜가 몇 주차인가 (ISO).
def week_no(d) -> int:
    return _d(d).isocalendar()[1]


# 날짜 칸 여러 개에서 한 항목을 더한다
def _sum_cells(cells, field):
    total = None
    for c in cells:
        v = (c or {}).get(field)
        if v is None:
            continue
        total = (total or 0) + v
    return total


# 그 날이 든 주(월~일)의 날짜 중 그 달에 드는 것만.
def _week_days_in_month(day, month: str) -> list:
    mon = str(month or day.strftime("%Y-%m"))[:7]
    d0 = day - _dt.timedelta(days=day.weekday())      # 그 주 월요일
    out = []
    for i in range(7):
        d = d0 + _dt.timedelta(days=i)
        if d.strftime("%Y-%m") == mon:
            out.append(d)
    return out


# 어떤 열을 그릴지 정한다 → [{kind, label, dates}]
def build_columns(dates, today=None, month="") -> list:
    if not dates:
        return []

    days = sorted({_d(x) for x in dates})
    today = _d(today) if today else _dt.date.today()
    cur_week = today.isocalendar()[1]
    # -----------------------------------------------------------
    # 1. 날짜를 주차별로 묶는다
    # -----------------------------------------------------------
    by_week = {}
    for d in days:
        by_week.setdefault(d.isocalendar()[1], []).append(d)
    # -----------------------------------------------------------
    # 2. 이번 주차가 자료에 없으면 (달이 지났거나 아직 안 왔으면)
    # -----------------------------------------------------------
    # 자료에 있는 주차 중 오늘과 가장 가까운 주차를 이번 주로 본다
    _mon = str(month or "")[:7]
    _this_month = (not _mon) or today.strftime("%Y-%m") == _mon

    if not _this_month:
        cur_week = None                     # 아무 주도 안 편다
    else:
        # 이번 주 날짜가 아직 자료에 없어도 칸은 세운다
        _full = _week_days_in_month(today, _mon or today.strftime("%Y-%m"))
        if _full:
            by_week[cur_week] = sorted(set(by_week.get(cur_week) or []) | set(_full))
    # -----------------------------------------------------------
    # 3. 주차 순서대로 열을 만든다
    # -----------------------------------------------------------
    out = []
    for w in sorted(by_week):
        ds = by_week[w]
        if w == cur_week:
            # 이번 주 — 하루씩 펼친다
            for d in ds:
                out.append({
                    "kind": "day",
                    "label": "%d/%d(%s)" % (d.month, d.day, WEEKDAY_KR[d.weekday()]),
                    "date": d.isoformat(),
                    "dates": [d.isoformat()],
                    "today": d == today,
                })
        else:
            out.append({
                "kind": "week",
                "label": "%d주차" % w,
                "week": w,
                "from": ds[0].isoformat(),
                "to": ds[-1].isoformat(),
                "dates": [x.isoformat() for x in ds],
                "past": bool(cur_week) and w < cur_week,
            })
    # -----------------------------------------------------------
    # 맨 끝에 '월 합계' 한 칸
    # -----------------------------------------------------------
    # 주차 칸만 있으면 "이 달에 다 해서 몇 개냐" 를 눈으로 더해야 한다
    _alld = sorted({d for c in out for d in (c.get("dates") or [])})
    if _alld:
        _mm = str(month or _alld[0])[:7]
        try:
            _lab = "%d월 합계" % int(_mm[5:7])
        except Exception:
            _lab = "합계"
        out.append({"kind": "sum", "label": _lab, "dates": _alld})

    return out


# 한 줄(공정)의 날짜 자료를 열 모양에 맞춰 접는다
def fold_row(days: dict, columns: list) -> list:
    cells = []
    for col in columns:
        picked = []
        for ds in col["dates"]:
            if ds in days:
                picked.append(days[ds])
        cells.append({
            "plan": _sum_cells(picked, "plan"),
            "actual": _sum_cells(picked, "actual"),
        })
    return cells


# 공정 한 줄을 열 모양에 맞춰 접는다 ('이전 데이터' 칸 포함).
def _cells_of(step: dict, columns: list) -> list:
    cells = fold_row(step.get("days") or {}, columns)
    # fold_row 는 날짜로만 채운다. '이전 데이터' 칸은 날짜가 없어서
    # 비어 있으니 여기서 넣어 준다.
    for i, col in enumerate(columns):
        if col.get("kind") == "prior":
            cells[i] = {"plan": step.get("prior_plan"),
                        "actual": step.get("prior_actual")}
    return cells


# 파서가 읽은 것 → 화면에 그릴 표.
def build(parsed: dict, today=None, month="") -> dict:
    columns = build_columns(parsed.get("dates") or [], today, month)
    # -----------------------------------------------------------
    # 맨 앞의 '이전 데이터' 칸
    # -----------------------------------------------------------
    #    ESS 보고자료에는 '10월05일 이전 데이터' 처럼, 날짜별로 안 적고
    #    한 칸에 몰아 둔 지난 기간이 있다. 이것도 '지난 주차를 통친 것'
    #    이라 맨 앞에 한 칸으로 둔다.
    prior_label = str(parsed.get("prior_label") or "").replace("\n", " ").strip()
    has_prior = False
    if prior_label:
        for it in (parsed.get("items") or []):
            for st in (it.get("steps") or []):
                if st.get("prior_plan") is not None or st.get("prior_actual") is not None:
                    has_prior = True
                    break
            if has_prior:
                break
    if has_prior:
        columns.insert(0, {"kind": "prior", "label": prior_label,
                           "dates": [], "past": True})

    rows = []
    for it in (parsed.get("items") or []):
        for st in (it.get("steps") or []):
            rows.append({
                "owner": it.get("owner") or "",
                "item": it.get("item") or "",
                "step": st.get("step") or "",
                "group": st.get("group") or "",
                # 재고는 품목 단위라 그 품목의 첫 공정 줄에만 적는다
                "wait_ship": it.get("wait_ship"),
                "wait_part": it.get("wait_part"),
                "wip": st.get("wip"),
                "month_plan": st.get("month_plan"),
                "month_actual": st.get("month_actual"),
                "cells": _cells_of(st, columns),
            })
    # -----------------------------------------------------------
    # 합계 줄 — 열마다 모든 공정을 더한다
    # -----------------------------------------------------------
    total = []
    for i, _col in enumerate(columns):
        plan = None
        actual = None
        for r in rows:
            c = r["cells"][i]
            if c["plan"] is not None:
                plan = (plan or 0) + c["plan"]
            if c["actual"] is not None:
                actual = (actual or 0) + c["actual"]
        total.append({"plan": plan, "actual": actual})

    return {
        "sheet": parsed.get("sheet"),
        "columns": columns,
        "rows": rows,
        "total": total,
        "notes": parsed.get("notes") or [],
    }
