# ══════════════════════════════════════════════════════════════════
#  올라온 주차별 계획 엑셀 원본 보관 (2026-10-23)
# ══════════════════════════════════════════════════════════════════
#
# 지금까지 엑셀 업로드는 메모리에서 열어 읽고 그대로 버렸다. 남는 것은
# 반영된 결과(models.json)와 저장 직전 자동 백업 열 개뿐이었다. 그래서
# "이 숫자가 왜 이렇게 들어갔나" 를 나중에 따질 근거가 없었다 — 파서가
# 잘못 읽었는지, 엑셀이 원래 그랬는지 구분할 방법이 없다.
#
# 이 파일은 그 원본을 한 벌 떠 둔다.
#
#   <uploads>/plan/<프로젝트>/<시각>_<원래 이름>.xlsx
#   <uploads>/plan/index.json          누가 · 언제 · 무엇을 올렸는지
#
# 보관하는 때
#   미리보기(preview) 와 반영(apply) 둘 다. 미리보기만 하고 접은 파일이
#   오히려 문제가 있던 파일이다 — 그것까지 남겨야 추적이 된다.
#   같은 파일을 두 번 올리면 파일은 한 벌만 두고 기록만 두 줄 남는다.
#
# 열리지 않는 파일도 보관한다. 열리지 않을수록 남겨 둘 이유가 크다.
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

# ---- 보관함 위치 (uploads 아래)
DIRNAME = "plan"
INDEX_NAME = "index.json"

# ---- 프로젝트 하나당 몇 벌까지 둘지.
# 엑셀 한 장이 보통 20~60KB 라 오백 벌이면 30MB 쯤이다. 넘으면 오래된
# 것부터 지운다. 운영 볼륨이 꽉 차는 쪽이 더 위험하기 때문이다.
KEEP_PER_PROJECT = 500

_BAD = re.compile(r'[^0-9A-Za-z가-힣._-]+')


# ==== 경로 ====
def root(upload_dir) -> Path:
    """보관함 뿌리. 없으면 만든다."""
    p = Path(upload_dir) / DIRNAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _index_path(upload_dir) -> Path:
    return root(upload_dir) / INDEX_NAME


def _safe_project(key) -> str:
    """프로젝트 키를 폴더 이름으로. 빈 값은 '_'."""
    s = _BAD.sub('_', str(key or '').strip())
    s = s.strip('._-')
    return s or '_'


def _safe_name(name) -> str:
    """원래 파일 이름을 파일 이름으로 쓸 수 있게 다듬는다.

    macOS 에서 올라온 한글 이름은 자모가 분리된 모양(NFD)으로 오는 일이
    있다. 그대로 두면 같은 파일인데 이름이 달라 보인다 — NFC 로 모은다.
    """
    import unicodedata
    s = unicodedata.normalize('NFC', str(name or ''))
    s = os.path.basename(s)                 # 경로가 섞여 와도 이름만
    s = _BAD.sub('_', s).strip('._-')
    if not s:
        s = 'plan.xlsx'
    # 너무 긴 이름은 자른다 (확장자는 지킨다)
    stem, dot, ext = s.rpartition('.')
    if dot and len(stem) > 80:
        s = stem[:80] + '.' + ext
    return s


# ==== 기록 읽고 쓰기 ====
def _load(upload_dir) -> list:
    fp = _index_path(upload_dir)
    if not fp.exists():
        return []
    try:
        with open(fp, encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, list) else list(d.get('items', []))
    except Exception:
        return []


def _store(upload_dir, items) -> None:
    """운영 파일을 직접 열어 쓰지 않는다. 옆에 다 쓰고 이름만 바꾼다.

    쓰는 도중 서버가 죽거나 배포로 교체되면 반만 적힌 JSON 이 남고,
    그건 다시 읽을 수 없다. (main.py 의 _save_models 와 같은 방식)
    """
    fp = _index_path(upload_dir)
    tmp = str(fp) + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, fp)


