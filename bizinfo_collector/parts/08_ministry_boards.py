# =========================================================
# 11) 부처 공고판 크롤러 (중기부 / 산자부 / 과기부)
# =========================================================
MINISTRY_BOARD_MAX_PAGES = 3

MSS_LIST_URL = "https://www.mss.go.kr/site/smba/ex/bbs/List.do?cbIdx=310"
MOTIR_LIST_URL = "https://www.motir.go.kr/kor/article/ATCLc01b2801b"
MSIT_LIST_URL = "https://www.msit.go.kr/bbs/list.do?sCode=user&mPid=121&mId=311"

MINISTRY_NEW_TASK_KEYWORDS = [
    "신규과제",
    "신규 과제",
    "신규지원",
    "신규 지원",
    "대상과제",
    "대상 과제",
    "지원과제",
    "지원 과제",
    "연구개발과제",
    "연구개발 과제",
    "r&d",
    "R&D",
    "기술개발",
    "사업 공고",
    "모집공고",
    "공고",
]

MINISTRY_BOARD_EXCLUDE_KEYWORDS = [
    "보도자료",
    "설명자료",
    "채용",
    "인사",
    "입찰",
    "계약",
    "고시",
    "행정예고",
    "법령",
    "훈령",
    "예규",
    "정정",
    "수정",
]

MINISTRY_ATTACHMENT_NAME_HINTS = [
    "공고",
    "공고문",
    "모집공고",
    "사업공고",
    "붙임",
    "첨부",
    "hwp",
    "hwpx",
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "zip",
]

MINISTRY_DETAIL_SELECTORS = [
    ".board_view",
    ".view",
    ".view_cont",
    ".view_content",
    ".article_view",
    ".articleView",
    ".bbs_view",
    ".bbsView",
    ".contents",
    "#contents",
    "#content",
    "main",
]


def ministry_board_norm(text):
    return re.sub(r"\s+", "", clean_text(text)).lower()


def ministry_board_abs_url(base_url, href):
    href = html.unescape(clean_text(href))
    href_low = href.lower()
    if (
        not href
        or href.startswith("#")
        or href_low.startswith("javascript:")
        or href_low.startswith("javascript:void")
    ):
        return ""
    return urljoin(base_url, href)


def ministry_board_text_has_new_task_hint(text):
    text = clean_text(text)
    if not text:
        return False
    text_low = text.lower()
    if any(k.lower() in text_low for k in MINISTRY_BOARD_EXCLUDE_KEYWORDS):
        return False
    return any(k.lower() in text_low for k in MINISTRY_NEW_TASK_KEYWORDS)


def ministry_board_is_candidate_title(title):
    if not title:
        return False
    if ministry_board_text_has_new_task_hint(title):
        return True
    relevance = calculate_relevance_score_v2(title=title, source="부처공고")
    return bool(relevance.get("save"))


def ministry_board_fetch_soup(url, params=None):
    html_text = fetch_html(url, params=params)
    return BeautifulSoup(html_text, "html.parser")


def ministry_board_find_list_table(soup):
    best_table = None
    best_score = 0

    for table in soup.select("table"):
        headers = [ministry_board_norm(th.get_text(" ", strip=True)) for th in table.select("th")]
        header_text = " ".join(headers)
        score = 0
        for key in ["제목", "등록일", "담당부서", "공고번호", "신청기간", "첨부파일"]:
            if key in header_text:
                score += 1
        if table.select("tbody tr"):
            score += 1
        if score > best_score:
            best_score = score
            best_table = table

    return best_table if best_score >= 2 else None


def ministry_board_col_map(table, aliases):
    header_cells = table.select("thead th")
    if not header_cells:
        first_tr = table.select_one("tr")
        header_cells = first_tr.find_all(["th", "td"]) if first_tr else []

    headers = [ministry_board_norm(cell.get_text(" ", strip=True)) for cell in header_cells]
    col = {}
    for key, names in aliases.items():
        for i, header in enumerate(headers):
            if any(ministry_board_norm(name) in header for name in names):
                col[key] = i
                break
    return col


