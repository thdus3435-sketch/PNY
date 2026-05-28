# =========================================================
# 4) 구글시트 서비스
# =========================================================
def setup_google_client():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
    return gspread.authorize(creds)


def get_or_create_worksheet(spreadsheet, title, rows=2000, cols=40):
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)


def setup_google_sheets():
    client = setup_google_client()
    spreadsheet = client.open_by_key(SHEET_ID)

    main_sheet = get_or_create_worksheet(spreadsheet, WORKSHEET_NAME, rows=10000, cols=50)
    history_sheet = get_or_create_worksheet(spreadsheet, HISTORY_WORKSHEET_NAME, rows=30000, cols=10)
    error_sheet = get_or_create_worksheet(spreadsheet, ERROR_WORKSHEET_NAME, rows=5000, cols=10)
    recurring_master_sheet = get_or_create_worksheet(spreadsheet, RECURRING_MASTER_WORKSHEET_NAME, rows=1000, cols=10)
    recurring_result_sheet = get_or_create_worksheet(spreadsheet, RECURRING_RESULT_WORKSHEET_NAME, rows=5000, cols=20)
    status_log_sheet = get_or_create_worksheet(spreadsheet, STATUS_LOG_WORKSHEET_NAME, rows=10000, cols=20)
    filter_drop_sheet = get_or_create_worksheet(spreadsheet, FILTER_DROP_WORKSHEET_NAME, rows=30000, cols=20)

    return (
        spreadsheet,
        main_sheet,
        history_sheet,
        error_sheet,
        recurring_master_sheet,
        recurring_result_sheet,
        status_log_sheet,
        filter_drop_sheet
    )

def clear_worksheet_values(sheet):
    """시트의 모든 값을 삭제한다. 헤더는 이후 ensure_sheet_header에서 다시 생성된다."""
    title = getattr(sheet, "title", "")
    sheet.clear()
    print(f"[{title}] 전체 내용 삭제 완료")


def clear_test_run_sheets():
    """
    테스트 실행 전 결과성 시트를 비운다.

    대상:
    - 신규공고
    - 수집이력(수정금지)
    - 정기공고탐지결과
    - 상태변경로그
    - 필터탈락공고(필터링확인용)
    """
    (
        _spreadsheet,
        new_sheet,
        history_sheet,
        _error_sheet,
        _recurring_master_sheet,
        recurring_result_sheet,
        status_log_sheet,
        filter_drop_sheet
    ) = setup_google_sheets()

    for sheet in [
        new_sheet,
        history_sheet,
        recurring_result_sheet,
        status_log_sheet,
        filter_drop_sheet,
    ]:
        clear_worksheet_values(sheet)


def col_num_to_letter(n: int) -> str:
    """
    1 -> A, 26 -> Z, 27 -> AA 변환
    """
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def normalize_header_row(row):
    """
    시트에서 읽어온 헤더 행 비교용 정리
    - None 제거
    - 앞뒤 공백 제거
    - 뒤쪽 빈칸 제거
    """
    if not row:
        return []

    cleaned = [clean_text(x) for x in row]

    while cleaned and cleaned[-1] == "":
        cleaned.pop()

    return cleaned


def replace_header(sheet, headers):
    """
    헤더 행을 코드 기준으로 업데이트

    기존 문제:
    - 새 헤더가 기존 헤더보다 짧으면 뒤쪽 옛날 헤더가 남을 수 있음

    개선:
    - 기존 헤더 길이와 새 헤더 길이 중 더 긴 길이만큼 1행을 덮어씀
    - 새 헤더 뒤쪽은 빈칸으로 채워서 기존 잔여 헤더 제거
    """
    headers = [clean_text(h) for h in headers]

    values = sheet.get_all_values()
    old_header = values[0] if values else []

    max_len = max(len(old_header), len(headers))

    if max_len == 0:
        return

    padded_headers = headers + [""] * (max_len - len(headers))

    end_col = col_num_to_letter(max_len)

    sheet.update(
        range_name=f"A1:{end_col}1",
        values=[padded_headers],
        value_input_option="USER_ENTERED"
    )


