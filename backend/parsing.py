# -*- coding: utf-8 -*-
"""파싱 — 사람이 쓴 글자에서 뜻을 꺼내는 함수들.

main.py 에서 떼어 왔다. 여기 들어오는 것의 조건은 하나다.
**서버 상태를 모른다** — 파일도 안 읽고, 설정도 안 보고, 전역 변수도 안 쓴다.
글자(또는 셀 목록)를 받아 dict 를 돌려줄 뿐이다. 그래서 따로 시험해 보기 쉽다.

  _parse_due_text              "8월 24일"      → "2026-08-24"
  _parse_report_filename       파일명          → 프로젝트 · 날짜 · 주차
  _extract_excel_markers       노트 글         → 본문과 표 마커를 분리
  _parse_shipping_table_header 출하표 머리 3줄 → 어느 칸이 무슨 뜻인지
  _parse_sales_input           매출 입력 글    → 판가와 주차별 숫자

엑셀 파일 자체를 여는 파서(프로젝트마다 양식이 달라 따로 만든 것들)는
여기가 아니라 *_import.py 에 있다. 여기는 '글자' 만 다룬다.
"""
import re
from datetime import date, datetime


_EXCEL_MARKER_RE = re.compile(
    "\U0001F4CA" r"\s*([^\n\r]+?)\s*@@table_ref=([^\s\n\r]+)",
    re.IGNORECASE,
)


def _parse_due_text(t: str):
    """due_text '8월 24일' -> 'YYYY-MM-DD' (올해 기준, 지났으면 내년)"""
    import re as _re
    from datetime import date as _date, datetime as _dt
    m = _re.search(r"(\d{1,2})월\s*(\d{1,2})일", t or "")
    if not m:
        return None
    mo, d = int(m.group(1)), int(m.group(2))
    today = _dt.utcnow().date()
    for y in (today.year, today.year + 1):
        try:
            cand = _date(y, mo, d)
            if cand >= today:
                return cand.isoformat()
        except ValueError:
            return None
    return None


def _parse_report_filename(file_name: str, fallback_date: str = "") -> dict:
    """
    파일명에서 프로젝트명 / 날짜 / 주차 추출.

    Examples:
        "260703_파워박스 진행현황.pptx"
            -> {"projects": ["파워박스"], "date": "2026-07-03", "week": 27, "display_title": "파워박스 · W27 주간보고"}
        "260528_내재화프레임, 메이져모듈 진행현황.pptx"
            -> {"projects": ["내재화프레임", "메이져모듈"], "date": "2026-05-28", "week": 22, "display_title": "내재화프레임, 메이져모듈 · W22 주간보고"}
        "Chamber_W26_20260706.pptx"
            -> {"projects": ["Chamber"], "date": "2026-07-06", "week": 26, "display_title": "Chamber · W26 주간보고"}
    """
    import re as _re
    import unicodedata as _ud
    from datetime import datetime as _dt, date as _date

    # macOS 파일명은 NFD(자모 분리) 로 저장되어 있을 수 있음 → NFC 로 정규화
    file_name = _ud.normalize("NFC", file_name or "")
    name = file_name.rsplit(".", 1)[0]  # 확장자 제거

    projects: list = []
    date_str = ""
    week_num: int = 0

    # 패턴 A: YYMMDD_프로젝트명(,프로젝트명) 진행현황
    m = _re.match(r"^(\d{6})[_\s]+(.+)$", name)
    if m:
        yymmdd = m.group(1)
        rest = m.group(2).strip()
        # " 진행현황", "_진행현황", "진행 현황" 등 trailing 제거
        rest = _re.sub(r"[\s_]*진행\s*현황.*$", "", rest).strip()
        rest = rest.rstrip("_ .").strip()
        try:
            dt = _dt.strptime(yymmdd, "%y%m%d").date()
            date_str = dt.isoformat()
            week_num = dt.isocalendar()[1]
        except Exception:
            pass
        # 콤마 분리
        projects = [x.strip() for x in _re.split(r"[,、/]", rest) if x.strip()]

    # 패턴 B: 프로젝트명_W##_YYYYMMDD
    if not projects:
        m2 = _re.match(r"^(.+?)_W(\d{1,2})_(\d{8})$", name)
        if m2:
            projects = [m2.group(1).strip()]
            try:
                week_num = int(m2.group(2))
                dt = _dt.strptime(m2.group(3), "%Y%m%d").date()
                date_str = dt.isoformat()
            except Exception:
                pass

    # fallback: 파일명 전체를 프로젝트명 취급
    if not projects:
        projects = [name]

    # fallback date
    if not date_str and fallback_date:
        try:
            dt = _dt.strptime(fallback_date, "%Y-%m-%d").date()
            date_str = fallback_date
            if not week_num:
                week_num = dt.isocalendar()[1]
        except Exception:
            pass

    display_title = ", ".join(projects)
    if week_num:
        display_title += " · W" + str(week_num) + " 주간보고"

    return {
        "projects": projects,
        "date": date_str,
        "week": week_num,
        "display_title": display_title,
    }