def ministry_board_td_text(tds, col, key):
    idx = col.get(key)
    if idx is None or idx >= len(tds):
        return ""
    return clean_text(tds[idx].get_text(" ", strip=True))


def ministry_board_td_node(tds, col, key):
    idx = col.get(key)
    if idx is None or idx >= len(tds):
        return None
    return tds[idx]


def ministry_board_pick_title_cell(tds, col):
    title_td = ministry_board_td_node(tds, col, "title")
    if title_td:
        return title_td

    best = None
    best_len = 0
    for td in tds:
        a = td.select_one("a[href]")
        text = clean_text((a or td).get_text(" ", strip=True))
        if len(text) > best_len:
            best = td
            best_len = len(text)
    return best


def ministry_board_extract_list_items(soup, base_url, aliases, source):
    table = ministry_board_find_list_table(soup)
    if not table:
        raise RuntimeError(f"{source} 목록 테이블을 찾지 못했습니다.")

    col = ministry_board_col_map(table, aliases)
    items = []

    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        if not tds:
            continue

        title_td = ministry_board_pick_title_cell(tds, col)
        if not title_td:
            continue

        a = title_td.select_one("a[href]")
        title = clean_text((a or title_td).get_text(" ", strip=True))
        if not title or "등록된 게시물이 없습니다" in title:
            continue

        raw_href = a.get("href") if a else ""
        onclick = " ".join([
            clean_text(tr.get("onclick")),
            clean_text(title_td.get("onclick")),
            clean_text(a.get("onclick") if a else ""),
            clean_text(raw_href),
        ])

        detail_url = ministry_board_abs_url(base_url, raw_href) if a else ""
        if not detail_url:
            detail_url = ministry_board_detail_url_from_onclick(base_url, onclick)

        announce_date = normalize_date(
            ministry_board_td_text(tds, col, "announce_date")
            or ministry_board_td_text(tds, col, "date")
        )
        apply_period = ministry_board_td_text(tds, col, "apply_period")
        deadline = extract_deadline_from_period(apply_period)

        items.append({
            "공고명": title,
            "공고일": announce_date,
            "마감일": deadline,
            "신청기간": clean_text(apply_period),
            "소관부처": source,
            "수행기관": ministry_board_td_text(tds, col, "agency"),
            "공고번호": ministry_board_td_text(tds, col, "notice_no"),
            "상세링크": detail_url,
        })

    return items


def ministry_board_normalize_script_date(raw_date):
    raw_date = clean_text(raw_date)
    if not raw_date:
        return ""

    normalized = normalize_date(raw_date)
    if normalized:
        return normalized

    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s*(20\d{2})", raw_date)
    if not m:
        return ""

    month_map = {
        "jan": "01", "january": "01",
        "feb": "02", "february": "02",
        "mar": "03", "march": "03",
        "apr": "04", "april": "04",
        "may": "05",
        "jun": "06", "june": "06",
        "jul": "07", "july": "07",
        "aug": "08", "august": "08",
        "sep": "09", "sept": "09", "september": "09",
        "oct": "10", "october": "10",
        "nov": "11", "november": "11",
        "dec": "12", "december": "12",
    }
    month = month_map.get(m.group(1).lower())
    if not month:
        return ""
    return f"{m.group(3)}-{month}-{int(m.group(2)):02d}"


