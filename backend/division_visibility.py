# -*- coding: utf-8 -*-
# ============================================================
#  앱에서 사업부를 숨긴다
# ============================================================
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR") or Path(__file__).resolve().parent)
FILE = DATA_DIR / "division_app_hidden.json"


def _read() -> dict:
    try:
        with open(FILE, "r", encoding="utf-8") as f:
            got = json.load(f)
        if isinstance(got, dict):
            return got
    except FileNotFoundError:
        pass
    except Exception as e:
        # 파일이 깨졌다고 사업부가 통째로 사라지면 안 된다. 빈 것으로 본다.
        print("[사업부 숨김] 읽지 못했습니다(무시) — %s" % e)
    return {}


# 앱에서 숨긴 사업부 id 들.
def hidden_set() -> set:
    got = _read().get("hidden")
    if not isinstance(got, list):
        return set()
    return {str(x).strip().lower() for x in got if str(x).strip()}


def is_hidden(division_id: str) -> bool:
    return str(division_id or "").strip().lower() in hidden_set()


# 하나를 숨기거나 되돌린다. 바뀐 뒤의 전체 목록을 돌려준다
def set_hidden(division_id: str, hide: bool) -> set:
    did = str(division_id or "").strip().lower()
    if not did:
        raise ValueError("사업부를 지정해 주세요")
    cur = hidden_set()
    if hide:
        cur.add(did)
    else:
        cur.discard(did)
    _write(cur)
    return cur


# 숨김 목록을 통째로 갈아 끼운다 (화면에서 체크박스를 한 번에 저장).
def replace(ids) -> set:
    cur = {str(x).strip().lower() for x in (ids or []) if str(x).strip()}
    _write(cur)
    return cur


def _write(ids: set) -> None:
    # 쓰는 도중 서버가 죽으면 반만 적힌 JSON 이 남는다. 옆에 쓰고 이름만 바꾼다.
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".json.tmp")
    body = {"hidden": sorted(ids),
            "updated_at": datetime.now().isoformat(timespec="seconds")}
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, FILE)
    print("[사업부 숨김] 앱에서 숨김 — %s" % (", ".join(sorted(ids)) or "(없음)"))
