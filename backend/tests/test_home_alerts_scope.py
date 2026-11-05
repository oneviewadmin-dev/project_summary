# 홈 '전체 현황' 은 반도체사업부만 센다
#   python3 backend/tests/test_home_alerts_scope.py
#
# 카드에는 '(반도체 기준)' 이라고 적혀 있는데 서버는 전 사업부를 세고
# 있었다. 적힌 것과 세는 것이 다르면 그 숫자는 아무도 못 믿는다.
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SRC = (ROOT / 'main.py').read_text(encoding='utf-8')
CARD = (ROOT.parent / 'mobile' / 'lib' / 'components' / 'home'
        / 'status_board_card.dart').read_text(encoding='utf-8')
ok = 0


def t(name, cond):
    global ok
    print(("  ok  " if cond else "  FAIL") + "  " + name)
    if not cond:
        raise SystemExit(1)
    ok += 1


fn = None
for n in ast.parse(SRC).body:
    if isinstance(n, ast.FunctionDef) and n.name == 'get_home_alerts':
        fn = n
assert fn is not None, 'get_home_alerts 가 없다'
src = ast.get_source_segment(SRC, fn)

args = {a.arg for a in fn.args.args}
t("division 인자가 있다", 'division' in args)

# 기본값이 semiconductor
defaults = dict(zip([a.arg for a in fn.args.args][-len(fn.args.defaults):],
                    fn.args.defaults))
d = defaults.get('division')
t("기본값이 반도체", isinstance(d, ast.Constant) and d.value == 'semiconductor')

t("사업부로 프로젝트를 좁힌다", '_cl.get_projects(div' in src)
t("목록에 없으면 뺀다", 'if pk not in visible' in src)
t("사업부를 지정하면 빈 목록이어도 전사로 안 샌다", 'scoped' in src)

# 카드가 말하는 범위와 같아야 한다
# 2026-11-02 부터 앱이 division= 를 비워 부른다 — 전 사업부다.
# 서버 기본값은 'semiconductor' 로 남아 있다 (위 검사). 그건 아직
# 안 올린 앱을 위한 것이고, 카드에 적히는 말은 지금 세는 범위다.
t("카드에 '(전 사업부)' 라고 적혀 있다", '(전 사업부)' in CARD)

# 설정상 반도체가 전사보다 적어야 의미가 있다 (같으면 필터가 무의미)
import config_loader as _cl  # noqa: E402
try:
    allp = {p.get("id") for p in _cl.get_projects(visible_only=True)}
    semi = {p.get("id") for p in _cl.get_projects("semiconductor", visible_only=True)}
    t("반도체는 전사의 일부다", semi and semi < allp)
except Exception as e:
    print("  skip  설정을 못 읽음: %s" % e)

print(f"전부 통과 ({ok}개)")

# ── 사업부로 묶은 내역 (2026-11-03) ──────────────────────────────
# Min: "이거 지금 사진에 보이는거 사업부별로 나눠줘"
#
# 프로젝트로 줄을 세우면 121곳이다. '모두 보기 (121곳)' 를 눌러도
# Smac · 파워박스 · SM … 이 끝없이 늘어설 뿐이라 어디가 문제인지 한눈에
# 안 들어온다. 사업부는 여섯이다.
_a = SRC.find('def get_home_alerts')
_b = SRC[_a:SRC.find('\n@app.', _a)]
t("사업부로 묶은 내역을 같이 준다", '"by_kind_div": by_kind_div' in _b)
t("프로젝트 내역은 그대로 둔다 (목록 화면이 쓴다)", '"by_kind": by_kind' in _b)
t("프로젝트에서 사업부를 찾는다", 'derive_division_from_project' in _b)
# 사업부를 못 찾은 프로젝트를 버리면 합이 조용히 빈다
t("사업부를 못 찾아도 안 버린다", "'_etc', '기타'" in _b or '"_etc", "기타"' in _b)
t("사업부 줄에 프로젝트 수도 담는다", '"projects": 0' in _b)

_D = ROOT.parent / 'mobile' / 'lib'
_svc = (_D / 'services' / 'home_alerts_service.dart').read_text(encoding='utf-8')
_card = (_D / 'components' / 'home' / 'status_board_card.dart').read_text(encoding='utf-8')
_home = (_D / 'screens' / 'home_screen.dart').read_text(encoding='utf-8')
t("앱이 사업부 내역을 읽는다", "j['by_kind_div']" in _svc)
t("카드가 사업부 줄을 쓴다", 'widget.alerts.byKindDiv[_key[k]]' in _card)
# 서버가 아직 안 올라간 폰에서 목록이 통째로 비면 안 된다
t("옛 서버면 프로젝트로 돌아간다", 'if (d != null && d.isNotEmpty) return d;' in _card)
# 세는 단위가 다른데 같은 말을 쓰면 숫자가 거짓이 된다
t("줄 단위를 '사업부' 로 적는다", "? '사업부'" in _card and '${_unit}' in _card)
# 줄을 누르면 프로젝트 화면이 아니라 그 사업부로 가야 한다
t("사업부 줄이 사업부 화면으로 간다", '_openStatusRow' in _home)
t("사업부를 못 찾으면 프로젝트로 연다", '_openProject(key, name);' in _home)

print('ok — 사업부로 묶은 전체 현황')