def msit_extract_script_value(html_text, field, index):
    patterns = [
        rf"unescape\('([^']*)'\);\s*sHtml\+=\s*newHtml;.*?\$\('#td_'\+'{re.escape(field)}'\+'_{index}'\)",
        rf"\$\('#td_'\+'{re.escape(field)}'\+'_{index}'\)\.html\('([^']*)'\)",
        rf"//\$\('#td_'\+'{re.escape(field)}'\+'_{index}'\)\.html\('([^']*)'\)",
        rf"td_{re.escape(field)}_{index}.*?unescape\('([^']*)'\)",
    ]
    for pattern in patterns:
        m = re.search(pattern, html_text, flags=re.S)
        if m:
            return html.unescape(clean_text(m.group(1)))
    return ""


def parse_msit_list_items(soup, base_url, source):
    html_text = str(soup)
    seq_matches = list(re.finditer(r"fn_detail\s*\(\s*['\"]?(\d+)['\"]?\s*\)", html_text))
    items = []
    seen = set()

    for idx, match in enumerate(seq_matches):
        ntt_seq_no = match.group(1)
        if ntt_seq_no in seen:
            continue
        seen.add(ntt_seq_no)

        title = msit_extract_script_value(html_text, "NTT_SJ", idx)
        if not title:
            anchor = soup.find("a", onclick=lambda value: value and ntt_seq_no in value)
            title = clean_text(anchor.get_text(" ", strip=True)) if anchor else ""
        if not title:
            continue

        date_raw = msit_extract_script_value(html_text, "REG_DT", idx)
        announce_date = ministry_board_normalize_script_date(date_raw)
        agency = msit_extract_script_value(html_text, "NTT_CT2", idx) or msit_extract_script_value(html_text, "DEPT_NM", idx)
        inquiry = msit_extract_script_value(html_text, "NTT_CT4", idx)

        detail_url = ministry_board_abs_url(
            base_url,
            f"/bbs/view.do?sCode=user&mPid=121&mId=311&bbsSeqNo=100&nttSeqNo={ntt_seq_no}"
        )

        items.append({
            "공고명": title,
            "공고일": announce_date,
            "마감일": "",
            "신청기간": "",
            "소관부처": source,
            "수행기관": agency,
            "공고번호": ntt_seq_no,
            "문의처": inquiry,
            "상세링크": detail_url,
        })

    return items


def parse_mss_list_items(soup, base_url, source):
    table = ministry_board_find_list_table(soup)
    if not table:
        raise RuntimeError(f"{source} 목록 테이블을 찾지 못했습니다.")

    items = []
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue

        title_td = tds[1]
        a = title_td.select_one("a.pc-detail") or title_td.select_one("a[href]")
        title = clean_text((a or title_td).get_text(" ", strip=True))
        if not title or "등록된 게시물이 없습니다" in title:
            continue

        kv = {}
        for dl in title_td.select("dl"):
            dt = clean_text(dl.find("dt").get_text(" ", strip=True)) if dl.find("dt") else ""
            dd = clean_text(dl.find("dd").get_text(" ", strip=True)) if dl.find("dd") else ""
            if dt:
                kv[dt] = dd

        detail_url = ministry_board_detail_url_from_onclick(base_url, tr.get("onclick") or "")
        announce_date = normalize_date(tds[3].get_text(" ", strip=True)) if len(tds) > 3 else ""
        apply_period = kv.get("신청기간", "")

        items.append({
            "공고명": title,
            "공고일": announce_date,
            "마감일": extract_deadline_from_period(apply_period),
            "신청기간": clean_text(apply_period),
            "소관부처": source,
            "수행기관": kv.get("담당부서", ""),
            "공고번호": kv.get("공고번호", ""),
            "상세링크": detail_url,
        })

    return items


