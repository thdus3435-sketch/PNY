# =========================================================
# 3) 공통 유틸
# =========================================================
def parse_date_obj(date_str: str):
    norm = normalize_date(date_str)
    if not norm:
        return None
    try:
        return datetime.strptime(norm, "%Y-%m-%d").date()
    except Exception:
        return None


def parse_datetime_safe(dt_text: str):
    dt_text = clean_text(dt_text)
    if not dt_text:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(dt_text, fmt)
        except Exception:
            pass
    return None


def try_extract_date_from_text(text: str) -> str:
    text = clean_text(text)
    if not text:
        return ""

    patterns = [
        r"(20\d{2}[./-]\d{1,2}[./-]\d{1,2})",
    ]

    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return normalize_date(m.group(1))
    return ""


def is_within_lookback(date_str: str, lookback_days: int) -> bool:
    dt = parse_date_obj(date_str)
    if not dt:
        return False

    if isinstance(lookback_days, str):
        lookback_days = int(lookback_days)

    today = datetime.now().date()
    cutoff = today - timedelta(days=int(lookback_days) - 1)
    return dt >= cutoff


def extract_deadline_from_period(period_text: str) -> str:
    period_text = clean_text(period_text)
    if not period_text:
        return ""

    parts = re.split(r"~|∼|～|to", period_text)
    if len(parts) >= 2:
        end_date = normalize_date(parts[-1])
        return end_date if end_date else clean_text(parts[-1])

    return period_text


def normalize_title(title: str) -> str:
    title = clean_text(title).lower()
    title = re.sub(r"\[(수정|공고|재공고|연장공고)\]", "", title)
    title = re.sub(r"\((수정|재공고|연장공고)\)", "", title)
    title = re.sub(r"\s+", "", title)
    title = re.sub(r"[^가-힣a-z0-9]", "", title)
    return title.strip()


def score_to_grade(score: int) -> str:
    """
    적합도 점수 등급 변환

    기준:
    - S: 정기 모니터링 대상 공고
    - A: 5점 이상 / 핵심공고
    - B: 4점 이상 / 관련공고
    - C: 1~3점 / 참고공고
    - D: 0점 / 저장 제외
    """
    try:
        score = int(score)
    except Exception:
        score = 0

    if score >= 60:
        return "S"
    elif score >= 5:
        return "A"
    elif score >= 4:
        return "B"
    elif score >= 1:
        return "C"
    return "D"

def contains_keyword_loose(text, keyword):
    text = clean_text(text)
    keyword = clean_text(keyword)

    if not text or not keyword:
        return False

    norm_text = normalize_for_match(text)
    norm_kw = normalize_for_match(keyword)

    if not norm_kw:
        return False

    # AI, AX, DX, TP, OT, DB처럼 짧은 영문 키워드는 단독 오탐 방지
    if re.fullmatch(r"[A-Za-z]{1,3}", keyword.strip()):
        return re.search(
            rf"(?<![A-Za-z0-9가-힣]){re.escape(keyword)}(?![A-Za-z0-9가-힣])",
            text,
            flags=re.IGNORECASE
        ) is not None

    return norm_kw in norm_text

def match_recurring_notice(text: str):
    """
    정기 모니터링 대상 매칭
    - REGULAR_MONITORING_PROGRAMS 구조:
      group, aliases, priority, reason
    """
    matched_groups = []

    for item in REGULAR_MONITORING_PROGRAMS:
        for alias in item.get("aliases", []):
            if contains_keyword_loose(text, alias):
                matched_groups.append({
                    "group": item.get("group", ""),
                    "alias": alias,
                    "priority": item.get("priority", ""),
                    "reason": item.get("reason", ""),
                })
                break

    return matched_groups

