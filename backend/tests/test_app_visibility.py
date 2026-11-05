# admin 에서 끈 사업부는 '앱에서만' 사라진다 (2026-10-27).
#
# Min: "admin v2에 자동차사업부를 숨김 처리를 하면 admin v2에는 멀쩡하게
#      보이고 flutter app에서는 그 사업부가 통채로 안 보이게끔"
#
# 두 가지를 같이 지켜야 한다.
#   1) 앱이 보는 목록(/divisions)에서 빠진다
#   2) admin 이 보는 목록에는 그대로 남는다 — 숨긴 사업부도 자료는 올려야 한다
# 하나만 지키면 쓸모가 없거나(둘 다 보임) 일을 못 하게 된다(둘 다 사라짐).
import ast
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

bad = []


def ok(cond, why):
    if not cond:
        bad.append(why)


# ── 1. 저장하는 쪽 — /data 에 쌓이고, 깨져도 사업부가 안 사라진다
import division_visibility as dv   # noqa: E402

ok(str(dv.FILE).endswith("division_app_hidden.json"), "담는 파일 이름이 다르다")
ok("DATA_DIR" in io.open(os.path.join(HERE, "..", "division_visibility.py"),
                         encoding="utf-8").read(),
   "/data 가 아니라 이미지 안에 적는다 — 배포하면 숨긴 게 되살아난다")

# 파일이 없을 때 (운영 첫 날) 전부 보임이어야 한다
if not dv.FILE.exists():
    ok(dv.hidden_set() == set(), "파일이 없는데 뭔가 숨겨져 있다")
    ok(not dv.is_hidden("automotive"), "파일이 없는데 숨김으로 읽힌다")

src = io.open(os.path.join(HERE, "..", "main.py"), encoding="utf-8").read()
tree = ast.parse(src)


def fn(name):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return ast.unparse(n)
    return ""


# ── 2. 앱이 보는 목록에서 빠진다
pub = fn("list_divisions")
ok(pub, "/divisions 가 없다")
ok("_dvis.hidden_set()" in pub,
   "/divisions 가 숨김 목록을 안 본다 — 앱에서 안 사라진다")

# ── 3. admin 이 보는 목록에는 남는다
adm = fn("admin_config_divisions")
ok(adm, "/admin/config/divisions 가 없다")
ok("hidden" not in adm,
   "admin 목록에서도 빠진다 — 숨긴 사업부에 자료를 못 올리게 된다")

# ── 4. 켜고 끄는 창구
get = fn("admin_division_app_visibility")
ok(get, "admin 용 조회 창구가 없다")
ok("app_visible" in get, "조회 결과에 켜짐/꺼짐이 없다")
ok("visible_only=True" in get, "숨김 화면에 안 쓰는 사업부까지 뜬다")

post = fn("admin_set_division_app_visibility")
ok(post, "저장 창구가 없다")
ok("get_admin_session" in post, "아무나 사업부를 숨길 수 있다")
ok("모르는 사업부입니다" in post,
   "오타로 적은 이름을 그냥 받는다 — 숨겼다고 생각했는데 안 숨겨진다")
ok("_dvis.replace(" in post, "목록을 통째로 갈아 끼우지 않는다")

# ── 5. 앱이 '바뀌었다' 를 알아챈다
ok('"division_app_hidden.json"' in src,
   "자료 버전에 안 넣었다 — 앱이 다음 날까지 옛 목록을 쓴다")

# ── 6. 홈 관리가 '앱에 보이나' 를 같이 내려준다
rows = fn("_home_division_rows")
ok(rows, "_home_division_rows 가 없다")
ok("_dvis.hidden_set()" in rows, "홈 관리 줄에 앱 노출 상태가 안 실린다")
ok("'app_visible'" in rows, "줄에 app_visible 이 없다 — 화면이 못 그린다")

# ── 7. admin 화면 — 홈 관리 안의 카드다 (2026-10-27)
#
#      처음에는 사이드바에 메뉴를 하나 세웠는데, 홈 관리가 이미
#      '앱 홈에 뜨는 것' 을 다루고 오른쪽에 앱 홈 미리보기가 붙어 있다.
#      거기 두면 끄는 순간 미리보기에서 사라지는 게 보인다 — 저장하기
#      전에 결과를 눈으로 본다. 메뉴도 안 늘어난다.
html = io.open(os.path.join(HERE, "..", "admin_v2.html"), encoding="utf-8").read()
ok("function appVisCard()" in html, "홈 관리에 '앱에 보이는 사업부' 카드가 없다")
ok("appVisCard() + '</div>'" in html, "카드를 화면에 안 세운다")
ok("function saveAppVis()" in html, "저장하는 길이 없다")
ok("/admin/divisions/app-visibility" in html, "저장 창구를 안 부른다")
ok("function appOffTag(" in html,
   "매출 · 진행현황 표에 '앱 숨김' 꼬리표가 없다 — 왜 앱에 안 뜨는지 모른다")

# ── 8. 앱 홈 미리보기 (2026-10-27)
#
# 숨긴 사업부도 줄은 세우되 **회색 + 취소선 + '숨김' 꼬리표**로 갈라 둔다.
# 아예 빼 버리면 '지금 누가 꺼져 있나' 를 보려고 아래 카드까지 내려가야
# 한다. 대신 진한 줄만 앱에 뜨는 것이라는 게 한눈에 보여야 하고,
# **합계는 진한 줄만** 더해야 한다 — 안 그러면 미리보기 숫자와 실제 앱
# 숫자가 달라진다.
# 2026-10-27 — 조건을 더 넓혔다. 자료가 없는 사업부도 세운다
# (test_home_target_auto 가 그쪽을 지킨다). 여기서는 '숨긴 사업부가
# 빠지지 않는가' 만 본다.
ok("var divs = (_st.divisions || []);" in html,
   "미리보기가 사업부를 걸러낸다 — 숨긴 줄이 빠지면 꺼진 걸 여기서 못 본다")
ok(".ha-mini .r.off .n { color:#B6BECB; text-decoration:line-through" in html,
   "숨긴 줄이 회색으로 안 갈린다 — 앱에 뜨는 것과 구별이 안 된다")
ok("class=\"ha-off\">숨김<" in html, "숨긴 줄에 '숨김' 꼬리표가 없다")
ok("function liveSum(" in html,
   "미리보기 합계가 숨긴 사업부까지 더한다 — 앱 화면과 숫자가 달라진다")
ok("if (r.app_visible !== false) t += Number(r[field] || 0);" in html,
   "liveSum 이 숨긴 사업부를 거르지 않는다")

# 사이드바에 따로 세웠던 메뉴는 거뒀다 — 두 자리에 있으면 어느 쪽이
# 진짜인지 모른다.
ok('data-page="appvis"' not in html, "옛 '앱 노출' 메뉴가 남아 있다")
ok("renderAppVisPage" not in html, "옛 독립 페이지가 남아 있다")

if bad:
    for b in bad:
        print("FAIL:", b)
    raise SystemExit(1)
print("ok test_app_visibility")