def ministry_board_detail_url_from_onclick(base_url, onclick):
    onclick = html.unescape(clean_text(onclick))
    if not onclick:
        return ""

    url_match = re.search(r"['\"]([^'\"]+(?:View|view|Detail|detail|Read|read)[^'\"]*)['\"]", onclick)
    if url_match:
        return ministry_board_abs_url(base_url, url_match.group(1))

    parsed = urlparse(base_url)

    m = re.search(r"doBbsFView\s*\(\s*['\"]?(\d+)['\"]?\s*,\s*['\"]?(\d+)['\"]?.*?['\"]?(\d+)['\"]?\s*\)", onclick)
    if m and "mss.go.kr" in parsed.netloc:
        cb_idx, bc_idx, parent_seq = m.group(1), m.group(2), m.group(3)
        return ministry_board_abs_url(
            base_url,
            f"/site/smba/ex/bbs/View.do?cbIdx={cb_idx}&bcIdx={bc_idx}&parentSeq={parent_seq}"
        )

    m = re.search(r"article\.view\s*\(\s*['\"]?(\d+)['\"]?\s*\)", onclick)
    if m and "motir.go.kr" in parsed.netloc:
        return ministry_board_abs_url(
            base_url,
            f"/kor/article/ATCLc01b2801b/{m.group(1)}/view"
        )

    m = re.search(r"fn_detail\s*\(\s*['\"]?(\d+)['\"]?\s*\)", onclick)
    if m and "msit.go.kr" in parsed.netloc:
        return ministry_board_abs_url(
            base_url,
            f"/bbs/view.do?sCode=user&mPid=121&mId=311&bbsSeqNo=100&nttSeqNo={m.group(1)}"
        )

    nums = re.findall(r"\d+", onclick)
    if not nums:
        return ""

    if "mss.go.kr" in parsed.netloc:
        return ministry_board_abs_url(base_url, f"View.do?cbIdx=310&bcIdx={nums[-1]}")
    return ""


def ministry_board_extract_detail_root(soup):
    for selector in MINISTRY_DETAIL_SELECTORS:
        root = soup.select_one(selector)
        if root and len(clean_text(root.get_text(" ", strip=True))) >= 80:
            return root
    return soup


def ministry_board_extract_detail_text(soup):
    root = ministry_board_extract_detail_root(soup)
    for tag in root.select("script, style, noscript, iframe"):
        tag.decompose()
    text = root.get_text("\n", strip=True)
    lines = []
    seen = set()
    for raw in text.splitlines():
        line = clean_text(raw)
        if not line:
            continue
        key = ministry_board_norm(line)
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return "\n".join(lines)


def ministry_board_find_labeled_value(text, labels, max_lines=5):
    lines = [clean_text(x) for x in clean_text(text).splitlines() if clean_text(x)]
    label_pattern = "|".join(re.escape(label) for label in labels)

    for i, line in enumerate(lines):
        m = re.search(rf"({label_pattern})\s*[:：]?\s*(.+)$", line)
        if m and clean_text(m.group(2)):
            return clean_text(m.group(2))

        if any(label in line for label in labels):
            values = []
            for follow in lines[i + 1:i + 1 + max_lines]:
                if ministry_board_line_starts_new_section(follow):
                    break
                values.append(follow)
            if values:
                return clean_text("\n".join(values))

    return ""


def ministry_board_line_starts_new_section(line):
    line = clean_text(line)
    if not line:
        return False
    section_labels = [
        "사업개요", "사업목적", "지원내용", "지원대상", "신청기간", "접수기간",
        "신청방법", "접수방법", "문의처", "담당부서", "첨부파일", "붙임",
        "공고기간", "추진일정", "선정방법", "평가방법",
    ]
    return any(line.startswith(label) or line == label for label in section_labels)