def calculate_relevance_score_v2(title: str, source: str = "", body_text: str = ""):
    """
    저장 기준:
    1. 공고명 기준 정기 모니터링 대상 alias hit → 저장
    2. 공고명 기준 키워드 1개 이상 hit + 기준 점수 이상 → 저장 후보

    중요:
    - 기업마당 / IRIS / 스마트공장 모두 공고명(title)만 기준으로 점수 계산
    - body_text는 상세정보 저장용으로만 사용하고, 키워드 매칭에는 사용하지 않음
    """
    title = clean_text(title)
    scoring_text = title

    if not scoring_text:
        return {
            "save": False,
            "score": 0,
            "grade": "D",
            "recurring_hit": False,
            "recurring_group_ids": [],
            "matched_keywords": [],
            "matched_combos": [],
            "matched_recurring": [],
            "keyword_hit_count": 0,
        }

    title_norm = normalize_title(title)

    matched_keywords = []

    # 1) 정기 모니터링 대상 탐지 - 공고명 기준
    recurring_matches = match_recurring_notice(scoring_text)
    recurring_hit = len(recurring_matches) > 0

    recurring_group_ids = []
    recurring_names = []
    recurring_score = 0

    for item in recurring_matches:
        group_name = item.get("group", "")
        alias = item.get("alias", "")

        if group_name:
            recurring_group_ids.append(group_name)
            recurring_names.append(group_name)

        if normalize_title(alias) == title_norm:
            recurring_score += 25
        else:
            recurring_score += 20

    recurring_score = min(recurring_score, 30)

    # 2) 일반 키워드 점수 - 공고명 기준
    keyword_hit_count = 0
    keyword_score = 0

    for kw, pts in KEYWORD_WEIGHT_MAP.items():
        if contains_keyword_loose(scoring_text, kw):
            keyword_hit_count += 1
            keyword_score += pts
            matched_keywords.append(f"{kw}(+{pts})")

    final_score = recurring_score + keyword_score
    final_score = max(final_score, 0)

    # 정기 모니터링 대상은 최소 S등급 점수 보장
    if recurring_hit:
        final_score = max(final_score, REGULAR_FORCE_SCORE)

    grade = score_to_grade(final_score)

    # 4) 저장 여부
    if recurring_hit:
        save = True
    elif final_score >= MIN_SAVE_SCORE and keyword_hit_count > 0:
        save = True
    else:
        save = False

    return {
        "save": save,
        "score": final_score,
        "grade": grade,
        "recurring_hit": recurring_hit,
        "recurring_group_ids": list(dict.fromkeys(recurring_group_ids)),
        "matched_keywords": list(dict.fromkeys(matched_keywords)),
        "matched_combos": [],
        "matched_recurring": list(dict.fromkeys(recurring_names)),
        "keyword_hit_count": keyword_hit_count,
    }

def classify_status_from_apply_period(apply_period: str, today=None) -> str:
    apply_period = clean_text(apply_period)
    if not apply_period:
        return "확인필요"

    if today is None:
        today = datetime.now().date()

    text = apply_period.replace("∼", "~").replace("～", "~")
    dates = re.findall(r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}", text)

    if len(dates) < 2:
        return "확인필요"

    start_date = parse_date_obj(dates[0])
    end_date = parse_date_obj(dates[1])

    if not start_date or not end_date:
        return "확인필요"

    if today < start_date:
        return "접수예정"
    elif start_date <= today <= end_date:
        return "접수중"
    else:
        return "마감"

def safe_get(lst, idx, default=""):
    if idx is None or idx < 0:
        return default
    return lst[idx] if idx < len(lst) else default

DETAIL_FIELD_LABEL_ALIASES = {
    "announce_date": ["공고일", "공고일자", "공고 등록일", "등록일"],
    "deadline": ["마감일", "접수마감일", "접수 마감일"],
    "apply_period": ["접수 기간", "접수기간", "신청기간", "신청 기간"],
    "receipt_status": ["접수 상태", "접수상태"],
    "progress_status": ["진행 상태", "진행상태"],
    "ministry": ["소관부처", "주무부처"],
    "agency": ["수행기관", "전문기관", "주관기관", "담당기관"],
    "support_target": ["지원 대상", "지원대상", "신청 대상", "신청대상"],
    "support_content": ["지원 내용", "지원내용", "사업내용", "사업 내용"],
    "receipt_place": ["접수 방법", "접수방법", "신청 방법", "신청방법"],
    "inquiry": ["문의처", "문의", "사업담당자 연락처", "담당자 연락처"],
    "notice_no": ["공고번호", "공고 번호"],
    "title": ["공고명", "세부공고명", "사업명"],
}

