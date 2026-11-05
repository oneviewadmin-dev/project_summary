# 사업부 매출은 매출 파일이 먼저다 (2026-10-28)
#   python3 backend/tests/test_division_revenue_file.py
#
# Min: "그냥 최대한 매출 파일 업로드가 되면 그걸 우선시 하고 만약에 없으면
#      판가 대비 계획 or 실적 계산해서 올리라고"
#      "통화는 USD로 통일 시킬거고 환율은 그 주 기준 평균 금액으로"
#
# 전에는 사업부 매출을 모델 판가 × 출하수량으로 어림잡았다. 회계가 쓰는
# 숫자에는 스페어 부품 · 반제품 단가 차이 · 선매출 · 환율 적용 시점이 다
# 들어 있어서, ESS 10월만 놓고도 $516만이 달랐다. 보고 자리에서 어느 쪽이
# 맞느냐는 질문이 나오면 답할 수가 없다.
import ast, importlib, os, pathlib, shutil, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
HTML = (ROOT / 'admin_v2.html').read_text(encoding='utf-8')
FORMS = ROOT / 'tests' / 'forms' / 'v2'
FIX = FORMS / 'ESS_매출_261019.xlsx'

import revenue_file_import as rfi        # noqa: E402
ok = 0

# ── 1. 환율: 그 주에 적힌 날만 평균 낸다 ─────────────────────────
# 쉬는 날은 줄이 아예 없다. 없는 날을 0 으로 치면 환율이 폭락한다.
import datetime as dt                    # noqa: E402


class _FakeWs:
    def __init__(self, rows):
        self._r = rows
        self.max_row = len(rows)
        self.max_column = len(rows[0]) if rows else 0

    def cell(self, r, c):
        class C:
            pass
        x = C()
        try:
            x.value = self._r[r - 1][c - 1]
        except Exception:
            x.value = None
        return x


ws = _FakeWs([
    ['날짜', '통화명', '환율'],
    [dt.datetime(2026, 10, 12), '미국 달러 (USD)', 1300.0],
    [dt.datetime(2026, 10, 13), '미국 달러 (USD)', 1400.0],
    # 10/14~16 은 줄이 없다 (쉬는 날 · 미기재)
    [dt.datetime(2026, 10, 19), '미국 달러 (USD)', 1500.0],
])
fx = rfi.parse_fx(ws)
assert fx[(2026, 42)] == 1350.0, '적힌 날만 평균 내야 한다: %r' % fx
assert fx[(2026, 43)] == 1500.0
ok += 1

# ── 2. 달 환산은 그 달에 걸친 주들의 평균 ─────────────────────────
# 매출 파일이 주는 것은 월 합계뿐이라 달 하나에 환율 하나가 필요하다.
got = rfi.fx_for_month({(2026, 42): 1300.0, (2026, 43): 1500.0}, 2026, 10)
assert abs(got - 1400.0) < 0.001, got
assert rfi.fx_for_month({}, 2026, 10) is None, '환율이 없는데 숫자를 만들어 냈다'
ok += 1