# ==== 보관 ====
def save(upload_dir, project_key, orig_name, raw,
         *, stage='apply', note='', who='') -> dict:
    """엑셀 원본 한 벌을 보관하고 그 기록을 돌려준다.

    stage  'preview' | 'apply'
    같은 내용(sha256)이 이미 있으면 파일은 새로 쓰지 않고 기록만 남긴다.
    """
    proj = _safe_project(project_key)
    base = root(upload_dir) / proj
    base.mkdir(parents=True, exist_ok=True)

    sha = hashlib.sha256(raw).hexdigest()
    items = _load(upload_dir)

    # ---- 같은 내용이 이미 있나 (같은 프로젝트 안에서만 본다)
    same = None
    for it in items:
        if it.get('project') == proj and it.get('sha256') == sha:
            if (base.parent / it.get('file', '')).exists():
                same = it
                break

    now = datetime.now()
    rel = same['file'] if same else '%s/%s_%s' % (
        proj, now.strftime('%Y%m%d_%H%M%S'), _safe_name(orig_name))

    if not same:
        # 같은 초에 두 번 올라와 이름이 겹치면 뒤에 숫자를 붙인다
        dst = root(upload_dir) / rel
        if dst.exists():
            stem, dot, ext = rel.rpartition('.')
            for i in range(2, 100):
                cand = '%s_%d.%s' % (stem, i, ext) if dot else '%s_%d' % (rel, i)
                if not (root(upload_dir) / cand).exists():
                    rel = cand
                    break
            dst = root(upload_dir) / rel
        dst.write_bytes(raw)

    rec = {
        'id': '%s_%s' % (now.strftime('%Y%m%d%H%M%S%f'), sha[:8]),
        'ts': now.isoformat(timespec='seconds'),
        'project': proj,
        'stage': str(stage or ''),
        'orig': _safe_name(orig_name),
        'file': rel,
        'bytes': len(raw),
        'sha256': sha,
        'dup': bool(same),
        'note': str(note or ''),
        'who': str(who or ''),
    }
    items.append(rec)
    items = _prune(upload_dir, items, proj)
    _store(upload_dir, items)
    return rec


def mark(upload_dir, rec_id, **fields) -> None:
    """이미 남긴 기록에 결과를 덧붙인다 (열기 실패 · 반영 건수 등)."""
    items = _load(upload_dir)
    for it in items:
        if it.get('id') == rec_id:
            it.update({k: v for k, v in fields.items() if v is not None})
            _store(upload_dir, items)
            return


# ==== 오래된 것 지우기 ====
def _prune(upload_dir, items, proj) -> list:
    """프로젝트 하나가 KEEP_PER_PROJECT 벌을 넘으면 오래된 파일부터 지운다.

    파일을 지우면 그 파일을 가리키는 기록도 같이 지운다. 가리킬 파일이
    없는 기록을 남기면 목록에서 눌렀을 때 404 만 뜬다.
    """
    mine = [it for it in items if it.get('project') == proj]
    files = []
    for it in mine:
        f = it.get('file')
        if f and f not in files:
            files.append(f)
    if len(files) <= KEEP_PER_PROJECT:
        return items

    drop = set(files[:len(files) - KEEP_PER_PROJECT])
    for f in drop:
        try:
            (root(upload_dir) / f).unlink()
        except Exception:
            pass
    return [it for it in items if it.get('file') not in drop]


# ==== 목록 ====
def entries(upload_dir, project_key=None, limit=100) -> list:
    """보관 기록을 최근 것부터. project_key 를 주면 그 프로젝트만."""
    items = _load(upload_dir)
    if project_key:
        proj = _safe_project(project_key)
        items = [it for it in items if it.get('project') == proj]
    items = list(reversed(items))
    if limit and limit > 0:
        items = items[:limit]
    # 목록에서 바로 누를 수 있게 파일 이름만 따로 준다
    out = []
    for it in items:
        d = dict(it)
        d['name'] = str(it.get('file', '')).split('/')[-1]
        d['exists'] = (root(upload_dir) / str(it.get('file', ''))).exists()
        out.append(d)
    return out


def file_path(upload_dir, project_key, name):
    """보관된 파일 하나의 실제 경로. 없으면 None.

    name 은 파일 이름만 받는다. '..' 이나 '/' 가 섞여 오면 거절한다 —
    주소로 보관함 바깥을 읽어 가지 못하게 한다.
    """
    nm = str(name or '')
    if not nm or '/' in nm or '\\' in nm or '..' in nm:
        return None
    base = root(upload_dir) / _safe_project(project_key)
    fp = base / nm
    try:
        fp.resolve().relative_to(base.resolve())
    except Exception:
        return None
    return fp if fp.exists() and fp.is_file() else None
