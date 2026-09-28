"""웹 호스팅(Render) 주소에 앱 대신 띄우는 안내 페이지.

왜 앱을 웹으로 두지 않나 (2026-09-29)
  다른 PC 사용자가 이 주소로 들어와 '앱이 웹페이지로 열린다', 'LMS 동기화가 계속 실패한다' 고 했다.
  - 무료 서버는 메모리가 512MB 인데, LMS 로그인에 쓰는 크롬 한 벌이 로그인 화면까지만 가도
    280MB 를 쓴다(파이썬·드라이버·크롬 7개 프로세스 합계, 실측). 과목 페이지를 열면 더 든다.
  - 15분 동안 아무도 안 들어오면 서버가 잠들고, 데이터를 /tmp 에 둬서 배포·재시작마다 사라진다.
  - 비밀번호를 지키는 DPAPI 는 Windows 에만 있어 서버에는 학교 비밀번호가 평문으로 남는다.
  그래서 이 주소에서는 비밀번호를 받지 않고 설치 파일로 안내만 한다. Dockerfile 이 web_ui.py 대신 이것을 띄운다.
"""
from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASES = "https://github.com/jykim5215/dgist-lms-autosaver/releases/latest"

PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="robots" content="noindex" />
<title>붕어빵 받기</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<style>
  :root {
    --bg: #faf9f5; --surface: #ffffff; --line: #e6e3da;
    --text: #1f1e1d; --soft: #5d5a52; --faint: #8b877c;
    --accent: #c0674a; --accent-strong: #9c4e33; --accent-soft: #f6e9e3;
    --serif: "Lora", "Noto Serif KR", Georgia, serif;
    --sans: "Inter", "Pretendard", "Segoe UI", "Malgun Gothic", system-ui, sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #262624; --surface: #30302e; --line: #45443f;
      --text: #e8e6df; --soft: #b5b1a6; --faint: #8a867b;
      --accent: #c0674a; --accent-strong: #dd8b6b; --accent-soft: #40312a;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    background: var(--bg); color: var(--text); font: 15px/1.6 var(--sans);
    padding: 24px 16px; word-break: keep-all;
  }
  main {
    width: 100%; max-width: 460px; background: var(--surface);
    border: 1px solid var(--line); border-radius: 18px; padding: 32px 28px 26px;
    text-align: center;
  }
  img { width: 112px; height: 112px; object-fit: contain; }
  h1 { font: 600 24px/1.35 var(--serif); margin: 10px 0 8px; }
  p { margin: 0 0 10px; color: var(--soft); }
  .go {
    display: inline-block; margin: 14px 0 6px; padding: 12px 22px; border-radius: 999px;
    background: var(--accent); color: #fff; font-weight: 600; text-decoration: none;
  }
  .go:hover { background: var(--accent-strong); }
  ol {
    text-align: left; margin: 18px 0 0; padding: 14px 16px 14px 34px;
    background: var(--accent-soft); border-radius: 12px; color: var(--soft);
  }
  li + li { margin-top: 4px; }
  small { display: block; margin-top: 16px; color: var(--faint); font-size: 12.5px; }
</style>
</head>
<body>
<main>
  <img src="/img/dalgu/hello.png" alt="" />
  <h1>붕어빵은 설치해서 쓰는 앱이에요</h1>
  <p>이 웹 주소에서는 LMS 동기화가 제대로 되지 않아 운영을 멈췄어요.
     윈도우 PC에 설치하면 자료 받기와 메일 확인이 모두 내 컴퓨터에서 돌아가요.</p>
  <a class="go" href="__RELEASES__">설치 파일 받기</a>
  <ol>
    <li>열린 페이지의 <b>Assets</b>에서 <b>…-setup.exe</b>를 받아요.</li>
    <li>받은 파일을 실행해 설치해요.</li>
    <li>앱의 설정에서 LMS 계정을 다시 넣어요.</li>
  </ol>
  <small>이 주소에 넣었던 계정과 설정은 서버에서 지워졌어요.<br />
  Bungeoppang is a Windows app — download the installer from the link above.</small>
</main>
</body>
</html>
""".replace("__RELEASES__", RELEASES)

# 안내 페이지가 쓰는 그림만 내보낸다 (앱 화면 파일은 내보내지 않는다)
ASSETS = {
    "/favicon.svg": (ROOT / "web" / "favicon.svg", "image/svg+xml"),
    "/img/dalgu/hello.png": (ROOT / "web" / "img" / "dalgu" / "hello.png", "image/png"),
}


class NoticeHandler(BaseHTTPRequestHandler):
    server_version = "BungeoppangNotice/1.0"

    def _send(self, status: int, body: bytes, content_type: str, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self._send(HTTPStatus.OK, b'{"ok": true, "mode": "notice"}', "application/json")
            return
        if path in ASSETS:
            file, content_type = ASSETS[path]
            self._send(HTTPStatus.OK, file.read_bytes(), content_type, "public, max-age=86400")
            return
        if path.startswith("/api/"):
            self._api_gone()
            return
        self._send(HTTPStatus.OK, PAGE.encode("utf-8"), "text/html; charset=utf-8")

    do_HEAD = do_GET

    def do_POST(self) -> None:
        # 예전 탭이 열려 있어도 비밀번호 같은 본문은 읽지도 저장하지도 않는다
        self._api_gone()

    def _api_gone(self) -> None:
        body = json.dumps(
            {"ok": False, "message": "웹 버전은 운영을 멈췄어요. 설치 파일을 받아 PC에서 써 주세요."},
            ensure_ascii=False,
        ).encode("utf-8")
        self._send(HTTPStatus.GONE, body, "application/json; charset=utf-8")

    def log_message(self, format: str, *args) -> None:  # 요청마다 찍히는 줄은 줄인다
        pass


def main() -> None:
    host = os.environ.get("AUTOSAVER_UI_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT") or os.environ.get("AUTOSAVER_UI_PORT") or "8765")
    print(f"붕어빵 안내 페이지: http://{host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), NoticeHandler).serve_forever()


if __name__ == "__main__":
    main()
