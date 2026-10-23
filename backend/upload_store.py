# ══════════════════════════════════════════════════════════════════
#  올라온 엑셀 원본 보관함 (2026-10-23)
# ══════════════════════════════════════════════════════════════════
#
# 왜 필요한가.
#
# 지금까지 엑셀 업로드는 파일을 메모리에서 열어 읽고 그대로 버렸다.
# 남는 것은 '반영된 결과'(models.json)뿐이다. 그래서 나중에 숫자가
# 이상할 때 "엑셀이 원래 그랬나, 우리가 잘못 읽었나" 를 가릴 방법이
# 없었다. 챔버 24줄 중 1줄만 읽힌 적이 있었는데, 그때 원본이 있었으면
# 바로 확인됐을 일이다.
#
# 그래서 올라온 파일을 손대지 않은 상태로 한 벌 복사해 둔다.
#
# 어디에 쌓이나.
#
#   <DATA_DIR>/uploads/plan/<연-월>/<시각>__<경로>__<프로젝트>__<원래이름>
#   <DATA_DIR>/uploads/plan/ledger.jsonl        한 줄에 한 번의 업로드
#
# DATA_DIR 은 운영에서 /data (fly 볼륨)다. 배포해도 지워지지 않는다.
# 연-월로 나누는 이유는 몇 년 쌓였을 때 한 폴더에 수천 개가 되지 않게,
# 그리고 '2026년 10월에 올린 것만' 내려받을 수 있게 하기 위해서다.
#
# 규칙 두 가지.
#
#  1. 보관이 실패해도 업로드는 성공해야 한다. 원본을 못 남겼다고 사람이
#     하던 일을 못 하게 만들면 안 된다 — 모든 함수가 예외를 삼키고
#     로그만 남긴다.
#  2. 한 번 들어온 원본은 코드가 지우지 않는다. 용량 상한에 걸리면
#     '안 받았다'고 기록하고 크게 로그를 남길 뿐, 옛것을 밀어내지 않는다.
#     (models.json.auto_ 백업이 10개에서 밀려 사라지는 걸로 이미 한 번
#      아쉬웠다)
import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

# ---- 한 파일 상한. 엑셀 한 장은 보통 20~60KB 다. 50MB 가 넘는 건
#      엑셀이 아니라 다른 것이 올라온 것으로 본다.
MAX_FILE_BYTES = 50 * 1024 * 1024

# ---- 보관함 전체 상한. 볼륨을 다 먹고 서버가 멈추는 것이 가장 나쁘다.
#      넘으면 더 받지 않고 기록만 남긴다(지우지는 않는다).
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024

_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _root() -> Path:
    base = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parent)))
    return base / "uploads" / "plan"


# ---- 기록은 폴더 안이 아니라 DATA_DIR 바로 밑에 둔다.
#      일일 백업(backups.py)이 DATA_DIR 바로 밑의 .json 만 담고 폴더는
#      안 따라가기 때문이다. 폴더 안에 두면 기록이 백업에서 빠진다.
#      (파일 자체는 용량 때문에 백업에 넣지 않는다 — 꺼내는 길은
#       admin 보관함의 'zip 으로 받기' 다)
def _ledger() -> Path:
    base = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parent)))
    return base / "excel_uploads.json"


def _ledger_old() -> Path:
    """옛 자리(폴더 안). 이미 쌓인 게 있으면 같이 읽어 준다."""
    return _root() / "ledger.jsonl"


# ==== 파일 이름 안전하게 만들기 ====
#
# 올라온 파일 이름은 사람이 지은 것이라 무엇이든 들어 있다. 경로
# 구분자('../'), 제어문자, 윈도에서 못 쓰는 글자, 맥에서 오는 자모
# 분리(NFD) 까지. 그대로 쓰면 보관함 밖에 파일을 쓸 수도 있다.
def safe_name(name: str) -> str:
    s = unicodedata.normalize("NFC", (name or "").strip())
    s = s.replace("\\", "/").split("/")[-1]      # 경로는 마지막 조각만
    s = _UNSAFE.sub("_", s)
    s = s.strip(". ")                            # 앞뒤 점·공백 제거
    if not s:
        s = "upload.xlsx"
    # 파일 이름 길이 제한(대부분 255바이트). 확장자는 살린다.
    stem, dot, ext = s.rpartition(".")
    if not dot:
        stem, ext = s, ""
    stem = stem[:80]
    return stem + (("." + ext[:12]) if ext else "")


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFC", (s or "").strip())
    s = re.sub(r"[^0-9A-Za-z가-힣._-]+", "-", s).strip("-")
    return s[:48] or "etc"


