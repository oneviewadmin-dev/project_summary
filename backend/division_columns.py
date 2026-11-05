# -*- coding: utf-8 -*-
# ============================================================
#  사업부마다 양식의 열 구성이 다르다
# ============================================================
from __future__ import annotations

import json
from pathlib import Path

# ============================================================
#  열 하나하나가 화면에서 어떻게 보이나
# ============================================================
#    key     : 코드가 쓰는 이름 (파서가 돌려주는 값의 열쇠와 같다)
#    label   : 표 머리글
#    align   : 'left' | 'right'
#    width   : 화면에서 잡아 둘 폭 (px). None 이면 남는 자리를 다 쓴다
COLUMN_SPEC = {
    "owner":        {"label": "고객사",    "align": "left",  "width": 110},
    "name":         {"label": "품목",      "align": "left",  "width": None},
    "part_number":  {"label": "파트넘버",  "align": "left",  "width": None},
    "group":        {"label": "구분",      "align": "left",  "width": 74},
    "dev_type":     {"label": "분류",      "align": "left",  "width": 84},
    "price":        {"label": "판가",      "align": "right", "width": 104},
    "material_cost":{"label": "재료비",    "align": "right", "width": 96},
    "year_qty":     {"label": "연간수량",  "align": "right", "width": 88},
    "po_qty":       {"label": "PO수량 · 변동", "align": "right", "width": 124},
    "shipped_qty":  {"label": "실적수량",  "align": "right", "width": 92},
    "note":         {"label": "비고",      "align": "left",  "width": 150},
    # 납기 — DUE_COLS 에 적힌 사업부만
    "due_date":     {"label": "고객 요청 납기일", "align": "left", "width": 104},
    "due_revised":  {"label": "출하 변경일 (고객 승인)", "align": "left", "width": 116},
    "made_date":    {"label": "제작 완료일", "align": "left", "width": 96},
}

# ============================================================
#  납기 칸을 쓰는 사업부
# ============================================================
# 사업부 양식(품목정보)의 실적수량 오른쪽에 날짜 세 칸을 붙인다
DUE_COLS = {
    "pcb": ["due_date", "due_revised", "made_date"],
}


def due_cols(division_id: str) -> list:
    return list(DUE_COLS.get(str(division_id or "").strip().lower(), []))