def ensure_sheet_header(sheet, expected_headers, mismatch_mode="overwrite", spreadsheet=None):
    """
    시트 헤더 확인 및 보정

    동작:
    1. 시트가 비어 있으면 헤더 생성
    2. 기존 헤더와 코드 헤더가 같으면 통과
    3. 다르면 overwrite 모드에서는 코드 기준으로 헤더 보정
    4. stop 모드에서는 실행 중단
    """
    expected_headers = [clean_text(h) for h in expected_headers]

    values = sheet.get_all_values()

    if not values:
        sheet.append_row(expected_headers, value_input_option="USER_ENTERED")
        print(f"[{sheet.title}] 헤더 생성 완료")
        return sheet

    current_header = normalize_header_row(values[0])

    if not current_header:
        replace_header(sheet, expected_headers)
        print(f"[{sheet.title}] 헤더 생성 완료")
        return sheet

    if current_header == expected_headers:
        return sheet

    detail_msg = (
        f"기존 헤더: {current_header}\n"
        f"코드 헤더: {expected_headers}"
    )

    print(f"[{sheet.title}] 기존 헤더와 코드 헤더 불일치")

    try:
        log_error(
            source="GoogleSheet",
            stage="헤더불일치",
            title=sheet.title,
            url="",
            detail=detail_msg
        )
    except Exception:
        pass

    if mismatch_mode == "overwrite":
        replace_header(sheet, expected_headers)
        print(f"[{sheet.title}] 헤더 덮어쓰기 완료")

        try:
            log_error(
                source="GoogleSheet",
                stage="헤더덮어쓰기완료",
                title=sheet.title,
                url="",
                detail=f"{sheet.title} 시트 헤더를 코드 기준으로 덮어썼습니다."
            )
        except Exception:
            pass

        return sheet

    raise RuntimeError(f"[{sheet.title}] 헤더 불일치로 실행 중단")

def seed_recurring_master_sheet_if_empty(sheet):
    values = sheet.get_all_values()
    if len(values) > 1:
        return

    seed_rows = []

    for idx, item in enumerate(REGULAR_MONITORING_PROGRAMS, start=1):
        seed_rows.append([
            f"REG-{idx:03d}",
            item.get("group", ""),
            "",
            item.get("priority", ""),
            " | ".join(item.get("aliases", []))
        ])

    if seed_rows:
        write_rows_from_first_empty(sheet, seed_rows)
        print(f"[{sheet.title}] 정기 모니터링 마스터 {len(seed_rows)}건 초기 입력 완료")


def build_existing_history_keys(history_sheet):
    values = history_sheet.get_all_values()
    existing_link_keys = set()
    existing_unique_keys = set()
    existing_cross_site_title_keys = set()

    if len(values) <= 1:
        return existing_link_keys, existing_unique_keys, existing_cross_site_title_keys

    header = values[0]
    idx_map = {name: i for i, name in enumerate(header)}

    idx_link = idx_map.get("링크키")
    idx_unique = idx_map.get("고유키")
    idx_cross_site_title = idx_map.get("공통공고명키")
    idx_title = idx_map.get("공고명")

    for row in values[1:]:
        link_key = ""
        unique_key = ""
        cross_site_title_key = ""

        if idx_link is not None and len(row) > idx_link:
            link_key = clean_text(row[idx_link])
            if link_key:
                existing_link_keys.add(link_key)

        if idx_unique is not None and len(row) > idx_unique:
            unique_key = clean_text(row[idx_unique])
            if unique_key:
                existing_unique_keys.add(unique_key)

        # 1차: 공통공고명키 컬럼 사용
        if idx_cross_site_title is not None and len(row) > idx_cross_site_title:
            cross_site_title_key = clean_text(row[idx_cross_site_title])

        # 기존 행에서 공통공고명키 자리에 공고일이 들어간 경우 방지
        if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", cross_site_title_key):
            cross_site_title_key = ""

        # 2차: 공고명 컬럼에서 생성
        if not cross_site_title_key and idx_title is not None and len(row) > idx_title:
            title = clean_text(row[idx_title])
            if title and not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", title):
                cross_site_title_key = normalize_title(title)

        # 3차: 고유키에서 공고명 normalize 값 추출
        # 일반 고유키 구조:
        # 출처||소관부처||수행기관||normalized_title||공고일||마감일
        if not cross_site_title_key and unique_key:
            parts = unique_key.split("||")

            if len(parts) >= 4:
                # 일반 사이트
                if parts[0] in ["기업마당", "IRIS"]:
                    cross_site_title_key = clean_text(parts[3])

                # 스마트공장 공고번호 없는 경우
                elif parts[0] == "스마트공장":
                    if len(parts) >= 2:
                        # source||normalized_title||공고일||신청기간||상태
                        cross_site_title_key = clean_text(parts[1])

        if cross_site_title_key:
            existing_cross_site_title_keys.add(cross_site_title_key)

    return existing_link_keys, existing_unique_keys, existing_cross_site_title_keys

