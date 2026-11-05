# =================================================================
# Project Name: OneView (사업부 진행현황) — 백엔드
# =================================================================
import os
import base64
import time
import hmac
import json
import re
import shutil
import hashlib
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Response, Cookie, Depends, Body
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from openai import OpenAI
from rag import vector_store as _vs

from project_templates import (
    PROJECT_LABELS,
    aggregate_projects,
    build_project_detail,
)

import config_loader as _cl
import week_calendar as _wcal
import division_visibility as _dvis
import division_revenue as _drev          # 매출 파일로 들어온 사업부 매출
import division_terms as _dterm
import issue_status as _iss
import revenue as _rev
import division_columns as _dcol


# ============================================================
#  분류(enrichment) — 올라온 자료에 사업부·프로젝트를 붙인다
# ============================================================
def _safe_text_for_card(card: dict) -> str:
    parts = [
        card.get("product") or "",      # 모델/제품 이름 — 분류에 제일 결정적이다
        card.get("headline") or "",     # 이슈 한 줄 요약 — 제품명이 없을 때의 보조
        card.get("project_key") or "",  # 이미 프로젝트를 안다면 그 키 (가장 확실)
    ]
    # 빈 값은 빼고 잇는다. 안 그러면 "  " 같은 공백만 남아 분류가 헛돈다.
    return " ".join([p for p in parts if p]).strip()

# ============================================================
#  카드 묶기 — 이슈 여러 건을 모델 한 장으로 합친다
# ============================================================
def _normalize_model_name(name: str) -> str:
    if not isinstance(name, str):
        return ""                                       # 이름이 글자가 아니면 빈 이름
    import re as _re
    t = name.strip()
    t = _re.sub(r"^\s*\d+(?:[-.]\d+)*[.)\]]?\s+", "", t)  # 앞 번호 '3. ' · '1-2) ' 떼기
    t = _re.sub(r"\s+", " ", t)                          # 띄어쓰기 여러 칸 → 한 칸
    return t.strip()


# 카드의 모델 이름 → 같은 모델끼리 묶을 열쇠.
def _model_match_key(name: str, project_id, existing) -> str:
    base = _normalize_model_name(name).lower()   # 앞 번호를 떼고 소문자로
    if not base:
        return base                              # 이름이 없으면 묶을 수 없다
    for (pid, k) in existing:                    # 지금까지 만든 묶음 (프로젝트, 열쇠)
        if pid != project_id:
            continue                             # 다른 프로젝트의 모델과는 안 합친다
        if not k:
            continue
        # 긴 이름을 a, 짧은 이름을 b 로 — 어느 쪽이 먼저 왔든 결과가 같다
        a, b = (base, k) if len(base) >= len(k) else (k, base)
        if a == b:
            return k                             # 이름이 똑같다
        if a.startswith(b):
            rest = a[len(b):]
            # 'EFEM' 과 'EFEM (2대)' 는 같은 모델, 'EFEM' 과 'EFEMX' 는 다른 모델.
            # 짧은 이름 바로 뒤가 띄어쓰기 · 괄호 · 기호일 때만 합친다.
            if rest[:1] in (" ", "(", "[", "{", "-", "_", ".", ",", ":", "/"):
                return k
    return base                                  # 맞는 묶음이 없으면 새 열쇠

# 신호등 등급. 숫자가 클수록 나쁘다.
#   RED   = 문제 있음      BLUE = 지켜봐야 함      BLACK = 정상
_STATUS_SEVERITY = {"RED": 3, "BLUE": 2, "BLACK": 1}

# 이슈 여러 개의 색 중 가장 나쁜 색 하나를 고른다
def _worst_status(statuses):
    best = "BLACK"
    best_sev = -1
    for s in statuses:
        sev = _STATUS_SEVERITY.get(s, 0)
        if sev > best_sev:
            best_sev = sev
            best = s
    return best


# ─── 이슈 한 줄 요약(headline) — GPT 요약, headline_cache.json 에 캐시 ───
import hashlib as _hashlib_hl
import json as _json_hl
from pathlib import Path as _Path_hl

_HEADLINE_CACHE_PATH = _Path_hl(__file__).parent / "headline_cache.json"

# headline_cache.json 을 읽는다
def _load_headline_cache() -> dict:
    try:
        return _json_hl.loads(_HEADLINE_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

# 캐시를 파일에 적는다. 실패해도 조용히 넘어간다(캐시일 뿐이라서).
def _save_headline_cache(cache: dict) -> None:
    try:
        _HEADLINE_CACHE_PATH.write_text(
            _json_hl.dumps(cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass

# dated_items: [(due_date, text, raw_str), ...] due_date_min 과 같은 날짜의 항목을 우선 선택.
def _pick_headline_source(dated_items: list, due_date_min) -> str:
    if not dated_items:
        return ""
    if due_date_min:
        for d, t, _ in dated_items:
            if d == due_date_min:
                return t
    return dated_items[0][1]

# 원문 한 줄을 15자 이내 행동 중심 요약으로 변환.
def _ai_headline(source_text: str) -> str:
    src = (source_text or "").strip()
    if not src:
        return ""
    # 캐시 키: 원문 해시
    key = _hashlib_hl.sha256(src.encode("utf-8")).hexdigest()[:16]
    cache = _load_headline_cache()
    if key in cache:
        return cache[key]

    # OpenAI 호출
    result = ""
    try:
        if client is not None:
            prompt = (
                "다음 프로젝트 상태 문장에서 가장 중요한 액션 하나만 뽑아 20자 이내 명사형 한 줄로 요약해라. "
                "규칙: 원문을 앞에서부터 그대로 자르지 말고 핵심 행동/상태를 재구성. "
                "조사·어미·부사어 삭제. 여러 항목 나열 금지(가장 시급한 것 하나만). "
                "괄호·날짜·이모지 제거. 숫자와 모델명(W25, CEFEM 등)은 유지. "
                "예시: 'W23 24EA, W24 7개 완료, W25 3개 출하예정 (자재부족)' → 'W25 3개 출하 지연'. "
                "예시: 'CEFEM 2대, VTM 2대 제작중, VTM 1대 자재 지연' → 'VTM 1대 자재 지연'. "
                "요약문만 출력.\n\n"
                f"원문: {src}"
            )
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=40,
            )
            result = (resp.choices[0].message.content or "").strip()
            # 따옴표/쌍따옴표 감싸져 오면 제거
            result = result.strip("\"'` ")
            # 개행 제거
            result = result.split("\n")[0].strip()
    except Exception:
        result = ""

    # 폴백: 원문 앞 15자
    if not result:
        result = src[:22]

    # 15자 초과 방어
    if len(result) > 24:
        result = result[:24].rstrip() + "…"

    cache[key] = result
    _save_headline_cache(cache)
    return result

# 이슈 헤드라인 dedup 용 정규화 (중간 강도).
def _normalize_issue_headline(text: str) -> str:
    if not isinstance(text, str):
        return ""
    import re as _re
    t = text.strip()
    # 앞 번호 prefix
    t = _re.sub(r"^\s*\d+(?:[-.]\d+)*[.)\]]?\s+", "", t)
    # 끝쪽 보조어 반복 제거
    suffixes = [
        "중입니다", "입니다", "중임", "되었음", "되었습니다",
        "중", "진행 중", "진행중", "진행", "예정", "완료", "완료됨",
        "진행 예정", "수행 중", "검토 중", "검토중",
    ]
    changed = True
    while changed:
        changed = False
        for suf in suffixes:
            if t.lower().endswith(suf.lower()):
                t = t[: -len(suf)].rstrip(" ,.;:·-")
                changed = True
    # 다중 공백/구두점 정리
    t = _re.sub(r"\s+", " ", t)
    t = t.strip(" ,.·-;:")
    return t.lower()

# cards 를 모델 단위로 그룹핑.
def _group_dashboard_cards(cards: list) -> list:
    groups = {}            # key=(project_id, model_key) → group dict
    order = []             # 그룹 등장 순서 보존
    issue_seen = {}        # 그룹 내 (status, headline) 중복 제거용

    for c in cards:
        product = c.get("product") or ""
        pid = c.get("project_id")  # None 가능 (미분류)
        # 미분류는 project_id 대신 라벨 "__unclassified__" 로 강제
        bucket_pid = pid if pid else "__unclassified__"

        match_key = _model_match_key(product, bucket_pid, groups.keys())
        gkey = (bucket_pid, match_key)

        if gkey not in groups:
            groups[gkey] = {
                "model": _normalize_model_name(product) or product,
                "status": c.get("status") or "BLACK",
                "project_id": pid,
                "project_label": c.get("project_label"),
                "project_badge": c.get("project_badge"),
                "division_id": c.get("division_id"),
                "division_label": c.get("division_label"),
                "report_date": c.get("report_date"),
                "report_family": c.get("report_family"),
                "issues": [],
                "_statuses": [],
            }
            order.append(gkey)
            issue_seen[gkey] = set()
        else:
            # 더 짧은(=상위) 모델명이 나중에 들어오면 그걸로 표시 보정 (예: "챔버 13종" 보다 "챔버" 우선)
            existing_name = groups[gkey]["model"]
            new_name = _normalize_model_name(product) or product
            if len(new_name) < len(existing_name):
                groups[gkey]["model"] = new_name

        # 이슈 dedup (정규화 헤드라인 기반)
        st = c.get("status") or "BLACK"
        head = (c.get("headline") or "").strip()
        # summary_bullets / due_date_min 은 headline 없어도 통과
        sb = c.get("summary_bullets") or []
        if sb and not groups[gkey].get("summary_bullets"):
            groups[gkey]["summary_bullets"] = sb
        ddm = c.get("due_date_min")
        if ddm and not groups[gkey].get("due_date_min"):
            groups[gkey]["due_date_min"] = ddm
        if st and st not in groups[gkey].get("_statuses", []):
            groups[gkey]["_statuses"].append(st)
        if not head:
            continue
        norm = _normalize_issue_headline(head)
        sig = (st, norm) if norm else (st, head.lower())
        if sig in issue_seen[gkey]:
            # 더 길고 풍부한 표현이 들어오면 표시용 headline 만 갱신
            for it in groups[gkey]["issues"]:
                if it.get("status") == st and _normalize_issue_headline(it.get("headline", "")) == norm:
                    if len(head) > len(it.get("headline", "")):
                        it["headline"] = head
                    break
            continue
        issue_seen[gkey].add(sig)
        groups[gkey]["issues"].append({
            "status": st,
            "headline": head,
            "doc_id": c.get("doc_id", ""),
        })
        # summary_bullets / due_date_min 통과
        sb = c.get("summary_bullets") or []
        if sb and not groups[gkey].get("summary_bullets"):
            groups[gkey]["summary_bullets"] = sb
        ddm = c.get("due_date_min")
        if ddm and not groups[gkey].get("due_date_min"):
            groups[gkey]["due_date_min"] = ddm
        groups[gkey]["_statuses"].append(st)

        # report_date 는 가장 최신으로 갱신
        rd_new = c.get("report_date") or ""
        rd_old = groups[gkey].get("report_date") or ""
        if rd_new > rd_old:
            groups[gkey]["report_date"] = rd_new

    result = []
    for gkey in order:
        g = groups[gkey]
        g["status"] = _worst_status(g.pop("_statuses") or [g["status"]])
        result.append(g)

    # 가장 심각한 그룹부터 정렬
    # 위험한 상태(RED → ORANGE → …)부터 앞에
    result.sort(key=lambda g: -_STATUS_SEVERITY.get(g["status"], 0))
    return result


# /dashboard 카드에 division/project 분류 정보를 '추가'한다
def enrich_card(card: dict) -> dict:
    try:
        text = _safe_text_for_card(card)

        # 1순위: 백엔드가 이미 정한 project_key 가 있으면 그걸 신뢰
        hint_pid = card.get("project_key")
        project_id = None
        if hint_pid:
            # project_key 가 config 의 project_id 와 일치하는 경우 우선 사용
            if _cl.get_project(hint_pid):
                project_id = hint_pid

        # 2순위: config_loader 분류기
        if not project_id:
            project_id = _cl.classify_project(text)

        # 3순위: /upload 때 사장님이 지정한 폴백 (자동 분류가 다 실패한 경우)
        if not project_id:
            project_id = card.get("_fallback_project_id")

        division_id = _cl.derive_division_from_project(project_id)
        # 폴백 division 도 받기 (project_id 가 없는 극단적 경우)
        if not division_id:
            division_id = card.get("_fallback_division_id")

        project = _cl.get_project(project_id) if project_id else None
        division = _cl.get_division(division_id) if division_id else None

        # ⚠️ 기존 필드 그대로 두고 새 필드만 추가
        card["division_id"] = division_id
        card["division_label"] = division.get("label") if division else None
        card["project_id"] = project_id
        card["project_label"] = project.get("label") if project else None
        card["project_badge"] = _cl.badge_label_for_project(project_id)

        # progress 없는 카드(notes 기반) → models.json 통합 진행률로 채움
        if card.get("progress") is None and project_id:
            try:
                _md = _load_models()
                _proj = (_md.get("projects", {}) or {}).get(project_id, {})
                if _proj.get("models"):
                    card["progress"] = _combined_project_progress(_proj)
            except Exception:
                pass
    except Exception as e:
        # 어떤 이유로든 분류 실패해도 응답이 깨지지 않게
        card.setdefault("division_id", None)
        card.setdefault("division_label", None)
        card.setdefault("project_id", None)
        card.setdefault("project_label", None)
        card.setdefault("project_badge", None)
        card["_enrich_error"] = str(e)
    return card


# /projects/{key} 상세 응답 최상위에 분류 정보를 '추가'한다
def enrich_project_detail(detail: dict) -> dict:
    if not isinstance(detail, dict):
        return detail
    try:
        hint_pid = detail.get("project_key") or detail.get("key")
        text = " ".join([
            str(detail.get("label") or ""),
            str(detail.get("name") or ""),
            str(hint_pid or ""),
        ]).strip()

        project_id = None
        if hint_pid and _cl.get_project(hint_pid):
            project_id = hint_pid
        if not project_id:
            project_id = _cl.classify_project(text)

        division_id = _cl.derive_division_from_project(project_id)
        project = _cl.get_project(project_id) if project_id else None
        division = _cl.get_division(division_id) if division_id else None

        detail["division_id"] = division_id
        detail["division_label"] = division.get("label") if division else None
        detail["project_id"] = project_id
        detail["project_label"] = project.get("label") if project else None
        detail["project_badge"] = _cl.badge_label_for_project(project_id)
    except Exception as e:
        detail.setdefault("division_id", None)
        detail.setdefault("division_label", None)
        detail.setdefault("project_id", None)
        detail.setdefault("project_label", None)
        detail.setdefault("project_badge", None)
        detail["_enrich_error"] = str(e)
    return detail

from chart_extractor import extract_charts_from_pptx

# 파싱 — 글자에서 뜻을 꺼내는 함수들은 parsing.py 로 뺐다.
# 서버 상태를 안 쓰는 순수 함수만 거기 있다 (파일도 설정도 안 본다).
from parsing import (
    _parse_due_text,
    _parse_report_filename,
    _extract_excel_markers,
    _parse_shipping_table_header,
    _parse_sales_input,
)


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")   # 챗봇·요약·교정에 쓴다. 없으면 그 기능만 꺼진다
# 챗봇 답변 모델. 환경변수로 교체 가능 (품질: gpt-4o > gpt-4o-mini, 비용은 반대)
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o")


# ============================================================
#  챗봇 도우미 — 숫자는 코드가 계산, 말은 RAG + GPT
# ============================================================
def _strip_useless_caveats(answer: str) -> str:
    import re as _re
    if not answer:
        return answer
    pats = [
        r"[^.\n]*실적이?\s*(없는|미등록)[^.\n]*(주의|참고|확인)[^.\n]*[.!]?",
        r"[^.\n]*데이터가?\s*없는[^.\n]*(주의|참고)[^.\n]*[.!]?",
        r"[^.\n]*주의가?\s*필요합니다[.!]?",
        r"[^.\n]*참고\s*(?:하시|바랍)[^.\n]*[.!]?",
        # 경영진용: 도입 어구와 맺음말만 덜어낸다 (본문은 건드리지 않는다)
        r"^\s*(?:말씀하신|문의하신|질문하신)\s+",
        r"^\s*(?:확인해\s*보니|조회해\s*보니|살펴보니)\s*,?\s*",
        r"[^.\n]*(?:도움이\s*되셨|추가\s*문의|더\s*궁금한|필요하시면\s*말씀)[^.\n]*[.!]?",
        r"[^.\n]*더\s*자세한\s*(?:내용|정보)[^.\n]*[.!]?",
        r"\n\s*(?:정리하면|요약하면)[^\n]*$",
    ]
    out = answer
    for p in pats:
        out = _re.sub(p, "", out)
    out = _re.sub(r"\n{3,}", "\n\n", out).strip()
    # 정규식이 문장을 통째로 먹은 경우엔 원문을 살린다 (빈 답변이 최악이다)
    return out or answer.strip()


# 프로젝트 이름 → 키 변환표. config 를 매번 읽지 않으려고 들고 있는다.
# stamp 는 config 파일이 바뀌었는지 보는 표시다 (바뀌면 다시 만든다).
_CHAT_PROJ_KW_CACHE = {"stamp": None, "map": None}

# 하바플레이트 음성 오인식/오타 (config 에 넣기 애매한 것만 남긴다)
# — 사장님이 앱에서 말로 물어보실 때 "하바플레이트" 가 이렇게 잘못 들린다.
#   새로 발견되면 여기에 한 줄 추가하면 된다.
_CHAT_KW_EXTRA = {
    "하바플레잍": "hrva_plate", "하바 플레잍": "hrva_plate",
    "하버": "hrva_plate", "하바플": "hrva_plate", "하바프": "hrva_plate",
    "하바플래이트": "hrva_plate", "하바 플래이트": "hrva_plate",
    "harbor": "hrva_plate", "harva": "hrva_plate",
}


# 벡터 인덱스를 다시 만드는 중인지 표시. 동시에 두 번 만들면
# 파일이 꼬이므로 building 이 True 면 다른 요청은 그냥 지나간다.
_RAG_STATE = {"checked": 0.0, "building": False}


# 벡터 인덱스에 넣을 텍스트 조각.
def _rag_build_chunks() -> list:
    chunks = []
    # -----------------------------------------------------------
    # 주간 보고 카드
    # -----------------------------------------------------------
    try:
        for division_id, div in (_load_notes().get("notes") or {}).items():
            report_date = div.get("report_date", "")
            for card in (div.get("cards") or []):
                title = card.get("title", "")
                raw = (card.get("raw_text") or "").strip()
                if not raw:
                    parts = []
                    for sec in (card.get("sections") or []):
                        for it in (sec.get("items") or []):
                            t = (it.get("text") or "").strip()
                            if t:
                                parts.append(f"- {t}")
                    raw = f"<{title}>\n" + "\n".join(parts)
                if len(raw.strip()) < 20:
                    continue
                chunks.append({"kind": "note", "division_id": division_id,
                               "project_key": title, "project_label": title,
                               "report_date": report_date, "text": raw})
    except Exception as e:
        print(f"[rag] notes 청킹 실패: {e}")
    # -----------------------------------------------------------
    # 모델 비고 / 이슈 (프로젝트 단위로 묶는다)
    # -----------------------------------------------------------
    try:
        for pk, proj in (_load_models().get("projects") or {}).items():
            label = _display_project_label(pk)
            rows = []
            for m in (proj.get("models") or []):
                bits = []
                for f in ("note", "issues", "status", "due_text"):
                    v = str(m.get(f) or "").strip()
                    if v:
                        bits.append(v)
                if bits:
                    name = m.get("name") or m.get("id") or ""
                    rows.append(f"- {name} ({m.get('id','')}): " + " / ".join(bits))
            if not rows:
                continue
            for i in range(0, len(rows), 25):
                chunks.append({
                    "kind": "model_note", "division_id": proj.get("division_id", ""),
                    "project_key": pk, "project_label": label, "report_date": "",
                    "text": f"<{label} 모델 비고>\n" + "\n".join(rows[i:i + 25]),
                })
    except Exception as e:
        print(f"[rag] 모델 비고 청킹 실패: {e}")
    # -----------------------------------------------------------
    # 블룸 일 보고 자재 메모
    # -----------------------------------------------------------
    try:
        board = ((_load_models().get("projects") or {})
                 .get(_BLOOM_STORE) or {}).get("daily_board") or {}
        notes = [str(n.get("text") or "").strip()
                 for n in (board.get("notes") or []) if isinstance(n, dict)]
        notes = [n for n in notes if n]
        if notes:
            chunks.append({"kind": "bloom_note", "division_id": "bloom",
                           "project_key": "bloom_main", "project_label": "블룸",
                           "report_date": board.get("report_date", ""),
                           "text": "<블룸 자재/특이사항>\n" + "\n".join(f"- {n}" for n in notes)})
    except Exception as e:
        print(f"[rag] 블룸 메모 청킹 실패: {e}")

    return chunks


# 인덱스를 지금 데이터로 다시 만든다
def _rag_rebuild() -> dict:
    import numpy as _np
    import faiss as _faiss
    chunks = _rag_build_chunks()
    if not chunks:
        return {"ok": False, "reason": "no_chunks", "count": 0}
    if client is None:
        return {"ok": False, "reason": "no_openai_key", "count": len(chunks)}
    vecs = []
    for i in range(0, len(chunks), 32):
        batch = [c["text"][:6000] for c in chunks[i:i + 32]]
        resp = client.embeddings.create(model=_vs.EMBED_MODEL, input=batch)
        vecs.append(_np.array([d.embedding for d in resp.data], dtype=_np.float32))
    matrix = _np.vstack(vecs)
    _faiss.normalize_L2(matrix)
    index = _faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    _vs.RAG_DIR.mkdir(parents=True, exist_ok=True)
    _faiss.write_index(index, str(_vs.INDEX_PATH))
    _vs.META_PATH.write_text(json.dumps(chunks, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    # 프로세스에 올라와 있던 옛 인덱스를 버린다
    _vs._index = None
    _vs._meta = None
    print(f"[rag] 인덱스 재빌드 완료: {len(chunks)} chunks")
    return {"ok": True, "count": len(chunks)}


# 인덱스가 없거나 하루 넘게 묵었으면 백그라운드에서 다시 만든다
def _rag_maybe_refresh():
    import time as _t
    import threading as _th
    now = _t.time()
    if _RAG_STATE["building"] or now - _RAG_STATE["checked"] < 3600:
        return
    _RAG_STATE["checked"] = now
    try:
        age = now - _vs.INDEX_PATH.stat().st_mtime if _vs.INDEX_PATH.exists() else 1e9
    except Exception:
        age = 1e9
    if age < 86400:
        return

    def _run():
        _RAG_STATE["building"] = True
        try:
            _rag_rebuild()
        except Exception as e:
            print(f"[rag] 재빌드 실패: {e}")
        finally:
            _RAG_STATE["building"] = False

    _th.Thread(target=_run, daemon=True).start()


# 질문과 가까운 메모를 찾아 LLM 에 넘길 배경 텍스트로 만든다
def _rag_context(query: str, top_k: int = 3, min_score: float = 0.30) -> str:
    if not query:
        return ""
    try:
        if not _vs.is_ready():
            return ""
        hits = _vs.search(query, top_k=top_k)
    except Exception as e:
        print(f"[rag] 검색 실패(무시): {e}")
        return ""
    parts = []
    for h in hits or []:
        if float(h.get("score") or 0) < min_score:
            continue
        txt = str(h.get("text") or "").strip()
        if not txt:
            continue
        head = h.get("project_label") or h.get("project_key") or ""
        when = h.get("report_date") or ""
        parts.append(f"[{head}{' / ' + when if when else ''}]\n{txt[:1200]}")
    return "\n\n".join(parts[:top_k])


# 이슈·지연 질문 즉답. 적어둔 이슈 문장을 자르지 않고 그대로 낸다
def _issue_answer(project_key: str) -> str:
    if not project_key or project_key == 'all':
        return ""
    proj = (_load_models().get("projects") or {}).get(_model_key_alias(project_key)) or {}
    models = proj.get("models") or []
    if not models:
        return ""
    label = _display_project_label(project_key)
    # 프로젝트가 통째로 멈춰 있으면 그것부터 말한다.
    _phold = _project_hold(proj)
    if _phold:
        _why = _project_hold_reason(proj)
        return (f"{label}는 현재 {_phold} 상태입니다"
                + (f" ({_why})." if _why else ".")
                + f" 모델 {len(models)}종 일정은 멈춰 있습니다.")

    rows, late, held = [], [], []
    for m in models:
        txt = " / ".join(x.strip().rstrip(" ,") for x in
                         str(m.get("issues") or "").splitlines() if x.strip())
        name = m.get("id") or m.get("name") or ""
        try:
            h = _model_hold(m)
        except Exception:
            h = ""
        if h:
            # 드롭·보류는 지연이 아니다. 따로 세서 따로 말한다.
            _memo = str(m.get("note") or "").strip().replace("\n", " · ")
            held.append(f"· [{h}] {name}" + (f": {_memo}" if _memo else ""))
            continue
        if txt:
            rows.append(f"· {name}: {txt}")
        try:
            if _model_alert(m) == "지연" and not txt:
                late.append(f"· {name}: 완료예정 {m.get('current_expected') or m.get('due_text') or '미정'} 경과")
        except Exception:
            pass

    if not rows and not late and not held:
        return f"{label}에 등록된 이슈나 지연 모델이 없습니다."

    head = f"{label} 이슈 {len(rows)}건"
    if late:
        head += f" · 지연 {len(late)}종"
    if held:
        head += f" · 보류 {len(held)}종"
    lines = [head + "."]
    lines.extend(rows[:6])
    lines.extend(late[:4])
    lines.extend(held[:4])
    if len(rows) > 6:
        lines.append(f"(그 외 {len(rows) - 6}건)")
    return "\n".join(lines)


_ALERT_WORD = {"지연": "일정 지연", "이슈": "특이사항", "임박": "집중관리"}


# '2026-09-14' → '9/14'.
def _alert_short_date(v) -> str:
    t = str(v or "").strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", t)
    return f"{int(m.group(2))}/{int(m.group(3))}" if m else t


# 한 줄 사유.
def _alert_brief(a: dict, width: int = 34) -> str:
    txt = " ".join(str(a.get("issue") or "").split())
    if txt:
        # 괄호 부연과 뒤에 이어 붙인 줄만 떼어낸다
        for sep in ("(", " · "):
            i = txt.find(sep)
            if i > 4:
                txt = txt[:i]
        txt = txt.strip(" -·,:")
        return txt[:width] + "…" if len(txt) > width else txt
    exp = _alert_short_date(a.get("expected"))
    d = a.get("days")
    if exp and isinstance(d, int) and d > 0:
        return f"완료예정 {exp} · {d}일 지남"
    if exp:
        return f"완료예정 {exp}"
    return str(a.get("stage") or "").strip()


# 프로젝트를 안 짚고 '일정 지연' 만 물었을 때.
def _alert_answer_all(kinds, per_project: int = 5) -> str:
    try:
        res = get_home_alerts(limit=500)
    except Exception as e:
        print(f"[chat] 홈 알림 계산 실패: {e}")
        return ""
    rows = [a for a in (res.get("alerts") or []) if a.get("kind") in kinds]
    word = " · ".join(_ALERT_WORD.get(k, k) for k in kinds
                      if any(a.get("kind") == k for a in rows)) or \
        " · ".join(_ALERT_WORD.get(k, k) for k in kinds)
    if not rows:
        return f"{word}으로 잡힌 모델이 없습니다."

    order, grouped = [], {}
    for a in rows:
        pk = a.get("project_key") or ""
        if pk not in grouped:
            order.append(pk)
            grouped[pk] = []
        grouped[pk].append(a)

    lines = [f"{word} {len(rows)}건 · {len(order)}곳."]
    for pk in order:
        got = grouped[pk]
        lines.append(f"[{got[0].get('project') or pk}] {len(got)}건")
        for a in got[:per_project]:
            name = a.get("model") or a.get("id") or ""
            why = _alert_brief(a)
            lines.append(f"· {name}: {why}" if why else f"· {name}")
        if len(got) > per_project:
            lines.append(f"· 외 {len(got) - per_project}건")
    return "\n".join(lines)


# 질문에서 프로젝트를 찾을 때 쓰는 '키워드 → project_key' 사전.
def _chat_project_keywords() -> dict:
    import config_loader as _clx
    try:
        _projs = _clx.get_projects(visible_only=False)
    except Exception:
        _projs = []
    stamp = len(_projs)
    if _CHAT_PROJ_KW_CACHE["map"] is not None and _CHAT_PROJ_KW_CACHE["stamp"] == stamp:
        return _CHAT_PROJ_KW_CACHE["map"]

    kw = {}

    def _put(term, pk):
        t = (term or "").strip().lower()
        if len(t) >= 2 and pk:
            kw.setdefault(t, pk)

    for _p in _projs:
        _pk = _p.get("id")
        _put(_p.get("label"), _pk)
        _put(_p.get("badge_label"), _pk)
        for _t in (_p.get("aliases") or []):
            _put(_t, _pk)
        for _t in (_p.get("keywords") or []):
            _put(_t, _pk)
    try:
        from project_templates import PRODUCT_TO_PROJECT as _P2P
        for _kws, _pk in _P2P:
            for _t in _kws:
                _put(_t, _pk)
    except Exception:
        pass
    for _t, _pk in _CHAT_KW_EXTRA.items():
        _put(_t, _pk)

    _CHAT_PROJ_KW_CACHE["stamp"] = stamp
    _CHAT_PROJ_KW_CACHE["map"] = kw
    return kw


# 질문 문장에서 프로젝트 키를 찾는다
def _chat_resolve_project(text: str):
    import re as _re
    if not text:
        return None
    low = text.lower()
    best, best_len = None, 0
    for term, pk in _chat_project_keywords().items():
        if len(term) <= best_len:
            continue
        # 3글자 이하 영문 약어(TC, SL7, BOP...)는 단어 경계로만 매칭한다.
        if len(term) <= 3 and term.isascii():
            if not _re.search(r"(?<![a-z0-9])" + _re.escape(term) + r"(?![a-z0-9])", low):
                continue
        elif term not in low:
            continue
        best, best_len = pk, len(term)
    if best:
        return best
    # 모델 품번이 섞인 질문만 분류기에 넘긴다. 분류기는 부분 문자열로 재서
    # 'batch' 안의 'TC' 같은 것도 잡아버리기 때문에 일반 문장엔 쓰지 않는다.
    if _re.search(r"\d{3}-\d|\d{4,}", text):
        try:
            import config_loader as _clx
            return _clx.classify_project(text)
        except Exception:
            return None
    return None

# 답변에 들어간 금액/수량이 권위 데이터에 없는 값이면 그 값을 돌려준다
def _answer_number_mismatch(answer: str, allowed_amounts: set, allowed_qty: set):
    import re as _re
    if not answer:
        return None
    for _m in _re.finditer(r"\$\s?([0-9][0-9,]*)", answer):
        try:
            v = int(_m.group(1).replace(",", ""))
        except Exception:
            continue
        if allowed_amounts and v not in allowed_amounts:
            return f"${v:,}"
    for _m in _re.finditer(r"(?<![0-9,])([0-9][0-9,]*)\s*대", answer):
        try:
            v = int(_m.group(1).replace(",", ""))
        except Exception:
            continue
        if allowed_qty and v not in allowed_qty:
            return f"{v}대"
    return None
UPLOAD_PASSWORD = os.getenv("UPLOAD_PASSWORD", "1234")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

BASE_DIR = Path(__file__).parent.resolve()

# Railway/프로덕션: /data (영구 Volume)
# 로컬 개발: backend 폴더 안
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR)))
DATA_DIR.mkdir(parents=True, exist_ok=True)

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_HASHES_PATH = DATA_DIR / "upload_hashes.json"
SLIDES_DIR = DATA_DIR / "slides"
SLIDE_IMAGES_DIR = DATA_DIR / "slide_images"   # 기존 호환용
CROPPED_DIR = DATA_DIR / "cropped"
LATEST_FILE = DATA_DIR / "reports_latest.json"
HISTORY_FILE = DATA_DIR / "reports_history.json"
# 주간 보고 첨부 자료 (표 JSON / 사진)
NOTE_ASSETS_DIR = DATA_DIR / "note_assets"
NOTE_TABLES_DIR = NOTE_ASSETS_DIR / "tables"
NOTE_PHOTOS_DIR = NOTE_ASSETS_DIR / "photos"

for d in [UPLOAD_DIR, SLIDES_DIR, SLIDE_IMAGES_DIR, CROPPED_DIR, NOTE_ASSETS_DIR, NOTE_TABLES_DIR, NOTE_PHOTOS_DIR]:
    d.mkdir(exist_ok=True)

# ============================================================
#  올라온 엑셀 원본 보관
# ============================================================
# 엑셀은 열어서 읽고 버려 왔다. 그래서 숫자가 이상할 때 "엑셀이 원래 그랬나, 우리가 잘못 읽었나" 를 가릴 수가 없었다
import upload_store

# ============================================================
#  올린 파일을 보관함에 한 벌 남기기
# ============================================================
async def _keep_upload(file, where: str = "", project: str = "") -> bytes:
    raw = await file.read()
    try:
        upload_store.keep(raw, getattr(file, "filename", "") or "",
                          where=where, project=project)
    except Exception as _e:
        # 보관 실패가 업로드를 막지 않는다
        print(f"[보관함] 호출 실패(무시) — {_e}")
    return raw

# DATA_DIR이 git 경로와 다르면(Railway), git에 포함된 시드 자산을 영구 볼륨에 복사
try:
    seed_assets = BASE_DIR / "note_assets"
    if DATA_DIR != BASE_DIR and seed_assets.exists():
        for src in seed_assets.rglob("*"):
            if src.is_file():
                rel = src.relative_to(seed_assets)
                dst = NOTE_ASSETS_DIR / rel
                if not dst.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
        print(f"[seed] note_assets seeded to {NOTE_ASSETS_DIR}")
except Exception as _e:
    print(f"[seed] note_assets seed failed: {_e}")

# notes.json 도 동일하게 시드
try:
    import shutil
    seed_notes = BASE_DIR / "notes.json"
    if DATA_DIR != BASE_DIR and seed_notes.exists() and not (DATA_DIR / "notes.json").exists():
        shutil.copy2(seed_notes, DATA_DIR / "notes.json")
        print(f"[seed] notes.json seeded to {DATA_DIR}")
except Exception as _e:
    print(f"[seed] notes.json seed failed: {_e}")

RETENTION_DAYS = 180   # 오래된 업로드 자료를 며칠까지 들고 있을지


DEVICE_TOKENS_FILE = DATA_DIR / "device_tokens.json"   # 기기 토큰이 쌓이는 파일
_fcm_initialized = False
_fcm_lock = None

# ============================================================
#  알림 (FCM) — 폰으로 푸시
# ============================================================
def _init_fcm():
    global _fcm_initialized
    if _fcm_initialized:
        return True
    try:
        import firebase_admin
        from firebase_admin import credentials
        raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        if not raw:
            print("[FCM] FIREBASE_SERVICE_ACCOUNT_JSON 환경변수 없음. FCM 비활성.")
            return False
        cred_dict = json.loads(raw)
        cred = credentials.Certificate(cred_dict)
        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app(cred)
        _fcm_initialized = True
        print("[FCM] Firebase Admin 초기화 완료")
        return True
    except Exception as e:
        print(f"[FCM] 초기화 실패: {e}")
        return False


# 등록된 기기 토큰 목록을 읽는다. 없으면 빈 목록.
def _load_device_tokens() -> list:
    try:
        with open(DEVICE_TOKENS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("tokens", []) if isinstance(data, dict) else []
    except Exception:
        return []


# 앱 푸시 알림을 받을 폰 목록(device_tokens.json)을 저장한다
def _save_device_tokens(tokens: list) -> None:
    from datetime import datetime
    DEVICE_TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DEVICE_TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump({"updated_at": datetime.now().isoformat(), "tokens": tokens}, f, ensure_ascii=False, indent=2)


# 앱이 보내온 기기 토큰을 명단에 넣는다
def _add_device_token(token: str, platform: str = "android", debug: bool = True) -> None:
    from datetime import datetime
    tokens = _load_device_tokens()
    for t in tokens:
        if t.get("token") == token:
            t["last_seen"] = datetime.now().isoformat()
            t["platform"] = platform
            t["debug"] = debug
            _save_device_tokens(tokens)
            return
    tokens.append({
        "token": token,
        "platform": platform,
        "debug": debug,
        "created_at": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat(),
    })
    _save_device_tokens(tokens)
    print(f"[FCM] 새 토큰 등록: {token[:20]}... (총 {len(tokens)}개)")


# 등록된 모든 토큰에 알람 전송. 오늘 스코프: 디버그 토큰만 대상.
def _send_fcm_to_all(title: str, body: str, data: dict = None) -> dict:
    if not _init_fcm():
        return {"ok": False, "reason": "fcm_not_initialized"}
    tokens = _load_device_tokens()
    # 안전장치: debug=True 토큰만 (릴리즈 빌드는 서버에 등록 안 되므로 자동 필터)
    # 릴리즈/디버그 모두 전송. debug 라벨은 로깅 참고용.
    target_tokens = [t["token"] for t in tokens if t.get("token")]
    if not target_tokens:
        print("[FCM] 대상 토큰 없음")
        return {"ok": False, "reason": "no_tokens"}

    from firebase_admin import messaging
    sent = 0
    failed = 0
    invalid_tokens = []
    for tok in target_tokens:
        try:
            msg = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={k: str(v) for k, v in (data or {}).items()},
                token=tok,
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        channel_id="briefing_alarm",
                        priority="high",
                    ),
                ),
            )
            messaging.send(msg)
            sent += 1
        except Exception as e:
            failed += 1
            err_str = str(e)
            if "registration-token-not-registered" in err_str or "invalid-argument" in err_str:
                invalid_tokens.append(tok)
            print(f"[FCM] 전송 실패: {e}")

    # 무효 토큰 정리
    if invalid_tokens:
        remaining = [t for t in tokens if t.get("token") not in invalid_tokens]
        _save_device_tokens(remaining)
        print(f"[FCM] 무효 토큰 {len(invalid_tokens)}개 제거")

    print(f"[FCM] 전송 완료: 성공 {sent}, 실패 {failed}")
    return {"ok": True, "sent": sent, "failed": failed}


# 현재 notes.json의 카드별 상태 + 원인 아이템 스냅샷.
def _snapshot_notes_status() -> dict:
    from datetime import date as _date

    # 카드 안 아이템 중 상태가 가장 위험한 것 하나 반환.
    def _pick_worst_item(card_dict):
        priority = {"RED": 5, "ORANGE": 4, "BLUE": 3, "GREEN": 2, "BLACK": 1}
        worst = None
        worst_sev = -1
        for sec in card_dict.get("sections", []) or []:
            for it in (sec.get("items", []) or []):
                if not isinstance(it, dict):
                    continue
                due = (it.get("due_date") or "").strip()
                if not due:
                    continue
                s = _due_status_one(due)
                sev = priority.get(s, 0)
                if sev > worst_sev:
                    worst_sev = sev
                    worst = {"item": it, "status": s}
        return worst

    # 카드 안 RED/ORANGE 아이템 전체 수집 (신규 지연 항목 감지용).
    def _collect_hot_items(card_dict):
        out = []
        for sec in card_dict.get("sections", []) or []:
            for it in (sec.get("items", []) or []):
                if not isinstance(it, dict):
                    continue
                due = (it.get("due_date") or "").strip()
                if not due:
                    continue
                s = _due_status_one(due)
                if s in ("RED", "ORANGE"):
                    out.append({
                        "text": (it.get("text") or it.get("title") or "").strip()[:80],
                        "due_date": due,
                        "status": s,
                    })
        return out

    try:
        notes = _load_notes()
        result = {}
        today = _date.today()
        for div_id, div_data in (notes.get("notes") or {}).items():
            for card in (div_data.get("cards") or []):
                title = card.get("title") or card.get("product") or ""
                if not title:
                    continue
                # 카드에 project_key가 이미 있으면 사용, 없으면 매핑
                project_key = (card.get("project_key") or "").strip()
                if not project_key:
                    try:
                        from project_templates import _match_project_key
                        project_key = _match_project_key(title) or ""
                    except Exception:
                        project_key = ""
                status = _calc_card_status(card) if card.get("sections") else (card.get("status") or "")
                trigger = None
                worst = _pick_worst_item(card) if card.get("sections") else None
                if worst and worst.get("status") == status:
                    it = worst["item"]
                    due = (it.get("due_date") or "").strip()
                    days_diff = None
                    try:
                        y, m, d = due[:10].split("-")
                        days_diff = (_date(int(y), int(m), int(d)) - today).days
                    except Exception:
                        days_diff = None
                    trigger = {
                        "text": (it.get("text") or it.get("title") or "").strip()[:80],
                        "due_date": due,
                        "days_diff": days_diff,
                    }
                result[f"{div_id}/{title}"] = {
                    "status": status,
                    "trigger": trigger,
                    "project_key": project_key,
                    "hot_items": _collect_hot_items(card) if card.get("sections") else [],
                }
        return result
    except Exception as e:
        print(f"[FCM] snapshot 실패: {e}")
        return {}


# 이전 → 이후 상태 diff. RED/ORANGE로 새로 전이된 카드만 반환.
def _detect_status_transitions(before: dict, after: dict) -> list:
    def _as_status(v):
        if isinstance(v, dict):
            return v.get("status") or ""
        return v or ""

    def _trigger(v):
        if isinstance(v, dict):
            return v.get("trigger")
        return None

    def _pkey(v):
        if isinstance(v, dict):
            return v.get("project_key") or ""
        return ""

    events = []
    for key, after_val in after.items():
        new_status = _as_status(after_val)
        old_status = _as_status(before.get(key, ""))
        # 상태 전이만 알림. 나빠지는 방향 (GREEN→ORANGE, GREEN→RED, ORANGE→RED) 만 발송
        _worsen = {
            ("", "RED"), ("없음", "RED"), ("GREEN", "RED"), ("BLUE", "RED"), ("ORANGE", "RED"),
            ("", "ORANGE"), ("없음", "ORANGE"), ("GREEN", "ORANGE"), ("BLUE", "ORANGE"),
        }
        if (old_status, new_status) in _worsen:
            div_id, title = key.split("/", 1) if "/" in key else ("", key)
            events.append({
                "division_id": div_id,
                "title": title,
                "old_status": old_status or "없음",
                "new_status": new_status,
                "trigger": _trigger(after_val),
                "project_key": _pkey(after_val),
            })
    # -----------------------------------------------------------
    # ─ 신규 RED/ORANGE 항목 감지 (카드 색 전이 없어도 발송)
    # -----------------------------------------------------------
    from datetime import date as _date2
    _today2 = _date2.today()
    for key, after_val in after.items():
        if not isinstance(after_val, dict):
            continue
        new_status = after_val.get("status") or ""
        if new_status not in ("RED", "ORANGE"):
            continue
        old_status = _as_status(before.get(key, ""))
        if (old_status, new_status) in _worsen:
            continue  # 색 전이 알람으로 이미 처리됨
        bv = before.get(key)
        before_hot = bv.get("hot_items") if isinstance(bv, dict) else []
        before_set = {(h.get("text") or "", h.get("due_date") or "") for h in (before_hot or []) if isinstance(h, dict)}
        for h in (after_val.get("hot_items") or []):
            if not isinstance(h, dict):
                continue
            sig = (h.get("text") or "", h.get("due_date") or "")
            if sig in before_set:
                continue
            due = h.get("due_date") or ""
            days_diff = None
            try:
                yy, mm, dd = due[:10].split("-")
                days_diff = (_date2(int(yy), int(mm), int(dd)) - _today2).days
            except Exception:
                pass
            div_id, title = key.split("/", 1) if "/" in key else ("", key)
            events.append({
                "division_id": div_id,
                "title": title,
                "old_status": old_status or "없음",
                "new_status": h.get("status") or new_status,
                "trigger": {"text": h.get("text") or "", "due_date": due, "days_diff": days_diff},
                "project_key": _pkey(after_val),
                "kind": "new_item",
            })
    return events


# FCM 중복 알람 쿨다운
FCM_COOLDOWN_FILE = DATA_DIR / "fcm_cooldown.json"
FCM_COOLDOWN_SECONDS = 30 * 60  # 30분


# 같은 알림을 너무 자주 안 보내려고 적어 둔 '마지막 보낸 시각'을 읽는다
def _load_fcm_cooldown() -> dict:
    try:
        return _read_json(FCM_COOLDOWN_FILE, {}) or {}
    except Exception:
        return {}


# 푸시 알림 '마지막 보낸 시각'을 저장한다
def _save_fcm_cooldown(d: dict) -> None:
    try:
        _write_json(FCM_COOLDOWN_FILE, d)
    except Exception as e:
        print(f"[FCM cooldown] save error: {e}")


# FCM 알람 히스토리
FCM_HISTORY_FILE = DATA_DIR / "notification_history.json"
FCM_HISTORY_MAX = 200


# 보낸 푸시 알림 기록을 읽는다 (알림 화면 · 중복 막기).
def _load_fcm_history() -> list:
    try:
        v = _read_json(FCM_HISTORY_FILE, [])
        return v if isinstance(v, list) else []
    except Exception:
        return []


# 보낸 푸시 알림 기록을 저장한다. 오래된 것은 잘라 낸다
def _save_fcm_history(hist: list) -> None:
    try:
        # 최신 200건만 유지
        if len(hist) > FCM_HISTORY_MAX:
            hist = hist[-FCM_HISTORY_MAX:]
        _write_json(FCM_HISTORY_FILE, hist)
    except Exception as e:
        print(f"[FCM history] save error: {e}")


# ─── FCM 편집 세션 관리 (알람 억제용) ───
EDIT_SESSION_FILE = Path("/tmp/fcm_edit_session.json")

# 편집 세션 파일 로드. 구조: {doc_id: {"snapshot": {...}, "started_at": timestamp}}
def _load_edit_session() -> dict:
    if not EDIT_SESSION_FILE.exists():
        return {}
    try:
        return json.loads(EDIT_SESSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

# 편집 세션 저장 (before snapshot)
def _save_edit_session(doc_id: str, snapshot: dict) -> None:
    import time as _time
    sessions = _load_edit_session()
    sessions[doc_id] = {
        "snapshot": snapshot,
        "started_at": int(_time.time())
    }
    try:
        EDIT_SESSION_FILE.write_text(json.dumps(sessions, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[FCM] edit session save error: {e}")

# 편집 세션 클리어 및 저장된 snapshot 반환
def _clear_edit_session(doc_id: str) -> dict:
    sessions = _load_edit_session()
    session_data = sessions.pop(doc_id, None)
    try:
        EDIT_SESSION_FILE.write_text(json.dumps(sessions, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[FCM] edit session clear error: {e}")
    return session_data.get("snapshot") if session_data else None

# 30분 이상 된 세션 자동 정리
def _cleanup_expired_sessions() -> None:
    import time as _time
    now = int(_time.time())
    sessions = _load_edit_session()
    expired = [k for k, v in sessions.items() if now - v.get("started_at", 0) > 30 * 60]
    for k in expired:
        sessions.pop(k, None)
        print(f"[FCM] expired session cleaned: {k}")
    if expired:
        try:
            EDIT_SESSION_FILE.write_text(json.dumps(sessions, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

# 상태 전이 이벤트를 FCM으로 전송.
def _fire_status_alarms(events: list) -> None:
    if not events:
        return

    import time as _time, uuid as _uuid
    from datetime import datetime as _dt
    now = int(_time.time())
    cooldown = _load_fcm_cooldown()
    history = _load_fcm_history()

    # 오래된 항목 청소 (24시간 이상 지난 것 제거)
    stale_keys = [k for k, v in cooldown.items() if not isinstance(v, (int, float)) or now - int(v) > 24 * 3600]
    for k in stale_keys:
        cooldown.pop(k, None)

    fired = 0
    skipped = 0
    for ev in events:
        div = ev.get("division_id") or ""
        proj_title = ev.get("title") or ""
        new_status = ev.get("new_status") or ""
        _due_key = ((ev.get("trigger") or {}).get("due_date") or "")
        key = f"{div}|{proj_title}|{new_status}|{_due_key}"

        last = cooldown.get(key, 0)
        try:
            last = int(last)
        except Exception:
            last = 0

        elapsed = now - last
        if last and elapsed < FCM_COOLDOWN_SECONDS:
            skipped += 1
            print(f"[FCM cooldown] skip {key} (last fired {elapsed}s ago, threshold={FCM_COOLDOWN_SECONDS}s)")
            continue

        emoji = "🔴" if new_status == "RED" else "🟠"
        # 제목은 프로젝트명만 (사업부명은 body 데이터로만 전달)
        title = f"{emoji} {proj_title}"

        # 본문 조립: 트리거 아이템이 있으면 AI 요약 + D-day 표기
        trig = ev.get("trigger") or {}
        trig_text_raw = (trig.get("text") or "").strip()
        # AI 요약 (캐시 우선, 실패 시 원문 앞 15자)
        try:
            trig_text = _ai_headline(trig_text_raw) if trig_text_raw else ""
        except Exception as _e:
            print(f"[FCM] AI 요약 실패, fallback: {_e}")
            trig_text = trig_text_raw[:20] if trig_text_raw else ""
        if not trig_text:
            trig_text = trig_text_raw[:20] if trig_text_raw else ""
        days_diff = trig.get("days_diff")
        due_date = (trig.get("due_date") or "").strip()

        if isinstance(days_diff, int):
            if days_diff < 0:
                dday_label = f"마감 지남 (D+{abs(days_diff)})"
            elif days_diff == 0:
                dday_label = "오늘 마감 (D-Day)"
            else:
                dday_label = f"마감 임박 (D-{days_diff})"
        elif due_date:
            dday_label = f"마감일 {due_date}"
        else:
            dday_label = f"{ev.get('old_status') or ''} → {new_status}"

        if trig_text:
            body = f"{trig_text} · {dday_label}"
        else:
            body = dday_label
        project_key = ev.get("project_key") or ""
        try:
            _send_fcm_to_all(title, body, data={
                "type": "status_change",
                "division_id": div,
                "title": proj_title,
                "new_status": new_status,
                "project_key": project_key,
            })
            cooldown[key] = now
            fired += 1
            history.append({
                "id": _uuid.uuid4().hex[:12],
                "ts": _dt.now().isoformat(timespec="seconds"),
                "division_id": div,
                "title": proj_title,
                "project_key": project_key,
                "old_status": ev.get("old_status") or "",
                "new_status": new_status,
                "trigger_text": trig_text,
                "due_date": due_date,
                "days_diff": days_diff if isinstance(days_diff, int) else None,
                "dday_label": dday_label,
                "read": False,
            })
        except Exception as e:
            print(f"[FCM] send error for {key}: {e}")

    _save_fcm_cooldown(cooldown)
    _save_fcm_history(history)
    print(f"[FCM] events={len(events)} fired={fired} skipped_by_cooldown={skipped}")


# ─── FCM 엔드포인트 ───

app = FastAPI(title="사업부 진행현황 보고 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 마운트
app.mount("/slides", StaticFiles(directory=str(SLIDES_DIR)), name="slides")
app.mount("/slide_images", StaticFiles(directory=str(SLIDE_IMAGES_DIR)), name="slide_images")
app.mount("/cropped", StaticFiles(directory=str(CROPPED_DIR)), name="cropped")
app.mount("/note_photos", StaticFiles(directory=str(NOTE_PHOTOS_DIR)), name="note_photos")
_STATIC_DIR = BASE_DIR / "static"
_STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

ADMIN_SESSION_COOKIE = "admin_auth"
ADMIN_SESSION_MAX_LIFETIME_SEC = int(os.getenv("ADMIN_SESSION_MAX_LIFETIME_SEC", str(24 * 3600)))  # 발급 후 최대 24시간
ADMIN_SESSION_TTL_SEC = 8 * 60 * 60
ADMIN_SESSION_SECRET = os.getenv("ADMIN_SESSION_SECRET", "")
ADMIN_COOKIE_SECURE = os.getenv("ADMIN_COOKIE_SECURE", "false").lower() == "true"
if not ADMIN_SESSION_SECRET:
    ADMIN_SESSION_SECRET = hashlib.sha256(("session::" + UPLOAD_PASSWORD).encode()).hexdigest()

# ============================================================
#  관리자 세션 — 로그인 유지 (쿠키 하나, 8시간)
# ============================================================
def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

# _b64u 의 반대. 잘라냈던 '=' 를 채워서 되돌린다
def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

# 쿠키 값을 만든다 — "발급시각.만료시각.서명".
def _sign_session(exp_ts: int, issued_at: int) -> str:
    msg = f"{issued_at}.{exp_ts}".encode()
    sig = hmac.new(ADMIN_SESSION_SECRET.encode(), msg, hashlib.sha256).digest()
    return f"{issued_at}.{exp_ts}.{_b64u(sig)}"

# 쿠키를 검사한다. 통과하면 만료시각, 아니면 None.
def _verify_session(token: Optional[str]) -> Optional[int]:
    if not token:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        issued_str, exp_str, sig_b64 = parts
        issued_at = int(issued_str)
        exp_ts = int(exp_str)
        msg = f"{issued_at}.{exp_ts}".encode()
        expected = hmac.new(ADMIN_SESSION_SECRET.encode(), msg, hashlib.sha256).digest()
        provided = _b64u_decode(sig_b64)
        if not hmac.compare_digest(expected, provided):
            return None
        now = int(time.time())
        if exp_ts < now:
            return None
        # 발급 후 최대 수명 초과 검사
        if now - issued_at > ADMIN_SESSION_MAX_LIFETIME_SEC:
            return None
        return exp_ts
    except Exception:
        return None

# 로그인에 성공했을 때 쿠키를 구워서 응답에 붙인다
def _issue_session_cookie(response: Response, issued_at: Optional[int] = None):
    now = int(time.time())
    if issued_at is None:
        issued_at = now  # 새 발급
    exp_ts = now + ADMIN_SESSION_TTL_SEC
    # 발급 후 최대 수명 초과 방지: exp_ts를 issued_at + max_lifetime 으로 제한
    hard_limit = issued_at + ADMIN_SESSION_MAX_LIFETIME_SEC
    if exp_ts > hard_limit:
        exp_ts = hard_limit
    token = _sign_session(exp_ts, issued_at)
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=token,
        max_age=max(0, exp_ts - now),
        httponly=True,
        samesite="lax",
        secure=ADMIN_COOKIE_SECURE,
        path="/",
    )
    return exp_ts

# 문지기. /admin 엔드포인트에 Depends(get_admin_session) 으로 붙인다
def get_admin_session(admin_auth: Optional[str] = Cookie(default=None)) -> int:
    exp = _verify_session(admin_auth)
    if not exp:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    return exp

_ADMIN_LOGIN_HTML = """<!doctype html>
<html lang=\"ko\"><head>
<meta charset=\"utf-8\" />
<title>관리자 인증</title>
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
<style>
  html, body { height:100%; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Pretendard', sans-serif; background:#f1f5f9; margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center; padding: 16px; box-sizing: border-box; }
  .card { background:#fff; padding:32px; border-radius:14px; box-shadow:0 8px 30px rgba(0,0,0,0.08); width:340px; margin: auto; }
  h2 { margin:0 0 8px; color:#1E3A5F; font-size:20px; }
  p { color:#64748b; font-size:13px; margin:0 0 18px; }
  input[type=password] { width:100%; padding:12px; font-size:14px; border:1px solid #cbd5e1; border-radius:8px; box-sizing:border-box; }
  button { width:100%; padding:12px; margin-top:14px; background:#1E3A5F; color:#fff; border:none; border-radius:8px; font-weight:700; font-size:14px; cursor:pointer; }
  .err { color:#b91c1c; font-size:13px; margin-top:10px; min-height:18px; }
</style></head>
<body>
  <form class="card" id="loginForm">
    <h2>🔒 관리자 인증</h2>
    <p>업로드 비밀번호를 입력하세요. 8시간 유지됩니다.</p>
    <input type=\"password\" id=\"pw\" placeholder=\"비밀번호\" required autofocus />
    <button type=\"submit\">로그인</button>
    <div class=\"err\" id=\"err\"></div>
  </form>
<script>
document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const pw = document.getElementById('pw').value;
  const err = document.getElementById('err');
  err.textContent = '';
  try {
    const fd = new FormData();
    fd.append('password', pw);
    const r = await fetch('/admin/login', { method: 'POST', body: fd, credentials: 'same-origin' });
    if (r.ok) {
      const next = new URLSearchParams(location.search).get('next') || '/admin/v2';
      location.href = next;
    } else {
      const j = await r.json().catch(()=>({}));
      err.textContent = j.detail || '비밀번호가 올바르지 않습니다.';
    }
  } catch (e) {
    err.textContent = '네트워크 오류';
  }
});
</script>


</body></html>"""

# admin 로그인 화면(HTML) ← release.sh
@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(
    admin_auth: Optional[str] = Cookie(default=None),
    next: Optional[str] = None,
):
    # next 안전성 체크: 반드시 /admin/ 하위만 허용
    safe_next = "/admin/v2"
    if next and next.startswith("/admin/") and "://" not in next:
        safe_next = next
    if _verify_session(admin_auth):
        return RedirectResponse(url=safe_next, status_code=302)
    # HTML 안에 next 값을 script 로 심어서 로그인 성공 후 리다이렉트에 활용
    html = _ADMIN_LOGIN_HTML.replace(
        "</head>",
        "<script>window.__LOGIN_NEXT__ = " + repr(safe_next) + ";</script></head>",
        1,
    )
    return HTMLResponse(content=html)

# admin 비밀번호 확인 → 세션 쿠키 ← release.sh
@app.post("/admin/login")
def admin_login_submit(
    response: Response,
    password: str = Form(...),
    next: Optional[str] = Form(default=None),
):
    if password != UPLOAD_PASSWORD:
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")
    exp = _issue_session_cookie(response)
    safe_next = "/admin/v2"
    if next and next.startswith("/admin/") and "://" not in next:
        safe_next = next
    return {"ok": True, "expires_at": exp, "next": safe_next}

# admin 로그아웃.
@app.post("/admin/logout")
def admin_logout(response: Response):
    response.delete_cookie(ADMIN_SESSION_COOKIE, path="/")
    return {"ok": True}

# admin 세션 시간 연장.
@app.post("/admin/extend")
def admin_extend(
    response: Response,
    admin_auth: Optional[str] = Cookie(default=None),
    _exp: int = Depends(get_admin_session),
):
    # 기존 토큰의 issued_at 보존 → 최대 수명 24시간 강제
    issued_at = None
    if admin_auth:
        try:
            parts = admin_auth.split(".")
            if len(parts) == 3:
                issued_at = int(parts[0])
        except Exception:
            pass
    now = int(time.time())
    if issued_at is not None and now - issued_at >= ADMIN_SESSION_MAX_LIFETIME_SEC:
        raise HTTPException(status_code=401, detail="세션 최대 수명을 초과했습니다. 다시 로그인해 주세요.")
    exp = _issue_session_cookie(response, issued_at=issued_at)
    return {"ok": True, "expires_at": exp, "max_lifetime_remaining": (issued_at + ADMIN_SESSION_MAX_LIFETIME_SEC - now) if issued_at else ADMIN_SESSION_MAX_LIFETIME_SEC}

# admin 세션이 살아 있나 · 남은 시간.
@app.get("/admin/session")
def admin_session_info(_exp: int = Depends(get_admin_session)):
    return {"ok": True, "expires_at": _exp, "ttl_sec": ADMIN_SESSION_TTL_SEC}

# ============================================================
#  유틸 — JSON 파일 읽고 쓰기 · 문서 id · PPT 변환
# ============================================================
def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


# JSON 파일에 적는다. 이 시스템의 "DB 쓰기".
def _write_json(path: Path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# 올라온 파일에 붙일 짧은 id 를 만든다 (12자리).
def _make_doc_id(filename: str) -> str:
    short = hashlib.md5(
        f"{filename}_{datetime.now().isoformat()}".encode("utf-8")
    ).hexdigest()[:12]
    return short


# LibreOffice + Poppler 로 PPTX → PDF → PNG 변환
def _convert_pptx_to_png(pptx_path: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf",
         "--outdir", str(out_dir), str(pptx_path)],
        check=True, capture_output=True,
    )
    pdf_file = out_dir / (pptx_path.stem + ".pdf")
    if not pdf_file.exists():
        raise RuntimeError("PDF 변환 실패")
    subprocess.run(
        ["pdftoppm", "-png", "-r", "150",
         str(pdf_file), str(out_dir / "slide")],
        check=True, capture_output=True,
    )
    # slide-1.png → slide_01.png 정규화
    for p in sorted(out_dir.glob("slide-*.png")):
        num = int(p.stem.split("-")[-1])
        p.rename(out_dir / f"slide_{num:02d}.png")
    try:
        pdf_file.unlink()
    except Exception:
        pass


# 슬라이드별 텍스트 추출
def _extract_text_per_slide(pptx_path: Path):
    from pptx import Presentation
    prs = Presentation(str(pptx_path))
    texts = []
    for slide in prs.slides:
        buf = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                buf.append(shape.text_frame.text)
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        buf.append(cell.text)
        texts.append("\n".join(buf))
    return texts


# 슬라이드별 텍스트(표 제외)와 표를 분리 추출.
def _extract_pptx_text_and_tables(pptx_path: Path):
    from pptx import Presentation
    prs = Presentation(str(pptx_path))
    slide_texts = []
    slide_tables = []
    for slide in prs.slides:
        text_buf = []
        tables_in_slide = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                t = shape.text_frame.text
                if t and t.strip():
                    text_buf.append(t)
            if shape.has_table:
                tbl = shape.table
                rows_data = []
                for row in tbl.rows:
                    rows_data.append([cell.text.strip() for cell in row.cells])
                if rows_data:
                    headers = rows_data[0]
                    body = rows_data[1:] if len(rows_data) > 1 else []
                    tables_in_slide.append({"headers": headers, "rows": body})
        slide_texts.append("\n".join(text_buf))
        slide_tables.append(tables_in_slide)
    return slide_texts, slide_tables


# 주간보고 PPT 글자를 GPT 에 보내 제품별 상태(신호등)를 뽑는다
def _classify_status_with_gpt(slide_texts: list[str]) -> dict:
    if not client:
        return {"products": []}

    joined = "\n\n".join([f"=== Slide {i+1} ===\n{t}" for i, t in enumerate(slide_texts)])

    system_prompt = """너는 반도체 사업부의 임원 보고서 분석 어시스턴트다.
PPT 슬라이드 텍스트를 읽고, 등장하는 모든 프로젝트/제품을 JSON으로 정리한다.

[가장 중요] 사장님이 30초 안에 다 파악할 수 있도록 정리한다.
- summary_bullets: 핵심 3줄 (한 줄 25자 이내, 가장 중요한 사실만)
- sections: 상세 내용 (펼쳤을 때 보임)

규칙:
1. 섹션 구조는 PPT 원문에 등장한 그대로 따른다 (양산/개발/EMA/주차별 출하/Dep챔버진행 등).
2. PPT에 없는 섹션은 만들지 말 것.
3. items는 원문을 가능하면 한 줄로 축약 (불필요한 수식어 제거, 핵심 숫자/일정 유지).
4. notes에는 ※ 또는 참고 사항만.
5. status:
   - RED: 출하 미달, PO 미접수, 자재 쇼티지, 일정 지연 등 즉시 확인
   - BLUE: 진행 중, 정상 추진
   - BLACK: 완료/이슈 없음
6. headline: 가장 중요한 한 줄 (15자 이내 권장).
7. summary_bullets: 핵심 3줄 (정확히 3개, 각 25자 이내).

JSON 스키마:
{
  "products": [
    {
      "name": "프로젝트명",
      "category": "분류",
      "status": "RED|BLUE|BLACK",
      "headline": "핵심 한 줄",
      "summary_bullets": ["요약1", "요약2", "요약3"],
      "header_summary": "상단 요약 (선택)",
      "sections": [
        {"title": "섹션 제목", "items": ["불릿1"], "notes": ["※ 참고"]}
      ]
    }
  ]
}"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"다음 PPT 내용을 정리:\n\n{joined}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"🔴 GPT 분류 실패: {e}")
        return {"products": []}

# 6개월 지난 파일 자동 삭제
def _cleanup_old_files():
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    for base in [UPLOAD_DIR, SLIDES_DIR, SLIDE_IMAGES_DIR, CROPPED_DIR]:
        if not base.exists():
            continue
        for entry in base.iterdir():
            try:
                mtime = datetime.fromtimestamp(entry.stat().st_mtime)
                if mtime < cutoff:
                    if entry.is_dir():
                        shutil.rmtree(entry, ignore_errors=True)
                    else:
                        entry.unlink()
            except Exception:
                continue


# 최신 보고서 저장.
def _update_latest(summary):
    latest = _read_json(LATEST_FILE, [])
    new_doc_id = summary.get("doc_id")

    # 같은 doc_id 있으면 제거하고 새로 추가
    latest = [r for r in latest if r.get("doc_id") != new_doc_id]
    latest.append(summary)

    # 업로드 시각 기준 최신순 정렬, 최대 50개
    latest.sort(
        # 올린 시각으로, 없으면 보고서 날짜로 — 최신이 앞
        key=lambda r: r.get("uploaded_at") or r.get("report_meta", {}).get("date", ""),
        reverse=True
    )
    latest = latest[:50]

    _write_json(LATEST_FILE, latest)

# ============================================================
#  헬스체크 · 자료 버전 — 배포가 갔나, 자료가 바뀌었나
# ============================================================
# 지금 코드의 지문(10자리). /health 로 '배포가 갔나'를 확인할 때 쓴다
def _build_stamp() -> str:
    import hashlib as _hl
    import os as _os
    here = _os.path.dirname(_os.path.abspath(__file__))
    h = _hl.sha256()
    for _n in ("main.py", "admin_v2.html", "division_columns.py",
               "division_form_import.py", "config_loader.py",
               # 파서만 고친 배포에서는 지문이 안 바뀌어서
               # "올라갔나" 를 가릴 수가 없었다. 자주 고치는 읽기 자리를
               # 다 넣는다.
               "dev_schedule_import.py", "revenue_file_import.py",
               "division_revenue.py"):
        try:
            with open(_os.path.join(here, _n), "rb") as _f:
                h.update(_f.read())
        except Exception:
            h.update(b"?")      # 파일이 없어도 서버는 떠야 한다
    return h.hexdigest()[:10]


BUILD = _build_stamp()
BUILD_AT = datetime.now().isoformat(timespec="seconds")


# 서버가 살아 있는지만 답한다 ← backup.sh
@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat(),
            "build": BUILD, "up": BUILD_AT}


# ─ 자료 버전 — 앱이 "새 자료 들어왔나" 묻는 창구 ───────────────
_DATA_VERSION_FILES = (
    "models.json",            # 프로젝트·모델·주차별 계획
    "revenue.json",           # 매출 실적·예상·타겟
    "home_orders.json",       # 사장님 지시사항
    "division_targets.json",  # 사업부별 월 매출 타겟
    "purchases.json",         # 매입·지급
    "overtime.json",          # 잔업·특근
    "notes.json",             # 프로젝트 메모
    "reports_latest.json",    # 주간보고 (PPT)
    "division_app_hidden.json",  # 앱에서 숨긴 사업부
)


# 자료가 바뀌었는지 한 줄로 알려준다 ← 앱 data_version_service.dart fetch()
@app.get("/data-version")
def data_version():
    import hashlib as _hl
    parts, newest = [], 0.0
    for name in _DATA_VERSION_FILES:
        try:
            st = (DATA_DIR / name).stat()
        except OSError:
            parts.append(name + ":-")      # 아직 없는 파일도 상태의 하나다
            continue
        parts.append("%s:%d:%d" % (name, int(st.st_mtime), st.st_size))
        newest = max(newest, st.st_mtime)
    token = _hl.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return JSONResponse(
        {
            "version": token,
            "updated_at": (datetime.fromtimestamp(newest).isoformat()
                           if newest else ""),
        },
        # 중간에 끼어 있는 캐시가 옛 값을 돌려주면 자동 반영이 영원히 안 돈다.
        headers={"Cache-Control": "no-store, max-age=0"},
    )

# ============================================================
#  PPT 업로드 — 주간보고 PPT 를 받아 슬라이드별로 읽는다
# ============================================================
# 올라왔던 파일들의 해시 장부를 읽는다
def _load_upload_hash_index():
    try:
        if not UPLOAD_HASHES_PATH.exists():
            return {}
        return json.loads(UPLOAD_HASHES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

# 해시 장부를 적는다. 실패해도 넘어간다(중복 검사가 느슨해질 뿐).
def _save_upload_hash_index(data):
    try:
        UPLOAD_HASHES_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass

# 전에 올라온 적 있는 파일인가?. 있으면 그때의 파일명·doc_id 를 준다
def _find_duplicate_upload_by_hash(file_hash: str):
    idx = _load_upload_hash_index()
    return idx.get(file_hash)

# 방금 받은 파일을 해시 장부에 적는다
def _record_upload_hash(file_hash: str, saved_name: str, doc_id: str):
    idx = _load_upload_hash_index()
    idx[file_hash] = {
        "filename": saved_name,
        "doc_id": doc_id,
    }
    _save_upload_hash_index(idx)

# 주간보고 PPT 를 받는다. 이 구역에서 제일 중요한 창구.
@app.post("/upload")
async def upload_ppt(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    admin_auth: Optional[str] = Cookie(default=None),
    report_family: str = Form("default"),
    division_id: Optional[str] = Form(None),  # 5-2b: 사업부 사전 매핑 (선택)
    project_id: Optional[str] = Form(None),   # 5-2b: 프로젝트 사전 매핑 (선택)
    allow_duplicate: bool = Form(False),  # 중복 업로드 허용
):
    _has_session = bool(_verify_session(admin_auth))
    if not _has_session and password != UPLOAD_PASSWORD:
        raise HTTPException(status_code=401, detail="비밀번호가 틀립니다.")
    if not file.filename.lower().endswith((".pptx", ".ppt")):
        raise HTTPException(status_code=400, detail=".pptx 또는 .ppt 파일만 업로드 가능합니다.")

    # 파일 내용 읽기 + 해시 계산
    file_bytes = await file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # 중복 업로드 검사 (allow_duplicate 이 False 일 때만 차단)
    duplicate_hit = _find_duplicate_upload_by_hash(file_hash)
    if duplicate_hit and not allow_duplicate:
        return JSONResponse(
            status_code=409,
            content={
                "ok": False,
                "code": "duplicate_upload",
                "detail": "이미 업로드된 파일입니다. 같은 파일을 다시 올리려면 '중복 업로드 허용'을 체크하세요.",
                "duplicate_of": duplicate_hit.get("filename"),
            },
        )

    _cleanup_old_files()

    doc_id = _make_doc_id(file.filename)
    saved_pptx_path = UPLOAD_DIR / f"{doc_id}.pptx"
    saved_pptx_path.write_bytes(file_bytes)
    _record_upload_hash(file_hash, saved_pptx_path.name, doc_id)

    # slides/ 와 slide_images/ 둘 다 저장 (호환성)
    slides_out_dir = SLIDES_DIR / doc_id
    try:
        _convert_pptx_to_png(saved_pptx_path, slides_out_dir)
        # slide_images/ 에도 복사
        slide_images_out = SLIDE_IMAGES_DIR / doc_id
        if not slide_images_out.exists():
            shutil.copytree(slides_out_dir, slide_images_out)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"슬라이드 변환 실패: {e}")

    slide_texts = _extract_text_per_slide(saved_pptx_path)
    gpt_result = _classify_status_with_gpt(slide_texts)
    products = gpt_result.get("products", [])

    section_images = {}
    try:
        section_images = extract_charts_from_pptx(
            pptx_path=saved_pptx_path,
            slides_image_dir=slides_out_dir,
            output_dir=CROPPED_DIR,
            doc_id=doc_id,
        )
        print(f"🟢 차트 자동 추출 완료: {list(section_images.keys())}")
    except Exception as e:
        print(f"🔴 차트 자동 추출 실패: {e}")

    slide_images = {
        str(i + 1): f"/slides/{doc_id}/slide_{i+1:02d}.png"
        for i in range(len(slide_texts))
    }
    # -----------------------------------------------------------
    # 5-2b: 사장님이 사전 지정한 division_id/project_id 폴백 적용
    # -----------------------------------------------------------
    # - 자동 분류 성공 카드: 그대로 유지
    # - 자동 분류 실패 카드만 사장님 의도로 폴백
    if division_id or project_id:
        import config_loader as _cl
        try:
            _cl.reload()
        except Exception:
            pass
        for p in products:
            name = p.get("name") or p.get("product", "")
            category = p.get("category", "")
            text = f"{name} {category}".strip()
            try:
                auto_pid = _cl.classify_project(text)
            except Exception:
                auto_pid = None
            if not auto_pid:
                # 자동 분류 실패한 카드만 폴백
                if project_id:
                    p["_fallback_project_id"] = project_id
                if division_id:
                    p["_fallback_division_id"] = division_id

    summary = {
        "report_meta": {
            "report_family": report_family,
            "date": datetime.now().strftime("%Y-%m-%d"),
        },
        "doc_id": doc_id,
        "file_name": file.filename,
        "upload_timestamp": datetime.now().isoformat(),
        "products": products,
        "section_images": section_images,
        "slide_images": slide_images,
    }
    _update_latest(summary)
    # -----------------------------------------------------------
    # KPI 자동 추출 훅 (신규)
    # -----------------------------------------------------------
    # - 프로파일 등록된 프로젝트만 자동 반영
    # - 실패해도 업로드는 성공
    _kpi_extract_result = _auto_extract_kpi_from_pptx(
        saved_pptx_path,
        file.filename,
        doc_id,
        project_id_hint=project_id,
        products=products,
    )

    return {
        "ok": True,
        "doc_id": doc_id,
        "product_count": len(products),
        "slide_count": len(slide_texts),
        "kpi_auto_extract": _kpi_extract_result,
    }

# ============================================================
#  대시보드 — 신호등 카드
# ============================================================
def _due_status_one(due_raw: str) -> str:
    from datetime import date
    due_raw = (due_raw or "").strip()
    if not due_raw:
        return "BLACK"  # 일정 없음 (내용은 있는데 일정 추출 안 됨)
    try:
        y, m, d = due_raw[:10].split("-")
        due = date(int(y), int(m), int(d))
    except Exception:
        return "BLACK"
    diff = (due - date.today()).days
    if diff < 0:
        return "RED"
    if diff <= 3:
        return "ORANGE"
    return "BLUE"


# 카드 안 items 들의 due_date 들을 보고 가장 위험한 색으로 집계.
def _calc_card_status(card: dict) -> str:
    priority = {"RED": 5, "ORANGE": 4, "BLUE": 3, "GREEN": 2, "BLACK": 1}
    best = "BLACK"
    sections = card.get("sections") or []
    has_sales = False
    for sec in sections:
        # 매출 데이터 감지
        if (sec.get("sales_summary") or "").strip():
            has_sales = True
        for it in (sec.get("items") or []):
            if not isinstance(it, dict):
                continue
            s = _due_status_one(it.get("due_date") or "")
            if priority.get(s, 0) > priority.get(best, 0):
                best = s
                if best == "RED":
                    return best
    # due 상태가 BLACK인데 매출은 있으면 GREEN 승격
    if best == "BLACK" and has_sales:
        return "GREEN"
    return best


# 신호등 카드 ← 앱 dashboard_service.dart
@app.get("/dashboard")
def dashboard():
    from project_templates import _match_project_key  # 키워드 매핑 함수 재사용

    latest = _read_json(LATEST_FILE, [])
    cards = []
    for report in latest:
        report_date = (
            report.get("report_meta", {}).get("date")
            or report.get("report_date")
        )
        report_family = (
            report.get("report_meta", {}).get("report_family")
            or report.get("report_family", "")
        )
        for p in report.get("products", []):
            product_name = p.get("name") or p.get("product", "")
            category = p.get("category", "")
            # 프로젝트 키 매핑 (백엔드 로직 그대로)
            project_key = (
                _match_project_key(product_name)
                or _match_project_key(category)
                or _match_project_key(report_family)
            )
            cards.append({
                "doc_id": report.get("doc_id", ""),
                "product": product_name,
                "status": p.get("status", "BLACK"),
                "headline": p.get("headline", ""),
                "report_date": report_date,
                "report_family": report_family,
                "project_key": project_key,  # ← 추가
            })


    # 🟢 카드별로 division/project 분류 정보 enrichment (기존 필드 변경 없음)
    cards = [enrich_card(c) for c in cards]

    # 🟢 오래된 이슈 카드 필터링 (사급자재/오웬 최종승인)
    cards = [c for c in cards if not any(kw in json.dumps(c, ensure_ascii=False) for kw in ['사급자재', '오웬 최종승인'])]

    # 🟢 주간 보고 노트 카드도 대시보드에 포함
    # 같은 project_key 가 PPT/노트 양쪽에 있으면 노트 카드를 우선
    try:
        notes_data = _load_notes()
        notes_map = notes_data.get("notes", {}) or {}
        note_cards = []
        for div_id, div_notes in notes_map.items():
            report_date = (div_notes or {}).get("report_date", "") or ""
            for nc in (div_notes or {}).get("cards", []) or []:
                if not isinstance(nc, dict):
                    continue
                title = (nc.get("title") or "").strip()
                if not title:
                    continue
                # 카드 제목 → project_key 매칭
                pkey = (nc.get("project_key") or "").strip()
                if not pkey:
                    try:
                        pkey = _cl.classify_project(title) or ""
                    except Exception:
                        pkey = ""

                # headline / summary_bullets 추출
                headline = ""
                bullets = []
                from datetime import date as _date
                due_items = []        # (date, text, raw_str)
                dated_bullets = []    # 날짜 있는 항목만 (앱 카드 본문용)
                highlight_text = ""
                due_date_min = None
                for sec in (nc.get("sections") or []):
                    for it in (sec.get("items") or []):
                        if not isinstance(it, dict):
                            if isinstance(it, str) and len(bullets) < 3:
                                bullets.append(it)
                            continue
                        t = (it.get("type") or "bullet").lower()
                        txt = (it.get("text") or "").strip()
                        if not txt:
                            continue
                        if t == "highlight" and not highlight_text:
                            highlight_text = txt
                        d = (it.get("due_date") or "").strip()
                        if d:
                            try:
                                y, m, dd = d[:10].split("-")
                                due_d = _date(int(y), int(m), int(dd))
                                due_items.append((due_d, txt, d[:10]))
                                dated_bullets.append(f"{txt} ({d[5:10]})")
                                if due_date_min is None or due_d < due_date_min:
                                    due_date_min = due_d
                            except Exception:
                                pass
                        if t in ("bullet", "group_note", "sub") and len(bullets) < 5:
                            bullets.append(txt)

                                # 카드 본문: 날짜 있는 항목 우선, 없으면 일반 bullets 사용
                # 완전히 빈 카드(bullets/highlight/dated/sales 모두 없음)만 스킵
                # sales_summary 가 있으면 매출 카드로 인정
                sales_summary_any = ""
                for _sec in (nc.get("sections") or []):
                    _ss = (_sec or {}).get("sales_summary")
                    if _ss and str(_ss).strip():
                        sales_summary_any = str(_ss).strip()
                        break

                if not dated_bullets and not bullets and not highlight_text and not sales_summary_any:
                    continue

                if dated_bullets:
                    bullets = dated_bullets[:10]
                else:
                    bullets = bullets[:10]

                # 매출만 있는 카드: 요약을 bullets/headline 으로 사용
                if not bullets and sales_summary_any:
                    bullets = [sales_summary_any]

                # headline: summary_bullets[0] 또는 첫 dated bullet 에서 날짜 제거
                def _shorten(txt: str, limit: int = 20) -> str:
                    txt = (txt or "").strip()
                    if len(txt) <= limit:
                        return txt
                    return txt[:limit].rstrip() + "…"

                # headline: due_date_min 항목 우선 선택 후 AI 15자 요약
                headline_src = _pick_headline_source(due_items, due_date_min)
                headline = _ai_headline(headline_src) if headline_src else ""
                # 매출만 있는 카드: headline 을 매출 요약으로 대체
                if not headline and sales_summary_any:
                    headline = sales_summary_any
                due_date_min_str = due_date_min.isoformat() if due_date_min else None

                computed_status = _calc_card_status(nc)
                note_cards.append({
                    "doc_id": f"note:{div_id}",
                    "product": title,
                    "status": computed_status,
                    "headline": headline,
                    "summary_bullets": bullets,
                    "due_date_min": due_date_min_str,
                    "report_date": report_date,
                    "report_family": "weekly_note",
                    "project_key": pkey or None,
                    "division_id": div_id,
                    "from_note": True,
                })

        # enrich (project_key 가 있으면 division/label 등 자동 채움)
        note_cards = [enrich_card(c) for c in note_cards]

        # 🟢 오래된 이슈 카드 필터링 (사급자재/오웬 최종승인)
        note_cards = [c for c in note_cards if not any(kw in json.dumps(c, ensure_ascii=False) for kw in ['사급자재', '오웬 최종승인'])]

        # 대시보드는 노트 카드만 표시 (PPT 카드는 관리자용 텍스트 추출 도구로만)
        cards = note_cards
    except Exception as _e:
        print(f"노트 대시보드 머지 실패: {_e}")
        cards = []

    severity = {"RED": 5, "ORANGE": 4, "BLUE": 3, "GREEN": 2, "GRAY": 2, "BLACK": 1}
    cards.sort(key=lambda c: -severity.get(c["status"], 0))

    # 🟢 project_key 기준 중복 제거 (같은 프로젝트는 1개만 유지)
    # - severity 높은 순으로 정렬되어 있으므로 첫 번째 카드만 남김
    # - project_key 없으면 product(제목)으로 대체
    seen_keys = set()
    deduped = []
    for c in cards:
        key = c.get("project_key") or c.get("product") or ""
        if not key:
            # 키가 없으면 고유 ID로 처리 (중복 아님)
            key = c.get("doc_id", "") or str(id(c))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(c)
    cards = deduped

    # 🟢 모델 단위 그룹핑 (신규 필드, 옛 cards 는 호환을 위해 그대로 유지)
    # --- ESS 합성 카드 주입 (models.json → dashboard 카드) ---
    _models_data = _load_models()
    # -----------------------------------------------------------
    # 반도체 frame 카드 주입
    # -----------------------------------------------------------
    _semi_frame_projects = {"frame": "프레임", "powerbox": "파워박스", "major_module": "메이저모듈"}
    for _pk, _label in _semi_frame_projects.items():
        for _m in _models_data.get("projects", {}).get(_pk, {}).get("models", []):
            if _m.get("group") != "개발":
                continue
            _issues_txt = (_m.get("issues") or "").strip()
            _first_issue = _issues_txt.splitlines()[0] if _issues_txt else ""
            cards.append({
                "doc_id": f"models:{_pk}:{_m.get('id')}",
                "product": _m.get("id") or _m.get("name") or "",
                "status": _m.get("status") or "BLACK",
                "progress": _model_progress(_m),
                "headline": _first_issue,
                "summary_bullets": [
                    f"진행률: {_m.get('progress', 0)}%",
                    f"개발 타입: {_m.get('dev_type', 'HVM')}",
                ] + ([f"이슈: {_issues_txt}"] if _issues_txt else []),
                "due_date_min": _parse_due_text(_m.get("due_text") or ""),
                "report_date": "2026-08-26",
                "report_family": "models",
                "project_key": _pk,
                "project_id": _pk,
                "project_label": _label,
                "project_badge": _label,
                "division_id": "semiconductor",
                "division_label": "반도체사업부",
                "from_note": False,
            })
    # ESS 프로젝트 키는 사업부 양식이 만든 ess_* 하나뿐이다
    # (_ess_legacy_cleanup 주석 참고).
    _ess_projects = {"ess_sdi": "SDI", "ess_fluence": "플루언스",
                     "ess_epc_power": "EPC POWER"}
    for _pk, _label in _ess_projects.items():
        for _m in _models_data.get("projects", {}).get(_pk, {}).get("models", []):
            _issues_txt = (_m.get("issues") or "").strip()
            _first_issue = _issues_txt.splitlines()[0] if _issues_txt else ""
            _remaining = (_m.get("po_qty") or 0) - (_m.get("shipped_qty") or 0)
            cards.append({
                "doc_id": f"models:{_pk}:{_m.get('id')}",
                "product": _m.get("id") or _m.get("name") or "",
                "status": _m.get("status") or "BLACK",
                "progress": _model_progress(_m),
                "headline": _first_issue,
                "summary_bullets": [
                    f"PO 수량: {_m.get('po_qty', 0)} / 출하완료: {_m.get('shipped_qty', 0)} / 잔여: {_remaining}",
                    f"납기: {_m.get('due_text') or '-'}",
                ] + ([f"이슈: {_issues_txt}"] if _issues_txt else []),
                "due_date_min": _parse_due_text(_m.get("due_text") or ""),
                "report_date": "2026-08-21",
                "report_family": "models",
                "project_key": _pk,
                "project_id": _pk,
                "project_label": _label,
                "project_badge": _label,
                "division_id": "ess",
                "division_label": "ESS사업부",
                "from_note": False,
            })

    grouped_cards = _group_dashboard_cards(cards)

    return {"cards": cards, "grouped_cards": grouped_cards}

# ============================================================
#  리포트 목록 · 제품 상세
# ============================================================
def _normalize_project_name(name) -> str:
    if not name:
        return ""
    s = str(name).strip()
    s = re.sub(r"\s+", " ", s)
    # 자주 틀리는 한글 표기 통일 (dedupe 기준값만; 실제 저장/표시 값은 안 바꿈)
    _alias = {
        "메이져": "메이저",
        "메이져모듈": "메이저모듈",
        "매이저": "메이저",
        "매이져": "메이저",
    }
    for k, v in _alias.items():
        s = s.replace(k, v)
    return s


# dedupe용 정렬 키. 최신이 클수록 큰 값.
def _report_sort_key(r: dict):
    if not isinstance(r, dict):
        return ""
    for k in ("uploaded_at", "created_at"):
        v = r.get(k)
        if v:
            return str(v)
    parsed = r.get("parsed") or {}
    d = parsed.get("date") or (r.get("report_meta") or {}).get("date") or ""
    return str(d)


# 같은 프로젝트명이 여러 카드에 있으면 최신 것만 남긴다
def _dedupe_cards_by_project(cards: list) -> list:
    if not cards:
        return []
    best = {}
    for c in cards:
        if not isinstance(c, dict):
            continue
        parsed = c.get("parsed") or {}
        projs = parsed.get("projects") or []
        proj = _normalize_project_name(projs[0] if projs else "")
        if not proj:
            # 프로젝트명 없는 카드는 doc_id 로 유지
            proj = "__no_project__" + str(c.get("doc_id", ""))
        key = proj
        prev = best.get(key)
        if prev is None or _report_sort_key(c) > _report_sort_key(prev):
            best[key] = c
    # 최신순 정렬
    out = list(best.values())
    out.sort(key=_report_sort_key, reverse=True)
    return out


# 한 리포트에 여러 프로젝트가 들어있으면 프로젝트 단위 카드로 분리.
def _split_report_by_project(r_enriched: dict) -> list:
    parsed = (r_enriched or {}).get("parsed") or {}
    projects = parsed.get("projects") or []
    week_num = (r_enriched or {}).get("week_override") or parsed.get("week")
    overrides = (r_enriched or {}).get("project_overrides") or {}
    def _resolve(name):
        return overrides.get(name, name)
    if len(projects) <= 1:
        # 단일 카드도 override 반영
        if projects:
            proj = _resolve(projects[0])
            new_parsed = dict(parsed)
            new_parsed["projects"] = [proj]
            new_parsed["week"] = week_num
            new_title = proj + (" · W" + str(week_num) + " 주간보고" if week_num else "")
            new_parsed["display_title"] = new_title
            r_enriched = dict(r_enriched)
            r_enriched["parsed"] = new_parsed
            r_enriched["display_title"] = new_title
            r_enriched["_split_project"] = projects[0]  # 원본 이름을 키로 유지
        return [r_enriched]
    cards = []
    for proj in projects:
        clone = dict(r_enriched)
        display_proj = _resolve(proj)
        new_parsed = dict(parsed)
        new_parsed["projects"] = [display_proj]
        new_parsed["week"] = week_num
        new_title = display_proj
        if week_num:
            new_title += " · W" + str(week_num) + " 주간보고"
        new_parsed["display_title"] = new_title
        clone["parsed"] = new_parsed
        clone["display_title"] = new_title
        clone["_split_project"] = proj  # 원본 이름을 키로 유지 (override 저장에 사용)
        cards.append(clone)
    return cards


# 업로드 후 경과 시간과 report_date 기준 상태 분류.
def _classify_report_status(upload_timestamp: str, report_date: str) -> dict:
    from datetime import datetime as _dt, timedelta as _td
    now = _dt.now()

    status = "published"
    d_day = None

    try:
        if upload_timestamp:
            ts = _dt.fromisoformat(upload_timestamp)
            if now - ts < _td(minutes=5):
                status = "ai_processing"
    except Exception:
        pass

    try:
        if report_date and status != "ai_processing":
            rd = _dt.strptime(report_date, "%Y-%m-%d").date()
            today = now.date()
            delta = (rd - today).days
            d_day = delta
            if delta >= 0:
                status = "review_pending"
            else:
                status = "published"
    except Exception:
        pass

    return {"status": status, "d_day": d_day}


# 올라온 주간보고 목록 ← admin v2 getISOWeek()
@app.get("/reports")
def list_reports():
    raw = _read_json(LATEST_FILE, [])
    enriched = []
    for r in (raw or []):
        try:
            if (r or {}).get("hidden") is True:
                continue
            meta = (r or {}).get("report_meta") or {}
            fname = (r or {}).get("file_name") or ""
            parsed = _parse_report_filename(fname, meta.get("date", ""))
            manual_projs = (r or {}).get("manual_projects")
            if manual_projs:
                parsed = dict(parsed)
                parsed["projects"] = list(manual_projs)
            mw = (r or {}).get("week_override")
            if mw:
                parsed["week"] = mw
            if parsed.get("projects"):
                _wk = parsed.get("week")
                parsed["display_title"] = ", ".join(parsed["projects"]) + (" · W" + str(_wk) + " 주간보고" if _wk else "")
            classified = _classify_report_status(
                (r or {}).get("upload_timestamp", ""),
                parsed.get("date") or meta.get("date", "")
            )
            r_enriched = dict(r or {})
            r_enriched["parsed"] = parsed
            r_enriched["display_title"] = parsed.get("display_title", "")
            r_enriched["report_status"] = classified.get("status", "published")
            r_enriched["d_day"] = classified.get("d_day")
            enriched.append(r_enriched)
        except Exception:
            enriched.append(r)
    split_cards = []
    for e in enriched:
        try:
            split_cards.extend(_split_report_by_project(e))
        except Exception:
            split_cards.append(e)
    split_cards = _dedupe_cards_by_project(split_cards)
    return {"reports": split_cards}


# 제품 단위 상세 (기존 카드 탭용) ← admin v2 executeDelete() · __moreBtn.onclick() · _loadSalesForSection() 외
@app.get("/reports/{doc_id}/{product_name}")
def get_product_detail(doc_id: str, product_name: str):
    latest = _read_json(LATEST_FILE, [])
    for report in latest:
        if report.get("doc_id") != doc_id:
            continue
        for p in report.get("products", []):
            name = p.get("product") or p.get("name", "")
            if name == product_name:
                return {
                    "doc_id": doc_id,
                    "report_date": (
                        report.get("report_meta", {}).get("date")
                        or report.get("report_date")
                    ),
                    "slide_images": report.get("slide_images", {}),
                    "section_images": report.get("section_images", {}),
                    **p,
                }
    raise HTTPException(status_code=404, detail="제품을 찾을 수 없습니다.")


_APP_RELEASE_HTML = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>앱 배포 · OneView Admin</title>
<style>
:root{--navy:#0E2841;--line:#E5E7EB;--t1:#111827;--t2:#4B5563;--t3:#6B7280;
      --hint:#9CA3AF;--blue:#2563EB;--red:#DC2626;--green:#059669;--soft:#F1F5F9}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Malgun Gothic','Apple SD Gothic Neo',sans-serif;
     background:#F8FAFC;color:var(--t1);padding:28px 16px 60px}
.wrap{max-width:660px;margin:0 auto}
h1{font-size:19px;font-weight:700;color:var(--navy)}
.sub{font-size:13px;color:var(--t3);margin:6px 0 20px}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:14px}
.card h2{font-size:14px;font-weight:700;margin-bottom:14px}
.row{display:flex;align-items:center;padding:7px 0;font-size:13px;border-bottom:1px solid #F1F5F9}
.row:last-child{border-bottom:0}
.row b{width:132px;color:var(--t3);font-weight:500;flex:0 0 auto}
.row span{flex:1;text-align:right;font-weight:600}
label{display:block;font-size:12.5px;color:var(--t2);font-weight:600;margin:12px 0 5px}
input[type=text],input[type=number],textarea{width:100%;border:1px solid var(--line);border-radius:8px;
  padding:9px 11px;font-size:13.5px;font-family:inherit;color:var(--t1)}
textarea{min-height:82px;resize:vertical;line-height:1.5}
input[type=file]{font-size:13px;margin-top:4px}
.chk{display:flex;align-items:center;gap:8px;margin-top:14px;font-size:13px;color:var(--t2)}
.btn{margin-top:18px;width:100%;border:0;border-radius:9px;background:var(--navy);color:#fff;
  padding:12px;font-size:14px;font-weight:700;cursor:pointer;font-family:inherit}
.btn:disabled{opacity:.55;cursor:default}
.warn{background:#FFFBEB;border:1px solid #FDE68A;color:#78350F;border-radius:9px;
  padding:11px 13px;font-size:12.5px;line-height:1.6;margin-bottom:14px}
.msg{margin-top:13px;font-size:13px;font-weight:600;line-height:1.5}
.ok{color:var(--green)} .err{color:var(--red)}
.bar{height:6px;border-radius:3px;background:var(--soft);overflow:hidden;margin-top:13px;display:none}
.bar>i{display:block;height:100%;background:var(--blue);width:0}
a.back{display:inline-block;margin-bottom:14px;font-size:13px;color:var(--blue);text-decoration:none}
</style></head><body><div class="wrap">
<a class="back" href="/admin/v2">‹ 관리자로</a>
<h1>앱 배포</h1>
<p class="sub">APK 를 올리면 바로 반영됩니다. 서버를 다시 배포할 필요 없습니다.</p>

<div class="card"><h2>지금 서버가 내주는 버전</h2><div id="cur">불러오는 중…</div></div>

<div class="card">
  <h2>새 버전 올리기</h2>
  <div class="warn">
    <b>버전 코드는 반드시 올려야 합니다.</b> 안드로이드는 같거나 낮은 번호의 APK 를
    기존 앱 위에 설치하지 않고, 이유도 알려주지 않습니다.<br>
    APK 를 만든 <b>서명 키</b>가 지금 깔린 앱과 달라도 설치가 막힙니다.
  </div>
  <form id="f">
    <label>APK 파일</label>
    <input type="file" name="file" accept=".apk" id="file">
    <label>버전 (예: 2.3.0)</label>
    <input type="text" name="latest_version" id="ver" placeholder="2.3.0">
    <label>버전 코드 (pubspec 의 + 뒤 숫자)</label>
    <input type="number" name="latest_version_code" id="code" placeholder="23">
    <label>변경 내용 — 앱 팝업에 그대로 보입니다</label>
    <textarea name="release_notes" id="notes" placeholder="무엇이 바뀌었는지 한두 줄"></textarea>
    <div class="chk"><input type="checkbox" id="force"> <span>강제 업데이트 (끄지 못하게)</span></div>
    <div class="bar" id="bar"><i></i></div>
    <button class="btn" id="go" type="submit">올리기</button>
    <div class="msg" id="msg"></div>
  </form>
</div>
</div>
<script>
var E=function(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});};
function mb(n){return n>0?(n/1048576).toFixed(1)+' MB':'-';}
function load(){
  fetch('/admin/app/release',{credentials:'same-origin'})
   .then(function(r){return r.json();})
   .then(function(d){
     var v=d.version||{},a=d.apk||{};
     document.getElementById('cur').innerHTML =
       '<div class="row"><b>버전</b><span>'+E(v.latest_version)+' (코드 '+E(v.latest_version_code)+')</span></div>'+
       '<div class="row"><b>받는 곳</b><span>'+E(v.download_url)+'</span></div>'+
       '<div class="row"><b>서버의 APK</b><span>'+(a.exists?mb(a.bytes)+' · '+E(a.uploaded_at):'없음')+'</span></div>'+
       '<div class="row"><b>강제 업데이트</b><span>'+(v.force_update?'켬':'끔')+'</span></div>'+
       '<div class="row"><b>변경 내용</b><span>'+E(v.release_notes||'-')+'</span></div>';
     if(!document.getElementById('ver').value) document.getElementById('ver').value=v.latest_version||'';
     if(!document.getElementById('code').value)
       document.getElementById('code').value=(parseInt(v.latest_version_code||0,10)+1);
   })
   .catch(function(e){document.getElementById('cur').textContent='불러오지 못했습니다: '+e.message;});
}
load();
document.getElementById('f').onsubmit=function(ev){
  ev.preventDefault();
  var msg=document.getElementById('msg'), go=document.getElementById('go');
  var bar=document.getElementById('bar'), fi=bar.firstChild;
  msg.textContent=''; msg.className='msg';
  var fd=new FormData();
  var f=document.getElementById('file').files[0];
  if(f) fd.append('file',f);
  fd.append('latest_version',document.getElementById('ver').value);
  fd.append('latest_version_code',document.getElementById('code').value);
  fd.append('release_notes',document.getElementById('notes').value);
  fd.append('force_update',document.getElementById('force').checked?'true':'false');
  go.disabled=true; go.textContent='올리는 중…'; bar.style.display='block';
  var x=new XMLHttpRequest();
  x.open('POST','/admin/app/release');
  x.withCredentials=true;
  x.upload.onprogress=function(e){ if(e.lengthComputable) fi.style.width=(e.loaded/e.total*100)+'%'; };
  x.onload=function(){
    go.disabled=false; go.textContent='올리기'; bar.style.display='none'; fi.style.width='0';
    var d={}; try{ d=JSON.parse(x.responseText); }catch(e){}
    if(x.status===200 && d.ok){
      msg.className='msg ok';
      msg.textContent='올렸습니다. '+(d.apk_bytes?mb(d.apk_bytes)+' · ':'')+'앱을 켜면 팝업이 뜹니다.';
      document.getElementById('file').value='';
      load();
    }else{
      msg.className='msg err';
      msg.textContent='실패: '+(d.detail||('HTTP '+x.status));
    }
  };
  x.onerror=function(){
    go.disabled=false; go.textContent='올리기'; bar.style.display='none';
    msg.className='msg err'; msg.textContent='실패: 연결이 끊겼습니다';
  };
  x.send(fd);
};
</script></body></html>"""


# ============================================================
#  모델 데이터 백업
# ============================================================
# models.json 자동 백업 파일 목록 (최신부터).
def _models_backups():
    import glob
    out = []
    for path in sorted(glob.glob(f"{MODELS_FILE}.auto_*"), reverse=True):
        try:
            st = os.stat(path)
            out.append({"name": os.path.basename(path), "bytes": st.st_size,
                        "at": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
        except Exception:
            pass
    return out


# 프로젝트별로 무엇이 몇 개 들어 있는지.
def _models_shape(data: dict) -> dict:
    out = {}
    for key, proj in (data.get("projects") or {}).items():
        ms = (proj or {}).get("models") or []
        if not ms:
            continue
        weeks = {}
        for m in ms:
            for mon, wk in ((m.get("weekly_plan") or {}) if isinstance(m, dict) else {}).items():
                weeks[str(mon)] = weeks.get(str(mon), 0) + len(wk or {})
        out[key] = {
            "models": len(ms),
            "weeks": dict(sorted(weeks.items())),
            "process": sum(1 for m in ms if isinstance(m, dict) and (m.get("process") or [])),
            "po": sum(1 for m in ms if isinstance(m, dict) and m.get("po_qty")),
        }
    return out


# 백업 목록. name 을 주면 그 백업 안이 어떤 모양인지 같이 보여준다
@app.get("/admin/models/backups")
def admin_models_backups(name: str = "", _admin: int = Depends(get_admin_session)):
    out = {"ok": True, "current": _models_shape(_load_models()),
           "backups": _models_backups()}
    if name:
        path = MODELS_FILE.parent / os.path.basename(name)
        if not path.exists() or ".auto_" not in path.name:
            raise HTTPException(status_code=404, detail="그런 백업이 없습니다")
        with open(path, "r", encoding="utf-8") as f:
            out["shape"] = _models_shape(json.load(f))
        out["name"] = path.name
    return out


# 백업으로 되돌린다. payload = {name, projects?: [키...]}
@app.post("/admin/models/restore")
def admin_models_restore(payload: dict, _admin: int = Depends(get_admin_session)):
    name = os.path.basename(str(payload.get("name") or ""))
    if not name or ".auto_" not in name:
        raise HTTPException(status_code=400, detail="백업 이름이 필요합니다")
    path = MODELS_FILE.parent / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="그런 백업이 없습니다")
    with open(path, "r", encoding="utf-8") as f:
        old = json.load(f)

    want = [str(k) for k in (payload.get("projects") or []) if str(k).strip()]
    data = _load_models()
    changed = []
    for key, proj in (old.get("projects") or {}).items():
        if want and key not in want:
            continue
        data.setdefault("projects", {})[key] = proj
        changed.append(key)
    if not changed:
        raise HTTPException(status_code=400, detail="되돌릴 프로젝트가 없습니다")
    _save_models(data)
    print(f"[restore] {name} → {', '.join(changed)}")
    return {"ok": True, "from": name, "projects": changed,
            "shape": _models_shape(data)}

# ============================================================
#  앱 배포 — APK · 버전 · 변경 내역
# ============================================================
# APK 올리는 화면. 배포 없이 새 버전을 내보낼 수 있다
@app.get("/admin/app", response_class=HTMLResponse)
def admin_app_page(admin_auth: Optional[str] = Cookie(default=None)):
    if not _verify_session(admin_auth):
        return RedirectResponse(url="/admin/login?next=/admin/app", status_code=302)
    return HTMLResponse(_APP_RELEASE_HTML)


# ============================================================
#  앱 배포
# ============================================================
# APK 와 버전 파일은 볼륨(/data)에 둔다
APP_VERSION_FILE = DATA_DIR / "app_version.json"
APP_VERSION_SEED = BASE_DIR / "app_version.json"   # 볼륨에 없으면 이걸 쓴다
APP_APK_FILE = DATA_DIR / "app_release.apk"

APP_VERSION_FALLBACK = {
    "latest_version": "1.0.0",
    "latest_version_code": 1,
    "download_url": "/app/download",
    "release_notes": "",
    "force_update": False,
}


# 볼륨과 이미지 중 버전 코드가 더 높은 쪽.
def _read_app_version() -> dict:
    best, best_code = None, -1
    for path in (APP_VERSION_FILE, APP_VERSION_SEED):
        try:
            if not path.exists():
                continue
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if not (isinstance(d, dict) and d):
                continue
            code = _as_int(d.get("latest_version_code"), 0)
            if code > best_code:
                best, best_code = d, code
        except Exception as e:
            print(f"[APP_VERSION] {path} 읽기 실패: {e}")
    return dict(best) if best else dict(APP_VERSION_FALLBACK)


# 변경 내역 (CHANGELOG.md)
_CHANGELOG_FILE = BASE_DIR / "CHANGELOG.md"
_CHANGELOG_FILE_ALT = BASE_DIR.parent / "CHANGELOG.md"


# '## 2.3.10 — 2026-09-16' 단위로 쪼갠다
def _parse_changelog(text: str) -> list:
    import re as _re
    out = []
    cur = None
    for line in (text or "").split("\n"):
        # '## 2.3.10 — 2026-09-16' 도 '## 2.3.9 이전' 도 받는다
        m = _re.match(r"^##\s+(\S+)\s*(.*?)\s*$", line.rstrip())
        if m:
            if cur:
                out.append(cur)
            cur = {"version": m.group(1).strip(),
                   "date": _re.sub(r"^[—–-]\s*", "", (m.group(2) or "").strip()),
                   "body": []}
            continue
        if cur is not None:
            cur["body"].append(line)
    if cur:
        out.append(cur)
    for e in out:
        e["body"] = "\n".join(e["body"]).strip()
    return [e for e in out if e["body"]]


# CHANGELOG.md 를 읽는다 (앱 '변경 내역' · 업데이트 팝업).
def _load_changelog() -> list:
    for path in (_CHANGELOG_FILE, _CHANGELOG_FILE_ALT):
        try:
            if path.exists():
                return _parse_changelog(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[CHANGELOG] {path} 읽기 실패: {e}")
    return []


# 그 버전의 본문. 없으면 빈 문자열.
def _changelog_for(version: str) -> str:
    v = str(version or "").strip().lstrip("vV")
    for e in _load_changelog():
        if e["version"].lstrip("vV") == v:
            return e["body"]
    return ""


# 설정 화면의 '변경 내역'. 최신 버전부터 ← 앱 changelog_screen.dart initState()
@app.get("/app/changelog")
def get_app_changelog(limit: int = 20):
    try:
        n = max(1, min(100, int(limit)))
    except (TypeError, ValueError):
        n = 20
    items = _load_changelog()[:n]
    return {"current": _read_app_version().get("latest_version") or "",
            "count": len(items), "items": items}


# 앱 시작 시 호출. 최신 버전 정보 반환 ← 앱 app_updater.dart _fromServer()
@app.get("/app/version")
def get_app_version():
    data = dict(_read_app_version())
    # 노트는 CHANGELOG.md 가 정본이다. app_version.json 의 release_notes 는
    # 한 줄뿐이라 버전을 올려도 안 고치면 옛 노트가 그대로 나갔다.
    _note = _changelog_for(data.get("latest_version"))
    if _note:
        data["release_notes"] = _note
    # APK 가 서버에 올라와 있으면 받는 곳을 서버로 돌린다.
    # (비공개 저장소의 릴리스 주소는 앱이 못 받는다 — 404 가 난다)
    _ready = APP_APK_FILE.exists() or (BASE_DIR / "app_release.apk").exists()
    if _ready:
        data["download_url"] = "/app/download"
        data["apk_url"] = "/app/download"
    data["apk_ready"] = bool(_ready)
    return data


# 최신 APK 다운로드 ← release.sh
@app.get("/app/download")
def download_app_apk():
    from fastapi.responses import FileResponse
    for apk_path in (APP_APK_FILE, BASE_DIR / "app_release.apk"):
        if apk_path.exists():
            return FileResponse(
                path=str(apk_path),
                media_type="application/vnd.android.package-archive",
                filename="app_release.apk",
            )
    raise HTTPException(status_code=404, detail="APK not uploaded yet")


# 지금 서버가 내주고 있는 버전과 APK 상태 ← release.sh
@app.get("/admin/app/release")
def admin_app_release(_admin: int = Depends(get_admin_session)):
    size = APP_APK_FILE.stat().st_size if APP_APK_FILE.exists() else 0
    mtime = ""
    if APP_APK_FILE.exists():
        mtime = datetime.fromtimestamp(
            APP_APK_FILE.stat().st_mtime).isoformat(timespec="seconds")
    return {
        "ok": True,
        "version": _read_app_version(),
        "apk": {"exists": APP_APK_FILE.exists(), "bytes": size,
                "uploaded_at": mtime},
    }


# 새 APK 와 버전 정보를 올린다 ← release.sh
@app.post("/admin/app/release")
async def admin_app_release_upload(
    file: UploadFile = File(None),
    latest_version: str = Form(""),
    latest_version_code: int = Form(0),
    release_notes: str = Form(""),
    force_update: bool = Form(False),
    _admin: int = Depends(get_admin_session),
):
    cur = _read_app_version()
    ver = (latest_version or "").strip() or cur.get("latest_version", "1.0.0")
    code = int(latest_version_code or 0) or _as_int(cur.get("latest_version_code"), 1)
    old_code = _as_int(cur.get("latest_version_code"), 0)
    # 같은 코드로 다시 올리는 건 둔다 — 망친 빌드를 갈아 끼울 때 쓴다.
    # (앱은 '더 높을 때만' 팝업을 띄우므로 이미 받은 사람을 괴롭히지 않는다)
    if code < old_code:
        raise HTTPException(
            status_code=400,
            detail=f"버전 코드를 낮출 수 없습니다. 지금 {old_code}, 받은 값 {code}")

    wrote = 0
    if file is not None and (file.filename or ""):
        if not (file.filename or "").lower().endswith(".apk"):
            raise HTTPException(status_code=400, detail="apk 파일만 올릴 수 있습니다")
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="빈 파일입니다")
        # 받다 끊겨도 멀쩡한 APK 가 남아 있게, 다 받은 뒤에 바꿔 끼운다.
        tmp = APP_APK_FILE.with_suffix(".apk.part")
        tmp.write_bytes(raw)
        tmp.replace(APP_APK_FILE)
        wrote = len(raw)

    data = dict(cur)
    data.update({
        "latest_version": ver,
        "latest_version_code": code,
        "download_url": "/app/download",
        "apk_url": "/app/download",
        "release_notes": release_notes if release_notes.strip() else cur.get("release_notes", ""),
        "force_update": bool(force_update),
    })
    APP_VERSION_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[APP_VERSION] {ver}+{code} 등록, APK {wrote} bytes")
    return {"ok": True, "version": data, "apk_bytes": wrote,
            "apk_exists": APP_APK_FILE.exists()}


NOTES_FILE = DATA_DIR / "notes.json"

# ============================================================
#  노트 저장소
# ============================================================
def _load_notes() -> dict:
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": 1, "updated_at": None, "notes": {}}


# 사업부 노트(notes.json)를 저장한다
def _save_notes(data: dict) -> None:
    from datetime import datetime
    data["updated_at"] = datetime.now().isoformat()
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── 프로젝트 모델 (양산/개발 구조) 헬퍼 ───
MODELS_FILE = DATA_DIR / "models.json"

#: 볼륨이 비었을 때 한 번 쓰는 씨앗. 저장소에 커밋된 사본이라 운영 중에는
#: 읽히지도 쓰이지도 않는다. 이름이 models.json 이던 때는 저장소 파일을 열어
#: 보고 "데이터가 왜 두 달 전이지" 하게 됐다.
SEED_MODELS_FILE = BASE_DIR / "models.seed.json"
_seed_warned = False


# 운영 파일을 읽은 것 한 벌. 파일이 바뀐 시각이 열쇠다
_MODELS_CACHE: dict = {"key": None, "data": None}

# ============================================================
#  모델 저장소 (models.json) — 모든 프로젝트·모델 자료
# ============================================================
def _load_models() -> dict:
    global _seed_warned
    # -----------------------------------------------------------
    # 한 번 읽은 것을 다시 쓴다
    # -----------------------------------------------------------
    # 캐시를 보는 일은 **try 밖**에서 한다
    _ck = None
    if MODELS_FILE.exists():
        try:
            _st = MODELS_FILE.stat()
            _ck = (_st.st_mtime_ns, _st.st_size)
        except OSError:
            _ck = None
        if _ck is not None and _MODELS_CACHE.get("key") == _ck \
                and _MODELS_CACHE.get("data") is not None:
            return _MODELS_CACHE["data"]
    if MODELS_FILE.exists():
        try:
            with open(MODELS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if _ck is not None:
                _MODELS_CACHE["key"] = _ck
                _MODELS_CACHE["data"] = data
            return data
        except Exception as _e:
            print(f"[models] !! {MODELS_FILE} 를 읽지 못했습니다: {_e}")
    if SEED_MODELS_FILE.exists():
        if not _seed_warned:
            _seed_warned = True
            print("=" * 64)
            print(f"[models] !! 운영 데이터가 없습니다: {MODELS_FILE}")
            print(f"[models] !! 씨앗으로 돌아갑니다: {SEED_MODELS_FILE.name}")
            print("[models] !! 볼륨이 안 붙었거나 비었을 수 있습니다. 확인하세요.")
            print("=" * 64)
        try:
            with open(SEED_MODELS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as _e:
            print(f"[models] !! 씨앗도 읽지 못했습니다: {_e}")
    return {"version": 1, "updated_at": None, "projects": {}}


# 모든 프로젝트·모델 자료(models.json)를 저장한다
def _save_models(data: dict) -> None:
    from datetime import datetime
    # 덮어쓰기 전에 직전 파일을 백업해 둔다. 엑셀 업로드 한 번에 모델이 통째로
    # 바뀔 수 있어서, 되돌릴 수단이 없으면 위험하다. 최근 10개만 보관.
    try:
        import shutil, glob, os as _os
        if _os.path.exists(MODELS_FILE):
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(MODELS_FILE, f"{MODELS_FILE}.auto_{stamp}")
            olds = sorted(glob.glob(f"{MODELS_FILE}.auto_*"))
            for p in olds[:-10]:
                try:
                    _os.remove(p)
                except Exception:
                    pass
    except Exception as _e:
        print(f"[save_models] 백업 실패(무시): {_e}")
    data["updated_at"] = datetime.now().isoformat()
    # 운영 파일을 직접 열어서 쓰지 않는다
    tmp = f"{MODELS_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, MODELS_FILE)
    # 방금 쓴 것이 곧 최신이다. 여기서 안 맞춰 두면 다음 읽기가 파일을
    # 다시 파싱한다 — 아끼려던 자리를 도로 쓴다.
    try:
        _st = MODELS_FILE.stat()
        _MODELS_CACHE["key"] = (_st.st_mtime_ns, _st.st_size)
        _MODELS_CACHE["data"] = data
    except OSError:
        _MODELS_CACHE["key"] = None
    _pj = {k: len(v.get("models", [])) for k, v in data.get("projects", {}).items()}
    print(f"[save_models] wrote {MODELS_FILE} | projects={len(_pj)} | {_pj}")


# ==== ESS 프로젝트가 두 벌이던 것을 한 벌로
_ESS_LEGACY = {"sdi": "ess_sdi", "fluence": "ess_fluence", "epc_power": "ess_epc_power"}
_ess_legacy_done = False

# ============================================================
#  옛 자료 정리 — ESS 옛 키 · 자동차 수주 합치기 (서버 켤 때)
# ============================================================
def _ess_legacy_cleanup() -> list:
    global _ess_legacy_done
    if _ess_legacy_done:
        return []
    _ess_legacy_done = True
    data = _load_models()
    projs = data.get("projects") or {}
    dropped = []
    for old, new in _ESS_LEGACY.items():
        if old not in projs:
            continue
        if not (projs.get(new) or {}).get("models"):
            print(f"[ess] {old} 는 그대로 둡니다 — {new} 에 품목이 없습니다")
            continue
        projs.pop(old, None)
        dropped.append(old)
    if dropped:
        _save_models(data)
        print(f"[ess] 옛 ESS 프로젝트를 지웠습니다: {dropped}")
    return dropped


# ==== 자동차 수주 자료를 양식 품목으로 옮긴다

# (원본 프로젝트, 원본 품목 id, 옮길 프로젝트, 옮길 품목 id)
_AUTO_ORDER_MOVE = [
    ("auto_schaeffler", "SVCT", "automotive_schaeffler", "AAA9543030400"),
    ("auto_schaeffler", "OV1", "automotive_schaeffler", "AAA9550840300"),
    ("auto_stellantis", "오일펌프하우징", "automotive_stellantis", "68666525AA"),
    ("auto_kefico", "V2LC HOUSING", "automotive_kefico_vn", "9191030001"),
    ("auto_kefico", "OBC HOUSING", "automotive_kefico_india", "9091060001"),
    ("auto_kefico", "EREV ICCU HOUSING", "automotive_kefico_india", "9091100001"),
]
# 짝을 가릴 수 없어 버리는 것 (민님 지시)
_AUTO_ORDER_DROP = [
    ("auto_kefico", "DCDC HOUSING"),
    ("auto_kefico", "HE ICCU ASSY"),
    ("auto_valeo", "DCDC HOUSING"),
]
_AUTO_ORDER_PROJECTS = ["auto_schaeffler", "auto_kefico",
                        "auto_stellantis", "auto_valeo"]
# 오타로 하나 더 생긴 프로젝트 → 본체
_AUTO_DUP_PROJECT = ("automotive_schaefller", "automotive_schaeffler")
_auto_order_done = False


# 수주 자료를 양식 품목에 얹고 auto_* 를 지운다
def _auto_order_merge() -> dict:
    global _auto_order_done
    if _auto_order_done:
        return {}
    _auto_order_done = True
    data = _load_models()
    projs = data.get("projects") or {}

    def _pick(pk, mid):
        for m in (projs.get(pk) or {}).get("models") or []:
            if isinstance(m, dict) and str(m.get("id") or "") == mid:
                return m
        return None

    moved, missing = [], []
    for spk, smid, tpk, tmid in _AUTO_ORDER_MOVE:
        src = _pick(spk, smid)
        if src is None or not src.get("auto"):
            continue                      # 이미 옮겼거나 없다
        tgt = _pick(tpk, tmid)
        if tgt is None:
            missing.append("%s/%s" % (tpk, tmid))
            continue
        if tgt.get("auto"):
            continue                      # 이미 있다 — 덮지 않는다
        blk = dict(src["auto"])
        # 수주 엑셀에 적힌 제품명을 남긴다. 양식 이름과 다른 경우가 있다
        # (오일펌프하우징 ↔ Oil pump) — 어디서 온 숫자인지 알아야 한다.
        blk.setdefault("product", src.get("name") or smid)
        tgt["auto"] = blk
        moved.append("%s/%s → %s/%s" % (spk, smid, tpk, tmid))

    if missing:
        print("[auto] 얹을 자리를 못 찾아 아무것도 지우지 않습니다: %s" % missing)
        if moved:
            _save_models(data)
        return {"moved": moved, "missing": missing}

    dropped = ["%s/%s" % (k, m) for k, m in _AUTO_ORDER_DROP if _pick(k, m)]
    removed = [k for k in _AUTO_ORDER_PROJECTS if projs.pop(k, None) is not None]

    # 오타 프로젝트 — 본체에 같은 품목이 같은 숫자로 있을 때만 지운다
    dup, keep = _AUTO_DUP_PROJECT
    dup_removed = ""
    if dup in projs:
        dms = [m for m in (projs.get(dup) or {}).get("models") or []
               if isinstance(m, dict)]
        kby = {str(m.get("id") or ""): m
               for m in (projs.get(keep) or {}).get("models") or []
               if isinstance(m, dict)}
        same = bool(dms) and all(
            str(m.get("id") or "") in kby
            and kby[str(m.get("id") or "")].get("po_qty") == m.get("po_qty")
            and kby[str(m.get("id") or "")].get("shipped_qty") == m.get("shipped_qty")
            for m in dms)
        if same:
            projs.pop(dup, None)
            dup_removed = dup
            # 프로젝트 목록에서는 **지우지 않고 끈다** (set_project_visible
            # 주석 참고 — 이름이 다시 올 수 있다).
            try:
                _cl.set_project_visible(dup, False, "dup_of_%s" % keep)
            except Exception as _e:
                print("[auto] %s 숨기기 실패(무시): %s" % (dup, _e))
        else:
            print("[auto] %s 는 그대로 둡니다 — %s 와 숫자가 다릅니다" % (dup, keep))

    if moved or removed or dup_removed:
        _save_models(data)
        print("[auto] 수주 얹음 %d · 버림 %d · 프로젝트 삭제 %s %s"
              % (len(moved), len(dropped), removed, dup_removed))
    return {"moved": moved, "dropped": dropped,
            "removed": removed, "dup": dup_removed}


# 서버가 켜질 때 저절로 돈다
@app.on_event("startup")
def _ess_legacy_cleanup_on_startup() -> None:
    # 뜨자마자 한 번. 여기서 터져도 서버는 떠야 하니 전부 감싼다.
    try:
        _ess_legacy_cleanup()
    except Exception as _e:
        print(f"[ess] 옛 프로젝트 정리 실패(무시): {_e}")
    try:
        _auto_order_merge()
    except Exception as _e:
        print(f"[auto] 수주 자료 정리 실패(무시): {_e}")

# ============================================================
#  모델 한 개 모양 맞추기
# ============================================================
def _normalize_model(raw: dict, existing_ids: set) -> dict | None:
    if not isinstance(raw, dict):
        return None
    mid = str(raw.get("id") or "").strip()
    name = str(raw.get("name") or "").strip()
    if not name:
        return None
    if not mid:
        mid = (name.lower().replace(" ", "-").replace("/", "-")) or f"model-{int(time.time()*1000)}"
    if mid in existing_ids:
        return None
    group = str(raw.get("group") or "양산").strip()
    if group not in ("양산", "개발"):
        group = "양산"
    try:
        progress = int(raw.get("progress") or 0)
    except (ValueError, TypeError):
        progress = 0
    progress = max(0, min(100, progress))
    status = str(raw.get("status") or "정상").strip()
    status = _LEGACY_MODEL_STATUS.get(status, status)
    if status not in MODEL_STATUSES:
        status = "정상"
    # 판가/재료비 (선택)
    price = 0
    material_cost = 0
    try:
        price = _as_money(raw.get("price"))
    except (ValueError, TypeError):
        pass
    try:
        material_cost = _as_money(raw.get("material_cost"))
    except (ValueError, TypeError):
        pass
    price = max(0, price)
    material_cost = max(0, material_cost)

    return {
        "id": mid,
        "name": name,
        "group": group,
        "progress": progress,
        "status": status,
        "price": price,
        "material_cost": material_cost,
    }


# 프로젝트 키로 모델 목록 조회 (별칭 매핑 적용)
def _get_project_models(project_key: str) -> list:
    _alias = {
        "havaplate": "hrva_plate",
        "hrvaplate": "hrva_plate",
        "hrva-plate": "hrva_plate",
    }
    _key = _alias.get(project_key.strip().lower(), project_key.strip())
    data = _load_models()
    proj = (data.get("projects") or {}).get(_key) or {}
    return proj.get("models") or []


# ─── 노트 첨부 자료 (표 JSON / 사진) 헬퍼 ───
import uuid as _uuid_mod
from datetime import datetime as _dt_mod

# ============================================================
#  노트에 붙이는 표 · 사진 파일
# ============================================================
def _new_asset_id(division_id: str) -> str:
    date_str = _dt_mod.now().strftime("%Y-%m-%d")
    uid = _uuid_mod.uuid4().hex[:8]
    return f"{date_str}_{uid}"

# 노트에 붙인 표(JSON) 파일 자리.
def _table_path(division_id: str, asset_id: str) -> Path:
    div_dir = NOTE_TABLES_DIR / division_id
    div_dir.mkdir(parents=True, exist_ok=True)
    return div_dir / f"{asset_id}.json"

# 노트에 붙인 사진 파일 자리.
def _photo_path(division_id: str, asset_id: str, ext: str = "jpg") -> Path:
    div_dir = NOTE_PHOTOS_DIR / division_id
    div_dir.mkdir(parents=True, exist_ok=True)
    return div_dir / f"{asset_id}.{ext}"

# 표 JSON 저장 → asset_id 반환 (예: 'semiconductor/2026-06-11_a1b2c3d4')
def _save_note_table(division_id: str, table_data: dict) -> str:
    asset_id = _new_asset_id(division_id)
    p = _table_path(division_id, asset_id)
    p.write_text(json.dumps(table_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"{division_id}/{asset_id}"

# 이미지 bytes → note_photos/에 저장 → photo_ref 반환.
def _save_note_photo(division_id: str, image_bytes: bytes, ext: str = "png") -> str:
    if not image_bytes:
        raise ValueError("empty image bytes")
    ext = (ext or "png").lower().lstrip(".")
    asset_id = _new_asset_id(division_id)
    dst = _photo_path(division_id, asset_id, ext)
    dst.write_bytes(image_bytes)
    return f"{division_id}/{asset_id}.{ext}"


# xlsx → PNG bytes (LibreOffice + pdf2image로 색상/스타일 완벽 반영).
def _xlsx_file_to_png_bytes(xlsx_path: Path) -> bytes:
    import subprocess
    import tempfile
    from io import BytesIO
    from pdf2image import convert_from_path

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # 1) LibreOffice: xlsx → pdf
        result = subprocess.run(
            ['libreoffice', '--headless', '--convert-to',
             'pdf:calc_pdf_Export:{"SinglePageSheets":{"type":"boolean","value":"true"}}',
             '--outdir', str(tmp_dir), str(xlsx_path)],
            capture_output=True, timeout=120
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"LibreOffice 변환 실패 (code={result.returncode}): "
                f"{result.stderr.decode('utf-8', errors='ignore')[:500]}"
            )

        pdf_files = list(tmp_dir.glob("*.pdf"))
        if not pdf_files:
            raise RuntimeError("LibreOffice가 PDF를 생성하지 못함")
        pdf_path = pdf_files[0]

        # 2) pdf → png (첫 페이지, 고해상도)
        images = convert_from_path(str(pdf_path), dpi=150, first_page=1, last_page=1)
        if not images:
            raise RuntimeError("pdf2image로 PNG 변환 실패")

        # 3) PNG bytes
        buf = BytesIO()
        images[0].save(buf, 'PNG', optimize=True)
        return buf.getvalue()


# report dict → division_id 유추.
def _derive_division_id_from_report(it: dict) -> str:
    if not isinstance(it, dict):
        return "semiconductor"
    division_id = (it.get("division_id") or "").strip()
    if division_id:
        return division_id
    products = it.get("products") or []
    for prod in products:
        if isinstance(prod, dict) and prod.get("name"):
            try:
                division_id = _cl.derive_division_from_project(prod["name"]) or ""
            except Exception:
                pass
            if division_id:
                return division_id
    return "semiconductor"


# table_ref = 'semiconductor/2026-06-11_a1b2c3d4' → 표 JSON 반환
def _load_note_table(table_ref: str):
    if not table_ref or "/" not in table_ref:
        return None
    division_id, asset_id = table_ref.split("/", 1)
    p = _table_path(division_id, asset_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

# 노트에 붙인 표 파일 하나를 지운다
def _delete_note_table(table_ref: str) -> bool:
    if not table_ref or "/" not in table_ref:
        return False
    division_id, asset_id = table_ref.split("/", 1)
    p = _table_path(division_id, asset_id)
    if p.exists():
        p.unlink()
        return True
    return False

# photo_ref = 'semiconductor/2026-06-11_a1b2c3d4.jpg'
def _delete_note_photo(photo_ref: str) -> bool:
    if not photo_ref or "/" not in photo_ref:
        return False
    p = NOTE_PHOTOS_DIR / photo_ref
    if p.exists():
        p.unlink()
        return True
    return False


_NOTE_AI_SYSTEM_PROMPT = """당신은 회사 임원에게 보고되는 주간 보고서를 구조화하는 도우미입니다.

입력으로 들어오는 자유 형식 텍스트를 다음 JSON 스키마로 변환하세요:

{
  "cards": [
    {
      "title": "프로젝트 이름",
      "sections": [
        {
          "title": "섹션 이름",
          "items": [
            {"type": "bullet | highlight | sub | group_note", "text": "항목 내용", "group_id": "g1 (선택)"}
          ]
        }
      ]
    }
  ]
}

규칙:
1. <텍스트>로 감싼 것은 새 카드(프로젝트)
2. 줄 시작에 "1.", "2.", "3." 같은 숫자+점으로 시작하는 줄은 무조건 새 섹션(section)이다. 절대 item으로 만들지 마라.
   - 예: "1. 양산 14종" → section title="양산 14종"
   - 예: "2. 개발 18종" → section title="개발 18종"
   - 예: "3. EMA 33종 (총 33종 중 승인 7종, 개발 26종)" → section title="EMA 33종 (총 33종 중 승인 7종, 개발 26종)"
3. "1)", "2)" 같은 괄호 번호나 들여쓰기는 일반 item(bullet) — section 만들지 마라
4. *로 시작하거나 "현황:" 표시는 type: highlight
4-1. 색상 태그 처리 — 본문에 "[빨간색]" / "[파란색]" / "[주황색]" / "[노란색]" 이 포함된 항목은:
     - 태그 문자열만 제거하고 본문은 그대로 유지
     - 결과 JSON 아이템에 "color": "red" / "blue" / "orange" 필드를 추가
     - 색상 태그는 group_id 부여의 신호가 아니다 (색깔이 같다고 묶지 말 것)
     - 예: "[파란색] W23 출하 24EA" → {"type":"bullet","text":"W23 출하 24EA","color":"blue"}
5. "-", "▸"로 시작하는 줄은 type: bullet
6. "→", "=>", "↳" 또는 명백한 들여쓰기는 type: sub (상위 항목의 부가 설명)
7. "※" 로 시작하는 줄은 type: highlight (참고/주의)
   - "※" 기호는 절대 제거하지 말고 본문 첫 글자로 그대로 유지한다 (예: "※에테르GDX 자재 ...")
   - "※" 로 시작하는 모든 줄은 반드시 출력 JSON 에 포함시켜야 한다 (절대 누락 금지, 요약/병합 금지)
   - 카드 마지막에 있는 "※" 줄들은 가장 가까운(직전) 섹션의 items 끝에 그대로 추가한다
   - "※" 줄을 별도 "기타 특이사항" 섹션으로 옮기지 말고, 원문이 속한 섹션 안에 그대로 둔다
   - "※" 줄에는 group_id 를 절대 부여하지 않는다
8. 카드 제목·섹션 제목에서 선행 번호와 기호는 제거
9. item 텍스트에서 선행 기호(-, *, ▸)는 제거. 본문 안의 →, ↳는 유지
10. "📷 파일명 @@photo_ref=..." 줄은 절대 수정/요약/제거하지 말고 그 자리에 그대로 한 줄 유지
11. 의미는 절대 바꾸지 말고, 임의로 항목을 합치거나 추가하지 마라
12. 빈 항목·중복 항목은 만들지 마라

★ group_id 부여 조건 (중요 — 함부로 묶지 말 것):

다음 신호 중 하나라도 명시적으로 존재할 때만 group_id를 부여한다:
  (a) 줄 끝에 "}" 기호가 있는 경우
  (b) "←", "<—", "<-" 화살표가 줄 시작이나 끝에 있는 경우
  (c) 텍스트에 "포괄적으로 들어가야", "공통으로 적용", "모두 해당" 같은 명시적 표현이 있는 경우

위 신호가 전혀 없으면 group_id를 절대 부여하지 마라. (일반 bullet들을 마음대로 묶지 말 것)

★ 사진 placeholder 규칙 (매우 중요, 절대 어기지 말 것):
  - 본문에 "[PHOTO_KEEP_0]", "[PHOTO_KEEP_1]" 같은 토큰이 포함된 줄이 있으면:
    1) 그 줄 전체를 반드시 별도 item 으로 만들 것 (다른 줄과 병합 금지, 삭제 금지, 요약 금지)
    2) item 의 text 는 원문 그대로 ("📷 파일명 [PHOTO_KEEP_0]") 유지
    3) item 의 type 은 "bullet" 로 둔다
    4) 원문에서 그 줄이 있던 위치 그대로 보존 — 앞뒤 내용 순서 절대 변경 금지, 카드 끝으로 옮기지 말 것
    5) placeholder 줄을 group_id 의 신호로 사용하지 말 것

★ group_id 를 부여하면 안 되는 경우 (오해 방지):
  - 색상 태그([빨간색]/[파란색]/[주황색]/[노란색])만으로는 group_id 부여 금지
  - 같은 섹션에 속한다는 이유로 묶지 말 것
  - 의미가 비슷하다는 이유로 묶지 말 것
  - "※" 로 시작하는 줄은 묶지 말 것

group_id를 부여하는 경우 처리 방법:
  1) 신호가 나타난 줄 바로 위쪽의 연관된 bullet 2-3개에 동일한 group_id ("g1", "g2", ...) 부여
  2) 공통 메모는 별도 항목으로 추가: {"type":"group_note","text":"<메모 본문>","group_id":"g1"}
  3) group_note의 text 에서는 "}", "←" 같은 메타 기호 제거하고 본문만 남긴다

[예시 1 — 번호 소제목]
입력:
<파워박스>
1. 양산 14종
- 에테르 GDX : 연간 1,461대

2. 개발 18종
- 화성 세이버 5종 7월말 승인 타겟

출력:
{
  "cards": [{
    "title": "파워박스",
    "sections": [
      {"title": "양산 14종", "items": [
        {"type":"bullet","text":"에테르 GDX : 연간 1,461대"}
      ]},
      {"title": "개발 18종", "items": [
        {"type":"bullet","text":"화성 세이버 5종 7월말 승인 타겟"}
      ]}
    ]
  }]
}

[예시 2 — } 마커가 있을 때만 group_id]
입력:
<하바플레이트>
*현황: 총141개 모델 중 양산진행 14종
- 신규 장비 40대
- 플라스틱 전용 장비 6대 } 6월말 고객사 승인 예정

출력:
{
  "cards": [{
    "title": "하바플레이트",
    "sections": [
      {"title": "현황", "items": [
        {"type":"highlight","text":"총141개 모델 중 양산진행 14종"},
        {"type":"bullet","text":"신규 장비 40대","group_id":"g1"},
        {"type":"bullet","text":"플라스틱 전용 장비 6대","group_id":"g1"},
        {"type":"group_note","text":"6월말 고객사 승인 예정","group_id":"g1"}
      ]}
    ]
  }]
}

응답은 반드시 위 JSON 형식 한 객체만 출력. 마크다운, 코드블록, 설명 없이 JSON만 출력하세요."""

# ============================================================
#  PPT → 노트 카드 · 프로젝트별 최근 노트
# ============================================================
# 업로드된 PPT를 주간 보고 카드 구조로 자동 변환.
@app.post("/admin/notes/from_pptx")
def admin_notes_from_pptx(payload: dict, _admin: int = Depends(get_admin_session)):
    doc_id = (payload or {}).get("doc_id", "").strip()
    division_id = (payload or {}).get("division_id", "").strip()
    if not doc_id:
        raise HTTPException(status_code=400, detail="doc_id가 필요합니다")
    if not division_id:
        raise HTTPException(status_code=400, detail="division_id가 필요합니다")

    pptx_path = UPLOAD_DIR / f"{doc_id}.pptx"
    if not pptx_path.exists():
        raise HTTPException(status_code=404, detail=f"PPT 파일을 찾을 수 없음: {doc_id}")
    # -----------------------------------------------------------
    # 텍스트 + 표 분리 추출
    # -----------------------------------------------------------
    try:
        slide_texts, slide_tables = _extract_pptx_text_and_tables(pptx_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PPT 추출 실패: {e}")
    # -----------------------------------------------------------
    # AI로 카드 구조 변환 (표 데이터는 텍스트로 함께 전달, AI가 표 참조 자리에 마커 삽입)
    # -----------------------------------------------------------
    joined_text = "\n\n".join([f"=== Slide {i+1} ===\n{t}" for i, t in enumerate(slide_texts) if t.strip()])
    if not joined_text.strip():
        return {"cards": []}

    user_message = (
        f"[PPT 텍스트 - 슬라이드별]\n{joined_text}\n\n"
        "위 PPT 텍스트를 주간 보고 카드 구조 JSON으로 변환해 주세요. "
        "한 슬라이드는 보통 한 프로젝트입니다. 슬라이드 제목이 프로젝트명입니다."
    )

    try:
        from openai import OpenAI
        import os
        oai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        resp = oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _NOTE_AI_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        result = json.loads(resp.choices[0].message.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 변환 실패: {e}")
    # -----------------------------------------------------------
    # 표가 있는 슬라이드 → 자동 저장 + 첫 번째 섹션에 table_ref 부착
    # -----------------------------------------------------------
    cards = result.get("cards", []) or []
    saved_tables = []
    for slide_idx, tables in enumerate(slide_tables):
        if not tables:
            continue
        if slide_idx >= len(cards):
            continue
        card = cards[slide_idx]
        sections = card.get("sections", []) or []
        if not sections:
            continue
        # 첫 번째 표만 첫 섹션에 자동 첨부 (나머지는 별도 섹션으로)
        for t_idx, tbl in enumerate(tables):
            table_obj = {
                "title": card.get("title", "") + (f" 표{t_idx+1}" if t_idx > 0 else ""),
                "headers": tbl["headers"],
                "rows": tbl["rows"],
            }
            try:
                table_ref = _save_note_table(division_id, None, table_obj)
                saved_tables.append(table_ref)
                target_section = sections[0] if t_idx == 0 else sections[min(t_idx, len(sections)-1)]
                target_section["table_ref"] = table_ref
            except Exception as e:
                print(f"표 저장 실패 slide={slide_idx+1} t={t_idx}: {e}")

    return {"cards": cards, "saved_tables": saved_tables}


# 프로젝트 키로 가장 최근 노트 카드를 찾아 반환.
@app.get("/notes/by_project")
def notes_by_project(project_key: str = ""):
    project_key = (project_key or "").strip()
    if not project_key:
        raise HTTPException(status_code=400, detail="project_key 필요")

    try:
        proj = _cl.get_project(project_key)
    except Exception:
        proj = None
    project_label = (proj or {}).get("label", "")
    project_aliases = set((proj or {}).get("aliases", []) or [])
    project_division = (proj or {}).get("division_id", "")
    if project_label:
        project_aliases.add(project_label)
    project_aliases.add(project_key)

    data = _load_notes()
    notes_map = data.get("notes", {}) or {}

    # 사업부 우선 검색, 없으면 전체 사업부 스캔
    div_ids = [project_division] if project_division else list(notes_map.keys())
    if project_division and project_division not in notes_map:
        div_ids = list(notes_map.keys())

    best = None
    best_date = ""
    best_division = ""
    for did in div_ids:
        ndata = notes_map.get(did) or {}
        cards = ndata.get("cards", []) or []
        report_date = ndata.get("report_date", "") or ""
        for c in cards:
            ck = (c.get("project_key") or "").strip()
            ctitle = (c.get("title") or "").strip()
            matched = False
            if ck and ck == project_key:
                matched = True
            elif ctitle and (ctitle == project_label or ctitle in project_aliases):
                matched = True
            if not matched:
                continue
            # 가장 최근 날짜 선택
            if report_date > best_date:
                best = c
                best_date = report_date
                best_division = did

    if not best:
        return {"card": None}

    # table_ref inline 로드
    sections = best.get("sections", []) or []
    for sec in sections:
        # 섹션 레벨 table_ref (기존 호환)
        sec_ref = sec.get("table_ref")
        if sec_ref:
            try:
                sec["table_data"] = _load_note_table(sec_ref)
            except Exception:
                sec["table_data"] = None
        # 아이템 흐름 안의 table/photo
        items = sec.get("items", []) or []
        for it in items:
            if not isinstance(it, dict):
                continue
            t_ref = it.get("table_ref")
            if t_ref:
                try:
                    it["table_data"] = _load_note_table(t_ref)
                except Exception:
                    it["table_data"] = None

    return {
        "card": best,
        "report_date": best_date,
        "division_id": best_division,
    }


# ─── 노트 엑셀(표) 마커 전/후처리 (ai_parse 용) ───

# ============================================================
#  노트 글 정리 — 표 · 사진 끼워 넣기 · 납기 글자 읽기
# ============================================================
def _inject_tables_into_cards(cards, tables):
    if not tables or not isinstance(cards, list):
        return cards

    def _norm(s):
        return re.sub(r"\s+", " ", str(s or "").strip().lower())

    used = set()

    for tb in tables:
        anchor_n = _norm(tb.get("anchor"))
        ref = tb.get("table_ref")
        fname = tb.get("filename") or ""
        if not ref or ref in used:
            continue

        # table_data 도 함께 로드해서 inline 포함
        table_data = _load_note_table(ref) if ref else None

        injected = False
        if anchor_n:
            for card in cards:
                if injected:
                    break
                for sec in (card.get("sections") or []):
                    if injected:
                        break
                    items = sec.get("items") or []
                    for idx, it in enumerate(items):
                        it_text = _norm(it.get("text") if isinstance(it, dict) else it)
                        if not it_text:
                            continue
                        if anchor_n == it_text or anchor_n in it_text or it_text in anchor_n:
                            new_item = {
                                "type": "table",
                                "text": fname,
                                "table_ref": ref,
                            }
                            if table_data:
                                new_item["table_data"] = table_data
                            items.insert(idx + 1, new_item)
                            sec["items"] = items
                            injected = True
                            used.add(ref)
                            break

        if not injected and cards:
            card0 = cards[0]
            secs = card0.setdefault("sections", [])
            if not secs:
                secs.append({"title": "첨부", "items": []})
            last_sec = secs[-1]
            new_item = {
                "type": "table",
                "text": fname,
                "table_ref": ref,
            }
            if table_data:
                new_item["table_data"] = table_data
            last_sec.setdefault("items", []).append(new_item)
            used.add(ref)

    return cards


# ─── 노트 사진 마커 전/후처리 (ai_parse 용) ───
import re as _re_photo
_PHOTO_MARKER_RE = _re_photo.compile(
    r"\u{1F4F7}\s*([^\n\r]+?)\s*@@photo_ref=([^\s\n\r]+)".replace(r"\u{1F4F7}", "\U0001F4F7"),
    _re_photo.IGNORECASE,
)

# 텍스트에서 사진 마커 추출 (next_anchor 기반 위치 보존).
def _extract_photo_markers(text: str):
    lines = text.split("\n")

    marker_positions = []
    for i, ln in enumerate(lines):
        m = _PHOTO_MARKER_RE.search(ln)
        if m:
            fname = (m.group(1) or "").strip()
            ref = (m.group(2) or "").strip()
            if fname and ref:
                marker_positions.append((i, fname, ref))

    photos = []
    out_lines = []
    last_nonempty = ""
    marker_idx_set = {pos[0] for pos in marker_positions}

    def find_next_anchor(start):
        for j in range(start + 1, len(lines)):
            if j in marker_idx_set:
                continue
            v = lines[j].strip()
            if v:
                return v
        return ""

    pos_map = {pos[0]: pos for pos in marker_positions}
    for i, ln in enumerate(lines):
        if i in pos_map:
            _, fname, ref = pos_map[i]
            idx = len(photos)
            placeholder = f"[PHOTO_KEEP_{idx}]"
            placeholder_line = f"\U0001F4F7 {fname} {placeholder}"
            nxt = find_next_anchor(i)
            photos.append({
                "filename": fname,
                "photo_ref": ref,
                "anchor": last_nonempty,
                "next_anchor": nxt,
                "placeholder": placeholder,
            })
            out_lines.append(placeholder_line)
            last_nonempty = placeholder_line
            continue
        out_lines.append(ln)
        if ln.strip():
            last_nonempty = ln.strip()
    return ("\n".join(out_lines), photos)


# 본문 텍스트에서 due_date(YYYY-MM-DD) 추출.
def _extract_due_date_from_text(txt: str) -> str:
    from datetime import date, timedelta
    import calendar
    if not txt:
        return ""
    YEAR = 2026
    today = date.today()
    # -----------------------------------------------------------
    # ─ Step 1: 화살표로 split
    # -----------------------------------------------------------
    arrow_pattern = r"-->|->|→|➜|⇒|~>|»"
    segments = re.split(arrow_pattern, txt)
    last_seg = segments[-1] if segments else txt

    # 문자열 s 에서 모든 날짜 후보를 date 리스트로 반환.
    def _collect_dates(s: str):
        out = []

        # 범위 (M/D-M/D) / (M/D~M/D) → 종료일
        for m in re.finditer(r"\(?\s*(\d{1,2})/(\d{1,2})\s*[-~]\s*(\d{1,2})/(\d{1,2})\s*\)?", s):
            try:
                mo = int(m.group(3))
                dd = int(m.group(4))
                if 1 <= mo <= 12 and 1 <= dd <= 31:
                    out.append(date(YEAR, mo, dd))
            except Exception:
                pass

        # YYYY-MM-DD
        for m in re.finditer(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", s):
            try:
                out.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
            except Exception:
                pass

        # YY.M.D / YY-M-D  (2자리 연도)
        for m in re.finditer(r"(\d{2})[-./](\d{1,2})[-./](\d{1,2})", s):
            try:
                out.append(date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))))
            except Exception:
                pass

        # X월말
        for m in re.finditer(r"(\d{1,2})\s*월\s*말", s):
            try:
                mo = int(m.group(1))
                last_day = calendar.monthrange(YEAR, mo)[1]
                d = date(YEAR, mo, last_day)
                if d.weekday() == 6:
                    d = d - timedelta(days=2)
                out.append(d)
            except Exception:
                pass

        # M월 D일
        for m in re.finditer(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", s):
            try:
                out.append(date(YEAR, int(m.group(1)), int(m.group(2))))
            except Exception:
                pass

        # (M/D) 또는 M/D  (분수 제외 — 경계 있을 때만)
        for m in re.finditer(r"(?:^|[\s\(\[~])(\d{1,2})/(\d{1,2})(?=[\s\)\]\,\.~]|$)", s):
            try:
                mo = int(m.group(1))
                dd = int(m.group(2))
                if 1 <= mo <= 12 and 1 <= dd <= 31:
                    out.append(date(YEAR, mo, dd))
            except Exception:
                pass

        # W23 ~ W53
        for m in re.finditer(r"W\s*(\d{1,2})", s, flags=re.IGNORECASE):
            try:
                wk = int(m.group(1))
                if 1 <= wk <= 53:
                    out.append(date.fromisocalendar(YEAR, wk, 5))
            except Exception:
                pass

        return out
    # -----------------------------------------------------------
    # ─ Step 2: 마지막 세그먼트에서 먼저 시도
    # -----------------------------------------------------------
    candidates = _collect_dates(last_seg)
    # -----------------------------------------------------------
    # ─ Step 3: 없으면 전체에서 fallback
    # -----------------------------------------------------------
    if not candidates and len(segments) == 1:
        # split 안 됐으면 이미 전체 = last_seg, 중복 fallback 불필요
        pass
    elif not candidates:
        candidates = _collect_dates(txt)

    if not candidates:
        return ""
    # -----------------------------------------------------------
    # ─ Step 4: 최적 선택
    # -----------------------------------------------------------
    future = [d for d in candidates if d >= today]
    if future:
        return min(future).isoformat()  # 가장 임박한 미래
    # 전부 과거 → 가장 최근 과거 (지연 표시용)
    return max(candidates).isoformat()


# AI 결과 아이템 후처리: 색상 태그, ※ 항목, 화살표 중복 제거.
def _normalize_note_item(it: dict, section_title: str = "") -> dict:
    if not isinstance(it, dict):
        return it

    txt = (it.get("text") or "").strip()
    typ = (it.get("type") or "bullet").strip().lower()
    color = (it.get("color") or "").strip().lower()

    # [빨간색]/[파란색]/[주황색]/[노란색] -> color 필드로 승격, 본문에서는 제거
    if "[빨간색]" in txt:
        color = "red"
        txt = txt.replace("[빨간색]", "").strip()
    if "[파란색]" in txt:
        color = "blue"
        txt = txt.replace("[파란색]", "").strip()
    if "[주황색]" in txt:
        color = "orange"
        txt = txt.replace("[주황색]", "").strip()
    if "[노란색]" in txt:
        color = "orange"
        txt = txt.replace("[노란색]", "").strip()

    # ※ 로 시작하는 줄은 절대 group_note/특이사항으로 빼지 말고 일반 bullet 유지
    if txt.startswith("※"):
        if typ == "group_note":
            typ = "bullet"
        it.pop("group_id", None)

    # sub: 선행 화살표가 여러 개거나 중복이면 1개로 정규화
    if typ == "sub":
        txt = re.sub(r"^(?:\s*(?:→|↳|=>)\s*)+", "→ ", txt).strip()

    # bullet/highlight 도 "→ → ..." 처럼 화살표 중복 시 1개로 축약
    txt = re.sub(r"^(→\s*){2,}", "→ ", txt)
    # -----------------------------------------------------------
    # ─ item_id 생성/갱신 (section_title + normalized_text 기반)
    # -----------------------------------------------------------
    normalized = re.sub(r"\s+", " ", txt).strip()
    if normalized:
        new_id = hashlib.md5(
            f"{section_title}||{normalized}".encode("utf-8")
        ).hexdigest()[:8]
        it["item_id"] = new_id
    # -----------------------------------------------------------
    # ─ due_date_auto 재계산 (매번, 텍스트는 원문 유지)
    # -----------------------------------------------------------
    _, auto_iso = _extract_due_date(txt)
    # 사용자가 자동 날짜를 숨긴 경우(auto_due_hidden=True)는 재계산돼도 유지
    _new_auto = auto_iso or ""
    it["due_date_auto"] = _new_auto
    # -----------------------------------------------------------
    # ─ due_date_override 처리
    # -----------------------------------------------------------
    override_raw = (it.get("due_date_override") or "").strip()
    override = override_raw if override_raw else ""
    # -----------------------------------------------------------
    # ─ 최종 due_date = override or auto (앱 호환)
    # -----------------------------------------------------------
    effective = override or (auto_iso or "")
    if effective:
        it["due_date"] = effective
    else:
        # 아무 값 없으면 due_date 필드 제거 (하위 호환)
        it.pop("due_date", None)

    # override 명시 저장 (빈 값이면 삭제)
    if override:
        it["due_date_override"] = override
    else:
        it.pop("due_date_override", None)

    it["type"] = typ
    it["text"] = txt
    if color:
        it["color"] = color

    return it


# parsed["cards"] 전체에 _normalize_note_item 적용 + 기타 특이사항 섹션 병합.
def _normalize_note_cards(parsed: dict) -> dict:
    if not isinstance(parsed, dict):
        return parsed
    cards = parsed.get("cards") or []
    _ETC_TITLES = {"기타 특이사항", "기타특이사항", "특이사항", "기타"}
    for card in cards:
        if not isinstance(card, dict):
            continue
        # -----------------------------------------------------------
        # 각 섹션 아이템 정규화
        # -----------------------------------------------------------
        for sec in (card.get("sections") or []):
            if not isinstance(sec, dict):
                continue
            new_items = []
            for it in (sec.get("items") or []):
                if isinstance(it, dict):
                    new_items.append(_normalize_note_item(it, sec.get('title', '')))
                else:
                    new_items.append(it)
            sec["items"] = new_items
        # -----------------------------------------------------------
        # "기타 특이사항" 류 섹션은 직전 섹션에 흡수 후 삭제
        # -----------------------------------------------------------
        sections = card.get("sections") or []
        merged_sections = []
        for sec in sections:
            if not isinstance(sec, dict):
                merged_sections.append(sec)
                continue
            title = (sec.get("title") or "").strip()
            if title in _ETC_TITLES and merged_sections:
                # 직전 섹션 마지막에 합치기
                prev = merged_sections[-1]
                if isinstance(prev, dict):
                    prev_items = prev.get("items") or []
                    prev_items.extend(sec.get("items") or [])
                    prev["items"] = prev_items
                    continue
            merged_sections.append(sec)
        card["sections"] = merged_sections

    return parsed


# 정리된 카드 구조에 type:'photo' item 을 주입.
def _inject_photos_into_cards(cards, photos):
    if not photos or not isinstance(cards, list):
        return cards

    def _norm(s):
        v = re.sub(r"^\s*\d+[.)\]]?\s*", "", str(s or "").strip())
        return re.sub(r"\s+", " ", v.lower())

    used = set()
    # -----------------------------------------------------------
    # 1순위: placeholder 직접 치환
    # -----------------------------------------------------------
    for ph in photos:
        placeholder = ph.get("placeholder") or ""
        ref = ph.get("photo_ref")
        fname = ph.get("filename") or ""
        if not ref or not placeholder or ref in used:
            continue

        replaced = False
        for card in cards:
            if replaced:
                break
            for sec in (card.get("sections") or []):
                if replaced:
                    break
                items = sec.get("items") or []
                for idx, it in enumerate(items):
                    if not isinstance(it, dict):
                        continue
                    txt = str(it.get("text") or "")
                    if placeholder in txt:
                        # 해당 item 을 photo item 으로 치환
                        items[idx] = {
                            "type": "photo",
                            "text": fname,
                            "photo_ref": ref,
                        }
                        sec["items"] = items
                        replaced = True
                        used.add(ref)
                        break

        if replaced:
            continue
        # -----------------------------------------------------------
        # 1.5순위: next_anchor 매칭 (마커 다음 줄 앞에 삽입)
        # -----------------------------------------------------------
        next_anchor_n = _norm(ph.get("next_anchor"))
        if next_anchor_n:
            inserted_by_next = False
            # (a) item 텍스트 매칭 → 그 앞에 삽입
            for card in cards:
                if inserted_by_next:
                    break
                for sec in (card.get("sections") or []):
                    if inserted_by_next:
                        break
                    items = sec.get("items") or []
                    for idx, it in enumerate(items):
                        it_text = _norm(it.get("text") if isinstance(it, dict) else it)
                        if not it_text:
                            continue
                        if next_anchor_n == it_text or next_anchor_n in it_text or it_text in next_anchor_n:
                            items.insert(idx, {
                                "type": "photo",
                                "text": fname,
                                "photo_ref": ref,
                            })
                            sec["items"] = items
                            inserted_by_next = True
                            used.add(ref)
                            break
            # (b) section title 매칭 → 그 섹션의 첫 item 으로 삽입
            if not inserted_by_next:
                for card in cards:
                    if inserted_by_next:
                        break
                    for sec in (card.get("sections") or []):
                        sec_title = _norm(sec.get("title"))
                        if not sec_title:
                            continue
                        if next_anchor_n == sec_title or next_anchor_n in sec_title or sec_title in next_anchor_n:
                            items = sec.get("items") or []
                            items.insert(0, {
                                "type": "photo",
                                "text": fname,
                                "photo_ref": ref,
                            })
                            sec["items"] = items
                            inserted_by_next = True
                            used.add(ref)
                            break
            if inserted_by_next:
                continue
        # -----------------------------------------------------------
        # 2순위(fallback): anchor 텍스트 매칭
        # -----------------------------------------------------------
        anchor_n = _norm(ph.get("anchor"))
        if anchor_n and anchor_n.startswith("__photo_placeholder_"):
            anchor_n = ""  # placeholder 자체는 anchor 로 쓰지 않음
        injected = False
        if anchor_n:
            # item 텍스트 매칭
            for card in cards:
                if injected:
                    break
                for sec in (card.get("sections") or []):
                    if injected:
                        break
                    items = sec.get("items") or []
                    for idx, it in enumerate(items):
                        it_text = _norm(it.get("text") if isinstance(it, dict) else it)
                        if not it_text:
                            continue
                        if anchor_n == it_text or anchor_n in it_text or it_text in anchor_n:
                            insert_at = idx + 1
                            matched_gid = (it.get("group_id") if isinstance(it, dict) else "") or ""
                            if matched_gid:
                                k = idx + 1
                                while k < len(items):
                                    nxt = items[k]
                                    if not isinstance(nxt, dict):
                                        break
                                    if (nxt.get("group_id") or "") != matched_gid:
                                        break
                                    insert_at = k + 1
                                    k += 1
                            else:
                                k = idx + 1
                                while k < len(items):
                                    nxt = items[k]
                                    if not isinstance(nxt, dict):
                                        break
                                    if (nxt.get("type") or "") != "group_note":
                                        break
                                    insert_at = k + 1
                                    k += 1
                            items.insert(insert_at, {
                                "type": "photo",
                                "text": fname,
                                "photo_ref": ref,
                            })
                            sec["items"] = items
                            injected = True
                            used.add(ref)
                            break

            # section title 매칭
            if not injected:
                for card in cards:
                    if injected:
                        break
                    for sec in (card.get("sections") or []):
                        sec_title = _norm(sec.get("title"))
                        if not sec_title:
                            continue
                        if anchor_n == sec_title or anchor_n in sec_title or sec_title in anchor_n:
                            items = sec.get("items") or []
                            items.insert(0, {
                                "type": "photo",
                                "text": fname,
                                "photo_ref": ref,
                            })
                            sec["items"] = items
                            injected = True
                            used.add(ref)
                            break

            # card title 매칭
            if not injected:
                for card in cards:
                    card_title = _norm(card.get("title"))
                    if not card_title:
                        continue
                    if anchor_n == card_title or anchor_n in card_title or card_title in anchor_n:
                        secs = card.setdefault("sections", [])
                        if not secs:
                            secs.append({"title": "첨부", "items": []})
                        secs[-1].setdefault("items", []).append({
                            "type": "photo",
                            "text": fname,
                            "photo_ref": ref,
                        })
                        injected = True
                        used.add(ref)
                        break

        # 앵커 못 찾으면 첫 카드 마지막 섹션 끝
        if not injected and cards:
            card0 = cards[0]
            secs = card0.setdefault("sections", [])
            if not secs:
                secs.append({"title": "첨부", "items": []})
            last_sec = secs[-1]
            last_sec.setdefault("items", []).append({
                "type": "photo",
                "text": fname,
                "photo_ref": ref,
            })
            used.add(ref)
    # -----------------------------------------------------------
    # 후처리: 사용되지 않은 placeholder item 제거 (AI 가 위치 보존 안 한 경우 대비)
    # -----------------------------------------------------------
    placeholder_re = re.compile(r"\[PHOTO_KEEP_\d+\]")
    for card in cards:
        for sec in (card.get("sections") or []):
            items = sec.get("items") or []
            sec["items"] = [
                it for it in items
                if not (isinstance(it, dict) and placeholder_re.match(str(it.get("text") or "").strip()))
            ]

    return cards

# ============================================================
#  노트 저장 · AI 정리 · 알림 목록
# ============================================================
# 자유 형식 텍스트를 AI로 구조화 JSON으로 변환 (증분 병합 지원).
@app.post("/admin/notes/ai_parse")
def admin_notes_ai_parse(payload: dict, _admin: int = Depends(get_admin_session)):
    text = (payload or {}).get("text", "").strip()
    division_id = (payload or {}).get("division_id", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text가 비어있습니다")

    # 사진 마커 추출 (AI 가 보지 않도록 제거 후, 응답에 주입)
    text, _extracted_photos = _extract_photo_markers(text)
    text, _extracted_tables = _extract_excel_markers(text)

    user_message = f"다음 텍스트를 정리:\n\n{text}"

    try:
        from openai import OpenAI
        import os
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _NOTE_AI_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
        if isinstance(parsed, dict) and isinstance(parsed.get("cards"), list):
            parsed["cards"] = _inject_photos_into_cards(parsed["cards"], _extracted_photos)
            parsed = _normalize_note_cards(parsed)
            # parsed["cards"] = _inject_tables_into_cards(parsed["cards"], _extracted_tables)  # 엑셀은 photo로 처리
        return parsed
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 파싱 실패: {str(e)}")


# 사업부별 노트 저장.
@app.post("/admin/notes")
def admin_save_note(payload: dict, _admin: int = Depends(get_admin_session)):
    division_id = (payload or {}).get("division_id", "").strip()
    report_date = (payload or {}).get("report_date", "").strip()
    raw_text = (payload or {}).get("raw_text", "").strip()
    cards = (payload or {}).get("cards", [])

    if not division_id:
        raise HTTPException(status_code=400, detail="division_id 필수")
    if not isinstance(cards, list):
        raise HTTPException(status_code=400, detail="cards는 배열이어야 합니다")

    # 저장 전 카드/아이템 정규화
    try:
        normalized = _normalize_note_cards({"cards": cards}) or {}
        cards = normalized.get("cards") or cards
    except Exception as _e:
        print(f"admin_save_note normalize 실패: {_e}")

    from datetime import datetime
    data = _load_notes()
    notes_map = data.setdefault("notes", {})
    existing = notes_map.get(division_id) or {}
    existing_cards = existing.get("cards") or []

    # 카드 제목 기준으로 merge (같은 title은 새 내용으로 교체, 새 title은 추가)
    def _norm_title(t):
        return re.sub(r"\s+", "", (t or "").strip()).lower()

    by_title = {}
    order = []
    for c in existing_cards:
        if not isinstance(c, dict):
            continue
        tkey = _norm_title(c.get("title"))
        if not tkey or tkey in by_title:
            continue
        by_title[tkey] = c
        order.append(tkey)

    for c in cards:
        if not isinstance(c, dict):
            continue
        tkey = _norm_title(c.get("title"))
        if not tkey:
            continue
        if tkey in by_title:
            by_title[tkey] = c  # 교체
        else:
            by_title[tkey] = c
            order.append(tkey)

    merged_cards = [by_title[k] for k in order]

    notes_map[division_id] = {
        "report_date": report_date or existing.get("report_date", ""),
        "updated_at": datetime.now().isoformat(),
        "raw_text": raw_text if isinstance(raw_text, str) else existing.get("raw_text", ""),
        "cards": merged_cards,
    }
    _save_notes(data)
    return {"ok": True, "division_id": division_id, "card_count": len(merged_cards)}


# 최근 알람 목록. 최신순 ← 앱 notifications_service.dart list()
@app.get("/notifications")
def get_notifications(limit: int = 100, unread_only: bool = False):
    hist = _load_fcm_history()
    if unread_only:
        hist = [h for h in hist if not h.get("read")]
    # 최신순
    hist = list(reversed(hist))[:max(1, min(limit, 200))]
    unread_count = sum(1 for h in _load_fcm_history() if not h.get("read"))
    return {"items": hist, "unread_count": unread_count}


# id 지정 시 해당 항목만, 없으면 전체 읽음 처리.
@app.post("/notifications/mark_read")
def mark_notifications_read(payload: dict = None):
    payload = payload or {}
    ids = payload.get("ids")
    hist = _load_fcm_history()
    changed = 0
    for h in hist:
        if ids is None or h.get("id") in ids:
            if not h.get("read"):
                h["read"] = True
                changed += 1
    _save_fcm_history(hist)
    return {"ok": True, "changed": changed}


# 앱이 호출하는 공개 API. division_id 지정 시 해당 사업부만 반환.
# ← admin v2 _loadNotesForSchedule() · _reloadNotesCache() · static · note_loader.js
@app.get("/notes")
def get_notes(division_id: str = ""):
    data = _load_notes()
    notes = data.get("notes", {})
    if division_id:
        item = notes.get(division_id)
        if not item:
            return {"division_id": division_id, "report_date": "", "cards": [], "updated_at": None}
        return {"division_id": division_id, **item}
    return {"notes": notes}

# ============================================================
#  노트 항목 납기 직접 지정
# ============================================================
# (item_ref, card_ref, section_ref) 반환.
def _find_item_by_id(notes_data: dict, division_id: str, card_title: str, item_id: str):
    div = (notes_data.get("notes") or {}).get(division_id)
    if not isinstance(div, dict):
        return None, None, None
    for card in div.get("cards", []) or []:
        if not isinstance(card, dict):
            continue
        if (card.get("title") or "").strip() != (card_title or "").strip():
            continue
        for sec in card.get("sections", []) or []:
            if not isinstance(sec, dict):
                continue
            for it in sec.get("items", []) or []:
                if isinstance(it, dict) and it.get("item_id") == item_id:
                    return it, card, sec
    return None, None, None


# it 안의 override/auto 를 보고 최종 due_date 필드를 갱신.
def _apply_effective_due_date(it: dict) -> None:
    override = (it.get("due_date_override") or "").strip()
    auto_raw = (it.get("due_date_auto") or "").strip()
    # auto_due_hidden 이 True 면 자동값을 무시
    auto = "" if it.get("auto_due_hidden") else auto_raw
    effective = override or auto
    if effective:
        it["due_date"] = effective
    else:
        it.pop("due_date", None)
    # 빈 override 는 필드 자체 제거
    if not override:
        it.pop("due_date_override", None)


# 특정 item 의 due_date_override 지정 ← admin v2 outsideClick()
@app.post("/admin/notes/item/due_override")
def admin_notes_item_due_override(
    payload: dict,
    _admin: int = Depends(get_admin_session),
):
    from datetime import date as _date

    division_id = (payload or {}).get("division_id", "").strip()
    card_title = (payload or {}).get("card_title", "").strip()
    item_id = (payload or {}).get("item_id", "").strip()
    due_date_raw = (payload or {}).get("due_date", "").strip()

    if not division_id or not card_title or not item_id:
        raise HTTPException(status_code=400, detail="division_id, card_title, item_id 필수")
    if not due_date_raw:
        raise HTTPException(status_code=400, detail="due_date 필수 (지우려면 DELETE 사용)")

    # 형식 검증 (YYYY-MM-DD)
    try:
        parsed = _date.fromisoformat(due_date_raw)
        due_iso = parsed.isoformat()
    except Exception:
        raise HTTPException(status_code=400, detail="due_date 형식 오류 (YYYY-MM-DD 이어야 함)")

    notes_data = _load_notes()
    item, card, sec = _find_item_by_id(notes_data, division_id, card_title, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"item_id={item_id} 을(를) 찾을 수 없음")

    # FCM alarm hook: 저장 전 스냅샷
    _fcm_before = _snapshot_notes_status()

    item["due_date_override"] = due_iso
    _apply_effective_due_date(item)
    _save_notes(notes_data)

    # FCM alarm hook: 저장 후 diff → RED/ORANGE 신규 전이 알람
    try:
        _fcm_after = _snapshot_notes_status()
        _events = _detect_status_transitions(_fcm_before, _fcm_after)
        if _events:
            print(f"[FCM] due_override POST 상태 전이: {_events}")
            _fire_status_alarms(_events)
    except Exception as _e:
        print(f"[FCM due_override POST hook] {_e}")

    return {
        "ok": True,
        "item_id": item_id,
        "due_date": item.get("due_date"),
        "due_date_auto": item.get("due_date_auto"),
        "due_date_override": item.get("due_date_override"),
        "auto_due_hidden": bool(item.get("auto_due_hidden")),
    }


# item 의 due_date_override 제거 → 자동값(due_date_auto) 복귀 ← admin v2 outsideClick()
@app.delete("/admin/notes/item/due_override")
def admin_notes_item_due_override_reset(
    payload: dict,
    _admin: int = Depends(get_admin_session),
):
    division_id = (payload or {}).get("division_id", "").strip()
    card_title = (payload or {}).get("card_title", "").strip()
    item_id = (payload or {}).get("item_id", "").strip()

    if not division_id or not card_title or not item_id:
        raise HTTPException(status_code=400, detail="division_id, card_title, item_id 필수")

    notes_data = _load_notes()
    item, card, sec = _find_item_by_id(notes_data, division_id, card_title, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"item_id={item_id} 을(를) 찾을 수 없음")

    # FCM alarm hook: 저장 전 스냅샷
    _fcm_before = _snapshot_notes_status()

    item.pop("due_date_override", None)
    _apply_effective_due_date(item)
    _save_notes(notes_data)

    # FCM alarm hook: DELETE 이후에도 상태 재판정 → 신규 RED/ORANGE 알람
    try:
        _fcm_after = _snapshot_notes_status()
        _events = _detect_status_transitions(_fcm_before, _fcm_after)
        if _events:
            print(f"[FCM] due_override DELETE 상태 전이: {_events}")
            _fire_status_alarms(_events)
    except Exception as _e:
        print(f"[FCM due_override DELETE hook] {_e}")

    return {
        "ok": True,
        "item_id": item_id,
        "due_date": item.get("due_date"),
        "due_date_auto": item.get("due_date_auto"),
        "due_date_override": item.get("due_date_override"),
        "auto_due_hidden": bool(item.get("auto_due_hidden")),
    }


# 특정 item 의 자동 파싱 날짜를 숨김 처리 ← admin v2 outsideClick()
@app.post("/admin/notes/item/hide_auto_due")
def admin_notes_item_hide_auto_due(
    payload: dict,
    _admin: int = Depends(get_admin_session),
):
    division_id = (payload or {}).get("division_id", "").strip()
    card_title = (payload or {}).get("card_title", "").strip()
    item_id = (payload or {}).get("item_id", "").strip()

    if not division_id or not card_title or not item_id:
        raise HTTPException(status_code=400, detail="division_id, card_title, item_id 필수")

    notes_data = _load_notes()
    item, card, sec = _find_item_by_id(notes_data, division_id, card_title, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"item_id={item_id} 을(를) 찾을 수 없음")

    # FCM alarm hook: 저장 전 스냅샷
    _fcm_before = _snapshot_notes_status()

    # 자동값 숨김 + 수동값도 함께 제거
    item["auto_due_hidden"] = True
    item.pop("due_date_override", None)
    _apply_effective_due_date(item)
    _save_notes(notes_data)

    # FCM alarm hook
    try:
        _fcm_after = _snapshot_notes_status()
        _events = _detect_status_transitions(_fcm_before, _fcm_after)
        if _events:
            print(f"[FCM] hide_auto_due POST 상태 전이: {_events}")
            _fire_status_alarms(_events)
    except Exception as _e:
        print(f"[FCM hide_auto_due POST hook] {_e}")

    return {
        "ok": True,
        "item_id": item_id,
        "due_date": item.get("due_date"),
        "due_date_auto": item.get("due_date_auto"),
        "due_date_override": item.get("due_date_override"),
        "auto_due_hidden": True,
    }


# item 의 auto_due_hidden 해제 → 자동값(due_date_auto) 복원 ← admin v2 outsideClick()
@app.delete("/admin/notes/item/hide_auto_due")
def admin_notes_item_hide_auto_due_reset(
    payload: dict,
    _admin: int = Depends(get_admin_session),
):
    division_id = (payload or {}).get("division_id", "").strip()
    card_title = (payload or {}).get("card_title", "").strip()
    item_id = (payload or {}).get("item_id", "").strip()

    if not division_id or not card_title or not item_id:
        raise HTTPException(status_code=400, detail="division_id, card_title, item_id 필수")

    notes_data = _load_notes()
    item, card, sec = _find_item_by_id(notes_data, division_id, card_title, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"item_id={item_id} 을(를) 찾을 수 없음")

    # FCM alarm hook: 저장 전 스냅샷
    _fcm_before = _snapshot_notes_status()

    item.pop("auto_due_hidden", None)
    _apply_effective_due_date(item)
    _save_notes(notes_data)

    # FCM alarm hook
    try:
        _fcm_after = _snapshot_notes_status()
        _events = _detect_status_transitions(_fcm_before, _fcm_after)
        if _events:
            print(f"[FCM] hide_auto_due DELETE 상태 전이: {_events}")
            _fire_status_alarms(_events)
    except Exception as _e:
        print(f"[FCM hide_auto_due DELETE hook] {_e}")

    return {
        "ok": True,
        "item_id": item_id,
        "due_date": item.get("due_date"),
        "due_date_auto": item.get("due_date_auto"),
        "due_date_override": item.get("due_date_override"),
        "auto_due_hidden": False,
    }

# ============================================================
#  노트 표 · 사진 올리기 · 지우기
# ============================================================
# 노트 삭제.
@app.delete("/admin/notes/{division_id}")
def admin_delete_note(division_id: str, _admin: int = Depends(get_admin_session)):
    data = _load_notes()
    if division_id in data.get("notes", {}):
        del data["notes"][division_id]
        _save_notes(data)
        return {"ok": True}
    raise HTTPException(status_code=404, detail="해당 사업부 노트 없음")


# ─── 노트 표/사진 첨부 API ───

# 표 생성/수정. payload = {division_id, table_ref?, table: {title, headers, rows}}
@app.post("/admin/notes/table")
def admin_save_note_table(payload: dict, _admin: int = Depends(get_admin_session)):
    division_id = (payload or {}).get("division_id", "").strip()
    table = (payload or {}).get("table")
    existing_ref = (payload or {}).get("table_ref", "").strip()

    if not division_id:
        raise HTTPException(status_code=400, detail="division_id 필수")
    if not isinstance(table, dict):
        raise HTTPException(status_code=400, detail="table 필수")

    # 기존 표 수정인 경우 같은 파일에 덮어쓰기
    if existing_ref and "/" in existing_ref:
        div_id, asset_id = existing_ref.split("/", 1)
        p = _table_path(div_id, asset_id)
        p.write_text(json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"table_ref": existing_ref, "updated": True}

    # 신규 생성
    table_ref = _save_note_table(division_id, table)
    return {"table_ref": table_ref, "updated": False}


# 표 JSON 조회 (모바일/관리자 공용)
@app.get("/notes/table/{division_id}/{asset_id}")
def get_note_table(division_id: str, asset_id: str):
    table_ref = f"{division_id}/{asset_id}"
    data = _load_note_table(table_ref)
    if data is None:
        raise HTTPException(status_code=404, detail="표를 찾을 수 없음")
    return {"table_ref": table_ref, "table": data}


# 노트에 붙인 표 하나 지우기 (잠김).
@app.delete("/admin/notes/table/{division_id}/{asset_id}")
def admin_delete_note_table(division_id: str, asset_id: str, _admin: int = Depends(get_admin_session)):
    table_ref = f"{division_id}/{asset_id}"
    ok = _delete_note_table(table_ref)
    if not ok:
        raise HTTPException(status_code=404, detail="표가 없음")
    return {"deleted": True, "table_ref": table_ref}


# 사진 업로드 → photo_ref(예: 'semiconductor/2026-06-11_abcd1234.jpg') 반환 ← static · photo_drop.js
@app.post("/admin/notes/photo")
async def admin_upload_note_photo(
    division_id: str = Form(...),
    file: UploadFile = File(...),
    _admin: int = Depends(get_admin_session),
):
    division_id = division_id.strip()
    if not division_id:
        raise HTTPException(status_code=400, detail="division_id 필수")

    # 확장자 결정
    orig_name = (file.filename or "").lower()
    ext = "jpg"
    for cand in ["jpg", "jpeg", "png", "gif", "webp"]:
        if orig_name.endswith("." + cand):
            ext = cand if cand != "jpeg" else "jpg"
            break

    asset_id = _new_asset_id(division_id)
    p = _photo_path(division_id, asset_id, ext)
    content = await file.read()
    p.write_bytes(content)
    photo_ref = f"{division_id}/{asset_id}.{ext}"
    return {"photo_ref": photo_ref, "url": f"/note_photos/{photo_ref}"}


# ─── 엑셀 업로드 (드래그&드롭) ───

# ============================================================
#  엑셀 → 노트 표 · 주차 계획표 읽기
# ============================================================
def _norm_label(t):
    import re as _re
    return _re.sub(r"[^0-9A-Za-z가-힣]", "", str(t or "")).upper()


# 판가·재료비 같은 '금액'. 소수점을 살린다
def _as_money(v, default=0):
    if v is None or v == "":
        return default
    try:
        n = float(str(v).replace(",", "").replace("$", "").replace("₩", "").strip())
    except Exception:
        return default
    if n != n or n in (float("inf"), float("-inf")):
        return default
    n = round(n, 2)
    return int(n) if n == int(n) else n


# 수량 값을 정수로. 문자열/소수/None/콤마 어느 쪽이 와도 터지지 않는다
def _as_int(v, default=0):
    if v is None or v == "":
        return default
    try:
        return int(float(str(v).replace(",", "").strip()))
    except Exception:
        return default


# 엑셀의 '키스톤 (556B)' 처럼 이름 뒤 괄호에 품번이 붙은 표기.
# 큐리는 모델명과 품번을 따로 관리하므로 갈라서 넣는다.
# __import__ 로 부르는 까닭: 테스트가 이 부분만 떼어 따로 돌린다 (re 가 없는 곳에서)
_PN_IN_LABEL = __import__("re").compile(r"^(.*?)\s*[(（]\s*([^()（）]{2,20})\s*[)）]\s*$")


# '키스톤 (556B)' -> ('키스톤', '556B').
def _split_pn(label):
    t = str(label or "").strip()
    m = _PN_IN_LABEL.match(t)
    if not m:
        return t, ""
    name, pn = m.group(1).strip(), m.group(2).strip()
    # '버스바/시트메탈류(11종)' 처럼 품번이 아니라 개수인 것은 가르지 않는다
    if not name or __import__("re").match(r"^\d+\s*종$", pn):
        return t, ""
    return name, pn


# 보드에서 여러 모델을 한 줄로 묶어둔 행.
def _board_group_rows(project_key: str) -> dict:
    out = {}
    try:
        spec = _load_board_spec(project_key) or {}
    except Exception:
        return out
    for sec in (spec.get("sections") or []):
        for row in (sec.get("rows") or []):
            ids = [str(x).strip() for x in (row.get("models") or []) if str(x).strip()]
            if len(ids) < 2:
                continue
            for name in (row.get("label"), row.get("key")):
                n = _norm_label(name)
                if n:
                    out.setdefault(n, ids)
    return out

# '구분 x 주차' 엑셀을 모델별 주차 계획 + 프로젝트 주차 합계에 반영.
def _apply_plan_matrix(data, project_key, parsed):
    proj = data.setdefault("projects", {}).setdefault(project_key, {"models": []})
    models = proj.setdefault("models", [])
    # -----------------------------------------------------------
    # 1. 등록된 모델을 이름으로 찾을 수 있게 색인을 만든다
    # -----------------------------------------------------------
    # 한 모델을 세 가지로 부를 수 있다 — 모델명 · id · 파트넘버.
    idx = {}
    for m in models:
        for k in (m.get("name"), m.get("id"), m.get("part_number")):
            n = _norm_label(k)
            if n:
                idx.setdefault(n, m)

    # 묶음 행('버스바/시트메탈류(11종)')은 모델로 만들지 않는다
    agg_rows = _board_group_rows(project_key)
    matched, unmatched, created = [], [], []
    for row in (parsed.get("rows") or []):
        label = row.get("label")
        name, pn = _split_pn(label)
        key = _norm_label(label)
        # '키스톤 (556B)' 는 이름으로도 품번으로도 찾아본다
        target = idx.get(key)
        if target is None and pn:
            target = idx.get(_norm_label(pn))
        if target is None and name:
            target = idx.get(_norm_label(name))
        # 앞뒤가 겹치면 같은 모델로 본다. 단 묶음 행에는 쓰지 않는다 —
        # '버스바/시트메탈류(11종)' 이 기존 '버스바' 한 개에 붙어버려서
        # 1,740 이 그 모델로 들어가고 나머지 10개가 따로 남았다.
        # ── 3. 그래도 못 찾았으면 '앞부분이 겹치는가' 로 한 번 더
        #    글자가 4자 이상일 때만 한다. 짧으면 엉뚱한 모델에 붙는다.
        #    묶음 줄에는 쓰지 않는다 — '버스바/시트메탈류(11종)' 이
        #    기존 '버스바' 한 개에 붙어서 1,740 이 그 모델로 다 들어가고
        #    나머지 10개가 따로 남은 적이 있다.
        if target is None and len(key) >= 4 and not row.get("is_aggregate"):
            for n, m in idx.items():
                if n.startswith(key) or key.startswith(n):
                    target = m
                    break
        # -----------------------------------------------------------
        # 4. 묶음 줄은 보드 설정을 보고 첫 모델에 얹는다
        # -----------------------------------------------------------
        # 묶음 줄('버스바/시트메탈류(11종)')은 모델로 만들지 않는다
        if target is None and row.get("is_aggregate"):
            ids = agg_rows.get(_norm_label(label)) or []
            for _id in ids:
                cand = idx.get(_norm_label(_id))
                if cand is not None:
                    target = cand
                    break

            if target is not None:
                _wp = target.setdefault("weekly_plan", {})
                for _mon, _weeks in (row.get("weeks") or {}).items():
                    _wp.setdefault(_mon, {}).update(_weeks)
                matched.append(row.get("label"))
                continue
        # -----------------------------------------------------------
        # 5. 끝까지 못 찾았으면 새 모델로 만들지 결정한다
        # -----------------------------------------------------------
        if target is None:
            # 이 줄에 주차 숫자가 하나라도 있는가
            has_week = False
            for _weeks in (row.get("weeks") or {}).values():
                if _weeks:
                    has_week = True
                    break

            # 만들지 않고 '못 찾았다'로 넘기는 두 경우
            #   · 묶음 줄 — 그 밑에 개별 모델이 따로 있어서 또 만들면
            #     같은 수량이 두 번 세어진다
            #   · 숫자가 하나도 없는 줄 — 만들어 봐야 빈 모델이다
            if row.get("is_aggregate") or not has_week:
                unmatched.append(row)
                continue
            target = {
                "id": pn or label,
                "name": name or label,
                "part_number": pn or label,
                "group": "양산",
                "dev_type": "",
                "price": 0,
                "material_cost": 0,
                "po_qty": 0,
                "shipped_qty": 0,
                "status": "정상",
                "progress": 0,
            }
            if row.get("site"):
                target["site"] = row.get("site")
            if row.get("stock") is not None:
                target["stock"] = row.get("stock")
            models.append(target)
            idx.setdefault(key, target)
            created.append(row.get("label"))

        wp = target.setdefault("weekly_plan", {})
        last_month = None
        for month, weeks in (row.get("weeks") or {}).items():
            bucket = wp.setdefault(month, {})
            bucket.update(weeks)          # 최신 업로드가 덮어씀
            if last_month is None or month > last_month:
                last_month = month
        for month, mv in (row.get("months") or {}).items():
            if month in (row.get("weeks") or {}):
                continue
            if mv.get("plan"):
                target.setdefault("monthly_plan", {})[month] = int(mv.get("plan") or 0)
            if mv.get("actual"):
                target.setdefault("monthly_actual", {})[month] = int(mv.get("actual") or 0)

        # 시트에 적힌 원문 그대로 (감사용 사본)
        if row.get("po_qty"):
            target["po_total"] = _as_int(row.get("po_qty"))
        if row.get("shipped_qty"):
            target["shipped_total"] = _as_int(row.get("shipped_qty"))
        if row.get("remaining"):
            target["remaining_total"] = _as_int(row.get("remaining"))

        # 이번 달 주차 계획/실적 합계. 누적값과는 다른 값이다.
        _p = 0        # 이번 달 주차 계획 합계
        _a = 0        # 이번 달 주차 실적 합계
        if last_month:
            _b = wp.get(last_month) or {}
            for v in _b.values():
                cell = v or {}
                _p += _as_int(cell.get("plan"))
                _a += _as_int(cell.get("actual"))

        # po_qty / shipped_qty 는 '지금까지 받은 주문 전체 / 지금까지 나간 전체'다
        _po_x = _as_int(row.get("po_qty"))
        _sh_x = _as_int(row.get("shipped_qty"))
        if _po_x:
            target["po_qty"] = _po_x
        elif not _as_int(target.get("po_qty")) and _p:
            target["po_qty"] = _p
        if _sh_x:
            target["shipped_qty"] = _sh_x
        elif not _as_int(target.get("shipped_qty")) and _a:
            target["shipped_qty"] = _a

        if last_month:
            # due_text 는 담당자가 직접 적는 납기 칸이다 (예: '8월 24일').
            has_numbers = bool(_p or _a)
            due_empty = not str(target.get("due_text") or "").strip()
            if has_numbers and due_empty:
                target["due_text"] = f"{last_month} 주차계획 · 잔여 {_p - _a}개"
            try:
                target["weekly_progress"] = _ensure_mass_progress(wp, last_month)
            except Exception:
                pass
        matched.append({"label": row.get("label"),
                        "model": target.get("name") or target.get("id")})
    # -----------------------------------------------------------
    # 프로젝트 주차 합계 (양산/개발)
    # -----------------------------------------------------------
    # 시트에는 개별 모델 행과 그것을 요약한 집계 행('양산 19종', '개발 22종')이 같이 들어 있다
    ws_out = proj.setdefault("weekly_summary", {})
    for grp in ("양산", "개발"):
        # -----------------------------------------------------------
        # 1. 이 구분(양산/개발)에 속한 줄만 고른다
        # -----------------------------------------------------------
        #    줄 이름에 '개발'이 들어 있으면 개발, 아니면 양산으로 본다.
        want_dev = (grp == "개발")
        rows_g = []
        for r in (parsed.get("rows") or []):
            is_dev = "개발" in str(r.get("label") or "")
            if is_dev == want_dev:
                rows_g.append(r)
        if not rows_g:
            continue
        # -----------------------------------------------------------
        # 2. 개별 모델 줄만 추린다
        # -----------------------------------------------------------
        #    시트에는 개별 줄과 그걸 요약한 묶음 줄('양산 19종')이 같이
        #    들어 있다. 둘을 다 더하면 정확히 두 배가 된다.
        detail = []
        for r in rows_g:
            if not r.get("is_aggregate"):
                detail.append(r)

        # 개별 줄이 하나도 없으면 묶음 줄이 유일한 자료다 (하바 개발이 그렇다)
        src = detail or rows_g
        # -----------------------------------------------------------
        # 3. 구분 단위 합계
        # -----------------------------------------------------------
        g = ws_out.setdefault(grp, {})
        g["po_qty"] = 0
        g["actual_total"] = 0
        g["remaining"] = 0
        for r in src:
            g["po_qty"] += _as_int(r.get("po_qty"))
            g["actual_total"] += _as_int(r.get("shipped_qty"))
            g["remaining"] += _as_int(r.get("remaining"))
        weeks = g.setdefault("weeks", {})
        agg = {}
        for r in src:
            for _month, wk in (r.get("weeks") or {}).items():
                for w, cell in wk.items():
                    tgt = agg.setdefault(w, {"plan": 0, "actual": 0})
                    tgt["plan"] += _as_int((cell or {}).get("plan"))
                    tgt["actual"] += _as_int((cell or {}).get("actual"))
        weeks.update(agg)          # 이번 업로드에 있는 주차만 갱신

    # 양산을 앞에, 개발을 뒤에 (같은 구분 안에서는 원래 순서 그대로)

    models.sort(key=lambda m: 0 if m.get("group") == "양산" else 1)
    return {"matched": matched,
            "created": created,
            "unmatched": [r.get("label") for r in unmatched],
            "months": parsed.get("months") or []}


# 엑셀에서 빨간(유채색) 굵은 테두리로 표시한 주차 라벨을 찾아 ['W35'] 형태로 반환.
def _detect_marked_weeks(ws):
    import re as _re
    marked_cols = set()
    for row in ws.iter_rows():
        for cell in row:
            try:
                bd = cell.border
            except Exception:
                continue
            if bd is None:
                continue
            for side in (bd.left, bd.right, bd.top, bd.bottom):
                if side is None or not getattr(side, "style", None):
                    continue
                col = getattr(side, "color", None)
                if col is None or getattr(col, "type", None) != "rgb":
                    continue
                v = col.rgb
                if not isinstance(v, str):
                    continue
                if len(v) == 8:
                    v = v[2:]
                v = v.upper()
                if v in ("000000", "FFFFFF"):
                    continue
                try:
                    r_, g_, b_ = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
                except Exception:
                    continue
                if (max(r_, g_, b_) - min(r_, g_, b_)) > 40 or side.style in ("thick", "double"):
                    marked_cols.add(cell.column)
                    break
    if not marked_cols:
        return []

    merged = {}
    for rng in ws.merged_cells.ranges:
        mc, mr, xc, xr = rng.bounds
        merged[(mr, mc)] = (xr, xc)

    weeks = []
    for row in ws.iter_rows():
        for cell in row:
            t = str(cell.value or "").strip()
            m = _re.match(r"^W\s*(\d{1,2})$", t, _re.I)
            if not m:
                continue
            _xr, xc = merged.get((cell.row, cell.column), (cell.row, cell.column))
            if set(range(cell.column, xc + 1)) & marked_cols:
                try:
                    weeks.append("W%02d" % int(m.group(1)))
                except Exception:
                    pass
    out = sorted(set(weeks), key=lambda w: int(w[1:]))
    return out


# 엑셀 첫 시트를 그림(PNG)으로 그려 미리보기용 data URL 로 만든다
def _excel_sheet_to_preview_data_url(ws):
    from io import BytesIO
    import base64
    from PIL import Image, ImageDraw, ImageFont, ImageChops

    NL = chr(10)

    def _effective_sheet_bounds():
        coords = []

        def _has_value(v):
            return v is not None and str(v).strip() != ""

        def _has_border(cell):
            try:
                b = cell.border
                return any([
                    b.left and b.left.style,
                    b.right and b.right.style,
                    b.top and b.top.style,
                    b.bottom and b.bottom.style,
                ])
            except Exception:
                return False

        def _has_fill(cell):
            try:
                f = cell.fill
                if f and f.fgColor and f.fgColor.rgb:
                    rgb = str(f.fgColor.rgb)
                    # 투명/흰색 제외
                    if rgb not in ("00000000", "FFFFFFFF", "FFFFFF", "None"):
                        return True
            except Exception:
                pass
            return False

        # 값 OR 테두리 OR 배경색 있는 셀 모두 포함
        for row in ws.iter_rows():
            for cell in row:
                if _has_value(cell.value) or _has_border(cell) or _has_fill(cell):
                    coords.append((cell.row, cell.column))

        # 병합 셀은 anchor 값이 있으면 병합 범위 전체 포함
        for rng in ws.merged_cells.ranges:
            min_col2, min_row2, max_col2, max_row2 = rng.bounds
            anchor = ws.cell(min_row2, min_col2)
            if _has_value(anchor.value) or _has_border(anchor) or _has_fill(anchor):
                coords.append((min_row2, min_col2))
                coords.append((max_row2, max_col2))

        if not coords:
            return 1, 1, 1, 1

        min_row2 = min(r for r, c in coords)
        max_row2 = max(r for r, c in coords)
        min_col2 = min(c for r, c in coords)
        max_col2 = max(c for r, c in coords)
        return min_row2, max_row2, min_col2, max_col2

    min_row, max_row, min_col, max_col = _effective_sheet_bounds()

    anchor_map = {}
    skip = set()
    for rng in ws.merged_cells.ranges:
        mc, mr, max_col2, max_row2 = rng.bounds
        anchor_map[(mr, mc)] = (max_row2, max_col2)
        for rr in range(mr, max_row2 + 1):
            for cc in range(mc, max_col2 + 1):
                if (rr, cc) != (mr, mc):
                    skip.add((rr, cc))

    # 한글 폰트 후보 (Mac → Linux/Railway 순)
    _font_candidates = [
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
    ]
    _font_bold_candidates = [
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKkr-Bold.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf",
    ]

    def _load_font(candidates, size):
        import os
        for fp in candidates:
            if os.path.exists(fp):
                try:
                    return ImageFont.truetype(fp, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    font = _load_font(_font_candidates, 22)
    font_bold = _load_font(_font_bold_candidates, 22)

    def text_size(txt, f):
        try:
            bbox = f.getbbox(txt)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            return (len(txt) * 11, 22)

    def format_value(cell):
        v = cell.value
        if v is None:
            return ""
        nf = (cell.number_format or "").lower()
        if isinstance(v, (int, float)) and ("#,##0" in nf or "0" in nf):
            try:
                iv = int(v)
                if iv == 0:
                    return "-"
                return f"{iv:,}" if iv >= 0 else f"-{abs(iv):,}"
            except Exception:
                return str(v)
        if isinstance(v, str):
            try:
                if v.strip() and v.strip().lstrip("-").isdigit():
                    iv = int(v)
                    if iv == 0:
                        return "-"
                    return f"{iv:,}" if iv >= 0 else f"-{abs(iv):,}"
            except Exception:
                pass
        return str(v)

    cell_text = {}
    for r in range(min_row, max_row + 1):
        for c in range(min_col, max_col + 1):
            cell_text[(r, c)] = format_value(ws.cell(r, c))

    col_widths = [0] * (max_col + 2)
    for c in range(min_col, max_col + 1):
        widest = 72
        for r in range(min_row, max_row + 1):
            if (r, c) in skip:
                continue
            t = cell_text.get((r, c), "")
            if not t:
                continue
            use_font = font_bold if (ws.cell(r, c).font and ws.cell(r, c).font.b) else font
            for line in t.split(NL):
                w, _ = text_size(line, use_font)
                if w + 24 > widest:
                    widest = min(w + 24, 320)
        col_widths[c] = widest

    row_heights = [0] * (max_row + 2)
    for r in range(min_row, max_row + 1):
        lines_max = 1
        for c in range(min_col, max_col + 1):
            t = cell_text.get((r, c), "")
            lines = max(1, t.count(NL) + 1)
            if lines > lines_max:
                lines_max = lines
        row_heights[r] = max(40, 14 + 26 * lines_max)

    # 표 범위만 그리도록 인덱스 맵 통일
    cols = list(range(min_col, max_col + 1))
    rows = list(range(min_row, max_row + 1))
    col_idx = {c: i for i, c in enumerate(cols)}
    row_idx = {r: i for i, r in enumerate(rows)}

    W = sum(col_widths[c] for c in cols)
    H = sum(row_heights[r] for r in rows)

    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    xs = [0]
    for c in cols:
        xs.append(xs[-1] + col_widths[c])
    ys = [0]
    for r in rows:
        ys.append(ys[-1] + row_heights[r])

    def argb_to_hex(argb):
        if not argb:
            return None
        v = str(argb)
        if v in ("00000000", "None"):
            return None
        if len(v) == 8:
            v = v[2:]
        if len(v) == 6:
            try:
                int(v, 16)
                return "#" + v.lower()
            except Exception:
                return None
        return None

    def get_fill(cell):
        try:
            fg = cell.fill.fgColor
            if fg is not None and getattr(fg, "type", None) == "rgb":
                return argb_to_hex(fg.rgb)
        except Exception:
            pass
        return None

    def get_font_color(cell):
        try:
            c = cell.font.color
            if c is not None and getattr(c, "type", None) == "rgb":
                return argb_to_hex(c.rgb)
        except Exception:
            pass
        return None

    def is_dark(hex_color):
        try:
            v = hex_color.lstrip("#")
            r = int(v[0:2], 16)
            g = int(v[2:4], 16)
            b = int(v[4:6], 16)
            return (0.299 * r + 0.587 * g + 0.114 * b) < 160
        except Exception:
            return False

    for r in range(min_row, max_row + 1):
        for c in range(min_col, max_col + 1):
            if (r, c) in skip:
                continue
            x1, y1 = xs[col_idx[c]], ys[row_idx[r]]
            rr, cc = anchor_map.get((r, c), (r, c))
            x2, y2 = xs[col_idx[cc] + 1], ys[row_idx[rr] + 1]
            cell = ws.cell(r, c)
            bg = get_fill(cell) or "#ffffff"
            fc = get_font_color(cell)
            if not fc:
                fc = "#ffffff" if is_dark(bg) else "#111111"
            draw.rectangle([x1, y1, x2 - 1, y2 - 1], fill=bg, outline="#cbd5e1", width=1)
            val = cell_text.get((r, c), "")
            if val:
                lines = val.split(NL)
                line_h = 26
                total_h = line_h * len(lines)
                ty = y1 + max(4, ((y2 - y1) - total_h) // 2)
                use_font = font_bold if (cell.font and cell.font.b) else font
                cell_w = x2 - x1
                for li, line in enumerate(lines):
                    w, _ = text_size(line, use_font)
                    tx = x1 + max(4, (cell_w - w) // 2)
                    draw.text((tx, ty + li * line_h), line, fill=fc, font=use_font)
    # -----------------------------------------------------------
    # 엑셀에서 강조한 테두리(빨간 박스 등) 재현
    # -----------------------------------------------------------
    # (색, 두께) — 유채색이거나 굵은 선일 때만.
    def _side_accent(side):
        if side is None or not getattr(side, "style", None):
            return None
        col = getattr(side, "color", None)
        if col is None or getattr(col, "type", None) != "rgb":
            return None
        v = col.rgb
        if not isinstance(v, str):
            return None
        if len(v) == 8:
            v = v[2:]
        v = v.upper()
        if v in ("000000", "FFFFFF"):
            return None
        try:
            r_, g_, b_ = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
        except Exception:
            return None
        colorful = (max(r_, g_, b_) - min(r_, g_, b_)) > 40
        heavy = side.style in ("thick", "double", "medium")
        if not (colorful or heavy):
            return None
        return ("#" + v.lower(), 4 if side.style in ("thick", "double") else 3)

    marked = {}
    for r in range(min_row, max_row + 1):
        for c in range(min_col, max_col + 1):
            try:
                bd = ws.cell(r, c).border
            except Exception:
                continue
            if bd is None:
                continue
            best = None
            for side in (bd.left, bd.right, bd.top, bd.bottom):
                acc = _side_accent(side)
                if acc and (best is None or acc[1] > best[1]):
                    best = acc
            if best:
                marked[(r, c)] = best

    if marked:
        # 병합 셀은 범위 전체를 함께 표시로 취급
        for rng in ws.merged_cells.ranges:
            mc, mr, xc, xr = rng.bounds
            hit = None
            for rr in range(mr, xr + 1):
                for cc in range(mc, xc + 1):
                    if (rr, cc) in marked:
                        hit = marked[(rr, cc)]
                        break
                if hit:
                    break
            if hit:
                for rr in range(max(mr, min_row), min(xr, max_row) + 1):
                    for cc in range(max(mc, min_col), min(xc, max_col) + 1):
                        marked.setdefault((rr, cc), hit)

        # 연결된 덩어리별로 바깥선만 그린다
        seen = set()
        for origin in list(marked.keys()):
            if origin in seen:
                continue
            comp = []
            stack = [origin]
            seen.add(origin)
            while stack:
                cur = stack.pop()
                comp.append(cur)
                cr, cc2 = cur
                for nb in ((cr - 1, cc2), (cr + 1, cc2), (cr, cc2 - 1), (cr, cc2 + 1)):
                    if nb in marked and nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
            comp_set = set(comp)
            line_col, line_w = marked[origin]
            for cell_rc in comp:
                if marked[cell_rc][1] > line_w:
                    line_col, line_w = marked[cell_rc]
            hw = max(1, line_w // 2)

            def _cx(v):
                return min(max(v, hw), max(hw, W - 1 - hw))

            def _cy(v):
                return min(max(v, hw), max(hw, H - 1 - hw))

            for (cr, cc2) in comp:
                x1, x2 = xs[col_idx[cc2]], xs[col_idx[cc2] + 1]
                y1, y2 = ys[row_idx[cr]], ys[row_idx[cr] + 1]
                if (cr - 1, cc2) not in comp_set:
                    draw.line([(_cx(x1 - hw), _cy(y1)), (_cx(x2 + hw), _cy(y1))],
                              fill=line_col, width=line_w)
                if (cr + 1, cc2) not in comp_set:
                    draw.line([(_cx(x1 - hw), _cy(y2)), (_cx(x2 + hw), _cy(y2))],
                              fill=line_col, width=line_w)
                if (cr, cc2 - 1) not in comp_set:
                    draw.line([(_cx(x1), _cy(y1 - hw)), (_cx(x1), _cy(y2 + hw))],
                              fill=line_col, width=line_w)
                if (cr, cc2 + 1) not in comp_set:
                    draw.line([(_cx(x2), _cy(y1 - hw)), (_cx(x2), _cy(y2 + hw))],
                              fill=line_col, width=line_w)

    # 마지막 흰 여백 소폭 trim
    try:
        bg = Image.new(img.mode, img.size, "white")
        diff = ImageChops.difference(img, bg)
        bbox = diff.getbbox()
        if bbox:
            l, t, r, b = bbox
            # 공백 최소화: 거의 딱 맞게 자르되 2px만 여유
            pad_x = 2
            pad_y = 2
            img = img.crop((
                max(0, l - pad_x),
                max(0, t - pad_y),
                min(img.width, r + pad_x),
                min(img.height, b + pad_y),
            ))
    except Exception:
        pass

    bio = BytesIO()
    img.save(bio, format="PNG")
    return "data:image/png;base64," + base64.b64encode(bio.getvalue()).decode("ascii")


# 엑셀(.xlsx/.xlsm) 업로드 → 첫 시트를 PNG 이미지로 변환 → 사진처럼 저장 → photo_ref 반환 ← static · excel_drop.js
@app.post("/admin/notes/excel")
async def admin_upload_note_excel(
    division_id: str = Form(...),
    file: UploadFile = File(...),
    _admin: int = Depends(get_admin_session),
):
    division_id = (division_id or "").strip()
    if not division_id:
        raise HTTPException(status_code=400, detail="division_id 필수")

    orig_name = file.filename or "upload.xlsx"
    lower = orig_name.lower()
    if not (lower.endswith(".xlsx") or lower.endswith(".xlsm")):
        raise HTTPException(status_code=400, detail="xlsx/xlsm 파일만 허용")

    raw = await _keep_upload(file, "/admin/notes/excel", "")
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일")

    try:
        import openpyxl
        from io import BytesIO
        import base64
        wb = openpyxl.load_workbook(BytesIO(raw), data_only=True, keep_links=False)
        ws = wb.worksheets[0]
        data_url = _excel_sheet_to_preview_data_url(ws)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"엑셀 변환 실패: {e}")

    # data:image/png;base64,... → 바이트 디코드
    try:
        b64 = data_url.split(",", 1)[1]
        png_bytes = base64.b64decode(b64)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PNG 디코딩 실패: {e}")

    asset_id = "xls_" + _new_asset_id(division_id)
    out_path = _photo_path(division_id, asset_id, "png")
    out_path.write_bytes(png_bytes)
    photo_ref = f"{division_id}/{asset_id}.png"

    return {
        "ok": True,
        "filename": orig_name,
        "photo_ref": photo_ref,
        "url": f"/note_photos/{photo_ref}",
    }

# 노트에 붙인 사진 하나 지우기 (잠김).
@app.delete("/admin/notes/photo/{division_id}/{filename}")
def admin_delete_note_photo(division_id: str, filename: str, _admin: int = Depends(get_admin_session)):
    photo_ref = f"{division_id}/{filename}"
    ok = _delete_note_photo(photo_ref)
    if not ok:
        raise HTTPException(status_code=404, detail="사진이 없음")
    return {"deleted": True, "photo_ref": photo_ref}

# ============================================================
#  사업부 · 프로젝트 목록
# ============================================================
# 공개 사업부 목록 + 각 사업부의 visible 프로젝트 리스트 ← admin v2 fillDivisions() · 앱 divisions_service.dart
@app.get("/divisions")
def list_divisions():
    _hidden = _dvis.hidden_set()
    divs = [d for d in _cl.get_divisions(visible_only=True)
            if str(d.get("id") or "").lower() not in _hidden]

    # 모델/현황/주차별 계획 데이터 로드 (프로젝트별 데이터 유무)
    models_data = _load_models()
    models_by_project = {}
    # 고객사 묶음 — 양식 '국내/해외' 칸으로 들어온 값
    _cgroup = {k: v.get("customer_group") for k, v in
               (models_data.get("projects") or {}).items()
               if isinstance(v, dict) and v.get("customer_group")}
    # 프로젝트의 종류 — 모델 '구분 1'(dev_type) 중 가장 많은 것 (아리스타 묶음)
    _ptype = {}
    for _k, _v in (models_data.get("projects") or {}).items():
        _c = {}
        for _m in (_v.get("models") or []) if isinstance(_v, dict) else []:
            _t = str((_m or {}).get("dev_type") or "").strip() if isinstance(_m, dict) else ""
            if _t:
                _c[_t] = _c.get(_t, 0) + 1
        if _c:
            # 가장 많이 쓴 구분 (개수가 같으면 이름순으로 앞선 것)
            def _by_count_then_name(kv):
                type_name, count = kv
                return (-count, type_name)
            _ptype[_k] = sorted(_c.items(), key=_by_count_then_name)[0][0]
    for proj_key, proj_data in models_data.get("projects", {}).items():
        has_models = len(proj_data.get("models", [])) > 0
        has_note = bool((proj_data.get("status_note") or "").strip())
        has_plan = bool(proj_data.get("weekly_plan", {}).get("photo_ref"))
        if has_models or has_note or has_plan:
            models_by_project[proj_key] = len(proj_data.get("models", []))

    result = []
    for d in divs:
        div_id = d.get("id")
        # 해당 사업부의 visible 프로젝트만 (order 순)
        try:
            ps = _cl.get_projects(div_id, visible_only=True)
        except Exception:
            ps = []
        ps_sorted = sorted(ps, key=lambda x: x.get("order", 999))
        # 같은 사업부 고객사 이름 전부 — 자동차는 이름 첫 낱말로 묶는다 (brand_map)
        _peers = [p.get("label") or "" for p in ps_sorted]
        # 고객사마다 묶음 — 묶지 않는 사업부면 None 이라 빠진다
        _groups_seen = []
        for p in ps_sorted:
            _grp = _dcol.customer_group(div_id, p.get("id"), _cgroup.get(p.get("id")),
                                        p.get("label"), _ptype.get(p.get("id")), _peers)
            if _grp:
                _groups_seen.append(_grp)
        result.append({
            "id": div_id,
            "label": d.get("label"),
            "order": d.get("order", 999),
            "badge_short_label": d.get("badge_short_label"),
            # 앱이 들고 있던 글자를 서버로
            #   owner_label  '고객사 22개' 의 '고객사' (division_columns FORMS)
            #   group_title  묶은 목록 위 작은 제목 ('국내 / 해외' · '고객사별')
            "owner_label": _dcol.columns_for(div_id)["owner_label"],
            "group_title": _dcol.group_title(div_id),
            # 고객사 묶음 —
            # 앱이 국내 / 해외로 나눠 그린다. 묶지 않는 사업부는 빈 목록.
            #    엑셀(양식 '국내/해외' 칸)로 들어온 값이 먼저다.
            "customer_groups": _dcol.customer_group_order(div_id, _groups_seen),
            "projects": [
                {
                    "id": p.get("id"),
                    # 화면 이름만 다듬는다 ('KMW HÀ nam' → 'KMW HA NAM'). 저장은 원문 그대로.
                    "label": _dcol.clean_label(p.get("label")),
                    "order": p.get("order", 999),
                    "has_models": p.get("id") in models_by_project,
                    "model_count": models_by_project.get(p.get("id"), 0),
                    "group": _dcol.customer_group(div_id, p.get("id"),
                                                  _cgroup.get(p.get("id")), p.get("label"),
                                                  _ptype.get(p.get("id")), _peers),
                }
                for p in ps_sorted
            ],
        })
    result.sort(key=lambda x: x.get("order", 999))
    return {"divisions": result}


# 각 사업부의 최신 업데이트 타임스탬프 반환.
@app.get("/divisions/updates")
def get_divisions_updates():
    try:
        with open(LATEST_FILE, "r", encoding="utf-8") as f:
            reports = json.load(f)
    except Exception:
        reports = []

    div_latest: dict[str, str] = {}

    for item in reports:
        ts = item.get("upload_timestamp") or ""
        products = item.get("products") or []
        for p in products:
            project_id = p.get("project_key") or p.get("project") or None
            if not project_id:
                parts = [
                    p.get("name") or "",
                    p.get("headline") or "",
                    " ".join(p.get("summary_bullets") or []),
                ]
                text = " ".join(s for s in parts if s)
                if text.strip():
                    try:
                        project_id = _cl.classify_project(text)
                    except Exception:
                        project_id = None

            div_id = _cl.derive_division_from_project(project_id) if project_id else None
            if not div_id:
                div_id = "unclassified"

            card_ts = p.get("updated_at") or ts
            if not card_ts:
                continue
            cur = div_latest.get(div_id, "")
            if card_ts > cur:
                div_latest[div_id] = card_ts

    all_divs = _cl.get_divisions(visible_only=True)
    result = []
    for d in all_divs:
        did = d.get("id")
        result.append({
            "division_id": did,
            "label": d.get("label"),
            "latest_updated_at": div_latest.get(did, ""),
        })

    return {"divisions": result}

# 프로젝트 버튼 목록 + 모델 데이터 유무 ← admin v2 _npLoadProjectButtons() · loadProjectOptions() · loadModels() 외
@app.get("/projects")
def list_projects():
    import config_loader
    config_projects = config_loader.get_projects(visible_only=False)

    models_data = _load_models()
    models_by_project = {}
    for proj_key, proj_data in models_data.get("projects", {}).items():
        models_list = proj_data.get("models", [])
        if models_list:
            models_by_project[proj_key] = len(models_list)

    projects = []
    for p in config_projects:
        proj_key = p.get("id") or p.get("key")
        projects.append({
            "key": proj_key,
            "label": p.get("label", proj_key.upper()),
            "status": "BLACK",
            "report_date": None,
            "has_models": models_by_project.get(proj_key, 0) > 0,
            "model_count": models_by_project.get(proj_key, 0),
            "division_id": p.get("division_id", "semiconductor"),
        })

    for proj_key, model_count in models_by_project.items():
        if not any(p["key"] == proj_key for p in projects):
            projects.append({
                "key": proj_key,
                "label": proj_key.upper(),
                "status": "BLACK",
                "report_date": None,
                "has_models": True,
                "model_count": model_count,
                "division_id": "ess" if proj_key.startswith("ess_") else "semiconductor",
            })

# ============================================================
#  모델 목록 양식 · 가져오기 (예전 방식)
# ============================================================
    return {"projects": projects}
# 모델 등록용 빈 엑셀 양식 ← admin v2 tplBtn.onclick() · _nm.onclick()
@app.get("/admin/models/template")
def admin_models_template(project_key: str = "", _admin: int = Depends(get_admin_session)):
    from urllib.parse import quote
    import model_template as _mt

    label, types = "", []
    key = (project_key or "").strip()
    if key:
        try:
            label = _display_project_label(key)
            proj = (_load_models().get("projects") or {}).get(_model_key_alias(key)) or {}
            types = [t for t in (proj.get("types") or []) if str(t).strip()]
        except Exception as _e:
            print(f"[models/template] {key} 정보 조회 실패(무시): {_e}")

    data = _mt.build_model_template(label, types)
    fname = f"{label + ' ' if label else ''}모델 등록 양식.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f"attachment; filename=model_template.xlsx; filename*=UTF-8''{quote(fname)}"},
    )


# 모델 목록 엑셀 올리기 (예전 방식) ← admin v2 doExcelUpload()
@app.post("/admin/projects/{project_key}/models/import")
async def admin_models_import(project_key: str, file: UploadFile = File(...), _admin: int = Depends(get_admin_session)):
    _form_only("models-import")
    from io import BytesIO
    from openpyxl import load_workbook
    raw = await _keep_upload(file, "/admin/projects/{project_key}/models/import", project_key)
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    try:
        wb = load_workbook(BytesIO(raw), data_only=True, keep_links=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"엑셀 파싱 실패: {e}")
    ws = wb.active
    # -----------------------------------------------------------
    # 개발현황 엑셀이 먼저다.
    # -----------------------------------------------------------
    # 열 이름이 모델 등록 양식과 겹쳐서('모델', '판가', '비고') 아래 일반
    # 파서가 그냥 읽어버리면 'PO 잔량' 이 'PO 수량' 자리를 덮고, '구분' 열이
    # 없어서 개발품이 양산으로 들어간다. 모양을 먼저 알아본다.
    try:
        import dev_status_import as _dsi
        _dev = _dsi.parse_workbook(wb)
    except Exception as _e:
        print(f"[models/import] 개발현황 판별 실패(무시): {_e}")
        _dev = None
    if _dev and _dev.get("rows"):
        _res = _apply_dev_status(project_key, _dev)
        _res["auto_detected"] = "dev_status"
        print(f"[models/import] 개발현황 형식 자동 인식 → {_dev.get('sheet')} "
              f"{len(_dev['rows'])}행")
        return _res

    # 헤더 행 탐색: '모델' 텍스트가 있는 행
    header_row = None
    col_map = {}
    for r in range(1, min(ws.max_row, 10) + 1):
        for c in range(1, ws.max_column + 1):
            v = ws.cell(row=r, column=c).value
            if v is None:
                continue
            t = str(v).strip()
            k = t.replace(" ", "").replace(".", "").lower()
            if k in ("모델", "모델명"):
                header_row = r
                col_map["name"] = c
            elif k == "구분":
                col_map["group"] = c
            elif k in ("유형", "개발유형", "type", "devtype"):
                # 예전에는 여기만 원문을 그대로 비교해서, '개발유형' 처럼 공백이 없거나 셀에 공백이 낀 머리글을 통째로 놓쳤다
                col_map["dev_type"] = c
            elif "비율" in k:
                # '재료비율' 은 양식에서 수식 칸이다
                continue
            elif k.startswith("판가"):
                col_map["price"] = c
            elif k.startswith("재료비"):
                col_map["material_cost"] = c
            elif k in ("파트넘버", "파트번호", "품번", "partno", "partnumber"):
                col_map["part_number"] = c
            elif k in ("po", "po수량", "poqty", "poq'ty", "발주수량"):
                # 'PO 잔량' 도 po 로 시작한다. startswith 로 잡으면 뒤에 나오는
                # 잔량이 PO 수량 자리를 덮어써서 수량이 통째로 틀어진다.
                col_map["po_qty"] = c
            elif k in ("실적수량", "출하수량", "출하실적", "실적", "출하"):
                col_map["shipped_qty"] = c
            elif k in ("전환주차", "양산전환", "양산전환주차", "전환", "전환시점",
                       "개발→양산전환주차", "개발->양산전환주차",
                       "개발→양산", "개발->양산"):
                # 추가 — 개발 → 양산으로 넘어간 주차.
                # 이 칸이 생기기 전에는 화면에서 손으로 넣었는데, 엑셀과
                # 어긋나면 어느 쪽이 맞는지 알 길이 없었다. 이제 엑셀이 기준이다.
                col_map["switch_week"] = c
            elif t == "비고":
                col_map["note"] = c
        if header_row:
            break
    if not header_row or "name" not in col_map:
        # 모델 템플릿이 아니라 '주간 보고 엑셀(W##.xlsx)' 일 수 있다 → 자동 판별해서 처리
        try:
            import hrva_import as _imp
            _parsed = _imp.parse_workbook(wb)
        except Exception:
            _parsed = None
        if _parsed and _parsed.get("models"):
            _res = _apply_report_workbook(project_key, _parsed)
            _res["auto_detected"] = "weekly_report"
            # 주간보고 파서가 못 읽는 값들(주차별 '변동' = PO증감, 진행중/완료 종수,
            # 그룹 누적 출하)을 현황 파서로 한 번 더 훑어서 채운다.
            try:
                _res["enriched"] = _enrich_from_status(project_key, wb)
            except Exception as _e:
                print(f"[models/import] 현황 보강 실패(무시): {_e}")
            print(f"[models/import] 주간보고 형식 자동 인식 → {_parsed.get('sheet')}")
            return _res
        raise HTTPException(
            status_code=400,
            detail="양식 오류: '모델' 헤더를 찾을 수 없습니다. "
                   "주간 보고 엑셀(W##.xlsx)이라면 '주차별 계획' 탭의 '주간보고 업로드'를 사용하세요.",
        )

    _key = project_key.strip()
    data = _load_models()
    projs = data.setdefault("projects", {})
    proj = projs.setdefault(_key, {"models": []})
    models = proj.setdefault("models", [])
    # 파트넘버가 있으면 그게 열쇠다
    by_name = {str(m.get("name", "")).strip().lower(): m for m in models}
    by_pn = {}
    for m in models:
        _p = str(m.get("part_number") or "").strip().lower()
        if _p:
            by_pn[_p] = m

    # 한 파일 안에서 같은 파트넘버가 두 번 이상 나오면, 그 파트넘버는 열쇠로 못 쓴다
    _pn_seen = {}
    if col_map.get("part_number"):
        for _r in range(header_row + 1, ws.max_row + 1):
            _v = ws.cell(row=_r, column=col_map["part_number"]).value
            _k = str(_v).strip().lower() if _v is not None else ""
            if _k:
                _pn_seen[_k] = _pn_seen.get(_k, 0) + 1
    _pn_dup = {k for k, n in _pn_seen.items() if n > 1}
    if _pn_dup:
        print(f"[models-import] 파일 안에서 겹치는 파트넘버 {len(_pn_dup)}개 "
              f"— 그 줄은 '파트넘버 + 모델명' 짝으로 맞춥니다")

    # 겹치는 파트넘버는 모델명만으로도 못 가른다. 아리스타 양산이 그렇다 —
    # 모델명이 출하처(Jabil Malaysia)뿐이라 품번 16개에 같은 이름이 걸린다.
    # 그래서 '파트넘버 + 모델명' 짝을 열쇠로 쓴다.
    by_pnname = {}
    for _m in models:
        _p = str(_m.get("part_number") or "").strip().lower()
        if _p:
            by_pnname[(_p, str(_m.get("name", "")).strip().lower())] = _m

    added, updated, skipped = 0, 0, 0
    skipped_rows = []
    for r in range(header_row + 1, ws.max_row + 1):
        name_v = ws.cell(row=r, column=col_map["name"]).value
        pn_v = ws.cell(row=r, column=col_map["part_number"]).value if col_map.get("part_number") else None
        pn = str(pn_v).strip() if pn_v is not None else ""
        if (name_v is None or not str(name_v).strip()) and not pn:
            # 모델명도 파트넘버도 없는 줄. 양식의 남는 빈 줄이 대부분이라
            # 조용히 넘기되, 뭔가 적혀 있던 줄이면 세어서 알려준다.
            if any(ws.cell(row=r, column=c).value not in (None, "")
                   for c in col_map.values()):
                skipped += 1
                if len(skipped_rows) < 20:
                    skipped_rows.append(
                        {"row": r, "why": "모델명과 파트넘버가 둘 다 비었습니다"})
            continue
        # 모델명 칸이 비어 있으면 비어 있는 대로 둔다
        name = str(name_v).strip() if name_v is not None else ""
        if not name and not pn:
            continue
        group = str(ws.cell(row=r, column=col_map.get("group", 0)).value or "").strip() if col_map.get("group") else ""
        group = "개발" if group == "개발" else "양산"
        dev_type = str(ws.cell(row=r, column=col_map.get("dev_type", 0)).value or "").strip() if col_map.get("dev_type") else ""

        def _num(col):
            if not col:
                return 0
            v = ws.cell(row=r, column=col).value
            try:
                return float(str(v).replace(",", "").replace("$", "").strip() or 0)
            except Exception:
                return 0

        # 그 칸에 사람이 뭔가 적었나.
        def _filled(col):
            if not col:
                return False
            v = ws.cell(row=r, column=col).value
            return v is not None and str(v).strip() != ""

        price = _num(col_map.get("price"))
        mcost = _num(col_map.get("material_cost"))
        # -----------------------------------------------------------
        # 전환주차
        # -----------------------------------------------------------
        # 엑셀에 '2026-W36' 처럼 적어 두면 그 주차부터 양산으로 본다.
        # 빈 칸이면 지금 이력을 그대로 둔다. '-' 나 '없음' 이면 이력을 지운다
        # (처음부터 끝까지 한 구분이라는 뜻).
        _sw_raw = ""
        if col_map.get("switch_week"):
            _sw_raw = str(ws.cell(row=r, column=col_map["switch_week"]).value or "").strip()
        _sw_ord = _phase_ord(_sw_raw) if _sw_raw else None
        if _sw_raw and _sw_ord is None and _sw_raw not in ("-", "없음", "N/A", "n/a"):
            if len(skipped_rows) < 20:
                skipped_rows.append(
                    {"row": r, "why": "전환주차를 못 읽었습니다: %s (예: 2026-W36)" % _sw_raw})

        # 전환주차 한 칸을 '개발 → 양산' 두 구간으로 펴 준다
        def _phases_from_switch(old_entry):
            prev = _norm_phases((old_entry or {}).get("phases"))
            dev_price = prev[0]["price"] if prev else _as_money((old_entry or {}).get("price"))
            dev_mcost = prev[0]["material_cost"] if prev else _as_money((old_entry or {}).get("material_cost"))
            return [
                {"from": _PHASE_EPOCH, "group": "개발",
                 "price": dev_price, "material_cost": dev_mcost},
                {"from": "%04d-W%02d" % (_sw_ord // 100, _sw_ord % 100), "group": "양산",
                 "price": price, "material_cost": mcost},
            ]
        _note = ""
        if col_map.get("note"):
            _note = str(ws.cell(row=r, column=col_map["note"]).value or "").strip()

        # 파트넘버가 있으면 그걸로 찾고, 없을 때만 모델명으로 찾는다.
        # 단, 이 파일 안에서 겹치는 파트넘버는 열쇠가 못 되니 모델명으로 찾는다.
        if pn and pn.lower() not in _pn_dup:
            existing = by_pn.get(pn.lower())
        elif pn:
            existing = by_pnname.get((pn.lower(), name.lower()))
        elif name:
            existing = by_name.get(name.lower())
        else:
            existing = None

        if existing is not None:
            # 적은 칸만 바꾼다. 빈 칸은 지금 값을 지킨다.
            if _filled(col_map.get("group")):
                existing["group"] = group
            if dev_type:
                existing["dev_type"] = dev_type
            if _filled(col_map.get("price")):
                existing["price"] = price
            if _filled(col_map.get("material_cost")):
                existing["material_cost"] = mcost
            if pn:
                existing["part_number"] = pn
                # 이름 칸을 비워 올리면 비운다. 단 모델명 열 자체가 없는
                # 양식(품번만 있는 파일)이면 지금 이름을 지키다.
                if col_map.get("name"):
                    existing["name"] = name
            if _note:
                existing["note"] = _note
            # 전환주차가 적혀 있으면 구분 이력을 엑셀에 맞춘다.
            if _sw_ord:
                existing["phases"] = _phases_from_switch(existing)
            elif _sw_raw in ("-", "없음", "N/A", "n/a"):
                existing.pop("phases", None)
            updated += 1
        else:
            entry = {
                "id": ("%s · %s" % (pn, name) if (pn and pn.lower() in _pn_dup)
                       else (pn or name)),
                "name": name,
                "group": group,
                "dev_type": dev_type,
                "price": price,
                "material_cost": mcost,
                "status": "정상",
                "progress": 0,
            }
            if pn:
                entry["part_number"] = pn
            if _note:
                entry["note"] = _note
            if group == "개발":
                entry["process"] = _default_process()
            if _sw_ord:
                entry["phases"] = _phases_from_switch(None)
            models.append(entry)
            if name:
                by_name.setdefault(name.lower(), entry)
            if pn:
                by_pnname[(pn.lower(), name.lower())] = entry
                if pn.lower() not in _pn_dup:
                    by_pn[pn.lower()] = entry
            existing = entry
            added += 1

        # 수량은 열이 있을 때만 건드린다. 열이 없는데 0 으로 덮으면
        # 이미 쌓인 PO·출하가 사라진다.
        if _filled(col_map.get("po_qty")):
            existing["po_qty"] = int(_num(col_map["po_qty"]))
        if _filled(col_map.get("shipped_qty")):
            existing["shipped_qty"] = int(_num(col_map["shipped_qty"]))

    # 양산을 앞에, 개발을 뒤에 (같은 구분 안에서는 원래 순서 그대로)

    models.sort(key=lambda m: 0 if m.get("group") == "양산" else 1)

    # 엑셀 '유형' 열에 나온 값을 프로젝트 유형 목록에 자동 등록 (칩·자동완성용)
    _types = proj.get("types")
    if not isinstance(_types, list):
        _types = []
    _before = len(_types)
    for _m in models:
        _t = str(_m.get("dev_type") or "").strip()
        if _t and _t not in _types:
            _types.append(_t)
    proj["types"] = _types
    _new_types = _types[_before:]

    _save_models(data)
    print(f"[models-import] {_key}: +{added} 신규, {updated} 갱신, {skipped} 건너뜀"
          + (f", 유형 추가 {_new_types}" if _new_types else ""))
    return {"ok": True, "added": added, "updated": updated, "total": len(models),
            "skipped": skipped, "skipped_rows": skipped_rows,
            "columns": sorted(col_map.keys()),
            "types": _types, "types_added": _new_types}


# ─── 이슈 AI 요약 (models.json 기반, 캐시) ───
_issues_summary_cache = {}  # project_key -> {"fingerprint": str, "summary": str}

# ============================================================
#  이슈 요약 · 프로젝트 상세
# ============================================================
def _issues_fingerprint(models: list) -> str:
    import hashlib
    raw = "|".join(str(m.get("issues") or "") for m in models)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# 모델별 이슈를 각각 1~2문장으로 요약.
def _summarize_issues(project_key: str, models: list) -> list:
    with_issues = [(m.get("name") or m.get("id") or "", (m.get("issues") or "").strip())
                   for m in models if (m.get("issues") or "").strip()]
    if not with_issues:
        return []
    fp = _issues_fingerprint(models)
    cached = _issues_summary_cache.get(project_key)
    if cached and cached.get("fingerprint") == fp:
        return cached["summary"]
    if client is None:
        return [{"model": n, "summary": t.splitlines()[0]} for n, t in with_issues]
    bullet_src = "\n".join(f"[{name}] {txt}" for name, txt in with_issues)
    prompt = (
        "다음은 프로젝트 모델별 이슈사항입니다. 각 모델의 이슈를 항목별로 한 줄씩 요약하세요.\n"
        "규칙:\n"
        "- 이슈가 여러 개면 절대 합치지 말고 각각 별도 줄로 작성\n"
        "- 각 줄은 짧은 명사구 형태 (예: '4T 철강 자재 8/20 입고 예정', 'KCC 도료 입고 지연 — 입고 후 3일 내 출하 가능')\n"
        "- 날짜와 조치/일정은 반드시 포함\n"
        "- 반드시 이 JSON 형식으로만 답하세요 (다른 텍스트 금지):\n"
        '{"items": [{"model": "모델명", "summary": "줄1\\n줄2"}, ...]}\n\n' + bullet_src
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        import json as _json
        raw = (resp.choices[0].message.content or "").strip()
        parsed = _json.loads(raw)
        items = parsed.get("items") if isinstance(parsed, dict) else parsed
        if not isinstance(items, list):
            items = list(parsed.values())[0] if isinstance(parsed, dict) else []
        result = []
        for it in items:
            if not isinstance(it, dict):
                continue
            s = str(it.get("summary", ""))
            # 문장 구분을 확실히: ". " 뒤를 줄바꿈으로
            s = s.replace(". ", ".\n")
            result.append({"model": str(it.get("model", "")), "summary": s})
    except Exception:
        result = [{"model": n, "summary": t.splitlines()[0]} for n, t in with_issues]
    _issues_summary_cache[project_key] = {"fingerprint": fp, "summary": result}
    return result

# 앱 개요 화면용 이슈 AI 요약 ← 앱 project_overview_screen.dart _loadBloom()
@app.get("/projects/{project_key}/issues/summary")
def get_issues_summary(project_key: str):
    _key = _model_key_alias(project_key)
    data = _load_models()
    models = data.get("projects", {}).get(_key, {}).get("models", [])
    items = _summarize_issues(_key, models)
    return {"project_key": _key, "items": items}

# 프로젝트 모델 목록 + 그룹별 요약 (앱 8번 화면용)
# ← admin v2 mdlRefresh() · loadModels() · saveModels() · _wpLoadModels() 외 1곳 외
@app.get("/projects/{project_key}/models")
def get_project_models(project_key: str):
    models = _get_project_models(project_key)
    groups: dict = {}
    for m in models:
        # 전환 주차가 지났으면 양산으로 보여준다 (저장된 group 은 그대로).
        # 탭이 표시와 어긋나면 '양산인데 개발 탭에 있는' 모델이 생긴다.
        g = _display_group(m) if isinstance(m, dict) else "기타"
        if isinstance(m, dict):
            m["display_group"] = g
        groups.setdefault(g, {"count": 0, "models": []})
        groups[g]["count"] += 1
        groups[g]["models"].append(m)
    return {
        "project_key": project_key,
        "has_models": len(models) > 0,
        "total": len(models),
        "groups": groups,
        "models": models,
    }


# 프로젝트 상세 ← admin v2 markClean() · reloadKpiSlot() · loadProjectTypes() 외
@app.get("/projects/{project_key}")
def get_project_detail(project_key: str):
    # 별칭 매핑: 앱/구 데이터에서 오는 키를 실제 프로젝트 키로 변환
    _alias_map = {
        "havaplate": "hrva_plate",
        "hrvaplate": "hrva_plate",
        "hrva-plate": "hrva_plate",
    }
    project_key = _alias_map.get(project_key.strip().lower(), project_key.strip())
    latest = _read_json(LATEST_FILE, [])
    grouped = aggregate_projects(latest)
    detail = build_project_detail(project_key, grouped)
    if not detail:
        # PPT 없어도 노트만 있으면 노트 카드로 응답
        try:
            notes_data = _read_json(NOTES_FILE, {})
            for div_id, div_obj in (notes_data.get("notes") or {}).items():
                for card in (div_obj.get("cards") or []):
                    if (card.get("title") or "").strip() == project_key.strip():
                        detail = {
                            "project_key": project_key,
                            "label": project_key,
                            "name": project_key,
                            "status": _calc_card_status(card),
                            "sections": card.get("sections") or [],
                            "note_only": True,
                            "report_date": div_obj.get("report_date"),
                            "updated_at": div_obj.get("updated_at"),
                        }
                        break
                if detail:
                    break
        except Exception:
            pass
        if not detail:
            raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    # -----------------------------------------------------------
    # notes.json 매칭 sections 우선 사용 + str items → obj items 변환
    # -----------------------------------------------------------
    try:
        _notes_data = _read_json(NOTES_FILE, {})
        _project_label = (detail.get("label") or detail.get("project_label") or "").strip()
        _notes_card = None
        for _div_id, _div_obj in (_notes_data.get("notes") or {}).items():
            for _card in (_div_obj.get("cards") or []):
                if (_card.get("title") or "").strip() == _project_label:
                    _notes_card = _card
                    break
            if _notes_card:
                break

        if _notes_card and _notes_card.get("sections"):
            detail["sections"] = _notes_card["sections"]
        else:
            for _sec in detail.get("sections") or []:
                _raw_items = _sec.get("items", []) or []
                _raw_notes = _sec.get("notes", []) or []
                _new_items = []
                for _txt in _raw_items:
                    if isinstance(_txt, dict):
                        _new_items.append(_txt)
                        continue
                    _s = str(_txt).strip()
                    if _s:
                        _new_items.append({"type": "bullet", "text": _s})
                for _txt in _raw_notes:
                    if isinstance(_txt, dict):
                        _new_items.append(_txt)
                        continue
                    _s = str(_txt).strip()
                    if not _s:
                        continue
                    if _s.startswith("※"):
                        _new_items.append({"type": "highlight", "text": _s.lstrip("※ ").strip()})
                    else:
                        _new_items.append({"type": "sub", "text": _s})
                _sec["items"] = _new_items
                _sec.pop("notes", None)
    except Exception:
        pass

    # 🟢 프로젝트 상세 enrichment (기존 필드 변경 없음)
    detail = enrich_project_detail(detail)

    # KPI 카드 자동 첨부 (project_key 별 화이트리스트)
    try:
        if project_key == "major_module":
            detail["kpi_card"] = _build_major_module_kpi_card()
            detail["issue_lines"] = _build_major_module_issue_lines()
    except Exception:
        # KPI 계산 실패해도 기본 상세는 정상 반환되어야 함
        pass

    return detail


# ============================================================
#  admin 설정 · 이름 맞추기
# ============================================================
# Admin Config API (5단계: admin 페이지 동적 dropdown용)
# - 운영 도구 페이지에서 사업부/프로젝트/섹션을 동적으로 로드하기 위한 API
# - 모두 GET, 인증 불필요 (admin 페이지 내부에서만 호출됨)


# admin 페이지의 사업부 dropdown 용.
@app.get("/admin/config/divisions")
def admin_config_divisions(_exp: int = Depends(get_admin_session)):
    try:
        items = _cl.get_divisions(visible_only=True)
        return {
            "divisions": [
                {
                    "id": d.get("id"),
                    "label": d.get("label"),
                    "mode": d.get("mode"),
                    "order": d.get("order"),
                    "badge_short_label": d.get("badge_short_label"),
                }
                for d in items
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"divisions load error: {e}")


# === Learned Aliases (사용자 승인 오타 -> 프로젝트 매핑) ===
LEARNED_ALIASES_FILE = Path("learned_aliases.json")

# ============================================================
#  배운 별칭 — '이 이름은 이 프로젝트'
# ============================================================
def _load_learned_aliases() -> dict:
    try:
        with open(LEARNED_ALIASES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": 1, "updated_at": None, "aliases": {}}

# 배운 별칭 목록을 저장한다
def _save_learned_aliases(data: dict) -> None:
    from datetime import datetime
    data["updated_at"] = datetime.now().isoformat()
    with open(LEARNED_ALIASES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 배운 별칭으로 프로젝트를 찾는다
def _find_project_by_learned_alias(query: str) -> Optional[dict]:
    q = (query or "").strip().lower()
    if not q:
        return None
    data = _load_learned_aliases()
    for project_id, alias_list in (data.get("aliases") or {}).items():
        for a in alias_list:
            if str(a).strip().lower() == q:
                try:
                    all_projects = _cl.get_projects(visible_only=True)
                    for p in all_projects:
                        if p.get("id") == project_id:
                            return {
                                "id": p.get("id"),
                                "label": (p.get("label") or "").strip(),
                                "division_id": p.get("division_id"),
                                "matched_on": a,
                                "source": "learned_alias",
                            }
                except Exception:
                    pass
    return None


# fuzzy로 못 잡은 오타를 AI로 판정 ← admin v2 _onNewProjectNameInput()
@app.post("/admin/projects/resolve")
def admin_projects_resolve(payload: dict, _admin: int = Depends(get_admin_session)):
    if client is None:
        return {"resolved": None, "reason": "OPENAI_API_KEY not configured"}

    query = str((payload or {}).get("query") or "").strip()
    division_id = (payload or {}).get("division_id") or None
    if not query:
        return {"resolved": None, "reason": "empty query"}

    # 먼저 learned aliases 체크 (AI 호출 안 하고)
    learned = _find_project_by_learned_alias(query)
    if learned:
        return {"resolved": learned, "source": "learned_alias", "confidence": 1.0}

    try:
        all_projects = _cl.get_projects(division_id=division_id, visible_only=True)
    except Exception:
        all_projects = []

    if not all_projects:
        return {"resolved": None, "reason": "no candidates"}

    # 후보 목록 문자열 생성
    candidates_desc = []
    for p in all_projects:
        label = (p.get("label") or "").strip()
        aliases = p.get("aliases") or []
        candidates_desc.append(f"- id={p.get('id')}, label={label}, aliases={aliases}")
    candidates_text = "\n".join(candidates_desc)

    system_msg = "너는 한국어/영어 프로젝트명 오타 판정 어시스턴트다. 사용자가 입력한 이름이 후보 목록 중 어느 프로젝트를 의미하는지 판단한다. 반드시 JSON만 응답한다."

    user_msg = f"""사용자 입력: "{query}"

후보 프로젝트 목록:
{candidates_text}

응답 형식 (JSON only, no markdown):
{{
  "matched_id": "chamber" 또는 null,
  "confidence": 0.0~1.0,
  "reason": "짧은 설명"
}}

규칙:
- 명백히 오타/약어/유사어면 matched_id 반환
- 완전히 다른 이름이면 matched_id: null
- confidence 0.6 미만이면 matched_id: null
- 후보에 없는 새로운 프로젝트로 보이면 matched_id: null
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        result = json.loads(raw)
    except Exception as e:
        return {"resolved": None, "reason": f"ai error: {e}"}

    matched_id = result.get("matched_id")
    confidence = float(result.get("confidence") or 0.0)
    reason = result.get("reason") or ""

    if not matched_id or confidence < 0.6:
        return {"resolved": None, "reason": reason, "confidence": confidence}

    # matched_id로 프로젝트 정보 찾기
    for p in all_projects:
        if p.get("id") == matched_id:
            return {
                "resolved": {
                    "id": p.get("id"),
                    "label": (p.get("label") or "").strip(),
                    "division_id": p.get("division_id"),
                    "matched_on": query,
                    "source": "ai",
                },
                "confidence": confidence,
                "reason": reason,
            }

    return {"resolved": None, "reason": "matched_id not found in candidates"}


# 사용자 승인 alias를 learned_aliases.json에 저장 ← admin v2 _npBuildAiSuggestBox()
@app.post("/admin/projects/alias")
def admin_projects_add_alias(payload: dict, _admin: int = Depends(get_admin_session)):
    project_id = str((payload or {}).get("project_id") or "").strip()
    alias = str((payload or {}).get("alias") or "").strip()

    if not project_id or not alias:
        raise HTTPException(status_code=400, detail="project_id and alias required")

    # 프로젝트 존재 확인
    try:
        all_projects = _cl.get_projects(visible_only=True)
        found = any(p.get("id") == project_id for p in all_projects)
        if not found:
            raise HTTPException(status_code=404, detail=f"project_id not found: {project_id}")
    except HTTPException:
        raise
    except Exception:
        pass

    data = _load_learned_aliases()
    aliases = data.setdefault("aliases", {})
    lst = aliases.setdefault(project_id, [])

    # 중복 방지 (case insensitive)
    alias_lower = alias.lower()
    if not any(str(a).lower() == alias_lower for a in lst):
        lst.append(alias)
        _save_learned_aliases(data)
        return {"ok": True, "added": True, "project_id": project_id, "alias": alias, "total_aliases": len(lst)}
    else:
        return {"ok": True, "added": False, "reason": "alias already exists"}


# === 한/영 자판 변환 유틸 ===
_EN_TO_KO_JAMO = {
    "q":"ㅂ","w":"ㅈ","e":"ㄷ","r":"ㄱ","t":"ㅅ","y":"ㅛ","u":"ㅕ","i":"ㅑ","o":"ㅐ","p":"ㅔ",
    "a":"ㅁ","s":"ㄴ","d":"ㅇ","f":"ㄹ","g":"ㅎ","h":"ㅗ","j":"ㅓ","k":"ㅏ","l":"ㅣ",
    "z":"ㅋ","x":"ㅌ","c":"ㅊ","v":"ㅍ","b":"ㅠ","n":"ㅜ","m":"ㅡ",
    "Q":"ㅃ","W":"ㅉ","E":"ㄸ","R":"ㄲ","T":"ㅆ","O":"ㅒ","P":"ㅖ",
}
_KO_JAMO_TO_EN = {v: k for k, v in _EN_TO_KO_JAMO.items()}

_CHOSEONG = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
_JUNGSEONG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
_JONGSEONG = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")

_JUNG_COMBINE = {
    ("ㅗ","ㅏ"):"ㅘ",("ㅗ","ㅐ"):"ㅙ",("ㅗ","ㅣ"):"ㅚ",
    ("ㅜ","ㅓ"):"ㅝ",("ㅜ","ㅔ"):"ㅞ",("ㅜ","ㅣ"):"ㅟ",
    ("ㅡ","ㅣ"):"ㅢ",
}
_JONG_COMBINE = {
    ("ㄱ","ㅅ"):"ㄳ",("ㄴ","ㅈ"):"ㄵ",("ㄴ","ㅎ"):"ㄶ",
    ("ㄹ","ㄱ"):"ㄺ",("ㄹ","ㅁ"):"ㄻ",("ㄹ","ㅂ"):"ㄼ",
    ("ㄹ","ㅅ"):"ㄽ",("ㄹ","ㅌ"):"ㄾ",("ㄹ","ㅍ"):"ㄿ",
    ("ㄹ","ㅎ"):"ㅀ",("ㅂ","ㅅ"):"ㅄ",
}

# ============================================================
#  한/영 자판 바꿔 찾기 · 프로젝트 추천
# ============================================================
def _en_to_ko(text: str) -> str:
    if not text:
        return text
    jamos = []
    for ch in text:
        if ch in _EN_TO_KO_JAMO:
            jamos.append(_EN_TO_KO_JAMO[ch])
        else:
            jamos.append(ch)
    result = []
    i = 0
    n = len(jamos)
    while i < n:
        j = jamos[i]
        if j not in _CHOSEONG and j not in _JUNGSEONG:
            result.append(j)
            i += 1
            continue
        if j not in _CHOSEONG:
            result.append(j)
            i += 1
            continue
        cho = _CHOSEONG.index(j)
        if i + 1 >= n or jamos[i+1] not in _JUNGSEONG:
            result.append(j)
            i += 1
            continue
        jung_char = jamos[i+1]
        i += 2
        if i < n and jamos[i] in _JUNGSEONG:
            combined = _JUNG_COMBINE.get((jung_char, jamos[i]))
            if combined:
                jung_char = combined
                i += 1
        jung = _JUNGSEONG.index(jung_char)
        jong = 0
        if i < n and jamos[i] in _CHOSEONG:
            if i + 1 >= n or jamos[i+1] not in _JUNGSEONG:
                jong_char = jamos[i]
                if jong_char in _JONGSEONG:
                    if i + 1 < n and jamos[i+1] in _CHOSEONG:
                        if i + 2 >= n or jamos[i+2] not in _JUNGSEONG:
                            combined = _JONG_COMBINE.get((jong_char, jamos[i+1]))
                            if combined and combined in _JONGSEONG:
                                jong = _JONGSEONG.index(combined)
                                i += 2
                            else:
                                jong = _JONGSEONG.index(jong_char)
                                i += 1
                        else:
                            jong = _JONGSEONG.index(jong_char)
                            i += 1
                    else:
                        jong = _JONGSEONG.index(jong_char)
                        i += 1
        code = 0xAC00 + (cho * 21 + jung) * 28 + jong
        result.append(chr(code))
    return "".join(result)

# 한글 자판으로 친 영문을 영문으로 바꾼다 (검색용).
def _ko_to_en(text: str) -> str:
    if not text:
        return text
    result = []
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            base = code - 0xAC00
            cho_i = base // (21 * 28)
            jung_i = (base % (21 * 28)) // 28
            jong_i = base % 28
            cho = _CHOSEONG[cho_i]
            jung = _JUNGSEONG[jung_i]
            jong = _JONGSEONG[jong_i]
            for jamo in [cho, jung, jong]:
                if not jamo:
                    continue
                if jamo in ["ㅘ","ㅙ","ㅚ","ㅝ","ㅞ","ㅟ","ㅢ"]:
                    for k, v in _JUNG_COMBINE.items():
                        if v == jamo:
                            for j2 in k:
                                if j2 in _KO_JAMO_TO_EN:
                                    result.append(_KO_JAMO_TO_EN[j2])
                            break
                elif jamo in ["ㄳ","ㄵ","ㄶ","ㄺ","ㄻ","ㄼ","ㄽ","ㄾ","ㄿ","ㅀ","ㅄ"]:
                    for k, v in _JONG_COMBINE.items():
                        if v == jamo:
                            for j2 in k:
                                if j2 in _KO_JAMO_TO_EN:
                                    result.append(_KO_JAMO_TO_EN[j2])
                            break
                elif jamo in _KO_JAMO_TO_EN:
                    result.append(_KO_JAMO_TO_EN[jamo])
        elif ch in _KO_JAMO_TO_EN:
            result.append(_KO_JAMO_TO_EN[ch])
        else:
            result.append(ch)
    return "".join(result)


# 프로젝트명 fuzzy match ← admin v2 _onNewProjectNameInput()
@app.get("/admin/projects/suggest")
def admin_projects_suggest(query: str = "", limit: int = 5):
    from difflib import SequenceMatcher
    import unicodedata

    def to_jamo(s: str) -> str:
        return unicodedata.normalize("NFKD", s or "")

    def get_choseong(s: str) -> str:
        # 한글 완성형에서 초성만 추출
        result = []
        for ch in s:
            code = ord(ch)
            if 0xAC00 <= code <= 0xD7A3:
                base = code - 0xAC00
                cho_i = base // (21 * 28)
                result.append(_CHOSEONG[cho_i])
            else:
                result.append(ch)
        return "".join(result)

    def sim_ratio(a: str, b: str) -> float:
        char_sim = SequenceMatcher(None, a, b).ratio()
        jamo_a, jamo_b = to_jamo(a), to_jamo(b)
        jamo_sim = SequenceMatcher(None, jamo_a, jamo_b).ratio() if jamo_a and jamo_b else 0.0
        base_sim = max(char_sim, jamo_sim)
        # 초성 일치 보너스 (한글 오타 특성)
        cho_a = get_choseong(a)
        cho_b = get_choseong(b)
        if cho_a and cho_b and len(cho_a) == len(cho_b):
            cho_sim = SequenceMatcher(None, cho_a, cho_b).ratio()
            if cho_sim >= 0.99:  # 초성 완전 일치
                base_sim = min(1.0, base_sim + 0.15)
            elif cho_sim >= 0.7:  # 초성 대부분 일치
                base_sim = min(1.0, base_sim + 0.08)
        return base_sim

    q_raw = (query or "").strip()
    q = q_raw.lower()
    if not q:
        return {"suggestions": [], "exact_match": None}

    learned = _find_project_by_learned_alias(q)
    if learned:
        return {
            "suggestions": [{
                "id": learned["id"],
                "label": learned["label"],
                "division_id": learned["division_id"],
                "similarity": 1.0,
                "matched_on": learned["matched_on"],
                "exact": True,
                "source": "learned_alias",
            }],
            "exact_match": learned,
        }

    q_variants = [q]
    has_en = any(("a" <= c <= "z") or ("A" <= c <= "Z") for c in q_raw)
    has_ko = any((0xAC00 <= ord(c) <= 0xD7A3) or (0x3131 <= ord(c) <= 0x318E) for c in q_raw)
    if has_en and not has_ko:
        converted = _en_to_ko(q_raw).lower()
        if converted and converted != q:
            q_variants.append(converted)
    elif has_ko and not has_en:
        converted = _ko_to_en(q_raw).lower()
        if converted and converted != q:
            q_variants.append(converted)

    try:
        all_projects = _cl.get_projects(visible_only=True)
    except Exception:
        all_projects = []

    scored = []
    exact = None

    for p in all_projects:
        candidates = []
        label = (p.get("label") or "").strip()
        if label:
            candidates.append(label)
        for a in (p.get("aliases") or []):
            if a:
                candidates.append(str(a))
        for k in (p.get("keywords") or []):
            if k:
                candidates.append(str(k))

        best_sim = 0.0
        best_matched = ""
        found_exact_here = False
        for c in candidates:
            cl = c.lower().strip()
            for qv in q_variants:
                if cl == qv:
                    exact = {
                        "id": p.get("id"),
                        "label": label,
                        "division_id": p.get("division_id"),
                        "matched_on": c,
                    }
                    best_sim = 1.0
                    best_matched = c
                    found_exact_here = True
                    break
                sim = sim_ratio(qv, cl)
                # 부분 포함 보정: alias가 label보다 짧으면 페널티
                if qv in cl or cl in qv:
                    # cl이 매우 짧으면(2자 이하) 부분 매칭 보너스 낮춤
                    if len(cl) <= 2 and c != label:
                        sim = max(sim, 0.5)
                    else:
                        sim = max(sim, 0.75)
                if sim > best_sim:
                    best_sim = sim
                    best_matched = c
            if found_exact_here:
                break

        if best_sim >= 0.55:
            scored.append({
                "id": p.get("id"),
                "label": label,
                "division_id": p.get("division_id"),
                "similarity": round(best_sim, 3),
                "matched_on": best_matched,
                "exact": best_sim >= 0.999,
            })

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return {
        "suggestions": scored[:limit],
        "exact_match": exact,
    }

# ============================================================
#  admin 설정 목록 · 통계
# ============================================================
# admin 페이지의 프로젝트 dropdown 용 ← admin v2 _npLoadProjectButtons() · loadProjectOptions() · back.onclick()
@app.get("/admin/config/projects")
def admin_config_projects(division_id: str | None = None):
    try:
        # 앱·홈에 안 띄우기로 한 프로젝트라도, admin 에서 자료를 올려야 하는 자리는 여기엔 나와야 한다
        items = _cl.get_projects(division_id=division_id, visible_only=False)
        items = [p for p in items
                 if p.get("visible", True) or p.get("admin_only")]
        return {
            "division_id": division_id,
            "projects": [
                {
                    "id": p.get("id"),
                    "label": p.get("label"),
                    "badge_label": p.get("badge_label"),
                    "group": p.get("group"),
                    "order": p.get("order"),
                    "admin_only": bool(p.get("admin_only")),
                }
                for p in items
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"projects load error: {e}")


# admin 이미지 업로드 탭의 섹션 dropdown 용.
@app.get("/admin/config/sections")
def admin_config_sections(project_key: str, _exp: int = Depends(get_admin_session)):
    try:
        latest = _read_json(LATEST_FILE, [])
        grouped = aggregate_projects(latest)
        detail = build_project_detail(project_key, grouped)
        if not detail:
            return {"project_key": project_key, "sections": []}

        sections = detail.get("sections", [])
        return {
            "project_key": project_key,
            "project_label": detail.get("label"),
            "sections": [
                {
                    "title": s.get("title"),
                    "image_count": len(s.get("image_urls", []) or []),
                }
                for s in sections
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"sections load error: {e}")


# 매핑 관리 탭용 통계.
@app.get("/admin/config/stats")
def admin_config_stats(_exp: int = Depends(get_admin_session)):
    try:
        divs = _cl.get_divisions(visible_only=True)
        all_projects = _cl.get_projects(visible_only=True)

        latest = _read_json(LATEST_FILE, [])
        total_cards = 0
        unclassified_cards = []
        for report in latest:
            for p in report.get("products", []):
                total_cards += 1
                name = p.get("name") or p.get("product", "")
                category = p.get("category", "")
                text = f"{name} {category}".strip()
                pid = _cl.classify_project(text)
                if not pid:
                    unclassified_cards.append({
                        "name": name,
                        "category": category,
                        "report_family": report.get("report_meta", {}).get("report_family", ""),
                    })

        return {
            "divisions_count": len(divs),
            "projects_count": len(all_projects),
            "total_cards": total_cards,
            "unclassified_count": len(unclassified_cards),
            "unclassified_samples": unclassified_cards[:20],
            "projects_by_division": {
                d.get("id"): [
                    {"id": p.get("id"), "label": p.get("label")}
                    for p in _cl.get_projects(division_id=d.get("id"), visible_only=True)
                ]
                for d in divs
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"stats load error: {e}")

# ============================================================
#  admin v2 화면
# ============================================================
# admin v2 화면(HTML) 자체를 내준다
@app.get("/admin/v2", response_class=HTMLResponse)
def admin_v2_page(admin_auth: Optional[str] = Cookie(default=None)):
    if not _verify_session(admin_auth):
        return RedirectResponse(url="/admin/login?next=/admin/v2", status_code=302)
    return HTMLResponse(open(_ADMIN_V2_HTML_PATH, encoding='utf-8').read())


#
# 보기 전용이다. 여기서는 운영 데이터를 바꾸지 않는다. admin_v2.html 은
# '수정 금지' 상태라 일부러 건드리지 않고 별도 페이지로 둔다.
#
# 주소
#   /admin/uploads               화면
#   /admin/uploads/summary       몇 건 · 몇 바이트 · 어느 달이 있나
#   /admin/uploads/list?month=   그 달의 기록
#   /admin/uploads/file/{id}     한 건 내려받기
#   /admin/uploads/zip?month=    한 달치 통째로

# ============================================================
#  원본 보관함 — 올라온 엑셀을 브라우저로 꺼내는 길
# ============================================================
# 업로드 보관함 화면(HTML).
@app.get("/admin/uploads", response_class=HTMLResponse)
def admin_uploads_page(admin_auth: Optional[str] = Cookie(default=None)):
    if not _verify_session(admin_auth):
        return RedirectResponse(url="/admin/login?next=/admin/uploads",
                                status_code=302)
    import upload_vault_page
    return HTMLResponse(upload_vault_page.HTML)


# 업로드 보관함 — 달별 건수 요약.
@app.get("/admin/uploads/summary")
def admin_uploads_summary(_admin: int = Depends(get_admin_session)):
    st = upload_store.stats()
    st["months"] = upload_store.months()
    return st


# 업로드 보관함 — 목록.
@app.get("/admin/uploads/list")
def admin_uploads_list(month: str = "", project: str = "",
                       _admin: int = Depends(get_admin_session)):
    return {"month": month,
            "entries": upload_store.entries(month=month, project=project,
                                            limit=2000)}


# 한 건 내려받기.
@app.get("/admin/uploads/file/{entry_id}")
def admin_uploads_file(entry_id: str,
                       _admin: int = Depends(get_admin_session)):
    from fastapi.responses import FileResponse
    p = upload_store.path_of(entry_id)
    if not p:
        raise HTTPException(status_code=404, detail="그 파일을 찾지 못했습니다")
    # 원래 올린 이름으로 받게 한다 (보관 파일명에는 시각·경로가 붙어 있다)
    name = p.name.split("__")[-1] or p.name
    return FileResponse(str(p), filename=name,
                        media_type="application/octet-stream")


# 한 달치를 zip 으로. 인수인계 때 통째로 넘기는 길.
@app.get("/admin/uploads/zip")
def admin_uploads_zip(month: str,
                      _admin: int = Depends(get_admin_session)):
    import re as _re
    if not _re.fullmatch(r"\d{4}-\d{2}", month or ""):
        raise HTTPException(status_code=400, detail="연-월 형식이 아닙니다")
    data = upload_store.zip_bytes(month)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition":
                 f'attachment; filename="uploads_{month}.zip"'},
    )


_ADMIN_V2_HTML_PATH = os.path.join(os.path.dirname(__file__), 'admin_v2.html')

# ============================================================
#  예전 업로드 화면 · 업로드 이력
# ============================================================
# 예전 업로드 화면 주소 — admin v2 로 보낸다 (옛 화면은 지웠다. 즐겨찾기 · 옛 링크용)
@app.get("/admin/upload", response_class=HTMLResponse)
def admin_upload_page(admin_auth: Optional[str] = Cookie(default=None)):
    return RedirectResponse(url="/admin/v2", status_code=302)


# 업로드된 PPT 목록 (삭제 UI용)
@app.get("/admin/uploads/history")
def admin_uploads_history(_admin: int = Depends(get_admin_session)):
    items = _read_json(LATEST_FILE, [])
    history = []
    for item in items:
        doc_id = item.get("doc_id", "")
        history.append({
            "doc_id": doc_id,
            "file_name": item.get("file_name") or item.get("filename") or "",
            "upload_timestamp": item.get("upload_timestamp") or item.get("uploaded_at") or "",
            "product_count": len(item.get("products", [])),
            "slide_count": len(item.get("slide_images", {})),
        })
    # 최신 업로드 먼저
    history.sort(key=lambda x: x.get("upload_timestamp", ""), reverse=True)
    return {"items": history}

# ============================================================
#  손으로 만드는 보고서
# ============================================================
# 숨긴 것까지 포함한 보고서 전체 목록 ← admin v2 loadAdminV2Reports() · openReportEdit()
@app.get("/admin/reports/all")
def admin_list_reports_all(_admin: int = Depends(get_admin_session)):
    # Admin 전용: hidden 항목까지 모두 반환
    raw = _read_json(LATEST_FILE, [])
    enriched = []
    for r in (raw or []):
        try:
            meta = (r or {}).get("report_meta") or {}
            fname = (r or {}).get("file_name") or ""
            parsed = _parse_report_filename(fname, meta.get("date", ""))
            manual_projs = (r or {}).get("manual_projects")
            if manual_projs:
                parsed = dict(parsed)
                parsed["projects"] = list(manual_projs)
            mw = (r or {}).get("week_override")
            if mw:
                parsed["week"] = mw
            if parsed.get("projects"):
                _wk = parsed.get("week")
                parsed["display_title"] = ", ".join(parsed["projects"]) + (" · W" + str(_wk) + " 주간보고" if _wk else "")
            classified = _classify_report_status(
                (r or {}).get("upload_timestamp", ""),
                parsed.get("date") or meta.get("date", "")
            )
            r_enriched = dict(r or {})
            r_enriched["parsed"] = parsed
            r_enriched["display_title"] = parsed.get("display_title", "")
            r_enriched["report_status"] = classified.get("status", "published")
            r_enriched["d_day"] = classified.get("d_day")
            r_enriched["hidden"] = bool((r or {}).get("hidden", False))
            enriched.append(r_enriched)
        except Exception:
            enriched.append(r)
    split_cards = []
    for e in enriched:
        try:
            split_cards.extend(_split_report_by_project(e))
        except Exception:
            split_cards.append(e)
    split_cards = _dedupe_cards_by_project(split_cards)
    return {"reports": split_cards}


# 보고서를 손으로 만든다 (잠김) ← admin v2 getISOWeek()
@app.post("/admin/reports")
def admin_create_manual_report(payload: dict, _admin: int = Depends(get_admin_session)):
    # 수기 프로젝트 생성. PPT 없이 리포트 카드만 추가.
    project_name = (payload.get("project_name") or "").strip()
    division_id = (payload.get("division_id") or "semiconductor").strip() or "semiconductor"

    # 중복 프로젝트명 검사 (정규화 후 비교)
    _norm_new = _normalize_project_name(project_name)
    if _norm_new:
        try:
            _existing = _read_json(LATEST_FILE, [])
        except Exception:
            _existing = []
        for _r in (_existing or []):
            # 기존 리포트가 가진 모든 프로젝트명 (override 포함)
            _parsed = (_r or {}).get("parsed") or {}
            _projs = list(_parsed.get("projects") or [])
            _manual = (_r or {}).get("manual_projects") or []
            _projs.extend(_manual)
            _overrides = (_r or {}).get("project_overrides") or {}
            _all_names = []
            for _pn in _projs:
                _all_names.append(_overrides.get(_pn, _pn))
            for _pn in _all_names:
                if _normalize_project_name(_pn) == _norm_new:
                    raise HTTPException(status_code=400, detail=f"이미 존재하는 프로젝트명입니다: {project_name}")
    week = payload.get("week")
    headline = (payload.get("headline") or "").strip()
    if not project_name:
        raise HTTPException(status_code=400, detail="project_name required")
    try:
        week_int = int(week)
        if week_int < 1 or week_int > 53:
            raise ValueError
    except Exception:
        raise HTTPException(status_code=400, detail="valid week required (1-53)")

    import uuid, datetime as _dt
    doc_id = "manual_" + uuid.uuid4().hex[:12]
    now_iso = _dt.datetime.utcnow().isoformat()
    # 해당 주차의 월요일 날짜 계산 (ISO week)
    today = _dt.date.today()
    year = today.year
    try:
        report_date = _dt.date.fromisocalendar(year, week_int, 1).isoformat()
    except Exception:
        report_date = today.isoformat()

    display_title = project_name + " · W" + str(week_int) + " 주간보고"
    default_sections = [
        {"id": "sec_" + uuid.uuid4().hex[:8], "title": "현황", "kind": "text", "blocks": []},
        {"id": "sec_" + uuid.uuid4().hex[:8], "title": "주차별 계획", "kind": "mixed", "blocks": []},
        {"id": "sec_" + uuid.uuid4().hex[:8], "title": "주요내용", "kind": "mixed", "blocks": []},
    ]
    new_report = {
        "doc_id": doc_id,
        "file_name": "",
        "upload_timestamp": now_iso,
        "is_manual": True,
        "division_id": division_id,
        "report_meta": {"date": report_date},
        "products": [{
            "name": project_name,
            "category": "",
            "status": "",
            "headline": headline,
            "summary_bullets": [],
            "sections": default_sections,
            "division_id": division_id
        }],
        "project_overrides": {},
        "week_override": week_int,
        "manual_projects": [project_name],
    }
    items = _read_json(LATEST_FILE, [])
    items.insert(0, new_report)
    _write_json(LATEST_FILE, items)
    try:
        _sync_report_to_notes(new_report)
    except Exception as _e:
        print("[WARN] create single sync failed:", _e)
    return {"ok": True, "doc_id": doc_id, "display_title": display_title}


# 손으로 만든 보고서 지우기 (잠김) ← admin v2 executeDelete() · __moreBtn.onclick() · _loadSalesForSection() 외
@app.delete("/admin/reports/{doc_id}")
def admin_delete_manual_report(doc_id: str, _admin: int = Depends(get_admin_session)):
    # 수기 리포트 삭제. 안전을 위해 is_manual=True 인 것만 허용.
    items = _read_json(LATEST_FILE, [])
    target = None
    for it in items:
        if it.get("doc_id") == doc_id:
            target = it
            break
    if not target:
        raise HTTPException(status_code=404, detail="not found")
    if not target.get("is_manual"):
        raise HTTPException(status_code=403, detail="only manual reports can be deleted here")
    items = [it for it in items if it.get("doc_id") != doc_id]
    _write_json(LATEST_FILE, items)
    try:
        _resync_notes_from_latest()
    except Exception as _e:
        print("[WARN] delete resync failed:", _e)
    return {"ok": True, "doc_id": doc_id}


# ─── reports → notes.json 자동 동기화 (수기 doc용) ───

# ============================================================
#  보고서 → 노트 옮기기
# ============================================================
def _extract_due_date(text: str) -> tuple:
    import re as _re
    from datetime import date as _date
    if not text or not isinstance(text, str):
        return (text or "", None)

    due_iso = None

    # 우선순위 1: 대괄호 안의 명시적 ISO 날짜
    m = _re.search(r'\[\s*(20\d{2})[-./](\d{1,2})[-./](\d{1,2})\s*\]', text)
    if m:
        try:
            due_iso = _date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except Exception:
            pass
    else:
        m = _re.search(r'\[\s*(\d{2})[-./](\d{1,2})[-./](\d{1,2})\s*\]', text)
        if m:
            try:
                due_iso = _date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
            except Exception:
                pass

    # 우선순위 2: 새 파서 (화살표 인식 + 마지막 세그먼트 우선)
    if not due_iso:
        due_iso = _extract_due_date_from_text(text) or None

    # ★ text 는 정리하지 않고 원문 그대로 반환
    return (text, due_iso)

# BeautifulSoup 노드를 재귀 순회하며 [(text, style_dict), ...] 반환.
def _collect_inline_runs(node, inherited_style: dict) -> list:
    from bs4 import NavigableString
    if isinstance(node, NavigableString):
        return [(str(node), dict(inherited_style))]

    style = dict(inherited_style)
    name = getattr(node, 'name', '') or ''
    name = name.lower()

    # ★ 블록 태그(div/p/br)는 줄바꿈 run으로 처리 — 저장 시 줄바꿈 보존
    if name in ('div', 'p'):
        children_runs = []
        for child in node.children:
            children_runs.extend(_collect_inline_runs(child, style))
        return children_runs + [('\n', {})]  # 블록 끝에 줄바꿈
    if name == 'br':
        return [('\n', {})]  # <br>은 줄바꿈

    # 태그별 스타일 부여
    if name == 'font':
        c = node.get('color')
        if c:
            style['color'] = c.strip()
        sz = node.get('size')
        if sz:
            try:
                # <font size="1..7"> → 스케일 (3이 기본)
                n = int(str(sz).strip())
                _map = {1: 0.7, 2: 0.85, 3: 1.0, 4: 1.15, 5: 1.3, 6: 1.5, 7: 1.75}
                style['size_scale'] = _map.get(n, 1.0)
            except ValueError:
                pass
    elif name in ('b', 'strong'):
        style['bold'] = True
    elif name in ('i', 'em'):
        style['italic'] = True
    elif name == 'u':
        style['underline'] = True

    # style 속성은 태그 종류에 관계없이 파싱 (b/strong/i/em/u/span/div/p 등 모두)
    # 예: <b style="color:red">, <span style="font-weight:bold">, <div style="color:blue">
    s_attr = node.get('style') if hasattr(node, 'get') else None
    if s_attr:
        import re as _re
        for m in _re.finditer(r'([\w-]+)\s*:\s*([^;]+)', s_attr):
            k = m.group(1).strip().lower()
            v = m.group(2).strip()
            if k == 'color':
                style['color'] = v
            elif k == 'font-weight':
                if v.lower() in ('bold', 'bolder') or (v.isdigit() and int(v) >= 600):
                    style['bold'] = True
            elif k == 'font-style' and v.lower() == 'italic':
                style['italic'] = True
            elif k == 'text-decoration' and 'underline' in v.lower():
                style['underline'] = True
            elif k == 'font-size':
                # "14px", "1.2em", "120%"
                _m2 = _re.match(r'(\d+(?:\.\d+)?)\s*(px|em|%)?', v)
                if _m2:
                    num = float(_m2.group(1))
                    unit = (_m2.group(2) or 'px').lower()
                    if unit == 'px':
                        style['size_scale'] = num / 14.0  # 14px 기준
                    elif unit == 'em':
                        style['size_scale'] = num
                    elif unit == '%':
                        style['size_scale'] = num / 100.0

    runs = []
    for child in node.children:
        runs.extend(_collect_inline_runs(child, style))
    return runs


# runs [(text, style), ...] → (plain_text, text_runs 또는 None).
def _runs_to_output(runs: list) -> tuple:
    if not runs:
        return ('', None)
    # 앞뒤 공백을 유지하되 완전히 빈 run은 제외
    filtered = [(t, st) for (t, st) in runs if t]
    if not filtered:
        return ('', None)
    # 병합 — 단, 줄바꿈 run은 항상 별도 유지
    merged = []
    for t, st in filtered:
        if t == '\n':
            merged.append([t, {}])  # 줄바꿈은 스타일 없이 별도
        elif merged and merged[-1][1] == st and merged[-1][0] != '\n':
            merged[-1] = (merged[-1][0] + t, st)
        else:
            merged.append([t, st])
    plain = ''.join(t for t, _ in merged)
    # 스타일이 하나라도 있는지
    has_style = any(bool(st) for _, st in merged)
    if not has_style:
        return (plain, None)
    # text_runs 포맷 (스키마 slim)
    text_runs = []
    for t, st in merged:
        run = {'text': t}
        if st.get('color'):
            run['color'] = st['color']
        if st.get('bold'):
            run['bold'] = True
        if st.get('italic'):
            run['italic'] = True
        if st.get('underline'):
            run['underline'] = True
        if 'size_scale' in st and st['size_scale'] != 1.0:
            run['size_scale'] = round(st['size_scale'], 2)
        text_runs.append(run)
    return (plain, text_runs)


# HTML(관리자 편집기 결과)을 모바일 앱이 이해하는 items 배열로 변환.
def _html_body_to_items(html: str) -> list:
    # items가 이미 있으면 그대로 반환
    if isinstance(html, list):
        return html
    if isinstance(html, dict) and 'items' in html:
        return html['items']
    print(f"[DEBUG _html_body_to_items] input length={len(html)}, first 500 chars: {html[:500]}")
    """
    print(f"[DEBUG _html_body_to_items] input length={len(html)}, first 500 chars: {html[:500]}")
    
    

    # 중첩된 <div> 평탄화 (브라우저 contenteditable 버그 대응)
    # 예: <div>외부<div>내부1</div><div>내부2</div></div> → <div>외부</div><div>내부1</div><div>내부2</div>
    from bs4 import BeautifulSoup as _BS
    _soup = _BS(html, 'html.parser')
    for _div in list(_soup.find_all('div')):
        _nested = _div.find_all('div', recursive=False)
        if _nested:
            for _child in _nested:
                _div.insert_after(_child)
    html = str(_soup)

    변환 규칙:
    - <ol depth 0> → {"type": "bullet", "text": "1. ..."}
    - <ol depth 1> → {"type": "sub", "text": "1) ..."}
    - <ol depth 2+> → {"type": "sub", "text": "① ..."} (원형숫자)
    - <div>*text*</div> 또는 <div>★text</div> → highlight
    - <div data-indent="N">text</div> (N>=1) → sub
    - <div>일반</div> → bullet
    - <del>...</del> 완전 제거
    - <ins>text</ins> → 텍스트만 유지
    """
    from bs4 import BeautifulSoup, NavigableString

    if not html or not isinstance(html, str):
        return []

    # <del> 제거, <ins>는 텍스트만 남김
    soup = BeautifulSoup(html, 'html.parser')
    for del_tag in soup.find_all('del'):
        del_tag.decompose()
    for ins_tag in soup.find_all('ins'):
        ins_tag.unwrap()

    # depth별 마커 함수
    CIRCLED = ['①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩',
               '⑪','⑫','⑬','⑭','⑮','⑯','⑰','⑱','⑲','⑳']

    # depth+index+is_ul로 실제 표시 문자 생성.
    def marker_for_depth(depth: int, idx: int, is_ul: bool = False) -> str:
        if is_ul:
            # ul(불릿): depth 0=•, 1=-, 2=*, 3+=·
            if depth == 0:
                return "•"
            elif depth == 1:
                return "-"
            elif depth == 2:
                return "*"
            else:
                return "·"
        else:
            # ol(숫자): depth 0=1., 1=1), 2=①...
            style = depth % 3
            if style == 0:
                return f"{idx + 1}."
            elif style == 1:
                return f"{idx + 1})"
            else:  # circled
                return CIRCLED[idx] if idx < len(CIRCLED) else f"{idx + 1}."

    # ol의 effective depth 계산 (data-depth-override 우선).
    def get_ol_depth(ol) -> int:
        override = ol.get('data-depth-override')
        if override:
            try:
                return int(override)
            except ValueError:
                pass
        # DOM nesting으로 계산
        depth = 0
        cur = ol.parent
        while cur is not None:
            if getattr(cur, 'name', None) == 'ol':
                ovr = cur.get('data-depth-override') if hasattr(cur, 'get') else None
                if ovr:
                    try:
                        return int(ovr) + depth + 1
                    except ValueError:
                        pass
                depth += 1
            cur = getattr(cur, 'parent', None)
        return depth

    items = []

    # ol의 li들을 순회하며 items에 추가 (nested ol도 재귀).
    def process_ol(ol, extra_prefix=""):
        print(f"[DEBUG process_ol] called, tag={ol.name}, children={len(list(ol.children))}, is_ul={ol.name == 'ul'}")
        # data-depth-override 속성이 있으면 우선 사용 (에디터 Tab 들여쓰기)
        _override = ol.get('data-depth-override')
        if _override is not None:
            try:
                depth = int(_override)
            except (ValueError, TypeError):
                depth = get_ol_depth(ol)
        else:
            depth = get_ol_depth(ol)
        # start 값 반영
        try:
            start = int(ol.get('data-start') or ol.get('start') or 1)
        except (ValueError, TypeError):
            start = 1

        lis = [c for c in ol.children if getattr(c, 'name', None) == 'li']
        for i, li in enumerate(lis):
            # li 안의 인라인 runs 수집 (색상/굵기 등 스타일 보존)
            li_runs = []
            nested_ols = []
            for child in li.children:
                if getattr(child, 'name', None) in ('ol', 'ul'):
                    nested_ols.append(child)
                else:
                    li_runs.extend(_collect_inline_runs(child, {}))

            li_plain, li_text_runs = _runs_to_output(li_runs)
            li_plain = li_plain.rstrip()
            print(f"[DEBUG process_ol] li[{i}] tag_name={repr(ol.name)}, plain='{li_plain[:50]}...'")
            if li_plain:
                # ul은 bullet(•), ol은 숫자 마커
                if ol.name == 'ul':
                    marker = '•'
                else:
                    marker = marker_for_depth(depth, i + (start - 1), is_ul=(ol.name == 'ul'))
                item_type = 'bullet' if depth == 0 else 'sub'
                clean_text, due_iso = _extract_due_date(li_plain)
                full_text = f"{marker} {clean_text}" if clean_text else f"{marker}"
                _item = {
                    'type': item_type,
                    'text': full_text,
                }
                if due_iso:
                    _item['due_date'] = due_iso
                # text_runs가 있고 due_date 추출로 텍스트가 안 바뀐 경우만 유지
                if li_text_runs and clean_text == li_plain:
                    prefixed_runs = [{'text': f"{marker} "}] + li_text_runs
                    _item['text_runs'] = prefixed_runs
                items.append(_item)

            # nested ol 재귀 처리
            for nested in nested_ols:
                process_ol(nested)

    # [(text, style), ...] 리스트 → bullet 아이템으로 emit.
    def emit_runs(runs: list):
        plain, text_runs = _runs_to_output(runs)
        plain = plain.rstrip()
        if not plain:
            return
        # text_runs가 있으면 각 run의 앞뒤 공백/양쪽 트림 동기화
        if text_runs:
            # plain의 정리에 맞춰 text_runs도 정리
            # 앞 공백 제거 (앱이 sub 들여쓰기를 대신하므로 이중 적용 방지)
            while text_runs and text_runs[0]['text'] and text_runs[0]['text'] != text_runs[0]['text'].lstrip():
                text_runs[0]['text'] = text_runs[0]['text'].lstrip()
                if not text_runs[0]['text']:
                    text_runs.pop(0)
                else:
                    break
            # 뒤 공백 제거
            while text_runs and text_runs[-1]['text'] and text_runs[-1]['text'].rstrip() != text_runs[-1]['text']:
                text_runs[-1]['text'] = text_runs[-1]['text'].rstrip()
                if not text_runs[-1]['text']:
                    text_runs.pop()
                else:
                    break
        clean, due_iso = _extract_due_date(plain)
        _bul = {'type': 'bullet', 'text': clean}
        if due_iso:
            _bul['due_date'] = due_iso
        if text_runs and clean == plain:
            # due_date 추출로 text가 바뀌지 않은 경우만 text_runs 유지 (안전)
            _bul['text_runs'] = text_runs
        items.append(_bul)

    # editor 직속 자식 처리 (div, ol, ul 등).
    def process_element(el):
        name = getattr(el, 'name', None)
        if name in ('ol', 'ul'):
            process_ol(el)
        elif name in ('div', 'p'):
            # 인라인 runs 수집 (색상/굵기 등 보존)
            # 단, 직접 자식 중 block 요소(ul, ol, div, p)는 제외 — 중첩 구조에서 텍스트 합침 방지
            BLOCK_TAGS = {'ul', 'ol', 'div', 'p', 'li'}
            _el_runs = []
            _has_block_child = False
            for _c in el.children:
                _c_name = getattr(_c, 'name', None)
                if _c_name in BLOCK_TAGS:
                    _has_block_child = True
                    continue  # block 자식은 건너뛰고, 나중에 재귀 처리
                _el_runs.extend(_collect_inline_runs(_c, {}))
            _el_plain, _el_text_runs = _runs_to_output(_el_runs)
            text = (_el_plain or '').rstrip()

            # block 자식(ul/ol)은 1단계(find_all)에서 이미 처리됨 → 여기선 중첩 div/p만 재귀
            if _has_block_child:
                # 자기 텍스트 먼저 flush (block 자식보다 위에 위치해야 함)
                if text:
                    clean, due_iso = _extract_due_date(text)
                    _bul = {'type': 'bullet', 'text': clean}
                    if _el_text_runs and clean == text:
                        _bul['text_runs'] = _el_text_runs
                    if due_iso:
                        _bul['due_date'] = due_iso
                    items.append(_bul)
                    text = ''  # 아래 공통 emit 방지
                for _c in el.children:
                    _c_name = getattr(_c, 'name', None)
                    if _c_name in ('div', 'p'):
                        process_element(_c)
                    elif _c_name in ('ul', 'ol'):
                        process_ol(_c)
                # div 자체의 텍스트도 있으면 추가로 item 생성
                if not text:
                    return
            # 들여쓰기 체크: data-indent 속성 우선, 없으면 텍스트 앞 공백 개수로 계산
            _indent_attr = el.get('data-indent')
            try:
                indent = int(_indent_attr) if _indent_attr else 0
            except (ValueError, TypeError):
                indent = 0

            # data-indent가 없으면 앞 공백 개수로 depth 계산 (2칸=1depth)
            if indent == 0:
                _leading = _el_plain or ''
                # 앞쪽 공백/탭/nbsp 개수 세기
                _stripped = _leading.lstrip(' \t\u00a0')
                _space_count = len(_leading) - len(_stripped)
                indent = _space_count // 2  # 2칸당 1depth
                if indent > 0:
                    print(f"[DEBUG indent] text='{text[:30]}...', space_count={_space_count}, depth={indent}")
            else:
                print(f"[DEBUG indent] text='{text[:30]}...', data-indent={_indent_attr}, depth={indent}")

            print(f"[DEBUG FINAL] text='{text[:40]}', indent={indent}, _has_block_child={_has_block_child}")
            if indent >= 1:
                clean, due_iso = _extract_due_date(text)
                _sub = {'type': 'sub', 'text': clean}
                if _el_text_runs and clean == text:
                    _sub['text_runs'] = _el_text_runs
                if due_iso:
                    _sub['due_date'] = due_iso
                items.append(_sub)
            else:
                clean, due_iso = _extract_due_date(text)
                _bul = {'type': 'bullet', 'text': clean}
                if _el_text_runs and clean == text:
                    _bul['text_runs'] = _el_text_runs
                if due_iso:
                    _bul['due_date'] = due_iso
                items.append(_bul)

    # 최상위 자식들 순회.
    # 연속된 NavigableString + 인라인 태그(font/span/b/i/u/em/strong/sub/sup 등)는 하나의 텍스트로 병합.
    # <br> 만나면 flush(하나의 아이템으로 emit).
    INLINE_TAGS = {'font', 'span', 'b', 'i', 'u', 'em', 'strong', 'sub', 'sup', 'small', 'mark', 'a', 'code'}
    runs_buf = []  # [(text, style_dict), ...]

    def flush_buf():
        if runs_buf:
            emit_runs(list(runs_buf))
            runs_buf.clear()


    for child in soup.children:
        name = getattr(child, 'name', None)
        if isinstance(child, NavigableString):
            runs_buf.append((str(child), {}))
        elif name == 'br':
            flush_buf()
        elif name in INLINE_TAGS:
            runs_buf.extend(_collect_inline_runs(child, {}))
        elif name in ('ul', 'ol'):
            # 제자리에서 바로 처리 (문서 순서 유지)
            flush_buf()
            process_ol(child)
        else:
            # 블록 요소(div, p 등): 지금까지 쌓인 인라인 flush 후 별도 처리
            flush_buf()
            process_element(child)
    flush_buf()

    return items


# products[] → notes.json 형식의 cards[] 로 변환.
def _products_to_note_cards(products: list, week_override=None) -> list:
    if not isinstance(products, list):
        return []

    cards = []
    for prod in products:
        if not isinstance(prod, dict):
            continue
        title = (prod.get('name') or '').strip()
        if not title:
            continue

        card_sections = []
        for sec in (prod.get('sections') or []):
            if not isinstance(sec, dict):
                continue
            sec_title = (sec.get('title') or '').strip()
            blocks = sec.get('blocks') or []

            items = []
            for blk in blocks:
                if not isinstance(blk, dict):
                    continue
                kind = blk.get('kind', 'text')
                if kind == 'text':
                    body = blk.get('body', '')
                    items.extend(_html_body_to_items(body))
                elif kind == 'file':
                    # 파일 첨부는 photo item으로. xlsx/xlsm 이면 PNG 자동 변환.
                    fname = blk.get('file_name', '') or ''
                    url = blk.get('url', '') or ''
                    if fname or url:
                        _lower = (fname + ' ' + url).lower()
                        _photo_ref = url  # 기본값: URL 그대로
                        if '.xlsx' in _lower or '.xlsm' in _lower:
                            try:
                                local_path = _xlsx_url_to_local_path(url)
                                if local_path and local_path.exists():
                                    # division_id 유추 (파서는 report 전체를 안 봄 → product 이름으로)
                                    _div_id = ''
                                    try:
                                        _div_id = _cl.derive_division_from_project(title) or ''
                                    except Exception:
                                        _div_id = ''
                                    if not _div_id:
                                        _div_id = 'semiconductor'
                                    png_bytes = _xlsx_file_to_png_bytes(local_path)
                                    _photo_ref = _save_note_photo(_div_id, png_bytes, ext='png')
                                    print(f'[parser] xlsx→png 자동 변환: {fname} → {_photo_ref}')
                                else:
                                    print(f'[parser] xlsx 파일 찾지 못함, URL 그대로: {url}')
                            except Exception as _e:
                                print(f'[parser] xlsx→png 변환 실패 (URL 그대로 사용): {_e}')
                        items.append({
                            'type': 'photo',
                            'text': fname or url,
                            'photo_ref': _photo_ref,
                        })

            if items:
                new_sec = {
                    'title': sec_title,
                    'items': items,
                }
                # sales_visible 이 명시적으로 지정돼 있으면 유지 (기본 True 는 저장 안 함)
                if isinstance(sec.get('sales_visible'), bool):
                    new_sec['sales_visible'] = sec['sales_visible']
                card_sections.append(new_sec)

        if card_sections:
            card = {
                'title': title,
                'sections': card_sections,
            }
            # summary/headline 등도 복사
            if prod.get('headline'):
                card['headline'] = prod.get('headline')
            if prod.get('status'):
                card['status'] = prod.get('status')
            cards.append(card)

    return cards


# 수기 doc 하나를 notes.json에 upsert.
def _sync_report_to_notes(it: dict) -> None:
    try:
        if not isinstance(it, dict):
            return
        if not it.get('is_manual'):
            return

        products = it.get('products') or []
        cards = _products_to_note_cards(products, week_override=it.get('week_override'))
        if not cards:
            return

        # division_id 결정
        division_id = (it.get('division_id') or '').strip()
        if not division_id:
            # product.name으로 유추 시도
            for prod in products:
                if isinstance(prod, dict) and prod.get('name'):
                    try:
                        division_id = _cl.derive_division_from_project(prod['name']) or ''
                    except Exception:
                        pass
                    if division_id:
                        break
        if not division_id:
            division_id = 'semiconductor'  # 폴백

        # 정규화
        parsed = {'cards': cards}
        _normalize_note_cards(parsed)
        cards = parsed['cards']

        # sales_input 자동 계산 (주차별 계획 섹션)
        try:
            products = it.get('products') or []
            for card in cards:
                for sec in card.get('sections', []) or []:
                    # products에서 같은 title의 section 찾아 sales_input 가져옴
                    sec_title = (sec.get('title') or '').strip()
                    for prod in products:
                        for psec in prod.get('sections', []) or []:
                            if (psec.get('title') or '').strip() == sec_title:
                                # [SALES v2] 우선순위:
                                #   1) 섹션에 첨부된 xlsx + sales_prices → 자동 파싱/계산
                                #   2) sales_data (구조화 JSON)
                                #   3) sales_input (구식 텍스트)
                                sd = psec.get('sales_data')
                                si = psec.get('sales_input') or ''
                                prices = psec.get('sales_prices') or {}
                                # -----------------------------------------------------------
                                # xlsx 파싱 (섹션 내 첨부 파일 자동 인식)
                                # -----------------------------------------------------------
                                #    reports_latest.json 은 blocks[] 를 씀 → blocks 우선 탐색
                                xlsx_ref = None
                                for _blk in (psec.get('blocks') or []):
                                    if not isinstance(_blk, dict):
                                        continue
                                    _url = _blk.get('url') or _blk.get('file_url') or ''
                                    _fname = _blk.get('file_name') or ''
                                    _all = (_url + ' ' + _fname).lower()
                                    if '.xlsx' in _all or '.xlsm' in _all:
                                        xlsx_ref = _url or _fname
                                        break
                                # fallback: items[] (notes 스키마)
                                if not xlsx_ref:
                                    xlsx_ref = _find_xlsx_in_section_items(psec.get('items') or [])
                                if not xlsx_ref:
                                    src_meta = psec.get('sales_source') or {}
                                    xlsx_ref = src_meta.get('file_url')

                                parsed_ok = False
                                if xlsx_ref:
                                    local_path = _xlsx_url_to_local_path(xlsx_ref)
                                    if local_path and local_path.exists():
                                        try:
                                            parsed = parse_sales_excel(local_path)
                                            sec['sales_source'] = {
                                                'file_name': local_path.name,
                                                'file_url': str(xlsx_ref),
                                                'parsed_at': datetime.now().isoformat(timespec='seconds'),
                                                'parsed': parsed,
                                            }
                                            sec['sales_prices'] = prices
                                            if prices:
                                                r = compute_sales_from_parsed(parsed, prices)
                                                sec['sales_summary'] = r['sales_summary']
                                                sec['sales_summary_data'] = r['sales_summary_data']
                                                sec['sales_computed_at'] = r['sales_computed_at']
                                            parsed_ok = True
                                        except Exception as _pe:
                                            print(f'[sales_xlsx parse ERROR] {xlsx_ref} :: {_pe}')
                                # -----------------------------------------------------------
                                # fallback: sales_data (JSON)
                                # -----------------------------------------------------------
                                if not parsed_ok and isinstance(sd, dict) and (sd.get('prices') or sd.get('weeks')):
                                    sec['sales_data'] = sd
                                    r = compute_sales_from_data(sd)
                                    sec['sales_summary'] = r['sales_summary']
                                    sec['sales_computed_at'] = r['sales_computed_at']
                                    parsed_ok = True
                                # -----------------------------------------------------------
                                # fallback: sales_input (구식 텍스트)
                                # -----------------------------------------------------------
                                if not parsed_ok and si:
                                    sec['sales_input'] = si
                                    r = compute_sales_from_input(si)
                                    sec['sales_summary'] = r['sales_summary']
                                    sec['sales_computed_at'] = r['sales_computed_at']
                                break
        except Exception as _e:
            print(f'[sales_compute in sync ERROR] {_e}')

        # notes.json upsert
        from datetime import datetime
        data = _load_notes()
        notes_map = data.setdefault('notes', {})
        existing = notes_map.get(division_id) or {}
        existing_cards = existing.get('cards') or []

        def _norm_title(t):
            return re.sub(r'\s+', '', (t or '').strip()).lower()

        by_title = {}
        order = []
        for c in existing_cards:
            if not isinstance(c, dict):
                continue
            tkey = _norm_title(c.get('title'))
            if not tkey or tkey in by_title:
                continue
            by_title[tkey] = c
            order.append(tkey)

        def _merge_card_preserve_manual_state(old_card, new_card):
            try:
                def _norm_text(x):
                    return re.sub(r'\s+', ' ', (x or '').strip()).lower()

                old_secs = old_card.get('sections') or []
                new_secs = new_card.get('sections') or []
                old_item_map = {}

                for os_ in old_secs:
                    os_title = (os_.get('title') or '').strip()
                    for oi in (os_.get('items') or []):
                        if not isinstance(oi, dict):
                            continue
                        keys = []
                        oi_id = (oi.get('item_id') or '').strip()
                        oi_text = (oi.get('text') or '').strip()
                        if oi_id:
                            keys.append(('id', os_title, oi_id))
                        if oi_text:
                            keys.append(('text', os_title, _norm_text(oi_text)))
                            keys.append(('text-any', '', _norm_text(oi_text)))
                        for k in keys:
                            old_item_map[k] = oi

                for ns in new_secs:
                    ns_title = (ns.get('title') or '').strip()
                    for ni in (ns.get('items') or []):
                        if not isinstance(ni, dict):
                            continue
                        match = None
                        ni_id = (ni.get('item_id') or '').strip()
                        ni_text = (ni.get('text') or '').strip()
                        if ni_id:
                            match = old_item_map.get(('id', ns_title, ni_id))
                        if not match and ni_text:
                            match = old_item_map.get(('text', ns_title, _norm_text(ni_text)))
                        if not match and ni_text:
                            match = old_item_map.get(('text-any', '', _norm_text(ni_text)))
                        if match:
                            if match.get('auto_due_hidden'):
                                ni['auto_due_hidden'] = True
                            if (match.get('due_date_override') or '').strip():
                                ni['due_date_override'] = (match.get('due_date_override') or '').strip()
                            if (match.get('due_date_auto') or '').strip() and not (ni.get('due_date_auto') or '').strip():
                                ni['due_date_auto'] = (match.get('due_date_auto') or '').strip()
                            try:
                                _apply_effective_due_date(ni)
                            except Exception:
                                pass
                return new_card
            except Exception:
                return new_card

        # 기존 notes 전체에서 수동 상태 맵 생성
        manual_state_map = {}
        for _oc in existing_cards:
            if not isinstance(_oc, dict):
                continue
            _ocard_title = (_oc.get('title') or '').strip()
            for _os in (_oc.get('sections') or []):
                if not isinstance(_os, dict):
                    continue
                _osec_title = (_os.get('title') or '').strip()
                for _oi in (_os.get('items') or []):
                    if not isinstance(_oi, dict):
                        continue
                    _otext = re.sub(r'\s+', ' ', (_oi.get('text') or '').strip()).lower()
                    if not _otext:
                        continue
                    _key = (_ocard_title, _osec_title, _otext)
                    manual_state_map[_key] = {
                        'auto_due_hidden': bool(_oi.get('auto_due_hidden')),
                        'due_date_override': (_oi.get('due_date_override') or '').strip(),
                        'due_date_auto': (_oi.get('due_date_auto') or '').strip(),
                    }

        def _apply_manual_state(card_obj):
            try:
                _ct = (card_obj.get('title') or '').strip()
                for _ns in (card_obj.get('sections') or []):
                    if not isinstance(_ns, dict):
                        continue
                    _st = (_ns.get('title') or '').strip()
                    for _ni in (_ns.get('items') or []):
                        if not isinstance(_ni, dict):
                            continue
                        _tx = re.sub(r'\s+', ' ', (_ni.get('text') or '').strip()).lower()
                        if not _tx:
                            continue
                        _m = manual_state_map.get((_ct, _st, _tx))
                        if not _m:
                            continue
                        if _m.get('auto_due_hidden'):
                            _ni['auto_due_hidden'] = True
                        if _m.get('due_date_override'):
                            _ni['due_date_override'] = _m['due_date_override']
                        if _m.get('due_date_auto') and not (_ni.get('due_date_auto') or '').strip():
                            _ni['due_date_auto'] = _m['due_date_auto']
                        try:
                            _apply_effective_due_date(_ni)
                        except Exception:
                            pass
                return card_obj
            except Exception:
                return card_obj

        for c in cards:
            tkey = _norm_title(c.get('title'))
            if not tkey:
                continue
            c = _apply_manual_state(c)
            if tkey in by_title:
                by_title[tkey] = _merge_card_preserve_manual_state(by_title[tkey], c)
            else:
                by_title[tkey] = c
                order.append(tkey)

        merged_cards = [by_title[k] for k in order]

        report_date = ''
        meta = it.get('report_meta') or {}
        if isinstance(meta, dict):
            report_date = meta.get('date', '') or ''

        existing_out = notes_map.get(division_id) or {}
        existing_cards_out = list(existing_out.get('cards') or [])

        # 현재 동기화 대상 카드 title 집합
        _target_titles = set()
        for _c in cards:
            _t = _norm_title((_c or {}).get('title'))
            if _t:
                _target_titles.add(_t)

        _final_cards = []
        for _c in existing_cards_out:
            if not isinstance(_c, dict):
                _final_cards.append(_c)
                continue
            _t = _norm_title((_c or {}).get('title'))
            if _t and _t in _target_titles:
                continue
            _final_cards.append(_c)

        # 현재 doc 카드만 추가 (기존 순서 유지 + 신규 카드 append)
        for _c in merged_cards:
            if isinstance(_c, dict):
                _final_cards.append(_c)

        notes_map[division_id] = {
            'report_date': report_date or existing.get('report_date', ''),
            'updated_at': datetime.now().isoformat(),
            'raw_text': existing.get('raw_text', ''),
            'cards': _final_cards,
        }
        _save_notes(data)
    except Exception as e:
        import traceback
        print(f'[sync_report_to_notes ERROR] {e}')
        traceback.print_exc()

# ============================================================
#  사업부 열 구성 · 화면 스위치 · 앱 숨기기 · 용어
# ============================================================
# 사업부별 양식 열 구성 (division_columns) ← admin v2 _mdlColSpecLoad()
@app.get("/admin/division-columns")
def admin_division_columns(_admin: int = Depends(get_admin_session)):
    return {d: _dcol.columns_for(d) for d in _dcol.SHAPES}


# ============================================================
#  사업부마다 무엇을 보이고 무엇을 숨길까
# ============================================================
# 사업부마다 앱에 보이나. admin 화면의 체크박스가 이걸 그린다 ← admin v2 saveAppVis()
@app.get("/admin/divisions/app-visibility")
def admin_division_app_visibility(_admin: int = Depends(get_admin_session)):
    hidden = _dvis.hidden_set()
    return {
        "divisions": [
            {
                "id": d.get("id"),
                "label": d.get("label"),
                "order": d.get("order", 999),
                "app_visible": str(d.get("id") or "").lower() not in hidden,
            }
            for d in _cl.get_divisions(visible_only=True)
        ],
        "hidden": sorted(hidden),
    }


# 숨김 목록을 통째로 갈아 끼운다 ← admin v2 saveAppVis()
@app.post("/admin/divisions/app-visibility")
async def admin_set_division_app_visibility(
    payload: dict = Body(...),
    _admin: int = Depends(get_admin_session),
):
    ids = payload.get("hidden")
    if not isinstance(ids, list):
        raise HTTPException(status_code=400,
                            detail="hidden 목록을 보내 주세요")
    known = {str(d.get("id") or "").lower()
             for d in _cl.get_divisions(visible_only=False)}
    unknown = [x for x in ids if str(x).strip().lower() not in known]
    if unknown:
        raise HTTPException(status_code=400,
                            detail="모르는 사업부입니다: %s" % ", ".join(map(str, unknown)))
    got = _dvis.replace(ids)
    return {"ok": True, "hidden": sorted(got)}


# 그 사업부의 용어 사전. 양식 '용어' 시트에서 온다
@app.get("/divisions/{division_id}/terms")
def division_terms(division_id: str):
    return JSONResponse(
        {"division_id": division_id, "terms": _dterm.get(division_id)},
        headers={"Cache-Control": "no-store, max-age=0"},
    )


# 어느 사업부에서 무엇을 보일까. 앱과 admin 이 같은 답을 본다 ← admin v2 _divUiLoad()
@app.get("/divisions/ui")
def divisions_ui():
    return JSONResponse(
        _dcol.all_ui(),
        # 스위치를 올리고 앱을 다시 켰는데 옛 값이 오면 안 고쳐진 줄 안다.
        headers={"Cache-Control": "no-store, max-age=0"},
    )

# ============================================================
#  admin 모델 표 (보기 · 예전 고치기 길)
# ============================================================
# admin용 모델 목록 조회 ← admin v2 mdlRefresh() · loadModels() · saveModels()
@app.get("/admin/projects/{project_key}/models")
def admin_get_project_models(project_key: str, _admin: int = Depends(get_admin_session)):
    models = _get_project_models(project_key)
    return {
        "project_key": project_key,
        "models": models,
        "alerts": _admin_model_alerts(models),
    }


# 모델 id → {kind, why}.
def _admin_model_alerts(models) -> dict:
    out = {}
    for m in (models or []):
        mid = str((m or {}).get("id") or "")
        if not mid:
            continue
        disp = _display_group(m)
        expected = ""
        progress = None
        if disp == "개발":
            proc = _ensure_process(m)
            _stage, expected = _process_current(proc)
            progress = _process_progress(proc)
        kind = _model_alert(m, disp, expected, progress)
        if kind not in ("지연", "주의"):
            continue
        out[mid] = {"kind": kind, "group": disp,
                    "why": _alert_why(m, disp, expected, kind)}
    return out


# 왜 그렇게 봤는지 한 줄. 빈칸으로 두면 화면에서 따질 근거가 없다
def _alert_why(m: dict, disp: str, expected: str, kind: str) -> str:
    manual = str((m or {}).get("status") or "").strip()
    if manual in ("지연", "주의"):
        return "상태를 %s 으로 지정" % manual
    txt = " ".join(str((m or {}).get("issues") or "").split())
    if _issue_says_delay(txt):
        return txt[:60]
    if disp != "개발" or not expected:
        return ""
    d = _parse_any_date(expected)
    if not d:
        return ""
    import datetime as _dt
    left = (d - _dt.date.today()).days
    stage = str((m or {}).get("current_stage") or "").strip()
    if not stage:
        try:
            stage = _process_current(_ensure_process(m))[0] or ""
        except Exception:
            stage = ""
    head = ("%s " % stage) if stage else ""
    return ("%s완료예정 %s · %d일 지남" % (head, expected, -left)) if left < 0 \
        else ("%s완료예정 %s · %d일 남음" % (head, expected, left))


# 모델 단건 추가. 같은 id가 이미 있으면 409 반환 ← admin v2 mdlRefresh() · loadModels() · saveModels()
@app.post("/admin/projects/{project_key}/models")
def admin_add_model(project_key: str, payload: dict, _admin: int = Depends(get_admin_session)):
    _alias = {
        "havaplate": "hrva_plate",
        "hrvaplate": "hrva_plate",
        "hrva-plate": "hrva_plate",
    }
    _key = _alias.get(project_key.strip().lower(), project_key.strip())
    data = _load_models()
    proj = data.setdefault("projects", {}).setdefault(_key, {"models": []})
    existing_ids = {m.get("id") for m in proj.get("models", [])}
    norm = _normalize_model(payload or {}, existing_ids)
    if norm is None:
        raise HTTPException(status_code=400, detail="모델명이 필요하거나 ID가 중복됩니다.")
    proj.setdefault("models", []).append(norm)
    # 양산을 앞에, 개발을 뒤에 (같은 구분 안에서는 원래 순서 그대로)
    proj["models"].sort(key=lambda m: 0 if m.get("group") == "양산" else 1)
    _save_models(data)
    print(f"[models] POST {_key}: +{norm['id']} ({len(proj['models'])} models)")
    return {"ok": True, "project_key": _key, "model": norm, "total": len(proj["models"])}


# 모델 단건 수정 (부분 업데이트) payload: 변경할 필드만 {"name": "...", "progress": 50, ...}
@app.patch("/admin/projects/{project_key}/models/{model_id}")
def admin_update_model(project_key: str, model_id: str, payload: dict, _admin: int = Depends(get_admin_session)):
    from urllib.parse import unquote
    model_id = unquote(model_id)
    _alias = {
        "havaplate": "hrva_plate",
        "hrvaplate": "hrva_plate",
        "hrva-plate": "hrva_plate",
    }
    _key = _alias.get(project_key.strip().lower(), project_key.strip())
    data = _load_models()
    proj = data.setdefault("projects", {}).setdefault(_key, {"models": []})
    target = None
    for m in proj.get("models", []):
        if m.get("id") == model_id:
            target = m
            break
    if target is None:
        raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")
    if "name" in payload and str(payload["name"]).strip():
        target["name"] = str(payload["name"]).strip()
    if "group" in payload:
        g = str(payload["group"]).strip()
        if g in ("양산", "개발"):
            target["group"] = g
    if "progress" in payload:
        try:
            p = int(payload["progress"])
        except (ValueError, TypeError):
            p = target.get("progress", 0)
        target["progress"] = max(0, min(100, p))
    if "status" in payload:
        s = str(payload["status"]).strip()
        s = _LEGACY_MODEL_STATUS.get(s, s)
        if s in MODEL_STATUSES:
            target["status"] = s
    if "price" in payload:
        try:
            target["price"] = max(0, _as_money(payload["price"]))
        except (ValueError, TypeError):
            pass
    if "material_cost" in payload:
        try:
            target["material_cost"] = max(0, _as_money(payload["material_cost"]))
        except (ValueError, TypeError):
            pass
    _save_models(data)
    print(f"[models] PATCH {_key}/{model_id}")
    return {"ok": True, "project_key": _key, "model": target}


# 모델 단건 삭제
@app.delete("/admin/projects/{project_key}/models/{model_id}")
def admin_delete_model(project_key: str, model_id: str, _admin: int = Depends(get_admin_session)):
    from urllib.parse import unquote
    model_id = unquote(model_id)
    _alias = {
        "havaplate": "hrva_plate",
        "hrvaplate": "hrva_plate",
        "hrva-plate": "hrva_plate",
    }
    _key = _alias.get(project_key.strip().lower(), project_key.strip())
    data = _load_models()
    proj = data.setdefault("projects", {}).setdefault(_key, {"models": []})
    before = len(proj.get("models", []))
    proj["models"] = [m for m in proj.get("models", []) if m.get("id") != model_id]
    after = len(proj["models"])
    if before == after:
        raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")
    _save_models(data)
    print(f"[models] DELETE {_key}/{model_id}")
    return {"ok": True, "project_key": _key, "removed": before - after, "total": after}


#: 화면에서도 고치고 엑셀로도 들어오는 칸. 둘이 부딪히는 자리다.
_SAVE_GUARDED = ("price", "material_cost", "po_qty", "shipped_qty")

# ============================================================
#  화면에서 고치는 길을 닫는다 — 기준은 엑셀 하나
# ============================================================
def _save_untouched(f, sent, base) -> bool:
    def num(v):
        try:
            return float(str(v if v is not None else "").replace(",", "").strip() or 0)
        except (TypeError, ValueError):
            return None

    a, b = num(sent), num(base)
    if a is not None and b is not None:
        return abs(a - b) < 0.005
    return str(sent or "").strip() == str(base or "").strip()


# 화면 쪽(admin_v2.html)만 잠그면 반쪽이다
ADMIN_WRITE_OFF = True

#: 막는 자리와, 사람에게 대신 알려줄 길
_WRITE_OFF_WHERE = {
    "models": "모델 정보(판가 · 재료비 · PO · 실적 · 구분 · 유형)",
    "status-note": "프로젝트 현황",
    "week-reason": "주차 미달 사유",
}


# ==== admin 은 보기 전용 — 손으로 바꾸는 길을 전부 닫는다
_ADMIN_LOCKED = [
    # 모델 · 공정 · 주차 계획 직접 입력
    ("POST", "/admin/projects/{project_key}/models"),
    ("PATCH", "/admin/projects/{project_key}/models/{model_id}"),
    ("DELETE", "/admin/projects/{project_key}/models/{model_id}"),
    ("PUT", "/admin/projects/{project_key}/models"),
    ("PUT", "/admin/projects/{project_key}/types"),
    ("PUT", "/admin/projects/{project_key}/status-note"),
    ("DELETE", "/admin/projects/{project_key}/weekly-plan"),
    ("POST", "/admin/projects/{project_key}/models/alias"),
    ("PUT", "/admin/projects/{project_key}/model-weekly-plan"),
    ("PUT", "/admin/projects/{project_key}/model-process"),
    ("POST", "/admin/projects/{project_key}/model-process/step-status"),
    ("PUT", "/admin/projects/{project_key}/group-weekly-plan"),
    ("PUT", "/admin/projects/{project_key}/group-summary"),
    ("PUT", "/admin/projects/{project_key}/week-reason"),
    ("PUT", "/admin/projects/{project_key}/board-rows"),
    ("PUT", "/admin/projects/{project_key}/models/{model_id}/weekly-plan"),
    ("PUT", "/admin/projects/{project_key}/process-lead"),
    ("POST", "/admin/projects/{project_key}/models/{model_id}/process/step-status"),
    ("PUT", "/admin/projects/{project_key}/models/{model_id}/process"),
    # 이름 맞추기를 손으로 고치는 길
    ("POST", "/admin/projects/resolve"),
    ("POST", "/admin/projects/alias"),
    # KPI 직접 입력
    ("POST", "/admin/kpi/{project_key}/months"),
    ("POST", "/admin/kpi/{project_key}/weeks"),
    ("POST", "/admin/kpi/{project_key}/issue_lines"),
    # 목표 · 예상 · 매입 · 잔특근 · 수주 직접 입력
    ("POST", "/admin/home/division-target"),
    ("PUT", "/admin/home/orders"),
    ("POST", "/admin/revenue/estimate"),
    ("POST", "/admin/revenue/target"),
    ("PUT", "/admin/division/purchase"),
    ("PUT", "/admin/overtime"),
    # 사업부 노트 편집 · 삭제
    ("POST", "/admin/notes/from_pptx"),
    ("POST", "/admin/notes/ai_parse"),
    ("POST", "/admin/notes"),
    ("POST", "/admin/notes/item/due_override"),
    ("DELETE", "/admin/notes/item/due_override"),
    ("POST", "/admin/notes/item/hide_auto_due"),
    ("DELETE", "/admin/notes/item/hide_auto_due"),
    ("DELETE", "/admin/notes/{division_id}"),
    ("POST", "/admin/notes/table"),
    ("DELETE", "/admin/notes/table/{division_id}/{asset_id}"),
    ("POST", "/admin/notes/photo"),
    ("POST", "/admin/notes/excel"),
    ("DELETE", "/admin/notes/photo/{division_id}/{filename}"),
    ("POST", "/admin/notes/section/sales_input"),
    ("POST", "/admin/notes/section/sales_recompute"),
    # 보고 카드 만들기 · 고치기 · 지우기 · 통째로 비우기
    ("POST", "/admin/reports"),
    ("PUT", "/admin/reports/{doc_id}"),
    ("DELETE", "/admin/reports/{doc_id}"),
    ("POST", "/admin/reports/{doc_id}/edit_done"),
    ("POST", "/admin/reports/{doc_id}/section-file"),
    ("POST", "/admin/reports/{doc_id}/section-parse-xlsx"),
    ("POST", "/admin/reports/{doc_id}/polish-text"),
    ("POST", "/admin/reports/{doc_id}/hide"),
    ("DELETE", "/admin/doc/{doc_id}"),
    ("POST", "/admin/docs/delete-batch"),
    ("DELETE", "/admin/card"),
    ("POST", "/admin/reset"),
]

_ADMIN_OPEN = [
    # 로그인
    ("POST", "/admin/login"), ("POST", "/admin/logout"), ("POST", "/admin/extend"),
    # 파일로 들어오는 길 — 자료는 이 길로만 바뀐다
    ("POST", "/admin/divisions/{division_id}/form/preview"),
    ("POST", "/admin/divisions/{division_id}/form/apply"),
    ("POST", "/admin/divisions/{division_id}/dev-schedule/preview"),
    ("POST", "/admin/divisions/{division_id}/dev-schedule/apply"),
    ("POST", "/admin/divisions/{division_id}/daily/preview"),
    ("POST", "/admin/divisions/{division_id}/daily/apply"),
    ("POST", "/admin/projects/{project_key}/bloom-daily/preview"),
    ("POST", "/admin/projects/{project_key}/bloom-daily"),
    ("POST", "/admin/divisions/{division_id}/revenue-file/preview"),
    ("POST", "/admin/divisions/{division_id}/revenue-file/apply"),
    ("POST", "/admin/revenue/import"),
    ("POST", "/admin/revenue/estimate/import"),
    ("POST", "/admin/overtime/import-xlsx"),
    ("POST", "/admin/division/purchase/import-xlsx"),
    ("POST", "/admin/kpi/{project_key}/upload_excel"),
    ("POST", "/admin/projects/{project_key}/weekly-plan"),
    ("POST", "/admin/projects/{project_key}/price-import-xlsx"),
    ("POST", "/admin/projects/{project_key}/import-xlsx"),
    ("POST", "/admin/projects/{project_key}/process/import-xlsx"),
    ("POST", "/admin/projects/{project_key}/weekly-summary-import"),
    ("POST", "/admin/projects/{project_key}/report-import"),
    # 사업부 양식이 대신해서 _form_only 가 따로 닫아 둔 길 (여기서는 열어 둔다)
    ("POST", "/admin/projects/{project_key}/models/import"),
    ("POST", "/admin/projects/{project_key}/plan-file/preview"),
    ("POST", "/admin/projects/{project_key}/plan-file/apply"),
    ("POST", "/admin/projects/{project_key}/status-excel"),
    ("POST", "/admin/automotive/product-import/preview"),
    ("POST", "/admin/automotive/product-import/apply"),
    # 앱 배포 (release.sh) · 백업 · 복구 · 운영
    ("POST", "/admin/app/release"),
    ("POST", "/admin/backups/run"), ("POST", "/admin/backups/prune"),
    ("POST", "/admin/backups/restore"),
    ("POST", "/admin/models/restore"), ("POST", "/admin/models/restore-missing"),
    ("POST", "/admin/projects/{project_key}/process-restore"),
    ("POST", "/admin/rag/rebuild"), ("POST", "/admin/fcm-test"),
    # 앱에서 어느 사업부를 숨길지 — 자료가 아니라 보이기 설정이다
    ("POST", "/admin/divisions/app-visibility"),
]

# ============================================================
#  admin 잠금 — 고치기 · 지우기 막기
# ============================================================
def _route_re(template: str):
    import re as _re
    return _re.compile("^" + _re.sub(r"\\\{[^}]+\\\}", "[^/]+", _re.escape(template)) + "/?$")


_ADMIN_LOCKED_RE = [(m, _route_re(t)) for m, t in _ADMIN_LOCKED]


# 이 주소가 admin 잠금 목록에 있나 (고치기·지우기 막기).
def _admin_locked(method: str, path: str) -> bool:
    m = str(method or "").upper()
    return any(m == lm and rx.match(path or "") for lm, rx in _ADMIN_LOCKED_RE)


# 모든 요청이 지나가는 문 (미들웨어)
@app.middleware("http")
async def _admin_write_lock(request: Request, call_next):
    if ADMIN_WRITE_OFF and request.url.path.startswith("/admin/") \
            and _admin_locked(request.method, request.url.path):
        # 423 Locked — 막혔다는 걸 화면이 알아보고 안내를 띄운다
        return JSONResponse(status_code=423, content={
            "detail": ("admin 에서는 자료를 고치거나 지울 수 없습니다. "
                       "사업부 양식(또는 해당 엑셀)으로 올려 주세요."),
            "locked": True})
    return await call_next(request)


# 화면이 받아 가는 잠금 목록. 화면에 따로 적어 두면 서버와 갈린다 ← admin v2 fetch()
@app.get("/admin/write-lock")
def admin_write_lock_info(_admin: int = Depends(get_admin_session)):
    return {"on": bool(ADMIN_WRITE_OFF),
            "locked": [[m, t] for m, t in _ADMIN_LOCKED]}


# 막혀 있으면 403 으로 돌려보낸다
def _write_off(what: str):
    if not ADMIN_WRITE_OFF:
        return
    raise HTTPException(
        status_code=403,
        detail=(_WRITE_OFF_WHERE.get(what, what)
                + " — 화면에서 고치지 않습니다. "
                  "'주차별 계획' 탭에서 양식을 받아 고친 뒤 올려 주세요."))

# ============================================================
#  모델 목록 통째로 저장
# ============================================================
# admin용 모델 목록 저장 (전체 교체) ← admin v2 mdlRefresh() · loadModels() · saveModels()
@app.put("/admin/projects/{project_key}/models")
def admin_put_project_models(project_key: str, payload: dict, _admin: int = Depends(get_admin_session)):
    _write_off("models")
    _alias = {
        "havaplate": "hrva_plate",
        "hrvaplate": "hrva_plate",
        "hrva-plate": "hrva_plate",
    }
    _key = _alias.get(project_key.strip().lower(), project_key.strip())

    raw_models = payload.get("models") or []
    if not isinstance(raw_models, list):
        raise HTTPException(status_code=400, detail="models는 배열이어야 합니다.")

    # 화면이 열릴 때 받아 둔 값. 없으면(옛 화면) 예전처럼 보낸 값을 다 쓴다.
    base_map = payload.get("base")
    if not isinstance(base_map, dict):
        base_map = {}

    data = _load_models()
    projects = data.setdefault("projects", {})
    proj = projects.setdefault(_key, {})
    old_map = {m.get("id"): m for m in proj.get("models", []) if isinstance(m, dict)}

    # 판가·재료비를 언제부터 적용할지. 화면에서 저장할 때 물어본다.
    #   from_now  이번 주부터 (지난 주차 매출은 그대로)
    #   retro     지금 적용 중인 구간을 덮는다 (입력 오류 정정)
    #   preview   저장하지 않고 '무엇이 바뀌는지' 만 돌려준다
    _price_mode = str(payload.get("price_mode") or "from_now").strip()
    if _price_mode not in ("from_now", "retro", "preview"):
        _price_mode = "from_now"
    _price_changes = []

    normalized = []
    seen_ids = set()
    for m in raw_models:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "").strip()
        name = str(m.get("name") or "").strip()
        # 이름이 비어 있어도 버리지 않는다
        if not mid:
            continue
        if mid in seen_ids:
            continue
        seen_ids.add(mid)
        group = str(m.get("group") or "양산").strip()
        if group not in ("양산", "개발"):
            group = "양산"
        try:
            progress = int(m.get("progress") or 0)
        except (ValueError, TypeError):
            progress = 0
        progress = max(0, min(100, progress))
        status = str(m.get("status") or "정상").strip()
        try:
            price = _as_money(m.get("price"))
        except (ValueError, TypeError):
            price = 0
        try:
            material_cost = _as_money(m.get("material_cost"))
        except (ValueError, TypeError):
            material_cost = 0
        old = old_map.get(mid) or {}
        # 서버에 있던 것을 바탕으로 깔고, 이 화면에서 고치는 칸만 덮는다
        entry = dict(old)
        entry.update({
            "id": mid,
            "name": name,
            "group": group,
            "progress": progress,
            "status": status,
            "price": max(0, price),
            "material_cost": max(0, material_cost),
            # ESS 필드 추가
            # 문자열('3,427')이 오면 int() 가 예외를 던져 저장 전체가 500 이 된다.
            "po_qty": max(0, _as_int(m.get("po_qty"))),
            "shipped_qty": max(0, _as_int(m.get("shipped_qty"))),
            "due_text": str(m.get("due_text") or ""),
            "issues": str(m.get("issues") or ""),
            # 이슈와 별개로 자유롭게 적는 비고(메모)
            "note": str(m.get("note") or ""),
        })
        # 화면을 연 뒤 다른 곳(엑셀 업로드·주차 입력)에서 들어간 값을 지킨다
        _b = base_map.get(mid)
        if isinstance(_b, dict):
            for _f in _SAVE_GUARDED:
                if _f not in _b or _f not in old:
                    continue
                if _save_untouched(_f, m.get(_f), _b.get(_f)):
                    entry[_f] = old[_f]

        # 이 화면에서 편집하지 않는 묶음은 서버에 있는 것을 그대로 둔다
        for _keep in ("weekly_plan", "weekly_progress", "weekly_summary",
                      "current_expected", "current_stage", "auto"):
            if old.get(_keep) is not None:
                entry[_keep] = old.get(_keep)
            elif m.get(_keep) is not None:
                entry[_keep] = m.get(_keep)
        # 파트넘버는 이 화면에서 고칠 수 있다 — 보낸 값을 먼저 본다.
        if m.get("part_number") is not None:
            entry["part_number"] = m.get("part_number")
        elif old.get("part_number") is not None:
            entry["part_number"] = old.get("part_number")
        # 비고를 지우고 저장하면 지워져야 한다. 빈 값을 '안 보냈다' 로 보고
        # 옛 값을 되살리면, 화면에서 비웠는데 저장하면 다시 살아난다.
        # (유형 칸에서 났던 것과 같은 문제다 — 키가 왔으면 그 값이 맞다.)
        if "note" not in m and old.get("note"):
            entry["note"] = old.get("note")
        # 구분·판가 이력 (개발→양산 전환, 판가 변경). 과거 매출이 흔들리지 않게 보존한다.
        _ph = _norm_phases(m.get("phases") if m.get("phases") is not None else old.get("phases"))
        if _ph:
            entry["phases"] = _ph
        # 판가·재료비가 바뀌었으면 구간으로 남긴다. 안 그러면 오늘 고친 판가로
        # 지난달 매출까지 다시 계산된다.
        _chg = _apply_price_change(
            entry, old, "from_now" if _price_mode == "preview" else _price_mode,
            sent=m)
        if _chg:
            _price_changes.append(_chg)
        # 프로세스는 이 화면에서 편집하지 않는다
        _proc = old.get("process")
        # 유형을 '—' 로 비우고 저장하면 지워져야 한다. 빈 값을 '안 보냈다' 로
        # 보고 옛 값을 되살리면, 화면에서는 비웠는데 저장하면 DEP챔버 가
        # 되돌아온다 (챔버에서 실제로 그랬다). 키가 왔으면 그 값이 맞다.
        _sent_dt = "dev_type" in m
        def _dt_of(mm, oldd):
            src = mm.get("dev_type") if _sent_dt else oldd.get("dev_type")
            return str(src or "").strip().upper()
        if group == "개발":
            dev_type = _dt_of(m, old)
            entry["dev_type"] = dev_type
            # 단계 수는 프로젝트마다 다르다 — 파워박스 15, EMA 14, 메이저모듈 12.
            entry["process"] = _proc if isinstance(_proc, list) and _proc else _default_process()
            # 진행률도 프로세스에서 다시 낸다. 보낸 값을 그대로 쓰면
            # 방금 고친 단계가 옛날 진행률로 되돌아간다.
            entry["progress"] = _process_progress(entry["process"])
        else:
            # 양산으로 넘어가도 개발 때 쌓인 유형/공정 이력은 지우지 않는다.
            # 단, 화면에서 비우고 저장한 것은 지우는 게 맞다.
            _dt = _dt_of(m, old)
            if _dt:
                entry["dev_type"] = _dt
            elif _sent_dt:
                entry["dev_type"] = ""
            if isinstance(_proc, list) and _proc:
                entry["process"] = _proc
        normalized.append(entry)

    # 양산을 앞에, 개발을 뒤에 (같은 구분 안에서는 원래 순서 그대로)

    normalized.sort(key=lambda m: 0 if m.get("group") == "양산" else 1)

    # 이 저장으로 사라지는 모델. '전체 교체' 라 화면이 목록을 덜 들고 저장하면 나머지가 통째로 지워진다 — 실제로 챔버 19종·SpaceX 16종이 그렇게 날아갔다
    _gone = [mid for mid in old_map if mid not in seen_ids]
    _allow = bool(payload.get("allow_delete"))
    if (_price_mode != "preview" and _gone and not _allow
            and (len(_gone) >= 5 or len(_gone) > len(old_map) * 0.25)):
        raise HTTPException(
            status_code=409,
            detail=("이 저장은 %d종을 지웁니다 (%d종 → %d종). 화면이 목록을 "
                    "덜 불러온 상태로 보이니 새로 고친 뒤 다시 저장해 주세요. "
                    "정말 지우려면 지우기 버튼으로 지운 뒤 저장하세요. "
                    "사라질 모델: %s"
                    % (len(_gone), len(old_map), len(normalized),
                       ", ".join(_gone[:8]) + (" 외" if len(_gone) > 8 else ""))))

    if _price_mode == "preview":
        # 무엇이 바뀌는지만 알려주고 아무것도 저장하지 않는다.
        return {"ok": True, "project_key": _key, "preview": True,
                "count": len(normalized), "removing": _gone,
                "price_changes": _price_changes}
    proj["models"] = normalized
    _save_models(data)
    print(f"[models] saved {_key}: {len(normalized)} models"
          + (f" · 삭제 {len(_gone)}종" if _gone else "")
          + (f" · 판가 이력 {len(_price_changes)}건({_price_mode})" if _price_changes else ""))
    return {"ok": True, "project_key": _key, "count": len(normalized),
            "removed": _gone,
            "price_mode": _price_mode, "price_changes": _price_changes}


# ─── 프로젝트별 유형(types) 관리 ───

# ============================================================
#  모델 유형 · 현황 메모
# ============================================================
def _get_project_types(project_key: str) -> list:
    data = _read_json(MODELS_FILE, {})
    proj = data.get("projects", {}).get(project_key, {})
    types = proj.get("types")
    out = [t for t in types if isinstance(t, str) and t.strip()] if isinstance(types, list) else []
    gone = {t for t in (proj.get("types_removed") or [])
            if isinstance(t, str) and t.strip()}
    seen = {t for t in out}
    extra = []
    for m in proj.get("models") or []:
        if not isinstance(m, dict):
            continue
        t = str(m.get("dev_type") or "").strip()
        if t and t not in seen and t not in gone:
            seen.add(t)
            extra.append(t)
    return out + sorted(extra)


# 프로젝트의 모델 유형 목록 (앱) ← admin v2 loadProjectTypes() · loadTypes() · saveTypes()
@app.get("/projects/{project_key}/types")
def get_project_types(project_key: str):
    return {"project_key": project_key, "types": _get_project_types(project_key)}


# 프로젝트의 모델 유형 목록 (admin) ← admin v2 loadProjectTypes() · loadTypes() · saveTypes()
@app.get("/admin/projects/{project_key}/types")
def get_admin_project_types(project_key: str, _admin: int = Depends(get_admin_session)):
    return {"project_key": project_key, "types": _get_project_types(project_key)}


# 프로젝트별 유형 목록 저장 ← admin v2 loadProjectTypes() · loadTypes() · saveTypes()
@app.put("/admin/projects/{project_key}/types")
def save_project_types(project_key: str, payload: dict,
                       _admin: int = Depends(get_admin_session)):
    types = payload.get("types")
    if not isinstance(types, list):
        raise HTTPException(status_code=400, detail="types는 배열이어야 합니다")
    # 공백 제거 + 중복 제거 + 빈 문자열 제거
    types = list(dict.fromkeys(t.strip() for t in types if isinstance(t, str) and t.strip()))
    data = _read_json(MODELS_FILE, {})
    proj = data.setdefault("projects", {}).setdefault(project_key, {"models": []})
    proj["types"] = types
    # 모델이 쓰고 있는데 목록에서 빠진 것 = 사람이 지운 것.
    # 적어 두지 않으면 다음에 읽을 때 모델을 보고 도로 끼워 넣는다.
    used = set()
    for m in proj.get("models") or []:
        if isinstance(m, dict):
            t = str(m.get("dev_type") or "").strip()
            if t:
                used.add(t)
    proj["types_removed"] = sorted(used - set(types))
    _save_models(data)
    return {"ok": True, "project_key": project_key, "types": types,
            "removed": proj["types_removed"]}


# ─── 프로젝트 현황 메모 ───

# 프로젝트 현황 메모 (앱 상세) ← admin v2 back.onclick()
@app.get("/projects/{project_key}/status-note")
def get_project_status_note(project_key: str):
    _key = _model_key_alias(project_key)
    proj = (_load_models().get("projects") or {}).get(_key) or {}
    return {"project_key": _key, "status_note": proj.get("status_note") or "",
            "hold": _project_hold(proj), "hold_reason": _project_hold_reason(proj)}


# 프로젝트 현황 메모 저장 (앱 프로젝트 화면에 표시) ← admin v2 back.onclick()
@app.put("/admin/projects/{project_key}/status-note")
def put_project_status_note(project_key: str, payload: dict,
                            _admin: int = Depends(get_admin_session)):
    _write_off("status-note")
    note = str((payload or {}).get("note") or "").strip()
    _key = _model_key_alias(project_key)
    data = _load_models()
    proj = data.setdefault("projects", {}).setdefault(_key, {"models": []})
    proj["status_note"] = note
    # admin 에서 직접 고른 값이 문구보다 우선한다
    _h = str((payload or {}).get("hold") or "").strip()
    if _h:
        if _h in ("진행", "해제", "없음"):
            # 지우기만 하면 서버가 다시 뜰 때 현황 문구를 읽고 되살린다.
            # '진행' 을 손으로 골랐다는 사실 자체를 남긴다.
            proj["hold"] = "진행"
            proj["hold_source"] = "manual"
            proj.pop("hold_reason", None)
        else:
            proj["hold"] = "드롭예정" if "드롭" in _h else "보류"
            proj["hold_source"] = "manual"
            proj["hold_reason"] = _hold_from_note(note)[1] or proj.get("hold_reason") or ""
    else:
        _stamp_project_hold(proj, note)
    _save_models(data)
    print(f"[status-note] {_key}: {len(note)}자 저장 · 보류={proj.get('hold') or '-'}")
    return {"ok": True, "project_key": _key, "status_note": note,
            "hold": proj.get("hold") or "", "hold_reason": proj.get("hold_reason") or ""}


# ─── 주차별 계획 (프로젝트당 1개) ───

# ============================================================
#  주차별 계획표 (이미지)
# ============================================================
# 프로젝트 주차별 계획 조회 (앱용) ← admin v2 loadWeekMarks() · 앱 project_overview_screen.dart _loadBloom() 외
@app.get("/projects/{project_key}/weekly-plan")
def get_weekly_plan(project_key: str):
    _alias = {
        "havaplate": "hrva_plate",
        "hrvaplate": "hrva_plate",
        "hrva-plate": "hrva_plate",
    }
    _key = _alias.get(project_key.strip().lower(), project_key.strip())
    data = _load_models()
    proj = (data.get("projects") or {}).get(_key) or {}
    plan = proj.get("weekly_plan") or {}
    _ref = plan.get("photo_ref")
    return {
        "project_key": _key,
        "has_plan": bool(_ref),
        "file_name": plan.get("file_name"),
        "uploaded_at": plan.get("uploaded_at"),
        "photo_ref": _ref,
        "marked_weeks": plan.get("marked_weeks") or [],
        "url": f"/note_photos/{_ref}" if _ref else None,
    }


# 주차별 계획 엑셀 업로드 → 첫 시트를 PNG로 변환 → 저장 (보고서 엑셀과 동일 방식)
@app.post("/admin/projects/{project_key}/weekly-plan")
async def admin_upload_weekly_plan(
    project_key: str,
    file: UploadFile = File(...),
    _admin: int = Depends(get_admin_session),
):
    _alias = {
        "havaplate": "hrva_plate",
        "hrvaplate": "hrva_plate",
        "hrva-plate": "hrva_plate",
    }
    _key = _alias.get(project_key.strip().lower(), project_key.strip())

    orig_name = file.filename or "weekly_plan.xlsx"
    lower = orig_name.lower()
    if not (lower.endswith(".xlsx") or lower.endswith(".xlsm")):
        raise HTTPException(status_code=400, detail="xlsx/xlsm 파일만 허용")
    raw = await _keep_upload(file, "/admin/projects/{project_key}/weekly-plan", project_key)
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일")

    try:
        import openpyxl
        from io import BytesIO
        import base64
        wb = openpyxl.load_workbook(BytesIO(raw), data_only=True, keep_links=False)
        ws = wb.worksheets[0]
        data_url = _excel_sheet_to_preview_data_url(ws)
        b64 = data_url.split(",", 1)[1]
        png_bytes = base64.b64decode(b64)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"엑셀 변환 실패: {e}")

    asset_id = "plan_" + _new_asset_id(_key)
    out_path = _photo_path(_key, asset_id, "png")
    out_path.write_bytes(png_bytes)
    photo_ref = f"{_key}/{asset_id}.png"

    data = _load_models()
    proj = data.setdefault("projects", {}).setdefault(_key, {"models": []})
    # 기존 계획 이미지가 있으면 삭제
    old_ref = (proj.get("weekly_plan") or {}).get("photo_ref")
    if old_ref:
        try:
            _delete_note_photo(old_ref)
        except Exception:
            pass
    try:
        _marked = _detect_marked_weeks(ws)
    except Exception as _e_mw:
        _marked = []
        print(f"[weekly_plan] 표시 주차 감지 실패: {_e_mw}")
    # -----------------------------------------------------------
    # '구분 x 주차' 표면 모델별 주차 계획까지 자동 반영
    # -----------------------------------------------------------
    _applied = None
    try:
        import plan_matrix_import as _pmi
        _wb_fresh = openpyxl.load_workbook(BytesIO(raw), data_only=True, keep_links=False)
        _parsed = _pmi.parse_plan_matrix(_wb_fresh)
        if _parsed.get("rows"):
            _applied = _apply_plan_matrix(data, _key, _parsed)
            print(f"[weekly_plan] 자동 반영: 매칭 {len(_applied['matched'])}건, "
                  f"신규 {_applied.get('created')}, 미매칭 {_applied['unmatched']}")
    except Exception as _e_pm:
        print(f"[weekly_plan] 주차 데이터 자동 반영 실패(무시): {_e_pm}")
    proj["weekly_plan"] = {
        "file_name": orig_name,
        "uploaded_at": datetime.now().isoformat(),
        "photo_ref": photo_ref,
        "marked_weeks": _marked,
    }
    if _marked:
        print(f"[weekly_plan] 표시 주차: {_marked}")
    _save_models(data)
    print(f"[weekly_plan] saved {_key}: {orig_name} -> {photo_ref}")
    return {
        "ok": True,
        "project_key": _key,
        "file_name": orig_name,
        "photo_ref": photo_ref,
        "url": f"/note_photos/{photo_ref}",
        "marked_weeks": _marked,
        "applied": _applied,
    }


# ============================================================
#  파워박스 'Plan and Actual' 출하계획 파일
# ============================================================
# 파워박스팀은 매주 'PBX 9월 출하계획' 파일을 쓴다


#: 주차 양식 왼쪽 칸 머리글 → 모델 필드
_PLAN_MODEL_COLS = {
    "파트넘버": "part_number", "파트번호": "part_number", "품번": "part_number",
    "모델명": "name", "모델": "name",
    "유형": "dev_type", "개발유형": "dev_type",
    "구분": "group",
    "판가": "price", "판가($)": "price",
    "재료비": "material_cost", "재료비($)": "material_cost",
    "po수량": "po_qty", "po": "po_qty",
    "실적수량": "shipped_qty",
    # 모델 등록 양식과 합치면서 들어온 두 칸
    "전환주차": "switch_week", "양산전환": "switch_week",
    "개발→양산전환주차": "switch_week", "개발->양산전환주차": "switch_week",
    "개발→양산": "switch_week", "개발->양산": "switch_week",
    "비고": "note",
}
#: 목록이 여기서 끝난다
_PLAN_STOP = ("합계", "미달사유", "총합계", "소계")

# ============================================================
#  계획표 엑셀 읽기 · 반영
# ============================================================
def _plan_sheet_models(ws) -> list:
    def _s2(v):
        return "" if v is None else str(v).strip()

    hdr, col = None, {}
    for r in range(1, min(ws.max_row, 10) + 1):
        got = {}
        for c in range(1, min(ws.max_column, 16) + 1):
            # 양식이 머리글 앞에 '✎' · '=' 표를 붙여 내보낸다
            # (적는 칸인지 자동 계산인지 글자로 보이게). 떼고 본다.
            k = _s2(ws.cell(r, c).value).strip("✎=＝*※·•-–— \t")
            k = k.replace(" ", "").lower()
            if not k or k.startswith("w"):
                continue
            f = _PLAN_MODEL_COLS.get(k)
            if f and f not in got:
                got[f] = c
        if "name" in got or "part_number" in got:
            hdr, col = r, got
            break
    if not hdr or len(col) < 2:
        return []

    # 그 줄이 누구인가는 **파트넘버가 먼저**다
    out = []
    _idc = col.get("part_number") or col.get("name") or 1
    for r in range(hdr + 1, ws.max_row + 1):
        head = "".join(_s2(ws.cell(r, c).value)
                       for c in range(1, min(_idc + 1, 5) + 1))
        if head.replace(" ", "") in _PLAN_STOP:
            break
        name = (_s2(ws.cell(r, col["part_number"]).value)
                if "part_number" in col else "")
        if not name and "name" in col:
            name = _s2(ws.cell(r, col["name"]).value)
        if not name:
            continue
        # 빈 양식에 얹어 둔 예시 줄은 모델로 만들지 않는다
        try:
            import pbx_plan_import as _pbxe
            if _pbxe._is_example(name):
                continue
        except Exception:
            pass
        row = {"row": r, "name": name}
        for f, c in col.items():
            # name 은 위에서 정한 '그 줄이 누구인가' 다. 덮어쓰지 않는다 —
            # 모델명 칸이 비어 있으면 숫자로 읽혀 None 이 돼 버린다.
            if f == "name":
                continue
            v = ws.cell(r, c).value
            # 글자 칸은 글자로 둔다. 2026-10-22 — 전환주차('2026-W36')와
            # 비고가 숫자 변환에 걸려 통째로 None 이 됐다. 양식에 적어
            # 올려도 서버에 안 들어갔다.
            if f in ("part_number", "dev_type", "group", "switch_week",
                     "note"):
                row[f] = _s2(v)
            else:
                # 빈 칸은 '그대로 둬라' 다. 0 으로 바꾸면 매주 여는 파일에서
                # 안 적은 칸이 지금 값을 지워 버린다.
                row[f] = (_as_int(v, None) if f in ("po_qty", "shipped_qty")
                          else _as_money(v, None))
        out.append(row)
    return out


# 어느 시트든 모델 줄이 있는 곳 → (시트이름, [줄]).
def _plan_models_anywhere(wb) -> tuple:
    best = ("", [])
    for ws in wb.worksheets:
        try:
            rows = _plan_sheet_models(ws)
        except Exception:
            rows = []
        if len(rows) > len(best[1]):
            best = (ws.title, rows)
    return best


# 개발 프로세스 일정표인가 → {'sheet','rows','steps'} 또는 None.
def _plan_process_peek(wb):
    import process_import as _pi

    best = None
    for ws in wb.worksheets:
        try:
            head, pn, steps, _c = _pi.find_layout(ws)
        except Exception:
            continue
        if not head or not pn or len(steps) < 2:
            continue
        rows = 0
        for r in range(head + 2, ws.max_row + 1):
            if str(ws.cell(r, pn).value or "").strip():
                rows += 1
        if rows and (best is None or rows > best["rows"]):
            best = {"sheet": ws.title, "rows": rows,
                    "steps": [s[1] for s in steps]}
    return best


#: 엑셀이 건드릴 수 있는 모델 칸
_PLAN_FIELDS = ("dev_type", "group", "price", "material_cost",
                "po_qty", "shipped_qty", "switch_week", "note")


# '덮어쓰기' 체크를 눌렀는가. 안 보내면 False (= 빈 칸만 채움).
def _plan_over(v) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "on", "yes")


# 그 칸이 '비어 있는가'.
def _plan_field_empty(old, f) -> bool:
    if f in ("price", "material_cost", "po_qty", "shipped_qty"):
        try:
            return not float(old or 0)
        except (TypeError, ValueError):
            return True
    return not str(old or "").strip()


# 등록된 모델과 대조 → (바뀌는 줄, 새로 생길 줄).
def _plan_model_changes(proj, mrows):
    import pbx_plan_import as _pbx

    models = proj.get("models") or []
    matcher = _pbx.Matcher(models)
    changed, created = [], []
    for row in mrows:
        m, _how = matcher.match(row["name"])
        fields = {}
        for f in ("dev_type", "group", "price", "material_cost", "po_qty", "shipped_qty"):
            v = row.get(f)
            if v in (None, "", 0) and f not in ("po_qty", "shipped_qty"):
                continue
            if v in (None, ""):
                continue
            fields[f] = v
        if m is None:
            created.append({"name": row["name"], "row": row["row"],
                            "part_number": row.get("part_number") or "",
                            "fields": fields})
            continue
        diff = {}
        for f, v in fields.items():
            old = m.get(f)
            if f in ("price", "material_cost"):
                same = abs(float(old or 0) - float(v or 0)) < 0.005
            elif f in ("po_qty", "shipped_qty"):
                same = int(old or 0) == int(v or 0)
            else:
                same = str(old or "").strip() == str(v).strip()
            if not same:
                # fill  : 비어 있던 칸을 채운다 → 늘 적용한다
                # 아니면: 값이 있던 칸을 덮어쓴다 → 골라야 적용한다
                diff[f] = {"from": old, "to": v,
                           "fill": _plan_field_empty(old, f)}
        if diff:
            changed.append({"name": m.get("name") or m.get("id"),
                            "model_id": m.get("id"), "row": row["row"], "fields": diff})
    return changed, created


# 모델 값을 넣는다. 없는 모델은 만든다 → {'updated','created','filled','over'}
def _plan_apply_models(proj, mrows, overwrite=False):
    import pbx_plan_import as _pbx

    models = proj.setdefault("models", [])
    matcher = _pbx.Matcher(models)
    updated, created = 0, []
    n_fill, n_over = 0, 0
    for row in mrows:
        m, _how = matcher.match(row["name"])
        if m is None:
            m = {"id": row["name"], "name": row["name"],
                 "group": row.get("group") or "양산"}
            if row.get("part_number"):
                m["part_number"] = row["part_number"]
            models.append(m)
            created.append(row["name"])
            matcher = _pbx.Matcher(models)      # 새 줄도 다음 매칭에 쓰이게
        touched = False
        for f in _PLAN_FIELDS:
            v = row.get(f)
            if v in (None, ""):
                continue
            if f == "group" and str(v).strip() not in ("양산", "개발"):
                continue
            was_empty = _plan_field_empty(m.get(f), f)
            if not was_empty and not overwrite:
                continue                      # 값이 있는 칸은 그대로 둔다
            m[f] = v
            touched = True
            if was_empty:
                n_fill += 1
            else:
                n_over += 1
        if row.get("part_number") and (overwrite or not str(
                m.get("part_number") or "").strip()):
            m["part_number"] = row["part_number"]
        if touched:
            updated += 1
    return {"updated": updated, "created": created,
            "filled": n_fill, "over": n_over}


#: 미달 사유를 '참고' 로 적는 말머리. 앞에 붙이면 문제로 세지 않는다.
_NOTE_FYI_HEADS = ("참고:", "참고 :", "[참고]", "참고)", "fyi:")


# '미달 사유' 줄 → 화면의 주차 미달 사유와 같은 자리에 넣는다
def _plan_apply_week_notes(proj, month, notes):
    if not notes:
        return 0
    import datetime as _dtn

    store = proj.setdefault("week_reasons", {})
    if not isinstance(store, dict):
        store = {}
        proj["week_reasons"] = store
    mon = store.setdefault(str(month), {})
    now = _dtn.datetime.now().isoformat(timespec="seconds")
    n_set = 0
    for w, text in (notes or {}).items():
        text = str(text or "").strip()
        if not text:
            continue                      # 빈 칸 = 그대로 둬라
        if text in ("-", "–", "—", "없음"):
            if mon.pop(str(w), None) is not None:
                n_set += 1
            continue
        low = text.lower().replace(" ", "")
        kind, body = "문제", text
        for head in _NOTE_FYI_HEADS:
            if low.startswith(head.replace(" ", "")):
                kind = "참고"
                body = text[len(head):].strip() or text
                break
        if kind == "문제":
            was = mon.get(w) if isinstance(mon.get(w), dict) else {}
            # 전에 '참고' 로 적어 둔 주는 말머리를 안 붙였어도 그대로 둔다
            if was.get("kind") in _WEEK_REASON_KINDS:
                kind = was["kind"]
        mon[str(w)] = {"kind": kind, "text": body, "at": now}
        n_set += 1
    if not mon:
        store.pop(str(month), None)
    return n_set

# ============================================================
#  파워박스 계획 엑셀
# ============================================================
def _pbx_diff(proj, parsed):
    import pbx_plan_import as _pbx

    models = proj.get("models") or []
    matcher = _pbx.Matcher(models)
    month = parsed["month"]
    weeks = parsed["weeks"]
    rows, missing, seen = [], [], {}

    for r in parsed["rows"]:
        m, how = matcher.match(r["label"])
        if m is None:
            missing.append({"label": r["label"], "reason": how, "row": r["row"]})
            continue
        cur = (m.get("weekly_plan") or {}).get(month) or {}
        cells, changed = [], 0
        for w in weeks:
            new = r["weeks"].get(w) or {}
            old = cur.get(w) or {}
            op, oa = _as_int(old.get("plan")), _as_int(old.get("actual"))
            np_, na = _as_int(new.get("plan")), _as_int(new.get("actual"))
            if (op, oa) != (np_, na):
                changed += 1
            cells.append({"week": w,
                          "old": {"plan": op, "actual": oa},
                          "new": {"plan": np_, "actual": na}})
        entry = {"label": r["label"], "row": r["row"],
                 "model_id": m.get("id"), "model_name": m.get("name"),
                 "group": m.get("group"), "how": how,
                 "changed": changed, "cells": cells}
        # 같은 모델이 시트에 두 줄 이상이면 뒤 줄이 앞 줄을 덮는다. 양쪽 다 표시한다.
        mid = str(m.get("id") or m.get("name"))
        if mid in seen:
            seen[mid]["duplicate"] = True
            entry["duplicate"] = True
        seen[mid] = entry
        rows.append(entry)

    # 합계는 시트의 TOTAL 열을 믿지 않고 주차 값을 더해서 만든다.
    # 실제 파일에서 그 열 수식이 깨져 계획이 400 대신 333 으로 나왔다.
    total_plan = 0
    total_actual = 0
    for _row in rows:                 # 모델 한 줄씩
        for _cell in _row["cells"]:   # 그 줄의 주차 칸
            total_plan += _cell["new"]["plan"]
            total_actual += _cell["new"]["actual"]

    return {
        "month": month,
        "weeks": weeks,
        "sheet": parsed.get("sheet"),
        "rows": rows,
        "unmatched": missing,
        "totals": {
            "plan": total_plan,
            "actual": total_actual,
        },
    }


# 읽어온 주차 행을 모델에 넣는다 → {'month','applied','unmatched'}.
def _pbx_apply_rows(proj: dict, parsed: dict) -> dict:
    diff = _pbx_diff(proj, parsed)
    by_id = {}
    for m in proj.get("models") or []:
        by_id[str(m.get("id") or m.get("name"))] = m

    mon = diff["month"]
    applied = 0
    for e in diff["rows"]:
        m = by_id.get(str(e["model_id"] or e["model_name"]))
        if m is None:
            continue
        wp_all = m.get("weekly_plan")
        if not isinstance(wp_all, dict):
            wp_all = {}
            m["weekly_plan"] = wp_all
        bucket = wp_all.setdefault(mon, {})
        for c in e["cells"]:
            bucket[c["week"]] = {"plan": c["new"]["plan"], "actual": c["new"]["actual"]}
        try:
            m["weekly_progress"] = _ensure_mass_progress(wp_all, mon)
        except Exception:
            pass
        applied += 1
    return {"month": mon, "weeks": diff["weeks"], "applied": applied,
            "unmatched": [u["label"] for u in diff["unmatched"]]}


# 시트 하나에 딸린 주차표를 달별로 반영한다
def _pbx_apply_sheet_months(proj: dict, ws) -> list:
    import pbx_plan_import as _pbx

    out = []
    try:
        got = _pbx.parse_sheet_all(ws)
    except Exception as _e:
        print(f"[plan-in-file] 주차표 읽기 실패(무시): {_e}")
        return out
    for parsed in got:
        if not parsed.get("rows"):
            continue
        try:
            out.append(_pbx_apply_rows(proj, parsed))
        except Exception as _e:
            print(f"[plan-in-file] {parsed.get('month')} 반영 실패(무시): {_e}")
    return out


# 업로드된 엑셀을 연다 → (원본 파일명, 워크북)
async def _pbx_open_upload(file, where: str = "주차별 계획 엑셀",
                           project: str = ""):
    orig = file.filename or "plan.xlsx"
    if not orig.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="xlsx/xlsm 파일만 올릴 수 있습니다")
    raw = await _keep_upload(file, where, project)
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일입니다")

    from io import BytesIO
    import openpyxl

    try:
        wb = openpyxl.load_workbook(BytesIO(raw), data_only=True, keep_links=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"엑셀을 열 수 없습니다: {e}")
    return orig, wb


# 주차표가 있는 시트를 고른다. 못 고르면 이유를 말하고 멈춘다
def _pbx_pick_sheet(wb, month):
    import pbx_plan_import as _pbx

    available = _pbx.sheet_months(wb)
    parsed = _pbx.parse(wb, (month or "").strip() or None)
    if not parsed:
        if available:
            raise HTTPException(
                status_code=400,
                detail="그 달 시트를 찾지 못했습니다. 이 파일에 있는 달: "
                       + ", ".join(g["month"] for g in available))
        raise HTTPException(
            status_code=400,
            detail="주차(W36 같은) 머리글이 있는 시트를 찾지 못했습니다")
    parsed["available"] = available
    return parsed


# 파일에 든 달을 전부 읽는다 → [parsed, ...].
def _pbx_pick_months(wb, month):
    import pbx_plan_import as _pbx

    available = _pbx.sheet_months(wb)
    if not available:
        _pbx_pick_sheet(wb, month)          # 여기서 멈춘다 (멈추지 않으면 아래로)
        raise HTTPException(status_code=400,
                            detail="주차 숫자가 적힌 시트를 찾지 못했습니다")

    order, seen = [], set()
    for g in available:
        if g["month"] in seen:
            continue
        seen.add(g["month"])
        order.append(g["month"])
    want = (month or "").strip()
    if want in seen:
        order = [want] + [m for m in order if m != want]

    out = []
    for mo in order:
        got = _pbx.parse(wb, mo)
        if got:
            got["available"] = available
            out.append(got)
    if not out:
        raise HTTPException(status_code=400,
                            detail="주차 숫자가 적힌 시트를 찾지 못했습니다")
    return out


# 열기 + 시트 고르기를 한 번에 (반영 단계에서 쓴다)
async def _pbx_read_upload(file, month):
    orig, wb = await _pbx_open_upload(file)
    return orig, _pbx_pick_sheet(wb, month)

# ============================================================
#  자동차 — 계약 · 제품 가져오기
# ============================================================
# 자동차사업부 제품 요약 — 앱 화면이 그리는 값 ← 앱 automotive_service.dart project()
@app.get("/projects/{project_key}/automotive-summary")
def get_automotive_summary(project_key: str):
    key = _model_key_alias(project_key.strip())
    proj = (_load_models().get("projects") or {}).get(key) or {}

    COST = ["material", "process", "admin", "depr", "logi"]
    products, years = [], set()
    for m in proj.get("models") or []:
        if not isinstance(m, dict):
            continue
        a = m.get("auto")
        if not isinstance(a, dict) or not a:
            continue
        parts = {k: _as_money((a.get("cost") or {}).get(k)) for k in COST}
        price = sum(parts.values())
        cost = price - parts.get("admin", 0.0)
        quote = _as_money(a.get("price_krw")) or (
            _as_money(a.get("price_fx")) * _as_money(a.get("fx_rate")))
        contract = {}
        for y, cell in (a.get("contract") or {}).items():
            y = str(y)
            years.add(y)
            contract[y] = {"qty": _as_int((cell or {}).get("qty")),
                           "revenue": round(_as_money((cell or {}).get("revenue")), 4)}
        qty = sum(c["qty"] for c in contract.values())
        rev = sum(c["revenue"] for c in contract.values())
        products.append({
            "id": m.get("id"), "name": m.get("name") or m.get("id"),
            "group": m.get("group") or "양산",
            "end_customer": a.get("end_customer") or "",
            "car_model": a.get("car_model") or "",
            "site": a.get("site") or "", "method": a.get("method") or "",
            "sop": a.get("sop") or "",
            "weight_kg": _as_money(a.get("weight_kg")),
            "tonnage": _as_int(a.get("tonnage")),
            "defect_rate": _as_money(a.get("defect_rate")),
            "price": round(price),
            "cost": round(cost),
            "cost_ratio": round(cost / price, 4) if price > 0 else None,
            "parts": {k: round(v) for k, v in parts.items()},
            "quote": round(quote),
            "quote_fx": _as_money(a.get("price_fx")) or None,
            "quote_rate": _as_money(a.get("fx_rate")) or None,
            "contract": contract,
            "qty_total": qty, "revenue_total": round(rev, 4),
        })

    # 묶음 원가율 — 물량으로 가중한다
    wc = sum(p["cost"] * p["qty_total"] for p in products)
    wp = sum(p["price"] * p["qty_total"] for p in products)

    # 매출 큰 제품부터, 같으면 이름순
    def _by_revenue_then_name(p):
        return (-p["revenue_total"], p["name"])
    products.sort(key=_by_revenue_then_name)
    ylist = sorted(years)
    by_year = {y: {"qty": sum(p["contract"].get(y, {}).get("qty", 0) for p in products),
                   "revenue": round(sum(p["contract"].get(y, {}).get("revenue", 0)
                                        for p in products), 4)}
               for y in ylist}
    return {
        "project_key": key,
        "label": _display_project_label(key),
        "years": ylist,
        "products": products,
        "by_year": by_year,
        "totals": {
            "products": len(products),
            "mass": sum(1 for p in products if p["group"] != "개발"),
            "dev": sum(1 for p in products if p["group"] == "개발"),
            "qty": sum(p["qty_total"] for p in products),
            "revenue": round(sum(p["revenue_total"] for p in products), 4),
            "cost_ratio": round(wc / wp, 4) if wp > 0 else None,
            # 사업부 합계에서 다시 가중하려면 분자·분모가 필요하다
            "cost_weighted": round(wc),
            "price_weighted": round(wp),
        },
    }


# 자동차사업부 전체 요약 — 앱 '고객사 목록' 화면이 그리는 값 ← admin v2 back.onclick() · 앱 automotive_service.dart division()
@app.get("/divisions/automotive/summary")
def get_automotive_division_summary(year: int = 0):
    import datetime as _dt

    cur = int(year) if year else _dt.date.today().year
    rows, years = [], set()
    for p in _auto_projects():
        s = get_automotive_summary(p["id"])
        t = s.get("totals") or {}
        by = s.get("by_year") or {}
        years.update(s.get("years") or [])
        cell = by.get(str(cur)) or {}
        rows.append({
            # 앱은 프로젝트 id 로 화면을 연다. 별칭이 걸린 키를 돌려주면 못 찾는다.
            "key": p["id"],
            "model_key": s.get("project_key") or p["id"],
            "label": p.get("label") or s.get("label"),
            "products": t.get("products", 0),
            "mass": t.get("mass", 0),
            "dev": t.get("dev", 0),
            "qty": t.get("qty", 0),
            "revenue": t.get("revenue", 0),
            "year_qty": _as_int(cell.get("qty")),
            "year_revenue": round(_as_money(cell.get("revenue")), 4),
            "cost_ratio": t.get("cost_ratio"),
            "_wc": _as_money(t.get("cost_weighted")),
            "_wp": _as_money(t.get("price_weighted")),
            "by_year": by,
        })

    total_rev = round(sum(r["revenue"] for r in rows), 4)
    for r in rows:
        # 막대 길이로 쓴다. 전체가 0이면 0 — 앱에서 0 으로 나누지 않게 여기서 막는다.
        r["share"] = round(r["revenue"] / total_rev, 4) if total_rev > 0 else 0.0

    # 계약이 잡힌 고객사가 위로. 같으면 이름순 — 순서가 매번 바뀌면 못 읽는다.
    def _by_revenue_then_label(r):
        return (-r["revenue"], r["label"])
    rows.sort(key=_by_revenue_then_label)

    ylist = sorted(years)
    by_year = {
        y: {
            "qty": sum(_as_int((r["by_year"].get(y) or {}).get("qty")) for r in rows),
            "revenue": round(sum(_as_money((r["by_year"].get(y) or {}).get("revenue"))
                                 for r in rows), 4),
        }
        for y in ylist
    }
    wc = sum(r.pop("_wc", 0) for r in rows)
    wp = sum(r.pop("_wp", 0) for r in rows)
    for r in rows:
        r.pop("by_year", None)

    return {
        "division_id": "automotive",
        "year": cur,
        "years": ylist,
        "projects": rows,
        "by_year": by_year,
        "totals": {
            "projects": len(rows),
            "with_contract": sum(1 for r in rows if r["revenue"] > 0),
            "products": sum(r["products"] for r in rows),
            "qty": sum(r["qty"] for r in rows),
            "revenue": total_rev,
            "year_qty": sum(r["year_qty"] for r in rows),
            "year_revenue": round(sum(r["year_revenue"] for r in rows), 4),
            "cost_ratio": round(wc / wp, 4) if wp > 0 else None,
        },
    }


# ============================================================
#  자동차사업부 제품 엑셀
# ============================================================
# 한 파일에 여러 고객사가 섞여 있다


# 자동차사업부 프로젝트 (라벨·별칭까지) — 고객사 이름을 여기에 맞춘다
def _auto_projects():
    out = []
    try:
        for p in _cl.get_projects(division_id="automotive", visible_only=True):
            out.append({"id": p.get("id"), "label": p.get("label"),
                        "aliases": list(p.get("aliases") or [])})
    except Exception as e:
        print(f"[auto-import] 프로젝트 목록 조회 실패: {e}")
    return out


# 업로드된 엑셀을 열어 제품표를 읽는다 → (파일명, parsed, 시트목록)
async def _auto_read_upload(file, sheet):
    orig = file.filename or "products.xlsx"
    if not orig.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="xlsx/xlsm 파일만 올릴 수 있습니다")
    raw = await _keep_upload(file, "/admin/automotive/product-import", "automotive")
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일입니다")

    from io import BytesIO
    import openpyxl
    import auto_import as _ai

    try:
        wbv = openpyxl.load_workbook(BytesIO(raw), data_only=True, keep_links=False)
        wbf = openpyxl.load_workbook(BytesIO(raw), keep_links=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"엑셀을 열 수 없습니다: {e}")

    avail = _ai.sheets(wbv, wbf)
    parsed = _ai.parse(wbv, wbf, (sheet or "").strip() or None)
    if not parsed:
        if avail:
            raise HTTPException(status_code=400, detail="그 시트를 찾지 못했습니다. 읽히는 시트: "
                                                        + ", ".join(g["sheet"] for g in avail))
        raise HTTPException(status_code=400,
                            detail="'고객사'와 '제품명' 머리글이 있는 시트를 찾지 못했습니다")
    return orig, parsed, avail


# 엑셀 행 ↔ 등록된 제품 대조표.
def _auto_diff(parsed):
    import auto_import as _ai

    projects = _auto_projects()
    label = {p["id"]: p["label"] for p in projects}
    # 엑셀 표기가 등록과 다를 수 있다 ('스탈란티스' vs '스텔란티스').
    # 화면에도 저장에도 등록된 표기로 나간다.
    names = _ai.name_labels(projects)
    pmap = _ai.match_projects(parsed["rows"], projects)
    data = _load_models()

    rows, missing = [], []
    for r in parsed["rows"]:
        pid = pmap.get(r["customer"])
        if not pid:
            missing.append({"customer": r["customer"], "product": r["product"], "row": r["row"]})
            continue
        proj = (data.get("projects") or {}).get(pid) or {}
        cur = None
        for m in proj.get("models") or []:
            if str(m.get("id")) == r["product"] or str(m.get("name")) == r["product"]:
                cur = m
                break
        a = r["auto"]
        parts = a.get("cost") or {}
        # 판가 = 다섯 항목 합계. 엑셀 '판가' 열은 외화 견적이라 따로 둔다.
        price = sum(_as_money(v) for v in parts.values())
        quote = _as_money(a.get("price_krw")) or (
            _as_money(a.get("price_fx")) * _as_money(a.get("fx_rate")))
        rows.append({
            "row": r["row"], "customer": r["customer"],
            "customer_label": label.get(pid, r["customer"]),
            "project_key": pid, "project_label": label.get(pid, pid),
            "product": r["product"], "group": r["group"],
            "is_new": cur is None,
            "price": round(price),
            "quote": round(quote),
            "qty": sum(_as_int(v.get("qty")) for v in (a.get("contract") or {}).values()),
            "revenue": round(sum(_as_money(v.get("revenue"))
                                 for v in (a.get("contract") or {}).values()), 1),
            "end_customer": _ai.canonical(a.get("end_customer", ""), names),
            "sop": a.get("sop", ""),
            # 엑셀이 적어 둔 합계와 우리가 모은 다섯 덩어리가 어긋난 금액.
            # 시트마다 원가 열이 달라서 한 칸을 놓쳐도 숫자는 그럴듯하게 나온다.
            "total_gap": r.get("total_gap"),
        })

    return {"sheet": parsed["sheet"], "years": parsed["years"],
            "rows": rows, "unmatched": missing,
            "projects": sorted({r["project_label"] for r in rows})}


# 올린 파일이 무엇을 어디로 넣는지 먼저 보여준다 ← admin v2 aiFile.onchange()
@app.post("/admin/automotive/product-import/preview")
async def admin_auto_import_preview(
    file: UploadFile = File(...),
    sheet: str = Form(""),
    _admin: int = Depends(get_admin_session),
):
    _form_only("auto-product")
    orig, parsed, avail = await _auto_read_upload(file, sheet)
    out = _auto_diff(parsed)
    out.update({"ok": True, "file_name": orig,
                "available": [g["sheet"] for g in avail]})
    return out


# 미리보기에서 확인한 내용을 저장한다 ← admin v2 onclick()
@app.post("/admin/automotive/product-import/apply")
async def admin_auto_import_apply(
    file: UploadFile = File(...),
    sheet: str = Form(""),
    skip: str = Form(""),
    _admin: int = Depends(get_admin_session),
):
    _form_only("auto-product")
    import auto_import as _ai

    orig, parsed, _avail = await _auto_read_upload(file, sheet)
    projects = _auto_projects()
    pmap = _ai.match_projects(parsed["rows"], projects)
    names = _ai.name_labels(projects)
    drop = {s.strip() for s in (skip or "").split("|") if s.strip()}

    data = _load_models()
    added = updated = 0
    touched = set()
    for r in parsed["rows"]:
        pid = pmap.get(r["customer"])
        if not pid or (r["customer"] + "/" + r["product"]) in drop:
            continue
        proj = data.setdefault("projects", {}).setdefault(pid, {"models": []})
        models = proj.setdefault("models", [])
        cur = None
        for m in models:
            if str(m.get("id")) == r["product"] or str(m.get("name")) == r["product"]:
                cur = m
                break
        if cur is None:
            cur = {"id": r["product"], "name": r["product"], "status": "정상", "progress": 0}
            models.append(cur)
            added += 1
        else:
            updated += 1
        cur["name"] = r["product"]
        cur["group"] = r["group"]
        # auto 묶음은 통째로 갈아끼운다. 엑셀이 이 제품의 정본이다.
        # 최종고객사만 등록 표기로 맞춘다 ('스탈란티스' → '스텔란티스').
        # 기아자동차·CEER 처럼 등록에 없는 회사는 그대로 둔다.
        if r["auto"].get("end_customer"):
            r["auto"]["end_customer"] = _ai.canonical(r["auto"]["end_customer"], names)
        cur["auto"] = r["auto"]
        # 원가율을 다른 화면에서도 쓸 수 있게 판가·재료비 칸에도 원화로 남긴다
        a = r["auto"]
        cur["price"] = round(_as_money(a.get("price_krw")) or
                             (_as_money(a.get("price_fx")) * _as_money(a.get("fx_rate"))))
        cur["material_cost"] = round(_as_money((a.get("cost") or {}).get("material")))
        touched.add(pid)

    for pid in touched:
        proj = data["projects"][pid]
        # 양산을 앞에, 개발을 뒤에 (같은 구분 안에서는 원래 순서 그대로)
        proj["models"].sort(key=lambda m: 0 if m.get("group") == "양산" else 1)
        proj["product_file"] = {
            "file_name": orig, "sheet": parsed["sheet"],
            "uploaded_at": datetime.now().isoformat(),
        }
    _save_models(data)
    print(f"[auto-import] '{orig}' {parsed['sheet']}: 신규 {added}, 갱신 {updated}, "
          f"프로젝트 {len(touched)}개, 건너뜀 {len(drop)}")
    return {"ok": True, "file_name": orig, "sheet": parsed["sheet"],
            "added": added, "updated": updated,
            "projects": sorted(touched), "skipped": len(drop)}

# ============================================================
#  모델 별칭
# ============================================================
# '이 품번도 그 모델이다' 를 적어 둔다 ← admin v2 back.onclick()
@app.post("/admin/projects/{project_key}/models/alias")
def admin_add_model_alias(project_key: str,
                          model_id: str = Form(...),
                          alias: str = Form(...),
                          _admin: int = Depends(get_admin_session)):
    key = _model_key_alias((project_key or "").strip())
    want = str(alias or "").strip()
    mid = str(model_id or "").strip()
    if not want or not mid:
        raise HTTPException(status_code=400, detail="품번과 모델을 지정해 주세요.")

    data = _load_models()
    proj = (data.get("projects") or {}).get(key)
    if not proj:
        raise HTTPException(status_code=404, detail="사업부를 찾지 못했습니다.")

    target, taken = None, None
    for m in proj.get("models") or []:
        if not isinstance(m, dict):
            continue
        if str(m.get("id") or "") == mid:
            target = m
        # 이미 등록된 품번을 남의 별칭으로 붙이면 둘 다 그 줄로 끌려간다
        if str(m.get("id") or "").strip() == want or \
                str(m.get("part_number") or "").strip() == want:
            taken = m
    if target is None:
        raise HTTPException(status_code=404, detail="그 모델을 찾지 못했습니다.")
    if taken is not None and taken is not target:
        raise HTTPException(
            status_code=400,
            detail="%s 는 이미 등록된 모델입니다. 별칭 대신 그 줄을 지워 주세요."
                   % want)

    alts = [str(a).strip() for a in (target.get("aliases") or []) if str(a).strip()]
    if want not in alts:
        alts.append(want)
    target["aliases"] = alts
    _save_models(data)
    print(f"[alias] {key} {mid} ← {want}")
    return {"ok": True, "model_id": mid, "aliases": alts}


# 엑셀을 올리는 자리가 스무 곳 넘게 흩어져 있었다
DIVISION_FORM_ONLY = True

#: 닫은 주소 → 사람이 읽을 이름. 사업부 양식이 대신하는 길들이다.
_FORM_REPLACED = {
    "models-import": "모델 등록 양식",
    "plan-file": "주차별 계획 파일",
    "status-excel": "주간 현황 엑셀",
    "auto-product": "자동차 제품 엑셀",
}

# ============================================================
#  올리는 길을 하나로 — 사업부 양식만 받는다
# ============================================================
def _form_only(which: str):
    if not DIVISION_FORM_ONLY:
        return
    what = _FORM_REPLACED.get(which, which)
    raise HTTPException(
        status_code=403,
        detail=("%s 는 이제 따로 올리지 않습니다. "
                "사업부 양식(품목정보·이슈사항) 한 장으로 올려 주세요. "
                "관리자 화면의 '양식 올리기' 에서 올릴 수 있습니다." % what),
    )


# 사업부마다 쓰는 한 벌짜리 양식을 올리면, 그 안의 두 장을 읽어 프로젝트(고객사)별 모델과 이슈로 반영한다

# ============================================================
#  양식의 고객사 · 품번 → 우리 프로젝트 · 모델
# ============================================================
def _df_norm(t) -> str:
    import re as _re
    import unicodedata as _ud
    t = _ud.normalize("NFC", str(t or "")).lower()
    t = _re.sub(r"[\s\-_()\[\].,/]+", "", t)
    return t


# 이름 하나 → 맞춰 볼 열쇠들.
def _df_keys(name) -> list:
    import re as _re
    raw = str(name or "").strip()
    out = []
    for cand in ([raw] + _re.split(r"[()\[\]]+", raw)):
        k = _df_norm(cand)
        if k and k not in out:
            out.append(k)
    return out


# 사업부 안에서 '엑셀에 적힌 이름 → 프로젝트 키' 색인.
def _df_owner_index(division_id: str) -> dict:
    import config_loader as _cl
    idx = {}
    for p in _cl.get_projects(division_id=division_id, visible_only=False):
        pid = p.get("id")
        if not pid:
            continue
        # 열쇠로 쓸 이름들 — 키 자체 · 화면 이름 · 별칭 전부
        names = [pid, p.get("label")]
        names.extend(p.get("aliases") or [])
        # 이름 하나가 열쇠 여럿이다 ('TC (Telemaetry Cabinet)' → tc · telemaetrycabinet).
        # setdefault 라 먼저 들어온 쪽이 이긴다 — 프로젝트 키·화면 이름이
        # 별칭 조각보다 앞이다.
        for n in names:
            for key in _df_keys(n):
                idx.setdefault(key, pid)
    # -----------------------------------------------------------
    # 이미 등록된 모델 이름도 열쇠로 쓴다
    # -----------------------------------------------------------
    # 모델 목록에 'TC (Telemaetry Cabinet)' 이라고 적혀 있으면, 시스템은 이미 TC 가 무엇인지 알고 있는 셈이다
    try:
        data = _load_models()
        projects = data.get("projects") or {}
        owners = {}                      # 열쇠 → {프로젝트 키}
        for p in _cl.get_projects(division_id=division_id, visible_only=False):
            pid = p.get("id")
            for m in ((projects.get(pid) or {}).get("models") or []):
                if not isinstance(m, dict):
                    continue
                for key in _df_keys(m.get("name")):
                    owners.setdefault(key, set()).add(pid)
        for key, pids in owners.items():
            if len(pids) == 1 and key not in idx:
                idx[key] = next(iter(pids))
    except Exception as _e:
        # 색인이 조금 모자란 것보다 반영이 통째로 막히는 게 나쁘다
        print("[양식] 모델 이름 색인 실패(무시) — %s" % _e)

    return idx


# 엑셀에 적힌 이름 → 프로젝트 키로 쓸 영문 토막.
def _df_slug(owner: str) -> str:
    import re as _re
    import unicodedata as _ud
    t = _ud.normalize("NFKD", str(owner or "")).encode("ascii", "ignore").decode()
    t = _re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_").lower()
    t = _re.sub(r"_+", "_", t)[:40]
    if not t:
        import hashlib as _hl
        t = "p" + _hl.md5(str(owner or "").encode("utf-8")).hexdigest()[:6]
    return t


# 못 찾은 줄을 이름으로 묶어 '이런 프로젝트를 만들겠다' 목록을 낸다
def _df_new_project_rows(division_id: str, unmatched: list) -> list:
    by = {}
    for x in (unmatched or []):
        name = str((x or {}).get("owner") or "").strip()
        if not name:
            continue                     # 이름이 비면 만들 수가 없다
        by.setdefault(name, 0)
        by[name] += 1

    taken = {p.get("id") for p in _cl.get_projects(visible_only=False)}
    out = []
    for name in sorted(by, key=lambda n: -by[n]):
        base = "%s_%s" % (_df_slug(division_id), _df_slug(name))
        key, n = base, 2
        while key in taken:              # 같은 키가 이미 있으면 뒤에 번호
            key, n = "%s_%d" % (base, n), n + 1
        taken.add(key)
        out.append({"owner": name, "key": key, "rows": by[name]})
    return out


# ============================================================
#  엑셀에 적힌 이름 → 화면에 띄울 이름
# ============================================================
# 엑셀마다 같은 곳을 다르게 적는다 — 양식은 'FLUENCE', 일 보고는 '플루언스'.
_DISPLAY_NAMES = None


# 그 이름을 화면에 어떻게 띄울까.
def _display_name(raw: str) -> str:
    global _DISPLAY_NAMES
    if _DISPLAY_NAMES is None:
        try:
            p = Path(__file__).parent / "config" / "display_names.json"
            _DISPLAY_NAMES = (json.loads(p.read_text(encoding="utf-8"))
                              .get("names") or {})
        except Exception as e:
            print("[names] 표시 이름 표를 못 읽었습니다: %s" % e)
            _DISPLAY_NAMES = {}
    key = "".join(str(raw or "").lower().split())
    return str(_DISPLAY_NAMES.get(key) or "")


# _df_new_project_rows 가 낸 목록을 실제로 만든다 → 만든 것만 돌려준다
def _df_create_projects(division_id: str, rows: list) -> list:
    made = []
    orders = [int(p.get("order") or 0)
              for p in _cl.get_projects(division_id=division_id, visible_only=False)]
    nxt = (max(orders) if orders else 0) + 1
    for r in (rows or []):
        # 화면 이름만 바꾼다. 엑셀 원문은 별칭으로 남는다 —
        # 다음 달에 영문으로 와도 같은 프로젝트를 찾아야 한다.
        _disp = _display_name(r["owner"]) or r["owner"]
        _names = [r["owner"]] + ([_disp] if _disp != r["owner"] else [])
        row = {
            "id": r["key"],
            "division_id": division_id,
            "label": _disp,
            "badge_label": _disp,
            # 다음에 같은 이름이 와도 이 프로젝트로 붙게 별칭을 달아 둔다
            "aliases": _names,
            "keywords": _names,
            "visible": True,
            "order": nxt,
            # 손으로 만든 것과 가르는 표시. 나중에 정리할 때 이것만 보면 된다.
            "created_by": "division_form",
            "created_at": date.today().isoformat(),
        }
        # -----------------------------------------------------------
        # 일 보고 사업부면 '품목 이름' 도 적어 둔다
        # -----------------------------------------------------------
        # 블룸은 일 보고 엑셀 한 장이 품목을 다 싣고 와서 bloom_main 에 담긴다
        if _daily_store_key(division_id) and \
                _dcol.shape_of(division_id) == "프로젝트형":
            row["bloom_item"] = r["owner"]
        nxt += 1
        try:
            _cl.add_project(row)
            made.append(row)
        except Exception as e:
            print("[form] 프로젝트 만들기 실패 %s: %s" % (r["key"], e))
    return made


# 양식에 없는 프로젝트는 끈다. 다시 적히면 켠다
def _df_project_sync(division_id: str, items: list, idx: dict,
                     dry: bool = False) -> dict:
    out = {"hidden": [], "shown": []}
    if not items:
        return out
    # 반도체형은 한 장이 프로젝트 하나다 — 여기서 돌리면 남은 것이 다 꺼진다
    if _dcol.shape_of(division_id) == "반도체형":
        return out

    alive = set()
    for it in items:
        pid = _df_find_project(it.get("owner"), idx)
        if pid:
            alive.add(pid)
    if not alive:
        return out

    store = _daily_store_key(division_id) or ""
    for p in _cl.get_projects(division_id=division_id, visible_only=False):
        pid = p.get("id")
        if not pid or pid == store:
            continue
        if not _cl.is_runtime_project(pid):
            continue
        want = pid in alive
        if bool(p.get("visible", True)) == want:
            continue
        if dry:
            (out["shown"] if want else out["hidden"]).append(
                {"key": pid, "label": p.get("label") or pid})
            continue
        try:
            if _cl.set_project_visible(pid, want, "division_form"):
                (out["shown"] if want else out["hidden"]).append(
                    {"key": pid, "label": p.get("label") or pid})
        except Exception as _e:
            print("[양식] 프로젝트 켜고 끄기 실패 %s — %s" % (pid, _e))
    return out

# ============================================================
#  판가 바뀜 · 주차 꼬리표
# ============================================================
def _df_price_preview(items, idx, tag: str) -> list:
    def _money(v):
        try:
            return max(0, _as_money(v))
        except Exception:
            return 0

    data = _load_models()
    out = []
    for it in (items or []):
        if it.get("price") is None and it.get("material_cost") is None:
            continue
        pid = _df_find_project(it.get("owner"), idx)
        if not pid:
            continue
        proj = (data.get("projects") or {}).get(pid) or {}
        m = _df_pick_model(proj.get("models") or [],
                           it.get("part_number"), it.get("name"))
        if m is None:                 # 새 모델은 '바뀐' 것이 아니다
            continue
        old_p, old_c = _money(m.get("price")), _money(m.get("material_cost"))
        new_p = _money(it.get("price")) if it.get("price") is not None else old_p
        new_c = (_money(it.get("material_cost"))
                 if it.get("material_cost") is not None else old_c)
        if abs(new_p - old_p) < 0.005 and abs(new_c - old_c) < 0.005:
            continue
        out.append({"project_key": pid, "id": m.get("id"),
                    "name": m.get("name") or m.get("id"),
                    "from": tag, "price": [old_p, new_p],
                    "material_cost": [old_c, new_c]})
    return out


# 양식의 기준 주차 → 판가 구간 시작점 ('2026-W43').
def _df_week_tag(month: str, week) -> str:
    o = _week_ord(month, week)
    # 주차가 빈 칸이면 _week_ord 가 '0주차'(202600)를 돌려준다
    if not o or not (1 <= o % 100 <= 53):
        return ""
    return "%04d-W%02d" % (o // 100, o % 100)


# 양식으로 판가·재료비가 바뀌면 **그 주차부터** 새 값.
def _df_apply_price(m: dict, it: dict, tag: str) -> dict:
    def _money(v):
        try:
            return max(0, _as_money(v))
        except Exception:
            return 0

    has_p = it.get("price") is not None
    has_c = it.get("material_cost") is not None
    if not (has_p or has_c):
        return {}

    old_p, old_c = _money(m.get("price")), _money(m.get("material_cost"))
    new_p = _money(it.get("price")) if has_p else old_p
    new_c = _money(it.get("material_cost")) if has_c else old_c

    # 값만 갈아 끼우고 끝 — 바뀐 게 없으면 구간을 늘리지 않는다
    if abs(new_p - old_p) < 0.005 and abs(new_c - old_c) < 0.005:
        if has_p:
            m["price"] = it["price"]
        if has_c:
            m["material_cost"] = it["material_cost"]
        return {}

    ph = _norm_phases(m.get("phases"))
    if not ph:
        # 구간이 없던 모델: 옛 값을 '처음부터' 구간으로 박아 과거를 고정한다.
        # 구분은 **저장된 group** 을 쓴다 — 개발이던 시절은 개발로 남아야
        # 지난달 개발 실적이 양산 판가로 다시 계산되지 않는다.
        ph = [{"from": _PHASE_EPOCH,
               "group": "개발" if m.get("group") == "개발" else "양산",
               "price": old_p, "material_cost": old_c}]
    _prev = ph[-1]
    grp = _prev.get("group") or ("개발" if m.get("group") == "개발" else "양산")

    same = next((e for e in ph if e["from"] == tag), None)
    if same is not None:
        # 같은 주차 양식을 두 번 올려도 구간이 늘지 않는다
        same["price"] = new_p
        same["material_cost"] = new_c
    else:
        ph.append({"from": tag, "group": grp,
                   "price": new_p, "material_cost": new_c})
    m["phases"] = _norm_phases(ph)

    if has_p:
        m["price"] = it["price"]
    if has_c:
        m["material_cost"] = it["material_cost"]
    return {"id": m.get("id"), "name": m.get("name") or m.get("id"),
            "from": tag, "price": [old_p, new_p],
            "material_cost": [old_c, new_c]}


# ==== 고객사 이름의 오타를 가장 가까운 한 곳에 붙인다
_DF_TYPO_MIN_LEN = 6

# ============================================================
#  고객사 이름 오타 맞추기
# ============================================================
def _df_digits(t: str) -> list:
    import re as _re
    return _re.findall(r"\d+", str(t or ""))


# 글자 차이가 1 이내인가 (자리바꿈 포함).
def _df_dam1(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diff) == 1:
            return True                      # 한 글자만 다르다
        if len(diff) == 2 and diff[1] == diff[0] + 1 \
                and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]:
            return True                      # 붙어 있는 두 글자가 뒤바뀌었다
        return False
    lo, hi = (a, b) if len(a) < len(b) else (b, a)
    for i in range(len(hi)):                 # 한 글자를 빼면 같아지는가
        if hi[:i] + hi[i + 1:] == lo:
            return True
    return False


# 오타로 보이는 이름 → 프로젝트 키.
def _df_typo_project(owner: str, idx: dict) -> str:
    hits = set()
    for cand in _df_keys(owner):
        if len(cand) < _DF_TYPO_MIN_LEN:
            continue
        cd = _df_digits(cand)
        for key, pid in idx.items():
            if len(key) < _DF_TYPO_MIN_LEN or key == cand:
                continue
            if _df_digits(key) != cd:
                continue
            if _df_dam1(cand, key):
                hits.add(pid)
                if len(hits) > 1:
                    return ""            # 둘 이상이면 안 붙인다
    return next(iter(hits)) if len(hits) == 1 else ""


# 엑셀에 적힌 이름이 어느 프로젝트인가.
def _df_find_project(owner: str, idx: dict, notes: dict | None = None) -> str:
    cands = _df_keys(owner)
    if not cands:
        return ""
    # -----------------------------------------------------------
    # 1. 똑같은 이름 (괄호 앞·안 조각까지)
    # -----------------------------------------------------------
    #    'TC' 도 'TC (Telemaetry Cabinet)' 도 여기서 걸린다.
    for key in cands:
        if key in idx:
            return idx[key]
    # -----------------------------------------------------------
    # 2. 한쪽이 다른 쪽을 품고 있는가
    # -----------------------------------------------------------
    #    'SDI(인디애나)' 처럼 뒤에 뭐가 붙어 와도 찾히게 한다.
    #    너무 짧은 글자는 아무 데나 걸리므로 세 자 이상일 때만 본다.
    for key in cands:
        if len(key) < 3:
            continue
        for k, pid in idx.items():
            if len(k) >= 3 and (key.startswith(k) or k.startswith(key)):
                return pid
    # -----------------------------------------------------------
    # 3. 오타로 보이는가 (_df_typo_project 주석 참고)
    # -----------------------------------------------------------
    pid = _df_typo_project(owner, idx)
    if pid:
        if notes is not None:
            notes[str(owner or "").strip()] = pid
        return pid
    return ""


# 모델을 가리키는 열쇠 — (품번, 이름) 둘 다 다듬어서.
def _df_model_key(m) -> tuple:
    return (_df_norm(m.get("part_number") or m.get("id")),
            _df_norm(m.get("name")))


# 이미 등록된 모델 중에서 이 줄에 해당하는 것을 찾는다
def _df_pick_model(models: list, pn: str, name: str):
    want_pn = _df_norm(pn)
    want_name = _df_norm(name)

    if want_pn:
        for m in models:
            if _df_norm(m.get("part_number")) == want_pn:
                return m
            if _df_norm(m.get("id")) == want_pn:
                return m

    if want_name:
        for m in models:
            if _df_norm(m.get("name")) == want_name:
                return m
    return None


# 오타로 붙인 이름을 사람이 읽을 줄로.
def _df_typo_warnings(notes: dict) -> list:
    out = []
    for owner, pid in sorted((notes or {}).items()):
        try:
            lbl = (_cl.get_project(pid) or {}).get("label") or pid
        except Exception:
            lbl = pid
        out.append("'%s' 는 '%s' 의 오타로 보여 그 프로젝트에 붙였습니다 "
                   "— 다른 곳이면 알려 주세요 (%s)" % (owner, lbl, pid))
    return out

# ============================================================
#  무엇이 새로 들어오고 무엇이 바뀌나
# ============================================================
def _df_plan(items, idx, notes: dict | None = None) -> dict:
    data = _load_models()
    plan = {}          # {프로젝트키: {"new": [...], "update": [...]}}
    unmatched = []     # 어느 프로젝트인지 못 찾은 줄
    seen = {}          # {프로젝트키: {양식이 건드린 모델의 자리}}

    for it in items:
        pid = _df_find_project(it.get("owner"), idx, notes)
        if not pid:
            unmatched.append(it)
            continue

        proj = (data.get("projects") or {}).get(pid) or {}
        models = proj.get("models") or []
        found = _df_pick_model(models, it.get("part_number"), it.get("name"))

        bucket = plan.setdefault(pid, {"new": [], "update": []})
        if found is None:
            bucket["new"].append(it)
        else:
            bucket["update"].append(it)
            # 양식이 건드린 기존 모델. 여기 없는 모델이 '양식에서 지운 줄'
            # 이다. 이름이 아니라 그 자리(파이썬 id)로 센다 — 같은 이름이
            # 둘일 때 이름으로 맞추면 엉뚱한 것이 남는다.
            seen.setdefault(pid, set()).add(id(found))

    return {"plan": plan, "unmatched": unmatched,
            "stale": _df_stale_models(data, seen)}

# ============================================================
#  이슈 진행 / 해결
# ============================================================
def _df_issue_apply(data: dict, pid: str, ix: dict, file: str = "",
                    dry: bool = False) -> str:
    import datetime as _dt
    today = _dt.date.today().isoformat()
    projects = data.get("projects") or {}
    proj = projects.get(pid)
    if proj is None:
        if dry:
            proj = {"models": []}
        else:
            proj = data.setdefault("projects", {}).setdefault(pid, {"models": []})
    pn = (ix.get("part_number") or "").strip()
    m = _df_pick_model(proj.get("models") or [], pn, "") if pn else None
    if m is not None:
        return _iss.apply_to_model(m, ix, today, file, dry=dry)
    return _iss.apply_to_project(proj, ix, today, file, dry=dry)


# 사업부 양식의 주차 계획이 보드에 안 뜨는 사업부면 한 줄 알려 준다
def _form_weekly_note(division_id: str, weeks) -> str:
    if str(division_id or "").strip().lower() not in _DAILY_BOARD_ROWS:
        return ""
    if not weeks:
        return ""
    return ("이 사업부의 주차 현황 보드는 일 보고 자료로 그립니다. "
            "양식에 적은 주차별 계획(%s)은 저장은 되지만 보드에는 "
            "안 뜹니다 — 주차 숫자는 일 보고 엑셀로 올려 주세요."
            % " · ".join(str(w) for w in weeks))


# 양식에 한 번도 안 나온 기존 모델 → [{project_key, id, name}]
def _df_stale_models(data: dict, seen: dict) -> list:
    out = []
    for pid, touched in seen.items():
        proj = (data.get("projects") or {}).get(pid) or {}
        for m in (proj.get("models") or []):
            if not isinstance(m, dict) or id(m) in touched:
                continue
            out.append({"project_key": pid,
                        "id": str(m.get("id") or ""),
                        "name": str(m.get("name") or m.get("id") or "")})
    return out

# ============================================================
#  양식 내려받기 · 미리보기 · 반영
# ============================================================
# 그 사업부 양식을, **지금 등록된 내용을 채워서** 내려준다 ← admin v2 fd.onclick()
@app.get("/admin/divisions/{division_id}/form/download")
def admin_division_form_download(
    division_id: str,
    month: str = "",
    months: int = 2,
    _admin: int = Depends(get_admin_session),
):
    import datetime as _dt
    from urllib.parse import quote
    import division_form_export as _dfe

    base = (month or "").strip() or _dt.date.today().strftime("%Y-%m")
    if not _MONTH_RE.match(base):
        raise HTTPException(status_code=400, detail="달을 YYYY-MM 으로 적어 주세요.")
    n = max(1, min(int(months or 2), 6))
    # -----------------------------------------------------------
    # 그 사업부의 모든 프로젝트에서 모델을 모은다
    # -----------------------------------------------------------
    #    양식 한 장이 사업부 하나다 — 올릴 때도 그렇게 받는다.
    data = _load_models()
    projects = (data.get("projects") or {})
    rows = []
    open_issues = []        # 지금 열린 이슈 — 양식 [이슈사항] 에 '진행' 으로 채운다
    for p in _cl.get_projects(division_id=division_id, visible_only=False):
        pid = p.get("id")
        owner = p.get("label") or pid
        # 양식에는 국내 / 해외 둘 중 하나만 (해외의 Lam · 아리스타 · 기타는 서버가 가른다)
        # 자동차는 '고객 묶음' 이름 그대로 (_dcol.group_cell)
        _rg = _dcol.group_cell(division_id, _dcol.customer_group(
            division_id, pid, (projects.get(pid) or {}).get("customer_group"), owner))
        for m in ((projects.get(pid) or {}).get("models") or []):
            if not isinstance(m, dict):
                continue
            r = dict(m)
            r["owner"] = owner
            r.setdefault("part_number", m.get("id") or "")
            r["region"] = _rg            # 국내/해외 칸 (묶는 사업부만 그려진다)
            rows.append(r)
        try:
            open_issues.extend(_iss.open_rows(owner, projects.get(pid) or {}))
        except Exception as _e:
            print("[양식 내려받기] 이슈 채우기 건너뜀 — %s" % _e)

    try:
        # 용어는 등록된 것을 채워 준다 — 이 시트는 올릴 때마다 통째로 바뀐다
        try:
            _terms = _dterm.get(division_id)
        except Exception:
            _terms = []
        blob = _dfe.build(division_id, rows, base, n, terms=_terms,
                          issues=open_issues)
    except Exception as e:
        raise HTTPException(status_code=500, detail="양식을 만들지 못했습니다: %s" % e)

    label = division_id
    try:
        d = _cl.get_division(division_id) or {}
        label = d.get("label") or division_id
    except Exception:
        pass
    fname = "%s 양식_%s.xlsx" % (label, base)
    print("[양식 내려받기] %s · 품목 %d · %s 부터 %d달"
          % (division_id, len(rows), base, n))
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 "attachment; filename=division_form.xlsx; "
                 "filename*=UTF-8''%s" % quote(fname)})


# 개발 일정 양식을, **적혀 있던 날짜를 채워서** 내려준다 ← admin v2 fv.onclick()
@app.get("/admin/divisions/{division_id}/dev-schedule/download")
def admin_dev_schedule_download(
    division_id: str,
    _admin: int = Depends(get_admin_session),
):
    from urllib.parse import quote
    import dev_schedule_export as _dse

    data = _load_models()
    projects = (data.get("projects") or {})
    rows = []
    for p in _cl.get_projects(division_id=division_id, visible_only=False):
        pid = p.get("id")
        owner = p.get("label") or pid
        for m in ((projects.get(pid) or {}).get("models") or []):
            if not isinstance(m, dict):
                continue
            if _display_group(m) != "개발":
                continue
            rows.append({
                "owner": owner,
                "name": m.get("name") or m.get("id") or "",
                "part_number": m.get("part_number") or m.get("id") or "",
                "dev_owner": m.get("dev_owner") or "",
                "process": m.get("process") or [],
            })
    if not rows:
        raise HTTPException(status_code=404,
                            detail="이 사업부에는 구분이 '개발'인 품목이 없습니다.")

    label = division_id
    try:
        label = (_cl.get_division(division_id) or {}).get("label") or division_id
    except Exception:
        pass
    try:
        blob = _dse.build(label, rows, [n for _k, n, _g in DEV_PROCESS_STEPS])
    except Exception as e:
        raise HTTPException(status_code=500, detail="양식을 만들지 못했습니다: %s" % e)

    fname = "%s 품목별 개발 일정.xlsx" % label
    print("[개발일정 양식] %s · 개발 품목 %d" % (division_id, len(rows)))
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument."
                   "spreadsheetml.sheet",
        headers={"Content-Disposition":
                 "attachment; filename=dev_schedule.xlsx; "
                 "filename*=UTF-8''%s" % quote(fname)})


# 올린 양식이 무엇을 바꾸는지 먼저 보여준다 ← admin v2 fd.onclick() · _divFormSend()
@app.post("/admin/divisions/{division_id}/form/preview")
async def admin_division_form_preview(
    division_id: str,
    file: UploadFile = File(...),
    _admin: int = Depends(get_admin_session),
):
    import io as _io
    import openpyxl as _ox
    import division_form_import as _dfi

    raw = await _keep_upload(file, "/admin/divisions/{division_id}/form/preview",
                             division_id)
    try:
        wb = _ox.load_workbook(_io.BytesIO(raw), data_only=True, keep_links=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail="엑셀을 열지 못했습니다: %s" % e)

    try:
        got = _dfi.parse_workbook(wb, division_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    idx = _df_owner_index(division_id)
    # 오타로 붙인 이름을 모아 둔다 — 화면 경고로 그대로 내보낸다
    typo = {}
    planned = _df_plan(got["items"], idx, typo)
    # 처음 보는 이름은 반영할 때 프로젝트를 만든다. 무엇이 생길지는
    # 여기서 미리 보여 준다 — 오타로 생긴 이름도 반영 전에 걸러진다.
    new_projects = _df_new_project_rows(division_id, planned["unmatched"])
    # -----------------------------------------------------------
    # 프로젝트별로 몇 건이 새로 생기고 몇 건이 바뀌는지
    # -----------------------------------------------------------
    by_project = []
    for pid, b in planned["plan"].items():
        by_project.append({
            "project_key": pid,
            "new": [x.get("part_number") or x.get("name") for x in b["new"]],
            "update": [x.get("part_number") or x.get("name") for x in b["update"]],
        })
    by_project.sort(key=lambda x: x["project_key"])
    # -----------------------------------------------------------
    # 이슈는 어느 프로젝트로 가는지만 세어 둔다
    # -----------------------------------------------------------
    #    상태(진행/해결)와, 올리면 어떻게 되는지까지
    issue_rows = []
    _idata = _load_models()
    for ix in got["issues"]:
        pid = _df_find_project(ix.get("owner"), idx, typo)
        outcome = ""
        if pid:
            try:
                outcome = _df_issue_apply(_idata, pid, ix, dry=True)
            except Exception:
                outcome = ""
        issue_rows.append({
            "project_key": pid,
            "owner": ix.get("owner"),
            "part_number": ix.get("part_number"),
            "date": ix.get("date"),
            "text": ix.get("text"),
            "status": _iss.status_of(ix.get("status")),
            "outcome": outcome,
            "matched": bool(pid),
        })

    return {
        "ok": True,
        "division_id": division_id,
        "file_name": file.filename or "",
        "sheet": got["sheet"],
        "kind": got["kind"],
        "month": got["month"],
        "weeks": got["weeks"],
        "weekly_note": _form_weekly_note(division_id, got["weeks"]),
        # 이 양식이 몇 주차 자료인가 — 실적이 적힌 마지막 주차.
        # PO 변동을 어느 주차에 적을지가 여기서 갈린다.
        "as_of_week": got.get("as_of_week") or "",
        # -----------------------------------------------------------
        # 양식의 나머지 시트
        # -----------------------------------------------------------
        #    전에는 읽고도 안 보여줬다. 올린 사람이 '용어도 적었는데 들어갔나'
        #    를 알 길이 없으면, 다음부터는 안 적는다.
        "terms": got.get("terms") or [],
        "daily_rows": len(got.get("daily") or []),
        "daily_dates": got.get("daily_dates") or [],
        # 예시 줄은 반영하지 않는다. 몇 줄이 예시인지는 보여 준다.
        "daily_example_rows": sum(1 for r in (got.get("daily") or [])
                                  if r.get("example")),
        # 양식에 없어서 '지우기' 를 켜면 사라질 기존 모델
        "stale": planned.get("stale") or [],
        "item_count": len(got["items"]),
        # '예시)' 표시가 붙은 채로 올라온 줄 — 안 지운 본보기일 수 있다
        "example_rows": got.get("example_rows") or [],
        "projects": by_project,
        "new_projects": new_projects,
        # 판가가 바뀌는 품목 — 누르기 전에 '언제부터 얼마로' 를 본다
        "price_changes": _df_price_preview(
            got["items"], idx,
            _df_week_tag(got["month"], got.get("as_of_week")) or _this_week_tag()),
        "price_from": (_df_week_tag(got["month"], got.get("as_of_week"))
                       or _this_week_tag()),
        # 양식에 이름이 없어서 화면에서 내려갈 프로젝트 (지우지는 않는다)
        "hidden_projects": _df_project_sync(
            division_id, got["items"], idx, dry=True)["hidden"],
        "unmatched": [
            {"row": x.get("row"), "owner": x.get("owner"),
             "part_number": x.get("part_number"), "name": x.get("name")}
            for x in planned["unmatched"]
        ],
        "issues": issue_rows,
        "issue_summary": _iss.summary([x["outcome"] for x in issue_rows
                                       if x.get("outcome")]),
        "warnings": got["warnings"] + _df_typo_warnings(typo),
    }


# 미리보기에서 확인한 내용을 저장한다 ← admin v2 fd.onclick() · _divFormSend()
@app.post("/admin/divisions/{division_id}/form/apply")
async def admin_division_form_apply(
    division_id: str,
    file: UploadFile = File(...),
    remove_missing: bool = Form(False),
    create_projects: bool = Form(True),
    _admin: int = Depends(get_admin_session),
):
    import datetime as _dt
    import io as _io
    import openpyxl as _ox
    import division_form_import as _dfi

    raw = await _keep_upload(file, "/admin/divisions/{division_id}/form/apply",
                             division_id)
    try:
        wb = _ox.load_workbook(_io.BytesIO(raw), data_only=True, keep_links=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail="엑셀을 열지 못했습니다: %s" % e)

    try:
        got = _dfi.parse_workbook(wb, division_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 주차 칸이 없는 양식도 받는다
    month = got["month"]

    idx = _df_owner_index(division_id)
    # 오타로 붙인 이름 — 미리보기와 같은 문구로 알린다
    typo = {}
    # -----------------------------------------------------------
    # 처음 보는 프로젝트를 먼저 만든다. 만들고 나서 색인을 다시
    # -----------------------------------------------------------
    #    세워야 아래 반영 고리가 그 프로젝트를 찾는다.
    made_projects = []
    if create_projects:
        _miss = [{"owner": it.get("owner")} for it in got["items"]
                 if not _df_find_project(it.get("owner"), idx)]
        made_projects = _df_create_projects(
            division_id, _df_new_project_rows(division_id, _miss))
        if made_projects:
            idx = _df_owner_index(division_id)

    data = _load_models()
    created = []
    updated = []
    unmatched = []
    # 판가가 바뀐 품목 — 화면에 '언제부터 얼마로' 를 보여 준다
    price_changes = []
    # 판가 구간을 **양식의 기준 주차**부터 연다.
    # 실적이 적힌 마지막 주차가 그 양식이 말하는 '지금' 이다.
    # 주차 칸이 없는 양식(CUP · 챔버)만 올린 날의 주차로 떨어진다.
    _price_tag = _df_week_tag(month, got.get("as_of_week")) or _this_week_tag()
    # 양식이 건드린 모델. 여기 없는 모델이 '양식에서 지운 줄' 이다.
    seen = {}
    # -----------------------------------------------------------
    # 1. 품목정보 반영
    # -----------------------------------------------------------
    for it in got["items"]:
        pid = _df_find_project(it.get("owner"), idx, typo)
        if not pid:
            unmatched.append({"row": it.get("row"), "owner": it.get("owner"),
                              "part_number": it.get("part_number"),
                              "name": it.get("name")})
            continue

        proj = data.setdefault("projects", {}).setdefault(pid, {"models": []})
        models = proj.setdefault("models", [])
        m = _df_pick_model(models, it.get("part_number"), it.get("name"))

        if m is None:
            # -----------------------------------------------------------
            # 새 모델. id 는 품번을 쓰고, 품번이 없으면 이름을 쓴다.
            # -----------------------------------------------------------
            mid = it.get("part_number") or it.get("name")
            m = {"id": mid,
                 "name": it.get("name") or it.get("part_number"),
                 "part_number": it.get("part_number") or "",
                 "group": it.get("group") or "양산",
                 "status": "정상",
                 "progress": 0}
            models.append(m)
            created.append({"project_key": pid, "model": mid})
        else:
            updated.append({"project_key": pid,
                            "model": m.get("name") or m.get("id")})

        seen.setdefault(pid, set()).add(id(m))
        # -----------------------------------------------------------
        # 이번 양식에 나왔다
        # -----------------------------------------------------------
        # 개발품은 끝나면 다음 양식에서 그냥 빠진다
        m["last_form"] = {"month": month or "",
                          "week": got.get("as_of_week") or "",
                          "at": _dt.date.today().strftime("%Y-%m-%d")}
        m.pop("missing_since", None)
        # -----------------------------------------------------------
        # 이 모델이 '언제 양식에 있었나' 를 적어 둔다
        # -----------------------------------------------------------
        # 양식에서 빠진 모델은 지우지 않는다 (remove_missing 기본 꺼짐).
        m["last_form"] = {"week": got.get("as_of_week") or "",
                          "month": month or "",
                          "at": _dt.date.today().strftime("%Y-%m-%d"),
                          "file": file.filename or ""}
        # -----------------------------------------------------------
        # 칸마다 '적혀 있을 때만' 덮어쓴다
        # -----------------------------------------------------------
        #    빈 칸을 0 으로 읽어 덮으면, 한 칸만 고쳐 올린 엑셀이
        #    나머지를 전부 0 으로 만든다.
        if it.get("group"):
            m["group"] = it["group"]
        if it.get("name"):
            m["name"] = it["name"]
        if it.get("part_number"):
            m["part_number"] = it["part_number"]
        # -----------------------------------------------------------
        # 0 도 적힌 값이다
        # -----------------------------------------------------------
        # Min: "가끔 불량 생기면 PO 취소 될 경우가 생기기도 해"
        #
        # 전에는 `if it.get("po_qty"):` 였다. 0 이 거짓이라 **PO 전량 취소가
        # 통째로 건너뛰어졌다** — 558 이 그대로 남았다. 이제 파서가 빈 칸을
        # None 으로 돌려주니(_int_or_none) 둘을 가릴 수 있다.
        #   적힌 0  → 덮어쓴다 (취소)
        #   빈 칸   → 그냥 둔다 (한 칸만 고쳐 올린 엑셀이 나머지를 안 날린다)
        if it.get("po_qty") is not None:
            # -----------------------------------------------------------
            # PO 수량이 바뀌면 기록을 남긴다
            # -----------------------------------------------------------
            #    "PO 가 왜 늘었지" 를 물으면 지금은 답할 자료가 없다.
            #    양식을 올릴 때마다 전/후를 적어 두면 화면에서 ▲12 로
            #    보여 줄 수 있고, 나중에 "언제 바뀌었나" 도 답이 된다.
            _before = m.get("po_qty")
            if _before is not None and int(_before) != int(it["po_qty"]):
                _log = m.setdefault("po_log", [])
                # -----------------------------------------------------------
                # 어느 주차 것인가
                # -----------------------------------------------------------
                # 양식이 스스로 말해 준다 — 실적이 적힌 마지막 주차가 그 양식의 기준 주차다 (parse_items 의 as_of_week).
                _log.append({"date": _dt.date.today().strftime("%Y-%m-%d"),
                             "week": got.get("as_of_week") or "",
                             "month": month or "",
                             "from": int(_before), "to": int(it["po_qty"]),
                             "delta": int(it["po_qty"]) - int(_before),
                             "file": file.filename or ""})
                # -----------------------------------------------------------
                # 몇 번까지 들고 있나
                # -----------------------------------------------------------
                # 12번이었다. 양식이 **주에 한 번** 올라오니 12번은 석 달도 못 채운다
                if len(_log) > 60:
                    del _log[:-60]
            m["po_qty"] = it["po_qty"]
        if it.get("shipped_qty") is not None:
            m["shipped_qty"] = it["shipped_qty"]
        # -----------------------------------------------------------
        # 판가·재료비는 '그 주차부터' 다
        # -----------------------------------------------------------
        # Min: "W43주차에 변경된 금액으로 올렸어 그러면 W42까지는 기존에
        #      있던 금액 그대로 지표가 되어야 하고 43주차 부터 변경된
        #      금액으로 지표가 되기를 원하는거야"
        #
        # 그냥 덮어쓰면 지난달 매출까지 새 판가로 다시 계산된다.
        # _df_apply_price 가 구간(phases)으로 쌓고 값도 같이 넣는다.
        _pc = _df_apply_price(m, it, _price_tag)
        if _pc:
            _pc["project_key"] = pid
            price_changes.append(_pc)
        if it.get("price_currency"):
            m["price_currency"] = it["price_currency"]
        if it.get("material_currency"):
            m["material_currency"] = it["material_currency"]
        # -----------------------------------------------------------
        # 반도체 양식에만 있는 칸. 없는 양식에서는 안 건드린다.
        # -----------------------------------------------------------
        if it.get("year_qty") is not None:
            m["year_qty"] = it["year_qty"]
        if it.get("dev_type"):
            m["dev_type"] = it["dev_type"]
        if it.get("note"):
            m["note"] = it["note"]
        # -----------------------------------------------------------
        # 납기 날짜
        # -----------------------------------------------------------
        #    칸이 있는 양식이면 빈칸도 그대로 (지운 날짜는 지운다).
        for _dk in ("due_date", "due_revised", "made_date"):
            if _dk in it:
                m[_dk] = it[_dk] or ""
        # -----------------------------------------------------------
        # 주차별 계획·실적
        # -----------------------------------------------------------
        # 주차마다 '그 주차가 속한 달' 칸에 넣는다
        if it.get("weeks"):
            wp = m.setdefault("weekly_plan", {})
            for _wk, _cell in it["weeks"].items():
                _mon = _wcal.month_of_week(_wk) or month
                if not _mon:
                    continue
                wp.setdefault(_mon, {})[_wk] = _cell
    # -----------------------------------------------------------
    # 2. 이슈사항 반영 — 진행 / 해결
    # -----------------------------------------------------------
    #    같은 이슈 = 프로젝트 + 품번 + 내용(띄어쓰기·기호 무시).
    #    '해결' 이면 닫고, 줄이 빠진 것은 건드리지 않는다.
    issue_applied = 0
    issue_unmatched = []
    issue_results = []
    for ix in got["issues"]:
        pid = _df_find_project(ix.get("owner"), idx, typo)
        if not pid:
            issue_unmatched.append(ix)
            continue
        res = _df_issue_apply(data, pid, ix, file=file.filename or "")
        issue_results.append(res)
        if res in (_iss.ADDED, _iss.CLOSED_NOW):
            issue_applied += 1
    # -----------------------------------------------------------
    # 2-1. 국내 / 해외
    # -----------------------------------------------------------
    #    고객사마다 품목 줄에 적힌 값 중 가장 많은 것. 다 비었으면 안 바꾼다.
    region_set = {}
    if _dcol.region_on(division_id):
        _votes = {}
        for it in got["items"]:
            grp = _dcol.parse_group(division_id, it.get("region"))
            if not grp:
                continue
            pid = _df_find_project(it.get("owner"), idx, typo)
            if pid:
                _votes.setdefault(pid, {}).setdefault(tuple(grp), 0)
                _votes[pid][tuple(grp)] += 1
        for pid, v in _votes.items():
            best = sorted(v.items(), key=lambda kv: -kv[1])[0][0]
            data.setdefault("projects", {}).setdefault(pid, {"models": []})["customer_group"] = list(best)
            data["projects"][pid]["customer_group_src"] = "excel"
            region_set[pid] = _dcol.region_label(
                _dcol.customer_group(division_id, pid, list(best)))
        # 묶음 칸이 비어 '미분류' 로 들어가는 고객사 — 짐작하지 않고 알린다
        _unsorted = []
        for it in got["items"]:
            pid = _df_find_project(it.get("owner"), idx, typo)
            if not pid or pid in _unsorted:
                continue
            _pj = (data.get("projects") or {}).get(pid) or {}
            # 그 고객사 모델들의 '구분 1' 중 가장 많은 것 (아리스타가 이걸로 묶는다)
            _count = {}
            for m in (_pj.get("models") or []):
                _t = str((m or {}).get("dev_type") or "") if isinstance(m, dict) else ""
                if _t:
                    _count[_t] = _count.get(_t, 0) + 1
            _top_type = ""
            if _count:
                _top_type = max(_count, key=_count.get)
            _g = _dcol.customer_group(division_id, pid, _pj.get("customer_group"),
                                      it.get("owner"), _top_type)
            if _g and list(_g)[:1] == _dcol.UNSORTED[:1]:
                _unsorted.append(pid)
        if _unsorted:
            got.setdefault("warnings", []).append(
                "%s 칸이 비어 '미분류' 로 들어간 고객사 %d곳: %s — 그 칸을 채워 다시 올려 주세요"
                % (_dcol.group_col(division_id)["header"], len(_unsorted),
                   ", ".join(_display_project_label(x) for x in _unsorted[:10])))
    # -----------------------------------------------------------
    # 2-2. 용어 사전
    # -----------------------------------------------------------
    #    양식 한 장이 그 사업부 용어 전부다. 통째로 갈아 끼운다.
    #    빈 목록이면 안 지운다 — 용어를 안 적은 양식이 훨씬 흔하다.
    term_saved = 0
    try:
        term_saved = _dterm.put(division_id, got.get("terms") or [],
                                file.filename or "")
    except Exception as _e:
        print("[용어] 담지 못했습니다(무시) — %s" % _e)
    # -----------------------------------------------------------
    # 3. 양식에 없는 모델
    # -----------------------------------------------------------
    #    목록은 늘 만들어 돌려준다 (화면에 보여 주려고). 실제로 지우는
    #    것은 사람이 켰을 때만.
    stale = _df_stale_models(data, seen)
    # -----------------------------------------------------------
    # 빠진 모델에 '언제부터 안 보이나' 를 적는다
    # -----------------------------------------------------------
    # 지우지는 않는다. 개발품(RPM)은 끝나면 양식에서 그냥 빠지는데, 지워 버리면 그 품목의 주차별 계획·실적이 통째로 없어진다
    _mark = {}
    for x in stale:
        _mark.setdefault(x["project_key"], set()).add(str(x["id"] or ""))
    for pid, ids in _mark.items():
        for m in ((data.get("projects") or {}).get(pid) or {}).get("models") or []:
            if not isinstance(m, dict) or str(m.get("id") or "") not in ids:
                continue
            if not m.get("missing_since"):
                m["missing_since"] = {
                    "month": month or "",
                    "week": got.get("as_of_week") or "",
                    "at": _dt.date.today().strftime("%Y-%m-%d"),
                }

    removed = []
    if remove_missing and stale:
        _by_pid = {}
        for x in stale:
            _by_pid.setdefault(x["project_key"], set()).add(x["id"])
        for pid, ids in _by_pid.items():
            proj = (data.get("projects") or {}).get(pid) or {}
            keep = []
            for m in (proj.get("models") or []):
                if isinstance(m, dict) and str(m.get("id") or "") in ids:
                    removed.append({"project_key": pid,
                                    "model": m.get("name") or m.get("id")})
                    continue
                keep.append(m)
            proj["models"] = keep
    # -----------------------------------------------------------
    # 4. 양식에 없는 프로젝트는 끈다
    # -----------------------------------------------------------
    #    모델보다 나중이다 — 위에서 이번 양식의 품목을 다 붙여 놓아야
    #    '어느 프로젝트가 살아 있나' 가 정확하다.
    proj_sync = _df_project_sync(division_id, got["items"], idx)

    _save_models(data)
    print("[사업부 양식] %s '%s': 모델 신규 %d · 갱신 %d · 삭제 %d · "
          "이슈 %d · 미매칭 %d"
          % (division_id, file.filename or "", len(created), len(updated),
             len(removed), issue_applied, len(unmatched)))

    return {
        "ok": True,
        "stale": stale,
        "removed": removed,
        "division_id": division_id,
        "file_name": file.filename or "",
        "month": month,
        "weeks": got["weeks"],
        "created": created,
        "updated": updated,
        "unmatched": unmatched,
        "created_projects": [{"key": p["id"], "label": p["label"]}
                             for p in made_projects],
        # 양식에 없어서 화면에서 내린 프로젝트 / 다시 적혀서 올린 프로젝트
        "hidden_projects": proj_sync["hidden"],
        "shown_projects": proj_sync["shown"],
        # 판가가 바뀐 품목 — '언제부터 얼마로' 를 그대로 보여 준다
        "price_changes": price_changes,
        "price_from": _price_tag,
        "issue_applied": issue_applied,
        "issue_summary": _iss.summary(issue_results),
        "region_set": region_set,
        "issue_unmatched": [
            {"owner": x.get("owner"), "text": x.get("text")}
            for x in issue_unmatched
        ],
        "term_saved": term_saved,
        # 양식 안의 일일 실적은 아직 반영하지 않는다
        "daily_rows": len(got.get("daily") or []),
        "warnings": got["warnings"] + _df_typo_warnings(typo),
    }

# ============================================================
#  계획 파일 (plan-file)
# ============================================================
# 올린 파일이 무엇을 바꾸는지 먼저 보여준다 ← admin v2 _pfRerun() · pfFile.onchange()
@app.post("/admin/projects/{project_key}/plan-file/preview")
async def admin_plan_file_preview(
    project_key: str,
    file: UploadFile = File(...),
    month: str = Form(""),
    _admin: int = Depends(get_admin_session),
):
    _form_only("plan-file")
    key = project_key.strip()
    orig, wb = await _pbx_open_upload(
        file, "/admin/projects/{project_key}/plan-file/preview", key)

    # 업로드 버튼이 하나라서 어느 쪽 파일인지 여기서 가른다.
    # 하바플레이트 주간 현황 엑셀은 시트 이름이 'W35' 처럼 주차 하나뿐이고,
    # 파워박스 출하계획은 시트 안에 주차 머리글이 늘어선 표다. 겹치지 않는다.
    try:
        import hrva_status_import as _hs
        status_sheets = _hs.parse_workbook(wb)
    except Exception:
        status_sheets = []
    if status_sheets:
        return {"ok": True, "kind": "status", "project_key": key,
                "file_name": orig, "sheets": [s[1] for s in status_sheets]}

    # 주차표가 없는 파일이면 모델 값만 받는다 (올리는 곳이 하나라서).
    try:
        parsed_all = _pbx_pick_months(wb, month)
        parsed = parsed_all[0]
    except HTTPException:
        # 개발 프로세스 일정표 — 모델보다 먼저 본다 (첫 칸 머리글이 '모델' 인
        # 일정표가 있어서, 모델 쪽을 먼저 보면 일정을 모델로 읽는다)
        _pk = _plan_process_peek(wb)
        if _pk:
            return {"ok": True, "kind": "process", "project_key": key,
                    "file_name": orig, "sheet": _pk["sheet"],
                    "rows": _pk["rows"], "steps": _pk["steps"]}
        _data0 = _load_models()
        _proj0 = (_data0.get("projects") or {}).get(key) or {"models": []}
        _sheet, _rows = _plan_models_anywhere(wb)
        if not _rows:
            raise
        _ch, _cr = _plan_model_changes(_proj0, _rows)
        return {"ok": True, "kind": "models", "project_key": key,
                "file_name": orig, "sheet": _sheet, "rows": len(_rows),
                "model_changed": _ch, "model_created": _cr}

    data = _load_models()
    proj = (data.get("projects") or {}).get(key) or {"models": []}
    diffs = [_pbx_diff(proj, p) for p in parsed_all]
    out = diffs[0]

    # 달마다 한 줄씩. 표는 맨 앞 달만 그리지만, 저장하면 전부 들어간다 —
    # 무엇이 들어가는지 보이지 않는 채로 저장하게 두면 안 된다.
    out["months"] = [
        {"month": d["month"], "sheet": d.get("sheet"), "weeks": d["weeks"],
         "rows": len(d["rows"]),
         "changed": sum(1 for e in d["rows"] if e.get("changed")),
         "plan": (d.get("totals") or {}).get("plan") or 0,
         "actual": (d.get("totals") or {}).get("actual") or 0,
         "notes": len(p.get("week_notes") or {})}
        for d, p in zip(diffs, parsed_all)]

    # 못 맞춘 줄은 달마다 같은 줄이 또 나온다. 라벨로 한 번만 모은다.
    _un, _useen = [], set()
    for d in diffs:
        for u in d.get("unmatched") or []:
            if u.get("label") in _useen:
                continue
            _useen.add(u.get("label"))
            _un.append(u)
    out["unmatched"] = _un

    # 같은 줄에 모델 값(판가·재료비·PO·실적)이 같이 올 수 있다.
    mrows, mchanged, mcreated = [], [], []
    try:
        _ws = wb[parsed["sheet"]] if parsed.get("sheet") in wb.sheetnames else None
        if _ws is not None:
            mrows = _plan_sheet_models(_ws)
            mchanged, mcreated = _plan_model_changes(proj, mrows)
    except Exception as _e:
        print(f"[plan-file] 모델 칸 읽기 실패(무시): {_e}")

    # 새로 생길 모델은 '건너뛰는 행' 이 아니다 — 저장하면 들어간다.
    _new = {c["name"] for c in mcreated}
    out["unmatched"] = [u for u in out.get("unmatched") or []
                        if u.get("label") not in _new]

    out.update({"ok": True, "kind": "plan", "project_key": key, "file_name": orig,
                "available": parsed.get("available") or [],
                "week_notes": parsed.get("week_notes") or {},
                "model_changed": mchanged, "model_created": mcreated})
    return out


# 미리보기에서 확인한 내용을 저장한다 ← admin v2 _pfModelsOnly() · onclick()
@app.post("/admin/projects/{project_key}/plan-file/apply")
async def admin_plan_file_apply(
    project_key: str,
    file: UploadFile = File(...),
    month: str = Form(""),
    skip: str = Form(""),
    overwrite: str = Form(""),
    _admin: int = Depends(get_admin_session),
):
    _form_only("plan-file")
    key = project_key.strip()
    orig, wb = await _pbx_open_upload(
        file, "/admin/projects/{project_key}/plan-file/apply", key)
    try:
        parsed_all = _pbx_pick_months(wb, month)
        parsed = parsed_all[0]
    except HTTPException:
        # 주차표가 없는 파일 — 모델 값만 넣는다
        _data0 = _load_models()
        _proj0 = _data0.setdefault("projects", {}).setdefault(key, {"models": []})
        _sheet, _rows = _plan_models_anywhere(wb)
        if not _rows:
            raise
        _r = _plan_apply_models(_proj0, _rows, overwrite=_plan_over(overwrite))
        _save_models(_data0)
        print(f"[plan-file] {key} '{orig}': 모델만 {_r['updated']}건"
              f"(채움 {_r['filled']} · 덮어씀 {_r['over']} · 신규 {len(_r['created'])})")
        return {"ok": True, "kind": "models", "project_key": key,
                "file_name": orig, "month": "", "weeks": [], "applied": 0,
                "skipped": 0, "unmatched": [],
                "model_updated": _r["updated"], "model_created": _r["created"],
                "week_notes": 0}

    data = _load_models()
    proj = data.setdefault("projects", {}).setdefault(key, {"models": []})

    # 모델 먼저. 새 모델이 생겨야 그 줄의 주차 숫자가 붙을 자리가 있다.
    mres = {"updated": 0, "created": [], "filled": 0, "over": 0}
    try:
        _ws = wb[parsed["sheet"]] if parsed.get("sheet") in wb.sheetnames else None
        if _ws is not None:
            mrows = _plan_sheet_models(_ws)
            if mrows:
                mres = _plan_apply_models(proj, mrows,
                                          overwrite=_plan_over(overwrite))
    except Exception as _e:
        print(f"[plan-file] 모델 칸 반영 실패(무시): {_e}")

    # 미리보기에서 체크를 푼 행 (라벨을 | 로 이어 보낸다)
    drop = {s.strip() for s in (skip or "").split("|") if s.strip()}

    by_id = {}
    for m in proj.get("models") or []:
        by_id[str(m.get("id") or m.get("name"))] = m

    applied, n_notes, done = 0, 0, []
    un_all, un_seen = [], set()
    for p in parsed_all:
        diff = _pbx_diff(proj, p)
        mon = diff["month"]
        hit = 0
        for e in diff["rows"]:
            if e["label"] in drop:
                continue
            m = by_id.get(str(e["model_id"] or e["model_name"]))
            if m is None:
                continue
            wp_all = m.setdefault("weekly_plan", {})
            bucket = wp_all.setdefault(mon, {})
            for c in e["cells"]:
                bucket[c["week"]] = {"plan": c["new"]["plan"],
                                     "actual": c["new"]["actual"]}
            try:
                m["weekly_progress"] = _ensure_mass_progress(wp_all, mon)
            except Exception:
                pass
            hit += 1
        # 미달 사유 — 화면의 '계획 미달' 패널과 같은 자리
        try:
            n_notes += _plan_apply_week_notes(proj, mon, p.get("week_notes"))
        except Exception as _e:
            print(f"[plan-file] {mon} 미달 사유 반영 실패(무시): {_e}")
        for u in diff.get("unmatched") or []:
            if u.get("label") in un_seen:
                continue
            un_seen.add(u.get("label"))
            un_all.append(u)
        applied += hit
        done.append({"month": mon, "applied": hit, "weeks": diff["weeks"]})

    # 프로젝트 현황 — 양식 아래 '프로젝트 현황' 두 줄
    _pstat = None
    try:
        _ws2 = wb[parsed["sheet"]] if parsed.get("sheet") in wb.sheetnames else None
        if _ws2 is not None:
            import pbx_plan_import as _pbxm
            _pstat = _pbxm.read_project_status(_ws2)
    except Exception as _e:
        print(f"[plan-file] 프로젝트 현황 읽기 실패(무시): {_e}")
    if _pstat is not None:
        proj["status_note"] = _pstat["note"]
        _h = _pstat["hold"]
        # 빈 칸은 '그대로 둬라' 다 — 이 양식의 다른 칸과 같은 규칙이다.
        # 비었다고 '진행' 으로 읽으면, 상태 칸을 안 건드린 사람이 올릴
        # 때마다 멈춰 세운 프로젝트가 조용히 풀린다.
        if _pstat["blank"]:
            print(f"[plan-file] {key}: 프로젝트 현황 글만 "
                  f"{len(_pstat['note'])}자 (상태 칸은 비어 있어 그대로 둠)")
        elif _h:
            proj["hold"] = _h
            proj["hold_source"] = "excel"
            proj["hold_reason"] = (_hold_from_note(_pstat["note"])[1]
                                   or _pstat["note"] or "")
            print(f"[plan-file] {key}: 프로젝트 현황 {_h} "
                  f"· {len(_pstat['note'])}자")
        else:
            # '진행' 을 골랐다 — 문구에서 다시 살아나지 않게 사실을 남긴다
            proj["hold"] = "진행"
            proj["hold_source"] = "excel"
            proj.pop("hold_reason", None)
            print(f"[plan-file] {key}: 프로젝트 현황 진행 "
                  f"· {len(_pstat['note'])}자")

    diff = _pbx_diff(proj, parsed)      # 맨 앞 달 — 응답의 대표 값
    mon = diff["month"]

    proj["plan_file"] = {
        "file_name": orig,
        "sheet": parsed.get("sheet"),
        "month": mon,
        "months": [d["month"] for d in done],
        "uploaded_at": datetime.now().isoformat(),
    }

    _save_models(data)
    print(f"[plan-file] {key} {'·'.join(d['month'] for d in done)} '{orig}': "
          f"주차 {applied}행, 모델 {mres['updated']}건"
          f"(채움 {mres.get('filled', 0)} · 덮어씀 {mres.get('over', 0)} · "
          f"신규 {len(mres['created'])}), 사유 {n_notes}주차, "
          f"건너뛴 {len(drop)}, 미매칭 {len(un_all)}")
    return {"ok": True, "project_key": key, "month": mon, "weeks": diff["weeks"],
            "applied": applied, "skipped": len(drop), "months": done,
            "model_updated": mres["updated"], "model_created": mres["created"],
            "model_filled": mres.get("filled", 0), "model_over": mres.get("over", 0),
            "week_notes": n_notes,
            "unmatched": un_all, "file_name": orig}


# 주차별 계획 삭제
@app.delete("/admin/projects/{project_key}/weekly-plan")
def admin_delete_weekly_plan(project_key: str, _admin: int = Depends(get_admin_session)):
    _alias = {
        "havaplate": "hrva_plate",
        "hrvaplate": "hrva_plate",
        "hrva-plate": "hrva_plate",
    }
    _key = _alias.get(project_key.strip().lower(), project_key.strip())
    data = _load_models()
    proj = data.setdefault("projects", {}).setdefault(_key, {"models": []})
    if "weekly_plan" in proj:
        _ref = (proj.get("weekly_plan") or {}).get("photo_ref")
        if _ref:
            try:
                _delete_note_photo(_ref)
            except Exception:
                pass
        del proj["weekly_plan"]
        _save_models(data)
    return {"ok": True, "project_key": _key}

# ============================================================
#  보고서 고치기 · 파일 붙이기 · AI 다듬기 (잠김)
# ============================================================
# 보고서 고치기 (잠김) ← admin v2 executeDelete() · __moreBtn.onclick() · _loadSalesForSection() 외
@app.put("/admin/reports/{doc_id}")
def admin_update_report(doc_id: str, payload: dict, _admin: int = Depends(get_admin_session)):
    # 수기 편집 저장
    # payload 예: {"project_overrides": {"메이져모듈": "메이저모듈"}, "products": [...]}
    items = _read_json(LATEST_FILE, [])
    # FCM alarm hook: 저장 전 상태 스냅샷
    _fcm_before_snapshot = _snapshot_notes_status()
    edit_mode = payload.get("edit_mode", False)
    if edit_mode:
        # 편집 모드: 알람 억제, 세션에 snapshot 저장
        _save_edit_session(doc_id, _fcm_before_snapshot)
        _cleanup_expired_sessions()
        print(f"[FCM] edit mode ON for {doc_id}: alarm suppressed")
    found = False
    for it in items:
        if it.get("doc_id") != doc_id:
            continue
        found = True
        try:
            _now = datetime.datetime.utcnow()
            _iso = _now.isocalendar()
            _week_now = int(_iso[1])
            _date_now = _now.date().isoformat()

            _meta = it.get("report_meta") or {}
            _meta["week"] = _week_now
            _meta["date"] = _date_now
            it["report_meta"] = _meta
            it["week_override"] = _week_now

            _parsed = it.get("parsed") or {}
            _projects = list(_parsed.get("projects") or [])
            if not _projects and (it.get("products") or []):
                _p0 = (it.get("products") or [])[0] or {}
                _nm = (_p0.get("name") or "").strip()
                if _nm:
                    _projects = [_nm]
            _projects = [str(x).strip() for x in _projects if str(x).strip()]
            if _projects:
                _parsed["projects"] = _projects
            _parsed["week"] = _week_now
            _parsed["date"] = _date_now
            _parsed["display_title"] = ", ".join(_projects) + (" · W" + str(_week_now) + " 주간보고" if _week_now else "")
            it["parsed"] = _parsed
            it["display_title"] = _parsed["display_title"]
        except Exception as _e:
            print("[WARN] week refresh failed:", _e)
        overrides = payload.get("project_overrides")
        # 이름 변경 시 다른 리포트와 중복되는지 검사
        if isinstance(overrides, dict) and overrides:
            _new_names = set()
            for _v in overrides.values():
                _n = _normalize_project_name(_v)
                if _n:
                    _new_names.add(_n)
            for _r in items:
                if (_r or {}).get("doc_id") == doc_id:
                    continue
                _parsed = (_r or {}).get("parsed") or {}
                _projs = list(_parsed.get("projects") or [])
                _manual = (_r or {}).get("manual_projects") or []
                _projs.extend(_manual)
                _overrides_o = (_r or {}).get("project_overrides") or {}
                for _pn in _projs:
                    _final = _overrides_o.get(_pn, _pn)
                    if _normalize_project_name(_final) in _new_names:
                        raise HTTPException(status_code=400, detail="이미 존재하는 프로젝트명입니다: " + str(_final))
        if isinstance(overrides, dict):
            existing_ov = it.get("project_overrides") or {}
            existing_ov.update({str(k): str(v) for k, v in overrides.items() if v})
            it["project_overrides"] = existing_ov

        # N-1: 저장 시점의 현재 주차로 강제 업데이트 (수정 저장 기준)
        current_week = date.today().isocalendar()[1]
        it["week_override"] = current_week

        # parsed.display_title도 업데이트
        if it.get("parsed") and it["parsed"].get("projects"):
            projects_str = ", ".join(it["parsed"]["projects"])
            it["parsed"]["week"] = current_week
            it["parsed"]["display_title"] = projects_str + " · W" + str(current_week) + " 주간보고"
            it["display_title"] = it["parsed"]["display_title"]

        new_products = payload.get("products")
        if isinstance(new_products, list):
            existing = it.get("products", [])
            merged = []
            for i, np in enumerate(new_products):
                base = dict(existing[i]) if i < len(existing) else {}
                for key in ("name", "headline", "category", "status", "summary_bullets", "sections", "sales_input", "sales_data", "sales_source", "sales_prices", "sales_summary", "sales_summary_data", "sales_computed_at", "sales_visible"):
                    if key in np:
                        base[key] = np[key]
                merged.append(base)
            it["products"] = merged
        break
    if not found:
        raise HTTPException(status_code=404, detail="doc_id not found")
    _write_json(LATEST_FILE, items)
    # 수기 doc이면 notes.json에는 현재 doc만 자동 동기화 (모바일 앱 반영용)
    for _it in items:
        if _it.get("doc_id") == doc_id and _it.get("is_manual"):
            try:
                _sync_report_to_notes(_it)
            except Exception as _e:
                print("[WARN] update single sync failed:", _e)
            break

    # FCM alarm hook: 저장 후 상태 diff → RED/ORANGE 신규 전이만 알람
    # edit_mode=True면 스킵 (세션에 저장됨, edit_done에서 처리)
    if not edit_mode:
        try:
            _fcm_after_snapshot = _snapshot_notes_status()
            _fcm_events = _detect_status_transitions(_fcm_before_snapshot, _fcm_after_snapshot)
            if _fcm_events:
                print(f"[FCM] 상태 전이 감지: {_fcm_events}")
                _fire_status_alarms(_fcm_events)
        except Exception as _fcm_e:
            print(f"[FCM] hook 오류: {_fcm_e}")
    else:
        print("[FCM] edit mode: alarm deferred to edit_done")

    return {"ok": True, "doc_id": doc_id, "edit_mode": edit_mode}


# 편집 완료: 저장된 before snapshot과 현재 상태 비교 → 알람 1회 발송 ← admin v2 _flushManualEditAlarmSession()
@app.post("/admin/reports/{doc_id}/edit_done")
def admin_report_edit_done(doc_id: str, _admin: int = Depends(get_admin_session)):
    _before_snapshot = _clear_edit_session(doc_id)
    if not _before_snapshot:
        return {"ok": True, "doc_id": doc_id, "message": "no edit session found"}

    try:
        _after_snapshot = _snapshot_notes_status()
        _events = _detect_status_transitions(_before_snapshot, _after_snapshot)
        if _events:
            print(f"[FCM] edit_done: 상태 전이 감지 → {_events}")
            _fire_status_alarms(_events)
            return {"ok": True, "doc_id": doc_id, "alarms_fired": len(_events)}
        else:
            print("[FCM] edit_done: 변경 없음 (no alarms)")
            return {"ok": True, "doc_id": doc_id, "alarms_fired": 0}
    except Exception as e:
        print(f"[FCM] edit_done 오류: {e}")
        return {"ok": False, "doc_id": doc_id, "error": str(e)}

# 보고서 섹션에 파일 붙이기 (잠김) ← admin v2 _flushManualEditAlarmSession()
@app.post("/admin/reports/{doc_id}/section-file")
async def admin_upload_section_file(
    doc_id: str,
    file: UploadFile = File(...),
    _admin: int = Depends(get_admin_session)
):
    # 수기 프로젝트의 섹션 안 파일 블록용 업로드.
    # uploads/manual/{doc_id}/ 아래에 저장하고 다운로드 URL 반환.
    import re as _re, uuid as _uuid
    items = _read_json(LATEST_FILE, [])
    target = None
    for it in items:
        if it.get("doc_id") == doc_id:
            target = it
            break
    if not target:
        raise HTTPException(status_code=404, detail="doc_id not found")
    if not target.get("is_manual"):
        raise HTTPException(status_code=403, detail="only manual reports support section files")

    if not file.filename:
        raise HTTPException(status_code=400, detail="file required")

    # 안전한 파일명: 원본 이름 유지하되 경로 문자 제거
    safe_name = _re.sub(r"[\\/]", "_", file.filename).strip()
    if not safe_name:
        safe_name = "file"
    # 중복 시 앞에 랜덤 프리픽스
    manual_dir = UPLOAD_DIR / "manual" / doc_id
    manual_dir.mkdir(parents=True, exist_ok=True)
    dest = manual_dir / safe_name
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        safe_name = stem + "_" + _uuid.uuid4().hex[:6] + suffix
        dest = manual_dir / safe_name

    data = await file.read()
    dest.write_bytes(data)

    # xlsx/xlsm 이면 PNG로도 자동 변환해서 photo_ref 확보 (앱 렌더용)
    photo_ref = None
    lower = safe_name.lower()
    if lower.endswith(('.xlsx', '.xlsm')):
        try:
            division_id = _derive_division_id_from_report(target)
            png_bytes = _xlsx_file_to_png_bytes(dest)
            photo_ref = _save_note_photo(division_id, png_bytes, ext='png')
            print(f"[section-file] xlsx→png 자동 변환 OK: {safe_name} (div={division_id}) → {photo_ref}")
        except Exception as _e:
            print(f"[section-file] xlsx→png 변환 실패 (원본은 저장됨): {_e}")

    return {
        "ok": True,
        "doc_id": doc_id,
        "file_name": safe_name,
        "size": len(data),
        "url": "/admin/manual-files/" + doc_id + "/" + safe_name,
        "photo_ref": photo_ref,
    }


# 섹션에 첨부된 xlsx 파일을 파싱해서 models/weeks 리턴 (판가 입력용) ← admin v2 _loadSalesForSection()
@app.post("/admin/reports/{doc_id}/section-parse-xlsx")
async def admin_parse_section_xlsx(
    doc_id: str,
    payload: dict,
    _admin: int = Depends(get_admin_session)
):
    import re as _re
    filename = (payload or {}).get('filename') or ''
    filename = filename.strip()
    if not filename:
        raise HTTPException(status_code=400, detail='filename required')
    if _re.search(r'[\\/]|\.\.', filename):
        raise HTTPException(status_code=400, detail='invalid filename')
    fp = UPLOAD_DIR / 'manual' / doc_id / filename
    if not fp.exists() or not fp.is_file():
        raise HTTPException(status_code=404, detail='xlsx not found')
    if not filename.lower().endswith(('.xlsx', '.xlsm')):
        raise HTTPException(status_code=400, detail='not an excel file')
    try:
        parsed = parse_sales_excel(fp)
        return {'ok': True, 'filename': filename, 'parsed': parsed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'parse error: {e}')

# 보고서 섹션에 붙인 파일 내려받기 ← admin v2 _loadXlsxPreviews()
@app.get("/admin/manual-files/{doc_id}/{filename}")
def admin_download_section_file(
    doc_id: str,
    filename: str,
    _admin: int = Depends(get_admin_session)
):
    # 수기 프로젝트 섹션 파일 다운로드
    import re as _re
    from fastapi.responses import FileResponse
    if _re.search(r"[\\/]|\.\.", filename):
        raise HTTPException(status_code=400, detail="invalid filename")
    fp = UPLOAD_DIR / "manual" / doc_id / filename
    if not fp.exists() or not fp.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(fp), filename=filename)


# 보고서에 붙인 엑셀을 표로 미리보기 ← admin v2 _loadXlsxPreviews()
@app.get("/admin/manual-files/{doc_id}/{filename}/xlsx-preview")
def admin_xlsx_preview(
    doc_id: str,
    filename: str,
    _admin: int = Depends(get_admin_session)
):
    # 수기 프로젝트 섹션 엑셀 미리보기: 병합 셀 + 스타일 유지, 빈 행/열 제거
    import re as _re
    if _re.search(r"[\\/]|\.\.", filename):
        raise HTTPException(status_code=400, detail="invalid filename")
    fp = UPLOAD_DIR / "manual" / doc_id / filename
    if not fp.exists() or not fp.is_file():
        raise HTTPException(status_code=404, detail="not found")
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="not an excel file")
    try:
        from openpyxl import load_workbook
        wb = load_workbook(str(fp), data_only=True, keep_links=False)
        ws = wb.active
        sheet_name = ws.title if ws else ""

        MAX_ROWS = 50
        MAX_COLS = 20
        # -----------------------------------------------------------
        # 병합 범위 파악: (min_row, min_col) → (rowspan, colspan)
        # -----------------------------------------------------------
        merged_map = {}
        skip_cells = set()
        for mr in ws.merged_cells.ranges:
            r1, c1, r2, c2 = mr.min_row, mr.min_col, mr.max_row, mr.max_col
            merged_map[(r1, c1)] = (r2 - r1 + 1, c2 - c1 + 1)
            for rr in range(r1, r2 + 1):
                for cc in range(c1, c2 + 1):
                    if (rr, cc) != (r1, c1):
                        skip_cells.add((rr, cc))
        # -----------------------------------------------------------
        # 실제 데이터 범위 (빈 행/열 제거 + 시작 여백 trim)
        # -----------------------------------------------------------
        max_r = min(ws.max_row or 0, MAX_ROWS)
        max_c = min(ws.max_column or 0, MAX_COLS)

        non_empty = []
        for r in range(1, max_r + 1):
            for c in range(1, max_c + 1):
                v = ws.cell(row=r, column=c).value
                if v is not None and str(v).strip() != "":
                    non_empty.append((r, c))

        if not non_empty:
            wb.close()
            return {"ok": True, "sheet": sheet_name, "rows": [], "n_rows": 0, "n_cols": 0}

        real_min_r = min(r for r, _ in non_empty)
        real_max_r = max(r for r, _ in non_empty)
        real_min_c = min(c for _, c in non_empty)
        real_max_c = max(c for _, c in non_empty)
        # -----------------------------------------------------------
        # 행 데이터 구성 (실제 데이터 bounding box만)
        # -----------------------------------------------------------
        rows = []
        for r in range(real_min_r, real_max_r + 1):
            row_cells = []
            for c in range(real_min_c, real_max_c + 1):
                if (r, c) in skip_cells:
                    continue
                cell = ws.cell(row=r, column=c)
                v = cell.value
                text = "" if v is None else str(v)

                # 병합 정보
                rspan, cspan = merged_map.get((r, c), (1, 1))

                # 현재 crop 범위를 벗어나는 병합은 잘라냄
                if r + rspan - 1 > real_max_r:
                    rspan = real_max_r - r + 1
                if c + cspan - 1 > real_max_c:
                    cspan = real_max_c - c + 1

                # 스타일 정보 (rgb / theme / indexed 모두 처리)
                bg = ""
                fg = ""
                bold = False

                # openpyxl theme index → 근사 RGB (Office 기본 테마)
                _THEME_RGB = {
                    0: "FFFFFF", 1: "000000", 2: "E7E6E6", 3: "44546A",
                    4: "4472C4", 5: "ED7D31", 6: "A5A5A5", 7: "FFC000",
                    8: "5B9BD5", 9: "70AD47",
                }

                # openpyxl tint(-1.0~1.0)를 근사 반영.
                def _apply_tint(hex6: str, tint) -> str:
                    try:
                        t = float(tint or 0)
                    except Exception:
                        t = 0.0
                    if not t:
                        return hex6
                    r = int(hex6[0:2], 16)
                    g = int(hex6[2:4], 16)
                    b = int(hex6[4:6], 16)
                    if t < 0:
                        f = 1 + t
                        r = int(r * f)
                        g = int(g * f)
                        b = int(b * f)
                    else:
                        r = int(r + (255 - r) * t)
                        g = int(g + (255 - g) * t)
                        b = int(b + (255 - b) * t)
                    r = max(0, min(255, r))
                    g = max(0, min(255, g))
                    b = max(0, min(255, b))
                    return f"{r:02X}{g:02X}{b:02X}"

                def _color_to_hex(color_obj):
                    if color_obj is None:
                        return ""
                    try:
                        ctype = getattr(color_obj, "type", None)
                        if ctype == "rgb":
                            rgb = getattr(color_obj, "rgb", None)
                            if rgb and isinstance(rgb, str) and rgb != "00000000":
                                return "#" + rgb[-6:]
                        elif ctype == "theme":
                            theme_idx = getattr(color_obj, "theme", None)
                            if isinstance(theme_idx, int) and theme_idx in _THEME_RGB:
                                base = _THEME_RGB[theme_idx]
                                tint = getattr(color_obj, "tint", 0)
                                return "#" + _apply_tint(base, tint)
                        elif ctype == "indexed":
                            # 흔한 인덱스만 처리 (필요시 확장)
                            _INDEXED = {
                                0: "000000", 1: "FFFFFF", 2: "FF0000", 3: "00FF00",
                                4: "0000FF", 5: "FFFF00", 6: "FF00FF", 7: "00FFFF",
                                64: "000000",  # system foreground
                            }
                            idx = getattr(color_obj, "indexed", None)
                            if isinstance(idx, int) and idx in _INDEXED:
                                return "#" + _INDEXED[idx]
                    except Exception:
                        return ""
                    return ""

                try:
                    if cell.fill and cell.fill.patternType:
                        bg = _color_to_hex(getattr(cell.fill, "fgColor", None))
                    if cell.font and cell.font.color:
                        fg = _color_to_hex(cell.font.color)
                    if cell.font and cell.font.bold:
                        bold = True
                except Exception:
                    pass

                # border 정보 (색상이 지정된 경우만 - default 검정선은 스킵)
                borders = {}
                try:
                    b = cell.border
                    for side_name in ("left", "right", "top", "bottom"):
                        side = getattr(b, side_name, None)
                        if not side or not side.style:
                            continue
                        col = side.color
                        if not col:
                            continue
                        # rgb 값 안전하게 추출 (openpyxl 버전 차이 대응)
                        rgb_val = None
                        try:
                            ctype = getattr(col, "type", None)
                            if ctype == "rgb":
                                raw = col.__dict__.get("rgb") if hasattr(col, "__dict__") else None
                                if isinstance(raw, str) and len(raw) >= 6:
                                    rgb_val = raw
                        except Exception:
                            pass
                        # default 검정선은 제외 (파일 크기 절약)
                        if not rgb_val:
                            continue
                        if rgb_val.upper() in ("00000000", "FF000000", "000000"):
                            continue
                        borders[side_name] = {
                            "color": "#" + rgb_val[-6:],
                            "style": side.style,
                        }
                except Exception:
                    pass

                row_cells.append({
                    "text": text,
                    "rowspan": rspan,
                    "colspan": cspan,
                    "bg": bg,
                    "fg": fg,
                    "bold": bold,
                    "borders": borders,
                })
            rows.append(row_cells)

        wb.close()
        return {
            "ok": True,
            "sheet": sheet_name,
            "rows": rows,
            "n_rows": real_max_r - real_min_r + 1,
            "n_cols": real_max_c - real_min_c + 1,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"excel parse error: {e}")


# 보고서 글을 AI 로 다듬기 (잠김) ← admin v2 _flushManualEditAlarmSession()
@app.post("/admin/reports/{doc_id}/polish-text")
def admin_polish_text(
    doc_id: str,
    payload: dict,
    _admin: int = Depends(get_admin_session)
):
    # 수기 프로젝트 텍스트 블록 AI 다듬기
    import re as _re
    from html import unescape as _html_unescape

    if client is None:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    raw_html = str((payload or {}).get("text") or "").strip()
    section_title = str((payload or {}).get("section_title") or "").strip()

    if not raw_html:
        raise HTTPException(status_code=400, detail="text is required")

    def _html_to_text(s: str) -> str:
        s = _re.sub(r'<br\s*/?>', '\n', s, flags=_re.I)
        s = _re.sub(r'</(p|div|li|h[1-6])>', '\n', s, flags=_re.I)
        s = _re.sub(r'<[^>]+>', '', s)
        s = _html_unescape(s)
        s = _re.sub(r'\n{3,}', '\n\n', s)
        s = _re.sub(r'[ \t]+', ' ', s)
        return s.strip()

    # few-shot 예시 수집
    items = _read_json(LATEST_FILE, [])
    examples = []
    seen = set()

    def _push_example(txt: str):
        t = _html_to_text(txt or "")
        t = _re.sub(r'\s+', ' ', t).strip()
        if len(t) < 25:
            return
        if t in seen:
            return
        seen.add(t)
        examples.append(t[:700])

    for it in items:
        if (it or {}).get("doc_id") == doc_id:
            continue
        for prod in ((it or {}).get("products") or []):
            if prod.get("headline"):
                _push_example(str(prod.get("headline")))
            for b in (prod.get("summary_bullets") or []):
                _push_example(str(b))
            for sec in (prod.get("sections") or []):
                for blk in (sec.get("blocks") or []):
                    if (blk or {}).get("type") == "text" and (blk or {}).get("body"):
                        _push_example(str(blk.get("body")))
            if len(examples) >= 3:
                break
        if len(examples) >= 3:
            break

    fewshot = "\n\n".join(
        [f"[예시 {i+1}]\n{ex}" for i, ex in enumerate(examples[:3])]
    ) or "(예시 없음)"

    system_prompt = """
너는 한국어 제조/개발 주간보고 문체 편집기다.
원본을 최대한 보존하면서 표기와 문법만 다듬는 게 유일한 목적이다.

[절대 규칙 - 위반 시 실패]
1. 원본에 있는 문장/항목/번호를 절대 삭제하지 마라.
2. 원본이 N줄이면 결과도 정확히 N줄이어야 한다.
3. 원본에 없는 내용을 추가하지 마라.
4. 숫자/날짜/주차/수량/고유명사(제품명, 파트명, 부서명, 사람이름)를 절대 바꾸지 마라.
5. 항목 번호(1. 2. 3. / 1) 2) 3) / 가) 나) / ① ②)와 순서를 절대 바꾸지 마라.
6. 원본의 bullet, sub-bullet, 들여쓰기 계층을 그대로 유지하라.
7. 요약/축약/의역 절대 금지. 표현이 어색해도 원본 단어를 다른 단어로 대체하지 마라.

[표기 정돈 - 반드시 적용]
1. 화살표 통일: `-->`, `->`, `=>`, `⇒`, `~>` → 모두 `→`
2. 라인 시작의 하이픈 bullet: `- ` → `• ` (라인 첫 문자가 하이픈일 때만)
3. 줄 앞 불필요한 공백 정리 (단, 들여쓰기 계층은 유지):
   - 라인 시작의 tab은 스페이스 4개로
   - 라인 시작 스페이스는 4의 배수로 정규화
4. 콜론 뒤 공백 하나 확보: `단어:다음` → `단어: 다음`
5. 괄호 앞뒤 공백 정리: `단어(내용)` → `단어 (내용)`은 하지 마라. 원본 그대로.
6. 마침표/쉼표 뒤 공백 하나 확보

[문법 확인 - 반드시 적용]
1. 맞춤법/띄어쓰기 오류 교정
2. 오탈자 교정
3. 어색한 조사 수정 (예: "을" ↔ "를", "이" ↔ "가", "은" ↔ "는")
4. 잘못된 어미 자연스럽게 수정
5. 반드시 최소 1개 이상의 실질적 텍스트 수정을 수행할 것

[중요]
- 공백/줄바꿈만 바꾸는 건 수정으로 치지 않음
- 실제 글자를 바꿔야 수정임
- 원문이 완벽하면 그대로 두되, 표기 정돈은 무조건 적용

[하지 말 것]
- 문장 삭제 금지
- 항목 삭제 금지
- 요약 금지
- 표현 대체 금지 (원본 단어를 다른 단어로 바꾸지 마)
- HTML 태그 임의 제거 금지
- <ol>, <ul>, <li> 새로 만들지 마라 (원본에 없으면 만들지 마)

[출력]
- HTML fragment만 (설명 없이)
- markdown code fence(```) 사용 금지
- 원본 HTML 태그(<p>, <span>, <b>, <br>, <ul>, <li> 등) 그대로 유지
- 원본에 <br>이 N개면 결과도 <br>이 N개

[리스트 규칙 - 매우 중요]
- 원본에 "1)" "2)" "가)" "1." "-" 같은 수동 번호매기기가 있으면 그대로 텍스트로 유지 (bullet 규칙에 따라 `-`는 `•`로만 변환)
- 절대로 <ol>, <ul>, <li> 태그로 감싸지 마라. 원본이 <ol>/<ul>이 아니면 만들지 마라.
- 원본이 평문(줄바꿈만 있는 텍스트)이면 결과도 평문으로 유지
- 원본의 들여쓰기(공백, 탭)를 최대한 그대로 유지
""".strip()

    user_prompt = f"""
[섹션]
{section_title or "일반"}

[참고 문체 예시]
{fewshot}

[원본 HTML]
{raw_html}
""".strip()

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            max_tokens=4000,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        polished = (resp.choices[0].message.content or "").strip()
        polished = _re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", polished)
        polished = _re.sub(r"\s*```$", "", polished)
        if not polished:
            raise HTTPException(status_code=500, detail="empty model output")
        # -----------------------------------------------------------
        # 후처리: 표기 통일 강제 (프롬프트가 놓친 경우 대비)
        # -----------------------------------------------------------
        # 화살표 통일: --> / -> / => / ⇒ / ~> → →
        # 주의: <br>, </li>, <br/> 등 HTML 안의 - 는 건드리지 않음
        polished = _re.sub(r"-->", "→", polished)
        polished = _re.sub(r"=>", "→", polished)
        polished = _re.sub(r"⇒", "→", polished)
        polished = _re.sub(r"~>", "→", polished)
        # -> 는 HTML 태그(<->, </->)와 겹치지 않게 좌우 공백 있는 경우만
        polished = _re.sub(r"(?<=\s)->(?=\s)", "→", polished)
        polished = _re.sub(r"^->(?=\s)", "→", polished, flags=_re.M)

        # 라인 시작 하이픈 bullet: `- xxx` → `• xxx`
        # HTML 태그 안이 아니라 텍스트 라인 시작만 처리
        # <br> 직후, <p> 직후, <div> 직후, 문자열 시작
        polished = _re.sub(r"(^|<br\s*/?>|<p[^>]*>|<div[^>]*>|<li[^>]*>)(\s*)-\s", r"\1\2• ", polished, flags=_re.I)

        # 인라인 diff HTML 생성 (플레인 텍스트 비교 후 마크업)
        import difflib as _difflib
        orig_text = _html_to_text(raw_html)
        new_text = _html_to_text(polished)
        sm = _difflib.SequenceMatcher(None, orig_text, new_text, autojunk=False)
        diff_parts = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            a_seg = orig_text[i1:i2]
            b_seg = new_text[j1:j2]
            def _esc(t):
                return (t.replace("&", "&amp;")
                         .replace("<", "&lt;")
                         .replace(">", "&gt;")
                         .replace("\n", "<br>"))
            if tag == "equal":
                diff_parts.append(_esc(a_seg))
            elif tag == "delete":
                diff_parts.append('<del style="background:#FEE2E2;color:#B42318;text-decoration:line-through;padding:0 2px;border-radius:3px;">' + _esc(a_seg) + '</del>')
            elif tag == "insert":
                diff_parts.append('<ins style="background:#D1FAE5;color:#065F46;text-decoration:none;padding:0 2px;border-radius:3px;">' + _esc(b_seg) + '</ins>')
            elif tag == "replace":
                diff_parts.append('<del style="background:#FEE2E2;color:#B42318;text-decoration:line-through;padding:0 2px;border-radius:3px;">' + _esc(a_seg) + '</del>')
                diff_parts.append('<ins style="background:#D1FAE5;color:#065F46;text-decoration:none;padding:0 2px;border-radius:3px;">' + _esc(b_seg) + '</ins>')
        diff_html = "".join(diff_parts)

        return {
            "ok": True,
            "doc_id": doc_id,
            "section_title": section_title,
            "original": raw_html,
            "polished": polished,
            "diff_html": diff_html,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ai polish error: {e}")


# 보고서 숨기기/보이기 (잠김) ← admin v2 __moreBtn.onclick()
@app.post("/admin/reports/{doc_id}/hide")
def admin_toggle_hide(doc_id: str, _admin: int = Depends(get_admin_session)):
    # 숨김/숨김해제 토글. hidden=True 이면 /reports 에서 제외됨.
    items = _read_json(LATEST_FILE, [])
    found = False
    new_state = False
    for it in items:
        if it.get("doc_id") == doc_id:
            new_state = not bool(it.get("hidden", False))
            it["hidden"] = new_state
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="doc_id not found")
    _write_json(LATEST_FILE, items)
    _resync_notes_from_latest()
    return {"ok": True, "doc_id": doc_id, "hidden": new_state}

# ============================================================
#  PPT · 카드 지우기 · 초기화 (잠김)
# ============================================================
def _resync_notes_from_latest() -> None:
    try:
        latest_items = _read_json(LATEST_FILE, [])
        notes_data = _load_notes()
        notes_map = notes_data.get("notes", {})
        for div_id, payload in list(notes_map.items()):
            if not isinstance(payload, dict):
                continue
            cards = payload.get("cards", []) or []
            preserved = [c for c in cards if isinstance(c, dict) and c.get("note_only") is True]
            payload["cards"] = preserved
        _save_notes(notes_data)
        for it in latest_items:
            try:
                _sync_report_to_notes(it)
            except Exception:
                import traceback
                traceback.print_exc()
    except Exception:
        import traceback
        traceback.print_exc()


# PPT 파일 단위 삭제: reports_latest.json + 관련 폴더/파일 전부 정리
@app.delete("/admin/doc/{doc_id}")
def admin_delete_doc(doc_id: str, _admin: int = Depends(get_admin_session)):
    import shutil
    # -----------------------------------------------------------
    # reports_latest.json 에서 제거
    # -----------------------------------------------------------
    items = _read_json(LATEST_FILE, [])
    before = len(items)
    items = [it for it in items if it.get("doc_id") != doc_id]
    after = len(items)
    if before == after:
        raise HTTPException(status_code=404, detail="해당 doc_id를 찾을 수 없습니다.")
    _write_json(LATEST_FILE, items)
    # -----------------------------------------------------------
    # 파일 시스템 정리
    # -----------------------------------------------------------
    removed = []
    pptx_path = UPLOAD_DIR / f"{doc_id}.pptx"
    if pptx_path.exists():
        pptx_path.unlink()
        removed.append(str(pptx_path.name))

    for folder_dir in [SLIDES_DIR, SLIDE_IMAGES_DIR, CROPPED_DIR]:
        target = folder_dir / doc_id
        if target.exists() and target.is_dir():
            shutil.rmtree(target)
            removed.append(f"{folder_dir.name}/{doc_id}/")
    # -----------------------------------------------------------
    # upload_hashes.json 에서 제거
    # -----------------------------------------------------------
    try:
        idx = _load_upload_hash_index()
        new_idx = {k: v for k, v in idx.items() if v.get("doc_id") != doc_id}
        if len(new_idx) != len(idx):
            _save_upload_hash_index(new_idx)
            removed.append("upload_hash entry")
    except Exception:
        pass

    return {"ok": True, "doc_id": doc_id, "removed": removed, "remaining": after}


# PPT doc_id 여러 개 일괄 삭제
@app.post("/admin/docs/delete-batch")
def admin_delete_docs_batch(
    payload: dict,
    _admin: int = Depends(get_admin_session),
):
    doc_ids = payload.get("doc_ids", []) if isinstance(payload, dict) else []
    if not isinstance(doc_ids, list):
        raise HTTPException(status_code=400, detail="doc_ids must be a list")

    removed = []
    failed = []
    for did in doc_ids:
        if not isinstance(did, str):
            continue
        try:
            admin_delete_doc(did, _admin=_admin)
            removed.append(did)
        except HTTPException as e:
            failed.append({"doc_id": did, "status": e.status_code, "detail": e.detail})
        except Exception as e:
            failed.append({"doc_id": did, "detail": str(e)})

    return {
        "ok": True,
        "removed_count": len(removed),
        "removed": removed,
        "failed": failed,
    }


# 카드(product) 1장 단위 삭제
@app.delete("/admin/card")
def admin_delete_card(
    doc_id: str,
    product_idx: int,
    _admin: int = Depends(get_admin_session),
):
    items = _read_json(LATEST_FILE, [])
    target = None
    for it in items:
        if it.get("doc_id") == doc_id:
            target = it
            break
    if not target:
        raise HTTPException(status_code=404, detail="해당 doc_id를 찾을 수 없습니다.")

    products = target.get("products", [])
    if product_idx < 0 or product_idx >= len(products):
        raise HTTPException(status_code=404, detail=f"product_idx 범위 초과 (0~{len(products)-1})")

    removed_product = products.pop(product_idx)
    target["products"] = products
    _write_json(LATEST_FILE, items)
    return {
        "ok": True,
        "doc_id": doc_id,
        "removed_product_name": removed_product.get("name") or removed_product.get("product"),
        "remaining_products": len(products),
    }


# 자료 초기화 (잠김).
@app.post("/admin/reset")
def admin_reset(
    password: str = Form(default=""),
    admin_auth: Optional[str] = Cookie(default=None),
):
    _has_session = bool(_verify_session(admin_auth))
    if not _has_session and password != UPLOAD_PASSWORD:
        raise HTTPException(status_code=401, detail="비밀번호가 틀립니다.")
    _write_json(LATEST_FILE, [])
    return {"ok": True, "message": "최신 데이터가 초기화되었습니다."}



# ============================================================
#  챗봇 (/chat) · RAG
# ============================================================
def _kmonth(month: str) -> str:
    try:
        return f"{int(str(month).split('-')[1])}월"
    except Exception:
        return str(month or "")


# 주차 단위 출하 수량/매출 확정 답변(LLM 우회).
def _week_shipment_answer(project_key, week, mode='qty', with_models=False, with_revenue=False, with_weeks=False):
    if not week:
        return None
    week = str(week).upper()
    month = _month_of_week(week) or _latest_data_month(project_key)
    if not month:
        return None
    # W40 처럼 두 달에 걸친 주차는 데이터가 있는 쪽 달을 쓴다
    try:
        _cands = [month]
        _y, _m = map(int, month.split('-'))
        _pm = f"{_y - 1}-12" if _m == 1 else f"{_y}-{_m - 1:02d}"
        _cands.append(_pm)
        for _c in _cands:
            _probe = get_weekly_revenue(
                project_key if project_key and project_key != 'all' else 'hrva_plate', _c) or {}
            _g = _probe.get('groups') or {}
            _yc = ((_g.get('양산') or {}).get('weeks') or {}).get(week) or {}
            _dc = ((_g.get('개발') or {}).get('weeks') or {}).get(week) or {}
            # 양산 · 개발 두 칸 중 계획이나 실적이 하나라도 있으면 그 달이다
            _has_num = False
            for _cell in (_yc, _dc):
                for _f in ('plan', 'actual'):
                    if int(_cell.get(_f) or 0):
                        _has_num = True
                        break
                if _has_num:
                    break
            if _has_num:
                month = _c
                break
    except Exception:
        pass

    keys = []
    if project_key and project_key != 'all':
        keys = [project_key]
    else:
        _d = _load_models()
        for k, v in (_d.get('projects') or {}).items():
            if (v.get('weekly_summary') or {}) or any((m.get('weekly_plan') or {})
                                                      for m in (v.get('models') or [])):
                keys.append(k)
    if not keys:
        return None

    yp = ya = dp = da = 0
    rev = prev = 0
    used_labels = []
    model_rows = []
    _month_rev = 0          # 그 달 누적 실적 매출
    _week_rev = {}          # 주차별 실적 매출 (직전 주 찾기용)
    _data = _load_models()
    for k in keys:
        wr = get_weekly_revenue(k, month) or {}
        _comb = wr.get('combined') or {}
        _month_rev += int(((_comb.get('total') or {}).get('revenue')) or 0)
        for _w, _wv in (_comb.get('weeks') or {}).items():
            _week_rev[_w] = _week_rev.get(_w, 0) + int((_wv or {}).get('revenue') or 0)
        if week not in (wr.get('weeks') or []):
            continue
        grp = wr.get('groups') or {}
        yc = ((grp.get('양산') or {}).get('weeks') or {}).get(week) or {}
        dc = ((grp.get('개발') or {}).get('weeks') or {}).get(week) or {}
        # 양산 · 개발 두 칸 다 계획·실적이 0 이면 건너뛴다
        _has_num = False
        for _cell in (yc, dc):
            for _f in ('plan', 'actual'):
                if int(_cell.get(_f) or 0):
                    _has_num = True
                    break
            if _has_num:
                break
        if not _has_num:
            continue
        used_labels.append(_display_project_label(k))
        _yp, _ya = int(yc.get('plan') or 0), int(yc.get('actual') or 0)
        # 원본 주간보고 합계가 있으면 양산 수량은 그쪽을 정본으로
        _src = ((_data.get('projects') or {}).get(_model_key_alias(k)) or {}) \
            .get('weekly_summary') or {}
        _sc = ((_src.get('양산') or {}).get('weeks') or {}).get(week)
        # 보드 스펙이 있는 프로젝트(엔클로저·파워박스·챔버…)는 모델별 값이 정본이다.
        # weekly_summary 는 예전 주간보고 엑셀에서 들어온 값이라 뒤처져 있다
        # (엔클로저 W37: 주간보고 110대 vs 모델 합계 106대 — 보드는 106 을 보여준다).
        if isinstance(_sc, dict) and not _load_board_spec(_model_key_alias(k)):
            _yp, _ya = int(_sc.get('plan') or 0), int(_sc.get('actual') or 0)
        yp += _yp
        ya += _ya
        dp += int(dc.get('plan') or 0)
        da += int(dc.get('actual') or 0)
        rev += int(yc.get('revenue') or 0) + int(dc.get('revenue') or 0)
        prev += int(yc.get('plan_revenue') or 0) + int(dc.get('plan_revenue') or 0)
        for m in ((_data.get('projects') or {}).get(_model_key_alias(k)) or {}).get('models') or []:
            if m.get('group') == '개발':
                continue
            cell = ((m.get('weekly_plan') or {}).get(month) or {}).get(week) or {}
            _a = int(cell.get('actual') or 0)
            if _a:
                model_rows.append({'id': m.get('id') or m.get('name'), 'actual': _a})

    if not used_labels:
        return None

    if len(used_labels) > 2:
        label = f'반도체사업부 전체({len(used_labels)}개 프로젝트)'
    else:
        label = ' + '.join(used_labels)

    lines = []
    # 실적 0 만 말하면 매출이 없는 것처럼 보인다. 직전 주와 월 누적을 같이 준다.
    _ctx = []
    _prior = sorted([w for w, v in _week_rev.items() if v > 0 and str(w) < str(week)])
    if _prior:
        _ctx.append(f"직전 {_prior[-1]} 실적 ${_week_rev[_prior[-1]]:,}")
    if _month_rev:
        _ctx.append(f"{_kmonth(month)} 누적 ${_month_rev:,}")

    if mode == 'rev':
        if rev > 0:
            lines.append(f"{week} {label} 매출 실적 ${rev:,} / 계획 ${prev:,}.")
        else:
            lines.append(f"{week} {label} 매출은 아직 실적 없음 (계획 ${prev:,}).")
            if _ctx:
                lines.append(" · ".join(_ctx) + ".")
        lines.append(f"수량 계획 {yp + dp}대 → 실적 {ya + da}대.")
    else:
        lines.append(f"{week} {label} 출하 실적 {ya + da}대 / 계획 {yp + dp}대 "
                     f"(양산 {ya}, 개발 {da}).")
        # 대수를 물었으면 대수만 답한다. 매출은 같이 물었을 때만 붙인다.
        if with_revenue:
            lines.append(f"매출 실적 ${rev:,} / 계획 ${prev:,}.")
        elif ya + da == 0 and _ctx:
            lines.append(" · ".join(_ctx) + ".")
        ms = sorted(model_rows, key=lambda x: -x['actual']) if with_models else []
        if ms:
            lines.append('')
            lines.append(f'{week} 모델별 양산 출하 실적')
            for m in ms[:10]:
                lines.append(f"- {m['id']}: {m['actual']}대")
            if len(ms) > 10:
                lines.append(f"- 그 외 {len(ms) - 10}개 모델 합계 "
                             f"{sum(x['actual'] for x in ms[10:])}대")
    return '\n'.join(lines)


# 월 단위 출하 수량/매출 확정 답변(LLM 우회).
def _month_shipment_answer(project_key, month, mode='qty', with_models=False, with_revenue=False, with_weeks=False):
    keys = []
    if project_key and project_key != 'all':
        keys = [project_key]
    else:
        _d = _load_models()
        for k, v in (_d.get('projects') or {}).items():
            if (v.get('weekly_summary') or {}) or any((m.get('weekly_plan') or {}) for m in (v.get('models') or [])):
                keys.append(k)
    if not keys:
        return None

    g_yang = {'plan': 0, 'actual': 0, 'revenue': 0, 'plan_revenue': 0}
    g_dev = {'plan': 0, 'actual': 0, 'revenue': 0, 'plan_revenue': 0}
    week_rows = {}
    model_rows = []
    used_labels = []
    for k in keys:
        wr = get_weekly_revenue(k, month) or {}
        if not wr.get('weeks'):
            continue
        grp = wr.get('groups') or {}
        y_tot = (grp.get('양산') or {}).get('total') or {}
        d_tot = (grp.get('개발') or {}).get('total') or {}
        # 양산 · 개발 합계가 다 0 이면 건너뛴다
        _has_num = False
        for _cell in (y_tot, d_tot):
            for _f in ('plan', 'actual'):
                if int(_cell.get(_f) or 0):
                    _has_num = True
                    break
            if _has_num:
                break
        if not _has_num:
            continue
        used_labels.append(_display_project_label(k))
        for tgt, src_t in ((g_yang, y_tot), (g_dev, d_tot)):
            for f in ('plan', 'actual', 'revenue', 'plan_revenue'):
                tgt[f] = tgt.get(f, 0) + int(src_t.get(f) or 0)
        for w in wr.get('weeks') or []:
            row = week_rows.setdefault(w, {'yp': 0, 'ya': 0, 'dp': 0, 'da': 0, 'rev': 0, 'prev': 0})
            yc = ((grp.get('양산') or {}).get('weeks') or {}).get(w) or {}
            dc = ((grp.get('개발') or {}).get('weeks') or {}).get(w) or {}
            row['yp'] += int(yc.get('plan') or 0)
            row['ya'] += int(yc.get('actual') or 0)
            row['dp'] += int(dc.get('plan') or 0)
            row['da'] += int(dc.get('actual') or 0)
            row['rev'] += int(yc.get('revenue') or 0) + int(dc.get('revenue') or 0)
            row['prev'] += int(yc.get('plan_revenue') or 0) + int(dc.get('plan_revenue') or 0)
        for m in ((grp.get('양산') or {}).get('models_used') or []):
            model_rows.append(m)

        # 원본 주차 합계(weekly_summary)가 있으면 수량은 그쪽을 정본으로 쓴다
        try:
            _ws_g = ((_load_models().get('projects') or {}).get(_model_key_alias(k)) or {}) \
                .get('weekly_summary') or {}
            _ws_y = (_ws_g.get('양산') or {}).get('weeks') or {}
            for w in wr.get('weeks') or []:
                cell = _ws_y.get(w)
                if not isinstance(cell, dict):
                    continue
                row = week_rows.setdefault(w, {'yp': 0, 'ya': 0, 'dp': 0, 'da': 0,
                                               'rev': 0, 'prev': 0})
                row['syp'] = row.get('syp', 0) + int(cell.get('plan') or 0)
                row['sya'] = row.get('sya', 0) + int(cell.get('actual') or 0)
        except Exception:
            pass

    if not week_rows:
        return None

    # 원본 합계가 하나라도 있으면 양산 수량 기준을 원본으로 전환
    _has_src = any('sya' in v or 'syp' in v for v in week_rows.values())
    if _has_src:
        for v in week_rows.values():
            v['yp'] = v.get('syp', v['yp'])
            v['ya'] = v.get('sya', v['ya'])
        g_yang['plan'] = sum(v['yp'] for v in week_rows.values())
        g_yang['actual'] = sum(v['ya'] for v in week_rows.values())

    if len(used_labels) > 2:
        label = f'반도체사업부 전체({len(used_labels)}개 프로젝트)'
    else:
        label = ' + '.join(used_labels) if used_labels else '반도체사업부'
    weeks_sorted = sorted(week_rows, key=lambda w: int(str(w).lstrip('Ww') or 0))
    lines = []

    _mlabel = _kmonth(month)
    if mode == 'rev':
        total_rev = g_yang['revenue'] + g_dev['revenue']
        total_plan_rev = g_yang['plan_revenue'] + g_dev['plan_revenue']
        _rate = round(total_rev * 100 / total_plan_rev) if total_plan_rev else 0
        if total_rev > 0:
            lines.append(f"{_mlabel} {label} 매출 실적 ${total_rev:,} / "
                         f"계획 ${total_plan_rev:,} (달성률 {_rate}%).")
        else:
            lines.append(f"{_mlabel} {label} 매출은 아직 실적 없음 "
                         f"(계획 ${total_plan_rev:,}).")
        if with_weeks:
            lines.append('')
            lines.append('주차별 (실적 / 계획)')
            for w in weeks_sorted:
                lines.append(f"- {w}: ${week_rows[w]['rev']:,} / ${week_rows[w]['prev']:,}")
    else:
        total_a = g_yang['actual'] + g_dev['actual']
        total_p = g_yang['plan'] + g_dev['plan']
        total_rev = g_yang['revenue'] + g_dev['revenue']
        total_plan_rev = g_yang['plan_revenue'] + g_dev['plan_revenue']
        lines.append(f"{_mlabel} {label} 출하 실적 {total_a}대 / 계획 {total_p}대 "
                     f"(양산 {g_yang['actual']}, 개발 {g_dev['actual']}).")
        if with_revenue:
            lines.append(f"매출 실적 ${total_rev:,} / 계획 ${total_plan_rev:,}.")
        if with_weeks:
            lines.append('')
            lines.append('주차별 (계획 → 실적)')
            for w in weeks_sorted:
                r = week_rows[w]
                lines.append(f"- {w}: 양산 {r['yp']}→{r['ya']}대 / 개발 {r['dp']}→{r['da']}대")
        ms = (sorted([m for m in model_rows if int(m.get('actual') or 0) > 0],
                     key=lambda x: -int(x.get('actual') or 0)) if with_models else [])
        if ms:
            lines.append('')
            lines.append('모델별 양산 출하 실적')
            for m in ms[:10]:
                lines.append(f"- {m.get('id')}: {int(m.get('actual') or 0)}대")
            if len(ms) > 10:
                _rest = sum(int(m.get('actual') or 0) for m in ms[10:])
                lines.append(f"- 그 외 {len(ms) - 10}개 모델 합계 {_rest}대")
    return '\n'.join(lines)


# admin v2 전체 데이터 기반 챗봇 ← 앱 chat_service.dart ask()
@app.post("/chat")
async def chat(payload: dict):
    message = (payload or {}).get("message", "").strip()
    if not message:
        return {"answer": "", "sources": [], "error": "empty message"}

    session_id = ((payload or {}).get("session_id") or "default").strip() or "default"

    # 세션별 마지막 컨텍스트 기억 (프로세스 전역)
    global _CHAT_SESSIONS
    try:
        _CHAT_SESSIONS
    except NameError:
        _CHAT_SESSIONS = {}
    sess = _CHAT_SESSIONS.setdefault(session_id, {})
    _user_text = message  # 세션 태그가 붙기 전 사용자 원문 (주차 판별은 이것만 본다)
    last_project = sess.get("last_project")
    last_week = sess.get("last_week")
    _month_context = ""  # 월 합계 컨텍스트 (월 키워드 있을 때만 채워짐)

    # 현재 메시지에서 주차/프로젝트 추출, 없으면 세션 값 사용
    import re as _re3
    week_m = _re3.search(r"W(\d{2})", message, _re3.I)
    if week_m:
        last_week = "W" + week_m.group(1)
    # 메시지에 프로젝트 이름이 들어 있으면 그 프로젝트로 확정한다.
    # (예전에는 하바플레이트 별칭만 하드코딩돼 있어서 '파워박스 8월 매출' 같은 질문이
    #  프로젝트 미지정 = 반도체사업부 전체 답변으로 떨어졌다.)
    _proj_in_msg = _chat_resolve_project(_user_text)
    # 사업부/전사 단위를 명시했으면 프로젝트 컨텍스트를 푼다
    if any(k in _user_text for k in ('사업부 전체', '전체 사업부', '반도체사업부',
                                     '전사', '전체 프로젝트', '모든 프로젝트')):
        _proj_in_msg = 'all'
    if _proj_in_msg:
        last_project = _proj_in_msg

    # 후속 질문 보강: 이번 메시지에 프로젝트가 안 나왔으면 세션 값을 태깅
    if last_project and last_project != 'all' and not _proj_in_msg:
        message = f"[project:{last_project}] {message}"
    if last_week and not week_m:
        message = f"{message} ({last_week} 기준)"

    sess["last_project"] = last_project
    sess["last_week"] = last_week
    # -----------------------------------------------------------
    # 블룸은 모델이 아니라 '대표님 일 보고' 보드를 본다
    # -----------------------------------------------------------
    if last_project and str(last_project).startswith('bloom'):
        try:
            _ans_b = _bloom_chat_answer(last_project, _user_text)
        except Exception as _e_b:
            _ans_b = None
            print(f"[chat] 블룸 즉답 실패(무시): {_e_b}")
        if _ans_b:
            sess['last_question_scope'] = True
            try:
                _lbl_b = (_cl.get_project(last_project) or {}).get('label') or last_project
            except Exception:
                _lbl_b = last_project
            return {'answer': _ans_b,
                    'sources': [{'key': last_project, 'label': _lbl_b}],
                    'corrected_query': None}
    # -----------------------------------------------------------
    # 이슈·지연 질문은 적힌 그대로 답한다 (LLM 이 중간에 끊는 걸 막는다)
    # -----------------------------------------------------------
    # 이번 메시지에 프로젝트 이름이 없으면 전 프로젝트를 훑는다. 예전에는
    # 세션에 남아 있던 마지막 프로젝트로 좁혀서, 홈에 '8건 · 3곳' 이라고
    # 떠 있는데 챗은 한 곳 1건만 말했다.
    if (any(k in _user_text for k in ('이슈', '지연', '문제', '리스크', '막힌', '지체', '밀린'))
            and not any(k in _user_text for k in ('매출', '금액', '얼마'))):
        _one = (_proj_in_msg and _proj_in_msg != 'all'
                and not str(_proj_in_msg).startswith('bloom'))
        # 물어본 것만 답한다. '일정 지연' 에 견적 협의 메모까지 끌어오면
        # 홈 카드의 숫자와 어긋난다.
        _kinds = []
        if any(k in _user_text for k in ('지연', '밀린', '지체', '늦')):
            _kinds.append('지연')
        if any(k in _user_text for k in ('이슈', '문제', '리스크', '막힌', '특이사항')):
            _kinds.append('이슈')
        if not _kinds:
            _kinds = ['지연', '이슈']
        try:
            _ans_i = _issue_answer(_proj_in_msg) if _one else _alert_answer_all(_kinds)
        except Exception as _e_i:
            _ans_i = ""
            print(f"[chat] 이슈 즉답 실패(무시): {_e_i}")
        if _ans_i:
            _scope = _proj_in_msg if _one else 'all'
            print(f"[chat] 이슈 즉답 → {_scope}")
            return {'answer': _ans_i,
                    'sources': ([{'key': _proj_in_msg,
                                  'label': _display_project_label(_proj_in_msg)}]
                                if _one else []),
                    'corrected_query': None}
    # -----------------------------------------------------------
    # 월 범위 기억 + 월 단위 수량/매출 즉답 (후속 질문 '각각 몇 대씩' 대응)
    # -----------------------------------------------------------
    _today_m = _dt_mod.now().date()
    _scope_month = None
    _mm_cur = _re3.search(r'(\d{1,2})\s*월', _user_text)
    if _mm_cur:
        _mn = int(_mm_cur.group(1))
        if 1 <= _mn <= 12:
            _yr = _today_m.year if _mn <= _today_m.month else _today_m.year - 1
            _scope_month = f"{_yr}-{_mn:02d}"
    elif any(k in _user_text for k in ['이번달', '이번 달', '이달', '금월']):
        _scope_month = f"{_today_m.year}-{_today_m.month:02d}"
    elif any(k in _user_text for k in ['지난달', '저번달', '전월']):
        _pm = _today_m.month - 1 or 12
        _py = _today_m.year if _today_m.month > 1 else _today_m.year - 1
        _scope_month = f"{_py}-{_pm:02d}"
    _week_num_in_msg = _re3.search(r'(?<!\d)(\d{1,2})\s*주차', _user_text)
    _week_alias_in_msg = any(k in _user_text for k in
                             ['이번주', '이번 주', '금주', '지난주', '지난 주', '저번주', '전주',
                              '차주', '다음주', '다음 주', '다다음주', '지지난주', '전전주'])
    _has_week_in_msg = bool(week_m) or bool(_week_num_in_msg) or _week_alias_in_msg
    _cum_in_msg = any(k in _user_text for k in ['누적', '여태', '지금까지', '올해', '전체 기간', '작년'])
    # 다른 기간 기준이 명시된 질문이면 이전 컨텍스트를 이어받지 않는다
    _other_scope = _week_alias_in_msg or _cum_in_msg

    # 이번 질문이 어떤 기준인지 기억해 둔다 (후속 질문이 같은 기준을 따라가도록)
    if _has_week_in_msg:
        sess['last_scope'] = 'week'
        if _week_num_in_msg:
            try:
                sess['last_week'] = f"W{int(_week_num_in_msg.group(1)):02d}"
            except Exception:
                pass
        elif week_m:
            sess['last_week'] = 'W' + week_m.group(1)
    elif _scope_month:
        sess['last_scope'] = 'month'
    if _scope_month:
        sess['last_month'] = _scope_month

    _qty_kw = any(k in _user_text for k in ['몇 대', '몇대', '대수', '수량', '출하량', '몇 개', '몇개', '출하'])
    _rev_kw = any(k in _user_text for k in ['매출', '금액', '얼마'])
    _mode_m = 'rev' if (_rev_kw and not _qty_kw) else 'qty'
    # 모델을 직접 물어봤을 때만 모델별 내역을 붙인다
    _want_weeks = any(k in _user_text for k in ['주차별', '주별', '주차 별', '주간 추이', '추이', '주차마다'])
    _want_models = any(k in _user_text for k in
                       ['모델', '품번', '파트', 'part', '기종', '어떤 거', '어떤걸', '무슨 모델'])
    # -----------------------------------------------------------
    # 후속 질문: 직전 질문의 기준(주차 or 월)을 그대로 이어간다
    # -----------------------------------------------------------
    if not _scope_month and not _has_week_in_msg and not _other_scope and (_qty_kw or _rev_kw):
        if sess.get('last_scope') == 'week' and sess.get('last_week'):
            _wk_prev = sess.get('last_week')
            try:
                _ans_w = _week_shipment_answer(last_project, _wk_prev, _mode_m,
                                              _want_models, _rev_kw, _want_weeks)
            except Exception as _e_ws:
                _ans_w = None
                print(f"[chat] 주차 즉답 실패(무시): {_e_ws}")
            if _ans_w:
                sess['last_question_scope'] = True
                print(f"[chat] 후속 질문 → 직전 주차 {_wk_prev} 유지 / {_mode_m}")
                _src_w = ([{'key': last_project, 'label': _display_project_label(last_project)}]
                          if last_project and last_project != 'all' else [])
                return {'answer': _ans_w, 'sources': _src_w, 'corrected_query': None}
        elif sess.get('last_month'):
            _scope_month = sess.get('last_month')
            print(f"[chat] 후속 질문 → 직전 월 {_scope_month} 유지")

    if _scope_month and not _has_week_in_msg and (_qty_kw or _rev_kw):
        try:
            _ans_m = _month_shipment_answer(last_project, _scope_month, _mode_m,
                                           _want_models, _rev_kw, _want_weeks)
        except Exception as _e_ms:
            _ans_m = None
            print(f"[chat] 월 즉답 실패(무시): {_e_ms}")
        if _ans_m:
            sess['last_month'] = _scope_month
            sess['last_question_scope'] = True
            print(f"[chat] 월 즉답 → {_scope_month} / {_mode_m} (project={last_project})")
            _src_m = ([{'key': last_project, 'label': _display_project_label(last_project)}]
                      if last_project and last_project != 'all' else [])
            return {'answer': _ans_m, 'sources': _src_m, 'corrected_query': None}
    # -----------------------------------------------------------
    # 한국어 주차 별칭 → ISO 주차 매핑 (오늘 = W35, 2026-08-27)
    # -----------------------------------------------------------
    week_aliases = {
        '이번주': 0, '금주': 0, '이번 주': 0, '금번주': 0, '지금주': 0, '이번주차': 0,
        '차주': 1, '다음주': 1, '다음 주': 1, '내주': 1, '익주': 1,
        '다다음주': 2, '내다음주': 2, '다다음 주': 2,
        '지난주': -1, '지난 주': -1, '저번주': -1, '전주': -1, '직전주': -1,
        '지지난주': -2, '전전주': -2,
    }
    try:

        import datetime as _dt_wk

        cur_wk = _dt_wk.date.today().isocalendar()[1]

    except Exception:

        cur_wk = 35
    alias_hit = None
    # 긴 키부터 매칭 ('다다음주'가 '다음주'보다 먼저 검사되도록)
    for kw, off in sorted(week_aliases.items(), key=lambda x: -len(x[0])):
        if kw in _user_text:
            cur_wk = max(1, cur_wk + off)
            alias_hit = kw
            break
    # -----------------------------------------------------------
    # 명시적 주차 숫자 ("33주차" 또는 "W33") 별칭 매핑 추가
    # -----------------------------------------------------------
    if not alias_hit:
        _m_explicit = _re3.search(r'(?<!\d)(\d{1,2})\s*주차', _user_text)
        if not _m_explicit:
            _m_explicit = _re3.search(r'\bW\s*(\d{1,2})\b', _user_text, _re3.I)
        if _m_explicit:
            try:
                _n = int(_m_explicit.group(1))
                if 1 <= _n <= 53:
                    cur_wk = _n
                    last_week = f'W{_n:02d}'
                    sess['last_week'] = last_week
                    alias_hit = f'explicit_W{_n:02d}'
                    print(f'[chat] explicit week digits → W{_n:02d}')
            except Exception:
                pass

    # "총", "얼마", "매출" 질문도 프로젝트가 없으면 전체 프로젝트로 간주
    if not alias_hit and any(k in message for k in ['총', '합계', '얼마', '매출', '실적', '나올', '어떨', '예상', '예측', '전망']):
        # 프로젝트 미지정 → 전체 프로젝트 기준으로 자동 간주
        if not last_project:
            last_project = 'all'
            sess['last_project'] = last_project
        # 기준(무엇의 총액인지) 불명확 → 되묻기
        # 기준 키워드: 이번주/금주/지난주/차주 등 주차 별칭, W숫자, 누적/여태/지금까지, 이번 달/이번달
        _has_time_scope = (
            bool(alias_hit) and alias_hit != 'implicit'
            or bool(_re3.search(r'W\d{2}', message, _re3.I))
            or bool(_re3.search(r'\d{1,2}주차', message))  # "34주차" 같은 형태
            or bool(_re3.search(r'\d{1,2}월', message))   # "8월" 같은 형태
            or any(k in message for k in ['누적', '여태', '지금까지', '올해', '이번 달', '이번달', '월간'])
        )
        # 무의미/초단문 입력 가드
        _bare = re.sub(r'\s+', '', message)
        _has_meaning = bool(re.search(r'\d|매출|실적|계획|주차|진행|수량|얼마|몇|누적|모델', _bare))
        if len(_bare) <= 2 or (len(_bare) <= 8 and not _has_meaning):
            return {"answer": "무슨 말씀이신지 잘 모르겠어요. 예: '하바플레이트 35주차 매출'처럼 구체적으로 물어봐 주세요.", "sources": [], "corrected_query": None}
        _prev_had_scope = bool(sess.get('last_question_scope'))
        if not _has_time_scope and not _prev_had_scope:
            # 되묻지 않는다. 경영진이 쓰는 챗봇이라 한 번에 답이 나와야 한다.
            # 기준을 안 밝히면 '이번 달 누적'으로 답하고, 무엇 기준인지 문장에 적는다.
            _def_month = f"{_today_m.year}-{_today_m.month:02d}"
            try:
                _ans_d = _month_shipment_answer(last_project, _def_month, _mode_m,
                                                _want_models, _rev_kw, _want_weeks)
            except Exception as _e_d:
                _ans_d = None
                print(f"[chat] 기본(이번 달) 즉답 실패(무시): {_e_d}")
            if _ans_d:
                sess['last_month'] = _def_month
                sess['last_scope'] = 'month'
                sess['last_question_scope'] = True
                print(f"[chat] 기준 미지정 → 이번 달 {_def_month} 기본 답변")
                _src_d = ([{'key': last_project,
                            'label': _display_project_label(last_project)}]
                          if last_project and last_project != 'all' else [])
                return {'answer': _ans_d, 'sources': _src_d, 'corrected_query': None}
            _scope_month = _def_month
        sess['last_question_scope'] = True
        # 누적 질문이면 주차 태그 없이 진행, 아니면 이전 세션 주차 유지/오늘 기준
        _is_cum_q = any(k in message for k in ['여태', '지금까지', '누적', '올해', '전체 기간'])
        if not _is_cum_q:
            if last_week and last_week in {'W32','W33','W34','W35'}:
                cur_wk = int(last_week[1:])
            else:
                # 세션에 저장된 주차가 없으면 오늘 주차 폴백 (방금 set한 경우 그대로 유지됨)
                cur_wk = _dt_wk.date.today().isocalendar()[1]
            last_week = f'W{cur_wk:02d}'
            sess['last_week'] = last_week
        alias_hit = 'implicit'
        if f'[week:{last_week}]' not in message:
            message = f'[week:{last_week}] ' + message
        print(f'[chat] implicit alias → {last_week} (project={last_project})')
        # -----------------------------------------------------------
        # 월 키워드 감지 시 월 합계 컨텍스트를 변수에 저장 (system_prompt 정의 전이라 직접 참조 불가)
        # -----------------------------------------------------------
        _month_match = _re3.search(r'(\d{1,2})\s*월', message)
        _today = _dt_mod.now().date()
        _target_month_num = None
        _month_label = None
        if _month_match:
            _m = int(_month_match.group(1))
            _target_month_num = _m
            _month_label = f"{_today.year}-{_m:02d}"
        elif any(kw in message for kw in ['이번달', '이번 달', '이달']):
            _target_month_num = _today.month
            _month_label = f"{_today.year}-{_today.month:02d} (이번 달)"
        elif any(kw in message for kw in ['지난달', '저번달', '전월']):
            _prev = _today.month - 1 if _today.month > 1 else 12
            _target_month_num = _prev
            _month_label = f"{_today.year}-{_prev:02d} (지난 달)"

        # 월 키워드 있으면 월 합계 컨텍스트 계산 후 변수에 저장
        if _target_month_num:
            _month_str = f"{_today.year}-{_target_month_num:02d}"
            try:
                _proj_key = last_project if last_project != 'all' else 'hrva_plate'
                _wr = get_weekly_revenue(_proj_key, _month_str)
                _combined = _wr.get('combined', {})
                _total_rev = _combined.get('total', {}).get('revenue', 0)
                _weeks_list = _wr.get('weeks', [])
                _week_details = []
                for _w in _weeks_list:
                    _wc = _combined.get('weeks', {}).get(_w, {})
                    _week_details.append(f"{_w} 매출=${_wc.get('revenue',0):,}")
                _month_context = (
                    f" [월 합계 (권위 데이터, 주차 alias보다 우선): {_month_label} "
                    f"총 누적 매출=${_total_rev:,}. "
                    f"주차별 내역: {' / '.join(_week_details)}. "
                    f"이 값들을 그대로 인용해서 답변할 것. "
                    f"형식: '{_month_label} 총 매출은 $X,XXX입니다. (주차별: W32 $X / W33 $X / W34 $X / W35 $X)'. "
                    f"근거 표시 생략.]"
                )
                print(f"[chat] 월 컨텍스트 계산 완료: {_month_label} 총매출=${_total_rev:,}")
            except Exception as _e_mon:
                print(f"[chat] 월 컨텍스트 계산 실패: {_e_mon}")

    if alias_hit:
        last_week = f'W{cur_wk:02d}'
        sess['last_week'] = last_week
        if f'[week:{last_week}]' not in message:
            message = f'[week:{last_week}] ' + message
        # 명시적 alias: 프로젝트 미지정 시 전체로 자동 간주 ('몇 주차' 질문 제외)
        _is_week_only = any(k in message for k in ['몇 주차', '몇주차', '몇 주', '몇주'])
        _rev_kws = ['총', '합계', '얼마', '매출', '실적', '수량', '몇', '나올', '어떨', '예상', '예측', '전망', '출하']
        if not last_project and any(k in message for k in _rev_kws) and not _is_week_only:
            last_project = 'all'
            sess['last_project'] = last_project
        print(f'[chat] alias {alias_hit!r} → {last_week} (project={last_project})')
    # -----------------------------------------------------------
    # 데이터 없는 주차는 LLM 우회하고 즉시 응답
    # -----------------------------------------------------------
    valid_weeks = _known_weeks(last_project)
    # 사용자가 실제로 주차를 지정한 경우에만 '데이터 없음'으로 끊는다
    _asked_week = bool(alias_hit) and alias_hit != 'implicit'
    if _asked_week and valid_weeks and last_week not in valid_weeks:
        _wk_list = ', '.join(sorted(valid_weeks, key=lambda w: int(str(w).lstrip('Ww') or 0)))
        _no_data_msg = f'해당 주차({last_week}) 데이터는 아직 등록되지 않았습니다. 현재 등록된 주차: {_wk_list}.'
        _no_data_src = [{'key': last_project, 'label': '하바플레이트'}] if last_project == 'hrva_plate' else []
        return {'answer': _no_data_msg, 'sources': _no_data_src, 'corrected_query': None}

    # 음성 오인식 보정
    corrected = message
    try:
        from difflib import SequenceMatcher
        import unicodedata, re as _re2

        def _sim(a, b):
            c = SequenceMatcher(None, a, b).ratio()
            j = SequenceMatcher(None, unicodedata.normalize("NFKD", a), unicodedata.normalize("NFKD", b)).ratio()
            return max(c, j)

        voice_aliases = _load_learned_aliases().get("aliases", {})
        words = _re2.findall(r'[가-힣a-zA-Z0-9]+', message)
        for w in words:
            wl = w.lower()
            if wl in voice_aliases:
                corrected = corrected.replace(w, voice_aliases[wl])
                print(f"[chat] '{w}' → '{voice_aliases[wl]}'")
    except Exception as e:
        print(f"[chat] 보정 오류: {e}")

    # models.json 전체 데이터 수집
    try:
        data = _load_models()
        projects = data.get("projects", {})

        # 질문 유형 파악
        is_process = any(k in corrected for k in ['프로세스', '공정', '단계', '진행률', '완료', 'process'])
        is_price = any(k in corrected for k in ['판가', '재료비', '가격', 'price', 'cost'])

        context_parts = []
        relevant_projects = []

        msg_lower = corrected.lower()

        for pk, proj in projects.items():
            proj_info = next((p for p in _cl.get_projects(visible_only=True) if p.get("id") == pk), None)
            label = proj_info.get("label", pk) if proj_info else pk

            if (label.lower() not in msg_lower and pk.lower() not in msg_lower
                    and last_project not in ('all', pk)):
                continue

            relevant_projects.append({"key": pk, "label": label})

            models = proj.get("models", [])
            mass = [m for m in models if m.get("group") == "양산"]
            dev = [m for m in models if m.get("group") == "개발"]

            ctx = f"=== {label} ({pk}) ==="
            ctx += f"모델 수: 양산 {len(mass)}종, 개발 {len(dev)}종, 총 {len(models)}종"

            progresses = [m.get("progress", 0) for m in models if m.get("progress") is not None]
            if progresses:
                avg_prog = sum(progresses) / len(progresses)
                ctx += f"평균 진행률: {avg_prog:.1f}%"

            if proj.get("status_note"):
                ctx += f"현황: {proj['status_note']}"

            if proj.get("weekly_plan"):
                wp = proj["weekly_plan"]
                if isinstance(wp, dict):
                    ctx += f"주간 계획: {wp.get('title', '')} - {wp.get('content', '')[:100]}"
                else:
                    ctx += f"주간 계획: {str(wp)[:100]}"

            # 그룹 PO / 실적 / 잔량
            ws = proj.get("weekly_summary") or {}
            _spec_ctx = _load_board_spec(pk)
            if _spec_ctx:
                ctx += "그룹 현황 (PO/실적/잔량, 모델 합계): "
                for gname, gm in (("양산", mass), ("개발", dev)):
                    if not gm:
                        continue
                    _po = sum(_as_int(m.get("po_qty")) for m in gm)
                    _sh = sum(_as_int(m.get("shipped_qty")) for m in gm)
                    ctx += f"{gname} PO {_po} / 실적 {_sh} / 잔량 {max(0, _po - _sh)}; "
            elif ws:
                ctx += "그룹 현황 (PO/실적/잔량): "
                for gname in ("양산", "개발"):
                    g = ws.get(gname) or {}
                    if g:
                        ctx += (f"{gname} PO {g.get('po_qty', 0)} / 실적 {g.get('actual_total', 0)}"
                                f" / 잔량 {g.get('remaining', 0)}; ")
            if (ws.get("개발") or {}).get("price_fixed"):
                ctx += f"개발 단가 고정 ${ws['개발']['price_fixed']}; "

            # 주차별 매출 (weekly-revenue v2)
            try:
                # 같은 프로세스 내 직접 계산 (HTTP 호출 X → 타임아웃 원천 차단)
                month = _month_of_week(last_week) or _latest_data_month(pk)
                weeks = _get_month_weeks(month) or ["W32", "W33", "W34", "W35"]

                # 주차별 수량·매출은 보드·매출 카드와 같은 엔진(get_weekly_revenue)에서 받는다
                _wr = get_weekly_revenue(pk, month) or {}
                _grp = _wr.get('groups') or {}
                _yw = ((_grp.get('양산') or {}).get('weeks') or {})
                _dw = ((_grp.get('개발') or {}).get('weeks') or {})
                _ytot = ((_grp.get('양산') or {}).get('total') or {})
                _dtot = ((_grp.get('개발') or {}).get('total') or {})

                def _n(d, f):
                    return int((d or {}).get(f) or 0)

                ctx += f"주차별 매출 ({month}): "
                for w in weeks:
                    mv, dv = _yw.get(w) or {}, _dw.get(w) or {}
                    _mp, _ma = _n(mv, 'plan'), _n(mv, 'actual')
                    _dp, _da = _n(dv, 'plan'), _n(dv, 'actual')
                    # 실적이 0이면 '계획 기준 예상'임을 문장에 박아 둔다.
                    # 그래야 LLM 이 예상 매출을 실적으로 바꿔 말하지 않는다.
                    _mr_show = (f"실적0→계획{_mp}대 예상${_n(mv, 'plan_revenue'):,}"
                                if _ma == 0 and _mp > 0 else f"${_n(mv, 'revenue'):,}")
                    _dr_show = (f"실적0→계획{_dp}대 예상${_n(dv, 'plan_revenue'):,}"
                                if _da == 0 and _dp > 0 else f"${_n(dv, 'revenue'):,}")
                    ctx += f"{w} 양산 {_mp}/{_ma} {_mr_show}, 개발 {_dp}/{_da} {_dr_show}; "
                ctx += (f"합계: 양산 {_n(_ytot,'plan')}/{_n(_ytot,'actual')} ${_n(_ytot,'revenue'):,}"
                        f"(계획 기준 ${_n(_ytot,'plan_revenue'):,}), "
                        f"개발 {_n(_dtot,'plan')}/{_n(_dtot,'actual')} ${_n(_dtot,'revenue'):,}"
                        f"(계획 기준 ${_n(_dtot,'plan_revenue'):,}), "
                        f"전체 매출 ${_n(_ytot,'revenue') + _n(_dtot,'revenue'):,}")
                ctx += (" [산출 기준: 양산 매출 = 모델별 판가(price) × 수량 합산 (고정 단가 아님). "
                        "계획 기준 예상 매출도 같은 판가로 계산한 값이다. "
                        "개발 매출 = 실적 × $3,400 고정. 계획(plan)과 실적(actual)은 서로 다른 값이다.]")
            except Exception as e:
                print(f"[chat] weekly 계산 실패 {pk}: {e}")
                rev = {}
                try:
                    rev = get_weekly_revenue(pk, _month_of_week(last_week) or _latest_data_month(pk)) or {}
                except Exception as _e_rev:
                    print(f"[chat] weekly-revenue 폴백도 실패 {pk}: {_e_rev}")
                if rev.get("groups"):
                    m_rev = rev["groups"].get("양산", {})
                    d_rev = rev["groups"].get("개발", {})
                    ctx += f"주차별 매출 ({rev.get('month','')}): "
                    for w in rev.get("weeks", []):
                        mv = m_rev.get("weeks", {}).get(w, {})
                        dv = d_rev.get("weeks", {}).get(w, {})
                        ctx += f"{w} 양산 {mv.get('plan',0)}/{mv.get('actual',0)} ${mv.get('revenue',0):,}, 개발 {dv.get('plan',0)}/{dv.get('actual',0)} ${dv.get('revenue',0):,}; "
                    ctx += f"합계: 양산 {m_rev.get('total',{}).get('plan',0)}/{m_rev.get('total',{}).get('actual',0)} ${m_rev.get('total',{}).get('revenue',0):,}, 개발 {d_rev.get('total',{}).get('plan',0)}/{d_rev.get('total',{}).get('actual',0)} ${d_rev.get('total',{}).get('revenue',0):,}, 전체 매출 ${rev.get('combined_revenue',0):,}"
            except Exception as e:
                print(f"[chat] weekly-revenue 로드 실패 {pk}: {e}")

            if proj.get("types"):
                ctx += f"유형: {', '.join(proj['types'])}"

            issue_models = [m for m in models if m.get("issues", "").strip()]
            if issue_models:
                # 80자에서 자르면 '선적 스페이스 부' 처럼 말이 끊긴 채 넘어가고
                # LLM 이 그 자리에서 문장을 멈춰버린다. 넉넉히 준다.
                ctx += f"\n이슈 있는 모델 ({len(issue_models)}개):"
                for m in issue_models[:12]:
                    _it = " / ".join(x.strip().rstrip(" ,") for x in
                                     str(m.get("issues") or "").splitlines() if x.strip())
                    ctx += f"\n  - {m.get('id') or m.get('name')}: {_it[:300]}"

            if is_process and dev:
                ctx += "개발 모델 진행률:"
                for m in dev[:5]:
                    prog = m.get("progress", 0)
                    proc = m.get("process", [])
                    done = sum(1 for s in proc if s.get("actual") or s.get("status") == "완료")
                    total = len(proc)
                    ctx += f"  - {m.get('name')}: {prog}% ({done}/{total} 단계 완료)"

            if is_price:
                price_models = [m for m in models if m.get("price") or m.get("material_cost")]
                if price_models:
                    ctx += "가격 정보:"
                    for m in price_models[:5]:
                        p = m.get("price", 0)
                        c = m.get("material_cost", 0)
                        margin = ((p - c) / p * 100) if p > 0 else 0
                        ctx += f"  - {m.get('name')}: 판가 ${p:,}, 재료비 ${c:,}, 마진 {margin:.1f}%"

            context_parts.append(ctx)

        if not context_parts:
            context_parts.append("=== 전체 프로젝트 요약 ===")
            for pk, proj in projects.items():
                models = proj.get("models", [])
                mass = sum(1 for m in models if m.get("group") == "양산")
                dev = sum(1 for m in models if m.get("group") == "개발")
                label = next((p.get("label") for p in _cl.get_projects(visible_only=True) if p.get("id") == pk), pk)
                context_parts.append(f"{label}: 양산 {mass}종, 개발 {dev}종")

        context = "\n".join(context_parts)

        system_prompt = (
            "너는 반도체 사업부의 프로젝트 관리 어시스턴트다. "
            "주어진 [데이터]만을 근거로 한국어로 답한다.\n"
            "\n[사실 규칙]\n"
            "- 숫자·모델명·날짜는 [데이터]에 있는 값을 그대로 쓴다. 계산하거나 추정하지 않는다.\n"
            "- '권위 데이터'로 표시된 값이 있으면 다른 어떤 수치보다 그 값을 우선한다.\n"
            "- 계획(plan)과 실적(actual)을 반드시 구분한다. 수량 질문에는 실적만 답한다.\n"
            "- [데이터]에 없으면 '해당 데이터는 아직 등록되지 않았습니다'라고 분명히 말한다. "
            "모르는 것을 지어내지 않는다.\n"
            "\n[답변 방식] — 읽는 사람은 경영진이다. 짧게.\n"
            "- 최대 2문장. 첫 문장에 답(숫자)을 쓰고 끝낸다. 세 문장을 넘기지 않는다.\n"
            "- 어떤 기준인지는 문장 안에 짧게 박는다. 예: 'W35 하바플레이트 양산 매출 $296,850 (실적 기준).'\n"
            "- 질문을 되풀이하지 않는다. '말씀하신', '문의하신', '확인해 보니' 같은 도입부 금지.\n"
            "- '~입니다만', '참고로', '추가로', '도움이 되셨길' 같은 군더더기 금지.\n"
            "- 항목이 3개를 넘으면 줄바꿈으로 나열하되 항목당 한 줄, 최대 5줄.\n"
            "- 묻지 않은 배경 설명·모델 종수 나열·요약 반복은 넣지 않는다.\n"
            "- 경고나 단서는 꼭 필요할 때만, 반 문장으로.\n"
            "- 기준이 모호해도 되묻지 말고 가장 그럴듯한 기준(이번 달 누적)으로 답한 뒤 "
            "그 기준을 문장에 밝힌다.\n"
            "\n[표기]\n"
            "- 수량 단위는 '대'를 쓴다 ('종' 금지). 금액은 $1,234 형식.\n"
            "- '(근거: ...)' 같은 인용 표시는 붙이지 않는다."
        )
        # -----------------------------------------------------------
        # 답변 검증용: 권위 데이터로 만든 폴백 문장과 허용 수치
        # -----------------------------------------------------------
        # LLM 이 문장을 만들되, 금액/수량이 권위 데이터와 다르면 이 문장으로 되돌린다.
        _direct_answer = None
        _allowed_amounts = set()
        _allowed_qty = set()
        # -----------------------------------------------------------
        # 주차별 실적/매출 합계 백엔드 직접 계산 (all 프로젝트 질문 대응)
        # -----------------------------------------------------------
        _week_stats_ctx = ""
        if last_week and last_week.startswith('W'):
            try:
                _wdata = _load_models()
                _mass_a, _dev_a = 0, 0
                _mass_r, _dev_r = 0, 0
                _mass_p, _dev_p = 0, 0
                for _pk, _proj in _wdata.get('projects', {}).items():
                    if last_project and last_project not in ('all', _pk):
                        continue
                    _ws = _proj.get('weekly_summary', {})
                    for _g in ('양산', '개발'):
                        if _g not in _ws:
                            continue
                        _wv = _ws[_g].get('weeks', {}).get(last_week, {})
                        _pa = int(_wv.get('actual') or 0)
                        _pl = int(_wv.get('plan') or 0)
                        if _g == '양산':
                            _mass_a += _pa
                            _mass_p += _pl
                            # 매출은 아래 모델별 단가 루프에서 별도 계산
                            pass  # 양산 매출은 모델별 단가로 계산 (하단)
                        else:
                            _dev_a += _pa
                            _dev_p += _pl
                            _dev_price = float((_ws[_g].get('price_fixed') or 3400))
                            _dev_r += _pa * _dev_price
                # 양산 매출: weekly_summary actual이 모델별 합계와 다르면 weekly_summary를 절대 기준으로 사용
                # 모델별 데이터는 불완전할 수 있으므로, weekly_summary actual이 있으면 그것을 강제로 사용
                if _mass_a > 0:
                    # 모델별 합계 (참고용)
                    _mr = 0.0
                    for _pk2, _proj2 in _wdata.get('projects', {}).items():
                        if last_project and last_project not in ('all', _pk2):
                            continue
                        for _m in _proj2.get('models', []):
                            if _m.get('group') != '양산':
                                continue
                            for _mk, _bucket in (_m.get('weekly_plan') or {}).items():
                                _cell = _bucket.get(last_week, {}) if isinstance(_bucket, dict) else {}
                                _ma = int(_cell.get('actual') or 0)
                                if _ma > 0:
                                    _mr += _ma * float(_m.get('price') or _m.get('unit_price') or 0)
                    # weekly_summary actual과 모델별 합계가 다르면 weekly_summary를 신뢰
                    # 매출은 weekly-revenue 블록에서 정확히 계산하도록 0으로 둠
                    _mass_r = 0  # weekly-revenue에서 정확한 매출 주입 예정
                print(f"[chat] 주차통계 계산 중: _mass_a={_mass_a}, _dev_a={_dev_a}")
                if _mass_a > 0 or _dev_a > 0:
                    _week_stats_ctx = (f" [주차통계 (권위 데이터): {last_week} 기준 "
                                       f"양산 실적={_mass_a}대 (계획 {_mass_p}대), 매출=${_mass_r:,}; "
                                       f"개발 실적={_dev_a}대 (계획 {_dev_p}대), 매출=${_dev_r:,}; "
                                       f"총 실적={_mass_a + _dev_a}대, 총 매출=${_mass_r + _dev_r:,}. "
                                       f"이 수치를 그대로 인용해서 답변할 것. 근거 생략.]")
            except Exception as e:
                import traceback
                print(f"[chat] 주차통계 계산 오류: {e}")
                traceback.print_exc()
        # -----------------------------------------------------------
        # 예측/전망 질문 감지 + 통계 자동 계산
        # -----------------------------------------------------------
        is_forecast = any(k in corrected for k in ['예상', '전망', '다음주', '다음 주', '앞으로', '추세', '리스크', '완료 가능'])
        forecast_note = ""
        if is_forecast and last_project:
            try:
                import datetime as _dtf
                fmonth = _dtf.date.today().strftime("%Y-%m")
                fdata = _load_models()
                fproj = fdata.get("projects", {}).get(last_project, {})
                fmodels = fproj.get("models", [])
                fweeks = ["W32", "W33", "W34", "W35"]
                mass_weekly = {}
                for w in fweeks:
                    tp, ta = 0, 0
                    for m in fmodels:
                        if m.get("group") != "양산":
                            continue
                        wp = (m.get("weekly_plan") or {}).get(fmonth, {})
                        cell = wp.get(w, {})
                        tp += cell.get("plan", 0)
                        ta += cell.get("actual", 0)
                    mass_weekly[w] = {"plan": tp, "actual": ta}
                vals = [v["actual"] for v in mass_weekly.values() if v["actual"] > 0]
                plans = [v["plan"] for v in mass_weekly.values() if v["plan"] > 0]
                if len(vals) >= 2:
                    avg_a = sum(vals) / len(vals)
                    avg_p = sum(plans) / len(plans) if plans else 0
                    achieve = round(vals[-1] / plans[-1] * 100) if plans and plans[-1] > 0 else 0
                    forecast_note = f" [예측통계: 최근 {len(vals)}주 양산 평균 실적 {avg_a:.0f}대, 평균 계획 {avg_p:.0f}대, 최근 달성률 {achieve}%.]"
                elif len(vals) == 1:
                    forecast_note = f" [예측통계: 데이터 1주뿐 ({vals[0]}대). 추세 판단 불가.]"
                else:
                    forecast_note = " [예측통계: 주차별 실적 데이터 없음. 예측 불가.]"
            except Exception as e:
                print(f"[chat] 예측 계산 오류: {e}")
        # -----------------------------------------------------------
        # "몇 주차야" 질문 감지 → 주차 번호만 간결하게 응답
        # -----------------------------------------------------------
        # ── 자주 묻는 질문은 데이터에서 바로 답한다 (LLM 우회) ──
        # 주차·매출·수량 질문은 아래 기존 로직이 더 정확하므로 넘긴다.
        _skip_intent = any(k in _user_text for k in ['매출', '수량', '얼마', '몇 대', '몇대', '대수', '출하량']) \
            or bool(alias_hit)
        if not _skip_intent:
            try:
                import chat_intents as _ci
                _labels = []
                try:
                    _labels = [p.get('label') or p.get('id')
                               for p in _cl.get_projects(visible_only=True)]
                except Exception:
                    pass
                _plabel = next((p.get('label') for p in _cl.get_projects(visible_only=True)
                                if p.get('id') == last_project), None) if last_project else None
                _direct_ans = _ci.resolve(_user_text, last_project, {
                    'load_models': _load_models,
                    'process_progress': _process_progress,
                    'process_current': _process_current,
                    'known_weeks': _known_weeks,
                    'project_label': _plabel or (last_project or ''),
                    'project_labels': [x for x in _labels if x],
                    # 이번 주가 언제인지는 서버만 안다. 챗 답변이 지난주
                    # 숫자를 오늘 것처럼 말하지 않게 같이 넘긴다.
                    'now_week': 'W%d' % datetime.now().isocalendar()[1],
                    'now_month': datetime.now().strftime('%Y-%m'),
                })
                if _direct_ans:
                    print(f"[chat] 정형 답변 매칭 → {_user_text[:30]}")
                    return {
                        'answer': _direct_ans,
                        'sources': ([{'key': last_project, 'label': _plabel or last_project}]
                                    if last_project and last_project != 'all' else []),
                        'corrected_query': None,
                    }
            except Exception as _e_ci:
                print(f"[chat] 정형 답변 실패(무시): {_e_ci}")

        if any(k in corrected for k in ['몇 주차', '몇주차', '몇 주', '몇주', '주차야', '주차야?', '주차 알려줘']):
            answer = f"이번 주는 {last_week}입니다."
            return {"answer": answer, "sources": [{"key": last_project, "label": "하바플레이트"}] if last_project == 'hrva_plate' else [], "corrected_query": None}
        # -----------------------------------------------------------
        # 누적 매출 질문 처리 ('여태까지', '지금까지', '누적', '올해')
        # -----------------------------------------------------------
        _is_cumulative = any(k in message for k in ['여태', '지금까지', '누적', '올해', '전체 기간'])
        if _is_cumulative and last_project in {'all', 'hrva_plate'}:
            try:
                _projs = ['hrva_plate'] if last_project == 'all' else [last_project]
                _cum_rev = 0
                _cum_detail = []
                for _pk in _projs:
                    _wrd = get_weekly_revenue(_pk, _month_of_week(last_week) or _latest_data_month(_pk))
                    for _gname, _gkey in [('양산','양산'), ('개발','개발')]:
                        _g = _wrd.get('groups',{}).get(_gkey,{})
                        for _w, _wv in (_g.get('weeks') or {}).items():
                            _cum_rev += _wv.get('revenue', 0)
                    _tot = _wrd.get('combined',{}).get('total',{})
                    _cum_detail.append(f"{_pk}: ${_tot.get('revenue', 0):,}")
                _proj_label = '반도체사업부 전체' if last_project == 'all' else '하바플레이트'
                system_prompt += (
                    f" [누적 매출 (권위 데이터): 2026-08 기준 W32~W35 누적 실적 매출 합계는 ${_cum_rev:,}. "
                    f"({_proj_label}) 이 값을 그대로 인용해서 답변할 것. 근거 표시 생략.]"
                )
                print(f"[chat] 누적 매출 주입: ${_cum_rev:,} ({_proj_label})")
            except Exception as _e_cum:
                print(f"[chat] 누적 매출 주입 실패: {_e_cum}")
        # -----------------------------------------------------------
        # 전체 프로젝트 합계 계산 (project='all')
        # -----------------------------------------------------------
        if alias_hit and last_project == 'all' and last_week in {'W32','W33','W34','W35'}:
            try:
                # 모든 프로젝트의 매출 합계 계산
                _all_projects = ['hrva_plate']  # 현재는 하바플레이트만 있음, 추후 확장
                _total_mass_rev = 0
                _total_dev_rev = 0
                _total_mass_plan_rev = 0
                _total_dev_plan_rev = 0

                for _proj_key in _all_projects:
                    _wr_data = get_weekly_revenue(_proj_key, _month_of_week(last_week) or _latest_data_month(_proj_key))
                    _mg = _wr_data.get('groups',{}).get('양산',{})
                    _dg = _wr_data.get('groups',{}).get('개발',{})
                    _mw = _mg.get('weeks',{}).get(last_week,{})
                    _dw = _dg.get('weeks',{}).get(last_week,{})

                    _m_plan, _m_act, _m_rev = _mw.get('plan',0), _mw.get('actual',0), _mw.get('revenue',0)
                    _d_plan, _d_act, _d_rev = _dw.get('plan',0), _dw.get('actual',0), _dw.get('revenue',0)

                    _total_mass_rev += _m_rev
                    _total_dev_rev += _d_rev

                    # 계획 기준 예상 매출 — 모델별 판가로 이미 계산돼 있다.
                    # 예전엔 실적이 0 이면 $3,350 고정 단가를 곱했다.
                    _m_plan_rev = int(_mw.get('plan_revenue') or 0)
                    _d_plan_rev = int(_dw.get('plan_revenue') or 0)

                    _total_mass_plan_rev += _m_plan_rev
                    _total_dev_plan_rev += _d_plan_rev

                _total_actual_rev = _total_mass_rev + _total_dev_rev
                _total_plan_rev = _total_mass_plan_rev + _total_dev_plan_rev

                # 답변 기준 결정 (전체 프로젝트)
                if _total_actual_rev > 0:
                    _all_basis = f"실적 기준 총 매출 ${_total_actual_rev:,} (양산 ${_total_mass_rev:,}, 개발 ${_total_dev_rev:,})"
                elif _total_plan_rev > 0:
                    _all_basis = f"실적 미발생, 계획 기준 예상 총 매출 ${_total_plan_rev:,} (양산 예상 ${_total_mass_plan_rev:,}, 개발 예상 ${_total_dev_plan_rev:,})"
                else:
                    _all_basis = "해당 주차 전체 프로젝트 계획/실적 모두 없음, 매출 $0"
                system_prompt += (
                    f" [전체 프로젝트 매출 (권위 데이터): {last_week} 주차 반도체사업부 전체 프로젝트 합계. {_all_basis}. "
                    f"이 값을 그대로 인용해서 답변할 것. 근거 표시 생략.]"
                )
                print(f"[chat] 전체 프로젝트 주입: {last_week} 실적 ${_total_actual_rev:,}, 예상 ${_total_plan_rev:,}")
            except Exception as _e_all:
                print(f"[chat] 전체 프로젝트 주입 실패: {_e_all}")
        # -----------------------------------------------------------
        # /weekly-revenue 직접 계산 결과를 last_week 컨텍스트로 강제 주입
        # -----------------------------------------------------------
        if alias_hit and last_project in ('hrva_plate', 'all') and last_week in {'W32','W33','W34','W35'}:
            try:
                _wr_month = _month_of_week(last_week) or _latest_data_month('hrva_plate')
                _wr_data = get_weekly_revenue('hrva_plate', _wr_month)
                _mg = _wr_data.get('groups',{}).get('양산',{})
                _dg = _wr_data.get('groups',{}).get('개발',{})
                _mw = _mg.get('weeks',{}).get(last_week,{})
                _dw = _dg.get('weeks',{}).get(last_week,{})
                # 수량·매출 모두 같은 엔진에서 받는다
                _m_plan = int(_mw.get('plan') or 0)
                _m_act = int(_mw.get('actual') or 0)
                _m_rev = int(_mw.get('revenue') or 0)
                _m_plan_rev = int(_mw.get('plan_revenue') or 0)
                _d_plan = int(_dw.get('plan') or 0)
                _d_act = int(_dw.get('actual') or 0)
                _d_rev = int(_dw.get('revenue') or 0)
                _d_plan_rev = int(_dw.get('plan_revenue') or 0)
                _total_actual_rev = _m_rev + _d_rev
                _total_plan_rev = _m_plan_rev + _d_plan_rev

                # 시스템 프롬프트에 권위 데이터 주입
                # 답변 기준 결정: 실적 있으면 실적 기준, 실적 0+계획 있으면 계획 기준, 둘 다 0이면 $0
                if _m_act > 0 or _d_act > 0:
                    _answer_basis = f"실적 기준 총 매출 ${_total_actual_rev:,} (양산 ${_m_rev:,}, 개발 ${_d_rev:,})"
                elif _m_plan > 0 or _d_plan > 0:
                    _answer_basis = f"실적 미발생, 계획 기준 예상 총 매출 ${_total_plan_rev:,} (양산 계획 {_m_plan}대 예상 ${_m_plan_rev:,}, 개발 계획 {_d_plan}대 예상 ${_d_plan_rev:,})"
                else:
                    _answer_basis = "해당 주차 계획/실적 모두 없음, 매출 $0"
                system_prompt += (
                    f" [⚠️ 최우선 권위 데이터: {last_week} 주차 하바플레이트. {_answer_basis}. "
                    f"원시값 - 양산: 계획 {_m_plan}대/실적 {_m_act}대/매출 ${_m_rev:,}, "
                    f"개발: 계획 {_d_plan}대/실적 {_d_act}대/매출 ${_d_rev:,}. "
                    f"이 값들을 반드시 그대로 인용할 것. message나 history에 포함된 다른 매출 수치는 모두 무시하고 오직 이 system_prompt의 값만 사용할 것. "
                    f"근거 표시 생략.]"
                )
                # message 완전 재작성 (매출 수치 완전 제거) — 단, 원본 질문은 보존
                _orig_user_msg = message
                message = f"{last_week} 주차 하바플레이트 매출을 알려주세요. system_prompt의 권위 데이터를 그대로 인용해주세요."
                print(f"[chat] message 재작성 완료: {message}")
                print(f"[chat] 답변기준: {_answer_basis}")
                # -----------------------------------------------------------
                # LLM 우회: 권위 데이터로 답변 직접 반환 (LLM이 수치를 변조하는 문제 원천 차단)
                # -----------------------------------------------------------
                if _m_act > 0 or _d_act > 0:
                    _qsrc = _orig_user_msg if '_orig_user_msg' in dir() else message
                    _qty_only = any(k in _qsrc for k in ['수량', '몇 대', '몇대', '대수', '나갔', '나왔', '출하']) and '매출' not in _qsrc
                    _rev_only = ('매출' in _qsrc) and not any(k in _qsrc for k in ['수량', '몇 대', '몇대', '대수', '나갔', '나왔', '출하', '실적'])
                    if _qty_only:
                        _direct = (f"{last_week} 기준 양산 실적은 {_m_act}대, 개발 실적은 {_d_act}대입니다. "
                                   f"총 실적은 {_m_act + _d_act}대입니다.")
                    elif _rev_only:
                        _direct = (f"{last_week} 주차 하바플레이트의 양산 매출은 ${_m_rev:,.0f}, "
                                   f"개발 매출은 ${_d_rev:,.0f}입니다. 총 매출은 ${_total_actual_rev:,.0f}입니다.")
                    else:
                        _direct = (f"{last_week} 주차 하바플레이트의 양산 매출은 ${_m_rev:,.0f}, "
                                   f"개발 매출은 ${_d_rev:,.0f}입니다. 총 매출은 ${_total_actual_rev:,.0f}입니다. "
                                   f"양산 실적은 {_m_act}대, 개발 실적은 {_d_act}대입니다.")
                    _direct_answer = _direct
                    _allowed_amounts = {int(round(_m_rev)), int(round(_d_rev)),
                                        int(round(_total_actual_rev))}
                    _allowed_qty = {_m_act, _d_act, _m_act + _d_act, _m_plan, _d_plan}
                    print(f"[chat] 권위 폴백 준비: {_direct}")
                # 주차통계 블록이 이미 계산한 값이 있으면 우선 사용 (모델별 실제 단가 기반)
                _has_ctx = bool(_week_stats_ctx) and "권위 데이터" in _week_stats_ctx
                if _has_ctx:
                    import re as _re_extract
                    _m = _re_extract.search(r"양산 매출=\$([0-9,]+)", _week_stats_ctx)
                    _m2 = _re_extract.search(r"개발 매출=\$([0-9,]+)", _week_stats_ctx)
                    if _m and _m2:
                        _m_rev = int(_m.group(1).replace(",", ""))
                        _d_rev = int(_m2.group(1).replace(",", ""))
                        print(f"[chat] 주차통계 값으로 덮어쓰기: 양산 ${_m_rev:,}, 개발 ${_d_rev:,}")
                    else:
                        print(f"[chat] weekly-revenue 주입: {last_week} 양산 {_m_act}/{_m_plan} ${_m_rev:,}, 개발 {_d_act}/{_d_plan} ${_d_rev:,}")
                else:
                    print(f"[chat] weekly-revenue 주입: {last_week} 양산 {_m_act}/{_m_plan} ${_m_rev:,}, 개발 {_d_act}/{_d_plan} ${_d_rev:,}")
            except Exception as _e_wr:
                print(f"[chat] weekly_revenue 컨텍스트 주입 실패: {_e_wr}")
        system_prompt += _week_stats_ctx + forecast_note
        system_prompt += ("\n(보강) 수량 질문에는 실적(actual)만 답한다. 실적이 0이면 '실적 0대'라고 명확히 말하고, "
                          "계획이 있으면 '계획은 N대'라고 덧붙인다. "
                          "PO 수량은 아직 연동 전 데이터이므로 출하·실적·매출 답변에서 언급하지 않는다.")
        # 월 컨텍스트 추가 (정의 전에 계산된 변수)
        if _month_context:
            system_prompt += _month_context
            print("[chat] 월 컨텍스트 주입 완료")
        # 주차 태그 강제 규칙
        if alias_hit and last_week:
            system_prompt += (
                f"\n[{last_week} 주차 질문 규칙]\n"
                f"- 이 질문은 {last_week} 기준이다. 다른 주차 수치는 인용하지 않는다.\n"
                f"- '권위 데이터' 섹션의 plan/actual/revenue 값을 그대로 쓴다. 직접 계산하지 않는다.\n"
                f"- 실적이 0이고 계획이 있으면 '{last_week} 실적은 아직 없고, 계획 기준 예상 매출은 $X입니다' 처럼 "
                f"실적 미발생임을 먼저 밝힌 뒤 계획 기준 값을 말한다. 계획도 0일 때만 $0이라고 답한다.\n"
                f"- '몇 주차야' 류 질문에는 주차 번호만 답하고 실적·매출은 붙이지 않는다."
            )
        # -----------------------------------------------------------
        # 벡터 검색: 규칙으로 못 잡는 비고·이슈·자재 메모를 배경으로 붙인다
        # -----------------------------------------------------------
        try:
            _rag_maybe_refresh()
            _rag_txt = _rag_context(_user_text)
        except Exception as _e_rag:
            _rag_txt = ""
            print(f"[chat] RAG 보조 실패(무시): {_e_rag}")
        if _rag_txt:
            context = context + "\n\n[참고 메모]\n" + _rag_txt
            system_prompt += ("\n[참고 메모] 는 배경 설명일 뿐이다. 숫자는 반드시 [데이터]의 "
                              "권위 값을 쓰고, 참고 메모의 숫자는 인용하지 않는다. "
                              "질문이 '왜/무슨 이슈/특이사항' 류일 때만 참고 메모를 근거로 쓴다.")
            print(f"[chat] RAG 컨텍스트 {len(_rag_txt)}자 주입")

        user_prompt = f"[데이터]\n{context}\n\n[질문]\n{corrected}"

        if client:
            resp = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.15,
                max_tokens=320,
            )
            answer = resp.choices[0].message.content or ""
            # 근거 표시 강제 제거
            import re as _re_clean1
            answer = _re_clean1.sub(r'\(근거:\s*[^)]+\)', '', answer).strip()
            # -----------------------------------------------------------
            # 수치 검증: 권위 데이터에 없는 금액/수량을 말하면 폴백 문장으로 교체
            # -----------------------------------------------------------
            if _direct_answer:
                _bad = _answer_number_mismatch(answer, _allowed_amounts, _allowed_qty)
                if _bad:
                    print(f"[chat] 수치 불일치 {_bad} → 권위 폴백 사용")
                    answer = _direct_answer
            if not answer.strip() and _direct_answer:
                answer = _direct_answer
        else:
            answer = _direct_answer or f"조회 결과:\n{context[:500]}"

        answer = _strip_useless_caveats(answer)

        return {
            "answer": answer,
            "sources": relevant_projects,
            "corrected_query": corrected if corrected != message else None
        }

    except Exception as e:
        return {"answer": "", "sources": [], "error": f"chat_failed: {e}"}


# 벡터 인덱스 상태 (몇 조각이 언제 만들어졌는지).
@app.get("/admin/rag/status")
def rag_status(_admin: int = Depends(get_admin_session)):
    import datetime as _dtr
    out = {"ready": False, "count": 0, "built_at": "", "kinds": {}}
    try:
        out["ready"] = _vs.is_ready()
        if _vs.META_PATH.exists():
            meta = json.loads(_vs.META_PATH.read_text(encoding="utf-8"))
            out["count"] = len(meta)
            for m in meta:
                k = m.get("kind") or "note"
                out["kinds"][k] = out["kinds"].get(k, 0) + 1
        if _vs.INDEX_PATH.exists():
            out["built_at"] = _dtr.datetime.fromtimestamp(
                _vs.INDEX_PATH.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except Exception as e:
        out["error"] = str(e)
    return out


# 지금 데이터로 벡터 인덱스를 다시 만든다
@app.post("/admin/rag/rebuild")
def rag_rebuild(_admin: int = Depends(get_admin_session)):
    try:
        return _rag_rebuild()
    except Exception as e:
        return {"ok": False, "reason": f"failed: {e}"}


KPI_HISTORY_FILE = BASE_DIR / "kpi_history.json"
PROJECT_PROFILES_FILE = BASE_DIR / "project_profiles.json"

# ============================================================
#  PPT 표에서 출하 실적 읽기
# ============================================================
def _extract_tables_from_pptx(file_path) -> list:
    from pptx import Presentation as _Presentation
    tables = []
    try:
        prs = _Presentation(str(file_path))
    except Exception:
        return []

    for s_idx, slide in enumerate(prs.slides, start=1):
        # 슬라이드 전체 텍스트 수집
        slide_texts = []
        slide_title = ""
        for shape in slide.shapes:
            try:
                if shape.has_text_frame:
                    tf_text = "\n".join(
                        p.text for p in shape.text_frame.paragraphs if p.text
                    ).strip()
                    if tf_text:
                        slide_texts.append(tf_text)
                        if not slide_title:
                            slide_title = tf_text.split("\n")[0]
            except Exception:
                continue

        nearby_text = "\n".join(slide_texts)

        # 슬라이드 안의 표 추출
        for shape in slide.shapes:
            try:
                if not shape.has_table:
                    continue
                tbl = shape.table
                rows = []
                for row in tbl.rows:
                    cells = []
                    for cell in row.cells:
                        try:
                            txt = cell.text_frame.text if cell.text_frame else ""
                        except Exception:
                            txt = ""
                        cells.append((txt or "").strip())
                    rows.append(cells)
                tables.append({
                    "slide_index": s_idx,
                    "slide_title": slide_title,
                    "nearby_text": nearby_text,
                    "rows": rows,
                })
            except Exception:
                continue

    return tables


# 표가 '출하 계획 및 실적' 관련인지 판정.
def _is_shipping_plan_table(table_dict: dict) -> bool:
    if not isinstance(table_dict, dict):
        return False
    keywords = [
        "모델 별 출하 계획 및 실적",
        "모델별 출하 계획 및 실적",
        "출하 계획 및 실적",
        "주차별 출하실적",
        "주차별 출하 실적",
    ]
    # 슬라이드 주변 텍스트에서 키워드 탐지
    nearby = (table_dict.get("nearby_text") or "").replace(" ", "")
    for kw in keywords:
        if kw.replace(" ", "") in nearby:
            return True
    # 표 헤더에서도 탐지 (첫 3행)
    rows = table_dict.get("rows") or []
    header_text = " ".join(
        " ".join(r) for r in rows[:3] if isinstance(r, list)
    ).replace(" ", "")
    for kw in ["W27", "W28", "PO", "누적합계", "누적 합계"]:
        if kw.replace(" ", "") in header_text:
            # 주차 헤더가 있는 표면 후보로 인정
            return True
    return False


# PPT에서 출하 계획 관련 표만 추출.
def _find_shipping_plan_tables(file_path) -> list:
    all_tables = _extract_tables_from_pptx(file_path)
    return [t for t in all_tables if _is_shipping_plan_table(t)]


# 여러 표 중 진짜 출하 계획 표를 하나만 선택.
def _pick_primary_shipping_table(tables: list, project_key: str) -> dict | None:
    if not tables:
        return None
    profile = _get_project_profile(project_key) or {}
    profile_models = {
        (m.get("display_name") or "").strip()
        for m in (profile.get("models") or [])
    }

    candidates = []
    for t in tables:
        rows = t.get("rows") or []
        if len(rows) < 3:
            continue
        r1 = rows[0]
        r1_txt = " ".join(r1)
        r1_first = (r1[0] or "").strip() if r1 else ""
        # 조건 1: 첫 셀 '구분'
        if "구분" not in r1_first:
            continue
        # 조건 2: 누적 합계 OR (PO + 실적/출하) 조합 존재
        r1_norm = r1_txt.replace(" ", "").replace("\n", "")
        has_cumulative = "누적" in r1_norm
        has_po_group = ("PO수량" in r1_norm or "PO" in r1_norm) and ("실적" in r1_norm or "출하" in r1_norm)
        if not (has_cumulative or has_po_group):
            continue
        # 조건 3: 데이터 행 첫 컬럼에 프로파일 모델 존재
        data_models = set()
        for row in rows[2:]:
            if not row:
                continue
            first = (row[0] or "").strip()
            if first:
                data_models.add(first)
        if profile_models and not (profile_models & data_models):
            # 프로파일 모델과 하나도 매칭 안 됨
            continue
        candidates.append(t)

    if not candidates:
        return None
    # 여러 개면 데이터 행이 가장 많은 것 선택
    candidates.sort(key=lambda x: len(x.get("rows") or []), reverse=True)
    return candidates[0]


# 표 → KPI 스키마로 변환.
def _shipping_table_to_kpi_data(table: dict, project_key: str, file_name: str = "") -> dict:
    warnings = []
    profile = _get_project_profile(project_key) or {}
    profile_models = {
        (m.get("display_name") or "").strip(): m
        for m in (profile.get("models") or [])
    }

    rows = table.get("rows") or []
    header_info = _parse_shipping_table_header(rows)
    columns = header_info["columns"]
    current_month_str = header_info["current_month"]  # 예: "7월"

    # 연도 판별: 파일명에서 추출
    year = None
    parsed = _parse_report_filename(file_name or "") if file_name else {}
    date_str = parsed.get("date") if parsed else None
    if date_str:
        try:
            year = int(date_str.split("-")[0])
        except Exception:
            pass
    if not year:
        from datetime import datetime as _dt
        year = _dt.now().year

    # 파일명 월 vs 표 현재 월 일치 확인
    file_month = None
    if date_str:
        try:
            file_month = int(date_str.split("-")[1])
        except Exception:
            pass
    table_month = None
    if current_month_str and current_month_str.endswith("월"):
        try:
            table_month = int(current_month_str[:-1])
        except Exception:
            pass
    if file_month and table_month and file_month != table_month:
        warnings.append(
            f"파일명 월({file_month}월)과 표의 현재 월({table_month}월)이 다릅니다"
        )

    def _month_key(month_str):
        if not month_str or not month_str.endswith("월"):
            return None
        try:
            m = int(month_str[:-1])
            return f"{year:04d}-{m:02d}"
        except Exception:
            return None

    def _week_key(week_str):
        if not week_str or not week_str.startswith("W"):
            return None
        num = week_str[1:]
        if not num.isdigit():
            return None
        return f"{year:04d}-W{int(num):02d}"

    def _to_int(v):
        if v is None:
            return None
        s = str(v).strip()
        if s in ("", "-", "·", "N/A"):
            return None
        try:
            return int(float(s.replace(",", "")))
        except Exception:
            return None

    # 데이터 행 순회 (R4부터)
    models_data = []
    for row in rows[2:]:
        if not row:
            continue
        model_name = (row[0] or "").strip()
        if not model_name:
            continue
        if model_name in ("합계", "총계", "TOTAL"):
            continue  # 합계 행은 파싱 대상 아님 (검증용, 이번엔 스킵)

        # 프로파일 매칭
        profile_model = profile_models.get(model_name)
        if not profile_model:
            warnings.append(f"프로파일에 없는 모델: '{model_name}' (project={project_key})")
            continue

        model_id = profile_model.get("model_id") or f"{project_key}::{model_name}"

        months_data = {}
        weeks_data = {}
        cumulative = {"po": None, "shipped": None}

        for col in columns:
            idx = col["index"]
            v = _to_int(row[idx]) if idx < len(row) else None
            kind = col["kind"]

            if kind == "month_plan":
                mk = _month_key(col["month"])
                if mk:
                    months_data.setdefault(mk, {})["plan"] = v
            elif kind == "month_actual":
                mk = _month_key(col["month"])
                if mk:
                    months_data.setdefault(mk, {})["actual"] = v
            elif kind == "week_plan":
                wk = _week_key(col["week"])
                if wk:
                    weeks_data.setdefault(wk, {})["plan"] = v
            elif kind == "week_actual":
                wk = _week_key(col["week"])
                if wk:
                    weeks_data.setdefault(wk, {})["actual"] = v
            elif kind == "month_total_plan":
                mk = _month_key(col["month"])
                if mk:
                    months_data.setdefault(mk, {})["plan"] = v
            elif kind == "month_total_actual":
                mk = _month_key(col["month"])
                if mk:
                    months_data.setdefault(mk, {})["actual"] = v
            elif kind == "cumulative_po":
                cumulative["po"] = v
            elif kind == "cumulative_shipped":
                cumulative["shipped"] = v
            elif kind == "cumulative_remaining":
                cumulative["remaining"] = v
            elif kind == "yearly_actual":
                cumulative["yearly_actual"] = v
        # -----------------------------------------------------------
        # 주차 실적/계획을 월별로 합산해서 월 데이터 보정
        # -----------------------------------------------------------
        # 규칙: 표 헤더에서 이미 "이 W##이 어느 월 컬럼 아래 있는지" 알고 있으므로,
        #       ISO 주차 계산 없이 헤더의 month 정보를 그대로 사용
        # 필요한 매핑: week_key(2026-W27) -> month_str("7월") -> month_key("2026-07")
        week_to_month = {}  # "2026-W27" -> "2026-07"
        for col in columns:
            if col.get("kind") in ("week_plan", "week_actual"):
                w = col.get("week")  # "W27"
                m = col.get("month")  # "7월"
                if w and m:
                    wk_full = _week_key(w)  # "2026-W27"
                    mk_full = _month_key(m)  # "2026-07"
                    if wk_full and mk_full:
                        week_to_month[wk_full] = mk_full

        # 주차 데이터를 월별로 합산
        week_by_month = {}
        for wk, wvals in weeks_data.items():
            mk = week_to_month.get(wk)
            if not mk:
                continue
            bucket = week_by_month.setdefault(mk, {"plan": [], "actual": []})
            if wvals.get("plan") is not None:
                bucket["plan"].append(wvals.get("plan"))
            if wvals.get("actual") is not None:
                bucket["actual"].append(wvals.get("actual"))

        # 월 데이터에 반영 (기존 값 우선, 없으면 합산값 채움)
        for mk, bucket in week_by_month.items():
            entry = months_data.setdefault(mk, {})
            if entry.get("actual") is None and bucket["actual"]:
                entry["actual"] = sum(bucket["actual"])
            if entry.get("plan") is None and bucket["plan"]:
                entry["plan"] = sum(bucket["plan"])

        models_data.append({
            "model_id": model_id,
            "display_name": model_name,
            "months": months_data,
            "weeks": weeks_data,
            "cumulative": cumulative,
        })

    return {
        "project_key": project_key,
        "report_month": f"{year:04d}-{table_month:02d}" if table_month else None,
        "report_year": year,
        "models": models_data,
        "warnings": warnings,
    }

# ============================================================
#  프로젝트 프로필 · PPT → KPI 반영
# ============================================================
def _load_project_profiles() -> dict:
    try:
        import json as _json
        with open(PROJECT_PROFILES_FILE, "r", encoding="utf-8") as f:
            data = _json.load(f)
        if not isinstance(data, dict):
            return {"profiles": {}}
        if "profiles" not in data or not isinstance(data.get("profiles"), dict):
            return {"profiles": {}}
        return data
    except FileNotFoundError:
        return {"profiles": {}}
    except Exception:
        return {"profiles": {}}


# 특정 프로젝트 프로파일 반환. 없으면 None.
def _get_project_profile(project_key: str) -> dict | None:
    if not project_key:
        return None
    data = _load_project_profiles()
    return (data.get("profiles") or {}).get(project_key)


# PPT 업로드 후 자동 KPI 추출 훅.
def _auto_extract_kpi_from_pptx(
    saved_file_path,
    file_name: str,
    doc_id: str,
    project_id_hint=None,
    products=None,
) -> dict:
    result = {
        "attempted": False,
        "project_key": None,
        "ok": False,
        "reason": None,
        "months_count": 0,
        "weeks_count": 0,
        "cumulative_updated": False,
    }
    try:
        # -----------------------------------------------------------
        # project_key 결정
        # -----------------------------------------------------------
        project_key = None

        # 1-a. 명시적 힌트 우선
        if project_id_hint:
            project_key = str(project_id_hint).strip() or None

        # 1-b. products에서 자동 매칭
        if not project_key and products:
            try:
                from project_templates import _match_project_key
                for p in products:
                    if not isinstance(p, dict):
                        continue
                    name = (p.get("name") or p.get("product") or "").strip()
                    if name:
                        pk = _match_project_key(name)
                        if pk:
                            project_key = pk
                            break
                    category = (p.get("category") or "").strip()
                    if category:
                        pk = _match_project_key(category)
                        if pk:
                            project_key = pk
                            break
            except Exception as e:
                print(f"[KPI 자동 추출] products 매칭 실패: {e}")

        # 1-c. 파일명에서 추론
        if not project_key and file_name:
            try:
                from project_templates import _match_project_key
                parsed = _parse_report_filename(file_name)
                for proj_name in (parsed or {}).get("projects", []):
                    pk = _match_project_key(proj_name)
                    if pk:
                        project_key = pk
                        break
            except Exception as e:
                print(f"[KPI 자동 추출] 파일명 매칭 실패: {e}")

        if not project_key:
            result["reason"] = "project_key 결정 실패"
            print(f"[KPI 자동 추출] 스킵: {result['reason']} (file={file_name})")
            return result

        result["project_key"] = project_key
        # -----------------------------------------------------------
        # 프로파일 조회
        # -----------------------------------------------------------
        profile = _get_project_profile(project_key)
        if not profile:
            result["reason"] = f"프로파일 없음: {project_key}"
            print(f"[KPI 자동 추출] 스킵: {result['reason']}")
            return result

        result["attempted"] = True
        # -----------------------------------------------------------
        # 표 감지
        # -----------------------------------------------------------
        plan_tables = _find_shipping_plan_tables(saved_file_path)
        if not plan_tables:
            result["reason"] = "출하 계획 표를 찾지 못함"
            print(f"[KPI 자동 추출] 스킵: {result['reason']}")
            return result
        # -----------------------------------------------------------
        # 진짜 출하 표 선택
        # -----------------------------------------------------------
        primary = _pick_primary_shipping_table(plan_tables, project_key)
        if not primary:
            result["reason"] = "출하 표 후보 없음 (프로파일 모델 미매칭)"
            print(f"[KPI 자동 추출] 스킵: {result['reason']}")
            return result
        # -----------------------------------------------------------
        # KPI 스키마 변환
        # -----------------------------------------------------------
        kpi_data = _shipping_table_to_kpi_data(primary, project_key, file_name or "")
        if not kpi_data.get("models"):
            result["reason"] = "모델 데이터가 비어있음"
            print(f"[KPI 자동 추출] 스킵: {result['reason']}")
            return result
        # -----------------------------------------------------------
        # 저장
        # -----------------------------------------------------------
        source_label = f"pptx:{doc_id}" if doc_id else f"pptx:{file_name}"
        apply_result = _apply_kpi_from_pptx(
            project_key,
            kpi_data,
            source_info={"label": source_label},
            dry_run=False,
        )
        result["ok"] = True
        result["months_count"] = apply_result.get("months_count", 0)
        result["weeks_count"] = apply_result.get("weeks_count", 0)
        result["cumulative_updated"] = apply_result.get("cumulative_updated", False)

        warnings = kpi_data.get("warnings") or []
        warn_str = f", warnings={len(warnings)}" if warnings else ""
        print(
            f"[KPI 자동 추출 성공] project={project_key}, "
            f"months={result['months_count']}, weeks={result['weeks_count']}, "
            f"cumulative={result['cumulative_updated']}{warn_str}"
        )
        return result
    except Exception as e:
        result["reason"] = f"예외 발생: {e}"
        print(f"[KPI 자동 추출 실패] {e}")
        import traceback
        traceback.print_exc()
        return result


# PPT에서 추출한 KPI 데이터를 kpi_history.json에 병합.
def _apply_kpi_from_pptx(
    project_key: str,
    kpi_data: dict,
    source_info: dict = None,
    dry_run: bool = True,
) -> dict:
    from datetime import datetime as _dt
    source_info = source_info or {}
    now = _dt.now().isoformat()

    # 수량 값 결정: actual 우선, 없으면 plan
    def _pick_value(model_dict, key_type):
        v = (model_dict or {}).get(key_type)
        return v

    # 월/주차 데이터에서 efem, vtm, type 결정.
    def _pick_efem_vtm_and_type(period_dict):
        efem_val = None
        vtm_val = None
        chosen_type = None
        for mid, vals in period_dict.items():
            if not isinstance(vals, dict):
                continue
            actual = vals.get("actual")
            plan = vals.get("plan")
            # actual 있으면 actual, 없으면 plan
            if actual is not None:
                v = actual
                t = "actual"
            elif plan is not None:
                v = plan
                t = "plan"
            else:
                continue
            display = mid.split("::")[-1] if "::" in mid else mid
            if display == "EFEM":
                efem_val = v
                chosen_type = t if chosen_type is None else chosen_type
            elif display == "VTM":
                vtm_val = v
                chosen_type = t if chosen_type is None else chosen_type
        # 둘 다 actual이면 actual, 하나라도 plan이면 plan 우선? -> 우선 actual 우선
        # 위 로직은 먼저 나온 것 채택. 명시적으로:
        # 두 모델 중 하나라도 actual 있으면 -> actual
        actual_found = any(
            (period_dict.get(k) or {}).get("actual") is not None
            for k in period_dict
        )
        chosen_type = "actual" if actual_found else "plan"
        return efem_val, vtm_val, chosen_type

    # 로드
    data = _load_kpi_history()
    if not isinstance(data, dict):
        data = {"version": 1, "projects": {}}
    data.setdefault("projects", {})
    proj = data["projects"].setdefault(project_key, {})
    proj.setdefault("months", {})
    proj.setdefault("weeks", {})

    changes = {"months": [], "weeks": [], "cumulative": None}

    # 월별 병합
    # kpi_data["models"] 구조: [{model_id, months:{...}, weeks:{...}, cumulative:{}}]
    all_months = {}   # month_key -> {model_id: {plan, actual}}
    all_weeks = {}
    cumulative = {}
    for m in kpi_data.get("models") or []:
        mid = m.get("model_id")
        for mk, vals in (m.get("months") or {}).items():
            all_months.setdefault(mk, {})[mid] = vals
        for wk, vals in (m.get("weeks") or {}).items():
            all_weeks.setdefault(wk, {})[mid] = vals
        cum = m.get("cumulative") or {}
        if cum:
            cumulative[mid] = cum

    src_label = source_info.get("label") or "pptx"

    # 월 병합
    for mk in sorted(all_months.keys()):
        period_models = all_months[mk]
        efem_v, vtm_v, t = _pick_efem_vtm_and_type(period_models)
        old = proj["months"].get(mk) or {}
        new_entry = dict(old)
        if efem_v is not None:
            new_entry["efem"] = efem_v
        if vtm_v is not None:
            new_entry["vtm"] = vtm_v
        new_entry["type"] = t
        new_entry["source"] = src_label
        new_entry["updated_at"] = now
        new_entry["month"] = mk
        # 신규 필드
        new_entry["models"] = {
            mid: {"plan": v.get("plan"), "actual": v.get("actual")}
            for mid, v in period_models.items()
        }
        changes["months"].append({
            "key": mk, "before": old, "after": new_entry
        })
        proj["months"][mk] = new_entry

    # 주 병합
    for wk in sorted(all_weeks.keys()):
        period_models = all_weeks[wk]
        efem_v, vtm_v, t = _pick_efem_vtm_and_type(period_models)
        old = proj["weeks"].get(wk) or {}
        new_entry = dict(old)
        if efem_v is not None:
            new_entry["efem"] = efem_v
        if vtm_v is not None:
            new_entry["vtm"] = vtm_v
        new_entry["type"] = t
        new_entry["source"] = src_label
        new_entry["updated_at"] = now
        new_entry["week"] = wk
        new_entry["models"] = {
            mid: {"plan": v.get("plan"), "actual": v.get("actual")}
            for mid, v in period_models.items()
        }
        changes["weeks"].append({
            "key": wk, "before": old, "after": new_entry
        })
        proj["weeks"][wk] = new_entry

    # 누적 병합
    if cumulative:
        proj["cumulative"] = {
            "models": {
                mid: {"po": c.get("po"), "shipped": c.get("shipped")}
                for mid, c in cumulative.items()
            },
            "source": src_label,
            "updated_at": now,
        }
        changes["cumulative"] = proj["cumulative"]

    data["updated_at"] = now + "Z"

    if not dry_run:
        _save_kpi_history(data)

    return {
        "dry_run": dry_run,
        "project_key": project_key,
        "months_count": len(changes["months"]),
        "weeks_count": len(changes["weeks"]),
        "cumulative_updated": changes["cumulative"] is not None,
        "changes": changes,
    }

# ============================================================
#  KPI 기록 · 달/주 꼬리표
# ============================================================
def _load_kpi_history() -> dict:
    try:
        with open(KPI_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"version": 1, "projects": {}}


# KPI(출하 실적 · 손익) 기록을 저장한다
def _save_kpi_history(data: dict) -> None:
    data["updated_at"] = datetime.utcnow().isoformat() + "Z"
    with open(KPI_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# date -> 'YYYY-Wnn'.
def _iso_week_of(dt: date) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


# 날짜 → 'YYYY-MM'.
def _month_key(dt: date) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


# '2026-07' -> '7월'.
def _month_label(month_key: str) -> str:
    try:
        _, m = month_key.split("-")
        return f"{int(m)}월"
    except Exception:
        return month_key


# '2026-W28' -> 'W28'.
def _week_label(week_key: str) -> str:
    try:
        return week_key.split("-")[1]
    except Exception:
        return week_key


# items: dict[key -> row], key는 정렬 가능한 문자열 key_fn_today: 오늘의 기준 key past 개 이전 ~ future 개 이후까지
# 반환.
def _slice_window(items: dict, key_fn_today, past: int, future: int) -> list:
    today_key = key_fn_today()
    all_keys = sorted(items.keys())
    if not all_keys:
        return []
    # 오늘 key 앞뒤로 잘라내기 (없으면 가장 가까운 이전 key 기준)
    if today_key in all_keys:
        idx = all_keys.index(today_key)
    else:
        # today_key보다 작거나 같은 가장 마지막 key
        idx = 0
        for i, k in enumerate(all_keys):
            if k <= today_key:
                idx = i
    lo = max(0, idx - past)
    hi = min(len(all_keys), idx + future + 1)
    return [(k, items[k]) for k in all_keys[lo:hi]]

# ============================================================
#  메이저모듈 KPI 카드 · 이슈 줄
# ============================================================
def _build_major_module_kpi_card() -> dict:
    hist = _load_kpi_history()
    proj = (hist.get("projects") or {}).get("major_module") or {}
    ue = proj.get("unit_economics") or {
        "EFEM": {"asp": 130000, "material": 107900},
        "VTM":  {"asp": 240000, "material": 196800},
    }
    asp_e = ue.get("EFEM", {}).get("asp", 130000)
    asp_v = ue.get("VTM",  {}).get("asp", 240000)

    def money_10k(efem_qty: float, vtm_qty: float) -> dict:
        efem = efem_qty * asp_e / 10000
        vtm  = vtm_qty  * asp_v / 10000
        return {"efem": round(efem, 2), "vtm": round(vtm, 2), "total": round(efem + vtm, 2)}

    today = date.today()

    months_raw = proj.get("months") or {}
    weeks_raw  = proj.get("weeks")  or {}

    m_slice = _slice_window(months_raw, lambda: _month_key(today), past=1, future=2)
    w_slice = _slice_window(weeks_raw,  lambda: _iso_week_of(today), past=1, future=4)

    months = []
    for mk, row in m_slice:
        e = row.get("efem", 0)
        v = row.get("vtm", 0)
        months.append({
            "month": _month_label(mk),
            "type": row.get("type", "plan"),
            **money_10k(e, v),
        })

    weeks = []
    for wk, row in w_slice:
        e = row.get("efem", 0)
        v = row.get("vtm", 0)
        weeks.append({
            "week": _week_label(wk),
            "type": row.get("type", "plan"),
            **money_10k(e, v),
        })

    # 주차별 타이틀 (가장 이른 주가 속한 달 표시)
    week_group_label = ""
    if w_slice:
        first_wk = w_slice[0][0]
        try:
            y, wn = first_wk.split("-W")
            monday = datetime.strptime(f"{y} {int(wn)} 1", "%G %V %u").date()
            week_group_label = f"{monday.month}월 주차별"
        except Exception:
            week_group_label = "주차별"

    return {
        "title": "월별/주차별 매출",
        "metric_mode": "revenue",
        "metric_note": "판가 기준 매출",
        "unit_label": "만불",
        "unit_economics": {
            "EFEM": {"asp": asp_e, "material": ue.get("EFEM", {}).get("material", 0)},
            "VTM":  {"asp": asp_v, "material": ue.get("VTM",  {}).get("material", 0)},
        },
        "week_group_label": week_group_label,
        "months": months,
        "weeks": weeks,
        "footnotes": [
            "※ 단위: 만불 (USD 10K)",
            "※ 매출 = 수량 × 판가 (ASP 기준)",
        ],
    }


# 이슈 라인 로드. 1) kpi_history.json 에 수동 등록된 값이 있으면 그걸 우선.
def _build_major_module_issue_lines() -> list:
    from datetime import date as _date
    # -----------------------------------------------------------
    # 수동 등록 우선
    # -----------------------------------------------------------
    hist = _load_kpi_history()
    proj = (hist.get("projects") or {}).get("major_module") or {}
    manual = proj.get("issue_lines") or []
    if manual:
        return manual
    # -----------------------------------------------------------
    # notes.json에서 자동 생성
    # -----------------------------------------------------------
    try:
        notes_data = _load_notes()
        semi = (notes_data.get("notes") or {}).get("semiconductor") or {}
        card = None
        for c in (semi.get("cards") or []):
            if (c.get("title") or "").strip() == "메이저모듈":
                card = c
                break
        if not card:
            return []

        today = _date.today()
        auto_lines = []
        for sec in (card.get("sections") or []):
            for it in (sec.get("items") or []):
                if not isinstance(it, dict):
                    continue
                itype = (it.get("type") or "").lower()
                text = (it.get("text") or "").strip()
                if not text:
                    continue
                # photo 는 스킵
                if itype == "photo":
                    continue
                # sub 또는 due_date 있는 것만
                due = (it.get("due_date") or it.get("due_date_auto") or "").strip()
                if itype != "sub" and not due:
                    continue

                line = {"text": text, "show_dday": False}
                if due:
                    try:
                        y, m, d = due[:10].split("-")
                        due_d = _date(int(y), int(m), int(d))
                        delta = (due_d - today).days
                        line["due_date"] = due[:10]
                        line["show_dday"] = True
                        if delta < 0:
                            line["severity"] = "high"
                        elif delta <= 3:
                            line["severity"] = "high"
                        elif delta <= 14:
                            line["severity"] = "mid"
                        else:
                            line["severity"] = "info"
                    except Exception:
                        line["severity"] = "info"
                else:
                    line["severity"] = "info"
                auto_lines.append(line)

        return auto_lines
    except Exception as _e:
        print(f"[issue_lines] 자동 생성 실패: {_e}")
        return []


from pydantic import BaseModel


class KpiMonthPayload(BaseModel):
    month: str            # "2026-07"
    efem: float
    vtm: float
    type: str = "plan"    # "actual" | "plan"
    source: str = ""


class KpiWeekPayload(BaseModel):
    week: str             # "2026-W28"
    efem: float
    vtm: float
    type: str = "plan"
    source: str = ""


class KpiIssueLinesPayload(BaseModel):
    issue_lines: list

# ============================================================
#  KPI 관리 주소 (월 · 주 · 엑셀)
# ============================================================
def _ensure_project(hist: dict, project_key: str) -> dict:
    hist.setdefault("projects", {})
    proj = hist["projects"].setdefault(project_key, {
        "unit_economics": {},
        "months": {},
        "weeks": {},
        "issue_lines": [],
    })
    proj.setdefault("months", {})
    proj.setdefault("weeks", {})
    proj.setdefault("issue_lines", [])
    return proj


# 같은 key가 이미 있을 때 덮어쓸지 판단.
def _should_overwrite(existing: dict, incoming_type: str) -> bool:
    if not existing:
        return True
    et = existing.get("type", "plan")
    if incoming_type == "actual" and et == "plan":
        return True
    if incoming_type == "plan" and et == "actual":
        return False
    return True  # 같은 type이면 최신이 덮음


# 프로젝트 KPI(손익) 자료 ← admin v2 closeModal()
@app.get("/admin/kpi/{project_key}")
def admin_kpi_get(project_key: str, _exp: int = Depends(get_admin_session)):
    hist = _load_kpi_history()
    proj = (hist.get("projects") or {}).get(project_key)
    if not proj:
        return {"project_key": project_key, "months": {}, "weeks": {}, "issue_lines": []}
    return {"project_key": project_key, **proj}


# KPI 월 자료 고치기 (잠김) ← admin v2 closeModal()
@app.post("/admin/kpi/{project_key}/months")
def admin_kpi_upsert_month(
    project_key: str,
    payload: KpiMonthPayload,
    _exp: int = Depends(get_admin_session),
):
    hist = _load_kpi_history()
    proj = _ensure_project(hist, project_key)
    existing = proj["months"].get(payload.month)
    if not _should_overwrite(existing, payload.type):
        return {"status": "skipped", "reason": "existing actual not overwritten by plan", "month": payload.month}
    proj["months"][payload.month] = {
        "efem": payload.efem,
        "vtm": payload.vtm,
        "type": payload.type,
        "source": payload.source,
        "uploaded_at": datetime.utcnow().isoformat() + "Z",
    }
    _save_kpi_history(hist)
    return {"status": "ok", "month": payload.month, "row": proj["months"][payload.month]}


# KPI 주 자료 고치기 (잠김) ← admin v2 closeModal()
@app.post("/admin/kpi/{project_key}/weeks")
def admin_kpi_upsert_week(
    project_key: str,
    payload: KpiWeekPayload,
    _exp: int = Depends(get_admin_session),
):
    hist = _load_kpi_history()
    proj = _ensure_project(hist, project_key)
    existing = proj["weeks"].get(payload.week)
    if not _should_overwrite(existing, payload.type):
        return {"status": "skipped", "reason": "existing actual not overwritten by plan", "week": payload.week}
    proj["weeks"][payload.week] = {
        "efem": payload.efem,
        "vtm": payload.vtm,
        "type": payload.type,
        "source": payload.source,
        "uploaded_at": datetime.utcnow().isoformat() + "Z",
    }
    _save_kpi_history(hist)
    return {"status": "ok", "week": payload.week, "row": proj["weeks"][payload.week]}


# 출하실적 엑셀 업로드 → 자동 파싱 → KPI 히스토리 반영.
@app.post("/admin/kpi/{project_key}/upload_excel")
async def admin_kpi_upload_excel(
    project_key: str,
    file: UploadFile = File(...),
    _admin: int = Depends(get_admin_session),
):
    import openpyxl
    from io import BytesIO
    from datetime import datetime as _dt

    raw = await _keep_upload(file, "/admin/kpi/{project_key}/upload_excel", project_key)
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일")

    try:
        wb = openpyxl.load_workbook(BytesIO(raw), data_only=True, keep_links=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"엑셀 파싱 실패: {e}")

    ws = wb.worksheets[0]

    # 헤더 인식: 주차 헤더 행에서 W## 위치 파악
    week_header_row = None
    plan_actual_row = None
    for r in range(1, min(10, ws.max_row) + 1):
        row_vals = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
        row_str = [str(v) if v is not None else "" for v in row_vals]
        joined = "|".join(row_str)
        if "W27" in joined or "W28" in joined:
            week_header_row = r
        if ("계획" in joined and "실적" in joined) and week_header_row and r > week_header_row:
            plan_actual_row = r
            break

    if not week_header_row or not plan_actual_row:
        raise HTTPException(status_code=400, detail="주차/계획/실적 헤더를 찾을 수 없습니다")

    # 주차 컬럼 매핑 (W## → (plan_col, actual_col))
    week_cols = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(row=week_header_row, column=c).value
        if v and isinstance(v, str) and v.strip().startswith("W"):
            wk = v.strip()
            # 오른쪽으로 스캔해서 계획/실적 위치 찾기
            plan_c = actual_c = None
            for cc in [c, c+1]:
                sub = ws.cell(row=plan_actual_row, column=cc).value
                if sub == "계획":
                    plan_c = cc
                elif sub == "실적":
                    actual_c = cc
            if plan_c is None or actual_c is None:
                continue
            week_cols[wk] = (plan_c, actual_c)

    # 월 컬럼 (6월/7월/8월) 파싱 - 카테고리 헤더 기준
    month_cols = {}
    if week_header_row > 2:
        cat_row = week_header_row - 1
        for c in range(1, ws.max_column + 1):
            v = ws.cell(row=cat_row, column=c).value
            if v and isinstance(v, str):
                sv = v.strip()
                if sv in ("6월", "7월", "8월"):
                    # 서브헤더에서 계획/실적 찾기
                    plan_c = actual_c = None
                    for cc in range(c, min(c + 3, ws.max_column + 1)):
                        sub = ws.cell(row=plan_actual_row, column=cc).value
                        if sub == "계획" and plan_c is None:
                            plan_c = cc
                        elif sub == "실적" and actual_c is None:
                            actual_c = cc
                    if plan_c is not None:
                        month_cols[sv] = (plan_c, actual_c)

    # 모델 데이터 행 찾기 (EFEM, VTM)
    data_rows = {}
    for r in range(plan_actual_row + 1, ws.max_row + 1):
        model = ws.cell(row=r, column=2).value  # B열
        if model and isinstance(model, str):
            key = model.strip().upper()
            if key in ("EFEM", "VTM"):
                data_rows[key] = r

    if not data_rows:
        raise HTTPException(status_code=400, detail="EFEM/VTM 데이터 행을 찾을 수 없습니다")

    def _to_num(v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    # 파싱 결과
    result = {"project_key": project_key, "months": [], "weeks": [], "raw_summary": {}}

    # 현재 연도 (report_date 파일명 기준으로 나중에 개선 가능)
    year = _dt.now().year

    # 월 데이터
    month_num_map = {"6월": 6, "7월": 7, "8월": 8}
    for month_label, (plan_c, actual_c) in month_cols.items():
        mnum = month_num_map.get(month_label)
        if not mnum:
            continue
        month_key = f"{year}-{mnum:02d}"

        # 실적이 있으면 actual, 없으면 plan
        efem_actual = _to_num(ws.cell(row=data_rows["EFEM"], column=actual_c).value) if actual_c else None
        vtm_actual = _to_num(ws.cell(row=data_rows["VTM"], column=actual_c).value) if actual_c else None
        efem_plan = _to_num(ws.cell(row=data_rows["EFEM"], column=plan_c).value)
        vtm_plan = _to_num(ws.cell(row=data_rows["VTM"], column=plan_c).value)

        # 실적/계획 둘 다 저장 (실적이 있으면 actual 타입, 아니면 plan 타입)
        if efem_actual is not None or vtm_actual is not None:
            result["months"].append({
                "month": month_key,
                "type": "actual",
                "efem": efem_actual if efem_actual is not None else 0,
                "vtm": vtm_actual if vtm_actual is not None else 0,
            })
        if efem_plan is not None or vtm_plan is not None:
            result["months"].append({
                "month": month_key,
                "type": "plan",
                "efem": efem_plan if efem_plan is not None else 0,
                "vtm": vtm_plan if vtm_plan is not None else 0,
            })

    # 주차 데이터
    for wk, (plan_c, actual_c) in week_cols.items():
        try:
            wnum = int(wk.lstrip("W"))
        except Exception:
            continue
        week_key = f"{year}-W{wnum:02d}"

        efem_actual = _to_num(ws.cell(row=data_rows["EFEM"], column=actual_c).value)
        vtm_actual = _to_num(ws.cell(row=data_rows["VTM"], column=actual_c).value)
        efem_plan = _to_num(ws.cell(row=data_rows["EFEM"], column=plan_c).value)
        vtm_plan = _to_num(ws.cell(row=data_rows["VTM"], column=plan_c).value)

        if efem_actual is not None or vtm_actual is not None:
            result["weeks"].append({
                "week": week_key,
                "type": "actual",
                "efem": efem_actual if efem_actual is not None else 0,
                "vtm": vtm_actual if vtm_actual is not None else 0,
            })
        if efem_plan is not None or vtm_plan is not None:
            result["weeks"].append({
                "week": week_key,
                "type": "plan",
                "efem": efem_plan if efem_plan is not None else 0,
                "vtm": vtm_plan if vtm_plan is not None else 0,
            })

    # kpi_history.json 반영
    hist = _load_kpi_history()
    proj = hist.setdefault("projects", {}).setdefault(project_key, {
        "months": {}, "weeks": {}, "issue_lines": []
    })

    # 병합 규칙: actual > plan (같은 키에서 actual 우선), source 기록
    now_iso = _dt.now().isoformat()

    def _upsert(dst_map, key, entry):
        cur = dst_map.get(key)
        # actual 은 plan 을 덮어씀. 같은 type 이면 항상 최신 upload 로 교체.
        if cur is None:
            dst_map[key] = {**entry, "source": "excel_upload", "updated_at": now_iso}
        else:
            cur_type = cur.get("type", "plan")
            new_type = entry.get("type", "plan")
            if new_type == "actual" or cur_type == new_type:
                dst_map[key] = {**entry, "source": "excel_upload", "updated_at": now_iso}

    for m in result["months"]:
        _upsert(proj.setdefault("months", {}), m["month"], m)
    for w in result["weeks"]:
        _upsert(proj.setdefault("weeks", {}), w["week"], w)

    _save_kpi_history(hist)

    return {
        "status": "ok",
        "project_key": project_key,
        "months_parsed": len(result["months"]),
        "weeks_parsed": len(result["weeks"]),
        "detail": result,
    }

# KPI 이슈 줄 바꾸기 (잠김).
@app.post("/admin/kpi/{project_key}/issue_lines")
def admin_kpi_replace_issue_lines(
    project_key: str,
    payload: KpiIssueLinesPayload,
    _exp: int = Depends(get_admin_session),
):
    hist = _load_kpi_history()
    proj = _ensure_project(hist, project_key)
    proj["issue_lines"] = payload.issue_lines
    _save_kpi_history(hist)
    return {"status": "ok", "count": len(payload.issue_lines)}


# ============================================================
#  매출 자동 계산 헬퍼
# ============================================================
def _iso_week_number(d: date) -> int:
    return d.isocalendar()[1]


# W-번호 → 그 주의 목요일이 속한 월 (ISO 규칙)
def _week_to_month(week_num: int, year: int) -> Optional[int]:
    try:
        # ISO week's Thursday belongs to that year's month
        thursday = datetime.strptime(f"{year}-W{week_num:02d}-4", "%G-W%V-%u").date()
        return thursday.month
    except Exception:
        return None


# 각 주차별로:
def _compute_sales_summary(parsed: dict, today: Optional[date] = None) -> str:
    if today is None:
        today = date.today()
    cur_week = _iso_week_number(today)
    year = today.year

    prices = parsed.get("prices", {})
    weeks = parsed.get("weeks", {})

    if not prices or not weeks:
        return ""

    # 주차별 매출 계산
    week_sales = {}  # {W27: 189.0}
    for wk, models in weeks.items():
        m = re.match(r'^W(\d+)$', wk, re.IGNORECASE)
        if not m:
            continue
        wk_num = int(m.group(1))
        total = 0.0
        for model_name, qty in models.items():
            price = prices.get(model_name, 0.0)
            if wk_num < cur_week:
                # 과거: 실적
                use = qty.get("actual", 0)
            elif wk_num > cur_week:
                # 미래: 계획
                use = qty.get("plan", 0)
            else:
                # 현재: 실적 우선, 없으면 계획
                use = qty.get("actual", 0) or qty.get("plan", 0)
            total += use * price
        week_sales[wk_num] = total

    # 월별 집계
    month_sales = {}  # {7: 74.0, 8: 407.0}
    for wk_num, sales in week_sales.items():
        mo = _week_to_month(wk_num, year)
        if mo is None:
            continue
        month_sales[mo] = month_sales.get(mo, 0.0) + sales

    # 문자열 조립
    parts = []
    for mo in sorted(month_sales.keys()):
        parts.append(f"{mo}월 {month_sales[mo]:.1f}만불")
    # 현재 주차만 별도 강조 (있으면)
    if cur_week in week_sales:
        parts.append(f"W{cur_week} {week_sales[cur_week]:.1f}만불")

    return " · ".join(parts)

# ============================================================
#  출하계획 엑셀 → 판가 × 수량 매출
# ============================================================
def parse_sales_excel(file_path):
    from openpyxl import load_workbook
    import re as _re

    wb = load_workbook(str(file_path), data_only=True, keep_links=False)
    ws = wb.active

    _WEEK_RE = _re.compile(r'W\s*(\d{1,2})', _re.I)

    def _cell_str(v):
        return '' if v is None else str(v).strip()

    def _safe_num(v):
        if v in (None, '', '-'):
            return 0.0
        try:
            return float(v)
        except Exception:
            s = str(v).replace(',', '').strip()
            try:
                return float(s) if s else 0.0
            except Exception:
                return 0.0

    def _month_from_label(raw):
        s = _cell_str(raw).replace(' ', '')
        m = _re.search(r'(\d{1,2})월', s)
        return int(m.group(1)) if m else None

    def _month_for_col(col):
        # 자기 자신 셀 or 왼쪽 셀들에서 "N월" 라벨 스캔 (병합셀 대응)
        for r in (1, 2):
            m = _month_from_label(ws.cell(r, col).value)
            if m:
                return m
        for c in range(col, 0, -1):
            for r in (1, 2):
                m = _month_from_label(ws.cell(r, c).value)
                if m:
                    return m
        return None

    def _build_model_name(row):
        b = _cell_str(ws.cell(row, 2).value)
        c = _cell_str(ws.cell(row, 3).value)
        if not b and not c:
            return None
        low_b = b.lower()
        low_c = c.lower()
        if low_b in ('합계', 'total', '계') or low_c in ('합계', 'total', '계'):
            return None
        # B+C 2단 (프레임처럼)
        if c and not _re.fullmatch(r'[\d,.\-]+', c):
            return f'{b} / {c}' if b else c
        return b or c

    # 주차 컬럼 스캔
    week_cols = []
    for c in range(1, ws.max_column + 1):
        label = _cell_str(ws.cell(3, c).value)
        m = _WEEK_RE.search(label)
        if not m:
            continue
        week_num = int(m.group(1))
        month_num = _month_for_col(c)
        week_cols.append((c, week_num, month_num))

    models = []
    weeks_map = {}

    for row in range(5, ws.max_row + 1):
        model = _build_model_name(row)
        if not model:
            continue

        row_has_value = False
        for col, week_num, month_num in week_cols:
            plan = _safe_num(ws.cell(row, col).value)
            actual = _safe_num(ws.cell(row, col + 1).value)
            if plan != 0 or actual != 0:
                row_has_value = True

            weeks_map.setdefault(week_num, {
                'week': week_num,
                'month': month_num,
                'models': {}
            })
            weeks_map[week_num]['models'][model] = {
                'plan': plan,
                'actual': actual,
            }

        if row_has_value and model not in models:
            models.append(model)

    return {
        'models': models,
        'weeks': [weeks_map[k] for k in sorted(weeks_map.keys())],
    }


# parsed(xlsx) + prices(만불) → 3박스 요약 문자열 + 구조화 데이터.
def compute_sales_from_parsed(parsed, prices, today=None):
    from datetime import date as _date, datetime as _dt

    today = today or _date.today()
    current_week = today.isocalendar()[1]
    current_month = today.month
    next_month = 1 if current_month == 12 else current_month + 1

    month_totals = {}
    week_totals = {}

    for w in (parsed.get('weeks') or []):
        wk = int(w.get('week') or 0)
        month_num = w.get('month')
        total = 0.0

        for model, qa in (w.get('models') or {}).items():
            price = float((prices or {}).get(model, 0) or 0)
            plan = float((qa or {}).get('plan', 0) or 0)
            actual = float((qa or {}).get('actual', 0) or 0)

            if wk < current_week:
                qty = actual
            elif wk == current_week:
                qty = actual if actual > 0 else plan
            else:
                qty = plan

            total += qty * price

        week_totals[wk] = total
        if month_num:
            month_totals[month_num] = month_totals.get(month_num, 0.0) + total

    cur_month_amt = round(month_totals.get(current_month, 0.0), 1)
    cur_week_amt = round(week_totals.get(current_week, 0.0), 1)
    next_month_amt = round(month_totals.get(next_month, 0.0), 1)

    delta_pct = 0.0
    if cur_month_amt > 0:
        delta_pct = round(((next_month_amt - cur_month_amt) / cur_month_amt) * 100.0, 1)

    summary_text = (
        f'{current_month}월 {cur_month_amt:.1f}만불 · '
        f'이번주 {cur_week_amt:.1f}만불 · '
        f'{next_month}월 {next_month_amt:.1f}만불'
    )
    if cur_month_amt > 0:
        arrow = '▲' if delta_pct >= 0 else '▼'
        summary_text += f' {arrow}{abs(delta_pct):.1f}%'

    return {
        'sales_summary': summary_text,
        'sales_summary_data': {
            'boxes': [
                {'key': 'current_month', 'label': f'{current_month}월',
                 'amount': cur_month_amt, 'unit': '만불'},
                {'key': 'current_week', 'label': '이번주',
                 'amount': cur_week_amt, 'unit': '만불', 'week': current_week},
                {'key': 'next_month', 'label': f'{next_month}월',
                 'amount': next_month_amt, 'unit': '만불', 'delta_pct': delta_pct},
            ]
        },
        'sales_computed_at': _dt.now().isoformat(timespec='seconds'),
    }


# 섹션 items에서 첫 번째 .xlsx 파일의 서버 URL 추출.
def _find_xlsx_in_section_items(items):
    if not items:
        return None
    for it in items:
        if not isinstance(it, dict):
            continue
        for key in ('url', 'file_url', 'href', 'photo_ref', 'text'):
            v = it.get(key)
            if not v:
                continue
            s = str(v)
            if '.xlsx' in s.lower() or '.xlsm' in s.lower():
                return s
    return None


# /admin/manual-files/{doc_id}/{filename} → 실제 파일 경로.
def _xlsx_url_to_local_path(url_str):
    if not url_str:
        return None
    s = str(url_str)
    # /admin/manual-files/{doc_id}/{filename} 패턴
    import re as _re
    m = _re.search(r'/admin/manual-files/([^/]+)/([^/?#]+)', s)
    if m:
        doc_id = m.group(1)
        fname = m.group(2)
        return UPLOAD_DIR / 'manual' / doc_id / fname
    return None


# ============================================================
#  매출 계산 주소
# ============================================================
def compute_sales_from_input(sales_input: str, today: Optional[date] = None) -> dict:
    if not sales_input or not sales_input.strip():
        return {"sales_summary": "", "sales_computed_at": ""}
    parsed = _parse_sales_input(sales_input)
    summary = _compute_sales_summary(parsed, today=today)
    return {
        "sales_summary": summary,
        "sales_computed_at": datetime.now().isoformat(timespec='seconds'),
        "_debug": {
            "prices": parsed.get("prices"),
            "weeks_count": len(parsed.get("weeks", {})),
        },
    }


# body: { division_id, card_title, section_title, sales_input } → notes.json 의 해당 section 에
# sales_input/sales_summary/sales_computed_at 저장 → 계산 결과 반환
@app.post("/admin/notes/section/sales_input")
def admin_set_sales_input(payload: dict, _admin: int = Depends(get_admin_session)):
    division_id = (payload.get("division_id") or "").strip()
    card_title = (payload.get("card_title") or "").strip()
    section_title = (payload.get("section_title") or "").strip()
    sales_input = payload.get("sales_input") or ""

    if not division_id or not card_title or not section_title:
        raise HTTPException(status_code=400, detail="division_id/card_title/section_title 필요")

    result = compute_sales_from_input(sales_input)

    # notes.json 갱신
    data = _load_notes()
    notes_map = data.get("notes", {}) or {}
    div = notes_map.get(division_id) or {}
    cards = div.get("cards", []) or []
    target_card = None
    for c in cards:
        if (c.get("title") or "").strip() == card_title:
            target_card = c
            break
    if not target_card:
        raise HTTPException(status_code=404, detail=f"카드 없음: {card_title}")

    sections = target_card.get("sections", []) or []
    target_sec = None
    for s in sections:
        if (s.get("title") or "").strip() == section_title:
            target_sec = s
            break
    if not target_sec:
        raise HTTPException(status_code=404, detail=f"섹션 없음: {section_title}")

    target_sec["sales_input"] = sales_input
    target_sec["sales_summary"] = result["sales_summary"]
    target_sec["sales_computed_at"] = result["sales_computed_at"]

    # 저장
    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    NOTES_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "ok": True,
        "sales_summary": result["sales_summary"],
        "sales_computed_at": result["sales_computed_at"],
        "debug": result.get("_debug", {}),
    }


# 구조화된 sales_data → summary 계산.
def compute_sales_from_data(sales_data: dict, today: Optional[date] = None) -> dict:
    if not isinstance(sales_data, dict):
        return {"sales_summary": "", "sales_computed_at": ""}
    prices = sales_data.get("prices") or {}
    weeks_list = sales_data.get("weeks") or []
    if not prices or not weeks_list:
        return {"sales_summary": "", "sales_computed_at": ""}

    # sales_helpers.py 의 _compute_sales_summary 와 동일 규칙
    if today is None:
        today = date.today()

    # weeks 리스트를 dict로 변환하여 _compute_sales_summary 재활용
    parsed = {"prices": {k: float(v) for k, v in prices.items()}, "weeks": {}}
    for w in weeks_list:
        wk_num = w.get("week")
        if not isinstance(wk_num, int) or wk_num <= 0:
            continue
        models = w.get("models") or {}
        parsed["weeks"][f"W{wk_num}"] = {
            m: {"plan": int(v.get("plan", 0) or 0), "actual": int(v.get("actual", 0) or 0)}
            for m, v in models.items() if isinstance(v, dict)
        }

    summary = _compute_sales_summary(parsed, today=today)
    return {
        "sales_summary": summary,
        "sales_computed_at": datetime.now().isoformat(timespec="seconds"),
    }


# 모든 section의 sales_input 재계산 (판가 정책 바뀔 때 등)
@app.post("/admin/notes/section/sales_recompute")
def admin_recompute_all_sales(_admin: int = Depends(get_admin_session)):
    data = _load_notes()
    notes_map = data.get("notes", {}) or {}
    count = 0
    for div_id, div in notes_map.items():
        for c in div.get("cards", []) or []:
            for s in c.get("sections", []) or []:
                si = s.get("sales_input")
                if not si:
                    continue
                r = compute_sales_from_input(si)
                s["sales_summary"] = r["sales_summary"]
                s["sales_computed_at"] = r["sales_computed_at"]
                count += 1
    NOTES_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"ok": True, "recomputed": count}

# ============================================================
#  폰 등록 · 알림 테스트
# ============================================================
# Flutter 앱이 앱 시작 시 FCM 토큰을 서버에 등록 ← 앱 fcm_service.dart initialize()
@app.post("/device-tokens")
def register_device_token(payload: dict):
    token = (payload or {}).get("token")
    if not token or not isinstance(token, str) or len(token) < 20:
        raise HTTPException(status_code=400, detail="invalid token")
    platform = (payload or {}).get("platform") or "android"
    debug = bool((payload or {}).get("debug", True))
    _add_device_token(token, platform=platform, debug=debug)
    return {"ok": True}


# 알람 시스템 동작 테스트용 엔드포인트.
@app.post("/admin/fcm-test")
def admin_fcm_test(_admin: int = Depends(get_admin_session)):
    result = _send_fcm_to_all(
        title="🔔 테스트 알람",
        body="FCM 파이프라인 정상 동작 중",
        data={"type": "test"},
    )
    return result


# ─── 개발 승인 프로세스 (13단계 고정 템플릿) ───
DEV_PROCESS_STEPS = [
    ("fa_po", "FA PO", "발주"),
    ("material_order", "자재 발주", "발주"),
    ("incoming", "입고", "발주"),
    ("machining", "가공 (조립)", "제작·검사"),
    ("la_incoming", "LA 입고", "제작·검사"),
    ("lair_write", "LAIR 제출", "제작·검사"),
    ("lair_approval", "LAIR 승인", "제작·검사"),
    ("source_inspection", "Source Inspection", "승인"),
    ("fair_write", "FAIR 제출", "승인"),
    ("fair_approval", "FAIR 승인", "승인"),
    ("lap_test", "LAP TEST", "승인"),
    ("cdr", "CDR", "승인"),
    ("final_approval", "최종 승인 완료", "승인"),
]

# ============================================================
#  공정 틀 · 빈 칸 지키기
# ============================================================
def _default_process() -> list:
    return [{"key": k, "name": n, "group": g, "expected": "", "actual": "", "status": ""} for k, n, g in DEV_PROCESS_STEPS]

# 실제로 데이터가 들어 있는 주차 집합.
def _known_weeks(project_key=None) -> set:
    try:
        data = _load_models()
    except Exception:
        return set()
    weeks = set()
    for pk, proj in (data.get("projects") or {}).items():
        if project_key and project_key not in ("all", pk):
            continue
        for g in ("양산", "개발"):
            for w, cell in (((proj.get("weekly_summary") or {}).get(g) or {}).get("weeks") or {}).items():
                if (cell or {}).get("plan") or (cell or {}).get("actual"):
                    weeks.add(str(w).upper())
        for m in (proj.get("models") or []):
            for _mo, wk in ((m.get("weekly_plan") or {})).items():
                for w, cell in (wk or {}).items():
                    if (cell or {}).get("plan") or (cell or {}).get("actual"):
                        weeks.add(str(w).upper())
    return weeks


# 예전 프로젝트 키를 지금 키로 (havaplate → hrva_plate 등).
def _model_key_alias(project_key: str) -> str:
    _alias = {"havaplate": "hrva_plate", "hrvaplate": "hrva_plate", "hrva-plate": "hrva_plate"}
    return _alias.get(project_key.strip().lower(), project_key.strip())

# 엑셀에서 읽은 공정을 기존 입력 위에 얹는다 — 빈 칸은 덮지 않는다
def _merge_process_keep(old, new):
    if not isinstance(old, list) or not old:
        return new
    by_key = {str(s.get("key") or ""): s for s in old if isinstance(s, dict)}
    by_name = {_canon_step(s.get("name")): s for s in old if isinstance(s, dict)}
    out = []
    for i, st in enumerate(new or []):
        st = dict(st or {})
        prev = by_key.get(str(st.get("key") or "")) \
            or by_name.get(_canon_step(st.get("name"))) \
            or (old[i] if i < len(old) and isinstance(old[i], dict) else {})
        for f in ("expected", "actual", "status"):
            if not str(st.get(f) or "").strip():
                st[f] = prev.get(f) or ""
        out.append(st)
    return out


# 'FAIR 제출' 단계에 예정일·실제일을 적는다
def _set_fair_dates(proc, expected: str = "", actual: str = "", today=None) -> list:
    import datetime as _dtf
    if not isinstance(proc, list):
        return proc
    today = today or _dtf.date.today()

    done = ""
    if actual:
        d = _parse_any_date(actual)
        if d and d <= today:
            done = actual

    hit = -1
    for i, st in enumerate(proc):
        if not isinstance(st, dict):
            continue
        if st.get("key") != "fair_write" and _canon_step(st.get("name")) != _canon_step("FAIR 제출"):
            continue
        if expected:
            st["expected"] = expected
        if done:
            st["actual"] = done
        if st.get("actual"):
            st["status"] = "완료"
        elif st.get("expected") and not str(st.get("status") or "").strip():
            st["status"] = "진행중"
        hit = i
        break

    # 방금 완료로 만든 단계의 다음 칸을 진행중으로. 이미 뭔가 적힌 칸은
    # 사람이 쓴 것이니 건드리지 않는다.
    if done and hit >= 0:
        for st in proc[hit + 1:]:
            if not isinstance(st, dict):
                continue
            if st.get("actual"):
                continue                    # 이미 끝난 칸
            cur = str(st.get("status") or "").strip()
            if cur in ("", "대기"):
                st["status"] = "진행중"
            break
    return proc


# 단계 이름만 서 있고 날짜 · 상태가 한 칸도 없는가.
def _dev_steps_blank(proc) -> bool:
    if not isinstance(proc, list) or not proc:
        return False
    for st in proc:
        st = st or {}
        for k in ("expected", "actual", "status", "expected_note", "actual_note"):
            if str(st.get(k) or "").strip():
                return False
    return True


# 개발 품목의 공정 단계. 없으면 기본 13단계를 깔아 준다
def _ensure_process(m: dict, division_id: str = "") -> list:
    proc = m.get("process")
    # process가 이미 있고 리스트면 그대로 사용
    if isinstance(proc, list) and len(proc) > 0:
        return proc
    if division_id and division_id != "semiconductor":
        return proc if isinstance(proc, list) else []
    # 없으면 기본값
    proc = _default_process()
    m["process"] = proc
    return proc


# 양산 모델 weekly_plan 기반 진행률(%)
def _ensure_mass_progress(weekly_plan, month=None):
    import datetime as _dt
    if not weekly_plan:
        return 0.0
    if month is None:
        month = _dt.date.today().strftime("%Y-%m")
    bucket = weekly_plan.get(month)
    if not bucket:
        return 0.0
    tp = sum(int(w.get("plan") or 0) for w in bucket.values())
    ta = sum(int(w.get("actual") or 0) for w in bucket.values())
    return round(min(100.0, ta / tp * 100), 1) if tp > 0 else 0.0

# ============================================================
#  주차 · 달 계산
# ============================================================
def _get_month_weeks(month):
    return _wcal.get_month_weeks(month)


# 'W40' → 그 주차를 소유한 'YYYY-MM'.
def _month_of_week(week_label, year=None):
    return _wcal.month_of_week(week_label, year)


# 모델 weekly_plan / weekly_summary에 데이터가 있는 가장 최근 'YYYY-MM'.
def _latest_data_month(project_key=None):
    import datetime as _dt
    try:
        data = _load_models()
    except Exception:
        return _dt.date.today().strftime("%Y-%m")
    months = set()
    for _pk, _proj in (data.get("projects") or {}).items():
        if project_key and project_key not in ("all", _pk):
            continue
        for _m in (_proj.get("models") or []):
            for _mo, _wk in ((_m.get("weekly_plan") or {})).items():
                if any((c or {}).get("actual") or (c or {}).get("plan") for c in (_wk or {}).values()):
                    months.add(_mo)
    return max(months) if months else _dt.date.today().strftime("%Y-%m")

# 사람이 직접 고른 상태. 추측보다 우선한다.
_STEP_PICKED = ("완료", "진행중", "대기", "미승인", "미제출")

# ============================================================
#  공정 진행률
# ============================================================
def _note_says_done(t) -> bool:
    t = str(t or "").replace(" ", "")
    return "완료" in t and "예정" not in t and "미완료" not in t


# 실적일이 있거나, 상태가 '완료' 거나, 칸에 '완료' 라고 적혔으면 완료다
def _process_step_done(s) -> bool:
    s = s or {}
    if str(s.get("actual") or "").strip() or s.get("status") == "완료":
        return True
    # _note_says_done 과 같은 규칙. 테스트가 이 함수만 떼어 돌려서 여기 적는다.
    for f in ("actual_note", "expected_note"):
        t = str(s.get(f) or "").replace(" ", "")
        if "완료" in t and "예정" not in t and "미완료" not in t:
            return True
    return False


# 끝났거나 하고 있는 중.
def _process_step_active(s) -> bool:
    return _process_step_done(s) or (s or {}).get("status") == "진행중"


# 지금 어디까지 왔는지 한 자리로 정하고, 뒤는 대기로 맞춘 사본.
def _process_rolled(proc: list) -> list:
    if not proc:
        return proc
    n = len(proc)
    cur = -1
    if _process_step_active(proc[-1]):
        cur = n - 1
    else:
        for i, s in enumerate(proc):
            # 실적일이 찍힌 자리는 '진행중' 이라고 적혀 있어도 끝난 것이다
            if (str((s or {}).get("status") or "").strip() == "진행중"
                    and not _process_step_done(s)):
                cur = i
                break
        if cur < 0:
            for i, s in enumerate(proc):
                if _process_step_done(s):
                    cur = i
    if cur < 0:
        return proc

    finished = cur == n - 1 and _process_step_done(proc[-1])
    out = []
    for i, s in enumerate(proc):
        t = dict(s or {})
        if i < cur:
            if finished or _process_step_done(t):
                t["status"] = "완료"
        elif i > cur:
            # 아직 오지 않은 자리. 실적일이 남아 있으면 같이 내린다 —
            # '대기' 라면서 실적일이 찍혀 있으면 어느 쪽이 맞는지 알 수 없다.
            t["status"] = "대기"
            t["actual"] = ""
        elif _process_step_done(t):
            t["status"] = "완료"
        out.append(t)
    # '○○ 승인' 이 끝났으면 바로 앞 '○○ 작성/제출' 도 완료
    import re as _re

    def _stem(nm, tails):
        t = _re.sub(r"^\s*\d+\s*", "", str(nm or "")).strip()
        for tail in tails:
            if t.endswith(tail):
                return t[: -len(tail)].strip().lower()
        return None
    for i in range(len(out) - 1):
        a = _stem(out[i].get("name"), ("작성", "제출"))
        b = _stem(out[i + 1].get("name"), ("승인",))
        if a and a == b and out[i + 1].get("status") == "완료" and out[i].get("status") != "완료":
            out[i]["status"] = "완료"
    return out


# 완료로 맞춰진 단계 수 ÷ 전체 단계 수.
def _process_progress(proc: list) -> int:
    if not proc:
        return 0
    rolled = _process_rolled(proc)
    done = sum(1 for s in rolled if (s or {}).get("status") == "완료")
    return round(done / len(rolled) * 100)


# 모델 1개 진행률: 양산=출하/PO, 개발=프로세스 완료율 (0~100)
def _model_progress(m: dict) -> int:
    if str(m.get('group') or '') == '양산':
        po = float(m.get('po_qty') or 0)
        sh = float(m.get('shipped_qty') or 0)
        return round(min(100.0, sh / po * 100.0)) if po > 0 else 0
    proc = m.get('process') or []
    if proc:
        # 규칙은 _process_rolled 한 곳에 있다. 여기서 따로 세면 화면마다 갈린다.
        rolled = _process_rolled(proc)
        done = sum(1 for s in rolled
                   if (str(s.get('actual') or '').strip() or str(s.get('status') or '') == '완료')
                   and str(s.get('status') or '') not in ('미승인', '미제출'))
        return round(done / len(rolled) * 100)
    return int(m.get('progress') or 0)

# 양산(출하/PO) + 개발(프로세스) 가중 평균 진행률
def _combined_project_progress(proj: dict) -> float:
    models = (proj or {}).get('models', []) or []
    vals = []
    for m in models:
        if str(m.get('group') or '') == '양산':
            po = float(m.get('po_qty') or 0)
            sh = float(m.get('shipped_qty') or 0)
            vals.append(min(100.0, sh / po * 100.0) if po > 0 else 0.0)
        else:
            proc = m.get('process') or []
            if proc:
                vals.append(float(_process_progress(proc) or 0))
            else:
                vals.append(float(m.get('progress') or 0))
    return round(sum(vals) / len(vals), 1) if vals else 0.0


# 양산 모델: weekly_plan이 있으면 앱 표시용 요약 텍스트 생성 (앱 수정 불필요)
def _inject_weekly_summary(m: dict) -> dict:
    if str(m.get('group') or '') != '양산':
        return m
    wp = m.get('weekly_plan') or {}
    if not wp:
        return m
    from datetime import datetime as _dt
    month = _dt.now().strftime('%Y-%m')
    weeks = wp.get(month) or {}
    if not weeks:
        # 가장 최근 월 사용
        latest = sorted(wp.keys())[-1] if wp.keys() else None
        if latest:
            month, weeks = latest, wp[latest]
    if not weeks:
        return m
    plan = sum(int((v or {}).get('plan') or 0) for v in weeks.values())
    actual = sum(int((v or {}).get('actual') or 0) for v in weeks.values())
    remain = plan - actual
    pct = round(actual / plan * 100, 1) if plan > 0 else 0
    summary = f"{month} 주차계획: 계획 {plan} / 실적 {actual} / 잔여 {remain} ({pct}%)"
    # due_text가 비어 있으면 채우고, 있으면 덧붙임
    if not str(m.get('due_text') or '').strip():
        m['due_text'] = summary
    m['weekly_summary'] = summary
    m['weekly_progress'] = pct
    return m

# 현재(다음) 진행 단계. 계획일·실적일·상태가 하나도 없는 단계는 아직 일정이 안 잡힌 것으로 보고 '진행중'으로 표시하지 않는다
def _process_current(proc: list):
    def _done(s):
        return bool(str((s or {}).get("actual") or "").strip()) or (s or {}).get("status") == "완료"

    def _has_input(s):
        return any(str((s or {}).get(k) or "").strip()
                   for k in ("expected", "actual", "status"))

    proc = proc or []
    # 0) 최종 승인이 완료면 중간 단계와 무관하게 완료로 본다
    if proc and _done(proc[-1]):
        return "최종 승인 완료", ""
    # 1) 상태를 '진행중'으로 직접 지정한 단계
    for s in proc:
        if (s or {}).get("status") == "진행중" and not _done(s):
            return s.get("name") or "", str(s.get("expected") or "")
    # 2) 계획일이 잡힌 첫 미완료 단계
    for s in proc:
        if not _done(s) and str((s or {}).get("expected") or "").strip():
            return s.get("name") or "", str(s.get("expected") or "")
    # 3) 입력이 하나라도 있는 첫 미완료 단계
    for s in proc:
        if not _done(s) and _has_input(s):
            return s.get("name") or "", str(s.get("expected") or "")
    # 4) 전부 완료했으면 완료, 입력이 아예 없으면 현재 단계 없음
    if proc and all(_done(s) for s in proc):
        return "최종 승인 완료", ""
    return "", ""

# 모델 1건의 진행률(%). 데이터가 없으면 None → 집계에서 제외.
def _model_progress_value(m: dict):
    if not isinstance(m, dict):
        return None
    # 저장된 group 이 아니라 '지금 어느 단계인가'로 센다. 전환 주차가 지났는데
    # 아무도 모델을 열어 저장하지 않으면 계속 개발로 집계됐다.
    if _display_group(m) == "개발":
        proc = m.get("process") if isinstance(m.get("process"), list) else []
        # 공정 단계 중 하나라도 계획일 · 실적일 · 상태가 적혀 있나
        has_input = False
        for _step in proc:
            for _f in ("expected", "actual", "status"):
                if str((_step or {}).get(_f) or "").strip():
                    has_input = True
                    break
            if has_input:
                break
        if not has_input:
            return None
        return _process_progress(proc)
    try:
        po = int(m.get("po_qty") or 0)
    except Exception:
        po = 0
    if po <= 0:
        return None
    try:
        shipped = int(m.get("shipped_qty") or 0)
    except Exception:
        shipped = 0
    return round(shipped * 100 / po)


# 프로젝트 하나의 진행률 한 줄 (모델 진행률 평균 · 지연 수).
def _project_progress_entry(project_key: str, proj: dict) -> dict:
    # 모델마다 진행률 — 셀 수 없는 모델(None)은 뺀다
    vals = []
    for m in (proj.get("models") or []):
        v = _model_progress_value(m)
        if v is not None:
            vals.append(v)
    try:
        div_id = _cl.derive_division_from_project(project_key)
    except Exception:
        div_id = None
    return {
        "project_key": project_key,
        "division_id": div_id,
        "models_total": len(proj.get("models") or []),
        "scored_count": len(vals),
        "score_sum": sum(vals),
        "progress": round(sum(vals) / len(vals)) if vals else None,
    }

# ============================================================
#  진행률 요약 · 개요 주소
# ============================================================
# 프로젝트별 진행률 요약 (앱 사업부 화면용) ← admin v2 back.onclick() · 앱 progress_service.dart fetch()
@app.get("/projects-progress-summary")
def get_projects_progress_summary(division_id: str = None):
    data = _load_models()
    out = {}
    for pk, proj in (data.get("projects") or {}).items():
        entry = _project_progress_entry(pk, proj)
        if division_id and entry.get("division_id") != division_id:
            continue
        out[pk] = entry
    # 앱에서 쓰는 별칭 키(hrva-plate 등)로도 찾을 수 있게 보강
    for _alias, _real in {"havaplate": "hrva_plate", "hrvaplate": "hrva_plate",
                          "hrva-plate": "hrva_plate"}.items():
        if _real in out and _alias not in out:
            out[_alias] = out[_real]
    # 별칭 중복 집계 방지: project_key 기준 유니크
    _seen, total_cnt, total_sum, total_models = set(), 0, 0, 0
    for e in out.values():
        if e["project_key"] in _seen:
            continue
        _seen.add(e["project_key"])
        total_cnt += e["scored_count"]
        total_sum += e["score_sum"]
        total_models += e["models_total"]
    return {
        "projects": out,
        "scored_count": total_cnt,
        "models_total": total_models,
        "progress": round(total_sum / total_cnt) if total_cnt else None,
        "note": "양산=PO수량 등록분, 개발=공정 입력분만 집계. 데이터 없으면 progress=null",
    }


# 프로젝트 표시 이름.
def _display_project_label(project_key: str) -> str:
    try:
        p = _cl.get_project(project_key)
        if p and (p.get("label") or "").strip():
            # 화면 이름만 다듬는다 (division_columns.clean_label)
            return _dcol.clean_label(p["label"].strip())
    except Exception:
        pass
    # 여기서만 고정 맵을 본다. 다른 곳은 전부 이 함수를 거친다.
    return PROJECT_LABELS.get(project_key, project_key)


# 앱 홈 화면용 요약 (admin/overview 와 동일) ← admin v2 renderHomeDashboard() · 앱 overview_service.dart fetch()
@app.get("/overview")
def get_overview(month: str = None, division_id: str = None):
    return get_admin_overview(month=month, division_id=division_id)


# 주차를 '끝난 주' 와 '남은 주' 로 가른다
def _split_weeks_closed_open(wr: dict, month: str, today) -> tuple:
    closed = {"closed_weeks": 0, "closed_qty_plan": 0, "closed_qty_actual": 0,
              "closed_revenue": 0, "closed_plan_revenue": 0}
    opened = {"open_weeks": 0, "open_qty_plan": 0, "open_plan_revenue": 0}
    weeks = (wr.get("combined") or {}).get("weeks") or {}
    for w, cell in weeks.items():
        cell = cell or {}
        end = _week_end_date(month, w)
        done = bool(end and end < today)
        if done:
            closed["closed_weeks"] += 1
            closed["closed_qty_plan"] += int(cell.get("plan") or 0)
            closed["closed_qty_actual"] += int(cell.get("actual") or 0)
            closed["closed_revenue"] += round(float(cell.get("revenue") or 0))
            closed["closed_plan_revenue"] += round(float(cell.get("plan_revenue") or 0))
        else:
            opened["open_weeks"] += 1
            opened["open_qty_plan"] += int(cell.get("plan") or 0)
            opened["open_plan_revenue"] += round(float(cell.get("plan_revenue") or 0))
    return closed, opened


# Admin 홈 대시보드용 요약: 프로젝트별 진행률 + 해당 월 수량/매출 ← admin v2 renderHomeDashboard()
@app.get("/admin/overview")
def get_admin_overview(month: str = None, division_id: str = None):
    import datetime as _dt
    data = _load_models()
    today = _dt.date.today()
    month = (month or "").strip() or today.strftime("%Y-%m")

    rows = []
    for pk, proj in (data.get("projects") or {}).items():
        entry = _project_progress_entry(pk, proj)
        if division_id and entry.get("division_id") != division_id:
            continue
        row = {
            "key": pk,
            "label": _display_project_label(pk),
            "division_id": entry.get("division_id"),
            "models_total": entry.get("models_total", 0),
            "scored_count": entry.get("scored_count", 0),
            "progress": entry.get("progress"),
            "qty_plan": 0, "qty_actual": 0,
            "revenue": 0, "plan_revenue": 0,
            "has_weekly": False,
        }
        try:
            wr = get_weekly_revenue(pk, month) or {}
            grp = wr.get("groups") or {}
            for g in ("양산", "개발"):
                t = (grp.get(g) or {}).get("total") or {}
                row["qty_plan"] += int(t.get("plan") or 0)
                row["qty_actual"] += int(t.get("actual") or 0)
                row["revenue"] += round(float(t.get("revenue") or 0))
                row["plan_revenue"] += int(t.get("plan_revenue") or 0)
            row["has_weekly"] = bool(row["qty_plan"] or row["qty_actual"])
            # 월 달성률 35% 를 그대로 보여주면 '큰일났다' 로 읽힌다. 아직
            # 3주가 남았는데 그 3주 계획까지 분모에 들어가 있어서다.
            # 끝난 주(일요일이 지난 주)와 남은 주를 갈라 둔다.
            _cl, _op = _split_weeks_closed_open(wr, month, today)
            row.update(_cl)
            row.update(_op)
        except Exception as _e:
            print(f"[overview] {pk} 주차 매출 계산 실패: {_e}")
        rows.append(row)

    # 이 달 계획 매출 큰 곳 → 모델 많은 곳 → 이름순
    def _by_plan_models_label(r):
        return (-(r["plan_revenue"] or 0), -(r["models_total"] or 0), r["label"])
    rows.sort(key=_by_plan_models_label)

    scored = sum(r["scored_count"] for r in rows)
    score_sum = 0
    for pk, proj in (data.get("projects") or {}).items():
        e = _project_progress_entry(pk, proj)
        if division_id and e.get("division_id") != division_id:
            continue
        score_sum += e.get("score_sum", 0)

    return {
        "month": month,
        "totals": {
            "projects": len(rows),
            "projects_active": sum(1 for r in rows if r["models_total"]),
            "models": sum(r["models_total"] for r in rows),
            "scored_count": scored,
            "progress": round(score_sum / scored) if scored else None,
            "qty_plan": sum(r["qty_plan"] for r in rows),
            "qty_actual": sum(r["qty_actual"] for r in rows),
            "revenue": sum(r["revenue"] for r in rows),
            "plan_revenue": sum(r["plan_revenue"] for r in rows),
            # 끝난 주 / 남은 주
            "closed_weeks": max([r.get("closed_weeks") or 0 for r in rows] or [0]),
            "open_weeks": max([r.get("open_weeks") or 0 for r in rows] or [0]),
            "closed_qty_plan": sum(r.get("closed_qty_plan") or 0 for r in rows),
            "closed_qty_actual": sum(r.get("closed_qty_actual") or 0 for r in rows),
            "closed_revenue": sum(r.get("closed_revenue") or 0 for r in rows),
            "closed_plan_revenue": sum(r.get("closed_plan_revenue") or 0 for r in rows),
            "open_qty_plan": sum(r.get("open_qty_plan") or 0 for r in rows),
            "open_plan_revenue": sum(r.get("open_plan_revenue") or 0 for r in rows),
        },
        "projects": rows,
    }

# ============================================================
#  날짜 · 진행 추세
# ============================================================
def _parse_any_date(v):
    import datetime as _dt, re as _re
    t = str(v or "").strip()
    if not t:
        return None
    t = t.replace(".", "-").replace("/", "-")
    m = _re.match(r"^(\d{2,4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return _dt.date(y, mo, d)
        except Exception:
            return None
    m = _re.match(r"^(\d{1,2})-(\d{1,2})$", t)
    if m:
        try:
            return _dt.date(_dt.date.today().year, int(m.group(1)), int(m.group(2)))
        except Exception:
            return None
    return None


# '2026-08' + 'W33' → 그 ISO 주의 일요일(주 마감일).
def _week_end_date(month: str, week_label: str):
    import datetime as _dt
    try:
        y = int(str(month).split("-")[0])
        mm = int(str(month).split("-")[1])
        n = int(str(week_label).upper().lstrip("W"))
    except (ValueError, IndexError, AttributeError):
        return None
    if mm == 12 and n <= 2:
        y += 1          # 12월 보드의 W01 = 다음 해 1주
    elif mm == 1 and n >= 52:
        y -= 1          # 1월 보드의 W52/W53 = 지난 해 마지막 주
    try:
        return _dt.date.fromisocalendar(y, n, 7)
    except ValueError:
        # 그 해에 없는 주차(52주 해의 W53). 앞뒤 해에서 찾아본다.
        for _y in (y - 1, y + 1):
            try:
                return _dt.date.fromisocalendar(_y, n, 7)
            except ValueError:
                continue
        return None


# cutoff(date) 시점 기준 모델 진행률.
def _model_progress_asof(m: dict, cutoff):
    if not isinstance(m, dict):
        return None
    if _display_group(m, cutoff) == "개발":
        proc = m.get("process") if isinstance(m.get("process"), list) else []
        # 공정 단계 중 하나라도 계획일 · 실적일 · 상태가 적혀 있나
        has_input = False
        for _step in proc:
            for _f in ("expected", "actual", "status"):
                if str((_step or {}).get(_f) or "").strip():
                    has_input = True
                    break
            if has_input:
                break
        if not has_input or not proc:
            return None
        done = 0
        for st in proc:
            a = str((st or {}).get("actual") or "").strip()
            is_done = bool(a) or str((st or {}).get("status") or "").strip() == "완료"
            if not is_done:
                continue
            d = _parse_any_date(a)
            # 날짜가 없는 완료('Complete', '완료' 등)는 시점을 알 수 없으므로
            # 모든 구간에서 완료로 본다 (마지막 시점이 현재 진행률과 일치하도록)
            if d is None or d <= cutoff:
                done += 1
        return round(done * 100 / len(proc))
    try:
        po = int(m.get("po_qty") or 0)
    except Exception:
        po = 0
    if po <= 0:
        return None
    # 주차 실적 누적. 주차 입력 합계가 총 출하량에 못 미치면 그 차이는
    # 주차 입력 이전에 나간 물량으로 보고 모든 시점에 기본값으로 깔아준다.
    # (그래야 마지막 시점 값이 shipped_qty 기준 진행률과 정확히 일치)
    weekly_all, weekly_asof = 0, 0
    for month, weeks in ((m.get("weekly_plan") or {})).items():
        for wk, cell in (weeks or {}).items():
            try:
                a = int((cell or {}).get("actual") or 0)
            except Exception:
                a = 0
            weekly_all += a
            end = _week_end_date(month, wk)
            if end is not None and end <= cutoff:
                weekly_asof += a
    try:
        shipped_total = int(m.get("shipped_qty") or 0)
    except Exception:
        shipped_total = 0
    baseline = max(0, shipped_total - weekly_all)
    return round((baseline + weekly_asof) * 100 / po)


# 진행률 추이. 주차별 실적(양산) / 공정 실적일(개발) 누적으로 과거 시점을 재구성한다 ← 앱 progress_service.dart fetch()
@app.get("/progress-trend")
def get_progress_trend(period: str = "week", points: int = 4, division_id: str = None):
    import datetime as _dt
    today = _dt.date.today()
    cutoffs = []
    if period == "day":
        n = max(1, min(points or 7, 31))
        for i in range(n - 1, -1, -1):
            d = today - _dt.timedelta(days=i)
            cutoffs.append((f"{d.month}/{d.day}", d))
    elif period == "month":
        n = max(1, min(points or 4, 12))
        y, mo = today.year, today.month
        seq = []
        for _ in range(n):
            seq.append((y, mo))
            mo -= 1
            if mo == 0:
                y, mo = y - 1, 12
        for y2, m2 in reversed(seq):
            last = (_dt.date(y2 + 1, 1, 1) if m2 == 12 else _dt.date(y2, m2 + 1, 1)) - _dt.timedelta(days=1)
            cutoffs.append((f"{m2}월", min(last, today)))
    else:
        n = max(1, min(points or 4, 26))
        for i in range(n - 1, -1, -1):
            d = today - _dt.timedelta(days=i * 7)
            cutoffs.append((f"{d.month}/{d.day}", d))

    data = _load_models()
    models = []
    for pk, proj in (data.get("projects") or {}).items():
        if division_id:
            try:
                if _cl.derive_division_from_project(pk) != division_id:
                    continue
            except Exception:
                pass
        models.extend(proj.get("models") or [])

    out = []
    for label, cutoff in cutoffs:
        # 그 날짜 기준 모델마다 진행률 — 셀 수 없는 모델(None)은 뺀다
        vals = []
        for m in models:
            v = _model_progress_asof(m, cutoff)
            if v is not None:
                vals.append(v)
        out.append({
            "label": label,
            "date": cutoff.isoformat(),
            "value": round(sum(vals) / len(vals)) if vals else None,
            "scored_count": len(vals),
        })
    _vals = [p["value"] for p in out if p["value"] is not None]
    return {
        "period": period,
        "points": out,
        "current": _vals[-1] if _vals else None,
        "delta": (_vals[-1] - _vals[-2]) if len(_vals) >= 2 else None,
        "delta_vs_average": (_vals[-1] - round(sum(_vals[:-1]) / len(_vals[:-1])))
        if len(_vals) >= 2 else None,
    }


# 모델 상태. '드롭예정'·'보류' 는 시계가 멈춘 상태라 지연으로 세지 않는다.
MODEL_STATUSES = ("정상", "주의", "지연", "드롭예정", "보류")

# 목록에 없는 옛 값 → 지금 값. 입력 받을 때와 기동 정리(_cleanup_legacy_status)가 쓴다.
_LEGACY_MODEL_STATUS = {"진행": "정상"}

# 비고·이슈에 이렇게 적어두면 상태를 안 골라도 알아본다.
_HOLD_WORDS = (("드롭예정", "드롭"), ("드롭예정", "drop"), ("보류", "보류"),
               ("보류", "홀딩"), ("보류", "홀드"), ("보류", "hold"), ("보류", "중단"))
_HOLD_NEGATIONS = ("드롭 안", "드롭안", "드롭 취소", "보류 해제", "보류해제",
                   "보류 취소", "드롭 아님", "드롭아님", "중단 없", "홀드 해제",
                   "홀딩 해제", "홀딩해제", "홀딩 없")

# ============================================================
#  보류 · PO 대기 · 지연 판정
# ============================================================
def _model_hold(m: dict) -> str:
    st = str((m or {}).get("status") or "").strip().replace(" ", "")
    if st in ("드롭예정", "드롭"):
        return "드롭예정"
    if st in ("보류", "홀드", "중단"):
        return "보류"
    txt = " ".join(str((m or {}).get(f) or "") for f in ("note", "issues")).lower()
    if not txt.strip():
        return ""
    if any(neg in txt for neg in _HOLD_NEGATIONS):
        return ""
    for kind, word in _HOLD_WORDS:
        if word in txt:
            return kind
    return ""


# 프로젝트 전체가 멈춰 있으면 '보류' · '드롭예정', 아니면 ''.
def _project_hold(proj: dict) -> str:
    st = str((proj or {}).get("hold") or "").strip().replace(" ", "")
    if st in ("진행", "해제", "없음"):
        return ""                      # admin 에서 직접 풀었다
    if st in ("드롭예정", "드롭"):
        return "드롭예정"
    if st in ("보류", "홀딩", "홀드", "중단"):
        return "보류"
    # 새겨둔 값이 없으면 현황 문구에서 읽는다 (읽자마자 _stamp 로 남긴다)
    kind, _ = _hold_from_note((proj or {}).get("status_note"))
    return kind


# 현황 문구에서 읽어낸 (종류, 근거 문장).
def _hold_from_note(note: str):
    txt = str(note or "")
    low = txt.lower()
    if not low.strip():
        return "", ""
    if any(neg in low for neg in _HOLD_NEGATIONS):
        return "", ""
    for kind, word in _HOLD_WORDS:
        if word in low:
            for line in txt.splitlines():
                if word in line.lower():
                    return kind, line.strip().lstrip("*・- ").strip()
            return kind, ""
    return "", ""


# 현황에 적힌 보류를 프로젝트 필드로 새겨 둔다
def _stamp_project_hold(proj: dict, note: str) -> bool:
    # 사람이 골라 둔 건 사람만 되돌린다
    if str((proj or {}).get("hold_source") or "") in ("manual", "excel"):
        return False

    kind, why = _hold_from_note(note)
    changed = False
    if kind:
        if proj.get("hold") != kind:
            proj["hold"] = kind
            changed = True
        if why and proj.get("hold_reason") != why:
            proj["hold_reason"] = why
            changed = True
        if proj.get("hold_source") != "status_note":
            proj["hold_source"] = "status_note"
            changed = True
        return changed
    # 현황에 '홀딩 해제' 처럼 푸는 말이 적혔으면 문구로 걸었던 보류를 푼다
    low = str(note or "").lower()
    if (proj.get("hold_source") == "status_note"
            and any(neg in low for neg in _HOLD_NEGATIONS)):
        for f in ("hold", "hold_reason", "hold_source"):
            if f in proj:
                proj.pop(f, None)
                changed = True
    return changed


# 보류라고 판단한 근거 문장 한 줄.
def _project_hold_reason(proj: dict) -> str:
    saved = str((proj or {}).get("hold_reason") or "").strip()
    if saved:
        return saved
    return _hold_from_note((proj or {}).get("status_note"))[1]


# 최종 승인이 끝난 개발품을 며칠 동안 '완료' 로 두었다가 PO 대기로 넘길까.
DEV_PO_WAIT_DAYS = 7


# 최종 승인이 끝난 날 (date) — 모르면 None.
def _dev_final_day(m: dict, proc: list):
    # 마지막 단계가 최종 승인이다
    last = {}
    if proc and proc[-1]:
        last = proc[-1]
    for raw in (last.get("actual"), (m or {}).get("final_done_seen")):
        hit = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", str(raw or ""))
        if hit:
            try:
                return date(int(hit.group(1)), int(hit.group(2)), int(hit.group(3)))
            except ValueError:
                continue
    return None


# 최종 승인이 끝난 개발품을 PO 대기로 넘길 때가 됐나.
def _dev_po_wait(m: dict, proc: list, today=None) -> bool:
    if not proc or not _process_step_done(proc[-1]):
        return False
    day = _dev_final_day(m, proc)
    if day is None:
        return True
    return ((today or date.today()) - day).days >= DEV_PO_WAIT_DAYS


# 양산으로 넘어왔는데 PO 가 아직 안 들어온 모델.
def _model_po_wait(m: dict, disp_group: str = "") -> bool:
    g = disp_group or _display_group(m)
    if g != "양산":
        return False
    try:
        return int((m or {}).get("po_qty") or 0) <= 0
    except (TypeError, ValueError):
        return True


# 완료예정일이 며칠 안 남았을 때 '임박' 으로 볼 것인가.
SOON_DAYS = 3


# '지연 없음' 처럼 아니라고 적은 문장. 낱말만 보면 이런 것도 지연이 된다.
_DELAY_NEG = ("지연 없", "지연없", "지연 해소", "지연해소", "지연 해제",
              "지연해제", "지연 아님", "지연아님", "지연 없이", "지연 방지",
              "지연 취소", "지연 우려 없")


# 이슈 칸에 사람이 '지연' 이라고 적었으면 일정 문제로 본다
def _issue_says_delay(text) -> bool:
    t = " ".join(str(text or "").split())
    if "지연" not in t:
        return False
    return not any(neg in t for neg in _DELAY_NEG)


# '지연' · '주의' · '정상'.
def _model_alert(m: dict, disp_group: str = "", expected: str = "",
                 progress=None) -> str:
    manual = str((m or {}).get("status") or "").strip()
    if manual in ("지연", "주의"):
        return manual
    # 드롭·보류는 일정이 멈춘 것이다. 예정일이 지났다고 지연으로 세면
    # 화면에는 '일정 지연' 인데 실제로는 드롭이라 말이 안 맞는다.
    if _model_hold(m):
        return "정상"
    try:
        pg = int(progress if progress is not None else (m or {}).get("progress") or 0)
    except Exception:
        pg = 0
    if pg >= 100:
        return "정상"
    _proc = (m or {}).get("process")
    if isinstance(_proc, list) and _proc and _process_step_done(_proc[-1]):
        return "정상"          # 최종 승인이 끝났으면 늦고 말고가 없다
    # 사람이 '지연' 이라고 적었으면 그것도 판정이다
    if _issue_says_delay(" ".join(str((m or {}).get(f) or "")
                                  for f in ("issues", "note"))):
        return "지연"
    g = disp_group or _display_group(m)
    if g != "개발":
        return "정상"
    exp = str(expected or (m or {}).get("current_expected") or "").strip()
    if not exp:
        return "정상"
    d = _parse_any_date(exp)
    if not d:
        return "정상"
    import datetime as _dt
    left = (d - _dt.date.today()).days
    if left < 0:
        return "지연"
    if left <= SOON_DAYS:
        return "주의"
    return "정상"

# ============================================================
#  모델 하나를 화면 모양으로 (_enrich_model)
# ============================================================
def _frame_group(m: dict, division_id: str = "") -> str:
    g = _display_group(m)
    if g != "개발":
        return g
    try:
        want = _dcol.dev_frame(division_id)
    except Exception:
        want = ""
    return want or g


# 모델 하나를 화면에 내보낼 모양으로 — 상태 · 지연 판정 · 공정 · 보류 를 붙인다
def _enrich_model(m: dict, proj_hold: str = "", division_id: str = "") -> dict:
    out = {k: m.get(k) for k in ("id", "name", "group", "status", "progress", "price", "material_cost", "dev_type", "po_qty", "shipped_qty", "due_text", "issues", "note", "part_number", "weekly_plan", "weekly_progress", "weekly_summary", "dev_owner", "due_date", "due_revised", "made_date")}
    _disp = _display_group(m)
    out["display_group"] = _disp
    # -----------------------------------------------------------
    # 어느 '틀' 로 그릴까
    # -----------------------------------------------------------
    # Min: "양산 개발을 나뉘는데 개발에 들어가더라도 양산처럼 틀
    #      똑같이 맞춰달라는거였어"
    #
    # 구분(display_group)과 틀(frame)은 다른 이야기다.
    #   구분 — 목록이 양산 · 개발 두 묶음으로 나뉘는 기준. 그대로 둔다.
    #   틀   — 그 묶음에 들어갔을 때 어떤 카드 · 어떤 상세 화면으로 보나.
    #
    # 아리스타 개발은 '개발' 묶음에 그대로 있되, 안에서는 양산처럼
    # 주차별 계획 · 실적으로 본다. 공정 13단계는 반도체 것이라 PCB 에는
    # 맞는 단계가 하나도 없다 — 들어가면 빈 단계표만 떴다.
    out["frame"] = _frame_group(m, division_id)
    if _disp == "개발":
        proc = _ensure_process(m, division_id)
        out["process"] = proc
        out["dev_type"] = m.get("dev_type") or ""
        out["progress"] = _process_progress(proc)
        stage, expected = _process_current(proc)
        out["current_stage"] = stage
        out["current_expected"] = expected
        # 상세 화면과 같은 기준 (실적일 · '완료' · 최종 승인이면 전부)
        out["done_steps"] = sum(1 for s in _process_rolled(proc) if _process_step_done(s))
        out["total_steps"] = len(proc)
        # 최종 승인이 끝났으면 끝난 것이다. 진행률 숫자에만 기대면
        # 양산으로 넘어간 뒤 PO 기준으로 다시 세어져 '완료'에서 빠진다.
        out["finished"] = bool(proc) and _process_step_done(proc[-1])
        # 최종 승인 뒤 1주일은 '완료', 그다음은 PO 대기 (_dev_po_wait)
        out["dev_po_wait"] = _dev_po_wait(m, proc)
        _fd = _dev_final_day(m, proc) if out["finished"] else None
        out["final_day"] = _fd.isoformat() if _fd else ""
        out["alert"] = _model_alert(m, _disp, expected, out["progress"])
    else:
        # 양산으로 넘어가도 최종 승인까지 간 공정 기록은 계속 볼 수 있어야 한다.
        # progress 는 덮지 않는다 — 그건 이제 PO 대비 출하다.
        _proc = m.get("process")
        # 공정 단계 중 하나라도 계획일 · 실적일 · 상태가 적혀 있으면 그대로 싣는다
        _proc_has_input = False
        if isinstance(_proc, list):
            for _step in _proc:
                for _f in ("expected", "actual", "status"):
                    if str((_step or {}).get(_f) or "").strip():
                        _proc_has_input = True
                        break
                if _proc_has_input:
                    break
        if _proc_has_input:
            out["process"] = _proc
            out["done_steps"] = sum(1 for st in _proc
                                    if str((st or {}).get("actual") or "").strip())
            out["total_steps"] = len(_proc)
            out["dev_type"] = m.get("dev_type") or ""
            out["finished"] = _process_step_done(_proc[-1])
    out.setdefault("finished", False)
    out.setdefault("alert", _model_alert(m, _disp))
    _own_hold = _model_hold(m)
    out["hold"] = _own_hold or (proj_hold or "")
    # 프로젝트가 통째로 멈춘 것과, 이 모델만 드롭인 것은 다르다.
    # 화면에서 '보류 29줄' 을 늘어놓는 대신 안내 한 줄로 바꿀 수 있게 구분해 준다.
    if _own_hold:
        out["hold_scope"] = "model"          # 이 모델만 멈춤
    elif proj_hold:
        out["hold_scope"] = "project"        # 프로젝트가 통째로 멈춤
    else:
        out["hold_scope"] = ""
    out["po_wait"] = _model_po_wait(m, _disp) or bool(out.get("dev_po_wait"))
    # 프로젝트가 통째로 멈춰 있으면 그 안의 모델도 늦은 게 아니다.
    if proj_hold and out.get("alert") in ("지연", "주의"):
        out["alert"] = "정상"
    return out

# ============================================================
#  홈 알림 (/home/alerts)
# ============================================================
def _has_week_plan(proj: dict, month: str) -> bool:
    for m in (proj.get("models") or []):
        if not isinstance(m, dict):
            continue
        bucket = ((m.get("weekly_plan") or {}).get(month)) or {}
        for cell in bucket.values():
            if (cell or {}).get("plan") or (cell or {}).get("actual"):
                return True
    return False


_WB_CACHE = {}          # (프로젝트, 달) → (바뀐 시각, 마감주차, 미달 한 줄)


# 그 달 **마지막 마감 주차의 미달 한 줄**만 캐시해 둔다
def _weekly_shortfall_cached(pk: str, month: str):
    try:
        stamp = os.path.getmtime(MODELS_FILE)
    except OSError:
        stamp = 0
    key = (pk, month)
    got = _WB_CACHE.get(key)
    if got and got[0] == stamp:
        return got[1], got[2]
    board = get_weekly_board(pk, month) or {}
    last = ((board.get("closed_weeks") or [])[-1:] or [""])[0]
    sh = next((x for x in (board.get("shortfalls") or [])
               if x.get("week") == last and x.get("kind") != "참고"), None)
    # 보드는 여기서 버린다. 들고 있으면 안 된다.
    if len(_WB_CACHE) > 400:
        _WB_CACHE.clear()
    _WB_CACHE[key] = (stamp, last, sh)
    return last, sh


# 홈 화면 한 눈 요약 — 모델 기준 ← 앱 home_alerts_service.dart fetch()
@app.get("/home/alerts")
def get_home_alerts(limit: int = 12, division: str = "semiconductor"):
    import datetime as _dth
    data = _load_models()
    div = (division or "").strip()
    scoped = bool(div)
    try:
        visible = {p.get("id") for p in (
            _cl.get_projects(div, visible_only=True) if scoped
            else _cl.get_projects(visible_only=True))}
    except Exception:
        visible = set()

    today = _dth.date.today()
    counts = {"total": 0, "delayed": 0, "issue": 0, "soon": 0, "hold": 0,
              "po_wait": 0, "done": 0, "running": 0, "normal": 0}
    alerts = []
    holds = []
    po_waits = []
    normals = []
    seen_projects = set()
    hit_projects = set()

    for pk, proj in (data.get("projects") or {}).items():
        # 사업부를 지정했으면 그 목록에 없는 프로젝트는 무조건 뺀다.
        # 목록을 못 읽었다고 전사를 세면 '반도체 기준' 이라 적힌 카드에
        # 남의 숫자가 들어간다 — 비는 편이 낫다.
        if scoped:
            if pk not in visible:
                continue
        elif visible and pk not in visible:
            continue
        models = proj.get("models") or []
        if not models:
            continue
        seen_projects.add(pk)
        label = _display_project_label(pk)
        _phold = _project_hold(proj)
        for m in models:
            if not isinstance(m, dict):
                continue
            try:
                e = _enrich_model(m, _phold)
            except Exception:
                continue
            counts["total"] += 1
            def _row(kind, extra=""):
                return {
                    "project_key": pk, "project": label,
                    "model": e.get("name") or e.get("id") or "",
                    "id": e.get("id") or "", "kind": kind,
                    "expected": str(e.get("current_expected") or ""),
                    "days": None,
                    "stage": extra or str(e.get("current_stage") or ""),
                    "note": str(e.get("note") or "").strip().replace("\n", " · "),
                }

            hold = str(e.get("hold") or "")
            if hold:
                counts["hold"] += 1
                holds.append(_row(hold))
            if e.get("po_wait"):
                counts["po_wait"] += 1
                po_waits.append(_row("PO 대기", "PO 미접수 · 최종승인 완료"
                                     if e.get("finished") else "PO 미접수"))
            done = bool(e.get("finished")) or int(e.get("progress") or 0) >= 100
            if done:
                counts["done"] += 1
            # 드롭·보류는 늦은 게 아니다. 완료된 것도 마찬가지.
            kind = "" if (hold or done) else str(e.get("alert") or "")
            if kind == "지연":
                counts["delayed"] += 1
            elif kind == "주의":
                counts["soon"] += 1
            _iss0 = str(e.get("issues") or "").strip()
            if kind in ("지연", "주의"):
                exp = str(e.get("current_expected") or "")
                d = _parse_any_date(exp)
                alerts.append({
                    "project_key": pk,
                    "project": label,
                    "model": e.get("name") or e.get("id") or "",
                    "id": e.get("id") or "",
                    "kind": "지연" if kind == "지연" else "임박",
                    "expected": exp,
                    "days": (today - d).days if d else None,
                    "stage": str(e.get("current_stage") or ""),
                    "note": str(e.get("note") or "").strip().replace("\n", " · "),
                    # 지연 판정이 이슈 칸에서 나온 경우가 있다. 그때는
                    # 적어 둔 내용이 곧 이유다.
                    "issue": _iss0.replace("\n", " · ") if kind == "지연" else "",
                })
                hit_projects.add(pk)

            # 이슈 — 적어 둔 문제. 지연과 겹치지 않는다: 지연은 개발품 공정이 밀린 것이고, 이슈는 주로 양산품에 사람이 적어 넣은 것이다
            _iss = _iss0
            if _iss and not hold and not done and kind != "지연":
                counts["issue"] += 1
                alerts.append({
                    "project_key": pk,
                    "project": label,
                    "model": e.get("name") or e.get("id") or "",
                    "id": e.get("id") or "",
                    "kind": "이슈",
                    "expected": str(e.get("current_expected") or ""),
                    "days": None,
                    "stage": str(e.get("current_stage") or ""),
                    "note": str(e.get("note") or "").strip().replace("\n", " · "),
                    "issue": _iss.replace("\n", " · "),
                })
                hit_projects.add(pk)

            # 정상 — 문제 없이 가고 있는 것.
            if (not hold and not done and not _iss0
                    and kind not in ("지연", "주의")):
                counts["normal"] += 1
                normals.append(_row("정상"))

    # 주차 미달도 이슈다. "계획 대비 실적이 안 나오면 이슈가 있는 거 아닐까?"
    # 단, 끝난 주차만 보고, 사유가 '참고' 로 적혀 있으면 세지 않는다
    # (엔클로저는 매출을 맞추려고 일부러 덜 출하하기도 한다).
    for pk, proj in (data.get("projects") or {}).items():
        # 위 반복에서 모델이 있어 이미 센 프로젝트만 본다. 나머지는 보드도
        # 비어 있어서 계산만 하고 버리게 된다.
        if pk not in seen_projects:
            continue
        try:
            if _project_hold(proj):
                continue
            # 주차 보드 한 장을 만드는 건 비싸다. 이 달에 주차 계획이
            # 한 칸도 없는 프로젝트는 미달이 나올 수가 없으니 먼저 거른다.
            if not _has_week_plan(proj, today.strftime("%Y-%m")):
                continue
            _last_wk, _sh = _weekly_shortfall_cached(pk, today.strftime("%Y-%m"))
        except Exception as _e:
            print(f"[home/alerts] {pk} 주차 미달 계산 실패: {_e}")
            continue
        label = _display_project_label(pk)
        # 방금 끝난 주만 본다. 3주 전에 못 채운 것은 이미 지나간 이야기고, 마감 주차가 쌓일수록 목록이 주차 미달로만 가득 찬다
        _last = [_last_wk]
        if not _sh:
            continue
        # 미달은 합계 기준이라 주차당 한 건이다.
        _why = _sh.get("reason") or "사유 미입력"
        counts["issue"] += 1
        alerts.append({
            "project_key": pk, "project": label,
            "model": f"{_last[0]} 계획 미달",
            "id": "", "kind": "이슈",
            "expected": "", "days": None,
            "stage": "주차 합계",
            "note": "",
            "issue": (f"계획 {_sh.get('plan')} → 실적 {_sh.get('actual')}"
                      f" (미달 {_sh.get('short')} · {_sh.get('rate')}%) · {_why}"),
        })
        hit_projects.add(pk)

    counts["running"] = max(0, counts["total"] - counts["done"] - counts["delayed"]
                            - counts["soon"] - counts["hold"])

    # 프로젝트 단위 묶음. 홈에서 모델 55줄을 세로로 늘어놓으면 아무도 안 읽는다.
    by_project = {}
    for a in alerts:
        row = by_project.setdefault(a["project_key"], {
            "key": a["project_key"], "label": a["project"],
            "delayed": 0, "issue": 0, "soon": 0,
            "worst_days": 0, "worst_model": "",
        })
        if a["kind"] == "지연":
            row["delayed"] += 1
        elif a["kind"] == "이슈":
            row["issue"] += 1
        else:
            row["soon"] += 1
        d = a["days"] if a["days"] is not None else 0
        if d > row["worst_days"]:
            row["worst_days"] = d
            row["worst_model"] = a["model"]
    # 문제(지연 + 이슈) 많은 곳 → 가장 오래 밀린 곳 → 임박 많은 곳
    def _by_trouble(r):
        return (-(r["delayed"] + r["issue"]), -r["worst_days"], -r["soon"])
    rows = sorted(by_project.values(), key=_by_trouble)

    # 타일별 내역. 홈의 '전체 현황' 타일을 누르면 그 종류가 어느 프로젝트에
    # 몇 건씩 있는지가 바로 아래 펼쳐진다. 전에는 타일(합계)과 목록(내역)이
    # 카드 두 장으로 떨어져 있어서 서로 무슨 관계인지가 안 보였다.
    _by_kind = {k: {} for k in ("지연", "이슈", "임박", "보류", "정상")}
    for a in alerts:
        b = _by_kind.get(a["kind"])
        if b is None:
            continue
        r = b.setdefault(a["project_key"],
                         {"key": a["project_key"], "label": a["project"], "count": 0})
        r["count"] += 1
    for h in holds:
        r = _by_kind["보류"].setdefault(
            h["project_key"],
            {"key": h["project_key"], "label": h["project"], "count": 0})
        r["count"] += 1
    for h in normals:
        r = _by_kind["정상"].setdefault(
            h["project_key"],
            {"key": h["project_key"], "label": h["project"], "count": 0})
        r["count"] += 1
    # 종류(지연 · 이슈 …)마다, 건수 많은 것부터 · 같으면 이름순
    def _by_count_then_label(r):
        return (-r["count"], r["label"])
    by_kind = {}
    for k, v in _by_kind.items():
        by_kind[k] = sorted(v.values(), key=_by_count_then_label)
    # -----------------------------------------------------------
    # 사업부로 묶은 같은 내역
    # -----------------------------------------------------------
    # 프로젝트로 줄을 세우면 121곳이다
    _div_label = {}
    for _d in _cl.get_divisions(visible_only=False):
        _div_label[str(_d.get("id") or "")] = str(_d.get("label") or _d.get("id") or "")
    _by_div = {k: {} for k in _by_kind}
    for k, v in _by_kind.items():
        for r in v.values():
            try:
                did = _cl.derive_division_from_project(r["key"]) or ""
            except Exception:
                did = ""
            if not did:
                # 사업부를 못 찾은 프로젝트는 버리지 않는다. 숫자가
                # 조용히 비면 합이 안 맞는 이유를 못 찾는다.
                did, lab = "_etc", "기타"
            else:
                lab = _div_label.get(did, did)
            row = _by_div[k].setdefault(did, {"key": did, "label": lab,
                                              "count": 0, "projects": 0, "items": []})
            row["count"] += r["count"]
            row["projects"] += 1
            # 사업부 줄을 누르면 펼쳐 볼 프로젝트 (어느 프로젝트에 몇 건인가)
            row["items"].append(dict(r))
    # -----------------------------------------------------------
    # 프로젝트마다 걸린 모델 이름 몇 개 — 펼친 줄에 '모델 EFEM · CB 외 2' 로 보인다
    # -----------------------------------------------------------
    _names = {}
    for a in alerts:
        _names.setdefault((a["kind"], a["project_key"]), []).append(str(a.get("model") or ""))
    for h in holds:
        _names.setdefault(("보류", h["project_key"]), []).append(str(h.get("model") or ""))
    # 같은 줄 세우기 — 사업부로 접은 목록 (펼친 프로젝트도 건수 많은 것부터)
    by_kind_div = {}
    for k, v in _by_div.items():
        for row in v.values():
            row["items"].sort(key=_by_count_then_label)
            for it in row["items"]:
                names = [x for x in _names.get((k, it["key"]), []) if x]
                it["models"] = names[:3]
                it["more"] = max(0, len(names) - 3)
        by_kind_div[k] = sorted(v.values(), key=_by_count_then_label)
    # 문제(지연·이슈) 먼저, 그 안에서는 오래 밀린 것부터. 임박은 뒤로.
    _ORD = {"지연": 0, "이슈": 1}
    def _by_kind_then_days(a):
        kind_rank = _ORD.get(a["kind"], 2)          # 지연 0 · 이슈 1 · 나머지 2
        days = a["days"] if a["days"] is not None else -9999
        return (kind_rank, -days)                   # 오래 밀린 것(일수 큰 것)부터
    alerts.sort(key=_by_kind_then_days)
    try:
        # 앱 목록 화면은 칩에 '임박 34' 라고 써 놓고 목록은 잘린 걸 보여준다.
        # 숫자와 목록이 어긋나면 그게 또 '연결성이 없다' 다. 넉넉히 준다.
        n = max(1, min(300, int(limit)))
    except (TypeError, ValueError):
        n = 12
    # 블룸은 모델이 없고 일 보고 보드로 움직인다. 진행이 있는데도
    # 홈에서 '진행 데이터 없음' 으로 보이던 이유가 이거다.
    bloom = None
    try:
        board, _ = _bloom_board_for(_BLOOM_STORE)
        if board and (board.get("dates") or []):
            _dates = board.get("dates") or []
            _day = today.strftime("%Y-%m-%d")
            if _day not in _dates:
                _day = _dates[-1]
            _sm = _bloom_summary(board, _day) or {}
            _cur = _sm.get("today") or {}
            _prev = _sm.get("prev") or {}
            bloom = {
                "date": _day,
                "plan": int(_cur.get("plan") or 0),
                "actual": int(_cur.get("actual") or 0),
                "pending": bool(_cur.get("pending")),
                "prev_date": str(_prev.get("date") or ""),
                "prev_plan": int(_prev.get("plan") or 0),
                "prev_actual": int(_prev.get("actual") or 0),
                "items": len(board.get("items") or []),
            }
    except Exception as _e_b2:
        print(f"[home] 블룸 요약 실패(무시): {_e_b2}")

    return {
        "date": today.strftime("%Y-%m-%d"),
        "counts": counts,
        "projects": len(seen_projects),
        "projects_with_alert": len(hit_projects),
        "by_project": rows,
        "by_kind": by_kind,
        "by_kind_div": by_kind_div,
        "alerts": alerts[:n],
        "alerts_total": len(alerts),
        "holds": holds[:n],
        "po_waits": po_waits[:n],
        "normals": normals[:n],
        "bloom": bloom,
    }


# ==== 캘린더에 띄울 일정 — 운영 자료에서 바로 모은다
_CAL_CACHE: dict = {"key": None, "data": None}

# ============================================================
#  캘린더 — 일정 · 마감
# ============================================================
def _cal_date(v):
    import re as _re
    import datetime as _d
    m = _re.search(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", str(v or ""))
    if not m:
        return None
    try:
        return _d.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None                          # 2026-06-31 같은 없는 날짜


# weekly_plan['2026-11']['W46'] → 그 주 월요일.
def _cal_week_monday(month_key: str, wk: str):
    import datetime as _d
    try:
        y, mo = int(str(month_key)[:4]), int(str(month_key)[5:7])
        n = int(str(wk).upper().lstrip("W"))
    except (TypeError, ValueError):
        return None
    if mo == 12 and n == 1:
        y += 1
    elif mo == 1 and n >= 52:
        y -= 1
    try:
        return _d.date.fromisocalendar(y, n, 1)
    except ValueError:
        return None


# 단계 이름 → 캘린더 분류. 앱 필터(출하·입고·보고·승인·마일스톤)와 같은 말.
def _cal_category(step: str) -> str:
    t = str(step or "").upper()
    if any(w in t for w in ("입고",)):
        return "receiving"
    if any(w in t for w in ("출하", "출고", "선적", "납품", "SOP")):
        return "shipping"
    if any(w in t for w in ("승인", "검토", "확정", "FAIR", "LAIR", "PPAP",
                            "PRR", "TPM", "심사", "SR ")):
        return "approval"
    if any(w in t for w in ("보고", "리뷰", "회의")):
        return "report"
    return "milestone"


# 운영 자료 → (날짜 있는 일정, 날짜 없는 지연·임박).
def _calendar_events() -> tuple:
    import datetime as _d
    today = _d.date.today()
    data = _load_models()
    _key = (_MODELS_CACHE.get("key"), today.isoformat())
    if _key[0] is not None and _CAL_CACHE.get("key") == _key:
        return _CAL_CACHE["data"]

    # 화면에 보이는 프로젝트만 — 꺼 둔 프로젝트(양식에서 빠진 것)는 뺀다
    try:
        _vis = {p.get("id"): p for p in _cl.get_projects(visible_only=True)}
        _divl = {d.get("id"): d.get("label") for d in _cl.get_divisions(visible_only=False)}
    except Exception:
        _vis, _divl = {}, {}

    out = []
    undated = []
    for pk, proj in (data.get("projects") or {}).items():
        if _vis and pk not in _vis:
            continue
        models = [m for m in (proj.get("models") or []) if isinstance(m, dict)]
        if not models:
            continue
        if _project_hold(proj):
            continue
        did = (_vis.get(pk) or {}).get("division_id") or ""
        base = {"project_key": pk, "project": _display_project_label(pk),
                "division_id": did, "division": _divl.get(did, did)}
        # -----------------------------------------------------------
        # 1) 개발 단계
        # -----------------------------------------------------------
        for m in models:
            try:
                e = _enrich_model(m, "", did)
            except Exception:
                continue
            if e.get("hold"):
                continue
            proc = e.get("process") or []
            cur = str(e.get("current_stage") or "")
            alert = str(e.get("alert") or "")
            name = e.get("name") or e.get("id") or ""
            placed = False                   # 지연·임박을 날짜 칸에 놓았나
            for i, st in enumerate(proc):
                if not isinstance(st, dict):
                    continue
                step = str(st.get("name") or "").strip()
                act = _cal_date(st.get("actual"))
                exp = _cal_date(st.get("expected"))
                if act:
                    day, status = act, "done"
                elif exp:
                    day, status = exp, "planned"
                    if step and step == cur:
                        if alert == "지연":
                            status = "late"
                            placed = True
                        elif alert == "주의":
                            status = "soon"
                            placed = True
                else:
                    continue
                out.append(dict(base, **{
                    "id": "step:%s:%s:%d" % (pk, e.get("id") or name, i),
                    "date": day.isoformat(), "kind": "step",
                    "category": _cal_category(step), "status": status,
                    "title": "%s · %s" % (name, step) if step else name,
                    "model": name, "step": step,
                    "expected": exp.isoformat() if exp else "",
                    "days": (today - exp).days if (status == "late" and exp) else None,
                }))
            if alert in ("지연", "주의") and not placed:
                why = str(e.get("note") or e.get("issues") or "").strip()
                undated.append(dict(base, **{
                    "id": "undated:%s:%s" % (pk, e.get("id") or name),
                    "kind": "undated", "category": "milestone",
                    "status": "late" if alert == "지연" else "soon",
                    "title": name + ((" · " + why.splitlines()[0][:40]) if why else ""),
                    "model": name, "note": why,
                }))
        # -----------------------------------------------------------
        # 2) 주차 계획 — 프로젝트 · 주차마다 한 줄로 묶는다.
        # -----------------------------------------------------------
        #    품목마다 한 줄이면 네트워크 한 주에 수십 줄이 서서 아무것도 안 보인다.
        wk = {}
        for m in models:
            if _model_hold(m):
                continue
            for mon, weeks in (m.get("weekly_plan") or {}).items():
                for w, c in (weeks or {}).items():
                    plan = _as_int((c or {}).get("plan"))
                    if plan <= 0:
                        continue
                    day = _cal_week_monday(mon, w)
                    if not day:
                        continue
                    a = wk.setdefault((day, str(w).upper()), {"plan": 0, "actual": 0, "items": 0})
                    a["plan"] += plan
                    a["actual"] += _as_int((c or {}).get("actual"))
                    a["items"] += 1
        for (day, w), a in wk.items():
            over = day + _d.timedelta(days=6) < today
            out.append(dict(base, **{
                "id": "ship:%s:%s:%s" % (pk, day.isoformat(), w),
                "date": day.isoformat(), "kind": "ship_plan",
                "category": "shipping",
                # 지난 주는 '끝난 주' 로만 둔다. 미달을 여기서 따로 '지연' 으로
                # 세면 홈 숫자와 또 갈린다 — 계획 · 실적 숫자를 그대로 보여 준다.
                "status": "done" if over else "planned",
                "title": "%s 출하 계획 %d대%s" % (
                    w, a["plan"], (" · 실적 %d대" % a["actual"]) if (over or a["actual"]) else ""),
                "week": w, "qty_plan": a["plan"], "qty_actual": a["actual"],
                "items": a["items"],
            }))

    # 날짜 있는 일정: 날짜 → 사업부 → 프로젝트 → 제목 순
    def _by_date(x):
        return (x["date"], x["division"], x["project"], x["title"])
    # 날짜 없는 일정: 지연인 것 먼저 (False 가 앞) → 사업부 → 프로젝트 → 제목
    def _late_first(x):
        return (x["status"] != "late", x["division"], x["project"], x["title"])
    out.sort(key=_by_date)
    undated.sort(key=_late_first)
    _CAL_CACHE["key"] = _key
    _CAL_CACHE["data"] = (out, undated)
    return out, undated


# 캘린더 일정. start · end(YYYY-MM-DD)로 자르고 division 으로 거른다 ← 앱 calendar_service.dart fetch()
@app.get("/calendar/events")
def get_calendar_events(start: str = "", end: str = "", division: str = ""):
    ev, undated = _calendar_events()
    s0 = str(start or "")[:10]
    e0 = str(end or "")[:10]
    dv = str(division or "").strip()
    rows = [x for x in ev
            if (not s0 or x["date"] >= s0) and (not e0 or x["date"] <= e0)
            and (not dv or x["division_id"] == dv)]
    und = [x for x in undated if not dv or x["division_id"] == dv]
    cnt = {"step": 0, "ship_plan": 0, "late": 0, "soon": 0, "done": 0, "planned": 0}
    for x in rows + und:
        cnt[x["kind"]] = cnt.get(x["kind"], 0) + 1
        cnt[x["status"]] = cnt.get(x["status"], 0) + 1
    # late · soon 은 날짜 없는 것까지 더한 값이다 — 홈의 '일정 지연' 과 같아야 한다
    return {"events": rows, "undated": und, "counts": cnt}

# ============================================================
#  모델 상세
# ============================================================
def _model_mix_note(models: list) -> str:
    total = mass = dev = 0
    for m in (models or []):
        if not isinstance(m, dict):
            continue
        total += 1
        if _display_group(m) == "개발":
            dev += 1
        else:
            mass += 1
    if not total:
        return ""
    return "총 %d종 중 양산 %d종, 개발 %d종" % (total, mass, dev)


# 앱용 확장 모델 목록: dev_type, 자동 진행률, 현황(현재 단계), 완료예정일, status_note 포함
# ← admin v2 _devProgRender() · loadStatusNote() 외
@app.get("/projects/{project_key}/models/detail")
def get_project_models_detail(project_key: str):
    _key = _model_key_alias(project_key)
    data = _load_models()
    proj = data.get("projects", {}).get(_key, {})
    _phold = _project_hold(proj)
    # 이 프로젝트가 어느 사업부인가 — 개발 품목을 어느 틀로 그릴지가 갈린다
    # (아리스타는 양산 틀. _frame_group)
    try:
        _div = _cl.derive_division_from_project(_key) or ""
    except Exception:
        _div = ""
    changed = False
    enriched = []
    for m in proj.get("models", []):
        if not isinstance(m, dict):
            continue
        # -----------------------------------------------------------
        # 전에 깔린 반도체 13단계를 걷어낸다
        # -----------------------------------------------------------
        # _ensure_process 가 사업부를 안 보고 기본 13단계를 깔던 때 자료에 박힌 것들이다
        if (_div and _div != "semiconductor"
                and m.get("group") == "개발"
                and _dev_steps_blank(m.get("process"))
                and [str((x or {}).get("name") or "") for x in m["process"]]
                    == [n for _k, n, _g in DEV_PROCESS_STEPS]):
            m["process"] = []
            changed = True
        if m.get("group") == "개발" and (not isinstance(m.get("process"), list) or len(m.get("process")) not in (12, 13, 14, 15)):
            changed = True
        enriched.append(_inject_weekly_summary(_enrich_model(m, _phold, _div)))
    # -----------------------------------------------------------
    # 읽기만 하는 길에서 저장하지 않는다
    # -----------------------------------------------------------
    # 여기는 GET 이다. 그런데 'changed' 가 서면 models.json 을 통째로 다시 쓰고, _save_models 는 쓰기 전에 백업 사본까지 한 장 뜬다
    _ = changed
    # 양산을 앞에, 개발을 뒤에 (같은 구분 안에서는 원래 순서 그대로)
    enriched.sort(key=lambda x: 0 if x.get("group") == "양산" else 1)
    return {
        "project_key": _key,
        # 이 프로젝트에 주차 현황 보드를 띄울까. 앱이 키 목록을
        # 들고 있던 것(_boardProjects)을 서버로 옮겼다 — 앱을 더 못 올린다.
        # 바꾸려면 division_columns.UI 의 project_board_keys 한 줄.
        "board": _dcol.board_on(_div, _key),
        "has_models": len(enriched) > 0,
        "total": len(enriched),
        # 사람이 적던 현황 글 대신 모델 수를 센 한 줄.
        "status_note": _model_mix_note(enriched),
        "status_note_memo": proj.get("status_note") or "",
        "hold": _phold,
        "hold_reason": _project_hold_reason(proj) if _phold else "",
        "models": enriched,
    }


# 모델 ID 에 '/' 가 들어가는 경우(예: 925-800083-711/-712) 경로 파라미터로는
# 라우팅이 안 되므로(퍼센트 인코딩이 경로 매칭 전에 풀림), 쿼리 파라미터
# 방식의 동일 기능 엔드포인트를 함께 제공한다.

# ============================================================
#  모델 주차 · 공정 (?model_id= 로)
# ============================================================
# 모델 하나의 주차별 계획·실적 (모델 id 를 ?model_id= 로).
# ← admin v2 _wpLoadOne() · _sbEl.onclick() · loadModelWeeklyData()
@app.get("/projects/{project_key}/model-weekly-plan")
def get_model_weekly_plan_q(project_key: str, model_id: str, month: str = None):
    return get_model_weekly_plan(project_key, model_id, month)


# 모델 하나의 주차별 계획·실적 고치기 (잠김) ← admin v2 _sbEl.onclick()
@app.put("/admin/projects/{project_key}/model-weekly-plan")
def put_model_weekly_plan_q(project_key: str, model_id: str, payload: dict,
                            _admin: int = Depends(get_admin_session)):
    return put_weekly_plan(project_key, model_id, payload, _admin)


# 모델 하나의 개발 공정 (앱) ← admin v2 openProcessEditor() · renderProcessEditor() 외
@app.get("/projects/{project_key}/model-process")
def get_model_process_q(project_key: str, model_id: str):
    return get_model_process(project_key, model_id)


# 모델 하나의 개발 공정 (admin) ← admin v2 openProcessEditor() · renderProcessEditor()
@app.get("/admin/projects/{project_key}/model-process")
def admin_get_model_process_q(project_key: str, model_id: str,
                              _admin: int = Depends(get_admin_session)):
    return admin_get_model_process(project_key, model_id, _admin)


# 모델 하나의 개발 공정 고치기 (잠김) ← admin v2 openProcessEditor() · renderProcessEditor()
@app.put("/admin/projects/{project_key}/model-process")
def admin_put_model_process_q(project_key: str, model_id: str, payload: dict,
                              _admin: int = Depends(get_admin_session)):
    return admin_put_model_process(project_key, model_id, payload, _admin)


# 공정 한 단계 상태 바꾸기 (잠김) ← admin v2 renderProcessEditor()
@app.post("/admin/projects/{project_key}/model-process/step-status")
def admin_set_process_step_status_q(project_key: str, model_id: str, payload: dict,
                                    _admin: int = Depends(get_admin_session)):
    return admin_set_process_step_status(project_key, model_id, payload, _admin)


# 양산 모델 월별 주차별 계획/실적 조회 ← get_model_weekly_plan_q (admin v2 의 ?model_id= 길)
@app.get("/projects/{project_key}/models/{model_id}/weekly-plan")
def get_model_weekly_plan(project_key: str, model_id: str, month: str = None):
    from urllib.parse import unquote
    import datetime as _dt
    model_id = unquote(model_id)
    _key = _model_key_alias(project_key)
    data = _load_models()
    proj = data.get("projects", {}).get(_key, {})
    if not month:
        month = _dt.date.today().strftime("%Y-%m")
    weeks = _get_month_weeks(month)
    target = next((m for m in proj.get("models", [])
                   if (m.get("id") or "").lower() == model_id.lower()), None)
    if not target:
        raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")
    bucket = (target.get("weekly_plan") or {}).get(month, {})
    rows, tp, ta = [], 0, 0
    for w in weeks:
        v = bucket.get(w, {"plan": 0, "actual": 0})
        p, a = int(v.get("plan") or 0), int(v.get("actual") or 0)
        rows.append({"week": w, "plan": p, "actual": a, "remaining": max(0, p - a)})
        tp += p
        ta += a
    return {"model_id": model_id, "model_name": target.get("name"), "month": month,
            "weeks": rows, "month_total_plan": tp, "month_total_actual": ta,
            "month_remaining": max(0, tp - ta),
            "excel_month_plan": (target.get("monthly_plan") or {}).get(month),
            "excel_month_actual": (target.get("monthly_actual") or {}).get(month),
            "progress": _ensure_mass_progress(target.get("weekly_plan") or {}, month)}


# ============================================================
#  그룹(양산/개발) 단위 주차 합계 · PO
# ============================================================
# 그룹(양산/개발) 단위 주차 합계 · PO 관리
#
# 하바플레이트 개발은 종수가 많고 모델별 주차 계획을 따로 잡지 않는다.
# 그래서 '개발' 은 모델이 아니라 그룹 총계로 주차 계획/실적을 입력한다.
# PO 수량과 '기초 누적 실적'(주차 입력 이전까지의 누적)도 여기서 관리해서,
# 엑셀 원본 없이도 PO/실적/잔량/PO증감 표를 계산해 낼 수 있게 한다.
#   weekly_summary[그룹] = {
#     po_qty, base_actual, next_month_plan,
#     ongoing_types, done_types,          # 개발 'N종 진행중 / M종 완료'
#     weeks: { "W32": {plan, actual}, ... },
#     po_history: [{date, from, to, note}]
#   }

# 구분 글자 → '양산' 또는 '개발'.
def _norm_group(g):
    return "개발" if str(g or "").strip() == "개발" else "양산"


# 프로젝트의 주차 요약(weekly_summary)에서 양산/개발 묶음.
def _group_bucket(proj, group):
    return (proj.get("weekly_summary") or {}).get(_norm_group(group)) or {}


# 양산 주차 합계는 모델별 weekly_plan 이 정본.
def _mass_week_totals(proj, month, weeks):
    out = {w: {"plan": 0, "actual": 0} for w in weeks}
    for m in proj.get("models", []):
        bucket = (m.get("weekly_plan") or {}).get(month) or {}
        for w in weeks:
            g, _ = _phase_at(m, month, w)
            if g != "양산":
                continue
            c = bucket.get(w) or {}
            out[w]["plan"] += int(c.get("plan") or 0)
            out[w]["actual"] += int(c.get("actual") or 0)
    return out


# 그 달에 '개발' 모델이 주차 숫자를 들고 있나.
def _dev_models_have_weeks(proj, month) -> bool:
    for m in proj.get("models", []):
        if _norm_group(m.get("group")) != "개발":
            continue
        if (m.get("weekly_plan") or {}).get(month):
            return True
    return False


# 개발 주차 합계.
def _dev_week_totals(proj, month, weeks):
    gw = (_group_bucket(proj, "개발").get("weeks") or {})
    if gw and not _dev_models_have_weeks(proj, month):
        return {w: {"plan": int((gw.get(w) or {}).get("plan") or 0),
                    "actual": int((gw.get(w) or {}).get("actual") or 0)} for w in weeks}
    out = {w: {"plan": 0, "actual": 0} for w in weeks}
    for m in proj.get("models", []):
        bucket = (m.get("weekly_plan") or {}).get(month) or {}
        for w in weeks:
            g, _ = _phase_at(m, month, w)
            if g != "개발":
                continue
            c = bucket.get(w) or {}
            out[w]["plan"] += int(c.get("plan") or 0)
            out[w]["actual"] += int(c.get("actual") or 0)
    return out


# 모델 목록에 직접 적은 PO 수량 / 실적 수량의 그룹 합계.
def _model_qty_sums(proj, group):
    group = _norm_group(group)
    po = ship = 0
    for m in proj.get("models", []):
        if _norm_group(m.get("group")) != group:
            continue
        po += int(m.get("po_qty") or 0)
        ship += int(m.get("shipped_qty") or 0)
    return po, ship


# 전 기간 주차 실적 합. 누적 실적 = base_actual + 이 값.
def _all_actual_sum(proj, group):
    group = _norm_group(group)
    if group == "개발":
        gw = _group_bucket(proj, "개발").get("weeks") or {}
        # 모델이 주차를 들고 있는 달이 하나라도 있으면 모델이 정본이다
        # (_dev_week_totals 와 같은 규칙 — 두 곳이 다르면 합계가 어긋난다)
        # 모델들이 주차 계획을 들고 있는 달 (그룹 주차가 비었으면 볼 필요 없다)
        _model_months = set()
        if gw:
            for _mdl in proj.get("models", []):
                for _mo in (_mdl.get("weekly_plan") or {}):
                    _model_months.add(_mo)
        _bymodel = False
        for _mon in _model_months:
            if _dev_models_have_weeks(proj, _mon):
                _bymodel = True
                break
        if gw and not _bymodel:
            return sum(int((v or {}).get("actual") or 0) for v in gw.values())
    total = 0
    for m in proj.get("models", []):
        for mon, bucket in (m.get("weekly_plan") or {}).items():
            for w, c in (bucket or {}).items():
                g, _ = _phase_at(m, mon, w)
                if g != group:
                    continue
                total += int((c or {}).get("actual") or 0)
    return total


# 그룹(개발) 주차 합계 조회. 모델별 조회와 같은 모양이라 화면을 그대로 재사용한다 ← admin v2 loadModelWeeklyData() · _sbEl.onclick()
@app.get("/projects/{project_key}/group-weekly-plan")
def get_group_weekly_plan(project_key: str, group: str = "개발", month: str = None):
    import datetime as _dt
    _key = _model_key_alias(project_key)
    proj = (_load_models().get("projects") or {}).get(_key) or {}
    group = _norm_group(group)
    month = (month or "").strip() or _dt.date.today().strftime("%Y-%m")
    weeks = _get_month_weeks(month)
    gw = _group_bucket(proj, group).get("weeks") or {}
    rows, tp, ta = [], 0, 0
    for w in weeks:
        c = gw.get(w) or {}
        p, a = int(c.get("plan") or 0), int(c.get("actual") or 0)
        rows.append({"week": w, "plan": p, "actual": a, "remaining": max(0, p - a)})
        tp += p
        ta += a
    return {"model_id": "__group__", "model_name": f"{group} (합계)", "group": group,
            "month": month, "weeks": rows,
            "month_total_plan": tp, "month_total_actual": ta,
            "month_remaining": max(0, tp - ta),
            "progress": round(min(100.0, ta / tp * 100), 1) if tp > 0 else 0.0}


# 그룹(개발) 주차 합계 저장 ← admin v2 _sbEl.onclick()
@app.put("/admin/projects/{project_key}/group-weekly-plan")
def put_group_weekly_plan(project_key: str, payload: dict, group: str = "개발",
                          month: str = None, _admin: int = Depends(get_admin_session)):
    import datetime as _dt
    _key = _model_key_alias(project_key)
    data = _load_models()
    proj = data.setdefault("projects", {}).setdefault(_key, {"models": []})
    group = _norm_group(payload.get("group") or group)
    month = (payload.get("month") or month or "").strip() or _dt.date.today().strftime("%Y-%m")
    weeks_in = payload.get("weeks") or {}
    ws = proj.setdefault("weekly_summary", {}).setdefault(group, {})
    cur = ws.setdefault("weeks", {})
    for w in _get_month_weeks(month):
        c = weeks_in.get(w) or {}
        cur[w] = {"plan": int(c.get("plan") or 0), "actual": int(c.get("actual") or 0)}
    _save_models(data)
    tp = sum(int((cur.get(w) or {}).get("plan") or 0) for w in _get_month_weeks(month))
    ta = sum(int((cur.get(w) or {}).get("actual") or 0) for w in _get_month_weeks(month))
    return {"ok": True, "group": group, "month": month,
            "month_total_plan": tp, "month_total_actual": ta,
            "progress": round(min(100.0, ta / tp * 100), 1) if tp > 0 else 0.0}


# PO 수량 / 기초 누적 실적 / 종수 / 다음달 계획 (그룹별) ← admin v2 openBoardEditor() · onclick()
@app.get("/projects/{project_key}/group-summary")
def get_group_summary(project_key: str, month: str = None):
    _key = _model_key_alias(project_key)
    proj = (_load_models().get("projects") or {}).get(_key) or {}
    out = {}
    for g in ("양산", "개발"):
        b = _group_bucket(proj, g)
        out[g] = {
            "po_qty": int(b.get("po_qty") or 0),
            "base_actual": int(b.get("base_actual") or 0),
            "next_month_plan": int(b.get("next_month_plan") or 0),
            "shipped_qty": int(b.get("shipped_qty") or 0),
            "ongoing_types": int(b.get("ongoing_types") or 0),
            "done_types": int(b.get("done_types") or 0),
            "po_history": b.get("po_history") or [],
        }
    import datetime as _dt2
    month = (month or "").strip() or _dt2.date.today().strftime("%Y-%m")
    return {"project_key": _key, "groups": out, "month": month,
            "delta_periods": _delta_periods(month),
            "po_delta_manual": _project_manual_deltas(proj, month)}


# PO 수량 등 저장. PO 수량이 바뀌면 증감 이력을 자동으로 남긴다 ← admin v2 onclick()
@app.put("/admin/projects/{project_key}/group-summary")
def put_group_summary(project_key: str, payload: dict,
                      _admin: int = Depends(get_admin_session)):
    import datetime as _dt
    _key = _model_key_alias(project_key)
    data = _load_models()
    proj = data.setdefault("projects", {}).setdefault(_key, {"models": []})
    ws = proj.setdefault("weekly_summary", {})
    today = (payload.get("date") or "").strip() or _dt.date.today().strftime("%Y-%m-%d")
    changed = []
    for g in ("양산", "개발"):
        src = (payload.get("groups") or {}).get(g)
        if not isinstance(src, dict):
            continue
        b = ws.setdefault(g, {})
        if "po_qty" in src:
            new_po = max(0, int(src.get("po_qty") or 0))
            old_po = int(b.get("po_qty") or 0)
            if new_po != old_po:
                hist = b.setdefault("po_history", [])
                hist.append({"date": today, "from": old_po, "to": new_po,
                             "note": str(src.get("po_note") or "")})
                b["po_history"] = hist[-200:]
                changed.append({"group": g, "from": old_po, "to": new_po})
            b["po_qty"] = new_po
        for f in ("shipped_qty", "base_actual", "next_month_plan",
                  "ongoing_types", "done_types"):
            if f in src:
                b[f] = max(0, int(src.get(f) or 0))

    # PO증감 직접 입력: [{period: '2026-03' | 'W36', delta: 619}, ...]
    # 양산/개발로 나누지 않고 합계 한 줄만 관리한다 (엑셀 표기와 동일).
    # 엑셀 업로드가 po_history 를 다시 만들어도 이건 지워지지 않게 따로 둔다.
    deltas = payload.get("po_deltas")
    if isinstance(deltas, list):
        rows = []
        for e in deltas:
            if not isinstance(e, dict):
                continue
            per = str(e.get("period") or "").strip()
            if not per:
                continue
            try:
                v = int(e.get("delta") or 0)
            except Exception:
                v = 0
            rows.append({"period": per, "delta": v})
        proj["po_delta_manual"] = rows
        for g in ("양산", "개발"):
            ws.get(g, {}).pop("po_delta_manual", None)

    _save_models(data)
    return {"ok": True, "project_key": _key, "changed": changed}

# ============================================================
#  현황 엑셀
# ============================================================
def _enrich_from_status(project_key: str, wb) -> dict:
    import hrva_status_import as _hs
    sheets = _hs.parse_workbook(wb)
    if not sheets:
        return {"sheets": 0}
    data = _load_models()
    _key = _model_key_alias(project_key)
    proj = data.setdefault("projects", {}).setdefault(_key, {"models": []})
    ws_all = proj.setdefault("weekly_summary", {})

    for g in ("양산", "개발"):
        ws_all.setdefault(g, {})["po_history"] = []
    weeks = 0
    for wno, name, d in sheets:
        st = d.get("status")
        if not st:
            continue
        day = _hs.week_monday(wno).strftime("%Y-%m-%d")
        wrote = False
        for g in ("양산", "개발"):
            dl = int((st.get(g) or {}).get("delta") or 0)
            if not dl:
                continue
            ws_all.setdefault(g, {}).setdefault("po_history", []).append(
                {"date": day, "week": f"W{wno:02d}", "delta": dl, "note": "엑셀"})
            wrote = True
        if wrote:
            weeks += 1

    st = (sheets[-1][2] or {}).get("status") or {}
    for g in ("양산", "개발"):
        src = st.get(g) or {}
        b = ws_all.setdefault(g, {})
        if src.get("po"):
            b["po_qty"] = int(src["po"])
        if src.get("ship"):
            b["shipped_qty"] = int(src["ship"])
    if st.get("ongoing_types") or st.get("done_types"):
        dev = ws_all.setdefault("개발", {})
        dev["ongoing_types"] = int(st.get("ongoing_types") or 0)
        dev["done_types"] = int(st.get("done_types") or 0)
    _save_models(data)
    return {"sheets": len(sheets), "history_weeks": weeks,
            "ongoing_types": st.get("ongoing_types"), "done_types": st.get("done_types")}


# 하바플레이트 주간 현황 엑셀(W6~W35 시트)을 읽어 PO 수량·출하수량을 맞춘다 ← admin v2 _pfStatusImport()
@app.post("/admin/projects/{project_key}/status-excel")
async def admin_import_status_excel(project_key: str,
                                    file: UploadFile = File(...),
                                    all_sheets: str = Form("1"),
                                    _admin: int = Depends(get_admin_session)):
    _form_only("status-excel")
    import io as _io, openpyxl as _xl
    import hrva_status_import as _hs

    _key = _model_key_alias(project_key)
    raw = await _keep_upload(file, "/admin/projects/{project_key}/status-excel", project_key)
    try:
        wb = _xl.load_workbook(_io.BytesIO(raw), data_only=True, keep_links=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"엑셀을 열 수 없습니다: {e}")

    sheets = _hs.parse_workbook(wb)
    if not sheets:
        raise HTTPException(status_code=400, detail="W숫자 형태의 시트를 찾지 못했습니다.")

    use_all = str(all_sheets).lower() not in ("0", "false", "no", "")
    data = _load_models()
    proj = data.setdefault("projects", {}).setdefault(_key, {"models": []})
    ws_all = proj.setdefault("weekly_summary", {})
    # -----------------------------------------------------------
    # PO증감 이력: 각 시트의 '변동' 을 그 주 월요일 날짜로 기록
    # -----------------------------------------------------------
    hist_weeks = []
    if use_all:
        for g in ("양산", "개발"):
            ws_all.setdefault(g, {})["po_history"] = []
        for wno, name, d in sheets:
            st = d.get("status")
            if not st:
                continue
            day = _hs.week_monday(wno).strftime("%Y-%m-%d")
            wrote = False
            for g in ("양산", "개발"):
                dl = int((st.get(g) or {}).get("delta") or 0)
                if not dl:
                    continue
                ws_all.setdefault(g, {}).setdefault("po_history", []).append(
                    {"date": day, "week": f"W{wno:02d}", "delta": dl, "note": "엑셀"})
                wrote = True
            if wrote:
                hist_weeks.append(name)
    # -----------------------------------------------------------
    # 마지막(최신) 시트로 현재 상태를 맞춘다
    # -----------------------------------------------------------
    last_w, last_name, last = sheets[-1]
    st = last.get("status") or {}
    for g in ("양산", "개발"):
        src = st.get(g) or {}
        b = ws_all.setdefault(g, {})
        if src.get("po"):
            b["po_qty"] = int(src["po"])
        if src.get("ship"):
            b["shipped_qty"] = int(src["ship"])
    if st.get("ongoing_types") or st.get("done_types"):
        dev = ws_all.setdefault("개발", {})
        dev["ongoing_types"] = int(st.get("ongoing_types") or 0)
        dev["done_types"] = int(st.get("done_types") or 0)

    models = proj.setdefault("models", [])
    by_id = {str(m.get("id") or "").strip().lower(): m for m in models}
    updated, created, group_diff = 0, [], []
    for row in last.get("models") or []:
        mid = str(row.get("id") or "").strip()
        tgt = by_id.get(mid.lower())
        if tgt is None:
            entry = {
                "id": mid, "name": mid,
                "group": row.get("group") or "양산",
                "status": "정상", "progress": 0,
                "price": _as_money(row.get("price")),
                "material_cost": 0,
                "po_qty": int(row.get("po_qty") or 0),
                "shipped_qty": int(row.get("shipped_qty") or 0),
                "issues": "", "note": "",
            }
            if entry["group"] == "개발":
                entry["dev_type"] = str(row.get("dev_type") or "").upper()
                entry["process"] = _default_process()
            models.append(entry)
            by_id[mid.lower()] = entry
            created.append(mid)
            continue
        # 기존 모델은 구분을 바꾸지 않는다 (개발→양산 전환은 이력이 필요해서 별도 처리)
        if _norm_group(tgt.get("group")) != _norm_group(row.get("group")):
            group_diff.append(mid)
        tgt["po_qty"] = int(row.get("po_qty") or 0)
        tgt["shipped_qty"] = int(row.get("shipped_qty") or 0)
        if row.get("price"):
            tgt["price"] = _as_money(row["price"])
        if row.get("dev_type") and _norm_group(tgt.get("group")) == "개발":
            tgt["dev_type"] = str(row["dev_type"]).upper()
        updated += 1

    # 같은 파일 맨 아래의 주차표(파트번호 x 주차 계획·실적)도 같이 넣는다
    _weeks_in_file = _pbx_apply_sheet_months(proj, wb[last_name]) \
        if last_name in wb.sheetnames else []

    _save_models(data)
    if _weeks_in_file:
        print("[status-excel] %s 주차표도 반영: %s" % (
            _key, ", ".join("%s %d행" % (x["month"], x["applied"])
                            for x in _weeks_in_file)))
    return {
        "ok": True, "project_key": _key,
        "sheets": [n for _, n, _ in sheets],
        "applied_sheet": last_name,
        "updated": updated, "created": created,
        "group_diff": group_diff,
        "history_weeks": len(hist_weeks),
        "weeks_in_file": _weeks_in_file,
        "status": st,
    }

# ============================================================
#  보드 줄 · 수량
# ============================================================
def _load_board_spec(project_key):
    import json as _json
    from pathlib import Path as _Path
    try:
        p = _Path(__file__).resolve().parent / "config" / "boards.json"
        d = _json.loads(p.read_text(encoding="utf-8"))
        return (d.get("boards") or {}).get(project_key)
    except Exception as e:
        print(f"[board] boards.json 읽기 실패: {e}")
        return None


# 보드 안에서 이미 품번으로 지목된 모델들.
def _spec_claimed_models(spec) -> set:
    out = set()
    for sec in (spec.get("sections") or []):
        for row in (sec.get("rows") or []):
            for x in (row.get("models") or []):
                if str(x).strip():
                    out.add(str(x).strip())
    return out


# 행이 가리키는 모델 목록.
def _board_row_models(proj, row, claimed=None):
    ids = [str(x).strip() for x in (row.get("models") or []) if str(x).strip()]
    dt = str(row.get("dev_type") or "").strip().upper()
    grp = _norm_group(row.get("group")) if row.get("group") else None
    ex = {str(x).strip() for x in (row.get("exclude") or []) if str(x).strip()}
    ex_dt = {str(x).strip().upper() for x in (row.get("exclude_dev_type") or []) if str(x).strip()}
    # 품번을 직접 적은 행은 자기가 적은 걸 가져가야 하므로 자동 제외를 안 쓴다
    auto_ex = set() if ids else {str(x).strip() for x in (claimed or set()) if str(x).strip()}
    out = []
    for m in proj.get("models") or []:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "").strip()
        pn = str(m.get("part_number") or "").strip()
        mdt = str(m.get("dev_type") or "").strip().upper()
        if mid in ex or (pn and pn in ex):
            continue
        if mid in auto_ex or (pn and pn in auto_ex):
            continue
        if ex_dt and mdt in ex_dt:
            continue
        if ids:
            if mid in ids or pn in ids:
                out.append(m)
            continue
        if grp and _norm_group(_display_group(m)) != grp:
            continue
        if dt and mdt != dt:
            continue
        if grp or dt:
            out.append(m)
    return out


# 기준 주차 '다음' 주차부터의 실적 합.
def _row_actual_after(models, base_week):
    if not base_week:
        return 0
    try:
        by, bw = str(base_week).upper().split("-W")
        base_ord = int(by) * 100 + int(bw)
    except Exception:
        return 0
    total = 0
    for m in models:
        for mon, bucket in (m.get("weekly_plan") or {}).items():
            if not isinstance(bucket, dict):
                continue
            for w, c in bucket.items():
                if _week_ord(mon, w) > base_ord:
                    total += _as_int((c or {}).get("actual"))
    return total


# 그 달 주차별 계획/실적 합계.
def _board_week_qty(models, month, weeks):
    out = {w: {"plan": 0, "actual": 0} for w in weeks}
    for m in models:
        bucket = (m.get("weekly_plan") or {}).get(month) or {}
        for w in weeks:
            c = bucket.get(w) or {}
            out[w]["plan"] += _as_int(c.get("plan"))
            out[w]["actual"] += _as_int(c.get("actual"))
    return out


# '현황' 칸.
def _board_row_status(models, spec_status, manual_status=None):
    if manual_status and str(manual_status).strip():
        return str(manual_status).strip()
    if spec_status and str(spec_status).strip():
        return str(spec_status).strip()
    if not models:
        return ""
    progs = [m.get("progress") for m in models]
    if progs and all(isinstance(p, (int, float)) and p >= 100 for p in progs):
        return "완료"
    if any(_norm_group(m.get("group")) == "양산" for m in models):
        return "양산"
    return "개발"


_NOTE_ROLLUP_MIN = 3        # 메모가 붙은 모델이 이 개수 이상이면 나열 대신 묶는다
_BOARD_NOTE_CACHE_PATH = _Path_hl(__file__).parent / "board_note_cache.json"

# ============================================================
#  보드 메모 · AI 메모
# ============================================================
def _note_groups(models):
    acc, order = {}, []
    for m in (models or []):
        if not isinstance(m, dict):
            continue
        txt = " ".join(str(m.get("note") or "").split())
        if not txt:
            continue
        if txt not in acc:
            acc[txt] = 0
            order.append(txt)
        acc[txt] += 1
    return sorted(((t, acc[t]) for t in order), key=lambda kv: -kv[1])


# AI 없이 묶는 기본형: '카이저 원소재 11월말 입고 예정 10종 · 1EA 황삭 완료 1종'.
def _note_rollup_text(groups):
    return " · ".join(f"{t} {c}종" for t, c in groups)


# 요약문의 'N종' 합이 실제 종수와 같은지.
def _note_total_ok(text, total):
    import re as _re
    nums = [int(x) for x in _re.findall(r"(\d+)\s*종", text or "")]
    return bool(nums) and sum(nums) == total


# 묶음 행(Dep 챔버 15종 등)의 메모를 상태별 종수로 요약한다
def _ai_board_note(groups):
    if not groups:
        return ""
    total = sum(c for _, c in groups)
    raw = "\n".join(f"{c}종: {t}" for t, c in groups)
    key = _hashlib_hl.sha256(raw.encode("utf-8")).hexdigest()[:16]

    try:
        cache = _json_hl.loads(_BOARD_NOTE_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    if key in cache:
        return cache[key]

    result = ""
    try:
        if client is not None:
            prompt = (
                "반도체 부품 생산 현황표의 '비고' 칸을 만든다. "
                "여러 모델의 진행 메모를 상태별로 묶어 '상태 N종' 형태로 요약해라.\n"
                "규칙:\n"
                "- 항목은 ' · ' 로 구분하고 3~5개 이내로 줄인다.\n"
                "- 각 항목은 '상태 N종' 형태. 상태는 12자 이내 명사형.\n"
                "- N종의 합은 반드시 입력의 종수 합과 같아야 한다 (지어내지 말 것).\n"
                "- 많은 것부터 적는다. 날짜는 꼭 필요한 것만 남긴다.\n"
                "- 설명·머리말 없이 요약문 한 줄만 출력.\n"
                "예시 입력: '10종: 카이저 원소재 11월말 입고 예정 / 3종: 1EA 조립 완료 (고객측 확인 중) / "
                "1종: 1EA 황삭 완료'\n"
                "예시 출력: '원소재 입고 대기 10종 · 조립 완료(고객 확인 중) 3종 · 황삭 완료 1종'\n\n"
                f"입력:\n{raw}"
            )
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=160,
            )
            result = (resp.choices[0].message.content or "").strip()
            result = result.strip("\"'` ").split("\n")[0].strip()
    except Exception as e:
        print(f"[board] 비고 AI 요약 실패, 기본형으로 대체: {e}")
        result = ""

    # 종수가 안 맞으면 지어낸 것으로 보고 버린다
    if result and not _note_total_ok(result, total):
        print(f"[board] 비고 AI 요약 종수 불일치({total}종) — 버린다: {result}")
        result = ""
    if not result:
        return _note_rollup_text(groups)

    cache[key] = result
    try:
        _BOARD_NOTE_CACHE_PATH.write_text(
            _json_hl.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return result


# '비고' 칸.
def _board_row_note(models, spec_note, manual_note=None, summarize=None):
    if manual_note and str(manual_note).strip():
        return str(manual_note).strip()
    if spec_note and str(spec_note).strip():
        return str(spec_note).strip()

    groups = _note_groups(models)
    if not groups:
        return ""
    total = sum(c for _, c in groups)
    if total >= _NOTE_ROLLUP_MIN:
        if summarize:
            try:
                txt = summarize(groups)
                if txt:
                    return txt
            except Exception as e:
                print(f"[board] 비고 요약 실패, 기본형으로 대체: {e}")
        return _note_rollup_text(groups)

    lines, seen = [], set()
    multi = len(models or []) > 1
    for m in (models or []):
        if not isinstance(m, dict):
            continue
        txt = str(m.get("note") or "").strip()
        if not txt or txt in seen:
            continue
        seen.add(txt)
        name = str(m.get("id") or m.get("name") or "").strip()
        lines.append(f"{name}: {txt}" if (multi and name) else txt)
    return "\n".join(lines)


# 그 달 계획/실적 합계. 모델별 weekly_plan 을 월 소유 규칙대로 더한다
def _board_month_qty(models, mon):
    weeks = _get_month_weeks(mon)
    plan = actual = 0
    for m in models:
        bucket = (m.get("weekly_plan") or {}).get(mon) or {}
        for w in weeks:
            c = bucket.get(w) or {}
            plan += _as_int(c.get("plan"))
            actual += _as_int(c.get("actual"))
    return {"plan": plan, "actual": actual}


# 오늘 달을 마지막으로 하는 월 목록.
def _board_months(month, span):
    y, m = int(str(month)[:4]), int(str(month)[5:7])
    out = []
    for off in range(span - 1, -1, -1):
        mm = m - off
        yy = y + (mm - 1) // 12
        mm = (mm - 1) % 12 + 1
        out.append(f"{yy}-{mm:02d}")
    return out


# 직접 입력 칸이 '채워져 있는가'.
def _has(d, k):
    if not isinstance(d, dict):
        return False
    v = d.get(k)
    return v is not None and str(v).strip() != ""

# ============================================================
#  섹션 표 (_spec_board)
# ============================================================
def _spec_section_rows(proj, sec):
    rows = list(sec.get("rows") or [])
    if str(sec.get("rows_from") or "").strip() != "models":
        return rows
    # 이미 줄에 적힌 모델 이름 전부
    seen = set()
    for _row in rows:
        for _name in (_row.get("models") or []):
            seen.add(str(_name).strip())
    out = list(rows)
    for m in (proj.get("models") or []):
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "").strip()
        pn = str(m.get("part_number") or "").strip()
        if not mid or mid in seen or (pn and pn in seen):
            continue
        seen.add(mid)
        label = str(m.get("name") or mid).strip() or mid
        # 품번이 따로 있으면 '이름 (품번)' — 엑셀에 적힌 그대로다
        if pn and pn != label:
            label = f"{label} ({pn})"
        out.append({"key": f"m_{mid}", "label": label, "models": [mid]})
    return out

# 사람이 직접 적은 값이 있으면 그것, 없으면 계산한 값.
def _pick_manual(store, field, calculated):
    if _has(store, field):
        return _as_int(store[field])
    return calculated


# 여러 줄의 {bucket}[{key}] 안에 있는 계획·실적을 각각 더한다
def _sum_pair(rows, bucket, key) -> dict:
    plan_sum = 0
    actual_sum = 0
    for r in rows:
        cell = (r.get(bucket) or {}).get(key) or {}
        plan_sum += (cell.get("plan") or 0)
        actual_sum += (cell.get("actual") or 0)
    return {"plan": plan_sum, "actual": actual_sum}


# boards.json 스펙대로 그린 보드 (섹션 + 행).
def _spec_board(project_key, proj, spec, month):
    # -----------------------------------------------------------
    # 1. 열을 무엇으로 세울 것인가
    # -----------------------------------------------------------
    #    'week'  — 주차별(하바플레이트처럼 주 단위로 보는 프로젝트)
    #    'month' — 달별(챔버처럼 달 단위로 보는 프로젝트)
    #    둘은 열 구성이 아예 달라서 아래에서 길이 갈린다.
    col_mode = spec.get("columns") or "month"
    if col_mode == "week":
        weeks = _get_month_weeks(month)
    else:
        weeks = []
    # -----------------------------------------------------------
    # 2. 앞뒤 달 (1월의 지난달은 작년 12월, 12월의 다음달은 내년 1월)
    # -----------------------------------------------------------
    y = int(str(month)[:4])
    mm = int(str(month)[5:7])
    if mm == 1:
        prev_month = f"{y - 1}-12"
    else:
        prev_month = f"{y}-{mm - 1:02d}"
    if mm == 12:
        next_month = f"{y + 1}-01"
    else:
        next_month = f"{y}-{mm + 1:02d}"
    want_next = bool(spec.get("next_month"))   # 다음달 열을 그릴지
    # -----------------------------------------------------------
    # 3. 달별 보드일 때 몇 달치를 보여줄지 (기본 2달)
    # -----------------------------------------------------------
    span = int(spec.get("month_span") or 2)
    if col_mode == "week":
        months = []
    else:
        months = _board_months(month, span)
    manual_store = (proj.get("board_manual") or {})
    # 섹션 이름 밑에 적는 재고. 설정에 기본값을 두고, 프로젝트에 적어 둔 게
    # 있으면 그게 이긴다 — 재고는 주마다 바뀌므로 설정 파일에 묶어 두면 안 된다.
    stock_store = (proj.get("board_stock") or {})

    claimed = _spec_claimed_models(spec)

    sections, flat = [], []
    for sec in (spec.get("sections") or []):
        srows = []
        for row in _spec_section_rows(proj, sec):
            key = str(row.get("key") or row.get("label") or "")
            man = manual_store.get(key) or {}
            # 행마다 직접 입력이 있으면 그 값이 정본, 없으면 모델 합계.
            if row.get("manual"):
                models = []
            else:
                models = _board_row_models(proj, row, claimed)

            # 모델들에서 더한 값 (직접 적은 값이 없을 때 쓰는 기본값)
            po_m = 0
            act_m = 0
            for m in models:
                po_m += _as_int(m.get("po_qty"))
                act_m += _as_int(m.get("shipped_qty"))

            # 직접 적어 둔 값이 있으면 그게 이긴다
            if _has(man, "po_qty"):
                po = _as_int(man["po_qty"])
            else:
                po = po_m
            # 실적: 기준 누적(base_actual) + 기준 주차 이후 주차 실적.
            # 기준값을 안 적었으면 모델의 '실적 수량' 합계를 쓴다.
            if _has(man, "base_actual"):
                act = _as_int(man["base_actual"]) + _row_actual_after(
                    models, man.get("base_week"))
            elif _has(man, "actual_total"):
                act = _as_int(man["actual_total"])
            else:
                act = act_m
            # -----------------------------------------------------------
            # 달별 칸 채우기
            # -----------------------------------------------------------
            #    칸마다 규칙이 같다: 직접 적은 값이 있으면 그것, 없으면
            #    모델에서 계산한 값.
            mq = {}
            man_mon = man.get("months") or {}
            for mon in months:
                if models:
                    calc = _board_month_qty(models, mon)
                else:
                    calc = {"plan": 0, "actual": 0}
                mv = man_mon.get(mon) or {}
                mq[mon] = {
                    "plan": _pick_manual(mv, "plan", calc["plan"]),
                    "actual": _pick_manual(mv, "actual", calc["actual"]),
                }
            # -----------------------------------------------------------
            # 주차별 칸 채우기 (주차형 보드에서만)
            # -----------------------------------------------------------
            wq = {}
            prev_act = 0
            mon_plan = 0
            mon_act = 0
            next_plan = 0

            if col_mode == "week":
                calc_w = _board_week_qty(models, month, weeks)
                man_w = man.get("weeks") or {}
                for w in weeks:
                    mv = man_w.get(w) or {}
                    wq[w] = {
                        "plan": _pick_manual(mv, "plan", calc_w[w]["plan"]),
                        "actual": _pick_manual(mv, "actual", calc_w[w]["actual"]),
                    }

                # 이번 달 합계 = 주차 칸을 다 더한 것
                mon_plan = _sum_of(wq.values(), "plan")
                mon_act = _sum_of(wq.values(), "actual")

                # 지난달 실적
                if models:
                    pc = _board_month_qty(models, prev_month)
                else:
                    pc = {"plan": 0, "actual": 0}
                prev_act = _pick_manual(man, "prev_month_actual", pc["actual"])

                # 다음달 계획 (스펙이 그 열을 쓰겠다고 했을 때만)
                if want_next:
                    if models:
                        nc = _board_month_qty(models, next_month)
                    else:
                        nc = {"plan": 0}
                    next_plan = _pick_manual(man, "next_month_plan", nc["plan"])
            r = {
                "key": key,
                "label": row.get("label") or key,
                "section": sec.get("name") or "",
                "status": _board_row_status(models, row.get("status"), man.get("status")),
                "model_count": len(models),
                "po_qty": po,
                "actual_total": act,
                "remaining": po - act,
                "months": mq,
                "weeks": wq,
                "prev_month_actual": prev_act,
                "month_plan": mon_plan,
                "month_actual": mon_act,
                "next_month_plan": next_plan,
                "base_actual": (_as_int(man.get("base_actual"))
                                if _has(man, "base_actual") else None),
                "base_week": str(man.get("base_week") or ""),
                "note": _board_row_note(models, row.get("note"), man.get("note"),
                                        summarize=_ai_board_note),
                "manual_row": bool(row.get("manual")),
                "po_manual": _has(man, "po_qty"),
                "actual_manual": _has(man, "actual_total"),
            }
            srows.append(r)
            flat.append(r)
        # -----------------------------------------------------------
        # 섹션 묶기
        # -----------------------------------------------------------
        #    재고는 프로젝트에 적어 둔 값이 먼저다. 설정 파일(boards.json)의
        #    값은 기본값일 뿐이다 — 재고는 주마다 바뀌어서 설정에 묶어 두면
        #    고칠 때마다 배포해야 한다.
        _sname = sec.get("name") or ""
        _stock = stock_store.get(_sname, sec.get("stock"))
        if _stock in (None, ""):
            stock_val = None
        else:
            stock_val = _as_int(_stock)
        sections.append({"name": _sname, "rows": srows, "stock": stock_val})
    # -----------------------------------------------------------
    # 합계 줄 (섹션을 가리지 않고 모든 줄을 더한다)
    # -----------------------------------------------------------
    total = {"label": "합계"}
    for field in ("po_qty", "actual_total", "remaining", "prev_month_actual",
                  "month_plan", "month_actual", "next_month_plan"):
        total[field] = _sum_of(flat, field)

    # 달별 칸 합계
    total_months = {}
    for mon in months:
        total_months[mon] = _sum_pair(flat, "months", mon)
    total["months"] = total_months

    # 주차별 칸 합계
    total_weeks = {}
    for w in weeks:
        total_weeks[w] = _sum_pair(flat, "weeks", w)
    total["weeks"] = total_weeks
    import datetime as _dt
    _reasons = _week_reasons_of(proj, month)
    # -----------------------------------------------------------
    # 계획 미달 표시
    # -----------------------------------------------------------
    #    달 단위 보드(챔버)에는 '주차 미달'이라는 개념이 없다.
    #    주차형 보드에서만 계산한다.
    if col_mode == "week":
        _closed, _shorts = _mark_board_shortfalls(
            flat, total, weeks, month, _reasons)
    else:
        _closed, _shorts = [], []
    return {"project_key": project_key, "month": month, "layout": "sections",
            "closed_weeks": _closed, "shortfalls": _shorts,
            "week_reasons": _reasons if col_mode == "week" else {},
            "columns": col_mode, "months": months,
            "show_status": spec.get("show_status", True),
            "show_note": spec.get("show_note", True),
            "weeks": weeks, "prev_month": prev_month,
            "next_month": next_month if want_next else None,
            "current_week": ("W%02d" % _dt.date.today().isocalendar()[1]),
            # 오늘이 속한 달 — 그 열을 빨간 테두리로 표시한다
            # (주차형 보드의 current_week 와 같은 역할)
            "current_month": _dt.date.today().strftime("%Y-%m"),
            "sections": sections, "rows": flat, "total": total}

# ============================================================
#  미달 사유 · 보드 줄 저장 주소
# ============================================================
# 주차 미달 사유를 적는다 ← admin v2 saveWeekReason()
@app.put("/admin/projects/{project_key}/week-reason")
def admin_put_week_reason(project_key: str, payload: dict,
                          _admin: int = Depends(get_admin_session)):
    _write_off("week-reason")
    import datetime as _dt, re as _re
    _key = _model_key_alias(project_key)
    month = str(payload.get("month") or "").strip()
    if not _re.match(r"^\d{4}-\d{2}$", month):
        raise HTTPException(status_code=400, detail="month 는 YYYY-MM 이어야 합니다.")
    # 'W7' 과 'W07' 이 다른 키가 되면, 적어 둔 사유가 보드 어디에도 안 뜬다.
    _m = _re.match(r"^[Ww]?(\d{1,2})$", str(payload.get("week") or "").strip())
    if not _m or not (1 <= int(_m.group(1)) <= 53):
        raise HTTPException(status_code=400, detail="week 는 W01~W53 이어야 합니다.")
    week = "W%02d" % int(_m.group(1))
    kind = str(payload.get("kind") or "문제").strip()
    if kind not in _WEEK_REASON_KINDS:
        kind = "문제"
    text = str(payload.get("text") or "").strip()

    data = _load_models()
    # 없는 프로젝트에 적으면 빈 프로젝트가 생겨 목록·홈 집계에 끼어든다.
    if _key not in (data.get("projects") or {}):
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {_key}")
    proj = data["projects"][_key]
    store = proj.setdefault("week_reasons", {})
    if not isinstance(store, dict):
        store = proj["week_reasons"] = {}
    bucket = store.setdefault(month, {})
    if not isinstance(bucket, dict):
        bucket = store[month] = {}
    if not text:
        bucket.pop(week, None)
        if not bucket:
            store.pop(month, None)
    else:
        bucket[week] = {"kind": kind, "text": text,
                        "at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
    _save_models(data)
    return {"ok": True, "project_key": _key, "month": month, "week": week,
            "reasons": _week_reasons_of(proj, month)}


# 보드 행별 직접 입력값 (PO수량·실적·월·비고) ← admin v2 _wbOpenRowEditor() · onclick()
@app.get("/projects/{project_key}/board-rows")
def get_board_rows(project_key: str):
    _key = _model_key_alias(project_key)
    proj = (_load_models().get("projects") or {}).get(_key) or {}
    spec = _load_board_spec(_key)
    return {"project_key": _key,
            "has_spec": bool(spec),
            "spec": spec or {},
            "manual": proj.get("board_manual") or {},
            "stock": proj.get("board_stock") or {}}


# 보드 행별 직접 입력값 저장 ← admin v2 onclick()
@app.put("/admin/projects/{project_key}/board-rows")
def put_board_rows(project_key: str, payload: dict,
                   _admin: int = Depends(get_admin_session)):
    _key = _model_key_alias(project_key)
    data = _load_models()
    proj = data.setdefault("projects", {}).setdefault(_key, {"models": []})
    rows = payload.get("rows")
    if not isinstance(rows, dict):
        raise HTTPException(status_code=400, detail="rows 는 객체여야 합니다")

    # 섹션 재고 (프레임의 'CEFEM BE 재고: 79'). 빈 문자열이면 지운다.
    if isinstance(payload.get("stock"), dict):
        keep = {}
        for name, v in payload["stock"].items():
            if str(v).strip() != "":
                keep[str(name)] = _as_int(v)
        if keep:
            proj["board_stock"] = keep
        else:
            proj.pop("board_stock", None)

    store = {}
    for k, v in rows.items():
        if not isinstance(v, dict):
            continue
        e = {}
        for f in ("po_qty", "actual_total", "base_actual",
                  "prev_month_actual", "next_month_plan"):
            if _has(v, f):
                e[f] = _as_int(v[f])
        bw = str(v.get("base_week") or "").strip().upper()
        if bw:
            e["base_week"] = bw
        mons = {}
        for mon, mv in (v.get("months") or {}).items():
            if not isinstance(mv, dict):
                continue
            cell = {}
            for f in ("plan", "actual"):
                if _has(mv, f):
                    cell[f] = _as_int(mv[f])
            if cell:
                mons[str(mon)] = cell
        if mons:
            e["months"] = mons
        note = str(v.get("note") or "").strip()
        if note:
            e["note"] = note
        stt = str(v.get("status") or "").strip()
        if stt:
            e["status"] = stt
        if e:
            store[str(k)] = e

    proj["board_manual"] = store
    _save_models(data)
    print(f"[board] {_key} 행 직접입력 저장: {len(store)}행")
    return {"ok": True, "project_key": _key, "rows": len(store)}


# ============================================================
#  블룸 일 보드
# ============================================================
# 반도체와 코드를 공유하지 않는다. 반도체는 '주차 x 모델' 한 겹인데 블룸은 '날짜 x 품목 x 공정(NCT/조립/출하)' 세 겹이고 매일 실적이 들어온다

_BLOOM_DIFF_CAP = 60

# ============================================================
#  블룸 보드 합치기 · 접기
# ============================================================
def _bloom_pick(new_v, old_v):
    return old_v if new_v is None or new_v == "" else new_v


# 품목·공정에서 숫자가 적힌 마지막 날 — 둘 중 어느 쪽이 새 것인지 가른다
def _bloom_last_day(x) -> str:
    steps = x.get("steps") if isinstance(x, dict) and "steps" in x else [x]
    last = ""
    for st in steps or []:
        for d, v in ((st or {}).get("days") or {}).items():
            if isinstance(v, dict) and (v.get("plan") is not None or v.get("actual") is not None):
                last = max(last, str(d))
    return last


# 같은 공정이 이름만 달리 두 번 있으면 (NCT(박장) / NCT(박닌)) 하나로.
def _bloom_fold_steps(steps):
    import bloom_daily_import as _bd
    groups, order = {}, []
    for st in steps or []:
        if not isinstance(st, dict):
            continue
        k = _bd.step_key(st.get("step"))
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(st)
    out = []
    for k in order:
        g = sorted(groups[k], key=_bloom_last_day)
        cur = dict(g[0])
        for nx in g[1:]:
            days = dict(cur.get("days") or {})
            days.update(nx.get("days") or {})
            for f, v in nx.items():
                if f != "days":
                    cur[f] = _bloom_pick(v, cur.get(f))
            cur["days"] = days
        out.append(cur)
    return out


# 'Corva KPE' 와 'Corva KPE (117품목)' 처럼 이름만 다른 같은 품목을 하나로.
def _bloom_fold(items):
    import bloom_daily_import as _bd
    groups, order = {}, []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        k = _norm_label(_bd.clean_item(it.get("item")))
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(it)
    out = []
    for k in order:
        g = sorted(groups[k], key=_bloom_last_day)
        cur = dict(g[0])
        cur["item"] = _bd.clean_item(cur.get("item"))
        cur["steps"] = _bloom_fold_steps(cur.get("steps"))
        for nx in g[1:]:
            cur = _bloom_merge({"items": [cur]}, {"items": [nx]})[0]["items"][0]
        out.append(cur)
    return out


# (합쳐진 보드, 무엇이 바뀌는지).
def _bloom_merge(old: dict, parsed: dict):
    import bloom_daily_import as _bd

    old = old if isinstance(old, dict) else {}
    diff = {"items_new": [], "steps_new": [], "items_kept": [],
            "days_added": 0, "day_changes": [], "month_changes": []}

    # 품목은 '(N품목)' 꼬리를 뗀 이름으로, 공정은 괄호(공장)를 뗀 이름으로 맞춘다
    # 품목 이름을 다듬은 글자 — 옛 것과 새 것을 같은 품목끼리 맞출 때 쓴다
    def _ik(i):
        return _norm_label(_bd.clean_item(i.get("item")))
    old_items = {_ik(i): i for i in _bloom_fold(old.get("items"))}
    new_items = {_ik(i): i for i in _bloom_fold(parsed.get("items"))}
    keys = list(new_items) + [k for k in old_items if k not in new_items]

    merged = []
    for key in keys:
        nu, ol = new_items.get(key), old_items.get(key)
        name = (nu or ol).get("item")
        if nu is None:
            merged.append(ol)
            diff["items_kept"].append(name)
            continue
        if ol is None and old_items:
            diff["items_new"].append(name)

        entry = dict(ol or {})
        entry["item"] = name
        # owner(고객사)도 같이 담는다
        for f in ("code", "owner", "wait_ship", "wait_part"):
            entry[f] = _bloom_pick(nu.get(f), (ol or {}).get(f))

        old_steps = {_bd.step_key(s.get("step")): s
                     for s in _bloom_fold_steps((ol or {}).get("steps"))}
        new_steps = {_bd.step_key(s.get("step")): s
                     for s in _bloom_fold_steps(nu.get("steps"))}
        steps = []
        for skey in list(new_steps) + [k for k in old_steps if k not in new_steps]:
            ns, os_ = new_steps.get(skey), old_steps.get(skey)
            if ns is None:
                steps.append(os_)
                continue
            sname = ns.get("step")
            if os_ is None and old_steps:
                diff["steps_new"].append(f"{name} · {sname}")

            st = dict(os_ or {})
            st["step"] = sname
            st["group"] = ns.get("group") or _bd.step_group(sname)
            for f in ("wip", "prior_plan", "prior_actual"):
                st[f] = _bloom_pick(ns.get(f), (os_ or {}).get(f))
            for f in ("month_plan", "month_actual"):
                was = (os_ or {}).get(f)
                now = _bloom_pick(ns.get(f), was)
                if os_ is not None and was is not None and now != was \
                        and len(diff["month_changes"]) < _BLOOM_DIFF_CAP:
                    diff["month_changes"].append(
                        {"item": name, "step": sname, "field": f, "from": was, "to": now})
                st[f] = now
            _note = str(ns.get("note") or "").strip()
            st["note"] = _note or str((os_ or {}).get("note") or "")

            days = dict((os_ or {}).get("days") or {})
            for d, v in (ns.get("days") or {}).items():
                was = days.get(d)
                if was is None:
                    diff["days_added"] += 1
                elif was != v and len(diff["day_changes"]) < _BLOOM_DIFF_CAP:
                    diff["day_changes"].append(
                        {"item": name, "step": sname, "date": d, "from": was, "to": v})
                days[d] = v
            st["days"] = days
            steps.append(st)

        entry["steps"] = [s for s in steps if isinstance(s, dict)]
        merged.append(entry)

    merged = [m for m in merged if isinstance(m, dict)]
    # 품목들의 공정에 나오는 날짜 전부 (앞에서부터)
    _days = set()
    for _item in merged:
        for _step in (_item.get("steps") or []):
            for _d in ((_step or {}).get("days") or {}):
                _days.add(_d)
    board = {
        "title": _bloom_pick(parsed.get("title"), old.get("title")) or "",
        "sheet": _bloom_pick(parsed.get("sheet"), old.get("sheet")) or "",
        "report_date": _bloom_pick(parsed.get("report_date"), old.get("report_date")) or "",
        "prior_label": _bloom_pick(parsed.get("prior_label"), old.get("prior_label")) or "",
        # 메모는 '오늘 자 알림'이라 누적하지 않고 새 파일 것으로 바꾼다
        "notes": parsed.get("notes") or [],
        # 금액은 그 달 누계 한 장이다. 새 파일에 있으면 바꾸고, 없으면 두던 것
        "money": parsed.get("money") or old.get("money"),
        "items": merged,
        "dates": sorted(_days),
    }
    return board, diff

# ============================================================
#  블룸 요약 · 품목 · 챗봇 답
# ============================================================
def _bloom_with_month_totals(board: dict) -> dict:
    items = []
    for it in (board.get("items") or []):
        if not isinstance(it, dict):
            continue
        steps = []
        for st in (it.get("steps") or []):
            if not isinstance(st, dict):
                continue
            if st.get("month_plan") is None or st.get("month_actual") is None:
                st = dict(st)
                days = st.get("days") or {}
                for fld, key, prior in (("month_plan", "plan", "prior_plan"),
                                        ("month_actual", "actual", "prior_actual")):
                    if st.get(fld) is not None:
                        continue
                    tot, found = 0, False
                    base = st.get(prior)          # 날짜 칸 앞의 '이전 데이터'
                    if base is not None:
                        try:
                            tot, found = int(base), True
                        except (TypeError, ValueError):
                            pass
                    for v in days.values():
                        x = (v or {}).get(key)
                        if x is None:
                            continue
                        try:
                            tot += int(x)
                        except (TypeError, ValueError):
                            continue
                        found = True
                    if found:
                        st[fld] = tot
            steps.append(st)
        it = dict(it)
        it["steps"] = steps
        items.append(it)
    out = dict(board)
    out["items"] = items
    return out


# 그 날 공정별 계획/실적 합계 + 직전에 실적이 있던 날.
def _bloom_summary(board: dict, date: str = ""):
    dates = board.get("dates") or []
    if not dates:
        return {}
    day = date or board.get("report_date") or dates[-1]
    if day not in dates:
        later = [d for d in dates if d >= day]
        day = later[0] if later else dates[-1]

    def at(d):
        groups, has_actual, has_plan = {}, False, False
        for it in (board.get("items") or []):
            for st in (it.get("steps") or []):
                cell = ((st or {}).get("days") or {}).get(d)
                if not cell:
                    continue
                g = groups.setdefault(st.get("group") or st.get("step") or "",
                                      {"plan": 0, "actual": 0, "has_actual": False})
                p, a = cell.get("plan"), cell.get("actual")
                if p is not None:
                    g["plan"] += int(p)
                    if int(p):
                        has_plan = True
                if a is not None:
                    g["actual"] += int(a)
                    g["has_actual"] = True
                    has_actual = True
        return {
            "date": d,
            "groups": groups,
            "plan": sum(g["plan"] for g in groups.values()),
            "actual": sum(g["actual"] for g in groups.values()),
            "has_actual": has_actual,
            "pending": has_plan and not has_actual,
        }

    today = at(day)
    prev = None
    for d in reversed([x for x in dates if x < day]):
        cand = at(d)
        if cand["has_actual"]:
            prev = cand
            break
    return {"date": day, "today": today, "prev": prev,
            "prev_date": (prev or {}).get("date", "")}


# 블룸은 품목 하나가 프로젝트 하나다 (YFP · Corva KPE · SL7 …).
_BLOOM_STORE = "bloom_main"


# 그 프로젝트가 맡은 품목 이름. 품목 프로젝트가 아니면 빈 문자열.
def _bloom_item_of(project_key: str) -> str:
    try:
        p = _cl.get_project(project_key) or {}
    except Exception:
        return ""
    return str(p.get("bloom_item") or "").strip()


# 품목 하나만 남긴 보드. 날짜·요약도 그 품목 기준으로 다시 낸다
def _bloom_slice(board: dict, item: str) -> dict:
    import bloom_daily_import as _bd
    want = _norm_label(_bd.clean_item(item))
    items = [i for i in (board.get("items") or [])
             if isinstance(i, dict) and _norm_label(_bd.clean_item(i.get("item"))) == want]
    out = dict(board)
    out["items"] = items
    # 품목들의 공정에 나오는 날짜 전부 (앞에서부터)
    _days = set()
    for _item in items:
        for _step in (_item.get("steps") or []):
            for _d in ((_step or {}).get("days") or {}):
                _days.add(_d)
    out["dates"] = sorted(_days)
    # 금액 시트는 품목 이름이 다르다 ('CORVA EFM KPE' ↔ 'Corva KPE') —
    # 억지로 맞추면 틀린 숫자가 붙는다. 품목 화면에서는 빼고 전체 화면에만 둔다.
    out.pop("money", None)
    return out

# 블룸 프로젝트 하나가 볼 보드 (품목 프로젝트면 자기 몫만).
def _bloom_board_for(project_key: str):
    _key = _model_key_alias(project_key)
    _item = _bloom_item_of(_key)
    _store = _BLOOM_STORE if _item else _key
    proj = (_load_models().get("projects") or {}).get(_store) or {}
    board = proj.get("daily_board")
    if not isinstance(board, dict) or not board.get("items"):
        return None, _item
    if _item:
        board = _bloom_slice(board, _item)
    return board, _item


# 그 날 품목별 계획/실적 합계.
def _bloom_item_totals(board: dict, day: str):
    out = []
    for it in (board.get("items") or []):
        plan = act = 0
        has_actual = False
        for st in (it.get("steps") or []):
            cell = ((st or {}).get("days") or {}).get(day)
            if not cell:
                continue
            if cell.get("plan") is not None:
                plan += int(cell["plan"])
            if cell.get("actual") is not None:
                act += int(cell["actual"])
                has_actual = True
        if plan or act:
            out.append({"item": it.get("item") or "", "plan": plan,
                        "actual": act, "has_actual": has_actual})
    return out


# 블룸 질문 즉답. 모델이 없는 프로젝트라 일 보고 보드를 직접 읽는다
def _bloom_chat_answer(project_key: str, text: str) -> str:
    board, item = _bloom_board_for(project_key)
    if not board:
        return ""
    dates = board.get("dates") or []
    if not dates:
        return ""
    import datetime as _dtb
    today = _dtb.date.today().strftime("%Y-%m-%d")
    day = today if today in dates else dates[-1]
    if any(k in (text or "") for k in ("어제", "전일", "지난날")):
        earlier = [d for d in dates if d < day]
        if earlier:
            day = earlier[-1]

    summ = _bloom_summary(board, day) or {}
    cur = summ.get("today") or {}
    label = item or "블룸 전체"

    def _md(d):
        try:
            return f"{int(d[5:7])}/{int(d[8:10])}"
        except Exception:
            return d

    lines = []
    plan, act = int(cur.get("plan") or 0), int(cur.get("actual") or 0)
    if cur.get("pending"):
        prev = summ.get("prev") or {}
        head = f"{_md(day)} {label} 실적은 아직 입력 전입니다 (계획 {plan}대)."
        pr = int((prev or {}).get("plan") or 0)
        pa = int((prev or {}).get("actual") or 0)
        if prev and (pr or pa):
            rate = f" ({round(pa / pr * 100)}%)" if pr else ""
            head += f" 직전 {_md(prev.get('date',''))} 실적 {pa}/{pr}대{rate}."
        lines.append(head)
    else:
        rate = f" ({round(act / plan * 100)}%)" if plan else ""
        lines.append(f"{_md(day)} {label} 실적 {act}/{plan}대{rate}.")

    # 전체 보드면 품목별 한 줄, 품목 보드면 공정별 한 줄
    if not item:
        rows = _bloom_item_totals(board, day)
        rows = [r for r in rows if r["plan"] or r["actual"]]
        rows.sort(key=lambda r: -(r["plan"] or 0))
        if rows:
            lines.append(" / ".join(
                (f"{r['item']} {r['plan']}" if cur.get("pending")
                 else f"{r['item']} {r['actual']}/{r['plan']}") for r in rows[:7]))
    else:
        groups = (cur.get("groups") or {})
        parts = []
        for g, v in groups.items():
            gp, ga = int(v.get("plan") or 0), int(v.get("actual") or 0)
            if not (gp or ga):
                continue
            parts.append(f"{g} {gp}" if cur.get("pending") else f"{g} {ga}/{gp}")
        if parts:
            lines.append(" / ".join(parts[:6]))

    # 계획 대비 실적이 모자란 곳 (막혀 있는 곳)
    behind = []
    if not cur.get("pending"):
        if not item:
            for r in _bloom_item_totals(board, day):
                if r["plan"] and r["actual"] < r["plan"]:
                    behind.append(f"{r['item']} {r['plan'] - r['actual']}대")
        else:
            for g, v in (cur.get("groups") or {}).items():
                gp, ga = int(v.get("plan") or 0), int(v.get("actual") or 0)
                if gp and ga < gp:
                    behind.append(f"{g} {gp - ga}대")
    if behind:
        lines.append("미달: " + ", ".join(behind[:5]))

    notes = [str(n.get("text") or "").strip()
             for n in (board.get("notes") or []) if isinstance(n, dict)]
    notes = [n for n in notes if n]
    if item:
        # 메모는 'KPE- ...' 처럼 품목 이름으로 시작한다. 내 품목 것만 남긴다.
        toks = [t.lower() for t in str(item).split() if len(t) >= 2]
        notes = [n for n in notes if any(t in n.lower() for t in toks)]
    notes = notes[:2]
    if notes:
        lines.append("특이사항: " + " / ".join(notes))

    return "\n".join(lines)

# ============================================================
#  일 보고 보드 주소
# ============================================================
# 블룸 일 보드. Admin 도 앱도 이걸 읽는다 ← admin v2 renderDailyBoard() · 앱 bloom_service.dart board()
@app.get("/projects/{project_key}/daily-board")
def get_daily_board(project_key: str, date: str = "", month: str = ""):
    _key = _model_key_alias(project_key)
    _item = _bloom_item_of(_key)
    # -----------------------------------------------------------
    # 일 보고는 블룸만의 것이 아니다
    # -----------------------------------------------------------
    # 전에는 저장 자리를 bloom_main 으로 못박아 둬서, ESS 프로젝트
    # (SDI · 플루언스 · EPC POWER)에서는 일 보고 보드가 아예 안 떴다.
    # 어느 자리에 담기는지는 _DAILY_STORE 가 안다 — 거기서 받는다.
    _div = _daily_board_division(_key)
    _store = (_daily_store_key(_div) or _key) if (_item or _div) else _key
    proj = (_load_models().get("projects") or {}).get(_store) or {}
    allm = _bloom_store_months(proj)
    months = sorted(allm)
    # 고른 달이 있으면 그 달, 없으면 가장 최근 달, 그것도 없으면 빈 글자
    if month in allm:
        pick = month
    elif months:
        pick = months[-1]
    else:
        pick = ""
    board = allm.get(pick)
    if isinstance(board, dict) and _item:
        board = _bloom_slice(board, _item)
    elif isinstance(board, dict) and _div and _store != _key:
        # 품목 이름 안에 프로젝트 이름이 든 줄만. 없으면 빈 보드.
        board = _daily_slice_by_project(board, _key)
    if not isinstance(board, dict) or not board.get("items"):
        # 자료가 아예 없는 것과, 자료는 있는데 이 프로젝트 이름이 거기
        # 없는 것은 다르다. 화면이 다른 말을 할 수 있게 갈라 준다.
        _had = bool(allm.get(pick, {}).get("items")) if isinstance(allm.get(pick), dict) else False
        return {"project_key": _key, "has_board": False, "items": [], "dates": [],
                "months": months, "month": pick,
                "no_match": bool(_had and (_item or _div))}
    import datetime as _dt
    board = _bloom_with_month_totals(board)
    out = dict(board)
    out["project_key"] = _key
    out["item"] = _item
    out["has_board"] = True
    out["months"] = months
    out["month"] = pick
    out["today"] = _dt.date.today().strftime("%Y-%m-%d")
    out["summary"] = _bloom_summary(board, date)
    # -----------------------------------------------------------
    # 지난 주는 주 단위로 접고, 이번 주만 날짜로 편다
    # -----------------------------------------------------------
    # 한 달치를 날짜 그대로 그리면 열이 서른 개가 넘어 아무도 못 읽는다
    try:
        import daily_view as _dv
        cols = _dv.build_columns(out.get("dates") or [], out.get("today"), pick)
        out["columns"] = cols
        for _it in (out.get("items") or []):
            for _st in (_it.get("steps") or []):
                _st["cells"] = _dv.fold_row(_st.get("days") or {}, cols)
    except Exception as e:
        print("[daily-board] 열 접기 실패: %s" % e)
        out["columns"] = []
    return out


# 지난 달은 몇 개까지 둘지. 보드 한 달이 20KB 쯤이고 models.json 은
# 요청마다 통째로 다시 읽는다 — 무한정 쌓으면 그 값을 치르게 된다.
_BLOOM_KEEP_MONTHS = 5

# ============================================================
#  블룸 달별 저장
# ============================================================
def _bloom_month_of(board: dict) -> str:
    ds = (board or {}).get("dates") or []
    return str(ds[0])[:7] if ds else ""


# {'2026-09': 보드, '2026-10': 보드} — 지난 달 + 이번 달.
def _bloom_store_months(proj: dict) -> dict:
    out = {}
    prev = proj.get("daily_board_months")
    if isinstance(prev, dict):
        for m, b in prev.items():
            if isinstance(b, dict) and b.get("items"):
                out[str(m)] = b
    cur = proj.get("daily_board")
    if isinstance(cur, dict) and cur.get("items"):
        m = _bloom_month_of(cur)
        if m:
            out[m] = cur
    return out


# 파일에 든 달 전부. {'2026-09': parsed, ...}
def _bloom_parse_months(raw: bytes) -> dict:
    import io as _io

    import openpyxl as _xl

    import bloom_daily_import as _bd
    try:
        wb = _xl.load_workbook(_io.BytesIO(raw), data_only=True, keep_links=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"엑셀을 열 수 없습니다: {e}")

    out = {}
    for ws, _last in _bd.find_sheets(wb):
        try:
            p = _bd.parse_daily(wb, sheet_name=ws.title)
        except Exception as _e:
            print(f"[bloom] 시트 읽기 실패(넘어감) {ws.title}: {_e}")
            continue
        if not p.get("items"):
            continue
        mon = _bloom_month_of(p)
        if not mon:
            continue
        # 같은 달 시트가 둘이면 날짜가 더 많은 쪽
        if mon in out and \
                len(out[mon].get("dates") or []) >= len(p.get("dates") or []):
            continue
        out[mon] = p
    if not out:
        raise HTTPException(
            status_code=400,
            detail="'대표님 일 보고 자료' 모양의 시트를 찾지 못했습니다. "
                   "품목·공정 열과 날짜별 계획/실적 칸이 있는 파일인지 확인해 주세요.")
    try:
        out[max(out)]["money"] = _bd.parse_money(wb)
    except Exception as _e:
        print(f"[bloom] 금액 실적 시트 읽기 실패(무시): {_e}")
        out[max(out)]["money"] = None
    return out


# 달별로 합친다 → ({'2026-09': 보드}, {'2026-09': diff}, 최신달).
def _bloom_apply_months(proj: dict, months_in: dict):
    store = _bloom_store_months(proj)
    diffs = {}
    for mon in sorted(months_in):
        b, d = _bloom_merge(store.get(mon) or {}, months_in[mon])
        store[mon] = b
        diffs[mon] = d
    keep = sorted(store)[-(_BLOOM_KEEP_MONTHS + 1):]
    store = {m: store[m] for m in keep}
    return store, diffs, (keep[-1] if keep else "")


# 화면에 '어느 달이 얼마나 바뀌는지' 한 줄씩.
def _bloom_months_brief(store: dict, diffs: dict):
    out = []
    for mon in sorted(store):
        b, d = store[mon], (diffs.get(mon) or {})
        out.append({
            "month": mon,
            "items": len(b.get("items") or []),
            "dates": len(b.get("dates") or []),
            "touched": mon in diffs,
            "days_added": d.get("days_added", 0),
            "day_changes": len(d.get("day_changes") or []),
        })
    return out


# 블룸 일 보고 엑셀을 읽어 보드 자료로.
def _bloom_parse_upload(raw: bytes):
    # openpyxl / BytesIO 는 main.py 최상단에 없다. 쓰는 함수마다 직접 가져온다.
    import io as _io
    import openpyxl as _xl
    import bloom_daily_import as _bd
    try:
        wb = _xl.load_workbook(_io.BytesIO(raw), data_only=True, keep_links=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"엑셀을 열 수 없습니다: {e}")
    parsed = _bd.parse_daily(wb)
    # 같은 파일의 '금액 실적' 시트 — 없으면 None (일 보고만 올린 파일)
    try:
        parsed["money"] = _bd.parse_money(wb)
    except Exception as _e:
        print(f"[bloom] 금액 실적 시트 읽기 실패(무시): {_e}")
        parsed["money"] = None
    if not parsed.get("items"):
        raise HTTPException(
            status_code=400,
            detail="'대표님 일 보고 자료' 모양의 시트를 찾지 못했습니다. "
                   "품목·공정 열과 날짜별 계획/실적 칸이 있는 파일인지 확인해 주세요.")
    return parsed


# 두 사업부는 보고 자료가 **날마다** 들어온다

#: 사업부 → 일 보고 자료를 담아 두는 자리(가짜 프로젝트 키)
_DAILY_STORE = {
    "bloom": _BLOOM_STORE,      # 'bloom_main' — 예전부터 쓰던 자리
    "ess": "ess_main",
}

# ============================================================
#  일 보고 올리기 (사업부 · 블룸)
# ============================================================
def _daily_store_key(division_id: str) -> str:
    return _DAILY_STORE.get(str(division_id or "").strip().lower(), "")


# 담을 자리가 없으면 여기서 끊는다
def _daily_need_store(division_id: str) -> str:
    key = _daily_store_key(division_id)
    if not key:
        raise HTTPException(
            status_code=400,
            detail=("%s 사업부는 일 보고 자료를 받지 않습니다. "
                    "받으려면 _DAILY_STORE 에 자리를 만들어야 합니다." % division_id))
    return key


# 올린 일 보고 자료가 무엇을 바꾸는지 먼저 보여준다 ← admin v2 _dailySend()
@app.post("/admin/divisions/{division_id}/daily/preview")
async def admin_division_daily_preview(
    division_id: str,
    file: UploadFile = File(...),
    _admin: int = Depends(get_admin_session),
):
    store_key = _daily_need_store(division_id)
    raw = await _keep_upload(file, "/admin/divisions/{division_id}/daily/preview",
                             division_id)
    months_in = _bloom_parse_months(raw)

    proj = (_load_models().get("projects") or {}).get(store_key) or {}
    store, diffs, latest = _bloom_apply_months(proj, months_in)
    return {
        "ok": True,
        "division_id": division_id,
        "store_key": store_key,
        "file_name": file.filename or "",
        "months": _bloom_months_brief(store, diffs),
        "latest_month": latest,
    }


# 미리보기에서 확인한 내용을 저장한다 ← admin v2 _dailySend()
@app.post("/admin/divisions/{division_id}/daily/apply")
async def admin_division_daily_apply(
    division_id: str,
    file: UploadFile = File(...),
    _admin: int = Depends(get_admin_session),
):
    store_key = _daily_need_store(division_id)
    raw = await _keep_upload(file, "/admin/divisions/{division_id}/daily/apply",
                             division_id)
    months_in = _bloom_parse_months(raw)

    data = _load_models()
    proj = data.setdefault("projects", {}).setdefault(store_key, {"models": []})
    store, diffs, latest = _bloom_apply_months(proj, months_in)

    # 이번 달은 daily_board 에 그대로 둔다 — 챗봇·매출 집계가 그 자리를
    # 읽고 있어서 옮기면 같이 고쳐야 한다. 지난 달만 따로 쌓는다.
    if latest:
        proj["daily_board"] = store.get(latest) or {}
    past = {}
    for mon, board in store.items():
        if mon != latest:
            past[mon] = board
    proj["daily_board_months"] = past

    _save_models(data)
    print("[일 보고] %s '%s': %d개 달 저장 (최신 %s)"
          % (division_id, file.filename or "", len(store), latest))
    return {
        "ok": True,
        "division_id": division_id,
        "store_key": store_key,
        "file_name": file.filename or "",
        "months": _bloom_months_brief(store, diffs),
        "latest_month": latest,
    }


# 일 보고 자료를 **접어서** 내보낸다 ← 앱 daily_board_card.dart _pickMonth()
@app.get("/divisions/{division_id}/daily-view")
def get_division_daily_view(division_id: str, month: str = "", today: str = ""):
    import daily_view as _dv

    store_key = _daily_store_key(division_id)
    if not store_key:
        return {"division_id": division_id, "columns": [], "rows": [],
                "total": [], "months": []}

    proj = (_load_models().get("projects") or {}).get(store_key) or {}
    # -----------------------------------------------------------
    # 1. 어느 달을 볼 것인가
    # -----------------------------------------------------------
    boards = _bloom_store_months(proj)
    if not boards:
        return {"division_id": division_id, "columns": [], "rows": [],
                "total": [], "months": []}
    mon = str(month or "").strip()
    if mon not in boards:
        # 기본은 '이번 달' 이다
        import datetime as _d4
        _now = (today or "")[:7] or _d4.date.today().strftime("%Y-%m")
        mon = _now if _now in boards else sorted(boards)[-1]
    # -----------------------------------------------------------
    # 2. 접는다 (어느 달을 보는지도 알려 준다)
    # -----------------------------------------------------------
    view = _dv.build(boards[mon], today or None, mon)
    view["division_id"] = division_id
    view["month"] = mon
    view["months"] = sorted(boards)
    return view


# 저장하지 않고 무엇이 바뀌는지만 보여준다 ← admin v2 fl.onchange()
@app.post("/admin/projects/{project_key}/bloom-daily/preview")
async def admin_bloom_daily_preview(project_key: str, file: UploadFile = File(...),
                                    _admin: int = Depends(get_admin_session)):
    # 엑셀은 품목 전체가 한 장이다. 어느 품목 화면에서 올리든 원본은 한 곳에.
    _key = _BLOOM_STORE if _bloom_item_of(_model_key_alias(project_key)) \
        else _model_key_alias(project_key)
    months_in = _bloom_parse_months(await _keep_upload(file, "/admin/projects/{project_key}/bloom-daily/preview", project_key))
    proj = (_load_models().get("projects") or {}).get(_key) or {}
    store, diffs, newest = _bloom_apply_months(proj, months_in)
    board = store.get(newest) or {}
    parsed = months_in.get(newest) or {}
    return {"ok": True, "project_key": _key, "file_name": file.filename,
            "sheet": parsed.get("sheet"), "title": parsed.get("title"),
            "report_date": parsed.get("report_date"),
            "items": len(board.get("items") or []),
            "dates": board.get("dates") or [],
            "notes": parsed.get("notes") or [],
            "month": newest,
            "months": _bloom_months_brief(store, diffs),
            "diff": diffs.get(newest) or {}}


# 합쳐서 저장한다 ← admin v2 _bdConfirm()
@app.post("/admin/projects/{project_key}/bloom-daily")
async def admin_bloom_daily_apply(project_key: str, file: UploadFile = File(...),
                                  _admin: int = Depends(get_admin_session)):
    _key = _BLOOM_STORE if _bloom_item_of(_model_key_alias(project_key)) \
        else _model_key_alias(project_key)
    months_in = _bloom_parse_months(await _keep_upload(file, "/admin/projects/{project_key}/bloom-daily", project_key))
    data = _load_models()
    proj = data.setdefault("projects", {}).setdefault(_key, {"models": []})
    store, diffs, newest = _bloom_apply_months(proj, months_in)
    board = store.get(newest) or {}
    board["updated_at"] = datetime.now().isoformat(timespec="seconds")
    board["file_name"] = file.filename or ""
    # 이번 달은 지금까지처럼 daily_board 에 둔다 — 챗봇·매출·RAG 가 거기를
    # 본다. 지난 달만 옆에 쌓는다.
    proj["daily_board"] = board
    older = {m: b for m, b in store.items() if m != newest}
    if older:
        proj["daily_board_months"] = older
    else:
        proj.pop("daily_board_months", None)
    _save_models(data)
    diff = diffs.get(newest) or {"days_added": 0, "day_changes": []}
    print(f"[bloom] 일 보드 저장 {_key}: {file.filename} · 달 {sorted(store)} · "
          f"품목 {len(board.get('items') or [])} · 날짜 {len(board.get('dates') or [])} · "
          f"새 칸 {diff.get('days_added', 0)} · 바뀐 칸 {len(diff.get('day_changes') or [])}")
    return {"ok": True, "project_key": _key, "file_name": board["file_name"],
            "report_date": board.get("report_date"),
            "items": len(board.get("items") or []),
            "dates": board.get("dates") or [],
            "month": newest,
            "months": _bloom_months_brief(store, diffs),
            "diff": diff}

# 주차 미달과 그 사유
_WEEK_REASON_KINDS = ("문제", "참고")

# ============================================================
#  주차 미달과 그 사유
# ============================================================
def _week_reasons_of(proj: dict, month: str) -> dict:
    store = proj.get("week_reasons")
    if not isinstance(store, dict):
        return {}
    got = store.get(str(month))
    if not isinstance(got, dict):
        return {}
    out = {}
    for w, v in got.items():
        if not isinstance(v, dict):
            continue
        kind = str(v.get("kind") or "").strip()
        out[str(w)] = {
            "kind": kind if kind in _WEEK_REASON_KINDS else "문제",
            "text": str(v.get("text") or "").strip(),
            "at": str(v.get("at") or ""),
        }
    return out


# 마감된 주차 = 그 ISO 주의 일요일이 오늘보다 앞선 주.
def _closed_week_labels(month: str, weeks: list, today=None) -> list:
    import datetime as _dtc
    today = today or _dtc.date.today()
    out = []
    for w in (weeks or []):
        end = _week_end_date(month, w)
        if end and end < today:
            out.append(str(w))
    return out


# 마감된 주차에서 합계가 계획에 못 미치면 표시를 달고 목록으로 돌려준다
def _mark_board_shortfalls(rows: list, total: dict, weeks: list, month: str,
                           reasons: dict, today=None) -> tuple:
    closed = set(_closed_week_labels(month, weeks, today))

    # 행은 '끝난 주인지' 만 달아 준다. 빨간 칸은 합계에만.
    for r in (rows or []):
        if not isinstance(r, dict):
            continue
        for w in (weeks or []):
            cell = (r.get("weeks") or {}).get(w)
            if isinstance(cell, dict):
                cell["closed"] = str(w) in closed
                cell.pop("short", None)

    shorts = []
    if isinstance(total, dict):
        for w in (weeks or []):
            cell = (total.get("weeks") or {}).get(w)
            if not isinstance(cell, dict):
                continue
            done = str(w) in closed
            cell["closed"] = done
            try:
                plan = int(cell.get("plan") or 0)
                actual = int(cell.get("actual") or 0)
            except (TypeError, ValueError):
                continue
            if not done or plan <= 0 or actual >= plan:
                cell.pop("short", None)
                continue
            cell["short"] = plan - actual
            rs = reasons.get(str(w)) or {}
            shorts.append({
                "week": str(w), "row": "합계",
                "plan": plan, "actual": actual, "short": plan - actual,
                "rate": round(actual * 100 / plan),
                "kind": rs.get("kind") or "",       # '' = 사유 미입력
                "reason": rs.get("text") or "",
            })
    shorts.sort(key=lambda e: e["week"])
    return sorted(closed), shorts


# 여러 줄에서 같은 칸을 더한다
def _sum_of(items, field) -> int:
    total = 0
    for it in items:
        total += (it.get(field) or 0)
    return total


# 주차 묶음에서 이번 달 주차만 남긴다
def _only_these_weeks(week_map, weeks) -> dict:
    out = {}
    for w in weeks:
        out[w] = week_map[w]
    return out


# ============================================================
#  블룸 프로젝트 한 개의 주차 현황 보드
# ============================================================
# 공정 한 줄의 날짜 자료를 주차 칸으로 묶는다 → {'W41': {plan, actual}}
def _bloom_step_weeks(step: dict, weeks: list, month: str) -> dict:
    import datetime as _dt
    out = {w: {"plan": 0, "actual": 0} for w in weeks}
    for ds, cell in ((step or {}).get("days") or {}).items():
        if not isinstance(cell, dict):
            continue
        try:
            d = _dt.date.fromisoformat(str(ds)[:10])
        except Exception:
            continue
        w = "W%02d" % d.isocalendar()[1]
        if w not in out:
            continue
        for fld in ("plan", "actual"):
            v = cell.get(fld)
            if v is not None:
                try:
                    out[w][fld] += int(v)
                except Exception:
                    pass
    return out


# 두 사업부는 자료가 날마다 들어오고, 프로젝트 안에 모델(품번)이 없거나 있어도 주차 계획을 따로 안 적는다
_DAILY_BOARD_ROWS = {
    "bloom": ("NCT", "조립", "출하"),
    "ess": ("제관/용접", "조립", "출하"),
}

# '이전 데이터' 칸의 열 이름. 주차 이름('W41')이 아니라서 마감 주차로도,
# 미달 주차로도 세지 않는다 — 날짜가 없으니 언제 끝난 주인지 알 수 없다.
_DAILY_PRIOR_COL = "이전"

# ============================================================
#  일 보고로 그리는 프로젝트 보드 — 블룸 · ESS
# ============================================================
def _daily_slice_by_project(board: dict, project_key: str):
    try:
        p = _cl.get_project(project_key) or {}
    except Exception:
        return None
    names = [p.get("label"), p.get("badge_label"), project_key]
    names.extend(p.get("aliases") or [])
    keys = [_norm_label(str(n)) for n in names if n]
    keys = [k for k in keys if len(k) >= 2]
    if not keys:
        return None
    # -----------------------------------------------------------
    # 고객사 칸이 있으면 그걸 먼저 본다
    # -----------------------------------------------------------
    # ESS 일 보고에는 품목 왼쪽에 **고객사** 열이 따로 있다 (SDI · 플루언스 · EPC POWER).
    picked = []
    for it in (board.get("items") or []):
        own = _norm_label(str((it or {}).get("owner") or ""))
        nm = _norm_label(str((it or {}).get("item") or ""))
        hay = own or nm
        if any(k in hay for k in keys) or (own and any(k in nm for k in keys)):
            picked.append(it)
    out = dict(board)
    out["items"] = picked          # 한 줄도 못 골랐으면 빈 보드다
    return out


# 그 프로젝트가 일 보고로 보드를 그리는 사업부인가.
def _daily_board_division(project_key: str) -> str:
    try:
        p = _cl.get_project(project_key) or {}
    except Exception:
        return ""
    d = str(p.get("division_id") or "").strip().lower()
    return d if d in _DAILY_BOARD_ROWS else ""


# 그 공정이 어느 줄인가 ('NCT(박닌)' → 'NCT').
def _daily_step_group(step: dict, rows: tuple) -> str:
    g = str((step or {}).get("group") or "").strip()
    if g:
        return g
    # group 이 비어 있으면 공정 이름에서 찾는다 ('조립(박장)' → '조립')
    name = str((step or {}).get("step") or "")
    for want in rows:
        if want in name:
            return want
    return name.strip()


# '구분' 열에 세울 공정 — 일 보고의 '공정구분' 칸에 적힌 그대로.
def _daily_report_rows(board, fallback: tuple) -> tuple:
    order = []
    for it in ((board or {}).get("items") or []):
        for st in ((it or {}).get("steps") or []):
            if not isinstance(st, dict):
                continue
            g = _daily_step_group(st, fallback)
            if g and g not in order:
                order.append(g)
    return tuple(order) or tuple(fallback)


# 그 프로젝트가 맡은 품목 자료만 골라낸다
def _daily_board_items(division_id: str, project_key: str, board: dict) -> list:
    items = [it for it in (board.get("items") or []) if isinstance(it, dict)]
    # -----------------------------------------------------------
    # 블룸 — 프로젝트 하나가 품목 하나
    # -----------------------------------------------------------
    item = _bloom_item_of(project_key)
    if item:
        import bloom_daily_import as _bd
        want = _norm_label(_bd.clean_item(item))
        return [it for it in items
                if _norm_label(_bd.clean_item(it.get("item"))) == want]
    # -----------------------------------------------------------
    # ESS — 고객사 칸으로 고른다
    # -----------------------------------------------------------
    idx = _df_owner_index(division_id)
    return [it for it in items
            if _df_find_project(it.get("owner") or "", idx) == project_key]


# 품목 단위로 쌓여 있는 재고 → {'wait_ship':.., 'wait_part':..}
def _daily_stock_of(items: list) -> dict:
    out = {}
    for fld in ("wait_ship", "wait_part"):
        vals = []
        for it in items:
            v = (it or {}).get(fld)
            if v is not None:
                try:
                    vals.append(int(v))
                except Exception:
                    pass
        out[fld] = sum(vals) if vals else None
    return out


# 품목들을 공정별로 더해 보드 행을 만든다
def _daily_board_rows(items: list, rows_want: tuple, weeks: list,
                      month: str, prev_by_group: dict) -> list:
    # -----------------------------------------------------------
    # 1. 공정별로 품목 자료를 모은다
    # -----------------------------------------------------------
    bucket = {}          # 줄이름 → [(공정 이름, 공정 자료), ...]
    for it in items:
        for st in (it.get("steps") or []):
            if isinstance(st, dict):
                g = _daily_step_group(st, rows_want)
                bucket.setdefault(g, []).append(st)
    # -----------------------------------------------------------
    # 2. 늘 세울 줄 + 못 보던 공정은 뒤에 붙인다
    # -----------------------------------------------------------
    #    조용히 빠뜨리면 그 숫자가 어디로 갔는지 아무도 못 찾는다.
    order = list(rows_want) + [g for g in bucket if g not in rows_want]

    out = []
    for g in order:
        steps = bucket.get(g) or []
        if not steps:
            # 자료에 없는 공정 — 줄은 세우되 칸은 비운다 (0 아님)
            out.append({
                "group": g, "label": g,
                "po_qty": None, "remaining": None, "next_month_plan": None,
                "actual_total": None, "prev_month_actual": None,
                "month_plan": None, "month_actual": None,
                "wip": None, "wait_ship": None, "wait_part": None,
                "weeks": {w: {"plan": None, "actual": None} for w in weeks},
            })
            continue

        # 줄 이름은 자료에 적힌 그대로 ('NCT(박닌)' — 어디서 하는지가 붙어
        # 있어 쓸모가 있다). 품목마다 다르면 (ESS) 줄 이름만 쓴다.
        names = {str(st.get("step") or "").strip() for st in steps}
        names.discard("")
        label = names.pop() if len(names) == 1 else g

        m_plan = sum(int(st.get("month_plan") or 0) for st in steps)
        m_act = sum(int(st.get("month_actual") or 0) for st in steps)
        wk = {w: {"plan": 0, "actual": 0} for w in weeks}
        for st in steps:
            one = _bloom_step_weeks(st, weeks, month)
            for w in weeks:
                wk[w]["plan"] += one[w]["plan"]
                wk[w]["actual"] += one[w]["actual"]

        # 공정 재고 — 그 공정에 지금 걸려 있는 것. 공정마다 따로 적혀 와서
        # 줄마다 값이 있다. 한 품목도 안 적혀 있으면 빈 칸(0 아님).
        wips = [int(st["wip"]) for st in steps if st.get("wip") is not None]

        # '이전 데이터' 칸 — ESS 보고자료에는 '10월05일 이전 데이터' 처럼 날짜별로 안 적고 한 칸에 몰아 둔 기간이 있다
        for fld, key in (("plan", "prior_plan"), ("actual", "prior_actual")):
            vals = [int(st[key]) for st in steps if st.get(key) is not None]
            if vals and _DAILY_PRIOR_COL in wk:
                wk[_DAILY_PRIOR_COL][fld] = sum(vals)

        out.append({
            "group": g,
            "label": label,
            # 일 보고에 없는 숫자 — 0 이 아니라 아예 비워 둔다
            "po_qty": None,
            "remaining": None,
            "next_month_plan": None,
            "actual_total": m_act,
            "prev_month_actual": prev_by_group.get(g, 0),
            "month_plan": m_plan,
            "month_actual": m_act,
            "wip": sum(wips) if wips else None,
            # 출하대기·구매품대기는 품목 단위라 공정 줄에는 안 붙는다
            "wait_ship": None,
            "wait_part": None,
            "weeks": wk,
        })
    return out


# 지난달 그 프로젝트의 공정별 실적.
def _daily_prev_by_group(division_id: str, project_key: str,
                         rows_want: tuple, prev_month: str) -> dict:
    store = _daily_store_key(division_id)
    if not store:
        return {}
    proj = (_load_models().get("projects") or {}).get(store) or {}
    board = (_bloom_store_months(proj) or {}).get(prev_month)
    if not isinstance(board, dict):
        return {}
    board = _bloom_with_month_totals(board)
    out = {}
    for it in _daily_board_items(division_id, project_key, board):
        for st in (it.get("steps") or []):
            if not isinstance(st, dict):
                continue
            g = _daily_step_group(st, rows_want)
            try:
                out[g] = out.get(g, 0) + int(st.get("month_actual") or 0)
            except Exception:
                pass
    return out


# 일 보고로 그리는 프로젝트 보드.
def _daily_project_board(project_key: str, month: str):
    import datetime as _dt
    _key = _model_key_alias(project_key)
    division = _daily_board_division(_key)
    if not division:
        return None
    rows_want = _DAILY_BOARD_ROWS[division]

    store = _daily_store_key(division)
    proj = (_load_models().get("projects") or {}).get(store) or {}
    allm = _bloom_store_months(proj)

    y, mm = int(month[:4]), int(month[5:7])
    prev = "%d-12" % (y - 1) if mm == 1 else "%d-%02d" % (y, mm - 1)
    nxt = "%d-01" % (y + 1) if mm == 12 else "%d-%02d" % (y, mm + 1)
    # -----------------------------------------------------------
    # 1. 그 프로젝트 몫의 품목 자료를 꺼낸다
    # -----------------------------------------------------------
    board = allm.get(month)
    items = []
    if isinstance(board, dict):
        board = _bloom_with_month_totals(board)
        items = _daily_board_items(division, _key, board)

    # '구분' 줄은 일 보고에 적힌 공정이다. 그 달 자료가 없으면 가장 최근
    # 달 일 보고의 공정을 쓴다 (다음 달 보드가 빈 줄 없이 서게).
    _src = board if isinstance(board, dict) else next(
        (allm[k] for k in sorted(allm, reverse=True)
         if isinstance(allm[k], dict)), None)
    rows_want = _daily_report_rows(_src, rows_want)
    # -----------------------------------------------------------
    # 1-1. 어떤 주차를 열로 세울까
    # -----------------------------------------------------------
    # 보통은 그 달이 가진 주차다 (_get_month_weeks → 10월이면 W41~W44).
    weeks = list(_get_month_weeks(month))
    extra = set()
    for it in items:
        for st in (it.get("steps") or []):
            for ds in ((st or {}).get("days") or {}):
                if str(ds)[:7] != month:
                    continue
                try:
                    import datetime as _d2
                    d = _d2.date.fromisoformat(str(ds)[:10])
                except Exception:
                    continue
                w = "W%02d" % d.isocalendar()[1]
                if w not in weeks:
                    extra.add(w)
    weeks = sorted(set(weeks) | extra)
    # -----------------------------------------------------------
    # 1-2. '이전 데이터' 칸이 있으면 맨 앞에 한 칸
    # -----------------------------------------------------------
    #    ESS 보고자료의 '10월05일 이전 데이터' 같은 칸이다. 날짜가 없어
    #    주차에 못 넣는데, 빼면 주차를 다 더해도 월 합계가 안 맞는다.
    # 공정 중 하나라도 '이전 데이터' 칸(prior_plan · prior_actual)을 들고 있나
    _has_prior = False
    for _it in items:
        for _st in (_it.get("steps") or []):
            if not isinstance(_st, dict):
                continue
            if _st.get("prior_plan") is not None or _st.get("prior_actual") is not None:
                _has_prior = True
                break
        if _has_prior:
            break
    if _has_prior:
        weeks = [_DAILY_PRIOR_COL] + weeks

    # 일 보고 자료가 이 프로젝트와 아예 상관없으면 (ESS 인데 고객사 칸에
    # 한 번도 안 나온 프로젝트) 옛 방식으로 보낸다 — 모델 주차 계획이
    # 적혀 있을 수 있는데 그걸 빈 표로 덮으면 안 된다.
    if not items and not any(
            _daily_board_items(division, _key, _bloom_with_month_totals(b))
            for b in allm.values() if isinstance(b, dict)):
        # 블룸은 모델이 없어서 옛 방식이 빈 표다 — 빈 공정 표를 보낸다
        if not _bloom_item_of(_key):
            return None
    # -----------------------------------------------------------
    # 2. 공정 줄을 만든다 (자료가 없어도 줄은 선다)
    # -----------------------------------------------------------
    prev_by_group = _daily_prev_by_group(division, _key, rows_want, prev)

    # 품목을 묶어서 보여 줄 것인가
    #
    #   블룸 — 프로젝트 하나가 품목 하나다. 품목 이름이 이미 화면 제목에
    #          있으니 한 번 더 쓰면 같은 글자가 두 번 뜬다. 평평한 표.
    #   ESS  — 프로젝트 하나가 품목을 여럿 맡는다 (SDI → SBB 1.5 · SBB 1.7
    #          · SBB 2.0). 다 더해 세 줄로 접으면 어느 품목이 밀렸는지가
    #          안 보인다. 품목마다 묶음(section)을 만들어 그 안에 공정을
    #          세운다.
    use_sections = division != "bloom"

    sections = []
    if use_sections:
        for it in items:
            srows = _daily_board_rows([it], rows_want, weeks, month,
                                      prev_by_group)
            # 출하대기 · 구매품대기는 품목에 붙는 숫자다. 묶음의 첫 줄에만
            # 적는다 — 줄마다 적으면 공정마다 그만큼 있는 것처럼 보이고,
            # 보는 사람이 더해 버린다.
            stock = _daily_stock_of([it])
            if srows:
                srows[0]["wait_ship"] = stock.get("wait_ship")
                srows[0]["wait_part"] = stock.get("wait_part")
            sections.append({
                "name": str(it.get("item") or "").strip() or "(이름 없음)",
                "rows": srows,
            })
        # 섹션마다 나뉜 줄을 한 줄로 이어 붙인다
        rows = []
        for _sec in sections:
            for _row in _sec["rows"]:
                rows.append(_row)
    else:
        rows = _daily_board_rows(items, rows_want, weeks, month, prev_by_group)
    # -----------------------------------------------------------
    # 3. 합계 줄 — 열마다 모든 공정을 더한다
    # -----------------------------------------------------------
    total = {"po_qty": None, "remaining": None, "next_month_plan": None}
    # 출하대기 · 구매품대기는 품목 단위라 더할 공정이 없다. 프로젝트가
    # 맡은 품목을 더해 합계 줄에만 적는다.
    total.update(_daily_stock_of(items))
    for f in ("actual_total", "prev_month_actual", "month_plan", "month_actual",
              "wip"):
        # 빈 줄(None)은 빼고 더한다. 한 줄도 안 적혀 있으면 합계도 빈 칸.
        vals = [r[f] for r in rows if r.get(f) is not None]
        total[f] = sum(vals) if vals else None
    total["weeks"] = {}
    for w in weeks:
        plans = [r["weeks"][w]["plan"] for r in rows
                 if r["weeks"][w]["plan"] is not None]
        acts = [r["weeks"][w]["actual"] for r in rows
                if r["weeks"][w]["actual"] is not None]
        total["weeks"][w] = {
            "plan": sum(plans) if plans else None,
            "actual": sum(acts) if acts else None,
        }

    try:
        cur_week = "W%02d" % _dt.date.today().isocalendar()[1]
    except Exception:
        cur_week = None

    _reasons = _week_reasons_of(proj, month)
    _closed, _shorts = _mark_board_shortfalls(rows, total, weeks, month, _reasons)
    # -----------------------------------------------------------
    # 3-1. 줄이 하나뿐이면 '합계' 줄만 남긴다
    # -----------------------------------------------------------
    #    '출하 10' 바로 밑에 '합계 10' 이 똑같이 한 번 더 찍히면, 읽는
    #    사람은 두 숫자가 다른 것인 줄 알고 한참 들여다본다. 줄이 하나면
    #    그 줄을 합계 자리에 올리고 이름만 공정 이름으로 바꿔 단다.
    total_label = "합계"
    if len(rows) == 1:
        total_label = rows[0]["label"]
        rows = []
    # -----------------------------------------------------------
    # 4. 앱이 그리지 말아야 할 열
    # -----------------------------------------------------------
    # PO수량 · 잔량 · 다음달 계획 · PO증감 은 일 보고 자료에 없는 숫자다
    hide = ["po_qty", "remaining", "next_month_plan", "po_delta"]
    if not (total.get("prev_month_actual") or 0):
        hide.append("prev_month_actual")

    out = {"project_key": _key, "month": month, "weeks": weeks,
            "prev_month": prev, "next_month": nxt,
            "current_week": cur_week, "po_delta": {},
            "closed_weeks": _closed, "shortfalls": _shorts,
            "week_reasons": _reasons,
            "hide_cols": hide, "total_label": total_label,
            # -----------------------------------------------------------
            # 재고 열 (반도체·자동차에는 없는 열이라 여기서만 보낸다)
            # -----------------------------------------------------------
            #    공정재고 — 공정마다 적혀 와서 줄마다 값이 있다
            #    출하대기 · 구매품대기 — 품목 단위라 합계 줄에만 값이 있다
            "stock_cols": [
                {"field": "wip", "label": "공정\n재고"},
                {"field": "wait_ship", "label": "출하\n대기"},
                {"field": "wait_part", "label": "구매품\n대기"},
            ],
            # 합계가 공정을 다 더한 값이라는 걸 화면에 한 줄로 적어 준다.
            # 안 적으면 '72대 나갔다' 로 읽힌다 (실제 출하는 40).
            "note": ("구분은 일 보고의 공정입니다. 합계는 공정을 더한 값이라"
                     " 출하량이 아닙니다 — 나간 수량은 '출하' 줄입니다."
                     " 출하대기·구매품대기는 품목 단위라 품목마다 한 번만"
                     " 적습니다."
                     if len(rows) > 1 else ""),
            "rows": rows, "total": total}

    if use_sections:
        # 품목 묶음 표로 그린다 (앱의 _sectionTable).
        #   layout   묶음 표를 쓰라는 뜻
        #   columns  'week' — 달이 아니라 주차로 열을 세운다
        #   현황 · 비고 열은 일 보고에 없는 칸이라 끈다
        out["layout"] = "sections"
        out["columns"] = "week"
        out["show_status"] = False
        out["show_note"] = False
        out["sections"] = sections
    return out

# ============================================================
#  주차 현황 보드 (프로젝트 · 사업부)
# ============================================================
def _weekly_filtered(project_key: str, proj: dict) -> dict:
    try:
        div = (_cl.get_project(project_key) or {}).get("division_id") or ""
        want = _dcol.weekly_only(div)
    except Exception:
        div, want = "", {}
    if not want:
        return proj
    keep = _weekly_match(proj, want)
    # -----------------------------------------------------------
    # 안 맞으면 어디까지 봐 주나
    # -----------------------------------------------------------
    # 한 프로젝트에 맞는 줄이 없다고 거르기를 포기하면 안 된다 — 아리스타 27개 중 렉이 있는 건 일곱뿐이라, 나머지 스물은 샷시 숫자를 그대로 띄우게 된다
    if not keep and not _weekly_rule_live(div, want):
        return proj
    out = dict(proj)
    out["models"] = keep
    return out


# 그 조건에 맞는 모델만.
def _weekly_match(proj: dict, want: dict) -> list:
    keep = []
    for m in (proj.get("models") or []):
        if not isinstance(m, dict):
            continue
        for field, vals in want.items():
            if str(m.get(field) or "").strip() in vals:
                keep.append(m)
                break
    return keep


# 그 사업부 어딘가에 조건에 맞는 줄이 하나라도 있나.
def _weekly_rule_live(division_id: str, want: dict) -> bool:
    try:
        data = _load_models()
        for p in _cl.get_projects(division_id=division_id, visible_only=False):
            pid = p.get("id")
            if not pid:
                continue
            proj = (data.get("projects") or {}).get(pid) or {}
            if _weekly_match(proj, want):
                return True
    except Exception as e:
        print("[weekly] 조건 확인 실패 %s: %s" % (division_id, e))
    return False


# 엑셀로 올리던 '주차별 계획 원본' 표를 데이터에서 계산해 돌려준다 ← admin v2 renderWeeklyBoard() · 앱 division_board_service.dart 외
@app.get("/projects/{project_key}/weekly-board")
def get_weekly_board(project_key: str, month: str = None):
    import datetime as _dt
    _key = _model_key_alias(project_key)
    proj = (_load_models().get("projects") or {}).get(_key) or {}
    month = (month or "").strip() or _dt.date.today().strftime("%Y-%m")
    # -----------------------------------------------------------
    # 여기서는 거르지 않는다
    # -----------------------------------------------------------
    # 한 번 _weekly_filtered 를 여기에 걸었다가, 아리스타 프로젝트 (Baja-Peninsula-90W 등)의 보드가 통째로 0 이 됐다

    # 블룸·ESS 는 일 보고로 그린다 — '구분' 열이 공정이다.
    # (양산/개발로 그리면 두 줄 다 0 이 뜬다. 그 구분이 자료에 없다.)
    _bl = _daily_project_board(_key, month)
    if _bl is not None:
        return _bl

    # 프로젝트별 행 구성이 정의돼 있으면 그대로 그린다 (챔버 등).
    # 없으면 예전처럼 양산/개발 두 줄 (하바플레이트).
    _spec = _load_board_spec(_key)
    if _spec:
        return _spec_board(_key, proj, _spec, month)

    weeks = _get_month_weeks(month)
    # -----------------------------------------------------------
    # 지난달 · 다음달이 몇 월인지
    # -----------------------------------------------------------
    #    표에 '지난달 실적'과 '다음달 계획' 열이 있어서 앞뒤 달이 필요하다.
    #    1월의 지난달은 작년 12월, 12월의 다음달은 내년 1월이다.
    y = int(month[:4])
    mm = int(month[5:7])
    if mm == 1:
        prev = f"{y - 1}-12"
    else:
        prev = f"{y}-{mm - 1:02d}"
    if mm == 12:
        nxt = f"{y + 1}-01"
    else:
        nxt = f"{y}-{mm + 1:02d}"

    # 그 달 주차별 합계 {'W41': {'plan':.., 'actual':..}, ...}
    def _group_week_totals(group, mon):
        wk = _get_month_weeks(mon)
        if group == "양산":
            return _mass_week_totals(proj, mon, wk)
        return _dev_week_totals(proj, mon, wk)

    # 그 달 실적을 한 숫자로 (주차별 실적을 다 더한다).
    def month_actual(group, mon):
        t = _group_week_totals(group, mon)
        total = 0
        for v in t.values():
            total += v["actual"]
        return total

    # 그 달 계획을 한 숫자로 (주차별 계획을 다 더한다).
    def month_plan(group, mon):
        t = _group_week_totals(group, mon)
        total = 0
        for v in t.values():
            total += v["plan"]
        return total

    rows = []
    for g in ("양산", "개발"):
        # b = 그 구분(양산/개발)에 사람이 직접 적어 둔 값 묶음
        b = _group_bucket(proj, g)
        # wk = 그 구분의 이번 달 주차별 계획·실적
        wk = _group_week_totals(g, month)
        # PO 수량은 그룹 단위로 직접 입력한 값이 정본 (없으면 모델별 합계).
        # 누적 실적은 모델 목록의 '실적 수량' 합계가 정본 (없으면 전 기간 주차 실적).
        base = int(b.get("base_actual") or 0)
        m_po, m_ship = _model_qty_sums(proj, g)
        po = int(b.get("po_qty") or 0) or m_po
        actual_total = (int(b.get("shipped_qty") or 0) or m_ship
                        or (base + _all_actual_sum(proj, g)))
        # -----------------------------------------------------------
        # 다음달 계획
        # -----------------------------------------------------------
        #    다음달 주차에 적힌 계획을 먼저 쓰고, 그게 0이면 사람이
        #    따로 적어 둔 '다음달 계획' 칸을 쓴다.
        nxt_plan = month_plan(g, nxt)
        if not nxt_plan:
            nxt_plan = int(b.get("next_month_plan") or 0)
        # -----------------------------------------------------------
        # 줄 이름
        # -----------------------------------------------------------
        #    개발은 몇 종이 진행 중이고 몇 종이 끝났는지를 이름에 같이 적는다.
        #    표에 열을 더 만들지 않고 한눈에 보이게 하려는 것이다.
        label = g
        if g == "개발":
            on = int(b.get("ongoing_types") or 0)
            done = int(b.get("done_types") or 0)
            if on or done:
                label = f"개발 ({on}종 진행중 / {done}종 완료)"
        rows.append({
            "group": g, "label": label,
            "po_qty": po,
            "base_actual": base,
            "actual_total": actual_total,
            "remaining": po - actual_total,
            "prev_month_actual": month_actual(g, prev),
            "weeks": _only_these_weeks(wk, weeks),
            "month_plan": _sum_of(wk.values(), "plan"),
            "month_actual": _sum_of(wk.values(), "actual"),
            "next_month_plan": nxt_plan,
        })
    # -----------------------------------------------------------
    # 합계 줄 만들기
    # -----------------------------------------------------------
    #    양산 줄과 개발 줄을 칸마다 더한다.
    total = {"label": "합계"}
    for field in ("po_qty", "actual_total", "remaining", "prev_month_actual",
                  "month_plan", "month_actual", "next_month_plan"):
        total[field] = _sum_of(rows, field)

    # 주차 칸은 계획·실적 두 개라 따로 더한다
    total_weeks = {}
    for w in weeks:
        plan_sum = 0
        actual_sum = 0
        for r in rows:
            plan_sum += r["weeks"][w]["plan"]
            actual_sum += r["weeks"][w]["actual"]
        total_weeks[w] = {"plan": plan_sum, "actual": actual_sum}
    total["weeks"] = total_weeks
    # -----------------------------------------------------------
    # PO증감 이력
    # -----------------------------------------------------------
    # PO 수량이 중간에 바뀐 기록이다
    _hist = []
    for g in ("양산", "개발"):
        _hist.extend((_group_bucket(proj, g).get("po_history") or []))
    _seen_log = set()
    for _m in (proj.get("models") or []):
        if not isinstance(_m, dict):
            continue
        for _e in (_m.get("po_log") or []):
            if not isinstance(_e, dict) or not _e.get("date"):
                continue
            # 같은 모델이 두 벌로 들어와 있어도 한 번만 센다
            _k = (_m.get("id"), _e.get("date"), _e.get("from"), _e.get("to"))
            if _k in _seen_log:
                continue
            _seen_log.add(_k)
            _hist.append(_e)
    po_delta = _po_delta_summary(_hist, month, _project_manual_deltas(proj, month))
    # -----------------------------------------------------------
    # 이번 주가 몇 번째 주인가 (화면에서 빨간 테두리를 두를 열)
    # -----------------------------------------------------------
    try:
        cur_week = "W%02d" % _dt.date.today().isocalendar()[1]
    except Exception:
        cur_week = None
    # -----------------------------------------------------------
    # 계획을 못 채운 주와 그 사유
    # -----------------------------------------------------------
    #    _reasons = {'W42': '고객사 라인 점검으로 …'} — 사람이 엑셀에 적는다
    _reasons = _week_reasons_of(proj, month)
    _closed, _shorts = _mark_board_shortfalls(rows, total, weeks, month, _reasons)
    return {"project_key": _key, "month": month, "weeks": weeks,
            "prev_month": prev, "next_month": nxt,
            "current_week": cur_week, "po_delta": po_delta,
            "closed_weeks": _closed, "shortfalls": _shorts,
            "week_reasons": _reasons,
            "rows": rows, "total": total}


# 사업부 화면에 띄울 주차 현황 보드 ← 앱 division_board_service.dart
@app.get("/divisions/{division_id}/weekly-board")
def get_division_weekly_board(division_id: str, month: str = ""):
    import datetime as _dt2
    mon = (month or "").strip() or _dt2.date.today().strftime("%Y-%m")
    # -----------------------------------------------------------
    # 앞뒤 달 (표에 '지난달 실적' · '다음달 계획' 열이 있다)
    # -----------------------------------------------------------
    # 이걸 안 실어 보냈더니 잔량과 W41 사이 열의 머리글이
    # 비어서, 아무 이름도 없는 빈 칸이 하나 서 있었다. 열은 그려지는데
    # 무엇인지 알 길이 없으면 '이게 뭐지' 를 매번 묻게 된다.
    _y, _m = int(mon[:4]), int(mon[5:7])
    prev = "%d-12" % (_y - 1) if _m == 1 else "%d-%02d" % (_y, _m - 1)
    nxt = "%d-01" % (_y + 1) if _m == 12 else "%d-%02d" % (_y, _m + 1)
    want = _dcol.weekly_only(division_id)
    data = _load_models()
    live = _weekly_rule_live(division_id, want) if want else False

    rows = []
    weeks = _get_month_weeks(mon)
    for p in _cl.get_projects(division_id=division_id, visible_only=False):
        pid = p.get("id")
        if not pid:
            continue
        proj = (data.get("projects") or {}).get(pid) or {}
        if want and live and not _weekly_match(proj, want):
            continue                 # 조건에 안 맞는 프로젝트는 줄을 안 세운다
        b = get_weekly_board(pid, mon)
        tot = (b or {}).get("total") or {}
        if not tot:
            continue
        rows.append({
            "group": str(p.get("label") or pid),
            "label": str(p.get("label") or pid),
            "project_key": pid,
            "po_qty": tot.get("po_qty") or 0,
            "base_actual": tot.get("base_actual") or 0,
            "actual_total": tot.get("actual_total") or 0,
            "remaining": tot.get("remaining") or 0,
            "prev_month_actual": tot.get("prev_month_actual") or 0,
            "weeks": tot.get("weeks") or {},
            "month_plan": tot.get("month_plan") or 0,
            "month_actual": tot.get("month_actual") or 0,
            "next_month_plan": tot.get("next_month_plan") or 0,
        })
        weeks = (b or {}).get("weeks") or weeks

    total = {}
    for field in ("po_qty", "base_actual", "actual_total", "remaining",
                  "prev_month_actual", "month_plan", "month_actual",
                  "next_month_plan"):
        total[field] = sum(int(r.get(field) or 0) for r in rows)
    tw = {}
    for w in weeks:
        tw[w] = {
            "plan": sum(int(((r.get("weeks") or {}).get(w) or {}).get("plan") or 0) for r in rows),
            "actual": sum(int(((r.get("weeks") or {}).get(w) or {}).get("actual") or 0) for r in rows),
        }
    total["weeks"] = tw

    try:
        cur_week = "W%02d" % _dt2.date.today().isocalendar()[1]
    except Exception:
        cur_week = None
    return {"division_id": division_id, "month": mon, "weeks": weeks,
            "prev_month": prev, "next_month": nxt,
            "current_week": cur_week, "rows": rows, "total": total,
            "closed_weeks": [], "shortfalls": [], "week_reasons": {},
            "po_delta": None}

# ============================================================
#  PO 증감
# ============================================================
def _month_of_week_key(week_no, ref_month):
    tag = "W%02d" % int(week_no)
    try:
        y, m = int(str(ref_month)[:4]), int(str(ref_month)[5:7])
    except Exception:
        return None
    for off in range(-7, 8):
        mm = m + off
        yy = y + (mm - 1) // 12
        mm = (mm - 1) % 12 + 1
        cand = f"{yy}-{mm:02d}"
        try:
            if tag in _get_month_weeks(cand):
                return cand
        except Exception:
            continue
    return None


# PO증감 입력 칸. 지난 6개월은 월 단위, 이번 달은 주차 단위로 고정한다
def _delta_periods(month):
    y, m = int(str(month)[:4]), int(str(month)[5:7])
    out = []
    for off in range(6, 0, -1):
        mm = m - off
        yy = y + (mm - 1) // 12 if mm > 0 else y - 1
        mm = (mm - 1) % 12 + 1 if mm > 0 else mm + 12
        out.append({"key": f"{yy}-{mm:02d}", "label": f"{mm}월", "kind": "month"})
    for w in _get_month_weeks(month):
        out.append({"key": w, "label": w, "kind": "week"})
    return out


# 직접 입력한 PO증감. 예전에 그룹별로 저장된 값도 합쳐서 한 벌로 돌려준다
def _project_manual_deltas(proj, month=None):
    import re as _re
    rows = proj.get("po_delta_manual")
    if not (isinstance(rows, list) and rows):
        merged = {}
        for g in ("양산", "개발"):
            b = (proj.get("weekly_summary") or {}).get(g) or {}
            for e in (b.get("po_delta_manual") or []):
                if not isinstance(e, dict):
                    continue
                per = str(e.get("period") or "").strip()
                if not per:
                    continue
                try:
                    merged[per] = merged.get(per, 0) + int(e.get("delta") or 0)
                except Exception:
                    pass
        rows = [{"period": k, "delta": v} for k, v in sorted(merged.items())]

    if not month:
        return rows

    # 이번 달이 아닌 주차 입력은 그 달 한 줄로 접는다 (9월이 지나면 W36~W40 → 9월)
    out = {}
    for e in rows:
        if not isinstance(e, dict):
            continue
        per = str(e.get("period") or "").strip()
        try:
            dv = int(e.get("delta") or 0)
        except Exception:
            dv = 0
        if not per:
            continue
        mw = _re.match(r"^[Ww]?(\d{1,2})$", per)
        if mw:
            mon = _month_of_week_key(int(mw.group(1)), month)
            if mon and mon != month:
                out[mon] = out.get(mon, 0) + dv
                continue
            per = "W%02d" % int(mw.group(1))
        out[per] = out.get(per, 0) + dv
    return [{"period": k, "delta": v} for k, v in sorted(out.items())]


# PO 증감 요약.
def _po_delta_summary(history, month, manual=None):
    import datetime as _dt
    # 직접 입력한 표가 있으면 그게 정본이다. 엑셀에서 읽은 이력과 더하면
    # 같은 기간이 두 번 세어져(3월 619 + 1,321 = 1,940) 입력값과 안 맞는다.
    if manual:
        history = []
    by_month, by_week = {}, {}
    for h in history or []:
        if h.get("delta") is not None:
            delta = int(h.get("delta") or 0)
        else:
            delta = int(h.get("to") or 0) - int(h.get("from") or 0)
        if not delta:
            continue
        # -----------------------------------------------------------
        # 양식이 '몇 주차 자료' 인지 적어 보냈으면 그걸 믿는다
        # -----------------------------------------------------------
        # 올린 날짜로 주차를 세면, W43 양식을 다음 주 월요일에 올렸을 때
        # W44 에 숫자가 선다. 그 주엔 아무 일도 안 일어났는데 보는 사람은
        # "이번 주에 PO 가 늘었네" 로 읽는다. 양식이 말하는 주차가 맞다.
        _wk = str(h.get("week") or "").strip().upper()
        if _wk:
            _mon = _wcal.month_of_week(_wk) or ""
            if _mon == month:
                by_week[_wk] = by_week.get(_wk, 0) + delta
            elif _mon:
                by_month[_mon] = by_month.get(_mon, 0) + delta
            continue

        # 주차를 안 적어 보낸 옛 기록은 날짜로 센다
        try:
            d = _dt.date.fromisoformat(str(h.get("date"))[:10])
        except Exception:
            continue
        mk = f"{d.year}-{d.month:02d}"
        if mk == month:
            wk = "W%02d" % d.isocalendar()[1]
            by_week[wk] = by_week.get(wk, 0) + delta
        else:
            by_month[mk] = by_month.get(mk, 0) + delta

    # 직접 입력분: period 가 'YYYY-MM' 이면 월, 'W36' 이면 주차
    import re as _re
    for e in manual or []:
        if not isinstance(e, dict):
            continue
        per = str(e.get("period") or "").strip()
        try:
            dv = int(e.get("delta") or 0)
        except Exception:
            dv = 0
        if not per or not dv:
            continue
        mw = _re.match(r"^[Ww]?(\d{1,2})$", per)
        if mw:
            wk = "W%02d" % int(mw.group(1))
            mon = _month_of_week_key(int(mw.group(1)), month)
            if mon and mon != month:
                # 지난 달 주차는 그 달 합계로 접는다
                by_month[mon] = by_month.get(mon, 0) + dv
            else:
                by_week[wk] = by_week.get(wk, 0) + dv
            continue
        mm = _re.match(r"^(\d{4})[-/](\d{1,2})$", per)
        if mm:
            key = "%s-%02d" % (mm.group(1), int(mm.group(2)))
            if key == month:
                continue
            by_month[key] = by_month.get(key, 0) + dv

    return {
        "months": [{"key": k, "delta": v} for k, v in sorted(by_month.items()) if v],
        "weeks": [{"key": k, "delta": v} for k, v in sorted(by_week.items()) if v],
    }

# ============================================================
#  모델 주차 계획 저장 (잠김)
# ============================================================
# 월별 주차별 계획/실적 저장
@app.put("/admin/projects/{project_key}/models/{model_id}/weekly-plan")
def put_weekly_plan(project_key: str, model_id: str, payload: dict,
                    _admin: int = Depends(get_admin_session)):
    from urllib.parse import unquote
    import datetime as _dt
    model_id = unquote(model_id)
    _key = _model_key_alias(project_key)
    month = (payload.get("month") or "").strip() or _dt.date.today().strftime("%Y-%m")
    weeks_in = payload.get("weeks") or {}
    data = _load_models()
    proj = data.get("projects", {}).setdefault(_key, {"models": []})
    target = next((m for m in proj.get("models", [])
                   if (m.get("id") or "").lower() == model_id.lower()), None)
    if not target:
        raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")
    # 하바플레이트만 개발을 주차별 '그룹 총계'(weekly_summary)로 관리한다.
    # 나머지 프로젝트는 개발 모델도 모델별 주차 계획을 직접 입력한다.
    if target.get("group") == "개발" and _key in ("hrva_plate", "havaplate"):
        raise HTTPException(
            status_code=400,
            detail="하바플레이트 개발은 주차별 합계(weekly_summary)로 관리합니다.")
    cur = target.setdefault("weekly_plan", {})
    bucket = {}
    for w in _get_month_weeks(month):
        wp = weeks_in.get(w, {})
        bucket[w] = {"plan": int(wp.get("plan") or 0), "actual": int(wp.get("actual") or 0)}
    cur[month] = bucket
    target["weekly_progress"] = _ensure_mass_progress(cur, month)
    # -----------------------------------------------------------
    # 앱 표시용 필드 자동 반영 (po_qty/shipped_qty/due_text)
    # -----------------------------------------------------------
    _plan_total = sum(v["plan"] for v in bucket.values())
    _act_total = sum(v["actual"] for v in bucket.values())
    if _plan_total > 0 or _act_total > 0:
        # po_qty / shipped_qty 는 '전체 PO 대비 누적 출하'라 모델 목록에서 직접 관리한다.
        # 예전에는 여기서 이번 달 주차 합계로 덮어써서 누적값이 매달 날아갔다.
        target["due_text"] = f"{month} 주차계획 · 잔여 {_plan_total - _act_total}개"
    _save_models(data)
    return {"ok": True, "model_id": model_id, "month": month, "progress": target["weekly_progress"]}


# ─ 단계별 표준 소요 (주) ───────────────────────────────
PROCESS_LEAD_DEFAULT = {
    "powerbox": {
        "FA PO": 0, "자재 발주": 1, "자재 입고": 4,
        "CB": 2, "BV1": 2, "BV2": 1, "LA 입고": 1,
        # SI 는 실측 3건이 전부 앞 단계와 같은 날이었지만, 몰아서 입력한
        # 것인지 실제로 당일에 끝난 것인지 가릴 수 없다. 0주로 두면
        # '공짜 단계' 처럼 보인다 — 1주로 잡는다.
        "LAIR 작성": 1, "LAIR 승인": 2, "Source Inspection": 1,
        # 13·14번은 CDR/PRR 한 틀로 맞췄다 (_unify_cdr_prr).
        "FAIR 작성": 1, "FAIR 승인": 2,
        "CDR/PRR 작성": 1, "CDR/PRR 승인": 1, "최종 승인": 1,
    },
}


# ─ 사업부 단위 표준 소요 ──────────────────────────────
_AUTO_LEAD_MONTHS = {
    "SDI":        [6, 12, 4, 8, 10, 12],
    "현대차":      [4, 6, 6, 8, 10, 12],
    "LG마그나":    [12, 1, 2, 2, 1, 1],
    "LGE":        [3, 12, 8, 8, 8, 1],
    "Schaeffler": [6, 8, 10, 12, 14],
    "Stellantis": [11, 14, 17, 19, 21],
}

# 고객사 묶음 → 프로젝트 키. 한 묶음이 여러 프로젝트다 (현대차는
# KEFICO · MOBIS · 영화테크가 다 같은 절차를 쓴다).
_AUTO_LEAD_PROJECTS = {
    "SDI": ["automotive_sdi_hungary", "automotive_sdi_kr", "automotive_sdi_mlbw",
            "automotive_sdi_austria", "automotive_sdi_usa", "automotive_sdi_ppe"],
    "현대차": ["automotive_kefico_kr", "automotive_kefico_india",
             "automotive_kefico_vn", "automotive_hyundai_mobis",
             "automotive_hyundai_jg", "automotive_younghwa_tech",
             "auto_kefico"],
    "LG마그나": ["automotive_lg_magna"],
    "LGE": ["automotive_lge_vn", "automotive_lge_kr"],
    # 'Schaeffler' 와 'Schaefller' 두 프로젝트로 나뉘어 있다. 하나로
    # 합치기 전까지는 둘 다 같은 값을 쓴다.
    "Schaeffler": ["automotive_schaeffler", "automotive_schaefller",
                   "auto_schaeffler"],
    "Stellantis": ["automotive_stellantis", "auto_stellantis"],
}

# 프로젝트 키 → 자리별 소요(개월).
PROCESS_LEAD_MONTHS_BY_PROJECT = {
    pk: months
    for group, months in _AUTO_LEAD_MONTHS.items()
    for pk in _AUTO_LEAD_PROJECTS.get(group, [])
}

# ============================================================
#  단계 이름 · 소요 개월 · CDR/PRR
# ============================================================
def _lead_by_position(project_key: str, steps: list) -> dict:
    months = PROCESS_LEAD_MONTHS_BY_PROJECT.get(project_key) or []
    out = {}
    for i, name in enumerate(steps or []):
        if i >= len(months):
            break
        m = months[i]
        # 1개월 = 4.345주 (52.14 ÷ 12). 반올림해도 되돌리면 같은 달수다.
        out[name] = (int(round(m * 4.345)), "%d개월" % m)
    return out


PROCESS_LEAD_BY_DIVISION = {
    "bloom": {
        "PO 발주": 2, "PO 접수": 2,
        "PRP": 3,
        "최종 승인": 0,
    },
}


# '04 CB' → 'CB'. 엑셀마다 번호를 붙이기도 하고 안 붙이기도 한다
def _canon_step(name: str) -> str:
    t = str(name or "").strip()
    if len(t) > 3 and t[:2].isdigit():
        t = t[3:].strip()
    return t


# ─ 파워박스 공정 13·14번 자리를 한 틀로 ─────────────────────────
_CDR_PRR_PROJECTS = {"powerbox"}


# 바꾼 사본, 바꿀 게 없으면 None.
def _unify_cdr_prr(proc: list):
    import re as _re
    if not proc or not _re.match(r"^\d{2}\s", str((proc[0] or {}).get("name") or "")):
        return None
    names = [_canon_step((x or {}).get("name")) for x in proc]
    if "PRR 작성" in names or "PRR 승인" in names:
        out = []
        for x, c in zip(proc, names):
            t = dict(x or {})
            t["name"] = ("CDR/PRR " + c.split(" ", 1)[1]) if c in ("PRR 작성", "PRR 승인") else c
            out.append(t)
    elif "CDR" in names:
        i = names.index("CDR")
        cdr = dict(proc[i] or {})
        write = {"key": "", "name": "CDR/PRR 작성", "group": cdr.get("group") or "승인",
                 "expected": "", "actual": "", "status": ""}
        appr = dict(cdr)
        appr["name"] = "CDR/PRR 승인"
        out = [dict(x or {}) for x in proc[:i]] + [write, appr] + \
              [dict(x or {}) for x in proc[i + 1:]]
        for t in out:
            t["name"] = _canon_step(t.get("name"))
    else:
        return None
    # 번호와 key 를 다시 매긴다. 파워박스 틀은 key 가 step_N 이다.
    for n, t in enumerate(out, start=1):
        t["name"] = f"{n:02d} {t['name']}"
        t["key"] = f"step_{n}"
    return out


# 이 프로젝트가 실제로 쓰는 단계 이름.
def _project_steps(proj: dict) -> list:
    from collections import Counter
    sigs = Counter()
    for m in (proj or {}).get("models") or []:
        proc = m.get("process") or []
        if not proc:
            continue
        sigs[tuple(_canon_step(s.get("name")) for s in proc)] += 1
    if sigs:
        return list(sigs.most_common(1)[0][0])
    return [n for _k, n, _g in DEV_PROCESS_STEPS]

# ============================================================
#  공정 주소
# ============================================================
# 앱 칩 줄 — 단계 이름 + 표준 소요(주) ← admin v2 leadBtn.onclick() · 앱 model_list_screen.dart _loadSteps()
@app.get("/projects/{project_key}/process-steps")
def get_process_steps(project_key: str):
    _key = _model_key_alias(project_key)
    data = _load_models()
    proj = (data.get("projects") or {}).get(_key) or {}
    steps = _project_steps(proj)
    lead = proj.get("process_lead")
    src = "saved"
    if not isinstance(lead, dict) or not lead:
        lead = PROCESS_LEAD_DEFAULT.get(_key) or {}
        src = "default" if lead else "none"
    if not lead:
        # 프로젝트에 없으면 사업부 값을 쓴다 (블룸 — 프로젝트 15개가
        # 같은 세 단계를 쓴다).
        _div = _cl.derive_division_from_project(_key)
        lead = PROCESS_LEAD_BY_DIVISION.get(_div or "") or {}
        src = "division" if lead else "none"
    # 자리로 맞춘 값이 있으면 그게 먼저다 (자동차 — 고객사마다 단계
    # 이름이 달라서 이름으로는 못 맞춘다).
    bypos = _lead_by_position(_key, steps)
    if bypos:
        src = "고객사별"

    out = []
    for n in steps:
        if n in bypos:
            w, label = bypos[n]
            out.append({"name": n, "weeks": w, "label": label})
            continue
        v = lead.get(n)
        if v is None:
            v = lead.get(_canon_step(n))
        try:
            v = int(v) if v is not None and str(v).strip() != "" else None
        except (TypeError, ValueError):
            v = None
        # label 은 앱이 칩에 그대로 적는 글자다. 주 단위 값은 '2주'.
        # 안 정한 단계는 label 도 빈 글자라 칩에 아무것도 안 붙는다.
        out.append({"name": n, "weeks": v,
                    "label": ("%d주" % v) if isinstance(v, int) else ""})
    total = sum(x["weeks"] for x in out if isinstance(x.get("weeks"), int))
    return {"project_key": _key, "source": src, "steps": out, "total_weeks": total}


# 단계별 표준 소요(주) 저장. 빈 값은 '안 정함' 으로 둔다 ← admin v2 onclick()
@app.put("/admin/projects/{project_key}/process-lead")
async def admin_set_process_lead(project_key: str, request: Request,
                                 _admin: int = Depends(get_admin_session)):
    payload = await request.json()
    lead_in = (payload or {}).get("lead") or {}
    if not isinstance(lead_in, dict):
        raise HTTPException(status_code=400, detail="lead 는 객체여야 합니다.")
    lead = {}
    for k, v in lead_in.items():
        name = str(k or "").strip()
        if not name:
            continue
        t = str(v if v is not None else "").strip()
        if t == "":
            continue
        try:
            n = int(float(t))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"'{name}' 의 주 수가 숫자가 아닙니다: {v}")
        if n < 0 or n > 104:
            raise HTTPException(status_code=400, detail=f"'{name}' 의 주 수가 범위를 벗어납니다: {n}")
        lead[name] = n
    _key = _model_key_alias(project_key)
    data = _load_models()
    proj = (data.setdefault("projects", {})).setdefault(_key, {"models": []})
    if lead:
        proj["process_lead"] = lead
    else:
        proj.pop("process_lead", None)
    _save_models(data)
    return {"ok": True, "project_key": _key, "count": len(lead),
            "total_weeks": sum(lead.values())}


# 앱용 개발 승인 프로세스 조회
@app.get("/projects/{project_key}/models/{model_id}/process")
def get_model_process(project_key: str, model_id: str):
    from urllib.parse import unquote
    model_id = unquote(model_id)
    _key = _model_key_alias(project_key)
    data = _load_models()
    proj = data.get("projects", {}).get(_key, {})
    for m in proj.get("models", []):
        if isinstance(m, dict) and (m.get("id") or "").lower() == model_id.lower():
            if m.get("group") != "개발":
                raise HTTPException(status_code=400, detail="개발 모델만 프로세스가 있습니다.")
            try:
                _d = _cl.derive_division_from_project(_key) or ""
            except Exception:
                _d = ""
            # 여기도 GET 이다. 기본 단계를 깔아 주려고 models.json 을 통째로 다시 쓰고 있었다 — 앱이 품목 하나를 열 때마다 큰 파일을 쓴 셈이다
            _ensure_process(m, _d)
            # 저장은 엑셀이 적은 그대로, 보여줄 때만 최종 승인 기준으로 채운다
            _rolled = _process_rolled(m.get("process") or [])
            proc = _ds_show_notes(_rolled)
            # 세는 건 글자를 채우기 전 것으로 한다. 채운 사본은 '카이저 입고
            # 필요' 같은 글자가 실적 자리에 들어가 있어서, 그걸로 세면
            # 안 끝난 단계가 끝난 것으로 잡힌다.
            done = sum(1 for s in _rolled
                       if (str(s.get("actual") or "").strip() or str(s.get("status") or "") == "완료")
                       and str(s.get("status") or "") not in ("미승인", "미제출"))
            stage, expected = _process_current(_rolled)
            return {
                "model_id": model_id,
                "model_name": m.get("name") or model_id,
                "dev_type": m.get("dev_type") or "",
                "steps": proc,
                "done": done,
                "total": len(proc),
                "progress": _process_progress(_rolled),
                "current_stage": stage,
                "current_expected": expected,
                "issues": m.get("issues") or "",
            }
    raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")

# admin v2 'Process 입력' 화면용 조회 (앱용과 같은 형식).
@app.get("/admin/projects/{project_key}/models/{model_id}/process")
def admin_get_model_process(project_key: str, model_id: str,
                            _admin: int = Depends(get_admin_session)):
    return get_model_process(project_key, model_id)


# 공정 단계 하나의 상태만 바꾼다 (표의 상태 드롭다운) ← admin v2 procInput.onchange() · _pfProcess()
@app.post("/admin/projects/{project_key}/models/{model_id}/process/step-status")
def admin_set_process_step_status(project_key: str, model_id: str, payload: dict,
                                  _admin: int = Depends(get_admin_session)):
    from urllib.parse import unquote
    model_id = unquote(model_id)
    step_key = str(payload.get("step_key") or "").strip()
    status = str(payload.get("status") or "").strip()
    if not step_key:
        raise HTTPException(status_code=400, detail="step_key 가 필요합니다.")

    _key = _model_key_alias(project_key)
    data = _load_models()
    proj = data.get("projects", {}).get(_key, {})
    target = next((m for m in proj.get("models", [])
                   if isinstance(m, dict) and (m.get("id") or "").lower() == model_id.lower()), None)
    if target is None:
        raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")
    if target.get("group") != "개발":
        raise HTTPException(status_code=400, detail="개발 모델만 프로세스가 있습니다.")

    proc = _ensure_process(target)
    step = next((st for st in proc if str(st.get("key")) == step_key), None)
    if step is None:
        raise HTTPException(status_code=404, detail=f"단계 '{step_key}' 를 찾을 수 없습니다.")

    step["status"] = status
    # '완료'로 바꿔도 실적일을 임의로 채우지 않는다 (실제 날짜는 사용자가 입력)
    if status in ("", "대기", "진행중"):
        # 완료 취소면 실적일도 비운다 (진행률이 남아 있지 않게)
        step["actual"] = ""

    target["process"] = proc
    target["progress"] = _process_progress(proc)
    stage, expected = _process_current(proc)
    _save_models(data)
    print(f"[process] step {_key}/{model_id} {step_key} → {status or '기본'} (progress={target['progress']}%)")
    return {
        "ok": True,
        "model_id": model_id,
        "step_key": step_key,
        "status": status,
        "actual": step.get("actual", ""),
        "progress": target["progress"],
        "current_stage": stage,
        "current_expected": expected,
    }


# admin v2 'Process 입력' 저장.
@app.put("/admin/projects/{project_key}/models/{model_id}/process")
def admin_put_model_process(project_key: str, model_id: str, payload: dict,
                            _admin: int = Depends(get_admin_session)):
    from urllib.parse import unquote
    model_id = unquote(model_id)
    _key = _model_key_alias(project_key)
    data = _load_models()
    proj = data.get("projects", {}).get(_key, {})
    target = None
    for m in proj.get("models", []):
        if isinstance(m, dict) and (m.get("id") or "").lower() == model_id.lower():
            target = m
            break
    if target is None:
        raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")
    if target.get("group") != "개발":
        raise HTTPException(status_code=400, detail="개발 모델만 프로세스가 있습니다.")

    proc = _ensure_process(target)
    incoming = payload.get("steps")
    if not isinstance(incoming, list):
        raise HTTPException(status_code=400, detail="steps 는 배열이어야 합니다.")

    by_key = {str(s.get("key")): s for s in incoming if isinstance(s, dict) and s.get("key")}
    for i, st in enumerate(proc):
        src = by_key.get(str(st.get("key")))
        if src is None and i < len(incoming) and isinstance(incoming[i], dict):
            src = incoming[i]          # key 가 없으면 순서로 매칭
        if not isinstance(src, dict):
            continue
        for f in ("expected", "actual", "status"):
            if f in src:
                st[f] = str(src.get(f) or "").strip()

    dev_type = str(payload.get("dev_type") or target.get("dev_type") or "").strip().upper()
    if dev_type:
        target["dev_type"] = dev_type
    target["process"] = proc
    target["progress"] = _process_progress(proc)
    stage, expected = _process_current(proc)
    _save_models(data)
    print(f"[process] saved {_key}/{model_id} progress={target['progress']}%")
    return {
        "ok": True,
        "model_id": model_id,
        "progress": target["progress"],
        "current_stage": stage,
        "current_expected": expected,
    }


# ============================================================
#  파워박스 프로세스 엑셀: 시트별 템플릿
# ============================================================
_PB_SHEET_STEPS = {
    'majormodule': ['FA PO','자재 발주','자재 입고','CB','BV1','BV2','Source Inspection','FAIR 작성','FAIR 승인','PRR 작성','PRR 승인','최종 승인'],
    'pbx':  ['FA PO','자재 발주','자재 입고','CB','BV1','BV2','LA 입고','LAIR 작성','LAIR 승인','Source Inspection','FAIR 작성','FAIR 승인','PRR','최종 승인'],
    'ema':  ['FA PO','자재 발주','자재 입고','CB','BV1','BV2','LA 입고','LAIR 작성','LAIR 승인','Source Inspection','FAIR 작성','FAIR 승인','CDR','최종 승인'],
}

# ============================================================
#  파워박스 판가 엑셀
# ============================================================
# 파워박스 판가/재료비 엑셀 업로드 (PBX/MajorModule/EMA 시트 자동 인식)
@app.post("/admin/projects/{project_key}/price-import-xlsx")
async def admin_price_import_xlsx(project_key: str, file: UploadFile = File(...), _admin: int = Depends(get_admin_session)):
    if project_key != "powerbox":
        raise HTTPException(status_code=400, detail="파워박스 프로젝트에서만 사용 가능합니다.")
    import io
    import openpyxl
    try:
        raw = await _keep_upload(file, "/admin/projects/{project_key}/price-import-xlsx", project_key)
        wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, keep_links=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"엑셀 읽기 실패: {e}")

    COL = {
        "id_match": ["파트넘버", "모델"],
        "name": ["모델명", "모델"],
        "group": ["구분"],
        "dev_type": ["유형"],
        "price": ["판가"],
        "material_cost": ["재료비"],
    }

    def find_col(headers, candidates):
        for h_idx, h in enumerate(headers):
            hn = str(h or "").strip()
            for c in candidates:
                if hn == c:
                    return h_idx
        return None

    def num(v):
        if v is None:
            return 0
        s = str(v).replace(",", "").strip()
        try:
            return int(float(s))
        except Exception:
            return 0

    data = _load_models()
    proj = data.setdefault("projects", {}).setdefault("powerbox", {"models": []})
    if "models" not in proj:
        proj["models"] = []

    updated = added = skipped = 0

    for sheet_name in wb.sheetnames:
        if sheet_name not in ("PBX", "MajorModule", "EMA"):
            continue
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 2:
            continue
        headers = rows[1]
        col_id = find_col(headers, COL["id_match"])
        col_name = find_col(headers, COL["name"])
        col_grp = find_col(headers, COL["group"])
        col_dt = find_col(headers, COL["dev_type"])
        col_pr = find_col(headers, COL["price"])
        col_mc = find_col(headers, COL["material_cost"])
        if col_id is None:
            continue

        for r in rows[2:]:
            mid = str(r[col_id] if col_id < len(r) else "" or "").strip()
            if mid in ("", "-", "None"):
                skipped += 1
                continue
            name = str(r[col_name] if col_name is not None and col_name < len(r) else "").strip()
            if name.lower() in ("none", "nan", "null", ""):
                name = mid
            grp = str(r[col_grp] if col_grp is not None and col_grp < len(r) else "").strip()
            if grp.lower() in ("none", "nan", "null", ""):
                grp = "양산"
            dvt = str(r[col_dt] if col_dt is not None and col_dt < len(r) else "").strip()
            if dvt.lower() in ("none", "nan", "null"):
                dvt = ""
            pr = num(r[col_pr]) if col_pr is not None and col_pr < len(r) else 0
            mc = num(r[col_mc]) if col_mc is not None and col_mc < len(r) else 0
            if not dvt:
                # 시트 이름이 곧 구분이다 (PBX · EMA), 나머지는 양산(HVM)
                if sheet_name == "PBX":
                    dvt = "PBX"
                elif sheet_name == "EMA":
                    dvt = "EMA"
                else:
                    dvt = "HVM"

            target = None
            for m in proj["models"]:
                if (m.get("part_number") or "").strip() == mid or (m.get("id") or "").strip() == mid:
                    target = m
                    break
            if not target:
                proj["models"].append({
                    "id": mid, "name": name, "part_number": mid,
                    "group": grp, "dev_type": dvt, "status": "정상",
                    "progress": 0, "price": pr, "material_cost": mc,
                    "po_qty": 0, "shipped_qty": 0, "due_text": "", "issues": "",
                    "process": []
                })
                added += 1
            else:
                target["name"] = name
                target["part_number"] = mid
                target["group"] = grp
                target["dev_type"] = dvt
                target["price"] = pr
                target["material_cost"] = mc
                updated += 1

    _save_models(data)
    return {"ok": True, "updated": updated, "added": added, "skipped": skipped}


# 일정표 칸에 들어오는 값은 세 가지다.
#   날짜        → 그 날짜에 끝났다
#   '완료' 글자 → 끝나긴 했는데 날짜를 안 적었다
#   'NA' 따위   → 이 모델에는 없는 단계다 (파워박스는 LAIR 이 대개 없다)
# 예전에는 셋을 구분하지 않고 '칸이 비지 않았으면 완료' 로 봐서,
# NA 도 완료로 세고 '완료' 글자를 날짜 칸에 밀어 넣었다.
_STEP_NA = {'na', 'n/a', '-', '--', 'tbd', '미정', '해당없음', '없음', 'x'}

# 예전 임포터가 비고에 적어 두던 모양: '10 FAIR Approval: Not yet · 11 LAP Test: Not yet'
_AUTO_NOTE_RE = re.compile(r'^\s*\d{2}\s+[^:]+:[^·]+(·\s*\d{2}\s+[^:]+:[^·]+)*\s*$')

# ============================================================
#  공정 엑셀 한 번에 올리기 · 주차 요약 · 되살리기
# ============================================================
def _looks_auto_note(note) -> bool:
    t = str(note or '').strip()
    return bool(t) and bool(_AUTO_NOTE_RE.match(t))


# 날짜면 'YYYY-MM-DD', 아니면 빈칸.
def _step_date(raw: str) -> str:
    import process_import as _pi
    return _pi._as_date(raw) or ''


# 실적 칸 → (실적일, 상태).
def _step_actual(raw: str):
    t = (raw or '').strip()
    if not t:
        return '', ''
    d = _step_date(t)
    if d:
        return d, '완료'
    if t.lower() in _STEP_NA:
        return '', ''
    # 날짜는 아닌데 뭔가 적혀 있다 → 끝난 것으로 보되 날짜는 비워 둔다
    return '', '완료'


# 통합 업로드: MajorModule/PBX/EMA 시트 자동 인식, 프로세스+가격 한번에 ← admin v2 procInput.onchange() · _pfProcess()
@app.post("/admin/projects/{project_key}/import-xlsx")
@app.post("/admin/projects/{project_key}/process/import-xlsx")
async def admin_import_unified(project_key: str, file: UploadFile = File(...),
                               _admin: int = Depends(get_admin_session)):
    import io, openpyxl, re as _re
    data = _load_models()
    applied, skipped = [], []
    raw = await _keep_upload(file, "/admin/projects/{project_key}/process/import-xlsx", project_key)
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, keep_links=False)

    # 시트 이름 → 프로젝트. 단계는 엑셀 1행 머리글에서 읽는다.
    # 단계 수와 순서가 시트마다 다르고(파워박스 15, EMA 14, 메이저모듈 12)
    # 앞으로도 바뀐다 — 여기 적어 두면 엑셀이 바뀔 때마다 어긋난다.
    _PB = {
        'majormodule': {'proj': 'major_module', 'dt': ''},
        'pbx': {'proj': 'powerbox', 'dt': ''},
        'ema': {'proj': 'powerbox', 'dt': 'EMA'},
    }
    # 영문 단계명 → 우리말. 없는 건 엑셀에 적힌 그대로 쓴다.
    _STEP_KO = {
        'fa po': 'FA PO', 'material order': '자재 발주', 'material receiving': '자재 입고',
        'cb': 'CB', 'bv1': 'BV1', 'bv2': 'BV2',
        'source inspection': 'Source Inspection', 'la receiving': 'LA 입고',
        'lair preparation': 'LAIR 작성', 'lair approval': 'LAIR 승인',
        'fair preparation': 'FAIR 작성', 'fair approval': 'FAIR 승인',
        'prr preparation': 'PRR 작성', 'prr approval': 'PRR 승인',
        'cdr': 'CDR', 'final approval': '최종 승인',
        'final approval complete': '최종 승인', 'machining (assy)': '가공',
    }

    def _pn(s):
        return _re.sub(r'\s+', '', str(s or '')).strip()
    def _cs(v):
        import datetime
        if v is None:
            return ''
        if isinstance(v, (datetime.datetime, datetime.date)):
            return v.strftime('%Y-%m-%d')
        s = str(v).strip()
        return '' if s.startswith('=') else s

    import process_import as _pi

    for skey, cfg in _PB.items():
        ws = next((wb[n] for n in wb.sheetnames if n.strip().lower() == skey), None)
        if not ws:
            continue
        proj = data.get('projects', {}).get(cfg['proj'])
        if not proj:
            continue

        # 계획·실적 열은 1행 머리글에서 찾는다. 자리를 번호로 세면
        # 'Model' 열이 있는 시트(PBX·MajorModule)와 없는 시트(EMA)가
        # 한 칸씩 밀려서, 실적이 계획 칸으로 들어간다.
        head_row, pn_col, sheet_steps, comment_col = _pi.find_layout(ws)
        if not sheet_steps:
            print(f"[import-xlsx] '{ws.title}' 시트에서 단계 머리글을 못 찾음")
            continue
        n_steps = len(sheet_steps)

        # 판가·재료비도 머리글로 찾는다. 없으면 건드리지 않는다.
        price_col = cost_col = None
        for c in range(pn_col + 1, ws.max_column + 1):
            for rr in (head_row, head_row + 1):
                t = _pn(ws.cell(rr, c).value).lower()
                if t in ('판가', 'price', 'unitprice', '단가'):
                    price_col = price_col or c
                elif t in ('재료비', 'materialcost', 'material'):
                    cost_col = cost_col or c

        models = proj.get('models', [])
        for r in range(head_row + 2, ws.max_row + 1):
            pn = _pn(ws.cell(r, pn_col).value)
            if not pn or pn.lower() in ('total', '합계'):
                continue
            m = next((x for x in models if _pn(x.get('part_number')) == pn or _pn(x.get('id')) == pn), None)
            if not m:
                skipped.append(f"{skey}:{pn}")
                continue
            steps, done = [], 0
            for i, (no, en, pc, ac) in enumerate(sheet_steps):
                planned = _step_date(_cs(ws.cell(r, pc).value) if pc >= 1 else '')
                actual, status = _step_actual(_cs(ws.cell(r, ac).value) if ac >= 1 else '')
                if status == '완료':
                    done += 1
                name = _STEP_KO.get(en.strip().lower(), en.strip())
                # 단계 묶음 — 앞 3단계는 발주, 끝 5단계는 승인, 그 사이는 제작·검사
                if i < 3:
                    _grp = '발주'
                elif i < n_steps - 5:
                    _grp = '제작·검사'
                else:
                    _grp = '승인'
                steps.append({
                    'key': f'step_{i+1}',
                    'name': f'{no:02d} {name}',
                    'group': _grp,
                    'expected': planned, 'actual': actual, 'status': status,
                })
            # 엑셀의 빈 칸이 이미 적어 둔 날짜를 지우면 안 된다.
            # 하바플레이트에서 17종의 공정 입력이 이렇게 통째로 비워졌다.
            steps = _merge_process_keep(m.get('process'), steps)
            done = sum(1 for st in steps if str(st.get('status') or '') == '완료')
            m['process'] = steps
            m['progress'] = round(done / n_steps * 100) if n_steps else 0
            # 파워박스는 CDR/PRR 한 틀로 받는다 (_unify_cdr_prr)
            if cfg['proj'] in _CDR_PRR_PROJECTS:
                _u = _unify_cdr_prr(steps)
                if _u:
                    m['process'] = _u
                    m['progress'] = _process_progress(_u)
            # 개발 일정표에 올라온 모델이다. 양산으로 잡혀 있으면 바로잡는다.
            m['group'] = '개발'
            if cfg['dt']:
                m['dev_type'] = cfg['dt']
            applied.append(f"{skey}:{pn}")
            if price_col:
                _pv = _as_money(_cs(ws.cell(r, price_col).value), None)
                if _pv is not None:
                    m['price'] = _pv
            if cost_col:
                _mv = _as_money(_cs(ws.cell(r, cost_col).value), None)
                if _mv is not None:
                    m['material_cost'] = _mv
    # -----------------------------------------------------------
    # 위 시트(pbx/ema/majormodule)가 하나도 안 걸리면 일반 Process Schedule 형식으로 처리
    # -----------------------------------------------------------
    if not applied:
        import process_import as _pi
        parsed = _pi.parse_process_schedule(wb)
        rows = parsed.get('rows') or []
        if not rows:
            raise HTTPException(
                status_code=400,
                detail="프로세스 표를 찾지 못했습니다. 1행에 'Part Number' 와 '01 …' 형태의 단계 머리글이 있어야 합니다.",
            )
        _key = _model_key_alias(project_key)
        proj = data.get('projects', {}).get(_key)
        if not proj:
            raise HTTPException(status_code=404, detail=f"프로젝트 '{_key}' 를 찾을 수 없습니다.")
        models = proj.get('models', [])
        for row in rows:
            pn = _pn(row['part_number'])
            m = next((x for x in models
                      if _pn(x.get('part_number')) == pn or _pn(x.get('id')) == pn), None)
            if not m:
                skipped.append(pn)
                continue
            # 앱의 13단계 틀에 순서대로 채운다 (엑셀 단계 수가 달라도 있는 만큼만)
            proc = _default_process()
            cells = row['steps']
            for i, st in enumerate(proc):
                if i >= len(cells):
                    break
                st['expected'] = cells[i]['expected']
                st['actual'] = cells[i]['actual']
                st['status'] = cells[i]['status']
            proc = _merge_process_keep(m.get('process'), proc)
            m['process'] = proc
            m['progress'] = _process_progress(proc)
            if m.get('group') != '개발':
                m['group'] = '개발'
            # 비고는 사람이 적는 칸이다. 엑셀 칸에 'Not yet' · 'In stock' 같은 글자가 있다고 해서 그걸 모아 비고에 적지 않는다 — 40종이 전부 단계 상태
            # 나열로 덮여 정작 적어 둔 메모가 묻힌다
            if _looks_auto_note(m.get('note')):
                m['note'] = ''       # 예전 업로드가 적어 둔 것만 지운다
            applied.append(pn)
        print(f"[process/import-xlsx] Process Schedule 형식 인식 → {_key} {len(applied)}종")

    _save_models(data)
    return {'ok': True, 'applied': len(applied), 'skipped': len(skipped), 'detail': {'applied': applied[:10], 'skipped': skipped[:10]}}


# 하바플레이트 주차별 현황 엑셀 업로드 (양산/개발 총량 구조).
@app.post("/admin/projects/{project_key}/weekly-summary-import")
async def admin_import_weekly_summary(project_key: str, file: UploadFile = File(...), _admin: int = Depends(get_admin_session)):
    import io, openpyxl
    if project_key != "hrva_plate":
        raise HTTPException(status_code=400, detail="현재 하바플레이트만 지원합니다.")
    data = _load_models()
    proj = data.get("projects", {}).get(project_key)
    if not proj:
        raise HTTPException(status_code=404, detail="프로젝트 없음")
    raw = await _keep_upload(file, "/admin/projects/{project_key}/weekly-summary-import", project_key)
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, keep_links=False)
    ws = wb.worksheets[0]

    def _num(v):
        try: return int(float(v)) if v not in (None, "") else 0
        except Exception: return 0

    summary = {}
    for row_idx, label in [(5, "양산"), (6, "개발")]:
        row = [c.value for c in ws[row_idx]]
        weeks = {}
        # F(5)=7월 → W32계획=G(6), 실적=H(7) / W33=I(8)·J(9) / W34=K(10)·L(11) / W35=M(12)·N(13)
        for w_i, wname in enumerate(["W32", "W33", "W34", "W35"]):
            weeks[wname] = {"plan": _num(row[6 + w_i*2]), "actual": _num(row[7 + w_i*2])}
        summary[label] = {
            "po_qty": _num(row[2]),
            "actual_total": _num(row[3]),
            "remaining": _num(row[4]),
            "weeks": weeks,
            "next_month_plan": _num(row[15]),
            "month_note": str(row[16] or "")[:100] if len(row) > 16 else "",
        }
    summary["개발"]["price_fixed"] = 3400   # 개발 판가 고정
    proj["weekly_summary"] = summary
    _save_models(data)
    return {"ok": True, "summary": {k: {"po": v["po_qty"], "done": v["actual_total"]} for k, v in summary.items() if isinstance(v, dict)}}


# 백업 models.json 에서 개발 공정(process) 입력만 골라 현재 데이터에 되살린다
@app.post("/admin/projects/{project_key}/process-restore")
async def admin_restore_process(
    project_key: str,
    file: UploadFile = File(...),
    dry_run: bool = Form(default=False),
    _admin: int = Depends(get_admin_session),
):
    raw = await _keep_upload(file, "/admin/projects/{project_key}/process-restore", project_key)
    try:
        backup = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"JSON 을 읽을 수 없습니다: {e}")

    _key = _model_key_alias(project_key)
    src_proj = (backup.get("projects") or {}).get(_key) or {}
    src_models = src_proj.get("models") or []
    if not src_models:
        raise HTTPException(status_code=400, detail=f"백업에 '{_key}' 프로젝트 모델이 없습니다.")

    def _filled(proc):
        if not isinstance(proc, list):
            return 0
        return sum(1 for st in proc
                   if any(str((st or {}).get(k) or "").strip()
                          for k in ("expected", "actual", "status")))

    src_map = {str(m.get("id")): m.get("process") for m in src_models
               if isinstance(m, dict) and _filled(m.get("process"))}

    data = _load_models()
    proj = (data.get("projects") or {}).get(_key)
    if not proj:
        raise HTTPException(status_code=404, detail="현재 데이터에 프로젝트가 없습니다.")

    restored, skipped, missing = [], [], []
    for m in proj.get("models") or []:
        mid = str(m.get("id"))
        if mid not in src_map:
            continue
        if _filled(m.get("process")) >= _filled(src_map[mid]):
            skipped.append(mid)      # 현재 입력이 더 많거나 같으면 덮어쓰지 않는다
            continue
        if not dry_run:
            m["process"] = src_map[mid]
        restored.append(mid)
    cur_ids = {str(m.get("id")) for m in proj.get("models") or []}
    missing = [mid for mid in src_map if mid not in cur_ids]

    if not dry_run and restored:
        _save_models(data)
        print(f"[process-restore] {_key}: {len(restored)}종 복구")

    return {
        "ok": True,
        "restored": restored,
        "skipped": skipped,
        "missing_in_current": missing,
        "dry_run": bool(dry_run),
    }

# ============================================================
#  주간 보고 엑셀(W##.xlsx)
# ============================================================
# 주간 보고 엑셀(W##.xlsx) 한 장으로 모델·판가·PO·출하·비고·주차별 계획을 한 번에 반영.
@app.post("/admin/projects/{project_key}/report-import")
async def admin_import_weekly_report(
    project_key: str,
    file: UploadFile = File(...),
    sheet: str = Form(default=""),
    dry_run: bool = Form(default=False),
    _admin: int = Depends(get_admin_session),
):
    import io as _io
    import openpyxl
    import hrva_import as _imp

    raw = await _keep_upload(file, "/admin/projects/{project_key}/report-import", project_key)
    try:
        wb = openpyxl.load_workbook(_io.BytesIO(raw), data_only=True, keep_links=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"엑셀을 열 수 없습니다: {e}")

    try:
        parsed = _imp.parse_workbook(wb, sheet_name=sheet or None)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"엑셀 구조를 해석하지 못했습니다: {e}")

    return _apply_report_workbook(project_key, parsed, dry_run=dry_run)


# 엑셀에서 빠지면 지워도 되는 모델인지.
def _is_rpm_model(m: dict) -> bool:
    if not isinstance(m, dict):
        return False
    if _norm_group(m.get("group")) != "개발":
        return False
    return "RPM" in str(m.get("dev_type") or "").upper()


# 개발현황 엑셀(dev_status_import)을 모델에 반영한다
def _apply_dev_status(project_key: str, parsed: dict, dry_run: bool = False) -> dict:
    key = str(project_key or "").strip()
    data = _load_models()
    proj = (data.setdefault("projects", {})).setdefault(key, {"models": []})
    models = proj.setdefault("models", [])

    # 파트넘버 · 모델명 · id 아무거나로 맞춘다. 이 파일은 셋이 다 같은 값이다.
    by = {}
    for m in models:
        for f in ("part_number", "name", "id"):
            v = str(m.get(f) or "").strip().lower()
            if v:
                by.setdefault(v, m)

    added = updated = dated = 0
    cancelled, released, pending = [], [], []
    for r in (parsed.get("rows") or []):
        nm = str(r.get("name") or "").strip()
        if not nm:
            continue
        m = by.get(nm.lower())
        if m is None:
            m = {"id": nm, "name": nm, "part_number": nm, "group": "개발",
                 "status": "정상", "progress": 0, "process": _default_process()}
            models.append(m)
            by[nm.lower()] = m
            added += 1
        else:
            updated += 1

        m["group"] = "개발"
        if r.get("dev_type"):
            m["dev_type"] = r["dev_type"]
        if r.get("price") is not None:
            m["price"] = r["price"]
        if r.get("po_qty") is not None:
            m["po_qty"] = int(r["po_qty"])
        if r.get("shipped_qty") is not None:
            m["shipped_qty"] = int(r["shipped_qty"])
        if r.get("note"):
            m["note"] = r["note"]

        # 고객요청일 → FAIR 제출 예정일 · 가공 완료 → FAIR 제출 실제일
        proc = _ensure_process(m)
        if r.get("request_date") or r.get("machining_date"):
            _req = r.get("request_date") or ""
            if _req.startswith("9999"):
                _req = ""          # 9999-12-31 은 '미정' 표기다
            _set_fair_dates(proc, _req, r.get("machining_date") or "")
            if r.get("machining_date"):
                dated += 1
        elif r.get("machining_text"):
            pending.append(nm)
        m["process"] = proc
        m["progress"] = _process_progress(proc)

        # PO 취소 → 드롭예정. 멈춰 세운 일정은 지연으로 세지 않는다.
        _note = str(m.get("note") or "")
        if r.get("cancelled"):
            m["status"] = "드롭예정"
            if "PO 취소" not in _note:
                m["note"] = ("PO 취소 · " + _note).strip(" ·")
            cancelled.append(nm)
        elif "PO 취소" in _note:
            # 취소가 풀렸다. 우리가 붙인 표시만 걷어낸다 —
            # 사람이 직접 고른 드롭예정까지 되돌리면 안 된다.
            m["note"] = _note.replace("PO 취소 ·", "").replace("PO 취소", "").strip(" ·")
            if str(m.get("status") or "") == "드롭예정":
                m["status"] = "정상"
            released.append(nm)

    # 양산을 앞에, 개발을 뒤에 (같은 구분 안에서는 원래 순서 그대로)

    models.sort(key=lambda x: 0 if x.get("group") == "양산" else 1)
    if not dry_run:
        _save_models(data)
    return {"ok": True, "added": added, "updated": updated,
            "machining_dates": dated, "cancelled": cancelled,
            "released": released, "machining_pending": pending,
            "sheet": parsed.get("sheet"), "rows": len(parsed.get("rows") or [])}


# 주간 보고 엑셀 파싱 결과를 models.json 에 병합한다
def _apply_report_workbook(project_key: str, parsed: dict, dry_run: bool = False) -> dict:
    new_models = parsed.get("models") or []
    if not new_models:
        raise HTTPException(status_code=400, detail="모델 블록을 찾지 못했습니다. 시트 구조를 확인해주세요.")

    _key = _model_key_alias(project_key)
    data = _load_models()
    proj = data.setdefault("projects", {}).setdefault(_key, {})
    old_map = {str(m.get("id")): m for m in (proj.get("models") or []) if isinstance(m, dict)}

    merged = []
    added, updated = [], []
    for nm in new_models:
        mid = nm["id"]
        old = old_map.get(mid) or {}
        entry = dict(old)
        entry.update({
            "id": mid,
            "name": nm.get("name") or mid,
            "group": nm["group"],
            "price": nm.get("price") or old.get("price") or 0,
            "po_qty": nm.get("po_qty", 0),
            "shipped_qty": nm.get("shipped_qty", 0),
            "status": old.get("status") or "정상",
            "material_cost": old.get("material_cost") or 0,
        })
        if nm.get("material"):
            entry["material"] = nm["material"]
        # 비고: 엑셀이 정본, 비어 있으면 기존 유지
        if nm.get("note"):
            entry["note"] = nm["note"]
        # 이슈는 수기 입력이므로 건드리지 않는다
        entry.setdefault("issues", old.get("issues") or "")
        if nm["group"] == "개발":
            entry["dev_type"] = nm.get("dev_type") or old.get("dev_type") or ""
            proc = old.get("process")
            proc = proc if isinstance(proc, list) and proc else _default_process()
            # 개발단계(FAIR/LAIR) + 날짜를 해당 공정 단계에 자동 반영.
            # 이미 공정 입력이 있으면 건드리지 않는다 (프로세스 엑셀이 정본).
            _stage = (nm.get("dev_stage") or "").upper()
            _sdate = nm.get("stage_date") or ""
            _skind = nm.get("stage_date_kind") or ""
            _step_key = {"FAIR": "fair_write", "LAIR": "lair_write"}.get(_stage)
            if _step_key and _sdate:
                # 공정 단계 중 하나라도 계획일 · 실적일 · 상태가 적혀 있나
                _filled = False
                for _step in proc:
                    for _f in ("expected", "actual", "status"):
                        if str((_step or {}).get(_f) or "").strip():
                            _filled = True
                            break
                    if _filled:
                        break
                if not _filled:
                    for st in proc:
                        if st.get("key") != _step_key:
                            continue
                        if _skind == "actual":
                            st["actual"] = _sdate
                            st["status"] = "완료"
                        else:
                            st["expected"] = _sdate
                            st["status"] = "진행중"
                        break
            # 고객요청일 → FAIR 제출 예정일 · 가공 완료 → FAIR 제출 실제일
            _set_fair_dates(proc, nm.get("fair_expected") or "", nm.get("fair_actual") or "")
            entry["process"] = proc
            entry["progress"] = _process_progress(proc)
        # 양산이어도 기존 공정 데이터는 지우지 않는다 (그룹이 바뀌어도 입력이 남도록)
        # 주차: 엑셀에 있는 월만 덮어쓰고 나머지 월은 보존
        if nm.get("weekly_plan"):
            wp = dict(old.get("weekly_plan") or {})
            wp.update(nm["weekly_plan"])
            entry["weekly_plan"] = wp
        if nm.get("monthly_actual"):
            entry["monthly_actual"] = nm["monthly_actual"]
        merged.append(entry)
        (updated if mid in old_map else added).append(mid)

    # 엑셀에 없는 기존 모델 처리:
    #   RPM 개발품  → 정리 (주 단위로 바뀌는 항목이라 남길 이유가 없다)
    #   그 외(양산·HVM) → 그대로 유지. 예전에는 전부 잘려 나가면서
    #                     주차별 계획과 개발 공정 이력까지 같이 사라졌다.
    _new_ids = {m["id"] for m in merged}
    kept, removed = [], []
    for mid, _old in old_map.items():
        if mid in _new_ids:
            continue
        if _is_rpm_model(_old):
            removed.append(mid)
            continue
        kept.append(mid)
        merged.append(_old)
    # 양산을 앞에, 개발을 뒤에 (같은 구분 안에서는 원래 순서 그대로)
    merged.sort(key=lambda m: 0 if m.get("group") == "양산" else 1)

    result = {
        "ok": True,
        "sheet": parsed.get("sheet"),
        "counts": parsed.get("counts"),
        "added": added,
        "added_count": len(added),
        "updated_count": len(updated),
        "total": len(merged),
        "kept": kept,
        "removed": removed,
        "weekly_summary": {
            k: {"po": v.get("po_qty"), "done": v.get("actual_total"),
                "weeks": sorted((v.get("weeks") or {}).keys())}
            for k, v in (parsed.get("weekly_summary") or {}).items()
        },
        "dry_run": bool(dry_run),
    }
    if dry_run:
        return result

    proj["models"] = merged
    if parsed.get("weekly_summary"):
        # PO증감 이력·종수 같은 우리 쪽 필드가 날아가지 않게 병합한다.
        _cur = proj.setdefault("weekly_summary", {})
        for _g, _v in (parsed["weekly_summary"] or {}).items():
            _dst = _cur.setdefault(_g, {})
            for _k, _val in (_v or {}).items():
                if _k == "weeks":
                    _dst.setdefault("weeks", {}).update(_val or {})
                else:
                    _dst[_k] = _val
    _save_models(data)
    print(f"[report-import] {_key} sheet={parsed.get('sheet')} "
          f"models={len(merged)} added={len(added)} removed={len(removed)}")
    return result


# 모델의 '구분·판가 이력' (phases)

# ============================================================
#  판가 이력 · 구분(양산/개발)
# ============================================================
def _week_ord(month: str, week) -> int:
    try:
        y = int(str(month)[:4])
        mm = int(str(month)[5:7])
    except Exception:
        return 0
    try:
        w = int(str(week).lstrip("Ww") or 0)
    except Exception:
        return 0
    if mm == 1 and w >= 52:
        y -= 1
    elif mm == 12 and w <= 2:
        y += 1
    return y * 100 + w


# '2026-W36' → 202636.
def _phase_ord(v) -> int:
    import re as _re
    m = _re.match(r"^\s*(\d{4})\s*[-/]?\s*[Ww]?\s*(\d{1,2})\s*$", str(v or ""))
    if not m:
        return None
    return int(m.group(1)) * 100 + int(m.group(2))


# 저장/조회용 정규화. from 오름차순, 잘못된 항목은 버린다
def _norm_phases(v):
    if not isinstance(v, list):
        return []
    out = []
    for e in v:
        if not isinstance(e, dict):
            continue
        o = _phase_ord(e.get("from"))
        if o is None:
            continue
        g = "개발" if str(e.get("group") or "").strip() == "개발" else "양산"
        try:
            p = max(0, _as_money(e.get("price")))
        except Exception:
            p = 0
        try:
            mc = max(0, _as_money(e.get("material_cost")))
        except Exception:
            mc = 0
        out.append({"from": "%04d-W%02d" % (o // 100, o % 100), "group": g,
                    "price": p, "material_cost": mc})
    out.sort(key=lambda e: _phase_ord(e["from"]))
    return out


# 판가를 고치면 그 값으로 지난 주차 매출까지 다시 계산된다. 8월에 판
# $7,243 으로 나간 물량이 오늘 $7,800 으로 고치는 순간 8월 매출이 올라간다.
# 그래서 판가·재료비는 '언제부터' 를 달고 구간으로 쌓는다.
_PHASE_EPOCH = "2000-W01"      # '처음부터' 를 뜻하는 구간 시작점


# 오늘이 속한 주차를 구간 시작점 형식으로.
def _this_week_tag(ref=None) -> str:
    import datetime as _dtw
    iso = (ref or _dtw.date.today()).isocalendar()
    return "%04d-W%02d" % (int(iso[0]), int(iso[1]))


# 판가·재료비가 바뀌었으면 구간으로 남긴다
def _apply_price_change(entry: dict, old: dict, mode: str,
                        sent: dict = None) -> dict:
    def _money(v):
        try:
            return max(0, _as_money(v))
        except Exception:
            return 0

    def _has(k):
        if sent is None:
            return True
        return k in sent and str(sent.get(k) if sent.get(k) is not None else "").strip() != ""

    new_p, new_c = _money(entry.get("price")), _money(entry.get("material_cost"))
    old_p, old_c = _money(old.get("price")), _money(old.get("material_cost"))
    if not old:                       # 새 모델은 이력이 필요 없다
        return {}
    # 안 보낸 칸은 안 바뀐 것으로 본다
    if not _has("price"):
        new_p = old_p
        entry["price"] = old.get("price") if old.get("price") is not None else entry.get("price")
    if not _has("material_cost"):
        new_c = old_c
        entry["material_cost"] = (old.get("material_cost")
                                  if old.get("material_cost") is not None
                                  else entry.get("material_cost"))
    if abs(new_p - old_p) < 0.005 and abs(new_c - old_c) < 0.005:
        return {}

    ph = _norm_phases(entry.get("phases") or old.get("phases"))
    # 새 구간의 구분은 '직전 구간' 을 따라간다. 저장된 group 은 개발→양산
    # 전환 뒤에도 개발 그대로라, entry 를 보면 양산 모델이 개발로 되돌아간다.
    _prev = ph[-1] if ph else None
    grp = (_prev or {}).get("group") or entry.get("group") or old.get("group") or "양산"
    # '처음부터' 구간은 지금까지의 모습 그대로여야 한다. 개발품을 양산으로
    # 돌리면서 판가를 넣는 순간, 지난달까지의 개발 실적이 양산 판가로
    # 다시 계산되면 안 된다 — 그게 '지난 주차 매출은 그대로' 의 뜻이다.
    grp_old = old.get("group") or entry.get("group") or "양산"
    now = _this_week_tag()

    if str(mode) == "retro":
        # 지금 적용 중인 구간(마지막 구간)의 값을 고친다. 구간을 늘리지 않는다.
        if ph:
            ph[-1]["price"] = new_p
            ph[-1]["material_cost"] = new_c
            entry["phases"] = ph
        # 이력이 없으면 price 만 바뀌면 전 기간이 새 값이다 — 그게 의도다.
        return {"id": entry.get("id"), "mode": "retro",
                "from": (ph[-1]["from"] if ph else _PHASE_EPOCH),
                "price": [old_p, new_p], "material_cost": [old_c, new_c]}

    # from_now — 이번 주부터
    if not ph:
        # 이력이 없던 모델: 옛 값을 '처음부터' 구간으로 박아 과거를 고정한다
        ph = [{"from": _PHASE_EPOCH, "group": grp_old,
               "price": old_p, "material_cost": old_c}]
    # 칸이 없어서 안 온 값은 직전 구간 값을 이어받는다. 반대로 사람이
    # 눈으로 보고 0 으로 지운 값은 0 으로 남는다.
    _keep = ph[-1] if ph else {}
    _p = new_p if _has("price") else (_keep.get("price") or old_p or 0)
    _c = new_c if _has("material_cost") else (_keep.get("material_cost") or old_c or 0)
    if ph and ph[-1]["from"] == now:
        # 같은 주에 두 번 고쳐도 구간이 늘지 않는다
        ph[-1]["price"] = _p
        ph[-1]["material_cost"] = _c
    else:
        ph.append({"from": now, "group": grp,
                   "price": _p, "material_cost": _c})
    entry["phases"] = _norm_phases(ph)
    return {"id": entry.get("id"), "mode": "from_now", "from": now,
            "price": [old_p, new_p], "material_cost": [old_c, new_c]}


# 그 주차에 유효한 구간 {group, price, material_cost}.
def _phase_row_at(m: dict, month: str, week) -> dict:
    def _money(v):
        try:
            return max(0, _as_money(v))
        except Exception:
            return 0
    base = {"group": "개발" if (m or {}).get("group") == "개발" else "양산",
            "price": _money((m or {}).get("price")),
            "material_cost": _money((m or {}).get("material_cost"))}
    ph = _norm_phases((m or {}).get("phases"))
    if not ph:
        return base
    cur = _week_ord(month, week)
    hit = None
    for e in ph:
        if _phase_ord(e["from"]) <= cur:
            hit = e
        else:
            break
    # 첫 구간보다 앞선 주차는 첫 구간을 적용한다 (이력 이전 = 최초 상태)
    hit = hit or ph[0]
    # 구간에 적힌 값이 0 이어도 그게 그 시절의 값이다. 모델의 지금 값으로
    # 되돌리면 과거를 고정해 둔 의미가 없어진다 (개발 때 판가 0 이던 모델이
    # 양산 판가로 소급된다). 키가 아예 없을 때만 지금 값을 쓴다.
    _p = hit.get("price")
    _c = hit.get("material_cost")
    return {"group": hit["group"],
            "price": base["price"] if _p is None else _p,
            "material_cost": base["material_cost"] if _c is None else _c}


# 그 주차의 재료비.
def _phase_cost_at(m: dict, month: str, week):
    return _phase_row_at(m, month, week)["material_cost"]


# 그 주차에 유효한 (구분, 판가).
def _phase_at(m: dict, month: str, week):
    r = _phase_row_at(m, month, week)
    return r["group"], r["price"]


# 오늘 기준으로 '보이는' 구분.
def _display_group(m: dict, ref=None) -> str:
    base = "개발" if (m or {}).get("group") == "개발" else "양산"
    ph = _norm_phases((m or {}).get("phases"))
    if not ph:
        return base
    import datetime as _dt
    iso = (ref or _dt.date.today()).isocalendar()
    cur = int(iso[0]) * 100 + int(iso[1])
    hit = None
    for e in ph:
        if _phase_ord(e["from"]) <= cur:
            hit = e
        else:
            break
    # 첫 구간보다 앞이면 아직 이력이 시작되기 전 — 첫 구간을 쓴다
    return (hit or ph[0])["group"]

# ============================================================
#  주차별 매출 · 일 보고 매출
# ============================================================
def _dev_weeks_from_models(dev_model_weeks, dev_group):
    if not (dev_group or {}).get("weeks"):
        return True
    return any((v or {}).get("plan") or (v or {}).get("actual")
               for v in (dev_model_weeks or {}).values())


# ============================================================
#  일 보고 사업부의 매출
# ============================================================
# 그 프로젝트 모델들의 판가 평균.
def _daily_unit_price(proj: dict) -> float:
    out = []
    for m in (proj.get("models") or []):
        try:
            v = float(str(m.get("price") or 0).replace(",", "").strip() or 0)
        except Exception:
            v = 0.0
        if v > 0:
            out.append(v)
    return (sum(out) / len(out)) if out else 0.0


# 일 보고 자료의 '출하' 줄 → {주차: {plan, actual}}
def _daily_ship_weeks(project_key: str, month: str) -> dict:
    import datetime as _d3
    _key = _model_key_alias(project_key)
    _div = _daily_board_division(_key)
    if not _div:
        return {}
    _item = _bloom_item_of(_key)
    _store = _daily_store_key(_div) or _key
    proj = (_load_models().get("projects") or {}).get(_store) or {}
    allm = _bloom_store_months(proj)
    board = allm.get(month)
    if not isinstance(board, dict):
        return {}
    if _item:
        board = _bloom_slice(board, _item)
    elif _store != _key:
        board = _daily_slice_by_project(board, _key)
    if not isinstance(board, dict):
        return {}

    out = {}
    for it in (board.get("items") or []):
        for st in (it.get("steps") or []):
            if _daily_step_group(st, _DAILY_BOARD_ROWS.get(_div, ())) != "출하":
                continue
            for ds, cell in ((st.get("days") or {}).items()):
                try:
                    d = _d3.date.fromisoformat(str(ds)[:10])
                except Exception:
                    continue
                if d.strftime("%Y-%m") != month:
                    continue
                w = "W%02d" % d.isocalendar()[1]
                slot = out.setdefault(w, {"plan": None, "actual": None})
                for k in ("plan", "actual"):
                    v = (cell or {}).get(k)
                    if v is None:
                        continue
                    slot[k] = (slot[k] or 0) + int(v)
    return out


# 주차별 현황+매출: 양산 = 모델별 weekly_plan 실적 합산 x 각 모델 판가 개발 = weekly_summary 그룹 실적 x $3,400 고정 (모델별
# 주차 데이터 없음) ← admin v2 renderRevenueCard() · 앱 api_service.dart fetchWeeklyRevenue()
@app.get("/projects/{project_key}/weekly-revenue")
def get_weekly_revenue(project_key: str, month: str = None):
    import datetime as _dt
    data = _load_models()
    _key = _model_key_alias(project_key)
    proj = data.get("projects", {}).get(_key)
    if not proj:
        return {"detail": "프로젝트 없음"}
    ws_data = proj.get("weekly_summary") or {}
    if not month:
        month = _dt.date.today().strftime("%Y-%m")

    DEV_PRICE = 3400
    # 주차 목록: 요청한 월 기준으로 필터링
    if month:
        # month 파라미터가 있으면 해당 월의 주차만 사용
        all_weeks = _get_month_weeks(month)
    else:
        # month 없으면 weekly_summary 기준
        # 양산 · 개발 두 묶음에 나오는 주차 전부
        _week_set = set()
        for _grp in ("양산", "개발"):
            if _grp not in ws_data:
                continue
            for _w in (ws_data[_grp].get("weeks") or {}):
                _week_set.add(_w)
        all_weeks = sorted(_week_set)
        if not all_weeks:
            all_weeks = _get_month_weeks(month)
    # -----------------------------------------------------------
    # 모델별 주차 실적 x 그 주차에 유효한 판가
    # -----------------------------------------------------------
    # 한 모델이 달 중간에 개발→양산으로 넘어가면 주차마다 다른 그룹/판가로 잡힌다.
    yang_weeks = {w: {"plan": 0, "actual": 0, "revenue": 0, "plan_revenue": 0} for w in all_weeks}
    dev_model_weeks = {w: {"plan": 0, "actual": 0, "revenue": 0, "plan_revenue": 0} for w in all_weeks}
    yang_models_used, dev_models_used = [], []
    # -----------------------------------------------------------
    # 일 보고 사업부면 수량을 거기서 받는다 (판가는 양식 그대로)
    # -----------------------------------------------------------
    _daily_div = _daily_board_division(_key)
    _daily_price = 0.0
    if _daily_div:
        _dq = _daily_ship_weeks(_key, month)
        _daily_price = _daily_unit_price(proj)
        for w in all_weeks:
            c = _dq.get(w) or {}
            p = int(c.get("plan") or 0)
            a = int(c.get("actual") or 0)
            if not p and not a:
                continue
            yang_weeks[w]["plan"] += p
            yang_weeks[w]["actual"] += a
            yang_weeks[w]["plan_revenue"] += int(round(p * _daily_price))
            yang_weeks[w]["revenue"] += int(round(a * _daily_price))

    for m in proj.get("models", []):
        bucket = (m.get("weekly_plan") or {}).get(month) or {}
        if not bucket:
            continue
        acc = {"양산": {"plan": 0, "actual": 0, "price": 0},
               "개발": {"plan": 0, "actual": 0, "price": 0}}
        for w in all_weeks:
            cell = bucket.get(w) or {}
            p, a = int(cell.get("plan") or 0), int(cell.get("actual") or 0)
            g, price = _phase_at(m, month, w)
            # 개발인데 판가가 비어 있으면 고정단가로 계산 (기존 동작 유지)
            if g == "개발" and not price:
                price = DEV_PRICE
            tgt = yang_weeks if g == "양산" else dev_model_weeks
            tgt[w]["plan"] += p
            tgt[w]["actual"] += a
            # 판가에 소수가 있을 수 있다. 누적은 정확히 하고 응답에서 반올림한다.
            tgt[w]["revenue"] += a * price
            tgt[w]["plan_revenue"] += p * price
            if p or a:
                acc[g]["plan"] += p
                acc[g]["actual"] += a
                acc[g]["price"] = price
        for g in ("양산", "개발"):
            if acc[g]["plan"] or acc[g]["actual"]:
                (yang_models_used if g == "양산" else dev_models_used).append(
                    {"id": m.get("id"), "price": acc[g]["price"],
                     "plan": acc[g]["plan"], "actual": acc[g]["actual"]})
    # 센트 단위까지 누적한 뒤 여기서 원 단위로 반올림한다.
    # 앱은 매출을 정수로 받으므로 float 이 그대로 나가면 파싱에서 터진다.
    for _wk in (yang_weeks, dev_model_weeks):
        for _v in _wk.values():
            _v["revenue"] = round(_v["revenue"])
            _v["plan_revenue"] = round(_v["plan_revenue"])

    yang_total = {"plan": sum(v["plan"] for v in yang_weeks.values()),
                  "actual": sum(v["actual"] for v in yang_weeks.values()),
                  "revenue": sum(v["revenue"] for v in yang_weeks.values()),
                  "plan_revenue": sum(v["plan_revenue"] for v in yang_weeks.values())}
    # -----------------------------------------------------------
    # 개발
    # -----------------------------------------------------------
    # 1) 개발 모델에 주차 값이 들어와 있으면 그걸 정본으로 쓴다 (파워박스 등).
    #    단가는 모델 판가가 있으면 그걸, 없으면 $3,400 고정단가.
    # 2) 모델 쪽이 비어 있고 weekly_summary['개발'] 그룹 총계만 있으면 그걸 쓴다
    #    (하바플레이트 — 개발을 모델이 아니라 그룹 단위로 관리한다).
    #    판단은 _dev_weeks_from_models 에 있다.
    dev_g = ws_data.get("개발") or {}
    if not _dev_weeks_from_models(dev_model_weeks, dev_g):
        # 하바플레이트: 개발은 모델이 아니라 그룹 총계로 관리 (x 고정단가)
        dev_weeks = {}
        for w in all_weeks:
            cell = (dev_g.get("weeks") or {}).get(w) or {}
            p, a = int(cell.get("plan") or 0), int(cell.get("actual") or 0)
            dev_weeks[w] = {"plan": p, "actual": a, "revenue": a * DEV_PRICE,
                            "plan_revenue": p * DEV_PRICE}
        dev_models_used = []
    else:
        # 나머지 프로젝트: 위 루프에서 구간 기준으로 이미 모아둔 값
        dev_weeks = dev_model_weeks
    dev_total = {"plan": sum(v["plan"] for v in dev_weeks.values()),
                 "actual": sum(v["actual"] for v in dev_weeks.values()),
                 "revenue": sum(v["revenue"] for v in dev_weeks.values()),
                 "plan_revenue": sum(v["plan_revenue"] for v in dev_weeks.values())}

    combined = {w: {"plan": yang_weeks[w]["plan"] + dev_weeks[w]["plan"],
                    "actual": yang_weeks[w]["actual"] + dev_weeks[w]["actual"],
                    "revenue": yang_weeks[w]["revenue"] + dev_weeks[w]["revenue"],
                    "plan_revenue": yang_weeks[w]["plan_revenue"] + dev_weeks[w]["plan_revenue"]}
                for w in all_weeks}

    yang_g = ws_data.get("양산") or {}
    return {
        "month": month,
        "start_week": all_weeks[0] if all_weeks else None,
        "weeks": all_weeks,
        "groups": {
            "양산": {"po_qty": yang_g.get("po_qty", 0),
                     "actual_total": yang_g.get("actual_total", 0),
                     "remaining": yang_g.get("remaining", 0),
                     "unit_price": None, "weeks": yang_weeks, "total": yang_total,
                     "models_used": yang_models_used},
            "개발": {"po_qty": dev_g.get("po_qty", 0),
                     "actual_total": dev_g.get("actual_total", 0),
                     "remaining": dev_g.get("remaining", 0),
                     "unit_price": DEV_PRICE, "weeks": dev_weeks, "total": dev_total,
                     "models_used": dev_models_used},
        },
        "combined": {"weeks": combined,
                     "total": {"plan": yang_total["plan"] + dev_total["plan"],
                               "actual": yang_total["actual"] + dev_total["actual"],
                               "revenue": yang_total["revenue"] + dev_total["revenue"],
                               "plan_revenue": yang_total["plan_revenue"] + dev_total["plan_revenue"]}},
        "note": "양산 = 모델별 판가 x 주차 실적. 개발 = 그룹 총계가 있으면 실적 x $3,400 고정, "
                "없으면 개발 모델의 모델별 주차 입력 x 모델 판가(판가 없으면 $3,400).",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))


# ============================================================
#  기동할 때 한 번 지나가는 정리
# ============================================================
# 예전 임포터가 비고에 적어 두던 단계 나열을 지운다
_PLAN_KEEP = {"chamber"}

# ============================================================
#  서버 켤 때 한 번 도는 정리
# ============================================================
def _cleanup_plan_originals() -> None:
    try:
        import config_loader as _c
        keys = [p.get("id") for p in _c.get_projects(division_id="semiconductor")]
    except Exception as e:
        print(f"[cleanup] 반도체 프로젝트 목록 조회 실패: {e}")
        return
    try:
        data = _load_models()
        hit = []
        for key in keys:
            if not key or key in _PLAN_KEEP:
                continue
            proj = (data.get("projects") or {}).get(key)
            if not isinstance(proj, dict):
                continue
            plan = proj.get("weekly_plan")
            if not isinstance(plan, dict) or not plan.get("photo_ref"):
                continue
            try:
                _delete_note_photo(plan["photo_ref"])
            except Exception:
                pass
            del proj["weekly_plan"]
            hit.append(f"{key}({plan.get('file_name') or '이름없음'})")
        if hit:
            _save_models(data)
            print(f"[cleanup] 주차별 계획 원본 {len(hit)}건 제거: {', '.join(hit)}")
    except Exception as e:
        print(f"[cleanup] 주차별 계획 원본 정리 실패(무시하고 계속): {e}")


# 서버 켤 때 — 자동으로 붙었던 옛 메모 정리.
def _cleanup_auto_notes() -> None:
    try:
        data = _load_models()
        hit = []
        for pkey, proj in (data.get("projects") or {}).items():
            for m in (proj or {}).get("models") or []:
                if isinstance(m, dict) and _looks_auto_note(m.get("note")):
                    m["note"] = ""
                    hit.append(f"{pkey}/{m.get('id')}")
        if hit:
            _save_models(data)
            print(f"[cleanup] 자동으로 적힌 비고 {len(hit)}건 삭제: {', '.join(hit[:5])}"
                  + (" ..." if len(hit) > 5 else ""))
    except Exception as e:
        print(f"[cleanup] 비고 정리 실패(무시하고 계속): {e}")


# ============================================================
#  큐리 버스바 되살리기 (1회)
# ============================================================
# 내가 잘못 만든 마이그레이션이 버스바 품번 11개(560D~570D)를 한 모델로 합치면서 지워버렸다

_CURIE_KEY = "spacex"
_CURIE_PN_RE = __import__("re").compile(r"^5[5-7]\dD$", __import__("re").I)
_CURIE_RESTORE_KEY = "curie_busbar_restored"


# 서버 켤 때 — CURIE 버스바 품목을 백업에서 되살린다 (한 번만).
def _restore_curie_busbar() -> None:
    import glob
    import json as _json
    try:
        data = _load_models()
        if (data.get("migrations") or {}).get(_CURIE_RESTORE_KEY):
            return
        proj = (data.get("projects") or {}).get(_CURIE_KEY)
        if not isinstance(proj, dict):
            return

        def _pns(models):
            return {str((m or {}).get("id") or "") for m in (models or [])
                    if isinstance(m, dict) and _CURIE_PN_RE.match(str(m.get("id") or ""))}

        if _pns(proj.get("models")):
            data.setdefault("migrations", {})[_CURIE_RESTORE_KEY] = True
            _save_models(data)
            return

        best = None
        for path in sorted(glob.glob(f"{MODELS_FILE}.auto_*"), reverse=True):
            try:
                with open(path, encoding="utf-8") as f:
                    old = _json.load(f)
            except Exception:
                continue
            ms = ((old.get("projects") or {}).get(_CURIE_KEY) or {}).get("models") or []
            if len(_pns(ms)) >= 10:
                best = (path, ms)
                break
        if not best:
            print("[curie] 되살릴 백업을 못 찾았다 — 품번은 직접 넣어야 한다")
            return

        path, ms = best
        proj["models"] = ms
        # 합치면서 만든 묶음 모델은 뺀다. 보드 행이 11개를 묶어 보여준다.
        proj["models"] = [m for m in proj["models"]
                          if not (isinstance(m, dict)
                                  and str(m.get("id") or "").strip() == "버스바/시트메탈류(11종)")]
        data.setdefault("migrations", {})[_CURIE_RESTORE_KEY] = True
        _save_models(data)
        print(f"[curie] 버스바 품번 {len(_pns(ms))}개를 되살렸다 "
              f"(모델 {len(proj['models'])}개, 출처 {os.path.basename(path)})")
    except Exception as e:
        print(f"[curie] 버스바 되살리기 실패(무시하고 계속): {e}")


# 현황 문구에 적힌 보류를 프로젝트 필드로 한 번 새겨 둔다
def _stamp_holds_once() -> None:
    try:
        data = _load_models()
        hit = []
        for pk, proj in (data.get("projects") or {}).items():
            if not isinstance(proj, dict):
                continue
            if _stamp_project_hold(proj, proj.get("status_note")):
                hit.append(f"{pk}={proj.get('hold')}")
        if hit:
            _save_models(data)
            print(f"[hold] 현황 문구에서 보류를 새겼다: {', '.join(hit)}")
    except Exception as e:
        print(f"[hold] 보류 새기기 실패(무시하고 계속): {e}")


# ============================================================
#  모델 상태 '진행' 을 '정상' 으로 (한 번)
# ============================================================
# 서버 켤 때 — 옛 상태 글자 정리.
def _cleanup_legacy_status() -> None:
    try:
        data = _load_models()
        hit = []
        for pkey, proj in (data.get("projects") or {}).items():
            for m in (proj or {}).get("models") or []:
                if not isinstance(m, dict):
                    continue
                st = str(m.get("status") or "").strip()
                if st in _LEGACY_MODEL_STATUS:
                    m["status"] = _LEGACY_MODEL_STATUS[st]
                    hit.append(f"{pkey}/{m.get('id')}")
        if hit:
            _save_models(data)
            print(f"[cleanup] 옛 상태 '진행' → '정상' {len(hit)}건: {', '.join(hit[:5])}"
                  + (" ..." if len(hit) > 5 else ""))
    except Exception as e:
        print(f"[cleanup] 옛 상태 정리 실패(무시하고 계속): {e}")


_cleanup_auto_notes()
_cleanup_plan_originals()
_restore_curie_busbar()
_cleanup_legacy_status()


# 서버 켤 때 — 파워박스 CDR/PRR 공정을 한 틀로 맞춘다
def _cleanup_cdr_prr() -> None:
    try:
        data = _load_models()
        hit = []
        for pkey in _CDR_PRR_PROJECTS:
            proj = (data.get("projects") or {}).get(pkey) or {}
            for m in proj.get("models") or []:
                if not isinstance(m, dict):
                    continue
                u = _unify_cdr_prr(m.get("process") or [])
                if u:
                    m["process"] = u
                    m["progress"] = _process_progress(u)
                    hit.append(f"{pkey}/{m.get('id')}")
        if hit:
            _save_models(data)
            print(f"[cleanup] 공정 CDR/PRR 틀로 맞춤 {len(hit)}건: {', '.join(hit[:5])}"
                  + (" ..." if len(hit) > 5 else ""))
    except Exception as e:
        print(f"[cleanup] CDR/PRR 정리 실패(무시하고 계속): {e}")


_cleanup_cdr_prr()


# 이미 저장된 블룸 보드에 'Corva KPE' / 'Corva KPE (117품목)' 가 따로 쌓인 것을 한 번 합친다
def _cleanup_bloom_dupes() -> None:
    try:
        import bloom_daily_import as _bd
        data = _load_models()
        changed = 0
        for pk, proj in (data.get("projects") or {}).items():
            b = (proj or {}).get("daily_board")
            if not isinstance(b, dict) or not b.get("items"):
                continue
            items = b["items"]
            n_items = len({_norm_label(_bd.clean_item(i.get("item"))) for i in items
                           if isinstance(i, dict)})
            n_steps = sum(len(i.get("steps") or []) for i in items if isinstance(i, dict))
            folded = _bloom_fold(items)
            if n_items == len(items) and \
                    n_steps == sum(len(i.get("steps") or []) for i in folded) and \
                    all(i.get("item") == f.get("item") for i, f in zip(items, folded)):
                continue
            b["items"] = folded
            # 접은 품목들의 공정에 나오는 날짜 전부
            _days = set()
            for _item in folded:
                for _step in (_item.get("steps") or []):
                    for _d in ((_step or {}).get("days") or {}):
                        _days.add(_d)
            b["dates"] = sorted(_days)
            changed += 1
        if changed:
            _save_models(data)
            print(f"[bloom] 중복 품목 합침: 보드 {changed}개")
    except Exception as e:
        print(f"[bloom] 중복 품목 합치기 실패: {e}")


_cleanup_bloom_dupes()
_stamp_holds_once()


# -----------------------------------------------------------
# 고객사 묶음을 자료로 옮겨 적기 — 딱 한 번
# -----------------------------------------------------------
# 묶음은 이제 양식의 묶음 칸이 정한다 (division_columns.customer_group).
_GROUP_SEED_FILE = DATA_DIR / "customer_groups_seeded.json"


# 지금 있는 고객사의 묶음을 자료(customer_group)에 한 번 적는다
def _seed_customer_groups() -> None:
    if _GROUP_SEED_FILE.exists():
        return
    try:
        data = _load_models()
        projects = data.setdefault("projects", {})
        n = 0
        for div in list(_dcol.CUSTOMER_GROUPS):
            for p in _cl.get_projects(division_id=div, visible_only=False):
                pid = p.get("id")
                if not pid:
                    continue
                proj = projects.get(pid)
                if isinstance(proj, dict) and proj.get("customer_group"):
                    continue            # 엑셀로 이미 들어온 값이 있다
                grp = _dcol.seed_group(div, pid, p.get("label") or "")
                if not grp:
                    continue            # 아리스타 — 구분 1 이 정한다
                projects.setdefault(pid, {"models": []})
                projects[pid]["customer_group"] = list(grp)
                projects[pid]["customer_group_src"] = "seed"
                n += 1
        if n:
            _save_models(data)
        _GROUP_SEED_FILE.write_text(json.dumps(
            {"at": datetime.now().isoformat(timespec="seconds"), "count": n},
            ensure_ascii=False), encoding="utf-8")
        print("[묶음] 지금 있는 고객사 %d곳의 묶음을 자료에 적었습니다 (한 번만)" % n)
    except Exception as e:
        print("[묶음] 옮겨 적기 실패(다음에 다시): %s" % e)


_seed_customer_groups()


# 매출 — 사업부 전체. 실적과 예상은 출처가 다르다
REVENUE_FILE = DATA_DIR / "revenue.json"

# ============================================================
#  사장님 지시사항
# ============================================================
# 앱 홈 맨 위 노란 카드. 전사 공통이라 사업부와 상관없이 한 벌이다.
# 줄마다 기한(날짜까지 · 기한 없음 · 매일 · 매주)과 등록일을 따로 가진다.
import home_orders as _ho

ORDERS_FILE = DATA_DIR / "home_orders.json"

# ============================================================
#  수주
# ============================================================
def _orders_load() -> dict:
    try:
        return _ho.load(ORDERS_FILE)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


# 앱 홈이 읽는다 — 완료는 빼고, 급한 것부터 ← admin v2 saveOrders()
@app.get("/home/orders")
def get_home_orders():
    data = _orders_load()
    items = _ho.for_app(data.get("items"))
    return {"items": items, "count": len(items),
            "updated_at": data.get("updated_at", "")}


# admin 편집 화면 — 완료한 줄까지 다 준다 ← admin v2 saveOrders()
@app.get("/admin/home/orders")
def admin_home_orders(_admin: int = Depends(get_admin_session)):
    data = _orders_load()
    items = data.get("items") or []
    return {"items": items,
            "live": _ho.for_app(items),
            "done_count": sum(1 for i in items if i.get("done")),
            "updated_at": data.get("updated_at", "")}


# ============================================================
#  사업부별 한 눈 (앱 홈의 매출 · 진행현황)
# ============================================================
# 사람이 넣는 건 타겟뿐이다. 실적은 사업부마다 이미 들어오는 자료가 달라서 (반도체는 주간보고, 블룸은 매일 올리는 보고자료, 나머지는 모델의 판가 × 출하 실적)
# 여기서 출처까지 같이 들고 나간다
DIV_TARGET_FILE = DATA_DIR / "division_targets.json"

# ============================================================
#  사업부 목표 · 실적 (홈 매출 카드)
# ============================================================
def _div_targets() -> dict:
    try:
        raw = json.loads(DIV_TARGET_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


# 사업부 월 매출 목표 하나를 저장한다
def _div_target_set(month: str, division_id: str, total) -> dict:
    data = _div_targets()
    mon = data.setdefault(month, {})
    try:
        v = float(str(total).replace(",", "").strip() or 0)
    except ValueError:
        raise HTTPException(status_code=400, detail="타겟은 숫자로 넣어 주세요.")
    if v > 0:
        mon[division_id] = {"total": round(v, 2),
                            "at": datetime.now().isoformat(timespec="seconds")}
    else:
        mon.pop(division_id, None)          # 0 이면 지운다 = '미등록'
    DIV_TARGET_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    return data


# 모델의 판가 × 출하 실적. 달을 나눌 수 없어서 누계다
def _div_model_money(models: list) -> float:
    out = 0.0
    for m in models or []:
        if not isinstance(m, dict):
            continue
        try:
            out += _as_money(m.get("price"), 0) * int(m.get("shipped_qty") or 0)
        except Exception:
            continue
    return round(out, 2)


# 그 달 주차별 **실적**을 다 더한 금액 (판가 × 실적 수량).
def _div_actual_money(models: list, month: str):
    out = 0.0
    hit = False
    for m in models or []:
        if not isinstance(m, dict):
            continue
        bucket = ((m.get("weekly_plan") or {}).get(month) or {})
        qty = 0
        for cell in bucket.values():
            if not isinstance(cell, dict):
                continue
            got = cell.get("actual")
            if got is None:
                continue
            try:
                qty += int(got)
            except Exception:
                continue
            hit = True
        if not qty:
            continue
        try:
            out += _as_money(m.get("price"), 0) * qty
        except Exception:
            continue
    return round(out, 2) if hit else None


# 그 달 주차별 계획을 다 더한 금액 (판가 × 계획 수량).
def _div_plan_money(models: list, month: str) -> float:
    out = 0.0
    for m in models or []:
        if not isinstance(m, dict):
            continue
        bucket = ((m.get("weekly_plan") or {}).get(month) or {})
        qty = 0
        for cell in bucket.values():
            if isinstance(cell, dict):
                try:
                    qty += int(cell.get("plan") or 0)
                except Exception:
                    continue
        if not qty:
            continue
        try:
            out += _as_money(m.get("price"), 0) * qty
        except Exception:
            continue
    return round(out, 2)


# (그 달 출하 계획 금액, 출하 실적 금액).
def _daily_div_money(plist: list, projects: dict, month: str) -> tuple:
    plan = act = 0.0
    for p in plist or []:
        pk = (p or {}).get("id")
        if not pk:
            continue
        try:
            _div = _daily_board_division(pk)
            if not _div or _daily_store_key(_div) == pk:
                continue
            price = _daily_unit_price(projects.get(pk) or {})
            if price <= 0:
                continue
            wk = _daily_ship_weeks(pk, month)
        except Exception as _e:
            print("[일보고매출] %s 계산 실패(무시) — %s" % (pk, _e))
            continue
        plan += sum(int((c or {}).get("plan") or 0) for c in wk.values()) * price
        act += sum(int((c or {}).get("actual") or 0) for c in wk.values()) * price
    return round(plan, 2), round(act, 2)


# 정상 · 지연 · 특이사항 · 집중관리.
def _div_counts(models: list) -> dict:
    c = {"total": 0, "normal": 0, "delayed": 0, "issue": 0, "watch": 0}
    for m in models or []:
        if not isinstance(m, dict):
            continue
        c["total"] += 1
        alert = _model_alert(m, _display_group(m))
        if alert == "지연":
            c["delayed"] += 1
        elif alert == "주의" or _model_hold(m):
            c["watch"] += 1                      # 집중관리 (보류 포함)
        elif str(m.get("issues") or "").strip():
            c["issue"] += 1                      # 특이사항
        else:
            c["normal"] += 1
    return c


# 홈 사업부 매출 카드 한 줄씩 — 목표 · 실적 · 어디서 온 숫자인지.
def _home_division_rows(month: str) -> list:
    data = _load_models()
    # 앱에서 숨긴 사업부. 홈 관리 화면이 켜고 끄는 값이고,
    # 매출 · 진행현황 표에는 '앱 숨김' 꼬리표로 붙는다. admin 에서는
    # 숨겨도 줄이 사라지지 않는다 — 자료는 계속 올려야 한다.
    _app_hidden = _dvis.hidden_set()
    projects = data.get("projects") or {}
    targets = (_div_targets().get(month) or {})

    # 반도체는 주간보고에서 실적·타겟이 온다 (매출 관리 화면이 쓰는 그 값)
    try:
        rv = _rev.month_view(_load_revenue(), month)
    except Exception:
        rv = {}

    rows = []
    for d in _cl.get_divisions(visible_only=True):
        did = d.get("id")
        try:
            plist = _cl.get_projects(did, visible_only=True)
        except Exception:
            plist = []
        models, with_models = [], 0
        for p in plist:
            ms = (projects.get(p.get("id")) or {}).get("models") or []
            if ms:
                with_models += 1
            models.extend(ms)

        actual, a_src, a_at = 0.0, "", ""
        target, t_src = 0.0, ""
        # -----------------------------------------------------------
        # 매출 파일이 있으면 그게 먼저다
        # -----------------------------------------------------------
        # 판가 × 실적은 어림값이다. 회계가 쓰는 숫자에는 스페어 부품 · 반제품 단가 차이 · 선매출 · 환율 적용 시점이 다 들어 있어서, ESS 10월만 놓고도
        # $516만이 달랐다
        _file_usd = None
        try:
            _file_usd = _drev.month_usd(did, month)
        except Exception as _e:
            print("[사업부매출] %s 읽기 실패(무시) — %s" % (did, _e))
        if _file_usd is not None:
            actual, a_src = float(_file_usd), "매출 파일"
            a_at = ""

        if _file_usd is not None:
            pass
        elif did == "semiconductor":
            actual = float(rv.get("actual") or 0)
            a_src, a_at = "주간보고", str(rv.get("as_of") or "")
            if rv.get("has_target"):
                target, t_src = float(rv.get("target") or 0), "직접 입력"
        elif did == "bloom":
            board = (projects.get(_BLOOM_STORE) or {}).get("daily_board") or {}
            money = (board.get("money") or {}).get("total") or {}
            actual = float(money.get("done_usd") or 0)
            target = float(money.get("plan_usd") or 0)
            a_at = str(board.get("report_date") or "")
            if actual or target:
                a_src, t_src = "보고자료 금액", "보고자료 계획"
        else:
            # 그 달 주차 실적이 있으면 달로 가른다
            _mon_actual = _div_actual_money(models, month)
            if _mon_actual is None:
                actual, a_src = 0.0, ""
            else:
                actual = _mon_actual
                a_src = "판가 × 그 달 실적"
        # -----------------------------------------------------------
        # 타겟도 매출 파일이 먼저다
        # -----------------------------------------------------------
        # 네트워크 · 자동차 파일에는 그 달 '실행계획' 이 같이 들어 있다.
        # 사람이 손으로 넣은 값이 있으면 그게 더 먼저다 — 아래에서 덮는다.
        try:
            _file_plan = _drev.month_plan(did, month)
        except Exception:
            _file_plan = None
        if _file_plan:
            target, t_src = float(_file_plan), "매출 파일 계획"

        # 자료에 계획이 없는 사업부는 손으로 넣은 타겟을 쓴다
        if did in targets and (targets.get(did) or {}).get("total"):
            target = float((targets.get(did) or {}).get("total") or 0)
            t_src = "직접 입력"

        # 그래도 없으면 그 달 주차별 계획을 다 더해 쓴다.
        # 손으로 적은 값이 늘 먼저다 — 사람이 정한 숫자를 계산이 덮지 않는다.
        if not target:
            target = _div_plan_money(models, month)
            if target:
                t_src = "그 달 계획 합계"

        # 일 보고 사업부(블룸·ESS)는 계획이 일 보고 보드에 있다 (_daily_div_money).
        if not target and _daily_store_key(did):
            _dp, _da = _daily_div_money(plist, projects, month)
            if _dp:
                target, t_src = _dp, "그 달 계획 합계 (일 보고)"
                if not actual and _da:
                    actual, a_src = _da, "일 보고 출하 실적"

        rows.append({
            "id": did, "label": d.get("label"), "order": d.get("order", 999),
            "actual": round(actual, 2), "actual_source": a_src, "actual_at": a_at,
            "target": round(target, 2), "target_source": t_src,
            "has_target": target > 0,
            "rate": round(actual / target * 100, 1) if target > 0 else None,
            "projects": len(plist), "projects_with_models": with_models,
            "models": len(models),
            "counts": _div_counts(models),
            "target_editable": t_src != "보고자료 계획",
            "app_visible": str(did or "").lower() not in _app_hidden,
        })
    rows.sort(key=lambda r: r.get("order", 999))
    return rows


# admin '홈 관리' 화면 — 앱 홈에 뜨는 것을 한자리에서 ← admin v2 renderHomeAdmin()
@app.get("/admin/home/summary")
def admin_home_summary(month: str = None,
                       _admin: int = Depends(get_admin_session)):
    month = _check_month(month)
    rows = _home_division_rows(month)
    orders = _orders_load()
    return {
        "month": month,
        "divisions": rows,
        "total_actual": round(sum(r["actual"] for r in rows), 2),
        "total_target": round(sum(r["target"] for r in rows), 2),
        "no_target": [r["id"] for r in rows
                      if not r["has_target"] and r["target_editable"]],
        "orders": orders.get("items") or [],
        "orders_live": _ho.for_app(orders.get("items")),
    }


# 자료에 계획이 없는 사업부의 그 달 타겟 ← admin v2 sv.onclick() · saveTarget()
@app.post("/admin/home/division-target")
def admin_home_division_target(month: str = Form(...),
                               division_id: str = Form(...),
                               total: str = Form(...),
                               _admin: int = Depends(get_admin_session)):
    month = _check_month(month)
    if not _cl.get_division(division_id):
        raise HTTPException(status_code=400, detail="없는 사업부입니다.")
    _div_target_set(month, division_id, total)
    return {"ok": True, "divisions": _home_division_rows(month)}


# 목록을 통째로 저장한다. 줄이 몇 개 안 되고 순서도 뜻이 있어서 한 줄씩 고치는 것보다 통째로 주고받는 쪽이 어긋날 일이 없다 ← admin v2 saveOrders()
@app.put("/admin/home/orders")
async def admin_home_orders_save(payload: dict = Body(...),
                                 _admin: int = Depends(get_admin_session)):
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="items 목록이 필요합니다.")
    if len(items) > _ho.MAX_ITEMS:
        raise HTTPException(status_code=400,
                            detail=f"지시사항은 {_ho.MAX_ITEMS}줄까지입니다.")
    data = _ho.save(ORDERS_FILE, items)
    return {"ok": True, "items": data["items"], "live": _ho.for_app(data["items"]),
            "updated_at": data["updated_at"]}


_MONTH_RE = re.compile(r"20\d\d-\d{2}$")

# ============================================================
#  매출 파일 · 매출 상세
# ============================================================
def _check_month(month: str) -> str:
    month = (month or "").strip() or datetime.now().strftime("%Y-%m")
    if not _MONTH_RE.match(month):
        raise HTTPException(status_code=400, detail="month 는 YYYY-MM 형식입니다.")
    return month


# 매출 실적 자료(revenue.json)를 읽는다
def _load_revenue() -> dict:
    try:
        return _rev.load(REVENUE_FILE)
    except _rev.RevenueFileBroken as e:
        # 빈 값으로 돌려주면 다음 저장이 멀쩡한 파일을 덮어쓴다.
        raise HTTPException(status_code=500,
                            detail=f"매출 파일을 읽지 못했습니다: {e}")


# 매출 실적 자료를 저장한다
def _save_revenue(store: dict) -> None:
    _rev.save(REVENUE_FILE, store)


# 파일 이름에서 연도(20xx)를 뽑는다
def _year_hint(name: str) -> int:
    m = re.search(r"(20\d\d)", str(name or ""))
    return int(m.group(1)) if m else datetime.now().year


# 사업부 하나를 더 쪼갠 줄들. 없으면 빈 목록.
def _div_breakdown(div: str, month: str) -> list:
    out = []
    try:
        if div == "semiconductor":
            rv = _rev.month_view(_load_revenue(), month) or {}
            # 내부거래도 한 줄로 세운다. 빼 놓으면 쪼갠 줄을 다 더해도 사업부 줄과 안 맞는다 — 10월만 해도 $421만이 비었다 (묶음 합 $1652만 vs 사업부 줄
            # $2073만).
            _gs = list(rv.get("groups") or [])
            if isinstance(rv.get("internal"), dict):
                _gs.append(rv["internal"])
            for g in _gs:
                a = int(round(float(g.get("actual") or 0)))
                if not a:
                    continue
                out.append({"item": str(g.get("label") or g.get("key") or ""),
                            "actual": a})
        else:
            # month_detail 은 {"groups": [{label, actual, items}]} 모양이다.
            det = _drev.month_detail(div, month) or {}
            for g in (det.get("groups") or []):
                a = int(round(float(g.get("actual") or 0)))
                if not a:
                    continue
                # '고객사별' 은 위 묶음들을 다시 쪼갠 같은 돈이다. 같이
                # 세우면 사업부 합계의 두 배가 선다.
                if str(g.get("key") or "") == "cust":
                    continue
                out.append({"item": str(g.get("label") or ""), "actual": a})
    except Exception as _e:
        print("[전사매출] %s 쪼개기 실패(무시) — %s" % (div, _e))
        return []
    out.sort(key=lambda x: -x["actual"])
    return out


# 매출 상세 화면 — 사업부별 목표 · 실적 표.
def _all_division_revenue_view(month: str, only: str = "") -> dict:
    rows = [r for r in _home_division_rows(month) if r.get("app_visible")]
    if only:
        rows = [r for r in rows if r.get("id") == only]

    actual = sum(float(r.get("actual") or 0) for r in rows)
    target = sum(float(r.get("target") or 0) for r in rows)

    ytd = 0.0
    for r in rows:
        try:
            ytd += float(_div_ytd_money(r.get("id"), month) or 0)
        except Exception as _e:
            print("[전사매출] %s 누적 실패(무시) — %s" % (r.get("id"), _e))

    # 묶음 = 사업부. 반도체 화면의 '반도체 · 데이터센터 · 우주항공' 자리에
    # 사업부 이름이 들어간다 — 전사로 보면 그게 묶음이다.
    groups = []
    for r in rows:
        a = float(r.get("actual") or 0)
        t = float(r.get("target") or 0)
        if not a and not t:
            continue
        groups.append({
            "key": str(r.get("id") or ""),
            "label": str(r.get("label") or r.get("id") or ""),
            "actual": int(round(a)),
            "estimate": int(round(t)),
            "rate": int(round(a / t * 100)) if t > 0 else None,
            # 그 사업부 안의 쪼갬
            "items": _div_breakdown(str(r.get("id") or ""), month),
        })

    # 언제 기준인지. 사업부마다 다르면 제일 늦은 날짜를 적는다.
    # 실적이 있는 줄만 본다 — 11월 실적이 0 인데 반도체 보고자료 날짜를 따라
    # '2026-10-05 까지' 가 떠서, 11월 실적이 10월 5일에 멈춘 것처럼 읽혔다.
    as_of = ""
    for r in rows:
        if not float(r.get("actual") or 0):
            continue
        at = str(r.get("actual_at") or "")
        if at > as_of:
            as_of = at

    # 목표도 실적도 없는 사업부 — 줄로는 안 세우고 이름만 알려 준다.
    # 아예 안 보이면 '그 사업부는 목표가 없다' 는 것을 알 길이 없다.
    no_target = [str(r.get("label") or r.get("id") or "") for r in rows
                 if not float(r.get("actual") or 0) and not float(r.get("target") or 0)]

    return {
        "month": month,
        "actual": int(round(actual)),
        "target": int(round(target)),
        "has_target": target > 0,
        "target_rate": int(round(actual / target * 100)) if target > 0 else None,
        "target_left": int(round(max(0.0, target - actual))),
        "estimate": int(round(target)),
        "rate": int(round(actual / target * 100)) if target > 0 else None,
        "left": int(round(max(0.0, target - actual))),
        "ytd": int(round(ytd)),
        "as_of": as_of,
        "groups": groups,
        "no_target": no_target,
        "internal": None,
        "has_data": bool(groups),
        "has_estimate": target > 0,
        "has_estimate_groups": any(g.get("estimate") for g in groups),
        "scope": "전사" if not only else str(only),
    }


# 그 달의 묶음별 실적 + 사람이 넣은 예상 ← admin v2 renderRevenuePage() · 앱 revenue_service.dart fetch()
@app.get("/revenue")
def get_revenue(month: str = None, division: str = "semiconductor"):
    month = _check_month(month)
    div = (division or "").strip()
    if div == "semiconductor":
        return _rev.month_view(_load_revenue(), month)
    return _all_division_revenue_view(month, div)


# 매출 관리 화면이 처음 켜질 때 받는 것 ← admin v2 renderRevenuePage()
@app.get("/admin/revenue/state")
def admin_revenue_state(month: str = None,
                        _admin: int = Depends(get_admin_session)):
    month = _check_month(month)
    store = _load_revenue()
    view = _rev.month_view(store, month)
    y = (store.get("years") or {}).get(month[:4]) or {}
    view["months_all"] = sorted((y.get("months") or {}).keys())
    return view


# 주간보고 엑셀을 받는다 ← admin v2 send()
@app.post("/admin/revenue/import")
async def admin_revenue_import(mode: str = Form("preview"),
                               file: UploadFile = File(...),
                               _admin: int = Depends(get_admin_session)):
    raw = await _keep_upload(file, "/admin/revenue/import", "")
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    name = file.filename or ""
    store = _load_revenue()
    try:
        parsed = _rev.parse_weekly(raw, _year_hint(name))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"엑셀을 읽지 못했습니다: {e}")

    months = sorted((parsed.get("months") or {}).keys())
    view_month = months[-1] if months else datetime.now().strftime("%Y-%m")
    for m in reversed(months):
        # 실적이 들어와 있는 마지막 달을 보여준다
        trial0 = {"years": {str(parsed["year"]): {
            "weeks": parsed["weeks"], "months": parsed["months"],
            "totals": parsed["totals"], "lines": parsed["lines"]}}}
        if _rev.month_view(trial0, m)["actual"] > 0:
            view_month = m
            break

    before = _rev.month_view(store, view_month)
    trial = json.loads(json.dumps(store))
    _rev.apply_weekly(trial, parsed, name)
    after = _rev.month_view(trial, view_month)

    # 세부를 더한 값이 [합 계] 블록과 다르면 조용히 넘기지 않는다
    gaps = []
    for b in after["groups"] + [after["internal"]]:
        if b["items_actual"] != b["actual"]:
            gaps.append({"label": b["label"], "items": b["items_actual"],
                         "total": b["actual"]})

    out = {
        "file": name, "mode": mode, "year": parsed.get("year"),
        "weeks": len(parsed.get("weeks") or []),
        "lines": len(parsed.get("lines") or []),
        "months": months,
        "view_month": view_month,
        "gaps": gaps,
        "before": {"actual": before["actual"]},
        "after": {"actual": after["actual"]},
    }
    if mode != "commit":
        return out
    out["applied"] = _rev.apply_weekly(store, parsed, name)
    _save_revenue(store)
    out["saved"] = True
    return out


# 그 달 예상 매출을 Commodity 별로 넣는다
@app.post("/admin/revenue/estimate")
def admin_revenue_estimate(month: str = Form(...),
                           items: str = Form("[]"),
                           _admin: int = Depends(get_admin_session)):
    month = _check_month(month)
    try:
        rows = json.loads(items or "[]")
    except Exception:
        raise HTTPException(status_code=400, detail="항목을 읽지 못했습니다.")
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="항목은 목록이어야 합니다.")
    store = _load_revenue()
    try:
        res = _rev.set_estimate(store, month, rows, "직접 입력")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _save_revenue(store)
    res["view"] = _rev.month_view(store, month)
    return res


# 그 달 타겟을 금액 하나로 넣는다 ← admin v2 tgs.onclick()
@app.post("/admin/revenue/target")
def admin_revenue_target(month: str = Form(...),
                         total: str = Form(...),
                         _admin: int = Depends(get_admin_session)):
    month = _check_month(month)
    store = _load_revenue()
    try:
        res = _rev.set_target(store, month, total, "직접 입력")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _save_revenue(store)
    res["view"] = _rev.month_view(store, month)
    return res


# Estimate 파일을 받아 그 달 예상 매출로 넣는다 ← admin v2 sendEst()
@app.post("/admin/revenue/estimate/import")
async def admin_revenue_estimate_import(month: str = Form(...),
                                        mode: str = Form("preview"),
                                        file: UploadFile = File(...),
                                        _admin: int = Depends(get_admin_session)):
    month = _check_month(month)
    raw = await _keep_upload(file, "/admin/revenue/estimate/import", "")
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    name = file.filename or ""
    try:
        parsed = _rev.parse_estimate(raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"엑셀을 읽지 못했습니다: {e}")

    store = _load_revenue()
    before = _rev.month_view(store, month)
    out = {"file": name, "mode": mode, "month": month,
           "items": parsed["items"], "total": parsed["total"],
           # 시트가 스스로 적어 둔 합계와 우리가 더한 값이 다르면 말해 준다
           "stated": parsed.get("stated"), "gap": parsed.get("gap"),
           "before": {"estimate": before["estimate"]},
           "after": {"estimate": parsed["total"]}}
    if mode != "commit":
        return out
    out["applied"] = _rev.set_estimate(store, month, parsed["items"], name)
    _save_revenue(store)
    out["saved"] = True
    out["view"] = _rev.month_view(store, month)
    return out


# ============================================================
#  사업부 월별 매입·지급 현황
# ============================================================
# PCB 사업부의 '월별 매입 현황 분석' 엑셀을 담는 자리다
import purchases as _pur

PURCHASE_FILE = DATA_DIR / "purchases.json"

# ============================================================
#  매입 · 지급
# ============================================================
def _pur_load() -> dict:
    return _pur.load(PURCHASE_FILE)


# 앱 카드 한 장이 필요한 전부 — 월별 + 누적 ← admin v2 save() · renderPurchasePage() · 앱 purchase_service.dart fetch()
@app.get("/division/{div}/purchase")
def get_division_purchase(div: str, region: str = "total"):
    return _pur.for_app(_pur_load(), (div or "").strip(), region)


# 사업부 매입·지급 자료 보기 ← admin v2 save() · renderPurchasePage()
@app.get("/admin/division/purchase")
def admin_division_purchase(div: str, _admin: int = Depends(get_admin_session)):
    data = _pur_load()
    div = (div or "").strip()
    out = _pur.for_admin(data, div)
    out["view"] = _pur.for_app(data, div)
    out["updated_at"] = data.get("updated_at", "")
    return out


# 사업부 매입·지급 자료 고치기 (잠김) ← admin v2 save() · renderPurchasePage()
@app.put("/admin/division/purchase")
def admin_division_purchase_save(payload: dict = Body(...),
                                 _admin: int = Depends(get_admin_session)):
    div = str((payload or {}).get("division") or "").strip()
    if not div:
        raise HTTPException(status_code=400, detail="사업부를 지정해 주세요.")
    data = _pur.put_division(_pur_load(), div, payload or {})
    saved = _pur.save(PURCHASE_FILE, data)
    out = _pur.for_admin(saved, div)
    out["view"] = _pur.for_app(saved, div)
    out["updated_at"] = saved.get("updated_at", "")
    out["saved"] = True
    return out


# ============================================================
#  매입 현황 엑셀 올리기
# ============================================================
# preview 로 한 번 보여 주고, commit 이어야 저장한다
import purchase_import as _purim


# 매입·지급 엑셀 올리기 ← admin v2 upload()
@app.post("/admin/division/purchase/import-xlsx")
async def admin_division_purchase_import(
        div: str = Form(...),
        file: UploadFile = File(...),
        year: Optional[int] = Form(None),
        sheet: Optional[str] = Form(None),
        mode: str = Form("preview"),
        _admin: int = Depends(get_admin_session)):
    div = (div or "").strip()
    if not div:
        raise HTTPException(status_code=400, detail="사업부를 지정해 주세요.")
    name = file.filename or ""
    if not name.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="xlsx 파일을 올려 주세요.")
    raw = await _keep_upload(file, "/admin/division/purchase/import-xlsx", "")
    try:
        parsed = _purim.parse_workbook(raw, year=year, sheet=sheet)
    except Exception as e:
        raise HTTPException(status_code=400, detail="엑셀을 읽지 못했습니다: %s" % e)

    data = _pur_load()
    body = (data.get("divisions") or {}).get(div) or {}
    cur = body.get("months") or {}
    merged = _purim.merge(cur, parsed["months"])
    payload = {"currency": body.get("currency", "USD"), "months": merged}
    summary = _purim.merge_summary(body.get("summary"), parsed.get("summary"))
    if summary:
        payload["summary"] = summary

    out = {"file": name, "division": div, "mode": mode,
           "sheet": parsed["sheet"], "sheets": parsed["sheets"],
           "year": parsed["year"],
           "months": sorted(parsed["months"]),
           "kept": sorted(m for m in cur if m not in parsed["months"]),
           "regions": parsed.get("regions") or [],
           "has_summary": bool(parsed.get("summary")),
           "notes": sorted((parsed.get("summary") or {}).get("notes") or {}),
           "read": parsed["read"], "warnings": parsed["warnings"],
           "preview": _pur.for_app(_pur.put_division(data, div, payload), div)}
    if mode != "commit":
        return out

    saved = _pur.save(PURCHASE_FILE, _pur.put_division(data, div, payload))
    out["saved"] = True
    out["updated_at"] = saved.get("updated_at", "")
    out["state"] = _pur.for_admin(saved, div)
    return out

# ============================================================
#  사업부 매출 (매출 관리 화면이 반도체 아닌 사업부를 열 때)
# ============================================================
# 그 해 1월부터 이 달까지의 매출.
def _div_ytd_money(div: str, month: str) -> float:
    try:
        year = int(str(month)[:4])
        upto = int(str(month)[5:7])
    except Exception:
        return 0.0
    data = _load_models()
    projects = data.get("projects") or {}
    try:
        plist = _cl.get_projects(div, visible_only=True)
    except Exception:
        plist = []
    models = []
    for p in plist:
        models.extend((projects.get(p.get("id")) or {}).get("models") or [])

    total = 0.0
    for mm in range(1, upto + 1):
        key = "%04d-%02d" % (year, mm)
        try:
            got = _drev.month_usd(div, key)
        except Exception:
            got = None
        if got is None:
            got = _div_actual_money(models, key)
        if got:
            total += float(got)
    return round(total, 2)


# 사업부 하나의 매출. 홈 카드와 같은 숫자를 쓴다
def _div_revenue_view(div: str, month: str) -> dict:
    row = None
    for r in _home_division_rows(month):
        if r.get("id") == div:
            row = r
            break
    if row is None:
        raise HTTPException(status_code=404, detail="없는 사업부입니다.")

    data = _load_models()
    projects = data.get("projects") or {}
    try:
        plist = _cl.get_projects(div, visible_only=True)
    except Exception:
        plist = []

    rows = []
    for p in plist:
        ms = (projects.get(p.get("id")) or {}).get("models") or []
        # 위 합계와 같은 잣대로 센다. 프로젝트 줄은 누계고 합계는 월별이면 더해도 안 맞아서 "어느 쪽이 틀렸지" 를 찾게 된다
        money = _div_actual_money(ms, month) or 0.0
        shipped = sum(int(m.get("shipped_qty") or 0)
                      for m in ms if isinstance(m, dict))
        po = sum(int(m.get("po_qty") or 0)
                 for m in ms if isinstance(m, dict))
        rows.append({"id": p.get("id"), "label": p.get("label") or p.get("id"),
                     "models": len(ms), "po_qty": po, "shipped_qty": shipped,
                     "money": money})
    rows.sort(key=lambda r: -r["money"])

    return {
        "scope": "division",
        "division": div,
        "label": row.get("label"),
        "month": month,
        "actual": row.get("actual"),
        "actual_source": row.get("actual_source"),
        "actual_at": row.get("actual_at"),
        "target": row.get("target"),
        "target_source": row.get("target_source"),
        "target_editable": row.get("target_editable"),
        "has_target": row.get("has_target"),
        "rate": row.get("rate"),
        "counts": row.get("counts"),
        "projects": rows,
        "months_all": [],
        # 반도체 화면과 같은 칸을 채운다.
        "ytd": _div_ytd_money(div, month),
        # -----------------------------------------------------------
        # 구분별 실적 표
        # -----------------------------------------------------------
        # Min: "반도체사업부도 보면 내가 있는 품목이 아니더라도 매출 관리
        #      파일 기준으로 구분이 나눠져 있잖아 다른 사업부들도 다
        #      동일하게 해줘"
        #
        # 매출 파일이 적어 둔 구분 그대로 준다. 없으면 화면이 아래
        # 프로젝트별 표로 떨어진다 — 그때는 판가 × 실적이다.
        "detail": _drev.month_detail(div, month),
        "as_of": row.get("actual_at") or "",
        "target_rate": row.get("rate"),
        # 매출 파일이 들어와 있나 — 화면에 '어느 파일이 언제' 를 적어 준다
        "revenue_file": _drev.info(div),
    }


# ============================================================
#  품목별 개발 일정 양식 올리기
# ============================================================
# 양식의 줄들을 등록된 모델에 붙여 본다
def _ds_plan(division_id: str, items: list, idx: dict) -> dict:
    data = _load_models()
    hit, miss = [], []
    for it in (items or []):
        pid = _df_find_project(it.get("project"), idx)
        proj = (data.get("projects") or {}).get(pid) or {} if pid else {}
        m = _ds_pick_model(proj.get("models") or [], it.get("part_number"))
        moved = ""
        if m is None:
            # 적힌 고객사에 없으면 사업부 전체에서 품번으로 찾는다.
            _pk, m = _ds_pick_in_division(data, division_id,
                                          it.get("part_number"), pid or "")
            if m is not None:
                pid, proj, moved = _pk, (data["projects"][_pk] or {}), _pk
        if m is None:
            miss.append({"row": it.get("row"), "project": it.get("project"),
                         "part_number": it.get("part_number"),
                         "why": ("프로젝트를 못 찾았습니다" if not pid
                                 else "그 프로젝트에 없는 품번입니다")})
            continue
        steps = it.get("steps") or []
        # 지금 적혀 있는데 새 파일에서 비어 있어 지워질 칸 (반영은 파일 그대로)
        _old = {str((x or {}).get("name") or ""): x
                for x in (m.get("process") or []) if isinstance(x, dict)}
        cleared = 0
        for _st in steps:
            _was = _old.get(_st.get("name") or "") or {}
            for _f in ("expected", "actual", "expected_note", "actual_note"):
                if str(_was.get(_f) or "").strip() and not _st.get(_f):
                    cleared += 1
        hit.append({
            "project_key": pid,
            "label": _display_project_label(pid),
            "part_number": it.get("part_number"),
            "name": m.get("name") or m.get("id"),
            "steps": [s.get("name") for s in steps],
            "plan": sum(1 for s in steps if s.get("expected")),
            "actual": sum(1 for s in steps if s.get("actual")),
            # 단계 이름이 바뀌는지 — 블룸은 13단계가 3단계로 바뀐다
            "before_steps": [str((x or {}).get("name") or "")
                             for x in (m.get("process") or [])],
            # 적힌 고객사가 아니라 다른 프로젝트에서 찾았으면 적어 둔다
            "moved_to": moved,
            "cleared": cleared,
        })
    return {"hit": hit, "miss": miss}


# 개발 일정 엑셀을 받아 연다 (원본은 보관함에 남긴다).
async def _ds_open(file: UploadFile, where: str):
    import io as _io
    import openpyxl as _ox
    raw = await _keep_upload(file, where=where)
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    try:
        return _ox.load_workbook(_io.BytesIO(raw), data_only=True, keep_links=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail="엑셀을 열지 못했습니다: %s" % e)


# 개발 일정 양식이 무엇을 바꾸는지 먼저 보여준다 ← admin v2 fv.onclick() · _devSend()
@app.post("/admin/divisions/{division_id}/dev-schedule/preview")
async def admin_dev_schedule_preview(
        division_id: str, file: UploadFile = File(...),
        _admin: int = Depends(get_admin_session)):
    import dev_schedule_import as _dsi
    wb = await _ds_open(file, "divisions/dev-schedule/preview")
    try:
        got = _dsi.parse_workbook(wb)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    plan = _ds_plan(division_id, got["items"], _df_owner_index(division_id))
    return {"ok": True, "preview": True, "division_id": division_id,
            "file_name": file.filename or "", "sheet": got["sheet"],
            "steps_max": got["steps_max"], "item_count": len(got["items"]),
            "hit": plan["hit"], "miss": plan["miss"],
            "warnings": got["warnings"]}


# 개발 일정 양식을 실제로 반영한다 ← admin v2 fv.onclick() · _devSend()
@app.post("/admin/divisions/{division_id}/dev-schedule/apply")
async def admin_dev_schedule_apply(
        division_id: str, file: UploadFile = File(...),
        _admin: int = Depends(get_admin_session)):
    import dev_schedule_import as _dsi
    wb = await _ds_open(file, "divisions/dev-schedule/apply")
    try:
        got = _dsi.parse_workbook(wb)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    idx = _df_owner_index(division_id)
    data = _load_models()
    applied, miss, step_changed = [], [], []
    warn_moved = []          # 적힌 고객사 말고 다른 프로젝트에서 찾은 줄
    for it in got["items"]:
        pid = _df_find_project(it.get("project"), idx)
        proj = (data.get("projects") or {}).get(pid) or {} if pid else {}
        m = _ds_pick_model(proj.get("models") or [],
                           it.get("part_number")) if pid else None
        if m is None:
            # 품번은 사실상 품목의 이름값을 한다 — 적힌 고객사에 없으면
            # 사업부 전체에서 찾는다 (딱 하나일 때만).
            _pk, m = _ds_pick_in_division(data, division_id,
                                          it.get("part_number"), pid or "")
            if m is not None:
                warn_moved.append({"row": it.get("row"),
                                   "project": it.get("project"),
                                   "part_number": it.get("part_number"),
                                   "found_in": _display_project_label(_pk)})
                pid, proj = _pk, (data["projects"][_pk] or {})
        if m is None:
            miss.append({"row": it.get("row"), "project": it.get("project"),
                         "part_number": it.get("part_number")})
            continue

        old = {str((x or {}).get("name") or ""): x
               for x in (m.get("process") or []) if isinstance(x, dict)}
        before = [str((x or {}).get("name") or "") for x in (m.get("process") or [])]
        names = [s.get("name") for s in (it.get("steps") or [])]
        if before != names:
            step_changed.append({"project_key": pid,
                                 "part_number": it.get("part_number"),
                                 "before": before, "after": names})

        was_final = bool(m.get("process")) and _process_step_done(m["process"][-1])
        proc = []
        for s in (it.get("steps") or []):
            nm = s.get("name") or ""
            # 옛 단계에서 이어받는 건 열쇠 · 묶음(틀)뿐이다. 날짜와 글자는
            # 새 파일 것만 쓴다 — 빈 칸이면 비운다.
            prev = old.get(nm) or {}
            row = {"key": prev.get("key") or _ds_key(nm),
                   "name": nm,
                   "group": prev.get("group") or "",
                   "expected": s.get("expected") or "",
                   "actual": s.get("actual") or "",
                   "status": ""}
            # 날짜가 아닌 글자도 같이 담는다 ('고객사 검토중' · 'PO 완료').
            # 날짜만 받던 때는 이런 칸이 소리 없이 사라졌다.
            for _f in ("expected_note", "actual_note"):
                row[_f] = s.get(_f) or ""
            # 양식 머리에 적힌 규칙 그대로 — "*완료되었으나 날짜 확인이 어려운 경우 '완료'로 작성" 실적 칸에 '완료' 라고 적혔으면 끝난 것으로 센다
            if (_note_says_done(row.get("actual_note"))
                    or _note_says_done(row.get("expected_note"))):
                row["status"] = "완료"
            proc.append(row)
        m["process"] = proc
        # 최종 승인이 처음 끝난 날을 적어 둔다. 실적 칸에 날짜 없이 '완료' 만
        # 적혀 오면 언제 끝났는지 알 길이 없어서, 1주일을 셀 기준이 없다
        # (_dev_final_day 참고).
        if proc and _process_step_done(proc[-1]):
            if not was_final or not m.get("final_done_seen"):
                m["final_done_seen"] = date.today().isoformat()
        else:
            m.pop("final_done_seen", None)
        # 빈 칸은 '안 적음' 이라 지우지 않는다. 한 번 적어 둔 담당이
        # 담당 칸을 비워 올린 다음 파일에 지워지면 안 된다.
        _own = str(it.get("owner") or "").strip()
        if _own:
            m["dev_owner"] = _own
        applied.append({"project_key": pid, "part_number": it.get("part_number"),
                        "name": m.get("name") or m.get("id"),
                        "steps": len(proc)})

    _save_models(data)
    print("[개발일정] %s '%s': %d품목 반영 · 단계 바뀜 %d · 못 찾음 %d"
          % (division_id, file.filename or "", len(applied),
             len(step_changed), len(miss)))
    return {"ok": True, "division_id": division_id,
            "file_name": file.filename or "", "sheet": got["sheet"],
            "steps_max": got["steps_max"], "item_count": len(got["items"]),
            # 몇 칸이 들어갔는지 숫자로 돌려준다. 전에는 통째로 버려도
            # '경고 0건' 이라 괜찮아 보였다 (Min: "엑셀에는 내용 다
            # 적혀져 있고 날짜도 작성 되어 있는데 왜 적용을 못 하는거야").
            "date_cells": got.get("date_cells", 0),
            "note_cells": got.get("note_cells", 0),
            "applied": applied, "step_changed": step_changed, "miss": miss,
            "moved": warn_moved,
            "warnings": got["warnings"]}


# 품번 한 칸 → 맞춰 볼 열쇠들.
def _pn_variants(t) -> set:
    import re as _re
    raw = str(t or "").strip()
    if not raw:
        return set()
    out = {_df_norm(raw)}
    head = _re.split(r"[(\[]", raw)[0]
    head = _re.sub(r"(?i)^\s*(part\s*(no|number)?|품번|파트\s*넘버)\s*[:：]?\s*",
                   "", head)
    out.add(_df_norm(head))
    m = _re.search(r"[(\[]([^)\]]+)[)\]]", raw)
    if m:
        out.add(_df_norm(m.group(1)))
    out.discard("")
    return out


# 개발 일정 양식 한 줄 → 등록된 모델.
def _ds_pick_model(models: list, pn: str):
    want = _pn_variants(pn)
    if not want:
        return None
    # -----------------------------------------------------------
    # 글자 그대로 — 지금까지 맞던 것은 그대로 맞아야 한다
    # -----------------------------------------------------------
    exact = _df_norm(pn)
    for m in models:
        for f in ("part_number", "id"):
            if _df_norm(m.get(f)) == exact:
                return m
    # -----------------------------------------------------------
    # 괄호를 가린 뒤 — 딱 하나일 때만
    # -----------------------------------------------------------
    hit = []
    for m in models:
        mine = set()
        for f in ("part_number", "id"):
            mine |= _pn_variants(m.get(f))
        if mine & want:
            hit.append(m)
    return hit[0] if len(hit) == 1 else None


# 그 사업부의 (프로젝트키, 프로젝트) 목록.
def _ds_div_projects(data: dict, division_id: str) -> list:
    out = []
    for pk, proj in (data.get("projects") or {}).items():
        try:
            if (_cl.derive_division_from_project(pk) or "") == division_id:
                out.append((pk, proj or {}))
        except Exception:
            continue
    return out


# 사업부 전체에서 품번으로 찾는다 → (프로젝트키, 모델) 또는 (None, None).
def _ds_pick_in_division(data: dict, division_id: str, pn: str, skip: str = ""):
    hit = []
    for pk, proj in _ds_div_projects(data, division_id):
        if pk == skip:
            continue
        m = _ds_pick_model(proj.get("models") or [], pn)
        if m is not None:
            hit.append((pk, m))
    if len(hit) == 1:
        return hit[0]
    return None, None


# 보여 줄 때만, 날짜가 없는 칸에 적혀 있던 글자를 채워 넣는다
def _ds_show_notes(proc: list) -> list:
    import re as _re
    out = []
    for st in (proc or []):
        st = dict(st or {})
        for f in ("expected", "actual"):
            if not str(st.get(f) or "").strip():
                note = str(st.get(f + "_note") or "").strip()
                if note:
                    st[f] = note
        # 끝난 단계인데 실적에 날짜가 없으면 실적 자리에 '완료' 라고 쓴다
        if st.get("status") == "완료" \
                and not _re.search(r"\d{4}-\d{1,2}-\d{1,2}", str(st.get("actual") or "")):
            st["actual"] = "완료"
        out.append(st)
    return out


# 단계 이름 → 저장용 열쇠.
def _ds_key(name: str) -> str:
    import hashlib as _hl
    import re as _re
    raw = str(name or "")
    t = _re.sub(r"[^0-9A-Za-z]+", "_", raw).strip("_").lower()
    plain = _re.sub(r"[^0-9A-Za-z]+", "", raw)
    if plain and len(plain) == len(_re.sub(r"\s+", "", raw)):
        return t                      # 영문·숫자만 있는 이름
    h = _hl.sha1(raw.encode("utf-8")).hexdigest()[:6]
    return (t + "_" + h) if t else ("s_" + h)


# ============================================================
#  사업부 매출 파일 올리기
# ============================================================
# 매출 파일 엑셀을 받아 연다 (원본은 보관함에 남긴다).
async def _rv_file_open(file: UploadFile, where: str = ""):
    import io as _io
    import openpyxl as _ox
    # 원본을 보관함에 한 벌 남긴다. 숫자가 이상할 때 '그때 올린 그 파일'
    # 을 다시 열어 볼 수 있어야 한다 — 매출은 특히 그렇다.
    raw = await _keep_upload(file, where=where)
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    try:
        return _ox.load_workbook(_io.BytesIO(raw), data_only=True, keep_links=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail="엑셀을 열지 못했습니다: %s" % e)


# 미리보기·반영이 같은 글자를 쓰게 한 자리에서 만든다
def _rv_file_view(got: dict) -> dict:
    months = []
    for k, v in sorted((got.get("months") or {}).items()):
        months.append({"month": k, "krw": v.get("krw"),
                       "usd": v.get("usd"), "fx": v.get("fx")})
    # 고객사별로 묶어 보여 준다 — 남의 사업부 줄이 섞여 있으면 여기서 보인다
    by_cust = {}
    for r in (got.get("rows") or []):
        by_cust.setdefault(r.get("customer") or "", 0)
        by_cust[r.get("customer") or ""] += 1
    for m in months:
        m["plan"] = (got.get("plan_months") or {}).get(m["month"])
    cl = got.get("customers") or [k for k, _v in sorted(by_cust.items())]
    return {"year": got.get("year"), "sheet": got.get("sheet"),
            "shape": got.get("shape") or "", "fx_weeks": got.get("fx_weeks"),
            "plan_kind": got.get("plan_kind") or "",
            "weeks": len(got.get("weeks") or {}),
            "months": months,
            "customers": [{"name": k, "rows": by_cust.get(k, 0)} for k in cl],
            "warnings": got.get("warnings") or []}


# 매출 파일이 무엇을 바꾸는지 먼저 보여준다 ← admin v2 inp.onchange()
@app.post("/admin/divisions/{division_id}/revenue-file/preview")
async def admin_division_revenue_file_preview(
        division_id: str, file: UploadFile = File(...),
        _admin: int = Depends(get_admin_session)):
    import revenue_file_import as _rfi
    wb = await _rv_file_open(file, "divisions/revenue-file/preview")
    try:
        got = _rfi.parse_workbook(wb)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    out = _rv_file_view(got)
    out.update({"ok": True, "division_id": division_id,
                "file_name": file.filename or "", "preview": True})
    return out


# 매출 파일을 실제로 담는다. 그 해만 갈아 끼운다 ← admin v2 go.onclick()
@app.post("/admin/divisions/{division_id}/revenue-file/apply")
async def admin_division_revenue_file_apply(
        division_id: str, file: UploadFile = File(...),
        _admin: int = Depends(get_admin_session)):
    import revenue_file_import as _rfi
    wb = await _rv_file_open(file, "divisions/revenue-file/apply")
    try:
        got = _rfi.parse_workbook(wb)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    saved = _drev.put(division_id, got.get("year"), got.get("months") or {},
                      got.get("rows") or [], file.filename or "",
                      plan_months=got.get("plan_months") or {},
                      weeks=got.get("weeks") or {},
                      shape=got.get("shape") or "",
                      detail=got.get("detail") or {})
    out = _rv_file_view(got)
    out.update({"ok": True, "division_id": division_id,
                "file_name": file.filename or "", "saved": saved.get("saved")})
    print("[사업부매출] %s '%s': %d개 달 담음"
          % (division_id, file.filename or "", len(saved.get("saved") or [])))
    return out


# 매출 파일로 들어온 사업부 매출 보기 ← admin v2 renderRevenuePage()
@app.get("/admin/division/revenue")
def admin_division_revenue(div: str, month: str = None,
                           _admin: int = Depends(get_admin_session)):
    month = _check_month(month)
    div = (div or "").strip()
    if not div:
        raise HTTPException(status_code=400, detail="사업부를 지정해 주세요.")
    return _div_revenue_view(div, month)


# ============================================================
#  사라진 모델 되살리기
# ============================================================
# 모델 저장이 '전체 교체' 라, 화면이 목록을 덜 들고 저장하면 나머지가 통째로 지워진다
RESTORE_DIR = BASE_DIR / "restore"

# ============================================================
#  백업 되살리기 · 특근
# ============================================================
def _restore_file(name: str):
    safe = os.path.basename(str(name or "").strip())
    if not safe or not safe.endswith(".json"):
        safe = (safe or "") + ".json"
    path = RESTORE_DIR / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="그런 복구 파일이 없습니다: %s" % safe)
    with open(path, "r", encoding="utf-8") as f:
        return safe, json.load(f)


# backend/restore/ 에 있는 복구 파일 목록.
@app.get("/admin/models/restore-files")
def admin_models_restore_files(_admin: int = Depends(get_admin_session)):
    out = []
    if RESTORE_DIR.exists():
        for p in sorted(RESTORE_DIR.glob("*.json")):
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
                shape = {k: len((v or {}).get("models") or [])
                         for k, v in (doc.get("projects") or {}).items()}
                out.append({"name": p.name, "source": doc.get("source", ""),
                            "at": doc.get("at", ""), "shape": shape,
                            "total": sum(shape.values())})
            except Exception as e:
                out.append({"name": p.name, "error": str(e)})
    return {"ok": True, "files": out}


# 복구 파일에서 '지금 없는 모델만' 더한다
@app.post("/admin/models/restore-missing")
def admin_models_restore_missing(payload: dict = Body(...),
                                 _admin: int = Depends(get_admin_session)):
    name, doc = _restore_file((payload or {}).get("name"))
    want = [str(k).strip() for k in ((payload or {}).get("projects") or []) if str(k).strip()]
    mode = str((payload or {}).get("mode") or "preview").strip()

    fill = bool((payload or {}).get("fill_empty"))

    data = _load_models()
    projects = data.setdefault("projects", {})
    report, total, filled = {}, 0, 0
    for key, block in (doc.get("projects") or {}).items():
        if want and key not in want:
            continue
        src = [m for m in ((block or {}).get("models") or []) if isinstance(m, dict)]
        if not src:
            continue
        proj = projects.setdefault(key, {})
        cur = [m for m in (proj.get("models") or []) if isinstance(m, dict)]
        have = {str(m.get("id") or "").strip() for m in cur}

        # 살아남은 모델의 '비어 있는 칸' 만 채운다. 유형이 지워지면 주차
        # 보드가 그 행을 못 찾아 전부 0 으로 뜬다 — 엔클로저가 그랬다.
        # 값이 들어 있는 칸은 지금 것이 최신이므로 건드리지 않는다.
        fills = []
        if fill:
            src_map = {str(m.get("id") or "").strip(): m for m in src}
            for m in cur:
                o = src_map.get(str(m.get("id") or "").strip())
                if not o:
                    continue
                got = []
                if (o.get("dev_type") or "") and not (m.get("dev_type") or ""):
                    m["dev_type"] = o["dev_type"]
                    got.append("dev_type")
                if (o.get("weekly_plan") or {}) and not (m.get("weekly_plan") or {}):
                    m["weekly_plan"] = o["weekly_plan"]
                    got.append("weekly_plan")
                if (o.get("part_number") or "") and not (m.get("part_number") or ""):
                    m["part_number"] = o["part_number"]
                    got.append("part_number")
                if got:
                    fills.append({"id": m.get("id"), "fields": got})
        add = [m for m in src if str(m.get("id") or "").strip()
               and str(m.get("id") or "").strip() not in have]
        if not add and not fills:
            continue
        if fills:
            filled += len(fills)
        report[key] = {"before": len(cur), "add": [str(m.get("id")) for m in add],
                       "after": len(cur) + len(add), "filled": fills}
        total += len(add)
        if mode == "commit":
            proj["models"] = cur + add

    out = {"ok": True, "file": name, "mode": mode,
           "total": total, "filled": filled, "projects": report}
    if mode != "commit":
        return out
    if not total and not filled:
        out["saved"] = False
        return out
    _save_models(data)
    print("[restore-missing] %s → %s (추가 %d종 · 칸 채움 %d종)"
          % (name, ", ".join(report), total, filled))
    out["saved"] = True
    return out

# ============================================================
#  전사 사업부별 잔업·특근
# ============================================================
# 주 단위다. 한 주에 사업부 16곳, 각 곳이 요일 7줄.
import overtime as _ot
import overtime_import as _otim

OVERTIME_FILE = DATA_DIR / "overtime.json"

# ============================================================
#  특근
# ============================================================
def _ot_load():
    return _ot.load(OVERTIME_FILE)


# 전사 화면 — 주차 하나, 지표 하나, 범위 하나 ← 앱 overtime_service.dart fetchWeek()
@app.get("/overtime/week")
def overtime_week(w: str = "", kind: str = "overtime", scope: str = "total"):
    return _ot.for_app(_ot_load(), w, kind, scope)


# 사업부 하나 — 요일별까지 ← 앱 overtime_service.dart fetchDivision()
@app.get("/overtime/week/{div}")
def overtime_division(div: str, w: str = ""):
    out = _ot.for_division(_ot_load(), div, w)
    if not out.get("has_data"):
        raise HTTPException(status_code=404, detail="그 주에 그 사업부가 없습니다.")
    return out


# 특근 자료 보기 ← admin v2 save() · load()
@app.get("/admin/overtime")
def admin_overtime_get(w: str = "", _admin: int = Depends(get_admin_session)):
    return _ot.for_admin(_ot_load(), w)


# 주차 하나를 통째로 갈아끼운다 — 다른 주는 건드리지 않는다 ← admin v2 save() · load()
@app.put("/admin/overtime")
def admin_overtime_put(payload: dict = Body(...),
                       _admin: int = Depends(get_admin_session)):
    wk = _ot.week_key((payload or {}).get("week"))
    if not wk:
        raise HTTPException(status_code=400, detail="주차는 2026-W39 처럼 적어 주세요.")
    data = _ot_load()
    before = set(((data.get("weeks") or {}).get(wk) or {}).get("divisions") or {})
    after = {_ot.div_key(k) for k in ((payload or {}).get("divisions") or {})}
    gone = sorted(before - after)
    if gone and not payload.get("allow_delete"):
        raise HTTPException(status_code=409, detail=(
            "이 저장은 %d곳을 지웁니다 (%s%s). 화면이 사업부를 다 들고 있는지 "
            "확인해 주세요. 정말 지우려면 allow_delete 를 같이 보내세요."
            % (len(gone), ", ".join(gone[:5]), " 외" if len(gone) > 5 else "")))
    saved = _ot.save(OVERTIME_FILE, _ot.put_week(data, wk, payload or {}))
    print("[overtime] 저장 %s (%d곳)" % (wk, len(after)))
    return _ot.for_admin(saved, wk)


# 취합 엑셀 올리기. preview 로 먼저 보여 주고 commit 이어야 저장한다 ← admin v2 upload()
@app.post("/admin/overtime/import-xlsx")
async def admin_overtime_import(
        file: UploadFile = File(...),
        year: Optional[int] = Form(None),
        week: Optional[str] = Form(None),
        mode: str = Form("preview"),
        _admin: int = Depends(get_admin_session)):
    name = file.filename or ""
    if not name.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="xlsx 파일을 올려 주세요.")
    raw = await _keep_upload(file, "/admin/overtime/import-xlsx", "")
    try:
        parsed = _otim.parse_workbook(raw, year=year, week=week)
    except Exception as e:
        raise HTTPException(status_code=400, detail="엑셀을 읽지 못했습니다: %s" % e)

    wk = _ot.week_key(parsed["week"])
    if not wk:
        raise HTTPException(status_code=400, detail="주차를 알 수 없습니다: %s"
                            % parsed.get("week"))
    data = _ot_load()
    payload = {"range": parsed.get("range", ""), "source": name,
               "divisions": parsed["divisions"], "order": parsed["order"],
               "issues": parsed.get("issues") or []}
    merged = _ot.put_week(data, wk, payload)

    out = {"file": name, "week": wk, "range": parsed.get("range", ""),
           "mode": mode, "sheets": parsed.get("sheets") or [],
           "divisions": parsed["order"],
           "read": parsed.get("read") or [],
           "warnings": parsed.get("warnings") or [],
           "issues": parsed.get("issues") or [],
           "replaced": wk in (data.get("weeks") or {}),
           "kept": sorted(x for x in (data.get("weeks") or {}) if x != wk),
           "preview": _ot.for_app(merged, wk)}
    if mode != "commit":
        return out

    saved = _ot.save(OVERTIME_FILE, merged)
    print("[overtime] %s ← %s (%d개 사업부)"
          % (wk, name, len(parsed["divisions"])))
    out["saved"] = True
    out["updated_at"] = saved.get("updated_at", "")
    out["state"] = _ot.for_admin(saved, wk)
    return out


# ============================================================
#  일일 백업
# ============================================================
# 요청이 들어올 때 '오늘 것이 있나' 를 보고 없으면 만든다
import backups as _bk

# ============================================================
#  자동 백업
# ============================================================
# 모든 요청이 지나가는 문 (미들웨어)
@app.middleware("http")
async def _daily_backup_mw(request, call_next):
    # 백업이 실패해도 요청은 그대로 흘러가야 한다. 백업 때문에 앱이
    # 멈추는 쪽이 백업이 하루 빠지는 쪽보다 나쁘다.
    try:
        if request.method == "GET" and not request.url.path.startswith(
                ("/static", "/slides", "/slide_images", "/cropped", "/note_photos")):
            await _run_in_threadpool_safe(_bk.ensure_today, DATA_DIR)
    except Exception as e:
        print(f"[backup] 건너뜀: {e}")
    return await call_next(request)


# 오래 걸리는 일을 별도 일꾼에서 돌린다 (서버가 멈추지 않게).
async def _run_in_threadpool_safe(fn, *a):
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(fn, *a)


# 백업 목록 + 지금 보관 계획. name 을 주면 그 안을 들여다본다 ← admin v2 load()
@app.get("/admin/backups")
def admin_backups(name: str = "", _admin: int = Depends(get_admin_session)):
    rows = _bk.list_backups(DATA_DIR)
    out = {"ok": True,
           "backups": rows,
           "usage": _bk.usage(DATA_DIR),
           "has_today": _bk.has_today(DATA_DIR),
           "policy": {"daily_days": _bk.DAILY_KEEP_DAYS,
                      "weekly_weeks": _bk.WEEKLY_KEEP_WEEKS,
                      "monthly_months": _bk.MONTHLY_KEEP_MONTHS,
                      "min_keep": _bk.MIN_KEEP},
           "plan": _bk.plan_prune([r["name"] for r in rows]),
           "sources": [p.name for p in _bk.source_files(DATA_DIR)]}
    if name:
        try:
            out["peek"] = _bk.peek(DATA_DIR, name)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="그런 백업이 없습니다")
    return out


# 지금 한 벌 뜬다. 오늘 것이 있으면 그 위에 덮어쓴다 ← admin v2 run.onclick()
@app.post("/admin/backups/run")
def admin_backups_run(payload: dict = Body(default=None),
                      _admin: int = Depends(get_admin_session)):
    label = str((payload or {}).get("label") or "")[:24]
    res = _bk.snapshot(DATA_DIR, label=label)
    if not res.get("ok"):
        raise HTTPException(status_code=500,
                            detail="백업하지 못했습니다: %s" % res.get("reason"))
    res["prune"] = _bk.prune(DATA_DIR)
    res["assets"] = _bk.ensure_assets_weekly(DATA_DIR)
    res["usage"] = _bk.usage(DATA_DIR)
    return res


# 보관 기간 지난 것 정리. dry_run 이면 무엇을 지울지만 알려준다 ← admin v2 pr.onclick()
@app.post("/admin/backups/prune")
def admin_backups_prune(payload: dict = Body(default=None),
                        _admin: int = Depends(get_admin_session)):
    dry = bool((payload or {}).get("dry_run"))
    return {"ok": True, **_bk.prune(DATA_DIR, dry_run=dry), "dry_run": dry}


# 되돌리기. payload = {name, files?: [파일명...]} ← admin v2 el.onclick()
@app.post("/admin/backups/restore")
def admin_backups_restore(payload: dict,
                          _admin: int = Depends(get_admin_session)):
    name = str((payload or {}).get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="백업 이름이 필요합니다")
    only = [str(x) for x in ((payload or {}).get("files") or []) if str(x).strip()]
    try:
        res = _bk.restore(DATA_DIR, name, only=only or None)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="그런 백업이 없습니다")
    except Exception as e:
        raise HTTPException(status_code=500, detail="되돌리지 못했습니다: %s" % e)
    return res


# 백업 파일 내려받기. 서버 밖에도 한 벌 두고 싶을 때 ← admin v2 detail()
@app.get("/admin/backups/download")
def admin_backups_download(name: str, _admin: int = Depends(get_admin_session)):
    from fastapi.responses import FileResponse
    import os as _os
    safe = _os.path.basename(name)
    p = _bk.backups_dir(DATA_DIR) / safe
    if not p.exists() or not p.is_file() or not safe.endswith(".tar.gz"):
        raise HTTPException(status_code=404, detail="그런 백업이 없습니다")
    return FileResponse(str(p), media_type="application/gzip", filename=safe)


# ============================================================
#  주차별 계획·실적 양식 내려받기
# ============================================================
# 주차는 반드시 week_calendar 에서 받는다
import weekly_template as _wt

# ============================================================
#  엑셀 양식 내려받기 (주차 · 계획 · 블룸)
# ============================================================
# 그 프로젝트의 주차별 계획·실적 양식.
@app.get("/admin/projects/{project_key}/weekly-template")
def admin_weekly_template(project_key: str, month: str = "", months: int = 1,
                          _admin: int = Depends(get_admin_session)):
    import datetime as _dt
    from urllib.parse import quote

    key = _model_key_alias((project_key or "").strip())
    if not key:
        raise HTTPException(status_code=400, detail="사업부를 지정해 주세요.")

    base = (month or "").strip() or _dt.date.today().strftime("%Y-%m")
    try:
        y, m = int(base[:4]), int(base[5:7])
        if not (1 <= m <= 12):
            raise ValueError
    except Exception:
        raise HTTPException(status_code=400, detail="달을 YYYY-MM 으로 적어 주세요.")

    n = max(1, min(int(months or 1), 6))
    sheets = []
    for i in range(n):
        yy, mm = y + (m - 1 + i) // 12, (m - 1 + i) % 12 + 1
        mon = "%04d-%02d" % (yy, mm)
        wks = _get_month_weeks(mon)        # ← 보드와 같은 달력을 쓴다
        if wks:
            sheets.append({"month": mon, "weeks": wks})
    if not sheets:
        raise HTTPException(status_code=400, detail="그 달의 주차를 계산하지 못했습니다.")

    proj = (_load_models().get("projects") or {}).get(key) or {}
    models = [m for m in (proj.get("models") or []) if isinstance(m, dict)]
    try:
        label = _display_project_label(key)
    except Exception:
        label = key

    # 서로 구분이 안 되는 줄이 있으면 로그에 남긴다. 파트넘버도 모델명도
    # 같은 줄이 여럿이면 올렸을 때 어느 줄의 숫자인지 알 수 없다.
    dups = _wt.duplicate_rows(models)
    if dups:
        print(f"[weekly-template] {key}: 구분 안 되는 줄 {len(dups)}개 — "
              + ", ".join(str(d.get('name')) for d in dups[:5]))

    # 미달 사유도 같이 — '문제' 로 적힌 것만. '참고' 는 미달 사유가 아니라서
    # 그 칸에 넣어 보내면 다시 올릴 때 참고가 미달 사유로 바뀐다.
    for s in sheets:
        s["notes"] = {w: r.get("text") or ""
                      for w, r in _week_reasons_of(proj, s["month"]).items()
                      if (r.get("kind") or "") != "참고" and (r.get("text") or "").strip()}

    # 숫자를 채워서 내려준다. 빈 양식을 따로 두지 않는 이유 —
    #   · 숫자가 없는 프로젝트는 채워도 비어 있다
    #   · 숫자가 있는 프로젝트에서 빈 양식은 '지난 주 실적이 뭐였나' 를
    #     보드에서 따로 찾게 만든다
    #   · 받은 파일에 이번 주만 적어 그대로 올리면 되니 손이 덜 간다
    data = _wt.build_weekly_template(label, sheets=sheets, models=models,
                                     filled=True)
    fname = "%s_주차별계획_%s.xlsx" % (label or key, sheets[0]["month"])
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f"attachment; filename=weekly_template.xlsx; "
                 f"filename*=UTF-8''{quote(fname)}"})


# ============================================================
#  연간 내보내기
# ============================================================
# 받는 양식과 모양이 다르다. 받는 쪽은 한 달이 한 시트(세로로 길다),
# 이건 한 해가 한 시트(가로로 길다)다. 한 해를 한 장에 놓고 보려고
# 쓰던 파일이라 그 모양을 그대로 따라간다.
import plan_export as _pex
import plan_form as _pfm


# 작성용 양식 — 한 해 한 장, 고른 달만 주차 칸이 열린다 ← admin v2 el.onclick()
@app.get("/admin/projects/{project_key}/plan-form")
def admin_plan_form(project_key: str, month: str = "",
                    _admin: int = Depends(get_admin_session)):
    import datetime as _dt
    from urllib.parse import quote

    key = _model_key_alias((project_key or "").strip())
    if not key:
        raise HTTPException(status_code=400, detail="사업부를 지정해 주세요.")

    base = (month or "").strip() or _dt.date.today().strftime("%Y-%m")
    try:
        y, m = int(base[:4]), int(base[5:7])
        if not (1 <= m <= 12):
            raise ValueError
    except Exception:
        raise HTTPException(status_code=400, detail="달을 YYYY-MM 으로 적어 주세요.")
    mon = "%04d-%02d" % (y, m)
    if not _get_month_weeks(mon):
        raise HTTPException(status_code=400, detail="그 달의 주차를 계산하지 못했습니다.")

    proj = (_load_models().get("projects") or {}).get(key) or {}
    models = [x for x in (proj.get("models") or []) if isinstance(x, dict)]
    try:
        label = _display_project_label(key)
    except Exception:
        label = key

    dups = _wt.duplicate_rows(models)
    if dups:
        print(f"[plan-form] {key}: 구분 안 되는 줄 {len(dups)}개 — "
              + ", ".join(str(d.get('name')) for d in dups[:5]))

    # 미달 사유도 같이 — 열두 달 전부. 접힌 달을 펴서 고칠 수 있으니
    # 그 달 사유도 같이 보여야 한다. '참고' 는 미달 사유가 아니라서 뺀다.
    notes = {}
    for _i in range(1, 13):
        _ym = "%04d-%02d" % (y, _i)
        _got = {w: r.get("text") or ""
                for w, r in _week_reasons_of(proj, _ym).items()
                if (r.get("kind") or "") != "참고" and (r.get("text") or "").strip()}
        if _got:
            notes[_ym] = _got

    # 프로젝트 현황도 같이 싣는다. 받는 사람이 지금 뭐라고 적혀 있는지
    # 보고 고칠 수 있어야 한다
    data = _pfm.build_year_form(label, y, mon, models, notes=notes,
                                status_note=str(proj.get("status_note") or ""),
                                hold=_project_hold(proj))
    fname = "%s_작성용_%s.xlsx" % (label or key, mon)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f"attachment; filename=plan_form.xlsx; "
                 f"filename*=UTF-8''{quote(fname)}"})


# 그 해에 주차 숫자가 적힌 달. 고르는 창의 기본 체크에 쓴다 ← admin v2 back.onclick() · done()
@app.get("/admin/projects/{project_key}/plan-export/months")
def admin_plan_export_months(project_key: str, year: int = 0,
                             _admin: int = Depends(get_admin_session)):
    import datetime as _dt

    key = _model_key_alias((project_key or "").strip())
    y = int(year or 0) or _dt.date.today().year
    proj = (_load_models().get("projects") or {}).get(key) or {}
    models = [m for m in (proj.get("models") or []) if isinstance(m, dict)]
    return {"ok": True, "year": y,
            "has": _pex.months_with_weeks(models, y)}


# 그 프로젝트 한 해치 주차별 계획·실적 엑셀 ← admin v2 onclick()
@app.get("/admin/projects/{project_key}/plan-export")
def admin_plan_export(project_key: str, year: int = 0, months: str = None,
                      _admin: int = Depends(get_admin_session)):
    import datetime as _dt
    from urllib.parse import quote

    key = _model_key_alias((project_key or "").strip())
    if not key:
        raise HTTPException(status_code=400, detail="사업부를 지정해 주세요.")
    y = int(year or 0) or _dt.date.today().year
    if not (2000 <= y <= 2100):
        raise HTTPException(status_code=400, detail="연도를 네 자리로 적어 주세요.")

    proj = (_load_models().get("projects") or {}).get(key) or {}
    # 등록된 순서 그대로 넘긴다 — plan_export 가 유형으로만 묶고 순서는 안 바꾼다
    models = [m for m in (proj.get("models") or []) if isinstance(m, dict)]
    try:
        label = _display_project_label(key)
    except Exception:
        label = key

    # months 를 아예 안 보내면 자동(숫자 있는 달). 비워서 보내면 전부 접는다.
    if months is None:
        want = None
    else:
        want = [x.strip() for x in months.split(",") if x.strip()]
    data = _pex.build_year_export(label, y, models,
                                  sheet_name=key.replace("-", "_").upper(),
                                  expand=want)
    fname = "%s_%d_주차별계획.xlsx" % (label or key, y)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f"attachment; filename=plan_export.xlsx; "
                 f"filename*=UTF-8''{quote(fname)}"})


# ============================================================
#  블룸 일 보고 — 빈 양식 내려주기
# ============================================================
# 기준은 사람이 쓰던 '블룸_보고자료_..._ver4_1.xlsx' 의 '10월 보고자료' 시트다
import bloom_template as _bt


# 블룸 일 보고 자료 빈 양식 (품목 칸은 채워서) ← admin v2 fm.onclick()
@app.get("/admin/projects/{project_key}/bloom-template")
def admin_bloom_template(project_key: str, month: str = "",
                         _admin: int = Depends(get_admin_session)):
    import datetime as _dt
    from urllib.parse import quote

    import bloom_daily_import as _bd

    key = _model_key_alias((project_key or "").strip())
    try:
        proj = _cl.get_project(key) or {}
    except Exception:
        proj = {}
    if str(proj.get("division_id") or "") != "bloom":
        raise HTTPException(status_code=400,
                            detail="블룸 양식은 블룸 프로젝트에서만 받습니다.")

    base = (month or "").strip() or _dt.date.today().strftime("%Y-%m")
    try:
        y, m = int(base[:4]), int(base[5:7])
        if not (1 <= m <= 12):
            raise ValueError
    except Exception:
        raise HTTPException(status_code=400, detail="달을 YYYY-MM 으로 적어 주세요.")
    base = "%04d-%02d" % (y, m)

    items, seen = [], set()

    def _add(nm):
        nm = str(nm or "").strip()
        if not nm:
            return
        k = _norm_label(_bd.clean_item(nm))
        if not k or k in seen:
            return
        seen.add(k)
        items.append(nm)

    try:
        for p in (_cl.get_projects(division_id="bloom", visible_only=False) or []):
            _add(p.get("bloom_item"))
    except Exception:
        pass
    try:
        _board, _ = _bloom_board_for(_BLOOM_STORE)
        for it in ((_board or {}).get("items") or []):
            if isinstance(it, dict):
                _add(it.get("item"))
    except Exception:
        pass

    data = _bt.build_bloom_template(base, items=items)
    fname = "블룸_일보고_양식_%s.xlsx" % base
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f"attachment; filename=bloom_template.xlsx; "
                 f"filename*=UTF-8''{quote(fname)}"})


# ============================================================
#  앱 오프라인용 묶음 — 사업부 하나의 화면 자료를 한 번에
# ============================================================
# 앱이 프로젝트마다 일곱 번씩 따로 받으면 150곳 × 7 = 1,000번이 넘어서,
# 다 받기 전에 오프라인이 되면 처음 여는 프로젝트가 비었다. 사업부마다 한 번에
# 묶어 주면 여덟 번이면 끝난다. 앱은 주소별로 쪼개 저장한다 (offline_prefetch.dart).
# 각 칸은 그 주소를 직접 부른 것과 같은 값이다 — 실패한 칸은 빠진다.
def _bundle_value(x):
    # 주소 함수가 Response 를 돌려주는 경우(JSONResponse)도 값으로 꺼낸다
    if isinstance(x, Response):
        try:
            return json.loads(x.body)
        except Exception:
            return None
    return x


# 사업부 하나의 오프라인 묶음 ← 앱 offline_prefetch.dart
@app.get("/divisions/{division_id}/offline-bundle")
def get_division_offline_bundle(division_id: str, month: str = ""):
    import gzip as _gzip
    month = (month or "").strip() or datetime.now().strftime("%Y-%m")
    out = {}
    q = "?month=" + month

    def _put(path, fn, *args, **kw):
        try:
            v = _bundle_value(fn(*args, **kw))
        except Exception:
            return                       # 그 칸만 빠진다 (주소를 부를 때도 실패했을 것)
        if v is not None:
            out[path] = v

    for p in _cl.get_projects(division_id, visible_only=True):
        pk = p.get("id")
        if not pk:
            continue
        base = "/projects/%s" % pk
        _put(base + "/models/detail", get_project_models_detail, pk)
        _put(base + "/models", get_project_models, pk)
        _put(base + "/weekly-plan", get_weekly_plan, pk)
        _put(base + "/issues/summary", get_issues_summary, pk)
        _put(base + "/process-steps", get_process_steps, pk)
        _put(base + "/weekly-board" + q, get_weekly_board, pk, month)
        _put(base + "/weekly-revenue" + q, get_weekly_revenue, pk, month)
    # 일 보고 사업부(블룸 · ESS)는 사업부 보드도
    _put("/divisions/%s/daily-view" % division_id, get_division_daily_view, division_id, "", "")
    _put("/divisions/%s/daily-view%s" % (division_id, q), get_division_daily_view, division_id, month, "")
    body = json.dumps({"division_id": division_id, "month": month, "urls": out},
                      ensure_ascii=False, default=str).encode("utf-8")
    # 묶음이 커서(반도체 1MB 안팎) 줄여 보낸다. 앱의 http 는 gzip 을 알아서 푼다.
    return Response(content=_gzip.compress(body), media_type="application/json",
                    headers={"Content-Encoding": "gzip"})
