const SPREADSHEET_ID = "18WxHYXwyRwf9X-NGh4pY09RDyS1B7gVs9iFqm-eIARw";
const DRIVE_FOLDER_ID = "1q2Fr3N2amD9L49Mmt6jywxN3tqLM-rK6";

const NOTICE_SHEET = "신규공고";
const STATUS_LOG_SHEET = "상태변경로그";
const REGULAR_SHEET = "정기지원(수정금지)";

const DEFAULT_STATUS = "신규";
const SYSTEM_USER = "system";


function doGet(e) {
  const template = HtmlService.createTemplateFromFile("Index");

  const params = e && e.parameter ? e.parameter : {};
  template.noticeId = params.id || "";
  template.webAppUrl = ScriptApp.getService().getUrl();

  return template
    .evaluate()
    .setTitle("고객지원사업 공고 관리")
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function getHeaderIndexMap(headers) {
  const idx = {};
  headers.forEach((h, i) => {
    idx[String(h).trim()] = i;
  });
  return idx;
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "";

  if (Object.prototype.toString.call(value) === "[object Date]") {
    return Utilities.formatDate(value, "Asia/Seoul", "yyyy-MM-dd");
  }

  return String(value).trim();
}

function getValue(row, idx, headerName) {
  if (idx[headerName] === undefined) return "";
  return formatValue(row[idx[headerName]]);
}

function getSheetValues(sheet) {
  const range = sheet.getDataRange();
  return range.getValues();
}

function getRegularNoticeCards() {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getSheetByName(REGULAR_SHEET);

  if (!sheet) return [];

  const values = getSheetValues(sheet);
  if (values.length < 2) return [];

  const headers = values[0].map(h => String(h).trim());
  const idx = getHeaderIndexMap(headers);
  const rows = values.slice(1);

  const idxTitle = idx["대표공고명"];
  const idxMinistry = idx["부처"];
  const idxGroupId = idx["사업군ID"];

  const idxPattern =
    idx["키워드 패턴"] !== undefined
      ? idx["키워드 패턴"]
      : idx["키워드패턴"];

  if (idxTitle === undefined) return [];

  return rows
    .filter(row => formatValue(row[idxTitle]) !== "")
    .map(row => ({
      사업군ID: idxGroupId !== undefined ? formatValue(row[idxGroupId]) : "",
      대표공고명: formatValue(row[idxTitle]),
      부처: idxMinistry !== undefined ? formatValue(row[idxMinistry]) : "",
      키워드패턴: idxPattern !== undefined ? formatValue(row[idxPattern]) : ""
    }));
}

function enrichRegularCardsWithMatchedCount(regularCards, notices) {
  return regularCards.map(card => {
    const cardTitle = String(card.대표공고명 || "").trim();
    const cardGroupId = String(card.사업군ID || "").trim();

    const keywordText = String(card.키워드패턴 || cardTitle || "");
    const keywords = keywordText
      .split("|")
      .map(v => v.trim())
      .filter(Boolean);

    const matchedCount = notices.filter(n => {
      const targetText = [
        n.공고명,
        n.소관부처,
        n.수행기관,
        n.지원대상,
        n.지원내용,
        n.매칭키워드,
        n.정기공고그룹,
        n.첨부파일
      ].join(" ");

      if (cardTitle && String(n.공고명 || "").includes(cardTitle)) {
        return true;
      }

      if (
        cardGroupId &&
        String(n.정기공고그룹 || "").includes(cardGroupId)
      ) {
        return true;
      }

      return keywords.some(k => k && targetText.includes(k));
    }).length;

    return {
      ...card,
      매칭건수: matchedCount,
      등록여부: matchedCount > 0 ? "Y" : "N"
    };
  });
}

function makeEmptySummary() {
  return {
    신규: 0,
    검토요청: 0,
    미진행: 0,
    진행확정: 0,
    상태미선택: 0
  };
}

function normalizeStatus(status) {
  const st = String(status || "").trim();

  if (!st) return DEFAULT_STATUS;
  if (st === "상태 미선택") return "상태미선택";

  return st;
}

function parseDateOnly(value) {
  if (!value) return null;

  if (Object.prototype.toString.call(value) === "[object Date]") {
    return new Date(value.getFullYear(), value.getMonth(), value.getDate());
  }

  const text = String(value).trim();
  const match = text.match(/(20\d{2})[-./](\d{1,2})[-./](\d{1,2})/);

  if (!match) return null;

  const y = Number(match[1]);
  const m = Number(match[2]) - 1;
  const d = Number(match[3]);

  return new Date(y, m, d);
}

function getTodayDateOnly() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

function getApplyStatusDisplay(deadline, applyPeriod, originalApplyStatus) {
  const today = getTodayDateOnly();
  const deadlineDate = parseDateOnly(deadline);

  // 마감일이 오늘보다 과거면 무조건 마감으로 표시
  if (deadlineDate && deadlineDate < today) {
    return "마감";
  }

  const periodText = String(applyPeriod || "").trim();
  const dates = periodText.match(/20\d{2}[-./]\d{1,2}[-./]\d{1,2}/g);

  if (dates && dates.length >= 2) {
    const startDate = parseDateOnly(dates[0]);
    const endDate = parseDateOnly(dates[1]);

    if (endDate && endDate < today) return "마감";
    if (startDate && today < startDate) return "접수예정";
    if (startDate && endDate && startDate <= today && today <= endDate) return "접수중";
  }

  return originalApplyStatus || "확인필요";
}

function getNoticeList() {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getSheetByName(NOTICE_SHEET);

  if (!sheet) {
    throw new Error("신규공고 시트를 찾을 수 없습니다.");
  }

  const values = getSheetValues(sheet);

  if (values.length < 2) {
    const emptyRegularCards = enrichRegularCardsWithMatchedCount(
      getRegularNoticeCards(),
      []
    );

    return {
      total: 0,
      notices: [],
      regularCards: emptyRegularCards,
      summary: makeEmptySummary()
    };
  }

  const headers = values[0].map(h => String(h).trim());
  const idx = getHeaderIndexMap(headers);
  const rows = values.slice(1);

  if (idx["공고ID"] === undefined) {
    throw new Error("신규공고 시트에서 공고ID 컬럼을 찾을 수 없습니다.");
  }

  if (idx["공고명"] === undefined) {
    throw new Error("신규공고 시트에서 공고명 컬럼을 찾을 수 없습니다.");
  }

  const notices = rows
    .filter(row => getValue(row, idx, "공고ID") !== "")
    .map(row => {
      const rawStatus = getValue(row, idx, "진행상태");
      const status = rawStatus || DEFAULT_STATUS;

      const applyStatusRaw = getValue(row, idx, "접수상태");
      const deadline = getValue(row, idx, "마감일");
      const applyPeriod = getValue(row, idx, "신청기간");
      const applyStatusDisplay = getApplyStatusDisplay(deadline, applyPeriod, applyStatusRaw);

      return {
        공고ID: getValue(row, idx, "공고ID"),

        // 진행상태: 내부 업무 상태
        상태: status,
        진행상태: status,

        공고명: getValue(row, idx, "공고명"),
        소관부처: getValue(row, idx, "소관부처"),
        수행기관: getValue(row, idx, "수행기관"),
        신청기간: applyPeriod,
        공고일: getValue(row, idx, "공고일"),
        마감일: deadline,
        적합도점수: getValue(row, idx, "적합도점수"),
        적합도등급: getValue(row, idx, "적합도등급") || "D",
        출처: getValue(row, idx, "출처"),

        // 접수상태: 원본값 / 접수상태표시: 마감일 기준 계산값
        접수상태: applyStatusRaw,
        접수상태표시: applyStatusDisplay,

        정기공고여부: getValue(row, idx, "정기공고여부"),
        정기공고그룹: getValue(row, idx, "정기공고그룹"),
        매칭키워드: getValue(row, idx, "매칭키워드"),
        첨부파일: getValue(row, idx, "첨부파일"),
        지원대상: getValue(row, idx, "지원대상"),
        지원내용: getValue(row, idx, "지원내용(혜택 및 금액)"),
        상세링크: getValue(row, idx, "상세링크"),
        비고: getValue(row, idx, "비고"),
        숨김여부: getValue(row, idx, "숨김여부")
      };
    });

  const summary = makeEmptySummary();

  notices.forEach(n => {
    const st = normalizeStatus(n.상태);

    if (summary[st] !== undefined) {
      summary[st]++;
    } else {
      summary.상태미선택++;
    }
  });

  const regularCards = enrichRegularCardsWithMatchedCount(
    getRegularNoticeCards(),
    notices
  );

  return {
    total: notices.length,
    notices,
    regularCards,
    summary
  };
}

function getNoticeDetail(noticeId) {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getSheetByName(NOTICE_SHEET);

  if (!sheet) {
    throw new Error("신규공고 시트를 찾을 수 없습니다.");
  }

  const values = getSheetValues(sheet);

  if (values.length < 2) {
    throw new Error("신규공고 시트에 데이터가 없습니다.");
  }

  const headers = values[0].map(h => String(h).trim());
  const idx = getHeaderIndexMap(headers);
  const rows = values.slice(1);

  if (idx["공고ID"] === undefined) {
    throw new Error("공고ID 컬럼을 찾을 수 없습니다.");
  }

  let target;

  if (noticeId && String(noticeId).trim() !== "") {
    target = rows.find(row =>
      getValue(row, idx, "공고ID") === String(noticeId).trim()
    );
  } else {
    target = rows.find(row => getValue(row, idx, "공고ID") !== "");
  }

  if (!target) return null;

  const detailApplyStatusRaw = getValue(target, idx, "접수상태");
  const detailDeadline = getValue(target, idx, "마감일");
  const detailApplyPeriod = getValue(target, idx, "신청기간");
  const detailApplyStatusDisplay = getApplyStatusDisplay(
    detailDeadline,
    detailApplyPeriod,
    detailApplyStatusRaw
  );

  return {
    공고ID: getValue(target, idx, "공고ID"),
    공고일: getValue(target, idx, "공고일"),
    공고명: getValue(target, idx, "공고명"),
    적합도점수: getValue(target, idx, "적합도점수"),
    적합도등급: getValue(target, idx, "적합도등급") || "D",
    마감일: getValue(target, idx, "마감일"),
    소관부처: getValue(target, idx, "소관부처"),
    수행기관: getValue(target, idx, "수행기관"),
    신청기간: getValue(target, idx, "신청기간"),
    지원대상: getValue(target, idx, "지원대상"),
    지원내용: getValue(target, idx, "지원내용(혜택 및 금액)"),
    접수처: getValue(target, idx, "접수처"),
    문의처: getValue(target, idx, "문의처"),
    상세링크: getValue(target, idx, "상세링크"),
    출처: getValue(target, idx, "출처"),
    접수상태: detailApplyStatusRaw,
    접수상태표시: detailApplyStatusDisplay,
    진행상태: getValue(target, idx, "진행상태") || DEFAULT_STATUS,
    정기공고여부: getValue(target, idx, "정기공고여부"),
    정기공고그룹: getValue(target, idx, "정기공고그룹"),
    매칭키워드: getValue(target, idx, "매칭키워드"),
    첨부파일: getValue(target, idx, "첨부파일"),
    비고: getValue(target, idx, "비고"),
    숨김여부: getValue(target, idx, "숨김여부")
  };
}

function updateNoticeStatus(noticeId, newStatus, userName) {
  if (!noticeId) {
    throw new Error("공고ID가 없습니다.");
  }

  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getSheetByName(NOTICE_SHEET);

  if (!sheet) {
    throw new Error("신규공고 시트를 찾을 수 없습니다.");
  }

  const values = getSheetValues(sheet);

  if (values.length < 2) {
    throw new Error("신규공고 시트에 데이터가 없습니다.");
  }

  const headers = values[0].map(h => String(h).trim());
  const idx = getHeaderIndexMap(headers);

  if (idx["공고ID"] === undefined) {
    throw new Error("공고ID 컬럼을 찾을 수 없습니다.");
  }

  let targetRow = -1;
  let oldStatus = "";
  let noticeTitle = "";

  for (let r = 1; r < values.length; r++) {
    if (getValue(values[r], idx, "공고ID") === String(noticeId).trim()) {
      targetRow = r + 1;
      oldStatus = getValue(values[r], idx, "진행상태") || DEFAULT_STATUS;
      noticeTitle = getValue(values[r], idx, "공고명");
      break;
    }
  }

  if (targetRow === -1) {
    throw new Error("공고ID를 찾을 수 없습니다.");
  }

  const now = new Date();
  const actor = userName || SYSTEM_USER;
  const noticeForCalendar = {
    공고ID: getValue(values[targetRow - 1], idx, "공고ID"),
    공고명: getValue(values[targetRow - 1], idx, "공고명"),
    수행기관: getValue(values[targetRow - 1], idx, "수행기관"),
    소관부처: getValue(values[targetRow - 1], idx, "소관부처"),
    신청기간: getValue(values[targetRow - 1], idx, "신청기간"),
    마감일: getValue(values[targetRow - 1], idx, "마감일"),
    상세링크: getValue(values[targetRow - 1], idx, "상세링크")
  };

  if (idx["진행상태"] !== undefined) {
    sheet.getRange(targetRow, idx["진행상태"] + 1).setValue(newStatus);
  }

  if (idx["상태변경일시"] !== undefined) {
    sheet.getRange(targetRow, idx["상태변경일시"] + 1).setValue(now);
  }

  if (idx["상태변경자"] !== undefined) {
    sheet.getRange(targetRow, idx["상태변경자"] + 1).setValue(actor);
  }

  const logSheet = ss.getSheetByName(STATUS_LOG_SHEET);
  if (logSheet) {
    logSheet.appendRow([
      now,
      noticeId,
      noticeTitle,
      oldStatus,
      newStatus,
      "",
      "",
      actor
    ]);
  }

  let calendarResult = null;

  if (newStatus === "검토요청" || newStatus === "진행확정") {
    calendarResult = createCalendarEventForConfirmedNotice_(noticeForCalendar);
  }

  return {
    success: true,
    status: newStatus,
    calendar: calendarResult
  };
}

function normalizeCalendarDate_(value) {
  if (!value) return null;

  if (Object.prototype.toString.call(value) === "[object Date]") {
    return new Date(value.getFullYear(), value.getMonth(), value.getDate());
  }

  const text = String(value).trim();

  const match = text.match(/(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})/);
  if (!match) return null;

  const y = Number(match[1]);
  const m = Number(match[2]) - 1;
  const d = Number(match[3]);

  return new Date(y, m, d);
}

