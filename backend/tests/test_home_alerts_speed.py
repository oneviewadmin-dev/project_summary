# 홈 '전체 현황' 이 전사에서도 돌아와야 한다 (2026-11-02)
#   python3 backend/tests/test_home_alerts_speed.py
#
# Min: "지금 현황 retrieve 못 하고 있는 것 같아"
#
# 카드를 전 사업부로 넓혔더니 통째로 못 불러왔다. 살아 있는 서버에서
# 재어 보니 —
#     반도체 7s · 자동차 45s · 블룸 44s · PCB 69s  → 전사는 150초 넘게 타임아웃
#
# 범인은 '주차 미달' 을 세는 자리였다. 프로젝트마다 주차 보드를 한 장씩
# 통째로 만들어 보고 미달 한 줄만 꺼내 썼다. 프로젝트가 200개가 되니
# 보드를 200장 만들었다.
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


G = {'__builtins__': __builtins__}
for n in ast.parse(SRC).body:
    if isinstance(n, ast.FunctionDef) and n.name == '_has_week_plan':
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
ok('_has_week_plan' in G, 'main.py 에 _has_week_plan 이 없다')
if FAIL:
    print('\n'.join(FAIL))
    raise SystemExit(1)
has = G['_has_week_plan']

# ── 1. 거르는 눈이 맞나 ──────────────────────────────────────────
M = '2026-11'
ok(has({'models': [{'weekly_plan': {M: {'W45': {'plan': 10}}}}]}, M) is True,
   '계획이 있는데 걸러 버린다 — 미달이 영영 안 잡힌다')
ok(has({'models': [{'weekly_plan': {M: {'W45': {'actual': 3}}}}]}, M) is True,
   '실적만 있는 달을 걸러 버린다')
ok(has({'models': [{'weekly_plan': {'2026-10': {'W41': {'plan': 10}}}}]}, M)
   is False, '다른 달 계획을 이 달로 센다')
ok(has({'models': [{'weekly_plan': {M: {'W45': {'plan': 0, 'actual': 0}}}}]}, M)
   is False, '0 만 적힌 칸을 계획으로 센다')
ok(has({'models': []}, M) is False, '모델이 없는데 보드를 만든다')
ok(has({}, M) is False, '빈 프로젝트에서 터진다')
ok(has({'models': [None, 'x']}, M) is False, '모델 목록이 지저분하면 터진다')

# ── 2. 보드를 캐시하나 ───────────────────────────────────────────
# 2026-11-03 — 처음에는 보드를 **통째로** 들고 있었다. 보드 한 장이
# 수십~수백 KB 라 프로젝트 200곳이면 금방 100MB 가 넘는다. 그게 메모리
# 부족으로 서버가 죽은 원인 중 하나였다 (anon-rss 408MB 에서 OOM).
# 쓰는 건 미달 한 줄과 마감주차뿐이라 그것만 들고 있는다.
ok('_weekly_shortfall_cached' in SRC, '주차 보드를 매번 다시 만든다')
ok('_weekly_board_cached' not in SRC, '보드를 통째로 쥐고 있는 옛 캐시가 남아 있다')
_i = SRC.find('def _weekly_shortfall_cached')
_fn = SRC[_i:SRC.find('\n@app.', _i)]
ok('_WB_CACHE[key] = (stamp, last, sh)' in _fn,
   '캐시가 아직 보드를 통째로 쥔다')
# 자료가 바뀌면 저절로 버려져야 한다. 손으로 비우는 자리를 두면
# 언젠가 안 비우고 옛 숫자를 보여 준다.
ok('getmtime' in _fn, '캐시가 자료 바뀐 걸 모른다 — 옛 숫자가 남는다')
ok('_WB_CACHE.clear()' in _fn, '캐시가 끝없이 자란다')

# ── 3. 비싼 호출이 싼 검사 뒤에 있나 ────────────────────────────
_a = SRC.find('def get_home_alerts')
_body = SRC[_a:SRC.find('\n@app.', _a)]
_i_chk = _body.find('_has_week_plan(proj')
_i_brd = _body.find('_weekly_shortfall_cached(pk')
ok(_i_chk > 0, '싼 검사를 안 쓴다')
ok(0 < _i_chk < _i_brd, '보드를 먼저 만들고 나서 거른다 — 거르는 뜻이 없다')
ok('get_weekly_board(pk' not in _body,
   '옛 호출이 남아 있다 — 캐시를 안 타는 길이 생긴다')

# ── 4. 운영 파일을 부를 때마다 다시 파싱하지 않는다 ─────────────
# 이게 OOM 의 큰 몫이었다. _load_models 를 부르는 데가 104곳이고,
# /revenue 한 번에도 여러 번 불린다. 큰 JSON 을 한 요청에 여러 번 새로
# 만들면 파이썬이 그 자리를 바로 안 돌려줘서 쓰는 메모리가 계속 는다.
ok('_MODELS_CACHE' in SRC, '운영 파일을 부를 때마다 다시 파싱한다')
_lm = SRC[SRC.find('def _load_models'):]
_lm = _lm[:_lm.find('\ndef ', 10)]
ok('st_mtime_ns' in _lm, '파일이 바뀐 걸 모르고 옛 자료를 들고 있는다')
ok('_MODELS_CACHE["data"] = data' in _lm, '읽은 것을 안 남긴다')
# 저장할 때 같이 맞춰 둬야 다음 읽기가 또 파싱하지 않는다
_sm = SRC[SRC.find('def _save_models'):]
_sm = _sm[:_sm.find('\ndef ', 10)]
ok('_MODELS_CACHE["data"] = data' in _sm, '저장 뒤에 캐시를 안 맞춘다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 전체 현황 속도')
