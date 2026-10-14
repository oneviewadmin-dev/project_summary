# 올린 자료가 새로고침 없이 바로 보이는지.
#   python3 backend/tests/test_auto_refresh.py
#
# "데이터가 업로드가 됐으면 알아서 refresh 해서 바로 반영이 되게끔"
#
# 두 군데를 본다.
#  · 관리자 웹 — 엑셀을 넣은 자리마다 ovAfterImport() 하나를 부른다.
#    예전에는 자리마다 손으로 적어 둬서, 주차 보드는 바뀌는데 모델
#    목록은 새로고침해야 보였다.
#  · 앱 — /data-version 한 줄만 자주 묻고, 값이 바뀐 때에만 전체를
#    다시 받는다. 매번 전부 받으면 통신량이 수십 배가 된다.
import pathlib
import re

BK = pathlib.Path(__file__).resolve().parents[1]
H = (BK / 'admin_v2.html').read_text(encoding='utf-8')
M = (BK / 'main.py').read_text(encoding='utf-8')
APP = BK.parents[0] / 'mobile' / 'lib'
HOME = (APP / 'screens' / 'home_screen.dart').read_text(encoding='utf-8')
SVC = (APP / 'services' / 'data_version_service.dart').read_text(encoding='utf-8')

fails = []


def need(cond, msg):
    if not cond:
        fails.append(msg)


# ── 1. 관리자 웹: 공용 갱신 함수 ──
need('window.ovAfterImport = function()' in H, 'ovAfterImport 가 없다')
fn = H[H.index('window.ovAfterImport = function()'):]
fn = fn[:fn.index('\n  };\n')]
need('window.loadModelList' in fn, '주차별 계획 목록을 다시 안 그린다')
need("window.mdlRefresh('all')" in fn, '모델 목록 표를 서버 값으로 안 바꾼다')
need('mdl-save-msg' in fn,
     '저장 안 한 수정이 있어도 표를 덮어쓴다 — 적어 둔 값이 날아간다')
need('window.wbRefresh' in fn, '주차 현황 보드를 안 돌린다')

# ── 2. 관리자 웹: 올리는 자리마다 부른다 ──
# 엑셀/파일을 서버에 넣는 자리 (미리보기는 제외 — 저장하지 않는다)
APPLY = [
    "/status-excel',",          # 하바플레이트 주간 현황
    "/plan-file/apply',",       # 주차 양식 · 모델 값만
    "/process/import-xlsx',",   # 개발 프로세스 일정표
]
for frag in APPLY:
    need(frag in H, '올리는 자리를 못 찾았다: %s' % frag)

# plan-file/apply 는 두 곳(주차 양식, 모델 값만)에서 부른다
need(H.count("/plan-file/apply',") == 2,
     'plan-file/apply 호출이 2곳이 아니다 — 자리마다 확인해야 한다')

# 각 호출의 .then 블록 안에 ovAfterImport 가 있어야 한다
for m in re.finditer(r"fetch\('/admin/projects/[^\n]*?/(status-excel|plan-file/apply|process/import-xlsx)'", H):
    tail = H[m.start():m.start() + 4000]
    cut = tail.find('.catch(')
    body = tail[:cut if cut > 0 else len(tail)]
    need('window.ovAfterImport()' in body,
         '%s 를 넣은 뒤 화면을 안 돌린다' % m.group(1))

# 옛 길(자리마다 손으로 적어 둔 것)이 남아 있으면 또 엇갈린다
need('// 모델 값이 바뀌었으면 모델 목록도 다시 그린다' not in H,
     '손으로 적어 둔 옛 갱신 코드가 남아 있다')

# 블록을 넘나드니 window 에 붙어 있어야 한다
need('window.loadTypes = loadTypes;' in H, 'loadTypes 가 window 에 없다')

# ── 3. 서버: /data-version ──
need('@app.get("/data-version")' in M, '/data-version 창구가 없다')
need('_DATA_VERSION_FILES' in M, '어느 파일을 보는지 안 적혀 있다')
for f in ('models.json', 'revenue.json', 'overtime.json', 'purchases.json',
          'home_orders.json', 'division_targets.json'):
    need('"%s"' % f in M.split('_DATA_VERSION_FILES')[1][:800],
         '%s 를 안 본다 — 그 화면은 자동 반영이 안 된다' % f)
need('no-store' in M.split('@app.get("/data-version")')[1][:1600],
     '캐시를 막지 않았다 — 옛 값이 돌아오면 자동 반영이 영원히 안 돈다')
# 저장 경로에 손대지 않았는지 (빠뜨릴 자리를 만들지 않는다)
need('st.st_mtime' in M, '파일 수정 시각이 아니라 다른 걸 본다')

# ── 4. 앱 ──
need('/data-version' in SVC, '앱이 /data-version 을 안 묻는다')
need('return null' in SVC,
     '못 받아온 걸 null 로 안 돌려준다 — 신호가 나쁠 때 새로고침이 계속 돈다')
need("import '../services/data_version_service.dart';" in HOME,
     '홈이 자료 버전 서비스를 안 쓴다')
need('_startDataWatch' in HOME and '_stopDataWatch' in HOME, '감시 타이머가 없다')
need('Duration(seconds: 30)' in HOME, '감시 주기가 30초가 아니다')
watch = HOME[HOME.index('Future<void> _checkDataVersion()'):]
watch = watch[:watch.index('\n  }\n')]
need('if (v == null) return;' in watch, '못 받아온 걸 바뀐 것으로 읽는다')
need('before != null && before != v' in watch,
     '처음 받은 값으로도 새로고침한다 — 앱을 켤 때마다 두 번 받는다')
need('_dataWatchBusy' in watch, '응답이 늦으면 요청이 겹친다')
# 설정의 [끔] 을 거짓말로 만들지 않는다
setup = HOME[HOME.index('void _setupAutoRefresh()'):]
setup = setup[:setup.index('\n  }\n')]
need('_stopDataWatch();' in setup, '자동 새로고침을 [끔] 으로 둬도 감시가 돈다')
need('_startDataWatch();' in setup, '감시를 시작하지 않는다')
# 타이머를 거둬야 한다
need('void dispose()' in HOME and '_stopDataWatch();' in
     HOME[HOME.index('void dispose()'):HOME.index('void dispose()') + 400],
     'dispose 에서 감시 타이머를 안 끈다')

if fails:
    print('실패 %d건' % len(fails))
    for f in fails:
        print('  -', f)
    raise SystemExit(1)
print('전부 통과 · 검사 4묶음')
