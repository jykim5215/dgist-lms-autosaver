# 공유 웹사이트 배포 가이드

이 앱을 여러 사람이 쓰게 하려면 서버 하나를 공유하되, 데이터는 사용자별로 분리해야 합니다.
현재 배포 모드는 다음 항목을 사용자별 작업공간에 저장합니다.

- LMS ID/비밀번호, Gmail 앱 비밀번호, Gemini API 키: `config.json`
- Google Drive OAuth 토큰: `token.json`
- 다운로드 파일, 다운로드 기록, 파일 메타데이터
- 실행 중인 동기화/검증 작업 상태

Google OAuth 클라이언트 파일(`credentials.json`)은 서버 공통입니다. 사용자는 각자 Google 로그인으로 권한을 허용하고, 토큰만 자기 작업공간에 저장됩니다.

## 환경 변수

PowerShell 예시:

```powershell
$env:AUTOSAVER_MULTI_USER = "1"
$env:AUTOSAVER_UI_HOST = "0.0.0.0"
$env:AUTOSAVER_UI_PORT = "8765"
$env:AUTOSAVER_OPEN_BROWSER = "0"
$env:AUTOSAVER_PUBLIC_BASE_URL = "https://your-domain.example"
$env:AUTOSAVER_USERS_ROOT = "C:\lms-autosaver\users"
$env:AUTOSAVER_GOOGLE_CLIENT_SECRETS = "C:\lms-autosaver\credentials.json"
python web_ui.py
```

리눅스 서버 예시:

```bash
export AUTOSAVER_MULTI_USER=1
export AUTOSAVER_UI_HOST=0.0.0.0
export AUTOSAVER_UI_PORT=8765
export AUTOSAVER_OPEN_BROWSER=0
export AUTOSAVER_PUBLIC_BASE_URL=https://your-domain.example
export AUTOSAVER_USERS_ROOT=/var/lib/lms-autosaver/users
export AUTOSAVER_GOOGLE_CLIENT_SECRETS=/var/lib/lms-autosaver/credentials.json
python web_ui.py
```

## Google Cloud Console 설정

OAuth 클라이언트의 Authorized redirect URIs에 아래 주소를 정확히 추가합니다.

```text
https://your-domain.example/oauth2callback
```

로컬 테스트와 함께 쓰려면 기존 로컬 주소도 같이 둘 수 있습니다.

```text
http://127.0.0.1:8765/
http://127.0.0.1:8765/oauth2callback
```

## 배포 방식

이 서버는 HTTP 앱이므로 실제 공개 배포에서는 HTTPS를 앞단에 둬야 합니다.

- 간단한 테스트: Cloudflare Tunnel, ngrok, Tailscale Funnel
- 지속 운영: Render, Railway, Fly.io, VPS + Nginx/Caddy 리버스 프록시

`AUTOSAVER_PUBLIC_BASE_URL`은 사용자가 접속하는 최종 HTTPS 주소와 같아야 합니다. 프록시 뒤에서 실행해도 이 값이 맞으면 Google OAuth 콜백이 안정적으로 동작합니다.

## 주의

이 구현은 사용자별 데이터 분리를 제공합니다. 다만 공개 서비스로 운영하려면 계정 로그인, 이용량 제한, 저장 비밀번호 암호화, 작업 큐 제한을 추가하는 것이 좋습니다.