# ==== 지금 보관함이 얼마나 차 있나 ====
def stats() -> dict:
    root = _root()
    n = 0
    total = 0
    months = {}
    if root.exists():
        for p in root.rglob("*"):
            if not p.is_file() or p.name == "ledger.jsonl":
                continue
            n += 1
            sz = p.stat().st_size
            total += sz
            mon = p.parent.name
            m = months.setdefault(mon, {"count": 0, "bytes": 0})
            m["count"] += 1
            m["bytes"] += sz
    return {"count": n, "bytes": total, "months": months,
            "max_total_bytes": MAX_TOTAL_BYTES}


# ==== 보관 ====
#
# where   어느 업로드 경로로 들어왔는지 (/admin/.../plan-file/apply 같은 것)
# project 프로젝트 키. 없으면 빈 칸
#
# 돌려주는 값은 기록된 한 줄이다. 실패해도 예외를 던지지 않고
# {"ok": False, ...} 를 돌려준다.
def keep(raw: bytes, filename: str, where: str = "", project: str = "",
         admin: str = "") -> dict:
    now = datetime.now()
    rec = {
        "at": now.isoformat(timespec="seconds"),
        "where": where,
        "project": project,
        "filename": unicodedata.normalize("NFC", filename or ""),
        "bytes": len(raw or b""),
        "admin": admin,
        "ok": False,
    }
    try:
        if not raw:
            rec["skipped"] = "빈 파일"
            return _write_ledger(rec)

        rec["sha256"] = hashlib.sha256(raw).hexdigest()
        rec["id"] = now.strftime("%Y%m%d_%H%M%S_") + rec["sha256"][:8]

        if len(raw) > MAX_FILE_BYTES:
            rec["skipped"] = "파일이 너무 큼(%.1fMB)" % (len(raw) / 1048576)
            print("[보관함] 안 받음 — %s %s" % (rec["skipped"], rec["filename"]))
            return _write_ledger(rec)

        st = stats()
        if st["bytes"] + len(raw) > MAX_TOTAL_BYTES:
            rec["skipped"] = "보관함이 상한에 닿음"
            print("[보관함] ⚠ 상한 도달 — 더 받지 않는다. "
                  "지금 %.1fGB / 상한 %.1fGB. 옛 파일을 다른 곳으로 옮기고 "
                  "MAX_TOTAL_BYTES 를 올려야 한다."
                  % (st["bytes"] / 1073741824, MAX_TOTAL_BYTES / 1073741824))
            return _write_ledger(rec)

        # ---- 같은 파일을 또 올렸으면 파일은 한 벌만 둔다 (기록은 남긴다)
        same = _find_by_hash(rec["sha256"])
        if same:
            rec["stored"] = same
            rec["ok"] = True
            rec["duplicate_of"] = same
            return _write_ledger(rec)

        # ---- 저장
        mdir = _root() / now.strftime("%Y-%m")
        mdir.mkdir(parents=True, exist_ok=True)
        fname = "%s__%s__%s__%s" % (
            now.strftime("%Y%m%d_%H%M%S"),
            _slug(where.strip("/").replace("/", "-")),
            _slug(project) if project else "공통",
            safe_name(filename),
        )
        dst = mdir / fname
        # 같은 초에 두 개가 들어오는 경우
        k = 1
        while dst.exists():
            dst = mdir / ("%s_%d%s" % (dst.stem, k, dst.suffix))
            k += 1
        # 쓰다가 죽으면 반쪽 파일이 남는다 — 옆에 쓰고 이름만 바꾼다
        tmp = dst.with_suffix(dst.suffix + ".part")
        tmp.write_bytes(raw)
        os.replace(tmp, dst)

        rec["stored"] = str(dst.relative_to(_root()))
        rec["ok"] = True
        print("[보관함] %s ← %s (%.1fKB)"
              % (rec["stored"], rec["filename"], len(raw) / 1024))
        return _write_ledger(rec)
    except Exception as e:
        # 보관 실패가 업로드를 막지 않는다
        rec["skipped"] = "저장 중 오류: %s" % e
        print("[보관함] 실패(무시) — %s" % e)
        try:
            return _write_ledger(rec)
        except Exception:
            return rec


