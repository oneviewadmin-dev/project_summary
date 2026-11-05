# 양식으로 판가를 바꾸면 '그 주차부터' 다 (2026-10-28)
#   python3 backend/tests/test_price_phase_form.py
#
# Min: "만약에 내가 W43주차에 변경된 금액으로 올렸어 그러면 W42까지는
#      기존에 있던 금액 그대로 지표가 되어야 하고 43주차 부터 변경된
#      금액으로 지표가 되기를 원하는거야"
#
# 매출은 `판가 × 그 주차 실적` 이다. 전에는 양식이 판가를 그냥 덮어써서,
# 10월에 $7,243 → $7,800 으로 고쳐 올리면 8월에 나간 물량 매출까지
# $7,800 으로 다시 계산됐다. 지난달 보고서 숫자가 조용히 바뀐다.
#
# 구간을 쌓을 자리(phases)는 처음부터 있었고 매출 계산도 그걸 봤다
# (_phase_at). 그런데 구간을 만드는 길이 admin 모델 표 저장 한 곳뿐이었고
# 그 길이 막혀 있어서(_write_off), 실제 데이터에는 구간이 한 건도 없었다.
import ast, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
HTML = (ROOT / 'admin_v2.html').read_text(encoding='utf-8')

tree = ast.parse(SRC)
WANT = {'_df_apply_price', '_df_week_tag', '_week_ord', '_phase_ord',
        '_norm_phases', '_phase_row_at', '_phase_at', '_as_money',
        '_this_week_tag'}
G = {}
for n in tree.body:
    if isinstance(n, ast.FunctionDef) and n.name in WANT:
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
missing = WANT - set(G)
assert not missing, 'main.py 에서 못 찾은 함수: %r' % sorted(missing)
G['_PHASE_EPOCH'] = '2000-W01'
ok = 0

tag = G['_df_week_tag']
apply_price = G['_df_apply_price']
price_at = G['_phase_at']

# ── 1. 양식의 기준 주차를 구간 시작점으로 ─────────────────────────
assert tag('2026-10', 'W43') == '2026-W43', tag('2026-10', 'W43')
assert tag('2026-10', '43') == '2026-W43', "'43' 처럼 W 없이 와도 읽어야 한다"
ok += 1
# 연말·연초 보정 — 1월 양식의 W52 는 지난해 것이다
assert tag('2026-01', 'W52') == '2025-W52', tag('2026-01', 'W52')
assert tag('2026-12', 'W01') == '2027-W01', tag('2026-12', 'W01')
ok += 1
# 주차가 빈 칸이면 '0주차' 가 아니라 빈 글자다. '2026-W00' 으로 열면
# 없는 주차부터 판가가 바뀌는 셈이라 사실상 전 기간 소급이 된다.
assert tag('', 'W43') == '' and tag('2026-10', '') == '' \
    and tag('2026-10', None) == '' and tag('2026-10', 'W99') == '', \
    '못 읽는 값에 아무 주차나 만들어 낸다'
ok += 1

# ── 2. W43 양식 → W42 는 옛 판가, W43 부터 새 판가 ────────────────
m = {'id': 'A', 'name': 'A', 'group': '양산', 'price': 7243}
got = apply_price(m, {'price': 7800}, '2026-W43')
assert got, '판가가 바뀌었는데 아무것도 안 남겼다'
assert got['price'] == [7243, 7800], got
ok += 1

assert price_at(m, '2026-10', 'W41')[1] == 7243, '지난 주차가 새 판가로 바뀌었다'
assert price_at(m, '2026-10', 'W42')[1] == 7243, '바로 전 주차가 새 판가로 바뀌었다'
assert price_at(m, '2026-10', 'W43')[1] == 7800, '기준 주차부터 안 바뀌었다'
assert price_at(m, '2026-11', 'W45')[1] == 7800, '다음 달이 옛 판가다'
ok += 1
# 지난달도 그대로여야 한다 — 그게 '지난달 보고서가 안 흔들린다' 는 뜻
assert price_at(m, '2026-08', 'W33')[1] == 7243, '지난달 매출이 새 판가로 다시 계산된다'
ok += 1
# 모델의 '지금 판가' 도 새 값이어야 한다 (표에 보이는 값)
assert m['price'] == 7800, '표에 보이는 판가가 안 바뀌었다'
ok += 1

