"""Runtime configuration shared by the web UI and background workers.

The original project used a single project-level config.py and a single
C:\\lms-autosaver data directory.  For hosted use, the web UI launches each
user's worker process with AUTOSAVER_CONFIG_PATH and AUTOSAVER_DATA_ROOT so
their LMS credentials, Drive token, downloads, and logs stay isolated.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent


def atomic_write_text(path: Any, text: str, encoding: str = "utf-8") -> int:
    """임시 파일에 다 쓴 뒤 한 번에 바꿔 끼운다.

    예전에는 작업 프로세스가 file_metadata.json 을 제자리에서 다시 쓰는 동안 화면 서버가
    반쯤 쓰인 파일을 읽어 JSON 오류 → '자료 0개' 로 보이고, 그 결과가 30초 캐시에 남았다
    (2026-09-24 동기화 중 '자료가 다 없어짐'). 바꿔 끼우기는 읽는 쪽이 늘 온전한 파일을 본다.
    Windows 에서는 다른 프로세스가 파일을 열고 있으면 교체가 잠깐 거절되므로 몇 번 다시 한다.
    """
    import threading
    import time

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with open(tmp, "w", encoding=encoding) as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    for _ in range(40):
        try:
            os.replace(tmp, target)
            return len(text)
        except PermissionError:
            time.sleep(0.05)
    try:
        os.replace(tmp, target)
    except OSError:
        try:
            os.remove(tmp)
        finally:
            raise
    return len(text)


def atomic_write_json(path: Any, data: Any, **dump_kwargs: Any) -> None:
    atomic_write_text(path, json.dumps(data, **dump_kwargs))


def _default_root() -> Path:
    if os.name == "nt":
        return Path(r"C:\lms-autosaver")
    return Path.home() / ".lms-autosaver"


AUTOSAVER_DATA_ROOT = Path(os.environ.get("AUTOSAVER_DATA_ROOT", str(_default_root())))
CONFIG_JSON_PATH = Path(
    os.environ.get("AUTOSAVER_CONFIG_PATH", str(AUTOSAVER_DATA_ROOT / "config.json"))
)
LEGACY_CONFIG_PATH = PROJECT_ROOT / "config.py"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _read_legacy_config() -> dict[str, Any]:
    if not LEGACY_CONFIG_PATH.exists():
        return {}
    try:
        tree = ast.parse(LEGACY_CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError):
        return {}

    values: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    pass
    return values


DPAPI_PREFIX = "dpapi:"
# web_ui.SECRET_KEYS 와 같아야 한다. 여기서 빠지면 설정 화면이 암호화해 저장한 값을
# 작업 프로세스와 dgist_api 가 'dpapi:...' 암호문 그대로 받아 API 호출이 실패한다.
SECRET_KEYS = ("LMS_PASSWORD", "EMAIL_PASSWORD", "SCHOOL_EMAIL_PASSWORD", "GEMINI_API_KEY", "DGIST_API_KEY")


def _dpapi_unprotect(text: str) -> str:
    """설정에 저장된 DPAPI 암호문을 푼다.

    이 모듈은 크롤러/메일 리더 같은 별도 프로세스에서도 쓰이므로,
    여기서 복호하지 않으면 암호문이 그대로 비밀번호로 들어가 로그인이 실패한다.
    """
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
        blob_in = BLOB(
            len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char))
        )
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


def _load_config() -> dict[str, Any]:
    if CONFIG_JSON_PATH.exists():
        data = _read_json(CONFIG_JSON_PATH)
    elif os.environ.get("AUTOSAVER_CONFIG_PATH") or os.environ.get(
        "AUTOSAVER_DISABLE_LEGACY_CONFIG"
    ):
        data = {}
    else:
        data = _read_legacy_config()
    for key in SECRET_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.startswith(DPAPI_PREFIX):
            data[key] = _dpapi_unprotect(value)
    return data


_CONFIG = _load_config()

LMS_ID = str(_CONFIG.get("LMS_ID", ""))
LMS_PASSWORD = str(_CONFIG.get("LMS_PASSWORD", ""))
GEMINI_API_KEY = str(_CONFIG.get("GEMINI_API_KEY", ""))
# 공공데이터포털(data.go.kr) 인증키 — 개설강좌·학사일정·세미나 조회에 쓴다
DGIST_API_KEY = str(_CONFIG.get("DGIST_API_KEY", ""))
EMAIL_ADDRESS = str(_CONFIG.get("EMAIL_ADDRESS", ""))
EMAIL_PASSWORD = str(_CONFIG.get("EMAIL_PASSWORD", ""))
EMAIL_TO = str(_CONFIG.get("EMAIL_TO", EMAIL_ADDRESS))
SCHEDULE_TIME = str(_CONFIG.get("SCHEDULE_TIME", "08:00"))
SCHOOL_EMAIL = str(_CONFIG.get("SCHOOL_EMAIL", ""))
SCHOOL_EMAIL_PASSWORD = str(_CONFIG.get("SCHOOL_EMAIL_PASSWORD", ""))
SCHOOL_IMAP_HOST = str(_CONFIG.get("SCHOOL_IMAP_HOST", "mail.dgist.ac.kr"))
SCHOOL_IMAP_PORT = int(_CONFIG.get("SCHOOL_IMAP_PORT", 993))
SCHOOL_SMTP_HOST = str(_CONFIG.get("SCHOOL_SMTP_HOST", "smtp.dgist.ac.kr"))
SCHOOL_SMTP_PORT = int(_CONFIG.get("SCHOOL_SMTP_PORT", 465))
EMAIL_INTERESTS = str(_CONFIG.get("EMAIL_INTERESTS", "전공 탐색, 취업, 음악, 세미나"))
LOCAL_SAVE_PATH = str(_CONFIG.get("LOCAL_SAVE_PATH", ""))
# 동기화 때 구글 드라이브에도 올릴지. 예전 설정에는 이 키가 없고, 그때는 늘 올렸다.
DRIVE_UPLOAD = _CONFIG.get("AUTO_DRIVE_UPLOAD", True) is not False
LMS_URL = str(_CONFIG.get("LMS_URL", "https://lms.dgist.ac.kr"))
LOGIN_URL = str(
    _CONFIG.get(
        "LOGIN_URL",
        "https://saml.dgist.ac.kr/authentication/idpw/idPwLogin.html?agentId=-100000&useOauth=0",
    )
)

DOWNLOAD_PATH = str(_CONFIG.get("DOWNLOAD_PATH", str(AUTOSAVER_DATA_ROOT / "downloads")))
DOWNLOADED_FILES_LOG = str(AUTOSAVER_DATA_ROOT / "downloaded_files.json")
FILE_METADATA_LOG = str(AUTOSAVER_DATA_ROOT / "file_metadata.json")
DEADLINES_LOG = str(AUTOSAVER_DATA_ROOT / "deadlines.json")
UPLOAD_SELECTION_PATH = str(AUTOSAVER_DATA_ROOT / "upload_selection.json")
LAST_SYNC_PATH = str(AUTOSAVER_DATA_ROOT / "last_sync.json")
COURSES_STATE_PATH = str(AUTOSAVER_DATA_ROOT / "courses_state.json")

SYNC_MODE = os.environ.get("AUTOSAVER_SYNC_MODE", "fast").strip().lower()


def extract_course_label(value: Any) -> str:
    """'일반화학Ⅰ (General chemistryⅠ )_03[ 2026_1학기 ]' → 'General chemistryⅠ'."""
    text = str(value or "").strip()
    if "(" in text and ")" in text:
        inside = text.split("(", 1)[1].split(")", 1)[0].strip()
        if inside:
            return inside
    if "[" in text:
        text = text.split("[", 1)[0].strip()
    return text or "기타"


def load_upload_selection() -> dict[str, Any]:
    """과목별 Drive 업로드 선택 상태. {"courses": {label: bool}} 형식, 기본은 전체 허용."""
    data = _read_json(Path(UPLOAD_SELECTION_PATH))
    courses = data.get("courses") if isinstance(data, dict) else None
    return {"courses": courses if isinstance(courses, dict) else {}}


def course_upload_enabled(course_name: Any, selection: dict[str, Any] | None = None) -> bool:
    selection = selection if selection is not None else load_upload_selection()
    label = extract_course_label(course_name)
    return bool(selection.get("courses", {}).get(label, True))

GOOGLE_CLIENT_SECRETS_PATH = str(
    Path(
        os.environ.get(
            "AUTOSAVER_GOOGLE_CLIENT_SECRETS",
            str(_default_root() / "credentials.json"),
        )
    )
)
GOOGLE_TOKEN_PATH = str(AUTOSAVER_DATA_ROOT / "token.json")

# 구글 권한 목록은 여기 한 곳에서만 정한다.
# Drive와 캘린더가 token.json 한 파일을 같이 쓰기 때문에, 한쪽이 자기 권한만
# 요청해서 파일을 덮어쓰면 다른 쪽 권한이 사라진다. (실제로 그래서
# 동기화를 돌릴 때마다 캘린더 권한이 날아가 학사일정 업로드가 막혔다)
GOOGLE_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"
GOOGLE_SCOPES = [GOOGLE_DRIVE_SCOPE, GOOGLE_CALENDAR_SCOPE]

PLAYWRIGHT_HEADLESS = os.environ.get("AUTOSAVER_HEADLESS", "1").lower() not in {
    "0",
    "false",
    "no",
    "off",
}

# ===== 하위 작업(새로고침·동기화) 실행 방식 =====
# 소스로 돌 때는 `python -c "..."` 로 하위 프로세스를 띄우면 된다.
# 그런데 EXE 로 묶이면 sys.executable 이 '붕어빵.exe' 라서, 같은 방식으로 부르면
# -c 가 무시된 채 앱이 통째로 다시 켜진다. (새로고침할 때마다 창이 하나씩 더 뜨고,
#  정작 크롤링은 돌지 않는다) 그래서 EXE 일 때는 이 인자를 붙여
# app.py 가 창을 띄우지 않고 작업만 하고 끝나도록 한다.
WORKER_FLAG = "--autosaver-job"