# ── 3. 실제 파일 ──────────────────────────────────────────────────
if FIX.exists():
    import openpyxl                      # noqa: E402
    g = rfi.parse_workbook(openpyxl.load_workbook(FIX, data_only=True))
    assert g['year'] == 2026, g['year']
    ok += 1

    # 원화 합계가 파일의 '월매출' 줄과 똑같아야 한다.
    # 같은 표가 KRW · USD 로 두 번 나오는데, 끝까지 훑으면 아래 USD 표가
    # 원화에 더해진다 — 10월이 724.3억이어야 하는데 724.9억이 나왔다.
    # 0.07% 라 눈으로는 안 보인다. 그래서 더 위험하다.
    assert round(g['months']['2026-10']['krw']) == 72432223036, \
        '10월 원화가 %r — USD 표까지 더했을 수 있다' % g['months']['2026-10']['krw']
    assert round(g['months']['2026-09']['krw']) == 114574953432, \
        g['months']['2026-09']['krw']
    ok += 1

    # 고객/모델 줄은 8개 (소계·합계·USD 표는 빼고)
    assert len(g['rows']) == 8, [r['model'] for r in g['rows']]
    assert not any(r['model'] in ('소계', '합계', '월매출') for r in g['rows'])
    ok += 1

    # 환율이 없는 달은 USD 를 만들지 않는다 (파일 환율은 10/16 까지)
    assert g['months']['2026-10']['usd'] is not None
    assert g['months']['2026-11']['usd'] is None, '환율이 없는 달에 USD 를 지어냈다'
    ok += 1

    # 주 평균이라 파일의 월평균환율(1332.2)과는 다른 값이 나온다 — 그게 의도다
    assert abs(g['months']['2026-10']['fx'] - 1332.2) > 1, \
        '월평균환율을 그대로 쓰고 있다 (주 평균이 아니다)'
    ok += 1

    # ── 4. 담기 · 꺼내기 ──────────────────────────────────────────
    TMP = tempfile.mkdtemp(prefix='divrev_')
    os.environ['DATA_DIR'] = TMP
    try:
        import division_revenue as dr    # noqa: E402
        importlib.reload(dr)
        assert str(dr.FILE).startswith(TMP), dr.FILE
        dr.put('ess', g['year'], g['months'], g['rows'], 'ESS매출.xlsx')
        assert dr.month_usd('ess', '2026-10') is not None
        ok += 1
        # 환율이 없어 USD 를 못 낸 달은 아예 안 담는다. 담으면 화면이
        # '매출 0' 으로 읽어서, 자료가 없는 것과 0 원인 것이 섞인다.
        assert dr.month_usd('ess', '2026-11') is None, '빈 달을 담았다'
        ok += 1
        # 파일 없는 사업부는 None — 부르는 쪽이 계산으로 간다
        assert dr.month_usd('bloom', '2026-10') is None
        assert dr.month_usd('', '2026-10') is None
        ok += 1
        # 그 해만 갈아 끼운다. 2026 파일을 올렸다고 2025 가 사라지면 안 된다.
        dr.put('ess', 2025, {'2025-12': {'usd': 11, 'krw': 1, 'fx': 1}}, [], 'a')
        dr.put('ess', 2026, {'2026-10': {'usd': 22, 'krw': 2, 'fx': 2}}, [], 'b')
        assert dr.month_usd('ess', '2025-12') == 11, '다른 해가 날아갔다'
        assert dr.month_usd('ess', '2026-10') == 22
        assert dr.month_usd('ess', '2026-09') is None, '같은 해 옛 달이 안 지워졌다'
        ok += 1
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
        os.environ.pop('DATA_DIR', None)

# ── 5. 홈·매출 관리가 파일을 먼저 보는가 ─────────────────────────
# 서버가 담아만 두고 안 쓰면 화면은 그대로다.
_h = SRC[SRC.index('def _home_division_rows'):]
_h = _h[:_h.index('\n@app.') if '\n@app.' in _h else len(_h)]
assert '_drev.month_usd(did, month)' in _h, '홈 사업부 줄이 매출 파일을 안 본다'
assert 'actual, a_src = float(_file_usd), "매출 파일"' in _h, \
    '파일 값을 실적으로 안 쓴다'
assert 'if _file_usd is not None:\n            pass\n        elif did == "semiconductor":' in _h, \
    '파일이 있어도 옛 계산이 덮어쓴다'
ok += 1
# 파일이 없으면 '그 달 판가 × 실적' 계산으로 간다.
# 2026-11-03 — 그 계산도 없을 때 쓰던 누계(_div_model_money)는 뺐다.
# 누계는 달과 상관없는 값이라 11월 3일에 11월 실적이 $1187만으로 떴다.
#   Min: "왜 누계로 되는거야...누구 마음대로"
assert '_div_actual_money(models, month)' in _h, \
    '파일이 없을 때 돌아갈 계산이 사라졌다'
assert '_div_model_money(models)' not in _h, '아직 누계로 돌아간다'
ok += 1

# ── 6. 창구와 화면 ───────────────────────────────────────────────
assert '/revenue-file/preview' in SRC and '/revenue-file/apply' in SRC, '올릴 창구가 없다'
assert '"revenue_file": _drev.info(div)' in SRC, '화면이 어느 파일인지 알 길이 없다'
ok += 1
assert 'dvWireRevFile' in HTML and 'dv-rvf-go' in HTML, 'admin 에 올리는 자리가 없다'
assert '이 파일로 담기' in HTML, '미리보기 없이 바로 담는다'
assert '주 평균' in HTML, '환율을 어떻게 쓰는지 화면이 말하지 않는다'
ok += 1

