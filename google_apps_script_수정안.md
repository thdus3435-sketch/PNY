# Google Apps Script 수정안

## 1. 마감 공고 목록 제외

Apps Script에서 목록 데이터를 만들 때 `숨김여부`와 `접수상태`를 함께 확인하세요.

```javascript
function isClosedNotice(row, headerMap) {
  const hiddenYn = String(row[headerMap['숨김여부']] || '').trim();
  const receiptStatus = String(row[headerMap['접수상태']] || '').trim();

  if (hiddenYn === 'Y') return true;
  if (receiptStatus.includes('마감') || receiptStatus.includes('종료')) return true;

  return false;
}

function getVisibleRows(values) {
  const headers = values[0];
  const headerMap = {};
  headers.forEach((name, index) => headerMap[name] = index);

  return values.slice(1).filter(row => !isClosedNotice(row, headerMap));
}
```

## 2. 기업마당 원문 페이지 미리보기

기업마당은 응답 헤더에 `X-Frame-Options: DENY`가 있어 iframe 직접 표시가 차단됩니다.

따라서 아래 방식 중 하나로 구현해야 합니다.

- `새 탭에서 열기` 버튼 유지
- 시트에 저장된 `지원대상`, `지원내용`, `접수처`, `문의처`, `첨부파일`을 앱 화면에서 직접 렌더링
- Apps Script 서버단에서 `UrlFetchApp.fetch(url)`로 원문 HTML을 가져온 뒤 필요한 본문만 추출해 자체 HTML로 렌더링

예시:

```javascript
function getBizinfoPreviewHtml(url) {
  const response = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    headers: {
      'User-Agent': 'Mozilla/5.0'
    }
  });

  const html = response.getContentText('UTF-8');
  const bodyMatch = html.match(/<div[^>]+class=["'][^"']*support_project_detail[^"']*["'][\s\S]*?<\/div>\s*<\/div>/i);

  if (!bodyMatch) {
    return '<p>기업마당 원문을 불러오지 못했습니다. 새 탭에서 원문을 확인하세요.</p>';
  }

  return bodyMatch[0]
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<iframe[\s\S]*?<\/iframe>/gi, '');
}
```

정규식 HTML 추출은 페이지 구조 변경에 약하므로, 가능하면 이미 Python에서 저장한 상세정보와 첨부파일 JSON을 화면에 렌더링하는 방식이 더 안정적입니다.
