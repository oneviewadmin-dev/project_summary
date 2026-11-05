# 캘린더를 운영 일정에 연결한다 (2026-11-04)
#   python3 backend/tests/test_calendar_events.py
#
# Min: "캘린더랑 일정들이랑 연결 되어 있어?" → "연결 부탁할게"
#
# 캘린더는 옛 주간보고 카드(/dashboard) 글자 속의 '(11-07)' 을 찾아 일정을
# 만들었다. 카드 86장 중 날짜가 잡히는 카드가 0장이라 통째로 비어 있었다.
# 이제 서버가 개발 단계 예정·실적일과 주차 계획에서 모아 준다.
#
# 제일 지켜야 할 것 — **홈의 '일정 지연' 수와 같아야 한다.** 운영 자료로
# 돌렸을 때 처음엔 캘린더 16 · 홈 18 이었다. 빠진 둘은 PBX 양산품으로,
# 날짜 없이 비고에 '지연' 이라고 적혀 있었다. 날짜를 지어내지 않고
# 'undated' 로 따로 내서 합계를 맞췄다.
import ast
import datetime as _d
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = ROOT.parent / 'mobile' / 'lib'
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


WANT = ('_cal_date', '_cal_week_monday', '_cal_category', '_calendar_events',
        'get_calendar_events', '_as_int')
class _App:                                     # @app.get 장식만 통과시킨다
    def get(self, *a, **k):
        return lambda f: f


G = {'__builtins__': __builtins__, 'app': _App()}
for n in ast.parse(SRC).body:
    if isinstance(n, ast.FunctionDef) and n.name in WANT:
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
    if isinstance(n, ast.AnnAssign) and getattr(n.target, 'id', '') == '_CAL_CACHE':
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
for w in WANT:
    ok(w in G, 'main.py 에 %s 가 없다' % w)
ok('@app.get("/calendar/events")' in SRC, '/calendar/events 주소가 없다')
if FAIL:
    print('\n'.join(FAIL))
    raise SystemExit(1)

# ── 1. 날짜 읽기 — 글자는 날짜가 아니다 ─────────────────────────
cd = G['_cal_date']
ok(cd('2026-11-07') == _d.date(2026, 11, 7), 'ISO 날짜를 못 읽는다')
ok(cd('2026.11.7') == _d.date(2026, 11, 7), '점 날짜를 못 읽는다')
ok(cd('Lam측 날짜지정') is None, '글자를 날짜로 읽었다')
ok(cd('진행 중') is None and cd('') is None and cd(None) is None, '빈 값을 날짜로 읽었다')
ok(cd('2026-06-31') is None, '없는 날짜(6/31)를 받아들였다')

# ── 2. 주차 → 그 주 월요일 ──────────────────────────────────────
wm = G['_cal_week_monday']
ok(wm('2026-11', 'W46') == _d.date(2026, 11, 9), 'W46 월요일이 아니다')
ok(wm('2026-11', 'W45') == _d.date(2026, 11, 2), 'W45 월요일이 아니다')
ok(wm('2026-12', 'W53') == _d.date(2026, 12, 28), '2026 W53 을 못 찾는다')
ok(wm('2026-12', 'W01') == _d.date(2026, 12, 28) + _d.timedelta(days=7),
   '12월 밑의 W01 은 다음 해 주차다')
ok(wm('2026-11', 'Wxx') is None, '이상한 주차를 날짜로 바꿨다')

# ── 3. 분류 — 앱 필터와 같은 말 ─────────────────────────────────
cc = G['_cal_category']
ok(cc('입고') == 'receiving', '입고가 입고로 안 간다')
ok(cc('FAIR 제출') == 'approval' and cc('최종 승인') == 'approval', '승인 단계 분류')
ok(cc('06 SOP') == 'shipping', 'SOP 는 출하 쪽이다')
ok(cc('가공 (조립)') == 'milestone', '나머지는 마일스톤')

# ── 4. 모으기 — 홈과 같은 판정, 날짜 없는 지연 ──────────────────
today = _d.date.today()
past = (today - _d.timedelta(days=10)).isoformat()
fut = (today + _d.timedelta(days=5)).isoformat()
done_day = (today - _d.timedelta(days=30)).isoformat()


def enrich(m, ph='', did=''):
    return m                                   # 이미 계산된 값으로 준다


models = {
    'frame': {'models': [
        # 지금 걸린 단계가 지연 → late 하나, 지난 단계는 완료
        {'id': 'A', 'name': 'SABRE', 'alert': '지연', 'current_stage': '최종 승인',
         'process': [{'name': 'FAIR 제출', 'expected': done_day, 'actual': done_day},
                     {'name': '최종 승인', 'expected': past, 'actual': ''},
                     {'name': '양산', 'expected': fut, 'actual': ''}]},
        # 예정일이 지났어도 지금 단계가 아니면 지연으로 세지 않는다 (홈과 같게)
        {'id': 'B', 'name': 'VECTOR', 'alert': '정상', 'current_stage': '가공',
         'process': [{'name': '입고', 'expected': past, 'actual': ''},
                     {'name': '가공', 'expected': fut, 'actual': ''}]},
        # 보류는 뺀다
        {'id': 'C', 'name': 'DROP', 'alert': '지연', 'hold': '드롭예정',
         'current_stage': '입고',
         'process': [{'name': '입고', 'expected': past, 'actual': ''}]},
    ]},
    'pbx': {'models': [
        # 비고에 '지연' — 날짜가 없다 → undated
        {'id': 'D', 'name': 'CEFEM VDP', 'alert': '지연', 'note': '시트메탈 지연',
         'weekly_plan': {'2026-11': {'W46': {'plan': 3, 'actual': 0}}}},
        {'id': 'E', 'name': 'AHM', 'alert': '정상',
         'weekly_plan': {'2026-11': {'W46': {'plan': 2, 'actual': 1},
                                     'W47': {'plan': 0, 'actual': 0}}}},
    ]},
}


