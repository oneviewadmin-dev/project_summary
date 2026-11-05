# -*- coding: utf-8 -*-
# ============================================================
#  사업부 매출 파일 읽기
# ============================================================

import datetime as _dt
import re as _re

# 달 머리글이 있는 줄을 찾을 때 쓰는 말. 'ㅇ월' 이 네 칸 넘게 늘어선 줄.
_MONTH_RE = _re.compile(r"^\s*(\d{1,2})\s*월\s*$")
SHEET_WORDS = ("써머리", "서머리", "summary")

# ============================================================
#  주간보고형 (네트워크 · 자동차) ── 2026-10-28
# ============================================================
# 네트워크 · 자동차 매출 파일은 ESS 와 생김새가 아예 다르다
WK_KINDS = ("사업계획", "실행계획", "Open PO", "실적")
# 타겟으로 쓸 줄. 사업계획은 연초에 잡은 것, 실행계획은 중간에 조정한 것.
# 지금 지키려는 숫자는 조정한 쪽이라 실행계획을 먼저 본다. 그 줄이 아예
# 없는 파일이면 사업계획으로 내려간다 — 여기 한 줄이 기준이다.
WK_PLAN_ORDER = ("실행계획", "사업계획")
# 파일 맨 아래 '[합 계]' 묶음. 여기 마지막 '실적' 줄이 그 파일의 바닥 숫자다.
WK_TOTAL_WORDS = ("[합 계]", "[합계]", "합 계", "합계")
# 합계 묶음 안에서 줄의 성격을 가르는 말. 나머지는 '구분' 묶음이다.
WK_SUB_WORDS = ("sub-total", "subtotal", "소계")
WK_INTERNAL_WORDS = ("내부거래", "internal")
WK_GRAND_WORDS = ("총합", "총 합계", "총합계", "grand")
_W_RE = _re.compile(r"^[Ww](\d{1,2})$")
_MM_RE = _re.compile(r"^\s*(\d{1,2})\s*월\s*$")
FX_SHEET_WORDS = ("환율정보", "환율")


def _s(v) -> str:
    return " ".join(str(v if v is not None else "").split())


# 숫자 칸. 빈 칸·글자는 None (0 과 다르다).
def _num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).replace(",", "").replace("₩", "").replace("$", "").strip()
    if not t:
        return None
    try:
        return float(t)
    except Exception:
        return None


def find_sheet(wb, words):
    for ws in wb.worksheets:
        name = _s(ws.title).lower()
        for w in words:
            if w.lower() in name:
                return ws
    return None


# ============================================================
#  환율
# ============================================================
def parse_fx(ws) -> dict:
    if ws is None:
        return {}
    head = None
    for r in range(1, min(ws.max_row, 20) + 1):
        row = [_s(ws.cell(r, c).value) for c in range(1, min(ws.max_column, 12) + 1)]
        if any("날짜" in x for x in row) and any("환율" == x for x in row):
            head = r
            break
    if head is None:
        return {}
    col_d = col_v = None
    for c in range(1, min(ws.max_column, 12) + 1):
        t = _s(ws.cell(head, c).value)
        if col_d is None and "날짜" in t:
            col_d = c
        elif col_v is None and t == "환율":
            col_v = c
    if not (col_d and col_v):
        return {}

    bucket = {}
    for r in range(head + 1, ws.max_row + 1):
        d = ws.cell(r, col_d).value
        v = _num(ws.cell(r, col_v).value)
        if v is None or not v:
            continue
        if isinstance(d, _dt.datetime):
            d = d.date()
        if not isinstance(d, _dt.date):
            continue
        iso = d.isocalendar()
        bucket.setdefault((int(iso[0]), int(iso[1])), []).append(v)
    return {k: sum(xs) / len(xs) for k, xs in bucket.items() if xs}


# 그 달에 걸친 주들의 평균 — 달 하나를 한 숫자로 바꿀 때 쓴다
def fx_for_month(fx: dict, year: int, month: int):
    want = []
    d = _dt.date(year, month, 1)
    while d.month == month:
        iso = d.isocalendar()
        k = (int(iso[0]), int(iso[1]))
        if k in fx and k not in [w[0] for w in want]:
            want.append((k, fx[k]))
        d += _dt.timedelta(days=1)
    if not want:
        return None
    return sum(v for _k, v in want) / len(want)


