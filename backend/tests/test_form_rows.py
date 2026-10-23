# 양식의 적는 줄은 어느 프로젝트든 백 줄이고, 그 아래 붙이는 자리가 있다
#   python3 backend/tests/test_form_rows.py
#
# 프로젝트마다 모델 수가 달라서 빈 줄만 똑같이 여덟 줄씩 두면 전체 줄 수가
# 들쭉날쭉했다 — 파워박스는 90줄, 엔클로저는 22줄. 받는 쪽이 "어디까지가
# 적는 칸인가" 를 매번 다시 봐야 했다. 백 줄로 고정한다.
#
# 적는 칸에서 세 줄 띄운 아래에는 PPT 에 그대로 끌어 붙이는 표가 있다.
# 전부 수식이라 위에 한 번 적으면 따라온다. 빈 줄이 섞이면 복사해 붙였을
# 때 PPT 에 빈 줄이 그대로 따라가므로, 모델이 있는 줄만 둔다.
# 서버는 '합계' 글자에서 읽기를 멈추므로 그 아래 표는 올리는 데 영향이 없다.
#
# 이 시험이 막는 것
#   적는 줄 수가 다시 모델 수에 따라 달라지는 것.
#   아래 표가 적는 칸 **위로** 올라가 파서가 읽어 버리는 것.
#   아래 표에 빈 줄이 섞이는 것 · 손으로 적는 칸이 생기는 것.
import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]      # backend/
sys.path.insert(0, str(ROOT))

from openpyxl import load_workbook                      # noqa: E402
import plan_form                                        # noqa: E402
import pbx_plan_import as pbx                           # noqa: E402
import plan_block                                       # noqa: E402

ok = 0


def _models(n):
    return [{"name": "M%03d" % i, "part_number": "PN%03d" % i,
             "dev_type": "자동차", "group": "양산" if i % 2 else "개발",
             "price": 10, "material_cost": 4, "po_qty": 100,
             "shipped_qty": 50} for i in range(1, n + 1)]


def _sheet(n):
    b = plan_form.build_year_form("테스트", 2026, "2026-10", _models(n))
    wb = load_workbook(io.BytesIO(b))
    return wb["2026-10"], b, wb


def _find(ws, text):
    for r in range(1, ws.max_row + 2):
        if str(ws.cell(r, 1).value or "").strip() == text:
            return r
    return None


# ── 1. 모델이 몇 종이든 적는 줄은 백 줄 ──────────────────────
#   오늘 가장 많은 프로젝트가 파워박스 82종이라 백 줄이면 다 들어간다.
for n in (0, 1, 14, 82, 92):
    ws, _, wb = _sheet(n)
    r_sum = _find(ws, "합계")
    assert r_sum, "%d종 — 합계 줄이 없다" % n
    rows = r_sum - plan_form.FIRST_ROW
    # 빈 양식에는 예시 줄 몇 개와 '여기까지 예시' 안내가 위에 얹힌다.
    # 그건 적는 자리가 아니니 빼고 센다 (2026-10-22).
    extra = (len(plan_form.EXAMPLE) + 1) if n == 0 else 0
    assert rows - extra == plan_form.TOTAL_ROWS, \
        "%d종 — 적는 줄이 %d 줄 (백 줄이어야 한다)" % (n, rows - extra)
ok += 1
print("1. 모델 0 · 1 · 14 · 82 · 92 종 모두 적는 줄 100 줄 ✓")

# ── 2. 백 줄을 넘는 프로젝트는 그만큼 늘고 빈 줄은 늘 남는다 ──
#   빈 줄이 하나도 없으면 새 모델을 적을 자리가 없어진다.
for n in (99, 120):
    ws, _, wb = _sheet(n)
    rows = _find(ws, "합계") - plan_form.FIRST_ROW
    want = max(plan_form.TOTAL_ROWS, n + plan_form.MIN_SPARE)
    assert rows == want, "%d종 — %d 줄 (%d 줄이어야 한다)" % (n, rows, want)
    assert rows - n >= plan_form.MIN_SPARE, "%d종 — 빈 줄이 모자란다" % n
ok += 1
print("2. 모델 99 · 120종 — 모델 줄 + 빈 줄 %d 줄 이상 ✓"
      % plan_form.MIN_SPARE)

# ── 3. PPT 표는 **다음 장**에 있다 ──────────────────────────
#   2026-10-22 — 적는 장 아래에 붙여 두다가 장을 나눴다. CUP ·
#   하바플레이트처럼 모델이 많으면 적는 칸만으로 한 장을 다 쓴다.
ws, _, wb = _sheet(14)
r_sum = _find(ws, "합계")
r_note = _find(ws, "미달 사유")
# 2026-10-22 — 프로젝트 현황이 **맨 위**로 올라갔다. 백 줄을 내려가야
# 보이던 것을 제목 바로 밑에 둔다 — 먼저 볼 것이 먼저 있어야 한다.
r_proj = _find(ws, plan_form.PROJ_LABEL)
assert r_proj == plan_form.ROW_PROJ, \
    "프로젝트 현황이 %s 줄에 있다 (%d 줄이어야 한다)" % (r_proj, plan_form.ROW_PROJ)