# ── 7. 세 사업부 파일이 다 읽히는가 (2026-10-28) ─────────────────
#
# Min: "내가 3가지 사업부 다 줬잖아..."
#
# 처음엔 ESS 모양만 붙여 놔서 네트워크 · 자동차는 "'써머리' 시트를 못
# 찾았습니다" 로 끊겼다. 세 파일이 서로 다르게 생겼다.
#   ESS      '써머리' 시트 + '환율정보' 시트 (원화 → 주 평균 환율로 환산)
#   네트워크   한 장에 고객사 × 주차 × 계획/실적. 주차를 매주 채운다
#   자동차    같은 모양인데 달 소계만 채우고 주차는 거의 비어 있다
import openpyxl as _ox                  # noqa: E402

CASES = [
    ('네트워크_매출_W42.xlsx', '주간보고', 8, '실행계획'),
    ('자동차_매출_20261016.xlsx', '주간보고', 32, '실행계획'),
]
for name, shape, ncust, plan in CASES:
    f = FORMS / name
    if not f.exists():
        continue
    g = rfi.parse_workbook(_ox.load_workbook(f, data_only=True))
    assert g['shape'] == shape, '%s: 모양을 %r 로 읽었다' % (name, g['shape'])
    assert g['year'] == 2026, '%s: 연도 %r' % (name, g['year'])
    assert len(g['customers']) == ncust, \
        '%s: 고객사 %d개여야 하는데 %d개 — 합계 줄까지 센 것 아닌가' \
        % (name, ncust, len(g['customers']))
    assert g['plan_kind'] == plan, '%s: 계획 줄이 %r' % (name, g['plan_kind'])
    # 1~10월이 다 있어야 한다. 자동차는 1행에 다른 표의 주차 머리글이
    # 17개 있어서 그쪽을 머리글로 잡은 적이 있다 — 그때 1~6월이 통째로
    # 빠졌다. 제일 많은 줄(52주)을 머리글로 고른다.
    want = ['2026-%02d' % m for m in range(1, 11)]
    got = sorted(g['months'])
    assert got == want, '%s: 달이 %r' % (name, got)
    # 실적도 계획도 0 이 아니어야 한다
    assert all(g['months'][k]['usd'] for k in want), name
    assert all(g['plan_months'].get(k) for k in want), '%s: 계획이 빈 달이 있다' % name
    ok += 1

# 네트워크 10월 — 파일의 달 소계 칸이 비어 있어 주차에서 만든 달이다.
f = FORMS / '네트워크_매출_W42.xlsx'
if f.exists():
    wb = _ox.load_workbook(f, data_only=True)
    ws = wb.worksheets[0]
    head, weeks, mcols, cc, ck = rfi._wk_layout(ws)
    g = rfi.parse_weekly(ws, 2026)
    last = 0
    for r in range(g['total_row'], ws.max_row + 1):
        if str(ws.cell(r, ck).value or '').strip() == '실적':
            last = r
    assert not ws.cell(last, mcols[10]).value, \
        '10월 소계가 차 있다 — 이 검사의 전제가 깨졌다'
    assert g['months'].get('2026-10'), '소계가 비면 주차에서 만들어야 한다'
    ok += 1
    # 주차도 담긴다 — 주차 보드가 쓸 자료다
    assert len(g['weeks']) >= 40, '주차를 %d개만 읽었다' % len(g['weeks'])
    ok += 1

# ── 8. 계획 · 주차도 담기고 꺼내지는가 ───────────────────────────
TMP2 = tempfile.mkdtemp(prefix='divrev2_')
os.environ['DATA_DIR'] = TMP2
try:
    import division_revenue as dr2      # noqa: E402
    importlib.reload(dr2)
    dr2.put('network', 2026,
            {'2026-10': {'usd': 100, 'krw': None, 'fx': None}}, [], 'n.xlsx',
            plan_months={'2026-10': 200}, weeks={'2026-W42': 30},
            shape='주간보고')
    assert dr2.month_usd('network', '2026-10') == 100
    assert dr2.month_plan('network', '2026-10') == 200
    assert dr2.week_usd('network', '2026-W42') == 30
    assert dr2.month_plan('network', '2026-09') is None
    assert dr2.month_plan('bloom', '2026-10') is None
    assert dr2.info('network')['shape'] == '주간보고'
    ok += 1
finally:
    shutil.rmtree(TMP2, ignore_errors=True)
    os.environ.pop('DATA_DIR', None)

# 타겟도 파일이 먼저여야 한다. 손으로 넣은 값은 그보다 더 먼저다.
assert '_drev.month_plan(did, month)' in _h, '타겟이 매출 파일을 안 본다'
assert 'target, t_src = float(_file_plan), "매출 파일 계획"' in _h
assert 'if did in targets and (targets.get(did) or {}).get("total"):' in _h, \
    '손으로 넣은 타겟이 파일 계획을 못 덮는다'
