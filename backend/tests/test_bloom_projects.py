# 블룸: 품목 하나가 프로젝트 하나
#   python3 backend/tests/test_bloom_projects.py
#
# 엑셀은 품목 전체가 한 장이다. 원본은 bloom_main 한 곳에 두고 품목
# 프로젝트는 자기 몫만 잘라 본다. 갈라 저장하면 다음 업로드 때 합치는 일이
# 또 생기고, 한 번 어긋나면 되돌리기 어렵다.
import ast, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
CFG = json.loads((ROOT / 'config' / 'projects.json').read_text(encoding='utf-8'))['projects']
ok = 0

# ── 2026-10-26 · 프로젝트 목록은 **엑셀이 만든다** ─────────────────
#
# 전에는 블룸 품목 여덟 개를 config 에 미리 적어 뒀다. 그런데 양식에
# 적힌 이름이 그와 달라지면(CORVA EFM KPE · SM · Telemaetry Cabinet)
# 화면에는 '등록된 모델 없음' 짜리와 새로 생긴 것이 나란히 서서, 어느
# 쪽이 진짜인지 알 수 없게 됐다.
#
# 이제 기준은 하나다 — **올라온 엑셀.** config 에는 반도체만 남기고,
# 다른 사업부 프로젝트는 양식을 올릴 때 만들어진다
# (_df_create_projects). 그때 블룸이면 bloom_item 도 같이 붙는다.
bloom = [p for p in CFG if p.get('division_id') == 'bloom']
assert not bloom, \
    'config 에 블룸 프로젝트가 아직 박혀 있다 (%d개) — 엑셀이 목록을 만든다' % len(bloom)
ok += 1
assert all(p.get('division_id') in ('semiconductor', 'system') for p in CFG), \
    '반도체 · 공용 말고 다른 사업부가 config 에 남아 있다: %r' % \
    sorted({p.get('division_id') for p in CFG})
ok += 1
# 반도체는 안 건드렸는지
assert len([p for p in CFG if p.get('division_id') == 'semiconductor']) >= 12
ok += 1
# 양식으로 프로젝트를 만들 때 일 보고 품목 이름을 붙이는가.
# 안 붙이면 새로 생긴 블룸 프로젝트가 일 보고를 잘라 볼 열쇠가 없다.
assert 'row["bloom_item"] = r["owner"]' in SRC, \
    '양식으로 만든 블룸 프로젝트에 bloom_item 을 안 붙인다'
assert '_daily_store_key(division_id)' in SRC, \
    '일 보고 사업부인지 안 보고 bloom_item 을 붙인다'
# 2026-10-26 — 고객사형(ESS)에는 안 붙인다. 양식 첫 열이 고객사('SDI')라
# 일 보고의 품목 이름과 다르다 — 붙이면 보드가 통째로 빈다.
assert '_dcol.shape_of(division_id) == "프로젝트형"' in SRC, \
    '고객사형 양식에까지 품목 이름을 붙인다'
ok += 1

# ── 잘라 보기 ─────────────────────────────────────────────────────
tree = ast.parse(SRC)
srcs = {n.name: ast.get_source_segment(SRC, n) for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name in ('_norm_label', '_bloom_item_of', '_bloom_slice')}
assert set(srcs) == {'_norm_label', '_bloom_item_of', '_bloom_slice'}, srcs.keys()


# 잘라 보기는 config 와 상관없는 계산이다. 이제 블룸 프로젝트는 엑셀을
# 올려야 생기므로, 여기서는 '양식이 만들었을 법한 모양' 을 지어서 쓴다.
_FAKE = [
    {'id': 'bloom_sl7', 'division_id': 'bloom', 'label': 'SL7', 'bloom_item': 'SL7'},
    {'id': 'bloom_main', 'division_id': 'bloom', 'label': '블룸 (전체)'},
] + [p for p in CFG if p.get('division_id') == 'semiconductor']


class _CL:
    @staticmethod
    def get_project(pid):
        return next((p for p in _FAKE if p['id'] == pid), None)


g = {'_cl': _CL}
for n in ('_norm_label', '_bloom_item_of', '_bloom_slice'):
    exec(srcs[n], g)

assert g['_bloom_item_of']('bloom_sl7') == 'SL7'
assert g['_bloom_item_of']('bloom_main') == ''
assert g['_bloom_item_of']('chamber') == '', '반도체 프로젝트가 블룸으로 잡힌다'
assert g['_bloom_item_of']('없는키') == ''
ok += 1

BOARD = {'title': 't', 'report_date': '2026-09-14', 'notes': [{'text': 'n'}],
         'dates': ['2026-09-13', '2026-09-14', '2026-09-20'],
         'items': [
             {'item': 'SL7', 'steps': [
                 {'step': 'NCT(박장)', 'group': 'NCT',
                  'days': {'2026-09-13': {'plan': 27, 'actual': 10},
                           '2026-09-14': {'plan': 27, 'actual': None}}}]},
             {'item': 'Corva KPE', 'steps': [
                 {'step': '조립(박닌)', 'group': '조립',
                  'days': {'2026-09-20': {'plan': 50, 'actual': 0}}}]},
         ]}

sl = g['_bloom_slice'](BOARD, 'SL7')
assert [i['item'] for i in sl['items']] == ['SL7'], sl['items']
ok += 1
# 날짜도 그 품목 기준으로 다시 낸다 (남의 날짜가 열로 뜨면 안 된다)
assert sl['dates'] == ['2026-09-13', '2026-09-14'], sl['dates']
ok += 1
# 원본은 안 건드린다
assert len(BOARD['items']) == 2 and len(BOARD['dates']) == 3
ok += 1
# 제목·메모 같은 건 그대로 따라온다
assert sl['title'] == 't' and sl['notes'] == [{'text': 'n'}]
ok += 1
# 없는 품목이면 빈 보드
assert g['_bloom_slice'](BOARD, 'YFP')['items'] == []
ok += 1

# ── 업로드는 어느 품목에서 눌러도 한 곳에 저장 ────────────────────
assert SRC.count('_BLOOM_STORE if _bloom_item_of(_model_key_alias(project_key))') == 2, \
    '미리보기·저장 두 곳 다 전체 저장소로 보내야 한다'
ok += 1
assert '_store = _BLOOM_STORE if _item else _key' in SRC, \
    '품목 프로젝트가 자기 저장소를 따로 본다'
ok += 1

# ── 앱 ────────────────────────────────────────────────────────────
M = ROOT.parent / 'mobile' / 'lib'
SVC = (M / 'services' / 'bloom_service.dart').read_text(encoding='utf-8')
assert 'Map<String, BloomDailyBoard> _cache' in SVC, \
    '캐시가 하나뿐이면 다른 품목을 열 때 남의 값이 보인다'
assert 'static bool isItemKey(String key)' in SVC
ok += 1
OV = (M / 'screens' / 'project_overview_screen.dart').read_text(encoding='utf-8')
assert 'BloomService.isItemKey(widget.projectKey)' in OV
assert 'BloomTodayCard(board: _bloom)' in OV, '품목 화면에 일 보드가 없다'
ok += 1
# 사업부 화면의 '오늘' 카드는 전체(bloom_main) 그대로
DIV = (M / 'screens' / 'division_projects_screen.dart').read_text(encoding='utf-8')
assert 'BloomTodayCard(board: _bloom)' in DIV, '사업부 오늘 카드가 사라졌다'
assert "static const String projectKey = 'bloom_main'" in SVC
ok += 1

print(f'전부 통과 ({ok}/15)')
