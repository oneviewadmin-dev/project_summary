# 앱 홈 매출 · 현황을 전 사업부 기준으로 (2026-11-02)
#   python3 backend/tests/test_all_division_revenue.py
#
# Min: "첫 번째 사진에 보이는 내용들 반도체 기준이 아니라 이제 전체적인
#      사업부 다 내용도 포함시켜주고"
#
# 숫자를 여기서 다시 계산하지 않는다. 사업부별 금액은 _home_division_rows
# 가 이미 낸다 (매출 파일 우선 → 없으면 판가 × 실적). 거기서 또 세면
# admin '홈 관리' 화면과 앱이 서로 다른 숫자를 들게 된다.
import ast, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


tree = ast.parse(SRC)
G = {}
for n in tree.body:
    if isinstance(n, ast.FunctionDef) and n.name == '_all_division_revenue_view':
        exec(compile(ast.Module([n], []), 'main.py', 'exec'), G)
ok('_all_division_revenue_view' in G, 'main.py 에 전사 합계 함수가 없다')

# ── 1. 더하기만 한다 ─────────────────────────────────────────────
rows = [
    {'id': 'semiconductor', 'label': '반도체사업부', 'actual': 1000.0,
     'target': 2000.0, 'rate': 50.0, 'actual_at': '2026-10-26', 'app_visible': True},
    {'id': 'network', 'label': '네트워크사업부', 'actual': 500.0,
     'target': 0.0, 'rate': None, 'actual_at': '2026-10-31', 'app_visible': True},
    # 앱에서 숨긴 사업부는 합계에도 안 들어간다. 줄은 안 보이는데 합만
    # 커지면, 줄을 다 더해도 합이 안 맞는다.
    {'id': 'hidden_one', 'label': '숨김', 'actual': 9999.0,
     'target': 9999.0, 'rate': 100.0, 'actual_at': '2026-11-01', 'app_visible': False},
]
G['_home_division_rows'] = lambda month: rows
G['_div_ytd_money'] = lambda did, month: {'semiconductor': 12000.0,
                                          'network': 3000.0,
                                          'hidden_one': 77777.0}.get(did, 0.0)
# 2026-11-03 — 사업부마다 '상세' 를 실어 보낸다. 앱이 사업부를 누르면
# 그 줄들이 펴진다 (Min: "사업부 밑에 만약에 상세로 내용이 있으면
# 눌렀을 때 뜨게끔 해줘"). 여기서는 쪼개는 쪽을 따로 시험하지 않고,
# 실려 나가는지만 본다.
G['_div_breakdown'] = lambda did, month: (
    [{'item': '데이터 센터', 'actual': 400}] if did == 'semiconductor' else [])

v = G['_all_division_revenue_view']('2026-11')
ok(v['actual'] == 1500, '실적 합이 틀렸다 — %r' % v['actual'])
# 상세가 실려 나가야 앱이 펼 수 있다. 없는 사업부는 빈 칸이고,
# 화면은 빈 칸이면 안 펴지게 그린다.
_byk = {g['key']: g for g in v['groups']}
ok(_byk['semiconductor']['items'] == [{'item': '데이터 센터', 'actual': 400}],
   '사업부 상세가 안 실린다 — %r' % _byk['semiconductor']['items'])
ok(_byk['network']['items'] == [], '쪼갤 게 없는데 뭔가 실렸다')
ok(v['target'] == 2000, '타겟 합이 틀렸다 — %r' % v['target'])
ok(v['ytd'] == 15000, '연간 누적에 숨긴 사업부가 섞였다 — %r' % v['ytd'])
ok(v['target_rate'] == 75, '달성률이 틀렸다 — %r' % v['target_rate'])
ok(v['target_left'] == 500, '남은 타겟이 틀렸다 — %r' % v['target_left'])

