# 자동차 수주 자료를 양식 품목에 얹는다 (2026-11-03)
#   python3 backend/tests/test_auto_order_merge.py
#
# Min: "auto는 안 될것 같아 나중에 자동화도 생길수도 있어서 그땐
#       automation_* 써야돼서 auto면 겹칠수도 있어"
#
# 자동차에 프로젝트가 두 벌 있었다 — 양식이 만든 automotive_* 32개와
# 수주 엑셀이 만든 auto_* 4개. 중복이 아니라 다른 자료였는데(수주는
# 원가·연도별 수주 물량), auto_* 키가 프로젝트 목록에 없어서
# /divisions/automotive/summary 가 revenue 0 을 내고 있었다.
#
# 이 마이그레이션은 **자료를 지우는** 일을 한다. 얹을 자리를 못 찾은
# 채로 원본을 지우면 수주 자료가 통째로 사라지고, 수주 엑셀 원본이
# 서버에도 저장소에도 없어서 되돌릴 수가 없다. 그래서 '못 찾으면
# 아무것도 안 지운다' 를 제일 먼저 확인한다.
import ast
import copy
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


NAMES = ('_AUTO_ORDER_MOVE', '_AUTO_ORDER_DROP', '_AUTO_ORDER_PROJECTS',
         '_AUTO_DUP_PROJECT', '_auto_order_done')
G = {'__builtins__': __builtins__}
for n in ast.parse(SRC).body:
    if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in NAMES for t in n.targets):
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
    if isinstance(n, ast.FunctionDef) and n.name == '_auto_order_merge':
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)

for n in NAMES + ('_auto_order_merge',):
    ok(n in G, 'main.py 에 %s 가 없다' % n)
if FAIL:
    print('\n'.join(FAIL))
    raise SystemExit(1)

merge = G['_auto_order_merge']
MOVE = G['_AUTO_ORDER_MOVE']
DROP = G['_AUTO_ORDER_DROP']

# ── 짝 표가 실제 자료와 맞는지 ───────────────────────────────────
ok(len(MOVE) == 6, '옮길 짝이 6건이 아니다: %d' % len(MOVE))
ok(len(DROP) == 3, '버릴 것이 3건이 아니다: %d' % len(DROP))
ok(sorted(G['_AUTO_ORDER_PROJECTS']) ==
   ['auto_kefico', 'auto_schaeffler', 'auto_stellantis', 'auto_valeo'],
   '지울 프로젝트 목록이 바뀌었다: %r' % (G['_AUTO_ORDER_PROJECTS'],))
# 옮길 자리는 전부 automotive_ 로 시작해야 한다 — auto_ 를 없애는 게 목적이다
for _s, _sm, t, _tm in MOVE:
    ok(t.startswith('automotive_'), '%s 는 automotive_ 로 시작해야 한다' % t)
    ok(not t.startswith('auto_'), '%s 가 아직 auto_ 다' % t)


