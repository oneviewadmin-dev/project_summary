# 고객사 이름의 오타를 가장 가까운 한 곳에 붙인다 (2026-11-03)
#   python3 backend/tests/test_form_typo_owner.py
#
# Min: "schaefller로 적힌건 결국에는 오타거든? 근데 누가봐도 제일 근접하고
#       가까운게 schaeffler이잖아, 그런것 처럼 만약에 오타가 나도 최대한
#       비슷한 느낌의 고객사품목이 있는지 확인을 해서 매핑을 해줘"
#
# 자동차 양식에 'Schaefller' 라고 적혀 와서 'Schaeffler' 를 못 찾고
# 프로젝트가 하나 더 생겼다. 같은 품번·같은 수량이 두 곳에 나뉘어
# 들어갔고, 개발 일정 양식을 붙일 때 품번이 두 곳에서 걸려 매칭도 흐려졌다.
#
# **품목 이름에는 절대 걸지 않는다.** 등록된 품목 1,331종으로 재 봤더니
# 글자 하나 차이인데 서로 다른 부품인 쌍이 78개였다 (좌/우 · 안/바깥 ·
# 등급). 아래 4번이 그 중 실제 이름들로 '안 붙는다' 를 못 박는다.
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


WANT = ('_df_norm', '_df_keys', '_df_digits', '_df_dam1',
        '_df_typo_project', '_df_find_project', '_df_typo_warnings')
G = {'__builtins__': __builtins__}
for n in ast.parse(SRC).body:
    if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == '_DF_TYPO_MIN_LEN' for t in n.targets):
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
    if isinstance(n, ast.FunctionDef) and n.name in WANT:
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
for n in WANT:
    ok(n in G, 'main.py 에 %s 가 없다' % n)
if FAIL:
    print('\n'.join(FAIL))
    raise SystemExit(1)

keys = G['_df_keys']
find = G['_df_find_project']
typo = G['_df_typo_project']


def index(*names):
    """이름들 → {열쇠: 프로젝트키} 색인 (_df_owner_index 와 같은 모양)."""
    idx = {}
    for name in names:
        pid = 'p_' + G['_df_norm'](name)
        for k in keys(name):
            idx.setdefault(k, pid)
    return idx


def pid(name):
    return 'p_' + G['_df_norm'](name)


# ── 1. 오타는 붙는다 ────────────────────────────────────────────
CASES = [
    # (적혀 온 이름, 이미 있는 이름)
    ('Schaefller', 'Schaeffler'),                  # 글자 하나 더
    ('Schaeffer', 'Schaeffler'),                   # 글자 하나 빠짐
    ('Schaefflar', 'Schaeffler'),                  # 글자 하나 다름
    ('스마스트택 POD', '스마트스택 POD'),               # 자리바꿈 (일 보고에 실제로 이렇게 온다)
    ('Telemaetry Cabinet', 'Telemetry Cabinet'),
]
for wrong, right in CASES:
    idx = index(right)
    got = find(wrong, idx)
    ok(got == pid(right), "'%s' 를 '%s' 에 못 붙였다 (%r)" % (wrong, right, got))
    # 알림이 남아야 한다 — 조용히 고치면 다음 달에 또 와도 아무도 모른다
    notes = {}
    find(wrong, idx, notes)
    ok(notes == {wrong: pid(right)}, "'%s' 를 고쳤는데 안 알린다: %r" % (wrong, notes))

# 뒤가 잘린 이름('VALEO ETAPLE')은 전부터 2단계가 잡았다 — 오타 길이 아니라
# 알림도 안 뜬다. 그 길이 살아 있는지만 확인한다.
notes = {}
ok(find('VALEO ETAPLE', index('VALEO ETAPLES'), notes) == pid('VALEO ETAPLES'),
   '뒤가 잘린 이름을 못 찾는다')
ok(notes == {}, '2단계가 잡은 것을 오타라고 알린다: %r' % notes)

# 정확히 같은 이름은 오타 길로 안 간다 (알림이 뜨면 안 된다)
notes = {}
ok(find('Schaeffler', index('Schaeffler'), notes) == pid('Schaeffler'),
   '같은 이름을 못 찾는다')
ok(notes == {}, '같은 이름인데 오타라고 알린다: %r' % notes)

# ── 2. 서로 다른 고객사는 안 붙는다 ─────────────────────────────
#    실제로 자동차·ESS 에 나란히 있는 이름들이다.
APART = [
    ('VALEO SFL', 'VALEO SLP'),
    ('KEFICO KR', 'KEFICO VN'),
    ('LGE KR', 'LGE VN'),
    ('SDI KR', 'SDI PPE'),
    ('SDI AUSTRIA', 'SDI HUNGARY'),
    ('HYUNDAI JG', 'HYUNDAI MOBIS'),
]
for a, b in APART:
    ok(find(a, index(b)) == '', "'%s' 를 '%s' 에 붙였다 — 다른 고객사다" % (a, b))

