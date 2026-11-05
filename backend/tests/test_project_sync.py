# 양식에 없는 프로젝트는 화면에서 내린다 (2026-10-28)
#   python3 backend/tests/test_project_sync.py
#
# Min: "양식 엑셀에 있는 프로젝트만 떠야 되는데 왜 없는것도 그대로 있는거야.."
#
# 블룸 양식에서 이름이 바뀌었다.
#     CORVA BOP          → BOP 기구
#     CORVA BOP ASSY     → BOP ASSY
#     Telemaetry Cabinet → TC (Telemaetry Cabinet)
#     CORVA EFM KPE(PB)  → 아예 빠짐
#
# 블룸 프로젝트 목록은 **양식이 만든다**. 그래서 이름이 바뀌면 새것이 하나
# 생기고 옛것이 그대로 남았다 — 품목 10개짜리 양식을 올렸는데 화면에는
# 15줄이 떴고, 어느 쪽이 지금 것인지 알 수가 없었다.
#
# 지우지 않고 **끈다**. 지우면 쌓인 주차별 계획·실적이 통째로 없어진다.
# 이름이 한 달 빠졌다가 돌아오는 일도 있다 — 그때 켜 주면 숫자가 살아 있다.
#
# 2026-10-28 (2) — '양식이 만든 것' 을 created_by 표시로 갈랐다가 하나도
# 안 걸렸다. 그 표시를 넣기 전에 생긴 프로젝트가 이미 서버에 쌓여 있었고,
# 정작 지워야 할 옛것들이 전부 표시 없는 것들이었다. 이제는 **어디에
# 적혀 있는가** 로 가른다 — /data 에 쌓인 것만 양식이 만든 것이다.
import ast, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')

tree = ast.parse(SRC)
WANT = {'_df_norm', '_df_keys', '_df_owner_index', '_df_digits', '_df_dam1', '_df_typo_project', '_df_find_project',
        '_df_project_sync'}
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
G['_daily_store_key'] = lambda div: 'bloom_main' if div == 'bloom' else ''


class _DCOL:
    @staticmethod
    def shape_of(div):
        return '반도체형' if div == 'semiconductor' else '프로젝트형'


G['_dcol'] = _DCOL
ok = 0

# 양식이 만든 것(=/data 에 쌓인 것) 넷 + 사람이 config 에 적은 것 하나 +
# 일 보고를 담는 창고(bloom_main) 하나.
# RUNTIME 에 있으면 '양식이 만든 것' 이다.
RUNTIME = {'bloom_bop', 'bloom_corva_bop', 'bloom_tc', 'bloom_old', 'bloom_main'}
BASE = [
    {'id': 'bloom_bop',  'division_id': 'bloom', 'label': 'BOP 기구',
     'visible': True},
    {'id': 'bloom_corva_bop', 'division_id': 'bloom', 'label': 'CORVA BOP',
     'visible': True},
    {'id': 'bloom_tc',   'division_id': 'bloom', 'label': 'TC (Telemaetry Cabinet)',
     'visible': True},
    {'id': 'bloom_old',  'division_id': 'bloom', 'label': 'Telemaetry Cabinet',
     'visible': True},
    {'id': 'bloom_hand', 'division_id': 'bloom', 'label': '손으로 만든 것',
     'visible': True},
    {'id': 'bloom_main', 'division_id': 'bloom', 'label': '블룸 (전체)',
     'visible': False},
]


def _setup(projects):
    """config_loader 를 세운다. set_project_visible 은 목록을 그 자리에서 고친다."""
    rows = [dict(p) for p in projects]

    class _CL:
        @staticmethod
        def get_projects(division_id=None, visible_only=True):
            out = [p for p in rows if p.get('division_id') == division_id]
            if visible_only:
                out = [p for p in out if p.get('visible', True)]
            return out

        @staticmethod
        def is_runtime_project(pid):
            return pid in RUNTIME

        @staticmethod
        def set_project_visible(pid, visible, why=''):
            if pid not in RUNTIME:       # /data 에 없는 것은 못 고친다
                return False
            for p in rows:
                if p.get('id') == pid:
                    if bool(p.get('visible', True)) == bool(visible):
                        return False
                    p['visible'] = bool(visible)
                    return True
            return False

    sys.modules['config_loader'] = _CL
    G['_cl'] = _CL
    G['_load_models'] = lambda: {'projects': {}}
    return rows


def _items(*owners):
    return [{'owner': o} for o in owners]


# ── 1. 양식에 없는 이름은 내려간다 ────────────────────────────────
rows = _setup(BASE)
idx = G['_df_owner_index']('bloom')
got = G['_df_project_sync']('bloom', _items('BOP 기구', 'TC (Telemaetry Cabinet)'), idx)
down = sorted(x['key'] for x in got['hidden'])
assert down == ['bloom_corva_bop', 'bloom_old'], \
    '내려간 프로젝트가 %r — 옛 이름 둘이어야 한다' % down