# ============================================================
#  고객사 묶음 — 앱 목록을 국내 / 해외로 나눈다
# ============================================================
# Min: "고객사 매출 기여순으로 하지 말고 국내/해외로 나누고 해외 같은 경우에
#      Lam, 아리스타, 기타로 나눠줘" → "최대한 앱 배포 없이 픽스 하려고 한다"
#
# 앱은 /divisions 가 보내 주는 대로만 묶는다. 고객사를 옮기거나 묶음을
# 더하려면 **여기만** 고치고 서버를 배포하면 된다 (앱은 그대로).
#
#   order  묶음 순서 [큰 묶음, 작은 묶음]. 작은 묶음이 없으면 ''.
#   rules  위에서부터 맞는 첫 줄. 키가 '_' 로 끝나면 접두사
#          (pcb_lam_ → 새 LAM 고객사도 저절로 Lam).
#   else   아무 줄에도 안 맞는 고객사
CUSTOMER_GROUPS = {
    "pcb": {
        "order": [["국내", ""], ["해외", "Lam"], ["해외", "아리스타"], ["해외", "기타"]],
        # 처음 한 번 자료에 옮겨 적을 때만 쓰는 옛 규칙 (seed_group)
        "seed": {
            "rules": [
                (["해외", "기타"], ["pcb_kaynes_technology", "pcb_kumho_india", "pcb_vvdn_tech",
                                  "pcb_motherson_marelli", "pcb_unominda", "pcb_cci_antenna"]),
            ],
            "else": ["국내", ""],
        },
        # 양식 품목정보에 '국내/해외' 칸을 둔다
        "excel_region": True,
        "title": "국내 / 해외",
    },
    # -----------------------------------------------------------
    # 네트워크 — 국내 / 해외
    # -----------------------------------------------------------
    # 정본은 양식 품목정보의 '국내/해외' 칸이다 (PCB 와 같다).
    "network": {
        "order": [["국내", ""], ["해외", ""]],
        "seed": {"else": ["국내", ""], "by_word": [(w, ["해외", ""]) for w in (
            "VN", "VIETNAM", "HA NAM", "INDIA", "CHINA", "MEXICO", "FINLAND", "USA",
            "JAPAN", "NOKIA", "ARISTOCRAT", "WATCH GUARD", "WATCHGUARD", "AVIGILON",
            "SANMINA",
            # Min: "ericsson, PORTABLE WINCH, WAVE TECH은 해외 아니야?"
            "ERICSSON", "PORTABLE WINCH", "WAVE TECH")]},
        "excel_region": True,
        "title": "국내 / 해외",
    },
    # -----------------------------------------------------------
    # 아리스타 — 프로젝트를 종류로
    # -----------------------------------------------------------
    # Min: "아리스타는 렉, 시트메탈, hoover table, cdu...말고 또 있나? 일단 그렇게 나눠줘"
    #
    # 양식의 '구분 1'(모델 dev_type: 렉 · 샷시 · 캐스팅 · 테이블 · 하드웨어)을
    # 그대로 쓴다 — 엑셀에서 구분을 고치면 앱 묶음이 따라온다.
    # 이름에 CDU 가 든 것은 따로 (구분 1 로는 렉이다).
    "arista": {
        "order": [["렉", ""], ["시트메탈", ""], ["캐스팅", ""], ["Hoover Table", ""],
                  ["CDU", ""], ["하드웨어", ""], ["기타", ""]],
        # 구분 1 로 안 갈리는 CDU · Hoover — 처음 한 번만 (seed_group)
        "seed": {"by_name": [("CDU", ["CDU", ""]), ("HOOVER", ["Hoover Table", ""])]},
        "by_dev_type": {"렉": "렉", "랙": "렉", "샷시": "시트메탈", "섀시": "시트메탈",
                        "시트메탈": "시트메탈", "캐스팅": "캐스팅", "다이캐스팅": "캐스팅",
                        "테이블": "Hoover Table", "하드웨어": "하드웨어"},
        "title": "종류별",
        # 양식에 '묶음' 칸 — 적으면 구분 1 보다 먼저 (CDU 같은 것을 옮길 때)
        "excel_group": "묶음",
    },
    # -----------------------------------------------------------
    # 자동차 — 고객사를 큰 고객으로
    # -----------------------------------------------------------
    # Min: "자동차사업부 같은 경우에는 고객사별로 묶어줘 HYYUNDAi, LG, VALEO처럼
    #      이렇게 고객사 여러개 있긴 한데 결국에는 한 큰틀로 나눌 수 잇게끔 해줘"
    #      → "자동차 같은 경우...이름으로 묶어주고"
    #
    # 고객사 이름의 **첫 낱말**이 곧 큰 고객이다 (brand_map).
    #     VALEO ETAPLES · VALEO SLP …   → VALEO
    #     LGE VN · LGE KR · LG MAGNA    → LG   (LGE 는 LG 로 — 짧은 쪽이 다른 쪽 앞머리면 합친다)
    #     HANON (혼자)                  → 기타
    # 명단을 외우지 않는다. 양식에 'VALEO MEXICO' 가 새로 들어오면 그날 VALEO 에
    # 붙고, 'BOSCH KR' · 'BOSCH CN' 둘이 들어오면 BOSCH 묶음이 저절로 생긴다.
    # 묶음 순서는 고객사가 많은 큰 고객부터, 기타는 맨 뒤.
    "automotive": {
        "order": [],
        "by_brand": True,
        "title": "고객사별",
    },
}


# ============================================================
#  엑셀이 먼저다
# ============================================================
# 사업부 양식 품목정보에 '국내/해외' 칸을 둔다 (묶는 사업부만).
REGION_CHOICES = ["국내", "해외"]


# ['해외', 'Lam'] → '해외 · Lam'.
def region_label(grp, big_only: bool = False) -> str:
    if not grp:
        return ""
    big, small = (list(grp) + ["", ""])[:2]
    return big if (big_only or not small) else "%s · %s" % (big, small)


