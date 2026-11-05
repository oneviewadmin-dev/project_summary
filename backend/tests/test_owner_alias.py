# 엑셀에 적힌 이름이 어느 프로젝트인가 — 줄여 쓴 이름까지
#   python3 backend/tests/test_owner_alias.py
#
# Min: "TC 같은 경우 일 보고에는 TC라고 작성되어 있고 모델 목록에는
#      TC (Tele...)이렇게 적혀있는데도 연결이 안되는건가..."
#
# 같은 물건을 세 군데서 다르게 적는다.
#     일 보고        TC
#     모델 목록      TC (Telemaetry Cabinet)
#     프로젝트 이름  Telemaetry Cabinet
#
# 전에는 _df_norm 이 괄호를 지워서 'TC (Telemaetry Cabinet)' 이
# 'tctelemaetrycabinet' 한 덩어리가 됐다. 'tc' 와도 'telemaetrycabinet'
# 과도 안 맞아서, 친절하게 괄호를 붙여 적을수록 더 안 붙었다.
#
# 이제 두 가지를 한다.
#   1) 괄호 앞·안을 따로 열쇠로 쓴다 (_df_keys)
#   2) 이미 등록된 **모델 이름**도 열쇠로 쓴다 — 모델 목록에
#      'TC (Telemaetry Cabinet)' 이 있으면 시스템은 이미 TC 를 아는 셈이다
#
# 2)는 한 사업부에서 그 이름이 한 프로젝트에만 있을 때만 쓴다. 하바플레이트는
# 소재가 모델 이름이라 'PC (Dynex)' 가 수십 줄이다 — 그걸 아무 데나 붙이면
# 아무도 못 알아챈다. 못 붙은 줄은 화면이 목록으로 보여 준다.
import ast, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')

tree = ast.parse(SRC)
WANT = {'_df_norm', '_df_keys', '_df_owner_index', '_df_digits', '_df_dam1', '_df_typo_project', '_df_find_project'}
G = {}
for n in tree.body:
    # 2026-11-03 — 고객사 이름 오타 매칭(3단계)이 쓰는 것들도 같이
    if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == '_DF_TYPO_MIN_LEN'
            for t in n.targets):
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
    if isinstance(n, ast.FunctionDef) and n.name in WANT:
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
missing = WANT - set(G)
assert not missing, 'main.py 에서 못 찾은 함수: %r' % sorted(missing)
ok = 0


def _idx(projects, models):
    """config_loader 와 _load_models 를 세워 두고 색인을 만든다."""
    class _CL:
        @staticmethod
        def get_projects(division_id=None, visible_only=True):
            return [p for p in projects if p.get('division_id') == division_id]
    sys.modules['config_loader'] = _CL
    G['_load_models'] = lambda: {'projects': models}
    return G['_df_owner_index']('bloom')


# ── 1. 괄호 앞·안이 따로 열쇠가 되는가 ────────────────────────────
keys = G['_df_keys']('TC (Telemaetry Cabinet)')
assert 'tc' in keys, '괄호 앞 조각이 열쇠에 없다: %r' % keys
assert 'telemaetrycabinet' in keys, '괄호 안 조각이 열쇠에 없다: %r' % keys
ok += 1

# ── 2. 세 가지로 적어도 같은 프로젝트에 붙는가 ────────────────────
PROJ = [
    {'id': 'bloom_tc',   'division_id': 'bloom', 'label': 'Telemaetry Cabinet'},
    {'id': 'bloom_sm',   'division_id': 'bloom', 'label': 'SM PART'},
    {'id': 'bloom_sl7',  'division_id': 'bloom', 'label': 'SL7'},
    {'id': 'bloom_main', 'division_id': 'bloom', 'label': '블룸 (전체)'},
]
MODELS = {
    'bloom_tc':  {'models': [{'name': 'TC (Telemaetry Cabinet)'}]},
    'bloom_sm':  {'models': [{'name': 'SM PART ( 판금 단품류 )'}]},
    'bloom_sl7': {'models': [{'name': 'SL7'}]},
}
idx = _idx(PROJ, MODELS)
for owner, want in [
    ('TC', 'bloom_tc'),                       # 일 보고가 적는 방식
    ('TC (Telemaetry Cabinet)', 'bloom_tc'),  # 모델 목록이 적는 방식
    ('Telemaetry Cabinet', 'bloom_tc'),       # 프로젝트 이름
    ('tc ', 'bloom_tc'),                      # 대소문자·공백
    ('SM PART', 'bloom_sm'),
    ('판금 단품류', 'bloom_sm'),               # 괄호 안이 한글인 경우
    ('SL7', 'bloom_sl7'),
]:
    got = G['_df_find_project'](owner, idx)
    assert got == want, '%r → %r (%r 이어야 함)' % (owner, got, want)
    ok += 1

# ── 3. 모르는 이름은 끝까지 모른다고 해야 한다 ────────────────────
# 아무 데나 붙이면 숫자가 엉뚱한 프로젝트로 들어가고, 화면은 멀쩡해 보인다.
assert G['_df_find_project']('없는거', idx) == '', '모르는 이름이 어딘가에 붙었다'
assert G['_df_find_project']('', idx) == '', '빈 이름이 어딘가에 붙었다'
ok += 2

# ── 4. 두 프로젝트에 같은 모델 이름이면 안 붙인다 ─────────────────
# 하바플레이트는 소재가 모델 이름이라 'PC (Dynex)' 가 수십 줄이다.
AMB = {
    'bloom_tc': {'models': [{'name': 'PC (Dynex)'}]},
    'bloom_sm': {'models': [{'name': 'PC (Dynex)'}]},
}
idx2 = _idx(PROJ, AMB)
assert G['_df_find_project']('PC (Dynex)', idx2) == '', \
    '두 프로젝트에 같이 있는 모델 이름을 한쪽에 붙였다'
ok += 1

# ── 5. 프로젝트 이름이 모델 이름보다 먼저다 ───────────────────────
# 모델 이름은 거드는 것이다. 'SL7' 이 다른 프로젝트의 모델로도 적혀 있다고
# 해서 SL7 프로젝트를 빼앗기면 안 된다.
STEAL = {
    'bloom_tc':  {'models': [{'name': 'SL7'}]},
    'bloom_sl7': {'models': [{'name': '뭔가'}]},
}
idx3 = _idx(PROJ, STEAL)
assert G['_df_find_project']('SL7', idx3) == 'bloom_sl7', \
    '모델 이름이 프로젝트 이름을 덮어썼다'
ok += 1

# ── 6. 모델 자료를 못 읽어도 반영이 막히지 않아야 한다 ────────────
# 색인이 조금 모자란 것보다 업로드가 통째로 막히는 게 나쁘다.
class _CL2:
    @staticmethod
    def get_projects(division_id=None, visible_only=True):
        return [p for p in PROJ if p.get('division_id') == division_id]


def _boom():
    raise RuntimeError('일부러 터뜨림')


sys.modules['config_loader'] = _CL2
G['_load_models'] = _boom
idx4 = G['_df_owner_index']('bloom')
assert G['_df_find_project']('Telemaetry Cabinet', idx4) == 'bloom_tc', \
    '모델 자료를 못 읽으니 색인이 통째로 비었다'
ok += 1

print('ok %d' % ok)