def ministry_board_extract_period(text, fallback=""):
    candidates = [
        ministry_board_find_labeled_value(text, ["신청기간", "접수기간", "공고기간", "전산접수기간", "온라인 접수기간"]),
        fallback,
    ]
    date_range_pattern = (
        r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}"
        r"(?:\s*\([^)]*\))?"
        r"\s*(?:~|∼|～|-|부터|부터\s*)\s*"
        r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}"
        r"(?:\s*\([^)]*\))?(?:\s*\d{1,2}:\d{2})?"
    )

    for candidate in candidates:
        candidate = clean_text(candidate)
        if not candidate:
            continue
        m = re.search(date_range_pattern, candidate)
        if m:
            return clean_text(m.group(0))
        dates = re.findall(r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}", candidate)
        if len(dates) >= 2:
            return f"{dates[0]} ~ {dates[1]}"

    m = re.search(date_range_pattern, clean_text(text))
    if m:
        return clean_text(m.group(0))

    dates = re.findall(r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}", clean_text(text))
    if len(dates) >= 2:
        return f"{dates[0]} ~ {dates[1]}"

    return clean_text(fallback)


def ministry_board_extract_section(text, start_labels, stop_labels=None, max_lines=10):
    stop_labels = stop_labels or [
        "신청기간", "접수기간", "신청방법", "접수방법", "문의처", "담당자",
        "첨부파일", "붙임", "추진일정", "평가방법", "선정방법",
    ]
    lines = [clean_text(x) for x in clean_text(text).splitlines() if clean_text(x)]

    for i, line in enumerate(lines):
        if not any(label in line for label in start_labels):
            continue

        values = []
        inline = line
        for label in start_labels:
            inline = re.sub(rf"^{re.escape(label)}\s*[:：]?\s*", "", inline)
        if inline and inline not in start_labels:
            values.append(inline)

        for follow in lines[i + 1:i + 1 + max_lines]:
            if any(follow.startswith(label) for label in stop_labels):
                break
            values.append(follow)

        return clean_text("\n".join(values))

    return ""


def ministry_board_extract_attachments(soup, detail_url):
    attachments = []
    seen = set()

    for a in soup.select("a[href]"):
        href = clean_text(a.get("href"))
        text = clean_text(a.get_text(" ", strip=True))
        title = clean_text(a.get("title"))
        name = text or title
        haystack = f"{href} {text} {title}".lower()

        if not any(hint.lower() in haystack for hint in MINISTRY_ATTACHMENT_NAME_HINTS):
            continue
        if any(skip in haystack for skip in ["javascript:void", "list.do", "view.do", "twitter", "facebook"]):
            continue

        file_url = ministry_board_abs_url(detail_url, href)
        if not file_url:
            continue

        if not name:
            parsed = urlparse(file_url)
            name = os.path.basename(parsed.path) or "첨부파일"
        name = re.sub(r"\s*다운로드\s*$", "", clean_text(name))
        name = name or "첨부파일"

        key = f"{name}||{file_url}"
        if key in seen:
            continue
        seen.add(key)
        attachments.append({"name": name, "url": file_url})

    return attachments


