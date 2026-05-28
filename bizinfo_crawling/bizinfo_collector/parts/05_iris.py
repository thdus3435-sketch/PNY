# =========================================================
# 9) IRIS
# =========================================================
def click_iris_status_tab(driver, status_label: str):
    xpath_candidates = [
        f"//*[normalize-space(text())='{status_label}']",
        f"//a[normalize-space(text())='{status_label}']",
        f"//button[normalize-space(text())='{status_label}']",
        f"//li[normalize-space(.)='{status_label}']",
        f"//*[contains(normalize-space(.), '{status_label}')]",
    ]

    for xpath in xpath_candidates:
        elems = driver.find_elements(By.XPATH, xpath)
        for elem in elems:
            try:
                driver.execute_script("arguments[0].click();", elem)
                return True
            except Exception:
                continue
    return False


def wait_iris_list_refresh(driver, before_text: str = "", timeout: int = 10):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            body_text = clean_text(driver.find_element(By.TAG_NAME, "body").text)
            if body_text and body_text != before_text:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def extract_iris_apply_period(text: str) -> str:
    text = clean_text(text)
    patterns = [
        r"(개념계획서|신청용 연구개발계획서)?\s*(20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s*~\s*20\d{2}[./-]\d{1,2}[./-]\d{1,2})",
        r"(20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s*~\s*20\d{2}[./-]\d{1,2}[./-]\d{1,2})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.S)
        if m:
            return clean_text(m.group(0))
    return ""


def extract_iris_notice_no(text: str) -> str:
    text = clean_text(text)
    patterns = [
        r"공고번호\s*[:：]?\s*([^\n]+)",
        r"공고\s*제\s*([^\n]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return clean_text(m.group(1))
    return ""


def extract_iris_status(text: str, fallback_status: str = "") -> str:
    text = clean_text(text)
    for candidate in ["접수예정", "접수중", "공고예고", "마감", "종료"]:
        if candidate in text:
            return candidate
    return fallback_status


def guess_iris_title(lines):
    ignore_keywords = [
        "공고번호", "공고일자", "공모유형", "공고상태", "접수예정", "접수중",
        "마감", "종료", "현재 페이지", "전체", "검색", "정렬", "한국연구재단"
    ]

    candidates = []
    for line in lines:
        s = clean_text(line)
        if not s:
            continue
        if any(k in s for k in ignore_keywords):
            continue
        if len(s) < 5:
            continue
        candidates.append(s)

    if not candidates:
        return ""

    candidates = sorted(candidates, key=lambda x: len(x), reverse=True)
    return candidates[0]


def guess_iris_agency(lines, full_text: str) -> str:
    full_text = clean_text(full_text)

    # 1) '부처 > 기관' 구조 우선 추출
    m = re.search(
        r"(과학기술정보통신부|산업통상자원부|중소벤처기업부|국토교통부|해양수산부|환경부|고용노동부|교육부)\s*>\s*([^\n>]+)",
        full_text
    )
    if m:
        return clean_text(m.group(2))

    # 2) 줄 단위 기관명만 허용
    for line in lines:
        s = clean_text(line)
        if not s:
            continue

        if "\n" in s:
            continue

        if len(s) > 30:
            continue

        if any(bad in s for bad in ["공고", "과제", "접수", "페이지", "검색", "전체", "공고번호", "공고일자"]):
            continue

        if any(word in s for word in ["재단", "진흥원", "연구원", "평가원", "기술원", "센터", "협회"]):
            return s

    return ""


def guess_iris_ministry(lines, full_text: str) -> str:
    full_text = clean_text(full_text)
    m = re.search(r"([가-힣A-Za-z0-9·\(\)\s]+)\s*>\s*([가-힣A-Za-z0-9·\(\)\s]+)", full_text)
    if m:
        return clean_text(m.group(1))
    return ""


def find_iris_item_elements(driver):
    """
    IRIS 목록에서 실제 공고 카드/행만 추출
    - 접수예정/접수중 탭, 메뉴, 퀵메뉴 제외
    - 공고번호/공고일자/제목이 포함된 실제 공고 블록만 사용
    """
    css_candidates = [
        "ul li",
        ".list li",
        ".board_list li",
        ".contents li",
        ".resultList li",
        ".bbs_list li",
        ".list_wrap li",
        ".content ul li",
        "div"
    ]

    found = []

    for css in css_candidates:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, css)

            for elem in elems:
                try:
                    txt = clean_text(elem.text)

                    if not txt:
                        continue

                    # 너무 짧은 탭/버튼 제외
                    if txt in ["접수예정", "접수중", "공고예고", "마감", "종료"]:
                        continue

                    # 상단/메뉴/퀵메뉴 제외
                    exclude_ui_words = [
                        "IRIS 소개",
                        "사업정보",
                        "알림·소식",
                        "참여소통",
                        "통합검색",
                        "로그인",
                        "회원가입",
                        "Quick Menu",
                        "QUICK MENU",
                        "국가연구자번호 찾기",
                        "고객상담챗봇"
                    ]

                    if any(w in txt for w in exclude_ui_words):
                        continue

                    # 실제 공고 카드 조건
                    has_notice_meta = (
                        "공고번호" in txt or
                        "공고일자" in txt or
                        "공모유형" in txt or
                        "접수기간" in txt
                    )

                    has_status = (
                        "접수예정" in txt or
                        "접수중" in txt or
                        "공고예고" in txt
                    )

                    # 공고 제목으로 보이는 긴 텍스트 포함 여부
                    has_title_like = bool(re.search(r"20\d{2}년.+공고", txt))

                    if not (has_notice_meta and has_status and has_title_like):
                        continue

                    found.append(elem)

                except Exception:
                    continue

        except Exception:
            continue

    unique = []
    seen = set()

    for elem in found:
        try:
            txt = clean_text(elem.text)
            key = normalize_title(txt[:200])

            if key in seen:
                continue

            seen.add(key)
            unique.append(elem)

        except Exception:
            continue

    return unique

def iris_abs_url(raw_url):
    raw_url = clean_text(raw_url)

    if not raw_url:
        return ""

    if raw_url.startswith("http://") or raw_url.startswith("https://"):
        return raw_url

    return urljoin("https://www.iris.go.kr", raw_url)


def is_iris_attachment_file_name(text):
    text = clean_text(text)
    return re.search(
        r"\.(pdf|hwp|hwpx|zip|xls|xlsx|doc|docx|ppt|pptx)$",
        text,
        flags=re.I
    ) is not None

def extract_iris_urls_from_node(node):
    urls = []

    attrs = []

    for attr in [
        "href",
        "onclick",
        "data-url",
        "data-href",
        "data-link",
        "data-file",
        "data-file-id",
        "data-atch-file-id",
        "title"
    ]:
        value = node.get(attr)
        if value:
            attrs.append(str(value))

    joined = html.unescape(" ".join(attrs))

    # 절대 URL
    urls.extend(re.findall(r"https?://[^\s'\"<>;)]+", joined))

    # 따옴표 안 상대 URL
    rels = re.findall(r"['\"](\/[^'\"]+)['\"]", joined)
    for rel in rels:
        urls.append(iris_abs_url(rel))

    href = clean_text(node.get("href", ""))
    if href and href != "#" and not href.lower().startswith("javascript"):
        urls.append(iris_abs_url(href))

    return list(dict.fromkeys([u for u in urls if u]))

def extract_value_after_label(lines, label):
    """
    IRIS 상세페이지처럼
    소관부처
    중소벤처기업부
    전문기관
    중소기업기술정보진흥원
    구조에서 label 다음 줄 값을 추출
    """
    label = clean_text(label)

    for i, line in enumerate(lines):
        if clean_text(line) == label:
            for j in range(i + 1, min(i + 4, len(lines))):
                value = clean_text(lines[j])

                if not value:
                    continue

                # 다음 라벨이면 값 없음
                if value in [
                    "소관부처", "전문기관", "공고번호", "공고명",
                    "공고일자", "재공고 여부", "접수기간",
                    "사업담당자 연락처", "접수 개시 여부"
                ]:
                    return ""

                return value

    return ""

def is_valid_iris_org_value(value: str) -> bool:
    value = clean_text(value)

    if not value:
        return False

    # 부처/기관명 치고 너무 길면 잘못 추출된 것
    if len(value) > 40:
        return False

    # 상세 본문 라벨이 섞이면 잘못된 값
    bad_tokens = [
        "전문기관",
        "공고번호",
        "공고명",
        "공고일자",
        "접수기간",
        "사업담당자",
        "접수",
        "공고문",
        "첨부파일",
        "신청하기",
        "목록",
        "링크공유",
    ]

    if any(token in value for token in bad_tokens):
        return False

    return True


def clean_iris_org_value(value: str) -> str:
    value = clean_text(value)
    return value if is_valid_iris_org_value(value) else ""

def extract_iris_apply_period_from_detail(lines, one_text):
    """
    IRIS 상세페이지 접수기간 추출
    - 2026-06-01 ~ 2026-06-15
    - 2026.06.01 00:00 ~ 2026.06.15 18:00
    모두 대응
    """
    # 1) 라벨 다음 줄 우선
    raw = extract_value_after_label(lines, "접수기간")

    if raw:
        period = clean_text(raw)
    else:
        period = ""

    # 2) 한 줄 텍스트에서 보조 추출
    if not period:
        patterns = [
            r"접수기간\s+((?:20\d{2}[./-]\d{1,2}[./-]\d{1,2})(?:\s+\d{1,2}:\d{2})?\s*~\s*(?:20\d{2}[./-]\d{1,2}[./-]\d{1,2})(?:\s+\d{1,2}:\d{2})?)",
            r"((?:20\d{2}[./-]\d{1,2}[./-]\d{1,2})(?:\s+\d{1,2}:\d{2})?\s*~\s*(?:20\d{2}[./-]\d{1,2}[./-]\d{1,2})(?:\s+\d{1,2}:\d{2})?)",
        ]

        for pattern in patterns:
            m = re.search(pattern, one_text)
            if m:
                period = clean_text(m.group(1))
                break

    return period

def extract_iris_detail_fields(detail_text: str, title: str = "") -> dict:
    """
    IRIS 상세페이지 body text에서 핵심 요약 정보를 추출한다.
    """
    detail_text = clean_text(detail_text)
    title = clean_text(title)

    result = {
        "ministry": "",
        "agency": "",
        "notice_no": "",
        "announce_date": "",
        "apply_period": "",
        "deadline": "",
        "inquiry": "",
        "support_target": "",
        "support_content": "",
    }

    if not detail_text:
        return result

    lines = [
        clean_text(x)
        for x in detail_text.splitlines()
        if clean_text(x)
    ]

    one = re.sub(r"\s+", " ", detail_text)

    # 1) 소관부처
    ministry_by_line = extract_value_after_label(lines, "소관부처")
    result["ministry"] = clean_iris_org_value(ministry_by_line)

    if not result["ministry"]:
        m = re.search(r"소관부처\s+(.+?)\s+전문기관", one)
        if m:
            result["ministry"] = clean_iris_org_value(m.group(1))

    # 2) 전문기관
    agency_by_line = extract_value_after_label(lines, "전문기관")
    result["agency"] = clean_iris_org_value(agency_by_line)

    if not result["agency"]:
        m = re.search(r"전문기관\s+(.+?)\s+공고번호", one)
        if m:
            result["agency"] = clean_iris_org_value(m.group(1))

    # 3) 공고번호
    notice_no_by_line = extract_value_after_label(lines, "공고번호")
    if notice_no_by_line:
        result["notice_no"] = notice_no_by_line
    else:
        m = re.search(r"공고번호\s+(.+?)\s+공고명", one)
        if m:
            result["notice_no"] = clean_text(m.group(1))

    # 4) 공고일자
    announce_date_by_line = extract_value_after_label(lines, "공고일자")
    if announce_date_by_line:
        result["announce_date"] = normalize_date(announce_date_by_line)

    if not result["announce_date"]:
        m = re.search(r"공고일자\s+(20\d{2}[./-]\d{1,2}[./-]\d{1,2})", one)
        if m:
            result["announce_date"] = normalize_date(m.group(1))

    # 5) 접수기간 / 마감일
    apply_period = extract_iris_apply_period_from_detail(lines, one)
    result["apply_period"] = clean_text(apply_period)

    if result["apply_period"]:
        result["deadline"] = extract_deadline_from_period(result["apply_period"])

    # 6) 문의처
    inquiry_by_line = extract_value_after_label(lines, "사업담당자 연락처")
    if inquiry_by_line:
        result["inquiry"] = inquiry_by_line
    else:
        m = re.search(
            r"사업담당자\s*연락처\s+(.+?)\s+접수\s*개시\s*여부",
            one
        )
        if m:
            result["inquiry"] = clean_text(m.group(1))

    # 7) 지원내용
    support = clean_iris_support_content(detail_text, title)

    support_lines = []
    for line in support.splitlines():
        line = clean_text(line)

        if not line:
            continue
        if title and normalize_for_match(line) == normalize_for_match(title):
            continue
        if re.fullmatch(r"20\d{2}년\s*\d{1,2}월\s*\d{1,2}일", line):
            continue
        if "산업통상부장관" in line:
            continue
        if "신규지원 대상과제 공고" in line and len(line) < 40:
            continue

        support_lines.append(line)

    result["support_content"] = clean_text("\n".join(support_lines))

    return result

def update_existing_notice_rows_by_unique_key(new_sheet, candidate_rows):
    """
    신규공고 시트에 이미 존재하는 공고라면,
    새로 수집한 상세링크/첨부파일/매칭키워드/비고를 기존 행에 업데이트한다.

    목적:
    - 과거에 IRIS 목록 URL로 잘못 저장된 상세링크를
      새로 추출한 정상 detail_url로 보정
    - 중복제거 때문에 새 링크가 시트에 반영되지 않는 문제 해결
    """
    if not candidate_rows:
        return 0

    values = new_sheet.get_all_values()
    if len(values) <= 1:
        return 0

    header = values[0]
    body_rows = values[1:]

    existing_map = {}

    for row_num, row in enumerate(body_rows, start=2):
        try:
            link_key, unique_key = make_notice_keys_from_raw_row(row)
            if unique_key:
                existing_map[unique_key] = row_num
        except Exception:
            continue

    updated_count = 0

    for new_row in candidate_rows:
        try:
            new_link_key, new_unique_key = make_notice_keys_from_raw_row(new_row)

            if not new_unique_key:
                continue

            target_row_num = existing_map.get(new_unique_key)
            if not target_row_num:
                continue

            # 새로 수집한 상세링크가 비어있으면 업데이트하지 않음
            new_detail_url = clean_text(safe_get(new_row, 12))
            if not new_detail_url:
                continue

            # IRIS 목록 URL이면 업데이트하지 않음
            if new_detail_url == IRIS_URL:
                continue

            # 기존 행 전체를 새 row로 업데이트
            end_col_num = len(NEW_NOTICE_HEADERS)
            end_col = ""
            n = end_col_num
            while n > 0:
                n, rem = divmod(n - 1, 26)
                end_col = chr(65 + rem) + end_col

            new_sheet.update(
                range_name=f"A{target_row_num}:{end_col}{target_row_num}",
                values=[new_row],
                value_input_option="USER_ENTERED"
            )

            updated_count += 1

            print(
                f"[기존공고 업데이트] row={target_row_num} | "
                f"title={safe_get(new_row, 1)} | detail_url={new_detail_url}"
            )

        except Exception as e:
            log_error(
                "GoogleSheet",
                "기존공고업데이트",
                safe_get(new_row, 1),
                safe_get(new_row, 12),
                e
            )

    if updated_count:
        print(f"[신규공고] 기존 행 상세링크/첨부파일 업데이트 완료: {updated_count}건")

    return updated_count
def iris_clear_performance_logs(driver):
    """
    Chrome performance log 비우기
    - 다운로드 버튼 클릭 전에 이전 네트워크 로그를 제거해야
      클릭 직후 발생한 다운로드 URL만 비교적 정확히 잡을 수 있음
    """
    try:
        driver.get_log("performance")
    except Exception:
        pass


def iris_get_recent_network_urls(driver):
    """
    Selenium performance log에서 최근 네트워크 요청/응답 URL 추출
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


def iris_find_attachment_click_targets(driver):
    """
    IRIS 상세페이지에서 첨부파일명과 클릭 가능한 요소를 함께 찾음
    """
    targets = []
    seen_names = set()

    file_xpath = (
        "//*[contains(text(),'.hwp') or contains(text(),'.hwpx') "
        "or contains(text(),'.pdf') or contains(text(),'.zip') "
        "or contains(text(),'.xls') or contains(text(),'.xlsx') "
        "or contains(text(),'.doc') or contains(text(),'.docx') "
        "or contains(text(),'.ppt') or contains(text(),'.pptx')]"
    )

    try:
        elements = driver.find_elements(By.XPATH, file_xpath)
    except Exception:
        elements = []

    for el in elements:
        try:
            raw_text = clean_text(el.text)

            if not raw_text:
                continue

            file_names = re.findall(
                r"([가-힣A-Za-z0-9_\-\[\]\(\)\s\.·ㆍ&]+?\.(?:pdf|hwp|hwpx|zip|xls|xlsx|doc|docx|ppt|pptx))",
                raw_text,
                flags=re.I
            )

            if not file_names:
                continue

            for raw_name in file_names:
                file_name = clean_text(raw_name)
                file_name = re.sub(
                    r"\([0-9,.]+\s*(KB|MB|GB)\)",
                    "",
                    file_name,
                    flags=re.I
                )
                file_name = clean_text(file_name)

                if not file_name:
                    continue

                if file_name in seen_names:
                    continue

                clickable = el

                for xp in [
                    "./ancestor-or-self::a[1]",
                    "./ancestor-or-self::button[1]",
                    "./ancestor-or-self::li[1]",
                    "./ancestor-or-self::div[1]",
                ]:
                    try:
                        cand = el.find_element(By.XPATH, xp)
                        if cand:
                            clickable = cand
                            break
                    except Exception:
                        pass

                seen_names.add(file_name)
                targets.append({
                    "name": file_name,
                    "element": clickable
                })

        except Exception:
            continue

    return targets

def iris_extract_direct_download_url_from_element(element):
    """
    클릭 전 요소의 href / onclick / data-* 속성에서 직접 다운로드 URL 후보 추출
    """
    attrs = [
        "href",
        "onclick",
        "data-url",
        "data-href",
        "data-link",
        "data-file",
        "data-file-id",
        "data-atch-file-id",
        "title",
    ]

    texts = []

    for attr in attrs:
        try:
            val = element.get_attribute(attr)
            if val:
                texts.append(str(val))
        except Exception:
            pass

    joined = html.unescape(" ".join(texts))

    urls = []

    # 절대 URL
    urls.extend(re.findall(r"https?://[^\s'\"<>;)]+", joined))

    # 따옴표 안 상대 URL
    rels = re.findall(r"['\"](\/[^'\"]+)['\"]", joined)
    for rel in rels:
        urls.append(iris_urljoin(rel))

    # href가 직접 상대경로인 경우
    try:
        href = clean_text(element.get_attribute("href"))
        if href and href != "#" and not href.lower().startswith("javascript"):
            urls.append(iris_urljoin(href))
    except Exception:
        pass

    urls = list(dict.fromkeys([u for u in urls if u]))

    # 실제 다운로드 URL만 남김
    for url in urls:
        if is_iris_real_download_url(url) or is_iris_possible_download_url(url):
            return url

    return ""


def iris_click_and_capture_download_url(driver, element, wait_sec=2.0):
    """
    첨부파일 요소를 실제 클릭한 뒤 발생한 네트워크 요청에서 다운로드 URL 추출
    """
    if not element:
        return ""

    iris_clear_performance_logs(driver)

    before_handles = set(driver.window_handles)

    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            element
        )
        time.sleep(0.3)

        try:
            ActionChains(driver).move_to_element(element).pause(0.2).click(element).perform()
        except Exception:
            driver.execute_script("arguments[0].click();", element)

        time.sleep(wait_sec)

        # 새 탭이 열리면 URL 확인 후 닫기
        try:
            after_handles = set(driver.window_handles)
            new_handles = list(after_handles - before_handles)

            if new_handles:
                current = driver.current_window_handle

                for h in new_handles:
                    try:
                        driver.switch_to.window(h)
                        time.sleep(0.5)
                        new_url = clean_text(driver.current_url)

                        if is_iris_real_download_url(new_url) or is_iris_possible_download_url(new_url):
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

        except Exception:
            pass

        urls = iris_get_recent_network_urls(driver)

        candidates = []

        for url in urls:
            if is_iris_real_download_url(url) or is_iris_possible_download_url(url):
                candidates.append(url)

        candidates = list(dict.fromkeys(candidates))

        if candidates:
            # 보통 마지막 요청이 실제 다운로드 요청일 가능성이 높음
            return candidates[-1]

    except Exception:
        return ""

    return ""


def extract_iris_attachments_from_detail_page(driver):
    """
    IRIS 상세페이지 첨부파일명 + 다운로드 URL 추출

    원칙:
    - 파일명은 화면에 보이는 원문을 최대한 그대로 저장
    - '붙임', '공고문', 'R&D' 등 앞부분 삭제하지 않음
    - 용량 정보만 제거
    """
    attachments = []

    try:
        targets = iris_find_attachment_click_targets(driver)

        for target in targets:
            file_name = clean_text(target.get("name", ""))

            # 용량 정보만 제거: (128KB), (1.57MB), (2087KB)
            file_name = re.sub(
                r"\([0-9,.]+\s*(KB|MB|GB)\)",
                "",
                file_name,
                flags=re.I
            )
            file_name = clean_text(file_name)

            element = target.get("element")

            if not file_name:
                continue

            download_url = ""

            try:
                download_url = iris_extract_direct_download_url_from_element(element)
            except Exception:
                download_url = ""

            if not download_url:
                download_url = iris_click_and_capture_download_url(
                    driver=driver,
                    element=element,
                    wait_sec=1.0
                )

            attachments.append({
                "name": file_name,
                "url": download_url or ""
            })

    except Exception as e:
        print(f"[IRIS 첨부파일 추출 오류] {str(e)[:300]}")

    # 중복 제거
    cleaned = []
    seen = set()

    for item in attachments:
        name = clean_text(item.get("name", ""))

        # 여기서도 용량 정보만 제거
        name = re.sub(
            r"\([0-9,.]+\s*(KB|MB|GB)\)",
            "",
            name,
            flags=re.I
        )
        name = clean_text(name)

        url = clean_text(item.get("url", ""))

        if not name:
            continue

        key = normalize_for_match(name)

        if key in seen:
            continue

        seen.add(key)
        cleaned.append({
            "name": name,
            "url": url
        })

    return cleaned

def is_iris_share_url(url):
    url = clean_text(url)
    if not url:
        return False

    # 실제 링크공유 팝업에 표시되는 URL
    if re.search(
        r"https?://www\.iris\.go\.kr/contents/retrieveBsnsAncmView\.do\?ancmId=\d+&ancmPrg=ancm(?:Ing|Bef)",
        url
    ):
        return True

    # 혹시 /0/ 공유 URL 형태가 나오는 경우도 허용
    if re.search(r"https?://www\.iris\.go\.kr/0/[A-Za-z0-9+/=%_-]+", url):
        return True

    return False

def extract_iris_share_url_by_click(driver, fallback_url=""):
    """
    IRIS 상세페이지 하단 '링크공유' 버튼 클릭 후
    팝업 input에 표시되는 실제 공유 URL을 추출한다.

    IRIS 동작:
    1) 링크공유 버튼 클릭
    2) URL input + 복사 버튼 팝업 표시
    3) input value가 실제 공유 URL
       예: https://www.iris.go.kr/contents/retrieveBsnsAncmView.do?ancmId=021660&ancmPrg=ancmIng
    """
    fallback_url = clean_text(fallback_url)

    def read_share_url_from_modal():
        """
        링크공유 팝업의 input value에서 URL 추출
        """
        try:
            # 현재 화면에 표시된 input 중 IRIS 공유 URL이 들어있는 값 찾기
            inputs = driver.find_elements(By.CSS_SELECTOR, "input")

            for inp in inputs:
                try:
                    if not inp.is_displayed():
                        continue

                    value = clean_text(inp.get_attribute("value"))

                    if value and is_iris_share_url(value):
                        return value

                except Exception:
                    continue

            # input value가 아닌 DOM 텍스트로 들어간 경우 보조 확인
            body_text = clean_text(driver.find_element(By.TAG_NAME, "body").text)
            urls = re.findall(r"https?://www\.iris\.go\.kr/[^\s'\"<>]+", body_text)

            for u in urls:
                if is_iris_share_url(u):
                    return u

        except Exception:
            pass

        return ""

    try:
        # clipboard / alert / prompt 가로채기
        driver.execute_script("""
            window.__IRIS_COPIED_TEXT__ = "";
            window.__IRIS_ALERT_TEXT__ = "";

            if (navigator.clipboard && navigator.clipboard.writeText) {
                const originalWriteText = navigator.clipboard.writeText.bind(navigator.clipboard);
                navigator.clipboard.writeText = function(text) {
                    window.__IRIS_COPIED_TEXT__ = text;
                    return Promise.resolve(text);
                };
            }

            const originalAlert = window.alert;
            window.alert = function(msg) {
                window.__IRIS_ALERT_TEXT__ = String(msg || "");
                return true;
            };

            const originalPrompt = window.prompt;
            window.prompt = function(msg, value) {
                window.__IRIS_COPIED_TEXT__ = value || msg || "";
                return value || "";
            };
        """)

        # 실제 하단의 링크공유 button/a만 후보로 사용
        buttons = driver.find_elements(
            By.XPATH,
            "//button[normalize-space(.)='링크공유' or normalize-space(.)='링크 공유']"
            " | //a[normalize-space(.)='링크공유' or normalize-space(.)='링크 공유']"
        )

        real_buttons = []

        for btn in buttons:
            try:
                if not btn.is_displayed():
                    continue

                txt = clean_text(btn.text)
                if txt not in ["링크공유", "링크 공유"]:
                    continue

                rect = driver.execute_script("""
                    const r = arguments[0].getBoundingClientRect();
                    return {
                        x: r.x,
                        y: r.y,
                        width: r.width,
                        height: r.height,
                        bottom: r.bottom
                    };
                """, btn)

                if rect["width"] < 40 or rect["height"] < 20:
                    continue

                real_buttons.append((rect["y"], btn))

            except Exception:
                continue

        # 하단 버튼 우선
        real_buttons.sort(key=lambda x: x[0], reverse=True)

        print(f"[IRIS 실제 링크공유 버튼 후보] {len(real_buttons)}개")

        for _, btn in real_buttons:
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});",
                    btn
                )
                time.sleep(0.4)

                try:
                    ActionChains(driver).move_to_element(btn).pause(0.2).click(btn).perform()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn)

                # 팝업 뜰 때까지 대기
                share_url = ""

                end_time = time.time() + 5
                while time.time() < end_time:
                    share_url = read_share_url_from_modal()
                    if share_url:
                        break
                    time.sleep(0.2)

                # input value에서 바로 잡혔으면 성공
                if share_url and is_iris_share_url(share_url):
                    print(f"[IRIS 링크공유 URL 추출 성공: modal input] {share_url}")

                    # 가능하면 팝업의 '복사' 버튼도 눌러서 실제 UI 흐름과 동일하게 처리
                    try:
                        copy_buttons = driver.find_elements(
                            By.XPATH,
                            "//button[normalize-space(.)='복사'] | //a[normalize-space(.)='복사']"
                        )

                        for copy_btn in copy_buttons:
                            if copy_btn.is_displayed():
                                driver.execute_script(
                                    "arguments[0].scrollIntoView({block:'center'});",
                                    copy_btn
                                )
                                time.sleep(0.2)
                                try:
                                    ActionChains(driver).move_to_element(copy_btn).pause(0.2).click(copy_btn).perform()
                                except Exception:
                                    driver.execute_script("arguments[0].click();", copy_btn)
                                time.sleep(0.5)
                                break
                    except Exception:
                        pass

                    # 팝업 닫기
                    try:
                        close_buttons = driver.find_elements(
                            By.XPATH,
                            "//button[normalize-space(.)='닫기'] | //a[normalize-space(.)='닫기'] | //*[@aria-label='Close']"
                        )
                        for close_btn in close_buttons:
                            if close_btn.is_displayed():
                                driver.execute_script("arguments[0].click();", close_btn)
                                time.sleep(0.3)
                                break
                    except Exception:
                        pass

                    return share_url

                # 혹시 복사 버튼 클릭 후 clipboard에 들어가는 경우 보조 처리
                try:
                    copy_buttons = driver.find_elements(
                        By.XPATH,
                        "//button[normalize-space(.)='복사'] | //a[normalize-space(.)='복사']"
                    )
                    for copy_btn in copy_buttons:
                        if not copy_btn.is_displayed():
                            continue

                        try:
                            ActionChains(driver).move_to_element(copy_btn).pause(0.2).click(copy_btn).perform()
                        except Exception:
                            driver.execute_script("arguments[0].click();", copy_btn)

                        time.sleep(0.5)

                        copied_text = clean_text(
                            driver.execute_script("return window.__IRIS_COPIED_TEXT__ || '';")
                        )

                        if copied_text and is_iris_share_url(copied_text):
                            print(f"[IRIS 링크공유 URL 추출 성공: copy button] {copied_text}")
                            return copied_text

                except Exception:
                    pass

            except Exception as e:
                print(f"[IRIS 링크공유 버튼 처리 실패] {str(e)[:200]}")
                continue

    except Exception as e:
        print(f"[IRIS 링크공유 URL 추출 실패] {str(e)[:200]}")

    return fallback_url

def wait_iris_detail_loaded(driver, before_url="", before_text="", timeout=12):
    end_time = time.time() + timeout

    detail_keywords = [
        "신청하기",
        "링크공유",
        "목록",
        "첨부파일",
        "공고문",
        "시행계획",
        "붙임",
        "서식",
        "연구개발계획서"
    ]

    while time.time() < end_time:
        try:
            current_url = clean_text(driver.current_url)
            body_text = clean_text(driver.find_element(By.TAG_NAME, "body").text)

            if not body_text:
                time.sleep(0.4)
                continue

            if "IRIS 콜센터" in body_text and len(body_text) < 1000:
                time.sleep(0.4)
                continue

            # URL이 바뀌었거나, 상세페이지 키워드가 충분히 보이면 성공
            url_changed = before_url and current_url != before_url
            keyword_hit = any(k in body_text for k in detail_keywords)

            if keyword_hit:
                return True

            if url_changed and "retrieveBsnsAncmView.do" in current_url:
                return True

        except Exception:
            pass

        time.sleep(0.4)

    return False

def click_iris_item_by_title(driver, title):
    """
    현재 목록 화면에서 제목 텍스트가 포함된 공고 카드를 다시 찾아 클릭한다.
    stale element 방지를 위해 매번 새로 찾는다.
    """
    title_norm = normalize_title(title)

    items = find_iris_item_elements(driver)

    for elem in items:
        try:
            txt = clean_text(elem.text)
            if title_norm not in normalize_title(txt):
                continue

            clickable = None

            for selector in ["a", "button", "span", "strong", "p"]:
                for cand in elem.find_elements(By.CSS_SELECTOR, selector):
                    cand_text = clean_text(cand.text)
                    if not cand_text:
                        continue

                    if normalize_title(cand_text) in title_norm or title_norm in normalize_title(cand_text):
                        clickable = cand
                        break

                if clickable:
                    break

            if clickable is None:
                clickable = elem

            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", clickable)
            time.sleep(0.3)

            try:
                ActionChains(driver).move_to_element(clickable).pause(0.2).click(clickable).perform()
            except Exception:
                driver.execute_script("arguments[0].click();", clickable)

            return True

        except Exception:
            continue

    return False

def iris_urljoin(raw_url):
    raw_url = clean_text(raw_url)

    if not raw_url:
        return ""

    if raw_url.startswith("http://") or raw_url.startswith("https://"):
        return raw_url

    if raw_url.startswith("/"):
        return urljoin("https://www.iris.go.kr", raw_url)

    return urljoin("https://www.iris.go.kr", raw_url)


def extract_urls_from_attrs_for_iris(node):
    urls = []

    attrs = []

    for attr in [
        "href",
        "onclick",
        "data-url",
        "data-href",
        "data-link",
        "data-file",
        "data-file-id",
        "data-atch-file-id",
        "title"
    ]:
        value = node.get(attr)
        if value:
            attrs.append(str(value))

    joined = html.unescape(" ".join(attrs))

    # 절대 URL
    urls.extend(re.findall(r"https?://[^\s'\"<>;)]+", joined))

    # 상대 URL
    rels = re.findall(r"['\"](\/[^'\"]+)['\"]", joined)
    for rel in rels:
        urls.append(iris_urljoin(rel))

    href = clean_text(node.get("href", ""))
    if href and href != "#" and not href.lower().startswith("javascript"):
        urls.append(iris_urljoin(href))

    return list(dict.fromkeys([u for u in urls if u]))

def is_iris_real_download_url(url):
    """
    IRIS 실제 첨부파일 다운로드 URL만 허용
    주의:
    - https://www.iris.go.kr/0/xxxxx 형태는 링크공유 URL일 가능성이 높으므로
      첨부파일 다운로드 URL로 사용하지 않는다.
    """
    url = clean_text(url)

    if not url:
        return False

    low = url.lower()

    block_tokens = [
        ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg",
        "javascript:", "blob:", "data:", "chunk", "bundle", "static"
    ]

    if any(t in low for t in block_tokens):
        return False

    # IRIS 링크공유 URL은 첨부파일 URL로 제외
    if re.search(r"https?://www\.iris\.go\.kr/0/[A-Za-z0-9+/=%_-]+", url):
        return False

    # 실제 다운로드 API로 보이는 URL만 허용
    download_tokens = [
        "filedown",
        "filedownload",
        "download",
        "atchfile",
        "attachfile",
        "attchfile",
        "cmmnfile",
        "cmnfile"
    ]

    if any(token in low for token in download_tokens):
        return True

    # 확장자가 URL에 직접 들어있는 경우만 허용
    if any(ext in low for ext in [
        ".pdf", ".hwp", ".hwpx", ".zip", ".xls", ".xlsx",
        ".doc", ".docx", ".ppt", ".pptx"
    ]):
        return True

    return False

def is_iris_possible_download_url(url):
    """
    IRIS 다운로드 URL 후보 판별
    - /0/... 형태는 링크공유/암호화 라우팅일 수 있어 다운로드 URL로 저장하지 않음
    """
    url = clean_text(url)

    if not url:
        return False

    low = url.lower()

    block_tokens = [
        ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg",
        "javascript:", "blob:", "data:", "chunk", "bundle", "static"
    ]

    if any(t in low for t in block_tokens):
        return False

    if re.search(r"https?://www\.iris\.go\.kr/0/[A-Za-z0-9+/=%_-]+", url):
        return False

    if any(ext in low for ext in [
        ".pdf", ".hwp", ".hwpx", ".zip", ".xls", ".xlsx",
        ".doc", ".docx", ".ppt", ".pptx"
    ]):
        return True

    if any(token in low for token in [
        "filedown", "filedownload", "download", "atch", "attach", "file"
    ]):
        return True

    return False

def parse_iris_item_text(item_text: str, fallback_status: str, iris_detail_info=None):
    """
    IRIS 목록/상세 정보를 신규공고 row로 변환

    수정 핵심:
    - 목록 카드(item_text)보다 상세페이지(iris_detail_info)에서 추출한 정보를 우선 반영
    - 접수기간/마감일/문의처/지원내용이 '-'로 저장되는 문제 개선
    - 첨부파일 JSON은 iris_detail_info["attachments"] 기준으로 저장
    """
    item_text = clean_text(item_text)
    lines = [clean_text(x) for x in item_text.splitlines() if clean_text(x)]

    iris_detail_info = iris_detail_info or {}

    iris_detail_url = clean_text(iris_detail_info.get("detail_url", ""))
    iris_attachments = iris_detail_info.get("attachments", []) or []
    iris_attachment_json = build_attachment_json(iris_attachments)

    # -------------------------------------------------
    # 1) 제목
    # -------------------------------------------------
    title = guess_iris_title(lines)

    if not title:
        return None

    # -------------------------------------------------
    # 2) 상세페이지 값 우선 반영
    # -------------------------------------------------
    agency = (
            clean_iris_org_value(iris_detail_info.get("agency", "")) or
            clean_iris_org_value(guess_iris_agency(lines, item_text))
    )

    ministry = (
            clean_iris_org_value(iris_detail_info.get("ministry", "")) or
            clean_iris_org_value(guess_iris_ministry(lines, item_text))
    )

    announce_date = (
        clean_text(iris_detail_info.get("announce_date", "")) or
        try_extract_date_from_text(item_text)
    )

    apply_period = (
        clean_text(iris_detail_info.get("apply_period", "")) or
        extract_iris_apply_period(item_text)
    )

    deadline = (
        clean_text(iris_detail_info.get("deadline", "")) or
        extract_deadline_from_period(apply_period)
    )

    status = extract_iris_status(item_text, fallback_status)

    notice_no = (
        clean_text(iris_detail_info.get("notice_no", "")) or
        extract_iris_notice_no(item_text)
    )

    inquiry = clean_text(iris_detail_info.get("inquiry", ""))

    support_target = clean_text(iris_detail_info.get("support_target", ""))

    support_content = clean_text(iris_detail_info.get("support_content", ""))

    if not support_content:
        support_content = clean_iris_support_content(item_text, title)

    # -------------------------------------------------
    # 3) 비고
    # -------------------------------------------------
    note_parts = []

    if notice_no:
        note_parts.append(f"공고번호: {notice_no}")

    if not announce_date:
        note_parts.append("IRIS 카드에서 공고일 미확인")

    # -------------------------------------------------
    # 4) 적합도 계산
    # -------------------------------------------------
    relevance = calculate_relevance_score_v2(
        title=title,
        source="IRIS",
        body_text=item_text
    )

    if not relevance["save"]:
        print_filter_drop(
            source="IRIS",
            title=title,
            relevance=relevance,
            detail_url=iris_detail_url,
            note=" | ".join(note_parts)
        )
        return None

    print(
        f"[IRIS 수집통과] 제목={title} | "
        f"score={relevance.get('score', 0)} | "
        f"grade={relevance.get('grade', 'D')} | "
        f"status={status} | "
        f"공고일={announce_date or '-'} | "
        f"마감일={deadline or '-'} | "
        f"신청기간={apply_period or '-'} | "
        f"소관부처={ministry or '-'} | "
        f"수행기관={agency or '-'} | "
        f"문의처={inquiry or '-'} | "
        f"지원내용={support_content[:100] if support_content else '-'} | "
        f"matched={relevance.get('matched_recurring', []) + relevance.get('matched_combos', []) + relevance.get('matched_keywords', [])}"
    )

    matched_keywords_text = " | ".join(
        relevance["matched_recurring"] +
        relevance["matched_combos"] +
        relevance["matched_keywords"][:10]
    )

    recurring_group_text = " | ".join(relevance["recurring_group_ids"])
    recurring_flag = "Y" if relevance["recurring_hit"] else "N"

    # -------------------------------------------------
    # 5) 최종 row 생성
    # -------------------------------------------------
    return make_row(
        source="IRIS",
        status=status,
        announce_date=announce_date,
        title=title,
        deadline=deadline,
        ministry=ministry,
        agency=agency,
        apply_period=apply_period,
        support_target=support_target,
        support_content=support_content,
        receipt_place="공고문 확인",
        inquiry=inquiry,
        detail_url=iris_detail_url,
        relevance_score=str(relevance["score"]),
        relevance_grade=relevance["grade"],
        recurring_flag=recurring_flag,
        recurring_group=recurring_group_text,
        matched_keywords=matched_keywords_text,
        note=" | ".join(note_parts),
        attachments=iris_attachment_json
    )

def parse_iris_rows_from_page(
    driver,
    status_label: str,
    lookback_days: int,
    skip_cross_site_title_keys=None
):
    """
    IRIS 목록 페이지 파싱

    수정된 흐름:
    1. 목록에서 공고 제목/본문 snapshot 추출
    2. 상세페이지 진입 전 제목+목록텍스트 기준 1차 필터링
    3. 날짜 기준 확인
    4. 필터 통과한 공고만 상세페이지 진입
    5. 상세 URL / 첨부파일 추출
    6. 최종 row 생성
    """
    results = []
    seen_titles = set()

    item_snapshots = []

    # 1) 목록 화면에서 후보 텍스트만 먼저 저장
    for elem in find_iris_item_elements(driver):
        try:
            item_text = clean_text(elem.text)
            lines = [clean_text(x) for x in item_text.splitlines() if clean_text(x)]
            title = guess_iris_title(lines)

            if not title:
                continue

            item_snapshots.append({
                "title": title,
                "text": item_text
            })

        except Exception:
            continue

    print(f"[IRIS 후보 스냅샷] 상태={status_label} | 후보={len(item_snapshots)}건")

    if not item_snapshots:
        body_text = clean_text(driver.find_element(By.TAG_NAME, "body").text)
        log_error(
            "IRIS",
            f"{status_label}_목록탐지실패",
            status_label,
            IRIS_URL,
            detail=body_text[:3000]
        )
        return results

    for snap in item_snapshots:
        title = snap["title"]
        item_text = snap["text"]

        try:
            title_key = normalize_title(title)

            if title_key in seen_titles:
                print(f"[IRIS 목록 중복제외] 제목={title}")
                continue

            seen_titles.add(title_key)

            cross_site_title_key = make_cross_site_title_key_from_title(title)

            if (
                cross_site_title_key
                and skip_cross_site_title_keys
                and cross_site_title_key in skip_cross_site_title_keys
            ):
                print(f"[IRIS 사이트간 중복제외-상세진입전] 제목={title}")
                continue

            print(f"[IRIS 후보] 상태={status_label} | 제목={title}")

            # -------------------------------------------------
            # 0) 상세 진입 전 1차 필터링
            # -------------------------------------------------
            pre_relevance = calculate_relevance_score_v2(
                title=title,
                source="IRIS",
                body_text=item_text
            )

            if not pre_relevance["save"]:
                print_filter_drop(
                    source="IRIS",
                    title=title,
                    relevance=pre_relevance,
                    detail_url=IRIS_URL,
                    note="IRIS 필터탈락"
                )
                continue

            # -------------------------------------------------
            # 1) 상세 진입 전 날짜 확인
            # -------------------------------------------------
            announce_date = try_extract_date_from_text(item_text)

            if announce_date:
                if not is_within_lookback(announce_date, lookback_days):
                    print(f"[IRIS 날짜제외-상세진입전] 제목={title} | 공고일={announce_date}")
                    continue
            else:
                print(f"[IRIS 공고일없음-상세확인] 제목={title}")

            print(f"[IRIS 상세진입 후보] 상태={status_label} | 제목={title}")

            # -------------------------------------------------
            # 2) 여기부터 필터 통과한 공고만 상세페이지 진입
            # -------------------------------------------------
            driver.get(IRIS_URL)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(1.0)

            click_iris_status_tab(driver, status_label)
            time.sleep(1.0)

            if not click_iris_item_by_title(driver, title):
                print(f"[IRIS 상세 진입 실패] 제목={title}")
                iris_detail_info = {
                    "detail_url": "",
                    "attachments": []
                }
            else:
                wait_iris_detail_loaded(
                    driver,
                    before_url=IRIS_URL,
                    before_text="",
                    timeout=10
                )
                time.sleep(0.7)

                detail_url = extract_iris_detail_url_from_page_source(driver)

                if detail_url:
                    print(
                        f"[IRIS 상세 URL 추출 성공: page_source] "
                        f"title={title} | detail_url={detail_url}"
                    )
                else:
                    share_url = extract_iris_share_url_by_click(driver, fallback_url="")
                    current_url = clean_text(driver.current_url)

                    print(
                        f"[IRIS 링크공유 확인] title={title} | "
                        f"share_url={share_url} | current_url={current_url}"
                    )

                    if share_url and is_iris_share_url(share_url):
                        detail_url = share_url
                    elif "retrieveBsnsAncmView.do" in current_url and "ancmId=" in current_url:
                        detail_url = current_url
                    else:
                        detail_url = ""

                attachments = extract_iris_attachments_from_detail_page(driver)
                detail_text = extract_iris_detail_text(driver)

                detail_fields = extract_iris_detail_fields(detail_text, title)

                print(
                    f"[IRIS 상세정보 추출] 제목={title} | "
                    f"공고일={detail_fields.get('announce_date', '')} | "
                    f"접수기간={detail_fields.get('apply_period', '')} | "
                    f"마감일={detail_fields.get('deadline', '')} | "
                    f"문의처={detail_fields.get('inquiry', '')} | "
                    f"지원내용={detail_fields.get('support_content', '')[:200]}"
                )

                iris_detail_info = {
                    "detail_url": detail_url,
                    "attachments": attachments,
                    "detail_text": detail_text,
                    **detail_fields,
                }

            # -------------------------------------------------
            # 3) 최종 row 생성
            # -------------------------------------------------
            parsed = parse_iris_item_text(
                item_text,
                status_label,
                iris_detail_info
            )

            if parsed:
                parsed_announce_date = clean_text(safe_get(parsed, 0))
                if parsed_announce_date:
                    if not is_within_lookback(parsed_announce_date, lookback_days):
                        print(f"[IRIS 날짜제외-상세확인후] 제목={title} | 공고일={parsed_announce_date}")
                        continue
                elif not IRIS_INCLUDE_UNDATED:
                    print(f"[IRIS 공고일없음 제외-상세확인후] 제목={title}")
                    continue

            if not parsed:
                continue

            results.append(parsed)

        except Exception as e:
            log_error("IRIS", f"{status_label}_행파싱", title, IRIS_URL, e)

    return results

def extract_iris_detail_url_from_page_source(driver):
    """
    IRIS 상세페이지 page_source / script / hidden input에서
    ancmId, ancmPrg 값을 찾아 상세 URL을 구성한다.
    """
    html_text = driver.page_source or ""
    text = clean_text(html_text)

    ancm_id = ""

    patterns = [
        r"ancmId['\"\s:=]+(\d{4,})",
        r"name=['\"]ancmId['\"][^>]*value=['\"](\d{4,})['\"]",
        r"id=['\"]ancmId['\"][^>]*value=['\"](\d{4,})['\"]",
        r"ancmId=(\d{4,})",
    ]

    for pattern in patterns:
        m = re.search(pattern, html_text, flags=re.I)
        if m:
            ancm_id = clean_text(m.group(1))
            break

    if not ancm_id:
        return ""

    body_text = clean_text(driver.find_element(By.TAG_NAME, "body").text)

    if "접수예정" in body_text:
        ancm_prg = "ancmBef"
    elif "접수중" in body_text or "공고접수중" in body_text:
        ancm_prg = "ancmIng"
    else:
        ancm_prg = "ancmIng"

    return f"https://www.iris.go.kr/contents/retrieveBsnsAncmView.do?ancmId={ancm_id}&ancmPrg={ancm_prg}"

def scrape_iris_recent(driver, lookback_days: int, skip_cross_site_title_keys=None):
    print("[IRIS] 수집 시작")
    driver.get(IRIS_URL)

    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    time.sleep(2)

    all_results = []

    for status_label in ["접수예정", "접수중"]:
        try:
            before_text = clean_text(driver.find_element(By.TAG_NAME, "body").text)

            clicked = click_iris_status_tab(driver, status_label)
            if not clicked:
                log_error("IRIS", "탭클릭", status_label, IRIS_URL, Exception(f"{status_label} 탭 클릭 실패"))
                continue

            wait_iris_list_refresh(driver, before_text, timeout=10)
            time.sleep(1)

            rows = parse_iris_rows_from_page(
                driver,
                status_label,
                lookback_days,
                skip_cross_site_title_keys=skip_cross_site_title_keys
            )
            print(f"[IRIS] {status_label}: {len(rows)}건")
            all_results.extend(rows)

        except Exception as e:
            log_error("IRIS", f"{status_label}_수집", status_label, IRIS_URL, e)

    print(f"[IRIS] 수집 완료: {len(all_results)}건")
    return all_results
def extract_iris_detail_text(driver) -> str:
    """
    IRIS 상세페이지 전체 본문 텍스트 추출
    """
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        return clean_text(body_text)
    except Exception:
        return ""


def clean_iris_support_content(detail_text: str, title: str = "") -> str:
    """
    IRIS 상세페이지 본문에서 지원내용/공고문 핵심 안내문을 추출한다.

    목표:
    - 상단 표 정보 제거
    - 첨부파일 목록 제거
    - 실제 공고문 안내문만 저장
    """
    detail_text = clean_text(detail_text)
    title = clean_text(title)

    if not detail_text:
        return ""

    lines = [
        clean_text(x)
        for x in detail_text.splitlines()
        if clean_text(x)
    ]

    title_norm = normalize_for_match(title)

    remove_exact = {
        "사업공고",
        "공고문",
        "소관부처",
        "전문기관",
        "공고번호",
        "공고명",
        "공고일자",
        "재공고 여부",
        "접수기간",
        "사업담당자 연락처",
        "접수 개시 여부",
        "첨부파일",
        "신청하기",
        "목록",
        "링크공유",
    }

    remove_contains = [
        "Request URL",
        ".zip",
        ".hwp",
        ".hwpx",
        ".pdf",
        "KB)",
        "MB)",
        "접수 미개시인 경우",
        "사업담당자에게 연락하여",
        "온라인 과제접수 매뉴얼",
    ]

    cleaned = []
    seen = set()

    for line in lines:
        if not line:
            continue

        line_norm = normalize_for_match(line)

        # 라벨 제거
        if line in remove_exact:
            continue

        # 제목과 완전 동일한 줄 제거
        if title_norm and line_norm == title_norm:
            continue

        # 첨부파일/용량/매뉴얼성 문구 제거
        if any(x in line for x in remove_contains):
            continue

        # 날짜 단독 제거
        if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", line):
            continue

        # 기간 단독 제거
        if re.search(r"20\d{2}-\d{2}-\d{2}\s*~\s*20\d{2}-\d{2}-\d{2}", line):
            continue

        # 너무 짧은 값 제거
        if len(line) <= 3:
            continue

        # 중복 제거
        if line_norm in seen:
            continue

        seen.add(line_norm)
        cleaned.append(line)

    if not cleaned:
        return ""

    # -------------------------------------------------
    # 실제 공고 안내문 시작 위치 찾기
    # -------------------------------------------------
    start_idx = 0

    start_keywords = [
        "다음과 같이 공고하오니",
        "신청하여 주시기 바랍니다",
        "수행하고자 하는 자는",
        "신규 지원대상",
        "신규지원 대상",
        "신규 지원대상 연구개발과제",
        "신규지원 대상 연구개발과제",
    ]

    for i, line in enumerate(cleaned):
        if any(k in line for k in start_keywords):
            start_idx = i
            break

    picked = []

    for line in cleaned[start_idx:]:
        # 첨부파일 영역 진입 시 종료
        if "첨부" in line and ("파일" in line or "서류" in line):
            break

        if "붙임" in line and any(ext in line.lower() for ext in [".hwp", ".hwpx", ".pdf", ".zip"]):
            break

        picked.append(line)

        # 안내문은 보통 1~3줄이면 충분
        if len(picked) >= 3:
            break

    return clean_text("\n".join(picked))

def extract_iris_detail_fields(detail_text: str, title: str = "") -> dict:
    """
    IRIS 상세페이지 body text에서 핵심 요약 정보를 추출한다.
    - 소관부처
    - 전문기관
    - 공고번호
    - 공고일자
    - 접수기간
    - 마감일
    - 문의처
    - 지원내용
    """
    detail_text = clean_text(detail_text)
    title = clean_text(title)

    result = {
        "ministry": "",
        "agency": "",
        "notice_no": "",
        "announce_date": "",
        "apply_period": "",
        "deadline": "",
        "inquiry": "",
        "support_target": "",
        "support_content": "",
    }

    if not detail_text:
        return result

    # 공백 정리용 한 줄 텍스트
    one = re.sub(r"\s+", " ", detail_text)
    label_values = extract_detail_label_values(
        detail_text,
        max_lines_by_field={
            "support_content": 8,
            "support_target": 5,
            "receipt_place": 5,
            "inquiry": 8,
        }
    )

    result["support_target"] = clean_text(label_values.get("support_target", ""))

    # 소관부처
    result["ministry"] = clean_iris_org_value(label_values.get("ministry", ""))

    if not result["ministry"]:
        m = re.search(r"소관부처\s+(.+?)\s+전문기관", one)
        if m:
            result["ministry"] = clean_iris_org_value(m.group(1))

    # 전문기관
    result["agency"] = clean_iris_org_value(label_values.get("agency", ""))

    if not result["agency"]:
        m = re.search(r"전문기관\s+(.+?)\s+공고번호", one)
        if m:
            result["agency"] = clean_iris_org_value(m.group(1))

    # 공고번호
    result["notice_no"] = clean_text(label_values.get("notice_no", ""))

    if not result["notice_no"]:
        m = re.search(r"공고번호\s+(.+?)\s+공고명", one)
        if m:
            result["notice_no"] = clean_text(m.group(1))

    # 공고일자
    result["announce_date"] = normalize_date(label_values.get("announce_date", ""))

    if not result["announce_date"]:
        m = re.search(r"공고(?:일자|일)\s+(20\d{2}[./-]\d{1,2}[./-]\d{1,2})", one)
        if m:
            result["announce_date"] = normalize_date(m.group(1))

    # 접수기간
    result["apply_period"] = clean_text(label_values.get("apply_period", ""))

    if result["apply_period"]:
        result["deadline"] = extract_deadline_from_period(result["apply_period"])

    if not result["apply_period"]:
        m = re.search(
            r"접수\s*기간\s+(20\d{2}[./-]\d{1,2}[./-]\d{1,2}\s*[~∼～]\s*20\d{2}[./-]\d{1,2}[./-]\d{1,2})",
            one
        )
        if m:
            result["apply_period"] = normalize_apply_period_text(m.group(1))
            result["deadline"] = extract_deadline_from_period(result["apply_period"])

    if not result["deadline"]:
        result["deadline"] = normalize_date(label_values.get("deadline", ""))

    # 문의처 / 사업담당자 연락처
    result["inquiry"] = clean_text(label_values.get("inquiry", ""))

    if not result["inquiry"]:
        m = re.search(
            r"사업담당자\s*연락처\s+(.+?)\s+접수\s*개시\s*여부",
            one
        )
        if m:
            result["inquiry"] = clean_text(m.group(1))

    # 지원내용 / 공고문 핵심 안내문
    support = clean_text(label_values.get("support_content", "")) or clean_iris_support_content(detail_text, title)

    # 제목/날짜가 섞여 들어가면 한 번 더 정리
    support_lines = []
    for line in support.splitlines():
        line = clean_text(line)

        if not line:
            continue
        if title and normalize_for_match(line) == normalize_for_match(title):
            continue
        if re.fullmatch(r"20\d{2}년\s*\d{1,2}월\s*\d{1,2}일", line):
            continue
        if "산업통상부장관" in line:
            continue
        if "신규지원 대상과제 공고" in line and len(line) < 40:
            continue

        support_lines.append(line)

    result["support_content"] = clean_text("\n".join(support_lines))

    return result

