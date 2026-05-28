import time
import re
import json
import html
import uuid
import traceback
import os
import sys
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, parse_qs

# Keep Windows console output from failing on characters outside cp949.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from bs4 import BeautifulSoup

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

# =========================================================
# 1) 기본 설정
# =========================================================
JSON_KEY_FILE = "key.json"
SHEET_ID = "18WxHYXwyRwf9X-NGh4pY09RDyS1B7gVs9iFqm-eIARw"

WORKSHEET_NAME = "신규공고"
HISTORY_WORKSHEET_NAME = "수집이력(수정금지)"
ERROR_WORKSHEET_NAME = "수집오류로그"
RECURRING_MASTER_WORKSHEET_NAME = "정기지원(수정금지)"
RECURRING_RESULT_WORKSHEET_NAME = "정기공고탐지결과"
STATUS_LOG_WORKSHEET_NAME = "상태변경로그"
FILTER_DROP_WORKSHEET_NAME = "필터탈락공고(필터링확인용)"

DEFAULT_PROGRESS_STATUS = "신규"
DEFAULT_HIDDEN_YN = "N"
SYSTEM_USER = "system"

LOOKBACK_DAYS = 5
IRIS_INCLUDE_UNDATED = False
SMART_FACTORY_PRE_FILTER_BEFORE_DETAIL = True

HEADER_MISMATCH_MODE = "overwrite"   # overwrite / stop

ERROR_LOG_RETENTION_DAYS = 3
HISTORY_RETENTION_DAYS = None

REQUEST_TIMEOUT = 20
BIZINFO_LIST_ROWS = 15

BIZINFO_BASE = "https://www.bizinfo.go.kr"
BIZINFO_LIST_URL = f"{BIZINFO_BASE}/web/lay1/bbs/S1T122C128/AS/74/list.do"
BIZINFO_DETAIL_PREFIX = f"{BIZINFO_BASE}/web/lay1/bbs/S1T122C128/AS/74/"

IRIS_URL = "https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do"

SMART_FACTORY_BASE_URL = "https://www.smart-factory.kr"
SMART_FACTORY_TARGET_URLS = [
    "https://www.smart-factory.kr/usr/bg/ra/ma/rcrtPbanc",
    "https://www.smart-factory.kr/usr/bg/ba/ma/bsnsPbanc",
]

SMART_FACTORY_DETAIL_TIMEOUT = 8
SMART_FACTORY_CAPTURE_LINKCOPY = True

SMART_FACTORY_DOWNLOAD_ATTACHMENTS = False
SMART_FACTORY_CAPTURE_DOWNLOAD_URL = True

SMART_FACTORY_DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads", "smart_factory")