def write_rows_from_first_empty(sheet, rows):
    if not rows:
        print(f"[{sheet.title}] 저장할 데이터 없음")
        return

    values = sheet.get_all_values()
    start_row = len(values) + 1
    range_start = f"A{start_row}"

    sheet.update(
        range_name=range_start,
        values=rows,
        value_input_option="USER_ENTERED"
    )

    print(f"[{sheet.title}] {start_row}행부터 {len(rows)}건 작성 완료")

def ensure_filter_drop_header_strict(sheet):
    """
    필터탈락공고 시트 헤더 강제 보정
    - 시트가 비어 있으면 헤더 생성
    - 1행이 데이터처럼 보이면 헤더를 1행에 삽입
    - 헤더가 다르면 코드 기준으로 덮어쓰기
    """
    expected_headers = [clean_text(h) for h in FILTER_DROP_HEADERS]
    values = sheet.get_all_values()

    if not values:
        sheet.update(
            range_name="A1",
            values=[expected_headers],
            value_input_option="USER_ENTERED"
        )
        print(f"[{sheet.title}] 필터탈락 헤더 생성 완료")
        return

    current_header = normalize_header_row(values[0])

    if current_header == expected_headers:
        return

    first_cell = clean_text(safe_get(values[0], 0))

    # 첫 행이 날짜로 시작하면 데이터가 1행에 들어간 상태로 판단
    if re.match(r"20\d{2}-\d{2}-\d{2}", first_cell):
        sheet.insert_row(expected_headers, index=1, value_input_option="USER_ENTERED")
        print(f"[{sheet.title}] 필터탈락 헤더 1행 삽입 완료")
        return

    replace_header(sheet, expected_headers)
    print(f"[{sheet.title}] 필터탈락 헤더 보정 완료")

def build_existing_filter_drop_keys(sheet):
    """
    필터탈락공고 시트에 이미 저장된 공고 중복키 생성
    기준:
    - 출처
    - 공고명 normalize
    - 상세링크
    """
    values = sheet.get_all_values()

    if len(values) <= 1:
        return set()

    header = values[0]
    idx = {name: i for i, name in enumerate(header)}

    existing_keys = set()

    for row in values[1:]:
        source = clean_text(safe_get(row, idx.get("출처", -1)))
        title = clean_text(safe_get(row, idx.get("공고명", -1)))
        detail_url = clean_text(safe_get(row, idx.get("상세링크", -1)))
        note = clean_text(safe_get(row, idx.get("비고", -1)))

        if not title:
            continue

        original_url = extract_original_link_from_note(note) or detail_url
        key = f"{source}||{normalize_title(title)}||{original_url}"
        existing_keys.add(key)

    return existing_keys

def write_filter_drop_rows(sheet, rows):
    """
    필터탈락공고 저장 전 헤더를 보장하고,
    기존 시트에 이미 있는 필터탈락 공고는 중복 저장하지 않는다.
    """
    ensure_filter_drop_header_strict(sheet)

    if not rows:
        print(f"[{sheet.title}] 필터탈락 저장할 데이터 없음")
        return

    existing_keys = build_existing_filter_drop_keys(sheet)

    deduped_rows = []
    seen_batch = set()

    for row in rows:
        source = clean_text(safe_get(row, 1))       # 출처
        title = clean_text(safe_get(row, 2))        # 공고명
        detail_url = clean_text(safe_get(row, 7))   # 상세링크
        note = clean_text(safe_get(row, 8))         # 비고

        if not title:
            continue

        original_url = extract_original_link_from_note(note) or detail_url
        key = f"{source}||{normalize_title(title)}||{original_url}"

        if key in existing_keys:
            print(f"[{sheet.title}] 기존 필터탈락 중복 제외: {title}")
            continue

        if key in seen_batch:
            print(f"[{sheet.title}] 배치 내 필터탈락 중복 제외: {title}")
            continue

        seen_batch.add(key)
        deduped_rows.append(row)

    if not deduped_rows:
        print(f"[{sheet.title}] 신규 필터탈락 저장 0건 - 중복 제외")
        return

    sheet.insert_rows(deduped_rows, row=2, value_input_option="USER_ENTERED")
    print(f"[{sheet.title}] 헤더 아래 {len(deduped_rows)}건 삽입 완료")
