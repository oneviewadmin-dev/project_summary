# 개발 일정 양식의 품번 맞추기 (2026-11-02)
#   python3 backend/tests/test_dev_schedule_match.py
#
# Min: "아니 KEFICO KR 파트넘버 보니까 매칭 됐는데 왜 매칭을 못 시키는건지...."
#
# 맞다. 품번은 같았다 — 괄호가 달랐을 뿐이다.
#
#     양식   9109020119 (VCU BASE)
#     등록   9109020119
#
# _df_norm 은 괄호를 '떼는' 게 아니라 없애고 앞뒤를 붙인다. 그래서
# '9109020119vcubase' 가 되어 안 맞았다. 품번 뒤에 품명을 괄호로 달아
# 주는 양식에서는 38줄 중 한 줄도 안 맞았다.
#
# 실제 등록 자료로 돌려 보니 29줄 중 0 → 20 줄이 붙었다. 남은 9줄은
# 괄호 문제가 아니라 품번 자체가 다른 건이다 (아래 '안 붙는 게 맞는 것').
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
    if isinstance(n, ast.FunctionDef) and n.name in (
            '_df_norm', '_pn_variants', '_ds_pick_model'):
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)

for f in ('_df_norm', '_pn_variants', '_ds_pick_model'):
    ok(f in G, 'main.py 에 %s 가 없다' % f)
if FAIL:
    print('\n'.join(FAIL))
    raise SystemExit(1)

var = G['_pn_variants']
pick = G['_ds_pick_model']

# ── 1. 열쇠 세 가지 ──────────────────────────────────────────────
v = var('9109020119 (VCU BASE)')
ok('9109020119' in v, '괄호 앞을 안 가린다')
ok('vcubase' in v, '괄호 안을 안 가린다')
ok('9109020119vcubase' in v, '칸 전체가 빠졌다 — 지금까지 맞던 게 깨진다')
ok(var('') == set() and var(None) == set(), '빈 칸이 열쇠를 만든다')
# 'PART NO :' 는 라벨이다. 안 떼면 모든 KET KOREA 줄이 같은 열쇠가 된다.
ok('sx31800wp2mblockrr' in var('PART NO : (SX3_1800 WP 2M BLOCK RR)'),
   "'PART NO :' 라벨을 안 뗀다")

# ── 2. 실제로 붙는가 ─────────────────────────────────────────────
KEFICO = [{'part_number': '9109090002', 'id': '9109090002'},
          {'part_number': '9109020119', 'id': '9109020119'}]
got = pick(KEFICO, '9109020119 (VCU BASE)')
ok(got is not None and got['part_number'] == '9109020119',
   'KEFICO KR 가 아직도 안 붙는다')
# 괄호 없이 적은 줄은 전에도 붙었다 — 그대로 붙어야 한다
ok((pick(KEFICO, '9109090002') or {}).get('part_number') == '9109090002',
   '괄호 없는 줄이 깨졌다')
# 붙여 쓴 괄호
LGE = [{'part_number': 'AGL30214001', 'id': 'AGL30214001'}]
ok(pick(LGE, 'AGL30214001(EMA FCD)') is not None, '붙여 쓴 괄호를 못 읽는다')

# ── 3. 아무거나 고르지는 않는다 ─────────────────────────────────
# 괄호 안이 'HOUSING' 처럼 흔하면 여럿이 걸린다. 그럴 땐 안 고른다 —
# 남의 품목에 남의 날짜가 박히는 쪽이 훨씬 나쁘다.
TWO = [{'part_number': 'A1', 'id': 'A1', 'name': 'x'},
       {'part_number': 'A2', 'id': 'A2', 'name': 'y'}]
ok(pick(TWO, 'ZZ (HOUSING)') is None, '없는 품번인데 뭔가를 골랐다')
DUP = [{'part_number': 'HOUSING (A)', 'id': 'HOUSING (A)'},
       {'part_number': 'HOUSING (B)', 'id': 'HOUSING (B)'}]
ok(pick(DUP, 'ZZ (HOUSING)') is None, '여럿이 걸렸는데 하나를 골랐다')
# 글자 그대로 같은 게 있으면 그게 먼저다 (느슨한 쪽이 이기면 안 된다)
MIX = [{'part_number': 'A100 (OLD)', 'id': 'A100 (OLD)'},
       {'part_number': 'A100', 'id': 'A100'}]