# 양식의 '국내/해외' 칸 → [큰 묶음, 작은 묶음].
def parse_region(text):
    import re as _re
    t = str(text or "").strip()
    if not t:
        return None
    if t.startswith("국내") or t.lower().startswith("domestic"):
        return ["국내", ""]
    if t.startswith("해외") or t.lower().startswith("overseas"):
        small = _re.sub(r"^(해외|overseas)\s*[·\-–—:/|]?\s*", "", t, flags=_re.I).strip()
        if not small:
            return ["해외", ""]          # 작은 묶음은 customer_group 이 가른다
        low = small.lower()
        if low.startswith("lam"):
            return ["해외", "Lam"]
        if "아리스타" in small or low.startswith("arista"):
            return ["해외", "아리스타"]
        return ["해외", small]
    return None


# 앱 목록 위 작은 제목 ('국내 / 해외' · '종류별' · '고객사별').
def group_title(division_id: str) -> str:
    g = CUSTOMER_GROUPS.get(str(division_id or "").strip().lower()) or {}
    return str(g.get("title") or "")


# 양식 품목정보에 둘 묶음 칸 → {"header", "choices"} 또는 None.
def group_col(division_id: str):
    g = CUSTOMER_GROUPS.get(str(division_id or "").strip().lower()) or {}
    if g.get("excel_region"):
        return {"header": "국내/해외", "choices": list(REGION_CHOICES)}
    if g.get("excel_group"):
        return {"header": g["excel_group"],
                "choices": [o[0] for o in g["order"] if o[0] != "기타"] + ["기타"]}
    return None


# 양식의 묶음 칸 한 칸 → [큰 묶음, 작은 묶음].
def parse_group(division_id: str, text):
    g = CUSTOMER_GROUPS.get(str(division_id or "").strip().lower()) or {}
    if g.get("excel_region"):
        return parse_region(text)
    t = " ".join(str(text or "").split())
    if not t or not g.get("excel_group"):
        return None
    # 정해 둔 이름이면 그 글자로 맞춘다 ('valeo' → 'VALEO')
    for o in g["order"]:
        if o[0].replace(" ", "").lower() == t.replace(" ", "").lower():
            return [o[0], ""]
    return [t, ""]                 # 새 묶음 — 적힌 그대로


# 묶음 → 양식에 적어 줄 글자.
def group_cell(division_id: str, grp) -> str:
    g = CUSTOMER_GROUPS.get(str(division_id or "").strip().lower()) or {}
    if not grp or list(grp)[:1] == UNSORTED[:1]:
        return ""                      # 미분류는 빈 칸으로 — 채워 달라는 뜻
    if g.get("excel_region"):
        return region_label(grp, big_only=True)
    return str(list(grp)[0] or "")


# 화면에 띄울 고객사 이름 — 이상하게 적힌 것을 다듬는다
def clean_label(raw) -> str:
    import unicodedata as _ud
    t = str(raw or "").strip()
    if not t:
        return t
    t = t.replace("Đ", "D").replace("đ", "d")
    t = "".join(c for c in _ud.normalize("NFKD", t) if not _ud.combining(c))
    t = _ud.normalize("NFC", t)
    words = [w for w in t.split() if any(ch.isalpha() and ch.isascii() for ch in w)]
    caps = [w for w in words if w.upper() == w]
    if words and len(caps) * 2 > len(words) and len(caps) < len(words):
        t = t.upper()
    return t


# 양식에 묶음 칸('국내/해외' · '고객 묶음')을 두는 사업부인가.
def region_on(division_id: str) -> bool:
    return group_col(division_id) is not None


# 묶음 순서. 묶지 않는 사업부면 빈 목록.
def customer_group_order(division_id: str, extra: list | None = None) -> list:
    g = CUSTOMER_GROUPS.get(str(division_id or "").strip().lower())
    if not g:
        return []
    out = [list(x) for x in g["order"]]
    extra = [e for e in (extra or []) if list(e) != UNSORTED]
    if g.get("by_brand"):
        # 고객사가 많은 큰 고객부터 · 기타는 맨 뒤
        cnt = {}
        for e in extra:
            cnt[e[0]] = cnt.get(e[0], 0) + 1

        def _by_size(name):
            return (name == "기타", -cnt[name], name)
        return [[n, ""] for n in sorted(cnt, key=_by_size)] + [list(UNSORTED)]
    for e in extra or []:
        e = list(e)
        if e in out:
            continue
        same = [i for i, x in enumerate(out) if x[0] == e[0]]
        if same:
            out.insert(max(same) + 1, e)
        elif out and out[-1][0] == "기타":
            out.insert(len(out) - 1, e)       # 엑셀로 생긴 새 묶음은 '기타' 앞
        else:
            out.append(e)
    # 묶음 칸이 빈 고객사 — 늘 맨 뒤 (비어 있으면 앱이 안 그린다)
    out.append(list(UNSORTED))
    return out