# ============================================================
#  써머리
# ============================================================
def _month_cols(ws, head_row: int) -> dict:
    out = {}
    for c in range(1, ws.max_column + 1):
        m = _MONTH_RE.match(_s(ws.cell(head_row, c).value))
        if m:
            mm = int(m.group(1))
            if 1 <= mm <= 12 and mm not in out:
                out[mm] = c
    return out


# '고객 / 모델' 과 달 머리글이 같이 있는 줄.
def _find_head(ws):
    for r in range(1, min(ws.max_row, 60) + 1):
        joined = " ".join(_s(ws.cell(r, c).value)
                          for c in range(1, min(ws.max_column, 8) + 1))
        if "고객" in joined and "모델" in joined:
            cols = _month_cols(ws, r)
            if len(cols) >= 4:
                return r, cols
    return None


# 써머리 시트 → 고객사·모델별 월 매출 (원화).
def parse_summary(ws, year: int) -> dict:
    got = _find_head(ws)
    if not got:
        return {"rows": [], "months": {}}
    head, cols = got

    # 머리글 줄에서 '고객' 글자가 있는 열. 그 오른쪽 칸이 모델이다.
    c0 = None
    for c in range(1, min(ws.max_column, 8) + 1):
        if "고객" in _s(ws.cell(head, c).value):
            c0 = c
            break
    if c0 is None:
        return {"rows": [], "months": {}}

    rows = []
    cust = ""
    # 고객사 칸은 묶여 있어서 첫 줄에만 적힌다. 아래 줄은 이어받는다.
    for r in range(head + 1, ws.max_row + 1):
        a = _s(ws.cell(r, c0).value)
        b = _s(ws.cell(r, c0 + 1).value)
        # -----------------------------------------------------------
        # 여기서 멈춘다
        # -----------------------------------------------------------
        # 같은 표가 KRW · USD 로 두 번 나온다
        if a.upper() == "USD" or (a and "고객" in a and "모델" in b):
            break

        if a:
            cust = a
        if not b:
            continue
        if b in ("소계", "합계", "월매출", "분기매출"):
            continue
        if a in ("합계",):
            continue
        months = {}
        for mm, c in cols.items():
            v = _num(ws.cell(r, c).value)
            if v is None:
                continue
            months[mm] = v
        if not months:
            continue
        rows.append({"customer": cust, "model": b, "months": months})

    total = {}
    for row in rows:
        for mm, v in row["months"].items():
            total[mm] = total.get(mm, 0.0) + v
    return {"rows": rows, "months": total}


# 주간보고형인가 → (머리글줄, {주차: 열}, {달: 열}, 고객사열, 구분열) 또는 None.
def _wk_layout(ws):
    # 주차 칸이 **가장 많은** 줄을 머리글로 본다
    best = None
    for r in range(1, min(ws.max_row, 20) + 1):
        weeks, months = {}, {}
        for c in range(1, ws.max_column + 1):
            t = _s(ws.cell(r, c).value)
            m = _W_RE.match(t)
            if m:
                w = int(m.group(1))
                if 1 <= w <= 53 and w not in weeks:
                    weeks[w] = c
                continue
            if not t and r > 1:
                mm = _MM_RE.match(_s(ws.cell(r - 1, c).value))
                if mm:
                    v = int(mm.group(1))
                    if 1 <= v <= 12 and v not in months:
                        months[v] = c
        if len(weeks) < 10:
            continue
        kind_col = None
        for rr in range(r + 1, min(r + 12, ws.max_row) + 1):
            for c in range(1, min(ws.max_column, 12) + 1):
                if _s(ws.cell(rr, c).value) in WK_KINDS:
                    kind_col = c
                    break
            if kind_col:
                break
        if not (kind_col and kind_col > 1):
            continue
        # 고객사는 구분 바로 왼쪽 칸이다 (자동차는 그 왼쪽에 '직거래' 가
        # 한 칸 더 있지만, 고객사 자리는 같다).
        cand = (r, weeks, months, kind_col - 1, kind_col)
        if best is None or len(weeks) > len(best[1]):
            best = cand
    return best


# ISO 주 → 'YYYY-MM'.
def _wk_month_of(year: int, week: int):
    import datetime as _d
    try:
        d = _d.date.fromisocalendar(int(year), int(week), 4)
    except Exception:
        return None
    return "%04d-%02d" % (d.year, d.month)


