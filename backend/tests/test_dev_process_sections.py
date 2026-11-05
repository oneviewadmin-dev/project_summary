# 앱이 품목마다 제 단계를 그린다 (2026-11-02)
#   python3 backend/tests/test_dev_process_sections.py
#
# Min: "자동차 개발은 고객사별로 개발 일정 양식이 맞춰저야돼"
#
# 앱의 개발 프로세스 화면은 단계를 반도체 묶음 세 개(발주 · 제작·검사 ·
# 승인)로만 훑었다. 묶음은 반도체 13단계에만 붙어 있는 값이라, 개발 일정
# 양식으로 들어온 단계는 group 이 빈 값이다. 그래서 자동차
# (01 T-car … 06 SOP) 와 블룸 (PO 발주 → PRP → 최종 승인) 은 진행률과
# 초록 체크는 맞게 나오는데 **단계 목록이 통째로 비어** 보였다.
#
# 이제 묶음이 있으면 그 묶음으로, 없으면 '개발 단계' 한 덩이로 그린다.
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1].parent
DART = ROOT / 'mobile' / 'lib' / 'screens' / 'dev_process_screen.dart'
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


if not DART.exists():
    print('(앱 파일 없음 — 건너뜀)')
    raise SystemExit(0)
S = DART.read_text(encoding='utf-8')

# ── 1. 묶음을 서버 값에서 만든다 ────────────────────────────────
ok('_sections(' in S, '단계 묶음을 서버 값에서 안 만든다')
ok('..._sections(steps).map(' in S,
   '여전히 정해 둔 묶음 셋만 훑는다 — 자동차 · 블룸 단계가 안 뜬다')
ok('..._groups.map(' not in S, '옛 그리기가 남아 있다')

# ── 2. 묶음 없는 단계도 자리가 있다 ─────────────────────────────
ok("_plain = ['개발 단계'" in S, '묶음 없는 단계를 담을 자리가 없다')
ok("sg.isEmpty ? _plain[0] : sg" in S,
   '묶음이 빈 단계를 거르고 지나간다')

# ── 3. 서버가 준 차례를 지키나 ──────────────────────────────────
# 고객사마다 단계가 다르다. 화면이 멋대로 재정렬하면 그 고객사의
# 일하는 차례가 깨진다.
_i = S.find('static List<List<dynamic>> _sections')
_fn = S[_i:S.find('\n  @override', _i)]
ok('for (final s in steps)' in _fn, '서버가 준 차례대로 안 훑는다')
ok('.sort(' not in _fn, '단계를 다시 정렬한다 — 고객사 차례가 깨진다')
ok('seen.contains(key)' in _fn, '같은 묶음이 여러 번 생긴다')

# ── 4. 반도체는 그대로 ──────────────────────────────────────────
for g in ('발주', '제작·검사', '승인'):
    ok("'%s'" % g in S, '반도체 묶음 %r 이 사라졌다' % g)
ok('_groups.firstWhere' in _fn, '반도체 묶음 색을 안 가져온다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 품목마다 제 단계')

