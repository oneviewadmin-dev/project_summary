# 읽기만 하는 길에서 models.json 을 쓰지 않는다 (2026-11-03)
#   python3 backend/tests/test_detail_no_write.py
#
# Min: "이것도 안 뜨고" (Schaeffler 프로젝트 — SocketException)
#
# 살아 있는 서버에서 재어 보니 —
#     automotive_schaeffler (모델  4종)  140초 넘게 → 타임아웃
#     automotive_schaefller (모델  2종)   15초
#     powerbox              (모델 82종)   70초
# 모델 수와 상관이 없었다. GET 인데 models.json 을 통째로 다시 쓰고,
# _save_models 는 쓰기 전에 백업 사본까지 한 장 뜬다 — 앱이 프로젝트를
# 한 번 열 때마다 큰 파일을 두 번 썼다.
#
# 'changed' 가 서는 조건이 '개발 품목의 단계 수가 12~15가 아니면' 이라,
# 단계가 3개 · 6개인 자동차 · 블룸은 열 때마다 매번 섰다.
import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
LINES = SRC.split('\n')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


# ── GET 핸들러 안에서 저장하는 자리를 기계가 훑는다 ──────────────
# 하나씩 적어 두면 다음에 또 생긴다.
tree = ast.parse(SRC)
bad = []
for n in ast.walk(tree):
    if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    is_get = False
    for d in n.decorator_list:
        src = ast.get_source_segment(SRC, d) or ''
        if src.startswith('app.get('):
            is_get = True
    if not is_get:
        continue
    body = ast.get_source_segment(SRC, n) or ''
    if '_save_models(' in body:
        bad.append(n.name)
ok(not bad, 'GET 인데 models.json 을 쓴다: %s' % ', '.join(bad))

# ── 두 자리를 콕 집어서도 본다 ──────────────────────────────────
for fn in ('get_project_models_detail', 'get_model_process'):
    _i = SRC.find('def %s(' % fn)
    ok(_i > 0, '%s 가 없다' % fn)
    if _i < 0:
        continue
    _nx = SRC.find('\n@app.', _i)
    body = SRC[_i:_nx if _nx > 0 else len(SRC)]
    ok('_save_models(' not in body, '%s 가 아직 저장한다' % fn)

# 계산은 그대로 해야 한다 — 저장만 안 하는 것이다
_d = SRC[SRC.find('def get_project_models_detail'):]
_d = _d[:_d.find('\n@app.')]
ok('_enrich_model(' in _d, '상세가 품목을 안 꾸민다')
ok('_dev_steps_blank(' in _d, '쌓인 반도체 단계를 안 걷어낸다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 읽기에서 안 쓴다')