DETAIL_FIELD_LABELS = [
    label
    for aliases in DETAIL_FIELD_LABEL_ALIASES.values()
    for label in aliases
]

DETAIL_FIELD_STOP_LABELS = [
    "핵심 요약 정보",
    "진행 상태 변경",
    "사업연도",
    "사업분류",
    "공고번호",
    "세부공고명",
    "첨부파일",
    "파일 등록 일자",
    "순번",
    "항목",
    "목록",
    "링크복사",
    "신청하기",
]

def normalize_detail_label(text: str) -> str:
    text = clean_text(text)
    text = re.sub(r"[\s:：ㆍ·\-/]+", "", text)
    return text

DETAIL_FIELD_LABEL_KEYS = {
    normalize_detail_label(label)
    for label in DETAIL_FIELD_LABELS + DETAIL_FIELD_STOP_LABELS
}

def is_detail_field_label(text: str) -> bool:
    return normalize_detail_label(text) in DETAIL_FIELD_LABEL_KEYS

def extract_labeled_value_from_lines(lines, labels, max_lines=1):
    """
    상세화면의 라벨-값 구조를 읽는다.

    대응 예:
    - 공고일 2026-05-19
    - 공고일
      2026-05-19
    """
    labels = [clean_text(x) for x in labels if clean_text(x)]
    label_keys = {normalize_detail_label(x) for x in labels}

    for i, line in enumerate(lines):
        line = clean_text(line)
        if not line:
            continue

        line_key = normalize_detail_label(line)

        if line_key in label_keys:
            values = []
            for next_line in lines[i + 1:]:
                next_line = clean_text(next_line)
                if not next_line:
                    continue
                if is_detail_field_label(next_line):
                    break
                values.append(next_line)
                if len(values) >= max_lines:
                    break
            return clean_text("\n".join(values))

        if line_key in DETAIL_FIELD_LABEL_KEYS:
            continue

        for label in labels:
            if not line.startswith(label):
                continue

            rest = clean_text(line[len(label):].lstrip(":：- "))
            if rest and normalize_detail_label(rest) not in DETAIL_FIELD_LABEL_KEYS:
                return rest

    return ""

def normalize_apply_period_text(text: str) -> str:
    text = clean_text(text)
    if not text:
        return ""

    text = text.replace("∼", "~").replace("～", "~").replace("~", " ~ ")
    text = re.sub(r"\s+", " ", text).strip()

    dates = re.findall(r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}", text)
    if len(dates) >= 2:
        return f"{normalize_date(dates[0])} ~ {normalize_date(dates[1])}"

    return text

def extract_detail_label_values(text: str, max_lines_by_field=None) -> dict:
    text = clean_text(text)
    max_lines_by_field = max_lines_by_field or {}

    lines = [
        clean_text(x)
        for x in text.splitlines()
        if clean_text(x)
    ]

    result = {}

    for field, aliases in DETAIL_FIELD_LABEL_ALIASES.items():
        result[field] = extract_labeled_value_from_lines(
            lines,
            aliases,
            max_lines=max_lines_by_field.get(field, 1)
        )

    if result.get("announce_date"):
        result["announce_date"] = normalize_date(result["announce_date"])

    if result.get("deadline"):
        result["deadline"] = normalize_date(result["deadline"])

    if result.get("apply_period"):
        result["apply_period"] = normalize_apply_period_text(result["apply_period"])
        if not result.get("deadline"):
            result["deadline"] = extract_deadline_from_period(result["apply_period"])

    return result

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def extract_notice_no_from_note(note: str) -> str:
    """
    비고 컬럼에서 공고번호를 추출
    예: '공고번호: 경기대진테크노파크 공고 제2026-092호'
    """
    note = clean_text(note)
    if not note:
        return ""

    m = re.search(r"공고번호\s*[:：]\s*([^|]+)", note)
    if m:
        return clean_text(m.group(1))

    return ""