def ministry_board_parse_detail(item, source):
    detail_url = item.get("상세링크", "")
    if not detail_url:
        raise RuntimeError("상세링크가 비어 있습니다.")

    soup = ministry_board_fetch_soup(detail_url)
    text = ministry_board_extract_detail_text(soup)

    title = item.get("공고명") or ministry_board_find_labeled_value(text, ["제목", "공고명", "사업명"], max_lines=2)
    announce_date = item.get("공고일") or normalize_date(
        ministry_board_find_labeled_value(text, ["등록일", "공고일", "공고일자"], max_lines=2)
    )
    apply_period = ministry_board_extract_period(text, item.get("신청기간", ""))
    deadline = extract_deadline_from_period(apply_period) or item.get("마감일", "")
    agency = item.get("수행기관") or ministry_board_find_labeled_value(
        text, ["담당부서", "전담기관", "전문기관", "수행기관", "소관부서"], max_lines=3
    )
    support_target = ministry_board_extract_section(
        text,
        ["지원대상", "신청자격", "지원자격", "대상"],
        stop_labels=["지원내용", "신청기간", "접수기간", "신청방법", "접수방법", "문의처", "첨부파일"],
        max_lines=8,
    )
    support_content = ministry_board_extract_section(
        text,
        ["지원내용", "사업내용", "지원규모", "사업개요", "공고내용"],
        stop_labels=["지원대상", "신청기간", "접수기간", "신청방법", "접수방법", "문의처", "첨부파일"],
        max_lines=12,
    )
    receipt_place = ministry_board_find_labeled_value(text, ["신청방법", "접수방법", "접수처", "제출방법"], max_lines=5)
    inquiry = ministry_board_find_labeled_value(text, ["문의처", "문의", "담당자", "연락처"], max_lines=5)
    notice_no = item.get("공고번호") or ministry_board_find_labeled_value(text, ["공고번호"], max_lines=1)
    attachments = ministry_board_extract_attachments(soup, detail_url)

    if not support_content:
        body_lines = [line for line in text.splitlines() if line and title not in line]
        support_content = clean_text("\n".join(body_lines[:10]))

    note_parts = [f"원문링크: {detail_url}"]
    if notice_no:
        note_parts.append(f"공고번호: {notice_no}")

    return {
        "출처": source,
        "접수상태": classify_status_from_apply_period(apply_period),
        "공고일": announce_date,
        "공고명": clean_text(title),
        "마감일": deadline,
        "소관부처": source,
        "수행기관": clean_text(agency),
        "신청기간": clean_text(apply_period),
        "지원대상": clean_text(support_target),
        "지원내용(혜택 및 금액)": clean_text(support_content),
        "접수처": clean_text(receipt_place),
        "문의처": clean_text(inquiry),
        "상세링크": detail_url,
        "첨부파일": build_attachment_json(attachments),
        "비고": " | ".join(note_parts),
    }


def ministry_board_make_rows(items, source, lookback_days, skip_cross_site_title_keys=None):
    results = []
    skip_cross_site_title_keys = skip_cross_site_title_keys or set()
    cutoff_date = datetime.now().date() - timedelta(days=int(lookback_days) - 1)

    for item in items:
        title = item.get("공고명", "")
        announce_date = item.get("공고일", "")

        reg_dt = parse_date_obj(announce_date)
        if reg_dt and reg_dt < cutoff_date:
            continue
        if not reg_dt and announce_date:
            continue

        if not ministry_board_is_candidate_title(title):
            relevance = calculate_relevance_score_v2(title=title, source=source)
            print_filter_drop(source, title, relevance, item.get("상세링크", ""), "목록 제목 기준 부처 신규과제 후보 아님")
            continue

        cross_key = make_cross_site_title_key_from_title(title)
        if cross_key and cross_key in skip_cross_site_title_keys:
            print(f"[{source} 사이트간 중복제외] 제목={title}")
            continue

        try:
            detail = ministry_board_parse_detail(item, source)
            body_text_for_scoring = " ".join([
                detail["공고명"],
                detail["소관부처"],
                detail["수행기관"],
                detail["신청기간"],
                detail["지원대상"],
                detail["지원내용(혜택 및 금액)"],
                detail["비고"],
            ])
            relevance = calculate_relevance_score_v2(
                title=detail["공고명"],
                source=source,
                body_text=body_text_for_scoring,
            )

            if not relevance["save"]:
                print_filter_drop(
                    source=source,
                    title=detail["공고명"],
                    relevance=relevance,
                    detail_url=detail["상세링크"],
                    note=detail["비고"],
                )
                continue

            matched_keywords_text = " | ".join(
                relevance["matched_recurring"] +
                relevance["matched_combos"] +
                relevance["matched_keywords"][:30]
            )
            recurring_group_text = " | ".join(relevance["recurring_group_ids"])
            recurring_flag = "Y" if relevance["recurring_hit"] else "N"

            results.append(make_row(
                source=detail["출처"],
                status=detail["접수상태"],
                announce_date=detail["공고일"],
                title=detail["공고명"],
                deadline=detail["마감일"],
                ministry=detail["소관부처"],
                agency=detail["수행기관"],
                apply_period=detail["신청기간"],
                support_target=detail["지원대상"],
                support_content=detail["지원내용(혜택 및 금액)"],
                receipt_place=detail["접수처"],
                inquiry=detail["문의처"],
                detail_url=detail["상세링크"],
                relevance_score=str(relevance["score"]),
                relevance_grade=relevance["grade"],
                recurring_flag=recurring_flag,
                recurring_group=recurring_group_text,
                matched_keywords=matched_keywords_text,
                note=detail["비고"],
                attachments=detail.get("첨부파일", ""),
            ))
        except Exception as e:
            log_error(source, "상세파싱", title, item.get("상세링크", ""), e)

    return results


