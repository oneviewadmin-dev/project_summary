# -*- coding: utf-8 -*-
"""모델 저장 — 고친 게 없으면 보내지 않고, 막히면 이유를 보여준다.

두 가지가 겹쳐서 '아무것도 안 고쳤는데 ❌ 저장 실패: HTTP 409' 가 떴다.

  · 저장은 '전체 교체' 다. 화면이 목록을 덜 들고 있으면 서버가 409 로
    막는다 (챔버 19종·SpaceX 16종이 그렇게 날아간 뒤 생긴 안전장치다).
  · 그런데 화면은 서버가 보낸 detail 을 버리고 'HTTP 409' 만 띄웠다.
    무엇이 몇 종 사라질 뻔했는지 알 길이 없었다.

이제는 고친 게 없으면 아예 안 보내고, 막히면 서버 설명을 그대로 띄운다.
"""
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
SRC = (BACK / "admin_v2.html").read_text(encoding="utf-8")

FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


i = SRC.find("function saveModels(")
ok(i > 0, "모델 저장 함수가 없어졌다")
blk = SRC[i:i + 4000]

# 변경 없음 → 안 보낸다
ok("window._mdlSavedSnap" in blk, "불러온 상태와 비교하지 않는다")
ok("'수정 사항이 없습니다'" in blk, "변경이 없을 때 알려주지 않는다")
ok("window._mdlDidDelete" in blk, "지운 것이 있을 때도 안 보내면 지우기가 안 먹는다")

# 막혔을 때 이유를 보여준다
ok("j.detail" in blk, "서버가 보낸 이유(detail)를 쓰지 않는다")
ok("throw new Error('HTTP ' + r.status);" not in blk,
   "아직 'HTTP 409' 만 띄우고 이유를 버린다")

# 비교 기준은 목록을 새로 받을 때마다 갱신돼야 한다
ok(SRC.count("window._mdlSavedSnap = JSON.stringify") >= 2,
   "목록을 새로 받을 때 비교 기준을 갱신하지 않는다 (두 곳)")

# 빈 모델명도 보낸다
j = SRC.find("function syncDomToData(")
sb = SRC[j:j + 1800]
ok('if (nm) m.name = String(nm.value || \'\').trim();' in sb,
   "빈 모델명을 아직 막고 있다 — 품번만 있는 줄의 이름을 비울 수 없다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print("  -", f)
    raise SystemExit(1)
print("전부 통과 · 변경 없으면 안 보내고, 막히면 이유를 보여준다")
