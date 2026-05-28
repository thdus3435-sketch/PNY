# =========================================================
# 11) 중복 제거
# =========================================================
def dedupe_new_rows_by_history(
    rows,
    history_link_keys,
    history_unique_keys,
    history_cross_site_title_keys
):
    deduped = []
    seen_in_batch_link = set()
    seen_in_batch_unique = set()
    seen_in_batch_cross_site_title = set()

    for row in rows:
        link_key, unique_key = make_notice_keys_from_raw_row(row)
        cross_site_title_key = make_cross_site_title_key_from_raw_row(row)

        # 1. 기존 링크키 기준 중복 제거
        if link_key and (link_key in history_link_keys or link_key in seen_in_batch_link):
            continue

        # 2. 기존 고유키 기준 중복 제거
        if unique_key and (unique_key in history_unique_keys or unique_key in seen_in_batch_unique):
            continue

        # 3. 사이트가 달라도 공고명이 같으면 중복 제거
        if cross_site_title_key and (
            cross_site_title_key in history_cross_site_title_keys
            or cross_site_title_key in seen_in_batch_cross_site_title
        ):
            print(f"[사이트간 중복제외] 제목={safe_get(row, 1)}")
            continue

        if link_key:
            seen_in_batch_link.add(link_key)

        if unique_key:
            seen_in_batch_unique.add(unique_key)

        if cross_site_title_key:
            seen_in_batch_cross_site_title.add(cross_site_title_key)

        deduped.append(row)

    return deduped