class _CL:
    @staticmethod
    def get_projects(visible_only=True):
        return [{'id': 'frame', 'division_id': 'semiconductor'},
                {'id': 'pbx', 'division_id': 'semiconductor'}]

    @staticmethod
    def get_divisions(visible_only=False):
        return [{'id': 'semiconductor', 'label': '반도체사업부'}]


G.update({'_load_models': lambda: {'projects': models},
          '_MODELS_CACHE': {'key': ('t', 1)}, '_cl': _CL,
          '_enrich_model': enrich, '_project_hold': lambda p: '',
          '_model_hold': lambda m: m.get('hold') or '',
          '_display_project_label': lambda pk: pk.upper()})
G['_CAL_CACHE'].update({'key': None, 'data': None})
r = G['get_calendar_events']()
ev, und, cnt = r['events'], r['undated'], r['counts']

late = [x for x in ev if x['status'] == 'late']
ok(len(late) == 1 and late[0]['step'] == '최종 승인',
   '지금 걸린 단계에만 지연을 달아야 한다: %r' % ([x['title'] for x in late],))
ok(late[0]['days'] == 10, '지연 일수가 %r 이다' % late[0]['days'])
ok(not any(x.get('model') == 'VECTOR' and x['status'] == 'late' for x in ev),
   '지금 단계가 아닌데 지연으로 셌다 — 홈 숫자와 갈린다')
ok(not any(x.get('model') == 'DROP' for x in ev + und), '보류 품목을 올렸다')
ok(any(x['status'] == 'done' and x.get('step') == 'FAIR 제출' for x in ev),
   '실적일이 있는 단계를 완료로 안 올렸다')
# 날짜 없는 지연
ok(len(und) == 1 and und[0]['model'] == 'CEFEM VDP', '날짜 없는 지연이 %r' % (und,))
ok('시트메탈 지연' in und[0]['title'], '왜 지연인지 안 적었다')
ok('date' not in und[0], '날짜 없는 지연에 날짜를 지어냈다')
# 합계는 홈과 같은 셈 — 날짜 있는 지연 + 날짜 없는 지연
ok(cnt['late'] == 2, '지연 합계가 %r (날짜 1 + 없음 1 = 2 여야)' % cnt['late'])

# 주차 계획 — 프로젝트 · 주차마다 한 줄로 묶는다
ship = [x for x in ev if x['kind'] == 'ship_plan']
ok(len(ship) == 1, '주차 계획이 품목마다 따로 섰다: %r' % ([x['title'] for x in ship],))
ok(ship and ship[0]['qty_plan'] == 5 and ship[0]['date'] == '2026-11-09',
   '주차 계획 합이나 날짜가 틀렸다: %r' % (ship[:1],))
ok(ship and 'W46 출하 계획 5대' in ship[0]['title'], '제목이 %r' % (ship[:1],))

# 자르기 · 거르기
r2 = G['get_calendar_events'](start='2026-11-09', end='2026-11-09')
ok(r2['events'] and all(x['date'] == '2026-11-09' for x in r2['events'])
   and any(x['kind'] == 'ship_plan' for x in r2['events']), '날짜로 못 자른다')
r3 = G['get_calendar_events'](division='network')
ok(r3['events'] == [] and r3['undated'] == [], '사업부로 못 거른다')

# 같은 자료면 다시 만들지 않는다 (OOM 교훈) — 같은 객체를 돌려준다
_a = G['_calendar_events']()
_b = G['_calendar_events']()
ok(_a is _b, '같은 자료인데 매번 새로 만든다')

# ── 5. 앱 ───────────────────────────────────────────────────────
svc = (LIB / 'services' / 'calendar_service.dart').read_text(encoding='utf-8')
ok('/calendar/events' in svc, '앱이 새 주소를 안 부른다')
ok("j['undated']" in svc, '앱이 날짜 없는 지연을 안 받는다')
scr = (LIB / 'screens' / 'calendar_screen.dart').read_text(encoding='utf-8')
ok('CalendarService.fetch()' in scr, '캘린더 화면이 새 주소를 안 쓴다')
ok('_cardsToEvents(cards)' in scr, '옛 서버에 붙었을 때 떨어질 자리가 없다')
ok('e.isLate' in scr and '..._undated' in scr,
   '마감 목록 맨 위에 일정 지연이 안 선다')
# 2026-11-04 — 제목을 일정 지연 유무로 바꾸면서 그 Text 가 `children: const [`
# 안에 남아 컴파일이 깨졌다 (flutter run: "Not a constant expression").
# 바뀌는 값을 쓰는 자리 바로 위에 const 목록이 있으면 안 된다.
_i = scr.find('_deadline7.any((e) => e.isLate)')
ok(_i > 0 and 'const [' not in scr[max(0, _i - 160):_i],
   '일정 지연 제목이 const 목록 안에 있다 — 컴파일이 안 된다')
evm = (LIB / 'models' / 'calendar_event.dart').read_text(encoding='utf-8')
ok('static CalendarEvent? fromServer(Map j)' in evm, '서버 줄을 못 읽는다')
ok("'일정 지연" in evm, '홈과 같은 말(일정 지연)을 안 쓴다')
row = (LIB / 'components' / 'calendar' / 'calendar_deadline_row.dart').read_text(encoding='utf-8')
ok("'날짜 없음'" in row, '날짜 없는 지연이 D-day 로 보인다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 캘린더가 운영 일정에 붙는다')
