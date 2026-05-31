# GitHub 기반 배포

이 프로젝트는 Python 서버가 필요하므로 GitHub Pages만으로는 실행할 수 없습니다. GitHub를 활용하는 배포 방식은 두 가지입니다.

## 1. 상시 운영: GitHub + Render

여러 사용자가 각자 이 앱을 웹에서 열어보게 하려면 이 방식을 사용합니다. 현재 설정은 결제 정보를 요구하지 않는 무료 테스트 배포입니다.

1. GitHub 저장소에 코드를 push합니다.
2. Render에서 저장소를 Blueprint로 연결합니다.
3. Render가 `render.yaml`과 `Dockerfile`을 사용해 웹 서비스를 생성합니다.
4. Render 기본 도메인 `*.onrender.com`이 자동 발급됩니다.
5. Google Cloud Console OAuth Redirect URI에 `https://<render-domain>/oauth2callback`을 추가합니다.

바로 배포 버튼:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/jykim5215/dgist-lms-autosaver)

운영 세부사항은 [DEPLOYMENT.md](DEPLOYMENT.md)를 참고하세요.

## 2. 개발/테스트: GitHub Codespaces

Codespaces는 테스트용으로만 권장합니다. 사용자가 없으면 꺼질 수 있고, 공개 포트 터널이 끊기면 URL이 404를 반환할 수 있습니다.

1. GitHub 저장소에서 **Code > Codespaces > Create codespace**를 선택합니다.
2. `.devcontainer/devcontainer.json`이 의존성을 설치하고 `python web_ui.py`를 실행합니다.
3. 포트 8765가 열리면 GitHub가 `https://<codespace-name>-8765.app.github.dev` 주소를 제공합니다.
4. 이 주소는 Codespace마다 달라질 수 있으므로 Google OAuth Redirect URI도 매번 맞춰야 합니다.

## GitHub에 올리지 않는 파일

`.gitignore`는 다음 민감 데이터를 제외합니다.

- `config.py`, `config.json`
- `credentials.json`, `token.json`, `oauth_pending.json`
- `downloaded_files.json`, `file_metadata.json`
- `downloads/`, `users/`

무료 Render 운영에서는 사용자별 데이터가 GitHub가 아니라 서버의 임시 저장소에 저장됩니다. 서버 재시작/재배포 후 데이터가 유지된다고 보장할 수 없습니다.
