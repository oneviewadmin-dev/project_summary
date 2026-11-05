# 유형은 지우면 지워지고, 더하면 더해진다 (2026-10-28)
#   python3 backend/tests/test_types_edit.py
#
# Min: "유형 삭제 안되고 추가도 안돼"
#
# 두 가지가 겹쳐 있었다.
#
#  1) 서버가 목록을 돌려줄 때 **모델이 쓰고 있는 유형을 도로 끼워 넣었다.**
#     원래는 엑셀로 들어온 유형이 목록에 없어 표가 '—' 로 보이던 일을
#     막으려던 것인데(챔버 14종), 그 때문에 손으로 지운 것도 되살아났다.
#     지운 사람 눈에는 아무 일도 안 일어난 것으로 보인다.
#
#  2) 화면이 저장할 때 칩을 읽을 때와 **다른 변수**에서 프로젝트 키를
#     찾았다. 그게 비어 있으면 아무 말 없이 돌아가서 버튼이 죽어 보였다.
import ast, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
HTML = (ROOT / 'admin_v2.html').read_text(encoding='utf-8')

tree = ast.parse(SRC)
G = {}
for n in tree.body:
    if isinstance(n, ast.FunctionDef) and n.name == '_get_project_types':
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
assert '_get_project_types' in G, 'main.py 에 _get_project_types 가 없다'
ok = 0

DATA = {}
G['_read_json'] = lambda *a, **k: DATA
G['MODELS_FILE'] = 'x'


def _set(types=None, removed=None, model_types=()):
    DATA.clear()
    proj = {'models': [{'id': str(i), 'dev_type': t}
                       for i, t in enumerate(model_types)]}
    if types is not None:
        proj['types'] = types
    if removed is not None:
        proj['types_removed'] = removed
    DATA['projects'] = {'p': proj}


# ── 1. 목록에 없는데 모델이 쓰는 유형은 올려 준다 (챔버 건) ───────
_set(types=[], model_types=['DEP챔버', 'DEP챔버', 'HVM'])
got = G['_get_project_types']('p')
assert got == ['DEP챔버', 'HVM'], \
    '엑셀로 들어온 유형이 목록에 안 올라온다: %r' % got
ok += 1

# ── 2. 지운 것은 모델이 아직 쓰고 있어도 안 올라온다 ──────────────
# 모델 칸의 값은 그대로 둔다 — 화면에 "모델에 입력된 값은 유지됩니다".
_set(types=[], removed=['함체'], model_types=['함체'])
got = G['_get_project_types']('p')
assert got == [], '지운 유형이 모델을 보고 되살아났다: %r' % got
ok += 1

# ── 3. 지운 것을 손으로 다시 더하면 돌아온다 ──────────────────────
_set(types=['함체'], removed=[], model_types=['함체'])
assert G['_get_project_types']('p') == ['함체']
ok += 1

# ── 4. 지운 것 말고 다른 유형은 그대로 올라온다 ───────────────────
_set(types=['HVM'], removed=['함체'], model_types=['함체', 'RPM'])
got = G['_get_project_types']('p')
assert got == ['HVM', 'RPM'], '지운 것 말고 다른 유형까지 사라졌다: %r' % got
ok += 1

# ── 5. 저장하는 쪽이 '지운 것' 을 적어 두는가 ─────────────────────
_put = SRC[SRC.index('def save_project_types'):]
_put = _put[:_put.index('\n@app.') if '\n@app.' in _put else len(_put)]
assert 'types_removed' in _put, '저장할 때 지운 유형을 안 적어 둔다 — 다음에 또 살아난다'
assert 'used - set(types)' in _put, \
    "'모델이 쓰는데 목록에 없는 것' 으로 지운 것을 가리지 않는다"
ok += 1

# ── 6. 화면: 저장할 때 **읽을 때 쓴 키**를 쓴다 ───────────────────
assert 'var _projTypesKey' in HTML, '칩을 어느 프로젝트로 읽었는지 안 적어 둔다'
assert '_projTypesKey = projectKey' in HTML, '읽을 때 키를 안 적는다'
_sv = HTML[HTML.index('function saveTypes()'):]
_sv = _sv[:_sv.index('// 유형 추가 버튼')]
assert '_projTypesKey ||' in _sv, '저장할 때 읽은 키를 안 본다'
ok += 1

# ── 7. 키가 없으면 조용히 돌아가지 않는다 ─────────────────────────
# 왜 안 되는지 모르는 게 제일 나쁘다. 버튼이 죽은 줄 알고 몇 번씩 누른다.
assert '프로젝트를 먼저 선택해 주세요' in _sv, \
    '키가 없을 때 아무 말 없이 돌아간다'
assert '/* 프로젝트 선택 대기 중 */ return;' not in _sv, \
    '조용히 돌아가는 줄이 아직 남아 있다'
ok += 1

# ── 8. 저장 뒤에는 서버가 돌려준 목록으로 다시 그린다 ─────────────
# 제 기억대로만 그리면 저장된 것과 보이는 것이 어긋나도 아무도 모른다.
assert 'if (d && Array.isArray(d.types)) _projTypes = d.types;' in _sv, \
    '저장 뒤 화면이 서버 값을 안 쓴다'
ok += 1

# ── 9. 화면에서는 아예 안 고친다 (2026-10-28) ────────────────────
#
# Min: "이것도 그냥 아예 빼버려줘 / 유형 있으면 그냥 pill 형식으로만
#      보여주고 저런 아예 빼버려"
#
# 유형은 엑셀의 '구분' 칸에서 들어온다. 화면에서 따로 더하고 지우면
# 엑셀과 화면이 서로 다른 목록을 들고 있게 된다.
assert 'var TYPE_EDIT_ON = false;' in HTML, '유형을 아직 화면에서 고친다'
ok += 1
# 입력칸·추가 단추·칩의 × 를 안 그린다
assert "(TYPE_EDIT_ON ?\n              '<input id=\"mdl-type-input\"" in HTML, \
    '새 유형 입력칸을 아직 그린다'
assert "(TYPE_EDIT_ON\n           ? '<button type=\"button\" class=\"mdl-type-del\"" in HTML, \
    '칩의 × 를 아직 그린다'
ok += 1
# 지우지 않고 끈다 — 되살릴 자리를 남긴다
assert 'mdl-type-add' in HTML and 'mdl-type-del' in HTML, \
    '고치는 길을 통째로 지웠다 — 되살릴 자리가 없다'
ok += 1

# ── 10. 유형이 없으면 줄 자체를 숨긴다 ────────────────────────────
# '유형' 이라고만 적힌 빈 줄이 표 위에 걸려 있으면 그게 제일 눈에 띈다.
_rc = HTML[HTML.index('function renderTypeChips()'):]
_rc = _rc[:_rc.index('function saveTypes()')]
assert "bar.hidden = !(_projTypes && _projTypes.length)" in _rc, \
    '유형이 없어도 줄을 그대로 둔다'
ok += 1
# hidden 만으로는 안 숨는다 — .mdl-types-bar 의 display:flex 가 이긴다
assert "'.mdl-types-bar[hidden] { display:none !important; }'," in HTML, \
    'hidden 을 걸어 놓고 CSS 로 안 숨긴다 — display:flex 가 이겨서 그대로 보인다'
ok += 1

print('ok %d' % ok)
