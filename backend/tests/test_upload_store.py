# -*- coding: utf-8 -*-
"""올라온 엑셀 원본 보관함 (upload_store).

지키려는 것
  1. 올린 파일이 바이트 하나 안 바뀌고 그대로 남는다
  2. 파일 이름이 이상해도 보관함 밖에 쓰이지 않는다 ('../' 같은 것)
  3. 같은 파일을 또 올리면 파일은 한 벌, 기록은 두 줄
  4. 너무 큰 파일 · 상한을 넘은 파일은 안 받고 '안 받았다'고 기록만 남는다
  5. 보관이 실패해도 예외가 밖으로 안 나간다 — 업로드를 막으면 안 된다
"""
import importlib
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


def fresh():
    """DATA_DIR 을 빈 임시 폴더로 돌린 보관함."""
    d = tempfile.mkdtemp(prefix="vault_")
    os.environ["DATA_DIR"] = d
    import upload_store
    importlib.reload(upload_store)
    return upload_store, Path(d)


# ── 1. 원본이 그대로 남는다 ───────────────────────────────────────
S, D = fresh()
raw = b"PK\x03\x04" + bytes(range(256)) * 4
rec = S.keep(raw, "주차별 계획_2026-10.xlsx",
             where="/admin/projects/chamber/plan-file/apply", project="chamber")
ok(rec["ok"] is True, "보관에 실패했다: %s" % rec.get("skipped"))
if rec.get("stored"):
    saved = D / "uploads" / "plan" / rec["stored"]
    ok(saved.read_bytes() == raw, "보관된 파일이 올린 파일과 다르다")
ok(rec["bytes"] == len(raw), "크기 기록이 틀렸다")
ok(rec["project"] == "chamber", "프로젝트 기록이 틀렸다")

# ── 2. 원래 이름과 들어온 경로가 남는다 ──────────────────────────
S, D = fresh()
S.keep(b"x" * 10, "파워박스 출하계획.xlsx",
       where="/admin/projects/powerbox/plan-file/apply", project="powerbox")
recs = S.entries()
ok(len(recs) == 1, "기록이 한 줄이어야 한다")
if recs:
    ok(recs[0]["filename"] == "파워박스 출하계획.xlsx", "원래 파일명이 안 남았다")
    ok(recs[0]["where"].endswith("plan-file/apply"), "들어온 경로가 안 남았다")
    ok("파워박스 출하계획.xlsx" in recs[0]["stored"],
       "보관 파일명에 원래 이름이 없어 사람이 알아볼 수 없다")

# ── 3. 이상한 파일 이름도 보관함 안에만 쓴다 ─────────────────────
S, D = fresh()
root = (D / "uploads" / "plan").resolve()
for bad in ["../../etc/passwd", "..\\..\\windows\\system32\\a.xlsx",
            "/절대/경로/계획.xlsx", 'a:b*c?d"e<f>g|h.xlsx', ".", ""]:
    r = S.keep(b"data", bad, where="t", project="p")
    ok(r["ok"] is True, "이름이 이상하다고 보관을 포기했다: %r" % bad)
    if r.get("stored"):
        p = (root / r["stored"]).resolve()
        ok(str(p).startswith(str(root)), "보관함 밖에 썼다: %r → %s" % (bad, p))

# ── 4. 같은 파일을 또 올리면 파일은 한 벌 ────────────────────────
S, D = fresh()
same = b"same-bytes" * 100
a = S.keep(same, "계획.xlsx", where="t", project="p")
b = S.keep(same, "계획(1).xlsx", where="t", project="p")
ok(b.get("duplicate_of") == a.get("stored"), "같은 파일인 걸 못 알아봤다")
ok(len(S.entries()) == 2, "기록은 두 줄이어야 한다")
files = [p for p in (D / "uploads" / "plan").glob("*/*") if p.is_file()]
ok(len(files) == 1, "파일이 %d벌 생겼다 — 한 벌이어야 한다" % len(files))

# ── 5. 너무 큰 파일은 안 받는다 ──────────────────────────────────
S, D = fresh()
S.MAX_FILE_BYTES = 100
r = S.keep(b"z" * 500, "큰파일.xlsx", where="t", project="p")
ok(r["ok"] is False and "너무" in r.get("skipped", ""), "큰 파일을 받아 버렸다")
ok(S.entries()[0]["ok"] is False, "안 받았다는 기록이 없다")

