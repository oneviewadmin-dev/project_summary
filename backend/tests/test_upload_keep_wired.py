# -*- coding: utf-8 -*-
"""올라온 엑셀 원본이 '빠짐없이' 보관되는지.

업로드 주소가 스무 곳이 넘는다. 새 업로드 주소를 하나 더 만들 때 보관을
붙이는 걸 잊으면 그 경로로 올린 파일만 조용히 안 남는다. 눈으로는 절대
안 보이는 구멍이라 여기서 센다.

규칙
  · UploadFile 을 받는 /admin 주소는 파일을 _keep_upload 로 읽는다
  · 그냥 file.read() 로 읽어도 되는 곳은 ALLOW 에 '왜 괜찮은지' 와 함께 적는다
  · 보관이 실패해도 업로드는 성공해야 한다 → _keep_upload 안의 try
  · 보관함을 꺼내 보는 주소는 관리자 확인이 걸려 있고, 보기만 한다
"""
import ast
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

FAIL = []


def ok(c, m):
    if not c:
        FAIL.append(m)


SRC = (BACK / "main.py").read_text(encoding="utf-8")
tree = ast.parse(SRC)

# 보관을 안 붙여도 되는 곳 — 자기 원본을 이미 따로 저장한다
ALLOW = {
    "/upload": "PPTX 는 예전부터 uploads/<doc_id>.pptx 로 저장한다",
    "/admin/app/release": "앱 설치파일(APK)이다. 엑셀이 아니다",
    "/admin/notes/photo": "사진은 note_assets/photos 에 저장한다",
    "/admin/reports/{doc_id}/section-file": "uploads/manual/<doc_id>/ 에 저장한다",
}
HELPERS = {"_keep_upload", "_pbx_open_upload", "_pbx_read_upload",
           "_auto_read_upload"}


def routes_of(node):
    out = []
    for dec in node.decorator_list:
        if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
            continue
        if not (isinstance(dec.func.value, ast.Name) and dec.func.value.id == "app"):
            continue
        if dec.func.attr.lower() not in ("get", "post", "put", "patch"):
            continue
        if dec.args and isinstance(dec.args[0], ast.Constant):
            out.append(dec.args[0].value)
    return out


def takes_upload(node):
    for a in list(node.args.args) + list(node.args.kwonlyargs):
        if a.annotation and "UploadFile" in ast.unparse(a.annotation):
            return True
    return False


def calls(node):
    return {ast.unparse(n.func) for n in ast.walk(node) if isinstance(n, ast.Call)}


def bare_read(node):
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "read" \
                and ast.unparse(n.func.value) in ("file", "f"):
            return True
    return False


funcs = [n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
by_name = {f.name: f for f in funcs}

# ── 1) 업로드를 받는 주소는 보관 통로로 읽는다 ────────────────────
checked = 0
for f in funcs:
    rs = routes_of(f)
    if not rs or not takes_upload(f):
        continue
    path = rs[0]
    if path in ALLOW:
        continue
    checked += 1
    c = calls(f)
    ok(c & HELPERS,
       "%s 가 원본을 보관하지 않고 읽는다 — _keep_upload 를 쓰거나, "
       "괜찮은 이유를 ALLOW 에 적어라" % path)
    if bare_read(f) and "_keep_upload" not in c:
        ok(False, "%s 안에 보관 없이 읽는 file.read() 가 남아 있다" % path)

ok(checked >= 15,
   "업로드 주소를 %d개만 검사했다 — 찾는 방법이 깨진 것 같다" % checked)

# ── 2) 파일을 열어 주는 도우미도 보관한다 ─────────────────────────
for name in ("_pbx_open_upload", "_auto_read_upload"):
    f = by_name.get(name)
    ok(f is not None, "%s 이 없어졌다 — 보관 연결을 다시 확인해야 한다" % name)
    if f:
        ok("_keep_upload" in calls(f), "%s 이 원본을 보관하지 않는다" % name)

# ── 3) 보관 통로 자체 ─────────────────────────────────────────────
keep = by_name.get("_keep_upload")
ok(keep is not None, "_keep_upload 도우미가 없다")
if keep:
    ok("upload_store.keep" in calls(keep),
       "_keep_upload 가 upload_store.keep 을 부르지 않는다")
    ok(any(isinstance(n, ast.Try) for n in ast.walk(keep)),
       "_keep_upload 에 try 가 없다 — 보관이 실패하면 업로드가 통째로 실패한다")
    ok("_keep_upload" not in calls(keep), "_keep_upload 가 자기를 부른다")
ok("import upload_store" in SRC, "upload_store 를 들여오지 않았다")

# ── 4) 보관함을 꺼내 보는 주소 ────────────────────────────────────
want = {
    "/admin/uploads": "화면",
    "/admin/uploads/summary": "요약",
    "/admin/uploads/list": "목록",
    "/admin/uploads/file/{entry_id}": "한 건 내려받기",
    "/admin/uploads/zip": "한 달치 zip",
}
found = {}
for f in funcs:
    for p in routes_of(f):
        if p in want:
            found[p] = f
for p, what in want.items():
    ok(p in found, "%s (%s) 주소가 없다" % (p, what))

for p, f in found.items():
    src = ast.unparse(f)
    ok("get_admin_session" in src or "_verify_session" in src,
       "%s 에 관리자 확인이 없다 — 주소만 알면 원본을 다 받아간다" % p)
    for bad in ("_save_models", "_save_notes", "_save_revenue"):
        ok(bad not in calls(f), "%s 가 %s 를 부른다 — 보관함은 보기 전용이다" % (p, bad))

dl = found.get("/admin/uploads/file/{entry_id}")
if dl:
    ok("upload_store.path_of" in calls(dl),
       "내려받기가 path_of 를 쓰지 않는다 — 보관함 밖 파일을 읽힐 수 있다")

if FAIL:
    print("실패 %d건" % len(FAIL))
    for m in FAIL:
        print("  -", m)
    raise SystemExit(1)
print("전부 통과 · 업로드 주소 %d곳에 보관이 걸려 있다" % checked)
