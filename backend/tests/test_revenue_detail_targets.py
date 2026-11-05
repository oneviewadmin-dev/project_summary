# 매출 상세 — 실적이 0 이어도 목표가 있는 사업부는 보인다 (2026-11-04)
#   python3 backend/tests/test_revenue_detail_targets.py
#
# Min: "사업부 밑에 리스트는 있어야 되지 않을까? 그래도 어떤 목표들이
#       있는지를 알아야지"
#
# 11월 매출 상세가 '사업부' 머리글만 있고 줄이 하나도 없었다. 두 겹이었다.
#   1) 앱이 실적 > 0 인 줄만 남겼다 — 달이 막 시작해서 전부 0 이었다.
#   2) 블룸은 계획이 일 보고 보드에 있어서 '그 달 계획 합계' 가 0 이었다.
#      사업부 목록은 같은 보드로 11월 계획 $3,344만을 그리는데 여기만 비었다.
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = ROOT.parent / 'mobile' / 'lib'
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


# ── 1. 일 보고 사업부 금액 — /overview 와 같은 함수를 쓴다 ──────
G = {'__builtins__': __builtins__}
for n in ast.parse(SRC).body:
    if isinstance(n, ast.FunctionDef) and n.name == '_daily_div_money':
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
ok('_daily_div_money' in G, 'main.py 에 _daily_div_money 가 없다')
if FAIL:
    print('\n'.join(FAIL))
    raise SystemExit(1)

_fn = SRC[SRC.find('def _daily_div_money'):]
_fn = _fn[:_fn.find('\ndef ', 10)]
ok('_daily_ship_weeks(pk, month)' in _fn and '_daily_unit_price(' in _fn,
   '목록 카드(/overview)와 다른 계산을 쓴다 — 숫자가 갈린다')

DIV = {'bloom_main': 'bloom', 'yfp': 'bloom', 'sl7': 'bloom', 'noprice': 'bloom',
       'frame': ''}
G['_daily_board_division'] = lambda pk: DIV.get(pk, '')
G['_daily_store_key'] = lambda d: 'bloom_main' if d == 'bloom' else ''
PRICE = {'bloom_main': 999.0, 'yfp': 100.0, 'sl7': 50.0, 'noprice': 0.0}
G['_daily_unit_price'] = lambda proj: proj.get('_price', 0.0)
WEEKS = {
    'bloom_main': {'W45': {'plan': 1000, 'actual': 1000}},     # 저장소 — 빼야 한다
    'yfp': {'W45': {'plan': 10, 'actual': 3}, 'W46': {'plan': 5, 'actual': None}},
    'sl7': {'W46': {'plan': 4, 'actual': 2}},
    'noprice': {'W45': {'plan': 99, 'actual': 99}},           # 판가 없음 — 0
    'frame': {'W45': {'plan': 7, 'actual': 7}},               # 일 보고 아님
}
G['_daily_ship_weeks'] = lambda pk, month: WEEKS.get(pk, {})
projects = {k: {'_price': v} for k, v in PRICE.items()}
plist = [{'id': k} for k in ('bloom_main', 'yfp', 'sl7', 'noprice', 'frame')]
plan, act = G['_daily_div_money'](plist, projects, '2026-11')
ok(plan == 15 * 100 + 4 * 50, '계획 금액이 %r (1700 이어야 — 저장소·판가 없음·일 보고 아님 제외)' % plan)
ok(act == 3 * 100 + 2 * 50, '실적 금액이 %r (400 이어야)' % act)

# ── 2. 목표 사슬 — 파일·직접 입력이 먼저, 보드는 마지막 ────────
_rows = SRC[SRC.find('def _home_division_rows'):]
_rows = _rows[:_rows.find('\n@app.get(', 10)]
i_plan = _rows.find('target = _div_plan_money(models, month)')
i_daily = _rows.find('_daily_div_money(plist, projects, month)')
i_file = _rows.find('_drev.month_plan(did, month)')
ok(i_file > 0 and i_plan > i_file and i_daily > i_plan,
   '일 보고 계산이 파일·직접 입력보다 앞에 있다 — 사람이 정한 목표를 덮는다')
ok('if not target and _daily_store_key(did):' in _rows,
   '목표가 이미 있는데도 보드로 덮는다')
# 같은 보드에서 잡은 목표에만 실적을 붙인다 — 출처가 섞이면 달성률이 의미 없다
_blk = _rows[i_daily:i_daily + 400]
ok('if not actual and _da:' in _blk, '보드 실적을 아무 때나 붙인다')

# ── 3. 전사 화면 — 목표 없는 사업부 이름 · 날짜 ────────────────
_view = SRC[SRC.find('def _all_division_revenue_view'):]
_view = _view[:_view.find('\n@app.get(', 10)]
ok('"no_target": no_target' in _view, '목표 없는 사업부를 안 알린다')
ok('if not float(r.get("actual") or 0):' in _view,
   "실적이 0 인 달에도 '2026-10-05 까지' 가 뜬다")

# ── 4. 앱 ───────────────────────────────────────────────────────
svc = (LIB / 'services' / 'revenue_service.dart').read_text(encoding='utf-8')
ok('g.actual > 0 || g.estimate > 0' in svc, '앱이 실적 0 인 사업부를 지운다')
ok("j['no_target']" in svc, '앱이 목표 없는 사업부를 안 읽는다')
scr = (LIB / 'screens' / 'revenue_detail_screen.dart').read_text(encoding='utf-8')
ok("목표 미등록 · ${r.noTarget.join(' · ')}" in scr, '목표 없는 사업부 이름을 안 보여준다')
ok('if (r.lines.isEmpty)' in scr, '줄이 하나도 없을 때 빈 화면이다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 매출 상세에 목표가 있는 사업부가 선다')
