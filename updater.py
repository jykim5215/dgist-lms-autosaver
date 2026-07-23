"""GitHub 기반 앱 자가 업데이트.

배포된 앱이 GitHub 공개 저장소(raw)에서 최신 코드 파일을 받아 스스로 교체한다.
credentials.json 등 개인정보 파일은 대상에서 제외한다.
"""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# 배포자(사장님) GitHub 저장소
REPO = "jykim5215/dgist-lms-autosaver"
BRANCH = "main"
# Contents API(api.github.com)는 비인증 시 시간당 60회 제한이라
# 파일 개수만큼 호출하면 금방 rate limit에 걸린다.
# raw는 그 쿼터를 쓰지 않으므로 raw + 캐시무효화 쿼리로 최신본을 받는다.
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
VERSION_FILE = PROJECT_ROOT / "VERSION"

# 업데이트가 교체할 수 있는 파일 (개인정보 파일은 제외)
UPDATE_FILES = [
    "app.py",
    "web_ui.py",
    "main.py",
    "lms_crawler.py",
    "drive_uploader.py",
    "calendar_sync.py",
    "email_reader.py",
    "email_notifier.py",
    "ai_summarizer.py",
    "runtime_config.py",
    "updater.py",
    "verify.py",
    "requirements.txt",
    "config.example.py",
    "README.md",
    "web/index.html",
    "web/app.js",
    "web/styles.css",
    "web/favicon.svg",
]


def local_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def _fetch_file(rel_path: str) -> bytes:
    """raw.githubusercontent.com에서 파일 원본(bytes)을 캐시 없이 받는다."""
    # CDN 캐시(~5분)를 피하려고 매 요청마다 다른 쿼리를 붙인다.
    url = f"{RAW_BASE}/{rel_path}?nocache={int(time.time() * 1000)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "DGIST-AutoSaver-Updater",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise RuntimeError(
                "GitHub 요청 한도에 걸렸습니다. 잠시 후(약 1시간) 다시 시도해 주세요."
            ) from exc
        if exc.code == 404:
            raise RuntimeError(f"저장소에 파일이 없습니다: {rel_path}") from exc
        raise


def _fetch_version_via_api() -> str:
    """VERSION만 Contents API로 읽는다 (캐시 없이 즉시 최신).

    호출이 1회뿐이라 시간당 60회 제한에 여유가 있다.
    """
    import base64
    import json

    url = f"https://api.github.com/repos/{REPO}/contents/VERSION?ref={BRANCH}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "DGIST-AutoSaver-Updater",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("encoding") == "base64" and "content" in data:
        return base64.b64decode(data["content"]).decode("utf-8").strip()
    raise RuntimeError("VERSION을 읽을 수 없습니다.")


def remote_version() -> str:
    """최신 버전 문자열.

    버전은 '갱신 필요 여부'의 기준이라 캐시 지연이 있으면 안 된다.
    → Contents API를 먼저 쓰고(1회), 막혀 있으면 raw로 대체한다.
    """
    try:
        return _fetch_version_via_api()
    except Exception:
        # API가 rate limit 등으로 막힌 경우: raw는 최대 몇 분 늦을 수 있다.
        return _fetch_file("VERSION").decode("utf-8").strip()


def _ver_tuple(v: str) -> tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", v)[:3]]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def check_update() -> dict:
    current = local_version()
    try:
        latest = remote_version()
    except Exception as exc:
        return {"ok": False, "current": current, "message": f"업데이트 확인 실패: {exc}"}
    available = _ver_tuple(latest) > _ver_tuple(current)
    return {
        "ok": True,
        "current": current,
        "latest": latest,
        "updateAvailable": available,
        "repo": REPO,
    }


def apply_update() -> dict:
    """최신 파일을 '전부' 받은 뒤에만 덮어쓴다. 성공 후 재시작 필요.

    한 개라도 못 받으면 아무 파일도 건드리지 않는다.
    (중간에 끊겨 프론트/백엔드 버전이 어긋나는 상태를 막기 위함)
    """
    root = PROJECT_ROOT.resolve()

    # 1단계: 모두 메모리로 내려받는다. 여기서 실패하면 디스크는 그대로다.
    payloads: list[tuple[Path, str, bytes]] = []
    for rel in UPDATE_FILES:
        target = (root / rel).resolve()
        # 경로 탈출 방지
        if target != root and root not in target.parents:
            continue
        try:
            payloads.append((target, rel, _fetch_file(rel)))
        except Exception as exc:
            return {
                "ok": False,
                "updated": [],
                "failed": [rel],
                "count": 0,
                "version": local_version(),
                "message": f"'{rel}' 을(를) 받지 못해 업데이트를 취소했습니다. 기존 파일은 그대로입니다. ({exc})",
            }

    try:
        latest = remote_version()
    except Exception:
        latest = ""

    # 2단계: 전부 받아둔 뒤에만 기록한다.
    updated: list[str] = []
    for target, rel, data in payloads:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        updated.append(rel)

    if latest:
        try:
            VERSION_FILE.write_text(latest + "\n", encoding="utf-8")
        except OSError:
            pass

    return {
        "ok": True,
        "updated": updated,
        "failed": [],
        "count": len(updated),
        "version": local_version(),
    }


if __name__ == "__main__":
    print(check_update())
