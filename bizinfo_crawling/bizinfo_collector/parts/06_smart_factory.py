# =========================================================
# 10) 스마트공장사업관리시스템
# =========================================================
def smart_factory_extract_url_from_attrs(node, base_url=SMART_FACTORY_BASE_URL):
    """
    스마트공장 사이트의 href / onclick / data-* 속성에서 URL을 추출한다.
    - 목록의 링크복사 버튼
    - 상세페이지의 다운로드 버튼
    - javascript 함수 인자 내 상대경로
    모두 가능한 범위에서 처리한다.
    """
    if not node:
        return ""

    attrs_to_check = []
    for attr in ["href", "onclick", "data-url", "data-href", "data-link", "data-clipboard-text"]:
        v = node.get(attr)
        if v:
            attrs_to_check.append(str(v))

    joined = " ".join(attrs_to_check)
    joined = html.unescape(joined)

    # 1) 절대 URL 우선
    m = re.search(r"https?://[^\s'\"<>;)]+", joined)
    if m:
        return m.group(0)

    # 2) javascript 안의 상대 URL 추출
    rel_candidates = re.findall(r"['\"]([^'\"]*(?:rcrtPbanc|bsnsPbanc|download|file|atch|attach|down)[^'\"]*)['\"]", joined, flags=re.I)
    for rel in rel_candidates:
        rel = clean_text(rel)
        if not rel or rel == "#" or rel.lower().startswith("javascript"):
            continue
        return urljoin(base_url, rel)

    # 3) href가 상대경로인 경우
    href = node.get("href") if node else ""
    href = clean_text(href)
    if href and href != "#" and not href.lower().startswith("javascript"):
        return urljoin(base_url, href)

    return ""


def smart_factory_extract_copy_link(root, fallback_url=""):
    """목록/상세의 '링크복사' 버튼 또는 URL성 속성에서 공유/상세 URL 추출"""
    if not root:
        return fallback_url

    candidates = []
    for node in root.select("a, button"):
        text = clean_text(node.get_text(" ", strip=True))
        attrs = " ".join([str(node.get(a, "")) for a in ["href", "onclick", "data-url", "data-href", "data-clipboard-text"]])
        if "링크복사" in text or "copy" in attrs.lower() or "clipboard" in attrs.lower():
            candidates.append(node)

    for node in candidates:
        url = smart_factory_extract_url_from_attrs(node, SMART_FACTORY_BASE_URL)
        if url:
            return url

    return fallback_url


def smart_factory_table_kv(soup):
    """상세페이지 상단 표/카드의 라벨-값 구조를 key-value로 변환"""
    kv = {}

    for tr in soup.select("tr"):
        cells = tr.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        # th-td, th-td, th-td 형태까지 대응
        i = 0
        while i < len(cells) - 1:
            key = clean_text(cells[i].get_text(" ", strip=True))
            val = clean_text(cells[i + 1].get_text(" ", strip=True))
            if key and val and len(key) <= 20:
                kv[key] = val
            i += 2

    body_text = clean_text(soup.get_text("\n", strip=True))
    label_values = extract_detail_label_values(
        body_text,
        max_lines_by_field={
            "support_content": 8,
            "support_target": 5,
            "receipt_place": 5,
            "inquiry": 8,
        }
    )

    canonical_to_header = {
        "announce_date": "공고일자",
        "deadline": "마감일",
        "apply_period": "접수기간",
        "receipt_status": "접수상태",
        "progress_status": "진행상태",
        "ministry": "소관부처",
        "agency": "수행기관",
        "support_target": "지원대상",
        "support_content": "지원내용",
        "receipt_place": "접수방법",
        "inquiry": "문의처",
        "notice_no": "공고번호",
        "title": "공고명",
    }

    for field, header in canonical_to_header.items():
        value = clean_text(label_values.get(field, ""))
        if value and not clean_text(kv.get(header, "")):
            kv[header] = value

    return kv


def smart_factory_extract_section_text(full_text, start_keywords, end_keywords=None):
    """본문 텍스트에서 특정 섹션 추출"""
    if not full_text:
        return ""
    end_keywords = end_keywords or []

    start_pos = -1
    used_kw = ""
    for kw in start_keywords:
        pos = full_text.find(kw)
        if pos != -1 and (start_pos == -1 or pos < start_pos):
            start_pos = pos
            used_kw = kw

    if start_pos == -1:
        return ""

    end_pos = len(full_text)
    for kw in end_keywords:
        pos = full_text.find(kw, start_pos + len(used_kw))
        if pos != -1 and pos < end_pos:
            end_pos = pos

    return clean_text(full_text[start_pos:end_pos])

def smart_factory_default_ministry(kv=None):
    kv = kv or {}
    return clean_text(kv.get("소관부처", "")) or "중소벤처기업부"

def smart_factory_guess_agency(kv=None, title="", notice_no="", body_text=""):
    """스마트공장 상세/제목/공고번호에서 수행기관을 보수적으로 추정한다."""
    kv = kv or {}

    for key in ["수행기관", "전문기관", "주관기관", "담당기관", "운영기관"]:
        value = clean_text(kv.get(key, ""))
        if value:
            return value

    title = clean_text(title)
    notice_no = clean_text(notice_no)
    body_text = clean_text(body_text)

    bracket_match = re.match(r"^\[([^\]]{2,40})\]", title)
    if bracket_match:
        bracket_value = clean_text(bracket_match.group(1))
        generic_bracket_values = {
            "공고", "재공고", "수정공고", "안내", "모집공고", "사업공고"
        }
        if bracket_value not in generic_bracket_values:
            return bracket_value

    org_suffixes = (
        "테크노파크", "공사", "공단", "진흥원", "재단", "협회", "센터",
        "대학교", "포스코", "LG전자", "LG이노텍", "LIG넥스원",
        "삼성디스플레이", "한국수력원자력", "한국가스안전공사"
    )

    source_text = "\n".join([notice_no, body_text])

    for line in [clean_text(x) for x in source_text.splitlines() if clean_text(x)]:
        if "공고" not in line and "제" not in line:
            continue

        for suffix in org_suffixes:
            pattern = rf"([가-힣A-Za-z0-9()·ㆍ\s]+?{re.escape(suffix)})"
            match = re.search(pattern, line)
            if match:
                return clean_text(match.group(1))

    return ""

def smart_factory_clean_inquiry_text(text):
    text = clean_text(text)

    if not text:
        return ""

    menu_phrases = {
        "맞춤형 공급기업 검색",
        "홍보관",
        "스마트공장소개",
        "솔루션소개",
        "우수구축사례",
        "보도자료",
        "홍보자료",
        "제조혁신센터소개",
        "로그인",
        "회원가입",
    }

    lines = []

    for line in [clean_text(x) for x in text.splitlines() if clean_text(x)]:
        if line in menu_phrases:
            continue
        lines.append(line)

    cleaned = clean_text("\n".join(lines))

    if not cleaned:
        return ""

    has_contact_signal = bool(
        re.search(r"\d{2,4}-\d{3,4}-\d{4}", cleaned)
        or re.search(r"[\w\.-]+@[\w\.-]+", cleaned)
        or any(x in cleaned for x in ["문의", "담당", "연락", "전화", "내선"])
    )

    if not has_contact_signal and len(cleaned.splitlines()) >= 3:
        return ""

    return cleaned

def smart_factory_merge_note_parts(*notes):
    parts = []
    seen = set()

    for note in notes:
        for part in [clean_text(x) for x in clean_text(note).split("|") if clean_text(x)]:
            key = normalize_for_match(part)
            if not key or key in seen:
                continue
            seen.add(key)
            parts.append(part)

    return " | ".join(parts)

def smart_factory_trim_section_value(text: str, stop_labels=None) -> str:
    """라벨 추출값 뒤에 다음 섹션이 붙은 경우 현재 섹션 값만 남긴다."""
    text = clean_text(text)
    if not text:
        return ""

    stop_labels = stop_labels or []
    stop_label_keys = {
        normalize_detail_label(label)
        for label in stop_labels
        if clean_text(label)
    }

    lines = []
    for line in [clean_text(x) for x in text.splitlines() if clean_text(x)]:
        line_key = normalize_detail_label(line)
        if line_key in stop_label_keys:
            break

        starts_next_label = False
        for label in stop_labels:
            label = clean_text(label)
            if not label:
                continue
            if line.startswith(label + ":") or line.startswith(label + "："):
                starts_next_label = True
                break
        if starts_next_label:
            break

        lines.append(line)

    return clean_text("\n".join(lines))

def smart_factory_is_section_label_line(line: str, labels) -> bool:
    line = clean_text(line)
    if not line:
        return False

    line_key = normalize_detail_label(line)

    for label in labels:
        label = clean_text(label)
        if not label:
            continue

        label_key = normalize_detail_label(label)
        if line_key == label_key:
            return True

        if line.startswith(label + ":") or line.startswith(label + "："):
            return True

    return False

def smart_factory_strip_section_label(line: str, labels) -> str:
    line = clean_text(line)

    for label in sorted([clean_text(x) for x in labels if clean_text(x)], key=len, reverse=True):
        if line == label:
            return ""
        if line.startswith(label + ":") or line.startswith(label + "："):
            return clean_text(line[len(label):].lstrip(":：- )("))

    return line

def smart_factory_extract_line_section_candidates(text: str, start_labels, stop_labels=None, max_lines=12):
    """
    스마트공장 본문은 PDF/HWP에서 줄바꿈이 잘게 쪼개져 들어온다.
    문자열 find 방식 대신 줄 단위로 섹션 후보를 여러 개 뽑아 실제 값에 가까운 후보를 고른다.
    """
    text = clean_text(text)
    stop_labels = stop_labels or []

    if not text:
        return []

    all_stop_labels = list(dict.fromkeys(stop_labels + [
        "사업개요", "사업 개요",
        "사업 목적", "사업목적",
        "지원 대상", "지원대상",
        "지원 내용", "지원내용",
        "지원 과제 및 조건", "지원과제 및 조건",
        "지원 과제", "지원과제",
        "지원 조건", "지원조건",
        "신청 방법", "신청방법",
        "접수 방법", "접수방법",
        "문의처", "문의 및 연락처",
        "첨부파일", "파일 등록 일자",
        "목록", "링크복사", "신청하기",
    ]))

    lines = [clean_text(x) for x in text.splitlines() if clean_text(x)]
    candidates = []

    for i, line in enumerate(lines):
        if not smart_factory_is_section_label_line(line, start_labels):
            continue

        values = []
        inline_value = smart_factory_strip_section_label(line, start_labels)
        if inline_value:
            values.append(inline_value)

        for next_line in lines[i + 1:]:
            if smart_factory_is_section_label_line(next_line, all_stop_labels):
                break

            # 스마트공장 공고에는 ")" 같은 장식 라인이 단독으로 들어오는 경우가 있음
            if next_line in [")", "(", "-", "·", "ㆍ"]:
                continue

            values.append(next_line)

            if len(values) >= max_lines:
                break

        candidate = clean_text("\n".join(values))
        if candidate:
            candidates.append(candidate)

    return candidates

