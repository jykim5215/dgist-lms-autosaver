"""DGIST LMS AutoSaver 데스크톱 앱.

웹 브라우저/터미널 없이 더블클릭으로 실행되는 네이티브 창 버전입니다.

동작 방식:
- 127.0.0.1:8765에 대시보드 서버를 백그라운드 스레드로 띄운 뒤
  네이티브 창(WebView2)으로 감쌉니다.
- 이미 앱이 떠 있어 포트가 사용 중이면 새 서버를 띄우지 않고
  기존 서버에 창만 하나 더 엽니다. (중복 실행해도 안전)
- 창을 닫으면 이 프로세스가 띄운 서버도 함께 종료됩니다.

실행:
    pythonw app.py   (또는 바탕화면의 "DGIST LMS AutoSaver" 바로가기)
"""
from __future__ import annotations

import os
import socket
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# 데스크톱 모드에서는 web_ui가 기본 브라우저를 열지 않도록 고정
os.environ.setdefault("AUTOSAVER_OPEN_BROWSER", "0")

from http.server import ThreadingHTTPServer

import web_ui

HOST = "127.0.0.1"
PORT = int(os.environ.get("AUTOSAVER_UI_PORT", "8765"))
WINDOW_TITLE = "DGIST LMS AutoSaver"
APP_ICON = Path(__file__).resolve().parent / "web" / "app.png"


def notify(title: str, message: str) -> None:
    """Windows 토스트 알림 (winotify 미설치/실패 시 조용히 무시)."""
    try:
        from winotify import Notification

        toast = Notification(
            app_id=WINDOW_TITLE,
            title=title,
            msg=message[:200],
            icon=str(APP_ICON) if APP_ICON.exists() else "",
        )
        toast.show()
    except Exception:
        pass


def upcoming_deadline_summary(workspace, hours: int = 48) -> str:
    """N시간 내 미제출 마감 요약 문자열 (없으면 빈 문자열)."""
    deadlines = web_ui.get_deadlines(workspace)
    now = datetime.now().astimezone()
    soon = []
    for item in deadlines.get("items", []):
        if item.get("myStatus") in ("Graded", "NeedsGrading"):
            continue
        due_raw = item.get("due")
        if not due_raw:
            continue
        try:
            due = datetime.fromisoformat(str(due_raw).replace("Z", "+00:00")).astimezone()
        except ValueError:
            continue
        delta = (due - now).total_seconds()
        if 0 <= delta <= hours * 3600:
            soon.append((due, item))
    if not soon:
        return ""
    soon.sort(key=lambda pair: pair[0])
    lines = [
        f"· {item.get('name', '과제')} ({due.strftime('%m/%d %H:%M')})"
        for due, item in soon[:4]
    ]
    if len(soon) > 4:
        lines.append(f"… 외 {len(soon) - 4}건")
    return "\n".join(lines)


def downloaded_count(workspace) -> int:
    data = web_ui.read_json(workspace.downloaded_files_log, [])
    return len(data) if isinstance(data, list) else 0


def run_scheduled_sync(workspace) -> None:
    """예약 동기화 실행 후 결과를 토스트로 알림."""
    before = downloaded_count(workspace)
    ok, _message = web_ui.start_task(workspace, "sync")
    if not ok:
        return
    # 작업 종료 대기 (최대 30분)
    for _ in range(360):
        time.sleep(5)
        with web_ui.task_lock:
            task = web_ui.task_states.get(workspace.user_id, {})
            if not task.get("running"):
                break
    new_count = downloaded_count(workspace) - before
    if new_count > 0:
        notify("자동 동기화 완료", f"새 자료 {new_count}건을 받았습니다.")
    else:
        notify("자동 동기화 완료", "새 자료가 없습니다.")
    summary = upcoming_deadline_summary(workspace)
    if summary:
        notify("과제 마감 임박", summary)


def scheduler_loop() -> None:
    """앱이 켜져 있는 동안 매일 예약 시간(SCHEDULE_TIME)에 자동 동기화."""
    workspace = web_ui.workspace_for_user("local")
    # 앱 시작 시점에 이미 예약 시간이 지났다면 오늘은 건너뜀 (켤 때마다 동기화 방지)
    last_run_day = None
    try:
        config = web_ui.read_config(workspace)
        schedule_time = str(config.get("SCHEDULE_TIME", "08:00")).strip() or "08:00"
        if datetime.now().strftime("%H:%M") >= schedule_time:
            last_run_day = datetime.now().strftime("%Y-%m-%d")
    except Exception:
        pass
    while True:
        try:
            config = web_ui.read_config(workspace)
            schedule_time = str(config.get("SCHEDULE_TIME", "08:00")).strip() or "08:00"
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            if now.strftime("%H:%M") >= schedule_time and last_run_day != today:
                with web_ui.task_lock:
                    running = web_ui.task_states.get(workspace.user_id, {}).get("running", False)
                if not running:
                    last_run_day = today
                    run_scheduled_sync(workspace)
        except Exception:
            pass
        time.sleep(30)


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def existing_dashboard(host: str, port: int) -> bool:
    """포트를 점유한 프로세스가 이 앱의 대시보드인지 확인."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/healthz", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_server() -> ThreadingHTTPServer | None:
    """서버를 띄우고 반환. 이미 대시보드가 떠 있으면 None."""
    if port_in_use(HOST, PORT):
        if existing_dashboard(HOST, PORT):
            return None
        raise RuntimeError(
            f"포트 {PORT}를 다른 프로그램이 사용 중입니다. "
            "AUTOSAVER_UI_PORT 환경 변수로 포트를 바꿔 주세요."
        )

    web_ui.ensure_data_files(web_ui.workspace_for_user("local"))
    server = ThreadingHTTPServer((HOST, PORT), web_ui.DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main() -> None:
    import webview

    try:
        server = start_server()
    except RuntimeError as exc:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, str(exc), WINDOW_TITLE, 0x10)
        return

    try:
        webview.settings["ALLOW_DOWNLOADS"] = True
    except Exception:
        pass

    # 이 프로세스가 서버 주인일 때만 스케줄러/알림 가동 (창만 띄운 경우 제외)
    if server is not None:
        threading.Thread(target=scheduler_loop, daemon=True).start()

        def startup_notice():
            time.sleep(3)
            summary = upcoming_deadline_summary(web_ui.workspace_for_user("local"))
            if summary:
                notify("과제 마감 임박 (48시간 이내)", summary)

        threading.Thread(target=startup_notice, daemon=True).start()

    url = f"http://{HOST}:{PORT}"
    webview.create_window(
        WINDOW_TITLE,
        url,
        width=1320,
        height=880,
        min_size=(900, 640),
    )
    try:
        webview.start()
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
