# admin 은 보기 전용 — 손으로 바꾸는 길은 전부 닫힌다 (2026-11-04)
#   python3 backend/tests/test_admin_write_lock.py
#
# Min: "admin v2에 수정, 삭제, 변경을 전혀 못 하게끔 해야함"
#      → 범위: "admin 자료 전체 잠금"
#
# 함수마다 한 줄씩 막던 방식은 97개 중 3개만 막고 있었다. 이제 목록 하나로
# 들어오는 자리에서 막는다. 이 테스트가 지키는 것:
#   1) admin 의 쓰기 주소는 **전부** 잠금 / 열림 중 하나로 정해져 있다
#      — 새 주소를 만들고 안 정하면 여기서 실패한다
#   2) 파일로 들어오는 길(사업부 양식 등)은 열려 있다
#   3) 잠금 판정이 비슷한 주소를 헷갈리지 않는다 (…/models 와 …/models/import)
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
HTML = (ROOT / 'admin_v2.html').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


G = {'__builtins__': __builtins__}
tree = ast.parse(SRC)
for n in tree.body:
    if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in
                                         ('_ADMIN_LOCKED', '_ADMIN_OPEN') for t in n.targets):
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
    if isinstance(n, ast.FunctionDef) and n.name in ('_route_re', '_admin_locked'):
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
for n in tree.body:
    if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_ADMIN_LOCKED_RE'
                                         for t in n.targets):
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
for w in ('_ADMIN_LOCKED', '_ADMIN_OPEN', '_admin_locked', '_ADMIN_LOCKED_RE'):
    ok(w in G, 'main.py 에 %s 가 없다' % w)
if FAIL:
    print('\n'.join(FAIL))
    raise SystemExit(1)

LOCKED = {(m, t) for m, t in G['_ADMIN_LOCKED']}
OPEN = {(m, t) for m, t in G['_ADMIN_OPEN']}
locked = G['_admin_locked']

# ── 1. 쓰기 주소 전부가 어느 한쪽에 있다 ────────────────────────
routes = set()
for n in tree.body:
    if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    for d in n.decorator_list:
        if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and d.func.attr in ('post', 'put', 'delete', 'patch')
                and d.args and isinstance(d.args[0], ast.Constant)
                and str(d.args[0].value).startswith('/admin')):
            routes.add((d.func.attr.upper(), d.args[0].value))
none = sorted(routes - LOCKED - OPEN)
both = sorted(LOCKED & OPEN)
ghost = sorted((LOCKED | OPEN) - routes)
ok(not none, '잠금/열림 어느 쪽에도 없는 admin 쓰기 주소: %r' % none)
ok(not both, '잠금과 열림 양쪽에 다 있는 주소: %r' % both)
ok(not ghost, '목록에만 있고 실제로 없는 주소 (오타?): %r' % ghost)

# ── 2. 파일로 들어오는 길은 열려 있다 ───────────────────────────
for m, p in (('POST', '/admin/divisions/pcb/form/apply'),
             ('POST', '/admin/divisions/pcb/form/preview'),
             ('POST', '/admin/divisions/bloom/daily/apply'),
             ('POST', '/admin/divisions/automotive/dev-schedule/apply'),
             ('POST', '/admin/divisions/network/revenue-file/apply'),
             ('POST', '/admin/overtime/import-xlsx'),
             ('POST', '/admin/app/release'),
             ('POST', '/admin/login'),
             ('POST', '/admin/projects/powerbox/price-import-xlsx'),
             ('POST', '/admin/projects/powerbox/models/import'),
             ('POST', '/admin/projects/powerbox/weekly-plan')):
    ok(not locked(m, p), '%s %s 가 막혔다 — 파일로 들어오는 길이다' % (m, p))

# ── 3. 손으로 바꾸는 길은 막힌다 — 비슷한 주소와 안 헷갈린다 ───
for m, p in (('POST', '/admin/projects/powerbox/models'),          # 추가
             ('PATCH', '/admin/projects/powerbox/models/AB-12'),   # 수정
             ('DELETE', '/admin/projects/powerbox/models/AB-12'),  # 삭제
             ('PUT', '/admin/projects/powerbox/models'),
             ('DELETE', '/admin/projects/powerbox/weekly-plan'),
             ('PUT', '/admin/projects/frame/models/X1/process'),
             ('POST', '/admin/home/division-target'),
             ('POST', '/admin/revenue/target'),
             ('PUT', '/admin/overtime'),
             ('DELETE', '/admin/notes/photo/semiconductor/a.jpg'),
             ('POST', '/admin/reset'),
             ('DELETE', '/admin/card')):
    ok(locked(m, p), '%s %s 가 안 막혔다' % (m, p))
# 같은 주소라도 방법이 다르면 다르다 — 이미지 올리기(POST)는 열림, 지우기(DELETE)는 잠금
ok(not locked('POST', '/admin/projects/p/weekly-plan') and locked('DELETE', '/admin/projects/p/weekly-plan'),
   '같은 주소의 올리기·지우기를 못 가린다')
# 읽기는 건드리지 않는다
ok(not locked('GET', '/admin/projects/powerbox/models'), '읽기까지 막았다')
# 꼬리 / 가 붙어도 막힌다
ok(locked('POST', '/admin/revenue/target/'), '주소 끝에 / 를 붙이면 빠져나간다')

# ── 4. 들어오는 자리(미들웨어)에서 막고, 스위치 하나로 되돌린다 ─
ok('@app.middleware("http")' in SRC and 'async def _admin_write_lock' in SRC,
   '들어오는 자리에서 안 막는다')
_mw = SRC[SRC.find('async def _admin_write_lock'):]
_mw = _mw[:_mw.find('\n\n\n')]
ok('ADMIN_WRITE_OFF' in _mw and 'status_code=423' in _mw, '스위치나 423 이 없다')

# ── 5. 화면 — 막힌 요청은 보내지 않고 안내를 띄운다 ─────────────
ok("'/admin/write-lock'" in HTML, '화면이 서버의 잠금 목록을 안 받는다')
ok('window.__adminWriteLocked' in HTML, '화면이 막힌 요청을 걸러내지 않는다')
ok('r.status === 423' in HTML, '서버가 423 을 돌려줘도 화면이 모른다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — admin 쓰기 주소 %d개: 잠금 %d · 열림 %d' % (len(routes), len(LOCKED), len(OPEN)))