def sort_sheet_by_relevance_score(sheet):
    """
    신규공고 시트를 적합도점수 내림차순으로 정렬
    1순위: 적합도점수 높은 순
    2순위: 공고일 최신순
    """
    values = sheet.get_all_values()

    if len(values) <= 1:
        return

    header = values[0]
    rows = values[1:]

    if "적합도점수" not in header:
        print(f"[{sheet.title}] 적합도점수 컬럼 없음 - 정렬 생략")
        return

    score_idx = header.index("적합도점수")
    date_idx = header.index("공고일") if "공고일" in header else -1

    def to_number(value):
        try:
            return float(str(value).replace(",", "").strip())
        except Exception:
            return 0

    def date_key(value):
        value = normalize_date(value)
        return value or ""

    rows_sorted = sorted(
        rows,
        key=lambda row: (
            to_number(safe_get(row, score_idx)),
            date_key(safe_get(row, date_idx)) if date_idx != -1 else ""
        ),
        reverse=True
    )

    sheet.clear()
    sheet.update(
        range_name="A1",
        values=[header] + rows_sorted,
        value_input_option="USER_ENTERED"
    )

    print(f"[{sheet.title}] 적합도점수 기준 내림차순 정렬 완료")


def prepend_rows_below_header(sheet, rows):
    if not rows:
        print(f"[{sheet.title}] 추가할 데이터 없음")
        return

    sheet.insert_rows(rows, row=2, value_input_option="USER_ENTERED")
    print(f"[{sheet.title}] 헤더 아래 {len(rows)}건 삽입 완료")


def prune_old_error_logs(error_sheet, retention_days=3):
    values = error_sheet.get_all_values()
    if len(values) <= 1:
        return

    header = values[0]
    rows = values[1:]
    cutoff = datetime.now() - timedelta(days=retention_days)

    kept = []
    for row in rows:
        dt = parse_datetime_safe(safe_get(row, 0))
        if dt is None:
            kept.append(row)
            continue
        if dt >= cutoff:
            kept.append(row)

    all_values = [header] + kept
    error_sheet.clear()
    error_sheet.update(range_name="A1", values=all_values)
    print(f"[{error_sheet.title}] {retention_days}일 지난 오류 로그 삭제 완료")


def refresh_error_logs(error_sheet, new_logs):
    prune_old_error_logs(error_sheet, ERROR_LOG_RETENTION_DAYS)

    if not new_logs:
        print(f"[{error_sheet.title}] 신규 오류 로그 없음")
        return

    prepend_rows_below_header(error_sheet, new_logs)


def prune_old_history(history_sheet, retention_days=None):
    if retention_days is None:
        print(f"[{history_sheet.title}] 수집이력 누적 보관")
        return

    values = history_sheet.get_all_values()
    if len(values) <= 1:
        return

    header = values[0]
    rows = values[1:]
    cutoff = datetime.now() - timedelta(days=retention_days)

    kept = []
    for row in rows:
        dt = parse_datetime_safe(safe_get(row, 0))
        if dt is None:
            kept.append(row)
            continue
        if dt >= cutoff:
            kept.append(row)

    all_values = [header] + kept
    history_sheet.clear()
    history_sheet.update(range_name="A1", values=all_values)
    print(f"[{history_sheet.title}] {retention_days}일 지난 이력 삭제 완료")

def get_header_index_map(sheet):
    values = sheet.get_all_values()
    if not values:
        return {}
    return {name: i for i, name in enumerate(values[0])}


def append_status_log(
    status_log_sheet,
    notice_id,
    notice_title,
    old_status,
    new_status,
    reason="",
    memo="",
    actor=SYSTEM_USER
):
    row = [
        now_str(),
        notice_id,
        notice_title,
        old_status,
        new_status,
        reason,
        memo,
        actor
    ]
    write_rows_from_first_empty(status_log_sheet, [row])


