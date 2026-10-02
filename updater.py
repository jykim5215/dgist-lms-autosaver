"""GitHub 릴리스로 앱을 업데이트한다.

설치형 앱(EXE)의 파이썬 코드는 실행 파일 안에 묶여 있어서, 예전처럼 저장소의 .py 파일을
받아 덮어써서는 바뀌지 않는다. 그래서 새 버전은 GitHub 릴리스에 설치 파일(setup.exe)로 올리고,
앱은 그것을 받아 조용히 설치한 뒤 다시 켠다.

  1) api.github.com/repos/<저장소>/releases/latest 에서 최신 릴리스(태그 v1.2.3)를 읽는다
  2) 첨부된 bungeoppang-<버전>-win-x64-setup.exe 를 내려받는다
  3) GitHub 이 붙여 주는 SHA-256(자산 digest) 과 맞는지 확인한다 — 안 맞거나 값이 없으면 설치하지 않는다
  4) 설치 파일을 /SILENT 로 실행하고 앱은 스스로 끈다. 설치가 끝나면 설치 프로그램이 앱을 다시 켠다(/RELAUNCH=1)

예전 방식(저장소 main 의 VERSION 과 비교)은 저장소가 1.8.6 에 멈춰 있어 늘 '최신' 으로 나왔다(2026-09-28).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from urllib.parse import urlparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# 배포자 GitHub 저장소 (공개)
REPO = "tutleblue/dgist-lms-autosaver"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_PATTERN = re.compile(r"^bungeoppang-[\d.]+-win-x64-setup\.exe$")
# 설치 파일만 받는다. 다른 호스트로 넘어가는 주소는 쓰지 않는다 (GitHub 이 저장소를 옮기는 곳은 이 둘)
ALLOWED_DOWNLOAD_HOSTS = ("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")
VERSION_FILE = PROJECT_ROOT / "VERSION"
USER_AGENT = "Bungeoppang-Updater"


def local_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def _ver_tuple(v: str) -> tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", v)[:3]]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def _get_json(url: str) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _pick_asset(release: dict) -> dict | None:
    for asset in release.get("assets") or []:
        if ASSET_PATTERN.match(str(asset.get("name", ""))):
            return asset
    return None


def _asset_sha256(release: dict, asset: dict) -> str:
    """GitHub 이 자산마다 계산해 주는 digest("sha256:…"). 없으면 릴리스 본문의 'SHA256: …' 줄."""
    digest = str(asset.get("digest") or "")
    if digest.lower().startswith("sha256:"):
        return digest.split(":", 1)[1].strip().lower()
    body = str(release.get("body") or "")
    m = re.search(r"SHA-?256\s*[:=]\s*([0-9a-fA-F]{64})", body)
    return m.group(1).lower() if m else ""


def _release_notes(body: str) -> list[str]:
    """릴리스 본문에서 '- ' 로 시작하는 줄만 짧게 뽑는다 (화면에 몇 줄 보여 주려고)."""
    lines = []
    for raw in str(body or "").splitlines():
        line = raw.strip()
        if line.startswith(("- ", "* ")):
            lines.append(line[2:].strip())
    return lines[:8]


def check_update() -> dict:
    current = local_version()
    try:
        release = _get_json(LATEST_RELEASE_API)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"ok": True, "current": current, "latest": current, "updateAvailable": False,
                    "message": "아직 올라온 릴리스가 없습니다.", "repo": REPO}
        if exc.code == 403:
            return {"ok": False, "current": current, "message": "GitHub 확인 한도에 걸렸습니다. 잠시 뒤 다시 확인해 주세요."}
        return {"ok": False, "current": current, "message": f"업데이트 확인 실패: HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "current": current, "message": f"업데이트 확인 실패: {exc}"}

    latest = str(release.get("tag_name") or "").lstrip("vV") or current
    asset = _pick_asset(release)
    available = _ver_tuple(latest) > _ver_tuple(current) and asset is not None
    return {
        "ok": True,
        "current": current,
        "latest": latest,
        "updateAvailable": available,
        "title": release.get("name") or f"v{latest}",
        "notes": _release_notes(release.get("body", "")),
        "publishedAt": release.get("published_at"),
        "size": (asset or {}).get("size"),
        "canInstall": bool(getattr(sys, "frozen", False)) and os.name == "nt",
        "repo": REPO,
    }


# 내려받기·설치 진행 (화면이 물어 볼 수 있게)
_job_lock = threading.Lock()
_job: dict = {"running": False, "stage": "", "done": 0, "total": 0, "message": "", "ok": None}


def get_update_job() -> dict:
    with _job_lock:
        return dict(_job)


def _set_job(**values) -> None:
    with _job_lock:
        _job.update(values)


def _download(url: str, dest: Path, total: int) -> str:
    """dest 에 받으면서 SHA-256 을 같이 계산해 돌려준다."""
    host = urlparse(url).hostname or ""
    if not any(host == h or host.endswith("." + h) for h in ALLOWED_DOWNLOAD_HOSTS):
        raise RuntimeError(f"허용되지 않은 다운로드 주소입니다: {host}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"})
    sha = hashlib.sha256()
    done = 0
    with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as out:
        final_host = urlparse(resp.geturl()).hostname or ""
        if not any(final_host == h or final_host.endswith("." + h) for h in ALLOWED_DOWNLOAD_HOSTS):
            raise RuntimeError(f"허용되지 않은 다운로드 주소로 넘어갔습니다: {final_host}")
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)
            sha.update(chunk)
            done += len(chunk)
            _set_job(done=done, total=total)
    return sha.hexdigest()


def update_marker_path() -> Path:
    try:
        from runtime_config import AUTOSAVER_DATA_ROOT

        return Path(AUTOSAVER_DATA_ROOT) / "update_done.json"
    except Exception:
        return Path(tempfile.gettempdir()) / "bungeoppang-update" / "update_done.json"


def _write_update_marker(old: str, new: str) -> None:
    try:
        path = update_marker_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"from": old, "to": new}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _run_update(on_ready_to_exit) -> None:
    try:
        _set_job(stage="확인", message="새 버전을 확인하는 중")
        release = _get_json(LATEST_RELEASE_API)
        latest = str(release.get("tag_name") or "").lstrip("vV")
        if _ver_tuple(latest) <= _ver_tuple(local_version()):
            raise RuntimeError(f"이미 최신입니다 (v{local_version()}).")
        asset = _pick_asset(release)
        if not asset:
            raise RuntimeError("릴리스에 설치 파일이 없습니다.")
        expected = _asset_sha256(release, asset)
        if not expected:
            # 확인할 값이 없으면 받은 파일이 진짜인지 알 수 없다. 설치하지 않는다.
            raise RuntimeError("설치 파일의 확인값(SHA-256)이 없어 설치하지 않았습니다.")

        folder = Path(tempfile.gettempdir()) / "bungeoppang-update"
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / asset["name"]
        _set_job(stage="내려받기", message="새 버전을 내려받는 중", total=int(asset.get("size") or 0))
        actual = _download(asset["browser_download_url"], dest, int(asset.get("size") or 0))
        _set_job(stage="검사", message="받은 파일이 진짜인지 확인하는 중")
        if actual != expected:
            dest.unlink(missing_ok=True)
            raise RuntimeError("받은 파일이 원본과 달라 설치하지 않았습니다. 다시 시도해 주세요.")

        _set_job(stage="설치", message="설치를 시작합니다. 잠시 뒤 앱이 다시 켜집니다.")
        # 다시 켜진 앱이 '업데이트를 마쳤어요' 를 보여 줄 수 있게 적어 둔다 (web_ui.get_whats_new)
        _write_update_marker(local_version(), latest)
        # 설치 프로그램이 켜져 있는 앱을 닫고(CloseApplications) 파일을 바꾼 뒤 다시 켠다(/RELAUNCH=1).
        # 진행은 앱 안 업데이트 카드가 보여 주므로 설치 창은 띄우지 않는다(/VERYSILENT).
        # 앱과 따로 살아야 하므로 새 프로세스 묶음으로 띄운다.
        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            [str(dest), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELAUNCH=1"],
            close_fds=True,
            creationflags=flags,
        )
        _set_job(running=False, ok=True, stage="설치")
        if on_ready_to_exit:
            on_ready_to_exit()
    except Exception as exc:
        _set_job(running=False, ok=False, stage="실패", message=str(exc))


def apply_update(on_ready_to_exit=None) -> dict:
    """설치형 앱: 최신 설치 파일을 받아 확인한 뒤 설치를 시작한다(뒤에서 돈다)."""
    if not (getattr(sys, "frozen", False) and os.name == "nt"):
        return {"ok": False, "message": "소스로 실행 중이면 git pull 로 받아 주세요. 설치형 앱에서만 자동 업데이트합니다."}
    with _job_lock:
        if _job["running"]:
            return {"ok": False, "busy": True, "message": "이미 업데이트하는 중입니다."}
        _job.update(running=True, stage="확인", done=0, total=0, message="", ok=None)
    threading.Thread(target=_run_update, args=(on_ready_to_exit,), name="app-update", daemon=True).start()
    return {"ok": True, "started": True, "message": "새 버전을 내려받는 중입니다."}


if __name__ == "__main__":
    print(check_update())
