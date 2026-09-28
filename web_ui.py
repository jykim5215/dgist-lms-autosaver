"""Local web dashboard for DGIST LMS AutoSaver.

Run with:
    python web_ui.py
"""
from __future__ import annotations

import ast
import gzip
import hashlib
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from http.cookies import SimpleCookie
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import urllib.request
from urllib.parse import parse_qs, quote, urlencode, urlparse


def _bundle_root() -> Path:
    """소스로 돌 때와 EXE로 묶였을 때 모두 맞는 '앱 파일이 있는 곳'.

    PyInstaller 로 묶으면 화면 파일이 exe 옆 _internal 폴더로 들어가고
    __file__ 은 그 안을 가리키지 않는다. sys._MEIPASS 를 봐야 한다.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parent


PROJECT_ROOT = _bundle_root()
WEB_ROOT = PROJECT_ROOT / "web"
DEFAULT_AUTOSAVER_ROOT = Path(r"C:\lms-autosaver") if os.name == "nt" else Path.home() / ".lms-autosaver"
AUTOSAVER_ROOT = Path(os.environ.get("AUTOSAVER_ROOT", str(DEFAULT_AUTOSAVER_ROOT)))
USERS_ROOT = Path(os.environ.get("AUTOSAVER_USERS_ROOT", str(AUTOSAVER_ROOT / "users")))
MULTI_USER_MODE = os.environ.get("AUTOSAVER_MULTI_USER", "0").lower() in {"1", "true", "yes", "on"}
DEFAULT_DOWNLOAD_PATH = AUTOSAVER_ROOT / "downloads"
CONFIG_PATH = PROJECT_ROOT / "config.py"
DRIVE_CREDENTIALS_PATH = Path(
    os.environ.get("AUTOSAVER_GOOGLE_CLIENT_SECRETS", str(AUTOSAVER_ROOT / "credentials.json"))
)
GOOGLE_OAUTH_PENDING_PATH = AUTOSAVER_ROOT / "oauth_pending.json"
FALLBACK_COURSE_MAP = PROJECT_ROOT / "file_course_map.json"
from runtime_config import GOOGLE_SCOPES as _GOOGLE_SCOPES
from runtime_config import atomic_write_text

GOOGLE_OAUTH_SCOPE = _GOOGLE_SCOPES[0]
GOOGLE_CALENDAR_SCOPE = _GOOGLE_SCOPES[1]
# Drive 업로드 + 캘린더 동기화를 함께 사용하므로 두 권한을 같이 요청한다.
GOOGLE_OAUTH_SCOPES = list(_GOOGLE_SCOPES)
GOOGLE_OAUTH_FALLBACK_REDIRECT_URI = "http://127.0.0.1:8765/oauth2callback"
SESSION_COOKIE = "autosaver_sid"


def detect_public_base_url() -> str:
    explicit = os.environ.get("AUTOSAVER_PUBLIC_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")

    render_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
    if render_url:
        return render_url.rstrip("/")

    codespace_name = os.environ.get("CODESPACE_NAME", "").strip()
    if codespace_name:
        port = os.environ.get("AUTOSAVER_UI_PORT") or os.environ.get("PORT") or "8765"
        domain = os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
        return f"https://{codespace_name}-{port}.{domain}".rstrip("/")

    return ""


PUBLIC_BASE_URL = detect_public_base_url()


task_lock = threading.Lock()
oauth_states: dict[str, dict[str, Any]] = {}
current_processes: dict[str, subprocess.Popen] = {}
task_states: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True)
class UserWorkspace:
    user_id: str
    root: Path
    config_path: Path
    default_download_path: Path
    token_path: Path
    downloaded_files_log: Path
    file_metadata_log: Path
    deadlines_log: Path
    upload_selection_path: Path
    emails_log: Path
    my_events_path: Path
    health_path: Path
    timetable_path: Path
    shelves_path: Path
    academic_path: Path
    notices_path: Path
    catalog_path: Path
    directory_path: Path
    shuttle_path: Path


def default_task_state() -> dict[str, Any]:
    return {
        "running": False,
        "kind": None,
        "startedAt": None,
        "finishedAt": None,
        "returnCode": None,
        "logs": [],
    }


def workspace_for_user(user_id: str) -> UserWorkspace:
    if MULTI_USER_MODE:
        root = USERS_ROOT / user_id
        config_path = root / "config.json"
    else:
        root = AUTOSAVER_ROOT
        config_path = AUTOSAVER_ROOT / "config.json"
    return UserWorkspace(
        user_id=user_id,
        root=root,
        config_path=config_path,
        default_download_path=root / "downloads",
        token_path=root / "token.json",
        downloaded_files_log=root / "downloaded_files.json",
        file_metadata_log=root / "file_metadata.json",
        deadlines_log=root / "deadlines.json",
        upload_selection_path=root / "upload_selection.json",
        emails_log=root / "emails.json",
        my_events_path=root / "my_events.json",
        health_path=root / "health.json",
        timetable_path=root / "timetable.json",
        shelves_path=root / "shelves.json",
        academic_path=root / "academic_calendar.json",
        notices_path=root / "notices.json",
        catalog_path=root / "course_catalog.json",
        directory_path=root / "directory.json",
        shuttle_path=root / "shuttle.json",
    )


def task_state_for(user_id: str) -> dict[str, Any]:
    with task_lock:
        return task_states.setdefault(user_id, default_task_state())


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        with path.open("r", encoding="utf-8-sig") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return fallback


def load_oauth_pending() -> dict[str, dict[str, Any]]:
    data = read_json(GOOGLE_OAUTH_PENDING_PATH, {})
    return data if isinstance(data, dict) else {}


def save_oauth_pending(states: dict[str, dict[str, Any]]) -> None:
    AUTOSAVER_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_write_text(GOOGLE_OAUTH_PENDING_PATH, 
        json.dumps(states, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def remember_oauth_state(
    workspace: UserWorkspace,
    state: str,
    redirect_uri: str,
    code_verifier: str | None,
    session_token: str | None = None,
) -> None:
    oauth_states[state] = {
        "user_id": workspace.user_id,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
        "session_token": session_token,
        "created_at": now_iso(),
    }
    pending = load_oauth_pending()
    pending[state] = oauth_states[state]
    save_oauth_pending(pending)


def pop_oauth_state(state: str) -> dict[str, Any] | None:
    pending = load_oauth_pending()
    saved = oauth_states.pop(state, None) or pending.pop(state, None)
    if state in pending:
        pending.pop(state, None)
    save_oauth_pending(pending)
    return saved


def read_legacy_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}

    values: dict[str, Any] = {}
    try:
        tree = ast.parse(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError):
        return values

    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    pass
    return values


def read_config(workspace: UserWorkspace) -> dict[str, Any]:
    data = read_json(workspace.config_path, {})
    if isinstance(data, dict) and data:
        # 저장된 비밀 항목은 암호문이므로 읽을 때 풀어 준다.
        # (평문으로 저장된 예전 설정도 그대로 통과한다)
        for key in SECRET_KEYS:
            value = data.get(key)
            if isinstance(value, str) and value.startswith(DPAPI_PREFIX):
                data[key] = dpapi_unprotect(value)
        return data
    if not MULTI_USER_MODE:
        return read_legacy_config()
    return {}


def py_string(value: Any) -> str:
    return repr(str(value))


def _minutes_field(payload: dict[str, Any], existing: dict[str, Any], key: str, existing_name: str, default: int) -> int:
    """자동 실행 주기(분). 0 이면 사용 안 함. 이상한 값은 기본값으로."""
    raw = payload.get(key, existing.get(existing_name, default))
    try:
        return max(0, int(str(raw).strip() or 0))
    except (TypeError, ValueError):
        return default


def _legacy_email_minutes(existing: dict[str, Any]) -> int:
    """예전 '주기적 자동 실행' 설정이 메일이었으면 그 주기를 이어받는다."""
    if str(existing.get("AUTO_INTERVAL_KIND", "emails")) == "emails":
        try:
            value = int(existing.get("AUTO_INTERVAL_MINUTES", 5) or 0)
            return value if value > 0 else 5
        except (TypeError, ValueError):
            pass
    return 5


def auto_minutes(config: dict[str, Any]) -> dict[str, int]:
    """종류별 자동 실행 주기(분). 설정이 없으면 기본값 (메일 5 / 마감 60 / 자료 180)."""
    return {
        "emails": _minutes_field({}, config, "", "AUTO_EMAIL_MINUTES", _legacy_email_minutes(config)),
        "deadlines": _minutes_field({}, config, "", "AUTO_DEADLINE_MINUTES", 60),
        "sync": _minutes_field({}, config, "", "AUTO_SYNC_MINUTES", 180),
    }


def _merge_cloud_save(existing: dict[str, Any], incoming: Any) -> dict[str, dict[str, Any]]:
    """화면에서 온 {key: {on, path}} 를 저장된 값 위에 얹는다. 안 온 키는 그대로."""
    merged = cloud_save_settings(existing)
    if isinstance(incoming, dict):
        for key, value in incoming.items():
            if key not in merged or not isinstance(value, dict):
                continue
            if "on" in value:
                merged[key]["on"] = bool(value["on"])
            if "path" in value:
                merged[key]["path"] = str(value.get("path") or "").strip()
    return merged


def write_config(workspace: UserWorkspace, payload: dict[str, Any]) -> dict[str, Any]:
    existing = read_config(workspace)

    def field(key: str, existing_name: str, default: str = "", secret: bool = False) -> str:
        value = str(payload.get(key, "")).strip()
        if secret and not value:
            return str(existing.get(existing_name, default))
        return value or str(existing.get(existing_name, default))

    download_path = field("downloadPath", "DOWNLOAD_PATH", str(workspace.default_download_path))
    schedule_time = field("scheduleTime", "SCHEDULE_TIME", "08:00")
    lms_url = field("lmsUrl", "LMS_URL", "https://lms.dgist.ac.kr")
    login_url = field(
        "loginUrl",
        "LOGIN_URL",
        "https://saml.dgist.ac.kr/authentication/idpw/idPwLogin.html?agentId=-100000&useOauth=0",
    )

    values = {
        "LMS_ID": field("lmsId", "LMS_ID"),
        "LMS_PASSWORD": field("lmsPassword", "LMS_PASSWORD", secret=True),
        "GEMINI_API_KEY": field("geminiKey", "GEMINI_API_KEY", secret=True),
        # 공공데이터포털(data.go.kr) 인증키. 인코딩·디코딩키 아무거나 넣어도 된다.
        "DGIST_API_KEY": field("dgistApiKey", "DGIST_API_KEY", secret=True),
        "EMAIL_ADDRESS": field("emailAddress", "EMAIL_ADDRESS"),
        "EMAIL_PASSWORD": field("emailPassword", "EMAIL_PASSWORD", secret=True),
        "EMAIL_TO": field("emailTo", "EMAIL_TO", field("emailAddress", "EMAIL_ADDRESS")),
        "DOWNLOAD_PATH": download_path,
        "SCHEDULE_TIME": schedule_time,
        "LMS_URL": lms_url,
        "LOGIN_URL": login_url,
        "SCHOOL_EMAIL": field("schoolEmail", "SCHOOL_EMAIL"),
        "SCHOOL_EMAIL_PASSWORD": field("schoolEmailPassword", "SCHOOL_EMAIL_PASSWORD", secret=True),
        "SCHOOL_IMAP_HOST": field("schoolImapHost", "SCHOOL_IMAP_HOST", "mail.dgist.ac.kr"),
        "LOCAL_SAVE_PATH": str(payload.get("localSavePath", existing.get("LOCAL_SAVE_PATH", ""))).strip(),
        # 동기화 때 내 컴퓨터에도 자동 저장: off / current(이번 학기) / all
        "AUTO_LOCAL_SAVE": local_autosave_mode(
            {"AUTO_LOCAL_SAVE": payload.get("autoLocalSave", existing.get("AUTO_LOCAL_SAVE", "off"))}
        ),
        # 내 컴퓨터·클라우드 폴더에 넣을 과목 범위
        "SAVE_SCOPE": (str(payload.get("saveScope")) if str(payload.get("saveScope")) in ("current", "all")
                       else str(existing.get("SAVE_SCOPE", "current"))),
        # 클라우드 폴더 자동 저장: {onedrive: {on, path}, ...}
        "CLOUD_SAVE": _merge_cloud_save(existing, payload.get("clouds")),
        # 동기화 때 구글 드라이브에도 올릴지. 키가 없던 예전 설정은 늘 올렸으니 기본은 켜짐.
        "AUTO_DRIVE_UPLOAD": bool(payload["driveUpload"]) if "driveUpload" in payload
        else existing.get("AUTO_DRIVE_UPLOAD", True) is not False,
        # 주기적 자동 실행 (분 단위, 0이면 사용 안 함)
        # 학교 메일서버는 IDLE(푸시)을 지원하지 않아서, 새 메일을 바로 알려면
        # 주기적으로 확인하는 수밖에 없다. 증분 수집으로 한 번에 1초 남짓이라
        # 5분마다 돌려도 부담이 없다. (스마트폰 메일 앱들의 기본 주기는 15분쯤)
        # 자동으로 가져오는 게 기본이다. 메일 5분 / 마감 1시간 / 자료 3시간.
        # 예전 설정(AUTO_INTERVAL_*)은 메일 주기로 이어받는다.
        "AUTO_EMAIL_MINUTES": _minutes_field(payload, existing, "autoEmailMinutes", "AUTO_EMAIL_MINUTES", _legacy_email_minutes(existing)),
        "AUTO_DEADLINE_MINUTES": _minutes_field(payload, existing, "autoDeadlineMinutes", "AUTO_DEADLINE_MINUTES", 60),
        "AUTO_SYNC_MINUTES": _minutes_field(payload, existing, "autoSyncMinutes", "AUTO_SYNC_MINUTES", 180),
        # 구글 캘린더 자동 동기화
        "GCAL_SYNC_ENABLED": bool(
            payload.get("gcalSyncEnabled", existing.get("GCAL_SYNC_ENABLED", False))
        ),
        "GCAL_CALENDAR_NAME": field("gcalCalendarName", "GCAL_CALENDAR_NAME", "DGIST 메일 일정"),
    }

    # 관심사: 선택한 태그 + 자유 입력을 합쳐 AI 분류 기준 문자열 생성
    interest_tags = payload.get("interestTags")
    if not isinstance(interest_tags, list):
        interest_tags = existing.get("EMAIL_INTEREST_TAGS", [])
    interest_tags = [str(tag).strip() for tag in interest_tags if str(tag).strip()]
    if "interestsCustom" in payload:
        interests_custom = str(payload.get("interestsCustom", "")).strip()
    else:
        interests_custom = str(existing.get("EMAIL_INTERESTS_CUSTOM", "")).strip()
    combined = ", ".join([part for part in [", ".join(interest_tags), interests_custom] if part])
    values["EMAIL_INTEREST_TAGS"] = interest_tags
    values["EMAIL_INTERESTS_CUSTOM"] = interests_custom
    values["EMAIL_INTERESTS"] = combined or str(
        existing.get("EMAIL_INTERESTS", "전공 탐색, 취업, 음악, 세미나")
    )
    if "hidePastEmails" in payload:
        values["EMAIL_HIDE_PAST"] = bool(payload.get("hidePastEmails"))
    # 알림 스위치 (기본은 켜짐)
    if "notifyDeadlines" in payload:
        values["NOTIFY_DEADLINES"] = bool(payload.get("notifyDeadlines"))
    if "notifyNewFiles" in payload:
        values["NOTIFY_NEW_FILES"] = bool(payload.get("notifyNewFiles"))
    else:
        values["EMAIL_HIDE_PAST"] = bool(existing.get("EMAIL_HIDE_PAST", False))

    # 명시적 삭제 요청 (저장된 비밀 값 제거)
    if payload.get("clearGeminiKey") is True:
        values["GEMINI_API_KEY"] = ""
    if payload.get("clearEmailPassword") is True:
        values["EMAIL_PASSWORD"] = ""
    if payload.get("clearSchoolEmailPassword") is True:
        values["SCHOOL_EMAIL_PASSWORD"] = ""

    save_config_dict(workspace, values)
    Path(download_path).mkdir(parents=True, exist_ok=True)
    ensure_data_files(workspace)
    return values


def save_config_dict(workspace: UserWorkspace, values: dict[str, Any]) -> None:
    """설정을 저장한다. 비밀 항목은 DPAPI로 암호화해서 넣는다."""
    to_write = dict(values)
    for key in SECRET_KEYS:
        raw = str(to_write.get(key, "") or "")
        # 이미 암호문이면 그대로 두고, 평문이면 암호화
        if raw and not raw.startswith(DPAPI_PREFIX):
            to_write[key] = dpapi_protect(raw)
    workspace.root.mkdir(parents=True, exist_ok=True)
    atomic_write_text(workspace.config_path, 
        json.dumps(to_write, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


BUNDLED_CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"


def ensure_data_files(workspace: UserWorkspace | None = None) -> None:
    workspace = workspace or workspace_for_user("local")
    workspace.root.mkdir(parents=True, exist_ok=True)
    defaults = {
        workspace.downloaded_files_log: [],
        workspace.file_metadata_log: {},
    }
    for path, value in defaults.items():
        if not path.exists():
            atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    # 배포판에 동봉된 Google OAuth 클라이언트를 첫 실행 시 데이터 폴더로 복사
    if not DRIVE_CREDENTIALS_PATH.exists() and BUNDLED_CREDENTIALS_PATH.exists():
        try:
            import shutil

            DRIVE_CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(BUNDLED_CREDENTIALS_PATH, DRIVE_CREDENTIALS_PATH)
        except OSError:
            pass


def extract_course_label(value: str) -> str:
    text = str(value or "").strip()
    if "(" in text and ")" in text:
        inside = text.split("(", 1)[1].split(")", 1)[0].strip()
        if inside:
            return inside
    if "[" in text:
        text = text.split("[", 1)[0].strip()
    return text or "기타"


def get_download_path(workspace: UserWorkspace, config: dict[str, Any] | None = None) -> Path:
    config = config if config is not None else read_config(workspace)
    return Path(str(config.get("DOWNLOAD_PATH", workspace.default_download_path)))


# 앱과 함께 넣어 두는 '데스크톱 앱' 구글 클라이언트.
#
# 왜 이건 같이 넣어도 되나
#   구글 OAuth 클라이언트에는 '웹'과 '데스크톱 앱' 두 종류가 있다.
#   웹 클라이언트의 secret 은 진짜 비밀이라 남에게 넘어가면 안 된다.
#   데스크톱 앱 클라이언트는 구글 문서에도 "설치형 앱에서는 secret 을
#   비밀로 취급하지 않는다"고 적혀 있다. 어차피 사용자 컴퓨터에 배포되는
#   파일에서 뽑아낼 수 있기 때문이고, 그래서 보안이 secret 이 아니라
#   다음 두 가지에 기대도록 설계되어 있다.
#     1) 되돌아오는 주소가 127.0.0.1 (그 컴퓨터 밖으로 안 나간다)
#     2) PKCE (매번 새로 만드는 검증값이 있어야 코드를 토큰으로 못 바꾼다)
#   gcloud CLI, rclone 같은 도구도 전부 이 방식으로 클라이언트를 넣어 배포한다.
BUNDLED_GOOGLE_CLIENT = PROJECT_ROOT / "google_client.json"


def read_google_client_config() -> tuple[str | None, dict[str, Any]]:
    # 이 컴퓨터에 따로 넣어 둔 것이 있으면 그걸 먼저 쓴다.
    # (내 계정 전용 클라이언트를 쓰고 싶은 경우)
    if not DRIVE_CREDENTIALS_PATH.exists() and BUNDLED_GOOGLE_CLIENT.exists():
        try:
            data = json.loads(BUNDLED_GOOGLE_CLIENT.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        kind = "installed" if "installed" in data else "web" if "web" in data else None
        if kind == "installed":
            return kind, data.get(kind, {})
        # 웹 클라이언트를 앱에 넣어 배포하는 것은 위험하다. 못 본 척한다.

    if not DRIVE_CREDENTIALS_PATH.exists():
        client_id = os.environ.get("AUTOSAVER_GOOGLE_CLIENT_ID", "").strip()
        client_secret = os.environ.get("AUTOSAVER_GOOGLE_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            return None, {}
        redirect_uris = [
            item.strip()
            for item in os.environ.get("AUTOSAVER_GOOGLE_REDIRECT_URIS", "").split(",")
            if item.strip()
        ]
        if PUBLIC_BASE_URL:
            callback = oauth_callback_uri(PUBLIC_BASE_URL)
            if callback not in redirect_uris:
                redirect_uris.append(callback)
        return "web", {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": redirect_uris,
        }
    data = json.loads(DRIVE_CREDENTIALS_PATH.read_text(encoding="utf-8"))
    credential_type = "installed" if "installed" in data else "web" if "web" in data else None
    return credential_type, data.get(credential_type, {}) if credential_type else {}


def save_google_credentials(payload: dict[str, Any]) -> dict[str, Any]:
    """사용자가 고른 credentials.json 내용을 이 컴퓨터에 저장한다.

    구글 클라우드 콘솔에서 받은 OAuth 클라이언트 파일을 그대로 붙여 넣으면 된다.
    앱과 함께 배포하지 않고 쓰는 사람이 각자 넣는 방식이라, 남에게 내 비밀이
    넘어가지 않는다.
    """
    raw = (payload or {}).get("json", "")
    if isinstance(raw, dict):
        data = raw
    else:
        text = str(raw).strip()
        if not text:
            raise ValueError("credentials.json 내용을 넣어 주세요.")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            raise ValueError("구글에서 받은 credentials.json 파일이 아닌 것 같아요.")

    kind = "installed" if "installed" in data else "web" if "web" in data else None
    if not kind:
        raise ValueError("구글 OAuth 클라이언트 파일이 아닙니다. (installed/web 항목이 없어요)")
    cfg = data.get(kind) or {}
    if not cfg.get("client_id") or not cfg.get("client_secret"):
        raise ValueError("client_id 또는 client_secret 이 없습니다.")

    DRIVE_CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(DRIVE_CREDENTIALS_PATH, 
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "ok": True,
        "message": "구글 로그인 준비가 끝났습니다. 이제 '구글 계정 연결'을 눌러 주세요.",
        "path": str(DRIVE_CREDENTIALS_PATH),
    }


def google_credentials_available() -> bool:
    credential_type, cfg = read_google_client_config()
    return bool(credential_type and cfg.get("client_id") and cfg.get("client_secret"))


def google_client_config_for_flow() -> dict[str, Any]:
    credential_type, cfg = read_google_client_config()
    if not credential_type or not cfg:
        raise FileNotFoundError(
            f"Google OAuth 클라이언트를 준비해 주세요. 기본 파일 위치: {DRIVE_CREDENTIALS_PATH}"
        )
    return {credential_type: cfg}


def oauth_callback_uri(base_url: str | None = None) -> str:
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL}/oauth2callback"
    if base_url:
        return f"{base_url.rstrip('/')}/oauth2callback"
    return GOOGLE_OAUTH_FALLBACK_REDIRECT_URI


def choose_google_redirect_uri(base_url: str | None = None) -> str:
    credential_type, cfg = read_google_client_config()
    redirect_uris = cfg.get("redirect_uris", [])
    callback_uri = oauth_callback_uri(base_url)
    base_root_uri = f"{base_url.rstrip('/')}/" if base_url else ""
    if PUBLIC_BASE_URL:
        return callback_uri
    if base_root_uri and base_root_uri in redirect_uris:
        return base_root_uri
    if callback_uri in redirect_uris:
        return callback_uri
    if base_url and not (
        base_url.startswith("http://127.0.0.1") or base_url.startswith("http://localhost")
    ):
        return callback_uri
    if base_url:
        return callback_uri
    local_redirects = [
        uri
        for uri in redirect_uris
        if uri.startswith("http://127.0.0.1:8765") or uri.startswith("http://localhost:8765")
    ]
    if local_redirects:
        return local_redirects[0]
    if credential_type == "installed":
        return GOOGLE_OAUTH_FALLBACK_REDIRECT_URI
    return GOOGLE_OAUTH_FALLBACK_REDIRECT_URI


def get_google_oauth_status(workspace: UserWorkspace, base_url: str | None = None) -> dict[str, Any]:
    selected_redirect_uri = (
        choose_google_redirect_uri(base_url) if google_credentials_available() else oauth_callback_uri(base_url)
    )
    status = {
        "credentialsPath": str(DRIVE_CREDENTIALS_PATH),
        "credentialsExists": google_credentials_available(),
        "credentialType": None,
        "redirectUris": [],
        "requiredRedirectUri": selected_redirect_uri,
        "redirectConfigured": False,
        "tokenPath": str(workspace.token_path),
        "tokenExists": workspace.token_path.exists(),
        "tokenValid": False,
        "tokenExpired": False,
        "hasRefreshToken": False,
        "tokenUsable": False,
        "scope": GOOGLE_OAUTH_SCOPE,
        "scopes": GOOGLE_OAUTH_SCOPES,
        "calendarGranted": False,
    }
    if google_credentials_available():
        try:
            credential_type, cfg = read_google_client_config()
            redirect_uris = cfg.get("redirect_uris", [])
            status["credentialType"] = credential_type
            status["redirectUris"] = redirect_uris
            status["redirectConfigured"] = (
                credential_type == "installed" or selected_redirect_uri in redirect_uris
            )
        except Exception as exc:
            status["credentialsError"] = str(exc)

    if not workspace.token_path.exists():
        return status
    try:
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(
            str(workspace.token_path),
            GOOGLE_OAUTH_SCOPES,
        )
        status["tokenValid"] = bool(creds.valid)
        status["tokenExpired"] = bool(creds.expired)
        status["hasRefreshToken"] = bool(creds.refresh_token)
        status["tokenUsable"] = bool(creds.valid or creds.refresh_token)
        # 캘린더 권한은 나중에 추가되었으므로 예전 토큰에는 없을 수 있다.
        # creds.scopes는 '요청한' 값을 그대로 돌려주므로 토큰 파일을 직접 읽어 확인한다.
        token_data = read_json(workspace.token_path, {})
        granted = set(token_data.get("scopes") or []) if isinstance(token_data, dict) else set()
        status["calendarGranted"] = GOOGLE_CALENDAR_SCOPE in granted
    except Exception as exc:
        status["error"] = str(exc)
    return status


def create_google_oauth_url(
    workspace: UserWorkspace,
    base_url: str | None = None,
    session_token: str | None = None,
) -> str:
    if not google_credentials_available():
        raise FileNotFoundError(
            f"Google OAuth 클라이언트를 먼저 준비해 주세요. 기본 파일 위치: {DRIVE_CREDENTIALS_PATH}"
        )

    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(
        google_client_config_for_flow(),
        scopes=GOOGLE_OAUTH_SCOPES,
        redirect_uri=choose_google_redirect_uri(base_url),
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    remember_oauth_state(workspace, state, flow.redirect_uri, flow.code_verifier, session_token)
    return auth_url


def finish_google_oauth(code: str, state: str) -> tuple[UserWorkspace, dict[str, Any]]:
    from google_auth_oauthlib.flow import Flow

    saved_state = pop_oauth_state(state) if state else None
    if not saved_state or not saved_state.get("code_verifier"):
        raise RuntimeError(
            "OAuth 세션 정보가 만료되었습니다. 대시보드로 돌아가 Google OAuth 연결을 다시 눌러 주세요."
        )

    workspace = workspace_for_user(str(saved_state.get("user_id", "local")))
    redirect_uri = saved_state.get("redirect_uri") or choose_google_redirect_uri()
    flow = Flow.from_client_config(
        google_client_config_for_flow(),
        scopes=GOOGLE_OAUTH_SCOPES,
        redirect_uri=redirect_uri,
        code_verifier=saved_state.get("code_verifier"),
        autogenerate_code_verifier=False,
    )
    flow.fetch_token(code=code)
    workspace.root.mkdir(parents=True, exist_ok=True)
    atomic_write_text(workspace.token_path, flow.credentials.to_json(), encoding="utf-8")
    return workspace, saved_state


def stored_relpath(name: str, meta: Any) -> str:
    """자료가 실제로 놓인 자리 (다운로드 폴더 기준 상대경로).

    예전에는 모든 파일을 다운로드 폴더에 그냥 쌓았다. 정리 기능을 쓰면
    '2026-2학기/일반화학II/...' 로 옮기고, 옮긴 자리를 메타데이터에 적어 둔다.
    아직 정리하지 않은 파일은 예전처럼 파일 이름 그대로다.
    """
    if isinstance(meta, dict):
        stored = str(meta.get("stored", "")).strip()
        if stored:
            return stored
    return name


def _safe_folder(text: str, limit: int = 60) -> str:
    """폴더 이름으로 쓸 수 있게 다듬는다."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(text or "")).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned or "기타")[:limit].strip(" .") or "기타"