# ── 3. 후보가 둘이면 안 붙인다 ──────────────────────────────────
#    잘못 붙은 줄은 아무도 못 알아챈다. 못 붙은 줄은 화면이 보여 준다.
idx = index('Schaeffler', 'Schaefflor')
ok(typo('Schaefflar', idx) == '', '후보가 둘인데 아무 데나 붙였다')
notes = {}
ok(find('Schaefflar', idx, notes) == '', '후보가 둘인데 붙였다')
ok(notes == {}, '안 붙였는데 알림을 남겼다: %r' % notes)

# ── 4. 숫자가 다르면 절대 안 붙는다 ─────────────────────────────
#    GSP2000 ↔ GSP5000 은 플루언스의 서로 다른 제품이다.
for a, b in (('GSP2000', 'GSP5000'), ('SBB 1.5UL', 'SBB 1.7UL'),
             ('M10 인버터', 'M20 인버터')):
    ok(find(a, index(b)) == '', "숫자가 다른데 '%s' 를 '%s' 에 붙였다" % (a, b))

# ── 5. 품목 이름에는 이 길을 쓰지 않는다 ───────────────────────
#
# 아래는 전부 실제로 등록된, 서로 다른 부품이다. 이름만 보면 한 글자
# 차이라서 **어떤 글자 규칙으로도 오타와 가를 수 없다** —
#     CT1 RCL TAIL LWR PCB RH      ↔ ... LH          (좌/우)
#     SU2i_..._IB_LAM_LH           ↔ ..._OB_LAM_LH   (안쪽/바깥쪽)
#     CL4 RCL OS STOP C LAM LH+RH  ↔ ... STOP A ...  (등급)
#     CEFEM FE(VN)                 ↔ CEFEM BE(VN)
#     JG FR_HOUSING ASSY_LHD       ↔ ..._RHD
#     Curb Impactor LH             ↔ Curb Impactor RH
# 1,331종 중 이런 쌍이 78개였다. 그래서 안전장치는 '함수를 똑똑하게' 가
# 아니라 **고객사 이름에서만 부른다** 이다. 그 자리를 기계로 지킨다.
ok(SRC.count('_df_typo_project(') == 2,
   '오타 매칭을 _df_find_project 밖에서도 부른다 — 품목에 번지면 좌/우가 섞인다')
_pick = SRC[SRC.find('def _df_pick_model'):]
_pick = _pick[:_pick.find('\ndef ', 10)]
ok('_df_typo' not in _pick, '_df_pick_model 이 오타 매칭을 쓴다 — 품목에는 쓰면 안 된다')
_mk = SRC[SRC.find('def _df_model_key'):]
_mk = _mk[:_mk.find('\ndef ', 10)]
ok('_df_typo' not in _mk, '_df_model_key 가 오타 매칭을 쓴다')

# ── 6. 너무 짧은 이름은 안 본다 ─────────────────────────────────
ok(G['_DF_TYPO_MIN_LEN'] >= 6, '최소 길이가 너무 짧다')
for a, b in (('TC', 'TD'), ('BOP', 'BOQ'), ('SDI', 'SDK')):
    ok(typo(a, index(b)) == '', "짧은 이름 '%s' 를 '%s' 에 붙였다" % (a, b))

# ── 7. 알림 문구에 두 이름이 다 들어간다 ────────────────────────
G['_cl'] = type('C', (), {'get_project': staticmethod(
    lambda pid: {'label': 'Schaeffler'})})
_w = G['_df_typo_warnings']({'Schaefller': 'automotive_schaeffler'})
ok(len(_w) == 1, '경고가 %d줄이다' % len(_w))
ok('Schaefller' in _w[0] and 'Schaeffler' in _w[0]
   and 'automotive_schaeffler' in _w[0],
   '경고에 적힌 이름·붙인 곳이 다 안 들어간다: %r' % (_w,))

# ── 8. 미리보기와 반영이 같은 알림을 낸다 ───────────────────────
ok(SRC.count('_df_typo_warnings(typo)') == 2,
   '미리보기와 반영 중 한쪽만 알린다')
# 미리보기는 _df_plan 을 거쳐(notes), 반영은 직접(typo) 모은다 — 둘 다 모아야 한다
ok('_df_find_project(it.get("owner"), idx, notes)' in SRC,
   '미리보기 경로가 오타를 안 모은다')
ok('_df_find_project(it.get("owner"), idx, typo)' in SRC,
   '반영 경로가 오타를 안 모은다')
ok(SRC.count('_df_plan(got["items"], idx, typo)') == 1,
   '미리보기가 오타 그릇을 안 넘긴다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 고객사 이름 오타 매칭 (품목은 제외)')
