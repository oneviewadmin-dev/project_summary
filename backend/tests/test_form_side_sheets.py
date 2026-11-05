# 내려받는 사업부 양식에 이슈사항 · 용어 시트가 있다 (2026-11-04)
#   python3 backend/tests/test_form_side_sheets.py
#
# Min: "파일에 이슈사항이랑 용어는 어디갔냐?"
#
# 처음 양식은 다섯 장인데, 양식 받기로 내려주는 파일은 품목정보 한 장뿐이었다.
# 올리는 쪽은 두 시트를 다 읽는데 적을 자리가 없었다.
# 이 테스트는 '내려받은 것을 그대로 다시 올리면 읽힌다' 를 못 박는다.
import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import openpyxl                          # noqa: E402
import division_form_export as dfe       # noqa: E402
import division_form_import as dfi       # noqa: E402

FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


rows = [{"owner": "Smac", "part_number": "KH00010", "name": "AI3", "group": "양산"}]
terms = [{"short": "MPS", "full": "Master Production Schedule",
          "ko": "주 생산계획", "note": "주별 업데이트"}]


def read(blob):
    return dfi.parse_workbook(openpyxl.load_workbook(io.BytesIO(blob), data_only=True), "pcb")


blob = dfe.build("pcb", rows, "2026-11", 2, terms=terms)
wb = openpyxl.load_workbook(io.BytesIO(blob))
ok("이슈사항" in wb.sheetnames, "이슈사항 시트가 없다")
ok("용어" in wb.sheetnames, "용어 시트가 없다")
ok(wb.sheetnames[0].endswith("품목정보"), "품목정보가 첫 시트가 아니다: %r" % wb.sheetnames)

# 처음 양식과 같은 모양 — 읽는 쪽이 4행 'NO' 로 표를 찾는다
for sn in ("이슈사항", "용어"):
    ok(wb[sn].cell(4, 2).value == "NO", "%s 머리글이 B4 의 NO 가 아니다" % sn)

got = read(blob)
ok(len(got["items"]) == 1, "품목을 못 읽는다 (시트가 늘어서 헷갈렸나)")
ok(got["issues"] == [], "빈 이슈사항 시트에서 이슈가 나왔다 — 예시 줄을 넣었나")
ok([t["short"] for t in got.get("terms") or []] == ["MPS"],
   "등록된 용어가 되돌아 읽히지 않는다: %r" % (got.get("terms"),))
ok(not got["warnings"], "경고가 났다: %r" % got["warnings"])

# 이슈 한 줄 적어서 올리면 들어간다
ws = wb["이슈사항"]
ws["C5"], ws["D5"], ws["E5"], ws["F5"] = "Smac", "KH00010", "2026-11-04", "리플로우 불량"
buf = io.BytesIO()
wb.save(buf)
g2 = read(buf.getvalue())
ok([(x["owner"], x["part_number"], x["text"]) for x in g2["issues"]]
   == [("Smac", "KH00010", "리플로우 불량")], "적은 이슈가 안 읽힌다: %r" % g2["issues"])

# 용어가 없으면 빈 시트 — 빈 시트는 저장된 용어를 지우지 않는다(division_terms.put)
g3 = read(dfe.build("pcb", rows, "2026-11", 2))
ok((g3.get("terms") or []) == [], "용어가 없는데 무언가 읽혔다")

# 내려받기가 등록된 용어를 넘긴다 — 안 넘기면 한 줄만 고쳐 올려도 나머지가 지워진다
SRC = (ROOT / "main.py").read_text(encoding="utf-8")
_dl = SRC[SRC.find("def admin_division_form_download"):]
_dl = _dl[:_dl.find("\n@app.", 10)]
ok("_dterm.get(division_id)" in _dl and "terms=_terms" in _dl,
   "양식 받기가 등록된 용어를 안 채운다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — 양식에 이슈사항 · 용어 시트")