# ── 6. 상한에 닿으면 더 받지 않되, 옛것을 밀어내지 않는다 ────────
S, D = fresh()
S.keep(b"a" * 400, "첫파일.xlsx", where="t", project="p")
S.MAX_TOTAL_BYTES = 500
r = S.keep(b"b" * 400, "둘째파일.xlsx", where="t", project="p")
ok(r["ok"] is False and "상한" in r.get("skipped", ""), "상한을 무시했다")
ok(S.entries()[0]["ok"] is True, "옛 기록이 사라졌다")
ok(len([p for p in (D / "uploads" / "plan").glob("*/*") if p.is_file()]) == 1,
   "옛 파일을 밀어냈다 — 들어온 원본은 코드가 지우지 않는다")

# ── 7. 빈 파일 ───────────────────────────────────────────────────
S, D = fresh()
r = S.keep(b"", "빈.xlsx", where="t")
ok(r["ok"] is False and "빈 파일" in r.get("skipped", ""), "빈 파일을 받았다")

# ── 8. 저장이 깨져도 예외가 밖으로 안 나간다 ─────────────────────
S, D = fresh()
_orig_mkdir = S.Path.mkdir
try:
    def boom(*a, **k):
        raise OSError("디스크 꽉 찼다")
    S.Path.mkdir = boom
    try:
        r = S.keep(b"data", "계획.xlsx", where="t")
        ok(r["ok"] is False, "실패를 성공으로 보고했다")
    except Exception as e:
        ok(False, "예외가 밖으로 나왔다 (업로드가 통째로 실패한다): %s" % e)
finally:
    S.Path.mkdir = _orig_mkdir

# ── 9. 파일은 기록의 id 로만 찾는다 ──────────────────────────────
S, D = fresh()
r = S.keep(b"data", "계획.xlsx", where="t", project="p")
ok(S.path_of(r["id"]) is not None, "id 로 파일을 못 찾는다")
ok(S.path_of("없는-id") is None, "없는 id 에 파일을 내줬다")
ok(S.path_of("../../etc/passwd") is None, "경로를 넣으면 통한다 — 막아야 한다")

# ── 10. 달별로 나뉘고 zip 에 그 달 기록이 같이 들어간다 ──────────
S, D = fresh()
r = S.keep(b"data", "계획.xlsx", where="t", project="p")
mon = r["at"][:7]
ok(mon in S.months(), "연-월 폴더가 안 보인다")
with zipfile.ZipFile(io.BytesIO(S.zip_bytes(mon))) as z:
    names = z.namelist()
    ok(any(n.endswith("계획.xlsx") for n in names), "zip 에 파일이 없다: %s" % names)
    ok("%s/기록.json" % mon in names, "zip 에 그 달 기록이 없다")
    if "%s/기록.json" % mon in names:
        got = json.loads(z.read("%s/기록.json" % mon).decode())
        ok(got[0]["filename"] == "계획.xlsx", "zip 안 기록이 틀렸다")

# ── 11. 기록은 DATA_DIR 바로 밑에 있어야 백업에 들어간다 ─────────
#
# 일일 백업(backups.py)은 DATA_DIR 바로 밑의 .json 만 담고 폴더는 안
# 따라간다. 기록을 폴더 안에 두면 백업에서 조용히 빠진다.
S, D = fresh()
S.keep(b"data", "계획.xlsx", where="t", project="p")
led = D / "excel_uploads.json"
ok(led.exists(), "기록이 DATA_DIR 바로 밑에 없다 — 일일 백업에서 빠진다")
if led.exists():
    ok(led.suffix == ".json", "기록 파일이 .json 이 아니면 백업이 안 담는다")
    ok(isinstance(json.loads(led.read_text(encoding="utf-8")), list),
       "기록이 배열이 아니다")
ok(not (D / "uploads" / "plan" / "ledger.jsonl").exists(),
   "옛 자리에 또 쓰고 있다")

# ── 12. 옛 자리에 쌓인 기록도 같이 읽는다 ────────────────────────
S, D = fresh()
S.keep(b"data", "새기록.xlsx", where="t")
oldp = D / "uploads" / "plan" / "ledger.jsonl"
oldp.parent.mkdir(parents=True, exist_ok=True)
with open(oldp, "a", encoding="utf-8") as f:
    f.write(json.dumps({"at": "2026-10-01T09:00:00", "filename": "옛기록.xlsx",
                        "ok": True}, ensure_ascii=False) + "\n")
    f.write("이건 JSON 이 아니다\n")
names = [r.get("filename") for r in S.entries()]
ok("옛기록.xlsx" in names and "새기록.xlsx" in names,
   "옛 자리 기록이 안 읽힌다: %s" % names)
ok(names == sorted(names, key=lambda n: 0 if n == "옛기록.xlsx" else 1),
   "기록이 시각 순이 아니다: %s" % names)

if FAIL:
    print("실패 %d건" % len(FAIL))
    for m in FAIL:
        print("  -", m)
    raise SystemExit(1)
print("전부 통과 · 보관함 검사 12묶음")