# =========================================================
# 12) 메인 실행
# =========================================================
# =========================================================
# 12) 메인 실행
# =========================================================
def run():
    print(f"실행 시각: {now_str()}")
    print(f"정기 모니터링 사업군 개수: {len(REGULAR_MONITORING_PROGRAMS)}")
    print(f"전체 키워드 개수: {len(KEYWORD_WEIGHT_MAP)}")
    print(f"최고 가점 키워드 개수: {len(HIGHEST_PRIORITY_KEYWORDS)}")
    print(f"가점 키워드 개수: {len(HIGH_PRIORITY_KEYWORDS)}")

    (
        spreadsheet,
        new_sheet,
        history_sheet,
        error_sheet,
        recurring_master_sheet,
        recurring_result_sheet,
        status_log_sheet,
        filter_drop_sheet
    ) = setup_google_sheets()

    new_sheet = ensure_sheet_header(
        new_sheet,
        NEW_NOTICE_HEADERS,
        mismatch_mode=HEADER_MISMATCH_MODE,
        spreadsheet=spreadsheet
    )

    history_sheet = ensure_sheet_header(
        history_sheet,
        HISTORY_HEADERS,
        mismatch_mode=HEADER_MISMATCH_MODE,
        spreadsheet=spreadsheet
    )

    error_sheet = ensure_sheet_header(
        error_sheet,
        ERROR_HEADERS,
        mismatch_mode=HEADER_MISMATCH_MODE,
        spreadsheet=spreadsheet
    )

    recurring_master_sheet = ensure_sheet_header(
        recurring_master_sheet,
        RECURRING_MASTER_HEADERS,
        mismatch_mode=HEADER_MISMATCH_MODE,
        spreadsheet=spreadsheet
    )

    recurring_result_sheet = ensure_sheet_header(
        recurring_result_sheet,
        RECURRING_RESULT_HEADERS,
        mismatch_mode=HEADER_MISMATCH_MODE,
        spreadsheet=spreadsheet
    )

    status_log_sheet = ensure_sheet_header(
        status_log_sheet,
        STATUS_LOG_HEADERS,
        mismatch_mode=HEADER_MISMATCH_MODE,
        spreadsheet=spreadsheet
    )

    filter_drop_sheet = ensure_sheet_header(
        filter_drop_sheet,
        FILTER_DROP_HEADERS,
        mismatch_mode=HEADER_MISMATCH_MODE,
        spreadsheet=spreadsheet
    )

    refresh_hidden_status_for_existing_notices(new_sheet)
    seed_recurring_master_sheet_if_empty(recurring_master_sheet)

    # 기존 수집이력 기준 중복키 로드
    # - 링크키: 같은 사이트/같은 링크 중복 방지
    # - 고유키: 기존 로직 기준 중복 방지
    # - 공통공고명키: IRIS/기업마당/스마트공장 간 같은 공고명 중복 방지
    (
        history_link_keys,
        history_unique_keys,
        history_cross_site_title_keys
    ) = build_existing_history_keys(history_sheet)

    runtime_cross_site_title_keys = set(history_cross_site_title_keys)
    all_rows = []
    driver = None

    try:
        # -------------------------------------------------
        # 1) 기업마당 수집
        # -------------------------------------------------
        try:
            biz_rows = scrape_bizinfo_recent(LOOKBACK_DAYS)
            all_rows.extend(biz_rows)
            add_cross_site_title_keys_from_rows(biz_rows, runtime_cross_site_title_keys)
        except Exception as e:
            log_error("기업마당", "전체수집", "", BIZINFO_LIST_URL, e)

        # -------------------------------------------------
        # 2) 부처 공고판 수집
        # -------------------------------------------------
        ministry_sources = [
            ("중기부", scrape_mss_recent, MSS_LIST_URL),
            ("산자부", scrape_motir_recent, MOTIR_LIST_URL),
            ("과기부", scrape_msit_recent, MSIT_LIST_URL),
        ]

        for source_name, scraper, source_url in ministry_sources:
            try:
                ministry_rows = scraper(
                    LOOKBACK_DAYS,
                    skip_cross_site_title_keys=runtime_cross_site_title_keys
                )
                all_rows.extend(ministry_rows)
                add_cross_site_title_keys_from_rows(ministry_rows, runtime_cross_site_title_keys)
            except Exception as e:
                log_error(source_name, "전체수집", "", source_url, e)

        # -------------------------------------------------
        # 3) Selenium 드라이버 생성
        # -------------------------------------------------
        print("[드라이버] 생성 시작")

        try:
            driver = setup_driver(download_dir=SMART_FACTORY_DOWNLOAD_DIR)
            print("[드라이버] 생성 완료")
        except Exception as e:
            print("[드라이버] 생성 실패:", str(e))
            log_error("Selenium", "드라이버생성", "", "", e)
            driver = None

        if driver:
            # -------------------------------------------------
            # 4) IRIS 수집
            # -------------------------------------------------
            try:
                print("[IRIS] 호출 직전")
                iris_rows = scrape_iris_recent(
                    driver,
                    LOOKBACK_DAYS,
                    skip_cross_site_title_keys=runtime_cross_site_title_keys
                )
                all_rows.extend(iris_rows)
                add_cross_site_title_keys_from_rows(iris_rows, runtime_cross_site_title_keys)
            except Exception as e:
                log_error("IRIS", "전체수집", "", IRIS_URL, e)

            # -------------------------------------------------
            # 5) 스마트공장 수집
            # -------------------------------------------------
            try:
                print("[스마트공장] 호출 직전")
                sf_rows = scrape_smart_factory_recent(
                    driver,
                    LOOKBACK_DAYS,
                    skip_cross_site_title_keys=runtime_cross_site_title_keys
                )
                all_rows.extend(sf_rows)
                add_cross_site_title_keys_from_rows(sf_rows, runtime_cross_site_title_keys)
            except Exception as e:
                log_error(
                    "스마트공장",
                    "전체수집",
                    "",
                    ", ".join(SMART_FACTORY_TARGET_URLS),
                    e
                )
        else:
            print("[Selenium] 드라이버 생성 실패로 IRIS/스마트공장 수집 생략")

        # -------------------------------------------------
        # 6) 기존 공고 업데이트
        # -------------------------------------------------
        # 이미 신규공고 시트에 있는 공고 중
        # 새로 수집한 상세링크/첨부파일/비고가 더 정확한 경우 기존 행 보정
        update_existing_notice_rows_by_unique_key(new_sheet, all_rows)

        # 신규 저장 대상 중복 제거
        new_raw_rows = dedupe_new_rows_by_history(
            all_rows,
            history_link_keys,
            history_unique_keys,
            history_cross_site_title_keys
        )

        new_notice_rows = new_raw_rows

        # 신규공고 / 수집이력 / 정기공고탐지결과 저장
        if new_notice_rows:
            write_rows_from_first_empty(new_sheet, new_notice_rows)
            refresh_hidden_status_for_existing_notices(new_sheet)
            sort_sheet_by_relevance_score(new_sheet)

            history_rows = make_history_rows_from_raw(new_raw_rows)
            write_rows_from_first_empty(history_sheet, history_rows)

            recurring_detect_rows = make_recurring_result_rows_from_raw(new_raw_rows)
            write_recurring_result_rows(recurring_result_sheet, recurring_detect_rows)

        else:
            print("[신규공고] 신규 저장 0건 - 신규공고/이력/정기탐지 시트 업데이트 생략")

        # 오래된 이력 정리
        prune_old_history(history_sheet, HISTORY_RETENTION_DAYS)

        # 실행 결과 요약 출력
        high_priority_count = 0
        recurring_count = 0

        for row in new_raw_rows:
            try:
                score = int(safe_get(row, 2, "0") or 0)  # 적합도점수
            except Exception:
                score = 0

            if score >= HIGH_PRIORITY_SCORE:
                high_priority_count += 1

            if clean_text(safe_get(row, 23)) == "Y":  # 정기공고여부
                recurring_count += 1

        print("=" * 100)
        print(f"전체 수집(필터 통과): {len(all_rows)}건")
        print(f"신규 저장: {len(new_raw_rows)}건")
        print(f"정기공고 탐지: {recurring_count}건")
        print(f"고우선 적합도({HIGH_PRIORITY_SCORE}점 이상): {high_priority_count}건")
        print("=" * 100)

    finally:
        if driver:
            driver.quit()

        write_filter_drop_rows(filter_drop_sheet, FILTER_DROP_ROWS)
        refresh_error_logs(error_sheet, ERROR_LOGS)


if __name__ == "__main__":
    run()
