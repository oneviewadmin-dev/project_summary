# 사업부 양식 '국내/해외' 칸 → 앱 고객사 묶음 (2026-11-04)
#   python3 backend/tests/test_form_region.py
#
# Min: "그냥 그렇게 어렵게 하지 않고 엑셀에 구분을 해두면 매핑하기 더 쉽겠지?"
#
# 고객사를 국내 / 해외(Lam · 아리스타 · 기타)로 옮기는 것은 양식 한 칸이다.
# 코드도 배포도 필요 없다. 엑셀에 안 적힌 고객사만 division_columns 규칙으로.
import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import openpyxl                          # noqa: E402
import division_columns as dc            # noqa: E402
import division_form_export as dfe       # noqa: E402
import division_form_import as dfi       # noqa: E402

FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


P = dc.parse_region
ok(P("국내") == ["국내", ""] and P("해외 · Lam") == ["해외", "Lam"] and P("해외-LAM") == ["해외", "Lam"],
   "국내 / 해외 · Lam 을 못 읽는다")
ok(P("해외") == ["해외", ""] and P("해외 아리스타") == ["해외", "아리스타"], "해외 · 아리스타 / 해외만")
# '해외' 만 적으면 서버가 가른다 (Min: "해외 적으면 알아서 매핑")
G = dc.customer_group
ok(G("pcb", "pcb_lam_venture", ["해외", ""], "LAM VENTURE") == ["해외", "Lam"], "해외 → Lam 을 못 가른다")
ok(G("pcb", "pcb_lam_brand_new", ["해외", ""], "LAM NEWCO") == ["해외", "Lam"], "새 LAM 고객사를 못 가른다")
ok(G("pcb", "pcb_arista", ["해외", ""], "아리스타") == ["해외", "아리스타"], "해외 → 아리스타")
ok(G("pcb", "pcb_kumho_india", ["해외", ""], "KUMHO INDIA") == ["해외", "기타"], "해외 → 기타 (명단)")
ok(G("pcb", "pcb_newco", ["해외", ""], "NewCo") == ["해외", "기타"], "모르는 해외 고객사는 기타")
ok(G("pcb", "pcb_lam_jabil", ["국내", ""], "LAM JABIL") == ["국내", ""], "엑셀에 국내라고 적으면 국내")
ok(dc.REGION_CHOICES == ["국내", "해외"], "양식 고르기가 국내 / 해외 둘이 아니다: %r" % dc.REGION_CHOICES)
ok(P("해외 · 일본") == ["해외", "일본"], "새 묶음(해외 · 일본)을 못 받는다")
ok(P("") is None and P("모름") is None, "빈칸 · 모르는 말이 묶음이 됐다")
ok(dc.region_label(["해외", "Lam"]) == "해외 · Lam" and dc.region_label(["국내", ""]) == "국내", "글자로 되돌리기")
# 엑셀 값이 규칙보다 먼저
ok(dc.customer_group("pcb", "pcb_smac", ["해외", "기타"]) == ["해외", "기타"], "엑셀 값이 규칙을 못 이긴다")
# 2026-11-05 — 엑셀 값이 없으면 짐작하지 않고 미분류 (Min: "이후에 다른 고객사 생기면 어떻게 분류하려고")
ok(dc.customer_group("pcb", "pcb_smac") == ["미분류", ""], "엑셀 값이 없는데 짐작했다")
ok(dc.customer_group_order("pcb", [["해외", "일본"]])[-2:] == [["해외", "일본"], ["미분류", ""]],
   "새 묶음이 순서에 안 붙는다")
ok(dc.group_cell("pcb", ["미분류", ""]) == "", "미분류를 양식에 글자로 적었다")

# 양식 왕복 — PCB 만 칸이 생긴다
rows = [{"owner": "Smac", "part_number": "KH00010", "name": "AI3", "group": "양산", "region": "국내"},
        {"owner": "LAM JABIL", "part_number": "LJ00032", "name": "710-1", "group": "양산", "region": "해외 · Lam"}]
blob = dfe.build("pcb", rows, "2026-11", 2)
ws = openpyxl.load_workbook(io.BytesIO(blob)).worksheets[0]
heads = [ws.cell(4, c).value for c in range(1, ws.max_column + 1)]
ok(heads.index("국내/해외") == heads.index("고객사") + 1, "국내/해외 칸이 고객사 옆이 아니다: %r" % heads)
_dv = [str(d.formula1) for d in ws.data_validations.dataValidation]
ok(any('"국내,해외"' == f for f in _dv), "국내/해외 고르기가 없다: %r" % _dv)
got = dfi.parse_workbook(openpyxl.load_workbook(io.BytesIO(blob), data_only=True), "pcb")
ok([(x["part_number"], x.get("region"), x["group"]) for x in got["items"]]
   == [("KH00010", "국내", "양산"), ("LJ00032", "해외 · Lam", "양산")],
   "국내/해외가 안 읽히거나 구분(양산/개발)과 섞였다: %r" % got["items"])
ess = openpyxl.load_workbook(io.BytesIO(dfe.build("ess", rows, "2026-11", 2))).worksheets[0]
ok("국내/해외" not in [ess.cell(4, c).value for c in range(1, ess.max_column + 1)], "ESS 양식에도 칸이 생겼다")
ari = openpyxl.load_workbook(io.BytesIO(dfe.build("arista", rows, "2026-11", 2))).worksheets[0]
ok("국내/해외" not in [ari.cell(4, c).value for c in range(1, ari.max_column + 1)],
   "아리스타 양식에 국내/해외 칸이 생겼다 (아리스타는 종류로 묶는다)")

SRC = (ROOT / "main.py").read_text(encoding="utf-8")
_ap = SRC[SRC.find("def admin_division_form_apply"):]
_ap = _ap[:_ap.find("\n@app.", 10)]
ok('["customer_group"] = list(best)' in _ap and "_dcol.parse_group(division_id, it.get(\"region\"))" in _ap,
   "양식 반영이 국내/해외를 안 담는다")
_dl = SRC[SRC.find("def admin_division_form_download"):]
_dl = _dl[:_dl.find("\n@app.", 10)]
# 2026-11-05 — 묶음 칸을 사업부마다 (국내/해외 · 고객 묶음) — group_cell 이 big_only 로 적는다
ok('r["region"] = _rg' in _dl and "_dcol.group_cell(division_id" in _dl, "양식 내려받기가 국내/해외 둘 중 하나로 안 채운다")
ok("region_label(grp, big_only=True)" in (ROOT / "division_columns.py").read_text(encoding="utf-8"),
   "묶음 칸에 '해외 · Lam' 처럼 두 단을 적는다")
_ld = SRC[SRC.find("def list_divisions"):]
_ld = _ld[:_ld.find("\n@app.", 10)]
ok("_cgroup.get(p.get(\"id\"))" in _ld, "/divisions 가 엑셀 값을 안 쓴다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — 양식 '국내/해외' 칸 → 앱 묶음 (엑셀 값 먼저 · 없으면 규칙)")
