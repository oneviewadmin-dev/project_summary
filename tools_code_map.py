# ============================================================
#  코드 지도 만들기 — 파일 머리 · 구분선 · 함수 설명을 모아 docs/코드_지도.md 로
# ============================================================
# 코드 안에 적어 둔 세 가지(파일 머리 설명 · 구분선 · 함수 위 설명)를 그대로
# 읽어서 한 문서로 모은다. 설명을 문서에 따로 적으면 코드와 금방 어긋나므로,
# 문서는 손으로 고치지 않고 이 스크립트로 다시 만든다.
#
#   python3 tools_code_map.py            → docs/코드_지도.md 를 새로 쓴다
#
# 규칙(무엇이 머리이고 무엇이 구분선인가)은 backend/tests/test_comment_rules.py
# 와 같다. 그 점검을 통과한 파일이면 여기서도 빠짐없이 잡힌다.
from __future__ import annotations

import ast
import datetime as _dt
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "docs", "코드_지도.md")

# 구분선 — '='·'-' 4개 이상, '─'·'━' 6개 이상 (점검기와 같다)
_DIV = r"(={4,}|-{4,}|─{6,}|━{6,})"
PY_DIV = re.compile(r"^\s*#\s*" + _DIV)
SL_DIV = re.compile(r"^\s*//+\s*" + _DIV)


# ============================================================
#  글자 다듬기
# ============================================================
# 주석 한 줄에서 '#' · '//' · '///' 와 앞뒤 공백을 떼어 낸다.
def _strip(line: str) -> str:
    return re.sub(r"^\s*(#+|/{2,}|\*)\s?", "", line).rstrip()


# 구분선 줄에서 제목만 뽑는다. '# ---- 묶음 이름 ----' → '묶음 이름'.
def _div_title(line: str) -> str:
    t = _strip(line)
    t = re.sub(r"^[=\-─━\s]+", "", t)
    t = re.sub(r"[=\-─━\s]+$", "", t)
    return t.strip()


# 표 · 목록 안에서 줄바꿈 없이 보이게 — '|' 는 표를 깨므로 바꾼다.
def _one(text: str) -> str:
    return " ".join(text.split()).replace("|", "/")


# ============================================================
#  파일 머리
# ============================================================
# 맨 위 머리 블록의 제목과, 그 바로 아래 이어지는 설명 줄들을 돌려준다.
# 머리가 없으면 ('', []). div_re 는 언어별 구분선 모양.
def _header(lines: list, div_re) -> tuple:
    i = 0
    while i < len(lines) and (lines[i].strip() == "" or lines[i].startswith("#!")
                              or lines[i].startswith("# -*-")):
        i += 1
    if i >= len(lines) or not div_re.match(lines[i]):
        return "", []
    title = []
    j = i + 1
    while j < len(lines) and not div_re.match(lines[j]) and j < i + 6:
        title.append(_strip(lines[j]).strip())
        j += 1
    # 머리 아래로 이어지는 주석 문단 (빈 줄이나 코드가 나오면 끝)
    desc = []
    k = j + 1
    while k < len(lines) and lines[k].lstrip().startswith(("#", "//")) and not div_re.match(lines[k]):
        desc.append(_strip(lines[k]))
        k += 1
        if len(desc) >= 6:
            break
    return " ".join(t for t in title if t), [d for d in desc if d.strip()]


# 함수 · 클래스 바로 위 주석 첫 줄 (데코레이터 · @override · 빈 줄 하나는 건너뛴다).
def _above(lines: list, idx: int) -> str:
    p = idx - 1
    while p >= 0 and lines[p].strip().startswith("@"):
        p -= 1
    if p >= 0 and lines[p].strip() == "":
        p -= 1
    buf = []
    while p >= 0 and lines[p].lstrip().startswith(("#", "//", "*", "/*")) \
            and not PY_DIV.match(lines[p]) and not SL_DIV.match(lines[p]):
        buf.append(_strip(lines[p]))
        p -= 1
    buf.reverse()
    return _short(" ".join(b for b in buf if b.strip()))


# 긴 설명은 첫 문장만 — 지도는 '어디에 무엇이 있나'만 보이면 된다. 자세한 건 코드에서.
def _short(text: str, limit: int = 140) -> str:
    t = _one(text)
    m = re.search(r"(?<=[.。!?])\s|(?<=다\.)\s|(?<=다)\s(?=[A-Z가-힣'\"(])", t)
    if m and m.start() >= 15:
        t = t[:m.start()]
    return t if len(t) <= limit else t[:limit - 1].rstrip() + "…"


# ============================================================
#  언어별로 읽기
# ============================================================
# 파이썬 파일 → [(구분선 제목, [(이름, 설명), ...]), ...]. 맨 바깥 함수 · 클래스만.
def _py_sections(lines: list, src: str) -> list:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    items = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([d.lineno for d in n.decorator_list] or [n.lineno])
            doc = ast.get_docstring(n)
            desc = _above(lines, start - 1) or _short((doc or "").split("\n")[0])
            kind = "class " if isinstance(n, ast.ClassDef) else ""
            items.append((start, kind + n.name, desc))
    return _group(lines, items, PY_DIV)