# '[합 계]' 묶음이 시작하는 줄.
def _wk_total_row(ws, head: int, c_kind: int) -> int:
    for r in range(head + 1, ws.max_row + 1):
        for c in range(1, min(ws.max_column, c_kind) + 1):
            t = _s(ws.cell(r, c).value)
            if t and any(t.startswith(w) for w in WK_TOTAL_WORDS):
                return r
    return 0


# 주간보고형 한 장 → 월별 실적 · 월별 계획 · 주차별 실적.
def parse_weekly(ws, year: int) -> dict:
    got = _wk_layout(ws)
    if not got:
        return None
    head, weeks, mcols, c_cust, c_kind = got
    tot_at = _wk_total_row(ws, head, c_kind)

    def _read(r):
        wv, mv = {}, {}
        for w, c in weeks.items():
            v = _num(ws.cell(r, c).value)
            if v is not None:
                wv[w] = v
        for mm, c in mcols.items():
            v = _num(ws.cell(r, c).value)
            if v is not None:
                mv[mm] = v
        return wv, mv
    # -----------------------------------------------------------
    # 고객사 줄 (합계 묶음 앞까지) — 목록을 보여 주는 데만 쓴다
    # -----------------------------------------------------------
    customers, cust = [], ""
    stop = tot_at or (ws.max_row + 1)
    for r in range(head + 1, stop):
        a = _s(ws.cell(r, c_cust).value)
        if a:
            cust = a
        if _s(ws.cell(r, c_kind).value) != "실적":
            continue
        wv, mv = _read(r)
        if (wv or mv) and cust and cust not in customers:
            customers.append(cust)
    # -----------------------------------------------------------
    # 합계 묶음에서 '마지막' 실적 · 계획 줄
    # -----------------------------------------------------------
    last = {}
    if tot_at:
        for r in range(tot_at, ws.max_row + 1):
            k = _s(ws.cell(r, c_kind).value)
            if k not in WK_KINDS:
                continue
            wv, mv = _read(r)
            if wv or mv:
                last[k] = (wv, mv)

    plan_kind = ""
    for want in WK_PLAN_ORDER:
        if want in last:
            plan_kind = want
            break

    # 한 줄 → {'YYYY-MM': 금액}.
    def _months(pair):
        if not pair:
            return {}
        wv, mv = pair
        by_wk = {}
        for w, v in wv.items():
            mon = _wk_month_of(year, w)
            if mon:
                by_wk[mon] = by_wk.get(mon, 0.0) + v
        out = {}
        for mm in range(1, 13):
            key = "%04d-%02d" % (int(year), mm)
            if mv.get(mm):
                out[key] = mv[mm]
            elif by_wk.get(key):
                out[key] = by_wk[key]
        return out

    act = last.get("실적")
    act_w = {}
    if act:
        for w, v in act[0].items():
            if v:
                act_w["%04d-W%02d" % (int(year), w)] = v

    return {"rows": [], "weeks": act_w,
            "detail": _wk_detail(ws, year, head, weeks, mcols,
                                 c_cust, c_kind, tot_at),
            "months": _months(act),
            "plan_months": _months(last.get(plan_kind)) if plan_kind else {},
            "plan_kind": plan_kind,
            "total_row": tot_at,
            "customers": customers}


# 그 줄의 묶음 이름. 구분 칸 **왼쪽 글자를 다 이어** 쓴다
def _wk_label(ws, r: int, c_kind: int) -> str:
    parts = []
    for c in range(1, c_kind):
        t = _s(ws.cell(r, c).value)
        if t and t not in parts:
            parts.append(t)
    return " · ".join(parts)