def dedupe_downloads(workspace: UserWorkspace) -> int:
    """같은 과목·같은 파일명이 여러 벌이면 최신 것만 남긴다.

    교수가 파일을 고쳐 다시 올리면 예전 코드는 새 이름으로 하나 더 받았다.
    (앞으로는 덮어쓰지만, 이미 쌓인 중복은 여기서 걷어낸다)
    남기는 기준은 실제 파일의 수정 시각 — 가장 최근 것.
    지운 것은 로컬 사본만이고 Drive 쪽은 건드리지 않는다.
    """
    metadata = read_json(workspace.file_metadata_log, {})
    if not isinstance(metadata, dict):
        return 0

    root = get_download_path(workspace)
    groups: dict[tuple[str, str], list[str]] = {}
    for local_name, meta in metadata.items():
        if not isinstance(meta, dict):
            continue
        key = (str(meta.get("course", "")), str(meta.get("original_name", local_name)))
        groups.setdefault(key, []).append(local_name)

    removed = 0
    for key, names in groups.items():
        if len(names) < 2:
            continue

        def mtime(local_name: str) -> float:
            path = root / stored_relpath(local_name, metadata.get(local_name))
            try:
                return path.stat().st_mtime
            except OSError:
                return 0.0

        names.sort(key=mtime, reverse=True)
        for old in names[1:]:  # 첫 번째(최신)만 남긴다
            path = root / stored_relpath(old, metadata.get(old))
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                continue
            metadata.pop(old, None)
            removed += 1

    if removed:
        atomic_write_text(workspace.file_metadata_log, 
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return removed


def organize_downloads(workspace: UserWorkspace) -> dict[str, Any]:
    """받아 둔 자료를 '학기 / 과목' 폴더로 옮긴다.

    Drive 에 올라가는 모양과 같게 로컬도 정리한다.
    파일을 옮긴 뒤 메타데이터에 새 자리를 적어 둬서, 화면과 다운로드가
    그대로 파일을 찾을 수 있게 한다. 이미 제자리에 있으면 건드리지 않는다.
    """
    import course_meta

    # 폴더로 옮기기 전에 중복부터 걷어낸다 (같은 파일이 두 폴더에 갈라지지 않게)
    deduped = dedupe_downloads(workspace)

    metadata = read_json(workspace.file_metadata_log, {})
    if not isinstance(metadata, dict) or not metadata:
        return {"ok": True, "moved": 0, "skipped": 0, "message": "정리할 자료가 없습니다."}

    root = get_download_path(workspace)
    moved = skipped = missing = 0

    for name, meta in list(metadata.items()):
        if not isinstance(meta, dict):
            continue
        course = str(meta.get("course", "")) or "기타"
        display = str(meta.get("original_name", name))

        term = course_meta.parse_term(course)
        term_folder = (
            f"{term['year']}-{term['term']}학기" if term["year"] and term["term"] else "학기미상"
        )
        course_folder = _safe_folder(extract_course_label(course))
        target_dir = root / _safe_folder(term_folder, 20) / course_folder

        current = root / stored_relpath(name, meta)
        if not current.exists():
            missing += 1
            continue

        target = target_dir / _safe_folder(display, 120)
        if current.resolve() == target.resolve():
            skipped += 1
            continue

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            # 같은 이름이 이미 있으면 뒤에 번호를 붙인다
            final = target
            stem, suffix = final.stem, final.suffix
            n = 2
            while final.exists() and final.resolve() != current.resolve():
                final = target_dir / f"{stem}_{n}{suffix}"
                n += 1
            shutil.move(str(current), str(final))
            meta["stored"] = str(final.relative_to(root)).replace("\\", "/")
            moved += 1
        except OSError:
            skipped += 1

    atomic_write_text(workspace.file_metadata_log, 
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "ok": True,
        "moved": moved,
        "skipped": skipped,
        "missing": missing,
        "deduped": deduped,
        "message": (f"중복 {deduped}개 정리. " if deduped else "")
        + (f"{moved}개를 학기·과목 폴더로 옮겼습니다." if moved else "이미 정리돼 있습니다."),
    }


# ===== 삼성 노트 넣기 (뒤에서) =====
# 예전에는 요청 하나가 모든 파일을 다 넣을 때까지 붙잡고 있었다.
# 열 개면 1분 넘게 버튼이 멈춘 채였다. 이제 뒤에서 돌리고 화면은 진행만 받아 간다.
notes_job_lock = threading.Lock()
notes_job: dict[str, Any] = {
    "running": False,
    "total": 0,
    "done": 0,
    "current": "",
    "message": "",
    "startedAt": None,
    "finishedAt": None,
    "result": None,
}


def start_notes_job(items: list[tuple[Path, str]]) -> dict[str, Any]:
    """PDF 들을 삼성 노트에 넣는 일을 뒤에서 시작한다."""
    import samsung_notes

    with notes_job_lock:
        if notes_job["running"]:
            return {"ok": False, "busy": True,
                    "message": "삼성 노트에 넣는 중입니다. 끝나면 다시 눌러 주세요."}
        notes_job.update(
            running=True, total=len(items), done=0, current="", message="",
            startedAt=now_iso(), finishedAt=None, result=None,
        )

    def progress(done: int, total: int, current: str) -> None:
        with notes_job_lock:
            notes_job.update(done=done, total=total, current=current)

    def run() -> None:
        try:
            result = samsung_notes.import_pdfs(items, progress=progress)
        except Exception as exc:
            result = {"ok": False, "message": f"삼성 노트에 넣지 못했습니다: {exc}"}
        with notes_job_lock:
            notes_job.update(
                running=False, result=result, message=result.get("message", ""),
                finishedAt=now_iso(), current="",
            )

    threading.Thread(target=run, name="samsung-notes-import", daemon=True).start()
    return {"ok": True, "started": True, "total": len(items),
            "message": f"삼성 노트에 넣는 중입니다 ({len(items)}개, 이미 있는 것은 건너뜀). 창은 뜨지 않습니다."}


def get_notes_job() -> dict[str, Any]:
    with notes_job_lock:
        return dict(notes_job)


def send_pdfs_to_samsung_notes(items: list[tuple[Path, str]]) -> dict[str, Any]:
    """(기다리는 판) PDF 들을 삼성 노트에 넣고 과목 폴더로 정리한다.

    화면에서는 start_notes_job 으로 뒤에서 돌린다. 이건 스크립트용.
    실제 흐름은 samsung_notes.import_pdfs 에 있다.
    """
    import samsung_notes

    return samsung_notes.import_pdfs(items)


def _notes_mapping_and_organize(workspace: UserWorkspace) -> dict[str, Any]:
    """로컬 PDF 전부의 {파일이름줄기: 과목} 짝을 만들어 삼성 노트를 정리한다.

    이번에 보낸 것만이 아니라 전부를 넘기는 이유: 예전에 보내 놓고
    최상위에 남아 있던 노트들도 이 김에 같이 제자리로 간다.
    """
    import samsung_notes

    mapping: dict[str, str] = {}
    for row in get_files(workspace):
        if row.get("status") != "local":
            continue
        name = str(row.get("name", ""))
        if not name.lower().endswith(".pdf"):
            continue
        stem = Path(name).stem
        course = str(row.get("courseLabel") or "").strip()
        if stem and course:
            mapping[stem] = course[:60]
    return samsung_notes.organize_notes(mapping)


_level_index_cache: dict[str, Any] = {}

# 자료 목록 캐시.
# 화면이 12초마다 /api/status 와 /api/files 를 부르는데, 그때마다
# 메타데이터 290개를 읽고 파일 265개를 stat 하면 요청 하나에 0.4초가 들었다
# (status 가 안에서 get_files 를 또 부르니 실제로는 두 번).
# 근거 파일(메타데이터·숨김 목록)이 안 바뀌었으면 만들어 둔 목록을 그대로 준다.
# 돌려주는 목록은 읽기 전용으로 다뤄야 한다.
_files_cache: dict[str, Any] = {}
_FILES_CACHE_MAX_AGE = 30.0


def _file_stamp(path: Path) -> tuple[int, int]:
    """파일이 바뀌었는지 알아보는 도장 (수정 시각·크기)."""
    try:
        st = path.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


def invalidate_files_cache() -> None:
    _files_cache.clear()


def _course_level_index(workspace: UserWorkspace) -> dict[str, int]:
    """과목 이름 → 학년 색인.

    한 학기 목록만 보면 지난 학기 과목의 학년을 못 찾는다.
    배포본에 넣어 둔 씨앗(여러 학기)까지 합쳐서 만든다.
    자료 목록은 자주 불리므로 한 번 만들고 재사용한다.
    """
    if _level_index_cache.get("index") is not None:
        return _level_index_cache["index"]

    import course_meta

    index: dict[str, int] = {}
    seed = read_seed("seed_course_catalog.json").get("terms") or {}
    for entry in seed.values():
        index.update(course_meta.build_level_index(entry.get("courses") or []))

    # 씨앗에 없는 학기는 이번 학기 목록으로 보충
    try:
        for undergrad in (True, False):
            found = get_course_catalog(workspace, year_term="", undergraduate=undergrad)
            index.update(course_meta.build_level_index(found.get("courses") or []))
    except Exception:
        pass

    _level_index_cache["index"] = index
    return index


def get_files(workspace: UserWorkspace) -> list[dict[str, Any]]:
    download_path = get_download_path(workspace)
    key = (
        str(workspace.root),
        str(download_path),
        _file_stamp(workspace.file_metadata_log),
        _file_stamp(workspace.upload_selection_path),
    )
    cached = _files_cache.get("rows")
    fresh = time.monotonic() - float(_files_cache.get("at", 0.0)) < _FILES_CACHE_MAX_AGE
    if cached is not None and fresh and _files_cache.get("key") == key:
        return cached
    try:
        rows = _build_file_rows(workspace, download_path)
    except _MetadataUnreadable:
        # 파일은 있는데 읽히지 않는다 = 누가 쓰는 중. 빈 목록을 주면 화면에서 자료가
        # 통째로 사라진 것처럼 보인다. 직전 목록을 주고 캐시 도장은 갱신하지 않아 다음에 다시 읽는다.
        if cached is not None:
            return cached
        time.sleep(0.3)
        rows = _build_file_rows(workspace, download_path, allow_sample=True)
    _files_cache.update(key=key, rows=rows, at=time.monotonic())
    return rows


class _MetadataUnreadable(Exception):
    pass


def _build_file_rows(
    workspace: UserWorkspace, download_path: Path, allow_sample: bool = False
) -> list[dict[str, Any]]:
    import course_meta

    metadata = read_json(workspace.file_metadata_log, None)
    source = "metadata"
    if metadata is None and workspace.file_metadata_log.exists() and not allow_sample:
        raise _MetadataUnreadable()
    if not isinstance(metadata, dict):
        metadata = {}
    if not metadata:
        metadata = read_json(FALLBACK_COURSE_MAP, {})
        if not isinstance(metadata, dict):
            metadata = {}
        source = "sample"

    level_index = _course_level_index(workspace)
    # 목록에서 뺀 파일은 여기서 걸러낸다 (파일 자체는 그대로 있다)
    hidden_files = set(get_upload_selection(workspace).get("hiddenFiles") or [])
    # 과목 하나당 한 번만 풀이한다 (같은 과목 파일이 수십 개씩 있다)
    course_info: dict[str, tuple[dict[str, Any], str, str]] = {}
    rows: list[dict[str, Any]] = []
    for name, meta in metadata.items():
        if name in hidden_files:
            continue
        display_name = name
        if isinstance(meta, dict):
            course = str(meta.get("course", "기타"))
            folder_path = [
                str(part).strip()
                for part in (meta.get("folder_path") or [])
                if str(part).strip() and str(part).strip().lower() not in _HIDDEN_FOLDER_TITLES
            ]
            folder = " / ".join(folder_path)
            display_name = str(meta.get("original_name", name))
            raw_order = meta.get("lms_order")
            lms_order = [int(x) for x in raw_order] if isinstance(raw_order, list) and all(
                isinstance(x, int) for x in raw_order
            ) else None
        else:
            course = str(meta)
            folder = ""
            folder_path = []
            lms_order = None

        # 정리된 자료는 '학기/과목' 아래에 있다. exists()+stat() 두 번 대신 한 번만.
        try:
            stat = (download_path / stored_relpath(name, meta)).stat()
        except OSError:
            stat = None
        exists_locally = stat is not None
        extension = Path(display_name).suffix.lower().replace(".", "") or "file"

        info = course_info.get(course)
        if info is None:
            info = (
                course_meta.describe(course, level_index),
                extract_course_label(course),
                extract_semester(course),
            )
            course_info[course] = info
        meta_info, course_label, semester = info
        rows.append(
            {
                "name": display_name,
                "localName": name,
                "course": course,
                "courseLabel": course_label,
                "semester": semester,
                # 몇 학년 무슨 학기 과정인지 (화면에서 묶어 보여 준다)
                "year": meta_info["year"],
                "term": meta_info["term"],
                "termLabel": meta_info["termLabel"],
                "level": meta_info["level"],
                "levelLabel": meta_info["levelLabel"],
                "isSyllabus": course_meta.is_syllabus(display_name),
                "folder": folder or ("샘플 데이터" if source == "sample" else "강의 자료"),
                # LMS 에서 이 파일이 들어 있는 폴더 경로와 그 안에서의 순서.
                # 화면이 LMS 와 같은 폴더 나무, 같은 순서로 보여 줄 때 쓴다.
                "folderPath": folder_path,
                "lmsOrder": lms_order,
                "type": extension.upper(),
                "status": "local" if exists_locally else ("sample" if source == "sample" else "missing"),
                "size": stat.st_size if stat else None,
                # 최근 받은 자료를 보여 주려면 시각이 필요하다
                "savedAt": (
                    datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
                    if stat
                    else None
                ),
                "source": source,
            }
        )

    # 과목 안에서는 LMS 에 올라온 순서대로. 순서를 모르는 파일(예전에 받은 것)은
    # 사람이 읽는 순서로 뒤에 둔다 — '10주차' 가 '2주차' 앞에 오지 않게 숫자를 숫자로 본다.
    rows.sort(
        key=lambda item: (
            item["courseLabel"],
            0 if item["lmsOrder"] else 1,
            item["lmsOrder"] or [],
            natural_key(item["folder"]),
            natural_key(item["name"]),
        )
    )
    return rows


# LMS 가 속으로만 쓰는 이름. 예전에 받은 자료의 경로에 들어 있어도 화면에는 안 보인다.
_HIDDEN_FOLDER_TITLES = {"weekly schedule", "ultradocumentbody"}


def natural_key(text: str) -> list:
    """'2주차' < '10주차' 가 되도록 숫자는 숫자로 비교한다."""
    return [
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in re.split(r"(\d+)", str(text or ""))
        if part
    ]


def get_deadlines(workspace: UserWorkspace) -> dict[str, Any]:
    data = read_json(workspace.deadlines_log, {})
    if not isinstance(data, dict):
        data = {}
    return {
        "updatedAt": data.get("updatedAt"),
        "items": data.get("items", []) if isinstance(data.get("items"), list) else [],
        "events": data.get("events", []) if isinstance(data.get("events"), list) else [],
    }


def deadline_counts(deadlines: dict[str, Any]) -> dict[str, int]:
    now = datetime.now().astimezone()
    upcoming = 0
    overdue_unsubmitted = 0
    for item in deadlines.get("items", []):
        due_raw = item.get("due")
        if not due_raw:
            continue
        try:
            due = datetime.fromisoformat(str(due_raw).replace("Z", "+00:00")).astimezone()
        except ValueError:
            continue
        submitted = item.get("myStatus") in ("Graded", "NeedsGrading")
        if due >= now and (due - now).days < 7 and not submitted:
            upcoming += 1
        if due < now and not submitted:
            overdue_unsubmitted += 1
    return {"upcoming7d": upcoming, "overdueUnsubmitted": overdue_unsubmitted}


def build_deadlines_ics(workspace: UserWorkspace) -> str:
    """과제 마감일을 iCalendar(.ics) 텍스트로 변환."""

    def ics_escape(text: str) -> str:
        return (
            str(text or "")
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n")
        )

    deadlines = get_deadlines(workspace)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//DGIST LMS AutoSaver//KR",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:DGIST 과제 마감",
    ]
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    for item in deadlines.get("items", []):
        due_raw = item.get("due")
        if not due_raw:
            continue
        try:
            due = datetime.fromisoformat(str(due_raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        uid = f"{item.get('columnId', '')}@dgist-lms-autosaver"
        summary = f"[{item.get('courseLabel', '')}] {item.get('name', '과제')}"
        submitted = item.get("myStatus") in ("Graded", "NeedsGrading")
        description = "제출 완료" if submitted else "미제출"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{due.strftime('%Y%m%dT%H%M%SZ')}",
            f"SUMMARY:{ics_escape(summary)}",
            f"DESCRIPTION:{ics_escape(description)}",
            "BEGIN:VALARM",
            "TRIGGER:-P1D",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{ics_escape(summary)} 마감 하루 전",
            "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def get_course_state(workspace: UserWorkspace) -> dict[str, Any]:
    path = workspace.root / "courses_state.json"
    data = read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    return {
        "pending": bool(data.get("pending")),
        "added": data.get("added", []) if isinstance(data.get("added"), list) else [],
        "removed": data.get("removed", []) if isinstance(data.get("removed"), list) else [],
        "current": data.get("current", []) if isinstance(data.get("current"), list) else [],
        "updatedAt": data.get("updatedAt"),
    }


def acknowledge_courses(workspace: UserWorkspace) -> dict[str, Any]:
    path = workspace.root / "courses_state.json"
    data = read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    current = data.get("current", []) if isinstance(data.get("current"), list) else []
    new_state = {
        "acknowledged": current,
        "current": current,
        "added": [],
        "removed": [],
        "pending": False,
        "updatedAt": now_iso(),
    }
    workspace.root.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(new_state, ensure_ascii=False, indent=2), encoding="utf-8")
    return new_state


def patch_email_local(workspace: UserWorkspace, uid: int | None, folder: str,
                      unread: bool | None = None, remove: bool = False,
                      all_in_folder: bool = False) -> None:
    """IMAP 작업 후 로컬 emails.json을 즉시 반영해 UI가 새로고침 없이 갱신되게."""
    data = read_json(workspace.emails_log, {})
    if not isinstance(data, dict) or not isinstance(data.get("emails"), list):
        return
    emails = data["emails"]
    if remove and uid is not None:
        data["emails"] = [m for m in emails if not (m.get("uid") == uid and m.get("folder") == folder)]
    else:
        for m in emails:
            if m.get("folder") != folder:
                continue
            if all_in_folder or m.get("uid") == uid:
                if unread is not None:
                    m["unread"] = unread
    atomic_write_text(workspace.emails_log, json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _repair_quoted_printable(mail: dict[str, Any]) -> dict[str, Any]:
    """저장된 메일 한 건의 본문이 quoted-printable 로 남아 있으면 푼다.

    받아올 때 푸는 자리를 고쳤지만, 그 전에 받아 둔 메일은 =EC=88=98 같은
    글자가 그대로 들어 있다. 메일을 다시 받아야만 읽히는 건 불편하니
    보여 줄 때 한 번 더 걸러 준다. (파일은 그대로 두고 화면만 고친다)
    """
    html = mail.get("bodyHtml")
    if not html or not isinstance(html, str):
        return mail
    try:
        import email_reader

        raw = html.encode("utf-8", "replace")
        if email_reader._looks_quoted_printable(raw):
            fixed = email_reader.decode_body_html(raw)
            if fixed:
                mail = {**mail, "bodyHtml": fixed}
    except Exception:
        pass
    return mail


# 목록에는 없어도 되는 무거운 칸.
# 예전에는 이것까지 통째로 실어 보내서 응답이 980KB 였고, 화면이 12초마다
# 그걸 받아 다시 그리느라 눈에 띄게 버벅였다. 본문은 메일을 열 때만 받는다.
_EMAIL_BODY_FIELDS = ("body", "bodyHtml")


# 메일 목록 캐시. emails.json 은 본문까지 1MB 가까이 되는데 화면이 12초마다
# 목록을 부른다. 파일이 안 바뀌었으면 풀어 둔 목록을 그대로 준다 (읽기 전용).
_emails_cache: dict[str, Any] = {}


# ===== 관심 분야 행사 (AI 없이) =====
# 예전에는 Gemini 가 메일마다 관심도 점수와 행사 날짜를 매겨, 관심 세미나가 캘린더에 올라갔다.
# 키가 없으면 점수도 날짜도 비어 이 기능이 통째로 사라졌다. 설정의 관심사를 낱말로 풀어
# 메일 제목·보낸 곳과 맞춰 본다.
_INTEREST_WORDS: dict[str, tuple[str, ...]] = {
    "물리학": ("물리", "physics", "양자", "quantum"),
    "화학": ("화학", "chem", "phch"),
    "생명과학": ("생명", "bio", "뉴바이올로지", "new biology"),
    "뇌과학": ("뇌", "brain", "neuro"),
    "컴퓨터·AI": ("ai", "인공지능", "컴퓨터", "computer", "소프트웨어", "딥러닝", "머신러닝", "데이터"),
    "전기·전자": ("전기", "전자", "반도체", "electr"),
    "로봇·기계": ("로봇", "기계", "robot", "mechan"),
    "신소재": ("신소재", "소재", "material"),
    "에너지공학": ("에너지", "energy", "배터리", "전지"),
    "의생명공학": ("의생명", "biomedical", "의공학"),
    "뉴바이올로지": ("뉴바이올로지", "new biology", "newbiology"),
    "수학·데이터": ("수학", "math", "통계", "데이터"),
    "대학원·연구": ("대학원", "연구", "research", "랩", "lab"),
    "취업·인턴": ("취업", "채용", "인턴", "커리어", "career", "진로", "현직자"),
    "창업": ("창업", "스타트업", "startup", "비즈니스 모델"),
    "장학금": ("장학",),
    "교환학생·해외": ("교환학생", "해외", "exchange", "fglp", "global"),
    "세미나·특강": ("세미나", "특강", "seminar", "colloquium", "강연", "학습법"),
    "공모전·대회": ("공모전", "대회", "경진", "contest", "해커톤"),
    "학생회·자치": ("총학생회", "학생회", "student council"),
    "동아리": ("동아리", "club"),
    "음악·공연": ("음악", "공연", "콘서트", "concert", "영화제"),
    "운동·스포츠": ("체육", "운동", "스포츠", "sports"),
    "봉사": ("봉사", "volunteer"),
}
# 관심사와 상관없이 누구나 알 만한 학교 전체 행사
_SCHOOL_EVENT_WORDS = ("달빛제", "축제", "festival", "영화제", "체육대회", "졸업식", "입학식", "개교기념", "오픈하우스")


def _interest_words(config: dict[str, Any]) -> list[str]:
    tags = config.get("EMAIL_INTEREST_TAGS") or []
    words: list[str] = []
    for tag in tags if isinstance(tags, list) else []:
        words.extend(_INTEREST_WORDS.get(str(tag), (str(tag),)))
    # 자유 입력과 예전 방식의 관심사 문장도 낱말로 쪼개 쓴다
    free = f"{config.get('EMAIL_INTERESTS_CUSTOM', '')},{config.get('EMAIL_INTERESTS', '')}"
    for piece in re.split(r"[,/·\n]", free):
        piece = piece.strip().lower()
        if len(piece) >= 2:
            words.append(piece)
            for tag, extra in _INTEREST_WORDS.items():
                if piece in tag.lower() or tag.split("·")[0] in piece:
                    words.extend(extra)
    return sorted({w.lower() for w in words if w})


def _mark_events(emails: list[dict[str, Any]], config: dict[str, Any]) -> None:
    """메일마다 행사 날짜를 채우고, 캘린더에 올릴 만한지(calendar) 표시한다."""
    import email_reader

    words = _interest_words(config)
    for mail in emails:
        if not isinstance(mail, dict) or mail.get("folder") in ("sent", "draft", "trash", "spam"):
            continue
        if not mail.get("eventDate"):
            guessed = email_reader.guess_event_date(
                str(mail.get("subject", "")), str(mail.get("body", "")), str(mail.get("date", ""))
            )
            if guessed:
                mail["eventDate"] = guessed
                mail["eventGuessed"] = True
        if not mail.get("eventDate"):
            continue
        head = f"{mail.get('subject', '')} {mail.get('fromName', '')} {mail.get('fromEmail', '')}".lower()
        hits = [w for w in words if w in head]
        school = any(w in head for w in _SCHOOL_EVENT_WORDS)
        mail["interestHits"] = hits[:4]
        mail["schoolEvent"] = school
        # Gemini 가 매긴 점수가 있으면 그것도 인정한다
        mail["calendar"] = bool(hits or school or (mail.get("score") or 0) >= 5)

    # 같은 행사를 여러 번 알린다(미리 알림·장소 수정·당일 알림). 같은 날 같은 행사는 가장 새 메일 하나만.
    def event_key(mail: dict[str, Any]) -> tuple[str, str]:
        title = str(mail.get("subject", "")).lower()
        title = re.sub(r"^\s*(re|fw|fwd)\s*:\s*", "", title)
        title = re.sub(r"<[^>]*>|\(today\)|\[today\]|오늘", "", title)
        title = re.sub(r"[\s\W_]+", "", title)
        # 앞 28자: 같은 행사의 재공지는 제목 앞부분이 같고, 같은 학과의 다른 세미나는
        # 시각(4:30PM / 2:30PM)이나 종류가 앞쪽에서 갈린다 (실제 메일로 확인)
        return (str(mail.get("eventDate", ""))[:10], title[:28])

    def better(a: dict[str, Any], b: dict[str, Any]) -> bool:
        """a 가 b 보다 남길 만한가: 시각까지 적힌 것 먼저, 그다음 새 메일."""
        a_time, b_time = "T" in str(a.get("eventDate", "")), "T" in str(b.get("eventDate", ""))
        if a_time != b_time:
            return a_time
        return str(a.get("date", "")) > str(b.get("date", ""))

    newest: dict[tuple[str, str], dict[str, Any]] = {}
    for mail in emails:
        if not isinstance(mail, dict) or not mail.get("calendar"):
            continue
        key = event_key(mail)
        kept = newest.get(key)
        if kept is None or better(mail, kept):
            if kept is not None:
                kept["calendar"] = False
            newest[key] = mail
        else:
            mail["calendar"] = False


def get_emails(workspace: UserWorkspace) -> dict[str, Any]:
    stamp = (str(workspace.emails_log), _file_stamp(workspace.emails_log), _file_stamp(workspace.config_path))
    if _emails_cache.get("key") == stamp and _emails_cache.get("data") is not None:
        return _emails_cache["data"]

    data = read_json(workspace.emails_log, None)
    if data is None and workspace.emails_log.exists() and _emails_cache.get("data") is not None:
        # 쓰는 중이라 못 읽었다. 메일함이 텅 비어 보이지 않게 직전 목록을 준다 (도장은 그대로 두어 다음에 다시 읽음)
        return _emails_cache["data"]
    if not isinstance(data, dict):
        data = {}
    emails = data.get("emails", []) if isinstance(data.get("emails"), list) else []
    try:
        _mark_events(emails, read_config(workspace))
    except Exception as exc:
        print(f"[메일] 행사 날짜를 고르지 못했습니다: {exc}")
    listed = [
        {k: v for k, v in mail.items() if k not in _EMAIL_BODY_FIELDS}
        for mail in emails
        if isinstance(mail, dict)
    ]
    result = {
        "updatedAt": data.get("updatedAt"),
        "briefing": data.get("briefing", ""),
        "interests": data.get("interests", ""),
        "contacts": data.get("contacts", []) if isinstance(data.get("contacts"), list) else [],
        "emails": listed,
    }
    _emails_cache.update(key=stamp, data=result)
    return result


def find_mail(workspace: UserWorkspace, mail_id: str) -> dict[str, Any] | None:
    data = read_json(workspace.emails_log, {})
    emails = data.get("emails", []) if isinstance(data, dict) else []
    for mail in emails:
        if isinstance(mail, dict) and str(mail.get("id", "")) == mail_id:
            return mail
    return None


_IMAGE_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}


def mail_image_path(workspace: UserWorkspace, mail_id: str, index: int, mime: str = "") -> Path:
    """본문 그림을 받아 둘 자리. 메일 id 는 'inbox:12345' 꼴이라 ':' 를 바꾼다."""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", mail_id)
    ext = _IMAGE_EXT.get(str(mime).lower(), ".img")
    return workspace.root / "mail_images" / f"{safe}_{index}{ext}"


def ensure_mail_images(workspace: UserWorkspace, mail: dict[str, Any]) -> None:
    """본문 그림을 아직 안 받았으면 한 번만 받아 둔다."""
    images = mail.get("inlineImages") or []
    if not images:
        return
    missing = [
        (index, image)
        for index, image in enumerate(images)
        if not mail_image_path(workspace, str(mail.get("id", "")), index, image.get("type", "")).exists()
    ]
    if not missing:
        return

    import email_reader

    folder, _, raw_uid = str(mail.get("id", "")).partition(":")
    uid = int(mail.get("uid") or raw_uid or 0)
    blobs = email_reader.fetch_inline_images(uid, folder or "inbox", [image for _, image in missing])
    target_dir = workspace.root / "mail_images"
    target_dir.mkdir(parents=True, exist_ok=True)
    for index, image in missing:
        blob = blobs.get(image.get("cid", ""))
        if not blob:
            continue
        mail_image_path(workspace, str(mail.get("id", "")), index, image.get("type", "")).write_bytes(blob)


def inline_images_into_html(workspace: UserWorkspace, mail: dict[str, Any], html: str) -> str:
    """HTML 안의 cid: 주소를 앱이 서빙하는 주소로 바꾼다.

    그림을 data: 로 통째로 박으면 한 통에 1MB 가 넘어 화면이 굳는다.
    주소만 바꿔 두면 브라우저가 필요한 것만 받아 간다.
    """
    images = mail.get("inlineImages") or []
    if not images or "cid:" not in html.lower():
        return html
    try:
        ensure_mail_images(workspace, mail)
    except Exception as exc:
        print(f"[메일] 본문 그림을 받지 못했습니다: {exc}")
        return html

    mail_id = str(mail.get("id", ""))
    for index, image in enumerate(images):
        cid = str(image.get("cid", ""))
        if not cid:
            continue
        if not mail_image_path(workspace, mail_id, index, image.get("type", "")).exists():
            continue
        url = f"/api/mail-image?id={quote(mail_id)}&n={index}"
        html = re.sub(
            r"cid:" + re.escape(cid) + r"(?=[\"'\s>)])",
            url,
            html,
            flags=re.IGNORECASE,
        )
    return html


def get_email_body(workspace: UserWorkspace, mail_id: str) -> dict[str, Any]:
    """메일 한 통의 본문. 목록에서 뺀 부분을 열었을 때만 따로 준다."""
    mail = find_mail(workspace, mail_id)
    if mail is None:
        return {"ok": False, "id": mail_id, "body": "", "bodyHtml": "", "message": "메일을 찾지 못했습니다."}
    fixed = _repair_quoted_printable(mail)
    return {
        "ok": True,
        "id": mail_id,
        "body": fixed.get("body", ""),
        "bodyHtml": inline_images_into_html(workspace, mail, fixed.get("bodyHtml", "")),
        "attachments": mail.get("attachments") or [],
    }


def documents_dir() -> Path:
    """윈도우의 진짜 '문서' 폴더.

    OneDrive 를 쓰면 문서가 홈이 아니라 OneDrive 아래로 옮겨져 있다
    (이 PC 도 C:\\...\\OneDrive\\문서 다). 경로를 손으로 짜맞추지 말고
    Windows 에 물어본다.
    """
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

            # FOLDERID_Documents = {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
            guid = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                        (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            fn = ctypes.windll.shell32.SHGetKnownFolderPath
            fn.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD,
                           wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
            fn.restype = ctypes.c_long
            out = ctypes.c_wchar_p()
            if fn(ctypes.byref(guid), 0, None, ctypes.byref(out)) == 0 and out.value:
                path = Path(out.value)
                ctypes.windll.ole32.CoTaskMemFree(out)
                return path
        except Exception:
            pass
    return Path.home() / "Documents"


# ===== 내 컴퓨터에도 자동 저장 (선택 기능) =====
# Drive 처럼, 동기화로 받은 강의자료를 '내 컴퓨터에 저장' 폴더(과목별)에도 자동으로 둔다.
#   off     : 끔 (기본)
#   current : 이번 학기 과목만
#   all     : 받아 둔 모든 과목
# 수동 '내 컴퓨터에 저장' 과 같은 자리(<저장 폴더>\<과목>\<파일>)에 두므로 두 벌이 생기지 않는다.
LOCAL_AUTOSAVE_MODES = ("off", "current", "all")
local_save_lock = threading.Lock()
local_save_job: dict[str, Any] = {"running": False, "result": None, "finishedAt": None}


def _long_path(path: Path) -> str:
    """Windows 의 260자 경로 제한을 넘는 경로도 다루게 한다.

    LMS 파일 이름은 180자까지 길어질 수 있어서, 저장 폴더·과목 폴더와 합치면
    260자를 넘기 쉽다(실제로 복사가 '경로를 찾을 수 없음' 으로 실패했다).
    경로 앞에 확장 경로 표시(물음표가 든 네 글자 접두어)를 붙이면 이 제한을 받지 않는다.
    """
    prefix = "\\\\?\\"  # 실제 값: \\?\
    text = str(Path(path).resolve())
    if os.name != "nt" or text.startswith(prefix) or len(text) < 240:
        return text
    if text.startswith("\\\\"):  # 네트워크 경로 \\server\share
        return prefix + "UNC\\" + text[2:]
    return prefix + text


def local_autosave_mode(config: dict[str, Any]) -> str:
    mode = str(config.get("AUTO_LOCAL_SAVE", "off") or "off").strip().lower()
    return mode if mode in LOCAL_AUTOSAVE_MODES else "off"


# ===== 클라우드 폴더에도 자동 저장 =====
# 클라우드마다 계정 로그인(API)을 붙이지 않고, PC용 동기화 프로그램이 지켜보는 폴더에 넣는다.
# 그러면 로그인·앱 등록·토큰이 필요 없고, 그 프로그램이 알아서 올린다.
# 폴더 안에 '붕어빵 강의자료\<과목>\<파일>' 로 둔다.
CLOUD_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("onedrive", "OneDrive"),
    ("dropbox", "Dropbox"),
    ("icloud", "iCloud Drive"),
    ("mybox", "네이버 MYBOX"),
)
CLOUD_FOLDER_NAME = "붕어빵 강의자료"


def _first_dir(candidates: list[Any]) -> Path | None:
    for c in candidates:
        if not c:
            continue
        try:
            path = Path(str(c)).expanduser()
            if path.is_dir():
                return path
        except OSError:
            continue
    return None


def detect_cloud_roots() -> dict[str, Path | None]:
    """이 PC 에 깔린 클라우드 동기화 폴더를 찾는다. 없으면 None."""
    home = Path.home()
    env = os.environ
    # OneDrive: 프로그램이 로그인할 때 환경변수에 폴더를 적어 둔다 (개인 / 학교·회사)
    onedrive = _first_dir([env.get("OneDrive"), env.get("OneDriveConsumer"), env.get("OneDriveCommercial"), home / "OneDrive"])
    # Dropbox: 설치 프로그램이 info.json 에 동기화 폴더를 적는다 (개인이 먼저)
    dropbox_paths: list[Any] = []
    for base in (env.get("APPDATA"), env.get("LOCALAPPDATA")):
        if not base:
            continue
        info = read_json(Path(base) / "Dropbox" / "info.json", {})
        if isinstance(info, dict):
            for kind in ("personal", "business"):
                entry = info.get(kind)
                if isinstance(entry, dict):
                    dropbox_paths.append(entry.get("path"))
    dropbox = _first_dir(dropbox_paths + [home / "Dropbox"])
    # iCloud for Windows 기본 폴더
    icloud = _first_dir([home / "iCloudDrive", home / "iCloud Drive"])
    # 네이버 MYBOX PC 앱: 흔한 이름만 본다(실제 설치본에서 확인하지 못했다). 못 찾으면 사용자가 고른다.
    mybox = _first_dir([home / "MYBOX", home / "네이버 MYBOX", home / "NAVER MYBOX", home / "Naver MYBOX"])
    return {"onedrive": onedrive, "dropbox": dropbox, "icloud": icloud, "mybox": mybox}


def cloud_save_settings(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """설정의 CLOUD_SAVE 를 {key: {on, path}} 로 고른다 (모르는 키·잘못된 값은 버림)."""
    raw = config.get("CLOUD_SAVE")
    raw = raw if isinstance(raw, dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for key, _label in CLOUD_PROVIDERS:
        item = raw.get(key) if isinstance(raw.get(key), dict) else {}
        out[key] = {"on": bool(item.get("on")), "path": str(item.get("path") or "").strip()}
    return out


def cloud_targets(config: dict[str, Any]) -> list[dict[str, Any]]:
    """클라우드 카드 목록: 찾았는지, 켰는지, 어디에 넣는지."""
    found = detect_cloud_roots()
    saved = cloud_save_settings(config)
    rows = []
    for key, label in CLOUD_PROVIDERS:
        chosen = saved[key]["path"]
        root = Path(chosen) if chosen and Path(chosen).is_dir() else found.get(key)
        rows.append({
            "key": key,
            "label": label,
            "installed": root is not None,
            "picked": bool(chosen),
            "root": str(root) if root else "",
            "folder": str(root / CLOUD_FOLDER_NAME) if root else "",
            "on": bool(saved[key]["on"] and root is not None),
        })
    return rows


def save_scope(config: dict[str, Any]) -> str:
    """내 컴퓨터·클라우드 폴더에 넣을 과목 범위 (current / all)."""
    mode = local_autosave_mode(config)
    if mode in ("current", "all"):
        return mode
    scope = str(config.get("SAVE_SCOPE", "current") or "current").strip().lower()
    return scope if scope in ("current", "all") else "current"


def autosave_local(workspace: UserWorkspace, mode: str | None = None) -> dict[str, Any]:
    """받아 둔 강의자료를 켜 둔 저장 위치(내 컴퓨터 폴더 + 클라우드 폴더)에 맞춰 둔다.
    여러 번 불러도 같은 결과.

    이미 있는 파일을 다룰 때 사용자가 손댄 것은 절대 덮어쓰지 않는다.
      - 내용(크기·수정 시각)이 원본과 같으면 건너뜀
      - 우리가 복사한 뒤로 아무도 안 건드렸는데 LMS 쪽이 바뀌었으면 새 것으로 바꿈
      - 사용자가 필기 등으로 고친 파일이면 그대로 두고 새 버전을 옆에 따로 둠
    '우리가 복사한 그대로인지' 는 local_autosave.json 에 적어 둔 크기·수정 시각으로 판단한다.
    (기록은 전체 경로로 적으므로 저장 위치가 여러 곳이어도 한 파일로 된다)
    """
    config = read_config(workspace)
    local_mode = local_autosave_mode(config)
    scope = mode if mode in ("current", "all") else save_scope(config)

    targets: list[tuple[str, Path]] = []
    if local_mode != "off":
        targets.append(("내 컴퓨터", get_local_save_dir(workspace)))
    for cloud in cloud_targets(config):
        if cloud["on"]:
            targets.append((cloud["label"], Path(cloud["folder"])))
    # 같은 폴더를 두 번 채우지 않는다 (예: 저장 폴더를 클라우드 폴더로 골랐을 때)
    unique: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for label, root in targets:
        key = os.path.normcase(str(root))
        if key not in seen:
            seen.add(key)
            unique.append((label, root))
    targets = unique
    if not targets:
        return {"ok": True, "skipped": True, "saved": 0, "updated": 0, "message": "자동 저장할 곳이 꺼져 있습니다."}

    rows = [row for row in get_files(workspace) if row.get("status") == "local"]
    if scope == "current":
        terms = [(row.get("year") or 0, row.get("term") or 0) for row in rows if row.get("year")]
        latest = max(terms) if terms else None
        rows = [row for row in rows if latest and (row.get("year") or 0, row.get("term") or 0) == latest]

    record_path = workspace.root / "local_autosave.json"
    record = read_json(record_path, {})
    copies: dict[str, dict[str, Any]] = record.get("files", {}) if isinstance(record, dict) else {}

    totals = {"saved": 0, "updated": 0, "kept": 0, "unchanged": 0, "failed": 0, "moved": 0}
    per_target = []
    for label, root in targets:
        counts = _mirror_rows(workspace, config, rows, root, copies)
        for k in totals:
            totals[k] += counts[k]
        per_target.append({"label": label, "folder": str(root), **counts})

    try:
        atomic_write_text(record_path,
            json.dumps({"files": copies, "updatedAt": now_iso()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass

    lines = []
    for item in per_target:
        parts = []
        if item["saved"]:
            parts.append(f"새 자료 {item['saved']}개")
        if item["updated"]:
            parts.append(f"바뀐 자료 {item['updated']}개")
        if item["kept"]:
            parts.append(f"새 버전 {item['kept']}개")
        if item["moved"]:
            parts.append(f"LMS 폴더대로 옮김 {item['moved']}개")
        if item["failed"]:
            parts.append(f"실패 {item['failed']}개")
        if parts:
            lines.append(f"{item['label']}: {', '.join(parts)}")
    message = ("저장했습니다 — " + " · ".join(lines) + ".") if lines else "저장 위치가 모두 최신입니다."
    if totals["kept"]:
        message += " (내가 고친 파일은 그대로 두고 옆에 새 버전을 두었습니다)"
    return {"ok": True, "mode": scope, "targets": per_target, **totals, "message": message}


def lms_subfolders(folder_path: Any) -> list[str]:
    """LMS 폴더 경로(['1주차', 'Lecture 1'])를 폴더 이름으로 쓸 수 있게.

    자료 화면·Drive 와 같은 구조로 두려고 쓴다. 'Weekly Schedule' 처럼 화면에서 감추는
    틀 폴더는 뺀다. 이름마다 40자로 잘라 경로가 너무 길어지지 않게 한다.
    """
    parts = []
    for part in folder_path or []:
        text = str(part).strip()
        if text and text.lower() not in _HIDDEN_FOLDER_TITLES:
            parts.append(_safe_folder(text, 40))
    return parts


def _mirror_rows(
    workspace: UserWorkspace,
    config: dict[str, Any],
    rows: list[dict[str, Any]],
    target_root: Path,
    copies: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """자료 줄들을 target_root / 과목 / LMS 하위 폴더 / 파일 로 복사한다. copies 기록을 고쳐 가며.

    예전(1.11.3까지)에는 하위 폴더 없이 과목 폴더에 바로 펼쳐 넣었다. 그 자리에 있는
    '우리가 넣은 그대로' 인 사본은 새 자리로 옮긴다(다시 복사하지 않는다).
    사용자가 고친 옛 사본은 그대로 두고, 새 자리에 또 만들지 않는다.
    """
    import shutil

    download_path = get_download_path(workspace, config).resolve()
    metadata = read_json(workspace.file_metadata_log, {})
    if not isinstance(metadata, dict):
        metadata = {}
    enabled = get_upload_selection(workspace).get("courses") or {}

    saved = updated = kept = skipped = failed = moved = 0
    for row in rows:
        label = str(row.get("courseLabel") or "기타")
        # Drive 업로드와 같은 과목 선택을 따른다 (강의 화면에서 뺀 과목은 저장하지 않음)
        if not enabled.get(label, True):
            skipped += 1
            continue
        local_name = str(row.get("localName", ""))
        meta = metadata.get(local_name, {})
        source = (download_path / stored_relpath(local_name, meta)).resolve()
        if not str(source).startswith(str(download_path)) or not source.is_file():
            failed += 1
            continue
        course_dir = target_root / _safe_folder(label)
        file_name = str(row.get("name") or source.name)
        parts = lms_subfolders(row.get("folderPath"))
        dest_dir = course_dir.joinpath(*parts)
        dest = dest_dir / file_name
        try:
            # 예전에 과목 폴더에 바로 넣었던 사본을 제자리(하위 폴더)로
            flat = course_dir / file_name
            if parts and not os.path.exists(_long_path(dest)) and os.path.exists(_long_path(flat)):
                old = copies.get(str(flat))
                flat_stat = os.stat(_long_path(flat))
                if old and old.get("source") == local_name:
                    if old.get("size") == flat_stat.st_size and old.get("mtime") == flat_stat.st_mtime_ns:
                        os.makedirs(_long_path(dest_dir), exist_ok=True)
                        os.replace(_long_path(flat), _long_path(dest))
                        copies.pop(str(flat), None)
                        copies[str(dest)] = dict(old)
                        moved += 1
                    else:
                        skipped += 1
                        continue
            src_stat = os.stat(_long_path(source))
            if os.path.exists(_long_path(dest)):
                dst_stat = os.stat(_long_path(dest))
                if dst_stat.st_size == src_stat.st_size:
                    skipped += 1
                    copies.setdefault(str(dest), {"source": local_name, "size": dst_stat.st_size, "mtime": dst_stat.st_mtime_ns})
                    continue
                mine = copies.get(str(dest))
                untouched = bool(
                    mine
                    and mine.get("source") == local_name
                    and mine.get("size") == dst_stat.st_size
                    and mine.get("mtime") == dst_stat.st_mtime_ns
                )
                if untouched:
                    shutil.copy2(_long_path(source), _long_path(dest))
                    updated += 1
                else:
                    # 사용자가 고친 파일이거나 이름만 같은 다른 자료다. 옆에 따로 둔다.
                    dest = dest.with_name(f"{dest.stem} (LMS 새 버전){dest.suffix}")
                    if os.path.exists(_long_path(dest)) and os.stat(_long_path(dest)).st_size == src_stat.st_size:
                        skipped += 1
                        continue
                    shutil.copy2(_long_path(source), _long_path(dest))
                    kept += 1
            else:
                os.makedirs(_long_path(dest_dir), exist_ok=True)
                shutil.copy2(_long_path(source), _long_path(dest))
                saved += 1
            final = os.stat(_long_path(dest))
            copies[str(dest)] = {"source": local_name, "size": final.st_size, "mtime": final.st_mtime_ns}
        except OSError:
            failed += 1
    # 옮기고 나서 빈 채로 남은 폴더는 없다(과목 폴더는 파일이 옮겨 가도 하위 폴더를 품는다)
    return {"saved": saved, "updated": updated, "kept": kept, "unchanged": skipped, "failed": failed, "moved": moved}


def start_local_save_job(workspace: UserWorkspace, mode: str | None = None) -> dict[str, Any]:
    """처음 켰을 때처럼 한꺼번에 복사할 일이 많으면 뒤에서 돌린다."""
    with local_save_lock:
        if local_save_job["running"]:
            return {"ok": False, "busy": True, "message": "저장 위치를 맞추는 중입니다."}
        local_save_job.update(running=True, result=None, finishedAt=None)

    def run() -> None:
        try:
            result = autosave_local(workspace, mode)
        except Exception as exc:
            result = {"ok": False, "message": f"저장하지 못했습니다: {exc}"}
        with local_save_lock:
            local_save_job.update(running=False, result=result, finishedAt=now_iso())

    threading.Thread(target=run, name="local-autosave", daemon=True).start()
    return {"ok": True, "started": True, "message": "저장 위치를 맞추는 중입니다."}


def get_local_save_job() -> dict[str, Any]:
    with local_save_lock:
        return dict(local_save_job)


def get_local_save_dir(workspace: UserWorkspace) -> Path:
    """'내 컴퓨터에 저장' 의 뿌리 폴더.

    설정(LOCAL_SAVE_PATH)이 있으면 그곳, 없으면 문서\\붕어빵 파일 정리.
    실제 저장은 이 아래 과목별 폴더로 갈라진다.
    """
    config = read_config(workspace)
    custom = str(config.get("LOCAL_SAVE_PATH", "")).strip()
    if custom:
        try:
            path = Path(custom)
            path.mkdir(parents=True, exist_ok=True)
            return path
        except OSError:
            pass
    return documents_dir() / "붕어빵 파일 정리"


SECRET_KEYS = (
    "LMS_PASSWORD",
    "EMAIL_PASSWORD",
    "SCHOOL_EMAIL_PASSWORD",
    "GEMINI_API_KEY",
    # 공공데이터포털 인증키 (개설강좌·학사일정·세미나 조회)
    "DGIST_API_KEY",
)
DPAPI_PREFIX = "dpapi:"


def dpapi_protect(text: str) -> str:
    """Windows DPAPI로 문자열을 암호화한다 (현재 사용자 계정에서만 복호 가능).

    실패하거나 Windows가 아니면 원문을 그대로 돌려준다 — 저장은 되어야 하므로.
    """
    if os.name != "nt" or not text:
        return text
    try:
        import base64
        import ctypes
        from ctypes import wintypes

        class BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        raw = text.encode("utf-8")
        blob_in = BLOB(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)))
        blob_out = BLOB()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        )
        if not ok:
            return text
        data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return DPAPI_PREFIX + base64.b64encode(data).decode("ascii")
    except Exception:
        return text


def dpapi_unprotect(text: str) -> str:
    """dpapi: 로 시작하면 복호화, 아니면 그대로 (평문 호환)."""
    if not isinstance(text, str) or not text.startswith(DPAPI_PREFIX):
        return text
    if os.name != "nt":
        return ""
    try:
        import base64
        import ctypes
        from ctypes import wintypes

        class BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        raw = base64.b64decode(text[len(DPAPI_PREFIX) :])
        blob_in = BLOB(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)))
        blob_out = BLOB()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        )
        if not ok:
            return ""
        data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return data.decode("utf-8")
    except Exception:
        return ""


def export_settings(workspace: UserWorkspace, include_secrets: bool = False) -> dict[str, Any]:
    """설정·과목 선택·내 일정을 한 덩어리로 내보낸다."""
    config = dict(read_config(workspace))
    if include_secrets:
        # 다른 PC에서도 열 수 있도록 평문으로 되돌려 담는다
        for key in SECRET_KEYS:
            if key in config:
                config[key] = dpapi_unprotect(str(config[key]))
    else:
        for key in SECRET_KEYS:
            config.pop(key, None)
    return {
        "app": "붕어빵",
        "version": (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        if (PROJECT_ROOT / "VERSION").exists()
        else "",
        "exportedAt": now_iso(),
        "includesSecrets": include_secrets,
        "config": config,
        "selection": get_upload_selection(workspace),
        "myEvents": get_my_events(workspace)["events"],
    }


def import_settings(workspace: UserWorkspace, payload: dict[str, Any]) -> dict[str, Any]:
    """내보낸 백업을 되돌린다. 빠진 항목은 기존 값을 유지한다."""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict) or "config" not in data:
        raise ValueError("붕어빵에서 내보낸 백업 파일이 아닙니다.")

    restored = []
    incoming = data.get("config")
    if isinstance(incoming, dict):
        current = dict(read_config(workspace))
        for key, value in incoming.items():
            # 비밀 항목은 값이 있을 때만 덮어쓴다 (빈 값으로 지워지는 사고 방지)
            if key in SECRET_KEYS:
                if str(value).strip():
                    current[key] = str(value)
            else:
                current[key] = value
        save_config_dict(workspace, current)  # 저장 시 자동 암호화
        restored.append("설정")

    selection = data.get("selection")
    if isinstance(selection, dict) and selection.get("courses") is not None:
        save_upload_selection(workspace, selection)
        restored.append("과목 선택")

    events = data.get("myEvents")
    if isinstance(events, list):
        workspace.root.mkdir(parents=True, exist_ok=True)
        atomic_write_text(workspace.my_events_path, 
            json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        restored.append(f"내 일정 {len(events)}건")

    if not restored:
        raise ValueError("복원할 내용이 없습니다.")
    return {"ok": True, "restored": restored, "message": f"{', '.join(restored)}을(를) 복원했습니다."}


def get_health(workspace: UserWorkspace) -> dict[str, Any]:
    """마지막 성공 시각과 최근 실패를 알려 준다 (조용한 실패 방지)."""
    data = read_json(workspace.health_path, {})
    if not isinstance(data, dict):
        data = {}
    out = {
        "lastSuccess": data.get("lastSuccess", {}),
        "lastFailure": data.get("lastFailure", {}),
        "consecutiveFailures": int(data.get("consecutiveFailures", 0) or 0),
        "staleDays": None,
        "stale": False,
        "warning": "",
    }
    # 매일 한 번 '꼼꼼히' 가 마지막으로 끝난 때 (사이드바 상태판에 보여 준다)
    full = read_json(workspace.root / "last_full_sync.json", {}) or {}
    out["lastFullSync"] = full.get("lastFullSync") if isinstance(full, dict) else None
    out["authFailed"] = data.get("authFailed") or {}
    out["failStreak"] = data.get("failStreak") or {}
    # 동기화/메일 중 가장 최근 성공을 기준으로 며칠 지났는지 계산
    stamps = [v for v in out["lastSuccess"].values() if v]
    if stamps:
        try:
            newest = max(datetime.fromisoformat(str(s)) for s in stamps)
            days = (datetime.now() - newest).days
            out["staleDays"] = days
            out["stale"] = days >= 3
        except ValueError:
            pass
    auth = data.get("authFailed") or {}
    if auth:
        names = {"emails": "학교 메일", "sync": "LMS", "deadlines": "LMS"}
        who = " · ".join(sorted({names.get(k, k) for k in auth}))
        out["authPaused"] = sorted(auth)
        out["warning"] = f"{who} 로그인이 거절되어 자동 확인을 멈췄어요. 설정에서 비밀번호를 확인해 주세요."
    elif out["consecutiveFailures"] >= 2:
        kind = out["lastFailure"].get("kind", "작업")
        out["warning"] = f"{kind}이(가) {out['consecutiveFailures']}번 연속 실패했습니다. 설정에서 계정 정보를 확인해 주세요."
    elif out["stale"]:
        out["warning"] = f"{out['staleDays']}일째 동기화가 되지 않았습니다."
    return out


def record_task_result(
    workspace: UserWorkspace, kind: str, return_code: int, auth_failed: bool = False
) -> dict[str, Any]:
    """작업 성공/실패를 기록한다. 실패가 쌓이면 사용자에게 알리기 위함.

    failStreak: 작업 종류별 연속 실패 수 (자동 재시도 간격을 늘리는 데 쓴다).
    authFailed: 서버가 로그인을 거절한 때와 그때의 설정 파일 도장. 설정이 바뀌기 전에는
    자동으로 다시 두드리지 않는다. 2026-09-24~25 에 학교 메일 로그인이 거절된 채
    5분마다 다시 시도해 하루 수백 번 실패 로그인을 보냈다(계정 잠김 위험).
    """
    data = read_json(workspace.health_path, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("lastSuccess", {})
    streaks = data.setdefault("failStreak", {})
    auth = data.setdefault("authFailed", {})
    stamp = now_iso()
    if return_code == 0:
        data["lastSuccess"][kind] = stamp
        data["consecutiveFailures"] = 0
        data.pop("lastFailure", None)
        streaks.pop(kind, None)
        auth.pop(kind, None)
    else:
        data["consecutiveFailures"] = int(data.get("consecutiveFailures", 0) or 0) + 1
        data["lastFailure"] = {"kind": kind, "at": stamp, "code": return_code}
        streaks[kind] = int(streaks.get(kind, 0) or 0) + 1
        if auth_failed:
            auth[kind] = {"at": stamp, "configStamp": list(_file_stamp(workspace.config_path))}
    try:
        workspace.root.mkdir(parents=True, exist_ok=True)
        atomic_write_text(workspace.health_path, 
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass
    return data


SEMESTER_RE = re.compile(r"\[\s*(\d{4})[_\s-]*(\d)\s*학기")


def extract_semester(course: str) -> str:
    """'일반화학Ⅰ (...)_03[ 2026_1학기 ]' → '2026-1학기'. 못 찾으면 '기타'."""
    m = SEMESTER_RE.search(str(course or ""))
    return f"{m.group(1)}-{m.group(2)}학기" if m else "기타"


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num) < 1024 or unit == "GB":
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024
    return f"{num:.1f} GB"


def get_storage(workspace: UserWorkspace) -> dict[str, Any]:
    """다운로드 폴더 용량과 디스크 여유 공간, 학기·과목별 사용량."""
    config = read_config(workspace)
    download_dir = Path(config.get("DOWNLOAD_PATH", str(workspace.default_download_path)))
    metadata = read_json(workspace.file_metadata_log, {})
    if not isinstance(metadata, dict):
        metadata = {}

    per_semester: dict[str, dict[str, Any]] = {}
    per_course: dict[str, dict[str, Any]] = {}
    total = 0
    file_count = 0
    unknown = {"bytes": 0, "count": 0}

    if download_dir.exists():
        for entry in download_dir.rglob("*"):
            if not entry.is_file():
                continue
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            total += size
            file_count += 1
            meta = metadata.get(entry.name)
            if not meta:
                unknown["bytes"] += size
                unknown["count"] += 1
                continue
            course = str(meta.get("course", ""))
            label = extract_course_label(course)
            sem = extract_semester(course)
            s = per_semester.setdefault(sem, {"bytes": 0, "count": 0, "courses": set()})
            s["bytes"] += size
            s["count"] += 1
            s["courses"].add(label)
            c = per_course.setdefault(label, {"bytes": 0, "count": 0, "semester": sem})
            c["bytes"] += size
            c["count"] += 1

    try:
        usage = shutil.disk_usage(str(download_dir if download_dir.exists() else workspace.root))
        disk = {
            "totalBytes": usage.total,
            "freeBytes": usage.free,
            "usedPercent": round((usage.total - usage.free) / usage.total * 100, 1),
            "freeHuman": human_size(usage.free),
            "totalHuman": human_size(usage.total),
            # 5GB 미만이면 경고
            "low": usage.free < 5 * 1024**3,
        }
    except Exception:
        disk = {}

    app_bytes = total - unknown["bytes"]
    # 다운로드 경로가 개인 폴더(Downloads/문서/바탕화면 등)로 잡혀 있으면 알려 준다
    # 앱 전용 폴더(C:\lms-autosaver\downloads)도 이름이 'downloads' 라 예전에는 잘못 경고했다.
    # 사용자 폴더 아래에 있는 진짜 개인 폴더일 때만 알린다.
    personal_dirs = {"downloads", "documents", "desktop", "다운로드", "문서", "바탕화면"}
    try:
        under_home = Path.home().resolve() in download_dir.resolve().parents
    except OSError:
        under_home = False
    shared_folder = download_dir.name.lower() in personal_dirs and under_home

    return {
        "downloadPath": str(download_dir),
        "sharedFolder": shared_folder,
        "totalBytes": total,
        "totalHuman": human_size(total),
        "appBytes": app_bytes,
        "appHuman": human_size(app_bytes),
        "appFileCount": file_count - unknown["count"],
        "fileCount": file_count,
        "disk": disk,
        "semesters": sorted(
            (
                {
                    "name": name,
                    "bytes": v["bytes"],
                    "human": human_size(v["bytes"]),
                    "count": v["count"],
                    "courseCount": len(v["courses"]),
                }
                for name, v in per_semester.items()
            ),
            key=lambda x: x["name"],
            reverse=True,
        ),
        "courses": sorted(
            (
                {
                    "name": name,
                    "bytes": v["bytes"],
                    "human": human_size(v["bytes"]),
                    "count": v["count"],
                    "semester": v["semester"],
                }
                for name, v in per_course.items()
            ),
            key=lambda x: x["bytes"],
            reverse=True,
        ),
        # 앱이 받지 않은 파일 = 사용자 개인 파일. 표시만 하고 절대 지우지 않는다.
        "unknown": {**unknown, "human": human_size(unknown["bytes"])},
        # 설정 화면에서 '앱이 차지하는 크기' 와 '강의자료 크기' 를 따로 보여 주려고 나눴다.
        "app": app_footprint(workspace, download_dir),
        "localSave": local_save_footprint(workspace, config),
        "cloudSave": cloud_save_footprint(config),
    }


def pick_folder_dialog() -> str:
    """운영체제 기본 '폴더 선택' 창을 띄워 고른 경로를 돌려준다 (취소하면 빈 문자열).

    예전에는 tkinter 를 썼는데, 설치 파일(bungeoppang.spec)이 크기를 줄이려고 tkinter 를 빼서
    설치형 앱에서는 '폴더 바꾸기'·'폴더 고르기' 가 늘 실패했다. 맥에서는 tkinter 창을
    서버 스레드에서 열 수도 없다. 앱 창(pywebview)이 가진 폴더 창을 쓴다.
    개발 서버처럼 앱 창이 없을 때만 tkinter 로 대신한다.
    """
    try:
        import webview

        if webview.windows:
            result = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
            if not result:
                return ""
            return str(result[0] if isinstance(result, (list, tuple)) else result)
    except ImportError:
        pass
    import tkinter
    from tkinter import filedialog

    root_widget = tkinter.Tk()
    root_widget.withdraw()
    root_widget.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(title="저장 폴더 선택") or ""
    finally:
        root_widget.destroy()


def drive_root_folder_name() -> str:
    """드라이브에 만드는 맨 위 폴더 이름 (drive_uploader.ROOT_FOLDER)."""
    global _DRIVE_ROOT_NAME
    if _DRIVE_ROOT_NAME is None:
        try:
            from drive_uploader import ROOT_FOLDER

            _DRIVE_ROOT_NAME = str(ROOT_FOLDER)
        except Exception:
            _DRIVE_ROOT_NAME = "AutoSaver"
    return _DRIVE_ROOT_NAME


_DRIVE_ROOT_NAME: str | None = None


def _dir_size(path: Path, skip: Path | None = None) -> tuple[int, int]:
    """폴더 전체 크기와 파일 수. skip 아래는 세지 않는다 (재귀 대신 스택으로)."""
    total = count = 0
    skip_text = os.path.normcase(str(skip)) if skip else ""
    stack = [str(path)]
    while stack:
        current = stack.pop()
        if skip_text and os.path.normcase(current) == skip_text:
            continue
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                            count += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return total, count


# 프로그램·브라우저 폴더는 거의 안 바뀌는데 파일이 수천 개다(브라우저만 700MB).
# 설정 화면을 열 때마다 훑지 않게 10분 동안 기억한다.
_FOOTPRINT_CACHE: dict[str, tuple[float, int]] = {}


def _cached_dir_size(key: str, path: Path) -> int:
    hit = _FOOTPRINT_CACHE.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    size = _dir_size(path)[0] if path.exists() else 0
    _FOOTPRINT_CACHE[key] = (time.time(), size)
    return size


def app_footprint(workspace: UserWorkspace, download_dir: Path) -> dict[str, Any]:
    """강의자료를 뺀 앱 자체의 크기: 프로그램 + LMS 접속용 브라우저 + 앱 데이터(메일·설정)."""
    parts = []
    if getattr(sys, "frozen", False):
        program = Path(sys.executable).resolve().parent
        parts.append({"key": "program", "label": "프로그램", "bytes": _cached_dir_size("program", program)})
    try:
        from browser_setup import browsers_root

        browser = browsers_root()
    except Exception:
        browser = None
    if browser is not None and browser.exists():
        # 앱은 화면 없는 크로미움(chromium_headless_shell)만 쓴다 (browser_setup 이 --only-shell 로 받음).
        # 같은 폴더에 개발용으로 받은 일반 크로미움(430MB)이 있을 수 있는데 앱 몫이 아니라 세지 않는다.
        shell_bytes = sum(
            _cached_dir_size(f"browser:{d.name}", d)
            for d in browser.iterdir()
            if d.is_dir() and d.name.lower().startswith("chromium_headless_shell-")
        )
        if shell_bytes:
            parts.append({"key": "browser", "label": "LMS 로그인용 브라우저", "bytes": shell_bytes})
    # 데이터 폴더 안에 강의자료 폴더가 들어 있으니 그것만 빼고 센다
    data_bytes = _dir_size(workspace.root, skip=download_dir)[0] if workspace.root.exists() else 0
    parts.append({"key": "data", "label": "메일·설정 데이터", "bytes": data_bytes})
    for p in parts:
        p["human"] = human_size(p["bytes"])
    total = sum(p["bytes"] for p in parts)
    return {"bytes": total, "human": human_size(total), "parts": parts}


def cloud_save_footprint(config: dict[str, Any]) -> dict[str, Any]:
    """켜 둔 클라우드 폴더(붕어빵 강의자료)가 이 PC 에서 차지하는 크기."""
    parts = []
    for cloud in cloud_targets(config):
        if not cloud["on"]:
            continue
        folder = Path(cloud["folder"])
        size, count = _dir_size(folder) if folder.exists() else (0, 0)
        parts.append({"label": cloud["label"], "bytes": size, "count": count, "human": human_size(size)})
    total = sum(item["bytes"] for item in parts)
    return {"bytes": total, "human": human_size(total), "count": sum(item["count"] for item in parts), "parts": parts}


def local_save_footprint(workspace: UserWorkspace, config: dict[str, Any]) -> dict[str, Any]:
    """내 컴퓨터 저장 폴더가 차지하는 크기. 꺼져 있으면 폴더만 알려 준다."""
    folder = get_local_save_dir(workspace)
    enabled = local_autosave_mode(config) != "off"
    size = count = 0
    if enabled and folder.exists():
        size, count = _dir_size(folder)
    return {
        "enabled": enabled,
        "path": str(folder),
        "bytes": size,
        "count": count,
        "human": human_size(size),
    }


def cleanup_storage(workspace: UserWorkspace, payload: dict[str, Any]) -> dict[str, Any]:
    """학기 또는 과목 단위로 '앱이 내려받은' 파일만 지운다.

    안전장치:
    - file_metadata.json에 기록된 파일(= 앱이 직접 받은 것)만 대상으로 한다.
      다운로드 경로가 사용자의 개인 Downloads 폴더로 잡혀 있는 경우가 있어,
      기록에 없는 파일은 어떤 경우에도 건드리지 않는다.
    - 대상이 명시되지 않으면 아무것도 지우지 않는다.
    지운 파일은 downloaded_files.json에서도 빼서 다음 동기화 때 다시 받을 수 있게 한다.
    """
    semesters = {str(s) for s in payload.get("semesters", []) if str(s).strip()}
    courses = {str(c) for c in payload.get("courses", []) if str(c).strip()}
    if not semesters and not courses:
        raise ValueError("지울 학기나 과목을 선택해 주세요.")

    config = read_config(workspace)
    download_dir = Path(config.get("DOWNLOAD_PATH", str(workspace.default_download_path)))
    metadata = read_json(workspace.file_metadata_log, {})
    if not isinstance(metadata, dict):
        metadata = {}

    removed_names: list[str] = []
    freed = 0
    if download_dir.exists():
        for entry in list(download_dir.rglob("*")):
            if not entry.is_file():
                continue
            meta = metadata.get(entry.name)
            # 앱이 받은 기록이 없는 파일은 사용자 개인 파일일 수 있으므로 절대 건드리지 않는다
            if not meta:
                continue
            course = str(meta.get("course", ""))
            label = extract_course_label(course)
            sem = extract_semester(course)
            if sem not in semesters and label not in courses:
                continue
            try:
                size = entry.stat().st_size
                entry.unlink()
                freed += size
                removed_names.append(entry.name)
            except OSError:
                continue

    # 기록에서도 제거 → 필요하면 다시 받을 수 있음
    if removed_names:
        gone = set(removed_names)
        log = read_json(workspace.downloaded_files_log, [])
        if isinstance(log, list):
            kept = [item for item in log if str(item) not in gone]
            atomic_write_text(workspace.downloaded_files_log, 
                json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        for name in gone:
            metadata.pop(name, None)
        atomic_write_text(workspace.file_metadata_log, 
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return {
        "ok": True,
        "removed": len(removed_names),
        "freedBytes": freed,
        "freedHuman": human_size(freed),
        "message": f"{len(removed_names)}개 파일을 지워 {human_size(freed)}를 확보했습니다.",
    }


def get_shelves(workspace: UserWorkspace) -> dict[str, Any]:
    """사용자가 직접 만든 자료 폴더(책장)."""
    data = read_json(workspace.shelves_path, {})
    if not isinstance(data, dict):
        data = {}
    shelves = data.get("shelves")
    if not isinstance(shelves, list):
        shelves = []
    cleaned = []
    for s in shelves:
        if not isinstance(s, dict) or not s.get("id"):
            continue
        cleaned.append(
            {
                "id": str(s.get("id")),
                "name": str(s.get("name", "새 폴더")),
                "files": [str(f) for f in s.get("files", []) if str(f).strip()],
                "courses": [str(c) for c in s.get("courses", []) if str(c).strip()],
            }
        )
    return {"shelves": cleaned}


def save_shelves(workspace: UserWorkspace, payload: dict[str, Any]) -> dict[str, Any]:
    """폴더 목록 전체를 저장한다 (만들기·이름변경·항목이동·삭제 공용)."""
    shelves = payload.get("shelves")
    if not isinstance(shelves, list):
        raise ValueError("폴더 목록이 올바르지 않습니다.")
    cleaned = []
    for s in shelves[:60]:
        if not isinstance(s, dict):
            continue
        name = str(s.get("name", "")).strip() or "새 폴더"
        cleaned.append(
            {
                "id": str(s.get("id") or f"shelf-{secrets.token_hex(5)}"),
                "name": name[:60],
                "files": [str(f) for f in s.get("files", [])][:500],
                "courses": [str(c) for c in s.get("courses", [])][:100],
            }
        )
    workspace.root.mkdir(parents=True, exist_ok=True)
    atomic_write_text(workspace.shelves_path, 
        json.dumps({"shelves": cleaned}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"ok": True, "shelves": cleaned}


ALLOWED_LINK_HOSTS = (".dgist.ac.kr",)


def open_mail_link(payload: dict[str, Any]) -> dict[str, Any]:
    """메일 본문에서 누른 링크를 기본 브라우저로 연다.

    본문은 스크립트를 막은 iframe 안에 있어서 링크를 눌러도 아무 일이 없었다
    (새 창을 여는 동작이 iframe 보안 설정에 막힌다). 메일 앱들이 하는 대로
    바깥 브라우저로 넘긴다. 주소창이 보이는 브라우저에서 열리는 편이,
    앱 안에서 여는 것보다 어디로 가는지 알아보기 쉽고 안전하다.

    학교 밖 주소도 연다. 메일 링크는 설문(forms.gle)·신청 페이지처럼
    학교 밖으로 가는 것이 많다. 다만 사람이 직접 누른 것만 열고,
    http·https 가 아닌 주소(파일·프로그램 실행 등)는 열지 않는다.
    """
    from urllib.parse import urlparse

    url = str(payload.get("url", "")).strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("열 수 없는 주소입니다.")

    opened = False
    if not MULTI_USER_MODE:
        try:
            opened = webbrowser.open(url)
        except Exception:
            opened = False
    return {"ok": True, "url": url, "host": parsed.hostname, "opened": opened}


def open_external_url(payload: dict[str, Any]) -> dict[str, Any]:
    """학교 사이트를 기본 브라우저로 연다.

    아무 주소나 열지 않도록 dgist.ac.kr 도메인만 허용한다.
    (화면에서 넘어온 값이라도 그대로 믿지 않는다)
    """
    from urllib.parse import urlparse

    url = str(payload.get("url", "")).strip()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https"):
        raise ValueError("열 수 없는 주소입니다.")
    if not (host == "dgist.ac.kr" or host.endswith(ALLOWED_LINK_HOSTS)):
        raise ValueError("학교(dgist.ac.kr) 사이트만 열 수 있습니다.")

    opened = False
    if not MULTI_USER_MODE:
        try:
            opened = webbrowser.open(url)
        except Exception:
            opened = False
    return {"ok": True, "url": url, "opened": opened}


def open_assignment_page(workspace: UserWorkspace, payload: dict[str, Any]) -> dict[str, Any]:
    """과제의 LMS 제출 페이지를 기본 브라우저로 연다.

    앱이 대신 제출하지는 않는다. 파일 업로드와 최종 제출은 사용자가 직접
    LMS 화면에서 하도록 두는 편이 안전하다 (되돌릴 수 없는 작업이므로).
    """
    course_id = str(payload.get("courseId", "")).strip()
    column_id = str(payload.get("columnId", "")).strip()
    if not course_id:
        raise ValueError("과제의 강의 정보를 찾을 수 없습니다. '마감 새로고침'을 먼저 해 주세요.")

    config = read_config(workspace)
    base = str(config.get("LMS_URL", "https://lms.dgist.ac.kr")).rstrip("/")
    if column_id:
        url = f"{base}/ultra/courses/{course_id}/outline/assessment/{column_id}"
    else:
        url = f"{base}/ultra/courses/{course_id}/outline"

    opened = False
    if not MULTI_USER_MODE:
        try:
            opened = webbrowser.open(url)
        except Exception:
            opened = False
    return {
        "ok": True,
        "url": url,
        "opened": opened,
        "message": "LMS 제출 페이지를 열었습니다." if opened else "아래 주소를 브라우저에서 열어 주세요.",
    }


def _fill_missing_credits(workspace: UserWorkspace, entries: list[dict[str, Any]]) -> bool:
    """학점이 비어 있는 칸을 개설강좌 목록에서 찾아 채운다. 채웠으면 True.

    학점을 저장하기 전에 넣어 둔 시간표는 학점 칸이 아예 없다.
    다시 담으라고 하는 대신, 과목명으로 맞춰 조용히 메워 준다.

    한 번 본 칸은 creditChecked 로 표시해 두고 다시 보지 않는다.
    이 표시가 없으면 개설강좌 목록(2천 과목)을 매 요청마다 다시 읽는다.
    시간표는 12초마다 갱신되는 화면이라 그 비용이 그대로 렉이 된다.
    """
    todo = [
        e for e in entries
        if not str(e.get("credit", "")).strip() and not e.get("creditChecked")
    ]
    if not todo:
        return False

    try:
        catalog: dict[str, dict[str, Any]] = {}
        for undergrad in (True, False):
            found = get_course_catalog(workspace, year_term="", undergraduate=undergrad)
            for course in found.get("courses", []) or []:
                title = str(course.get("title", "")).strip()
                if title and title not in catalog:
                    catalog[title] = course
    except Exception:
        return False

    for entry in todo:
        # 목록에 없는 과목이어도 '봤다'고 남겨야 다음부터 건너뛴다
        entry["creditChecked"] = True
        course = catalog.get(str(entry.get("title", "")).strip())
        if not course:
            continue
        entry["credit"] = str(course.get("credit", "")).strip()[:8]
        entry.setdefault("courseNo", str(course.get("courseNo", "")).strip()[:20])
        entry.setdefault("professor", str(course.get("professor", "")).strip()[:60])
    return True


def get_timetable(workspace: UserWorkspace) -> dict[str, Any]:
    """주간 시간표. 학기별로 따로 보관해 지난 학기 것도 남는다."""
    data = read_json(workspace.timetable_path, {})
    if not isinstance(data, dict):
        data = {}
    entries = data.get("entries")
    entries = entries if isinstance(entries, list) else []
    semester = str(data.get("semester", ""))

    # 채운 값을 파일에 남겨야 다음 요청부터 이 일을 안 한다
    if _fill_missing_credits(workspace, entries):
        try:
            workspace.root.mkdir(parents=True, exist_ok=True)
            atomic_write_text(workspace.timetable_path, 
                json.dumps({"entries": entries, "semester": semester}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass  # 못 써도 화면은 그대로 나온다

    return {"entries": entries, "semester": semester}


def save_timetable_entry(workspace: UserWorkspace, payload: dict[str, Any]) -> dict[str, Any]:
    """시간표 칸 추가/수정. day는 0=월 … 5=토."""
    title = str(payload.get("title", "")).strip()
    if not title:
        raise ValueError("과목명을 입력해 주세요.")
    try:
        day = int(payload.get("day", 0))
    except (TypeError, ValueError):
        raise ValueError("요일이 올바르지 않습니다.")
    if not 0 <= day <= 5:
        raise ValueError("요일이 올바르지 않습니다.")

    start = str(payload.get("start", "")).strip()
    end = str(payload.get("end", "")).strip()
    if not re.fullmatch(r"\d{2}:\d{2}", start) or not re.fullmatch(r"\d{2}:\d{2}", end):
        raise ValueError("시간을 HH:MM 형식으로 입력해 주세요.")
    if start >= end:
        raise ValueError("끝나는 시간이 시작 시간보다 늦어야 합니다.")

    data = get_timetable(workspace)
    entries = data["entries"]
    entry_id = str(payload.get("id", "")).strip()
    entry = {
        "id": entry_id or f"tt-{secrets.token_hex(5)}",
        "title": title[:60],
        "day": day,
        "start": start,
        "end": end,
        "room": str(payload.get("room", "")).strip()[:40],
        "color": str(payload.get("color", "")).strip()[:20] or "coral",
        "courseLabel": str(payload.get("courseLabel", "")).strip()[:120],
        # 개설강좌 목록에는 학점·과목번호·교수가 다 들어 있는데, 예전에는 여기서
        # 걸러 버려서 시간표에 담는 순간 사라졌다. (그래서 몇 학점인지 볼 수 없었다)
        "credit": str(payload.get("credit", "")).strip()[:8],
        "courseNo": str(payload.get("courseNo", "")).strip()[:20],
        "professor": str(payload.get("professor", "")).strip()[:60],
    }
    if entry_id:
        entries = [entry if e.get("id") == entry_id else e for e in entries]
    else:
        entries.append(entry)

    workspace.root.mkdir(parents=True, exist_ok=True)
    atomic_write_text(workspace.timetable_path, 
        json.dumps(
            {"entries": entries, "semester": str(payload.get("semester", data.get("semester", "")))},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"ok": True, "entry": entry, "entries": entries}


def delete_timetable_entry(workspace: UserWorkspace, entry_id: str) -> dict[str, Any]:
    data = get_timetable(workspace)
    remaining = [e for e in data["entries"] if e.get("id") != entry_id]
    atomic_write_text(workspace.timetable_path, 
        json.dumps({"entries": remaining, "semester": data["semester"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"ok": True, "entries": remaining}


# ===== 미리 탑재한 씨앗 데이터 =====
# 학사일정과 개설강좌는 학기 내내 그대로다. 그런데 예전에는 앱을 처음 켠
# 사람마다 학교 홈페이지를 새로 긁어서, 첫 화면이 뜨는 데 몇 초씩 걸렸다.
# 배포본에 미리 넣어 두고(scripts/build_seed.py 로 만든다) 첫 화면은
# 네트워크 없이 즉시 띄운 뒤, 예약 새로고침이 알아서 최신으로 바꾼다.
SEED_DIR = PROJECT_ROOT / "data"
_seed_cache: dict[str, Any] = {}

# 캐시 수명. 성격에 맞춰 다르게 둔다.
ACADEMIC_TTL = 7 * 86400       # 학사일정: 학기 시작에 한 번 정해지면 그대로
CATALOG_TTL = 14 * 86400       # 개설강좌: 수강신청 끝나면 사실상 고정


def get_whats_new(workspace: UserWorkspace) -> dict[str, Any]:
    """업데이트 내용 (data/changelog.json) + 사용자가 어디까지 봤는지.

    '봤음' 표시는 데이터 폴더에 적는다. 앱 창(pywebview)은 기본으로 사적 모드라
    브라우저 저장소가 창을 닫을 때마다 지워져서, 거기 적으면 켤 때마다 '새 업데이트' 가 뜬다.
    """
    import updater

    entries = read_seed("changelog.json").get("entries") or []
    seen = read_json(workspace.root / "whats_new.json", {})
    version = updater.local_version()
    # 앱 안 '지금 업데이트' 로 방금 바뀌었으면 화면이 '업데이트를 마쳤어요' 카드를 띄운다
    marker = read_json(updater.update_marker_path(), {})
    just = marker if isinstance(marker, dict) and str(marker.get("to", "")) == version else None
    return {
        "version": version,
        "seen": str((seen or {}).get("seen", "")) if isinstance(seen, dict) else "",
        "entries": entries,
        "justUpdated": just,
    }


UI_THEMES = ("auto", "claude", "light", "navy", "dark")


def get_ui_prefs(workspace: UserWorkspace) -> dict[str, Any]:
    """화면 취향(테마). 앱 창의 브라우저 저장소는 끌 때마다 지워져, 거기 두면 켤 때마다 기본 테마로 돌아갔다."""
    data = read_json(workspace.root / "ui_prefs.json", {})
    data = data if isinstance(data, dict) else {}
    theme = data.get("theme")
    lang = data.get("lang")
    return {"theme": theme if theme in UI_THEMES else None, "lang": lang if lang in UI_LANGS else None}


# 화면 언어. None 이면 화면이 윈도우 언어를 보고 고른다 (한국어가 아니면 영어)
UI_LANGS = ("ko", "en")


def save_ui_prefs(workspace: UserWorkspace, payload: dict[str, Any]) -> dict[str, Any]:
    """테마·언어 중 보낸 것만 바꾼다."""
    data = read_json(workspace.root / "ui_prefs.json", {})
    data = data if isinstance(data, dict) else {}
    if "theme" in payload:
        theme = str(payload.get("theme") or "")
        if theme not in UI_THEMES:
            raise ValueError("알 수 없는 테마입니다.")
        data["theme"] = theme
    if "lang" in payload:
        lang = str(payload.get("lang") or "")
        if lang not in UI_LANGS:
            raise ValueError("알 수 없는 언어입니다.")
        data["lang"] = lang
    workspace.root.mkdir(parents=True, exist_ok=True)
    atomic_write_text(workspace.root / "ui_prefs.json", json.dumps(data, ensure_ascii=False))
    return {"ok": True, **{k: data.get(k) for k in ("theme", "lang")}}


def get_tutorial_state(workspace: UserWorkspace) -> dict[str, Any]:
    """첫 실행 소개(달구 튜토리얼)를 이미 봤는지.

    '업데이트 내용' 과 같은 이유로 브라우저 저장소가 아니라 데이터 폴더에 적는다.
    (앱 창은 끌 때마다 저장소가 지워져서, 거기 적으면 켤 때마다 소개가 다시 뜬다)
    """
    data = read_json(workspace.root / "tutorial.json", {})
    data = data if isinstance(data, dict) else {}
    return {
        "done": bool(data.get("done")),
        "skipped": bool(data.get("skipped")),
        "at": data.get("at"),
    }


def mark_tutorial_done(workspace: UserWorkspace, payload: dict[str, Any]) -> dict[str, Any]:
    import updater

    record = {
        "done": True,
        "skipped": bool(payload.get("skipped")),
        "step": int(payload.get("step") or 0),
        "at": now_iso(),
    }
    workspace.root.mkdir(parents=True, exist_ok=True)
    atomic_write_text((workspace.root / "tutorial.json"), json.dumps(record, ensure_ascii=False), encoding="utf-8")
    # 처음 쓰는 사람에게 '새 업데이트' 점은 뜻이 없다. 소개를 마치면 지금 버전은 본 것으로 친다.
    # (예전 버전을 쓰다 올린 사람은 이미 본 기록이 있으니 그대로 점이 뜬다)
    seen = read_json(workspace.root / "whats_new.json", {})
    if not (isinstance(seen, dict) and seen.get("seen")):
        mark_whats_new_seen(workspace, updater.local_version())
    return {"ok": True, **record}


def mark_whats_new_seen(workspace: UserWorkspace, version: str) -> dict[str, Any]:
    workspace.root.mkdir(parents=True, exist_ok=True)
    try:
        import updater

        updater.update_marker_path().unlink(missing_ok=True)  # '업데이트를 마쳤어요' 는 한 번만
    except OSError:
        pass
    atomic_write_text((workspace.root / "whats_new.json"), 
        json.dumps({"seen": str(version)[:20], "at": now_iso()}, ensure_ascii=False), encoding="utf-8"
    )
    return {"ok": True, "seen": str(version)[:20]}


def read_seed(name: str) -> dict[str, Any]:
    """data/ 안의 씨앗 파일. 한 번 읽으면 메모리에 둔다(디스크·파싱 반복 방지)."""
    if name in _seed_cache:
        return _seed_cache[name]
    path = SEED_DIR / name
    data: dict[str, Any] = {}
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        data = {}
    _seed_cache[name] = data
    return data


def get_academic_calendar(workspace: UserWorkspace, year: int | None = None, refresh: bool = False) -> dict[str, Any]:
    """DGIST 학사일정.

    캐시 → 씨앗 → 새로 받기 순서. 앞에서 걸리면 네트워크를 아예 안 쓴다.
    """
    import academic_calendar

    year = int(year or datetime.now().year)
    cache = read_json(workspace.academic_path, {}) or {}
    entry = cache.get(str(year)) if isinstance(cache, dict) else None
    fresh_enough = False
    if entry and not refresh:
        try:
            fetched = datetime.fromisoformat(entry.get("fetchedAt", ""))
            fresh_enough = (datetime.now() - fetched).total_seconds() < ACADEMIC_TTL
        except ValueError:
            fresh_enough = False
    def with_semester(payload: dict[str, Any]) -> dict[str, Any]:
        """지금이 몇 학기인지 함께 담아 준다. 시간표가 이 값에 맞춰 움직인다."""
        # 홈페이지 제목의 &#039; 같은 문자 코드가 그대로 남아 있던 캐시도 여기서 푼다
        for event in payload.get("events", []) or []:
            if isinstance(event, dict) and "&" in str(event.get("title", "")):
                event["title"] = html.unescape(str(event["title"]))
        try:
            payload["semester"] = academic_calendar.current_semester(payload.get("events", []))
        except Exception:
            payload["semester"] = {}
        return payload

    if entry and fresh_enough:
        return with_semester(
            {"ok": True, "year": year, "cached": True, **{k: v for k, v in entry.items() if k != "fetchedAt"}}
        )

    # 캐시가 없는 첫 실행이면 미리 넣어 둔 것으로 바로 화면을 채운다.
    # 새로 받는 건 예약 새로고침에 맡기고 여기서 기다리게 하지 않는다.
    if not entry and not refresh:
        seeded = (read_seed("seed_academic_calendar.json").get("years") or {}).get(str(year))
        if seeded and seeded.get("events"):
            return with_semester({**seeded, "ok": True, "seeded": True})

    result = academic_calendar.fetch_academic_calendar(year)
    if not result.get("ok"):
        # 새로 못 받으면 오래된 캐시라도 돌려준다
        if entry:
            return with_semester({"ok": True, "year": year, "cached": True, "stale": True,
                    **{k: v for k, v in entry.items() if k != "fetchedAt"}})
        return result

    if not isinstance(cache, dict):
        cache = {}
    cache[str(year)] = {
        "count": result.get("count", 0),
        "events": result.get("events", []),
        "fetchedAt": datetime.now().isoformat(timespec="seconds"),
    }
    atomic_write_text(workspace.academic_path, 
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return with_semester(result)


def get_shuttle(workspace: UserWorkspace, refresh: bool = False) -> dict[str, Any]:
    """셔틀·통근버스 시간표. 하루 캐시.

    예전에는 '학기 중에는 거의 안 바뀐다' 며 일주일을 두었는데, 2026년 9월에
    학기 중 개편이 있었다. 하루면 늦어도 다음 날엔 바뀐 시간표가 뜬다.
    """
    import shuttle

    cache = read_json(workspace.shuttle_path, {}) or {}
    if not refresh and isinstance(cache, dict) and cache.get("routes"):
        try:
            fetched = datetime.fromisoformat(cache.get("fetchedAt", ""))
            if (datetime.now() - fetched).total_seconds() < 86400:
                return {"cached": True, **cache}
        except ValueError:
            pass

    result = shuttle.fetch_shuttle()
    if result.get("ok"):
        result = {**result, "fetchedAt": datetime.now().isoformat(timespec="seconds")}
        atomic_write_text(workspace.shuttle_path, json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return result
    if isinstance(cache, dict) and cache.get("routes"):
        # 새로 못 받으면 지난 것이라도 보여 주되, 화면이 '예전 시간표' 라고 알리게 한다
        return {"cached": True, "stale": True, **cache}
    return result


_directory_cache: dict[str, Any] = {}


def search_directory_api(workspace: UserWorkspace, query: str, limit: int = 8) -> dict[str, Any]:
    """조직도에서 사람 찾기. 받은 메일 연락처와 합쳐서 돌려준다.

    조직도는 4,800여 명·600KB 라 글자를 칠 때마다 다시 읽지 않고 파일 도장이 바뀔 때만 읽는다.
    """
    import directory

    stamp = (str(workspace.directory_path), _file_stamp(workspace.directory_path))
    if _directory_cache.get("stamp") != stamp:
        _directory_cache.update(stamp=stamp, people=directory.load_directory(workspace.directory_path))
    people = _directory_cache["people"]
    hits = directory.search_directory(people, query, limit=max(1, min(int(limit or 8), 50)))
    return {"ok": True, "total": len(people), "results": hits}


def import_directory(workspace: UserWorkspace, people: list[dict[str, Any]]) -> dict[str, Any]:
    import directory

    if not isinstance(people, list) or not people:
        raise ValueError("가져올 사람 목록이 비어 있습니다.")
    return directory.save_directory(workspace.directory_path, people)


def get_course_catalog(
    workspace: UserWorkspace, year_term: str, undergraduate: bool, refresh: bool = False
) -> dict[str, Any]:
    """개설과목 목록.

    수강신청이 끝나면 학기 내내 그대로다. 캐시 → 씨앗 → 새로 받기 순서로 본다.
    """
    import timetable_import

    key = f"{year_term or 'auto'}|{'under' if undergraduate else 'grad'}"
    cache = read_json(workspace.catalog_path, {}) or {}
    entry = cache.get(key) if isinstance(cache, dict) else None
    if entry and not refresh:
        try:
            fetched = datetime.fromisoformat(entry.get("fetchedAt", ""))
            if (datetime.now() - fetched).total_seconds() < CATALOG_TTL:
                return {"cached": True, **{k: v for k, v in entry.items() if k != "fetchedAt"}}
        except ValueError:
            pass

    if not entry and not refresh:
        # 'auto' 로 들어오면 씨앗은 실제 학기 코드로 저장돼 있으니 그쪽으로 맞춰 찾는다
        term = year_term or timetable_import.current_term_value()
        seeded = (read_seed("seed_course_catalog.json").get("terms") or {}).get(
            f"{term}|{'under' if undergraduate else 'grad'}"
        )
        if seeded and seeded.get("courses"):
            return {**seeded, "seeded": True}

    result = timetable_import.fetch_dgist_catalog(
        year_term=year_term, undergraduate=undergraduate
    )
    if result.get("ok") and result.get("courses"):
        if not isinstance(cache, dict):
            cache = {}
        cache[key] = {**result, "fetchedAt": datetime.now().isoformat(timespec="seconds")}
        atomic_write_text(workspace.catalog_path, 
            json.dumps(cache, ensure_ascii=False), encoding="utf-8"
        )
    elif entry:
        # 새로 못 받으면 지난 것이라도 보여 준다
        return {"cached": True, "stale": True, **{k: v for k, v in entry.items() if k != "fetchedAt"}}
    return result


def _restart_process() -> None:
    """같은 명령으로 프로세스를 새로 띄우고 자신은 끝낸다.

    응답이 먼저 나가도록 잠깐 기다린 뒤 실행한다.
    """
    import subprocess
    import sys
    import time as _time

    _time.sleep(0.8)
    try:
        entry = PROJECT_ROOT / "app.py"
        args = [sys.executable, str(entry)] if entry.exists() else [sys.executable, *sys.argv]
        creation = 0
        if os.name == "nt":
            # 콘솔 창이 새로 뜨지 않게
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(args, cwd=str(PROJECT_ROOT), close_fds=True, creationflags=creation)
    except Exception:
        pass
    os._exit(0)


def get_notices(workspace: UserWorkspace, refresh: bool = False) -> dict[str, Any]:
    """학교 공지. 로그인 없이 볼 수 있는 게시판만 모은다.

    자주 새로고침하면 학교 서버에 부담이라 1시간 캐시를 둔다.
    """
    import notice_board

    cache = read_json(workspace.notices_path, {}) or {}
    if not refresh and isinstance(cache, dict) and cache.get("items"):
        try:
            fetched = datetime.fromisoformat(cache.get("fetchedAt", ""))
            if (datetime.now() - fetched).total_seconds() < 3600:
                return {"ok": True, "cached": True, **{k: v for k, v in cache.items() if k != "fetchedAt"}}
        except ValueError:
            pass

    result = notice_board.fetch_all()
    if not result.get("ok"):
        # 새로 못 받으면 지난 것이라도 보여 준다
        if isinstance(cache, dict) and cache.get("items"):
            return {"ok": True, "cached": True, "stale": True,
                    **{k: v for k, v in cache.items() if k != "fetchedAt"}}
        return result

    atomic_write_text(workspace.notices_path, 
        json.dumps({**result, "fetchedAt": datetime.now().isoformat(timespec="seconds")},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def get_my_events(workspace: UserWorkspace) -> dict[str, Any]:
    """사용자가 캘린더에서 직접 만든 일정 목록."""
    data = read_json(workspace.my_events_path, [])
    items = data if isinstance(data, list) else []
    cleaned = []
    for item in items:
        if isinstance(item, dict) and item.get("id") and item.get("date"):
            cleaned.append(item)
    return {"events": cleaned}


def search_place(query: str) -> dict[str, Any]:
    """장소 이름으로 좌표를 찾는다 (OpenStreetMap Nominatim).

    구글 지도 JavaScript API 는 OAuth 가 아니라 결제가 연결된 API 키를 요구한다.
    캘린더용 OAuth 자격증명으로는 지도를 띄울 수 없어, 키 없이 쓸 수 있는
    OpenStreetMap 검색으로 좌표를 얻고 링크만 구글 지도로 연다.
    """
    query = (query or "").strip()
    if len(query) < 2:
        return {"ok": True, "places": []}

    url = "https://nominatim.openstreetmap.org/search?" + urlencode(
        {"q": query, "format": "jsonv2", "limit": "6", "accept-language": "ko"}
    )
    req = urllib.request.Request(
        url,
        headers={
            # Nominatim 은 신원을 밝히지 않으면 막는다
            "User-Agent": "bungeoppang-dgist-autosaver/1.0 (personal student app)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        rows = json.loads(resp.read().decode("utf-8", "ignore"))

    places = []
    for row in rows:
        name = row.get("display_name") or ""
        places.append(
            {
                "name": name.split(",")[0].strip(),
                "address": name,
                "lat": float(row.get("lat", 0) or 0),
                "lon": float(row.get("lon", 0) or 0),
            }
        )
    return {"ok": True, "places": places}


def save_my_event(workspace: UserWorkspace, payload: dict[str, Any]) -> dict[str, Any]:
    """일정 추가 또는 수정 (id가 있으면 수정)."""
    title = str(payload.get("title", "")).strip()
    date = str(payload.get("date", "")).strip()
    if not title:
        raise ValueError("일정 제목을 입력해 주세요.")
    if not date:
        raise ValueError("날짜를 선택해 주세요.")

    events = get_my_events(workspace)["events"]
    event_id = str(payload.get("id", "")).strip()
    # 반복 규칙. 화면에서 펼쳐 그리므로 여기서는 규칙만 적어 둔다.
    repeat = str(payload.get("repeat", "")).strip()
    if repeat not in ("", "none", "daily", "weekly", "biweekly", "monthly", "yearly"):
        repeat = ""
    if repeat == "none":
        repeat = ""

    entry = {
        "id": event_id or f"my-{secrets.token_hex(6)}",
        "title": title[:200],
        "date": date,                                   # YYYY-MM-DD (시작일)
        "time": str(payload.get("time", "")).strip(),   # HH:MM (빈 값이면 종일)
        "endTime": str(payload.get("endTime", "")).strip(),
        # 여러 날에 걸친 일정이면 마지막 날. 비어 있으면 하루짜리.
        "endDate": str(payload.get("endDate", "")).strip(),
        "repeat": repeat,
        # 반복을 언제까지 할지. 비어 있으면 1년치만 펼친다.
        "repeatUntil": str(payload.get("repeatUntil", "")).strip(),
        "location": str(payload.get("location", "")).strip()[:200],
        "note": str(payload.get("note", "")).strip()[:500],
        "updatedAt": now_iso(),
    }
    if event_id:
        events = [entry if e.get("id") == event_id else e for e in events]
    else:
        events.append(entry)

    workspace.root.mkdir(parents=True, exist_ok=True)
    atomic_write_text(workspace.my_events_path, 
        json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"ok": True, "event": entry, "events": events}


def delete_my_event(workspace: UserWorkspace, event_id: str) -> dict[str, Any]:
    events = get_my_events(workspace)["events"]
    remaining = [e for e in events if e.get("id") != event_id]
    workspace.root.mkdir(parents=True, exist_ok=True)
    atomic_write_text(workspace.my_events_path, 
        json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"ok": True, "removed": len(events) - len(remaining), "events": remaining}


def _clean_hidden(value: Any) -> list[str]:
    """숨긴(목록에서 제거한) 과목 라벨 목록을 정규화한다."""
    if not isinstance(value, list):
        return []
    return sorted({str(name) for name in value if str(name).strip()})


def get_upload_selection(workspace: UserWorkspace) -> dict[str, Any]:
    data = read_json(workspace.upload_selection_path, {})
    courses = data.get("courses") if isinstance(data, dict) else None
    hidden = data.get("hidden") if isinstance(data, dict) else None
    return {
        "courses": courses if isinstance(courses, dict) else {},
        "hidden": _clean_hidden(hidden),
        "hiddenDeadlines": _clean_hidden(
            data.get("hiddenDeadlines") if isinstance(data, dict) else None
        ),
        # 자료 목록에서만 뺀 파일 (실제 파일은 그대로 둔다)
        "hiddenFiles": _clean_hidden(
            data.get("hiddenFiles") if isinstance(data, dict) else None
        ),
    }


def save_upload_selection(workspace: UserWorkspace, payload: dict[str, Any]) -> dict[str, Any]:
    courses = payload.get("courses")
    if not isinstance(courses, dict):
        courses = {}
    cleaned = {str(name): bool(enabled) for name, enabled in courses.items()}
    hidden = _clean_hidden(payload.get("hidden"))
    hidden_deadlines = _clean_hidden(payload.get("hiddenDeadlines"))
    hidden_files = _clean_hidden(payload.get("hiddenFiles"))
    record = {
        "courses": cleaned,
        "hidden": hidden,
        "hiddenDeadlines": hidden_deadlines,
        "hiddenFiles": hidden_files,
    }
    workspace.root.mkdir(parents=True, exist_ok=True)
    atomic_write_text(workspace.upload_selection_path, 
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record


def get_status(workspace: UserWorkspace, base_url: str | None = None) -> dict[str, Any]:
    config = read_config(workspace)
    files = get_files(workspace)
    google_oauth = get_google_oauth_status(workspace, base_url)
    courses = sorted({item["courseLabel"] for item in files})
    downloaded_log = read_json(workspace.downloaded_files_log, [])
    download_path = get_download_path(workspace, config)
    # '로컬 저장된 강의자료' 수.
    # 예전에는 다운로드 폴더의 파일을 전부 셌는데, 이 경로가 사용자의 개인
    # Downloads 폴더로 잡혀 있으면 앱과 무관한 개인 파일까지 포함돼
    # 실제 자료 목록(1개)과 화면 표시(54개)가 어긋났다.
    # 앱이 받은 자료 중 실제로 있는 것만 센다.
    downloaded_files = [item for item in files if item["status"] == "local"]

    required_config = {
        "lms": bool(config.get("LMS_ID") and config.get("LMS_PASSWORD")),
        "gemini": bool(config.get("GEMINI_API_KEY")),
        "drive": bool(google_oauth["tokenUsable"]),
        "gmail": bool(config.get("EMAIL_ADDRESS") and config.get("EMAIL_PASSWORD")),
    }

    with task_lock:
        task_state = task_states.setdefault(workspace.user_id, default_task_state())
        running = bool(task_state["running"])
        task_kind = task_state["kind"]

    deadlines = get_deadlines(workspace)
    course_state = get_course_state(workspace)

    return {
        "deadlines": {
            "updatedAt": deadlines.get("updatedAt"),
            "total": len(deadlines.get("items", [])),
            **deadline_counts(deadlines),
        },
        "courseChange": {
            "pending": course_state["pending"],
            "added": course_state["added"],
            "removed": course_state["removed"],
        },
        "mode": "multi-user" if MULTI_USER_MODE else "single-user",
        "workspaceId": workspace.user_id,
        "workspacePath": str(workspace.root),
        "configExists": workspace.config_path.exists() or (not MULTI_USER_MODE and CONFIG_PATH.exists()),
        "configPath": str(workspace.config_path),
        "downloadPath": str(download_path),
        "downloadPathExists": download_path.exists(),
        "credentialsPath": str(DRIVE_CREDENTIALS_PATH),
        "credentialsExists": google_credentials_available(),
        "tokenExists": workspace.token_path.exists(),
        "googleOAuth": google_oauth,
        "scheduleTime": config.get("SCHEDULE_TIME", "08:00"),
        "counts": {
            "files": len(files),
            "courses": len(courses),
            "downloadedLog": len(downloaded_log) if isinstance(downloaded_log, list) else 0,
            "localFiles": len(downloaded_files),
            "missing": len([item for item in files if item["status"] == "missing"]),
        },
        "courses": courses,
        "requiredConfig": required_config,
        "task": {
            "running": running,
            "kind": task_kind,
        },
    }


def safe_public_config(workspace: UserWorkspace) -> dict[str, Any]:
    config = read_config(workspace)
    return {
        "lmsId": config.get("LMS_ID", ""),
        "emailAddress": config.get("EMAIL_ADDRESS", ""),
        "emailTo": config.get("EMAIL_TO", config.get("EMAIL_ADDRESS", "")),
        "downloadPath": config.get("DOWNLOAD_PATH", str(workspace.default_download_path)),
        "scheduleTime": config.get("SCHEDULE_TIME", "08:00"),
        "lmsUrl": config.get("LMS_URL", "https://lms.dgist.ac.kr"),
        "loginUrl": config.get(
            "LOGIN_URL",
            "https://saml.dgist.ac.kr/authentication/idpw/idPwLogin.html?agentId=-100000&useOauth=0",
        ),
        "schoolEmail": config.get("SCHOOL_EMAIL", ""),
        "schoolImapHost": config.get("SCHOOL_IMAP_HOST", "mail.dgist.ac.kr"),
        "autoEmailMinutes": auto_minutes(config)["emails"],
        "autoDeadlineMinutes": auto_minutes(config)["deadlines"],
        "autoSyncMinutes": auto_minutes(config)["sync"],
        "gcalSyncEnabled": bool(config.get("GCAL_SYNC_ENABLED", False)),
        "gcalCalendarName": config.get("GCAL_CALENDAR_NAME", "DGIST 메일 일정"),
        "interests": config.get("EMAIL_INTERESTS", "전공 탐색, 취업, 음악, 세미나"),
        "interestTags": config.get("EMAIL_INTEREST_TAGS", []),
        "interestsCustom": config.get("EMAIL_INTERESTS_CUSTOM", ""),
        "hidePastEmails": bool(config.get("EMAIL_HIDE_PAST", False)),
        "notifyDeadlines": config.get("NOTIFY_DEADLINES", True) is not False,
        "notifyNewFiles": config.get("NOTIFY_NEW_FILES", True) is not False,
        "localSavePath": config.get("LOCAL_SAVE_PATH", ""),
        "autoLocalSave": local_autosave_mode(config),
        "localSaveFolder": str(get_local_save_dir(workspace)),
        "driveUpload": config.get("AUTO_DRIVE_UPLOAD", True) is not False,
        "saveScope": save_scope(config),
        "clouds": cloud_targets(config),
        "driveFolderName": drive_root_folder_name(),
        "hasLmsPassword": bool(config.get("LMS_PASSWORD")),
        "hasGeminiKey": bool(config.get("GEMINI_API_KEY")),
        "hasDgistApiKey": bool(config.get("DGIST_API_KEY")),
        "hasEmailPassword": bool(config.get("EMAIL_PASSWORD")),
        "hasSchoolEmailPassword": bool(config.get("SCHOOL_EMAIL_PASSWORD")),
    }


def append_log(user_id: str, line: str) -> None:
    with task_lock:
        task_state = task_states.setdefault(user_id, default_task_state())
        task_state["logs"].append(line.rstrip())
        task_state["logs"] = task_state["logs"][-500:]


def run_process(workspace: UserWorkspace, kind: str, command: list[str], extra_env: dict[str, str] | None = None, auto: bool = False) -> None:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["AUTOSAVER_DATA_ROOT"] = str(workspace.root)
    env["AUTOSAVER_CONFIG_PATH"] = str(workspace.config_path)
    env["AUTOSAVER_GOOGLE_CLIENT_SECRETS"] = str(DRIVE_CREDENTIALS_PATH)
    if extra_env:
        env.update(extra_env)
    if MULTI_USER_MODE:
        env["AUTOSAVER_DISABLE_LEGACY_CONFIG"] = "1"

    with task_lock:
        task_state = task_states.setdefault(workspace.user_id, default_task_state())
        task_state.update(
            {
                "running": True,
                "kind": kind,
                "startedAt": now_iso(),
                "finishedAt": None,
                "returnCode": None,
                # 예약·주기 실행이면 표시해 둔다. 이걸 안 하면 5분 메일 확인이
                # 돌 때마다 사용자가 시킨 것처럼 보여서 헷갈린다.
                "auto": auto,
                "logs": [f"[{now_iso()}] {kind} 작업을 시작합니다."
                         + (" (자동 실행)" if auto else "")],
            }
        )

    try:
        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        with task_lock:
            current_processes[workspace.user_id] = process

        assert process.stdout is not None
        for line in process.stdout:
            append_log(workspace.user_id, line)
        return_code = process.wait()
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        append_log(workspace.user_id, f"[오류] {exc}")
        return_code = -1

    with task_lock:
        current_processes.pop(workspace.user_id, None)
        task_state = task_states.setdefault(workspace.user_id, default_task_state())
        task_state.update(
            {
                "running": False,
                "finishedAt": now_iso(),
                "returnCode": return_code,
            }
        )
        task_state["logs"].append(
            f"[{now_iso()}] {kind} 작업이 종료되었습니다. 종료 코드: {return_code}"
        )

    # 자료를 새로 받았으면 곧바로 '학기 / 과목' 폴더로 정리한다.
    # 버튼을 눌러야만 정리되면, 새로 받은 자료는 계속 폴더 밖에 쌓인다.
    if kind == "sync" and return_code == 0:
        try:
            result = organize_downloads(workspace)
            if result.get("moved"):
                append_log(workspace.user_id, f"[정리] {result['message']}")
        except Exception as exc:
            append_log(workspace.user_id, f"[정리] 건너뜀: {exc}")
        # 설정에서 켠 경우, Drive 처럼 내 컴퓨터 저장 폴더에도 자동으로 둔다
        try:
            local = autosave_local(workspace)
            if not local.get("skipped") and (local.get("saved") or local.get("updated") or local.get("kept") or local.get("failed")):
                append_log(workspace.user_id, f"[자동 저장] {local['message']}")
        except Exception as exc:
            append_log(workspace.user_id, f"[자동 저장] 저장하지 못했습니다: {exc}")

    # 성공/실패 기록 (조용한 실패를 사용자에게 알리기 위함)
    if kind in ("sync", "emails", "deadlines"):
        # 서버가 로그인 자체를 거절했는지 (네트워크 오류와 구분해 자동 재시도를 멈춘다)
        recent = " ".join(str(line) for line in (task_state.get("logs") or [])[-40:])
        auth_failed = return_code != 0 and "로그인에 실패" in recent
        health = record_task_result(workspace, kind, return_code, auth_failed=auth_failed)
        if return_code != 0:
            fails = health.get("consecutiveFailures", 0)
            append_log(
                workspace.user_id,
                f"[알림] {kind} 작업이 실패했습니다 (연속 {fails}회). 계정 정보나 네트워크를 확인해 주세요.",
            )

    # 메일을 새로 읽어온 뒤 구글 캘린더 자동 동기화 (설정에서 켠 경우에만)
    if kind in ("emails", "sync") and return_code == 0:
        auto_sync_calendar(workspace)


def auto_sync_calendar(workspace: UserWorkspace) -> None:
    """설정이 켜져 있으면 메일 일정을 구글 캘린더에 자동 반영한다.

    실패해도 본 작업에는 영향을 주지 않도록 로그만 남긴다.
    """
    try:
        config = read_config(workspace)
        if not config.get("GCAL_SYNC_ENABLED"):
            return
        if not workspace.token_path.exists():
            append_log(workspace.user_id, "[캘린더] 구글 계정이 연결되지 않아 동기화를 건너뜁니다.")
            return

        import calendar_sync

        if not calendar_sync.has_calendar_scope(str(workspace.token_path)):
            append_log(
                workspace.user_id,
                "[캘린더] 캘린더 권한이 없습니다. 설정에서 구글 계정을 다시 연결해 주세요.",
            )
            return
        # 관심 분야 세미나와 학교 행사만 보낸다 (날짜가 잡힌 메일 전부를 넣으면 캘린더가 넘친다)
        emails = [m for m in get_emails(workspace).get("emails", []) if m.get("calendar")]
        result = calendar_sync.sync_email_events(
            emails,
            calendar_name=config.get("GCAL_CALENDAR_NAME", "DGIST 메일 일정"),
            token_path=str(workspace.token_path),
        )
        append_log(
            workspace.user_id,
            f"[캘린더] '{result.get('calendar')}' 동기화 완료 — {result.get('message')}",
        )
    except Exception as exc:
        append_log(workspace.user_id, f"[캘린더] 자동 동기화 실패: {exc}")


def start_task(workspace: UserWorkspace, kind: str, sync_mode: str = "fast", auto: bool = False) -> tuple[bool, str]:
    with task_lock:
        task_state = task_states.setdefault(workspace.user_id, default_task_state())
        if task_state["running"]:
            return False, "이미 실행 중인 작업이 있습니다."

    extra_env = {}
    if kind == "sync":
        extra_env["AUTOSAVER_SYNC_MODE"] = "full" if sync_mode == "full" else "fast"

    if kind not in ("sync", "verify", "deadlines", "emails", "google-oauth"):
        return False, "알 수 없는 작업입니다."

    if getattr(sys, "frozen", False):
        # EXE 에서는 sys.executable 이 '붕어빵.exe' 다.
        # `-c "..."` 를 붙여도 무시되고 앱이 통째로 다시 켜지므로(창이 계속 늘어남),
        # app.py 의 작업 전용 진입점으로 들어가게 한다.
        from runtime_config import WORKER_FLAG

        command = [sys.executable, WORKER_FLAG, kind]
        ensure_data_files(workspace)
        thread = threading.Thread(
            target=run_process, args=(workspace, kind, command, extra_env, auto), daemon=True
        )
        thread.start()
        return True, "작업을 시작했습니다."

    if kind == "sync":
        command = [
            sys.executable,
            "-u",
            "-c",
            "import asyncio; import main; asyncio.run(main.run_job())",
        ]
    elif kind == "verify":
        # verify.py 에는 __main__ 블록이 없어서 파일로 실행하면 아무 일도 하지 않는다
        command = [
            sys.executable,
            "-u",
            "-c",
            "import asyncio; import verify; asyncio.run(verify.verify())",
        ]
    elif kind == "deadlines":
        command = [
            sys.executable,
            "-u",
            "-c",
            "import asyncio; import lms_crawler; asyncio.run(lms_crawler.crawl_deadlines_only())",
        ]
    elif kind == "emails":
        command = [sys.executable, "-u", "email_reader.py"]
    elif kind == "google-oauth":
        command = [
            sys.executable,
            "-u",
            "-c",
            "from drive_uploader import authorize_drive; authorize_drive(force=True)",
        ]
    else:
        return False, "알 수 없는 작업입니다."

    ensure_data_files(workspace)
    thread = threading.Thread(target=run_process, args=(workspace, kind, command, extra_env, auto), daemon=True)
    thread.start()
    return True, "작업을 시작했습니다."


def stop_task(workspace: UserWorkspace) -> tuple[bool, str]:
    with task_lock:
        process = current_processes.get(workspace.user_id)
        task_state = task_states.setdefault(workspace.user_id, default_task_state())
        running = bool(task_state["running"])

    if not running or process is None or process.poll() is not None:
        return False, "실행 중인 작업이 없습니다."

    process.terminate()
    append_log(workspace.user_id, f"[{now_iso()}] 사용자가 작업 중지를 요청했습니다.")
    return True, "작업 중지를 요청했습니다."


def disconnect_google_oauth(workspace: UserWorkspace) -> tuple[bool, str]:
    if workspace.token_path.exists():
        workspace.token_path.unlink()
    return True, "Google OAuth 연결 정보를 이 컴퓨터에서 제거했습니다."


class DashboardHandler(SimpleHTTPRequestHandler):
    server_version = "DGISTAutoSaverUI/1.0"

    def translate_path(self, path: str) -> str:
        from urllib.parse import unquote

        parsed = urlparse(path)
        route = unquote(parsed.path)
        if route == "/":
            return str(WEB_ROOT / "index.html")
        # 경로 탈출 차단: 정규화 후 WEB_ROOT 밖으로 나가면 차단
        web_root = WEB_ROOT.resolve()
        candidate = (web_root / route.lstrip("/")).resolve()
        if candidate != web_root and web_root not in candidate.parents:
            return str(web_root / "__forbidden__")
        return str(candidate)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def end_headers(self) -> None:
        cookie = getattr(self, "_new_session_cookie", None)
        if cookie:
            secure = "; Secure" if PUBLIC_BASE_URL.startswith("https://") else ""
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE}={cookie}; Path=/; HttpOnly; SameSite=Lax{secure}",
            )
        # 화면 파일은 캐시하지 않는다.
        # 앱을 업데이트했는데 옛 화면이 그대로 뜨는 문제를 원천 차단하기 위함
        # (로컬 서버라 캐시로 얻는 이득이 없다).
        path = self.path.split("?", 1)[0]
        if path.endswith((".js", ".css", ".html", "/")):
            self.send_header("Cache-Control", "no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
        super().end_headers()

    def host_allowed(self) -> bool:
        """DNS 리바인딩 방어: 로컬 모드에서는 Host가 루프백일 때만 허용."""
        if MULTI_USER_MODE or PUBLIC_BASE_URL:
            return True  # 호스팅 모드는 리버스 프록시/외부 도메인 사용
        host = (self.headers.get("Host") or "").split(":")[0].strip().lower()
        return host in {"127.0.0.1", "localhost", "[::1]", "::1", ""}

    def reject_bad_host(self) -> bool:
        if self.host_allowed():
            return False
        self.send_json({"ok": False, "message": "허용되지 않은 호스트입니다."}, HTTPStatus.FORBIDDEN)
        return True

    def csrf_ok(self) -> bool:
        """브라우저 폼/이미지 기반 CSRF 차단.

        정상 프런트엔드는 fetch로 application/json을 보낸다. 브라우저가
        교차 출처에서 자동 전송할 수 있는 요청은 JSON Content-Type을
        붙일 수 없으므로, JSON 본문을 요구하면 CSRF가 막힌다.
        """
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        return ctype == "application/json"

    def request_base_url(self) -> str:
        if PUBLIC_BASE_URL:
            return PUBLIC_BASE_URL
        proto = self.headers.get("X-Forwarded-Proto", "http").split(",")[0].strip() or "http"
        host = (
            self.headers.get("X-Forwarded-Host")
            or self.headers.get("Host")
            or "127.0.0.1:8765"
        )
        return f"{proto}://{host}".rstrip("/")

    def get_workspace(self) -> UserWorkspace:
        if not MULTI_USER_MODE:
            return workspace_for_user("local")

        cookie_header = self.headers.get("Cookie", "")
        cookies = SimpleCookie(cookie_header)
        token = cookies.get(SESSION_COOKIE).value if SESSION_COOKIE in cookies else ""
        if not token:
            token = secrets.token_urlsafe(32)
            self._new_session_cookie = token

        self._session_token = token
        user_id = hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]
        workspace = workspace_for_user(user_id)
        ensure_data_files(workspace)
        return workspace

    def read_body_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _accepts_gzip(self) -> bool:
        return "gzip" in (self.headers.get("Accept-Encoding") or "").lower()

    def send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # 자료 목록 137KB, 메일 목록 70KB 가 12초마다 오간다. 압축하면 1/5 이하.
        if len(body) > 1024 and self._accepts_gzip():
            body = gzip.compress(body, compresslevel=4)
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_static_gz(self, path: Path, content_type: str) -> bool:
        """화면 파일(js/css/html)을 압축해서 준다. 못 주면 False (기본 처리로)."""
        try:
            body = path.read_bytes()
        except OSError:
            return False
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        if self._accepts_gzip():
            body = gzip.compress(body, compresslevel=6)
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def do_GET(self) -> None:
        if self.reject_bad_host():
            return
        parsed = urlparse(self.path)
        route = parsed.path
        params = parse_qs(parsed.query)

        if route == "/healthz":
            self.send_json(
                {
                    "ok": True,
                    "mode": "multi-user" if MULTI_USER_MODE else "single-user",
                    "time": now_iso(),
                }
            )
            return

        workspace = self.get_workspace()
        base_url = self.request_base_url()
        if route in ("/", "/oauth2callback") and ("code" in params or "error" in params):
            code = params.get("code", [""])[0]
            state = params.get("state", [""])[0]
            error = params.get("error", [""])[0]
            if error:
                self.send_html(
                    "Google OAuth 연결 실패",
                    f"Google에서 오류를 반환했습니다: {error}",
                    success=False,
                )
                return
            if not code:
                self.send_html(
                    "Google OAuth 연결 실패",
                    "인증 코드가 없습니다. 대시보드에서 다시 연결해 주세요.",
                    success=False,
                )
                return
            try:
                callback_workspace, saved_state = finish_google_oauth(code, state)
                if MULTI_USER_MODE and callback_workspace.user_id != workspace.user_id:
                    self._new_session_cookie = saved_state.get("session_token") or secrets.token_urlsafe(32)
                self.send_html(
                    "Google OAuth 연결 완료",
                    "이제 대시보드로 돌아가 Drive 동기화를 실행할 수 있습니다.",
                    success=True,
                )
            except Exception as exc:
                self.send_html(
                    "Google OAuth 연결 실패",
                    str(exc),
                    success=False,
                )
            return
        if route == "/api/status":
            self.send_json(get_status(workspace, base_url))
            return
        if route == "/api/files":
            self.send_json({"files": get_files(workspace)})
            return
        if route == "/api/task":
            with task_lock:
                self.send_json(dict(task_states.setdefault(workspace.user_id, default_task_state())))
            return
        if route == "/api/config":
            self.send_json(safe_public_config(workspace))
            return
        if route == "/api/deadlines":
            self.send_json(get_deadlines(workspace))
            return
        if route == "/api/selection":
            self.send_json(get_upload_selection(workspace))
            return
        if route == "/api/my-events":
            self.send_json(get_my_events(workspace))
            return
        if route == "/api/timetable":
            self.send_json(get_timetable(workspace))
            return
        if route == "/api/notices":
            try:
                self.send_json(
                    get_notices(workspace, params.get("refresh", [""])[0] == "1")
                )
            except Exception as exc:
                self.send_json({"ok": False, "items": [], "message": str(exc)})
            return
        if route == "/api/academic-calendar":
            year = params.get("year", [""])[0]
            refresh = params.get("refresh", [""])[0] == "1"
            try:
                self.send_json(
                    get_academic_calendar(workspace, int(year) if year else None, refresh)
                )
            except Exception as exc:
                self.send_json({"ok": False, "events": [], "message": str(exc)})
            return
        if route == "/api/mail/folders":
            try:
                import email_reader

                self.send_json(email_reader.list_mail_folders())
            except Exception as exc:
                self.send_json({"ok": False, "folders": [], "message": str(exc)})
            return
        if route == "/api/mail/pending":
            # 보냈는데 답이 없는 메일 (리마인드 대상)
            try:
                import email_reader

                days = int(params.get("days", ["3"])[0] or 3)
                data = read_json(workspace.emails_log, {})
                mails = data.get("emails", []) if isinstance(data, dict) else []
                self.send_json({"ok": True, "items": email_reader.pending_replies(mails, days)})
            except Exception as exc:
                self.send_json({"ok": False, "items": [], "message": str(exc)})
            return
        if route == "/api/mail/eml":
            # 메일 원본을 .eml 파일로 내려준다
            try:
                import email_reader

                uid = int(params.get("uid", ["0"])[0] or 0)
                folder = params.get("folder", ["inbox"])[0]
                raw = email_reader.fetch_raw_message(uid, folder)
                name = f"mail-{uid}.eml"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "message/rfc822")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                self.end_headers()
                self.wfile.write(raw)
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/whats-new":
            self.send_json(get_whats_new(workspace))
            return
        if route == "/api/tutorial":
            self.send_json(get_tutorial_state(workspace))
            return
        if route == "/api/ui-prefs":
            self.send_json(get_ui_prefs(workspace))
            return
        if route == "/api/local-autosave/job":
            self.send_json(get_local_save_job())
            return
        if route == "/api/samsung-notes/job":
            self.send_json(get_notes_job())
            return
        if route == "/api/samsung-notes/status":
            try:
                import samsung_notes

                self.send_json({"ok": True, "available": samsung_notes.is_available()})
            except Exception as exc:
                self.send_json({"ok": False, "available": False, "message": str(exc)})
            return
        if route == "/api/email-body":
            try:
                self.send_json(get_email_body(workspace, params.get("id", [""])[0]))
            except Exception as exc:
                self.send_json({"ok": False, "body": "", "bodyHtml": "", "message": str(exc)})
            return
        if route == "/api/mail-image":
            self.serve_mail_image(
                workspace, params.get("id", [""])[0], params.get("n", ["0"])[0]
            )
            return
        if route == "/api/seminars":
            # 세미나·행사는 매주 새로 올라온다. 학기마다 갱신하는 강의·학사일정과 달리
            # 그때그때 받아서 보여 준다.
            try:
                import dgist_api

                if not dgist_api.has_key():
                    self.send_json(
                        {
                            "ok": False,
                            "items": [],
                            "needsKey": True,
                            "message": "DGIST 오픈API 인증키가 없습니다. 설정에서 등록해 주세요.",
                        }
                    )
                    return
                rows = params.get("rows", ["30"])[0]
                self.send_json(dgist_api.fetch_notices(rows=int(rows or 30)))
            except Exception as exc:
                self.send_json({"ok": False, "items": [], "message": str(exc)})
            return
        if route == "/api/dgist-api/status":
            try:
                import dgist_api

                self.send_json(dgist_api.probe())
            except Exception as exc:
                self.send_json({"ok": False, "hasKey": False, "message": str(exc)})
            return
        if route == "/api/shuttle":
            try:
                self.send_json(
                    get_shuttle(workspace, params.get("refresh", [""])[0] == "1")
                )
            except Exception as exc:
                self.send_json({"ok": False, "routes": [], "message": str(exc)})
            return
        if route == "/api/place-search":
            # 지도 검색. 구글 지도는 별도 API 키가 필요해서, 키 없이 쓸 수 있는
            # OpenStreetMap 검색을 쓴다. 브라우저에서 바로 부르면 CORS와
            # User-Agent 규칙에 걸려서 여기서 대신 불러 준다.
            try:
                self.send_json(search_place(params.get("q", [""])[0]))
            except Exception as exc:
                self.send_json({"ok": False, "places": [], "message": str(exc)})
            return
        if route == "/api/fglp":
            try:
                from fglp import get_fglp

                self.send_json(get_fglp())
            except Exception as exc:
                self.send_json({"ok": False, "schools": [], "message": str(exc)})
            return
        if route == "/api/directory":
            try:
                self.send_json(
                    search_directory_api(
                        workspace,
                        params.get("q", [""])[0],
                        int((params.get("limit", ["8"])[0] or "8")) if (params.get("limit", ["8"])[0] or "8").isdigit() else 8,
                    )
                )
            except Exception as exc:
                self.send_json({"ok": False, "results": [], "message": str(exc)})
            return
        if route == "/api/course-catalog":
            try:
                self.send_json(
                    get_course_catalog(
                        workspace,
                        year_term=(params.get("term", [""])[0] or ""),
                        undergraduate=(params.get("level", ["under"])[0] != "grad"),
                        refresh=params.get("refresh", [""])[0] == "1",
                    )
                )
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/course-terms":
            try:
                import timetable_import
                self.send_json(
                    {
                        "ok": True,
                        "terms": timetable_import.available_terms(),
                        "current": timetable_import.current_term_value(),
                    }
                )
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/storage":
            self.send_json(get_storage(workspace))
            return
        if route == "/api/shelves":
            self.send_json(get_shelves(workspace))
            return
        if route == "/api/health":
            self.send_json(get_health(workspace))
            return
        if route == "/api/config/export":
            try:
                self.send_json(export_settings(workspace, params.get("secrets", ["0"])[0] == "1"))
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/emails":
            self.send_json(get_emails(workspace))
            return
        if route == "/api/course-state":
            self.send_json(get_course_state(workspace))
            return
        if route == "/api/update/check":
            try:
                import updater
                self.send_json(updater.check_update())
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/update/job":
            import updater

            self.send_json(updater.get_update_job())
            return
        if route == "/api/drive/list":
            try:
                import drive_uploader
                service = drive_uploader.get_drive_service()
                results = service.files().list(
                    pageSize=25, orderBy="modifiedTime desc",
                    q="trashed=false and mimeType!='application/vnd.google-apps.folder'",
                    fields="files(id,name,size,mimeType)",
                ).execute()
                self.send_json({"files": results.get("files", [])})
            except Exception as exc:
                self.send_json({"ok": False, "files": [], "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/drive/get":
            file_id = params.get("id", [""])[0]
            try:
                import base64 as _b64
                import drive_uploader
                service = drive_uploader.get_drive_service()
                meta = service.files().get(fileId=file_id, fields="name,size,mimeType").execute()
                content = service.files().get_media(fileId=file_id).execute()
                if len(content) > 20 * 1024 * 1024:
                    raise ValueError("파일이 20MB를 넘습니다.")
                self.send_json({
                    "filename": meta.get("name", "file"),
                    "size": len(content),
                    "content": _b64.b64encode(content).decode("ascii"),
                })
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/file":
            self.serve_download(workspace, params.get("name", [""])[0])
            return
        if route == "/api/deadlines.ics":
            body = build_deadlines_ics(workspace).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/calendar; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Disposition", "attachment; filename=dgist-deadlines.ics")
            self.end_headers()
            self.wfile.write(body)
            return
        # 화면 파일은 압축해서 준다 (app.js 316KB, styles.css 203KB → 1/4 정도)
        static_types = {
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".html": "text/html; charset=utf-8",
            # 영어 화면 번역표 (web/i18n/en.json)
            ".json": "application/json; charset=utf-8",
        }
        target = Path(self.translate_path(self.path))
        if target.suffix.lower() in static_types and target.is_file():
            if self.send_static_gz(target, static_types[target.suffix.lower()]):
                return
        super().do_GET()

    def serve_mail_image(self, workspace: UserWorkspace, mail_id: str, index_raw: str) -> None:
        """메일 본문 안의 그림 한 장. 받아 둔 것이 없으면 그때 받아 온다."""
        try:
            index = int(index_raw)
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        mail = find_mail(workspace, mail_id)
        images = (mail or {}).get("inlineImages") or []
        if not mail or index < 0 or index >= len(images):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime = images[index].get("type", "image/jpeg")
        path = mail_image_path(workspace, mail_id, index, mime)
        if not path.exists():
            try:
                ensure_mail_images(workspace, mail)
            except Exception:
                pass
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        # 같은 메일을 다시 열 때 또 받지 않도록
        self.send_header("Cache-Control", "private, max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    def serve_download(self, workspace: UserWorkspace, name: str) -> None:
        """다운로드 폴더의 파일을 첨부파일로 전송 (브라우저 모드용)."""
        safe_name = Path(str(name)).name
        if not safe_name:
            self.send_json({"ok": False, "message": "파일 이름이 필요합니다."}, HTTPStatus.BAD_REQUEST)
            return
        download_path = get_download_path(workspace).resolve()
        metadata = read_json(workspace.file_metadata_log, {})
        meta = metadata.get(safe_name, {}) if isinstance(metadata, dict) else {}
        file_path = (download_path / stored_relpath(safe_name, meta)).resolve()
        if not str(file_path).startswith(str(download_path)) or not file_path.is_file():
            self.send_json({"ok": False, "message": "파일을 찾을 수 없습니다."}, HTTPStatus.NOT_FOUND)
            return
        display_name = str(meta.get("original_name", safe_name)) if isinstance(meta, dict) else safe_name

        from urllib.parse import quote

        body = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header(
            "Content-Disposition",
            f"attachment; filename*=UTF-8''{quote(display_name)}",
        )
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, title: str, message: str, success: bool = True) -> None:
        safe_title = html.escape(title)
        safe_message = html.escape(message)
        color = "#16945f" if success else "#b4232c"
        body = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    body {{ margin: 0; font-family: "Segoe UI", system-ui, sans-serif; background: #f7f8fb; color: #17202a; }}
    main {{ max-width: 680px; margin: 12vh auto; padding: 28px; border: 1px solid #d9e0e8; border-radius: 8px; background: white; }}
    h1 {{ margin: 0 0 10px; color: {color}; font-size: 26px; }}
    p {{ margin: 0 0 22px; color: #667085; line-height: 1.6; }}
    a {{ display: inline-flex; min-height: 38px; align-items: center; padding: 0 14px; border-radius: 8px; background: #b4232c; color: white; text-decoration: none; font-weight: 700; }}
  </style>
</head>
<body>
  <main>
    <h1>{safe_title}</h1>
    <p>{safe_message}</p>
    <a href="/">대시보드로 돌아가기</a>
  </main>
</body>
</html>""".encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.reject_bad_host():
            return
        if not self.csrf_ok():
            self.send_json(
                {"ok": False, "message": "잘못된 요청입니다 (Content-Type: application/json 필요)."},
                HTTPStatus.FORBIDDEN,
            )
            return
        workspace = self.get_workspace()
        base_url = self.request_base_url()
        route = urlparse(self.path).path
        if route == "/api/config":
            payload = self.read_body_json()
            values = write_config(workspace, payload)
            self.send_json({"ok": True, "config": safe_public_config(workspace), "values": bool(values)})
            return
        if route == "/api/run":
            payload = self.read_body_json()
            if payload.get("confirm") is not True:
                self.send_json(
                    {"ok": False, "message": "동기화 확인이 필요합니다."},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            sync_mode = str(payload.get("mode", "fast")).lower()
            ok, message = start_task(workspace, "sync", sync_mode)
            if ok:
                message = "전체 동기화를 시작했습니다." if sync_mode == "full" else "빠른 동기화를 시작했습니다."
            self.send_json({"ok": ok, "message": message}, HTTPStatus.OK if ok else HTTPStatus.CONFLICT)
            return
        if route == "/api/verify":
            ok, message = start_task(workspace, "verify")
            self.send_json({"ok": ok, "message": message}, HTTPStatus.OK if ok else HTTPStatus.CONFLICT)
            return
        if route == "/api/refresh-deadlines":
            ok, message = start_task(workspace, "deadlines")
            self.send_json({"ok": ok, "message": message}, HTTPStatus.OK if ok else HTTPStatus.CONFLICT)
            return
        if route == "/api/refresh-emails":
            config = read_config(workspace)
            if not config.get("SCHOOL_EMAIL") or not config.get("SCHOOL_EMAIL_PASSWORD"):
                self.send_json(
                    {"ok": False, "message": "설정 → 학교 이메일에서 계정을 먼저 입력해 주세요."},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            ok, message = start_task(workspace, "emails")
            self.send_json({"ok": ok, "message": message}, HTTPStatus.OK if ok else HTTPStatus.CONFLICT)
            return
        if route == "/api/acknowledge-courses":
            state = acknowledge_courses(workspace)
            self.send_json({"ok": True, "pending": state["pending"]})
            return
        if route == "/api/update/apply":
            if MULTI_USER_MODE:
                self.send_json({"ok": False, "message": "공유 웹사이트 모드에서는 쓸 수 없습니다."}, HTTPStatus.BAD_REQUEST)
                return
            try:
                import updater

                def exit_for_installer() -> None:
                    # 설치 프로그램이 파일을 바꿀 수 있게 앱을 끈다. 화면이 '설치 중' 을 받아 갈 틈을 준다.
                    threading.Timer(2.0, lambda: os._exit(0)).start()

                self.send_json(updater.apply_update(on_ready_to_exit=exit_for_installer))
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/send-email":
            payload = self.read_body_json()
            config = read_config(workspace)
            if not config.get("SCHOOL_EMAIL") or not config.get("SCHOOL_EMAIL_PASSWORD"):
                self.send_json(
                    {"ok": False, "message": "설정 → 학교 이메일에서 계정을 먼저 입력해 주세요."},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            try:
                import email_reader

                attachments = payload.get("attachments")
                if not isinstance(attachments, list):
                    attachments = []
                result = email_reader.send_email(
                    to_addr=str(payload.get("to", "")),
                    subject=str(payload.get("subject", "")),
                    body=str(payload.get("body", "")),
                    cc=str(payload.get("cc", "")),
                    bcc=str(payload.get("bcc", "")),
                    html=bool(payload.get("html")),
                    in_reply_to=str(payload.get("inReplyTo", "")),
                    references=str(payload.get("references", "")),
                    attachments=attachments,
                    account=config.get("SCHOOL_EMAIL"),
                    password=config.get("SCHOOL_EMAIL_PASSWORD"),
                    host=config.get("SCHOOL_SMTP_HOST", "smtp.dgist.ac.kr"),
                    port=int(config.get("SCHOOL_SMTP_PORT", 465) or 465),
                )
                self.send_json({"ok": True, "message": f"메일을 보냈습니다: {result['to']}"})
            except Exception as exc:
                self.send_json({"ok": False, "message": f"메일 발송 실패: {exc}"}, HTTPStatus.BAD_REQUEST)
            return
        if route in ("/api/mark-read", "/api/mark-all-read", "/api/delete-email", "/api/restore-email"):
            payload = self.read_body_json()
            config = read_config(workspace)
            if not config.get("SCHOOL_EMAIL") or not config.get("SCHOOL_EMAIL_PASSWORD"):
                self.send_json({"ok": False, "message": "학교 이메일 계정을 먼저 입력해 주세요."}, HTTPStatus.BAD_REQUEST)
                return
            try:
                import email_reader

                uid = payload.get("uid")
                folder = str(payload.get("folder", "inbox"))
                if route == "/api/mark-read":
                    email_reader.mark_read(int(uid), folder, bool(payload.get("seen", True)))
                    patch_email_local(workspace, int(uid), folder, unread=not bool(payload.get("seen", True)))
                    self.send_json({"ok": True})
                elif route == "/api/mark-all-read":
                    result = email_reader.mark_all_read(folder)
                    patch_email_local(workspace, None, folder, unread=False, all_in_folder=True)
                    self.send_json({"ok": True, "message": f"{result['count']}개를 읽음으로 표시했습니다."})
                elif route == "/api/restore-email":
                    email_reader.restore_message(int(uid), folder)
                    patch_email_local(workspace, int(uid), folder, remove=True)
                    self.send_json({"ok": True, "message": "받은 편지함으로 되돌렸습니다."})
                else:  # delete
                    # 휴지통 안에서 지우는 것은 되돌릴 수 없다.
                    # 화면에서 한 번 더 확인받은 경우에만 permanent 가 온다.
                    permanent = bool(payload.get("permanent"))
                    result = email_reader.delete_message(int(uid), folder, permanent)
                    if not result.get("ok") and result.get("needsConfirm"):
                        self.send_json(result)
                        return
                    patch_email_local(workspace, int(uid), folder, remove=True)
                    self.send_json({
                        "ok": True,
                        "message": "완전히 지웠습니다." if permanent else "휴지통으로 옮겼습니다.",
                    })
            except Exception as exc:
                self.send_json({"ok": False, "message": f"작업 실패: {exc}"}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/pick-folder":
            if MULTI_USER_MODE:
                self.send_json(
                    {"ok": False, "message": "공유 웹사이트 모드에서는 폴더 선택을 사용할 수 없습니다."},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            try:
                selected = pick_folder_dialog()
            except Exception as exc:
                self.send_json({"ok": False, "message": f"폴더 선택 실패: {exc}"}, HTTPStatus.BAD_REQUEST)
                return
            if not selected:
                self.send_json({"ok": False, "message": "폴더 선택이 취소되었습니다."})
                return
            self.send_json({"ok": True, "path": str(Path(selected))})
            return
        if route == "/api/selection":
            payload = self.read_body_json()
            saved = save_upload_selection(workspace, payload)
            self.send_json({"ok": True, **saved})
            return
        if route == "/api/timetable/import-image":
            try:
                import timetable_import
                payload = self.read_body_json()
                result = timetable_import.import_timetable_image(
                    str(payload.get("image", "")), str(payload.get("mime", "image/png"))
                )
                self.send_json(result)
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/timetable/import-link":
            try:
                import timetable_import
                payload = self.read_body_json()
                self.send_json(timetable_import.import_everytime(str(payload.get("url", ""))))
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/directory/import":
            try:
                payload = self.read_body_json() or {}
                self.send_json(import_directory(workspace, payload.get("people", [])))
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/mail/translate":
            try:
                import email_reader
                import translator

                payload = self.read_body_json()
                target = str(payload.get("id", ""))
                data = read_json(workspace.emails_log, {})
                mails = data.get("emails", []) if isinstance(data, dict) else []
                found = next((m for m in mails if str(m.get("id")) == target), None)
                if not found:
                    raise ValueError("메일을 찾지 못했습니다.")
                text = found.get("body") or found.get("snippet") or ""
                if not text.strip() and found.get("bodyHtml"):
                    text = email_reader.clean_html_to_text(found["bodyHtml"], 4000)
                result = translator.translate(text)
                self.send_json({"ok": True, **result})
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route in ("/api/mail/star", "/api/mail/move", "/api/mail/folder-create", "/api/mail/reminder"):
            try:
                import email_reader

                payload = self.read_body_json()
                if route == "/api/mail/star":
                    self.send_json(
                        email_reader.star_message(
                            int(payload.get("uid")),
                            str(payload.get("folder", "inbox")),
                            bool(payload.get("starred", True)),
                        )
                    )
                elif route == "/api/mail/move":
                    self.send_json(
                        email_reader.move_message(
                            int(payload.get("uid")),
                            str(payload.get("folder", "inbox")),
                            str(payload.get("target", "")),
                        )
                    )
                elif route == "/api/mail/folder-create":
                    self.send_json(email_reader.create_mail_folder(str(payload.get("name", ""))))
                else:  # reminder — 초안만 만들어 돌려준다 (보내기는 사용자가 확인 후)
                    data = read_json(workspace.emails_log, {})
                    mails = data.get("emails", []) if isinstance(data, dict) else []
                    target = str(payload.get("id", ""))
                    found = next((m for m in mails if str(m.get("id")) == target), None)
                    if not found:
                        raise ValueError("메일을 찾지 못했습니다.")
                    self.send_json({"ok": True, "draft": email_reader.build_reminder(found)})
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/samsung-notes/send":
            try:
                import samsung_notes

                payload = self.read_body_json()
                safe_name = Path(str(payload.get("name", ""))).name
                metadata = read_json(workspace.file_metadata_log, {})
                meta = metadata.get(safe_name, {}) if isinstance(metadata, dict) else {}
                root = get_download_path(workspace).resolve()
                source = (root / stored_relpath(safe_name, meta)).resolve()
                if not str(source).startswith(str(root)):
                    raise ValueError("파일을 찾을 수 없습니다.")
                course = str(meta.get("course", "")) if isinstance(meta, dict) else ""
                if not source.is_file():
                    raise ValueError("파일을 찾을 수 없습니다.")
                if not samsung_notes.is_supported(source):
                    raise ValueError("삼성 노트는 PDF 만 가져올 수 있습니다.")
                # 한 개짜리도 같은 흐름: 뒤에서 넣고 → 방금 생긴 노트를 과목 폴더로
                result = start_notes_job([(source, extract_course_label(course)[:60])])
                self.send_json(result, HTTPStatus.OK if result.get("ok") else HTTPStatus.CONFLICT)
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/files/bulk":
            # 고른 자료를 한꺼번에 처리한다 (Drive 업로드 / 삼성 노트 / 목록에서 빼기)
            try:
                payload = self.read_body_json()
                action = str(payload.get("action", ""))
                names = payload.get("names")
                if not isinstance(names, list) or not names:
                    raise ValueError("고른 자료가 없습니다.")

                metadata = read_json(workspace.file_metadata_log, {})
                if not isinstance(metadata, dict):
                    metadata = {}
                root = get_download_path(workspace).resolve()

                def resolve(raw_name: str):
                    safe = Path(str(raw_name)).name
                    meta = metadata.get(safe, {})
                    path = (root / stored_relpath(safe, meta)).resolve()
                    if not str(path).startswith(str(root)) or not path.is_file():
                        return None, None, None
                    return safe, meta, path

                done, failed, skipped = [], [], []

                if action == "drive":
                    from drive_uploader import upload_to_drive_with_path

                    for raw_name in names:
                        safe, meta, path = resolve(raw_name)
                        if not path:
                            failed.append(str(raw_name))
                            continue
                        display = str(meta.get("original_name", safe)) if isinstance(meta, dict) else safe
                        course = str(meta.get("course", "기타")) if isinstance(meta, dict) else "기타"
                        try:
                            result = upload_to_drive_with_path(str(path), display, course)
                            (skipped if result == "exists" else done).append(display)
                        except Exception:
                            failed.append(display)
                    message = f"Drive에 {len(done)}개 올렸습니다."
                    if skipped:
                        message += f" 이미 있던 {len(skipped)}개는 건너뛰었습니다."

                elif action == "notes":
                    import samsung_notes

                    if not samsung_notes.is_available():
                        raise ValueError("이 컴퓨터에 삼성 노트 앱이 없습니다.")
                    items = []
                    for raw_name in names:
                        safe, meta, path = resolve(raw_name)
                        if not path:
                            failed.append(str(raw_name))
                            continue
                        if not samsung_notes.is_supported(path):
                            skipped.append(path.name)
                            continue
                        course = str(meta.get("course", "")) if isinstance(meta, dict) else ""
                        items.append((path, extract_course_label(course)[:60]))
                    if not items:
                        raise ValueError("고른 자료 중에 PDF 가 없습니다. 삼성 노트는 PDF 만 가져올 수 있습니다.")
                    job = start_notes_job(items)
                    if not job.get("ok"):
                        raise ValueError(job.get("message", "삼성 노트에 넣지 못했습니다."))
                    self.send_json({**job, "skipped": len(skipped), "failed": len(failed)})
                    return

                elif action == "hide":
                    selection = get_upload_selection(workspace)
                    hidden = list(selection.get("hiddenFiles") or [])
                    for raw_name in names:
                        safe = Path(str(raw_name)).name
                        if safe not in hidden:
                            hidden.append(safe)
                            done.append(safe)
                    selection["hiddenFiles"] = hidden
                    save_upload_selection(workspace, selection)
                    message = f"{len(done)}개를 목록에서 뺐습니다. 파일은 그대로 있습니다."

                else:
                    raise ValueError("알 수 없는 작업입니다.")

                self.send_json(
                    {
                        "ok": True,
                        "done": len(done),
                        "skipped": len(skipped),
                        "failed": len(failed),
                        "message": message + (f" 실패 {len(failed)}개." if failed else ""),
                    }
                )
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/samsung-notes/organize":
            # 수동 정리 버튼 (자동 정리가 실패했을 때의 예비)
            # 삼성 노트로 보낸 PDF 들을 과목 이름 폴더로 정리한다.
            # 노트 제목은 보낸 파일 이름(확장자 뺀 것)과 같으므로 그것으로 짝을 짓는다.
            try:
                result = _notes_mapping_and_organize(workspace)
                self.send_json(result, HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/organize-files":
            try:
                self.send_json(organize_downloads(workspace))
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/timetable/bulk":
            try:
                payload = self.read_body_json()
                entries = payload.get("entries", [])
                if not isinstance(entries, list) or not entries:
                    raise ValueError("추가할 수업이 없습니다.")
                if payload.get("replace"):
                    atomic_write_text(workspace.timetable_path, 
                        json.dumps({"entries": [], "semester": ""}, ensure_ascii=False),
                        encoding="utf-8",
                    )
                saved = 0
                for item in entries:
                    try:
                        save_timetable_entry(workspace, item)
                        saved += 1
                    except ValueError:
                        continue
                self.send_json({"ok": True, "saved": saved, **get_timetable(workspace)})
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/timetable/save":
            try:
                self.send_json(save_timetable_entry(workspace, self.read_body_json()))
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/timetable/delete":
            try:
                eid = str(self.read_body_json().get("id", "")).strip()
                if not eid:
                    raise ValueError("삭제할 항목을 찾을 수 없습니다.")
                self.send_json(delete_timetable_entry(workspace, eid))
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/my-events/save":
            try:
                self.send_json(save_my_event(workspace, self.read_body_json()))
            except ValueError as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/shelves/save":
            try:
                self.send_json(save_shelves(workspace, self.read_body_json()))
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/mail/open-link":
            try:
                self.send_json(open_mail_link(self.read_body_json()))
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/open-url":
            try:
                self.send_json(open_external_url(self.read_body_json()))
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/assignment/open":
            try:
                self.send_json(open_assignment_page(workspace, self.read_body_json()))
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/storage/cleanup":
            try:
                self.send_json(cleanup_storage(workspace, self.read_body_json()))
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/google/credentials":
            # 다른 컴퓨터에서도 구글 로그인을 할 수 있게, credentials.json 을
            # 앱 화면에서 직접 넣는다. 이 파일은 배포판에 넣지 않는다.
            # (들어 있으면 받은 사람이 내 앱 이름으로 동의 화면을 띄울 수 있다)
            try:
                self.send_json(save_google_credentials(self.read_body_json()))
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/config/import":
            try:
                self.send_json(import_settings(workspace, self.read_body_json()))
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/my-events/delete":
            try:
                payload = self.read_body_json()
                event_id = str(payload.get("id", "")).strip()
                if not event_id:
                    raise ValueError("삭제할 일정을 찾을 수 없습니다.")
                self.send_json(delete_my_event(workspace, event_id))
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/restart":
            # 업데이트한 파이썬 코드는 프로세스를 다시 띄워야 반영된다.
            # (파일만 새로 받아도 이미 메모리에 올라온 모듈은 그대로다)
            try:
                self.send_json({"ok": True, "message": "앱을 다시 시작합니다."})
                threading.Thread(target=_restart_process, daemon=True).start()
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/gcal/sync-academic":
            try:
                import calendar_sync

                config = read_config(workspace)
                if not workspace.token_path.exists():
                    raise RuntimeError("먼저 설정에서 구글 계정을 연결해 주세요.")
                if not calendar_sync.has_calendar_scope(str(workspace.token_path)):
                    raise RuntimeError(
                        "구글 캘린더 권한이 없습니다. 설정에서 구글 계정을 다시 연결해 주세요."
                    )
                payload = self.read_body_json() or {}
                data = get_academic_calendar(workspace, payload.get("year"))
                events = data.get("events", [])
                # 학부만 보기로 해 뒀으면 대학원 전용 일정은 올리지 않는다
                if payload.get("undergraduateOnly"):
                    events = [e for e in events if e.get("kind") != "대학원"]
                result = calendar_sync.sync_academic_events(
                    events,
                    calendar_name=config.get("GCAL_ACADEMIC_NAME", "DGIST 학사일정"),
                    token_path=str(workspace.token_path),
                )
                self.send_json(result)
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/gcal/sync":
            try:
                import calendar_sync

                config = read_config(workspace)
                if not workspace.token_path.exists():
                    raise RuntimeError("먼저 설정에서 구글 계정을 연결해 주세요.")
                if not calendar_sync.has_calendar_scope(str(workspace.token_path)):
                    raise RuntimeError(
                        "구글 캘린더 권한이 없습니다. 설정에서 구글 계정을 다시 연결해 주세요."
                    )
                emails = [m for m in get_emails(workspace).get("emails", []) if m.get("calendar")]
                result = calendar_sync.sync_email_events(
                    emails,
                    calendar_name=config.get("GCAL_CALENDAR_NAME", "DGIST 메일 일정"),
                    token_path=str(workspace.token_path),
                )
                self.send_json(result)
            except Exception as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        if route == "/api/google/connect":
            try:
                payload = self.read_body_json()
                status = get_google_oauth_status(workspace, base_url)
                if not status["credentialsExists"]:
                    raise FileNotFoundError("Google OAuth 클라이언트를 먼저 준비해 주세요.")
                auth_url = create_google_oauth_url(
                    workspace,
                    base_url,
                    getattr(self, "_session_token", None),
                )
                # 데스크톱 앱(WebView)에서는 구글이 임베디드 브라우저 로그인을 막으므로
                # 시스템 기본 브라우저를 대신 띄운다.
                opened = False
                if payload.get("openBrowser") and not MULTI_USER_MODE:
                    try:
                        opened = webbrowser.open(auth_url)
                    except Exception:
                        opened = False
                self.send_json(
                    {
                        "ok": True,
                        "authUrl": auth_url,
                        "openedInBrowser": opened,
                        "requiredRedirectUri": choose_google_redirect_uri(base_url),
                        "redirectHint": (
                            "redirect_uri_mismatch가 뜨면 Google Cloud Console에 requiredRedirectUri를 "
                            "정확히 추가해 주세요."
                        ),
                    }
                )
            except FileNotFoundError as exc:
                self.send_json(
                    {
                        "ok": False,
                        "message": str(exc),
                    },
                    HTTPStatus.BAD_REQUEST,
                )
            except Exception as exc:
                self.send_json(
                    {
                        "ok": False,
                        "message": str(exc),
                    },
                    HTTPStatus.BAD_REQUEST,
                )
            return
        if route == "/api/google/disconnect":
            ok, message = disconnect_google_oauth(workspace)
            self.send_json({"ok": ok, "message": message})
            return
        if route == "/api/stop":
            ok, message = stop_task(workspace)
            self.send_json({"ok": ok, "message": message}, HTTPStatus.OK if ok else HTTPStatus.CONFLICT)
            return
        if route == "/api/tutorial/done":
            self.send_json(mark_tutorial_done(workspace, self.read_body_json()))
            return
        if route == "/api/ui-prefs":
            try:
                self.send_json(save_ui_prefs(workspace, self.read_body_json()))
            except ValueError as exc:
                self.send_json({"ok": False, "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/whats-new/seen":
            payload = self.read_body_json()
            self.send_json(mark_whats_new_seen(workspace, str(payload.get("version", ""))))
            return
        if route == "/api/local-autosave/run":
            if MULTI_USER_MODE:
                self.send_json({"ok": False, "message": "공유 웹사이트 모드에서는 쓸 수 없습니다."}, HTTPStatus.BAD_REQUEST)
                return
            payload = self.read_body_json()
            mode = str(payload.get("mode") or "").strip().lower() or None
            if mode is not None and mode not in ("current", "all"):
                mode = None
            result = start_local_save_job(workspace, mode)
            self.send_json(result, HTTPStatus.OK if result.get("ok") else HTTPStatus.CONFLICT)
            return
        if route == "/api/save-local":
            if MULTI_USER_MODE:
                self.send_json(
                    {"ok": False, "message": "공유 웹사이트 모드에서는 /api/file 다운로드를 사용해 주세요."},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            payload = self.read_body_json()
            names = payload.get("names")
            if not isinstance(names, list):
                names = [payload.get("name", "")]

            download_path = get_download_path(workspace).resolve()
            metadata = read_json(workspace.file_metadata_log, {})
            if not isinstance(metadata, dict):
                metadata = {}
            target_dir = get_local_save_dir(workspace)
            target_dir.mkdir(parents=True, exist_ok=True)

            import shutil

            saved = []
            failed = []
            for raw_name in names:
                safe_name = Path(str(raw_name)).name
                meta = metadata.get(safe_name, {})
                source = (download_path / stored_relpath(safe_name, meta)).resolve()
                if not safe_name or not str(source).startswith(str(download_path)) or not source.is_file():
                    failed.append(safe_name or str(raw_name))
                    continue
                display_name = str(meta.get("original_name", safe_name)) if isinstance(meta, dict) else safe_name
                # 문서\붕어빵 파일 정리\<과목>\<LMS 하위 폴더>\ 로 갈라 담는다 (자동 저장·Drive 와 같은 구조)
                course = str(meta.get("course", "")) if isinstance(meta, dict) else ""
                sub = lms_subfolders(meta.get("folder_path") if isinstance(meta, dict) else None)
                course_dir = (target_dir / _safe_folder(extract_course_label(course))).joinpath(*sub)
                os.makedirs(_long_path(course_dir), exist_ok=True)
                target = course_dir / display_name
                stem, suffix = target.stem, target.suffix
                counter = 2
                while os.path.exists(_long_path(target)):
                    target = course_dir / f"{stem} ({counter}){suffix}"
                    counter += 1
                shutil.copy2(_long_path(source), _long_path(target))
                saved.append(target.name)

            if not saved:
                self.send_json({"ok": False, "message": "파일을 찾을 수 없습니다."}, HTTPStatus.NOT_FOUND)
                return
            message = (
                f"'{target_dir}'에 저장했습니다: {saved[0]}"
                if len(saved) == 1
                else f"'{target_dir}'에 {len(saved)}개 파일을 저장했습니다."
            )
            if failed:
                message += f" (실패 {len(failed)}건)"
            self.send_json({"ok": True, "saved": saved, "failed": failed, "message": message})
            return
        if route == "/api/export-ics":
            if MULTI_USER_MODE:
                self.send_json(
                    {"ok": False, "message": "공유 웹사이트 모드에서는 /api/deadlines.ics 다운로드를 사용해 주세요."},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            content = build_deadlines_ics(workspace)
            target_dir = get_local_save_dir(workspace)
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / "dgist-deadlines.ics"
            counter = 2
            while target.exists():
                target = target_dir / f"dgist-deadlines ({counter}).ics"
                counter += 1
            atomic_write_text(target, content, encoding="utf-8")
            self.send_json(
                {"ok": True, "savedTo": str(target), "message": f"다운로드 폴더에 저장했습니다: {target.name}"}
            )
            return
        if route == "/api/open-downloads":
            if MULTI_USER_MODE:
                self.send_json(
                    {
                        "ok": False,
                        "message": "공유 웹사이트 모드에서는 서버의 다운로드 폴더를 직접 열 수 없습니다.",
                    },
                    HTTPStatus.BAD_REQUEST,
                )
                return
            download_path = get_download_path(workspace)
            download_path.mkdir(parents=True, exist_ok=True)
            # os.startfile 은 윈도우에만 있다. 맥은 open, 리눅스는 xdg-open.
            if os.name == "nt":
                os.startfile(str(download_path))
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(download_path)])
            self.send_json({"ok": True})
            return
        self.send_json({"ok": False, "message": "Not found"}, HTTPStatus.NOT_FOUND)


def main() -> None:
    ensure_data_files(workspace_for_user("local"))
    host = os.environ.get("AUTOSAVER_UI_HOST", "127.0.0.1")
    port = int(os.environ.get("AUTOSAVER_UI_PORT") or os.environ.get("PORT") or "8765")
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = PUBLIC_BASE_URL or f"http://{display_host}:{port}"
    print(f"DGIST LMS AutoSaver UI: {url}")
    print(f"Mode: {'multi-user' if MULTI_USER_MODE else 'single-user'}")
    print("Press Ctrl+C to stop.")
    if os.environ.get("AUTOSAVER_OPEN_BROWSER", "1").lower() not in {"0", "false", "no", "off"}:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping UI server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
