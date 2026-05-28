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


def _load_config() -> dict[str, Any]:
    if CONFIG_JSON_PATH.exists():
        return _read_json(CONFIG_JSON_PATH)
    if os.environ.get("AUTOSAVER_CONFIG_PATH") or os.environ.get("AUTOSAVER_DISABLE_LEGACY_CONFIG"):
        return {}
    return _read_legacy_config()


_CONFIG = _load_config()

LMS_ID = str(_CONFIG.get("LMS_ID", ""))
LMS_PASSWORD = str(_CONFIG.get("LMS_PASSWORD", ""))
GEMINI_API_KEY = str(_CONFIG.get("GEMINI_API_KEY", ""))
EMAIL_ADDRESS = str(_CONFIG.get("EMAIL_ADDRESS", ""))
EMAIL_PASSWORD = str(_CONFIG.get("EMAIL_PASSWORD", ""))
EMAIL_TO = str(_CONFIG.get("EMAIL_TO", EMAIL_ADDRESS))
SCHEDULE_TIME = str(_CONFIG.get("SCHEDULE_TIME", "08:00"))
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

GOOGLE_CLIENT_SECRETS_PATH = str(
    Path(
        os.environ.get(
            "AUTOSAVER_GOOGLE_CLIENT_SECRETS",
            str(_default_root() / "credentials.json"),
        )
    )
)
GOOGLE_TOKEN_PATH = str(AUTOSAVER_DATA_ROOT / "token.json")

PLAYWRIGHT_HEADLESS = os.environ.get("AUTOSAVER_HEADLESS", "1").lower() not in {
    "0",
    "false",
    "no",
    "off",
}