def _extract_excel_markers(text: str):
    """텍스트에서 엑셀 마커 추출.
    반환: (clean_text, [{filename, table_ref, anchor}])
    """
    lines = text.split("\n")
    out_lines = []
    tables = []
    last_nonempty = ""
    for ln in lines:
        m = _EXCEL_MARKER_RE.search(ln)
        if m:
            fname = (m.group(1) or "").strip()
            ref = (m.group(2) or "").strip()
            if fname and ref:
                tables.append({
                    "filename": fname,
                    "table_ref": ref,
                    "anchor": last_nonempty,
                })
            continue
        out_lines.append(ln)
        if ln.strip():
            last_nonempty = ln.strip()
    return ("\n".join(out_lines), tables)


def _parse_shipping_table_header(rows: list) -> dict:
    """헤더 3행(R1, R2, R3)을 분석해 각 컬럼의 의미를 매핑.

    처리 규칙:
    - R1: 대분류 (월/누적합계) - forward-fill (병합 셀)
    - R2: 서브그룹 (W27/W28.../합계) - forward-fill (계획/실적 쌍의 왼쪽 셀에만 값 있음)
    - R3: 세부 (계획/실적/PO/출하)
    """
    if len(rows) < 3:
        return {"columns": [], "detected_months": [], "current_month": None}

    r1 = rows[0]
    r2 = rows[1]
    r3 = rows[2]
    n_cols = max(len(r1), len(r2), len(r3))

    def _fill(row, n):
        """forward-fill: 빈 셀은 왼쪽 값으로 채움"""
        out = []
        last = ""
        for i in range(n):
            v = (row[i] if i < len(row) else "").strip()
            if v:
                last = v
            out.append(last)
        return out

    r1_filled = _fill(r1, n_cols)
    # R2는 forward-fill 하되, 다음 대분류가 바뀌면 리셋
    r2_filled = []
    last_r1 = ""
    last_r2 = ""
    for i in range(n_cols):
        cur_r1 = r1_filled[i]
        cur_r2 = (r2[i] if i < len(r2) else "").strip()
        if cur_r1 != last_r1:
            # 대분류가 바뀌면 R2 리셋
            last_r2 = ""
            last_r1 = cur_r1
        if cur_r2:
            last_r2 = cur_r2
        r2_filled.append(last_r2)

    columns = []
    detected_months = []
    months_with_weeks = []

    for i in range(1, n_cols):  # 0번은 '구분' 열
        top = r1_filled[i]
        mid = r2_filled[i]
        sub = (r3[i] if i < len(r3) else "").strip()

        if not top:
            continue

        top_norm = top.replace(" ", "").replace("\n", "")
        is_month = top.endswith("월") and "누적" not in top and top_norm not in ("PO수량", "출하실적", "잔량")
        is_cumulative = "누적" in top_norm
        is_direct_po = top_norm in ("PO수량", "PO",)
        is_direct_shipped = top_norm in ("출하실적", "출하",)
        is_direct_remaining = top_norm in ("잔량",)
        is_yearly = ("년실적" in top_norm) or ("년도실적" in top_norm)

        if is_month and top not in detected_months:
            detected_months.append(top)

        if is_direct_po:
            columns.append({"index": i, "kind": "cumulative_po"})
            continue
        if is_direct_shipped:
            columns.append({"index": i, "kind": "cumulative_shipped"})
            continue
        if is_direct_remaining:
            columns.append({"index": i, "kind": "cumulative_remaining"})
            continue
        if is_yearly:
            columns.append({"index": i, "kind": "yearly_actual", "label": top})
            continue

        if is_cumulative:
            if "PO" in sub.upper():
                columns.append({"index": i, "kind": "cumulative_po"})
            elif "출하" in sub:
                columns.append({"index": i, "kind": "cumulative_shipped"})
            else:
                columns.append({"index": i, "kind": "cumulative_other"})
            continue

        if is_month:
            # W##이 있으면 주차별
            if mid.startswith("W") and mid[1:].isdigit():
                if top not in months_with_weeks:
                    months_with_weeks.append(top)
                if sub == "계획":
                    columns.append({"index": i, "kind": "week_plan", "month": top, "week": mid})
                elif sub == "실적":
                    columns.append({"index": i, "kind": "week_actual", "month": top, "week": mid})
            elif mid == "합계":
                if sub == "계획":
                    columns.append({"index": i, "kind": "month_total_plan", "month": top})
                elif sub == "실적":
                    columns.append({"index": i, "kind": "month_total_actual", "month": top})
            else:
                # 완료 월 또는 다음 월 계획만
                if sub == "계획":
                    columns.append({"index": i, "kind": "month_plan", "month": top})
                elif sub == "실적":
                    columns.append({"index": i, "kind": "month_actual", "month": top})

    current_month = months_with_weeks[0] if months_with_weeks else None

    return {
        "columns": columns,
        "detected_months": detected_months,
        "current_month": current_month,
    }


