# 누계를 '그 달 실적' 으로 쓰지 않는다 (2026-11-03)
#   python3 backend/tests/test_month_actual_no_cumulative.py
#
# Min: "11월 이제 시작인데 실적이 어디서 나온건지"
#      "왜 누계로 되는거야...누구 마음대로"
#
# 그 달 자료가 없을 때 '숫자가 사라지는 것보다 낫다' 며 누계
# (판가 × 전체 출하수량) 를 넣어 뒀었다. 누계는 달과 상관없는 값이라,
# 11월 3일에 11월 실적이 $1187만으로 떴다. 자동차는 10월도 11월도
# 똑같이 $253만 5,913 — 같은 누계가 두 달에 겹쳐 선 것이다.
#
# 출처 글자('판가 × 출하 (누계)')로 구분된다고 적어 뒀지만, 앱에는 그
# 글자가 안 뜬다. 보는 사람에게는 그냥 '그 달 실적' 이다.
#
# 매출을 가져오는 차례는 그대로다 — 파일 → 그 달 판가×실적. 달과
# 상관없는 누계만 뺀다. 누계는 '연간 누적'(_div_ytd_money) 자리에만 선다.
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


# ── 1. 달 숫자를 만드는 곳에서 누계를 안 쓴다 ───────────────────
ok('_div_model_money' in SRC, '_div_model_money 가 사라졌다')
# 정의 한 줄 말고는 아무도 안 불러야 한다
ok(SRC.count('_div_model_money(') == 1,
   '누계를 아직 어디선가 쓴다 (%d곳)' % SRC.count('_div_model_money('))
ok('판가 × 출하 (누계)' not in SRC, "'누계' 출처가 아직 붙는다")

# ── 2. 자료가 없으면 0 이다 ─────────────────────────────────────
_i = SRC.find('def _home_division_rows')
_body = SRC[_i:SRC.find('\n@app.', _i)]
ok('actual, a_src = 0.0, ""' in _body, '그 달 자료가 없을 때 0 이 아니다')
# 파일 → 그 달 실적 차례는 그대로여야 한다
ok('_drev.month_usd(did, month)' in _body, '매출 파일을 먼저 안 본다')
ok('_div_actual_money(models, month)' in _body, '그 달 판가×실적을 안 쓴다')
_i_file = _body.find('_drev.month_usd(did, month)')
_i_calc = _body.find('_div_actual_money(models, month)')
ok(0 < _i_file < _i_calc, '파일보다 계산을 먼저 본다')

# ── 3. 프로젝트 줄도 같은 잣대 ──────────────────────────────────
# 합계가 0 인 달에 프로젝트 줄만 누계로 서면 "어느 쪽이 틀렸지" 가 된다.
_j = SRC.find('def _div_revenue_view')
_vbody = SRC[_j:SRC.find('\n@app.', _j)]
ok('_div_actual_money(ms, month) or 0.0' in _vbody,
   '프로젝트 줄이 아직 누계로 내려간다')

# ── 4. 연간 누적은 살아 있어야 한다 ─────────────────────────────
# 누계를 없앤 게 아니라, 달 칸에서 뺀 것이다.
ok('def _div_ytd_money' in SRC, '연간 누적이 사라졌다')
_k = SRC.find('def _div_ytd_money')
_ybody = SRC[_k:SRC.find('\ndef ', _k + 10)]
ok('month_usd' in _ybody or '_div_actual_money' in _ybody,
   '연간 누적이 달마다 제 출처로 안 센다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 달 실적에 누계 안 씀')