def smart_factory_clean_section_lines(text: str, max_lines=None) -> str:
    text = clean_text(text)
    if not text:
        return ""

    noisy_exact = {
        ")", "(", "-", "·", "ㆍ",
        "지원 대상", "지원대상",
        "지원 내용", "지원내용",
        "사업개요", "사업 개요",
    }
    noisy_contains = [
        "지원계획을 다음과 같이 공고합니다",
        "지원계획을 다음과 같이 공고",
        "테크노파크 원장",
        "스마트공장 사업관리시스템",
    ]

    lines = []
    seen = set()

    for line in [clean_text(x) for x in text.splitlines() if clean_text(x)]:
        if line in noisy_exact:
            continue
        if any(noise in line for noise in noisy_contains):
            continue

        key = normalize_for_match(line)
        if not key or key in seen:
            continue

        seen.add(key)
        lines.append(line)

        if max_lines and len(lines) >= max_lines:
            break

    return clean_text("\n".join(lines))

def smart_factory_choose_support_target(candidates, fallback=""):
    all_candidates = [clean_text(x) for x in candidates if clean_text(x)]
    fallback = clean_text(fallback)
    if fallback:
        all_candidates.append(fallback)

    best = ""
    best_score = -999

    for candidate in all_candidates:
        cleaned = smart_factory_clean_section_lines(candidate, max_lines=8)
        if not cleaned:
            continue

        score = 0
        if any(k in cleaned for k in ["기업", "중소", "중견", "제조기업", "도입기업"]):
            score += 20
        if any(k in cleaned for k in ["스마트공장", "구축", "제조"]):
            score += 8
        if "지원계획" in cleaned or "공고합니다" in cleaned or "사업개요" in cleaned:
            score -= 30
        if "지원 내용" in cleaned or "지원내용" in cleaned:
            score -= 20

        line_count = len(cleaned.splitlines())
        if 1 <= line_count <= 6:
            score += 5
        if line_count > 8:
            score -= 10

        if score > best_score:
            best_score = score
            best = cleaned

    return best

def smart_factory_choose_support_content(candidates, fallback=""):
    all_candidates = [clean_text(x) for x in candidates if clean_text(x)]
    fallback = clean_text(fallback)
    if fallback:
        all_candidates.append(fallback)

    best = ""
    best_score = -999

    for candidate in all_candidates:
        cleaned = smart_factory_clean_section_lines(candidate, max_lines=12)
        if not cleaned:
            continue

        score = 0
        if any(k in cleaned for k in ["지원", "구축", "솔루션", "자동화장비", "센서", "ICT", "정보통신기술"]):
            score += 20
        if any(k in cleaned for k in ["지원계획을 다음과 같이 공고", "원장"]):
            score -= 30
        if "지원 대상" in cleaned or "지원대상" in cleaned:
            score -= 15

        line_count = len(cleaned.splitlines())
        if 1 <= line_count <= 12:
            score += 5
        if line_count > 20:
            score -= 10

        if score > best_score:
            best_score = score
            best = cleaned

    return best

def smart_factory_clean_notice_content_lines(notice_body: str, kv: dict = None) -> str:
    """
    스마트공장 상세 본문에서 지원내용에 들어갈 핵심 안내문만 정리

    목표:
    - 공고명/세부공고명 중복 제거
    - 접수기간/공고일자/사업연도/문의처/첨부파일 안내 제거
    - 동일 문장 중복 제거
    - 실제 안내문 중심으로 저장
    """
    kv = kv or {}
    notice_body = clean_text(notice_body)

    if not notice_body:
        return ""

    title = clean_text(
        kv.get("세부공고명", "") or
        kv.get("공고명", "")
    )

    main_title = clean_text(kv.get("공고명", ""))
    apply_period = clean_text(kv.get("접수기간", ""))

    title_norm = normalize_for_match(title)
    main_title_norm = normalize_for_match(main_title)
    apply_period_norm = normalize_for_match(apply_period)

    lines = [
        clean_text(x)
        for x in notice_body.splitlines()
        if clean_text(x)
    ]

    remove_exact = {
        "공고일자",
        "사업연도",
        "공고명",
        "세부공고명",
        "사업분류",
        "공고번호",
        "접수상태",
        "진행상태",
        "마감일",
        "접수기간",
        "문의처",
        "문의 및 연락처",
        "신청방법",
        "접수방법",
        "첨부파일",
        "목록",
        "링크복사",
        "신청하기",
        "예시)",
        "예시",
    }

    remove_contains = [
        "044-300-0959",
        "044-300-0952",
        "스마트제조혁신추진단",
        "사무실번호",
        "시스템번호",
        "PDF, ZIP 파일",
        "PDF",
        "ZIP",
        "업로드",
        "상시 접수됩니다",
        "기획기관 컨소시엄은 사업 신청 단계부터 매칭하는 것도 가능합니다",
        "자율형공장 참여기업 모집 공고는 사업안내ㆍ사업공고에서 확인하실수 있습니다",
        "별도신청이 불필요합니다",
        "신청기간",
        "접수기간",
        "사업연도",
        "공고일자",
        "파일 업로드",
        "첨부파일",
        "신청화면",
        "사무실번호",
        "내선",
    ]

    cleaned = []
    seen = set()
    skip_next_meta_value = False
    meta_value_labels = {"사업분류", "공고번호", "접수상태", "진행상태"}

    for line in lines:
        if not line:
            continue

        line_norm = normalize_for_match(line)

        if skip_next_meta_value:
            skip_next_meta_value = False
            continue

        # 1) 라벨성 문구 제거
        if line in remove_exact:
            if line in meta_value_labels:
                skip_next_meta_value = True
            continue

        # 2) 공고명/세부공고명과 동일한 줄 제거
        if title_norm and line_norm == title_norm:
            continue

        if main_title_norm and line_norm == main_title_norm:
            continue

        # 3) 공고명 + "안내" 형태는 실제 안내 제목일 수 있으므로 유지
        #    단, 공고명과 완전 동일한 줄만 제거함

        # 4) 접수기간과 동일한 줄 제거
        if apply_period_norm and line_norm == apply_period_norm:
            continue

        # 5) 날짜/기간 단독 라인 제거
        if re.fullmatch(r"20\d{2}", line):
            continue

        if re.fullmatch(r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}", line):
            continue

        # 2026-04-27 00:00 ~ 2026-05-15 17:00
        if re.search(
            r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+\d{1,2}:\d{2}\s*~\s*20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s+\d{1,2}:\d{2}",
            line
        ):
            continue

        # 2026년 4월 27일 ~ 2026년 5월 15일
        if re.search(
            r"20\d{2}년\s*\d{1,2}월\s*\d{1,2}일.*20\d{2}년\s*\d{1,2}월\s*\d{1,2}일",
            line
        ):
            continue

        # 6) 문의처/첨부/예시 안내 제거
        if any(x in line for x in remove_contains):
            continue

        # 7) 전화번호 포함 라인 제거
        if re.search(r"\d{2,4}-\d{3,4}-\d{4}", line):
            continue

        if re.search(r"(공고|제)\s*20\d{2}[-\s]?\d{1,4}호", line):
            continue

        # 8) 너무 짧은 값 제거
        if len(line) <= 3:
            continue

        # 9) 중복 제거
        if line_norm in seen:
            continue

        seen.add(line_norm)
        cleaned.append(line)

    if not cleaned:
        return ""

    # ---------------------------------------------------------
    # 실제 안내문 시작 위치 보정
    # ---------------------------------------------------------
    start_idx = 0

    # 우선 "안내"가 포함된 제목성 문장부터 시작
    for i, line in enumerate(cleaned):
        if "안내" in line and any(k in line for k in ["모집", "공고", "지원사업", "스마트공장", "자율형공장"]):
            start_idx = i
            break

    for i, line in enumerate(cleaned):
        if (
            "지원계획을" in line
            or "붙임과 같이 공고" in line
            or "다음과 같이 공고" in line
            or "구축지원사업" in line and "공고합니다" in line
        ):
            start_idx = i
            break

    # "※ 본 공고는" 유형은 그 문장부터 시작하는 것이 더 깔끔함
    for i, line in enumerate(cleaned):
        if line.startswith("※ 본 공고는") or line.startswith("* 본 공고는"):
            start_idx = i
            break

    # 일반 안내문 시작 키워드
    for i, line in enumerate(cleaned):
        if (
            "모집하오니" in line
            or "신청하여 주시기 바랍니다" in line
            or "사업참여를 희망하는" in line
            or "참여하는" in line and "접수를 위해 게시하는 공고" in line
        ):
            # 단, 바로 앞 줄이 안내 제목이면 제목도 같이 포함
            if i > 0 and "안내" in cleaned[i - 1]:
                start_idx = i - 1
            else:
                start_idx = i
            break

    cleaned = cleaned[start_idx:]

    # ---------------------------------------------------------
    # 실제 지원내용 종료 위치 보정
    # ---------------------------------------------------------
    picked = []

    for line in cleaned:
        # 접수방법/문의처 이후 내용은 지원내용에서 제외
        if line in ["접수방법", "신청방법", "문의처", "문의 및 연락처"]:
            break

        if "문의 및 연락처" in line:
            break

        if "첨부파일" in line:
            break

        picked.append(line)

        # 일반 공고 안내문은 첫 설명문까지만 남기는 게 가장 깔끔함
        if (
            "모집하오니" in line
            or "신청하여 주시기 바랍니다" in line
            or "공고문 안내에 따라 신청하여 주시기 바랍니다" in line
        ):
            break

        # 대중소상생형 공고 유형
        if "접수를 위해 게시하는 공고" in line:
            # 다음 줄의 신청 불가 안내까지는 포함할 수 있으므로 바로 break 하지 않음
            continue

        if "신청 불가" in line:
            break

    return clean_text("\n".join(picked))

