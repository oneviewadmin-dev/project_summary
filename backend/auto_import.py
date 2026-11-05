# ============================================================
#  자동차사업부 '양산주요제품' 엑셀 파서
# ============================================================

from __future__ import annotations

import re

# 엑셀 머리글 → 우리 이름
HEAD = {
    "고객사": "customer", "제품명": "product", "모델명": "model_name",
    "최종고객사": "end_customer", "차종": "car_model", "납품위치": "site",
    "제품중량": "weight_kg", "주조톤수": "tonnage", "구분": "kind",
    "재료비": "c_material", "부품비": "c_parts", "주조비": "c_casting",
    "가공비": "c_machining", "관리이윤": "c_margin", "감가상각": "c_depr",
    "포장": "c_packing", "물류": "c_logi",
    # 시트마다 원가를 쪼갠 정도가 다르다. 주조비·가공비로 나뉜 시트가 있고
    # 공정비 한 칸으로만 있는 시트가 있다. 둘 다 읽는다.
    "공정비": "c_process",
    # 엑셀이 스스로 낸 합계. 우리가 모은 다섯 덩어리와 맞는지 대조용으로만 쓴다.
    "합계": "c_total",
    "판가": "price", "불량률": "defect_rate",
    "현재단계": "stage", "SOP시점": "sop",
}
YEAR_RE = re.compile(r"^(20\d{2})$")
PRICE_FX_RE = re.compile(r"^=\s*([\d.]+)\s*\*\s*([\d.]+)\s*$")
STOP = ("총매출", "합계", "총계")


def _s(v):
    return "" if v is None else " ".join(str(v).split())


def _key(v):
    return re.sub(r"[\s()\n]", "", _s(v))


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, str):
        v = v.replace(",", "").replace("%", "").strip()
        if not v or v.startswith("="):
            return None
    try:
        return float(v)
    except Exception:
        return None


# 병합 셀이면 왼쪽 위 값을 돌려준다 (고객사처럼 세로 병합된 칸).
def _merged_value(ws, r, c):
    v = ws.cell(r, c).value
    if v is not None:
        return v
    for rng in ws.merged_cells.ranges:
        if rng.min_row <= r <= rng.max_row and rng.min_col <= c <= rng.max_col:
            return ws.cell(rng.min_row, rng.min_col).value
    return None


# '고객사' 와 '제품명' 이 같이 있는 행 → (행번호, {이름: 열}, {연도: 열})
def _find_header(ws, max_scan=12):
    for r in range(1, min(ws.max_row, max_scan) + 1):
        cols, years = {}, {}
        for c in range(1, ws.max_column + 1):
            k = _key(ws.cell(r, c).value)
            if not k:
                continue
            m = YEAR_RE.match(k)
            if m:
                years[m.group(1)] = c
                continue
            hit = HEAD.get(k)
            if hit is None:
                # 긴 이름부터 본다 ('제품중량' 이 '제품명' 에 먹히지 않게)
                for hk in sorted(HEAD, key=len, reverse=True):
                    if k.startswith(hk):
                        hit = HEAD[hk]
                        break
            if hit:
                cols.setdefault(hit, c)
        if "customer" in cols and "product" in cols:
            return r, cols, years
    return None


# 워크북 → {'sheet', 'years', 'rows'[]}.
def parse(wb, wb_formula=None, sheet=None):
    names = [sheet] if sheet else list(wb.sheetnames)
    for nm in names:
        if nm not in wb.sheetnames:
            continue
        ws = wb[nm]
        hdr = _find_header(ws)
        if not hdr:
            continue
        wsf = wb_formula[nm] if (wb_formula and nm in wb_formula.sheetnames) else None
        got = _read_sheet(ws, hdr, wsf)
        if got and got["rows"]:
            return got
    return None


