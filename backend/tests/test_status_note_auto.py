# 프로젝트 현황은 사람이 적지 않고 숫자로 센다 (2026-10-28)
#   python3 backend/tests/test_status_note_auto.py
#
# Min: "프로젝트 현황 모든 프로젝트에 다 빼주고 flutter app에 프로젝트
#      현황에 작성되어 있던 내용을 알아서 반영되게 할거야 ...
#      총 00종 중 양산 00종, 개발 00종"
#
# 현황 글은 손으로 적는 칸이었다. 모델이 늘고 줄 때 같이 고쳐 주는 사람이
# 없어서 앱에는 몇 달 전 문장이 그대로 떠 있었다. 숫자는 모델 목록에 이미
# 있으니 그걸 세면 늘 맞는다.
#
# 앱은 안 건드린다 — 서버가 같은 칸(status_note)에 다른 글을 넣으면
# 앱을 다시 올리지 않아도 바뀐다.
import ast, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
HTML = (ROOT / 'admin_v2.html').read_text(encoding='utf-8')

tree = ast.parse(SRC)
WANT = {'_model_mix_note', '_display_group', '_norm_phases', '_phase_ord'}
G = {}
for n in tree.body:
    if isinstance(n, ast.FunctionDef) and n.name in WANT:
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
assert '_model_mix_note' in G, 'main.py 에 _model_mix_note 가 없다'
mix = G['_model_mix_note']
ok = 0

# ── 1. 세는 법 ────────────────────────────────────────────────────
assert mix([{'group': '양산'}]) == '총 1종 중 양산 1종, 개발 0종', mix([{'group': '양산'}])
ok += 1
got = mix([{'group': '양산'}] * 89 + [{'group': '개발'}] * 3)
assert got == '총 92종 중 양산 89종, 개발 3종', got
ok += 1
# 합이 안 맞으면 읽는 사람이 바로 이상하다고 느낀다
assert mix([{'group': '개발'}] * 2) == '총 2종 중 양산 0종, 개발 2종'
ok += 1

# ── 2. 모델이 없으면 빈 글자 ──────────────────────────────────────
# 앱은 빈 글이면 카드를 아예 안 그린다 (_buildStatusNote).
# '총 0종' 짜리 카드가 떠 있으면 그게 화면에서 제일 눈에 띈다.
assert mix([]) == '' and mix(None) == ''
ok += 1
assert mix(['이상한것', None]) == '', '딕셔너리가 아닌 줄까지 셌다'
ok += 1

# ── 3. 구분은 '오늘 기준' 으로 센다 ───────────────────────────────
# '개발→양산 W37' 이력이 있으면 화면의 구분 칸은 양산이다.
# 저장된 group 으로 세면 표와 한 줄이 어긋난다.
assert '_display_group(m)' in SRC[SRC.index('def _model_mix_note'):
                                  SRC.index('def _model_mix_note') + 1500], \
    '저장된 group 을 그대로 센다 — 표와 어긋난다'
ok += 1

# ── 4. 앱이 받는 칸에 들어가는가 ──────────────────────────────────
_d = SRC[SRC.index('def get_project_models_detail'):]
_d = _d[:_d.index('\n@app.')]
assert '"status_note": _model_mix_note(enriched)' in _d, \
    '앱이 읽는 칸(status_note)에 안 넣었다 — 앱을 다시 올려야 해진다'
ok += 1
# 적어 둔 글은 지우지 않는다. 보류·드롭 판정이 그 글을 읽는다.
assert '"status_note_memo": proj.get("status_note")' in _d, \
    '사람이 적어 둔 글을 어디에도 안 남겼다'
ok += 1
assert '_hold_from_note' in SRC, '보류 판정이 사라졌다'
ok += 1

# ── 5. admin 에서는 그 카드를 안 그린다 ───────────────────────────
assert 'var STATUS_NOTE_CARD_ON = false;' in HTML, '프로젝트 현황 카드가 아직 켜져 있다'
ok += 1
assert '(STATUS_NOTE_CARD_ON ?' in HTML, '스위치를 만들어 놓고 안 쓴다'
ok += 1
# 지우지 않고 끈다 — 보류·드롭 고르는 칸이 같이 들어 있다
assert "id=\"mdl-proj-hold\"" in HTML, '보류 고르는 칸을 통째로 지웠다 — 되살릴 자리가 없다'
ok += 1
# 스위치는 함수 밖에 있어야 한다. 함수 안에 두면 카드를 그리는 쪽에서 안 보인다.
_line = [l for l in HTML.splitlines() if 'var STATUS_NOTE_CARD_ON' in l][0]
assert len(_line) - len(_line.lstrip()) <= 2, \
    '스위치가 함수 안에 들어가 있다 (들여쓰기 %d칸)' % (len(_line) - len(_line.lstrip()))
ok += 1

print('ok %d' % ok)
