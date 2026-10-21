# 구분(양산/개발)은 엑셀로만 바꾼다 — 화면에서는 못 고친다
#   python3 backend/tests/test_group_readonly.py
#
# 왜 막았나
#   엑셀에는 개발인데 화면에서 양산으로 바꿔 둔 모델이 생겼다. 다음에 엑셀을
#   올리면 도로 개발이 되니 어느 쪽이 맞는지 아무도 모르게 된다. 매출도
#   양산(판가 x 수량)과 개발($3,400 고정)이 달라서 숫자까지 어긋났다.
#   그래서 기준을 하나로 못 박았다 — 엑셀이 맞다.
#
# 이 시험이 막는 것
#   누가 disabled 를 떼어 다시 고를 수 있게 만드는 것.
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]      # backend/
SRC = (ROOT / "admin_v2.html").read_text(encoding="utf-8")
ok = 0

# ── 1. 모델 목록의 구분 칸은 disabled 다 ──────────────────────
assert 'data-field="group" disabled' in SRC, \
    "모델 목록의 구분 select 에 disabled 가 없다 — 손으로 고칠 수 있다"
ok += 1

# ── 2. 왜 막았는지, 어떻게 바꾸는지가 적혀 있다 ───────────────
assert "구분은 엑셀로만" in SRC, "막은 이유·대처 안내가 없다"
ok += 1

# ── 3. 자동차 상세의 '현재단계' 도 막혀 있다 ──────────────────
assert "function selRO" in SRC, "읽기 전용 select helper 가 없다"
assert "selRO('현재단계'" in SRC, "자동차 상세의 현재단계가 아직 고를 수 있다"
ok += 1

# ── 4. 값은 여전히 읽어서 저장한다 ────────────────────────────
# disabled 라도 JS 는 값을 읽는다. 이 줄이 빠지면 저장할 때 구분이 날아간다.
assert """querySelector('[data-field="group"]')""" in SRC, \
    "syncDomToData 가 구분 값을 안 읽는다"
ok += 1

# ── 5. 고를 수 있는 select 가 남아 있지 않다 ──────────────────
# disabled 없이 같은 모양으로 또 만들면 이 줄이 걸린다.
plain = SRC.count('<select data-field="group">')
assert plain == 0, "disabled 없는 구분 select 가 %d개 남아 있다" % plain
ok += 1

print("전부 통과 ·", ok, "가지")