def smart_factory_extract_receipt_place(notice_body: str) -> str:
    """
    스마트공장 상세 본문에서 접수방법만 분리 추출
    """
    notice_body = clean_text(notice_body)

    if not notice_body:
        return ""

    receipt = smart_factory_extract_section_text(
        notice_body,
        ["접수방법", "접수 방법", "신청방법", "신청 방법"],
        ["문의처", "문의 및 연락처", "첨부파일", "목록", "링크복사"]
    )

    # '공고문 확인' 같은 짧은 접수방법만 허용
    lines = [clean_text(x) for x in receipt.splitlines() if clean_text(x)]

    if not lines:
        return ""

    cleaned = []

    for line in lines:
        if line in ["접수방법", "신청방법", "접수 방법", "신청 방법"]:
            continue
        if "문의" in line:
            break
        cleaned.append(line)

    return clean_text("\n".join(cleaned[:5]))

def smart_factory_extract_support_fields(full_text, kv=None):
    """
    스마트공장 상세 본문에서 지원대상/지원내용/접수처를 추출한다.

    수정 방향:
    - 지원내용에 공고일자/사업연도/공고명/접수기간/문의처가 섞이지 않도록 제거
    - 중복 안내문 제거
    - 지원내용은 핵심 공고 안내문만 저장
    """
    full_text = clean_text(full_text)
    kv = kv or {}

    notice_body = smart_factory_extract_notice_body(full_text, kv)

    target_stop_labels = [
        "지원내용", "지원 내용",
        "지원규모", "지원 규모",
        "사업개요", "사업 개요",
        "신청방법", "신청 방법",
        "접수방법", "접수 방법",
        "문의처", "문의 및 연락처",
        "첨부파일", "목록", "링크복사",
    ]
    content_stop_labels = [
        "신청방법", "신청 방법",
        "접수방법", "접수 방법",
        "문의처", "문의 및 연락처",
        "첨부파일", "파일 등록 일자",
        "목록", "링크복사", "신청하기",
    ]
    receipt_stop_labels = [
        "문의처", "문의 및 연락처",
        "첨부파일", "파일 등록 일자",
        "목록", "링크복사",
    ]

    # 1) 지원대상/신청자격 계열 섹션만 지원대상으로 인정
    target_candidates = smart_factory_extract_line_section_candidates(
        notice_body,
        [
            "지원대상", "지원 대상",
            "신청자격", "신청 자격",
            "신청대상", "신청 대상",
            "모집대상", "모집 대상",
            "참여대상", "참여 대상",
        ],
        target_stop_labels,
        max_lines=8,
    )
    support_target = smart_factory_choose_support_target(
        target_candidates,
        fallback=smart_factory_trim_section_value(kv.get("지원대상", ""), target_stop_labels)
    )

    # 2) 지원내용은 "지원 내용" 섹션을 우선하고, 없을 때만 안내문/추정값을 사용
    content_candidates = smart_factory_extract_line_section_candidates(
        notice_body,
        [
            "지원내용", "지원 내용",
            "지원규모", "지원 규모",
            "사업내용", "사업 내용",
        ],
        content_stop_labels + [
            "지원 과제 및 조건", "지원과제 및 조건",
            "지원 과제", "지원과제",
            "지원 조건", "지원조건",
            "사업개요", "사업 개요",
            "지원대상", "지원 대상",
        ],
        max_lines=12,
    )
    kv_support_content = smart_factory_trim_section_value(
        kv.get("지원내용", ""),
        content_stop_labels
    )
    support_content = smart_factory_choose_support_content(
        content_candidates,
        fallback=kv_support_content
    ) or smart_factory_clean_notice_content_lines(
        notice_body=notice_body,
        kv=kv
    )

    if not support_content:
        support_content = smart_factory_guess_content_from_body(notice_body)

    # 3) 접수처/접수방법 분리
    receipt_place = smart_factory_trim_section_value(
        kv.get("접수방법", ""),
        receipt_stop_labels
    ) or smart_factory_extract_receipt_place(notice_body)

    return {
        "support_target": support_target,
        "support_content": support_content,
        "receipt_place": receipt_place,
        "notice_body": notice_body,
    }
def smart_factory_extract_notice_body(body_text: str, kv: dict = None) -> str:
    """
    스마트공장 상세페이지 본문 추출
    - 고정 섹션명이 없는 공고가 많아서,
      접수기간 이후부터 첨부파일 영역 전까지를 본문으로 잡는다.
    """
    kv = kv or {}
    body_text = clean_text(body_text)

    if not body_text:
        return ""

    # 상세페이지에서 실제 공고명 위치부터 시작
    start_candidates = []

    for key in ["공고명", "세부공고명"]:
        title = clean_text(kv.get(key, ""))
        if title:
            pos = body_text.find(title)
            if pos != -1:
                start_candidates.append(pos)

    # 접수기간 이후 본문이 시작되는 경우가 많음
    apply_period = clean_text(kv.get("접수기간", ""))
    if apply_period:
        pos = body_text.find(apply_period)
        if pos != -1:
            start_candidates.append(pos + len(apply_period))

    start_pos = min(start_candidates) if start_candidates else 0

    end_candidates = []
    for marker in ["순번\n항목\n첨부파일", "첨부파일\n파일 등록 일자", "목록", "링크복사"]:
        pos = body_text.find(marker, start_pos)
        if pos != -1:
            end_candidates.append(pos)

    end_pos = min(end_candidates) if end_candidates else len(body_text)

    notice_body = clean_text(body_text[start_pos:end_pos])

    # 메뉴/상단 공통 문구 제거
    remove_phrases = [
        "You need to enable JavaScript to run this app.",
        "로그인",
        "회원가입",
        "중소벤처24 통합로그인",
        "전체메뉴",
        "사업안내",
        "홍보관",
        "알림/참여마당",
        "조직소개",
        "home",
        "모집공고상세",
        "사업공고상세",
    ]

    lines = []
    for line in notice_body.splitlines():
        line = clean_text(line)
        if not line:
            continue
        if line in remove_phrases:
            continue
        if len(line) <= 1:
            continue
        lines.append(line)

    return clean_text("\n".join(lines))


def smart_factory_guess_target_from_body(notice_body: str) -> str:
    """
    상세 본문에서 지원대상/신청자격으로 보이는 문장 추정
    """
    notice_body = clean_text(notice_body)

    if not notice_body:
        return ""

    target_keywords = [
        "신청자격", "신청 자격",
        "지원대상", "지원 대상",
        "신청대상", "신청 대상",
        "참여대상", "참여 대상",
        "도입기업", "공급기업",
        "중소기업", "중견기업",
        "주관기관", "기획기관",
        "참여기관", "신청기업",
        "모집대상", "모집 대상",
    ]

    lines = [clean_text(x) for x in notice_body.splitlines() if clean_text(x)]
    picked = []

    for line in lines:
        if any(k in line for k in target_keywords):
            picked.append(line)

    # 너무 없으면 앞부분 본문 일부라도 지원대상에 넣어 빈칸 방지
    if not picked:
        picked = lines[:5]

    return clean_text("\n".join(picked[:10]))


def smart_factory_guess_content_from_body(notice_body: str) -> str:
    """
    상세 본문에서 지원내용으로 저장할 내용 추출
    - 섹션명이 없으면 상세 본문 전체를 저장
    """
    notice_body = clean_text(notice_body)

    if not notice_body:
        return ""

    content_keywords = [
        "사업개요", "사업 개요",
        "지원내용", "지원 내용",
        "지원규모", "지원 규모",
        "지원금", "지원비율", "지원 비율",
        "사업비", "정부지원금",
        "구축", "지원", "모집", "신청",
    ]

    lines = [clean_text(x) for x in notice_body.splitlines() if clean_text(x)]

    picked = []
    for line in lines:
        if any(k in line for k in content_keywords):
            picked.append(line)

    # 섹션 기반 추출이 안 되면 본문 전체를 지원내용으로 저장
    if not picked:
        picked = lines

    return clean_text("\n".join(picked[:40]))

def parse_smart_factory_attachments_from_soup(soup, base_url):
    """
    스마트공장 상세페이지 첨부파일 추출
    - 파일명
    - 다운로드 href
    - onclick 내부 다운로드 URL 후보
    """
    attachments = []

    # 1) 첨부파일 테이블/영역 후보 찾기
    all_rows = soup.select("table tr")
    for tr in all_rows:
        row_text = clean_text(tr.get_text(" ", strip=True))

        # 첨부파일명으로 보이는 확장자가 없으면 스킵
        if not re.search(r"\.(pdf|hwp|hwpx|zip|xlsx?|docx?|pptx?)", row_text, flags=re.I):
            continue

        # 파일명 후보 추출
        file_names = re.findall(
            r"([가-힣A-Za-z0-9_\-\[\]\(\)\s\.·ㆍ&]+?\.(?:pdf|hwp|hwpx|zip|xls|xlsx|doc|docx|ppt|pptx))",
            row_text,
            flags=re.I
        )

        links = []

        # href 기반 다운로드 링크
        for a in tr.select("a[href]"):
            href = clean_text(a.get("href"))
            if href and href != "#":
                links.append(urljoin(base_url, href))

            onclick = clean_text(a.get("onclick"))
            if onclick:
                links.extend(extract_urls_from_onclick(onclick, base_url))

        # button/input onclick 기반 다운로드 링크
        for el in tr.select("button, input"):
            onclick = clean_text(el.get("onclick"))
            if onclick:
                links.extend(extract_urls_from_onclick(onclick, base_url))

        links = list(dict.fromkeys([x for x in links if x]))

        if file_names:
            for i, file_name in enumerate(file_names):
                attachments.append({
                    "name": clean_text(file_name),
                    "url": links[i] if i < len(links) else (links[0] if links else "")
                })

    return attachments


