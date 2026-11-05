# 머리글이 영어인 양식도 읽는다 (2026-11-03)
#   python3 backend/tests/test_form_english_head.py
#
# Min: "파워박스 이거 올릴려고 했는데 ... 읽을 품목이 없습니다
#      양식의 예시) 줄은 일부러 건너뜁니다 — 그 밑에 실제 품목을 적어 주세요"
#
# 실제로는 예시 줄 문제가 아니었다. 그 양식은 머리글이 영어였다 —
#     No. · Project · P/N · Model Name · FA / HVM · Unit Price ·
#     Material Cost · EAU
# 한글 말만 알고 있어서 '프로젝트' 열을 못 찾았고, 품목을 어디에 붙일지
# 모르니 한 줄도 못 읽었다. 그런데 화면에는 '예시) 줄은 건너뜁니다' 만
# 떠서, 적은 사람은 엉뚱한 데를 고치게 된다.
#
# 사업부마다 쓰던 양식이 달라서 앞으로도 섞여 들어온다. 같은 칸을
# 가리키는 말을 한글 · 영어 둘 다 받아 둔다.
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


import division_form_import as D

# ── 1. 말 목록 ──────────────────────────────────────────────────
for w, words, what in (
        ('project', D.OWNER_WORDS, '프로젝트'),
        ('p/n', D.PN_WORDS, '파트넘버'),
        ('model name', D.NAME_WORDS, '모델명'),
        ('fa / hvm', D.GROUP_WORDS, '구분'),
        ('unit price', D.PRICE_WORDS, '판가'),
        ('material cost', D.MATERIAL_WORDS, '재료비'),
        ('eau', D.YEAR_WORDS, '연간수량')):
    ok(any(D._key(x) in D._key(w) for x in words),
       "'%s' 를 %s 로 못 알아본다" % (w, what))
# 한글은 그대로 남아 있어야 한다
for w, words in (('프로젝트', D.OWNER_WORDS), ('파트넘버', D.PN_WORDS),
                 ('모델명', D.NAME_WORDS), ('구분', D.GROUP_WORDS),
                 ('판가', D.PRICE_WORDS), ('재료비', D.MATERIAL_WORDS)):
    ok(any(D._key(x) in D._key(w) for x in words), "'%s' 가 사라졌다" % w)

# ── 2. 실제 파일 ────────────────────────────────────────────────
import openpyxl
FX = ROOT / 'tests' / 'forms' / 'v2' / '반도체_양식_PBX_1030.xlsx'
if FX.exists():
    g = D.parse_workbook(openpyxl.load_workbook(FX, data_only=True),
                         'semiconductor')
    items = g.get('items') or []
    ok(len(items) == 23, '품목이 %d개다 (23개여야 한다)' % len(items))
    ok(g.get('sheet') == '프로젝트별 품목정보', '시트를 잘못 골랐다')
    _one = {i['part_number']: i for i in items}
    ok('925-800083-394' in _one, '첫 품목을 못 읽었다')
    _a = _one.get('925-800083-394') or {}
    ok(_a.get('owner') == 'PBX', '프로젝트를 못 읽었다: %r' % _a.get('owner'))
    ok(_a.get('name') == 'Aether - GDX', '모델명을 못 읽었다')
    ok(_a.get('group') == '양산', '구분(FA / HVM)을 못 읽었다: %r' % _a.get('group'))
    ok(abs(float(_a.get('price') or 0) - 6688.66) < 0.01, '판가를 못 읽었다')
    ok(abs(float(_a.get('material_cost') or 0) - 5096.54) < 0.01, '재료비를 못 읽었다')
    ok(int(_a.get('year_qty') or 0) == 3255, '연간수량(EAU)을 못 읽었다')
    # 주차도 같이 읽혀야 한다 — 품목만 읽고 주차를 흘리면 계획이 빈다
    wk = _a.get('weeks') or {}
    ok(wk.get('W40', {}).get('plan') == 20, '주차 계획을 못 읽었다: %r' % wk)
    ok(len(wk) == 5, '주차가 %d칸이다 (W40~W44 다섯 칸)' % len(wk))
    # 개발도 섞여 있다
    _grp = [i.get('group') for i in items]
    ok(_grp.count('개발') == 4, "개발이 %d개다 (4개)" % _grp.count('개발'))
    # 예시) 가 붙은 줄에 진짜 품목이 적혀 있었다. 버리지 말고 알린다 —
    # 조용히 빼면 한 품목이 사라진 걸 아무도 모른다.
    ok(any('예시' in w for w in (g.get('warnings') or [])),
       "'예시)' 줄을 읽었다는 말이 없다")
else:
    print('(파워박스 양식 없음 — 파일 검사는 건너뜀)')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 영어 머리글 양식')