def should_keep_smart_factory_notice(ann_date: str, status: str, lookback_days: int) -> bool:
    """
    스마트공장 공고 수집 유지 여부 판단

    스마트공장사업관리시스템은 접수예정 공고가
    오늘보다 미래 공고일자로 표시될 수 있으므로,
    공고일만 보지 않고 접수상태를 함께 본다.
    """
    status = clean_text(status)

    # 접수중/접수예정은 공고일이 미래여도 수집
    if "접수중" in status or "접수예정" in status:
        return True

    # 공고일이 없으면 일단 수집 후 점수 필터에 맡김
    if not ann_date:
        return True

    # 그 외는 기존 최근 N일 기준 적용
    return is_within_lookback(ann_date, lookback_days)

def make_notice_keys_from_raw_row(row):
    """
    신규공고 시트 row 구조 기준 중복키 생성

    - 일반 공고:
      링크키 = 출처 + 상세링크
      고유키 = 출처 + 소관부처 + 수행기관 + 공고명 + 공고일 + 마감일

    - 스마트공장 공고:
      상세링크가 공고별 고유값으로 안 잡힐 수 있으므로
      공고번호를 우선 중복키로 사용
    """
    announce_date = clean_text(safe_get(row, 0))   # 공고일
    title = clean_text(safe_get(row, 1))           # 공고명
    deadline = clean_text(safe_get(row, 4))        # 마감일
    ministry = clean_text(safe_get(row, 5))        # 소관부처
    agency = clean_text(safe_get(row, 6))          # 수행기관
    apply_period = clean_text(safe_get(row, 7))    # 신청기간
    detail_url = clean_text(safe_get(row, 12))     # 상세링크
    source = clean_text(safe_get(row, 15))         # 출처
    status = clean_text(safe_get(row, 16))         # 접수상태
    note = clean_text(safe_get(row, 27))           # 비고 (첨부파일 컬럼 추가로 index 변경)

    normalized_title = normalize_title(title)

    # 스마트공장 전용 중복키
    if source == "스마트공장":
        notice_no = extract_notice_no_from_note(note)

        if notice_no:
            link_key = f"{source}||{notice_no}"
            unique_key = f"{source}||{notice_no}||{normalized_title}||{announce_date}||{apply_period}"
        else:
            # 공고번호가 없을 경우 보조키 사용
            link_key = ""
            unique_key = (
                f"{source}||{normalized_title}||"
                f"{announce_date}||{apply_period}||{status}"
            )

        return link_key, unique_key

    # 일반 사이트 중복키
    link_key = f"{source}||{detail_url}" if detail_url else ""
    unique_key = (
        f"{source}||{ministry}||{agency}||"
        f"{normalized_title}||{announce_date}||{deadline}"
    )

    return link_key, unique_key

def make_cross_site_title_key_from_raw_row(row):
    """
    사이트가 달라도 같은 공고명을 중복으로 판단하기 위한 공통키 생성

    기준:
    - 출처 제외
    - 공고명 normalize 기준
    - [수정공고], (재공고), 공백, 특수문자 차이는 normalize_title()에서 정리
    """
    title = clean_text(safe_get(row, 1))  # 공고명

    if not title:
        return ""

    return normalize_title(title)

def make_cross_site_title_key_from_title(title):
    """
    Build the cross-site duplicate key directly from a notice title.
    """
    title = clean_text(title)

    if not title:
        return ""

    return normalize_title(title)

def add_cross_site_title_keys_from_rows(rows, target_keys):
    """
    Add collected notice title keys to the runtime duplicate set.
    """
    if target_keys is None:
        return

    for row in rows or []:
        cross_site_title_key = make_cross_site_title_key_from_raw_row(row)

        if cross_site_title_key:
            target_keys.add(cross_site_title_key)

def make_history_rows_from_raw(rows):
    history_rows = []

    for row in rows:
        link_key, unique_key = make_notice_keys_from_raw_row(row)
        cross_site_title_key = make_cross_site_title_key_from_raw_row(row)

        history_rows.append([
            now_str(),
            unique_key,
            link_key,
            cross_site_title_key,
            safe_get(row, 0),   # 공고일
            safe_get(row, 1),   # 공고명
            safe_get(row, 5),   # 소관부처
        ])

    return history_rows

