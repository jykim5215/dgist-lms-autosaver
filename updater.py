"""GitHub 기반 앱 자가 업데이트.

배포된 앱이 GitHub 공개 저장소(raw)에서 최신 코드 파일을 받아 스스로 교체한다.
credentials.json 등 개인정보 파일은 대상에서 제외한다.
"""
from __future__ import annotations

import re
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# 배포자(사장님) GitHub 저장소
REPO = "jykim5215/dgist-lms-autosaver"
BRANCH = "main"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
VERSION_FILE = PROJECT_ROOT / "VERSION"

# 업데이트가 교체할 수 있는 파일 (개인정보 파일은 제외)
UPDATE_FILES = [
    "app.py",
    "web_ui.py",
    "main.py",
    "lms_crawler.py",
    "drive_uploader.py",
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
]


def local_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "DGIST-AutoSaver-Updater"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


def remote_version() -> str:
    return _fetch(f"{RAW_BASE}/VERSION").decode("utf-8").strip()


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
    """최신 파일들을 받아 로컬에 덮어쓴다. 성공 후 재시작 필요."""
    root = PROJECT_ROOT.resolve()
    updated: list[str] = []
    failed: list[str] = []
    for rel in UPDATE_FILES:
        target = (root / rel).resolve()
        # 경로 탈출 방지
        if target != root and root not in target.parents:
            continue
        try:
            data = _fetch(f"{RAW_BASE}/{rel}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            updated.append(rel)
        except Exception:
            failed.append(rel)

    try:
        VERSION_FILE.write_text(remote_version(), encoding="utf-8")
    except Exception:
        pass

    return {
        "ok": bool(updated),
        "updated": updated,
        "failed": failed,
        "count": len(updated),
        "version": local_version(),
    }


if __name__ == "__main__":
    print(check_update())
