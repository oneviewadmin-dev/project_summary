# 글자로 적은 단계를 앱에도 보여 준다 (2026-11-02)
#   python3 backend/tests/test_process_note_show.py
#
# Min: "완료 라고 적힌 부분들은 그냥 진행률에도 추가하고 완료 되었다고
#      표기만 해두면 되잖아 문제가 되나"
#
# 진행률은 이미 세고 있었다 — 양식의 실적 칸에 '완료' 라고 적히면 그
# 단계의 status 를 '완료' 로 두고, 앱도 status 를 보고 초록 체크를
# 그린다. 남은 건 글자 한 줄이었다: 앱은 actual(날짜 칸)만 읽어서
# '계획 - · 실제 미완료' 라고 적었다.
#
# 보여 주는 사본에만 채운다. 저장까지 바꾸면 expected · actual 이
# 날짜 칸이 아니게 되어, 다음에 날짜로 읽으려 할 때 깨진다.
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
    if isinstance(n, ast.FunctionDef) and n.name == '_ds_show_notes':
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
ok('_ds_show_notes' in G, 'main.py 에 _ds_show_notes 가 없다')
if FAIL:
    print('\n'.join(FAIL))
    raise SystemExit(1)
show = G['_ds_show_notes']

src = [{'name': '01 T-car', 'expected': '', 'actual': '',
        'expected_note': '완료', 'actual_note': '완료', 'status': '완료'},
       {'name': '03 P1', 'expected': '2025-11-30', 'actual': '2025-11-30',
        'expected_note': '', 'actual_note': ''},
       {'name': '06 SOP', 'expected': '2026-10-15', 'actual': '',
        'expected_note': '', 'actual_note': ''}]
got = show(src)

ok(got[0]['actual'] == '완료', "'완료' 가 실적 자리에 안 뜬다")
ok(got[0]['expected'] == '완료', "'완료' 가 계획 자리에 안 뜬다")
ok(got[0]['status'] == '완료', 'status 가 사라졌다 — 초록 체크가 꺼진다')
# 날짜가 있는 칸은 건드리면 안 된다
ok(got[1]['actual'] == '2025-11-30', '날짜 칸을 덮어썼다')
ok(got[2]['actual'] == '', '없는 실적을 만들어 냈다')

# 원본은 그대로여야 한다 — 저장되는 자료가 바뀌면 안 된다
ok(src[0]['actual'] == '', '원본 자료를 고쳤다 — 날짜 칸에 글자가 저장된다')
ok(src[0]['expected'] == '', '원본 자료를 고쳤다')

# 보여 줄 때만 쓴다. 저장 경로(apply)에서 부르면 안 된다.
ok(SRC.count('_ds_show_notes(') == 2,
   '보여 주는 자리 한 곳에서만 불러야 한다 (지금 %d곳)'
   % (SRC.count('_ds_show_notes(') - 1))
# 2026-11-05 — 세는 것은 채우기 전 사본(_rolled)으로, 보여 주는 것만 채운다
_i = SRC.find('proc = _ds_show_notes(_rolled)')
ok(_i > 0, '보여 주는 사본에 안 걸려 있다')
_fn = SRC.rfind('def get_model_process', 0, _i)
ok(_fn > 0, '_ds_show_notes 가 get_model_process 밖에서 불린다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 글자 단계 보여 주기')