ok += 1

# ── 9. 파일이 적어 둔 '구분' 표 (2026-10-28) ─────────────────────
#
# Min: "반도체사업부도 보면 내가 있는 품목이 아니더라도 매출 관리 파일
#      기준으로 구분이 나눠져 있잖아 다른 사업부들도 다 동일하게 해줘"
DETS = [
    ('네트워크_매출_W42.xlsx', '2026-09',
     ['제품 매출 금액', '금형 매출 금액', '고객사별'],
     'Sub-total', '내부거래', '총합'),
    ('자동차_매출_20261016.xlsx', '2026-09',
     ['직거래', '3자거래', '고객사별'], 'Sub-total', None, '총 합계'),
]
for name, mon, want_boxes, want_sub, want_int, want_grand in DETS:
    f = FORMS / name
    if not f.exists():
        continue
    g = rfi.parse_workbook(_ox.load_workbook(f, data_only=True))
    d = (g.get('detail') or {}).get(mon)
    assert d, '%s: %s 구분 표가 없다' % (name, mon)
    labels = " | ".join(b['label'] for b in d['groups'])
    for w in want_boxes:
        assert w in labels, '%s: 구분에 %r 가 없다 — %s' % (name, w, labels)
    assert d['subtotal'] and want_sub in d['subtotal']['label'], \
        '%s: 소계 줄이 %r' % (name, d.get('subtotal'))
    assert d['grand'] and want_grand in d['grand']['label'], \
        '%s: 총합 줄이 %r' % (name, d.get('grand'))
    if want_int:
        assert d['internal'] and want_int in d['internal']['label'], \
            '%s: 내부거래 줄이 %r' % (name, d.get('internal'))
    # 총합이 위 KPI 실적과 같아야 한다 — 두 숫자가 다르면 어느 쪽이
    # 맞는지 아무도 모른다
    assert abs(d['grand']['actual'] - g['months'][mon]['usd']) < 1, \
        '%s: 총합 %r 와 월 실적 %r 가 다르다' % (name, d['grand']['actual'],
                                            g['months'][mon]['usd'])
    # 고객사 묶음에는 세부가 붙어 있어야 한다
    cb = [b for b in d['groups'] if b['label'] == '고객사별']
    assert cb and len(cb[0]['items']) >= 5, '%s: 고객사 세부가 없다' % name
    ok += 1

# 네트워크 총합 줄 이름에 '내부거래' 가 들어 있다 ('총합 (내부거래 포함)').
# 내부거래를 먼저 보면 총합이 내부거래로 잡힌다 — 총합을 먼저 본다.
f = FORMS / '네트워크_매출_W42.xlsx'
if f.exists():
    g = rfi.parse_workbook(_ox.load_workbook(f, data_only=True))
    d = g['detail']['2026-09']
    assert '내부거래' in d['grand']['label'], '이 검사의 전제가 깨졌다'
    assert d['internal'] and d['internal']['actual'] != d['grand']['actual'], \
        '총합을 내부거래로 잡았다'
    ok += 1

# ESS 도 같은 모양이어야 한다 — 묶음은 고객사, 세부는 모델
if FIX.exists():
    g = rfi.parse_workbook(_ox.load_workbook(FIX, data_only=True))
    d = (g.get('detail') or {}).get('2026-10')
    assert d and len(d['groups']) >= 3, 'ESS 구분 표가 없다'
    assert any(b['items'] for b in d['groups']), 'ESS 세부(모델)가 없다'
    assert abs(d['grand']['actual'] - g['months']['2026-10']['usd']) < 1
    ok += 1

# 담기고 꺼내지는가
TMP3 = tempfile.mkdtemp(prefix='divrev3_')
os.environ['DATA_DIR'] = TMP3
try:
    import division_revenue as dr3      # noqa: E402
    importlib.reload(dr3)
    dr3.put('network', 2026, {'2026-10': {'usd': 1, 'krw': None, 'fx': None}},
            [], 'n.xlsx', detail={'2026-10': {'groups': [], 'grand': None}})
    assert dr3.month_detail('network', '2026-10') is not None
    assert dr3.month_detail('network', '2026-09') is None
    ok += 1
finally:
    shutil.rmtree(TMP3, ignore_errors=True)
    os.environ.pop('DATA_DIR', None)

assert '"detail": _drev.month_detail(div, month)' in SRC, '화면이 구분 표를 못 받는다'
ok += 1

print('ok %d' % ok)
