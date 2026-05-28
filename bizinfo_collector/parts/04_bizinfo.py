# =========================================================
# 8) Bizinfo (requests 기반)
# =========================================================
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
})


def fetch_html(url, params=None, timeout=REQUEST_TIMEOUT, max_retry=3):
    last_exc = None
    for i in range(max_retry):
        try:
            r = session.get(url, params=params, timeout=timeout, allow_redirects=True)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_exc = e
            time.sleep(1 + i)
    raise last_exc


def bizinfo_get_last_page(html_text: str) -> int:
    soup = BeautifulSoup(html_text, "html.parser")
    a = soup.select_one('a[title="마지막페이지"]')
    if not a:
        for cand in soup.select("a"):
            if cand.get_text(strip=True) == "마지막":
                a = cand
                break
    if not a or not a.get("href"):
        return 1

    href = a["href"]
    full = href if href.startswith("http") else BIZINFO_BASE + href
    parsed = urlparse(full)
    qs = parse_qs(parsed.query)
    return int(qs.get("cpage", ["1"])[0])


def bizinfo_find_target_table(soup: BeautifulSoup):
    table = soup.select_one("table.table_type_1")
    if table:
        return table
    th = soup.find("th", string=lambda s: s and "지원사업명" in s)
    if th:
        return th.find_parent("table")
    return None


