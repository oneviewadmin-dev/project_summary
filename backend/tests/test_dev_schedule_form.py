# 품목별 개발 일정 양식 읽기 (2026-10-28)
#   python3 backend/tests/test_dev_schedule_form.py
#
# Min: "참고로 저 양식대로 개발 업로드 될거라 미리 세팅 부탁할게"
#
# 한 품목이 세 줄이다 — 프로세스 · 계획 · 실적.
#
#   No. | 프로젝트 | 파트넘버 | 개발 담당 주재원 | 구분     | 단계 1  | 단계 2 | …
#    1  | SS8     | 881400  |                | 프로세스  | PO 발주 | PRP   | …
#    1  | SS8     | 881400  |                | 계획      | 날짜    |       | …
#    1  | SS8     | 881400  |                | 실적      |        |       | …
#
# 단계 개수는 사업부마다 다르다 — 반도체 13 · 메이저모듈 12 · 블룸 3.
# 그래서 **머리글에 '단계 N' 이 적힌 만큼** 읽는다. 13 을 박아 두면
# 14번째가 생긴 날 조용히 잘린다 (docs/엑셀_읽는_규칙.md).
import ast, datetime as dt, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
HTML = (ROOT / 'admin_v2.html').read_text(encoding='utf-8')

import dev_schedule_import as dsi      # noqa: E402
import openpyxl                        # noqa: E402
ok = 0
TMP = pathlib.Path(tempfile.mkdtemp(prefix='devsch_'))