def extract_urls_from_onclick(onclick, base_url):
    """
    onclick 안의 URL 또는 다운로드 파라미터를 최대한 추출
    """
    results = []
    onclick = html.unescape(clean_text(onclick))

    # 완전한 URL
    urls = re.findall(r"https?://[^\s'\";]+", onclick)
    results.extend(urls)

    # / 로 시작하는 상대경로
    rels = re.findall(r"['\"](\/[^'\"]+)['\"]", onclick)
    for rel in rels:
        results.append(urljoin(base_url, rel))

    # 스마트공장 다운로드 함수 파라미터 후보
    # 예: fnDownload('abc', 'def') 같은 구조일 때
    params = re.findall(r"['\"]([^'\"]+)['\"]", onclick)

    for p in params:
        if not p:
            continue

        # 이미 URL이면 추가
        if p.startswith("http"):
            results.append(p)
        elif p.startswith("/"):
            results.append(urljoin(base_url, p))

    return list(dict.fromkeys(results))

def smart_factory_extract_attachments(soup, base_url=SMART_FACTORY_BASE_URL):
    """
    스마트공장 상세페이지 첨부파일 추출

    수정 방향:
    - 실제 확장자가 있는 파일명만 첨부파일로 인정
    - '첨부파일 2', '첨부파일 3' 같은 빈 placeholder 생성 금지
    - 다운로드 URL은 href/onclick/data-*에서 잡히는 경우만 우선 저장
    """
    attachments = []
    seen = set()

    file_pattern = re.compile(
        r"([가-힣A-Za-z0-9_\-\[\]\(\)\s\.]+?\.(?:pdf|hwp|hwpx|zip|xls|xlsx|doc|docx|ppt|pptx))",
        flags=re.I
    )

    # 1) 첨부파일 섹션 주변 우선 탐색
    candidate_nodes = []

    for node in soup.select("tr, li, div, p, span"):
        text = clean_text(node.get_text("\n", strip=True))
        if not text:
            continue

        if not file_pattern.search(text):
            continue

        candidate_nodes.append(node)

    for node in candidate_nodes:
        node_text = clean_text(node.get_text("\n", strip=True))

        file_names = file_pattern.findall(node_text)

        if not file_names:
            continue

        links = []

        for child in node.select("a, button, span"):
            url = smart_factory_extract_url_from_attrs(child, base_url)
            if url:
                links.append(url)

            onclick = clean_text(child.get("onclick"))
            if onclick:
                links.extend(extract_urls_from_onclick(onclick, base_url))

        links = list(dict.fromkeys([x for x in links if x]))

        for i, raw_name in enumerate(file_names):
            file_name = smart_factory_clean_attachment_name(raw_name)

            if not file_name:
                continue

            url = ""
            if i < len(links):
                url = links[i]
            elif links:
                url = links[0]

            key = file_name
            if key in seen:
                continue

            seen.add(key)
            attachments.append({
                "name": file_name,
                "url": url
            })

    return attachments

def parse_smart_factory_detail_from_current_page(driver, fallback_url=""):
    """현재 Selenium 화면이 상세페이지라고 가정하고 스마트공장 상세내용 파싱"""
    actual_url = driver.current_url
    soup = BeautifulSoup(driver.page_source, "html.parser")

    kv = smart_factory_table_kv(soup)

    # 링크복사는 옵션으로만 시도
    if SMART_FACTORY_CAPTURE_LINKCOPY:
        final_detail_url = smart_factory_extract_linkcopy_url_by_click(
            driver,
            fallback_url=actual_url or fallback_url
        )
    else:
        final_detail_url = actual_url or fallback_url

    # 링크복사 클릭 후 페이지 DOM이 바뀔 수 있으므로 soup 재생성
    soup = BeautifulSoup(driver.page_source, "html.parser")
    body_text = clean_text(soup.get_text("\n", strip=True))

    support_fields = smart_factory_extract_support_fields(body_text, kv)

    attachments = smart_factory_extract_attachments(
        soup,
        SMART_FACTORY_BASE_URL
    )

    # 1순위: 웹에서 다운로드 URL 최대한 추출
    if SMART_FACTORY_CAPTURE_DOWNLOAD_URL:
        modal_attachments = smart_factory_extract_modal_attachments_web(driver)

        if modal_attachments:
            attachments = modal_attachments
        else:
            attachments = smart_factory_enrich_attachments_by_click(
                driver,
                attachments
            )

    # 2순위: 실제 파일 다운로드는 현재 사용하지 않음
    elif SMART_FACTORY_DOWNLOAD_ATTACHMENTS:
        downloaded_attachments = smart_factory_download_attachments_from_modal(
            driver,
            download_dir=SMART_FACTORY_DOWNLOAD_DIR
        )

        if downloaded_attachments:
            attachments = downloaded_attachments

    # 3순위: 파일명만 정리
    else:
        for a in attachments:
            a["name"] = smart_factory_clean_attachment_name(a.get("name", "첨부파일"))
            a["url"] = clean_text(a.get("url", ""))

    apply_period = kv.get("접수기간", "") or support_fields.get("apply_period", "")
    deadline = extract_deadline_from_period(apply_period)
    if not deadline:
        deadline = normalize_date(kv.get("마감일", ""))

    title = kv.get("세부공고명", "") or kv.get("공고명", "")
    main_title = kv.get("공고명", "")
    notice_no = kv.get("공고번호", "")
    announce_date = normalize_date(kv.get("공고일자", ""))
    agency = smart_factory_guess_agency(
        kv=kv,
        title=title,
        notice_no=notice_no,
        body_text=body_text
    )
    status = clean_text(kv.get("접수상태", ""))
    progress_status = clean_text(kv.get("진행상태", ""))

    note_parts = []
    if notice_no:
        note_parts.append(f"공고번호: {notice_no}")
    if progress_status:
        note_parts.append(f"진행상태: {progress_status}")
    if main_title and main_title != title:
        note_parts.append(f"상위공고명: {main_title}")
    if attachments:
        note_parts.append("첨부파일: " + ", ".join([
            smart_factory_clean_attachment_name(a.get("name", "첨부파일"))
            for a in attachments[:5]
        ]))

    return {
        "title": title,
        "announce_date": announce_date,
        "status": status,
        "ministry": smart_factory_default_ministry(kv),
        "agency": agency,
        "apply_period": apply_period,
        "deadline": deadline,
        "detail_url": final_detail_url,
        "support_target": support_fields.get("support_target", ""),
        "support_content": support_fields.get("support_content", ""),
        "receipt_place": support_fields.get("receipt_place", ""),
        "inquiry": smart_factory_clean_inquiry_text(
            clean_text(kv.get("문의처", "")) or smart_factory_extract_section_text(
                body_text,
                ["문의처", "문의"],
                ["첨부파일", "목록", "링크복사", "순번"]
            )
        ),
        "attachments": build_attachment_json(attachments),
        "note": " | ".join(note_parts),
        "raw_text": support_fields.get("notice_body", body_text),
    }

def parse_smart_factory_row(tr, base_url):
    tds = tr.find_all("td")
    if len(tds) < 2:
        return None

    row_text = clean_text(tr.get_text("\n", strip=True))
    if not row_text:
        return None

    title = ""
    detail_url = ""

    # 1) 제목 링크 우선 탐지
    for a in tr.find_all("a"):
        a_text = clean_text(a.get_text(" ", strip=True))
        if not a_text or "다운로드" in a_text or "링크복사" in a_text:
            continue
        title = a_text
        url = smart_factory_extract_url_from_attrs(a, base_url)
        if url:
            detail_url = url
        break

    # 2) 링크복사 버튼 URL 보조 탐지
    copied_url = smart_factory_extract_copy_link(tr, "")
    if copied_url:
        detail_url = copied_url

    if not title:
        td_texts = [clean_text(td.get_text(" ", strip=True)) for td in tds if clean_text(td.get_text(" ", strip=True))]

        ignore_patterns = [
            r"공고번호",
            r"공고일자",
            r"접수기간",
            r"접수상태",
            r"사업연도",
            r"^\d{4}-\d{2}-\d{2}",
            r"접수마감",
            r"접수중",
            r"전체 접수개시",
            r"링크복사",
        ]

        for txt in td_texts:
            if len(txt) < 5:
                continue
            if any(re.search(p, txt) for p in ignore_patterns):
                continue
            title = txt
            break

    if not title:
        return None

    ann_date = ""
    apply_period = ""
    deadline = ""
    notice_no = ""

    m_notice = re.search(r"공고번호\s*:\s*(.+?)(?=\n|공고일자|접수기간|$)", row_text)
    if m_notice:
        notice_no = clean_text(m_notice.group(1))

    m_date = re.search(r"공고일자\s*:\s*(20\d{2}[./-]\d{1,2}[./-]\d{1,2})", row_text)
    if m_date:
        ann_date = normalize_date(m_date.group(1))

    m_period = re.search(r"접수기간\s*:\s*([0-9./:-]+\s*[~\-]\s*[0-9./: -]+)", row_text)
    if m_period:
        apply_period = clean_text(m_period.group(1))
        deadline = extract_deadline_from_period(apply_period)

    status = clean_text(tds[-1].get_text(" ", strip=True)) if len(tds) >= 3 else ""
    note = f"공고번호: {notice_no}" if notice_no else ""

    return {
        "source": "스마트공장",
        "status": status,
        "announce_date": ann_date,
        "title": title,
        "deadline": deadline,
        "ministry": "중소벤처기업부",
        "agency": "",
        "apply_period": apply_period,
        "support_target": "",
        "support_content": "",
        "receipt_place": "",
        "inquiry": "",
        "detail_url": detail_url,
        "attachments": "",
        "note": note,
        "raw_text": row_text
    }

