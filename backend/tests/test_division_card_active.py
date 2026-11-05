# 사업부 카드의 '진행 중' · 잔특근 최신 주차 (2026-11-03)
#   python3 backend/tests/test_division_card_active.py
#
# Min: "잔특근 43주차가 제일 최신인데 반영 안 되어 있는지"
#      "전체 사업부별 카드에 시스템 빼곤 다 진행중이여서 이거 카드 변경 좀 해줘"
#
# ── 카드
# '진행 중' 을 /dashboard 의 주간보고 카드만 보고 정했다. 주간보고를
# 내는 건 반도체뿐이라, 프로젝트가 27개씩 있는 아리스타 · PCB ·
# 자동차 · 네트워크가 전부 '진행 데이터 없음' 이었다.
# 사업부마다 예외를 두지 않는다 — 어느 사업부든 모델이 등록돼 있으면
# 진행 중이다.
#
# ── 잔 · 특근
# 서버는 주차를 안 주면 **가장 최신 주차**를 돌려준다. 앱도 빈 값으로
# 부른다. 그런데 서버가 8초 안에 답을 못 하면 저장본으로 떨어진 채
# 그대로 머물렀다 — 43주차가 올라왔는데 카드는 41주차를 들고 있던
# 이유다. 저장본을 먼저 주고 새 값이 따라오게 한다 (onFresh).
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = ROOT.parent / 'mobile' / 'lib'
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
OT = (ROOT / 'overtime.py').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


# ── 1. 서버는 최신 주차를 준다 ──────────────────────────────────
ok('def for_app' in OT, 'for_app 이 없다')
_f = OT[OT.find('def for_app'):]
_f = _f[:_f.find('\ndef ', 10)]
ok('wk = week_key(wk) or (weeks[-1] if weeks else "")' in _f,
   '주차를 안 주면 최신 주차를 돌려주지 않는다')
ok('def overtime_week' in SRC, '/overtime/week 이 없다')

# ── 2. 앱이 저장본에 머물지 않는다 ──────────────────────────────
_svc = (LIB / 'services' / 'overtime_service.dart').read_text(encoding='utf-8')
ok('onFresh' in _svc, '저장본을 준 뒤 새 값을 안 받는다 — 옛 주차에 머문다')
ok('void Function(OvertimeWeek)? onFresh' in _svc, 'onFresh 를 안 받는다')
_home = (LIB / 'screens' / 'home_screen.dart').read_text(encoding='utf-8')
ok('OvertimeService.fetchWeek(onFresh:' in _home, '홈 카드가 새 값을 안 받는다')

# ── 3. 모델이 있으면 진행 중 — 홈과 목록이 **같은 함수**를 쓴다 ──
#
# Min: "목록에도 홈처럼 동일하게 반영되게끔 연결 되어야지"
#
# 처음에는 이 규칙을 홈 화면 안에 적었다. 그래서 홈에서는 '진행 중' 인
# 아리스타 · PCB · 자동차 · 네트워크가 목록 화면에서는 '진행 데이터
# 없음' 으로 떴다 — 같은 사업부가 화면마다 달라 보였다. 규칙을 두 곳에
# 적으면 또 갈린다. 한 곳에 두고 둘이 부르게 한다.
_dash = (LIB / 'models' / 'dashboard.dart').read_text(encoding='utf-8')
ok('Set<String> divisionsWithModels(' in _dash,
   'models/dashboard.dart 에 공용 규칙이 없다')
ok('DivisionStatus divisionStatusWithModels(' in _dash,
   'models/dashboard.dart 에 공용 상태 판정이 없다')
_rule = _dash[_dash.find('Set<String> divisionsWithModels('):]
_rule = _rule[:_rule.find('\n}')]
ok('modelsTotal ?? 0) > 0' in _rule, '모델 수를 안 본다')
# 사업부 이름을 콕 집지 않는다. 그래야 시스템사업부에 품목을 올리면
# 코드를 안 고쳐도 그날로 '진행 중' 이 된다.
for bad in ("'bloom'", "'pcb'", "'automotive'", "'system'", "'semiconductor'"):
    ok(bad not in _rule, '규칙이 사업부 이름을 콕 집는다: %s' % bad)
_up = _dash[_dash.find('DivisionStatus divisionStatusWithModels('):]
_up = _up[:_up.find('\n}')]
ok('DivisionStatus.empty' in _up and 'DivisionStatus.active' in _up,
   '주간보고가 없을 때 모델로 올려 주지 않는다')

# 두 화면이 그 함수를 쓴다
_list = (LIB / 'screens' / 'division_select_screen.dart').read_text(encoding='utf-8')
ok('_markDivisionsWithModels' in _home, '홈이 모델 있는 사업부를 안 센다')
ok('divisionsWithModels(divs, prog)' in _home, '홈이 공용 규칙을 안 쓴다')
ok('divisionStatusWithModels(divisionId, cards, _divWithModels)' in _home,
   '홈이 공용 상태 판정을 안 쓴다')
ok('divisionsWithModels(all, prog)' in _list, '목록이 공용 규칙을 안 쓴다')
ok('divisionStatusWithModels(' in _list, '목록이 공용 상태 판정을 안 쓴다')
# 목록도 모델 수를 받아와야 한다 — 안 받으면 늘 빈 Set 이다
# 저장본에 머물면 품목을 새로 올려도 카드가 안 바뀐다 (잔·특근 41주차와 같은 자리)
ok('ProgressService.fetch(onFresh:' in _list,
   '목록이 진행률 요약의 새 값을 안 받는다 — 저장본에 머문다')
ok('_progressFuture' in _list and '_progressFuture])' in _list,
   '목록이 진행률 요약을 같이 기다리지 않는다')
# 목록 카드 두 군데(즐겨찾기 · 전체) 모두 같은 잣대를 받아야 한다
ok(_list.count('_statusOf(d.id, cards, withModels)') == 2,
   '목록의 카드 두 자리가 같은 잣대를 안 쓴다')
# 홈은 자료가 늦게 와도 다시 센다
ok(_home.count('_markDivisionsWithModels();') >= 2,
   '자료가 늦게 와도 다시 안 센다')

# 2026-11-04 — onFresh 안에서만 셌다. onFresh 는 저장본을 먼저 줬을 때만
# 불려서, 저장본이 없는 첫 실행·업데이트 직후에는 한 번도 안 셌다 — 홈만
# 반도체·ESS 빼고 전부 '진행 데이터 없음' 이었다 (목록은 멀쩡).
# Min: "이거 왜 매칭이 안되는거야...?"
_init = _home[_home.find('void initState()'):]
_init = _init[:_init.find('\n  }\n')]
_outside = _init
for blk in _init.split('onFresh:')[1:]:
    _outside = _outside.replace(blk[:blk.find('}));') + 4], '')
ok('_markDivisionsWithModels();' in _outside,
   '홈이 onFresh 밖에서 안 센다 — 저장본이 없으면 한 번도 안 센다')
_rf = _home[_home.find('Future<void> _refresh() async'):]
_rf = _rf[:_rf.find('\n  }\n')]
ok('_markDivisionsWithModels();' in _rf, '당겨서 새로고침해도 다시 안 센다')
ok('hit.containsAll(_divWithModels)' in _home,
   '사업부 수만 같으면 바뀐 걸 무시한다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 사업부 카드 · 잔특근 최신 주차')