def bizinfo_norm(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", "", s)


def bizinfo_get_col_index_map(table) -> dict:
    ths = table.select("thead th")
    headers = [bizinfo_norm(th.get_text(strip=True)) for th in ths]

    key_alias = {
        "번호": ["번호"],
        "지원분야": ["지원분야"],
        "지원사업명": ["지원사업명"],
        "신청기간": ["신청기간"],
        "등록일": ["등록일"],
        "소관부처·지자체": ["소관부처·지자체"],
        "사업수행기관": ["사업수행기관"],
    }

    idx_map = {}
    for key, aliases in key_alias.items():
        for i, h in enumerate(headers):
            if any(a == h for a in aliases):
                idx_map[key] = i
                break
    return idx_map


def bizinfo_build_detail_url(href: str):
    if not href:
        return None
    href = html.unescape(href.strip())
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return BIZINFO_BASE + href
    href = href.lstrip("./")
    return BIZINFO_DETAIL_PREFIX + href


def parse_bizinfo_period(text: str):
    if not text:
        return None, None, None

    t = html.unescape(str(text)).strip()
    t = re.sub(r"\s+", " ", t)
    t = t.replace("∼", "~").replace("～", "~")

    dates = re.findall(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}", t)
    if len(dates) >= 2:
        start = dates[0].replace(".", "-").replace("/", "-")
        end = dates[1].replace(".", "-").replace("/", "-")
        return start, end, t

    return None, None, t


def split_support_target_and_content(business_overview: str):
    overview = clean_text(business_overview)
    if not overview:
        return "", ""

    bullet_blocks = re.findall(r"☞\s*(.*?)(?=(?:\n☞)|$)", overview, flags=re.S)
    if len(bullet_blocks) >= 2:
        return clean_text(bullet_blocks[0]), clean_text("\n".join(bullet_blocks[1:]))

    if len(bullet_blocks) == 1:
        support_target = clean_text(bullet_blocks[0])
        amount_lines = []
        for line in overview.splitlines():
            line = clean_text(line)
            if any(k in line for k in ["지원", "최대", "억원", "천원", "만원", "융자", "보조", "컨설팅", "바우처"]):
                amount_lines.append(line)
        return support_target, clean_text("\n".join(amount_lines))

    lines = [clean_text(x) for x in overview.splitlines() if clean_text(x)]
    target_lines, content_lines = [], []
    for line in lines:
        if any(k in line for k in ["대상", "기업", "소상공인", "벤처", "중소기업", "창업", "컨소시엄"]):
            target_lines.append(line)
        if any(k in line for k in ["지원", "최대", "억원", "천원", "만원", "융자", "보조", "컨설팅", "사업비", "바우처"]):
            content_lines.append(line)

    return clean_text("\n".join(target_lines)), clean_text("\n".join(content_lines))


def extract_contact_place_from_apply_method(apply_method: str):
    apply_method = clean_text(apply_method)
    receipt_place = ""

    patterns = [
        r"접수처\s*:\s*(.+?)(?=\n|$)",
        r"방문\s*접수\s*:\s*(.+?)(?=\n|$)",
        r"온라인\s*접수\s*:\s*(.+?)(?=\n|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, apply_method, flags=re.S)
        if match:
            receipt_place = clean_text(match.group(1))
            break

    return receipt_place, apply_method


def parse_bizinfo_list_page(html_text: str):
    soup = BeautifulSoup(html_text, "html.parser")
    table = bizinfo_find_target_table(soup)
    if not table:
        raise RuntimeError("기업마당 목록 테이블을 찾지 못했습니다.")

    col = bizinfo_get_col_index_map(table)
    rows = []

    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        if not tds:
            continue

        def td_text(key):
            i = col.get(key)
            if i is None or i >= len(tds):
                return ""
            return tds[i].get_text(" ", strip=True)

        def td_node(key):
            i = col.get(key)
            if i is None or i >= len(tds):
                return None
            return tds[i]

        field = td_text("지원분야")
        title_td = td_node("지원사업명")
        reg_dt = normalize_date(td_text("등록일"))

        a = title_td.select_one("a") if title_td else None
        title = a.get_text(" ", strip=True) if a else (title_td.get_text(" ", strip=True) if title_td else "")
        raw_href = a.get("href") if a else None
        detail_url = bizinfo_build_detail_url(raw_href)

        ministry = td_text("소관부처·지자체")
        agency = td_text("사업수행기관")
        apply_period_text = td_text("신청기간")
        _, end_dt, period_raw = parse_bizinfo_period(apply_period_text)

        rows.append({
            "지원분야": field,
            "공고명": clean_text(title),
            "공고일": reg_dt,
            "마감일": end_dt or extract_deadline_from_period(period_raw),
            "소관부처": clean_text(ministry),
            "수행기관": clean_text(agency),
            "신청기간": clean_text(period_raw),
            "상세링크": detail_url or "",
        })

    return rows


def bizinfo_extract_source_links(root):
    links = []
    btn = root.select_one("div.btn_area2") or root.select_one(".btn_area2")
    if not btn:
        return links

    for a in btn.select("a"):
        href = (a.get("href") or "").strip()
        onclick = (a.get("onclick") or "").strip()

        if href and not href.lower().startswith("javascript"):
            if href.startswith("/"):
                href = urljoin(BIZINFO_BASE, href)
            links.append(href)

        if onclick:
            links += re.findall(r"(https?://[^\s'\";]+)", onclick)
            rels = re.findall(r"['\"](\/[^'\"]+)['\"]", onclick)
            for rel in rels:
                links.append(urljoin(BIZINFO_BASE, rel))

    return list(dict.fromkeys([x for x in links if x.startswith("http")]))


def bizinfo_extract_attachments(root):
    results = []
    wrapper = root.select_one("div.attached_file_list")
    if not wrapper:
        return results

    current_group = None
    for child in wrapper.select(":scope > ul > *"):
        if child.name == "h3":
            current_group = clean_text(child.get_text())
            continue
        if child.name != "li":
            continue

        file_name_el = child.select_one("div.file_name")
        file_name = clean_text(file_name_el.get_text()) if file_name_el else ""

        right = child.select_one("div.right_btn")
        download_a = right.select_one("a.icon_download[href]") if right else None
        download_href = (download_a.get("href") or "").strip() if download_a else ""
        download_url = urljoin(BIZINFO_BASE, download_href) if download_href else ""

        results.append({
            "group": current_group or "",
            "file_name": file_name,
            "download_url": download_url,
        })

    return results

def build_attachment_json(attachments):
    """
    첨부파일 정보를 시트 저장용 JSON 문자열로 변환

    구조:
    [
      {
        "name": "공고문.pdf",
        "url": "https://...",
        "local_path": "C:/.../downloads/smart_factory/공고문.pdf"
      }
    ]
    """
    if not attachments:
        return ""

    items = []

    for a in attachments:
        file_name = clean_text(
            a.get("name", "") or
            a.get("file_name", "") or
            a.get("filename", "")
        )

        file_url = clean_text(
            a.get("url", "") or
            a.get("download_url", "") or
            a.get("href", "")
        )

        local_path = clean_text(
            a.get("local_path", "") or
            a.get("path", "")
        )

        if not file_name:
            continue

        item = {
            "name": file_name,
            "url": file_url
        }

        if local_path:
            item["local_path"] = local_path

        items.append(item)

    if not items:
        return ""

    return json.dumps(items, ensure_ascii=False)

def parse_bizinfo_detail(detail_url: str, list_title: str):
    html_text = fetch_html(detail_url)
    soup = BeautifulSoup(html_text, "html.parser")

    root = soup.select_one("div.support_project_detail")
    if not root:
        raise RuntimeError("기업마당 상세영역 support_project_detail을 찾지 못했습니다.")

    kv_norm = {}
    view_cont = root.select_one("div.view_cont")
    if view_cont:
        for li in view_cont.select("ul > li"):
            k_el = li.select_one("span.s_title")
            v_el = li.select_one("div.txt")
            if not k_el or not v_el:
                continue
            key = re.sub(r"\s+", "", clean_text(k_el.get_text()))
            value = clean_text(v_el.get_text("\n", strip=True))
            kv_norm[key] = value

    ministry = kv_norm.get("소관부처·지자체", "")
    agency = kv_norm.get("사업수행기관", "")
    apply_period = kv_norm.get("신청기간", "")
    business_overview = kv_norm.get("사업개요", "")
    apply_method = kv_norm.get("사업신청방법", "")
    inquiry = kv_norm.get("문의처", "")
    deadline = extract_deadline_from_period(apply_period)
    status = classify_status_from_apply_period(apply_period)

    support_target, support_content = split_support_target_and_content(business_overview)
    receipt_place, _ = extract_contact_place_from_apply_method(apply_method)

    source_links = bizinfo_extract_source_links(root)
    attachments = bizinfo_extract_attachments(root)

    # 첨부파일(JSON) 컬럼 저장용
    attachment_json = build_attachment_json(attachments)

    note_parts = []

    if source_links:
        note_parts.append(f"원문링크: {source_links[0]}")

    if attachments:
        file_names = [
            clean_text(a.get("file_name", ""))
            for a in attachments
            if clean_text(a.get("file_name", ""))
        ]

        if file_names:
            note_parts.append("첨부파일: " + ", ".join(file_names[:5]))

    return {
        "출처": "기업마당",
        "접수상태": status,
        "공고일": "",
        "공고명": list_title,
        "마감일": deadline,
        "소관부처": ministry,
        "수행기관": agency,
        "신청기간": apply_period,
        "지원대상": support_target,
        "지원내용(혜택 및 금액)": support_content,
        "접수처": receipt_place,
        "문의처": inquiry,
        "상세링크": detail_url,
        "첨부파일": attachment_json,
        "비고": " | ".join(note_parts)
    }

def scrape_bizinfo_recent(lookback_days: int):
    print("[기업마당] 수집 시작")
    first_html = fetch_html(BIZINFO_LIST_URL, params={"rows": BIZINFO_LIST_ROWS, "cpage": 1})
    last_page = bizinfo_get_last_page(first_html)

    results = []
    cutoff_date = datetime.now().date() - timedelta(days=lookback_days - 1)

    for page_num in range(1, last_page + 1):
        print(f"[기업마당] {page_num}페이지 수집 중")
        try:
            html_text = first_html if page_num == 1 else fetch_html(
                BIZINFO_LIST_URL, params={"rows": BIZINFO_LIST_ROWS, "cpage": page_num}
            )
            rows = parse_bizinfo_list_page(html_text)

            stop_program = False

            for item in rows:
                reg_dt = parse_date_obj(item["공고일"])

                # 날짜가 없으면 스킵
                if not reg_dt:
                    continue

                # 최신순이라는 전제: 오래된 날짜가 나오면 전체 중지
                if reg_dt < cutoff_date:
                    stop_program = True
                    break

                try:
                    detail = parse_bizinfo_detail(item["상세링크"], item["공고명"])
                    detail["공고일"] = item["공고일"]
                    detail["소관부처"] = detail["소관부처"] or item["소관부처"]
                    detail["수행기관"] = detail["수행기관"] or item["수행기관"]
                    detail["신청기간"] = detail["신청기간"] or item["신청기간"]
                    detail["마감일"] = detail["마감일"] or item["마감일"]

                    if not detail["접수상태"]:
                        detail["접수상태"] = classify_status_from_apply_period(detail["신청기간"])

                    body_text_for_scoring = " ".join([
                        item["공고명"],
                        item["소관부처"],
                        item["수행기관"],
                        item["신청기간"],
                        detail["공고명"],
                        detail["소관부처"],
                        detail["수행기관"],
                        detail["신청기간"],
                        detail["지원대상"],
                        detail["지원내용(혜택 및 금액)"],
                        detail["비고"]
                    ])

                    relevance = calculate_relevance_score_v2(
                        title=detail["공고명"],
                        source="기업마당",
                        body_text=body_text_for_scoring
                    )

                    if not relevance["save"]:
                        print_filter_drop(
                            source="기업마당",
                            title=detail["공고명"],
                            relevance=relevance,
                            detail_url=detail["상세링크"],
                            note=detail["비고"]
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
                        attachments=detail.get("첨부파일", "")
                    ))

                except Exception as e:
                    log_error("기업마당", "상세파싱", item["공고명"], item["상세링크"], e)

            if stop_program:
                print(f"[기업마당] 수집 완료")
                break

            time.sleep(0.4)

        except Exception as e:
            log_error("기업마당", f"목록수집_{page_num}페이지", "", BIZINFO_LIST_URL, e)

    print(f"[기업마당] 수집 완료: {len(results)}건")
    return results


