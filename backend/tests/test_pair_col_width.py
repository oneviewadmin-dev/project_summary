# 주차 현황 보드 — 계획·실적 칸이 숫자 길이에 맞춰 넓어지는지 지킨다.
#
# 2026-10-26 — 계획·실적 두 칸이 76 / 84 로 고정이라 한 칸이 38~42px 였다.
# 좌우 여백 12 를 빼면 글자 자리가 30px 뿐이라, PCB 처럼 수량이 큰
# 사업부에서 120,380 이 '120,3' / '80' 으로 두 줄로 끊겼다. 다시 고정
# 폭으로 되돌아가면 같은 일이 또 생긴다.
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DART = os.path.join(HERE, "..", "..", "mobile", "lib", "widgets",
                    "weekly_board_card.dart")

bad = []


def ok(cond, why):
    if not cond:
        bad.append(why)


src = io.open(DART, encoding="utf-8").read()

# ── 1. 폭을 재는 함수가 있다
ok("static double _pairHalfW(" in src, "_pairHalfW 가 없다 — 폭을 재지 않는다")
ok("static double _textW(" in src, "_textW 가 없다 — 글자 폭을 재지 않는다")
ok("const double _kPairHalfMin" in src, "_kPairHalfMin 최소 폭이 없다")

# ── 2. 두 렌더러 모두 고정 폭이 아니라 그 값을 쓴다
ok("width: math.max(84.0, (halfW ?? _kPairHalfMin) * 2)" in src,
   "_pairCol 이 다시 고정 폭으로 돌아갔다")
ok("width: math.max(76.0, (halfW ?? _kPairHalfMin) * 2)" in src,
   "_secPairCol 이 다시 고정 폭으로 돌아갔다")
ok("      width: 84,\n" not in src, "_pairCol 에 고정 폭 84 가 남아 있다")
ok("      width: 76,\n" not in src, "_secPairCol 에 고정 폭 76 가 남아 있다")

# ── 3. 표마다 한 번 계산해서 모든 주차 열에 같은 폭을 넘긴다
#      (주차마다 따로 재면 열 폭이 들쭉날쭉해진다)
ok(src.count("final pairW = _pairHalfW(") == 2,
   "주차형 · 섹션형 두 표에서 폭을 계산하지 않는다")
ok("halfW: pairW" in src, "계산한 폭을 월 합계 열에 넘기지 않는다")
ok("halfW: halfW" in src, "계산한 폭을 주차 열에 넘기지 않는다")

# ── 4. ▼ 까지 세어야 한다 (미달 표시가 붙으면 한 글자가 더 늘어난다)
ok("'${c.text} ▼'" in src, "미달 ▼ 를 폭 계산에 넣지 않는다")

# ── 5. 자릿수가 늘면 폭도 늘어나는지 — 계산 규칙을 파이썬으로 옮겨 확인
def textw(t, fs=10.5):
    w = 0.0
    for ch in t:
        if ch in ",.":
            w += fs * 0.32
        elif ch == " ":
            w += fs * 0.28
        elif ch in "-·":
            w += fs * 0.42
        elif ch in "▼▲":
            w += fs
        else:
            w += fs * 0.60
    return w


# 예전 한 칸(42px)에서 글자 자리는 42-13 = 29px 였다.
ok(textw("120,380") > 29, "120,380 이 예전 폭에 들어간다면 재현이 틀렸다")
ok(textw("120,380") + 13 <= 80, "120,380 이 새 폭 상한(80)에도 안 들어간다")
ok(textw("120,380 ▼") + 13 <= 80, "미달 표시까지 붙으면 상한을 넘는다")

if bad:
    for b in bad:
        print("FAIL:", b)
    raise SystemExit(1)
print("ok test_pair_col_width")
