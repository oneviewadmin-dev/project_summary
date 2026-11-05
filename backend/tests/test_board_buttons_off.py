# 보드 머리 · 잔특근 머리의 단추 끄기 (2026-11-03)
#   python3 backend/tests/test_board_buttons_off.py
#
# Min: "엑셀 받기랑 PO 실적 증감 빼버려 / 그동안 있떤 PO증감 데이 그대로 두고"
#      "잔특근에 있는 수정 잠금 버튼도 삭제 해버리고"
#
# 지우지 않고 숨긴다. 되살리려면 hidden 만 떼면 된다 — 지워 버리면
# 예전 방식을 쓰던 사람이 '어디 갔지' 하고 한참 찾는다.
#
# 제일 조심할 것: **적어 둔 값은 안 건드린다.** 창구만 닫는 것이라
# PO증감 칸도 보드 숫자도 그대로여야 한다.
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
H = (ROOT / 'admin_v2.html').read_text(encoding='utf-8')
FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


def hidden(el_id):
    """그 id 를 가진 단추가 hidden 으로 그려지는가."""
    i = H.find('id="%s"' % el_id)
    if i < 0:
        return False
    # 같은 태그 안에서 본다 — 다음 '>' 까지
    tag = H[max(0, i - 200):H.find('>', i)]
    return 'hidden' in tag


# ── 1. 주차 현황 보드 ───────────────────────────────────────────
ok('id="wp-form"' in H, "'엑셀 받기' 단추가 아예 사라졌다 — 숨기기로 한다")
ok(hidden('wp-form'), "'엑셀 받기' 가 아직 보인다")
ok('id="wb-edit"' in H, "'PO · 실적 · 증감 입력' 단추가 아예 사라졌다")
ok(hidden('wb-edit'), "'PO · 실적 · 증감 입력' 이 아직 보인다")

# 값은 그대로다 — 창구만 닫았다
ok('PO증감' in H, 'PO증감 칸이 사라졌다')
ok('/admin/projects/' in H and 'board-rows' in H,
   '보드 숫자를 읽어 오는 길이 사라졌다')

# ── 2. 잔 · 특근 ────────────────────────────────────────────────
ok("id=\"ot-lock\"" not in H and "id='ot-lock'" not in H,
   "'수정 잠금' 단추를 아직 그린다")
ok('_lock=true' in H.replace(' ', '') or 'var _lock = true' in H,
   '_lock 변수가 사라졌다 — 표 칸이 전부 열린다')
# 단추가 없어도 핸들러가 안 터져야 한다
ok("var lk=document.getElementById('ot-lock');\n    if(lk)" in H,
   '잠금 단추 핸들러에 없을 때 대비가 없다')
ok("var sv=document.getElementById('ot-save'); if(sv)" in H,
   '저장 단추 핸들러에 없을 때 대비가 없다')
# 엑셀로 올리는 길은 남는다 — 잔·특근은 그걸로만 들어온다
ok("id=\"ot-upload\"" in H, '잔·특근 엑셀 올리기가 사라졌다')

if FAIL:
    print('실패 %d건' % len(FAIL))
    for f in FAIL:
        print(' -', f)
    raise SystemExit(1)
print('ok — 보드 · 잔특근 단추 끄기')
