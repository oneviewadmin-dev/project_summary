# 모델 표는 보기 전용 — 고치는 것은 엑셀뿐이다
#   python3 backend/tests/test_models_readonly.py
#
# 2026-10-22 — 같은 모델이 화면과 엑셀에서 따로 놀았다. 엑셀에는 개발인데
# 화면에서 양산으로 바꿔 두면 다음 엑셀을 올릴 때 도로 개발이 된다. 어느
# 쪽이 맞는지 아무도 모르게 되고, 매출은 양산(판가 x 수량)과 개발(고정)이
# 달라서 숫자까지 어긋났다. 구분 하나만 막아 뒀더니 같은 일이 판가·수량에서
# 또 났다. 기준을 엑셀 하나로 모은다.
#
# 이 시험이 막는 것
#   잠금을 거는 자리(lockModelTable)가 사라지는 것.
#   표를 그리는 길에서 그 호출이 빠져 칸이 열린 채 남는 것.
#   화면에서 저장 · 추가 · 삭제가 다시 나가는 것.
#   화면 코드를 통째로 지워 되살릴 자리를 잃는 것.
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]      # backend/
HTML = (ROOT / "admin_v2.html").read_text(encoding="utf-8")

ok = 0


def has(pat, why):
    global ok
    assert re.search(pat, HTML, re.S), why
    ok += 1


# ── 1. 잠금 스위치와 함수가 있다 ─────────────────────────────
has(r"var MODELS_READONLY = true;", "MODELS_READONLY 스위치가 없다")
has(r"function lockModelTable\(container\)", "lockModelTable 이 없다")
print("1. 잠금 스위치 · 잠금 함수 ✓")

# ── 2. 표를 그리는 길에서 실제로 부른다 ──────────────────────
#   리스너를 붙이는 자리가 모든 그리기가 지나가는 길목이다.
i_call = HTML.find("    lockModelTable(container);")
i_wire = HTML.find("// 모든 입력 변경 시 window._modelsData 실시간 동기화")
assert i_call > 0, "표를 그릴 때 lockModelTable 을 안 부른다"
assert i_wire > 0, "표를 그리는 자리를 못 찾았다"
assert i_call < i_wire, "잠금이 리스너 붙이기보다 뒤에 있다"
ok += 1
print("2. 표를 그릴 때마다 잠근다 ✓")

# ── 3. 저장 · 추가 · 삭제가 막혀 있다 ────────────────────────
save = HTML[HTML.find("function saveModels(statusEl) {"):][:900]
assert "MODELS_READONLY" in save, "saveModels 가 안 막혔다 — PUT 이 나간다"
dele = HTML[HTML.find("window.mdlDeleteModels = function"):][:700]
assert "MODELS_READONLY" in dele, "삭제가 안 막혔다"
assert re.search(r"if \(MODELS_READONLY\) \{\s*\n\s*if \(addBtn\)", HTML), \
    "'모델 추가' 버튼이 안 막혔다"
ok += 1
print("3. 저장 · 추가 · 삭제 세 길이 다 막혔다 ✓")

# ── 4. 입력 칸을 지우지 않고 잠그기만 했다 ───────────────────
#   지우면 되살릴 자리를 잊는다. 칸은 그대로 두고 readOnly/disabled 만 건다.
for f in ("price", "material_cost", "po_qty", "shipped_qty", "name",
          "part_number", "dev_type", "group"):
    assert ('data-field="%s"' % f) in HTML, "%s 칸이 사라졌다" % f
assert "el.readOnly = true;" in HTML, "입력 칸을 readonly 로 안 건다"
assert "el.classList.add('mdl-locked-sel');" in HTML, \
    "select 를 손 못 대게 하는 자리가 없다"
ok += 1
print("4. 입력 칸은 그대로 두고 잠그기만 했다 ✓")

# ── 4-2. 색을 죽이지 않는다 ──────────────────────────────────
#   2026-10-22 — 잠그면서 흐린 회색으로 덮었더니 표가 통째로 죽은 화면이
#   됐다. 구분(파랑) · 유형 칩 색이 사라지면 한눈에 읽히던 것이 안 읽힌다.
#   select 에 disabled 를 걸면 브라우저가 제멋대로 회색을 입히므로 안 쓴다.
lock_css = re.search(r"'\.mdl-locked \{[^']*'", HTML)
assert lock_css, "잠긴 칸 CSS 가 없다"
for bad in ("background", "color:", "border-color", "opacity"):
    assert bad not in lock_css.group(0), \
        "잠긴 칸 CSS 가 %s 를 덮는다 — 색을 죽이면 안 된다" % bad
lock_fn = HTML[HTML.find("function lockModelTable"):][:1600]
assert "el.disabled = true" not in lock_fn, \
    "입력 칸에 disabled 를 건다 — 브라우저가 회색으로 덮는다"
ok += 1
print("4-2. 잠그되 색은 그대로 둔다 ✓")

# ── 5. 사람에게 왜 못 고치는지 말해 준다 ─────────────────────
assert "mdl-xl-only" in HTML, "안내 띠가 없다"
assert "엑셀로만" in HTML, "엑셀로만 바꾼다는 말이 없다"
assert ".mdl-locked" in HTML, "잠긴 칸 모양(CSS)이 없다"
ok += 1
print("5. 안내 띠 · 잠긴 칸 모양 ✓")

# ── 6. 자바스크립트가 깨지지 않았다 ──────────────────────────
#   따옴표 안에 따옴표를 넣다가 스크립트가 통째로 죽은 적이 있다.
n = len(re.findall(r"<script\b", HTML))
assert n >= 10, "script 블록이 %d 개뿐이다" % n
ok += 1
print("6. script 블록 %d 개 그대로 ✓" % n)

print("전부 통과 · %d 가지" % ok)
