# 이슈 진행 / 해결 — 모든 사업부 공통 (2026-11-04)
#   python3 backend/tests/test_issue_status.py
#
# Min: "이걸로 적었는데 만약에 이슈 지울려면 어떻게 판단하려고 하냐"
#      → admin 은 전부 잠그고, 이슈는 양식 '상태' 칸(진행/해결)으로 닫는다.
#        같은 이슈 = 프로젝트 + 품번 + 내용 (띄어쓰기·기호 무시).
#
# 못 박는 것
#   · '해결' 로 올리면 열린 줄이 빠지고 기록(issues_closed)에 남는다
#   · 줄을 지워서 올리는 것은 해결이 아니다 (아무것도 안 건드린다)
#   · 닫힌 이슈를 '진행' 으로 다시 올려도 안 열린다
#   · 띄어쓰기·기호·날짜만 다른 줄은 같은 이슈 — 두 번 안 들어간다
#   · 내려받는 양식에 열린 이슈가 '진행' 으로 채워지고, 그대로 올리면 바뀌는 게 없다
import copy
import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import openpyxl                          # noqa: E402
import issue_status as iss               # noqa: E402
import division_form_export as dfe       # noqa: E402
import division_form_import as dfi       # noqa: E402

FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


T = "2026-11-04"

# ── 상태 칸 읽기
ok(iss.status_of("") == "진행", "빈 상태가 진행이 아니다")
ok(iss.status_of("해결") == "해결" and iss.status_of(" 해결됨 ") == "해결", "해결을 못 읽는다")
ok(iss.status_of("완료") == "해결", "완료를 해결로 안 친다")
ok(iss.status_of("진행") == "진행" and iss.status_of("헤결") == "진행", "모르는 말이 해결이 됐다")

# ── 같은 이슈 판정 — 띄어쓰기 · 기호 · 대소문자 무시
ok(iss.norm("리플로우 불량 (재작업)") == iss.norm("리플로우불량-재작업"), "띄어쓰기·기호를 못 무시한다")
ok(iss.norm("PCB Warpage") == iss.norm("pcb  warpage."), "대소문자를 못 무시한다")
ok(iss.split_line("[2026-10-01] 자재 입고 지연") == ("2026-10-01", "자재 입고 지연"), "줄 나누기")

# ── 모델 이슈
m = {"id": "KH00010", "issues": "[2026-10-01] 자재 입고 지연\n리플로우 불량"}
r = iss.apply_to_model(m, {"text": "자재입고 지연", "date": "2026-11-01"}, T)
ok(r == iss.DUP and m["issues"].count("\n") == 1, "날짜·띄어쓰기만 다른 줄이 또 들어갔다")

r = iss.apply_to_model(m, {"text": "새 이슈", "date": T}, T)
ok(r == iss.ADDED and m["issues"].endswith("[2026-11-04] 새 이슈"), "새 이슈가 안 붙는다")

before = copy.deepcopy(m)
r = iss.apply_to_model(m, {"text": "자재 입고 지연", "status": "해결"}, T, dry=True)
ok(r == iss.CLOSED_NOW and m == before, "미리보기(dry)가 자료를 바꿨다")

r = iss.apply_to_model(m, {"text": "자재 입고 지연", "status": "해결"}, T, "a.xlsx")
ok(r == iss.CLOSED_NOW, "해결이 안 된다: %r" % r)
ok("자재 입고 지연" not in m["issues"], "해결한 줄이 열린 이슈에 남았다")
ok(m["issues_closed"] == [{"date": "2026-10-01", "text": "자재 입고 지연",
                           "closed": T, "file": "a.xlsx"}],
   "닫힌 기록이 이상하다: %r" % m.get("issues_closed"))

r = iss.apply_to_model(m, {"text": "자재 입고 지연", "status": "진행"}, T)
ok(r == iss.NOT_REOPENED and "자재 입고 지연" not in m["issues"], "닫힌 이슈가 다시 열렸다")
r = iss.apply_to_model(m, {"text": "자재 입고 지연", "status": "해결"}, T)
ok(r == iss.ALREADY_CLOSED and len(m["issues_closed"]) == 1, "이미 닫힌 것을 또 기록했다")

r = iss.apply_to_model(m, {"text": "처음부터 끝난 일", "status": "해결"}, T)
ok(r == iss.CLOSED_NEW and "처음부터" not in m["issues"], "해결로 적힌 새 줄이 열렸다")