def _read_sheet(ws, hdr, wsf=None):
    head_row, cols, years = hdr
    ylist = sorted(years)
    rows = []
    r = head_row + 1
    customer = ""
    while r <= ws.max_row:
        cust = _s(_merged_value(ws, r, cols["customer"])) or customer
        product = _s(_merged_value(ws, r, cols["product"]))
        if _key(cust) in STOP or _key(product) in STOP:
            break
        if not product:
            r += 1
            continue
        customer = cust

        def cell(name, row=r):
            c = cols.get(name)
            return _merged_value(ws, row, c) if c else None

        # 원가 칸들 → 다섯 덩어리
        g = lambda k: _num(cell(k)) or 0.0          # noqa: E731
        # 공정비는 시트에 따라 주조비+가공비로 나뉘어 있거나 한 칸으로만 있다.
        # 나뉜 칸이 있으면 그걸 쓰고, 없을 때만 공정비 칸을 쓴다.
        # (나뉜 시트의 '공정비' 칸은 포장·물류까지 섞인 다른 합이라 같이 더하면 겹친다)
        process = g("c_casting") + g("c_machining") or g("c_process")
        cost = {
            "material": g("c_material") + g("c_parts") + g("c_packing"),
            "process": process,
            "admin": g("c_margin"),
            "depr": g("c_depr"),
            "logi": g("c_logi"),
        }
        cost = {k: v for k, v in cost.items() if v}

        # 엑셀이 적어 둔 합계와 맞는지 본다. 열 구성이 시트마다 달라서
        # 한 칸을 놓쳐도 숫자는 그럴듯하게 나온다 — 그때 잡히는 건 이 대조뿐이다.
        excel_total = _num(cell("c_total"))
        total_gap = None
        if excel_total:
            gap = sum(cost.values()) - excel_total
            if abs(gap) > max(1.0, excel_total * 0.005):
                total_gap = round(gap, 1)

        # 판가 — 수식이면 외화 단가와 환율을 살린다
        price_fx = fx_rate = price_krw = None
        c_price = cols.get("price")
        if c_price:
            m = None
            if wsf is not None:
                f = wsf.cell(r, c_price).value       # '=27.06*1350'
                m = PRICE_FX_RE.match(_s(f)) if isinstance(f, str) else None
            if m:
                price_fx, fx_rate = float(m.group(1)), float(m.group(2))
            else:
                price_krw = _num(_merged_value(ws, r, c_price))

        # 연도별: 이 줄이 물량, 다음 줄이 매출
        contract = {}
        for y in ylist:
            q = _num(_merged_value(ws, r, years[y]))
            v = _num(_merged_value(ws, r + 1, years[y]))
            if q or v:
                contract[y] = {}
                if q:
                    contract[y]["qty"] = int(round(q))
                if v:
                    contract[y]["revenue"] = v

        stage = _s(cell("stage"))
        rows.append({
            "row": r,
            "customer": cust,
            "product": product,
            "group": "개발" if "개발" in stage else "양산",
            "total_gap": total_gap,
            "auto": _clean({
                "model_name": _s(cell("model_name")),
                "end_customer": _s(cell("end_customer")),
                "car_model": _s(cell("car_model")),
                "site": _s(cell("site")),
                "sop": _s(cell("sop")),
                "weight_kg": _num(cell("weight_kg")),
                "tonnage": _num(cell("tonnage")),
                "defect_rate": _num(cell("defect_rate")),
                # 통화는 엑셀에 없다. 환율만 보고 EUR/USD 를 찍던 걸 뺀다 —
                # 맞을 수도 있지만 근거가 없으면 적지 않는 게 낫다.
                "price_fx": price_fx,
                "fx_rate": fx_rate,
                "price_krw": price_krw,
                "cost": cost,
                "contract": contract,
            }),
        })
        r += 2          # 비용 행 + 비율 행

    return {"sheet": ws.title, "years": ylist, "rows": rows}


def _clean(d):
    return {k: v for k, v in d.items() if v not in (None, "", {}, [])}


# 어느 시트가 읽히는지만 훑는다 (같은 표의 개정본이 여러 장 있다).
def sheets(wb, wb_formula=None):
    out = []
    for nm in wb.sheetnames:
        try:
            hdr = _find_header(wb[nm])
            if not hdr:
                continue
            wsf = wb_formula[nm] if (wb_formula and nm in wb_formula.sheetnames) else None
            got = _read_sheet(wb[nm], hdr, wsf)
        except Exception:
            continue
        if got and got["rows"]:
            out.append({"sheet": nm, "rows": len(got["rows"]), "years": got["years"]})
    return out


# 별칭 → 등록된 표기. 엑셀에 '스탈란티스' 로 적혀 있어도 화면에는 등록된 '스텔란티스' 로 나가게 하려고 쓴다
def name_labels(projects):
    out = {}
    for p in projects:
        lab = _s(p.get("label"))
        if not lab:
            continue
        for nm in [lab] + list(p.get("aliases") or []):
            k = _key(nm).lower()
            if k:
                out.setdefault(k, lab)
    return out


# 등록된 고객사 이름이면 등록 표기로 바꾼다
def canonical(name, labels):
    return labels.get(_key(name).lower(), _s(name))


# 고객사 이름 → 프로젝트 키.
def match_projects(rows, projects):
    idx = {}
    for p in projects:
        for nm in [p.get("label")] + list(p.get("aliases") or []):
            k = _key(nm).lower()
            if k:
                idx.setdefault(k, p["id"])
    return {c: idx.get(_key(c).lower()) for c in {r["customer"] for r in rows}}