def make_recurring_result_rows_from_raw(rows):
    recurring_rows = []

    for row in rows:
        recurring_flag = clean_text(safe_get(row, 23))  # 정기공고여부
        if recurring_flag != "Y":
            continue

        recurring_rows.append([
            now_str(),
            safe_get(row, 24),  # 사업군ID(정기공고그룹)
            "",                 # 대표공고명
            safe_get(row, 1),   # 실제공고명
            safe_get(row, 15),  # 출처
            safe_get(row, 0),   # 공고일
            safe_get(row, 12),  # 상세링크
            safe_get(row, 2),   # 적합도점수
            safe_get(row, 3),   # 적합도등급
            safe_get(row, 25),  # 매칭키워드
        ])

    return recurring_rows

def build_recurring_result_key(row):
    """
    정기공고탐지결과 중복키 생성
    기준:
    - 사업군ID
    - 실제공고명
    - 출처
    - 공고일
    - 상세링크
    """
    group_id = clean_text(safe_get(row, 1))      # 사업군ID
    title = clean_text(safe_get(row, 3))         # 실제공고명
    source = clean_text(safe_get(row, 4))        # 출처
    announce_date = clean_text(safe_get(row, 5)) # 공고일
    detail_url = clean_text(safe_get(row, 6))    # 상세링크

    return (
        f"{group_id}||"
        f"{normalize_title(title)}||"
        f"{source}||"
        f"{announce_date}||"
        f"{detail_url}"
    )


def build_existing_recurring_result_keys(sheet):
    """
    정기공고탐지결과 시트에 이미 저장된 공고 중복키 생성
    """
    values = sheet.get_all_values()

    if len(values) <= 1:
        return set()

    header = values[0]
    idx = {name: i for i, name in enumerate(header)}

    existing_keys = set()

    for row in values[1:]:
        group_id = clean_text(safe_get(row, idx.get("사업군ID", -1)))
        title = clean_text(safe_get(row, idx.get("실제공고명", -1)))
        source = clean_text(safe_get(row, idx.get("출처", -1)))
        announce_date = clean_text(safe_get(row, idx.get("공고일", -1)))
        detail_url = clean_text(safe_get(row, idx.get("상세링크", -1)))

        if not title:
            continue

        key = (
            f"{group_id}||"
            f"{normalize_title(title)}||"
            f"{source}||"
            f"{announce_date}||"
            f"{detail_url}"
        )

        existing_keys.add(key)

    return existing_keys


def write_recurring_result_rows(sheet, rows):
    """
    정기공고탐지결과 저장 시 기존 시트와 배치 내 중복 제거
    """
    ensure_sheet_header(
        sheet,
        RECURRING_RESULT_HEADERS,
        mismatch_mode=HEADER_MISMATCH_MODE
    )

    if not rows:
        print(f"[{sheet.title}] 정기공고탐지결과 저장할 데이터 없음")
        return

    existing_keys = build_existing_recurring_result_keys(sheet)

    deduped_rows = []
    seen_batch = set()

    for row in rows:
        key = build_recurring_result_key(row)

        title = clean_text(safe_get(row, 3))

        if key in existing_keys:
            print(f"[{sheet.title}] 기존 정기공고 중복 제외: {title}")
            continue

        if key in seen_batch:
            print(f"[{sheet.title}] 배치 내 정기공고 중복 제외: {title}")
            continue

        seen_batch.add(key)
        deduped_rows.append(row)

    if not deduped_rows:
        print(f"[{sheet.title}] 신규 정기공고탐지결과 0건 - 중복 제외")
        return

    write_rows_from_first_empty(sheet, deduped_rows)

def is_closed_receipt_status(receipt_status: str) -> bool:
    receipt_status = clean_text(receipt_status)

    if not receipt_status:
        return False

    return any(x in receipt_status for x in ["마감", "종료"])

def should_hide_notice_by_status(receipt_status: str, progress_status: str) -> bool:
    """접수상태/진행상태 기준으로 숨김 여부를 계산한다."""
    progress_status = clean_text(progress_status)

    if is_closed_receipt_status(receipt_status):
        return True

    if progress_status in ["미진행", "종료"]:
        return True

    return False

