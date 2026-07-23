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
import secrets
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
GOOGLE_OAUTH_SCOPE = "https://www.googleapis.com/auth/drive.file"
GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"
# Drive 업로드 + 캘린더 동기화를 함께 사용하므로 두 권한을 같이 요청한다.
GOOGLE_OAUTH_SCOPES = [GOOGLE_OAUTH_SCOPE, GOOGLE_CALENDAR_SCOPE]
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

    workspace.root.mkdir(parents=True, exist_ok=True)
    workspace.config_path.write_text(
        json.dumps(values, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    Path(download_path).mkdir(parents=True, exist_ok=True)
    ensure_data_files(workspace)
    return values


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
        rows.append(
            {
                "name": display_name,
                "localName": name,
                "course": course,
                "courseLabel": extract_course_label(course),
                "folder": folder or ("샘플 데이터" if source == "sample" else "강의 자료"),
                "type": extension.upper(),
                "status": "local" if exists_locally else ("sample" if source == "sample" else "missing"),
                "size": file_path.stat().st_size if exists_locally else None,
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
    }


def save_upload_selection(workspace: UserWorkspace, payload: dict[str, Any]) -> dict[str, Any]:
    courses = payload.get("courses")
    if not isinstance(courses, dict):
        courses = {}
    cleaned = {str(name): bool(enabled) for name, enabled in courses.items()}
    hidden = _clean_hidden(payload.get("hidden"))
    workspace.root.mkdir(parents=True, exist_ok=True)
    workspace.upload_selection_path.write_text(
        json.dumps({"courses": cleaned, "hidden": hidden}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"courses": cleaned, "hidden": hidden}


def get_status(workspace: UserWorkspace, base_url: str | None = None) -> dict[str, Any]:
    config = read_config(workspace)
    files = get_files(workspace)
    google_oauth = get_google_oauth_status(workspace, base_url)
    courses = sorted({item["courseLabel"] for item in files})
    downloaded_log = read_json(workspace.downloaded_files_log, [])
    download_path = get_download_path(workspace, config)
    downloaded_files = []
    if download_path.exists():
        downloaded_files = [item for item in download_path.iterdir() if item.is_file()]

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
                    result["message"] = f"{result['count']}개 파일을 업데이트했습니다. 앱을 재시작해 주세요."
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
