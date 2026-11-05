# 반도체 13단계를 다른 사업부에 깔지 않는다 (2026-11-02)
#   python3 backend/tests/test_dev_default_steps.py
#
# Min: "이거 없어야 되는데 잇는 이유가 뭐야"
#      (자동차 KEFICO INDIA 표에 'Source Inspection · FAIR 제출 ·
#       FAIR 승인 · LAP TEST · CDR · 최종 승인 완료' 가 자기 단계
#       '01 T-car … 06 SOP' 옆에 같이 서 있었다)
#
# DEV_PROCESS_STEPS 13단계는 반도체사업부의 승인 절차다. 그런데
# _ensure_process 가 사업부를 안 보고 모든 개발 품목에 깔았다. 개발
# 진행현황 표는 품목들의 단계 이름을 합집합으로 모으기 때문에, 한 품목만
# 반도체 단계를 달고 있어도 표 전체에 13칸이 늘어선다.
#
# 게다가 부른 쪽에서 곧바로 저장하는 자리가 많아서, 한 번 열어 보기만
# 해도 반도체 단계가 자료에 박혔다.
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


G = {'__builtins__': __builtins__}
tree = ast.parse(SRC)
for n in tree.body:
    if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == 'DEV_PROCESS_STEPS' for t in n.targets):
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
    if isinstance(n, ast.FunctionDef) and n.name in (
            '_default_process', '_ensure_process', '_dev_steps_blank'):
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)

for f in ('_default_process', '_ensure_process', '_dev_steps_blank'):
    ok(f in G, 'main.py 에 %s 가 없다' % f)
if FAIL:
    print('\n'.join(FAIL))
    raise SystemExit(1)

ens = G['_ensure_process']
blank = G['_dev_steps_blank']
N13 = len(G['DEV_PROCESS_STEPS'])

# ── 1. 반도체는 그대로 ───────────────────────────────────────────
m = {'group': '개발'}
ok(len(ens(m, 'semiconductor')) == N13, '반도체에 기본 단계가 안 깔린다')
ok(len(m.get('process') or []) == N13, '반도체는 자료에도 박혀야 한다')
# 사업부를 모르면 전처럼 — 반도체 경로들이 조용히 깨지면 안 된다
m2 = {'group': '개발'}
ok(len(ens(m2, '')) == N13, '사업부를 모를 때 동작이 바뀌었다')

# ── 2. 다른 사업부는 안 깐다 ─────────────────────────────────────
for div in ('automotive', 'bloom', 'pcb', 'network'):
    m3 = {'group': '개발'}
    ok(ens(m3, div) == [], '%s 에 반도체 단계를 깔았다' % div)
    ok(not m3.get('process'), '%s 자료에 반도체 단계를 박았다' % div)

# ── 3. 이미 있는 단계는 사업부와 무관하게 그대로 ────────────────
mine = [{'name': '01 T-car', 'expected': '2026-01-01'}]
m4 = {'group': '개발', 'process': mine}
ok(ens(m4, 'automotive') is mine, '자기 단계를 덮어썼다')
ok(ens({'group': '개발', 'process': mine}, 'semiconductor') is mine,
   '반도체에서도 자기 단계는 그대로여야 한다')

# ── 4. 걷어내기는 '빈 것' 만 ─────────────────────────────────────
ok(blank(G['_default_process']()) is True, '빈 기본 단계를 못 알아본다')
ok(blank([{'name': 'a', 'expected': '2026-01-01'}]) is False,
   '날짜가 있는데 비었다고 본다')
ok(blank([{'name': 'a', 'status': '완료'}]) is False,
   "상태 '완료' 가 있는데 비었다고 본다")
ok(blank([{'name': 'a', 'actual_note': '완료'}]) is False,
   '글자로 적힌 실적이 있는데 비었다고 본다')
ok(blank([]) is False and blank(None) is False, '빈 목록을 걷어낼 대상으로 본다')

# ── 5. 걷어내는 자리가 상세에 있는가 ────────────────────────────
_i = SRC.find('def get_project_models_detail')
_body = SRC[_i:SRC.find('\n@app.', _i + 10)]
ok('_dev_steps_blank(m.get("process"))' in _body, '쌓인 것을 안 걷어낸다')
ok('_div != "semiconductor"' in _body, '반도체 것까지 걷어낼 수 있다')
ok('== [n for _k, n, _g in DEV_PROCESS_STEPS]' in _body,
   '이름이 기본 13단계와 같은지 안 보고 걷어낸다 — 남의 단계를 지운다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 기본 단계는 반도체만')
