# ESS 프로젝트는 한 벌뿐이다 (2026-11-03)
#   python3 backend/tests/test_ess_one_set.py
#
# Min: "sdi는 어디서 나왔는지 모르겠지만 만약에 ESS 에 있는 SDI 데이터라면
#       ess_sdi랑 합쳐야 될텐데..."
#
# ESS 사업부에 프로젝트가 여섯 개로 보였다. 손으로 만든 sdi · fluence ·
# epc_power 와 사업부 양식이 만든 ess_sdi · ess_fluence · ess_epc_power 가
# 나란히 있었다. 숫자는 두 벌이 똑같았고(PO · 출하 · 판가 전부 확인),
# 품목 이름만 달랐다 — 옛 벌은 'SSTK_SKID', ess_ 벌은 일 보고 엑셀에
# 적힌 '스마트스택 SKID'. 그래서 일 보고는 ess_ 벌에만 붙고 옛 벌은
# 보드를 아예 못 찾았다.
#
# 옛 키가 열세 곳에 손으로 박혀 있었다 (main.py 7 · admin_v2.html 6 ·
# division_columns.py 1 · app_config.dart 1). 한 곳만 되살아나도 지운
# 프로젝트가 화면에 다시 서거나, ESS 인데 반도체식 화면이 뜬다.
# 그래서 사람 눈으로 확인하지 않고 기계로 훑는다.
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


# ── 1. 옛 키가 코드에 남아 있지 않다 ────────────────────────────
# 지우개 표(_ESS_LEGACY)만 예외다. 그 줄에는 옛 키가 있어야 한다.
OLD = ('sdi', 'fluence', 'epc_power')
TARGETS = [ROOT / 'main.py', ROOT / 'admin_v2.html',
           ROOT / 'division_columns.py',
           REPO / 'mobile' / 'lib' / 'config' / 'app_config.dart']
for path in TARGETS:
    ok(path.exists(), '%s 가 없다' % path.name)
    if not path.exists():
        continue
    for i, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if '_ESS_LEGACY' in line or 'ess_legacy' in line:
            continue
        for k in OLD:
            if ("'%s'" % k) in line or ('"%s"' % k) in line:
                FAIL.append('%s:%d 에 옛 ESS 키 %s 가 남았다 — %s'
                            % (path.name, i, k, line.strip()[:70]))

# ── 2. ESS 판별은 접두사로 한다 ─────────────────────────────────
# 2026-11-05 — main.py 안에 있던 admin v2 화면 사본을 지웠다. 화면은 admin_v2.html 하나뿐.
for path in (ROOT / 'admin_v2.html',):
    t = path.read_text(encoding='utf-8')
    ok("indexOf('ess_') === 0" in t,
       '%s 의 _projIsEss 가 접두사 검사를 안 쓴다' % path.name)
ok("'ess_sdi', 'ess_fluence', 'ess_epc_power'" in
   (ROOT / 'admin_v2.html').read_text(encoding='utf-8'),
   'DAILY_BOARD_PROJECTS 의 ESS 키가 옛것이다')

# 사업부 열 설정도 접두사 하나만 본다
dc = {'__builtins__': __builtins__}
for n in ast.parse((ROOT / 'division_columns.py').read_text(encoding='utf-8')).body:
    if isinstance(n, ast.Assign):
        try:
            exec(compile(ast.Module([n], []), 'division_columns.py', 'exec'), dc)
        except Exception:
            pass
_ess_cols = None
for v in dc.values():
    if isinstance(v, dict) and isinstance(v.get('ess'), dict):
        _ess_cols = v['ess']
        break
ok(_ess_cols is not None, 'division_columns.py 에서 ess 설정을 못 찾았다')
if _ess_cols is not None:
    ok(_ess_cols.get('project_board_keys') == ['ess_'],
       'ess 의 project_board_keys 가 %r 이다' % (_ess_cols.get('project_board_keys'),))

