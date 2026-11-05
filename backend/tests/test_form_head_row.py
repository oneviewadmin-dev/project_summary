# 머리글 줄을 어디까지 찾나 (2026-11-02)
#   python3 backend/tests/test_form_head_row.py
#
# Min: "자동차사업부에 이 시트 인식을 못 하는 이유가 뭐야"
#      → "읽을 품목이 없습니다 ... 읽은 시트: 고객사별 품목정보"
#
# 머리글('No.' 줄)을 **12줄까지만** 찾았다. 자동차 양식은 머리글이 15행이다 —
# 위에 영문 머리글 한 벌(Part Name · Part Number …)과 기준환율 표
# (1 USD = 1350 · 25850 · 0.8911)가 먼저 서 있다. 그래서 품목 1,000줄짜리
# 파일이 통째로 "읽을 품목이 없습니다" 로 끊겼다.
#
# 줄 수는 앞으로도 는다(안내 문구 한 줄, 환율 한 줄…). 그래서 넉넉히 보되
# **같은 줄에 고객사·프로젝트나 파트넘버가 같이 있어야** 머리글로 인정한다.
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FORMS = ROOT / 'tests' / 'forms' / 'v2'

import openpyxl                         # noqa: E402
import division_form_import as dfi      # noqa: E402
ok = 0


def sheet(rows):
    """rows: [(행번호, [(열번호, 값)])] 로 지어 낸 가짜 시트."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for r, cells in rows:
        for c, v in cells:
            ws.cell(r, c, v)
    return ws


# ── 1. 머리글이 15행이어도 찾는다 ─────────────────────────────────
ws = sheet([
    (9, [(5, 'Part Name'), (6, 'Part Number'), (7, 'Classification')]),
    (13, [(8, '기준환율'), (9, 'KRW')]),
    (14, [(8, '1 USD ='), (9, 1350)]),
    (15, [(3, 'No.'), (4, '고객사'), (5, '품목 (있을 시)'), (6, '파트넘버')]),
])
assert dfi._find_header_row(ws) == 15, dfi._find_header_row(ws)
ok += 1

# ── 2. 이름 칸이 없는 'No.' 줄에 먼저 걸리지 않는다 ───────────────
# 표 한가운데 'No.' 한 글자가 끼어든 줄을 머리글로 잡으면 그 아래를
# 통째로 못 읽는다.
ws = sheet([
    (3, [(2, 'No.')]),                       # 이름 칸이 없는 줄
    (7, [(3, 'No.'), (4, '프로젝트'), (6, '파트넘버')]),
])
assert dfi._find_header_row(ws) == 7, dfi._find_header_row(ws)
ok += 1

# ── 3. 'No.' 줄뿐이면 그거라도 쓴다 (옛 양식 대비) ────────────────
ws = sheet([(4, [(2, 'No.')])])
assert dfi._find_header_row(ws) == 4
ok += 1

# ── 4. 아예 없으면 None ───────────────────────────────────────────
assert dfi._find_header_row(sheet([(1, [(2, '안내')])])) is None
ok += 1

# ── 5. 실제 양식들이 그대로 읽히는가 ──────────────────────────────
CASES = [
    ('자동차_양식_20261027.xlsx', 'automotive', 164, '2026-10', 4),
    ('블룸_주차별_2026-10.xlsx', 'bloom', 87, '2026-10', 4),
    ('반도체_CUP_실제_1023.xlsx', 'semiconductor', None, None, None),
    ('ESS_실제_2026-10.xlsx', 'ess', None, None, None),
]
for name, div, items, month, weeks in CASES:
    f = FORMS / name
    if not f.exists():
        continue
    g = dfi.parse_workbook(openpyxl.load_workbook(f, data_only=True), div)
    assert g['items'], '%s: 품목을 한 건도 못 읽었다 — %r' % (name, g['warnings'])
    if items is not None:
        assert len(g['items']) == items, \
            '%s: 품목 %d건이어야 하는데 %d건' % (name, items, len(g['items']))
    if month:
        assert g['month'] == month, '%s: 달이 %r' % (name, g['month'])
    if weeks:
        assert len(g['weeks']) == weeks, '%s: 주차가 %r' % (name, g['weeks'])
    ok += 1

print('ok %d' % ok)
