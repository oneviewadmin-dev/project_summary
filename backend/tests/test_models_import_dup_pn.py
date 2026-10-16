# -*- coding: utf-8 -*-
"""한 파일 안에서 겹치는 파트넘버는 줄을 합치지 않는다.

모델 등록 엑셀은 파트넘버를 열쇠로 쓴다. 모델명이 겹쳐도 파트넘버로
가를 수 있어서 그렇게 뒀다(큐리 파일이 여기 기댄다).

그런데 아리스타 PCB 는 반대다. 품번 하나가 출하처마다 한 줄씩, 많으면
세 줄이다. 파트넘버로만 맞추면 세 줄이 한 모델로 합쳐지고 마지막 줄만
남는다. 화면에 '합쳐졌습니다' 라고 뜨지도 않아서 더 나쁘다.

그래서 '이 파일 안에서 두 번 이상 나오는 파트넘버' 만 모델명으로
맞춘다. 한 번만 나오는 파트넘버는 예전 그대로다.
"""
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
SRC = (BACK / "main.py").read_text(encoding="utf-8")

FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


i = SRC.find("async def admin_models_import")
ok(i > 0, "모델 등록 엑셀 처리가 없어졌다")
blk = SRC[i:i + 14000]

ok("_pn_dup" in blk, "겹치는 파트넘버를 세지 않는다")
ok("_pn_seen" in blk, "파일을 미리 훑어 파트넘버를 세지 않는다")

# 맞추는 규칙에 예외가 걸려 있나
ok("if pn and pn.lower() not in _pn_dup:" in blk,
   "겹치는 파트넘버인데도 그대로 열쇠로 쓴다 — 줄이 합쳐진다")
ok("by_pnname.get((pn.lower(), name.lower()))" in blk,
   "겹치는 파트넘버를 '파트넘버+모델명' 짝으로 맞추지 않는다 — "
   "모델명이 출하처뿐이면 품번이 달라도 한 줄로 합쳐진다")

# 새로 넣을 때 by_pn 에 등록하면 다음 줄이 또 합쳐진다
ok("by_pnname[(pn.lower(), name.lower())] = entry" in blk,
   "새 모델을 짝 목록에 등록하지 않는다 — 두 번째 줄부터 합쳐진다")
ok("if pn.lower() not in _pn_dup:\n                    by_pn[pn.lower()] = entry" in blk,
   "겹치는 파트넘버를 by_pn 에 그대로 등록한다")

# id 도 겹치면 안 된다
ok('"id": ("%s · %s" % (pn, name) if (pn and pn.lower() in _pn_dup)' in blk,
   "겹치는 파트넘버를 id 로 쓴다 — 모델 id 가 겹친다")

# 한 번만 나오는 파트넘버는 예전 그대로여야 한다
ok("by_pn.get(pn.lower())" in blk,
   "파트넘버로 맞추는 길이 통째로 사라졌다 — 큐리 파일이 깨진다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for f in FAIL:
        print("  -", f)
    raise SystemExit(1)
print("전부 통과 · 겹치는 파트넘버는 모델명으로 가른다")
