"""Local web dashboard for DGIST LMS AutoSaver.

Run with:
    python web_ui.py
"""
from __future__ import annotations

import ast
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
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parent
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
    GOOGLE_OAUTH_PENDING_PATH.write_text(
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
        # 주기적 자동 실행 (분 단위, 0이면 사용 안 함)
        "AUTO_INTERVAL_MINUTES": max(
            0,
            int(
                str(
                    payload.get("autoIntervalMinutes", existing.get("AUTO_INTERVAL_MINUTES", 0))
                    or 0
                )
                or 0
            ),
        ),
        "AUTO_INTERVAL_KIND": str(
            payload.get("autoIntervalKind", existing.get("AUTO_INTERVAL_KIND", "emails"))
        ).strip()
        or "emails",
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
    workspace.config_path.write_text(
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
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

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


def read_google_client_config() -> tuple[str | None, dict[str, Any]]:
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
    workspace.token_path.write_text(flow.credentials.to_json(), encoding="utf-8")
    return workspace, saved_state


def get_files(workspace: UserWorkspace) -> list[dict[str, Any]]:
    metadata = read_json(workspace.file_metadata_log, {})
    source = "metadata"
    if not isinstance(metadata, dict):
        metadata = {}
    if not metadata:
        metadata = read_json(FALLBACK_COURSE_MAP, {})
        if not isinstance(metadata, dict):
            metadata = {}
        source = "sample"

    download_path = get_download_path(workspace)
    rows: list[dict[str, Any]] = []
    for name, meta in metadata.items():
        display_name = name
        if isinstance(meta, dict):
            course = str(meta.get("course", "기타"))
            folder_path = meta.get("folder_path", [])
            folder = " / ".join(str(part) for part in folder_path if str(part).strip())
            display_name = str(meta.get("original_name", name))
        else:
            course = str(meta)
            folder = ""

        file_path = download_path / name
        extension = Path(display_name).suffix.lower().replace(".", "") or "file"
        exists_locally = file_path.exists()
        stat = file_path.stat() if exists_locally else None
        rows.append(
            {
                "name": display_name,
                "localName": name,
                "course": course,
                "courseLabel": extract_course_label(course),
                "semester": extract_semester(course),
                "folder": folder or ("샘플 데이터" if source == "sample" else "강의 자료"),
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

    rows.sort(key=lambda item: (item["courseLabel"], item["folder"], item["name"]))
    return rows


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
    path.write_text(json.dumps(new_state, ensure_ascii=False, indent=2), encoding="utf-8")
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
    workspace.emails_log.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_emails(workspace: UserWorkspace) -> dict[str, Any]:
    data = read_json(workspace.emails_log, {})
    if not isinstance(data, dict):
        data = {}
    return {
        "updatedAt": data.get("updatedAt"),
        "briefing": data.get("briefing", ""),
        "interests": data.get("interests", ""),
        "contacts": data.get("contacts", []) if isinstance(data.get("contacts"), list) else [],
        "emails": data.get("emails", []) if isinstance(data.get("emails"), list) else [],
    }


def get_local_save_dir(workspace: UserWorkspace) -> Path:
    config = read_config(workspace)
    custom = str(config.get("LOCAL_SAVE_PATH", "")).strip()
    if custom:
        try:
            path = Path(custom)
            path.mkdir(parents=True, exist_ok=True)
            return path
        except OSError:
            pass
    return Path.home() / "Downloads"


SECRET_KEYS = (
    "LMS_PASSWORD",
    "EMAIL_PASSWORD",
    "SCHOOL_EMAIL_PASSWORD",
    "GEMINI_API_KEY",
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
        workspace.my_events_path.write_text(
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
    if out["consecutiveFailures"] >= 2:
        kind = out["lastFailure"].get("kind", "작업")
        out["warning"] = f"{kind}이(가) {out['consecutiveFailures']}번 연속 실패했습니다. 설정에서 계정 정보를 확인해 주세요."
    elif out["stale"]:
        out["warning"] = f"{out['staleDays']}일째 동기화가 되지 않았습니다."
    return out


def record_task_result(workspace: UserWorkspace, kind: str, return_code: int) -> dict[str, Any]:
    """작업 성공/실패를 기록한다. 실패가 쌓이면 사용자에게 알리기 위함."""
    data = read_json(workspace.health_path, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("lastSuccess", {})
    stamp = now_iso()
    if return_code == 0:
        data["lastSuccess"][kind] = stamp
        data["consecutiveFailures"] = 0
        data.pop("lastFailure", None)
    else:
        data["consecutiveFailures"] = int(data.get("consecutiveFailures", 0) or 0) + 1
        data["lastFailure"] = {"kind": kind, "at": stamp, "code": return_code}
    try:
        workspace.root.mkdir(parents=True, exist_ok=True)
        workspace.health_path.write_text(
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
    personal_dirs = {"downloads", "documents", "desktop", "다운로드", "문서", "바탕화면"}
    shared_folder = download_dir.name.lower() in personal_dirs

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
            workspace.downloaded_files_log.write_text(
                json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        for name in gone:
            metadata.pop(name, None)
        workspace.file_metadata_log.write_text(
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
    workspace.shelves_path.write_text(
        json.dumps({"shelves": cleaned}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"ok": True, "shelves": cleaned}


ALLOWED_LINK_HOSTS = (".dgist.ac.kr",)


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


def get_timetable(workspace: UserWorkspace) -> dict[str, Any]:
    """주간 시간표. 학기별로 따로 보관해 지난 학기 것도 남는다."""
    data = read_json(workspace.timetable_path, {})
    if not isinstance(data, dict):
        data = {}
    entries = data.get("entries")
    return {
        "entries": entries if isinstance(entries, list) else [],
        "semester": str(data.get("semester", "")),
    }


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
    }
    if entry_id:
        entries = [entry if e.get("id") == entry_id else e for e in entries]
    else:
        entries.append(entry)

    workspace.root.mkdir(parents=True, exist_ok=True)
    workspace.timetable_path.write_text(
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
    workspace.timetable_path.write_text(
        json.dumps({"entries": remaining, "semester": data["semester"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"ok": True, "entries": remaining}


def get_academic_calendar(workspace: UserWorkspace, year: int | None = None, refresh: bool = False) -> dict[str, Any]:
    """DGIST 학사일정. 자주 바뀌지 않으니 하루 한 번만 받아 온다."""
    import academic_calendar

    year = int(year or datetime.now().year)
    cache = read_json(workspace.academic_path, {}) or {}
    entry = cache.get(str(year)) if isinstance(cache, dict) else None
    fresh_enough = False
    if entry and not refresh:
        try:
            fetched = datetime.fromisoformat(entry.get("fetchedAt", ""))
            fresh_enough = (datetime.now() - fetched).total_seconds() < 86400
        except ValueError:
            fresh_enough = False
    def with_semester(payload: dict[str, Any]) -> dict[str, Any]:
        """지금이 몇 학기인지 함께 담아 준다. 시간표가 이 값에 맞춰 움직인다."""
        try:
            payload["semester"] = academic_calendar.current_semester(payload.get("events", []))
        except Exception:
            payload["semester"] = {}
        return payload

    if entry and fresh_enough:
        return with_semester(
            {"ok": True, "year": year, "cached": True, **{k: v for k, v in entry.items() if k != "fetchedAt"}}
        )

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
    workspace.academic_path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return with_semester(result)


def search_directory_api(workspace: UserWorkspace, query: str) -> dict[str, Any]:
    """조직도에서 사람 찾기. 받은 메일 연락처와 합쳐서 돌려준다."""
    import directory

    people = directory.load_directory(workspace.directory_path)
    hits = directory.search_directory(people, query, limit=8)
    return {"ok": True, "total": len(people), "results": hits}


def import_directory(workspace: UserWorkspace, people: list[dict[str, Any]]) -> dict[str, Any]:
    import directory

    if not isinstance(people, list) or not people:
        raise ValueError("가져올 사람 목록이 비어 있습니다.")
    return directory.save_directory(workspace.directory_path, people)


def get_course_catalog(
    workspace: UserWorkspace, year_term: str, undergraduate: bool, refresh: bool = False
) -> dict[str, Any]:
    """개설과목 목록. 학기 중에는 거의 바뀌지 않으니 하루 캐시를 둔다."""
    import timetable_import

    key = f"{year_term or 'auto'}|{'under' if undergraduate else 'grad'}"
    cache = read_json(workspace.catalog_path, {}) or {}
    entry = cache.get(key) if isinstance(cache, dict) else None
    if entry and not refresh:
        try:
            fetched = datetime.fromisoformat(entry.get("fetchedAt", ""))
            if (datetime.now() - fetched).total_seconds() < 86400:
                return {"cached": True, **{k: v for k, v in entry.items() if k != "fetchedAt"}}
        except ValueError:
            pass

    result = timetable_import.fetch_dgist_catalog(
        year_term=year_term, undergraduate=undergraduate
    )
    if result.get("ok") and result.get("courses"):
        if not isinstance(cache, dict):
            cache = {}
        cache[key] = {**result, "fetchedAt": datetime.now().isoformat(timespec="seconds")}
        workspace.catalog_path.write_text(
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

    workspace.notices_path.write_text(
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
    entry = {
        "id": event_id or f"my-{secrets.token_hex(6)}",
        "title": title[:200],
        "date": date,                                   # YYYY-MM-DD
        "time": str(payload.get("time", "")).strip(),   # HH:MM (빈 값이면 종일)
        "note": str(payload.get("note", "")).strip()[:500],
        "updatedAt": now_iso(),
    }
    if event_id:
        events = [entry if e.get("id") == event_id else e for e in events]
    else:
        events.append(entry)

    workspace.root.mkdir(parents=True, exist_ok=True)
    workspace.my_events_path.write_text(
        json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"ok": True, "event": entry, "events": events}


def delete_my_event(workspace: UserWorkspace, event_id: str) -> dict[str, Any]:
    events = get_my_events(workspace)["events"]
    remaining = [e for e in events if e.get("id") != event_id]
    workspace.root.mkdir(parents=True, exist_ok=True)
    workspace.my_events_path.write_text(
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
    }


def save_upload_selection(workspace: UserWorkspace, payload: dict[str, Any]) -> dict[str, Any]:
    courses = payload.get("courses")
    if not isinstance(courses, dict):
        courses = {}
    cleaned = {str(name): bool(enabled) for name, enabled in courses.items()}
    hidden = _clean_hidden(payload.get("hidden"))
    hidden_deadlines = _clean_hidden(payload.get("hiddenDeadlines"))
    workspace.root.mkdir(parents=True, exist_ok=True)
    workspace.upload_selection_path.write_text(
        json.dumps(
            {"courses": cleaned, "hidden": hidden, "hiddenDeadlines": hidden_deadlines},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"courses": cleaned, "hidden": hidden, "hiddenDeadlines": hidden_deadlines}


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
        "autoIntervalMinutes": int(config.get("AUTO_INTERVAL_MINUTES", 0) or 0),
        "autoIntervalKind": config.get("AUTO_INTERVAL_KIND", "emails"),
        "gcalSyncEnabled": bool(config.get("GCAL_SYNC_ENABLED", False)),
        "gcalCalendarName": config.get("GCAL_CALENDAR_NAME", "DGIST 메일 일정"),
        "interests": config.get("EMAIL_INTERESTS", "전공 탐색, 취업, 음악, 세미나"),
        "interestTags": config.get("EMAIL_INTEREST_TAGS", []),
        "interestsCustom": config.get("EMAIL_INTERESTS_CUSTOM", ""),
        "hidePastEmails": bool(config.get("EMAIL_HIDE_PAST", False)),
        "localSavePath": config.get("LOCAL_SAVE_PATH", ""),
        "hasLmsPassword": bool(config.get("LMS_PASSWORD")),
        "hasGeminiKey": bool(config.get("GEMINI_API_KEY")),
        "hasEmailPassword": bool(config.get("EMAIL_PASSWORD")),
        "hasSchoolEmailPassword": bool(config.get("SCHOOL_EMAIL_PASSWORD")),
    }


def append_log(user_id: str, line: str) -> None:
    with task_lock:
        task_state = task_states.setdefault(user_id, default_task_state())
        task_state["logs"].append(line.rstrip())
        task_state["logs"] = task_state["logs"][-500:]


def run_process(workspace: UserWorkspace, kind: str, command: list[str], extra_env: dict[str, str] | None = None) -> None:
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
                "logs": [f"[{now_iso()}] {kind} 작업을 시작합니다."],
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

    # 성공/실패 기록 (조용한 실패를 사용자에게 알리기 위함)
    if kind in ("sync", "emails", "deadlines"):
        health = record_task_result(workspace, kind, return_code)
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
        emails = get_emails(workspace).get("emails", [])
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


def start_task(workspace: UserWorkspace, kind: str, sync_mode: str = "fast") -> tuple[bool, str]:
    with task_lock:
        task_state = task_states.setdefault(workspace.user_id, default_task_state())
        if task_state["running"]:
            return False, "이미 실행 중인 작업이 있습니다."

    extra_env = {}
    if kind == "sync":
        extra_env["AUTOSAVER_SYNC_MODE"] = "full" if sync_mode == "full" else "fast"

    if kind == "sync":
        command = [
            sys.executable,
            "-u",
            "-c",
            "import asyncio; import main; asyncio.run(main.run_job())",
        ]
    elif kind == "verify":
        command = [sys.executable, "-u", "verify.py"]
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
    thread = threading.Thread(target=run_process, args=(workspace, kind, command, extra_env), daemon=True)
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

    def send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
        if route == "/api/directory":
            try:
                self.send_json(
                    search_directory_api(workspace, params.get("q", [""])[0])
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
        super().do_GET()

    def serve_download(self, workspace: UserWorkspace, name: str) -> None:
        """다운로드 폴더의 파일을 첨부파일로 전송 (브라우저 모드용)."""
        safe_name = Path(str(name)).name
        if not safe_name:
            self.send_json({"ok": False, "message": "파일 이름이 필요합니다."}, HTTPStatus.BAD_REQUEST)
            return
        download_path = get_download_path(workspace).resolve()
        file_path = (download_path / safe_name).resolve()
        if not str(file_path).startswith(str(download_path)) or not file_path.is_file():
            self.send_json({"ok": False, "message": "파일을 찾을 수 없습니다."}, HTTPStatus.NOT_FOUND)
            return

        metadata = read_json(workspace.file_metadata_log, {})
        meta = metadata.get(safe_name, {}) if isinstance(metadata, dict) else {}
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
            try:
                import updater
                result = updater.apply_update()
                if result.get("ok"):
                    result["message"] = f"{result['count']}개 파일을 업데이트했습니다. 앱을 재시작하면 적용됩니다."
                    result["needsRestart"] = True
                else:
                    result["message"] = "업데이트할 파일을 받지 못했습니다."
                self.send_json(result)
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
        if route in ("/api/mark-read", "/api/mark-all-read", "/api/delete-email"):
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
                else:  # delete
                    email_reader.delete_message(int(uid), folder)
                    patch_email_local(workspace, int(uid), folder, remove=True)
                    self.send_json({"ok": True, "message": "메일을 삭제했습니다."})
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
                import tkinter
                from tkinter import filedialog

                root_widget = tkinter.Tk()
                root_widget.withdraw()
                root_widget.attributes("-topmost", True)
                selected = filedialog.askdirectory(title="로컬 저장 폴더 선택")
                root_widget.destroy()
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
        if route == "/api/timetable/bulk":
            try:
                payload = self.read_body_json()
                entries = payload.get("entries", [])
                if not isinstance(entries, list) or not entries:
                    raise ValueError("추가할 수업이 없습니다.")
                if payload.get("replace"):
                    workspace.timetable_path.write_text(
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
                emails = get_emails(workspace).get("emails", [])
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
                source = (download_path / safe_name).resolve()
                if not safe_name or not str(source).startswith(str(download_path)) or not source.is_file():
                    failed.append(safe_name or str(raw_name))
                    continue
                meta = metadata.get(safe_name, {})
                display_name = str(meta.get("original_name", safe_name)) if isinstance(meta, dict) else safe_name
                target = target_dir / display_name
                stem, suffix = target.stem, target.suffix
                counter = 2
                while target.exists():
                    target = target_dir / f"{stem} ({counter}){suffix}"
                    counter += 1
                shutil.copy2(source, target)
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
            target.write_text(content, encoding="utf-8")
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
            os.startfile(str(download_path))
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