def find_smart_factory_notice_rows(driver):
    """
    스마트공장 Ant Design 테이블에서 실제 공고 목록 row만 추출
    - 검색조건 테이블 row 제외
    - ant-table-measure-row 제외
    - aria-hidden=true 제외
    - 공고일자/접수기간/접수상태가 있는 실제 row만 사용
    """
    all_rows = driver.find_elements(By.CSS_SELECTOR, "tr.ant-table-row")
    notice_rows = []

    for row in all_rows:
        try:
            cls = row.get_attribute("class") or ""
            aria_hidden = row.get_attribute("aria-hidden") or ""
            text = clean_text(row.text)

            if not text:
                continue

            if "ant-table-measure-row" in cls:
                continue

            if aria_hidden == "true":
                continue

            if "공고일자" not in text and "접수기간" not in text:
                continue

            if "검색조건" in text or "사업연도" in text:
                continue

            notice_rows.append(row)

        except Exception:
            continue

    return notice_rows

def scrape_smart_factory_recent(driver, lookback_days: int, skip_cross_site_title_keys=None):
    """
    스마트공장 공고 수집

    수정된 흐름:
    1. 목록 페이지에서 공고 제목/공고일/접수상태 추출
    2. 상세페이지 진입 전 제목 기준 1차 필터링
    3. 날짜/접수상태 기준 확인
    4. 필터 통과한 공고만 상세페이지 진입
    5. 상세페이지에서 지원내용/첨부파일 수집
    """
    print("[스마트공장] 수집 시작")

    results = []
    seen_in_smart_factory = set()

    for target_url in SMART_FACTORY_TARGET_URLS:
        driver.get(target_url)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(2)

        # 조회 버튼 클릭
        try:
            query_btns = driver.find_elements(By.XPATH, "//*[normalize-space(text())='조회']")
            if query_btns:
                driver.execute_script("arguments[0].click();", query_btns[0])
                time.sleep(1.5)
        except Exception:
            pass

        # 1) 목록 row 텍스트 먼저 저장
        notice_row_elements = find_smart_factory_notice_rows(driver)

        list_items = []

        for row_index, row_el in enumerate(notice_row_elements):
            try:
                row_html = row_el.get_attribute("outerHTML")
                tr = BeautifulSoup(row_html, "html.parser").select_one("tr")

                parsed = parse_smart_factory_row(tr, SMART_FACTORY_BASE_URL)

                if parsed:
                    parsed["_row_index"] = row_index
                    list_items.append(parsed)

            except Exception:
                continue

        print(f"[스마트공장] 목록 후보: {len(list_items)}건")

        for idx, parsed in enumerate(list_items):
            try:
                title = parsed["title"]
                cross_site_title_key = make_cross_site_title_key_from_title(title)

                if (
                    cross_site_title_key
                    and skip_cross_site_title_keys
                    and cross_site_title_key in skip_cross_site_title_keys
                ):
                    print(f"[스마트공장 사이트간 중복제외-상세진입전] 제목={title}")
                    continue

                # -------------------------------------------------
                # 0) 상세 진입 전 1차 필터링
                # -------------------------------------------------
                if SMART_FACTORY_PRE_FILTER_BEFORE_DETAIL:
                    pre_relevance = calculate_relevance_score_v2(
                        title=title,
                        source="스마트공장",
                        body_text=parsed.get("raw_text", "")
                    )

                    if not pre_relevance["save"]:
                        print_filter_drop(
                            source="스마트공장",
                            title=title,
                            relevance=pre_relevance,
                            detail_url=parsed.get("detail_url", ""),
                            note=(parsed.get("note", "") + " | 스마트공장 필터탈락").strip(" |")
                        )
                        continue

                # -------------------------------------------------
                # 1) 상세 진입 전 날짜/접수상태 확인
                # -------------------------------------------------
                if not should_keep_smart_factory_notice(
                    parsed["announce_date"],
                    parsed["status"],
                    lookback_days
                ):
                    print(
                        f"[스마트공장 날짜제외-상세진입전] "
                        f"제목={title} | 공고일={parsed['announce_date']} | 상태={parsed['status']}"
                    )
                    continue

                # -------------------------------------------------
                # 2) 중복 여부도 상세 진입 전에 먼저 확인
                # -------------------------------------------------
                notice_no = extract_notice_no_from_note(parsed.get("note", ""))

                if notice_no:
                    inner_key = (
                        "스마트공장",
                        clean_text(notice_no),
                        normalize_title(parsed["title"]),
                        clean_text(parsed["announce_date"]),
                        clean_text(parsed["apply_period"]),
                    )
                else:
                    inner_key = (
                        "스마트공장",
                        normalize_title(parsed["title"]),
                        clean_text(parsed["announce_date"]),
                        clean_text(parsed["apply_period"]),
                        clean_text(parsed["status"]),
                    )

                if inner_key in seen_in_smart_factory:
                    print(f"[스마트공장 목록단계 중복제외] 제목={title}")
                    continue

                seen_in_smart_factory.add(inner_key)

                print(f"[스마트공장 상세진입 후보] 제목={title}")

                # -------------------------------------------------
                # 3) 여기부터 필터 통과 공고만 상세페이지 진입
                # -------------------------------------------------
                driver.get(target_url)

                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(1.5)

                try:
                    query_btns = driver.find_elements(By.XPATH, "//*[normalize-space(text())='조회']")
                    if query_btns:
                        driver.execute_script("arguments[0].click();", query_btns[0])
                        time.sleep(1.0)
                except Exception:
                    pass

                success = click_smart_factory_row_detail(
                    driver,
                    parsed.get("_row_index", idx)
                )

                if not success:
                    print(f"[스마트공장 상세 진입 실패] {title}")
                    detail = {}
                else:
                    detail = parse_smart_factory_detail_from_current_page(
                        driver,
                        fallback_url=driver.current_url
                    )

                if detail:
                    parsed["title"] = detail.get("title") or parsed["title"]
                    parsed["announce_date"] = detail.get("announce_date") or parsed["announce_date"]
                    parsed["status"] = detail.get("status") or parsed["status"]
                    parsed["ministry"] = detail.get("ministry") or parsed["ministry"]
                    parsed["agency"] = detail.get("agency") or parsed["agency"]
                    parsed["apply_period"] = detail.get("apply_period") or parsed["apply_period"]
                    parsed["deadline"] = detail.get("deadline") or parsed["deadline"]
                    parsed["detail_url"] = detail.get("detail_url") or parsed["detail_url"]
                    parsed["support_target"] = detail.get("support_target") or parsed["support_target"]
                    parsed["support_content"] = detail.get("support_content") or parsed["support_content"]
                    parsed["receipt_place"] = detail.get("receipt_place") or parsed["receipt_place"]
                    parsed["inquiry"] = detail.get("inquiry") or parsed["inquiry"]
                    parsed["attachments"] = detail.get("attachments") or parsed.get("attachments", "")
                    parsed["note"] = smart_factory_merge_note_parts(
                        parsed.get("note", ""),
                        detail.get("note", "")
                    )
                    parsed["raw_text"] = " ".join([
                        parsed.get("raw_text", ""),
                        detail.get("raw_text", "")
                    ])

                # -------------------------------------------------
                # 4) 상세페이지 반영 후 최종 점수 재계산
                # -------------------------------------------------
                relevance = calculate_relevance_score_v2(
                    title=parsed["title"],
                    source="스마트공장",
                    body_text=parsed.get("raw_text", "")
                )

                if not relevance["save"]:
                    print_filter_drop(
                        source="스마트공장",
                        title=parsed["title"],
                        relevance=relevance,
                        detail_url=parsed.get("detail_url", ""),
                        note=parsed.get("note", "")
                    )
                    continue

                matched_keywords_text = " | ".join(
                    relevance["matched_recurring"] +
                    relevance["matched_combos"] +
                    relevance["matched_keywords"][:10]
                )

                recurring_group_text = " | ".join(relevance["recurring_group_ids"])
                recurring_flag = "Y" if relevance["recurring_hit"] else "N"

                results.append(make_row(
                    source=parsed["source"],
                    status=parsed["status"],
                    announce_date=parsed["announce_date"],
                    title=parsed["title"],
                    deadline=parsed["deadline"],
                    ministry=parsed["ministry"],
                    agency=parsed["agency"],
                    apply_period=parsed["apply_period"],
                    support_target=parsed["support_target"],
                    support_content=parsed["support_content"],
                    receipt_place=parsed["receipt_place"],
                    inquiry=parsed["inquiry"],
                    detail_url=parsed["detail_url"],
                    relevance_score=str(relevance["score"]),
                    relevance_grade=relevance["grade"],
                    recurring_flag=recurring_flag,
                    recurring_group=recurring_group_text,
                    matched_keywords=matched_keywords_text,
                    note=parsed["note"],
                    attachments=parsed.get("attachments", "")
                ))

            except Exception as e:
                log_error(
                    "스마트공장",
                    "클릭상세파싱",
                    parsed.get("title", ""),
                    target_url,
                    e
                )

    print(f"[스마트공장] 전체 수집 완료: {len(results)}건")
    return results

def wait_smart_factory_detail_loaded(driver, before_url="", timeout=SMART_FACTORY_DETAIL_TIMEOUT):
    end_time = time.time() + timeout

    detail_keywords = [
        "공고번호",
        "공고명",
        "세부공고명",
        "접수기간",
        "사업개요",
        "지원규모",
        "지원조건",
        "신청자격",
        "첨부파일",
        "파일 등록 일자"
    ]

    while time.time() < end_time:
        try:
            body_text = clean_text(driver.find_element(By.TAG_NAME, "body").text)

            # Loading 화면이면 아직 성공 아님
            if "해당 화면으로 이동 중" in body_text or "Loading" in body_text:
                time.sleep(0.5)
                continue

            # 실제 상세 키워드가 있어야 성공
            if any(k in body_text for k in detail_keywords):
                return True

        except Exception:
            pass

        time.sleep(0.5)

    return False

