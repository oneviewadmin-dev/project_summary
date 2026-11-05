# ============================================================
#  '월별 매입 현황 분석' 엑셀 읽기
# ============================================================
from __future__ import annotations

import datetime as _dt
import io
import os
import re
import tempfile

from openpyxl import load_workbook

# 이름이 이렇게 적혀 있으면 이 키로 맞춰 준다. 여기 없는 항목도 그대로
# 받는다 (키는 g1, g2 … 로 만든다).
ITEM_KEYS = [
    ("raw", ("원소재", "원자재")),
    ("supply", ("소모품", "소모자재")),
    ("etc", ("기타", "약품", "포장재")),
    ("outsourcing", ("외주", "외주가공")),
]
METRICS = {
    "buy": ("매입액", "매입", "구매액", "구매"),
    "paid": ("지급액", "지급", "결제액"),
    "balance": ("잔액", "미지급", "잔여"),
}
PAYMENT = {
    "prepaid": ("선급금", "선급"),
    "actual_paid": ("실지급액", "실지급"),
    "invest": ("설비투자", "실비투자", "설비", "실비"),
}
REVENUE = ("매출액", "매출")
# 재고·미수금·총매입액 줄. 이름이 또렷해서 '구분' 칸을 안 봐도 알아본다 —
# 아래쪽 블록 이름이 '합계' 라서 구분 칸만 보면 통째로 건너뛰게 된다.
STOCK_KEYS = (
    ("available", ("가용원재고", "가용원자재", "가용재고")),
    ("dead", ("불용원자재", "불용원재고", "불용재고")),
    ("wip", ("재공재고", "재공품재고", "재공")),
    ("finished", ("완제품재고", "완제품")),
)
SIDE_KEYS = (
    ("receivable", ("외상매출", "미수금")),
    ("total_buy", ("총매입액", "총매입")),
    ("ratio", ("매출대비매입비율", "매입비율", "매출대비")),
)
REGION_WORDS = {"total": ("합계", "총계"), "overseas": ("해외",), "domestic": ("국내",)}
NOTE_WORDS = ("비고", "특이사항", "note")
MAX_EXTRA = 24
SKIP_IN = ("합계", "총계", "소계")      # 어디에 끼어 있어도 건너뛴다
SKIP_EQ = ("계", "total")                # 딱 그 글자일 때만

_MONTH_TXT = re.compile(r"(?:^|\D)(1[0-2]|0?[1-9])\s*월")


def _txt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (_dt.datetime, _dt.date)):
        return "%d월" % v.month
    return re.sub(r"\s+", " ", str(v).replace(" ", " ")).strip()


def _norm(s) -> str:
    return re.sub(r"[\s()（）\[\]·.,/]+", "", _txt(s)).lower()


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = _txt(v).replace(",", "").replace("$", "").replace("₩", "")
    if not t or t in ("-", "—", "–"):
        return None
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg, t = True, t[1:-1].strip()
    elif t.startswith("-"):
        neg, t = True, t[1:].strip()
    try:
        f = float(t)
    except ValueError:
        return None
    return -f if neg else f


# 다듬은 글자 n 안에 words 중 하나라도 들어 있는가.
def _has_any(n: str, words) -> bool:
    for w in words:
        if _norm(w) in n:
            return True
    return False


# 다듬은 글자 n 이 words 중 하나와 정확히 같은가.
def _equals_any(n: str, words) -> bool:
    for w in words:
        if _norm(w) == n:
            return True
    return False


# 읽지 않고 건너뛸 줄인가 (머리글·안내문·합계 같은 것).
def _is_skip(s) -> bool:
    n = _norm(s)
    if not n:
        return False
    # -----------------------------------------------------------
    # 1. 일부만 들어 있어도 건너뛰는 말
    # -----------------------------------------------------------
    if _has_any(n, SKIP_IN):
        return True
    # -----------------------------------------------------------
    # 2. 글자가 통째로 같아야 건너뛰는 말
    # -----------------------------------------------------------
    skip_exact = set()
    for k in SKIP_EQ:
        skip_exact.add(_norm(k))
    return n in skip_exact


