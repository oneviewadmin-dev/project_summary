# -*- coding: utf-8 -*-
"""올린 엑셀 원본을 남긴다 (2026-10-23).

### 왜 필요한가

여태 엑셀 업로드는 파일을 메모리에서 열어 읽고 그대로 버렸다. 남는 것은
'반영된 결과'(models.json 등)뿐이었다. 그래서 숫자가 이상할 때

    - 엑셀이 원래 그랬나
    - 읽는 코드가 잘못 읽었나

를 가릴 방법이 없었다. 챔버 24줄 중 1줄만 읽힌 적이 있었는데, 그때 원본이
있었으면 10초에 끝났을 일이다. 올린 파일을 그대로 한 벌 남겨 두면 나중에
누구든 열어서 대조할 수 있다.

### 어디에 남는가

    /data/uploads/excel/<날짜>/<시각>_<어디>_<프로젝트>__<원래 파일명>

/data 는 fly.io 머신에 붙은 볼륨이다. 배포해도 지워지지 않는다. 서버
디스크이지 누구의 PC 가 아니므로, 올린 사람이 회사를 떠나도 남는다.

기록(누가 언제 무엇을 올렸고 어느 파일이 됐는지)은 폴더가 아니라
**DATA_DIR 바로 밑의 excel_uploads.json** 에 쌓는다. 일일 백업
(backups.py)이 DATA_DIR 바로 밑의 .json 만 담기 때문이다 — 기록은 백업에
같이 들어가고, 원본 파일은 볼륨에 남는다.

### 볼륨이 하나라는 점

/data 볼륨은 974MB 한 개다. 엑셀 한 장이 20~60KB 라 용량은 문제가 아니지만
(한 달에 30장이면 1년에 20MB 쯤), **볼륨이 사라지면 원본도 같이 사라진다.**
주간 백업 묶음을 같은 볼륨에 하나 더 만드는 것은 그 사고에 아무 도움이
안 되므로 하지 않는다. 대신 사람이 서버 밖으로 내려받을 수 있게
`/admin/uploads/excel` 목록과 내려받기·전체 zip 을 둔다. 볼륨 밖에 한 벌을
두고 싶으면 그 zip 을 받아 두면 된다.

### 지우지 않는다

이 모듈은 아무것도 지우지 않는다. 용량이 차면 로그로 알리기만 한다.
'오래된 건 알아서 지운다' 를 넣으면, 정작 필요할 때 없는 쪽이 된다.
정리는 사람이 목록을 보고 판단한다.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import unicodedata
import zipfile
from pathlib import Path

# ── 설정 ────────────────────────────────────────────────────────────

#: 원본을 쌓는 폴더 (DATA_DIR 기준)
SUBDIR = "uploads/excel"

#: 기록 파일. DATA_DIR 바로 밑이어야 일일 백업에 들어간다.
INDEX_NAME = "excel_uploads.json"

#: 한 파일이 이보다 크면 저장하지 않고 기록만 남긴다.
#: 엑셀은 보통 20~60KB 다. 20MB 가 넘어오면 엑셀이 아니거나 사고다.
MAX_FILE_BYTES = 20 * 1024 * 1024

#: 폴더 총합이 이보다 커지면 로그로 알린다 (지우지는 않는다).
WARN_TOTAL_BYTES = 300 * 1024 * 1024

#: 파일명에 남길 수 없는 글자
_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


# ── 경로 ────────────────────────────────────────────────────────────
def root_dir(data_dir) -> Path:
    """원본이 쌓이는 폴더. 없으면 만든다."""
    p = Path(data_dir) / SUBDIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def index_path(data_dir) -> Path:
    return Path(data_dir) / INDEX_NAME


def _safe_name(name: str) -> str:
    """파일명을 그대로 쓸 수 있게 다듬는다.

    맥에서 올라온 한글 파일명은 자모가 분리된 형태(NFD)로 온다. 그대로
    두면 'ㅈ ㅜ ㅊ ㅏ' 처럼 보이거나 나중에 찾을 때 글자가 안 맞는다.
    NFC 로 모아 둔다.
    """
    n = unicodedata.normalize("NFC", (name or "").strip())
    n = os.path.basename(n)
    n = _BAD.sub("_", n)
    n = n.strip(". ")
    if len(n) > 120:
        stem, dot, ext = n.rpartition(".")
        n = (stem[:110] + ("." + ext if dot else "")) if stem else n[:120]
    return n or "upload.xlsx"


def _slug(s: str) -> str:
    """경로 한 토막에 넣을 짧은 이름."""
    n = unicodedata.normalize("NFC", (s or "").strip())
    n = _BAD.sub("_", n).replace(" ", "_")
    return n[:40]


# ── 기록 읽고 쓰기 ──────────────────────────────────────────────────
def _load_index(data_dir) -> dict:
    p = index_path(data_dir)
    if not p.exists():
        return {"uploads": []}
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("uploads"), list):
            return d
    except Exception as e:
        print(f"[upload_archive] 기록을 읽지 못했습니다(새로 시작): {e}")
    return {"uploads": []}


def _save_index(data_dir, d: dict) -> None:
    """옆에 다 쓰고 이름만 바꾼다. 쓰는 중에 죽어도 반쯤 적힌 json 이 안 남는다."""
    p = index_path(data_dir)
    tmp = str(p) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


# ── 한 벌 남기기 ────────────────────────────────────────────────────
def archive(data_dir, raw: bytes, filename: str, *, where: str,
            project: str = "", month: str = "", extra: dict | None = None) -> dict:
    """올라온 바이트를 그대로 한 벌 남긴다.

    where    어느 업로드 경로였나 (사람이 읽는 말. '매출 실적', '주차별 계획')
    project  프로젝트 키. 없으면 빈 값.
    month    그 업로드가 다루는 달 (알 수 있으면).
    extra    경로마다 다른 메모 (시트 이름, 연도 등)

    같은 파일(내용이 같은)을 또 올리면 바이트는 다시 쓰지 않고 기록만
    한 줄 더 남긴다 — 'LGK 양식을 세 번 올렸다' 는 사실 자체가 기록이다.

    실패해도 예외를 밖으로 던지지 않는다. 원본을 못 남긴 것 때문에 업로드
    자체가 실패하면 안 된다.
    """
    try:
        now = _dt.datetime.now()
        idx = _load_index(data_dir)
        ups = idx["uploads"]

        digest = hashlib.sha256(raw).hexdigest()
        orig = _safe_name(filename)
        size = len(raw)

        # ---- 내용이 같은 파일이 이미 있나
        dup_of = ""
        for e in reversed(ups):
            if e.get("sha256") == digest and e.get("path"):
                if (Path(data_dir) / SUBDIR / e["path"]).exists():
                    dup_of = e["path"]
                    break

        rel = dup_of
        saved = False
        note = ""

        if not dup_of:
            if size > MAX_FILE_BYTES:
                note = "너무 커서 저장하지 않았습니다 (%.1fMB)" % (size / 1048576)
            else:
                day = now.strftime("%Y-%m-%d")
                stem = "%s_%s" % (now.strftime("%H%M%S"), _slug(where) or "upload")
                if project:
                    stem += "_" + _slug(project)
                name = "%s__%s" % (stem, orig)
                out_dir = root_dir(data_dir) / day
                out_dir.mkdir(parents=True, exist_ok=True)
                dst = out_dir / name
                # 같은 초에 두 번 올라오면 이름이 겹친다
                k = 2
                while dst.exists():
                    dst = out_dir / ("%s-%d__%s" % (stem, k, orig))
                    k += 1
                tmp = dst.with_suffix(dst.suffix + ".part")
                tmp.write_bytes(raw)
                os.replace(tmp, dst)
                rel = "%s/%s" % (day, dst.name)
                saved = True

        entry = {
            "at": now.isoformat(timespec="seconds"),
            "where": where,
            "project": project,
            "month": month,
            "orig": orig,
            "path": rel,
            "bytes": size,
            "sha256": digest,
        }
        if dup_of:
            entry["same_as"] = dup_of
        if note:
            entry["note"] = note
        if extra:
            entry["extra"] = {str(k): v for k, v in extra.items()}
        ups.append(entry)
        idx["updated_at"] = now.isoformat(timespec="seconds")
        _save_index(data_dir, idx)

        # ---- 용량이 차 가면 알린다 (지우지는 않는다)
        tot = usage(data_dir).get("bytes", 0)
        if tot > WARN_TOTAL_BYTES:
            print("[upload_archive] 원본 폴더가 %.0fMB 입니다 — 한 번 정리하세요"
                  % (tot / 1048576))

        print("[upload_archive] %s | %s | %s (%d bytes)%s"
              % (where, project or "-", orig, size,
                 " · 같은 파일 재업로드" if dup_of else ""))
        return {"ok": True, "saved": saved, "path": rel, "sha256": digest,
                "bytes": size, "same_as": dup_of, "note": note}
    except Exception as e:
        print(f"[upload_archive] 남기지 못했습니다(업로드는 계속): {e}")
        return {"ok": False, "reason": str(e)}


# ── 보기 ────────────────────────────────────────────────────────────
def listing(data_dir, *, project: str = "", where: str = "",
            limit: int = 200, offset: int = 0) -> dict:
    """최근에 올라온 것부터. 파일이 실제로 있는지도 같이 알려준다."""
    ups = _load_index(data_dir)["uploads"]
    rows = []
    for e in ups:
        if project and e.get("project") != project:
            continue
        if where and where not in (e.get("where") or ""):
            continue
        rows.append(e)
    rows.reverse()
    total = len(rows)
    page = rows[offset:offset + max(1, min(limit, 1000))]
    root = root_dir(data_dir)
    out = []
    for e in page:
        d = dict(e)
        d["exists"] = bool(e.get("path")) and (root / e["path"]).exists()
        out.append(d)
    return {"total": total, "offset": offset, "rows": out,
            "usage": usage(data_dir)}


def file_path(data_dir, rel: str) -> Path | None:
    """목록에서 고른 파일의 실제 경로. 폴더 밖은 내주지 않는다."""
    root = root_dir(data_dir).resolve()
    try:
        p = (root / (rel or "")).resolve()
    except Exception:
        return None
    if root not in p.parents and p != root:
        return None
    if not p.is_file():
        return None
    return p


def usage(data_dir) -> dict:
    """원본 폴더가 지금 얼마나 쓰고 있나."""
    root = Path(data_dir) / SUBDIR
    n, b = 0, 0
    if root.is_dir():
        for p in root.rglob("*"):
            if p.is_file() and not p.name.endswith(".part"):
                n += 1
                b += p.stat().st_size
    import shutil as _sh
    try:
        st = _sh.disk_usage(str(data_dir))
        disk = {"total": st.total, "used": st.used, "free": st.free}
    except Exception:
        disk = {}
    return {"count": n, "bytes": b, "disk": disk}


def zip_all(data_dir, out_path, *, project: str = "") -> dict:
    """원본 전부를 zip 한 덩이로. 볼륨 밖에 한 벌 두려고 받는 용도."""
    root = Path(data_dir) / SUBDIR
    if not root.is_dir():
        return {"ok": False, "reason": "남은 원본이 없습니다"}

    keep = None
    if project:
        keep = {e["path"] for e in _load_index(data_dir)["uploads"]
                if e.get("project") == project and e.get("path")}

    n = 0
    out = Path(out_path)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.name.endswith(".part"):
                continue
            rel = str(p.relative_to(root))
            if keep is not None and rel not in keep:
                continue
            z.write(str(p), arcname=rel)
            n += 1
        # 무엇이 언제 어디서 올라온 것인지 같이 넣는다
        ip = index_path(data_dir)
        if ip.exists():
            z.write(str(ip), arcname=INDEX_NAME)
    if n == 0:
        out.unlink(missing_ok=True)
        return {"ok": False, "reason": "담을 파일이 없습니다"}
    return {"ok": True, "count": n, "bytes": out.stat().st_size,
            "path": str(out)}
