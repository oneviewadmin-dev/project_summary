# 단계별 표준 소요를 사업부 단위로 (2026-11-02)
#   python3 backend/tests/test_process_lead_division.py
#
# Min: "소요되는 주는 PO접수는 2주, PRP 3주 그 뒤로 바로 최종승인이야"
#
# 소요를 담는 자리는 원래 프로젝트 하나(powerbox)뿐이었다. 블룸은
# 프로젝트가 열다섯인데 공정은 다 같은 세 단계라, 프로젝트마다 똑같은
# 값을 열다섯 번 적게 할 수는 없다. 사업부로 한 번 적는다.
#
# 앱은 안 건드린다 — 앱은 이미 /projects/{key}/process-steps 를 읽어
# weeks 가 있는 단계에만 '(2주)' 를 붙인다. 서버 값만 채우면 된다.
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


# ── 1. 값 ────────────────────────────────────────────────────────
G = {}
tree = ast.parse(SRC)
for n in tree.body:
    if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name)
            and t.id in ('PROCESS_LEAD_BY_DIVISION', 'PROCESS_LEAD_DEFAULT')
            for t in n.targets):
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)

BY = G.get('PROCESS_LEAD_BY_DIVISION')
ok(isinstance(BY, dict), 'PROCESS_LEAD_BY_DIVISION 가 없다')
bl = (BY or {}).get('bloom') or {}
ok(bl.get('PO 발주') == 2, "블룸 'PO 발주' 가 2주가 아니다: %r" % bl.get('PO 발주'))
ok(bl.get('PRP') == 3, "블룸 'PRP' 가 3주가 아니다: %r" % bl.get('PRP'))
# '그 뒤로 바로' — 0 이다. None(안 정함) 과 다르다: None 이면 칩에
# 아무것도 안 붙고, 0 이면 '걸리는 시간이 없다' 를 적어 둔 것이다.
ok(bl.get('최종 승인') == 0,
   "블룸 '최종 승인' 이 0주가 아니다: %r" % bl.get('최종 승인'))
ok(bl.get('최종 승인') is not None, "'최종 승인' 이 '안 정함' 으로 비어 있다")
# Min 은 'PO접수' 라고 부르고 양식에는 'PO 발주' 로 적힌다. 같은 단계다.
ok(bl.get('PO 접수') == 2, "'PO 접수' 별칭이 없다 — 양식 글자가 바뀌면 소요가 사라진다")
ok(sum(v for k, v in bl.items() if k != 'PO 접수') == 5,
   '블룸 전체가 5주가 아니다: %r' % bl)

# ── 2. 찾는 차례 ─────────────────────────────────────────────────
# 프로젝트 저장값 → 프로젝트 기본값 → 사업부 기본값.
# 사업부 값이 먼저 오면 한 프로젝트만 따로 정할 수가 없다.
fn = None
for n in ast.walk(tree):
    if isinstance(n, ast.FunctionDef) and n.name == 'get_process_steps':
        fn = n
body = ast.get_source_segment(SRC, fn) if fn else ''
ok(bool(body), 'get_process_steps 가 없다')
i_saved = body.find('proj.get("process_lead")')
i_proj = body.find('PROCESS_LEAD_DEFAULT.get')
i_div = body.find('PROCESS_LEAD_BY_DIVISION.get')
ok(i_saved >= 0 and i_proj > i_saved,
   '프로젝트 저장값보다 기본값을 먼저 본다')
ok(i_div > i_proj >= 0,
   '사업부 값을 프로젝트 값보다 먼저 본다 — 프로젝트별로 못 바꾼다')
ok('derive_division_from_project' in body,
   '프로젝트에서 사업부를 못 찾는다')
ok('"division"' in body, "source 에 'division' 표시가 없다 — 어디서 온 값인지 모른다")

# ── 3. 0 이 살아남나 ─────────────────────────────────────────────
# v = int(v) if v is not None and str(v).strip() != "" else None
# 여기서 0 을 거짓으로 보고 떨어뜨리면 '최종 승인' 이 조용히 사라진다.
ok('if v is not None and str(v).strip() != ""' in body,
   '0 주가 빈 값으로 떨어질 수 있다 — not v 로 거르면 안 된다')


