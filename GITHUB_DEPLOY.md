# GitHub로 실행/배포하기

이 프로젝트는 Python 백엔드가 필요하므로 GitHub Pages만으로는 실행할 수 없습니다. GitHub를 활용하는 권장 방식은 두 가지입니다.

## 1. 각 사용자가 자기 앱을 여는 방식: GitHub Codespaces

이 방식이 "사용자마다 각자 자기 LMS/Drive를 연결"하는 목적에 가장 잘 맞습니다.

1. 이 폴더를 GitHub 저장소로 올립니다.
2. 사용자는 GitHub에서 저장소를 열고 **Code → Codespaces → Create codespace**를 누릅니다.
3. Codespaces가 열리면 `.devcontainer/devcontainer.json`이 의존성을 설치하고 `python web_ui.py`를 실행합니다.
4. GitHub가 `https://<codespace-name>-8765.app.github.dev` 형태의 주소를 자동으로 만듭니다.
5. 앱 화면의 `?` 도움말과 OAuth 상태에 표시되는 redirect URI를 Google Cloud Console의 Authorized redirect URIs에 추가합니다.

Codespaces에서는 각 사용자의 파일이 자기 Codespace 내부 `~/.lms-autosaver`에 저장됩니다. 따라서 다른 사용자와 LMS 계정이나 Drive 토큰을 공유하지 않습니다.

## 2. 하나의 공개 웹서비스로 운영: GitHub + Render

지속 운영이 필요하면 GitHub 저장소를 Render Blueprint로 연결합니다. Render는 기본 `onrender.com` 주소를 자동으로 제공합니다.

1. GitHub 저장소에 이 프로젝트를 올립니다.
2. Render에서 **New → Blueprint**를 선택하고 이 저장소를 연결합니다.
3. `render.yaml`이 Python 서버를 만들고 `*.onrender.com` 주소를 생성합니다.
4. Render 환경 변수에 `AUTOSAVER_GOOGLE_CLIENT_ID`, `AUTOSAVER_GOOGLE_CLIENT_SECRET`을 입력합니다.
5. Google Cloud Console의 Authorized redirect URIs에 `https://<render-service>.onrender.com/oauth2callback`을 추가합니다.

Render 모드는 `AUTOSAVER_MULTI_USER=1`로 실행되어 접속자별 작업공간을 분리합니다. 사용자 데이터 보존을 위해 `render.yaml`에는 `/var/data` 디스크를 붙이도록 설정했습니다.

## GitHub에 올릴 때 제외되는 파일

`.gitignore`가 아래 민감 파일을 제외합니다.

- `config.py`, `config.json`
- `credentials.json`, `token.json`, `oauth_pending.json`
- `downloaded_files.json`, `file_metadata.json`
- `downloads/`, `users/`

## 중요한 제한

- GitHub Pages는 정적 호스팅이라 이 앱의 Python 서버, OAuth 콜백, Playwright 기반 LMS 동기화를 실행할 수 없습니다.
- Codespaces 주소는 Codespace마다 달라집니다. 각 사용자가 자기 Google OAuth 클라이언트에 화면에 표시된 redirect URI를 등록해야 합니다.
- 공개 서비스로 오래 운영하려면 사용자 로그인, 저장 비밀번호 암호화, 작업 큐 제한을 추가하는 것이 좋습니다.
