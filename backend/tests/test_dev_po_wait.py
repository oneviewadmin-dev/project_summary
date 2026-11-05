# 개발 일정 — 새 파일이 정본 · 최종 승인 뒤 1주일 → PO 대기 (2026-11-05)
#   python3 backend/tests/test_dev_po_wait.py
#
# Min: "새로운 파일이 올라가면 기존에 있던 내용 지워지고 최신 내용 기준으로
#       내용 업로드 되어야 하는데"
#      "최종 승인 완료 되면 1주일동안 두고 PO 대기로 넘어가게끔 하고 만약에
#       1주일 전에 양산에 파트넘버가 올라오는거면 그냥 바로 넘어가게끔"
import ast
import pathlib
import re
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / "main.py").read_text(encoding="utf-8")
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


T = ast.parse(SRC)
NS = {"re": re, "date": date}
for n in T.body:
    name = getattr(n, "name", None)
    if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "DEV_PO_WAIT_DAYS" for t in n.targets):
        exec(ast.get_source_segment(SRC, n), NS)
    if name in ("_process_step_done", "_process_step_active", "_process_rolled",
                "_ds_show_notes", "_dev_final_day", "_dev_po_wait"):
        exec(ast.get_source_segment(SRC, n), NS)
wait = NS["_dev_po_wait"]
D = date(2026, 11, 5)


def proc(last):
    return [{"name": "01 PO 접수", "actual": "2026-04-05"},
            dict({"name": "13 최종 승인 완료"}, **last)]


ok(NS["DEV_PO_WAIT_DAYS"] == 7, "기다리는 날이 7일이 아니다")
# 최종 승인 전 — PO 대기 아님
ok(not wait({}, proc({"actual": ""}), D), "최종 승인 전인데 PO 대기다")
# 끝난 지 6일 — 아직 '완료'
ok(not wait({}, proc({"actual": "2026-10-30"}), D), "6일째인데 벌써 PO 대기다")
# 7일 — PO 대기
ok(wait({}, proc({"actual": "2026-10-29"}), D), "7일이 지났는데 PO 대기가 아니다")
# 날짜 없이 '완료' — 처음 본 날부터 센다
_m = {"final_done_seen": "2026-11-03"}
ok(not wait(_m, proc({"actual": "", "status": "완료"}), D), "처음 본 날부터 안 센다")
ok(wait({"final_done_seen": "2026-10-20"}, proc({"actual": "", "status": "완료"}), D),
   "처음 본 날부터 7일이 지났는데 그대로다")
# 끝난 날을 모르면(옛 자료) 바로 PO 대기
ok(wait({}, proc({"actual": "", "status": "완료"}), D), "끝난 날을 모르는데 기다린다")

# ── '완료' 라고 적힌 칸 (2026-11-05)
# Min: "완료라고 적혀 있는것도 실적 (완료)로 표기해주고 만약에 그 앞 단계는
#      완료나 실적 일정이 있는데 뒤에 비어있거나 그러면 완료로 표기해줘"
done = NS["_process_step_done"]
ok(done({"expected_note": "완료"}), "계획 칸 '완료' 를 끝난 것으로 안 센다")
ok(done({"actual_note": "PO 완료"}), "실적 칸 'PO 완료' 를 끝난 것으로 안 센다")
ok(not done({"actual_note": "완료 예정"}) and not done({"expected_note": "미완료"}),
   "'완료 예정' · '미완료' 를 끝난 것으로 셌다")
show = lambda p: NS["_ds_show_notes"](NS["_process_rolled"](p))
P = [{"name": "01", "actual": "2026-04-05"},
     {"name": "02", "expected_note": "완료"},          # 계획 칸 '완료'
     {"name": "03", "actual_note": "카이저 입고 필요"},  # 글자 — 끝난 게 아니다
     {"name": "04"},                                   # 비었지만 뒤가 끝남
     {"name": "05", "actual": "2026-07-15"},
     {"name": "06", "expected": "2026-12-01"}]
got = [x.get("actual") for x in show(P)]
# 앞 단계를 완료로 채우지 않는다 (Min: "715-156359-006 예시 보니까 전에
# 완료로 두면 안 될것 같아" → "앞 단계 채우기 전부 빼기")
ok(got == ["2026-04-05", "완료", "카이저 입고 필요", None, "2026-07-15", ""],
   "끝난 단계의 실적 표기가 이상하다: %r" % got)
# 최종 승인이 끝난 품목은 앞이 전부 완료
F = [{"name": "01"}, {"name": "02", "actual_note": "진행중"}, {"name": "13 최종 승인", "actual": "2026-10-01"}]
got = [x.get("actual") for x in show(F)]
ok(got == ["완료", "완료", "2026-10-01"], "최종 승인이 끝났는데 앞이 안 채워졌다: %r" % got)
# '○○ 승인' 이 끝났으면 바로 앞 '○○ 작성' 도 완료
W = [{"name": "06 LAIR 작성"}, {"name": "07 LAIR 승인", "actual": "2026-10-01"}, {"name": "08 SI"}]
got = [x.get("status") for x in NS["_process_rolled"](W)]
ok(got[:2] == ["완료", "완료"], "승인이 끝났는데 작성이 안 끝났다: %r" % got)

# ── _enrich_model 이 쓴다 · 양산으로 올라오면 _model_po_wait 가 바로 맡는다
_en = SRC[SRC.index("def _enrich_model("):]
_en = _en[:_en.index("\ndef ", 10)]
ok('out["dev_po_wait"] = _dev_po_wait(m, proc)' in _en, "개발 모델에 1주일 규칙이 안 붙는다")
ok('_model_po_wait(m, _disp) or bool(out.get("dev_po_wait"))' in _en, "PO 대기가 1주일 규칙을 안 본다")

# ── 반영 — 양식에 있는 품목은 새 파일 그대로 (빈 칸은 지운다)
_ap = SRC[SRC.index("async def admin_dev_schedule_apply"):]
_ap = _ap[:_ap.index("\ndef _pn_variants")]
ok('"expected": s.get("expected") or ""' in _ap and '"actual": s.get("actual") or ""' in _ap,
   "빈 칸에 옛 날짜가 남는다")
ok('prev.get("expected")' not in _ap and 'prev.get("actual")' not in _ap, "옛 날짜를 이어받는다")
ok('row[_f] = s.get(_f) or ""' in _ap, "빈 글자 칸에 옛 글자가 남는다")
ok('"status": ""' in _ap, "옛 완료 표시가 남는다")
ok('m["final_done_seen"]' in _ap, "최종 승인이 끝난 날을 안 적는다")
_pl = SRC[SRC.index("def _ds_plan("):]
_pl = _pl[:_pl.index("\nasync def _ds_open")]
ok('"cleared": cleared' in _pl, "미리보기가 지워질 칸을 안 센다")

# ── 앱 — 서버가 정한 PO 대기를 따른다
DART = (ROOT.parent / "mobile/lib/screens/model_list_screen.dart").read_text(encoding="utf-8")
ok("m.containsKey('dev_po_wait')" in DART, "앱이 1주일 규칙을 모른다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1)
print("ok — 새 파일이 정본 · 최종 승인 뒤 7일 → PO 대기 · '완료' 칸 · 앞 단계는 적힌 그대로")
