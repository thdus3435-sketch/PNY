# Apps Script 동기화 가이드

`clasp`와 Node.js portable 설치는 이 프로젝트의 `tools/` 아래에 완료되어 있습니다.

## 1. 로그인

PowerShell에서 아래 명령을 실행하세요.

```powershell
.\tools\clasp-login.ps1
```

브라우저가 열리면 Google 계정으로 로그인하고 Apps Script 권한을 승인합니다.

## 2. Script ID 확인

Apps Script 편집기에서 확인합니다.

```text
프로젝트 설정 > 스크립트 ID
```

## 3. 프로젝트 clone

아래 명령에서 `SCRIPT_ID`를 실제 스크립트 ID로 바꿔 실행하세요.

```powershell
.\tools\clasp-clone.ps1 -ScriptId "SCRIPT_ID"
```

성공하면 `apps_script/` 폴더에 Apps Script 파일이 내려옵니다.

## 4. 이후 작업 방식

`apps_script/` 폴더가 생기면 Codex가 파일을 직접 읽고 수정할 수 있습니다.

수정 후 Google Apps Script로 다시 올릴 때는 다음 명령을 사용합니다.

```powershell
$env:Path = "$PWD\tools\node;$env:Path"
.\tools\clasp\node_modules\.bin\clasp.cmd push --rootDir apps_script
```