# ── 2. 묶음 = 사업부 ─────────────────────────────────────────────
keys = [g['key'] for g in v['groups']]
ok(keys == ['semiconductor', 'network'], '묶음이 사업부가 아니다 — %r' % keys)
# 2026-11-03 — items 는 이제 '그 사업부를 더 쪼갠 줄' 이다. 전에는
# 늘 비어 있었다 (전사 화면에서는 쪼갤 게 없다고 봤다). 지금은
# 반도체의 '데이터 센터 · 우주항공', 자동차 · 네트워크의 '구분' 이
# 여기 실려서, 사업부를 누르면 펴진다.
ok(v['groups'][0]['items'] != [], '사업부 상세가 안 실린다')
# 네트워크는 타겟이 0이라 달성률을 지어내면 안 된다
ok(v['groups'][1]['rate'] is None, '타겟 없는 사업부에 달성률을 만들었다')

# ── 3. 언제 기준인지 ────────────────────────────────────────────
ok(v['as_of'] == '2026-10-31',
   '기준일이 제일 늦은 날이 아니다 — %r' % v['as_of'])

# ── 4. 타겟이 하나도 없으면 ─────────────────────────────────────
# 앱 카드가 '타겟 미등록' 으로 그린다. 0 으로 나누면 안 된다.
rows2 = [dict(rows[0], target=0.0, rate=None)]
G['_home_division_rows'] = lambda month: rows2
v2 = G['_all_division_revenue_view']('2026-11')
ok(v2['has_target'] is False, '타겟이 없는데 있다고 한다')
ok(v2['target_rate'] is None, '타겟이 없는데 달성률을 만들었다')

# ── 5. 아무 사업부도 안 보이면 ──────────────────────────────────
G['_home_division_rows'] = lambda month: []
v3 = G['_all_division_revenue_view']('2026-11')
ok(v3['actual'] == 0 and v3['groups'] == [] and v3['has_data'] is False,
   '빈 목록에서 터지거나 거짓 숫자를 만든다')

# ── 6. 기본값은 아직 반도체다 ───────────────────────────────────
# 안 올린 앱은 division 칸을 안 보낸다. 기본을 전사로 바꾸면 그 앱들의
# 숫자가 말없이 바뀐다 — 쓰는 사람은 왜 달라졌는지 알 길이 없다.
ok('def get_revenue(month: str = None, division: str = "semiconductor")' in SRC,
   '/revenue 기본값이 반도체가 아니다')
ok('def get_home_alerts(limit: int = 12, division: str = "semiconductor")' in SRC,
   '/home/alerts 기본값이 반도체가 아니다')

# ── 7. 앱은 또박또박 비워 보낸다 ────────────────────────────────
REV = (ROOT.parent / 'mobile/lib/services/revenue_service.dart').read_text(encoding='utf-8')
ALR = (ROOT.parent / 'mobile/lib/services/home_alerts_service.dart').read_text(encoding='utf-8')
ok("'?division=' : '?month=$month&division='" in REV,
   '앱 매출이 전사로 안 부른다')
ok('&division=' in ALR, '앱 현황이 전사로 안 부른다')
# 캐시 이름도 갈라야 한다 — 반도체만 담긴 지난 캐시가 그대로 뜬다
ok("'revenue_all" in REV and "'home_alerts_all'" in ALR,
   '캐시 이름을 안 갈랐다 — 옛 반도체 값이 그대로 보인다')

# ── 8. 적힌 말과 세는 것이 같아야 한다 ──────────────────────────
for f in ('mobile/lib/components/home/exec_revenue_card.dart',
          'mobile/lib/components/home/status_board_card.dart'):
    t = (ROOT.parent / f).read_text(encoding='utf-8')
    ok('(반도체 기준)' not in t, '%s 에 아직 반도체 기준이라 적혀 있다' % f)
    ok('(전 사업부)' in t, '%s 에 무슨 기준인지 안 적혀 있다' % f)

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 전 사업부 매출 · 현황')