function extractApplyPeriodDates_(applyPeriod, deadline) {
  const text = String(applyPeriod || "").trim();

  const dateMatches = text.match(/20\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2}/g) || [];

  let startDate = null;
  let endDate = null;

  if (dateMatches.length >= 2) {
    startDate = normalizeCalendarDate_(dateMatches[0]);
    endDate = normalizeCalendarDate_(dateMatches[1]);
  } else if (dateMatches.length === 1) {
    startDate = normalizeCalendarDate_(dateMatches[0]);
    endDate = normalizeCalendarDate_(deadline || dateMatches[0]);
  } else {
    endDate = normalizeCalendarDate_(deadline);
    startDate = endDate;
  }

  if (!startDate || !endDate) {
    return null;
  }

  // Google Calendar 종일 일정의 종료일은 exclusive라서 하루 더해야 실제 마감일까지 표시됨
  const exclusiveEndDate = new Date(endDate);
  exclusiveEndDate.setDate(exclusiveEndDate.getDate() + 1);

  return {
    startDate,
    endDate: exclusiveEndDate
  };
}

function cleanNoticeTitleForCalendar_(title) {
  let text = String(title || "").trim();

  if (!text) return "";

  text = text
    .replace(/R\s*&\s*D/gi, "R&D")
    .replace(/[ㆍ∙·]/g, "ㆍ")
    .replace(/\s+/g, " ")
    .trim();
    

  text = text.replace(/^\[[^\]]+\]\s*/g, "");

  text = text.replace(/20\d{2}\s*년도?/g, "").trim();

  const leadingRegionPattern =
    /^(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)\s*/;

  text = text.replace(leadingRegionPattern, "");
  text = text.replace(/^[가-힣]+(시|군|구)\s*/g, "");

  text = text.replace(/제?\s*\d+\s*차\s*/g, "");

  text = text.replace(/^공고\s*/g, "");
  text = text.replace(/^공고명\s*[:：]\s*/g, "");

  const suffixPatterns = [
    // 수정/재공고/추가/연장/변경 계열
    /\s*수정\s*공고\s*$/g,
    /\s*수정공고\s*$/g,
    /\s*변경\s*공고\s*$/g,
    /\s*변경공고\s*$/g,
    /\s*재\s*공고\s*$/g,
    /\s*재공고\s*$/g,
    /\s*추가\s*공고\s*$/g,
    /\s*추가공고\s*$/g,
    /\s*연장\s*공고\s*$/g,
    /\s*연장공고\s*$/g,

    // 모집 공고 계열
    /\s*지원기업\s*모집\s*공고\s*$/g,
    /\s*참여기업\s*모집\s*공고\s*$/g,
    /\s*수혜기업\s*모집\s*공고\s*$/g,
    /\s*수요기업\s*모집\s*공고\s*$/g,
    /\s*공급기업\s*모집\s*공고\s*$/g,
    /\s*주관기관\s*모집\s*공고\s*$/g,
    /\s*참여기관\s*모집\s*공고\s*$/g,
    /\s*대상기업\s*모집\s*공고\s*$/g,
    /\s*기업\s*모집\s*공고\s*$/g,
    /\s*모집\s*공고\s*$/g,

    // 공고 없는 모집 계열
    /\s*지원기업\s*모집\s*$/g,
    /\s*참여기업\s*모집\s*$/g,
    /\s*수혜기업\s*모집\s*$/g,
    /\s*수요기업\s*모집\s*$/g,
    /\s*공급기업\s*모집\s*$/g,
    /\s*주관기관\s*모집\s*$/g,
    /\s*참여기관\s*모집\s*$/g,
    /\s*대상기업\s*모집\s*$/g,
    /\s*기업\s*모집\s*$/g,
    /\s*모집\s*$/g,

    // 일반 공고 계열
    /\s*시행\s*계획\s*공고\s*$/g,
    /\s*시행계획\s*공고\s*$/g,
    /\s*사업\s*공고\s*$/g,
    /\s*사업공고\s*$/g,
    /\s*지원사업\s*공고\s*$/g,
    /\s*공고\s*$/g,

    // 뒤쪽 부가 표기
    /_?\s*추가\s*모집\s*$/g,
    /_?\s*추가모집\s*$/g,
    /_?\s*\d+\s*차\s*$/g
  ];

  suffixPatterns.forEach(pattern => {
    text = text.replace(pattern, "");
  });

  const beforeParenPatterns = [
    /\s*지원기업\s*모집\s*공고(?=\()/g,
    /\s*참여기업\s*모집\s*공고(?=\()/g,
    /\s*수혜기업\s*모집\s*공고(?=\()/g,
    /\s*수요기업\s*모집\s*공고(?=\()/g,
    /\s*공급기업\s*모집\s*공고(?=\()/g,
    /\s*주관기관\s*모집\s*공고(?=\()/g,
    /\s*참여기관\s*모집\s*공고(?=\()/g,
    /\s*모집\s*공고(?=\()/g,
    /\s*사업\s*공고(?=\()/g,
    /\s*사업공고(?=\()/g,
    /\s*공고(?=\()/g
  ];

  beforeParenPatterns.forEach(pattern => {
    if (String(pattern).includes("사업")) {
      text = text.replace(pattern, " 사업");
    } else {
      text = text.replace(pattern, "");
    }
  });

  text = text
    .replace(/\s+\)/g, ")")
    .replace(/\(\s+/g, "(")
    .replace(/\s*,\s*/g, ", ")
    .replace(/\s+/g, " ")
    .trim();

  if (!text) {
    text = String(title || "")
      .replace(/^\[[^\]]+\]\s*/g, "")
      .replace(/20\d{2}\s*년도?/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  return text;
}

function buildCalendarEventTitle_(agency, noticeTitle) {
  const cleanAgency = String(agency || "").trim();
  const cleanTitle = cleanNoticeTitleForCalendar_(noticeTitle);

  if (cleanAgency && cleanTitle) {
    return `(${cleanAgency}) ${cleanTitle}`;
  }

  if (cleanTitle) return cleanTitle;
  if (cleanAgency) return `(${cleanAgency}) 공고 접수기간`;

  return "고객지원사업 접수기간";
}

function buildCalendarEventKey_(noticeId) {
  return `[NOTICE_ID:${noticeId}]`;
}

function createCalendarEventForConfirmedNotice_(notice) {
  const noticeId = String(notice.공고ID || "").trim();

  if (!noticeId) {
    throw new Error("캘린더 등록 실패: 공고ID가 없습니다.");
  }

  const title = buildCalendarEventTitle_(
    notice.수행기관,
    notice.공고명
  );

  const dateRange = extractApplyPeriodDates_(
    notice.신청기간,
    notice.마감일
  );

  if (!dateRange) {
    throw new Error("캘린더 등록 실패: 접수기간 또는 마감일을 날짜로 해석할 수 없습니다.");
  }

  const calendar = CalendarApp.getDefaultCalendar();
  const eventKey = buildCalendarEventKey_(noticeId);

  // 중복 등록 방지: 같은 공고ID가 description에 있으면 재등록하지 않음
  const existingEvents = calendar.getEvents(
    dateRange.startDate,
    dateRange.endDate,
    {
      search: eventKey
    }
  );

  if (existingEvents && existingEvents.length > 0) {
    return {
      created: false,
      reason: "이미 등록된 캘린더 일정이 있습니다.",
      eventId: existingEvents[0].getId(),
      title: existingEvents[0].getTitle()
    };
  }

  const description = [
    eventKey,
    `공고명: ${notice.공고명 || ""}`,
    `수행기관: ${notice.수행기관 || ""}`,
    `소관부처: ${notice.소관부처 || ""}`,
    `신청기간: ${notice.신청기간 || ""}`,
    `마감일: ${notice.마감일 || ""}`,
    `상세링크: ${notice.상세링크 || ""}`
  ].join("\n");

  const event = calendar.createAllDayEvent(
    title,
    dateRange.startDate,
    dateRange.endDate,
    {
      description: description
    }
  );

  return {
    created: true,
    eventId: event.getId(),
    title: event.getTitle()
  };
}

function testGetNoticeList() {
  try {
    const result = getNoticeList();

    Logger.log("getNoticeList 성공");
    Logger.log("total: " + result.total);
    Logger.log("notices length: " + (result.notices ? result.notices.length : 0));
    Logger.log("regularCards length: " + (result.regularCards ? result.regularCards.length : 0));

    if (result.notices && result.notices.length > 0) {
      Logger.log("첫 번째 공고명: " + result.notices[0].공고명);
      Logger.log("첫 번째 공고ID: " + result.notices[0].공고ID);
      Logger.log("첫 번째 첨부파일: " + result.notices[0].첨부파일);
    }

    return result;
  } catch (err) {
    Logger.log("getNoticeList 실패");
    Logger.log(err.message);
    Logger.log(err.stack);
    throw err;
  }
}

function testGetNoticeDetail() {
  const list = getNoticeList();

  if (!list.notices || list.notices.length === 0) {
    Logger.log("테스트할 공고가 없습니다.");
    return null;
  }

  const firstId = list.notices[0].공고ID;
  const detail = getNoticeDetail(firstId);

  Logger.log(JSON.stringify(detail, null, 2));
  return detail;
}

function saveNoticeAttachmentsToDrive(noticeId) {
  if (!noticeId) {
    throw new Error("공고ID가 없습니다.");
  }

  if (!DRIVE_FOLDER_ID || DRIVE_FOLDER_ID === "여기에_구글드라이브_폴더_ID_입력") {
    throw new Error("DRIVE_FOLDER_ID를 설정해야 합니다.");
  }

  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getSheetByName(NOTICE_SHEET);

  if (!sheet) {
    throw new Error("신규공고 시트를 찾을 수 없습니다.");
  }

  const values = getSheetValues(sheet);

  if (values.length < 2) {
    throw new Error("신규공고 시트에 데이터가 없습니다.");
  }

  const headers = values[0].map(h => String(h).trim());
  const idx = getHeaderIndexMap(headers);

  if (idx["공고ID"] === undefined) {
    throw new Error("공고ID 컬럼을 찾을 수 없습니다.");
  }

  if (idx["공고명"] === undefined) {
    throw new Error("공고명 컬럼을 찾을 수 없습니다.");
  }

  if (idx["첨부파일"] === undefined) {
    throw new Error("첨부파일 컬럼을 찾을 수 없습니다.");
  }

  let targetRow = null;

  for (let i = 1; i < values.length; i++) {
    if (getValue(values[i], idx, "공고ID") === String(noticeId).trim()) {
      targetRow = values[i];
      break;
    }
  }

  if (!targetRow) {
    throw new Error("해당 공고를 찾지 못했습니다.");
  }

  const noticeTitle = getValue(targetRow, idx, "공고명") || "공고";
  const attachmentsText = getValue(targetRow, idx, "첨부파일");

  if (!attachmentsText) {
    throw new Error("저장할 첨부파일 정보가 없습니다.");
  }

  let attachments;

  try {
    attachments = JSON.parse(attachmentsText);
  } catch (e) {
    throw new Error("첨부파일 JSON 형식이 올바르지 않습니다.");
  }

  if (!Array.isArray(attachments) || attachments.length === 0) {
    throw new Error("첨부파일 목록이 비어 있습니다.");
  }

  const noticeDocumentAttachments = selectNoticeDocumentAttachments_(attachments);

  if (noticeDocumentAttachments.length === 0) {
    throw new Error("공고문으로 판단되는 첨부파일을 찾지 못했습니다.");
  }

  const folder = DriveApp.getFolderById(DRIVE_FOLDER_ID);

  const safeNoticeTitle = sanitizeFileName_(noticeTitle).substring(0, 80);
  const dateText = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyyMMdd");

  // 공고별 하위 폴더 생성
  const noticeFolder = folder.createFolder(`${safeNoticeTitle}_${dateText}`);

  const savedFiles = [];
  const failedFiles = [];
  const labelCountMap = {};

  noticeDocumentAttachments.forEach(function(file, index) {
    const originalFileName = sanitizeFileName_(
      file.name ||
      file.file_name ||
      file.filename ||
      `첨부파일_${index + 1}`
    );
    const fileUrl = normalizeDownloadUrl_(
      file.url ||
      file.download_url ||
      file.href ||
      ""
    );

    if (!fileUrl) {
      failedFiles.push({
        name: originalFileName,
        reason: "다운로드 URL 없음"
      });
      return;
    }

    const fileLabel = "공고문";
    const fileExt = getFileExtension_(originalFileName);

    labelCountMap[fileLabel] = (labelCountMap[fileLabel] || 0) + 1;

    const count = labelCountMap[fileLabel];
    const countSuffix = count > 1 ? `_${count}` : "";

    // 최종 저장 파일명: 공고명_공고문.pdf / 공고명_사업계획서.hwp
    const newFileName = `${safeNoticeTitle}_${fileLabel}${countSuffix}${fileExt}`;

    try {
      const response = fetchDownloadFile_(fileUrl);

      const code = response.getResponseCode();

      if (code < 200 || code >= 300) {
        failedFiles.push({
          name: originalFileName,
          reason: `다운로드 실패 HTTP ${code}`
        });
        return;
      }

      const blob = response.getBlob().setName(newFileName);
      const driveFile = noticeFolder.createFile(blob);

      savedFiles.push({
        originalName: originalFileName,
        name: driveFile.getName(),
        url: driveFile.getUrl(),
        id: driveFile.getId()
      });

    } catch (e) {
      failedFiles.push({
        name: originalFileName,
        reason: e.message
      });
    }
  });

  return {
    success: true,
    noticeTitle: noticeTitle,
    folderName: noticeFolder.getName(),
    folderUrl: noticeFolder.getUrl(),
    selectedFiles: noticeDocumentAttachments.map(function(file) {
      return sanitizeFileName_(file.name || "");
    }),
    savedFiles: savedFiles,
    failedFiles: failedFiles
  };
}

function sanitizeFileName_(name) {
  return String(name || "")
    .replace(/[\\/:*?"<>|]/g, "_")
    .replace(/\s+/g, " ")
    .trim();
}

function getFileExtension_(fileName) {
  const text = String(fileName || "").trim();
  const match = text.match(/(\.[a-zA-Z0-9]+)$/);

  if (!match) {
    return "";
  }

  return match[1];
}

function normalizeDownloadUrl_(url) {
  let text = String(url || "").trim();

  if (!text) return "";

  text = text
    .replace(/&amp;/g, "&")
    .replace(/&#38;/g, "&")
    .replace(/^\s+|\s+$/g, "");

  if (!/^https?:\/\//i.test(text)) {
    return "";
  }

  const bizinfoFileMatch = text.match(
    /^(https?:\/\/www\.bizinfo\.go\.kr\/cmm\/fms\/fileDown\.do)\?(.+)$/i
  );

  if (bizinfoFileMatch) {
    const baseUrl = bizinfoFileMatch[1];
    const queryText = bizinfoFileMatch[2];
    const params = {};

    queryText.split("&").forEach(function(part) {
      const pieces = part.split("=");
      const key = decodeURIComponent(pieces.shift() || "").trim();
      const value = decodeURIComponent(pieces.join("=") || "").trim();

      if (key) {
        params[key] = value;
      }
    });

    if (params.atchFileId) {
      const fileSn = params.fileSn || "0";
      return (
        baseUrl +
        "?atchFileId=" + encodeURIComponent(params.atchFileId) +
        "&fileSn=" + encodeURIComponent(fileSn)
      );
    }
  }

  return encodeURI(text);
}

function fetchDownloadFile_(url) {
  const options = {
    method: "get",
    muteHttpExceptions: true,
    followRedirects: true,
    headers: {
      "User-Agent": "Mozilla/5.0",
      "Accept": "*/*",
      "Referer": "https://www.bizinfo.go.kr/"
    }
  };

  let lastError = null;

  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      return UrlFetchApp.fetch(url, options);
    } catch (e) {
      lastError = e;
      Utilities.sleep(700 * attempt);
    }
  }

  throw new Error(
    (lastError && lastError.message ? lastError.message : "다운로드 요청 실패") +
    ` | 정규화 URL: ${url}`
  );
}

function isNoticeDocumentAttachment_(fileName) {
  const text = String(fileName || "").toLowerCase();

  if (!text) return false;

  const noticeKeywords = [
    "꽁고문",
    "공고문",
    "모집공고",
    "공고"
  ];

  return noticeKeywords.some(function(keyword) {
    return text.includes(keyword);
  });
}

function selectNoticeDocumentAttachments_(attachments) {
  if (!Array.isArray(attachments)) return [];

  return attachments.filter(function(file) {
    const fileName = sanitizeFileName_(
      file.name ||
      file.file_name ||
      file.filename ||
      "첨부파일"
    );
    const fileUrl = normalizeDownloadUrl_(
      file.url ||
      file.download_url ||
      file.href ||
      ""
    );

    return fileUrl && isNoticeDocumentAttachment_(fileName);
  });
}

function classifyAttachmentLabel_(fileName, index) {
  const text = String(fileName || "").toLowerCase();

  if (
    text.includes("공고문") ||
    text.includes("모집공고") ||
    text.includes("공고") ||
    text.includes("announcement")
  ) {
    return "공고문";
  }

  if (
    text.includes("사업계획서") ||
    text.includes("계획서") ||
    text.includes("business_plan")
  ) {
    return "사업계획서";
  }

  if (
    text.includes("신청서") ||
    text.includes("신청양식") ||
    text.includes("신청 서식")
  ) {
    return "신청서";
  }

  if (
    text.includes("양식") ||
    text.includes("서식") ||
    text.includes("template") ||
    text.includes("form")
  ) {
    return "양식";
  }

  if (
    text.includes("가이드") ||
    text.includes("매뉴얼") ||
    text.includes("manual") ||
    text.includes("guide")
  ) {
    return "가이드";
  }

  if (
    text.includes("산출내역") ||
    text.includes("내역서") ||
    text.includes("견적")
  ) {
    return "산출내역서";
  }

  if (
    text.includes("확약서") ||
    text.includes("동의서") ||
    text.includes("서약서")
  ) {
    return "확약서_동의서";
  }

  if (
    text.includes("별첨") ||
    text.includes("붙임") ||
    text.includes("첨부")
  ) {
    return `첨부파일_${index + 1}`;
  }

  return `기타서류_${index + 1}`;
}

function testSaveNoticeAttachmentsToDrive() {
  const list = getNoticeList();

  if (!list.notices || list.notices.length === 0) {
    Logger.log("테스트할 공고가 없습니다.");
    return null;
  }

  const target = list.notices.find(n => String(n.첨부파일 || "").trim() !== "");

  if (!target) {
    Logger.log("첨부파일이 있는 공고가 없습니다.");
    return null;
  }

  const result = saveNoticeAttachmentsToDrive(target.공고ID);
  Logger.log(JSON.stringify(result, null, 2));
  return result;
}