def build(nstep, rows, name='t.xlsx'):
    """머리글 nstep 칸짜리 양식을 지어 낸다."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws['C2'] = '품목별 개발 일정'
    head = ['No.', '프로젝트', '파트넘버', '개발 담당 주재원', '구분'] + \
           ['단계 %d' % (i + 1) for i in range(nstep)]
    for i, h in enumerate(head):
        ws.cell(4, 2 + i, h)
    r = 5
    for no, (proj, pn, names, plan, act) in enumerate(rows, 1):
        for kind, vals in (('프로세스', names), ('계획', plan), ('실적', act)):
            ws.cell(r, 2, no); ws.cell(r, 3, proj)
            ws.cell(r, 4, pn); ws.cell(r, 6, kind)
            for j, v in enumerate(vals):
                if v is not None:
                    ws.cell(r, 7 + j, v)
            r += 1
    p = TMP / name
    wb.save(p)
    return p


def read(p):
    return dsi.parse_workbook(openpyxl.load_workbook(p, data_only=True))


# ── 1. 단계 개수를 외워 두지 않는다 ───────────────────────────────
for n in (1, 3, 13, 20, 30):
    g = read(build(n, [('A', 'P', ['s%d' % i for i in range(1, n + 1)],
                        [None] * n, [None] * n)], 't%d.xlsx' % n))
    got = len(g['items'][0]['steps'])
    assert got == n, '단계 %d칸 양식에서 %d개만 읽었다' % (n, got)
ok += 1

# ── 2. 머리글은 13칸인데 세 단계만 쓰는 양식 ──────────────────────
# 블룸이 그렇다. 빈 이름을 단계로 세면 화면에 빈 칸이 열 개 늘어선다.
g = read(build(13, [('B', 'P2', ['PO 발주', 'PRP', '최종 승인'] + [None] * 10,
                     [dt.datetime(2026, 10, 1), None, None] + [None] * 10,
                     [None] * 13)], 'short.xlsx'))
it = g['items'][0]
assert [s['name'] for s in it['steps']] == ['PO 발주', 'PRP', '최종 승인'], \
    [s['name'] for s in it['steps']]
assert it['steps'][0]['expected'] == '2026-10-01'
ok += 1

# ── 3. 빈 칸은 '안 적음' 이다 (0 도 글자도 아니다) ─────────────────
# 빈 문자열로 덮으면 한 칸만 고쳐 올린 엑셀이 나머지 날짜를 전부 지운다.
assert it['steps'][1]['expected'] is None and it['steps'][0]['actual'] is None
ok += 1

# ── 4. 날짜가 글자로 와도 읽는다 ──────────────────────────────────
g = read(build(3, [('C', 'P3', ['a', 'b', 'c'],
                    ['2026-10-05', '2026/10/06', ''],
                    ['', '2026.10.07', '몰라'])], 'text.xlsx'))
st = g['items'][0]['steps']
assert [s['expected'] for s in st] == ['2026-10-05', '2026-10-06', None], st
assert [s['actual'] for s in st] == [None, '2026-10-07', None], st
ok += 1

# ── 5. 프로세스 줄 없이 날짜만 오면 버리고 알린다 ─────────────────
wb = openpyxl.Workbook(); ws = wb.active
ws['C2'] = '품목별 개발 일정'
for i, h in enumerate(['No.', '프로젝트', '파트넘버', '개발 담당 주재원', '구분', '단계 1']):
    ws.cell(4, 2 + i, h)
ws.cell(5, 2, 1); ws.cell(5, 3, 'D'); ws.cell(5, 4, 'P4')
ws.cell(5, 6, '계획'); ws.cell(5, 7, dt.datetime(2026, 1, 1))
wb.save(TMP / 'orphan.xlsx')
g = read(TMP / 'orphan.xlsx')
assert g['items'] == [], '프로세스 줄 없이 날짜만 있는 줄을 품목으로 셌다'
assert g['warnings'], '왜 안 들어갔는지 안 알린다'
ok += 1

# ── 6. 실제 파일 두 장 ────────────────────────────────────────────
FIX = ROOT / 'tests' / 'forms' / 'v2'
for name, items, smax in (('개발일정_반도체.xlsx', 309, 13),
                          ('개발일정_블룸.xlsx', 3, 3)):
    f = FIX / name
    if not f.exists():
        continue
    g = read(f)
    assert len(g['items']) == items, \
        '%s: 품목을 %d건 읽어야 하는데 %d건' % (name, items, len(g['items']))
    assert g['steps_max'] == smax, '%s: 머리글 단계가 %r' % (name, g['steps_max'])
    assert not g['warnings'], '%s: %r' % (name, g['warnings'])
    ok += 1
# 반도체 파일에는 12단계짜리(메이저모듈)가 섞여 있다 — 한 장에 섞여도 읽어야 한다
f = FIX / '개발일정_반도체.xlsx'
if f.exists():
    g = read(f)
    sizes = {len(i['steps']) for i in g['items']}
    assert sizes == {12, 13}, '한 장 안에서 단계 수가 섞인 걸 못 읽는다: %r' % sizes
    ok += 1

# ── 7. 단계 열쇠 ─────────────────────────────────────────────────
G = {}
for n in ast.parse(SRC).body:
    if isinstance(n, ast.FunctionDef) and n.name == '_ds_key':
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
k = G['_ds_key']
assert k('FA PO') == 'fa_po', k('FA PO')          # 영문은 보던 그대로
# 한글이 섞이면 영문만 남겨서는 구별이 안 된다 — 'PO 발주' 와 'PO 승인'
assert k('PO 발주') != k('PO 승인'), '다른 단계가 같은 열쇠가 된다'
assert k('PO 발주') == k('PO 발주'), '같은 이름인데 열쇠가 달라진다'
assert k('') and k('최종 승인'), '열쇠가 빈 글자다'
ok += 1

# ── 8. 창구와 화면 ───────────────────────────────────────────────
assert '/dev-schedule/preview' in SRC and '/dev-schedule/apply' in SRC, '올릴 창구가 없다'
assert 'def _ds_plan(' in SRC, '미리보기가 무엇이 붙는지 안 따져 본다'
# 양식에 없는 품목은 안 건드린다 — 한 프로젝트만 올려도 나머지가 살아야 한다
_ap = SRC[SRC.index('async def admin_dev_schedule_apply'):]
_ap = _ap[:_ap.index('\ndef _ds_key')]
assert 'for it in got["items"]:' in _ap, '양식 줄만 돌지 않는다'
assert 'm["process"] = proc' in _ap, '공정을 안 붙인다'
# 같은 이름 단계에 적혀 있던 날짜는 따라가야 한다
assert 'prev = old.get(nm) or {}' in _ap, '옛 날짜를 안 이어받는다'
assert 'step_changed' in _ap, '단계가 바뀐 것을 안 알린다'
ok += 1
assert 'xl-opt-dev' in HTML and 'window._devSend' in HTML, 'admin 에 올리는 자리가 없다'
assert '없는 품목은 건드리지 않습니다' in HTML, '무엇이 안 바뀌는지 안 알린다'
assert '이름이 없어진 단계의 날짜는 사라집니다' in HTML, \
    '단계가 바뀔 때 날짜가 사라질 수 있다는 걸 안 알린다'
ok += 1

import shutil                           # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
# ── 9. 자동차 개발 일정 (2026-11-02) ─────────────────────────────
#
# Min: "· 9행: '계획' 줄 위에 프로세스 줄이 없습니다 ( · 9109020119) …"
#      (같은 경고가 60줄 넘게) "이거 뭔소리야..."
#
# 세 가지가 겹쳤다.
#   1) 머리글 첫 칸이 '고객사' 다. '프로젝트' 만 받아서 그 칸이 빈 글자가
#      됐다 — 경고에 프로젝트 이름이 안 찍힌 게 그 자국이다.
#   2) **프로세스 줄에만 품번 뒤에 설명이 붙어 온다.**
#        8행 프로세스  9109020119 (VCU BASE)
#        9행 계획      9109020119
#      글자 그대로 맞추니 계획·실적 줄이 제 프로세스 줄을 못 찾았다.
#   3) 날짜가 '2025. 11. 30' 처럼 점 뒤에 공백이 붙어 온다.
assert dsi.pn_key('9109020119 (VCU BASE)') == dsi.pn_key('9109020119'), \
    '괄호 뒤 설명 때문에 같은 품번이 다르게 보인다'
assert dsi.pn_key(' aaa-955 ') == dsi.pn_key('AAA955'), '공백·기호·대소문자를 안 턴다'
ok += 1
# 'PART NO :' 처럼 칸 이름이 앞에 붙으면 괄호 앞이 빈다 — 그때는 칸 전체로 가린다
a = dsi.pn_key('PART NO : \n(SX3_1900 WP 2P HVS BLOCK_MOBIS)')
b = dsi.pn_key('PART NO : \n(SX3_1900 WP 2P HVS BLOCK_KAPEC)')
assert a and b and a != b, '서로 다른 품목이 같은 열쇠가 된다: %r / %r' % (a, b)
ok += 1
# 날짜 안의 공백
assert dsi._date('2025. 11. 30') == '2025-11-30', dsi._date('2025. 11. 30')
assert dsi._date('2027.05.17') == '2027-05-17'
ok += 1

f = FIX / '개발일정_자동차.xlsx'
if f.exists():
    g = read(f)
    assert len(g['items']) == 38, '품목 38건이어야 하는데 %d건' % len(g['items'])
    assert not g['warnings'], g['warnings'][:3]
    n = sum(1 for i in g['items'] for s in i['steps'] if s['expected'] or s['actual'])
    assert n == 139, '날짜 칸 139개여야 하는데 %d개' % n
    # 첫 칸이 '고객사' 여도 읽어야 한다
    assert all(i['project'] for i in g['items']), '고객사 칸이 비었다'
    hit = [i for i in g['items'] if i['part_number'].startswith('9109020119')][0]
    got = {s['name']: (s['expected'], s['actual']) for s in hit['steps']}
    assert got['03 P1 [Pilot]'] == ('2025-11-30', '2025-11-30'), got['03 P1 [Pilot]']
    assert got['06 SOP'] == ('2026-10-15', '2026-10-15'), got['06 SOP']
    assert got['01 T-car'] == (None, None), '빈 칸을 날짜로 읽었다'
    ok += 1

print('ok %d' % ok)

# ── 개발 담당 주재원을 품목에 남긴다 (2026-11-02) ────────────────
# Min: "개발 담당 주재원도 보이게끔 해줘"
#
# 양식의 '개발 담당 주재원' 칸은 읽고 있었지만(parse 의 owner) 저장을
# 안 해서, 올릴 때마다 읽고 버렸다. 화면에 띄우려면 품목에 남아야 한다.
import pathlib as _pl
_SRC = (_pl.Path(__file__).resolve().parents[1] / 'main.py').read_text(encoding='utf-8')
_i = _SRC.find('async def admin_dev_schedule_apply')
_body = _SRC[_i:_SRC.find('def _ds_key(', _i)]
assert 'm["dev_owner"] = _own' in _body, '올려도 담당이 저장되지 않는다'
# 빈 칸은 '안 적음' 이다. 담당 칸을 비워 올린 파일이 적어 둔 담당을
# 지워 버리면 안 된다 — 엑셀 빈 칸 규칙(docs/엑셀_읽는_규칙.md).
assert 'if _own:' in _body, '담당 빈 칸이 적어 둔 담당을 지운다'
# 앱·admin 이 읽으려면 상세에 실려야 한다
assert '"dev_owner"' in _SRC[_SRC.find('out = {k: m.get(k) for k in ("id"'):][:400], '상세(_enrich_model)에 담당이 안 실린다'
print('ok — 개발 담당 주재원 저장')

# ── 날짜가 아닌 칸을 버리지 않는다 (2026-11-02) ──────────────────
# Min: "엑셀에는 내용 다 적혀져 있고 날짜도 작성 되어 있는데 왜 적용을
#      못 하는거야 / 계획 대비 실적도 못 찾고 뭐야"
#
# 올려 준 블룸 양식을 열어 보니 칸에 날짜만 오는 게 아니었다 —
#   '고객사 검토중'   아직 날짜를 못 잡은 단계
#   'PO 완료'         날짜 없이 끝난 단계
#   '2026-06-31'      6월 31일. 없는 날짜다 (오타)
# 셋 다 소리 없이 사라졌고, 그런데도 경고는 0건이었다. 그게 제일 나빴다.
import openpyxl as _ox
_FX = _pl.Path(__file__).resolve().parent / 'forms' / 'v2' / '개발일정_블룸_채움.xlsx'
if _FX.exists():
    import dev_schedule_import as _dsi
    _g = _dsi.parse_workbook(_ox.load_workbook(_FX, data_only=True))
    _by = {it['part_number']: {s['name']: s for s in it['steps']}
           for it in _g['items']}

    # 글자가 살아 있나
    assert _by['881400']['PO 발주']['expected_note'] == '고객사 검토중', \
        "'고객사 검토중' 이 사라졌다"
    assert _by['126391']['PO 발주']['expected_note'] == 'PO 완료', \
        "'PO 완료' 가 사라졌다"
    # 날짜는 그대로 날짜로
    assert _by['126391']['PRP']['expected'] == '2026-06-01'
    assert _by['126391']['PRP']['actual'] == '2026-06-01'
    assert _by['881400']['PRP']['expected'] == '2026-11-27'

    # 없는 날짜 — 버리지 않고 글자로 두되, 반드시 알린다
    assert _by['126391']['최종 승인']['expected_note'] == '2026-06-31'
    assert _by['126391']['최종 승인']['expected'] is None, \
        '없는 날짜를 날짜로 들였다'
    _bad = [w for w in _g['warnings'] if '2026-06-31' in w and '없는 날짜' in w]
    assert len(_bad) == 2, '없는 날짜를 안 알린다: %r' % _g['warnings']

    # 몇 칸이 들어갔는지 숫자로 — '경고 0건' 만 보고 괜찮다고 믿으면 안 된다
    assert _g['date_cells'] == 6, _g['date_cells']
    assert _g['note_cells'] == 3, _g['note_cells']

    # 담당도 같이
    assert _by and all(it['owner'] == '이수현 이사, 이수만 과장'
                       for it in _g['items']), '담당이 안 읽힌다'
    print('ok — 글자 칸 · 없는 날짜')
else:
    print('(채운 양식 없음 — 건너뜀)')

# 빈 칸은 여전히 '안 적음' 이다 — 글자로 바뀌면 안 된다
assert _dsi.cell_value(None) == (None, '', '')
assert _dsi.cell_value('   ') == (None, '', '')
assert _dsi.cell_value('2026-11-30')[0] == '2026-11-30'
assert _dsi.cell_value('고객사 검토중') == (None, '고객사 검토중', '')
assert _dsi.cell_value('2026-02-30')[2] == '2026-02-30', '2월 30일을 못 거른다'
print('ok — 빈 칸 규칙')

# ── 세 줄이 한 묶음인데 글자가 흔들릴 때 (2026-11-02) ────────────
# Min: "자동차 개발일정 파일 보면 고객사마다 프로세스 다르고 계획이랑
#      실적 일정이 있는데 왜 반영이 안되는거야"
#
# 한 품목은 프로세스 · 계획 · 실적 세 줄이다. 그런데 사람이 적다 보니
# 줄마다 글자가 조금씩 달랐다 —
#   프로세스  JAHWA VINA         32-C90H-2H001
#   계획      JAHWA ELECTRONICS  32-C90H-2H001      ← 고객사만 다름
#   프로세스  SCHAEFFLER         AAA9994000100
#   계획      SCHAEFFLER         AAA99940001        ← 품번이 다름
#
# 품번이 같으면 붙인다 (고객사는 사람이 부르는 말이라 흔들린다).
# 품번까지 다르면 안 붙이되, **무엇이 다른지**를 적는다. 전에는
# "프로세스 줄이 없습니다" 라고만 해서, 바로 위에 멀쩡히 있는 줄을
# 두고 왜 그러는지 알 수가 없었다.
_F2 = _pl.Path(__file__).resolve().parent / 'forms' / 'v2' / '개발일정_자동차_1102.xlsx'
if _F2.exists():
    _g2 = _dsi.parse_workbook(_ox.load_workbook(_F2, data_only=True))
    _b2 = {it['part_number']: it for it in _g2['items']}

    assert len(_g2['items']) == 38, len(_g2['items'])
    # 고객사만 다른 줄은 붙어야 한다 — 안 붙으면 그 품목은 날짜가 통째로 빈다
    _j = _b2.get('32-C90H-2H001')
    assert _j is not None, 'JAHWA 품목이 통째로 빠졌다'
    assert any(s['expected'] for s in _j['steps']), 'JAHWA 계획이 안 붙었다'
    assert any('고객사가 위 프로세스 줄과 다릅니다' in w for w in _g2['warnings']), \
        '고객사가 달랐다는 걸 안 알린다'

    # 품번이 다른 줄은 안 붙되, 무엇이 다른지 적혀야 한다
    _bad = [w for w in _g2['warnings'] if '품번이 위 프로세스 줄과 다릅니다' in w]
    assert len(_bad) == 2, _g2['warnings']
    assert 'AAA9994000100' in _bad[0] and 'AAA99940001' in _bad[0], _bad[0]
    assert not any(s['expected'] or s.get('expected_note')
                   for s in _b2['AAA9994000100']['steps']), \
        '품번이 다른 줄을 억지로 붙였다'

    # 'NA364-50000' 은 진짜 등록된 품번이다 — NA 를 군더더기로 떼면 안 된다
    assert any(it['part_number'].startswith('NA364-50000')
               for it in _g2['items']), 'NA 접두가 사라졌다'

    # 날짜와 글자가 둘 다 실린다
    assert _g2['date_cells'] >= 200, _g2['date_cells']
    assert _g2['note_cells'] >= 80, _g2['note_cells']
    print('ok — 세 줄 글자 흔들림')
else:
    print('(자동차 1102 양식 없음 — 건너뜀)')
