# 매입 관리 메뉴는 잠가 둔다 — 눌러도 안 넘어간다
#   python3 backend/tests/test_purchase_menu_off.py
#
# 메뉴를 아예 지우지 않은 이유
#   지우면 "있던 메뉴가 왜 사라졌지" 가 되고, 나중에 되살릴 때 어디에
#   있었는지도 잊는다. 그래서 흐리게 남겨 두고 클릭만 끊는다.
#
# 이 시험이 막는 것
#   흐리게만 해 놓고 클릭은 안 막는 것(눌리면 화면이 넘어간다),
#   그리고 반대로 메뉴를 통째로 지워 버리는 것.
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]      # backend/
SRC = (ROOT / "admin_v2.html").read_text(encoding="utf-8")
ok = 0

# ── 1. 메뉴는 그대로 있다 ────────────────────────────────────
assert 'data-page="purchase"' in SRC, "매입 관리 메뉴가 통째로 사라졌다"
ok += 1

# ── 2. 잠금 표시가 붙어 있다 ─────────────────────────────────
assert 'class="nav-item nav-off" data-page="purchase"' in SRC, \
    "매입 관리에 nav-off 가 없다"
ok += 1

# ── 3. 클릭을 실제로 끊는다 ──────────────────────────────────
# 모양만 흐리게 하고 이 줄이 없으면 눌러서 넘어가진다.
assert "if (el.classList.contains('nav-off')) return;" in SRC, \
    "nav-off 를 눌렀을 때 끊는 코드가 없다"
ok += 1

# ── 4. 흐리게 보이고 커서가 금지 표시다 ──────────────────────
assert ".nav-item.nav-off{" in SRC, "nav-off 모양 규칙이 없다"
assert "cursor:not-allowed" in SRC, "눌러도 되는 것처럼 보인다"
ok += 1

# ── 5. 왜 막혔는지 마우스를 올리면 보인다 ────────────────────
assert "매입 관리는 잠시 닫아 두었습니다" in SRC, "잠근 이유 안내가 없다"
ok += 1

# ── 6. 매입 화면 코드는 지우지 않았다 (되살릴 수 있어야 한다) ─
assert "매입 관리 v2" in SRC, "매입 화면 코드까지 지웠다 — 되살릴 수 없다"
ok += 1

print("전부 통과 ·", ok, "가지")