def _month_of(v, year: int):
    if isinstance(v, (_dt.datetime, _dt.date)):
        return "%04d-%02d" % (v.year, v.month)
    t = _txt(v)
    if not t or _is_skip(t):
        return None
    m = re.match(r"^(20\d\d)[-./\s]+(1[0-2]|0?[1-9])$", t)
    if m:
        return "%04d-%02d" % (int(m.group(1)), int(m.group(2)))
    m = _MONTH_TXT.search(t)
    if m:
        return "%04d-%02d" % (year, int(m.group(1)))
    return None


def _known_key(label):
    n = _norm(label)
    if not n:
        return None
    # ITEM_KEYS = [('출하대기', ('출하 대기', '출하대기')), …]
    # 앞에 적힌 것부터 본다 — 먼저 맞는 것이 이긴다.
    for key, words in ITEM_KEYS:
        if _has_any(n, words):
            return key
    return None


def _metric(label):
    n = _norm(label)
    if not n:
        return None
    # -----------------------------------------------------------
    # 1. 글자가 똑같은 것을 먼저 찾는다
    # -----------------------------------------------------------
    #    '매입' 은 '총매입액' 안에도 들어 있다. 포함부터 보면 둘이 섞여서
    #    '매입' 줄이 '총매입액' 으로 들어간다.
    for key, words in METRICS.items():
        if _equals_any(n, words):
            return key
    # -----------------------------------------------------------
    # 2. 똑같은 게 없으면 포함으로 한 번 더
    # -----------------------------------------------------------
    #    '매입액(원)' 처럼 뒤에 뭐가 붙은 경우를 잡는다.
    for key, words in METRICS.items():
        if _has_any(n, words):
            return key
    return None


# 라벨이 words 중 하나를 품고 있는가.
def _match(label, words):
    n = _norm(label)
    if not n:
        return False
    return _has_any(n, words)


# 재고·미수금·총매입액·비율 줄인지.
def _special(label):
    n = _norm(label)
    if not n:
        return None
    # -----------------------------------------------------------
    # 1. 재고 줄인가 → ('stock', 어느 재고인지)
    # -----------------------------------------------------------
    for key, words in STOCK_KEYS:
        if _has_any(n, words):
            return ("stock", key)
    # -----------------------------------------------------------
    # 2. 미수금·총매입액·비율 같은 곁줄인가 → (그 키, None)
    # -----------------------------------------------------------
    for key, words in SIDE_KEYS:
        if _has_any(n, words):
            return (key, None)

    return None


# 비고는 줄바꿈을 지킨다 — 몇 건인지 눈으로 세야 하니까.
def _note_txt(v) -> str:
    if v is None:
        return ""
    t = str(v).replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    # 줄 끝 공백만 떼고 줄 구조는 그대로 둔다
    lines = []
    for ln in t.split("\n"):
        lines.append(ln.rstrip())
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


# bytes · 파일객체 · 경로를 다 받는다
def _open_book(data):
    if isinstance(data, (bytes, bytearray, memoryview)):
        raw = bytes(data)
    elif hasattr(data, "read"):
        raw = data.read()
        if not isinstance(raw, (bytes, bytearray)):
            raise ValueError("파일을 바이트로 읽지 못했습니다.")
        raw = bytes(raw)
    else:
        return load_workbook(data, data_only=True, keep_links=False)

    try:
        return load_workbook(io.BytesIO(raw), data_only=True, keep_links=False)
    except Exception:
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
            return load_workbook(path, data_only=True, keep_links=False)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


def _grid(ws, max_row=400, max_col=40):
    out = []
    for r in ws.iter_rows(min_row=1, max_row=min(ws.max_row or 1, max_row),
                          max_col=min(ws.max_column or 1, max_col)):
        out.append([c.value for c in r])
    return out


# 월이 2개 이상 있는 줄을 머리줄로 본다
def _header(rows, year: int):
    best, best_i = {}, -1
    for i, row in enumerate(rows[:40]):
        cols, seen = {}, set()
        for j, v in enumerate(row):
            m = _month_of(v, year)
            if m and m not in seen:
                cols[j] = m
                seen.add(m)
        if len(cols) >= 2 and len(cols) > len(best):
            best, best_i = cols, i
    return best_i, best


