# PCB 사업부 양식 — 납기 날짜 세 칸 (2026-11-04)
#   python3 backend/tests/test_form_due_cols.py
#
# Min: "결국에 내가 알고 싶은건 이슈사항이 생기면 무슨 이슈사항이 있는지 볼 수
#      있는거랑 납기일이 언제인지" → "이 양식 기준으로 납기 일정 추가하면 될 것 같은데"
#
# 품목정보 실적수량 오른쪽에 고객 요청 납기일 · 출하 변경일 · 제작 완료일.
# 주차별 '계획' 칸이 그 주 납기 수량이다. PCB 만 켠다 (division_columns.DUE_COLS).
import datetime as dt
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


ok(dc.due_cols("pcb") == ["due_date", "due_revised", "made_date"], "PCB 에 납기 칸이 없다")
ok(dc.due_cols("ess") == [] and dc.due_cols("semiconductor") == [], "다른 사업부에도 납기 칸이 켜졌다")
keys = [c["key"] for c in dc.columns_for("pcb")["columns"]]
ok(keys[-3:] == ["due_date", "due_revised", "made_date"], "납기 칸이 실적수량 뒤가 아니다: %r" % keys)

rows = [{"owner": "LAM JABIL", "part_number": "LJ00032", "name": "710-137424-002", "group": "양산",
         "due_date": "2026-09-04", "due_revised": "2026-11-20", "made_date": "",
         "weekly_plan": {"2026-11": {"W46": {"plan": 300}}}},
        {"owner": "LAM JABIL", "part_number": "LJ00029", "name": "710-082745-003", "group": "양산"}]
blob = dfe.build("pcb", rows, "2026-11", 2)
wb = openpyxl.load_workbook(io.BytesIO(blob))
ws = wb.worksheets[0]
heads = [ws.cell(4, c).value for c in range(1, ws.max_column + 1)]
ok("고객 요청 납기일" in heads and "출하 변경일 (고객 승인)" in heads and "제작 완료일" in heads,
   "양식에 납기 칸 머리글이 없다: %r" % heads)
_c = heads.index("고객 요청 납기일") + 1
ok(isinstance(ws.cell(7, _c).value, dt.datetime) and ws.cell(7, _c).number_format == "yyyy-mm-dd",
   "납기일이 날짜로 안 들어간다: %r" % ws.cell(7, _c).value)

got = dfi.parse_workbook(openpyxl.load_workbook(io.BytesIO(blob), data_only=True), "pcb")
it = {x["part_number"]: x for x in got["items"]}
ok(it["LJ00032"].get("due_date") == "2026-09-04" and it["LJ00032"].get("due_revised") == "2026-11-20",
   "내려받은 납기가 되돌아 안 읽힌다: %r" % it["LJ00032"])
ok(it["LJ00032"]["owner"] == "LAM JABIL", "'(고객사 승인)' 머리글이 고객사 칸으로 잡혔다")
ok(it["LJ00029"].get("due_date") == "", "빈 납기 칸이 빈 글자로 안 넘어온다 (지운 날짜를 못 지운다)")
ok(it["LJ00032"]["weeks"].get("W46", {}).get("plan") == 300, "주차 계획(납기 수량)이 깨졌다")
ok(not got["warnings"], "경고가 났다: %r" % got["warnings"])

# 이력 글자 · 틀린 글자
ws2 = wb.worksheets[0]
_r = heads.index("출하 변경일 (고객 승인)") + 1
ws2.cell(7, _r).value = "10/22->10/27\n->11/6"
ws2.cell(8, _c).value = "긴급"
buf = io.BytesIO(); wb.save(buf)
g2 = dfi.parse_workbook(openpyxl.load_workbook(io.BytesIO(buf.getvalue()), data_only=True), "pcb")
i2 = {x["part_number"]: x for x in g2["items"]}
ok(i2["LJ00032"]["due_revised"].endswith("-11-06"), "이력 글자에서 마지막 날짜를 못 읽는다: %r" % i2["LJ00032"])
ok(i2["LJ00029"]["due_date"] == "" and any("긴급" in w for w in g2["warnings"]),
   "날짜 아닌 글자를 경고 없이 넣었다: %r" % g2["warnings"])

# 다른 사업부는 '납기' 머리글이 있어도 안 읽는다
g3 = dfi.parse_workbook(openpyxl.load_workbook(io.BytesIO(blob), data_only=True), "ess")
ok(all("due_date" not in x for x in g3["items"]), "ESS 로 읽었는데 납기 칸을 읽었다")

# 서버 반영 · 앱 상세
SRC = (ROOT / "main.py").read_text(encoding="utf-8")
_ap = SRC[SRC.find("def admin_division_form_apply"):]
_ap = _ap[:_ap.find("\n@app.", 10)]
ok('for _dk in ("due_date", "due_revised", "made_date"):' in _ap and 'm[_dk] = it[_dk] or ""' in _ap,
   "양식 반영이 납기 날짜를 안 담는다")
ok('"due_date", "due_revised", "made_date")}' in SRC, "모델 상세에 납기 날짜가 안 나간다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — PCB 양식 납기 세 칸 (왕복 · 이력 글자 · 다른 사업부 안 건드림)")
