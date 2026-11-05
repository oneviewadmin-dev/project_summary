# -*- coding: utf-8 -*-
# ============================================================
#  사업부별 용어 사전
# ============================================================
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR") or Path(__file__).resolve().parent)
FILE = DATA_DIR / "division_terms.json"


def _read() -> dict:
    try:
        with open(FILE, "r", encoding="utf-8") as f:
            got = json.load(f)
        if isinstance(got, dict):
            return got
    except FileNotFoundError:
        pass
    except Exception as e:
        print("[용어] 읽지 못했습니다(무시) — %s" % e)
    return {}


# 그 사업부의 용어 목록. 없으면 빈 목록.
def get(division_id: str) -> list:
    did = str(division_id or "").strip().lower()
    got = (_read().get(did) or {}).get("terms")
    return got if isinstance(got, list) else []


# 사업부 → 용어 목록. 화면이 한 번에 받아 간다
def all_terms() -> dict:
    out = {}
    for did, bucket in _read().items():
        rows = (bucket or {}).get("terms")
        if isinstance(rows, list) and rows:
            out[did] = rows
    return out


# 그 사업부 용어를 통째로 갈아 끼운다
def put(division_id: str, terms: list, file_name: str = "") -> int:
    did = str(division_id or "").strip().lower()
    if not did:
        raise ValueError("사업부를 지정해 주세요")
    rows = []
    for t in terms or []:
        if not isinstance(t, dict):
            continue
        short = str(t.get("short") or "").strip()
        if not short:
            continue
        rows.append({"short": short,
                     "full": str(t.get("full") or "").strip(),
                     "ko": str(t.get("ko") or "").strip(),
                     "note": str(t.get("note") or "").strip()})
    if not rows:
        return 0

    data = _read()
    data[did] = {"terms": rows,
                 "at": datetime.now().isoformat(timespec="seconds"),
                 "file": str(file_name or "")}
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, FILE)
    print("[용어] %s — %d개 담았습니다" % (did, len(rows)))
    return len(rows)