# 다트 파일 → 같은 모양. 맨 바깥 클래스 · 함수와, 클래스 안 메서드(들여쓰기 2칸).
_DART_DECL = re.compile(
    r"^( {0}| {2})(?:abstract\s+|sealed\s+|final\s+|base\s+|static\s+)*"
    r"(?:(class|enum|mixin|extension|typedef)\s+(\w+)"
    r"|(?:Future<.*?>|Stream<.*?>|void|dynamic|[A-Z]\w*(?:<.*?>)?\??|int|double|num|bool|String|List<.*?>|Map<.*?>|Set<.*?>)\s+"
    r"(?:get\s+)?(_?[a-zA-Z]\w*)\s*(?:\(|=>|\{))")
_SKIP = {"if", "for", "while", "switch", "return", "catch", "new", "await", "else", "case"}


# 중괄호 깊이를 세면서 맨 바깥(깊이 0) 선언과 클래스 바로 안(깊이 1) 멤버만 집는다.
def _dart_sections(lines: list) -> list:
    items = []
    depth = 0
    for i, l in enumerate(lines):
        code = re.sub(r"//.*$", "", l)
        m = _DART_DECL.match(l) if depth <= 1 else None
        if m:
            name = m.group(3) or m.group(4)
            ok_top = depth == 0
            ok_member = depth == 1 and m.group(1) == "  " and not m.group(2)
            if name and name not in _SKIP and (ok_top or ok_member):
                label = (m.group(2) + " " + name) if m.group(2) else name
                if ok_member:
                    label = "  ↳ " + label
                items.append((i + 1, label, _above(lines, i)))
        depth = max(0, depth + code.count("{") - code.count("}"))
    return _group(lines, items, SL_DIV)


# admin_v2.html → <script> 블록마다 (블록 머리, 묶음들).
_JS_FN = re.compile(r"^(\s*)(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("
                    r"|^(\s*)(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>)")


# <script> 블록을 하나씩 잘라, 블록 맨 위 머리와 가장 바깥 들여쓰기의 함수들을 모은다.
def _html_blocks(lines: list) -> list:
    out = []
    start = None
    for i, l in enumerate(lines):
        low = l.lower()
        if start is None and "<script" in low and "src=" not in low and "</script>" not in low:
            start = i + 1
        elif start is not None and "</script>" in low:
            body = lines[start:i]
            k = 0
            while k < len(body) and (body[k].strip() == "" or body[k].strip().startswith("(function")):
                k += 1
            title, _ = _header(body[k:], SL_DIV)
            items = []
            base = None
            for j, b in enumerate(body):
                m = _JS_FN.match(b)
                if not m:
                    continue
                ind = len(m.group(1) if m.group(1) is not None else m.group(3))
                if base is None or ind < base:
                    base = ind
                    items = [x for x in items if x[3] <= ind]
                if ind == base:
                    items.append((j + 1, m.group(2) or m.group(4), _above(body, j), ind))
            if title or items:
                out.append((start + 1, title, _group(body, [x[:3] for x in items], SL_DIV)))
            start = None
    return out


# 줄 번호가 붙은 항목들을 바로 앞 구분선 제목 아래로 묶는다.
def _group(lines: list, items: list, div_re) -> list:
    _, _hd = 0, 0
    # 머리 블록(맨 위 구분선 두 줄)은 묶음 제목으로 쓰지 않는다
    seen = 0
    head_end = 0
    for i, l in enumerate(lines[:10]):
        if div_re.match(l):
            seen += 1
            if seen == 2:
                head_end = i + 1
                break
    titles = []
    i = head_end
    while i < len(lines):
        if div_re.match(lines[i]):
            t = _div_title(lines[i])
            # '# ====' / '#  제목' / '# ====' 꼴이면 가운데 줄이 제목이다
            if not t and i + 1 < len(lines) and lines[i + 1].lstrip().startswith(("#", "//")) \
                    and not div_re.match(lines[i + 1]):
                t = _strip(lines[i + 1]).strip()
                i += 1
                if i + 1 < len(lines) and div_re.match(lines[i + 1]):
                    i += 1
            if t:
                titles.append((i + 1, t))
        i += 1
    out = []
    cur = None
    for ln, name, desc in items:
        t = ""
        for tl, tt in titles:
            if tl < ln:
                t = tt
        if cur is None or cur[0] != t:
            cur = (t, [])
            out.append(cur)
        cur[1].append((name, desc))
    return out


