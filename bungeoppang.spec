# -*- mode: python ; coding: utf-8 -*-
"""붕어빵을 EXE 한 벌로 묶는다.

왜 onefile 이 아니라 onedir 인가
  onefile 은 켤 때마다 임시 폴더에 전부 풀어 놓아 시작이 느리고, 백신이
  자주 잡는다. 폴더째 주는 편이 켜는 속도도 빠르고 문제도 적다.

같이 넣지 않는 것
  credentials.json — 구글 OAuth 비밀. 이게 들어가면 받은 사람이 내 앱
  이름으로 동의 화면을 띄울 수 있다. 앱 안에서 각자 넣도록 해 두었다.
  (설정 → 계정 연결 → 파일 고르기)

만들기:  python -m PyInstaller bungeoppang.spec --noconfirm
"""

from pathlib import Path

PROJECT = Path(SPECPATH)

# 화면 파일과 사진은 그대로 함께 넣는다
#
# google_client.json (데스크톱 앱 OAuth 클라이언트)이 있으면 같이 넣는다.
# 웹 클라이언트와 달리 데스크톱 클라이언트의 secret 은 구글도 비밀로 보지
# 않는다(설치형 앱에서는 어차피 숨길 수 없다). 보안은 127.0.0.1 로만
# 되돌아오는 점과 PKCE 가 맡는다. 그래서 넣어 두면 받은 사람이 파일을
# 따로 챙기지 않아도 바로 로그인할 수 있다.
datas = [
    (str(PROJECT / "web"), "web"),
    (str(PROJECT / "uni_photos.json"), "."),
    (str(PROJECT / "VERSION"), "."),
    (str(PROJECT / "config.example.py"), "."),
]

_client = PROJECT / "google_client.json"
if _client.exists():
    datas.append((str(_client), "."))
else:
    print("[붕어빵] google_client.json 이 없어 로그인 준비물 없이 묶습니다. "
          "받는 사람이 설정에서 직접 넣어야 합니다.")

hiddenimports = [
    # 구글 라이브러리는 늦게 불러오는 곳이 있어 PyInstaller 가 놓친다
    "googleapiclient.discovery",
    "googleapiclient.http",
    "google.oauth2.credentials",
    "google_auth_oauthlib.flow",
    "google.auth.transport.requests",
    # 앱이 상황에 따라 부르는 것들
    "winotify",
    "schedule",
    "webview.platforms.edgechromium",
]

a = Analysis(
    ["app.py"],
    pathex=[str(PROJECT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # 안 쓰는 무거운 것들은 빼서 크기를 줄인다
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PIL", "playwright", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="붕어빵",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # 창이 뜨는 앱이라 검은 콘솔은 띄우지 않는다
    console=False,
    icon=str(PROJECT / "web" / "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="붕어빵",
)