def _parse_sales_input(text: str) -> dict:
    """
    [모델/판가]
    EFEM=65
    VTM=24
    
    [주차별]
    W27: EFEM 2/2, VTM 2/2
    W30: EFEM 5/0, VTM 1/0
    
    → {"prices": {"EFEM": 65.0}, "weeks": {"W27": {"EFEM": {"plan":2,"actual":2}}}}
    """
    prices = {}
    weeks = {}
    section = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        # 섹션 헤더
        m = re.match(r'^\[(.+?)\]\s*$', line)
        if m:
            tag = m.group(1).strip().lower()
            if '판가' in tag or 'price' in tag or '모델' in tag:
                section = 'prices'
            elif '주차' in tag or 'week' in tag:
                section = 'weeks'
            else:
                section = None
            continue
        if section == 'prices':
            # EFEM=65  또는  EFEM = 65.0
            m = re.match(r'^([^\s=]+)\s*=\s*([\d.]+)\s*$', line)
            if m:
                prices[m.group(1).strip()] = float(m.group(2))
            continue
        if section == 'weeks':
            # W30: EFEM 5/0, VTM 1/0
            m = re.match(r'^(W\d+)\s*[:：]?\s*(.+)$', line, re.IGNORECASE)
            if not m:
                continue
            wk = m.group(1).upper()
            payload = m.group(2)
            models = {}
            # "EFEM 5/0, VTM 1/0" → 콤마/공백 mix 처리
            for part in re.split(r'\s*,\s*', payload):
                part = part.strip()
                if not part:
                    continue
                # "EFEM 5/0"
                mm = re.match(r'^(\S+)\s+([\d]+)\s*/\s*([\d]+)\s*$', part)
                if mm:
                    models[mm.group(1)] = {
                        "plan": int(mm.group(2)),
                        "actual": int(mm.group(3)),
                    }
            if models:
                weeks[wk] = models
    return {"prices": prices, "weeks": weeks}
