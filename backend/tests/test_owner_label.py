# 고객사형 사업부는 앱에서 '고객사 N개' 로 부른다 (2026-11-04)
#   python3 backend/tests/test_owner_label.py
#
# Min: "ESS, 자동차, 네트워크, PCB는 고객사 00개로 명칭 변경해줘"
#
# 어느 사업부가 고객사형인지는 서버 division_columns.SHAPES 가 정한다.
# 앱의 kCustomerDivisions 가 그것과 어긋나면 양식은 '고객사' 인데 화면은
# '프로젝트' 로 부르는 일이 다시 생긴다.
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import division_columns as dc   # noqa: E402

FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


LIB = ROOT / "mobile" / "lib"
cfg = (LIB / "config" / "owner_label.dart").read_text(encoding="utf-8")
m = re.search(r"kCustomerDivisions\s*=\s*\{([^}]*)\}", cfg)
app = set(re.findall(r"'([a-z_]+)'", m.group(1))) if m else set()
srv = {d for d, shape in dc.SHAPES.items() if dc.FORMS[shape]["owner_label"] == "고객사"}
ok(app == srv, "앱 고객사 사업부 %r 와 서버 %r 가 다르다" % (sorted(app), sorted(srv)))
ok({"ess", "pcb", "network", "automotive"} <= app, "네 사업부가 다 안 들어 있다: %r" % sorted(app))

USES = {
    "components/home/division_grid_card.dart": "ownerLabelOf(divisionId)",
    "screens/home_screen.dart": "ownerLabelOf(d.id)",
    "screens/alert_list_screen.dart": "ownerLabelOf(p.key)",
    "screens/division_projects_screen.dart": "ownerLabelOf(widget.division.id)",
}
for f, needle in USES.items():
    src = (LIB / f).read_text(encoding="utf-8")
    ok(needle in src, "%s 가 사업부별 이름을 안 쓴다" % f)
    ok("config/owner_label.dart" in src, "%s 가 owner_label.dart 를 안 불러온다" % f)

grid = (LIB / "components/home/division_grid_card.dart").read_text(encoding="utf-8")
ok("'프로젝트 $projectCount개'" not in grid, "사업부 카드에 '프로젝트 N개' 가 박혀 있다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — ESS·PCB·네트워크·자동차는 '고객사 N개'")
