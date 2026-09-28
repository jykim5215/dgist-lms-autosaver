r"""소스 코드 그대로 대시보드를 8794 포트에 띄운다 (설치본과 섞이지 않게).

    .venv\Scripts\python.exe scripts\dev_server.py

설치된 앱과 같은 데이터(C:\lms-autosaver)를 쓴다. 화면만 보고 고칠 때 쓰고,
동기화·삼성 노트 같은 쓰기 작업은 설치된 앱과 동시에 돌리지 않는다.
"""
import os
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))
os.chdir(PROJ)
os.environ.setdefault("AUTOSAVER_DATA_ROOT", r"C:\lms-autosaver")
os.environ.setdefault("AUTOSAVER_CONFIG_PATH", r"C:\lms-autosaver\config.json")
os.environ["AUTOSAVER_OPEN_BROWSER"] = "0"
PORT = int(os.environ.get("AUTOSAVER_DEV_PORT", "8794"))

import web_ui  # noqa: E402  (경로를 잡은 뒤에 불러야 한다)

workspace = web_ui.workspace_for_user("local")
web_ui.ensure_data_files(workspace)
print("web root:", web_ui.WEB_ROOT, flush=True)
server = ThreadingHTTPServer(("127.0.0.1", PORT), web_ui.DashboardHandler)
print(f"listening on {PORT}", flush=True)
server.serve_forever()
