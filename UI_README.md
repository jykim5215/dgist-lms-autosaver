# DGIST LMS AutoSaver UI

로컬 웹 대시보드를 실행하려면 프로젝트 폴더에서 아래 명령을 실행하세요.

```powershell
python web_ui.py
```

브라우저가 `http://127.0.0.1:8765`로 열립니다.

공유 웹사이트처럼 여러 사용자가 각자 자기 LMS/Drive 계정으로 쓰게 하려면 `DEPLOYMENT.md`의 멀티 사용자 모드 설정을 사용하세요.

## 화면에서 할 수 있는 일

- LMS, Gemini, Gmail, 예약 시간 설정 저장
- `C:\lms-autosaver\credentials.json` 연결 상태 확인
- Google OAuth 연결 실행 및 `token.json` 상태 확인
- 다운로드된 자료와 강의별 파일 목록 확인
- 즉시 동기화 실행
- LMS 자료 누락 검증 실행
- 실행 로그 확인

## 참고

Google Drive OAuth 클라이언트 파일은 기본적으로 `C:\lms-autosaver\credentials.json` 위치를 사용합니다.
대시보드의 `?` 도움말 버튼에서 Google Drive API 사용 설정, OAuth 클라이언트 생성, JSON 저장 순서를 확인할 수 있습니다.
로컬 단일 사용자 모드는 기존 설정을 읽을 수 있고, 멀티 사용자 모드는 사용자별 작업공간의 `config.json`과 `token.json`을 사용합니다.