UNSORTED = ["미분류", ""]


# 고객사 이름의 첫 낱말 ('VALEO ETAPLES' → 'VALEO').
def _brand(label) -> str:
    import re as _re
    t = clean_label(label).upper().strip()
    parts = [x for x in _re.split(r"[\s/\-_(),.·]+", t) if x]
    return parts[0] if parts else ""


# 고객사 이름들 → {이름: 큰 고객}.
def brand_map(labels) -> dict:
    raw = {lab: _brand(lab) for lab in labels or [] if str(lab or "").strip()}
    keys = sorted(set(raw.values()), key=len)
    merged = {}
    for k in keys:
        to = k
        for short in keys:
            if len(short) >= 2 and short != k and k.startswith(short):
                to = merged.get(short, short)
                break
        merged[k] = to
    count = {}
    for lab, b in raw.items():
        count[merged.get(b, b)] = count.get(merged.get(b, b), 0) + 1
    out = {}
    for lab, b in raw.items():
        big = merged.get(b, b)
        out[lab] = big if (big and count.get(big, 0) >= 2) else "기타"
    return out


# PCB '해외' 를 Lam · 아리스타 · 기타로.
def _overseas_sub(g: dict, k: str, label: str = ""):
    if k.startswith("pcb_lam_") or clean_label(label).upper().startswith("LAM"):
        return ["해외", "Lam"]
    lab = str(label or "")
    if k.startswith("pcb_arista") or "아리스타" in lab or lab.upper().startswith("ARISTA"):
        return ["해외", "아리스타"]
    return ["해외", "기타"]


# 그 고객사의 [큰 묶음, 작은 묶음].
def customer_group(division_id: str, project_key: str, override=None, label: str = "",
                   dev_type: str = "", peers=None):
    g = CUSTOMER_GROUPS.get(str(division_id or "").strip().lower())
    if not g:
        return None
    k = str(project_key or "").strip().lower()
    if override and isinstance(override, (list, tuple)) and override and str(override[0] or "").strip():
        big, small = (list(override) + ["", ""])[:2]
        if big == "해외" and not small:
            if ["해외", ""] in [list(x) for x in g["order"]]:
                return ["해외", ""]           # 해외를 더 안 나누는 사업부 (네트워크)
            return _overseas_sub(g, k, label)
        if big == "국내":
            return ["국내", ""]
        return [big, small]
    # 자동차 — 이름 첫 낱말 (peers 는 그 사업부 고객사 이름 전부)
    if g.get("by_brand"):
        return [brand_map(list(peers or []) + [label]).get(label, "기타") or "기타", ""]
    # 아리스타 — 양식 '구분 1' 그대로 (모르는 말이면 그 말이 곧 묶음 이름)
    if "by_dev_type" in g:
        t = str(dev_type or "").strip()
        if t:
            return [g["by_dev_type"].get(t, t), ""]
    return list(UNSORTED)


# 옛 이름 규칙으로 고른 묶음 — **처음 한 번 자료에 옮겨 적을 때만** 쓴다
def seed_group(division_id: str, project_key: str, label: str = "", dev_type: str = ""):
    g = CUSTOMER_GROUPS.get(str(division_id or "").strip().lower())
    if not g:
        return None
    sd = g.get("seed") or {}
    k = str(project_key or "").strip().lower()
    lab_u = clean_label(label).upper()
    for word, grp in sd.get("by_name") or []:
        if word in lab_u:
            return list(grp)
    for word, grp in sd.get("by_name_start") or []:
        if lab_u.strip().startswith(word):
            return list(grp)
    import re as _re
    _flat = " " + " ".join(_re.split(r"[^0-9A-Z가-힣]+", lab_u)) + " "
    for word, grp in sd.get("by_word") or []:
        if " %s " % word in _flat:
            return list(grp)
    for grp, keys in sd.get("rules") or []:
        for want in keys:
            if (want.endswith("_") and k.startswith(want)) or k == want:
                return list(grp)
    if division_id == "pcb" and (k.startswith("pcb_lam_") or k.startswith("pcb_arista")
                                 or lab_u.startswith("LAM") or "아리스타" in str(label or "")):
        return _overseas_sub(g, k, label)
    return list(sd["else"]) if sd.get("else") else None