def update_notice_status(
    new_sheet,
    status_log_sheet,
    notice_id,
    new_status,
    actor,
    reason="",
    memo=""
):
    values = new_sheet.get_all_values()
    if len(values) <= 1:
        raise RuntimeError("신규공고 시트에 데이터가 없습니다.")

    header = values[0]
    idx = {name: i for i, name in enumerate(header)}

    required_cols = [
        "공고ID", "공고명", "접수상태", "진행상태", "상태변경일시", "상태변경자",
        "미진행사유", "상태변경메모", "숨김여부"
    ]
    for col in required_cols:
        if col not in idx:
            raise RuntimeError(f"신규공고 시트에 '{col}' 컬럼이 없습니다.")

    target_row_num = None
    target_row = None

    for i, row in enumerate(values[1:], start=2):
        if clean_text(safe_get(row, idx["공고ID"])) == clean_text(notice_id):
            target_row_num = i
            target_row = row
            break

    if not target_row_num:
        raise RuntimeError(f"공고ID '{notice_id}'를 찾지 못했습니다.")

    old_status = safe_get(target_row, idx["진행상태"])
    notice_title = safe_get(target_row, idx["공고명"])

    receipt_status = safe_get(target_row, idx.get("접수상태", -1))

    hidden_yn = "Y" if should_hide_notice_by_status(
        receipt_status=receipt_status,
        progress_status=new_status
    ) else "N"

    new_sheet.update(range_name=f"{chr(65 + idx['진행상태'])}{target_row_num}", values=[[new_status]])
    new_sheet.update(range_name=f"{chr(65 + idx['상태변경일시'])}{target_row_num}", values=[[now_str()]])
    new_sheet.update(range_name=f"{chr(65 + idx['상태변경자'])}{target_row_num}", values=[[actor]])
    new_sheet.update(range_name=f"{chr(65 + idx['미진행사유'])}{target_row_num}", values=[[reason]])
    new_sheet.update(range_name=f"{chr(65 + idx['상태변경메모'])}{target_row_num}", values=[[memo]])
    new_sheet.update(range_name=f"{chr(65 + idx['숨김여부'])}{target_row_num}", values=[[hidden_yn]])

    append_status_log(
        status_log_sheet=status_log_sheet,
        notice_id=notice_id,
        notice_title=notice_title,
        old_status=old_status,
        new_status=new_status,
        reason=reason,
        memo=memo,
        actor=actor
    )

def refresh_hidden_status_for_existing_notices(new_sheet):
    """기존 신규공고 시트의 숨김여부를 접수상태/신청기간/진행상태 기준으로 보정한다."""
    values = new_sheet.get_all_values()

    if len(values) <= 1:
        print("[신규공고] 숨김여부 보정 대상 없음")
        return 0

    header = values[0]
    rows = values[1:]

    idx = {name: i for i, name in enumerate(header)}

    required_cols = ["접수상태", "진행상태", "신청기간", "숨김여부"]

    for col in required_cols:
        if col not in idx:
            raise RuntimeError(f"신규공고 시트에 '{col}' 컬럼이 없습니다.")

    hidden_col_num = idx["숨김여부"] + 1
    hidden_col_letter = col_num_to_letter(hidden_col_num)

    updates = []
    changed_count = 0

    for row_num, row in enumerate(rows, start=2):
        receipt_status = clean_text(safe_get(row, idx["접수상태"]))
        progress_status = clean_text(safe_get(row, idx["진행상태"]))
        apply_period = clean_text(safe_get(row, idx["신청기간"]))
        current_hidden_yn = clean_text(safe_get(row, idx["숨김여부"]))

        calculated_status = classify_status_from_apply_period(apply_period)

        if calculated_status in ["접수예정", "접수중", "마감"]:
            effective_receipt_status = calculated_status
        else:
            effective_receipt_status = receipt_status

        new_hidden_yn = "Y" if should_hide_notice_by_status(
            receipt_status=effective_receipt_status,
            progress_status=progress_status
        ) else "N"

        if current_hidden_yn != new_hidden_yn:
            updates.append({
                "range": f"{hidden_col_letter}{row_num}",
                "values": [[new_hidden_yn]]
            })
            changed_count += 1

    if updates:
        new_sheet.batch_update(updates, value_input_option="USER_ENTERED")

    print(f"[신규공고] 기존 공고 숨김여부 보정 완료: {changed_count}건 변경")
    return changed_count

def get_active_notices(new_sheet):
    values = new_sheet.get_all_values()
    if len(values) <= 1:
        return []

    header = values[0]
    idx = {name: i for i, name in enumerate(header)}

    results = []
    for row in values[1:]:
        hidden_yn = clean_text(safe_get(row, idx.get("숨김여부", -1)))
        if hidden_yn == "Y":
            continue

        receipt_status = clean_text(safe_get(row, idx.get("접수상태", -1)))
        if is_closed_receipt_status(receipt_status):
            continue

        results.append(row)

    return results