# 머리줄에서 월 오른쪽에 있는 합계·해외·국내·비고 열을 찾는다
def _side_cols(row, after: int):
    regions = {}      # {'해외': 열번호, '국내': 열번호, ...}
    note = None       # 비고 열 번호
    # -----------------------------------------------------------
    # 1. 찾을 말을 미리 다듬어 둔다
    # -----------------------------------------------------------
    #    REGION_WORDS = {'해외': ('해외', 'overseas'), '국내': (...)}
    #    돌 때마다 다듬으면 같은 일을 열 수만큼 반복한다.
    want = {}
    for r, words in REGION_WORDS.items():
        normed = set()
        for w in words:
            normed.add(_norm(w))
        want[r] = normed
    # -----------------------------------------------------------
    # 2. 월 열 오른쪽을 한 칸씩 본다
    # -----------------------------------------------------------
    for j in range(after + 1, len(row)):
        n = _norm(row[j])
        if not n:
            continue

        # ── 2-1. 비고 열을 아직 못 찾았으면 먼저 그것부터
        if note is None and _has_any(n, NOTE_WORDS):
            note = j
            continue

        # ── 2-2. 비고를 이미 찾았으면 그 오른쪽은 지역 열이 아니다
        #        (비고 뒤는 사람이 적어 둔 메모 영역이다)
        if note is not None:
            continue

        # ── 2-3. 지역 열인가. 먼저 찾은 열을 쓴다 — 같은 말이 또 나오면
        #        오른쪽 것은 보통 소계라 덮어쓰면 안 된다.
        for r, ns in want.items():
            if n in ns and r not in regions:
                regions[r] = j

    return regions, note


