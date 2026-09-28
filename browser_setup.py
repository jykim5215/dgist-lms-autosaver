"""LMS 로그인에 쓸 크로미움을 처음 한 번 내려받는다.

왜 앱에 같이 넣지 않았나
    크로미움은 426MB(헤드리스 전용도 270MB)라 설치 파일에 넣으면 배포본이
    400MB를 넘는다. 대신 브라우저를 돌리는 부분(playwright 패키지)만 넣고,
    LMS를 처음 쓸 때 실제 브라우저를 받는다. 한 번 받으면 계속 쓴다.

받는 위치
    %LOCALAPPDATA%\\ms-playwright — 앱을 지웠다 다시 깔아도 남는다.
    이미 개발용으로 playwright 를 쓴 적 있으면 그것을 그대로 쓴다.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _default_root() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def browsers_root() -> Path:
    custom = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    return Path(custom) if custom else _default_root()


# EXE 로 묶으면 playwright 드라이버가 앱 폴더 안(_internal\playwright\driver\
# package\.local-browsers)에서 브라우저를 찾는다. 거기엔 아무것도 없고, 설치
# 폴더는 보통 쓰기도 막혀 있다. 그래서 찾는 위치를 사용자 폴더로 고정한다.
# (launch 전에 정해져 있어야 해서 이 모듈을 불러오는 시점에 박아 둔다)
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_default_root()))


def browser_ready() -> bool:
    """크로미움(또는 헤드리스 셸)이 이미 있는지."""
    root = browsers_root()
    if not root.exists():
        return False
    for child in root.iterdir():
        name = child.name.lower()
        if name.startswith(("chromium-", "chromium_headless_shell-")):
            # 폴더만 남고 알맹이가 없는 경우가 있어 실행 파일까지 본다
            if any(child.rglob("*.exe")) or any(child.rglob("chrome")):
                return True
    return False


def _driver_command() -> list[str]:
    """`playwright install` 을 부를 명령.

    EXE 로 묶이면 `python -m playwright` 가 통하지 않는다(파이썬이 없다).
    playwright 가 함께 넣어 둔 node 드라이버를 직접 부른다.
    """
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-m", "playwright"]

    import playwright

    driver = Path(playwright.__file__).parent / "driver"
    node = driver / ("node.exe" if os.name == "nt" else "node")
    cli = driver / "package" / "cli.js"
    if node.exists() and cli.exists():
        return [str(node), str(cli)]
    raise RuntimeError("브라우저 설치 도구를 찾지 못했습니다.")


def ensure_browser() -> bool:
    """없으면 받는다. 받는 동안 진행 상황을 그대로 화면에 흘려보낸다."""
    if browser_ready():
        return True

    print("LMS 로그인에 쓸 브라우저가 없어 처음 한 번 내려받습니다.")
    print("270MB 정도이고, 다음부터는 바로 시작합니다.")
    sys.stdout.flush()

    try:
        command = _driver_command() + ["install", "chromium", "--only-shell"]
    except RuntimeError as exc:
        print(f"{exc}")
        return False

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
    except Exception as exc:
        print(f"브라우저를 받지 못했습니다: {exc}")
        return False

    for line in process.stdout or []:
        line = line.rstrip()
        # 진행률 막대는 줄마다 쏟아져서 로그를 덮는다. 요점만 남긴다.
        if line and "%" not in line:
            print(line)
            sys.stdout.flush()
    process.wait()

    if process.returncode != 0 or not browser_ready():
        print("브라우저 설치가 끝나지 않았습니다. 인터넷 연결을 확인하고 다시 시도해 주세요.")
        return False

    print("브라우저 준비 완료.")
    return True


if __name__ == "__main__":
    print("이미 있음" if browser_ready() else "없음 — 받는 중")
    raise SystemExit(0 if ensure_browser() else 1)