def click_smart_factory_row_detail(driver, row_index):
    """
    스마트공장 목록에서 실제 공고 row_index번째 행을 상세페이지로 진입 시도
    """
    rows = find_smart_factory_notice_rows(driver)

    if row_index >= len(rows):
        print(f"[스마트공장 클릭 실패] row_index 초과: {row_index}")
        return False

    row = rows[row_index]
    before_url = driver.current_url

    # 실제 공고 제목 영역 우선 클릭
    clickable_candidates = []

    try:
        clickable_candidates.extend(row.find_elements(By.CSS_SELECTOR, "button.eu-btn-link"))
    except Exception:
        pass

    try:
        clickable_candidates.extend(row.find_elements(By.CSS_SELECTOR, "button.eu-btn-link span"))
    except Exception:
        pass

    try:
        clickable_candidates.extend(row.find_elements(By.CSS_SELECTOR, "a button"))
    except Exception:
        pass

    try:
        clickable_candidates.extend(row.find_elements(By.CSS_SELECTOR, "a"))
    except Exception:
        pass

    for elem in clickable_candidates:
        try:
            txt = clean_text(elem.text)

            if not txt:
                continue
            if "링크복사" in txt or "다운로드" in txt:
                continue
            if "접수중" in txt or "접수마감" in txt or "접수예정" in txt:
                continue

            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                elem
            )
            time.sleep(0.5)

            ActionChains(driver).move_to_element(elem).pause(0.3).click(elem).perform()

            if wait_smart_factory_detail_loaded(driver, before_url, timeout=SMART_FACTORY_DETAIL_TIMEOUT):
                print("[스마트공장 상세 진입 성공]")
                return True

        except Exception as e:
            print("[스마트공장 클릭 후보 실패]", str(e)[:200])
            continue

    # 마지막: row 자체 클릭
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            row
        )
        time.sleep(0.3)
        ActionChains(driver).move_to_element(row).pause(0.3).click(row).perform()

        if wait_smart_factory_detail_loaded(driver, before_url, timeout=8):
            return True

    except Exception:
        pass

    return False

def get_smart_factory_linkcopy_url_from_current_page(driver, fallback_url=""):
    """
    스마트공장 상세페이지의 '링크복사' 버튼에서 실제 공유 URL을 가져온다.
    - DOM 속성에서 1차 추출
    - navigator.clipboard.writeText 가로채기 후 버튼 클릭으로 2차 추출
    """
    fallback_url = clean_text(fallback_url)

    # 1) DOM 속성 기반 우선 추출
    try:
        soup = BeautifulSoup(driver.page_source, "html.parser")
        copied = smart_factory_extract_copy_link(soup, "")
        if copied and copied != fallback_url:
            return copied
    except Exception:
        pass

    # 2) JS clipboard 가로채기
    try:
        driver.execute_script("""
            window.__copiedText = "";
            if (navigator.clipboard && navigator.clipboard.writeText) {
              const originalWriteText = navigator.clipboard.writeText.bind(navigator.clipboard);
              navigator.clipboard.writeText = function(text) {
                window.__copiedText = text;
                return Promise.resolve(text);
              };
            }
        """)

        buttons = driver.find_elements(
            By.XPATH,
            "//*[contains(normalize-space(.), '링크복사')]"
        )

        for btn in buttons:
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});",
                    btn
                )
                time.sleep(0.2)
                ActionChains(driver).move_to_element(btn).pause(0.2).click(btn).perform()
                time.sleep(0.5)

                copied_text = clean_text(driver.execute_script("return window.__copiedText || '';"))
                if copied_text and copied_text.startswith("http"):
                    return copied_text
            except Exception:
                continue

    except Exception:
        pass

    return fallback_url

def enrich_smart_factory_attachment_urls_from_current_page(driver, attachments):
    """
    상세페이지의 다운로드 버튼에서 첨부파일 URL을 보강한다.
    기존 attachments의 url이 비어 있으면 다운로드 버튼 후보 URL을 매칭한다.
    """
    if not attachments:
        attachments = []

    download_urls = []

    try:
        soup = BeautifulSoup(driver.page_source, "html.parser")

        for node in soup.select("a, button"):
            text = clean_text(node.get_text(" ", strip=True))
            attrs = " ".join([
                str(node.get(a, ""))
                for a in [
                    "href",
                    "onclick",
                    "data-url",
                    "data-href",
                    "data-file",
                    "data-file-id",
                    "data-atch-file-id",
                    "data-atch",
                    "title"
                ]
            ])

            is_download_node = (
                "다운로드" in text
                or "download" in attrs.lower()
                or "down" in attrs.lower()
                or "atch" in attrs.lower()
                or "attach" in attrs.lower()
                or "file" in attrs.lower()
            )

            if not is_download_node:
                continue

            url = smart_factory_extract_url_from_attrs(node, SMART_FACTORY_BASE_URL)
            if url:
                download_urls.append(url)

            onclick = clean_text(node.get("onclick"))
            if onclick:
                download_urls.extend(extract_urls_from_onclick(onclick, SMART_FACTORY_BASE_URL))

    except Exception:
        pass

    download_urls = list(dict.fromkeys([u for u in download_urls if u]))

    if not attachments and download_urls:
        attachments = [
            {
                "name": "공고 첨부파일",
                "url": download_urls[0]
            }
        ]

    if attachments:
        for i, item in enumerate(attachments):
            if not item.get("url") and i < len(download_urls):
                item["url"] = download_urls[i]

    return attachments

def smart_factory_clean_attachment_name(name: str) -> str:
    """
    스마트공장 첨부파일명 정리
    - '1 / 공고 첨부파일 / 파일명.pdf / 다운로드' 형태에서 실제 파일명만 추출
    - 파일명이 없으면 빈값 반환
    """
    text = clean_text(name)
    if not text:
        return ""

    text = text.replace("\\n", "\n")
    lines = [clean_text(x) for x in text.splitlines() if clean_text(x)]

    ignore_words = {
        "순번", "항목", "첨부파일", "공고 첨부파일",
        "파일 등록 일자", "다운로드", "다운로드 불가"
    }

    candidates = []

    for line in lines:
        if line in ignore_words:
            continue
        if re.fullmatch(r"\d+", line):
            continue
        if re.match(r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}", line):
            continue

        candidates.append(line)

    # 확장자가 있는 실제 파일명 우선
    for line in candidates:
        m = re.search(
            r"([가-힣A-Za-z0-9_\-\[\]\(\)\s\.]+?\.(?:pdf|hwp|hwpx|zip|xls|xlsx|doc|docx|ppt|pptx))",
            line,
            flags=re.I
        )
        if m:
            return clean_text(m.group(1))

    return ""

def smart_factory_drain_performance_logs(driver):
    """
    Chrome performance log 비우기
    """
    try:
        driver.get_log("performance")
    except Exception:
        pass


def smart_factory_get_network_urls(driver):
    """
    Selenium performance log에서 실제 요청 URL 목록 추출
    """
    urls = []

    try:
        logs = driver.get_log("performance")
    except Exception:
        return urls

    for entry in logs:
        try:
            message = json.loads(entry.get("message", "{}")).get("message", {})
            method = message.get("method", "")
            params = message.get("params", {})

            if method == "Network.requestWillBeSent":
                req = params.get("request", {})
                url = req.get("url", "")
                if url:
                    urls.append(url)

            elif method == "Network.responseReceived":
                res = params.get("response", {})
                url = res.get("url", "")
                if url:
                    urls.append(url)

        except Exception:
            continue

    return list(dict.fromkeys(urls))


def smart_factory_is_download_url(url: str) -> bool:
    """
    스마트공장 첨부파일 다운로드 URL 판별
    - JS/CSS/이미지/React chunk/blob/data URL은 제외
    - 실제 파일 다운로드로 보이는 URL만 허용
    """
    url = clean_text(url)
    if not url:
        return False

    low = url.lower()

    # 1) 브라우저 내부 URL / JS chunk / 정적 리소스 제외
    block_tokens = [
        "blob:",
        "data:",
        "javascript:",
        ".js",
        ".css",
        ".map",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        "webpack",
        "chunk",
        "runtime",
        "bundle",
        "loader",
        "upload",
        "crypto-js",
        "jszip",
        "react",
        "static/js",
        "static/css",
        "/assets/",
    ]

    if any(t in low for t in block_tokens):
        return False

    # 2) 실제 파일 확장자면 허용
    file_exts = [
        ".pdf",
        ".hwp",
        ".hwpx",
        ".zip",
        ".xls",
        ".xlsx",
        ".doc",
        ".docx",
        ".ppt",
        ".pptx"
    ]

    if any(ext in low for ext in file_exts):
        return True

    # 3) 스마트공장 도메인의 다운로드성 API만 허용
    if "smart-factory.kr" in low:
        positive_tokens = [
            "download",
            "downfile",
            "filedown",
            "filedownload",
            "atchfile",
            "attachfile",
            "filedownload",
            "cmmnfile",
            "cmnfile"
        ]

        if any(t in low for t in positive_tokens):
            return True

    return False


def smart_factory_capture_download_url_by_click(driver, button):
    """
    상세페이지의 다운로드 버튼을 실제 클릭한 뒤 네트워크 요청에서 다운로드 URL 추출
    """
    if not button:
        return ""

    smart_factory_drain_performance_logs(driver)

    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            button
        )
        time.sleep(0.2)

        before_handles = set(driver.window_handles)

        try:
            ActionChains(driver).move_to_element(button).pause(0.2).click(button).perform()
        except Exception:
            driver.execute_script("arguments[0].click();", button)

        time.sleep(1.2)

        # 새 탭이 열리면 닫고 원래 탭으로 복귀
        after_handles = set(driver.window_handles)
        new_handles = list(after_handles - before_handles)
        if new_handles:
            current = driver.current_window_handle
            for h in new_handles:
                try:
                    driver.switch_to.window(h)
                    time.sleep(0.3)
                    new_url = driver.current_url
                    if smart_factory_is_download_url(new_url):
                        driver.close()
                        driver.switch_to.window(current)
                        return new_url
                    driver.close()
                except Exception:
                    pass
            try:
                driver.switch_to.window(current)
            except Exception:
                pass

        urls = smart_factory_get_network_urls(driver)
        candidates = []

        for u in urls:
            if not smart_factory_is_download_url(u):
                continue

            low = u.lower()

            # 혹시라도 JS/정적 리소스가 섞이면 제외
            if any(x in low for x in [".js", ".css", "chunk", "bundle", "static/js", "blob:", "data:"]):
                continue

            candidates.append(u)

        if candidates:
            return candidates[-1]

    except Exception:
        return ""

    return ""