assert r_proj < plan_form.FIRST_ROW < r_sum < r_note, "자리 순서가 틀렸다"
assert plan_block.SHEET_NAME in wb.sheetnames, \
    "'%s' 장이 없다: %r" % (plan_block.SHEET_NAME, wb.sheetnames)
blk = wb[plan_block.SHEET_NAME]
assert plan_block.TITLE_MARK in str(blk.cell(1, 1).value or ""), \
    "둘째 장 첫 줄이 PPT 표 제목이 아니다"
# 적는 장에는 그 표가 남아 있으면 안 된다
left = [r for r in range(1, ws.max_row + 1)
        if plan_block.TITLE_MARK in str(ws.cell(r, 1).value or "")]
assert not left, "적는 장에 PPT 표가 그대로 남아 있다: %r" % left
ok += 1
print("3. PPT 표가 '%s' 장으로 빠졌다 (적는 장에는 없음) ✓"
      % plan_block.SHEET_NAME)

# ── 3-2. 둘째 장에는 빈 줄이 없다 — 모델 줄 + 합계 줄뿐 ─────
#   14종을 양산 · 개발로 번갈아 넣었으니 14줄 + 묶음 합계 2줄 + 총 합계 1줄.
r0 = 5                                   # 제목 1 + 머리글 3 다음
tail = []
for rr in range(r0, blk.max_row + 1):
    a = str(blk.cell(rr, 1).value or "").strip()
    b2 = str(blk.cell(rr, 2).value or "").strip()
    if not a and not b2:
        break                            # 맨 아래 안내 줄 앞에서 끊는다
    tail.append((a, b2))
assert len(tail) == 14 + 3, "둘째 장이 %d 줄 (17줄이어야 한다)" % len(tail)
assert [t[0] for t in tail if t[0]][:1] == ["양산"], "양산 묶음이 먼저여야 한다"
assert tail[-1][0] == "총 합계", "맨 아래가 총 합계가 아니다"
ok += 1
print("3-2. 둘째 장 %d 줄 — 빈 줄 없음 · 양산 → 개발 · 총 합계 ✓" % len(tail))

# ── 3-3. 둘째 장 칸은 전부 수식이고 적는 장을 가리킨다 ──────
hand = []
for rr in range(r0, r0 + len(tail)):
    # 합계 줄은 제 장 안의 줄을 더한다 — 적는 장을 가리키지 않는다
    if str(blk.cell(rr, 1).value or "").strip() in ("합계", "총 합계"):
        continue
    for cc in range(2, 7):
        v = blk.cell(rr, cc).value
        if v is None:
            continue
        if not str(v).startswith("="):
            hand.append((rr, cc, v))
        elif "'2026-10'!" not in str(v):
            hand.append((rr, cc, "적는 장을 안 가리킨다"))
assert not hand, "수식이 아니거나 엉뚱한 곳을 본다 — %r" % hand[:3]
ok += 1
print("3-3. 둘째 장이 전부 '2026-10' 장을 가리키는 수식 ✓")

# ── 4. 둘째 장에 무엇을 적어도 파서는 안 읽는다 ─────────────
#   그 장은 전부 수식이라 적는 장과 같은 숫자를 들고 있다. 읽으면 같은
#   달이 두 번 들어와 실적이 두 배로 보인다.
ws, raw, wb = _sheet(14)
import week_calendar as wc                              # noqa: E402
oct_weeks = set(wc.get_month_weeks("2026-10") or [])
wcol = next(c for c in range(1, ws.max_column + 1)
            if str(ws.cell(plan_form.HDR_WEEK, c).value or "").strip()
            in oct_weeks)
for rr in range(plan_form.FIRST_ROW, plan_form.FIRST_ROW + 14):
    ws.cell(rr, wcol, 10)
buf = io.BytesIO()
wb.save(buf)
wb2 = load_workbook(io.BytesIO(buf.getvalue()), data_only=True)
months = pbx.sheet_months(wb2)
assert [g["sheet"] for g in months] == ["2026-10"], \
    "읽은 장이 둘 이상이다: %r" % [(g["sheet"], g["month"]) for g in months]
assert months[0]["rows"] == 14, "읽은 줄 %d" % months[0]["rows"]
ok += 1
print("4. 둘째 장은 읽지 않는다 — 읽은 장 '2026-10' 하나, %d 줄 ✓"
      % months[0]["rows"])

print("전부 통과 · %d 가지" % ok)