# 칸 안 줄바꿈은 한 줄로 — 모델 이슈는 한 줄이 이슈 하나
m2 = {"issues": ""}
iss.apply_to_model(m2, {"text": "A 불량\n재작업 중", "date": T}, T)
ok(m2["issues"] == "[2026-11-04] A 불량 / 재작업 중", "줄바꿈이 이슈를 둘로 쪼갰다: %r" % m2["issues"])
r = iss.apply_to_model(m2, {"text": "A 불량 / 재작업 중", "status": "해결"}, T)
ok(r == iss.CLOSED_NOW and m2["issues"] == "", "한 줄로 합친 이슈를 못 닫는다")

# ── 프로젝트 이슈 — 품번까지 같아야 같은 이슈
p = {"issues": [{"date": "2026-10-02", "part_number": "", "text": "고객 승인 대기"}]}
ok(iss.apply_to_project(p, {"text": "고객 승인대기", "part_number": ""}, T) == iss.DUP, "프로젝트 이슈 중복")
ok(iss.apply_to_project(p, {"text": "고객 승인 대기", "part_number": "X1"}, T) == iss.ADDED,
   "품번이 다른데 같은 이슈로 봤다")
ok(iss.apply_to_project(p, {"text": "고객 승인 대기", "part_number": "", "status": "해결"}, T)
   == iss.CLOSED_NOW, "프로젝트 이슈를 못 닫는다")
ok([x["part_number"] for x in p["issues"]] == ["X1"], "엉뚱한 프로젝트 이슈가 닫혔다")
ok(iss.apply_to_project(p, {"text": "고객 승인 대기", "part_number": ""}, T) == iss.NOT_REOPENED,
   "닫힌 프로젝트 이슈가 다시 열렸다")

# ── 양식 왕복 — 열린 이슈가 '진행' 으로 채워지고, 그대로 올리면 아무것도 안 바뀐다
proj = {"models": [{"id": "KH00010", "part_number": "KH00010",
                    "issues": "[2026-10-01] 자재 입고 지연"}],
        "issues": [{"date": "", "part_number": "", "text": "고객 승인 대기"}]}
open_rows = iss.open_rows("Smac", proj)
ok([(x["part_number"], x["text"], x["status"]) for x in open_rows]
   == [("KH00010", "자재 입고 지연", "진행"), ("", "고객 승인 대기", "진행")],
   "열린 이슈 채우기가 이상하다: %r" % open_rows)

rows = [{"owner": "Smac", "part_number": "KH00010", "name": "AI3", "group": "양산"}]
blob = dfe.build("pcb", rows, "2026-11", 2, issues=open_rows)
wb = openpyxl.load_workbook(io.BytesIO(blob))
ws = wb["이슈사항"]
ok(ws.cell(4, 10).value == "상태", "이슈사항 시트에 상태 칸(J4)이 없다: %r" % ws.cell(4, 10).value)
ok(ws.cell(5, 10).value == "진행" and ws.cell(5, 6).value == "자재 입고 지연", "열린 이슈가 안 채워졌다")
_dv = [str(d.formula1) for d in ws.data_validations.dataValidation]
ok(any("진행" in f and "해결" in f for f in _dv), "상태 칸에 진행/해결 고르기가 없다: %r" % _dv)

# 상태 칸 머리글 위치와 검증 범위가 같아야 한다 (J)
_rng = [str(d.sqref) for d in ws.data_validations.dataValidation]
ok(any(x.startswith("J5:") for x in _rng), "진행/해결 고르기가 상태 칸이 아닌 곳에 걸렸다: %r" % _rng)

got = dfi.parse_workbook(openpyxl.load_workbook(io.BytesIO(blob), data_only=True), "pcb")
ok([(x["part_number"], x["text"], x["status"]) for x in got["issues"]]
   == [("KH00010", "자재 입고 지연", "진행"), ("", "고객 승인 대기", "진행")],
   "내려받은 이슈가 되돌아 안 읽힌다: %r" % got["issues"])
p2 = copy.deepcopy(proj)
res = [iss.apply_to_model(p2["models"][0], got["issues"][0], T),
       iss.apply_to_project(p2, got["issues"][1], T)]
ok(res == [iss.DUP, iss.DUP] and p2 == proj, "받은 양식을 그대로 올렸는데 바뀌었다: %r" % res)

