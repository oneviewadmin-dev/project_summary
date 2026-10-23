# 시트 보호 — 지금은 꺼 두었다
#   python3 backend/tests/test_form_protect.py
#
# 수식 칸(잔량 · 월 합계 · 합계 줄 · 맨 아래 PPT 표)을 손으로 덮어쓰면 그
# 줄만 조용히 틀린 숫자가 된다. 그래서 한 번 잠가 봤는데, 쓰는 쪽에서
# 시트 보호가 거치적거린다는 말이 나와 껐다 (2026-10-22).
#
# 끄는 것과 코드를 지우는 것은 다른 일이다. 가르는 셈(여는 칸 · 잠그는
# 칸)은 그대로 두고 PROTECT_SHEET 한 줄로만 끈다 — 다시 켜야 할 때
# 처음부터 만들지 않아도 되고, 켜면 바로 맞는 자리가 잠긴다.
#
# 이 시험이 막는 것
#   꺼 둔다고 하고 보호가 걸린 파일이 나가는 것.
#   되돌릴 자리(PROTECT_SHEET · _protect)가 통째로 사라지는 것.
#   다시 켰을 때 적는 칸이 잠기거나 수식 칸이 열려 있는 것.
import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]      # backend/
sys.path.insert(0, str(ROOT))

from openpyxl import load_workbook                      # noqa: E402
from openpyxl.utils import get_column_letter as L       # noqa: E402
import plan_form as pf                                  # noqa: E402


# 2026-10-22 — 머리글 앞에 '✎'(적는 칸) · '='(자동 계산) 표가 붙는다.
# 비교할 때는 떼고 본다. 읽는 쪽(_head_key · _plan_sheet_models)도 같다.
def _hk(v):
    return str(v or "").strip().strip("✎=＝*※·•-–— \t").strip()


ok = 0
MS = [{"part_number": "PN%03d" % i, "name": "M%03d" % i, "dev_type": "자동차",
       "group": "양산" if i % 2 else "개발", "price": 10, "material_cost": 4,
       "po_qty": 100, "shipped_qty": 50} for i in range(1, 6)]

raw = pf.build_year_form("테스트", 2026, "2026-10", MS,
                         status_note="홀딩", hold="보류")
wb = load_workbook(io.BytesIO(raw))
ws = wb["2026-10"]


def is_open(ref):
    c = ws[ref]
    return bool(c.protection) and c.protection.locked is False


def find(text):
    for r in range(1, ws.max_row + 1):
        if str(ws.cell(r, 1).value or "").strip() == text:
            return r
    return None


# ── 1. 지금은 보호가 꺼져 있다 ───────────────────────────────
assert pf.PROTECT_SHEET is False, "PROTECT_SHEET 가 켜져 있다"
assert not ws.protection.sheet, "시트 보호가 걸린 파일이 나간다"
assert not wb["작성 안내"].protection.sheet, "작성 안내 장이 잠겼다"
marks = [c.coordinate for row in ws.iter_rows() for c in row
         if c.protection and c.protection.locked is False]
assert not marks, \
    "꺼 뒀는데 칸 잠금 표시가 남아 있다 (%d개) — 나중에 누가 보호를 켜면 " \
    "절반만 잠긴 파일이 된다" % len(marks)
ok += 1
print("1. 시트 보호 꺼짐 · 칸 잠금 표시도 안 남는다 ✓")

# ── 2. 되돌릴 자리가 그대로 있다 ─────────────────────────────
src = (ROOT / "plan_form.py").read_text(encoding="utf-8")
assert "def _protect(ws, open_cells):" in src, "_protect 가 사라졌다"
assert "if not PROTECT_SHEET:" in src, "스위치로 끄게 되어 있지 않다"
assert "_protect(ws, _open)" in src, "부르는 자리가 사라졌다"
ok += 1
print("2. PROTECT_SHEET 한 줄로 다시 켤 수 있다 ✓")

# ── 3. 다시 켜면 맞는 자리가 잠긴다 ──────────────────────────
#   꺼 두는 동안 가르는 셈이 썩지 않게 여기서 계속 확인한다.
pf.PROTECT_SHEET = True
try:
    raw2 = pf.build_year_form("테스트", 2026, "2026-10", MS,
                              status_note="홀딩", hold="보류")
finally:
    pf.PROTECT_SHEET = False
w2 = load_workbook(io.BytesIO(raw2))["2026-10"]


def is_open(ref):
    c = w2[ref]
    return bool(c.protection) and c.protection.locked is False


def find(text):
    for r in range(1, w2.max_row + 1):
        if str(w2.cell(r, 1).value or "").strip() == text:
            return r
    return None


assert w2.protection.sheet, "켰는데 보호가 안 걸린다"
assert not w2.protection.password, "암호를 걸었다 — 나중에 아무도 못 연다"
assert w2.protection.selectLockedCells, \
    "잠긴 칸을 고를 수 없다 — PPT 표를 복사 못 한다"

r_sum = find("합계")
r_end = r_sum - 1
head = {_hk(w2.cell(pf.HDR_TOP, c).value): c for c in range(1, 14)}
wk = [c for c in range(1, w2.max_column + 1)
      if _hk(w2.cell(pf.HDR_WEEK, c).value).startswith("W")]
r_proj = find(pf.PROJ_LABEL)
openers = [
    ("파트넘버", "%s%d" % (L(head["파트넘버"]), pf.FIRST_ROW)),
    ("구분", "%s%d" % (L(head["구분"]), pf.FIRST_ROW)),
    ("판가($)", "%s%d" % (L(head["판가($)"]), pf.FIRST_ROW)),
    ("PO수량", "%s%d" % (L(head["PO수량"]), pf.FIRST_ROW)),
    ("개발→양산 전환주차", "%s%d" % (L(head["개발→양산 전환주차"]), pf.FIRST_ROW)),
    ("비고", "%s%d" % (L(head["비고"]), pf.FIRST_ROW)),
    ("첫 주차 계획", "%s%d" % (L(wk[0]), pf.FIRST_ROW)),
    ("첫 주차 실적", "%s%d" % (L(wk[0] + 1), pf.FIRST_ROW)),
    ("맨 아래 빈 줄", "%s%d" % (L(1), r_end)),
    ("미달 사유 주차", "%s%d" % (L(wk[0]), find("미달 사유"))),
    ("프로젝트 상태", "B%d" % (r_proj + 1)),
    ("프로젝트 현황 글", "C%d" % (r_proj + 1)),
]
shut = [n for n, ref in openers if not is_open(ref)]
assert not shut, "적는 칸이 잠겼다: %r" % shut

tot = [c for c in range(1, w2.max_column + 1)
       if _hk(w2.cell(pf.HDR_WEEK, c).value) == "월 합계"]
# PPT 표는 다음 장으로 빠졌다 (2026-10-22)
locked = [
    ("잔량", "%s%d" % (L(head["잔량"]), pf.FIRST_ROW)),
    ("월 합계 계획", "%s%d" % (L(tot[0]), pf.FIRST_ROW)),
    ("월 합계 실적", "%s%d" % (L(tot[0] + 1), pf.FIRST_ROW)),
    ("합계 줄", "%s%d" % (L(head["PO수량"]), r_sum)),
    ("머리글", "A2"),
]
leak = [n for n, ref in locked if is_open(ref)]
assert not leak, "수식 칸이 열려 있다: %r" % leak
ok += 1
print("3. 다시 켜면 적는 칸 %d 자리 열림 · 수식 칸 %d 자리 잠김 ✓"
      % (len(openers), len(locked)))

print("전부 통과 · %d 가지" % ok)
