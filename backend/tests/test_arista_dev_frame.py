# 아리스타 개발은 양산과 같은 틀로 본다 (2026-10-28)
#   python3 backend/tests/test_arista_dev_frame.py
#
# Min: "아리스타 개발이 flutter app 에서 보여지는 결과야 / 지금은 반도체사업부에
#      맞춰서 개발은 전사업부가 반도체사업부 개발에 맞게 틀이 잡혀져 있잖아,
#      근데 아리스타 같은 경우에는 그냥 양산이랑 동일하게 틀 적용해주면 될 것 같아"
#
# 개발 품목은 반도체 기준으로 공정 13단계 화면을 쓴다 (PO 접수 → FAIR 승인).
# 아리스타는 PCB 라 그 단계가 아예 없어서, 개발 품목에 들어가면 빈 단계표만
# 떴고 진행률도 '—' 였다.
#
# **저장된 구분은 안 건드린다.** admin 표와 엑셀은 그대로 '개발' 이다.
# 바뀌는 건 앱이 어느 카드로 그리나 하나뿐이라 앱을 다시 올릴 필요가 없다 —
# 앱은 display_group 으로 양산 카드 · 개발 카드를 가른다.
import ast, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')

import division_columns as dc            # noqa: E402
ok = 0

# ── 1. 어느 사업부가 양산 틀인가 ──────────────────────────────────
assert dc.dev_frame('arista') == '양산', '아리스타가 아직 개발 틀이다'
assert dc.dev_frame('ARISTA') == '양산', '대문자로 물으면 못 찾는다'
ok += 1
# 반도체는 그대로 — 여기가 뒤집히면 공정 화면이 통째로 사라진다
for d in ('semiconductor', 'bloom', 'ess', 'pcb', 'automotive', '', None):
    assert dc.dev_frame(d) == '', '%r 까지 양산 틀로 바뀌었다' % (d,)
ok += 1

# ── 2. 틀 고르기 ─────────────────────────────────────────────────
tree = ast.parse(SRC)
G = {}
for n in tree.body:
    if isinstance(n, ast.FunctionDef) and n.name in (
            '_frame_group', '_display_group', '_norm_phases', '_phase_ord',
            '_as_money'):
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
G['_dcol'] = dc
fg = G['_frame_group']

dev = {'id': 'A', 'group': '개발'}
mass = {'id': 'B', 'group': '양산'}
assert fg(dev, 'arista') == '양산', '아리스타 개발이 아직 개발 틀이다'
assert fg(dev, 'semiconductor') == '개발', '반도체 개발이 양산 틀이 됐다'
assert fg(dev, '') == '개발', '사업부를 모르면 개발 틀이어야 한다'
ok += 1
# 양산은 어느 사업부든 양산이다
assert fg(mass, 'arista') == '양산' and fg(mass, 'semiconductor') == '양산'
ok += 1
# 저장된 구분은 안 건드린다 — 넘긴 dict 가 그대로여야 한다
assert dev['group'] == '개발', '모델의 구분을 바꿔 버렸다'
ok += 1

# ── 3. 개발→양산 전환 이력은 그대로 이긴다 ────────────────────────
# 'W37 부터 양산' 이력이 있으면 아리스타가 아니어도 양산이다.
hist = {'id': 'C', 'group': '개발',
        'phases': [{'from': '2000-W01', 'group': '개발', 'price': 0},
                   {'from': '2020-W01', 'group': '양산', 'price': 10}]}
assert fg(hist, 'semiconductor') == '양산', '전환 이력을 무시했다'
ok += 1

# ── 4. 구분과 틀은 다른 칸이다 ────────────────────────────────────
# Min: "양산 개발을 나뉘는데 개발에 들어가더라도 양산처럼 틀 똑같이
#      맞춰달라는거였어"
# 목록은 그대로 양산 · 개발로 나뉘고, 그 안에서 보이는 모양만 바뀐다.
_e = SRC[SRC.index('def _enrich_model('):]
_e = _e[:_e.index('\n@app.') if '\n@app.' in _e else len(_e)]
assert '_disp = _display_group(m)' in _e, '구분이 틀에 끌려갔다 — 묶음이 합쳐진다'
assert 'out["display_group"] = _disp' in _e, '구분을 안 내려준다'
assert 'out["frame"] = _frame_group(m, division_id)' in _e, '틀을 안 내려준다'
ok += 1
# 목록 묶기는 구분 그대로여야 한다 (양산/개발 두 묶음)
assert 'g = _display_group(m) if isinstance(m, dict) else "기타"' in SRC, \
    '목록 묶기가 틀로 바뀌었다 — 개발 묶음이 사라진다'
ok += 1
# 창구가 사업부를 넘겨 주는가 — 안 넘기면 늘 개발 틀이다
assert '_enrich_model(m, _phold, _div)' in SRC, \
    '/models/detail 이 사업부를 안 넘긴다'
assert SRC.count('_cl.derive_division_from_project(_key) or ""') >= 1
ok += 1

# ── 4-2. 앱이 그 칸을 쓰는가 ──────────────────────────────────────
MOB = ROOT.parent / 'mobile' / 'lib' / 'screens'
ML = (MOB / 'model_list_screen.dart').read_text(encoding='utf-8')
PO = (MOB / 'project_overview_screen.dart').read_text(encoding='utf-8')
assert 'String frameOf(Map m) {' in ML, '앱에 틀 읽는 자리가 없다'
# 서버가 frame 을 안 주는 옛 응답에서도 지금까지처럼 돌아야 한다
assert "m['display_group'] ?? m['group']" in ML.split('String frameOf(Map m) {')[1][:400], \
    'frame 이 없는 옛 응답에서 틀이 빈 글자가 된다'
assert "return frameOf(m) == '개발'" in ML, '줄마다 어느 카드로 그릴지가 틀을 안 본다'
assert "final g = frameOf(m);" in PO, "'확인 필요' 에서 눌렀을 때가 틀을 안 본다"
# 개발 묶음이어도 틀이 양산이면 공정 칩 줄을 안 그린다
assert "models.any((m) => frameOf(m) == '개발')" in ML, \
    '틀이 양산인데 공정 칩 줄을 그대로 그린다'
ok += 1

# ── 5. 개발 틀일 때만 공정을 붙인다 ───────────────────────────────
# 양산 틀로 보기로 했는데 공정 단계가 같이 오면, 앱이 그걸 보고 다시
# 개발 화면을 열 수 있다.
assert 'if _disp == "개발":' in _e, '공정 붙이는 조건이 사라졌다'
ok += 1

print('ok %d' % ok)