def parse_workbook(data, year=None, sheet=None) -> dict:
    year = int(year or _dt.date.today().year)
    wb = _open_book(data)
    ws = wb[sheet] if (sheet and sheet in wb.sheetnames) else wb[wb.sheetnames[0]]

    rows = _grid(ws)
    hi, cols = _header(rows, year)
    if not cols:
        raise ValueError("월(4월·5월…)이 적힌 머리줄을 찾지 못했습니다.")

    regions, note_col = _side_cols(rows[hi], max(cols))
    months_keys = sorted(set(cols.values()))

    blank = lambda: {"revenue": None, "items": {}, "prepaid": None,      # noqa: E731
                     "actual_paid": None, "invest": None, "stock": {},
                     "receivable": None, "total_buy": None}
    # 달마다 빈 그릇을 하나씩 만들어 둔다. 표를 훑으면서 여기에 채운다.
    #   acc = {'2026-04': {빈 그릇}, '2026-05': {빈 그릇}, ...}
    acc = {}
    for m in months_keys:
        acc[m] = blank()
    # 누적 — 달을 더해서 만들지 않는다. 표의 합계/해외/국내 열을 그대로 담는다.
    sacc = blank()
    notes, extra = {}, []
    warnings, read = [], []
    label_cols = list(range(0, min(cols))) or [0]

    order, labels, keymap = [], {}, {}

    # 항목 이름 → 키. 모르는 이름도 그대로 받는다
    def item_key(label):
        n = _norm(label)
        if n in keymap:
            return keymap[n]
        key = _known_key(label)
        if key is None or key in order:
            key = "g%d" % (len(order) + 1)
        keymap[n] = key
        order.append(key)
        labels[key] = _txt(label)
        return key

    def note_path(target):
        t, arg = target
        if t == "item":
            return "item:%s:%s" % arg
        if t == "stock":
            return "stock:%s" % arg
        if t == "sum":
            return "sum:%s" % arg
        return t

    # 한 칸 넣기. region=None 이면 그 달, 아니면 누적의 그 지역.
    def put(bucket, target, v, region=None):
        t, arg = target
        if t == "sum":
            return                      # 합계 줄은 우리가 더해서 확인한다
        if t == "item":
            ikey, mkey = arg
            box = bucket["items"].setdefault(ikey, {})
            if region is None:
                box[mkey] = v
            else:
                box.setdefault(mkey, {})[region] = v
            return
        if t == "stock":
            box = bucket["stock"].setdefault(arg, {})
            if region is None:
                box["value"] = v
            else:
                box.setdefault("value", {})[region] = v
            return
        if region is None:
            bucket[t] = v
        else:
            cur = bucket.get(t)
            cur = cur if isinstance(cur, dict) else {}
            cur[region] = v
            bucket[t] = cur

    cur_item = None
    skip_group = False

    for ri in range(hi + 1, len(rows)):
        row = rows[ri]
        # -----------------------------------------------------------
        # 1. 이 줄의 라벨 조각들 (왼쪽 라벨 열들에서 글자만 모은다)
        # -----------------------------------------------------------
        #    줄이 짧아 그 열이 아예 없는 경우가 있어 길이를 먼저 본다.
        parts = []
        for j in label_cols:
            if j < len(row):
                t = _txt(row[j])
                if t:
                    parts.append(t)
        # -----------------------------------------------------------
        # 2. 달마다의 숫자 {'2026-04': 120, '2026-05': None, ...}
        # -----------------------------------------------------------
        vals = {}
        for j, m in cols.items():
            if j < len(row):
                vals[m] = _num(row[j])
            else:
                vals[m] = None
        # -----------------------------------------------------------
        # 3. 지역별 숫자 {'해외': 50, '국내': 70}
        # -----------------------------------------------------------
        regs = {}
        for r, j in regions.items():
            if j < len(row):
                regs[r] = _num(row[j])
            else:
                regs[r] = None
        note = (_note_txt(row[note_col])
                if (note_col is not None and note_col < len(row)) else "")
        # 비고 오른쪽에 적어 둔 메모(‘추가 분석 필요’ 목록 같은 것)도 챙긴다
        side = []
        if note_col is not None:
            for j in range(note_col + 1, len(row)):
                t = _note_txt(row[j])
                if t:
                    side.append(t)
        # -----------------------------------------------------------
        # 4. 라벨 조각에서 '묶음'과 '항목'을 가른다
        # -----------------------------------------------------------
        #    왼쪽부터 ['구매품', '출하대기'] 처럼 들어오면
        #    뒤에서 두 번째가 묶음, 마지막이 항목이다.
        group = None
        if len(parts) >= 2:
            group = parts[-2]
        metric = None
        if parts:
            metric = parts[-1]
        # -----------------------------------------------------------
        # 5. 이 줄에 숫자가 하나라도 있는가
        # -----------------------------------------------------------
        #    하나도 없으면 머리글이나 빈 줄이라 값으로 다루지 않는다.
        has_val = False
        for v in vals.values():
            if v is not None:
                has_val = True
                break
        if not has_val:
            for v in regs.values():
                if v is not None:
                    has_val = True
                    break

        def stash(*texts):
            for t in texts:
                for ln in [x for x in t.split("\n") if x.strip()] if t else []:
                    if ln not in extra and len(extra) < MAX_EXTRA:
                        extra.append(ln)

        stash(*side)
        if metric is None:
            stash(note)
            continue

        target = None
        sp = _special(metric)
        if sp:
            cur_item, skip_group = None, False
            target = sp if sp[0] == "stock" else (sp[0], None)
        else:
            if group is not None:
                skip_group = _is_skip(group)
                if skip_group:
                    cur_item = None
            if _is_skip(metric):
                stash(note)              # 재고 합계·지급 합계 줄 — 비고만
                continue
            if skip_group:
                mk = _metric(metric)
                if mk:
                    target = ("sum", mk)
                else:
                    stash(note)
                    continue
            else:
                if _match(metric, REVENUE):
                    target = ("revenue", None)
                if target is None:
                    for key, words in PAYMENT.items():
                        if _match(metric, words):
                            target = (key, None)
                            break
                if target is None:
                    mk = _metric(metric)
                    if mk:
                        if group is not None:
                            cur_item = item_key(group)
                        if cur_item:
                            target = ("item", (cur_item, mk))

        if target is None:
            if has_val:
                warnings.append("알 수 없는 줄: %s" % " ".join(parts)[:40])
            stash(note)
            continue
        if not has_val and not note:
            continue

        if target[0] == "ratio":
            # 비율은 저장하지 않는다 — 총매입액÷매출액으로 우리가 낸다.
            if note:
                notes.setdefault("ratio", note)
            continue

        for m, v in vals.items():
            if v is not None:
                put(acc[m], target, v)
        for r, v in regs.items():
            if v is not None:
                put(sacc, target, v, r)
        if note:
            notes.setdefault(note_path(target), note)
        read.append(" ".join(parts)[:40])

    def items_of(box):
        out = []
        for key in order:
            got = box.get(key)
            if not got:
                continue
            row = {"key": key, "label": labels.get(key, key)}
            for mk in ("buy", "paid", "balance"):
                row[mk] = got.get(mk)
            out.append(row)
        return out

    def stock_of(box):
        return [{"key": k, "value": v.get("value")}
                for k, v in box.items() if v.get("value") is not None]

    out = {}
    for m, mv in acc.items():
        items = items_of(mv["items"])
        stock = stock_of(mv["stock"])
        # 아무것도 안 들어온 달은 내보내지 않는다.
        # 품목도 없고 매출도 없고 재고도 없으면 그 달은 표에 없던 것이다.
        if not items and mv["revenue"] is None and not stock:
            continue
        one = {"revenue": mv["revenue"], "items": items,
               "prepaid": mv["prepaid"], "actual_paid": mv["actual_paid"],
               "invest": mv["invest"], "receivable": mv["receivable"],
               "total_buy": mv["total_buy"]}
        if stock:
            one["stock"] = stock
        out[m] = one

    if not out:
        raise ValueError("읽을 수 있는 숫자가 없습니다. 시트를 확인해 주세요.")
    # -----------------------------------------------------------
    # 누적(합계) 칸 만들기
    # -----------------------------------------------------------
    #    해외/국내 열이 있는 표에만 누적이 있다. 그 열이 없으면 만들지 않는다.
    summary = None
    s_items = items_of(sacc["items"])
    s_stock = stock_of(sacc["stock"])

    # 누적에 숫자가 하나라도 들어왔는지 본다
    has_side = False
    for k in ("revenue", "prepaid", "actual_paid", "invest",
              "receivable", "total_buy"):
        if sacc.get(k):
            has_side = True
            break

    if regions and (s_items or s_stock or has_side):
        summary = {"revenue": sacc["revenue"], "items": s_items,
                   "prepaid": sacc["prepaid"], "actual_paid": sacc["actual_paid"],
                   "invest": sacc["invest"], "stock": s_stock,
                   "receivable": sacc["receivable"], "total_buy": sacc["total_buy"],
                   "from": months_keys[0], "to": months_keys[-1],
                   "notes": dict(notes)}
        if extra:
            summary["notes"].setdefault("month", "\n".join(extra))

    return {"sheet": ws.title, "sheets": wb.sheetnames, "year": year,
            "months": out, "summary": summary,
            "regions": [r for r in ("total", "overseas", "domestic") if r in regions],
            "read": read, "warnings": warnings,
            "items": [{"key": k, "label": labels.get(k, k)} for k in order]}


# 엑셀에 없는 달은 그대로 둔다. 있는 달은 숫자를 통째로 바꾼다
def merge(old: dict, new: dict) -> dict:
    out = dict(old or {})
    for m, mv in (new or {}).items():
        mv = dict(mv or {})
        prev = out.get(m)
        # -----------------------------------------------------------
        # 비고는 새로 올린 파일에 없으면 예전 것을 지킨다
        # -----------------------------------------------------------
        #    비고는 사람이 손으로 적는 칸이라, 엑셀에 안 적혀 왔다고 해서
        #    지워 버리면 적어 둔 내용이 사라진다.
        keep_note = False
        if not mv.get("notes"):
            if isinstance(prev, dict) and prev.get("notes"):
                keep_note = True
        if keep_note:
            mv["notes"] = prev["notes"]
        out[m] = mv
    return out


# 누적도 숫자는 새 걸로, 비고는 합친다 (같은 줄이면 새 것).
def merge_summary(old, new):
    if not isinstance(new, dict):
        return old if isinstance(old, dict) else None
    out = dict(new)
    notes = dict((old or {}).get("notes") or {}) if isinstance(old, dict) else {}
    notes.update(out.get("notes") or {})
    if notes:
        out["notes"] = notes
    return out
