# 상시 호스팅 배포 가이드

이 앱은 Python 서버, Playwright 기반 LMS 동기화, Google OAuth 콜백이 필요하므로 GitHub Pages 같은 정적 호스팅으로는 운영할 수 없습니다. 돈을 쓰지 않는 배포는 가능하지만, 무료 호스팅에서는 서버가 잠들거나 사용자 데이터가 사라질 수 있습니다.

## 권장 구조

- GitHub: 소스 코드 저장소와 자동 배포 트리거
- Render Web Service: 앱 서버 실행
- 임시 파일 시스템: 사용자별 설정, OAuth 토큰, 다운로드 기록 저장
- Render 기본 도메인: `https://<service-name>.onrender.com`

현재 `render.yaml`은 결제 정보를 요구하지 않도록 `free` 플랜 기준으로 작성되어 있습니다. 이 모드는 테스트/가벼운 공유용입니다. 진짜 상시 운영과 데이터 보존이 필요하면 유료 인스턴스와 persistent disk를 다시 켜야 합니다.

## Render 배포

1. GitHub 저장소의 `main` 브랜치에 최신 코드를 push합니다.
2. Render에서 **New > Blueprint**를 선택합니다.
3. 저장소 `jykim5215/dgist-lms-autosaver`를 연결합니다.
4. Render가 `render.yaml`을 읽어 `dgist-lms-autosaver` 서비스를 생성하게 둡니다.
5. 환경 변수 `AUTOSAVER_GOOGLE_CLIENT_ID`, `AUTOSAVER_GOOGLE_CLIENT_SECRET`을 Render Dashboard에서 입력합니다.
6. 배포가 끝난 뒤 Render 서비스 URL을 엽니다.

`render.yaml`은 다음 값을 포함합니다.

- `runtime: docker`: Playwright/Chromium 의존성을 Docker 이미지 안에 고정
- `plan: free`: 결제 정보 없이 테스트 배포
- `AUTOSAVER_ROOT=/tmp/autosaver`: 무료 인스턴스의 임시 저장 위치
- `healthCheckPath: /healthz`: Render 상태 확인 전용 엔드포인트
- `autoDeployTrigger: commit`: GitHub push 후 자동 재배포

## Google OAuth Redirect URI

Render가 발급한 실제 주소가 예를 들어 아래와 같다면:

```text
https://dgist-lms-autosaver.onrender.com
```

Google Cloud Console의 OAuth 클라이언트에 아래 Redirect URI를 추가합니다.

```text
https://dgist-lms-autosaver.onrender.com/oauth2callback
```

앱 화면의 Google 연동 도움말에도 현재 서버 기준 Redirect URI가 표시됩니다. `redirect_uri_mismatch`가 나면 그 값을 Google Cloud Console에 그대로 추가하면 됩니다.

## 사용자 데이터 분리

운영 모드는 `AUTOSAVER_MULTI_USER=1`입니다. 접속자별 세션 쿠키를 기준으로 `/tmp/autosaver/users/<user-id>` 아래에 다음 데이터가 분리 저장됩니다.

- LMS 설정과 다운로드 경로 설정
- Google Drive OAuth 토큰
- 다운로드 파일과 업로드 기록
- 검증/동기화 작업 로그

현재 구현은 별도 회원가입 없이 브라우저 세션 쿠키로 사용자를 구분합니다. 무료 Render 인스턴스에서는 이 데이터가 영구 보존된다고 보면 안 됩니다. 여러 기기에서 같은 작업공간을 이어 쓰거나 데이터를 안정적으로 보존하려면 계정 로그인과 영구 저장소를 추가해야 합니다.

## 상시 운영으로 다시 바꾸려면

Render에서 결제 정보를 등록한 뒤 `render.yaml`을 아래 방향으로 되돌립니다.

- `plan: starter`
- `disk.mountPath: /var/data`
- `AUTOSAVER_ROOT=/var/data`
- `AUTOSAVER_USERS_ROOT=/var/data/users`

## 로컬 확인

```powershell
$env:AUTOSAVER_MULTI_USER = "1"
$env:AUTOSAVER_UI_HOST = "127.0.0.1"
$env:AUTOSAVER_UI_PORT = "8765"
$env:AUTOSAVER_OPEN_BROWSER = "0"
python web_ui.py
```

상태 확인:

```powershell
Invoke-WebRequest http://127.0.0.1:8765/healthz
```