# ============================================================
#  사업부 → 양식 모양
# ============================================================
#    한 줄만 고치면 그 사업부의 표가 통째로 바뀐다.
SHAPES = {
    "semiconductor": "반도체형",
    "ess": "고객사형",
    "pcb": "고객사형",
    "network": "고객사형",
    "automotive": "고객사형",
    "bloom": "프로젝트형",
    "arista": "프로젝트형",
}

# ============================================================
#  모양마다 쓰는 열과 머리글
# ============================================================
#    순서가 곧 화면에 서는 차례다. 양식의 왼쪽→오른쪽 순서와 같게 둔다 —
#    엑셀을 보면서 화면을 읽는 사람이 눈으로 따라갈 수 있어야 한다.
FORMS = {
    "반도체형": {
        "owner_label": "프로젝트",
        "name_label": "모델명",
        # 파트넘버가 주 식별자다. 이름은 그 아래 작은 글씨로 붙인다.
        "primary": "part_number",
        "secondary": "name",
        "columns": ["group", "dev_type", "price", "material_cost",
                    "year_qty", "po_qty", "shipped_qty", "note"],
        "labels": {"dev_type": "분류"},
    },
    "고객사형": {
        "owner_label": "고객사",
        "name_label": "품목",
        # 파트넘버를 안 적는 품목이 많다 (ESS 는 13건 전부 비어 있다).
        # 그래서 품목명이 먼저다 — 양식의 열 순서와도 같다.
        "primary": "name",
        "secondary": "part_number",
        "columns": ["group", "price", "material_cost", "po_qty", "shipped_qty"],
        "labels": {},
    },
    "프로젝트형": {
        "owner_label": "프로젝트",
        "name_label": "모델명",
        "primary": "part_number",
        "secondary": "name",
        "columns": ["group", "price", "material_cost", "po_qty", "shipped_qty"],
        "labels": {},
    },
}

# ============================================================
#  양식에서 읽기를 멈출 열 (1 = A)
# ============================================================
# 어떤 양식은 품목 자료 오른쪽에 올리는 쪽에서 따로 쓰는 칸이 붙는다
LAST_COL = {}


# ============================================================
#  개발 품목을 어떤 틀로 보여 줄까 (1 = 사업부별)
# ============================================================
# 개발 품목은 반도체 기준으로 **공정 13단계** 화면을 쓴다 — PO 접수부터 FAIR 승인까지.
DEV_FRAME = {
    "arista": "양산",
}


# 그 사업부의 개발 품목을 어떤 틀로 그릴까.
def dev_frame(division_id: str) -> str:
    return DEV_FRAME.get(str(division_id or "").strip().lower(), "")


# 그 사업부 양식에서 읽기를 멈출 열 번호.
def last_col(division_id: str):
    return LAST_COL.get(str(division_id or "").strip().lower())


# ============================================================
#  주차 칸이 보통 몇 개인가 (눈금일 뿐, **한계가 아니다**)
# ============================================================
# 반도체 양식만 W40 부터다. 나머지는 W41~W44 네 주차뿐이다
WEEK_HINT = {"반도체형": 5, "고객사형": 4, "프로젝트형": 4}


# ============================================================
#  주차별 계획에 세울 줄을 고르는 규칙
# ============================================================
# 아리스타는 품목이 90줄인데 주차 계획을 세우는 건 **렉(랙)** 뿐이다
WEEKLY_ONLY = {
    "arista": {"dev_type": ["렉"]},
}


# 그 사업부의 주차별 계획에 세울 줄 조건.
def weekly_only(division_id: str) -> dict:
    return WEEKLY_ONLY.get(str(division_id or "").strip().lower()) or {}


