# 상태는 비고 한 칸으로 정해진다
#   python3 backend/tests/test_note_drives_status.py
#
# 2026-10-22 — 모델 정보를 엑셀로만 고치게 바꿨다. 그러면서 화면의 상태 칩과
# 이슈 칸이 잠겼는데, 엑셀이 싣고 오는 글자 칸은 **비고 하나**다.
# 그래서 비고에 적은 말이 상태까지 이어져야 한다.
#
#   비고에 '드롭 예정'  → 드롭예정 (일정이 멈춘 것이라 지연으로 안 센다)
#   비고에 '홀딩'      → 보류
#   비고에 '지연'      → 지연 (양산품은 완료예정일이 없어 이것 말고 근거가 없다)
#   비고에 '보류 해제'  → 아무것도 아님 (뒤집는 말을 알아본다)
#
# 이 시험이 막는 것
#   비고를 안 읽고 이슈 칸만 보던 때로 돌아가는 것.
#   드롭·보류를 지연으로 세는 것 — 멈춰 세운 일정을 늦었다고 하면 숫자가
#   거짓말을 한다.
import ast
import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]      # backend/
sys.path.insert(0, str(ROOT))

# main.py 를 import 하면 서버가 통째로 올라온다. 쓰는 함수만 꺼내 쓴다.
src = io.open(ROOT / "main.py", encoding="utf-8").read()
tree = ast.parse(src)
NS = {"__builtins__": __builtins__}
WANT = {"_model_hold", "_issue_says_delay", "_model_alert", "_display_group",
        "_phase_ord", "_norm_phases", "_phase_at", "_process_step_done",
        "_parse_any_date"}
CONST = {"_HOLD_WORDS", "_HOLD_NEGATIONS", "_DELAY_NEG", "MODEL_STATUSES",
         "_PHASE_EPOCH", "SOON_DAYS"}
for node in tree.body:
    if isinstance(node, ast.Assign) and getattr(
            node.targets[0], "id", "") in CONST:
        exec(compile(ast.Module([node], []), "<main>", "exec"), NS)
    if isinstance(node, ast.FunctionDef) and node.name in WANT:
        exec(compile(ast.Module([node], []), "<main>", "exec"), NS)

hold = NS["_model_hold"]
alert = NS["_model_alert"]
ok = 0


def M(note="", issues="", group="양산", status=""):
    return {"id": "X", "name": "X", "group": group, "status": status,
            "note": note, "issues": issues, "progress": 0}


# ── 1. 비고의 '드롭' · '보류' 를 읽는다 ──────────────────────
CASES = [
    ("드롭 예정", "드롭예정"),
    ("고객사 드롭 예정이라 중단", "드롭예정"),
    ("홀딩", "보류"),
    ("보류", "보류"),
    ("자재 hold", "보류"),
    ("양산 중단", "보류"),
    ("", ""),
    ("정상 진행 중", ""),
]
for note, want in CASES:
    got = hold(M(note=note))
    assert got == want, "비고 %r → %r (%r 여야 한다)" % (note, got, want)
ok += 1
print("1. 비고의 드롭 · 보류를 읽는다 — %d 가지 ✓" % len(CASES))

# ── 2. 뒤집는 말을 알아본다 ──────────────────────────────────
for note in ("보류 해제", "드롭 취소", "드롭 아님", "홀드 해제"):
    assert hold(M(note=note)) == "", "뒤집는 말을 못 읽었다: %r" % note
ok += 1
print("2. '보류 해제' 같은 뒤집는 말을 알아본다 ✓")

# ── 3. 드롭 · 보류는 지연으로 안 센다 ────────────────────────
assert alert(M(note="드롭 예정")) == "정상", "드롭을 지연으로 셌다"
assert alert(M(note="홀딩")) == "정상", "보류를 지연으로 셌다"
ok += 1
print("3. 드롭 · 보류는 지연이 아니다 ✓")

# ── 4. 비고에 적은 '지연' 이 상태가 된다 (양산품) ────────────
#   양산품은 완료예정일이 없어서 이것 말고 늦었는지 볼 근거가 없다.
assert alert(M(note="2대 고객 사급자재 지연 (ETA: 9/20)")) == "지연", \
    "비고의 '지연' 을 안 읽는다"
assert alert(M(issues="자재 지연")) == "지연", "이슈의 '지연' 을 안 읽는다"
assert alert(M(note="지연 없음")) == "정상", "'지연 없음' 을 지연으로 읽었다"
assert alert(M(note="자재 입고 완료")) == "정상", "멀쩡한 줄을 지연으로 읽었다"
ok += 1
print("4. 비고에 적은 '지연' 이 상태가 된다 ✓")

# ── 5. 손으로 적어 둔 상태가 아직 우선이다 ───────────────────
#   화면은 잠갔지만, 전에 적어 둔 값과 엑셀에 상태 칸이 생길 날을 위해
#   읽는 길은 남겨 둔다.
assert alert(M(status="지연")) == "지연", "손으로 적은 상태를 안 읽는다"
assert alert(M(status="주의")) == "주의", "손으로 적은 상태를 안 읽는다"
ok += 1
print("5. 적어 둔 상태가 있으면 그게 먼저 ✓")

print("전부 통과 · %d 가지" % ok)