# =========================================================
# 2) 정기 모니터링 대상 / 키워드 / 적합도 설정
# =========================================================
def clean_text(text: str) -> str:
    if text is None:
        return ""
    text = str(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()

def normalize_date(date_str: str) -> str:
    """
    날짜 문자열을 YYYY-MM-DD 형식으로 정규화

    지원 예:
    - 2026.05.18
    - 2026-05-18
    - 2026/05/18
    - 2026년 5월 18일
    - 2026. 5. 18.
    """
    date_str = clean_text(date_str)

    if not date_str:
        return ""

    # 2026년 5월 18일
    m = re.search(
        r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일?",
        date_str
    )
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    # 2026.05.18 / 2026-05-18 / 2026/05/18 / 2026. 5. 18.
    m = re.search(
        r"(20\d{2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{1,2})",
        date_str
    )
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    return ""

def normalize_for_match(text: str) -> str:
    """
    키워드 매칭용 정규화
    - 공백, 특수문자, 하이픈, 점 차이 제거
    - 영문 대소문자 통일
    """
    if text is None:
        return ""

    text = str(text).lower()
    text = text.replace("\xa0", " ")

    replace_map = {
        "ax-sprint": "axsprint",
        "ax sprint": "axsprint",
        "ai-agent": "aiagent",
        "ai agent": "aiagent",
        "multi-ai": "multiai",
        "multi ai": "multiai",
        "r&d": "rnd",
        "r/d": "rnd",
        "opc-ua": "opcua",
        "opc ua": "opcua",
        "·": "",
        "ㆍ": "",
        "-": "",
        "_": "",
        "/": "",
        " ": "",
        "(": "",
        ")": "",
        "[": "",
        "]": "",
        "{": "",
        "}": "",
        ".": "",
    }

    for old, new in replace_map.items():
        text = text.replace(old, new)

    text = re.sub(r"[^0-9a-z가-힣]", "", text)
    return text

def dedupe_keywords_by_normalized_form(keywords):
    """
    띄어쓰기/하이픈/특수문자 차이만 있는 중복 키워드 제거
    예:
    제조AI / 제조 AI -> 제조AI
    AX-Sprint / AX Sprint / AXSprint -> 먼저 나온 값만 유지
    """
    deduped = []
    seen = set()

    for kw in keywords:
        kw = clean_text(kw)

        if not kw:
            continue

        key = normalize_for_match(kw)

        if not key:
            continue

        if key in seen:
            continue

        seen.add(key)
        deduped.append(kw)

    return deduped

def dedupe_regular_monitoring_programs(programs):
    """
    정기 모니터링 대상 alias 중
    띄어쓰기/하이픈/특수문자 차이만 있는 중복 alias 제거
    """
    for item in programs:
        item["aliases"] = dedupe_keywords_by_normalized_form(item.get("aliases", []))
    return programs

# =========================================================
# 3) 정기 모니터링 대상 / 키워드 / 적합도 설정
# =========================================================

# ---------------------------------------------------------
# 3-1. 정기 모니터링 대상
# ---------------------------------------------------------
REGULAR_MONITORING_PROGRAMS = [
    {
        "group": "스마트 제조혁신 지원사업 통합공고",
        "aliases": [
            "스마트제조혁신지원사업통합공고",
            "스마트제조혁신통합공고",
            "스마트제조혁신지원사업",
        ],
        "priority": "S",
    },
    {
        "group": "자율형공장 구축 지원사업",
        "aliases": [
            "자율형공장구축지원사업",
            "자율형공장구축지원사업공고",
        ],
        "priority": "S",
    },
    {
        "group": "부처협업형 스마트공장 구축 지원사업",
        "aliases": [
            "부처협업형스마트공장구축지원사업",
            "부처협업형스마트공장운영기관모집",
        ],
        "priority": "S",
    },
    {
        "group": "제조AI특화 스마트공장 구축지원사업",
        "aliases": [
            "제조AI특화스마트공장구축지원사업",
            "제조AI특화스마트공장",
        ],
        "priority": "S",
    },
    {
        "group": "로봇활용 제조혁신 지원사업",
        "aliases": [
            "로봇활용제조혁신지원사업",
        ],
        "priority": "S",
    },
    {
        "group": "지역특화 제조데이터 활성화사업",
        "aliases": [
            "지역특화제조데이터활성화사업",
            "지역특화제조데이터",
            "지역특화제조데이터활성화사업수행기관모집",
            "지역특화제조데이터활성화사업AI솔루션실증",
        ],
        "priority": "S",
    },
    {
        "group": "AI바우처 지원사업",
        "aliases": [
            "AI바우처지원사업",
            "AI바우처지원사업공급기업POOL모집",
            "AI통합바우처지원사업",
        ],
        "priority": "S",
    },
    {
        "group": "데이터바우처 지원사업",
        "aliases": [
            "데이터바우처지원사업",
            "데이터바우처지원사업수요기업모집",
            "데이터바우처지원사업공급기업모집",
        ],
        "priority": "S",
    },
    {
        "group": "AI 응용제품 신속 상용화 지원사업 / AX-Sprint",
        "aliases": [
            "AI응용제품신속상용화지원사업",
            "AI응용제품신속상용화",
            "AX-Sprint",
            "AXSprint",
            "AX스프린트",
        ],
        "priority": "S",
    },
    {
        "group": "산업AI 솔루션 실증·확산 지원사업",
        "aliases": [
            "산업AI솔루션실증확산지원",
            "산업AI솔루션실증확산지원사업",
            "산업AI솔루션실증·확산지원",
            "산업AI솔루션실증·확산지원사업",
        ],
        "priority": "S",
    },
    {
        "group": "AI로봇 실증사업 / 첨단제조로봇 실증사업",
        "aliases": [
            "AI로봇실증사업",
            "AI로봇실증사업제조분야",
            "첨단제조로봇실증사업",
        ],
        "priority": "S",
    },
    {
        "group": "제조안전고도화기술개발사업",
        "aliases": [
            "제조안전고도화기술개발사업",
            "제조안전고도화기술개발사업신규지원대상과제",
            "제조안전고도화기술개발사업신규지원대상과제공고",
        ],
        "priority": "S",
    },
    {
        "group": "뿌리 AI공정 시스템 구축사업",
        "aliases": [
            "뿌리AI공정시스템구축사업",
            "지능형뿌리공정시스템구축지원사업",
        ],
        "priority": "S",
    },
    {
        "group": "표준공정 기반 공정최적화 기술개발사업",
        "aliases": [
            "표준공정기반공정최적화기술개발사업",
            "표준공정기반공정최적화기술개발",
            "표준공정기반공정최적화기술개발R&D",
        ],
        "priority": "S",
    },
    {
        "group": "제조암묵지기반AI모델개발사업",
        "aliases": [
            "제조암묵지기반AI모델개발사업",
            "제조암묵지기반AI모델개발사업신규지원대상과제",
        ],
        "priority": "S",
    },
    {
        "group": "중소제조 특화 Multi AI Agent 개발사업",
        "aliases": [
            "중소제조특화MultiAIAgent개발",
            "중소제조특화MultiAIAgent개발사업",
            "중소제조특화Multi-AIAgent개발",
            "중소제조특화MultiAIAgent개발R&D",
        ],
        "priority": "S",
    },
    {
        "group": "산업현장문제해결형 산업AI 에이전트 기술개발사업",
        "aliases": [
            "산업현장문제해결형산업AI에이전트기술개발",
            "산업현장문제해결형산업AI에이전트",
            "산업AI에이전트기술개발",
        ],
        "priority": "S",
    },
    {
        "group": "AI팩토리 선도사업 / 기계장비산업기술개발사업(AI팩토리)",
        "aliases": [
            "AI팩토리선도사업",
            "기계장비산업기술개발사업AI팩토리",
            "기계장비산업기술개발사업(AI팩토리)",
        ],
        "priority": "S",
    },
    {
        "group": "제조데이터 상품가공지원사업",
        "aliases": [
            "제조데이터상품가공지원사업",
            "제조데이터상품가공지원",
            "제조데이터상품가공지원사업공고",
            "제조데이터상품가공지원가공기업Pool모집",
        ],
        "priority": "S",
    },
]

REGULAR_MONITORING_PROGRAMS = dedupe_regular_monitoring_programs(REGULAR_MONITORING_PROGRAMS)


# ---------------------------------------------------------
# 3-2. 최고가점 키워드
# ---------------------------------------------------------
HIGHEST_PRIORITY_KEYWORDS = [
    # 스마트공장 / 제조AI 핵심
    "스마트공장",
    "스마트팩토리",
    "스마트제조",
    "스마트제조혁신",
    "제조AI",
    "산업AI",
    "AI팩토리",
    "AI자율제조",
    "자율제조",
    "자율형공장",

    # AX / 실증 / 상용화
    "AX",
    "AX실증",
    "AXSprint",
    "AXSprint300",
    "AI응용제품신속상용화",
    "산업AI솔루션실증",
    "산업AI솔루션실증확산",

    # 제조데이터 / 표준화
    "제조데이터",
    "지역특화제조데이터",
    "제조데이터활성화",
    "제조데이터상품가공",
    "제조데이터표준화",
    "제조데이터공동활용",
    "AAS",
    "AssetAdministrationShell",

    # AI Agent / 생성형 AI
    "AIAgent",
    "AI에이전트",
    "MultiAIAgent",
    "중소제조특화MultiAIAgent",
    "산업현장문제해결형AIAgent",
    "산업문제해결형AIAgent",
    "AIAgent융합확산",
    "생성형AI",
    "LLM",
    "RAG",

    # 안전 / 로봇 / 피지컬AI
    "제조안전",
    "제조안전고도화",
    "제조안전기술개발",
    "스마트안전",
    "스마트안전장비",
    "피지컬AI",
    "PhysicalAI",
    "로봇활용제조혁신",
    "AI자율제조로봇",
    "첨단제조로봇",
    "자율제조로봇",

    # 디지털트윈 / 공정최적화
    "디지털트윈",
    "공정최적화",
    "표준공정기반공정최적화",
    "표준기반공정최적화",
    "공정조건최적화",
]


# ---------------------------------------------------------
# 3-3. 고가점 키워드
# ---------------------------------------------------------
HIGH_PRIORITY_KEYWORDS = [
    # AI 분석 / 예측 / 품질
    "예지보전",
    "설비예지보전",
    "이상탐지",
    "불량예측",
    "품질예측",
    "품질검사",
    "비전검사",
    "외관검사",
    "결함검출",
    "불량검출",
    "머신비전",
    "컴퓨터비전",

    # 제조 데이터 / 공정 데이터
    "공정데이터",
    "설비데이터",
    "품질데이터",
    "센서데이터",
    "시계열데이터",
    "생산데이터",
    "제조공정",
    "공정조건",

    # OT / 현장 시스템
    "MES",
    "ERP",
    "ERP연계",
    "PLC",
    "OT",
    "OPCUA",
    "SCADA",
    "EdgeAI",
    "엣지AI",
    "온디바이스AI",
    "MLOps",
    "ModelOps",

    # 자동화 / 로봇
    "공정자동화",
    "제조자동화",
    "자동화공정",
    "로봇자동화",
    "협동로봇",
    "산업용로봇",

    # 제조 도메인
    "뿌리산업",
    "뿌리공정",
    "지능형뿌리공정",
    "용접",
    "도장",
    "주조",
    "열처리",
    "소성가공",
    "절삭가공",
    "연삭",
    "사출",
    "금형",
    "가공",
    "조립",
    "검사공정",

    # 정부사업명 확장
    "AI바우처",
    "데이터바우처",
    "혁신바우처",
    "기술혁신개발",
    "중소기업기술혁신개발",
    "산업기술혁신",
    "산업집적지경쟁력강화",
    "스마트그린산단",
    "스마트생태공장",
    "에너지기술개발",
]

# ---------------------------------------------------------
# 3-5. 키워드 중복 제거 적용
# ---------------------------------------------------------
HIGHEST_PRIORITY_KEYWORDS = dedupe_keywords_by_normalized_form(HIGHEST_PRIORITY_KEYWORDS)
HIGH_PRIORITY_KEYWORDS = dedupe_keywords_by_normalized_form(HIGH_PRIORITY_KEYWORDS)

# ---------------------------------------------------------
# 3-6. 키워드 점수 맵 생성
# ---------------------------------------------------------
KEYWORD_BUCKETS = {
    "highest": {
        "score": 5,
        "keywords": HIGHEST_PRIORITY_KEYWORDS,
    },
    "high": {
        "score": 4,
        "keywords": HIGH_PRIORITY_KEYWORDS,
    },
}


def build_keyword_weight_map():
    """
    키워드별 가중치 dict 생성
    동일 키워드가 여러 그룹에 중복될 경우 높은 점수만 유지
    """
    result = {}

    for _, config in KEYWORD_BUCKETS.items():
        score = config["score"]

        for kw in config["keywords"]:
            kw = clean_text(kw)

            if not kw:
                continue

            if kw not in result:
                result[kw] = score
            else:
                result[kw] = max(result[kw], score)

    return result


KEYWORD_WEIGHT_MAP = build_keyword_weight_map()

MIN_SAVE_SCORE = 1
REGULAR_FORCE_SCORE = 60
HIGH_PRIORITY_SCORE = 5

# ---------------------------------------------------------
# 키워드 매칭 범위 설정
# ---------------------------------------------------------
MATCH_KEYWORDS_TITLE_ONLY = True

NEW_NOTICE_HEADERS = [
    "공고일",
    "공고명",
    "적합도점수",
    "적합도등급",
    "마감일",
    "소관부처",
    "수행기관",
    "신청기간",
    "지원대상",
    "지원내용(혜택 및 금액)",
    "접수처",
    "문의처",
    "상세링크",

    "공고ID",
    "수집일시",
    "출처",
    "접수상태",
    "진행상태",
    "상태변경일시",
    "상태변경자",
    "숨김여부",
    "미진행사유",
    "상태변경메모",

    "정기공고여부",
    "정기공고그룹",
    "매칭키워드",
    "첨부파일",
    "비고"
]

HISTORY_HEADERS = [
    "수집시각",
    "고유키",
    "링크키",
    "공통공고명키",
    "공고일",
    "공고명",
    "소관부처",
]

ERROR_HEADERS = [
    "실행시각",
    "출처",
    "단계",
    "공고명",
    "URL",
    "에러메시지",
    "상세",
]

FILTER_DROP_HEADERS = [
    "수집일시",
    "출처",
    "공고명",
    "적합도점수",
    "적합도등급",
    "키워드매칭수",
    "상세링크",
    "비고",
]

RECURRING_MASTER_HEADERS = [
    "사업군ID",
    "대표공고명",
    "부처",
    "중요도",
    "키워드패턴"
]

RECURRING_RESULT_HEADERS = [
    "탐지일시",
    "사업군ID",
    "대표공고명",
    "실제공고명",
    "출처",
    "공고일",
    "상세링크",
    "적합도점수",
    "적합도등급",
    "매칭키워드"
]

STATUS_LOG_HEADERS = [
    "로그일시",
    "공고ID",
    "공고명",
    "이전진행상태",
    "변경진행상태",
    "변경사유",
    "상세메모",
    "처리자"
]