# 달마다 '구분별 실적' 표를 만든다
def _wk_detail(ws, year: int, head: int, weeks: dict, mcols: dict,
               c_cust: int, c_kind: int, tot_at: int) -> dict:
    def _vals(r):
        wv, mv = {}, {}
        for w, c in weeks.items():
            v = _num(ws.cell(r, c).value)
            if v is not None:
                wv[w] = v
        for mm, c in mcols.items():
            v = _num(ws.cell(r, c).value)
            if v is not None:
                mv[mm] = v
        return wv, mv

    def _month_map(pair):
        wv, mv = pair
        by_wk = {}
        for w, v in wv.items():
            mon = _wk_month_of(year, w)
            if mon:
                by_wk[mon] = by_wk.get(mon, 0.0) + v
        out = {}
        for mm in range(1, 13):
            key = "%04d-%02d" % (int(year), mm)
            if mv.get(mm):
                out[key] = mv[mm]
            elif by_wk.get(key):
                out[key] = by_wk[key]
        return out
    # -----------------------------------------------------------
    # 합계 묶음 읽기
    # -----------------------------------------------------------
    boxes, sub, internal, grand = [], None, None, None
    if tot_at:
        label = ""
        for r in range(tot_at, ws.max_row + 1):
            k = _s(ws.cell(r, c_kind).value)
            if k not in WK_KINDS:
                continue
            lb = _wk_label(ws, r, c_kind)
            if lb:
                label = lb
            if k not in ("실적", "실행계획", "사업계획"):
                continue
            pair = _vals(r)
            if not (pair[0] or pair[1]):
                continue
            low = label.lower()
            # 총합을 먼저 본다. 네트워크의 총합 줄 이름이
            # '총합 (내부거래 포함) Grand Total' 이라, 내부거래를 먼저 보면
            # 총합이 내부거래로 잡힌다.
            slot = ("grand" if any(w in low for w in WK_GRAND_WORDS)
                    else "internal" if any(w in low for w in WK_INTERNAL_WORDS)
                    else "sub" if any(w in low for w in WK_SUB_WORDS)
                    else "box")
            rec = {"label": label, "kind": k, "months": _month_map(pair)}
            if slot == "box":
                boxes.append(rec)
            elif slot == "sub":
                sub = rec if k == "실적" else sub
            elif slot == "internal":
                internal = rec if k == "실적" else internal
            else:
                grand = rec if k == "실적" else grand
    # -----------------------------------------------------------
    # 고객사 줄
    # -----------------------------------------------------------
    custs, cust = [], ""
    stop = tot_at or (ws.max_row + 1)
    for r in range(head + 1, stop):
        a = _s(ws.cell(r, c_cust).value)
        if a:
            cust = a
        if _s(ws.cell(r, c_kind).value) != "실적":
            continue
        pair = _vals(r)
        if not (pair[0] or pair[1]) or not cust:
            continue
        custs.append({"label": cust, "months": _month_map(pair)})
    # -----------------------------------------------------------
    # 달마다 한 장씩
    # -----------------------------------------------------------
    out = {}
    months = set()
    for rec in boxes + custs + [x for x in (sub, internal, grand) if x]:
        months |= set(rec["months"])
    for mon in sorted(months):
        # 한 해 내내 0 인 묶음은 뺀다 — 이름 없는 빈 줄이 앞 묶음 이름을
        # 물려받아 '금형 매출 금액' 이 두 번 서는 일이 있었다.
        gs = [{"key": "g%d" % i, "label": b["label"],
               "actual": round(b["months"].get(mon, 0.0), 2), "items": []}
              for i, b in enumerate(x for x in boxes
                                    if x["kind"] == "실적"
                                    and any(x["months"].values()))]
        items = [{"item": c["label"],
                  "actual": round(c["months"].get(mon, 0.0), 2)}
                 for c in custs if c["months"].get(mon) is not None]
        if items:
            gs.append({"key": "cust", "label": "고객사별",
                       "actual": round(sum(i["actual"] for i in items), 2),
                       "items": sorted(items, key=lambda r: -r["actual"]),
                       "aside": True})
        out[mon] = {
            "groups": gs,
            "subtotal": ({"label": sub["label"],
                          "actual": round(sub["months"].get(mon, 0.0), 2)}
                         if sub else None),
            "internal": ({"label": internal["label"],
                          "actual": round(internal["months"].get(mon, 0.0), 2)}
                         if internal else None),
            "grand": ({"label": grand["label"] or "총합",
                       "actual": round(grand["months"].get(mon, 0.0), 2)}
                      if grand else None),
        }
    return out


# 파일이 몇 해 것인가. 시트 앞머리에 적힌 연도를 쓰고, 없으면 올해.
def _year_of(wb, ws) -> int:
    for r in range(1, 7):
        for c in range(1, min(ws.max_column, 12) + 1):
            v = ws.cell(r, c).value
            if isinstance(v, (int, float)) and not isinstance(v, bool) \
                    and 2000 <= int(v) <= 2100:
                return int(v)
            m = _re.search(r"(20\d{2})\s*년", _s(v))
            if m:
                return int(m.group(1))
    return _dt.date.today().year