def _pick(v):
    """get_process_steps 의 값 고르기만 떼어내 흉내 낸다."""
    try:
        return int(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


ok(_pick(0) == 0, '0 주가 None 으로 떨어진다')
ok(_pick(None) is None, '안 정한 단계가 0 으로 바뀐다')
ok(_pick('') is None, '빈 칸이 0 으로 바뀐다')

# ── 4. 빌드 지문 ─────────────────────────────────────────────────
# main.py 는 이미 지문 목록에 있다. 바뀌면 /health 의 build 가 달라져야
# 배포가 됐는지 눈으로 확인할 수 있다.
ok('"main.py"' in SRC or "'main.py'" in SRC, '지문 목록에 main.py 가 없다')

# ── 자동차 — 고객사마다 소요가 다르다 (2026-11-03) ──────────────
# Min 이 불러 준 값. 단위가 개월이고, 단계 이름이 아니라 자리(01~06)다 —
#     "삼성SDI는 01 6개월 02 12개월 03 4개월 04 8개월 05 10개월 06 12개월"
# 이름으로는 못 맞춘다. 같은 01 이라도 'T-car' · 'X0' · 'G1' 로 다르다.
G2 = {'__builtins__': __builtins__}
for n in ast.parse(SRC).body:
    if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in (
                '_AUTO_LEAD_MONTHS', '_AUTO_LEAD_PROJECTS',
                'PROCESS_LEAD_MONTHS_BY_PROJECT')
            for t in n.targets):
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G2)
    if isinstance(n, ast.FunctionDef) and n.name == '_lead_by_position':
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G2)

MB = G2.get('PROCESS_LEAD_MONTHS_BY_PROJECT') or {}
ok(MB.get('automotive_sdi_hungary') == [6, 12, 4, 8, 10, 12], 'SDI 값이 다르다')
ok(MB.get('automotive_kefico_kr') == [4, 6, 6, 8, 10, 12], '현대차 값이 다르다')
ok(MB.get('automotive_hyundai_mobis') == MB.get('automotive_kefico_kr'),
   'MOBIS 가 현대차 묶음에 안 들어갔다')
ok(MB.get('automotive_younghwa_tech') == MB.get('automotive_kefico_kr'),
   '영화테크가 현대차 묶음에 안 들어갔다')
ok(MB.get('automotive_lg_magna') == [12, 1, 2, 2, 1, 1], 'LG마그나 값이 다르다')
ok(MB.get('automotive_lge_vn') == [3, 12, 8, 8, 8, 1], 'LGE 값이 다르다')
ok(MB.get('automotive_schaeffler') == [6, 8, 10, 12, 14], 'Schaeffler 값이 다르다')
ok(MB.get('automotive_schaefller') == MB.get('automotive_schaeffler'),
   '철자가 다른 Schaefller 프로젝트가 빠졌다')
ok(MB.get('automotive_stellantis') == [11, 14, 17, 19, 21], 'Stellantis 값이 다르다')
# 아직 안 받은 곳은 비어 있어야 한다 — 짐작해서 채우면 안 된다
for k in ('automotive_ket_korea', 'automotive_jahwa_vina'):
    ok(k not in MB, '%s 는 아직 안 받았는데 값이 들어 있다' % k)

pos = G2['_lead_by_position']
# 자리로 맞춘다 — 이름이 뭐든 차례대로
got = pos('automotive_lg_magna',
          ['T-car', 'Proto', 'G1[Pilot]', 'G2 [Pilot]', 'G3 [Pilot]',
           'G4 [Pilot]', 'SOP'])
ok(got.get('T-car') == (52, '12개월'), 'LG마그나 첫 단계가 다르다: %r' % (got.get('T-car'),))
ok(got.get('Proto') == (4, '1개월'), '1개월이 4주로 안 바뀐다')
# 단계가 값보다 많으면 남는 단계는 비워 둔다 (7단계인데 값은 6개)
ok('SOP' not in got, '값이 없는 단계에 억지로 붙였다')
# 값이 단계보다 많으면 남는 값은 버린다
got2 = pos('automotive_stellantis', ['01 X0', '02 X1'])
ok(len(got2) == 2, '단계보다 많은 값을 밀어 넣었다')
ok(got2.get('01 X0') == (48, '11개월'), 'Stellantis 첫 단계가 다르다')
# 모르는 프로젝트는 빈 손
ok(pos('powerbox', ['FA PO']) == {}, '반도체에 자동차 값이 붙었다')

# 자리 값이 이름 값을 이겨야 한다 (이름으로는 못 맞추는 게 본론이다)
_fn = SRC[SRC.find('def get_process_steps'):]
_fn = _fn[:_fn.find('\n@app.')]
ok('bypos = _lead_by_position(_key, steps)' in _fn, '자리로 맞추는 걸 안 쓴다')
ok(_fn.find('bypos = ') < _fn.find('v = lead.get(n)'),
   '이름 값을 먼저 본다 — 자동차가 안 붙는다')
# 앱이 칩에 적을 글자를 서버가 정한다. '21개월' 을 '91주' 로 적으면 안 읽는다.
ok('"label"' in _fn, '칩에 적을 글자를 안 내려준다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 사업부 단위 표준 소요')