ok += 1

by = {p['id']: p for p in rows}
assert by['bloom_bop']['visible'] and by['bloom_tc']['visible'], \
    '양식에 적힌 프로젝트까지 내렸다'
ok += 1

# ── 2. 사람이 만든 목록은 안 건드린다 ─────────────────────────────
# 반도체처럼 config 에 사람이 적어 둔 프로젝트는 양식이 못 끈다.
assert by['bloom_hand']['visible'], \
    "config 에 손으로 적은 프로젝트를 양식이 내렸다"
ok += 1

# ── 3. 일 보고 창고(bloom_main)는 꺼진 채로 둔다 ──────────────────
# 그건 프로젝트가 아니라 엑셀 원본을 담는 자리다. 켜면 화면에 뜬다.
assert by['bloom_main']['visible'] is False, 'bloom_main 을 건드렸다'
assert not any(x['key'] == 'bloom_main' for x in got['shown'] + got['hidden']), \
    'bloom_main 을 켜고 껐다'
ok += 1

# ── 4. 이름이 돌아오면 다시 켠다 ──────────────────────────────────
# 쌓인 주차 계획·실적은 그대로 있다 — 지운 게 아니라 껐을 뿐이다.
got2 = G['_df_project_sync']('bloom', _items('BOP 기구', 'CORVA BOP'), idx)
up = [x['key'] for x in got2['shown']]
assert up == ['bloom_corva_bop'], '돌아온 이름을 다시 안 켰다: %r' % up
assert by['bloom_corva_bop']['visible'] is True
ok += 1

# ── 5. 빈 양식으로는 아무것도 안 내린다 ───────────────────────────
# 빈 장을 잘못 올렸을 때 사업부가 통째로 사라지는 게 제일 나쁘다.
rows = _setup(BASE)
idx = G['_df_owner_index']('bloom')
assert G['_df_project_sync']('bloom', [], idx) == {'hidden': [], 'shown': []}, \
    '품목이 없는 양식으로 프로젝트를 내렸다'
ok += 1

# 이름을 하나도 못 알아본 양식도 마찬가지다 — 양식이 틀렸을 뿐이다
blind = G['_df_project_sync']('bloom', _items('처음보는것', '이것도'), idx)
assert blind == {'hidden': [], 'shown': []}, \
    '아무것도 못 붙은 양식으로 프로젝트를 내렸다: %r' % blind
ok += 1

# ── 6. dry=True 는 아무것도 안 바꾼다 ─────────────────────────────
# 미리보기가 쓴다. 반영 전에 사라질 목록을 눈으로 보고 누른다.
rows = _setup(BASE)
idx = G['_df_owner_index']('bloom')
plan = G['_df_project_sync']('bloom', _items('BOP 기구'), idx, dry=True)
assert sorted(x['key'] for x in plan['hidden']) == \
    ['bloom_corva_bop', 'bloom_old', 'bloom_tc'], plan['hidden']
assert all(p['visible'] for p in rows if p['id'] != 'bloom_main'), \
    '미리보기가 실제로 프로젝트를 껐다'
ok += 1

# ── 7. 반도체는 건드리지 않는다 ───────────────────────────────────
# 반도체는 Chamber · CUP · 엔클로저 · HRVA 를 **파일 따로** 올린다.
# 여기서 이 규칙을 돌리면 CUP 한 장 올렸다고 나머지 셋이 통째로 사라진다.
SEMI = [
    {'id': 'semi_cup', 'division_id': 'semiconductor', 'label': 'CUP', 'visible': True},
    {'id': 'semi_chamber', 'division_id': 'semiconductor', 'label': '챔버', 'visible': True},
]
rows = _setup(SEMI)
idx = {'cup': 'semi_cup', 'chamber': 'semi_chamber'}
assert G['_df_project_sync']('semiconductor', _items('CUP'), idx) == \
    {'hidden': [], 'shown': []}, '반도체 양식 한 장으로 다른 프로젝트를 내렸다'
assert all(p['visible'] for p in rows), '반도체 프로젝트가 꺼졌다'
ok += 1

# ── 8. 화면·창구가 그 목록을 쓰는가 ───────────────────────────────
# 서버가 세어도 화면이 안 보여 주면 올린 사람은 왜 줄이 사라졌는지 모른다.
assert '"hidden_projects": proj_sync["hidden"]' in SRC, '반영 결과에 목록이 없다'
assert '_df_project_sync(\n            division_id, got["items"], idx, dry=True)' in SRC, \
    '미리보기가 내려갈 목록을 안 만든다'
HTML = (ROOT / 'admin_v2.html').read_text(encoding='utf-8')
assert 'd.hidden_projects' in HTML, 'admin 화면이 내려간 프로젝트를 안 보여 준다'
assert '지우는 게 아니라 끄는 것입니다' in HTML, \
    "'지운 게 아니다' 를 안 알려 준다 — 올린 사람이 놀란다"
ok += 2

print('ok %d' % ok)