# 매출 파일 한 장 → 월별 USD.
def parse_workbook(wb, year: int = None) -> dict:
    warn = []
    # -----------------------------------------------------------
    # 주간보고형을 먼저 본다. 주차 칸이 있으면 그 모양이 확실하고,
    # -----------------------------------------------------------
    #    ESS 써머리에는 주차 칸이 없어서 서로 안 헷갈린다.
    for ws in wb.worksheets:
        try:
            got = parse_weekly(ws, _year_of(wb, ws))
        except Exception:
            got = None
        if not got or not got["months"]:
            continue
        yr = _year_of(wb, ws)
        months = {k: {"krw": None, "usd": round(v, 2), "fx": None}
                  for k, v in sorted(got["months"].items())}
        if not months:
            continue
        if got["plan_kind"] and got["plan_kind"] != "실행계획":
            warn.append("'실행계획' 줄이 없어 '%s' 을 계획으로 썼습니다."
                        % got["plan_kind"])
        return {"year": yr, "shape": "주간보고", "sheet": ws.title,
                "fx_weeks": 0, "months": months,
                "weeks": {k: round(v, 2) for k, v in sorted(got["weeks"].items())},
                "plan_months": {k: round(v, 2)
                                for k, v in sorted(got["plan_months"].items())},
                "plan_kind": got["plan_kind"],
                "detail": got.get("detail") or {},
                "rows": [], "customers": got["customers"],
                "warnings": warn}
    # -----------------------------------------------------------
    # ESS형
    # -----------------------------------------------------------
    ws = find_sheet(wb, SHEET_WORDS)
    if ws is None:
        raise ValueError(
            "매출 파일 모양을 못 알아봤습니다. "
            "'써머리' 시트(ESS형)도, 주차(W1·W2…) 칸이 늘어선 장(주간보고형)도 없습니다.")
    if not year:
        year = _year_of(wb, ws)

    fx = parse_fx(find_sheet(wb, FX_SHEET_WORDS))
    if not fx:
        warn.append("환율정보 시트를 못 읽어 USD 환산을 건너뜁니다.")

    got = parse_summary(ws, year)
    months = {}
    for mm, krw in sorted(got["months"].items()):
        rate = fx_for_month(fx, year, mm) if fx else None
        months["%04d-%02d" % (year, mm)] = {
            "krw": round(krw),
            "usd": round(krw / rate, 2) if rate else None,
            "fx": round(rate, 2) if rate else None,
        }
        if fx and not rate:
            warn.append("%d월 환율이 없어 USD 를 못 냈습니다." % mm)
    # -----------------------------------------------------------
    # ESS 도 같은 모양으로
    # -----------------------------------------------------------
    #    묶음 = 고객사, 세부 = 모델. 총합은 묶음을 더한 값이다 —
    #    써머리에는 따로 적힌 바닥 줄이 없다.
    detail = {}
    for mm in sorted(got["months"]):
        key = "%04d-%02d" % (year, mm)
        cell = months.get(key) or {}
        rate = cell.get("fx")
        if not rate:
            continue
        by = {}
        for row in got["rows"]:
            v = row["months"].get(mm)
            if v is None:
                continue
            b = by.setdefault(row["customer"] or "(이름 없음)",
                              {"actual": 0.0, "items": []})
            b["actual"] += v / rate
            b["items"].append({"item": row["model"],
                               "actual": round(v / rate, 2)})
        gs = [{"key": "c%d" % i, "label": k,
               "actual": round(v["actual"], 2),
               "items": sorted(v["items"], key=lambda r: -r["actual"])}
              for i, (k, v) in enumerate(sorted(by.items()))]
        detail[key] = {
            "groups": gs, "subtotal": None, "internal": None,
            "grand": {"label": "총합", "actual": cell.get("usd")},
        }

    return {"year": year, "shape": "ESS", "sheet": ws.title, "detail": detail,
            "fx_weeks": len(fx), "months": months, "weeks": {},
            "plan_months": {}, "plan_kind": "",
            "rows": got["rows"],
            "customers": sorted({r.get("customer") or "" for r in got["rows"]}),
            "warnings": warn}
