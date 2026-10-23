# 미달 사유는 엑셀 한 군데서만 적는다
#   python3 backend/tests/test_week_reason_excel.py
#
# 2026-10-22 — 같은 자리(week_reasons)를 두 군데서 쓰고 있었다.
#   · 관리자 웹 주차별 보드   PUT /week-reason  {month, week, kind, text}
#   · 엑셀 양식의 '미달 사유' 줄
# 양쪽이 다른 값을 들고 있으면 엑셀을 올릴 때 화면에서 적은 것이 덮인다.
# 구분(양산/개발) 에서 겪은 그 문제다. 엑셀 하나로 모은다.
#
# 화면에서만 되던 일이 둘 있어서 글자 규칙으로 옮겼다.
#   · 종류 고르기 → '참고:' 로 시작하면 참고, 아니면 문제
#   · 지우기     → '-' 한 글자. 빈 칸은 '그대로 둬라' 라 지우는 뜻이 못 된다
#
# 이 시험이 막는 것
#   화면에서 다시 적을 수 있게 되는 것.
#   '참고' 가 문제로 세어지는 것 — 일부러 덜 출하한 주가 지연이 된다.
#   빈 칸이 사유를 지워 버리는 것.
import ast
import io
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / "main.py").read_text(encoding="utf-8")
HTML = (ROOT / "admin_v2.html").read_text(encoding="utf-8")
TREE = ast.parse(SRC)
ok = 0

NS = {"_WEEK_REASON_KINDS": ("문제", "참고")}
for n in TREE.body:
    if isinstance(n, ast.Assign) and getattr(
            n.targets[0], "id", "") == "_NOTE_FYI_HEADS":
        exec(compile(ast.Module([n], []), "<m>", "exec"), NS)
    if isinstance(n, ast.FunctionDef) and n.name == "_plan_apply_week_notes":
        exec(compile(ast.Module([n], []), "<m>", "exec"), NS)
apply = NS["_plan_apply_week_notes"]


def run(before, notes):
    proj = {"week_reasons": {"2026-10": dict(before)}}
    n = apply(proj, "2026-10", notes)
    return proj.get("week_reasons", {}).get("2026-10", {}), n


# ── 1. 보통 사유는 '문제' 로 들어간다 ────────────────────────
got, n = run({}, {"W41": "자재 입고 지연"})
assert got["W41"]["kind"] == "문제" and got["W41"]["text"] == "자재 입고 지연", got
assert n == 1
ok += 1
print("1. 보통 사유 → 문제 ✓")

# ── 2. '참고:' 로 시작하면 참고 ──────────────────────────────
for head in ("참고:", "참고 :", "[참고]", "참고)", "FYI:"):
    got, _ = run({}, {"W41": head + " 고객 요청으로 덜 출하"})
    assert got["W41"]["kind"] == "참고", "%r → %r" % (head, got)
    assert "참고" not in got["W41"]["text"], "말머리가 글에 남았다: %r" % got
ok += 1
print("2. '참고:' · '[참고]' · 'FYI:' → 참고 (말머리는 뗀다) ✓")

# ── 3. '-' 한 글자는 지우기 ──────────────────────────────────
got, n = run({"W41": {"kind": "문제", "text": "자재 지연"}}, {"W41": "-"})
assert "W41" not in got, "안 지워졌다: %r" % got
assert n == 1
ok += 1
print("3. '-' 는 그 주 사유를 지운다 ✓")

# ── 4. 빈 칸은 '그대로 둬라' ─────────────────────────────────
#   매주 같은 파일을 열어 그 주만 적어 올린다. 빈 칸이 지우는 뜻이면
#   지난 주 사유가 매번 날아간다.
got, n = run({"W41": {"kind": "문제", "text": "자재 지연"}},
             {"W41": "", "W42": ""})
assert got["W41"]["text"] == "자재 지연", "빈 칸이 사유를 지웠다: %r" % got
assert n == 0
ok += 1
print("4. 빈 칸은 그대로 둔다 ✓")

# ── 5. 전에 '참고' 였던 주는 말머리 없이도 참고로 남는다 ─────
got, _ = run({"W41": {"kind": "참고", "text": "덜 출하"}},
             {"W41": "이번 주도 덜 출하"})
assert got["W41"]["kind"] == "참고", "참고가 문제로 바뀌었다: %r" % got
ok += 1
print("5. 전에 참고였던 주는 참고로 남는다 ✓")

# ── 6. 서버의 화면용 입력 길이 막혔다 ────────────────────────
f = next((n for n in ast.walk(TREE)
          if isinstance(n, ast.FunctionDef) and n.name == "admin_put_week_reason"),
         None)
assert f, "admin_put_week_reason 가 없다 — 지우지 말고 막아 둔다"
body = [b for b in f.body
        if not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant))]
first = body[0]
assert (isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
        and getattr(first.value.func, "id", "") == "_write_off"
        and first.value.args[0].value == "week-reason"), \
    "첫 줄이 _write_off('week-reason') 이 아니다"
ok += 1
print("6. 서버가 화면용 입력을 403 으로 막는다 ✓")

# ── 7. 화면의 사유 칸도 잠겼다 ───────────────────────────────
assert 'data-role="wbr-text"' in HTML, "사유 칸이 사라졌다"
seg = HTML[HTML.find('data-role="wbr-kind"'):][:1200]
assert "mdl-locked-sel" in seg, "종류 고르는 칸이 안 잠겼다"
assert "readonly" in seg, "사유 글 칸이 안 잠겼다"
assert "disabled" in seg, "저장 버튼이 안 잠겼다"
guard = HTML[HTML.find("window.saveWeekReason = function"):][:600]
assert "window.MODELS_READONLY" in guard, "저장 요청이 안 막혔다"
ok += 1
print("7. 화면의 종류 · 사유 · 저장 세 칸이 다 잠겼다 ✓")

# ── 8. 사람에게 어디에 적는지 알려준다 ──────────────────────
assert "엑셀로만" in HTML[HTML.find("mdl-hint"):][:4000] or \
       "미달 사유는 <b>엑셀로만</b>" in HTML, "안내 문구가 없다"
pf = (ROOT / "plan_form.py").read_text(encoding="utf-8")
assert "'참고:' 로 시작하면" in pf and "'-' 는 지우기" in pf, \
    "양식 안에 규칙 안내가 없다"
ok += 1
print("8. 화면 · 양식 양쪽에 '어디에 어떻게 적나' 가 적혀 있다 ✓")

print("전부 통과 · %d 가지" % ok)