# ── 매출 상세 머리글 (2026-11-03) ───────────────────────────────
# Min: "왜 반도체 안에 자동차사업부가 들어가 있는거야"
#
# 머리글이 '반도체' 로 못 박혀 있었다. 데이터 센터도 우주항공도 결국
# 반도체 하나 안의 이야기였기 때문이다. 그런데 카드를 전사로 넓히면서
# 자동차 · 네트워크가 들어왔고, 그것들이 '반도체' 아래에 매달려 보였다.
_RV = ROOT / 'mobile' / 'lib' / 'screens' / 'revenue_detail_screen.dart'
_RS = ROOT / 'mobile' / 'lib' / 'services' / 'revenue_service.dart'
if _RV.exists() and _RS.exists():
    _v = _RV.read_text(encoding='utf-8')
    _s = _RS.read_text(encoding='utf-8')
    ok("Text('반도체'," not in _v, "머리글에 '반도체' 가 아직 박혀 있다")
    # 2026-11-03 — '전사' 머리 한 겹을 아예 없앴다. 사업부가 바로 카드다.
    #   Min: "전사 걍 빼버리고 각각 사업부 리스트 두고 사업부 밑에
    #        만약에 상세로 내용이 있으면 눌렀을 때 뜨게끔 해줘"
    # 그래서 머리글에 범위를 적을 자리도 없어졌다. scope 는 모델에
    # 남겨 둔다 — 다른 화면이 쓸 수 있고, 떼면 캐시에서 되살리기 번거롭다.
    ok('Widget divisionCard(RevenueGroup d)' in _v,
       '사업부 하나가 카드 한 장이 아니다')
    ok('for (final d in r.lines) divisionCard(d)' in _v,
       '사업부를 목록으로 안 그린다')
    ok('_openDiv' not in _v, "'전사' 한 겹이 아직 남아 있다")
    ok('final Set<String> _openKeys' in _v,
       '사업부마다 따로 못 편다 — 하나 열면 다 열린다')
    # 펼 게 없으면 눌러도 아무 일이 없어야 하고, 화살표도 없어야 한다.
    # 눌리는 척하는 화살표는 고장으로 읽힌다.
    ok('sub.isEmpty\n                ? null' in _v or 'sub.isEmpty ? null' in _v,
       '쪼갤 내용이 없는데도 눌린다')
    ok('sub.isEmpty\n                      ? const SizedBox.shrink()' in _v
       or 'sub.isEmpty ? const SizedBox.shrink()' in _v,
       '펼 게 없는데 화살표를 그린다')
    # 비중은 그 사업부 안에서 — 전사 대비로 재면 큰 사업부 안의 줄이 0% 로 눌린다
    ok('divTotal > 0 ? (it.actual * 100 / divTotal).round() : null' in _v,
       '상세 비중을 전사 대비로 잰다')
    ok('final String scope;' in _s, '매출 모델에 범위가 없다')
    ok("scope: (j['scope'] ?? '').toString()" in _s, '서버의 scope 를 안 읽는다')
    ok('scope: scope,' in _s, 'copyWith 에서 범위가 떨어진다 — 캐시에서 오면 빈다')
    # 서버가 사업부마다 쪼갠 줄을 실어 줘야 펼 게 있다
    _M = ROOT / 'backend' / 'main.py'
    _src = _M.read_text(encoding='utf-8')
    ok('def _div_breakdown' in _src, '서버가 사업부를 안 쪼갠다')
    ok('"items": _div_breakdown(' in _src, '쪼갠 줄을 안 실어 보낸다')
    # '고객사별' 은 위 묶음을 다시 쪼갠 같은 돈이다 — 같이 세우면 두 배가 된다
    ok('if str(g.get("key") or "") == "cust":' in _src,
       "'고객사별' 묶음을 걸러내지 않는다 — 합계가 두 배로 선다")
    # 반도체는 내부거래도 한 줄로 세워야 사업부 줄과 합이 맞는다.
    # 10월만 해도 빼 놓으면 $421만이 빈다.
    ok('_gs.append(rv["internal"])' in _src,
       '내부거래가 빠져서 쪼갠 줄 합이 사업부 줄과 안 맞는다')
    print('ok — 매출 상세 사업부별')
else:
    print('(매출 화면 없음 — 건너뜀)')

# ── 빈 유형 배지 (2026-11-03) ───────────────────────────────────
# Min: "파란색 동그라미는 왜 저걸 둔 이유를 모르겠어"
#
# 글자 없는 연보라 알약이 품목 이름 옆에 붙어 있었다. 유형(dev_type)이
# 비어 있어도 배지를 그려서 생긴 빈 칸이다 — 자동차 품목은 유형이 없다.
_ML = ROOT / 'mobile' / 'lib' / 'screens' / 'model_list_screen.dart'
if _ML.exists():
    _m = _ML.read_text(encoding='utf-8')
    ok('if (devType.trim().isNotEmpty) ...[' in _m,
       '유형이 비어도 배지를 그린다 — 빈 알약이 남는다')
    print('ok — 빈 유형 배지')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
