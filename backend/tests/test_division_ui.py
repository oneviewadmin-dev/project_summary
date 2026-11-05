# 사업부별 숨김/보임 스위치는 한 곳에 있어야 한다 (2026-10-27).
#
# Min: "각 사업부 별 숨김 보임 처리"
#
# 전에는 네 곳에 흩어져 있었다 — 앱의 kDivisionBoardOn · kProjectBoardOn,
# 앱 화면의 _boardProjects, admin 의 _DAILY_DIVISIONS. 그래서 PCB 를 켤 때
# 한 곳을 빠뜨려 프로젝트 보드가 통째로 안 뜬 적이 있고, 앱 쪽 둘은
# 스위치 하나 올리려고 앱을 새로 배포해야 했다.
#
# 이 검사는 두 가지를 지킨다.
#   1) 서버가 한 벌로 알려준다 (/divisions/ui)
#   2) 그 값이 **지금 앱이 하는 것과 같다** — 옮기면서 화면이 달라지면 안 된다
import ast
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import division_columns as dcol   # noqa: E402

bad = []


def ok(cond, why):
    if not cond:
        bad.append(why)


# ── 1. 스위치 묶음이 있고, 사업부마다 같은 열쇠를 쓴다
need = {"division_board", "project_board", "project_board_keys",
        "daily_upload", "revenue_excel"}
allui = dcol.all_ui()
ok(allui, "all_ui() 가 비었다")
for d, u in allui.items():
    ok(set(u) == need, "%s 의 스위치 열쇠가 다르다 (%s)" % (d, sorted(u)))

# ── 2. 서버가 로그인 없이 내준다 (앱이 읽어야 한다)
src = io.open(os.path.join(HERE, "..", "main.py"), encoding="utf-8").read()
tree = ast.parse(src)
fn = None
for n in ast.walk(tree):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "divisions_ui":
        fn = n
ok(fn is not None, "/divisions/ui 가 없다")
if fn:
    body = ast.unparse(fn)
    ok("get_admin_session" not in body,
       "/divisions/ui 에 관리자 로그인이 걸려 있다 — 앱이 못 읽는다")
    ok("all_ui()" in body, "/divisions/ui 가 all_ui() 를 안 쓴다")
    ok("no-store" in body, "캐시를 막지 않았다 — 스위치를 올려도 옛 값이 온다")

# ── 3. 옮기면서 화면이 달라지지 않았는가.
#      앱이 지금 쓰는 목록과 글자 하나까지 맞춘다.
dart_cfg = io.open(os.path.join(HERE, "..", "..", "mobile", "lib", "config",
                                "app_config.dart"), encoding="utf-8").read()
dart_scr = io.open(os.path.join(HERE, "..", "..", "mobile", "lib", "screens",
                                "project_overview_screen.dart"),
                   encoding="utf-8").read()


def dart_set(src_text, name):
    """dart 의 `… NAME = { … };` 안의 글자들.

    이름만 찾으면 위쪽 주석에 적힌 같은 이름에 걸린다 (실제로 한 번
    걸렸다 — kProjectBoardOn 주석을 짚고 kDivisionBoardOn 의 괄호를 읽었다).
    그래서 '= {' 가 붙은 자리만 본다.
    """
    i = -1
    for cand in (name + " = {", name + " ={"):
        i = src_text.find(cand)
        if i >= 0:
            break
    if i < 0:
        return None
    a = src_text.index("{", i)
    b = src_text.index("}", a)
    # 주석은 **줄 단위**로 먼저 떼어낸다. 쉼표로 먼저 쪼개면 주석 뒤에
    # 줄바꿈으로 이어지는 값이 통째로 사라진다 ('// ESS' 다음 줄의 'ess_').
    body = []
    for line in src_text[a + 1:b].splitlines():
        body.append(line.split("//")[0])
    out = set()
    for part in ",".join(body).split(","):
        part = part.strip()
        if part.startswith("'") and part.endswith("'"):
            out.add(part[1:-1])
    return out


# 사업부 화면 보드
want_div = dart_set(dart_cfg, "kDivisionBoardOn")
got_div = {d for d, u in allui.items() if u["division_board"]}
ok(want_div == got_div,
   "사업부 화면 보드가 앱과 다르다 — 앱 %s / 설정 %s" % (want_div, got_div))

# 프로젝트 보드 — 앱은 키 목록 셋을 합쳐서 본다
want_proj = (dart_set(dart_cfg, "kProjectBoardOn") or set()) | \
            (dart_set(dart_scr, "_boardProjects") or set()) | {"auto_"}
got_proj = set()
for u in allui.values():
    got_proj |= set(u["project_board_keys"])
ok(want_proj == got_proj,
   "프로젝트 보드 키가 앱과 다르다 — 앱에만 %s / 설정에만 %s"
   % (sorted(want_proj - got_proj), sorted(got_proj - want_proj)))

# 일 보고 칸 — admin 의 기본값과 같아야 한다
html = io.open(os.path.join(HERE, "..", "admin_v2.html"), encoding="utf-8").read()
ok("window._DAILY_DIVISIONS = ['ess', 'bloom'];" in html,
   "admin 의 기본 일 보고 목록이 바뀌었다 — 설정과 같이 고쳐야 한다")
got_daily = {d for d, u in allui.items() if u["daily_upload"]}
ok(got_daily == {"ess", "bloom"},
   "일 보고 사업부가 admin 기본값과 다르다 (%s)" % got_daily)
ok("window._divUiLoad" in html, "admin 이 /divisions/ui 를 안 받아 간다")

# ── 4. board_on 이 접두사와 정확한 키를 둘 다 본다
ok(dcol.board_on("pcb", "pcb_smac"), "접두사(pcb_)로 안 켜진다")
ok(dcol.board_on("semiconductor", "chamber"), "정확한 키(chamber)로 안 켜진다")
ok(not dcol.board_on("network", "net_x"), "꺼 둔 사업부가 켜진다")
ok(not dcol.board_on("semiconductor", "pcb_smac"),
   "남의 사업부 키로 켜진다")

if bad:
    for b in bad:
        print("FAIL:", b)
    raise SystemExit(1)
print("ok test_division_ui · 사업부 %d곳" % len(allui))
