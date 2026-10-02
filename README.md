# DGIST LMS AutoSaver

DGIST LMS 강의 자료를 찾아 Google Drive에 정리하고, 새 자료 확인과 업로드 상태를 웹 인터페이스에서 관리하는 앱입니다.

© 2026 DGIST 기초학부 26학번 김유준. [Apache License 2.0](LICENSE)으로 공개합니다.

- 개인정보: 개발자에게 아무것도 보내지 않습니다 → [PRIVACY.md](PRIVACY.md)
- 코드 서명: Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org) → [CODE_SIGNING.md](CODE_SIGNING.md)

## 주요 기능

- DGIST LMS 로그인 및 강의 자료 탐색
- 여러 과목의 파일을 강의별/주차별로 분류
- Google OAuth 기반 Google Drive 연동
- Gemini API를 이용한 자료 요약
- 웹 대시보드에서 설정, 동기화, 검증 실행
- 사용자별 작업공간 분리 모드

## 실행

**쓰는 사람은 설치 파일로 설치합니다 (Windows).**
[Releases](https://github.com/jykim5215/dgist-lms-autosaver/releases/latest)의 Assets에서 `…-setup.exe`를 받아 실행하면 됩니다.
설치한 앱은 새 버전이 나오면 앱 안에서 업데이트됩니다.

> 웹 주소(Render)로 쓰는 방식은 2026-09-29에 멈췄습니다. 무료 서버에서는 LMS 동기화가 계속 실패했고
> 학교 비밀번호가 서버에 평문으로 남았습니다. 그 주소는 이제 설치 안내만 보여 줍니다(`hosted_notice.py`).
> `DEPLOYMENT.md`, `GITHUB_DEPLOY.md`는 옛 기록입니다.

개발할 때 (소스에서 실행):

```powershell
pip install -r requirements.txt
pythonw app.py            # 앱 창으로 실행 (LMS용 브라우저는 처음 동기화 때 자동으로 받음)
```

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
