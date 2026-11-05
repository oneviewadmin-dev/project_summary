# -*- coding: utf-8 -*-
# ============================================================
#  사업부 매출 파일로 들어온 금액을 담는 자리
# ============================================================

import datetime as _dt
import json
import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR") or Path(__file__).resolve().parent)
FILE = DATA_DIR / "division_revenue.json"


def _load() -> dict:
    try:
        if FILE.exists():
            d = json.loads(FILE.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return d
    except Exception as e:
        print("[사업부매출] 읽지 못했습니다(무시) — %s" % e)
    return {}


def _save(d: dict) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(FILE)      # 쓰다 만 파일이 남지 않게


# 한 해치를 갈아 끼운다 → 담긴 달 목록.
def put(division_id: str, year: int, months: dict, rows=None,
        file_name: str = "", plan_months: dict = None,
        weeks: dict = None, shape: str = "", detail: dict = None) -> dict:
    div = str(division_id or "").strip().lower()
    if not div:
        return {"saved": []}
    d = _load()
    book = d.setdefault(div, {})
    keep = {k: v for k, v in (book.get("months") or {}).items()
            if not k.startswith("%04d-" % int(year))}
    saved = []
    for k, v in (months or {}).items():
        if not isinstance(v, dict) or v.get("usd") in (None, ""):
            continue
        keep[k] = {"usd": v.get("usd"), "krw": v.get("krw"), "fx": v.get("fx")}
        saved.append(k)
    book["months"] = dict(sorted(keep.items()))
    # -----------------------------------------------------------
    # 계획 · 주차도 같이 담는다
    # -----------------------------------------------------------
    # 네트워크 · 자동차 파일에는 실적뿐 아니라 그 달 '실행계획' 과 주차별 실적이 같이 있다
    yr = "%04d-" % int(year)
    pk = {k: v for k, v in (book.get("plan_months") or {}).items()
          if not k.startswith(yr)}
    for k, v in (plan_months or {}).items():
        try:
            pk[k] = float(v)
        except Exception:
            continue
    book["plan_months"] = dict(sorted(pk.items()))

    wk = {k: v for k, v in (book.get("weeks") or {}).items()
          if not k.startswith(yr)}
    for k, v in (weeks or {}).items():
        try:
            wk[k] = float(v)
        except Exception:
            continue
    book["weeks"] = dict(sorted(wk.items()))

    # 달마다 '구분별 실적' 표. 반도체 매출 관리 화면이 보여 주는 그 표를
    # 다른 사업부도 같게 그리려고 파일 모양 그대로 담는다.
    dt = {k: v for k, v in (book.get("detail") or {}).items()
          if not k.startswith(yr)}
    for k, v in (detail or {}).items():
        if isinstance(v, dict):
            dt[k] = v
    book["detail"] = dict(sorted(dt.items()))

    book["shape"] = shape or book.get("shape") or ""
    book["rows"] = rows or []
    book["file"] = file_name or ""
    book["at"] = _dt.datetime.now().isoformat(timespec="seconds")
    d[div] = book
    _save(d)
    return {"saved": sorted(saved)}


# 그 사업부 · 그 달의 매출(USD).
def month_usd(division_id: str, month: str):
    div = str(division_id or "").strip().lower()
    cell = ((_load().get(div) or {}).get("months") or {}).get(str(month or ""))
    if not isinstance(cell, dict):
        return None
    v = cell.get("usd")
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


# 그 사업부 · 그 달의 계획(USD).
def month_plan(division_id: str, month: str):
    div = str(division_id or "").strip().lower()
    v = ((_load().get(div) or {}).get("plan_months") or {}).get(str(month or ""))
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


# '2026-W42' 그 주의 매출(USD).
def week_usd(division_id: str, week_key: str):
    div = str(division_id or "").strip().lower()
    v = ((_load().get(div) or {}).get("weeks") or {}).get(str(week_key or ""))
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


# 그 달 '구분별 실적' 표. 없으면 None — 화면이 프로젝트별로 떨어진다
def month_detail(division_id: str, month: str):
    div = str(division_id or "").strip().lower()
    v = ((_load().get(div) or {}).get("detail") or {}).get(str(month or ""))
    return v if isinstance(v, dict) else None


# 화면에 '어느 파일이 언제 들어왔나' 를 보여 주려고.
def info(division_id: str) -> dict:
    div = str(division_id or "").strip().lower()
    book = _load().get(div) or {}
    return {"file": book.get("file") or "", "at": book.get("at") or "",
            "shape": book.get("shape") or "",
            "months": sorted((book.get("months") or {}).keys()),
            "plan_months": sorted((book.get("plan_months") or {}).keys()),
            "weeks": len(book.get("weeks") or {}),
            "rows": book.get("rows") or []}


def all_divisions() -> list:
    return sorted(_load().keys())
