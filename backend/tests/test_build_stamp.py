# 올라간 코드가 내 코드인지 가리는 지문 (2026-10-28)
#   python3 backend/tests/test_build_stamp.py
#
# Min: "flyctl deploy를 oneview admin 계정으로 했는데 그래서 적용이
#      안되는건가 뭐지"
#
# 배포했는데 화면이 안 바뀌는 날이 있었다. 세 가지가 증상이 똑같다.
#   · 배포가 안 갔다
#   · 배포는 갔는데 고친 게 틀렸다
#   · 둘 다 됐는데 엑셀을 다시 안 올렸다
# 가릴 방법이 없으니 같은 배포를 몇 번씩 돌렸다.
#
# 이제 /health 가 코드 지문을 같이 준다. 로컬에서 build_stamp.py 를 찍어
# 두고 배포 뒤 비교하면 1번이 한 번에 가려진다.
import ast, os, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
ok = 0

# ── 1. 두 곳이 **같은 방식으로** 잰다
# 다르게 재면 늘 다른 값이 나와서, 제대로 올라갔는데도 안 갔다고 읽는다.
G = {}
for n in ast.parse(SRC).body:
    if isinstance(n, ast.FunctionDef) and n.name == '_build_stamp':
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
assert '_build_stamp' in G, 'main.py 에 _build_stamp 가 없다'
G['__file__'] = str(ROOT / 'main.py')
inside = G['_build_stamp']()
ok += 1

tool = ROOT / 'build_stamp.py'
assert tool.exists(), 'build_stamp.py 가 없다 — 배포 전에 찍을 데가 없다'
outside = subprocess.run([sys.executable, str(tool)],
                         capture_output=True, text=True).stdout.strip()
assert inside == outside, \
    '서버가 재는 값(%s)과 손으로 재는 값(%s)이 다르다 — 늘 안 갔다고 읽힌다' \
    % (inside, outside)
ok += 1

# ── 2. 코드가 바뀌면 지문도 바뀌어야 한다
assert len(inside) == 10 and all(c in '0123456789abcdef' for c in inside), \
    '지문 꼴이 이상하다: %r' % inside
ok += 1

# ── 3. /health 가 그 값을 준다. 여기가 fly.io 가 부르는 자리다.
assert '"build": BUILD' in SRC and '"up": BUILD_AT' in SRC, \
    '/health 가 지문을 안 준다'
ok += 1

# ── 4. /health 는 파일을 읽지 않는다
# fly.io 가 수시로 부른다. 여기서 파일 다섯 개를 열면 그게 부하가 된다.
_h = SRC[SRC.index('@app.get("/health")'):]
_h = _h[:_h.index('\n@app.')]
assert 'open(' not in _h and '_build_stamp()' not in _h, \
    '/health 가 부를 때마다 파일을 읽는다'
ok += 1

# ── 5. 파일이 없어도 서버는 뜬다
# 지문을 못 재는 것보다 서버가 안 뜨는 게 훨씬 나쁘다.
G2 = {'__file__': '/없는폴더/main.py'}
for n in ast.parse(SRC).body:
    if isinstance(n, ast.FunctionDef) and n.name == '_build_stamp':
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G2)
assert len(G2['_build_stamp']()) == 10, '파일이 없으면 지문 재다가 터진다'
ok += 1

print('ok %d' % ok)