ok((pick(MIX, 'A100') or {}).get('part_number') == 'A100',
   '글자 그대로 같은 것을 두고 다른 것을 골랐다')

# ── 4. 미리보기와 반영이 같은 함수를 쓰는가 ─────────────────────
# 따로 두면 미리보기에서 본 것과 저장되는 것이 어긋난다.
ok(SRC.count('_ds_pick_model(') >= 3,
   '미리보기나 반영 중 한쪽이 옛 찾기를 쓴다')
ok('_df_pick_model(proj.get("models") or [], it.get("part_number"), "")'
   not in SRC, '개발 일정 쪽에 옛 찾기가 남아 있다')

# ── 5. 안 붙는 게 맞는 것 ────────────────────────────────────────
# 아래는 괄호 문제가 아니라 품번이 서로 다른 건이다. 실제 등록 자료로
# 확인했다 (2026-11-02). 억지로 붙이면 남의 날짜가 박힌다.
#   Stellantis    68654538AA   → 등록은 68666525AA
#   KEFICO INDIA  9191090001   → 등록은 9091090001 (9191 / 9091)
#   KEFICO INDIA  9191060001   → 등록은 9091060001
#   YOUNGHWA      M230080      → 등록은 M23008 (끝자리 하나 빠짐)
#   SCHAEFFLER    AAA99940001  → 등록은 AAA9994000100
#   KET KOREA     PART NO : (…)→ 양식에 품번이 아예 없다
NEAR = [{'part_number': '9091090001', 'id': '9091090001'}]
ok(pick(NEAR, '9191090001 (HE HOUSING)') is None,
   '숫자가 다른 품번을 억지로 붙였다')
ok(pick([{'part_number': 'M23008', 'id': 'M23008'}], 'M230080 (PCDU TOP COVER)')
   is None, '끝자리가 다른 품번을 억지로 붙였다')

# ── 6. 프로젝트를 넘어서 찾는다 ─────────────────────────────────
# Min: "애초에 파트넘버가 다른 사업부들 다 보면 같은 수가 없는데
#      왜 사업부에 맞춰서 안 바뀌는거야"
#
# 세어 봤더니 맞는 말이었다. 자동차 모델 173종에 서로 다른 품번이
# 162개, 겹치는 건 2개뿐 — 그 2개도 'Schaeffler' 와 'Schaefller' 가
# 같은 품목을 두 번 들고 있어서 생긴 것이다. 품번은 사실상 이름값이다.
#
# 그런데 찾기는 '양식에 적힌 고객사 → 그 프로젝트 안' 으로 갇혀 있었다.
# 고객사를 조금 다르게 적거나 프로젝트가 두 번 등록돼 있으면, 품번이
# 멀쩡히 있는데도 못 찾았다. 실제로 이 한 줄이 3품목을 더 살렸다
#   SCHAEFFLER AAA9983310100  → automotive_schaeffler (적힌 건 schaefller)
#   SCHAEFFLER AAA9994000100  → 〃
#   KEFICO INDIA 9191060001   → auto_kefico
ok('def _ds_pick_in_division' in SRC, '사업부 전체에서 찾는 길이 없다')
_i = SRC.find('def _ds_pick_in_division')
_div = SRC[_i:SRC.find('\ndef ', _i + 10)]
ok('len(hit) == 1' in _div,
   '여럿이 걸려도 하나를 고른다 — 남의 품목에 남의 날짜가 박힌다')
ok('if pk == skip' in _div, '이미 본 프로젝트를 또 뒤진다')
# 미리보기와 반영 둘 다 — 따로 두면 미리보기가 거짓말이 된다
ok(SRC.count('_ds_pick_in_division(data, division_id') == 2,
   '미리보기나 반영 중 한쪽만 넓게 찾는다')
# 어디서 찾았는지 알려 줘야 한다. 조용히 다른 프로젝트에 넣으면,
# 양식의 고객사가 틀렸다는 걸 아무도 모른 채 지나간다.
ok('"moved_to": moved' in SRC, '미리보기가 어디서 찾았는지 안 알린다')
ok('warn_moved' in SRC and '"found_in"' in SRC,
   '반영이 어디서 찾았는지 안 알린다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 개발 일정 품번 맞추기')
