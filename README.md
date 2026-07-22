# DGIST LMS AutoSaver

DGIST LMS 강의 자료를 찾아 Google Drive에 정리하고, 새 자료 확인과 업로드 상태를 웹 인터페이스에서 관리하는 앱입니다.

© 2026 DGIST 기초학부 26학번 오정민 · 김유준. All rights reserved.

## 주요 기능

- DGIST LMS 로그인 및 강의 자료 탐색
- 여러 과목의 파일을 강의별/주차별로 분류
- Google OAuth 기반 Google Drive 연동
- Gemini API를 이용한 자료 요약
- 웹 대시보드에서 설정, 동기화, 검증 실행
- 사용자별 작업공간 분리 모드

## 실행

데스크톱 앱 (권장):

바탕화면의 **DGIST LMS AutoSaver** 바로가기를 더블클릭하면 네이티브 창으로 실행됩니다.
서버를 따로 띄울 필요가 없고, 이미 실행 중이면 기존 인스턴스에 창만 다시 엽니다.

```powershell
# 바로가기가 없을 때 직접 실행
pythonw app.py
```

최초 설치:

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

브라우저 모드 (선택):

```powershell
python web_ui.py
```

운영 배포:

- GitHub + Render 상시 호스팅: [DEPLOYMENT.md](DEPLOYMENT.md)
- GitHub 기반 배포 방식 비교: [GITHUB_DEPLOY.md](GITHUB_DEPLOY.md)

## Google API 설정

앱의 설정 화면에는 Google Drive OAuth와 Gemini API 발급을 돕는 도움말이 포함되어 있습니다.

운영 배포 후에는 Google Cloud Console의 OAuth Redirect URI에 Render 도메인을 추가해야 합니다.

```text
https://<render-domain>/oauth2callback
```

## 민감 파일

다음 파일은 GitHub에 올리지 않습니다.

- `config.py`, `config.json`
- `credentials.json`, `token.json`, `oauth_pending.json`
- `downloaded_files.json`, `file_metadata.json`
- `downloads/`, `users/`

## 구조

```text
dgist-lms-autosaver/
├── web_ui.py          # 웹 대시보드 서버
├── main.py            # 동기화 작업 실행
├── lms_crawler.py     # LMS 자료 탐색
├── drive_uploader.py  # Google Drive 업로드
├── runtime_config.py  # 사용자별 실행 설정
├── web/               # 프론트엔드 파일
├── Dockerfile         # Render Docker 배포
└── render.yaml        # Render Blueprint 설정
```