# ── 3. 정리 함수 — 짝에 품목이 있을 때만 지운다 ─────────────────
G = {'__builtins__': __builtins__}
tree = ast.parse(SRC)
for n in tree.body:
    if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in ('_ESS_LEGACY', '_ess_legacy_done')
            for t in n.targets):
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
    if isinstance(n, ast.FunctionDef) and n.name == '_ess_legacy_cleanup':
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)

ok('_ess_legacy_cleanup' in G, 'main.py 에 _ess_legacy_cleanup 이 없다')
ok(G.get('_ESS_LEGACY') == {'sdi': 'ess_sdi', 'fluence': 'ess_fluence',
                            'epc_power': 'ess_epc_power'},
   '_ESS_LEGACY 표가 바뀌었다: %r' % (G.get('_ESS_LEGACY'),))
if FAIL:
    print('\n'.join(FAIL))
    raise SystemExit(1)

clean = G['_ess_legacy_cleanup']


def run(data):
    """stub 을 꽂고 한 번 돌린다. (지운 키, 저장 횟수) 를 준다."""
    saved = []
    G['_load_models'] = lambda: data
    G['_save_models'] = lambda d: saved.append(d)
    G['_ess_legacy_done'] = False
    return clean(), len(saved)


def proj(*keys):
    return {'projects': {k: {'models': [{'id': 'X'}]} for k in keys}}


# 두 벌이 다 있으면 옛 벌만 지운다
d = proj('sdi', 'ess_sdi', 'fluence', 'ess_fluence', 'epc_power',
         'ess_epc_power', 'powerbox')
got, n = run(d)
ok(sorted(got) == ['epc_power', 'fluence', 'sdi'], '지운 키가 %r 이다' % (got,))
ok(n == 1, '저장을 %d 번 했다 (한 번이어야 한다)' % n)
ok(sorted(d['projects']) == ['ess_epc_power', 'ess_fluence', 'ess_sdi', 'powerbox'],
   '남은 프로젝트가 %r 이다' % (sorted(d['projects']),))

# 짝이 비어 있으면 손대지 않는다 — 양식을 아직 안 올린 상태다
d = {'projects': {'sdi': {'models': [{'id': 'X'}]}, 'ess_sdi': {'models': []}}}
got, n = run(d)
ok(got == [], '짝이 빈데 %r 를 지웠다' % (got,))
ok(n == 0, '지운 것도 없는데 저장했다')
ok('sdi' in d['projects'], 'sdi 가 사라졌다')

# 짝이 아예 없을 때도 손대지 않는다
d = proj('sdi')
got, n = run(d)
ok(got == [] and n == 0, '짝이 없는데 건드렸다: %r' % (got,))

# 이미 ess_ 한 벌뿐이면 조용히 지나간다
d = proj('ess_sdi', 'ess_fluence', 'ess_epc_power')
got, n = run(d)
ok(got == [] and n == 0, '지울 것이 없는데 저장했다')

# 한 프로세스에서 두 번 돌지 않는다 — 매 요청마다 저장하면 안 된다
d = proj('sdi', 'ess_sdi')
G['_load_models'] = lambda: d
saved = []
G['_save_models'] = lambda x: saved.append(x)
G['_ess_legacy_done'] = False
first = clean()
second = clean()
ok(first == ['sdi'], '첫 번째에 %r 를 지웠다' % (first,))
ok(second == [], '두 번째에도 일을 했다: %r' % (second,))
ok(len(saved) == 1, '저장을 %d 번 했다' % len(saved))

# ── 4. 뜰 때 한 번 부른다 ───────────────────────────────────────
ok('@app.on_event("startup")' in SRC and '_ess_legacy_cleanup()' in SRC,
   '시작할 때 정리를 부르는 자리가 없다')

if FAIL:
    print('\n'.join(FAIL))
    raise SystemExit(1)
print('ok — ESS 프로젝트 한 벌')