def ministry_board_scrape_recent(config, lookback_days, skip_cross_site_title_keys=None):
    source = config["source"]
    list_url = config["list_url"]
    print(f"[{source}] 수집 시작")

    all_items = []
    for page_num in range(1, MINISTRY_BOARD_MAX_PAGES + 1):
        try:
            print(f"[{source}] {page_num}페이지 수집 중")
            params = config["page_params"](page_num)
            soup = ministry_board_fetch_soup(list_url, params=params)
            if config.get("list_parser"):
                items = config["list_parser"](soup, list_url, source)
            else:
                items = ministry_board_extract_list_items(
                    soup=soup,
                    base_url=list_url,
                    aliases=config["aliases"],
                    source=source,
                )
            if not items:
                break
            all_items.extend(items)
            time.sleep(0.4)
        except Exception as e:
            log_error(source, f"목록수집_{page_num}페이지", "", list_url, e)
            break

    rows = ministry_board_make_rows(
        all_items,
        source,
        lookback_days,
        skip_cross_site_title_keys=skip_cross_site_title_keys,
    )
    print(f"[{source}] 수집 완료: {len(rows)}건")
    return rows


def scrape_mss_recent(lookback_days, skip_cross_site_title_keys=None):
    return ministry_board_scrape_recent({
        "source": "중기부",
        "list_url": MSS_LIST_URL,
        "list_parser": parse_mss_list_items,
        "page_params": lambda page: {"pageIndex": page} if page > 1 else None,
        "aliases": {
            "title": ["제목", "공고명"],
            "apply_period": ["신청기간", "접수기간"],
            "notice_no": ["공고번호", "번호"],
            "agency": ["담당부서", "부서"],
            "announce_date": ["등록일", "공고일"],
            "date": ["등록일", "공고일"],
        },
    }, lookback_days, skip_cross_site_title_keys)


def scrape_motir_recent(lookback_days, skip_cross_site_title_keys=None):
    return ministry_board_scrape_recent({
        "source": "산자부",
        "list_url": MOTIR_LIST_URL,
        "page_params": lambda page: {"pageIndex": page} if page > 1 else None,
        "aliases": {
            "title": ["제목", "공고명"],
            "notice_no": ["공고번호", "번호"],
            "agency": ["담당부서", "부서"],
            "announce_date": ["등록일", "공고일"],
            "date": ["등록일", "공고일"],
        },
    }, lookback_days, skip_cross_site_title_keys)


def scrape_msit_recent(lookback_days, skip_cross_site_title_keys=None):
    return ministry_board_scrape_recent({
        "source": "과기부",
        "list_url": MSIT_LIST_URL,
        "list_parser": parse_msit_list_items,
        "page_params": lambda page: {
            "sCode": "user",
            "mPid": "121",
            "mId": "311",
            "pageIndex": page,
        } if page > 1 else None,
        "aliases": {
            "title": ["제목", "공고명"],
            "notice_no": ["번호", "공고번호"],
            "agency": ["담당부서", "부서"],
            "announce_date": ["등록일", "공고일", "작성일"],
            "date": ["등록일", "공고일", "작성일"],
        },
    }, lookback_days, skip_cross_site_title_keys)