# ============================================================
#  문서 쓰기
# ============================================================
# 파일 하나를 마크다운 조각으로. sections 는 [(묶음 제목, [(이름, 설명)])].
def _file_md(rel: str, title: str, desc: list, sections: list) -> list:
    out = [("### %s" % rel) if " — " in rel else ("### `%s`" % rel), ""]
    if title:
        out.append("**%s**" % _one(title))
        out.append("")
    if desc:
        out.append("> " + " ".join(_one(d) for d in desc))
        out.append("")
    for st, items in sections:
        if st:
            out.append("- **%s**" % _one(st))
            pad = "  "
        else:
            pad = ""
        # 설명이 비면 바로 위 구분선 제목이 그 함수 설명이다 (묶음 첫 함수) — 이름만 적는다
        for name, d in items:
            sub = "  " if name.startswith("  ↳") else ""
            line = "%s%s- `%s`" % (pad, sub, name.replace("↳", "").strip())
            out.append(line + (" — " + d if d else ""))
    out.append("")
    return out


# 폴더 안 파일 목록 (확장자로 거르고 이름순).
def _files(rel_dir: str, exts: tuple, recursive: bool = False) -> list:
    base = os.path.join(ROOT, rel_dir)
    out = []
    if recursive:
        for dp, _, fs in os.walk(base):
            for f in fs:
                if f.endswith(exts):
                    out.append(os.path.relpath(os.path.join(dp, f), ROOT))
    else:
        for f in os.listdir(base):
            if f.endswith(exts):
                out.append(os.path.join(rel_dir, f))
    return sorted(out)


# 코드 지도 전체를 만들어 docs/코드_지도.md 에 쓴다.
def build() -> str:
    md = ["# OneView 코드 지도", "",
          "코드 안의 **파일 머리 설명 · 구분선 · 함수 위 설명**을 모아 만든 문서입니다. "
          "손으로 고치지 말고 `python3 tools_code_map.py` 로 다시 만드세요.", "",
          "만든 날: %s" % _dt.date.today().isoformat(), "",
          "- [서버 (backend)](#서버-backend)", "- [관리자 화면 (admin_v2.html)](#관리자-화면-admin_v2html)",
          "- [앱 (mobile/lib)](#앱-mobilelib)", "- [테스트](#테스트)", "- [저장소 맨 위 스크립트](#저장소-맨-위-스크립트)", ""]

    # ── 1. 서버: main.py 를 맨 앞에, 나머지 모듈은 이름순
    md += ["## 서버 (backend)", ""]
    py = _files("backend", (".py",))
    py.sort(key=lambda p: (not p.endswith("main.py"), p))
    md += ["| 파일 | 하는 일 |", "|---|---|"]
    for rel in py:
        lines = open(os.path.join(ROOT, rel), encoding="utf-8").read().split("\n")
        t, _ = _header(lines, PY_DIV)
        md.append("| `%s` | %s |" % (rel, _one(t)))
    md.append("")
    for rel in py:
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        lines = src.split("\n")
        t, d = _header(lines, PY_DIV)
        md += _file_md(rel, t, d, _py_sections(lines, src))

    # ── 2. 관리자 화면: <script> 블록마다
    md += ["## 관리자 화면 (admin_v2.html)", ""]
    lines = open(os.path.join(ROOT, "backend", "admin_v2.html"), encoding="utf-8").read().split("\n")
    for ln, title, sections in _html_blocks(lines):
        md += _file_md("admin_v2.html %d행 — %s" % (ln, title or "script"), "", [], sections)

    # ── 3. 앱: 폴더별로
    md += ["## 앱 (mobile/lib)", ""]
    dart = _files("mobile/lib", (".dart",), recursive=True)
    md += ["| 파일 | 하는 일 |", "|---|---|"]
    for rel in dart:
        lines = open(os.path.join(ROOT, rel), encoding="utf-8").read().split("\n")
        t, _ = _header(lines, SL_DIV)
        md.append("| `%s` | %s |" % (rel.replace("mobile/lib/", ""), _one(t)))
    md.append("")
    for rel in dart:
        lines = open(os.path.join(ROOT, rel), encoding="utf-8").read().split("\n")
        t, d = _header(lines, SL_DIV)
        md += _file_md(rel.replace("mobile/lib/", ""), t, d, _dart_sections(lines))

    # ── 4. 테스트: 많아서 한 줄씩만
    md += ["## 테스트", "", "| 파일 | 지키는 것 |", "|---|---|"]
    tests = _files("backend/tests", (".py",)) + _files("mobile/test", (".dart",))
    for rel in tests:
        lines = open(os.path.join(ROOT, rel), encoding="utf-8").read().split("\n")
        t, _ = _header(lines, SL_DIV if rel.endswith(".dart") else PY_DIV)
        md.append("| `%s` | %s |" % (rel, _one(t)))
    md.append("")

    # ── 5. 맨 위 스크립트
    md += ["## 저장소 맨 위 스크립트", "", "| 파일 | 하는 일 |", "|---|---|"]
    for rel in ("release.sh", "backup.sh", "tools_changelog.py", "tools_pull_api.py", "tools_code_map.py"):
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            t, _ = _header(open(p, encoding="utf-8").read().split("\n"), PY_DIV)
            md.append("| `%s` | %s |" % (rel, _one(t)))
    md.append("")

    text = "\n".join(md)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    return text


if __name__ == "__main__":
    t = build()
    print("썼습니다: %s (%d줄)" % (os.path.relpath(OUT, ROOT), t.count("\n") + 1))