# ── 3. 같은 주차 양식을 두 번 올려도 구간이 안 늘어난다 ───────────
# 같은 파일을 다시 올리는 일은 흔하다.
before = len(m['phases'])
apply_price(m, {'price': 7900}, '2026-W43')
assert len(m['phases']) == before, '같은 주차에 구간이 또 생겼다: %r' % m['phases']
assert price_at(m, '2026-10', 'W43')[1] == 7900
assert price_at(m, '2026-10', 'W42')[1] == 7243, '다시 올렸더니 과거가 흔들렸다'
ok += 1

# ── 4. 판가가 안 바뀌면 구간을 안 만든다 ──────────────────────────
m2 = {'id': 'B', 'group': '양산', 'price': 100}
assert apply_price(m2, {'price': 100}, '2026-W43') == {}
assert not m2.get('phases'), '안 바뀌었는데 구간이 생겼다'
assert m2['price'] == 100
ok += 1

# ── 5. 양식에 없는 칸은 안 건드린다 ───────────────────────────────
# 판가 칸이 없는 양식(ESS)이 저장할 때 0 을 보내 판가를 날린 적이 있다.
m3 = {'id': 'C', 'group': '양산', 'price': 500, 'material_cost': 50}
assert apply_price(m3, {}, '2026-W43') == {}, '빈 줄로 구간을 만들었다'
assert m3['price'] == 500 and m3['material_cost'] == 50
ok += 1
# 재료비만 와도 판가는 그대로
apply_price(m3, {'material_cost': 70}, '2026-W43')
assert m3['price'] == 500, '재료비만 고쳤는데 판가가 바뀌었다'
assert price_at(m3, '2026-10', 'W42')[1] == 500
ok += 1

# ── 6. 개발이던 시절은 개발로 남는다 ──────────────────────────────
# '처음부터' 구간의 구분을 양산으로 박으면, 지난달 개발 실적이 양산
# 판가로 다시 계산된다.
m4 = {'id': 'D', 'group': '개발', 'price': 0}
apply_price(m4, {'price': 9000}, '2026-W43')
assert m4['phases'][0]['group'] == '개발', m4['phases']
assert price_at(m4, '2026-09', 'W38')[0] == '개발', '개발이던 주차가 양산이 됐다'
ok += 1

# ── 7. 지난 주 양식을 뒤늦게 올려도 그 주차에 꽂힌다 ──────────────
# W43 을 넣은 뒤 W41 양식을 올리면 W41~W42 만 그 값이어야 한다.
m5 = {'id': 'E', 'group': '양산', 'price': 100}
apply_price(m5, {'price': 300}, '2026-W43')
apply_price(m5, {'price': 200}, '2026-W41')
assert price_at(m5, '2026-10', 'W40')[1] == 100, '더 앞 주차까지 바뀌었다'
assert price_at(m5, '2026-10', 'W41')[1] == 200
assert price_at(m5, '2026-10', 'W42')[1] == 200
assert price_at(m5, '2026-10', 'W43')[1] == 300, '나중 구간이 덮였다'
ok += 1

# ── 8. 양식 반영 고리가 이 함수를 쓰는가 ──────────────────────────
# 서버가 계산만 해 두고 안 쓰면 아무 일도 안 일어난다.
_ap = SRC[SRC.index('# 1. 품목정보 반영'):]
_ap = _ap[:_ap.index('2. 이슈사항 반영')]
assert '_df_apply_price(m, it, _price_tag)' in _ap, '반영할 때 판가 구간을 안 쌓는다'
assert 'm["price"] = it["price"]' not in _ap, '아직 판가를 그냥 덮어쓰는 줄이 남아 있다'
ok += 1
# 기준 주차는 **양식이 말하는 주차**다. 오늘 주차로 찍으면 W43 양식을
# 다음 주 월요일에 올렸을 때 W43 실적이 옛 판가로 계산된다.
assert '_price_tag = _df_week_tag(month, got.get("as_of_week")) or _this_week_tag()' in SRC, \
    '판가 구간을 오늘 주차로 연다'
ok += 1

# ── 9. 누르기 전에 보여 주는가 ────────────────────────────────────
assert '"price_changes": price_changes' in SRC, '반영 결과에 판가 변동이 없다'
assert '_df_price_preview(' in SRC, '미리보기가 판가 변동을 안 만든다'
ok += 1
assert "var pc = d.price_changes || [];" in HTML, '화면이 판가 변동을 안 읽는다'
assert "_xn('판가 바뀜', pc.length" in HTML, '판가 바뀜 수를 안 보여 준다'
assert '그 전 주차 매출은 <b>옛 판가 그대로</b> 남습니다.' in HTML, \
    '과거가 안 바뀐다는 것을 안 알려 준다'
ok += 1

print('ok %d' % ok)
