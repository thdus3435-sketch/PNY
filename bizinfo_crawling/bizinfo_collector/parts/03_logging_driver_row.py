# =========================================================
# 5) 에러 로깅
# =========================================================
ERROR_LOGS = []
FILTER_DROP_ROWS = []
FILTER_DROP_KEYS = set()

def log_error(source, stage, title="", url="", error=None, detail=""):
    err_msg = str(error) if error else ""
    tb = traceback.format_exc() if error else detail
    ERROR_LOGS.append([
        now_str(),
        source,
        stage,
        title,
        url,
        err_msg[:1000],
        clean_text(tb)[:5000],
    ])

def extract_original_link_from_note(note: str) -> str:
    note = clean_text(note)
    if not note:
        return ""

    m = re.search(r"원문링크\s*:\s*(https?://[^\s|]+)", note)
    if m:
        return clean_text(m.group(1))

    return ""

def format_filter_drop_note(source, detail_url="", note=""):
    detail_url = clean_text(detail_url)
    note = clean_text(note)

    original_url = extract_original_link_from_note(note) or detail_url

    parts = []
    if original_url:
        parts.append(f"원문링크: {original_url}")

    for part in [clean_text(x) for x in note.split("|") if clean_text(x)]:
        if part.startswith("원문링크:"):
            continue
        if part not in parts:
            parts.append(part)

    reason = f"{source} 필터탈락"
    if reason not in parts:
        parts.append(reason)

    return " | ".join(parts)

def print_filter_drop(source, title, relevance, detail_url="", note=""):
    matched = (
        relevance.get("matched_recurring", []) +
        relevance.get("matched_combos", []) +
        relevance.get("matched_keywords", [])
    )

    title_clean = clean_text(title)
    detail_url_clean = clean_text(detail_url)
    note_clean = format_filter_drop_note(source, detail_url_clean, note)
    original_url = extract_original_link_from_note(note_clean) or detail_url_clean

    notice_no = extract_notice_no_from_note(note_clean)

    if notice_no:
        drop_key = f"{source}||{notice_no}"
    else:
        drop_key = f"{source}||{normalize_title(title_clean)}||{original_url}"

    if drop_key in FILTER_DROP_KEYS:
        print(f"[{source} 필터탈락 중복제외] 제목={title_clean} | key={drop_key}")
        return

    FILTER_DROP_KEYS.add(drop_key)

    print(
        f"[{source} 필터탈락] 제목={title_clean} | "
        f"score={relevance.get('score', 0)} | "
        f"grade={relevance.get('grade', 'D')} | "
        f"keyword_hit_count={relevance.get('keyword_hit_count', 0)} | "
        f"matched={matched} | "
    )

    FILTER_DROP_ROWS.append([
        now_str(),
        source,
        title_clean,
        relevance.get("score", 0),
        relevance.get("grade", "D"),
        relevance.get("keyword_hit_count", 0),
        detail_url_clean,
        note_clean,
    ])

# =========================================================
# 6) Selenium 드라이버
# =========================================================
def setup_driver(download_dir=None):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    if download_dir is None:
        download_dir = os.path.join(os.getcwd(), "downloads")

    os.makedirs(download_dir, exist_ok=True)

    chrome_options = Options()

    # 필요 시 headless 유지 가능
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1600,1200")

    # 다운로드 설정
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "plugins.always_open_pdf_externally": True,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    # 네트워크 로그 수집 설정
    chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    print("[드라이버] ChromeDriverManager install 시작")
    driver_path = ChromeDriverManager().install()
    print("[드라이버] ChromeDriverManager install 완료")

    print("[드라이버] webdriver.Chrome 실행 시작")
    driver = webdriver.Chrome(
        service=Service(driver_path),
        options=chrome_options
    )
    print("[드라이버] webdriver.Chrome 실행 완료")

    # 네트워크 요청 캡처 활성화
    try:
        print("[드라이버] Network.enable 시작")
        driver.execute_cdp_cmd("Network.enable", {})
        print("[드라이버] Network.enable 완료")
    except Exception:
        print("[드라이버] Network.enable 실패 - 계속 진행")
        pass

    try:
        print("[드라이버] 다운로드 경로 설정 시작")
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": download_dir
        })
        print("[드라이버] 다운로드 경로 설정 완료")
    except Exception:
        print("[드라이버] 다운로드 경로 설정 실패 - 계속 진행")

    return driver

# =========================================================
# 7) 데이터 row 생성
# =========================================================
def make_row(
    source, status, announce_date, title, deadline,
    ministry, agency, apply_period, support_target,
    support_content, receipt_place, inquiry, detail_url,
    relevance_score, relevance_grade,
    recurring_flag, recurring_group,
    matched_keywords, note, attachments="",
):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        relevance_score = int(relevance_score)
    except Exception:
        relevance_score = 0

    progress_status = DEFAULT_PROGRESS_STATUS

    hidden_yn = "Y" if should_hide_notice_by_status(
        receipt_status=status,
        progress_status=progress_status
    ) else "N"

    return [
        announce_date, title, relevance_score, relevance_grade, deadline,
        ministry, agency, apply_period, support_target, support_content,
        receipt_place, inquiry, detail_url,
        str(uuid.uuid4()), now, source, status, progress_status, now, SYSTEM_USER,
        hidden_yn, "", "",
        recurring_flag, recurring_group, matched_keywords, attachments, note
    ]