def _write_ledger(rec: dict) -> dict:
    """기록 한 줄 추가.

    옆에 다 쓰고 이름만 바꾼다. 쓰는 도중에 서버가 죽거나 배포로 교체되면
    반만 적힌 JSON 이 남고, 그건 다시 읽을 수 없다 (_save_models 와 같은 방식).
    """
    try:
        recs = entries(limit=0)
        recs.append(rec)
        p = _ledger()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(recs, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception as e:
        print("[보관함] 기록 실패(무시) — %s" % e)
    return rec


def _find_by_hash(sha: str) -> str:
    for rec in reversed(entries(limit=0)):
        if rec.get("sha256") == sha and rec.get("stored"):
            p = _root() / rec["stored"]
            if p.exists():
                return rec["stored"]
    return ""


# ==== 기록 읽기 ====
#
# limit 0 이면 전부. 최근 것이 뒤에 온다(기록 순서 그대로).
def entries(month: str = "", project: str = "", limit: int = 500) -> list:
    out = []
    # ---- 지금 자리 (DATA_DIR/excel_uploads.json — 배열)
    p = _ledger()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                out.extend(r for r in data if isinstance(r, dict))
        except Exception as e:
            print("[보관함] 기록 읽기 실패 — %s" % e)
    # ---- 옛 자리 (폴더 안 ledger.jsonl — 한 줄에 한 건)
    q = _ledger_old()
    if q.exists():
        try:
            for line in q.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue      # 깨진 한 줄 때문에 나머지를 못 읽으면 안 된다
                if isinstance(rec, dict):
                    out.append(rec)
        except Exception as e:
            print("[보관함] 옛 기록 읽기 실패 — %s" % e)

    out.sort(key=lambda r: str(r.get("at", "")))
    if month:
        out = [r for r in out if str(r.get("at", "")).startswith(month)]
    if project:
        out = [r for r in out if r.get("project") == project]
    if limit and len(out) > limit:
        out = out[-limit:]
    return out


# ==== 한 건의 실제 파일 경로 ====
#
# 바깥에서 오는 id 로 파일을 찾는다. 경로를 직접 받지 않는 이유는
# '../../etc/passwd' 같은 값으로 보관함 밖을 읽히지 않기 위해서다.
def path_of(entry_id: str) -> Path | None:
    for rec in reversed(entries(limit=0)):
        if rec.get("id") != entry_id or not rec.get("stored"):
            continue
        p = (_root() / rec["stored"]).resolve()
        try:
            p.relative_to(_root().resolve())   # 보관함 안인지 확인
        except ValueError:
            return None
        return p if p.exists() else None
    return None


def months() -> list:
    """파일이 있는 연-월 목록. 최근 것이 앞."""
    root = _root()
    if not root.exists():
        return []
    ms = [d.name for d in root.iterdir()
          if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}", d.name)]
    return sorted(ms, reverse=True)


def zip_bytes(month: str) -> bytes:
    """한 달치를 zip 한 덩어리로. 후임이 브라우저로 통째로 내려받는 길."""
    import io
    import zipfile
    mdir = _root() / month
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if mdir.exists():
            for p in sorted(mdir.iterdir()):
                if p.is_file() and not p.name.endswith(".part"):
                    z.write(p, arcname="%s/%s" % (month, p.name))
        # 그 달의 기록도 같이 넣는다 — 어느 파일이 무엇을 바꿨는지
        recs = entries(month=month, limit=0)
        if recs:
            z.writestr("%s/기록.json" % month,
                       json.dumps(recs, ensure_ascii=False, indent=1))
    return buf.getvalue()
