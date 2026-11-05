# 아리스타 프로젝트 — 종류별 묶음 (2026-11-04)
#   python3 backend/tests/test_arista_groups.py
#
# Min: "아리스타는 렉, 시트메탈, hoover table, cdu...말고 또 있나? 일단 그렇게 나눠줘"
#
# 양식 '구분 1'(모델 dev_type)을 그대로 쓴다 — 엑셀에서 고치면 따라온다.
#   렉 → 렉 · 샷시 → 시트메탈 · 캐스팅 → 캐스팅 · 테이블 → Hoover Table · 하드웨어
#   이름에 CDU 가 든 것은 CDU (구분 1 로는 렉)
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import division_columns as dc   # noqa: E402

FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


G = lambda lab, t: dc.customer_group("arista", "arista_x", None, lab, t)
# 2026-11-05 — 묶음은 엑셀 칸이 정한다. 코드 이름 규칙은 처음 한 번 옮겨 적을 때만(seed_group).
ok([x[0] for x in dc.customer_group_order("arista")]
   == ["렉", "시트메탈", "캐스팅", "Hoover Table", "CDU", "하드웨어", "기타", "미분류"], "묶음 순서")
ok(G("Monstro DUT Rack V2", "렉") == ["렉", ""], "렉")
ok(G("Banff", "샷시") == ["시트메탈", ""], "샷시 → 시트메탈")
ok(G("Quartz 4", "캐스팅") == ["캐스팅", ""], "캐스팅")
ok(G("Hoover Vertical Assemble Table", "테이블") == ["Hoover Table", ""], "Hoover")
# CDU 는 구분 1 로는 렉이다 — 처음 옮겨 적을 때 CDU 로 적고, 그 뒤로는 엑셀 '묶음' 칸
ok(dc.seed_group("arista", "arista_x", "CDU Bypass Box") == ["CDU", ""], "CDU 는 렉이 아니라 CDU")
ok(dc.customer_group("arista", "arista_x", ["CDU", ""], "CDU Bypass Box", "렉") == ["CDU", ""],
   "적어 둔 CDU 가 구분 1 에 졌다")
ok(dc.seed_group("arista", "arista_x", "Banff") is None, "구분 1 로 갈리는 것까지 옮겨 적는다")
ok(G("Banff", "새구분") == ["새구분", ""], "처음 보는 구분이 기타로 갔다 (그 말이 곧 묶음)")
ok(G("Denali", "하드웨어") == ["하드웨어", ""], "하드웨어")
ok(G("Brand New", "") == ["미분류", ""], "구분이 없으면 미분류 (짐작하지 않는다)")
ok(dc.group_col("arista")["header"] == "묶음" and dc.group_col("pcb")["header"] == "국내/해외",
   "아리스타는 '묶음', PCB 는 '국내/해외' 칸")
# PCB 는 그대로
ok(dc.customer_group("pcb", "pcb_lam_jabil", ["해외", ""], "LAM JABIL", "") == ["해외", "Lam"], "PCB 가 깨졌다")

SRC = (ROOT / "main.py").read_text(encoding="utf-8")
_ld = SRC[SRC.find("def list_divisions"):]
_ld = _ld[:_ld.find("\n@app.", 10)]
ok("_ptype.get(p.get(\"id\"))" in _ld and 'get("dev_type")' in _ld, "/divisions 가 모델 구분으로 안 묶는다")
SCR = (ROOT.parent / "mobile/lib/screens/division_projects_screen.dart").read_text(encoding="utf-8")
ok("'종류별'" in SCR, "아리스타 목록 위에 '국내 / 해외' 가 뜬다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — 아리스타: 렉 · 시트메탈 · 캐스팅 · Hoover Table · CDU · 하드웨어")
