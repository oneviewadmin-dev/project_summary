# 전체 현황 목록도 사업부로 접는다 (2026-11-03)
#   python3 backend/tests/test_alert_list_division.py
#
# Min: "전체 사업부 들어가면 여기서도 사업부로 보였으면 좋겠는데..."
#
# 홈 카드는 이미 사업부로 접어 보여주는데(by_kind_div), '정상 1191' 을
# 눌러 들어간 목록만 프로젝트로 늘어놓았다 — Smac 113 · 파워박스 80 ·
# SM 78 … 125줄. 같은 숫자를 눌렀는데 화면마다 다른 것이 나왔다.
#
# 접으면 7줄이다 (PCB 539 · 반도체 238 · 자동차 155 · 네트워크 99 ·
# 블룸 87 · 아리스타 60 · ESS 13).
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = ROOT.parent / 'mobile' / 'lib'
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


if not LIB.exists():
    print('(앱 없음 — 건너뜀)')
    raise SystemExit(0)

# ── 1. 서버가 사업부로 접은 것을 준다 ───────────────────────────
ok('"by_kind_div": by_kind_div' in SRC, '/home/alerts 가 by_kind_div 를 안 준다')
_fn = SRC[SRC.find('def get_home_alerts'):]
_fn = _fn[:_fn.find('\ndef ', 10)]
ok('"projects": 0' in _fn, '사업부 줄에 프로젝트 수가 없다')
ok('row["projects"] += 1' in _fn, '프로젝트 수를 안 센다')
# 접은 줄도 건수가 많은 것부터 — 순서가 매번 바뀌면 못 읽는다
ok('return (-r["count"], r["label"])' in _fn and 'key=_by_count_then_label' in _fn, '사업부 줄 정렬이 바뀌었다')

# ── 2. 앱이 그 값을 받는다 ──────────────────────────────────────
_svc = (LIB / 'services' / 'home_alerts_service.dart').read_text(encoding='utf-8')
ok("j['by_kind_div']" in _svc, '앱이 by_kind_div 를 안 읽는다')
ok("projects: (j['projects'] as num?)?.toInt() ?? 0" in _svc,
   '사업부 줄의 프로젝트 수를 안 읽는다')

# ── 3. 목록 화면이 사업부로 그린다 ──────────────────────────────
_al = (LIB / 'screens' / 'alert_list_screen.dart').read_text(encoding='utf-8')
ok("a.byKindDiv['정상']" in _al, '목록이 사업부로 접은 것을 안 쓴다')
# 서버가 못 줄 때(옛 배포)도 화면이 비면 안 된다
ok("a.byKind['정상']" in _al, '사업부 값이 없을 때 떨어질 자리가 없다')
ok("byKindDiv['정상']?.isNotEmpty == true" in _al,
   '빈 사업부 목록을 그대로 그려서 화면이 빈다')
# 눌렀을 때 사업부 화면으로
ok('DivisionProjectsScreen(division:' in _al, '사업부 줄을 눌러도 사업부로 안 간다')
ok('ProjectOverviewScreen(' in _al, '사업부를 못 찾았을 때 갈 곳이 없다')
ok('DivisionsService.fetchAll()' in _al, '사업부 목록을 안 받아온다')
ok('${ownerLabelOf(p.key)} ${p.projects}곳' in _al, '몇 곳이 모인 건지 안 보여준다')
# 홈 카드와 같은 잣대를 쓰는지 — 한쪽만 바뀌면 또 갈린다
_card = (LIB / 'components' / 'home' / 'status_board_card.dart').read_text(encoding='utf-8')
ok('byKindDiv' in _card, '홈 카드가 사업부로 안 접는다')

# ── 4. 칩은 다섯 개만 ───────────────────────────────────────────
#
# Min: "지금 위에 탭/pill을 정상, 일정지연, 집중관리, 특이사항,
#       PO 대기 로만 보이게 변경햐줘"
#
# '문제' 는 지연+특이사항을 합친 것이고 '전체' 는 거기에 임박까지 더한
# 것이라, 같은 건이 칩 세 개에 겹쳐 세어졌다 — 18 · 18 · 19 가 나란히
# 서서 어느 것이 무엇인지 알 수 없었다.
_chips = [l.strip() for l in _al.splitlines() if '_chip(' in l and 'Widget' not in l]
ok(len(_chips) == 5, '칩이 %d개다 (다섯이어야 한다): %r' % (len(_chips), _chips))
for bad in ("_chip('문제'", "_chip('전체'"):
    ok(bad not in _al, '%s 칩이 남았다' % bad)
for want in ('StatusWords.normal', 'StatusWords.delayed', 'StatusWords.soon',
             'StatusWords.issue', "'PO 대기'"):
    ok(any(want in c for c in _chips), '%s 칩이 없다' % want)
# 순서 — 정상 · 일정 지연 · 집중관리 · 특이사항 · PO 대기
_order = ['StatusWords.normal', 'StatusWords.delayed', 'StatusWords.soon',
          'StatusWords.issue', "'PO 대기'"]
ok(all(w in c for w, c in zip(_order, _chips)),
   '칩 순서가 다르다: %r' % ([c[:40] for c in _chips],))
# 칩에 없는 값으로 들어와도 아무것도 안 눌린 채로 서면 안 된다
ok('_kChips' in _al and '_kChips.contains(want)' in _al,
   '칩에 없는 필터로 들어오면 빈 화면이 된다')
# 홈 카드가 넘기는 값은 전부 칩에 있어야 한다 — 하나라도 없으면 첫 칩으로 떨어진다
_card_keys = ('정상', '지연', '이슈', '임박')
for k in _card_keys:
    ok("'%s'" % k in _al.split('_kChips =')[1].split(';')[0],
       '홈 카드가 넘기는 %s 가 칩에 없다' % k)

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 전체 현황 목록도 사업부로')