def world():
    """운영 자료와 같은 모양. 수주 블록은 실제 값에서 줄여 왔다."""
    def o(name, **kw):
        a = {'end_customer': kw.pop('ec', ''), 'site': kw.pop('site', ''),
             'cost': {'material': 1.0}, 'contract': {'2026': {'qty': 1, 'revenue': 2.0}}}
        a.update(kw)
        return {'id': name, 'name': name, 'group': '양산', 'auto': a}

    def f(mid, name, **kw):
        m = {'id': mid, 'name': name, 'part_number': mid, 'group': '양산'}
        m.update(kw)
        return m

    return {'projects': {
        'auto_schaeffler': {'models': [o('SVCT', price_fx=27.06), o('OV1', price_fx=30.73)]},
        'auto_kefico': {'models': [o('V2LC HOUSING', price_fx=33.63),
                                   o('DCDC HOUSING', ec='CEER'),
                                   o('OBC HOUSING', ec='CEER'),
                                   o('HE ICCU ASSY'),
                                   o('EREV ICCU HOUSING')]},
        'auto_stellantis': {'models': [o('오일펌프하우징', price_fx=27.23)]},
        'auto_valeo': {'models': [o('DCDC HOUSING', ec='PSA')]},
        'automotive_schaeffler': {'models': [
            f('AAA9550840300', 'OV1', po_qty=8559, shipped_qty=4833),
            f('AAA9543030400', 'SVCT', po_qty=11520, shipped_qty=7920),
            f('AAA9983310100', 'SVCT FACELIFT', po_qty=0, shipped_qty=0)]},
        'automotive_schaefller': {'models': [
            f('AAA9550840300', 'OV1', po_qty=8559, shipped_qty=4833),
            f('AAA9543030400', 'SVCT', po_qty=11520, shipped_qty=7920)]},
        'automotive_stellantis': {'models': [f('68666525AA', 'Oil pump'),
                                             f('ZEPSB000658', 'Support Bracket (N)')]},
        'automotive_kefico_vn': {'models': [f('9191030001', 'HOUSING ASSY V2LC'),
                                            f('9191030005', 'COVER UPPER V2LC')]},
        'automotive_kefico_india': {'models': [
            f('9091100001', 'EREV ICCU_HOUSING ASSY'),
            f('9091090001', 'HE ICCU_HOUSING ASSY (V2L)'),
            f('9091060001', 'CEER OBC_HOUSING ASSY'),
            f('9091070005', 'CEER DCDC'),
            f('9191070129', 'DCDC Housing')]},
        'powerbox': {'models': [f('PB1', 'PB1')]},
    }}


def run(data):
    saved, hidden = [], []
    G['_load_models'] = lambda: data
    G['_save_models'] = lambda d: saved.append(d)
    G['_cl'] = type('C', (), {
        'set_project_visible': staticmethod(
            lambda pid, vis, why='': hidden.append((pid, vis, why)) or True)})
    G['_auto_order_done'] = False
    return merge(), saved, hidden


def pick(d, pk, mid):
    for m in (d['projects'].get(pk) or {}).get('models') or []:
        if m.get('id') == mid:
            return m
    return None


# ── 1. 정상 ─────────────────────────────────────────────────────
d = world()
got, saved, hidden = run(d)
ok(len(got.get('moved') or []) == 6, '옮긴 것이 %r' % (got.get('moved'),))
ok(not got.get('missing'), '못 찾은 자리가 있다: %r' % (got.get('missing'),))
ok(len(got.get('dropped') or []) == 3, '버린 것이 %r' % (got.get('dropped'),))
ok(sorted(got.get('removed') or []) ==
   ['auto_kefico', 'auto_schaeffler', 'auto_stellantis', 'auto_valeo'],
   '지운 프로젝트가 %r' % (got.get('removed'),))
ok(got.get('dup') == 'automotive_schaefller', '오타 프로젝트를 안 지웠다: %r' % (got.get('dup'),))
ok(len(saved) == 1, '저장을 %d 번 했다' % len(saved))
ok(hidden == [('automotive_schaefller', False, 'dup_of_automotive_schaeffler')],
   '프로젝트 목록에서 끄지 않았다: %r' % (hidden,))

# auto_ 로 시작하는 프로젝트가 하나도 안 남아야 한다
left = [k for k in d['projects'] if k.startswith('auto_')]
ok(left == [], 'auto_ 프로젝트가 남았다: %r' % (left,))
ok('automotive_schaefller' not in d['projects'], '오타 프로젝트가 남았다')
ok('powerbox' in d['projects'], '남의 프로젝트를 건드렸다')

# 수주 블록이 제 자리에 얹혔나
ok((pick(d, 'automotive_stellantis', '68666525AA') or {}).get('auto', {})
   .get('product') == '오일펌프하우징', '수주 엑셀 제품명을 안 남겼다')
ok((pick(d, 'automotive_schaeffler', 'AAA9543030400') or {}).get('auto', {})
   .get('price_fx') == 27.06, 'SVCT 수주가 안 얹혔다')
ok((pick(d, 'automotive_kefico_vn', '9191030001') or {}).get('auto', {})
   .get('price_fx') == 33.63, 'V2LC 수주가 안 얹혔다')
ok((pick(d, 'automotive_kefico_india', '9091060001') or {}).get('auto', {})
   .get('end_customer') == 'CEER', 'OBC 수주가 안 얹혔다')