# ============================================================
#  사업부마다 무엇을 보이고 무엇을 숨길까
# ============================================================
# 지금까지 이 스위치가 **네 곳**에 흩어져 있었다
UI_DEFAULT = {
    "division_board": False,
    "project_board": False,
    "project_board_keys": [],
    "daily_upload": False,
    "revenue_excel": False,
}

UI = {
    # 반도체 — 프로젝트 키를 직접 적어 둔 곳 (앱의 _boardProjects)
    "semiconductor": {
        "project_board": True,
        "project_board_keys": ["hrva_plate", "havaplate", "hrva-plate",
                               "chamber", "enclosure", "powerbox",
                               "major_module",
                               # CURIE (Space X) — 2026-11-04
                               "spacex"],
        "revenue_excel": True,       # 주간보고 엑셀 한 장이 원본
    },
    # 아리스타 — 사업부 화면에도 보드를 띄우는 유일한 곳
    "arista": {
        "division_board": True,
        "project_board": True,
        "project_board_keys": ["arista_"],
    },
    "bloom": {
        "project_board": True,
        "project_board_keys": ["bloom_"],
        "daily_upload": True,
    },
    "ess": {
        "project_board": True,
        # 옛 키(sdi · fluence · epc_power)를 뺐다.
        # main.py 의 _ess_legacy_cleanup 주석 참고.
        "project_board_keys": ["ess_"],
        "daily_upload": True,
    },
    "pcb": {
        "project_board": True,
        "project_board_keys": ["pcb_"],
    },
    "automotive": {
        "project_board": True,
        "project_board_keys": ["auto_"],
    },
    # 네트워크 · 시스템 · 자동화 — 아직 양식이 안 들어왔다. 전부 꺼 둔다.
    "network": {},
    "system": {},
    "automation": {},
}


# 그 사업부에서 무엇을 보일까. 모르는 사업부는 전부 끈 상태.
def ui_for(division_id: str) -> dict:
    out = dict(UI_DEFAULT)
    out["project_board_keys"] = list(UI_DEFAULT["project_board_keys"])
    got = UI.get(str(division_id or "").strip().lower()) or {}
    for k, v in got.items():
        out[k] = list(v) if isinstance(v, list) else v
    return out


# 사업부 전체의 스위치 한 벌. 화면과 앱이 이걸 받아 간다
def all_ui() -> dict:
    return {d: ui_for(d) for d in UI}


# 이 프로젝트에 주차 현황 보드를 띄울까.
def board_on(division_id: str, project_key: str = "") -> bool:
    u = ui_for(division_id)
    if not u["project_board"]:
        return False
    keys = u["project_board_keys"]
    if not keys:
        return True
    k = str(project_key or "").strip().lower()
    for want in keys:
        if want.endswith("_") and k.startswith(want):
            return True
        if k == want:
            return True
    return False


# 그 사업부의 양식 모양. 모르는 사업부면 가장 흔한 '고객사형'.
def shape_of(division_id: str) -> str:
    return SHAPES.get(str(division_id or "").strip().lower(), "고객사형")


# 화면이 그릴 표의 열 구성 → {owner_label, primary, secondary, columns:[{key,label,align,width}]}
def columns_for(division_id: str) -> dict:
    form = FORMS[shape_of(division_id)]
    cols = []
    for key in list(form["columns"]) + due_cols(division_id):
        spec = dict(COLUMN_SPEC[key])
        if key in form["labels"]:
            spec["label"] = form["labels"][key]
        spec["key"] = key
        cols.append(spec)
    return {
        "division_id": division_id,
        "shape": shape_of(division_id),
        "owner_label": form["owner_label"],
        "name_label": form["name_label"],
        "primary": form["primary"],
        "secondary": form["secondary"],
        "columns": cols,
        "week_count": WEEK_HINT[shape_of(division_id)],
        # 주차별 계획에 세울 줄 조건 (없으면 빈 dict — 전부 센다)
        "weekly_only": weekly_only(division_id),
        # 무엇을 보이고 무엇을 숨길까 (위 UI)
        "ui": ui_for(division_id),
    }


# 설정 파일로 떨어뜨린다 (화면이 읽는 자리).
def save_config(path) -> None:
    data = {d: columns_for(d) for d in SHAPES}
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                          encoding="utf-8")