def smart_factory_find_attachment_buttons(driver):
    """
    상세페이지 하단 첨부파일 영역의 다운로드 버튼만 추출

    기존 문제:
    - 페이지 전체에서 '다운로드' 텍스트가 들어간 요소를 전부 잡아
      같은 버튼의 부모/자식이 중복으로 잡힘
    - 이 때문에 첨부파일 2~11 placeholder가 생성됨

    수정:
    - 실제 button/a 요소만 사용
    - 화면에 보이는 요소만 사용
    - 중복 제거
    """
    buttons = []

    xpaths = [
        "//button[contains(normalize-space(.), '다운로드')]",
        "//a[contains(normalize-space(.), '다운로드')]",
    ]

    for xp in xpaths:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                try:
                    if not el.is_displayed():
                        continue

                    txt = clean_text(el.text)
                    if "다운로드" not in txt:
                        continue

                    # 너무 작은 아이콘/숨김 요소 제외
                    rect = driver.execute_script("""
                        const r = arguments[0].getBoundingClientRect();
                        return {width: r.width, height: r.height};
                    """, el)

                    if rect["width"] < 20 or rect["height"] < 15:
                        continue

                    buttons.append(el)

                except Exception:
                    continue
        except Exception:
            pass

    unique = []
    seen = set()

    for b in buttons:
        try:
            key = b.id
            if key in seen:
                continue
            seen.add(key)
            unique.append(b)
        except Exception:
            continue

    return unique

def smart_factory_extract_linkcopy_url_by_click(driver, fallback_url=""):
    """
    상세페이지 하단 '링크복사' 버튼 클릭 결과를 가져온다.
    navigator.clipboard.writeText를 가로채서 복사 URL 추출.
    """
    fallback_url = clean_text(fallback_url)

    # 1차: DOM 속성에 URL이 있으면 사용
    try:
        soup = BeautifulSoup(driver.page_source, "html.parser")
        copied = smart_factory_extract_copy_link(soup, "")
        if copied and copied.startswith("http"):
            return copied
    except Exception:
        pass

    # 2차: clipboard writeText 가로채기
    try:
        driver.execute_script("""
            window.__SMART_FACTORY_COPIED_TEXT__ = "";

            if (navigator.clipboard && navigator.clipboard.writeText) {
              const originalWriteText = navigator.clipboard.writeText.bind(navigator.clipboard);
              navigator.clipboard.writeText = function(text) {
                window.__SMART_FACTORY_COPIED_TEXT__ = text;
                return Promise.resolve(text);
              };
            }

            document.execCommand = new Proxy(document.execCommand, {
              apply: function(target, thisArg, argumentsList) {
                try {
                  const active = document.activeElement;
                  if (active && (active.value || active.textContent)) {
                    window.__SMART_FACTORY_COPIED_TEXT__ = active.value || active.textContent;
                  }
                } catch(e) {}
                return true;
              }
            });
        """)

        buttons = driver.find_elements(
            By.XPATH,
            "//*[contains(normalize-space(.), '링크복사')]"
        )

        for btn in buttons:
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});",
                    btn
                )
                time.sleep(0.2)

                try:
                    ActionChains(driver).move_to_element(btn).pause(0.2).click(btn).perform()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn)

                time.sleep(0.5)

                copied_text = clean_text(
                    driver.execute_script("return window.__SMART_FACTORY_COPIED_TEXT__ || '';")
                )

                if copied_text and copied_text.startswith("http"):
                    return copied_text

            except Exception:
                continue

    except Exception:
        pass

    return fallback_url


def smart_factory_enrich_attachments_by_click(driver, attachments):
    """
    상세페이지 하단 다운로드 버튼을 클릭해서 첨부파일 URL 보강

    중요 수정:
    - attachments가 이미 1개면 1개만 유지
    - 다운로드 버튼이 여러 개 잡혀도 '첨부파일 2, 3...'을 새로 만들지 않음
    - 실제 파일명이 확인된 첨부파일에만 URL을 매칭
    """
    attachments = attachments or []

    cleaned = []
    seen = set()

    for a in attachments:
        name = smart_factory_clean_attachment_name(a.get("name", ""))
        url = clean_text(a.get("url", ""))

        if not name:
            continue

        if name in seen:
            continue

        seen.add(name)
        cleaned.append({
            "name": name,
            "url": url
        })

    attachments = cleaned

    # 실제 파일명이 하나도 없으면 placeholder 생성하지 않고 빈 리스트 반환
    if not attachments:
        return []

    buttons = smart_factory_find_attachment_buttons(driver)

    if not buttons:
        return attachments

    # 첨부파일 개수만큼만 다운로드 버튼 클릭
    max_count = min(len(attachments), len(buttons))

    for i in range(max_count):
        if attachments[i].get("url"):
            continue

        url = smart_factory_capture_download_url_by_click(driver, buttons[i])

        if url:
            attachments[i]["url"] = url

    return attachments

def list_download_files(download_dir):
    """
    다운로드 폴더의 현재 파일 목록 반환
    .crdownload 임시파일은 제외
    """
    os.makedirs(download_dir, exist_ok=True)

    files = []

    for name in os.listdir(download_dir):
        path = os.path.join(download_dir, name)

        if not os.path.isfile(path):
            continue

        if name.endswith(".crdownload"):
            continue

        files.append(path)

    return set(files)


def wait_for_new_downloads(download_dir, before_files, timeout=30):
    """
    다운로드 버튼 클릭 후 새로 생성된 파일이 완료될 때까지 대기
    """
    os.makedirs(download_dir, exist_ok=True)

    end_time = time.time() + timeout

    while time.time() < end_time:
        # Chrome 다운로드 중 임시파일 확인
        temp_files = [
            f for f in os.listdir(download_dir)
            if f.endswith(".crdownload")
        ]

        current_files = list_download_files(download_dir)
        new_files = current_files - before_files

        if new_files and not temp_files:
            return sorted(list(new_files))

        time.sleep(0.5)

    current_files = list_download_files(download_dir)
    return sorted(list(current_files - before_files))


def smart_factory_open_download_modal(driver):
    """
    스마트공장 상세페이지 첨부파일 영역의 다운로드 버튼을 클릭해서
    파일 다운로드 모달을 연다.
    """
    # 상세페이지 하단의 실제 다운로드 버튼 우선
    buttons = driver.find_elements(
        By.XPATH,
        "//button[contains(normalize-space(.), '다운로드')] | //a[contains(normalize-space(.), '다운로드')]"
    )

    real_buttons = []

    for btn in buttons:
        try:
            if not btn.is_displayed():
                continue

            txt = clean_text(btn.text)

            if "다운로드" not in txt:
                continue

            rect = driver.execute_script("""
                const r = arguments[0].getBoundingClientRect();
                return {x: r.x, y: r.y, width: r.width, height: r.height};
            """, btn)

            if rect["width"] < 30 or rect["height"] < 15:
                continue

            real_buttons.append((rect["y"], btn))

        except Exception:
            continue

    if not real_buttons:
        return False

    # 화면 아래쪽 첨부파일 다운로드 버튼 우선 클릭
    real_buttons.sort(key=lambda x: x[0], reverse=True)

    for _, btn in real_buttons:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.3)

            try:
                ActionChains(driver).move_to_element(btn).pause(0.2).click(btn).perform()
            except Exception:
                driver.execute_script("arguments[0].click();", btn)

            # 모달 대기
            end_time = time.time() + 8

            while time.time() < end_time:
                body_text = clean_text(driver.find_element(By.TAG_NAME, "body").text)

                if "파일 다운로드" in body_text and ("전체 다운로드" in body_text or "다운로드" in body_text):
                    return True

                time.sleep(0.3)

        except Exception:
            continue

    return False


def smart_factory_get_modal_file_names(driver):
    """
    파일 다운로드 모달 안의 파일명 목록 추출
    """
    body_text = clean_text(driver.find_element(By.TAG_NAME, "body").text)

    file_names = re.findall(
        r"([가-힣A-Za-z0-9_\-\[\]\(\)\s\.]+?\.(?:pdf|hwp|hwpx|zip|xls|xlsx|doc|docx|ppt|pptx))",
        body_text,
        flags=re.I
    )

    cleaned = []

    for name in file_names:
        name = clean_text(name)

        if name and name not in cleaned:
            cleaned.append(name)

    return cleaned


def smart_factory_select_all_files_in_modal(driver):
    """
    파일 다운로드 모달에서 전체 체크박스 선택
    """
    try:
        # 1차: 전체 선택 체크박스 시도
        checkboxes = driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")

        for cb in checkboxes:
            try:
                if not cb.is_displayed():
                    continue

                selected = cb.is_selected()

                if not selected:
                    driver.execute_script("arguments[0].click();", cb)
                    time.sleep(0.2)

            except Exception:
                continue

        return True

    except Exception:
        return False


def smart_factory_click_modal_download(driver):
    """
    파일 다운로드 모달에서 전체 다운로드 또는 다운로드 버튼 클릭
    """
    button_xpaths = [
        "//button[normalize-space(.)='전체 다운로드']",
        "//a[normalize-space(.)='전체 다운로드']",
        "//button[contains(normalize-space(.), '전체 다운로드')]",
        "//a[contains(normalize-space(.), '전체 다운로드')]",
        "//button[normalize-space(.)='다운로드']",
        "//a[normalize-space(.)='다운로드']",
        "//button[contains(normalize-space(.), '다운로드')]",
        "//a[contains(normalize-space(.), '다운로드')]",
    ]

    for xp in button_xpaths:
        try:
            buttons = driver.find_elements(By.XPATH, xp)

            for btn in buttons:
                try:
                    if not btn.is_displayed():
                        continue

                    txt = clean_text(btn.text)

                    # 상세페이지의 다운로드 버튼이 아니라 모달 안 버튼만 클릭해야 함
                    body_text = clean_text(driver.find_element(By.TAG_NAME, "body").text)
                    if "파일 다운로드" not in body_text:
                        continue

                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                    time.sleep(0.2)

                    try:
                        ActionChains(driver).move_to_element(btn).pause(0.2).click(btn).perform()
                    except Exception:
                        driver.execute_script("arguments[0].click();", btn)

                    return True

                except Exception:
                    continue

        except Exception:
            continue

    return False