ok(pick(d, 'automotive_kefico_india', '9091100001').get('auto'), 'EREV 수주가 안 얹혔다')
# 버린 셋은 어디에도 붙지 않았다
for pk, mid in (('automotive_kefico_india', '9091070005'),
                ('automotive_kefico_india', '9191070129'),
                ('automotive_kefico_india', '9091090001')):
    ok(not (pick(d, pk, mid) or {}).get('auto'),
       '%s/%s 에 확인 안 된 수주를 붙였다' % (pk, mid))
# 남의 품목은 그대로
ok(not (pick(d, 'automotive_stellantis', 'ZEPSB000658') or {}).get('auto'),
   'Support Bracket 에 수주를 붙였다')

# ── 2. 얹을 자리가 없으면 아무것도 지우지 않는다 ───────────────
d = world()
d['projects']['automotive_kefico_vn']['models'] = [
    {'id': '9191030005', 'name': 'COVER UPPER V2LC'}]      # 9191030001 이 사라졌다
got, saved, hidden = run(d)
ok(got.get('missing') == ['automotive_kefico_vn/9191030001'],
   '못 찾은 자리를 안 알렸다: %r' % (got.get('missing'),))
ok('auto_kefico' in d['projects'], '자리를 못 찾았는데 auto_kefico 를 지웠다')
ok('auto_schaeffler' in d['projects'], '자리를 못 찾았는데 다른 프로젝트까지 지웠다')
ok('automotive_schaefller' in d['projects'], '자리를 못 찾았는데 오타 프로젝트를 지웠다')
ok(hidden == [], '자리를 못 찾았는데 프로젝트를 껐다')

# ── 3. 오타 프로젝트는 숫자가 같을 때만 지운다 ─────────────────
d = world()
d['projects']['automotive_schaefller']['models'][0]['shipped_qty'] = 9999
got, saved, hidden = run(d)
ok(got.get('dup') == '', '숫자가 다른데 오타 프로젝트를 지웠다')
ok('automotive_schaefller' in d['projects'], '숫자가 다른데 지웠다')
ok(hidden == [], '숫자가 다른데 껐다')
ok(sorted(got.get('removed') or []) ==
   ['auto_kefico', 'auto_schaeffler', 'auto_stellantis', 'auto_valeo'],
   'auto_* 는 그대로 지워야 한다: %r' % (got.get('removed'),))

# ── 4. 이미 수주가 있는 품목은 덮지 않는다 ─────────────────────
d = world()
pick(d, 'automotive_stellantis', '68666525AA')['auto'] = {'mine': True}
got, saved, hidden = run(d)
ok(pick(d, 'automotive_stellantis', '68666525AA')['auto'] == {'mine': True},
   '이미 있는 수주를 덮었다')
ok(len(got.get('moved') or []) == 5, '덮지 않은 것까지 옮겼다고 센다: %r' % (got.get('moved'),))

# ── 5. 두 번 돌지 않는다 ───────────────────────────────────────
d = world()
G['_load_models'] = lambda: d
saved = []
G['_save_models'] = lambda x: saved.append(x)
G['_cl'] = type('C', (), {'set_project_visible': staticmethod(lambda *a, **k: True)})
G['_auto_order_done'] = False
first = merge()
second = merge()
ok(len(first.get('moved') or []) == 6, '첫 번째가 %r' % (first.get('moved'),))
ok(second == {}, '두 번째에도 일을 했다: %r' % (second,))
ok(len(saved) == 1, '저장을 %d 번 했다' % len(saved))

# ── 6. 이미 정리된 서버에서 또 돌아도 조용하다 ─────────────────
d = world()
run(d)
clean = copy.deepcopy(d)
got, saved, hidden = run(d)
ok(got.get('moved') == [] and not got.get('removed'),
   '정리된 자료를 또 건드렸다: %r' % (got,))
ok(len(saved) == 0, '할 일이 없는데 저장했다')
ok(d == clean, '정리된 자료가 바뀌었다')

# ── 7. 뜰 때 부른다 ────────────────────────────────────────────
ok('_auto_order_merge()' in SRC, '시작할 때 부르는 자리가 없다')

if FAIL:
    print('\n'.join(FAIL))
    raise SystemExit(1)
print('ok — 자동차 수주 자료 합치기')