# 해결로 바꿔 올리면 닫힌다
ws.cell(5, 10).value = "해결"
buf = io.BytesIO()
wb.save(buf)
g2 = dfi.parse_workbook(openpyxl.load_workbook(io.BytesIO(buf.getvalue()), data_only=True), "pcb")
ok(iss.apply_to_model(p2["models"][0], g2["issues"][0], T) == iss.CLOSED_NOW
   and p2["models"][0]["issues"] == "", "양식에서 '해결' 로 바꿔도 안 닫힌다")

# 상태 칸이 없는 옛 양식도 읽힌다 (진행으로)
old = openpyxl.Workbook()
o = old.active
o.title = "이슈사항"
for c, v in enumerate(["NO", "고객사", "품번", "발생일", "이슈사항"], start=2):
    o.cell(4, c, v)
o.cell(5, 2, 1), o.cell(5, 3, "Smac"), o.cell(5, 6, "옛 양식 이슈")
_issues, _w = dfi.parse_issues(o)
ok([(x["text"], iss.status_of(x["status"])) for x in _issues] == [("옛 양식 이슈", "진행")],
   "상태 칸 없는 옛 양식을 못 읽는다: %r" % _issues)

# ── main.py 연결
SRC = (ROOT / "main.py").read_text(encoding="utf-8")
_dl = SRC[SRC.find("def admin_division_form_download"):]
_dl = _dl[:_dl.find("\n@app.", 10)]
ok("_iss.open_rows(" in _dl and "issues=open_issues" in _dl, "양식 받기가 열린 이슈를 안 채운다")
_ap = SRC[SRC.find("def admin_division_form_apply"):]
_ap = _ap[:_ap.find("\n@app.", 10)]
ok("_df_issue_apply(data, pid, ix" in _ap and "issue_summary" in _ap, "반영이 진행/해결을 안 쓴다")
ok('m["issues"] = (old + "\\n" + line)' not in _ap, "옛 이슈 덧붙이기 코드가 남아 있다")
_pv = SRC[SRC.find("def admin_division_form_preview"):]
_pv = _pv[:_pv.find("\n@app.", 10)]
ok("dry=True" in _pv and "issue_summary" in _pv, "미리보기가 결과를 안 보여 준다")
HTML = (ROOT / "admin_v2.html").read_text(encoding="utf-8")
ok("window._xlIssueSummary = function" in HTML and HTML.count("_xlIssueSummary(") >= 2,
   "admin 화면이 이슈 진행/해결을 안 보여 준다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
# ── 이슈 분류 · 조치사항 · 담당자 (2026-11-04) — 왕복되고, 조치가 바뀌어도 같은 이슈
m3 = {"id": "P1", "part_number": "P1", "issues": ""}
iss.apply_to_model(m3, {"text": "도금 약품 소진", "category": "자재", "action": "대체 약품 검토",
                        "person": "홍길동"}, T)
ok(m3["issue_meta"][iss.norm("도금 약품 소진")] == {"category": "자재", "action": "대체 약품 검토",
                                                 "person": "홍길동"}, "조치사항이 안 남는다: %r" % m3.get("issue_meta"))
r = iss.apply_to_model(m3, {"text": "도금 약품 소진", "action": "11/6 출하로 변경"}, T)
ok(r == iss.DUP and m3["issues"].count("도금") == 1, "조치만 바뀐 줄이 새 이슈가 됐다")
ok(m3["issue_meta"][iss.norm("도금 약품 소진")]["action"] == "11/6 출하로 변경", "바뀐 조치가 안 들어간다")
_or = iss.open_rows("Smac", {"models": [m3]})
ok(_or and _or[0].get("action") == "11/6 출하로 변경" and _or[0].get("person") == "홍길동",
   "내려받는 양식에 조치 · 담당자가 안 채워진다: %r" % _or)
b2 = dfe.build("pcb", rows, "2026-11", 2, issues=_or)
g4 = dfi.parse_workbook(openpyxl.load_workbook(io.BytesIO(b2), data_only=True), "pcb")
ok([(x["text"], x["category"], x["action"], x["person"]) for x in g4["issues"]]
   == [("도금 약품 소진", "자재", "11/6 출하로 변경", "홍길동")], "이슈 분류 · 조치 · 담당자가 왕복 안 된다: %r" % g4["issues"])
iss.apply_to_model(m3, {"text": "도금 약품 소진", "status": "해결"}, T)
ok(m3["issues_closed"][-1].get("action") == "11/6 출하로 변경" and not m3.get("issue_meta"),
   "닫힌 기록에 조치가 안 남는다")

print("ok — 이슈 진행/해결 (내용으로 맞춤 · 지운 줄은 그대로 · 닫힌 건 안 열림)")