def smart_factory_close_download_modal(driver):
    """
    파일 다운로드 모달 닫기
    """
    close_xpaths = [
        "//button[normalize-space(.)='닫기']",
        "//a[normalize-space(.)='닫기']",
        "//button[contains(@class, 'close')]",
        "//*[@aria-label='Close']",
        "//*[contains(normalize-space(.), '×')]",
    ]

    for xp in close_xpaths:
        try:
            buttons = driver.find_elements(By.XPATH, xp)

            for btn in buttons:
                try:
                    if not btn.is_displayed():
                        continue

                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.3)
                    return True

                except Exception:
                    continue

        except Exception:
            continue

    return False

def smart_factory_extract_urls_from_element_attrs_web(el):
    """
    Selenium WebElement의 href / onclick / data-* 속성에서
    스마트공장 다운로드 URL 후보를 최대한 추출한다.
    """
    urls = []

    attrs = [
        "href",
        "onclick",
        "data-url",
        "data-href",
        "data-link",
        "data-file",
        "data-file-id",
        "data-atch-file-id",
        "data-atch",
        "data-download",
        "title",
    ]

    raw_values = []

    for attr in attrs:
        try:
            value = el.get_attribute(attr)
            if value:
                raw_values.append(str(value))
        except Exception:
            pass

    joined = html.unescape(" ".join(raw_values))

    # 1) 절대 URL
    urls.extend(re.findall(r"https?://[^\s'\"<>;)]+", joined))

    # 2) 상대 URL
    rels = re.findall(r"['\"](\/[^'\"]+)['\"]", joined)
    for rel in rels:
        urls.append(urljoin(SMART_FACTORY_BASE_URL, rel))

    # 3) onclick 파라미터 안의 URL성 문자열
    params = re.findall(r"['\"]([^'\"]+)['\"]", joined)
    for p in params:
        p = clean_text(p)
        if not p:
            continue

        if p.startswith("http"):
            urls.append(p)
        elif p.startswith("/"):
            urls.append(urljoin(SMART_FACTORY_BASE_URL, p))
        elif any(token in p.lower() for token in ["download", "file", "atch", "attach", "down"]):
            urls.append(urljoin(SMART_FACTORY_BASE_URL, p))

    cleaned = []

    for url in urls:
        url = clean_text(url)
        if not url:
            continue

        # 정적 리소스 제외
        low = url.lower()
        if any(x in low for x in [".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", "blob:", "data:"]):
            continue

        if url not in cleaned:
            cleaned.append(url)

    return cleaned


def smart_factory_get_modal_rows(driver):
    """
    스마트공장 파일 다운로드 모달 안의 파일 row 후보를 찾는다.
    """
    row_candidates = []

    selectors = [
        ".ant-modal tr",
        ".ant-modal-body tr",
        "[role='dialog'] tr",
        ".ant-modal li",
        ".ant-modal-body li",
        "[role='dialog'] li",
        ".ant-modal div",
        ".ant-modal-body div",
    ]

    for selector in selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, selector)
        except Exception:
            elems = []

        for el in elems:
            try:
                if not el.is_displayed():
                    continue

                text = clean_text(el.text)
                if not text:
                    continue

                if not re.search(r"\.(pdf|hwp|hwpx|zip|xls|xlsx|doc|docx|ppt|pptx)", text, flags=re.I):
                    continue

                row_candidates.append(el)

            except Exception:
                continue

    unique = []
    seen = set()

    for el in row_candidates:
        try:
            text = clean_text(el.text)
            key = normalize_for_match(text)

            if key in seen:
                continue

            seen.add(key)
            unique.append(el)

        except Exception:
            continue

    return unique


def smart_factory_extract_modal_attachments_web(driver):
    """
    스마트공장 첨부파일 모달에서 파일명 + 다운로드 URL 후보를 최대한 추출한다.

    주의:
    - 실제 파일 다운로드는 하지 않음
    - URL이 HTML/onclick/network에 노출되는 경우에만 url 값이 채워짐
    - 세션 기반 blob/POST 다운로드면 url은 빈값일 수 있음
    """
    attachments = []

    opened = smart_factory_open_download_modal(driver)

    if not opened:
        return []

    time.sleep(0.8)

    modal_rows = smart_factory_get_modal_rows(driver)

    if not modal_rows:
        # row 구조가 안 잡힐 경우 body 텍스트에서 파일명만 추출
        file_names = smart_factory_get_modal_file_names(driver)

        smart_factory_close_download_modal(driver)

        return [
            {
                "name": name,
                "url": ""
            }
            for name in file_names
        ]

    for row in modal_rows:
        try:
            row_text = clean_text(row.text)

            file_names = re.findall(
                r"([가-힣A-Za-z0-9_\-\[\]\(\)\s\.]+?\.(?:pdf|hwp|hwpx|zip|xls|xlsx|doc|docx|ppt|pptx))",
                row_text,
                flags=re.I
            )

            if not file_names:
                continue

            file_name = smart_factory_clean_attachment_name(file_names[0])

            if not file_name:
                continue

            url_candidates = []

            # 1) row 자체 속성 확인
            url_candidates.extend(
                smart_factory_extract_urls_from_element_attrs_web(row)
            )

            # 2) row 내부 a/button/input/span 속성 확인
            try:
                children = row.find_elements(By.CSS_SELECTOR, "a, button, input, span")
            except Exception:
                children = []

            for child in children:
                url_candidates.extend(
                    smart_factory_extract_urls_from_element_attrs_web(child)
                )

            # 3) 실제 다운로드 URL로 보이는 것 우선 선택
            download_url = ""

            for url in url_candidates:
                if smart_factory_is_download_url(url):
                    download_url = url
                    break

            # 4) URL이 직접 안 보이면 해당 row 안의 다운로드 버튼 클릭 후 네트워크 로그 확인
            if not download_url:
                try:
                    download_buttons = row.find_elements(
                        By.XPATH,
                        ".//button[contains(normalize-space(.), '다운로드')] | .//a[contains(normalize-space(.), '다운로드')]"
                    )

                    for btn in download_buttons:
                        if not btn.is_displayed():
                            continue

                        captured_url = smart_factory_capture_download_url_by_click(driver, btn)

                        if captured_url:
                            download_url = captured_url
                            break

                except Exception:
                    pass

            attachments.append({
                "name": file_name,
                "url": download_url or ""
            })

        except Exception:
            continue

    smart_factory_close_download_modal(driver)

    # 중복 제거
    cleaned = []
    seen = set()

    for item in attachments:
        name = smart_factory_clean_attachment_name(item.get("name", ""))
        url = clean_text(item.get("url", ""))

        if not name:
            continue

        key = name

        if key in seen:
            continue

        seen.add(key)
        cleaned.append({
            "name": name,
            "url": url
        })

    # 모든 파일 url이 비어 있으면 모달 하단 다운로드 버튼 기준으로 마지막 확인
    if cleaned and all(not x.get("url") for x in cleaned):
        captured = smart_factory_capture_modal_download_request(driver)

        print(f"[스마트공장 첨부파일 다운로드 요청 확인] {captured}")

        if captured.get("url"):
            # 개별 파일 URL이 아니라 전체 다운로드 요청 URL일 수 있으므로 첫 파일에만 표시
            cleaned[0]["url"] = captured["url"]
            cleaned[0]["download_note"] = captured.get("reason", "")
    return cleaned

def smart_factory_capture_modal_download_request(driver):
    """
    스마트공장 첨부파일 모달에서 다운로드 버튼 클릭 시 발생하는
    네트워크 요청 URL을 최대한 확인한다.

    주의:
    - 실제 재사용 가능한 GET URL이 나오면 반환
    - POST/blob/session 방식이면 URL을 웹앱 다운로드 링크로 쓰기 어려움
    """
    smart_factory_drain_performance_logs(driver)

    try:
        smart_factory_select_all_files_in_modal(driver)
        time.sleep(0.3)

        clicked = smart_factory_click_modal_download(driver)
        if not clicked:
            return {
                "url": "",
                "method": "",
                "reason": "모달 다운로드 버튼 클릭 실패"
            }

        time.sleep(2.0)

        urls = smart_factory_get_network_urls(driver)

        candidates = []
        for url in urls:
            if smart_factory_is_download_url(url):
                candidates.append(url)

        candidates = list(dict.fromkeys(candidates))

        if candidates:
            return {
                "url": candidates[-1],
                "method": "GET_OR_UNKNOWN",
                "reason": "네트워크 로그에서 다운로드 URL 후보 확인"
            }

        return {
            "url": "",
            "method": "",
            "reason": "네트워크 로그에 재사용 가능한 다운로드 URL 없음"
        }

    except Exception as e:
        return {
            "url": "",
            "method": "",
            "reason": f"캡처 실패: {str(e)[:200]}"
        }

def smart_factory_download_attachments_from_modal(driver, download_dir=SMART_FACTORY_DOWNLOAD_DIR):
    """
    스마트공장 상세페이지 첨부파일 다운로드 처리

    반환 예:
    [
        {
            "name": "260416_2026년도_자율형공장_구축_지원사업_2차_공고.pdf",
            "url": "",
            "local_path": "C:/.../downloads/smart_factory/파일명.pdf"
        }
    ]
    """
    os.makedirs(download_dir, exist_ok=True)

    opened = smart_factory_open_download_modal(driver)

    if not opened:
        return []

    modal_file_names = smart_factory_get_modal_file_names(driver)

    before_files = list_download_files(download_dir)

    smart_factory_select_all_files_in_modal(driver)

    clicked = smart_factory_click_modal_download(driver)

    if not clicked:
        smart_factory_close_download_modal(driver)
        return [
            {
                "name": name,
                "url": "",
                "local_path": ""
            }
            for name in modal_file_names
        ]

    downloaded_files = wait_for_new_downloads(
        download_dir=download_dir,
        before_files=before_files,
        timeout=40
    )

    smart_factory_close_download_modal(driver)

    results = []

    if downloaded_files:
        for path in downloaded_files:
            results.append({
                "name": os.path.basename(path),
                "url": "",
                "local_path": path
            })

        return results

    # 다운로드가 안 됐지만 모달에서 파일명은 확인된 경우
    return [
        {
            "name": name,
            "url": "",
            "local_path": ""
        }
        for name in modal_file_names
    ]
