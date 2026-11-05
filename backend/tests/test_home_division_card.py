# 사업부 카드 '진행 중' · 잔특근 최신 주차 (2026-11-03)
#   python3 backend/tests/test_home_division_card.py
#
# Min: "잔특근 43주차가 제일 최신인데 반영 안 되어 있는지"
#      "전체 사업부별 카드에 시스템 빼곤 다 진행중이여서 이거 카드 변경 좀 해줘"
#
# 1) 잔·특근 — 홈에서 부르는 자리만 onFresh 가 없었다. 그래서 서버가
#    8초 안에 답을 못 하면 저장본으로 떨어진 채 **그대로 머물렀다**.
#    43주차가 올라왔는데 카드는 41주차를 들고 있던 이유다. (서버는
#    기본 호출에 이미 W43 을 준다 — 확인했다.)
#
# 2) 사업부 카드 — '진행 중' 을 /dashboard 의 주간보고 카드만 보고
#    정했다. 주간보고를 내는 건 반도체뿐이라, 프로젝트가 27개씩 있는
#    아리스타 · PCB · 자동차 · 네트워크가 전부 '진행 데이터 없음' 이었다.
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1].parent
LIB = ROOT / 'mobile' / 'lib'
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


if not LIB.exists():
    print('(앱 없음 — 건너뜀)')
    raise SystemExit(0)

HOME = (LIB / 'screens' / 'home_screen.dart').read_text(encoding='utf-8')
OT = (LIB / 'services' / 'overtime_service.dart').read_text(encoding='utf-8')

# ── 1. 잔·특근 ──────────────────────────────────────────────────
ok('OvertimeService.fetchWeek(onFresh:' in HOME,
   '잔·특근만 새 값을 안 받아 간다 — 옛 주차에 머문다')
ok('void Function(OvertimeWeek)? onFresh' in OT,
   '잔·특근 서비스가 새 값을 알려줄 길이 없다')
# 저장본을 아예 안 쓰면 신호가 나쁠 때 카드가 빈다 — 그건 더 나쁘다
ok('OfflineStore.fetch(' in OT, '저장본을 안 쓴다 — 신호 나쁘면 카드가 빈다')

# ── 2. 사업부 카드 ──────────────────────────────────────────────
#
# 2026-11-03 — 규칙 자체는 models/dashboard.dart 로 옮겼다. 홈에만 적어
# 두었더니 목록 화면이 따라오지 않아서, 같은 사업부가 홈에서는 '진행 중'
# 인데 목록에서는 '진행 데이터 없음' 으로 떴다 (Min: "목록에도 홈처럼
# 동일하게 반영되게끔 연결 되어야지"). 규칙 내용과 목록 쪽 연결은
# test_division_card_active.py 가 본다 — 여기서는 홈이 그 규칙을
# **직접 다시 적지 않고 불러 쓰는지**만 본다.
ok('_divWithModels' in HOME, '모델이 있는 사업부를 안 센다')
ok('divisionsWithModels(divs, prog)' in HOME, '홈이 공용 규칙을 안 쓴다')
ok('divisionStatusWithModels(divisionId, cards, _divWithModels)' in HOME,
   '홈이 공용 상태 판정을 안 쓴다')
ok('modelsTotal ?? 0) > 0' not in HOME,
   '홈이 규칙을 다시 적었다 — 목록과 또 갈린다')
# 사업부마다 예외를 두지 않는다 — 그 예외는 2026-10-23 에 거뒀다
_i = HOME.find('DivisionStatus _divisionStatus(')
_body = HOME[_i:HOME.find('\n  // 즉시 확인', _i)]
ok("divisionId == 'bloom'" not in _body.split('kSameFrameForAll')[0],
   '새 판정이 특정 사업부만 봐준다')
# 자료가 들어올 때마다 다시 세야 한다 (둘 다 비동기로 온다)
ok(HOME.count('_markDivisionsWithModels();') >= 2,
   '사업부나 진행률 중 한쪽만 들어와도 다시 안 센다')
# setState 를 매번 부르면 화면이 떤다
ok('hit.length == _divWithModels.length' in HOME, '바뀐 게 없어도 다시 그린다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 사업부 카드 · 잔특근 최신 주차')
