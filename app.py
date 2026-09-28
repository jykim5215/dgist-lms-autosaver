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
import sys
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
WINDOW_TITLE = "붕어빵"
# 작업표시줄이 pythonw.exe나 옛 캐시가 아니라 이 앱을 별도 앱으로 인식하게 하는 식별자.
# 바로가기(install.ps1)에도 같은 값을 넣어야 아이콘이 완전히 일치한다.
APP_USER_MODEL_ID = "DGIST.Bungeoppang.App"
# EXE 로 묶이면 화면 파일이 exe 옆 _internal 로 들어간다. 그때는 __file__ 이
# 아니라 sys._MEIPASS 를 봐야 아이콘을 찾는다.
_APP_ROOT = Path(getattr(sys, "_MEIPASS", "") or Path(__file__).resolve().parent)
APP_ICON = _APP_ROOT / "web" / "app.png"


APP_ICO = _APP_ROOT / "web" / "app.ico"


def set_app_user_model_id() -> None:
    """창을 만들기 '전에' 호출해야 작업표시줄 아이콘이 창 아이콘을 따라온다.

    이걸 지정하지 않으면 Windows가 여러 pythonw 창을 하나로 묶고,
    실행에 쓰인 바로가기의 (옛) 캐시 아이콘을 그대로 보여 준다.
    """
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def apply_window_icon(timeout: float = 15.0) -> bool:
    """pywebview 창에 앱 아이콘을 입힌다 (Windows 전용).

    pywebview의 create_window에는 아이콘 인자가 없어서, 창이 만들어진 뒤
    Win32 WM_SETICON으로 직접 설정한다. 이걸 하지 않으면 창과 작업표시줄에
    pythonw.exe의 기본 파이썬 아이콘이 그대로 노출된다.
    """
    if os.name != "nt" or not APP_ICO.exists():
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        IMAGE_ICON, LR_LOADFROMFILE = 1, 0x0010
        WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1

        deadline = time.time() + timeout
        hwnd = 0
        while time.time() < deadline:
            hwnd = user32.FindWindowW(None, WINDOW_TITLE)
            if hwnd:
                break
            time.sleep(0.3)
        if not hwnd:
            return False

        path = str(APP_ICO)
        big = user32.LoadImageW(None, path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        small = user32.LoadImageW(None, path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        if big:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, big)
        if small:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small)
        return bool(big or small)
    except Exception:
        return False


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


# ===== 마감 알림 · 새 자료 알림 =====
# 예전 알림은 예약 동기화마다 '새 자료가 없습니다' 를, 켤 때마다 48시간 마감 요약을 띄워
# 쓸모 없이 자주 떴다. 이제 꼭 필요할 때만: 마감은 하루·3시간·1시간 전에 한 번씩,
# 자료는 새로 들어오거나 고쳐 다시 올라왔을 때만. 무엇을 알렸는지는 alerts.json 에 적어 두 번 알리지 않는다.
DEADLINE_ALERT_HOURS = ((1, "1시간"), (3, "3시간"), (24, "하루"))  # 가까운 것부터


def _alerts_path(workspace):
    return workspace.root / "alerts.json"


def _load_alerts(workspace) -> dict:
    data = web_ui.read_json(_alerts_path(workspace), {})
    return data if isinstance(data, dict) else {}


def _save_alerts(workspace, data: dict) -> None:
    import json

    web_ui.atomic_write_text(_alerts_path(workspace), json.dumps(data, ensure_ascii=False))


def _alert_on(config: dict, key: str) -> bool:
    return config.get(key, True) is not False


def check_deadline_alerts(workspace, config: dict) -> None:
    """안 낸 과제가 하루·3시간·1시간 안으로 들어오면 알린다. 늦게 켜졌으면 지금 해당하는 가장 가까운 것 하나만."""
    if not _alert_on(config, "NOTIFY_DEADLINES"):
        return
    now = datetime.now().astimezone()
    data = _load_alerts(workspace)
    sent = data.setdefault("sent", {})
    hits = []
    for item in web_ui.get_deadlines(workspace).get("items", []):
        if item.get("myStatus") in ("Graded", "NeedsGrading"):
            continue
        try:
            due = datetime.fromisoformat(str(item.get("due") or "").replace("Z", "+00:00")).astimezone()
        except ValueError:
            continue
        left = (due - now).total_seconds()
        if left <= 0 or left > 24 * 3600:
            continue
        # 마감이 바뀌면 다시 알리도록 마감 시각까지 열쇠에 넣는다
        base = f"{item.get('courseId')}:{item.get('columnId') or item.get('name')}:{due.isoformat()}"
        for hours, label in DEADLINE_ALERT_HOURS:
            if left <= hours * 3600:
                key = f"{base}:{hours}"
                if key not in sent:
                    sent[key] = now.isoformat(timespec="seconds")
                    hits.append((due, label, item))
                break
    # 지난 지 사흘 넘은 기록은 치운다
    for key in list(sent):
        try:
            due_part = key.rsplit(":", 1)[0].split(":", 2)[2]
            if (now - datetime.fromisoformat(due_part)).days > 3:
                del sent[key]
        except (IndexError, ValueError):
            continue
    if not hits:
        return
    _save_alerts(workspace, data)
    hits.sort(key=lambda h: h[0])

    def line(due, item):
        course = item.get("courseLabel") or web_ui.extract_course_label(item.get("course", ""))
        when = "오늘" if due.date() == now.date() else "내일" if (due.date() - now.date()).days == 1 else due.strftime("%m/%d")
        return f"{course} · {item.get('name', '과제')} ({when} {due.strftime('%H:%M')})"

    if len(hits) == 1:
        due, label, item = hits[0]
        notify(f"과제 마감 {label} 전", line(due, item))
    else:
        text = "\n".join(line(d, i) for d, _, i in hits[:4])
        if len(hits) > 4:
            text += f"\n… 외 {len(hits) - 4}건"
        notify(f"과제 마감 {len(hits)}건 임박", text)


def _current_files(workspace) -> dict:
    """받아 둔 자료: 이름 → (크기). 크기가 바뀌면 교수가 고쳐 다시 올린 것."""
    meta = web_ui.read_json(workspace.file_metadata_log, None)
    if not isinstance(meta, dict):
        return {}
    base = web_ui.get_download_path(workspace)
    out = {}
    for name, info in meta.items():
        try:
            size = (base / web_ui.stored_relpath(name, info)).stat().st_size
        except OSError:
            continue
        out[name] = size
    return out


def check_new_file_alerts(workspace, config: dict) -> None:
    """동기화가 끝난 뒤 새로 들어온 자료·새 판을 알린다. 처음에는 지금 있는 것을 기억만 한다."""
    with web_ui.task_lock:
        if web_ui.task_states.get(workspace.user_id, {}).get("running"):
            return  # 받는 중에는 반쯤 들어온 목록으로 알리지 않는다
    current = _current_files(workspace)
    if not current:
        return
    data = _load_alerts(workspace)
    known = data.get("files")
    if not isinstance(known, dict):
        data["files"] = current
        _save_alerts(workspace, data)
        return
    new = [n for n in current if n not in known]
    changed = [n for n in current if n in known and known[n] and known[n] != current[n]]
    if current == known:
        return
    data["files"] = current
    _save_alerts(workspace, data)
    if not (new or changed) or not _alert_on(config, "NOTIFY_NEW_FILES"):
        return
    meta = web_ui.read_json(workspace.file_metadata_log, {}) or {}

    def line(name, tag=""):
        info = meta.get(name) if isinstance(meta.get(name), dict) else {}
        course = web_ui.extract_course_label(info.get("course", ""))
        return f"{course} · {info.get('original_name', name)}{tag}"

    lines = [line(n) for n in new] + [line(n, " (새 판)") for n in changed]
    title = " · ".join(
        part for part in (f"새 강의자료 {len(new)}개" if new else "", f"새 판 {len(changed)}개" if changed else "") if part
    )
    text = "\n".join(lines[:4]) + (f"\n… 외 {len(lines) - 4}개" if len(lines) > 4 else "")
    notify(title, text)


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
    # '하루 한 번 꼼꼼히' 는 이름 그대로 전체를 훑어야 한다. 예전에는 기본값(fast)으로 불려
    # 변경 시각이 옛날인 채로 나중에 공개된 자료를 영영 못 봤다.
    ok, _message = web_ui.start_task(workspace, "sync", sync_mode="full", auto=True)
    if not ok:
        return
    # 작업 종료 대기 (최대 30분)
    for _ in range(360):
        time.sleep(5)
        with web_ui.task_lock:
            task = web_ui.task_states.get(workspace.user_id, {})
            if not task.get("running"):
                break
    # 새 자료·마감 알림은 scheduler_loop 의 check_new_file_alerts / check_deadline_alerts 가 한다
    # (예전에는 여기서 매일 '새 자료가 없습니다' 까지 알려 귀찮았다)


def scheduler_loop() -> None:
    """앱이 켜져 있는 동안 매일 예약 시간(SCHEDULE_TIME)에 자동 동기화."""
    workspace = web_ui.workspace_for_user("local")

    def last_sync_day() -> str | None:
        """마지막으로 자료 동기화가 실제로 끝난 날(로컬 날짜).

        예전에는 '앱을 켤 때 이미 예약 시간이 지났으면 오늘은 건너뜀' 이었다.
        그러면 08:00 이후에 앱을 켜는 날은 동기화가 영영 안 돈다 — 실제로
        LMS 에 새로 올라온 학술 글쓰기 자료가 하루 넘게 안 들어왔다.
        메모리 대신 last_sync.json 을 보면 '오늘 아직 안 했다' 를 정확히 안다.
        """
        try:
            # 빠른 동기화(3시간마다)도 last_sync.json 을 고치므로, 그걸 보면 '오늘은 이미 했다' 로
            # 보여 전체 검사가 한 번도 돌지 않았다. 전체 검사만 적는 파일을 본다.
            data = web_ui.read_json(workspace.root / "last_full_sync.json", {})
            raw = str((data or {}).get("lastFullSync", ""))
            if not raw:
                return None
            when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return when.astimezone().strftime("%Y-%m-%d")
        except Exception:
            return None

    last_run_day = last_sync_day()
    # 켜자마자 LMS 를 두드리지 않도록 2분만 숨을 고른다
    started_at = time.monotonic()
    while True:
        try:
            config = web_ui.read_config(workspace)
            schedule_time = str(config.get("SCHEDULE_TIME", "08:00")).strip() or "08:00"
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            due_today = now.strftime("%H:%M") >= schedule_time and last_run_day != today
            if due_today and time.monotonic() - started_at > 120:
                with web_ui.task_lock:
                    running = web_ui.task_states.get(workspace.user_id, {}).get("running", False)
                if not running:
                    last_run_day = today
                    run_scheduled_sync(workspace)

            # 알림: 마감이 가까워졌는지, 새 자료가 들어왔는지 (둘 다 파일만 읽어 가볍다)
            try:
                check_deadline_alerts(workspace, config)
                check_new_file_alerts(workspace, config)
            except Exception:
                pass

            # 종류별 자동 실행. 자동이 기본이고, 새로고침 버튼은 '지금 당장' 용.
            # 기준은 메모리가 아니라 health.json 의 마지막 성공 시각이라,
            # 앱을 껐다 켜도 방금 한 걸 또 하지 않고, 오래 안 했으면 곧 한다.
            # 한 번에 하나만 돌린다 (LMS 로그인이 겹치지 않게).
            if time.monotonic() - started_at > 45:
                with web_ui.task_lock:
                    running = web_ui.task_states.get(workspace.user_id, {}).get("running", False)
                if not running:
                    kind = next_due_job(workspace, web_ui.auto_minutes(config))
                    if kind:
                        web_ui.start_task(workspace, kind, auto=True)
        except Exception:
            pass
        time.sleep(30)


def next_due_job(workspace, minutes: dict[str, int]) -> str | None:
    """지금 돌 차례인 자동 작업 하나. 없으면 None.

    급한 순서: 메일(짧은 주기) → 마감 → 자료.
    막 실패한 작업을 30초마다 다시 두드리지 않도록, 실패 뒤에는 주기의
    절반(최소 5분)은 쉰다.
    """
    health = web_ui.read_json(workspace.root / "health.json", {}) or {}
    success = health.get("lastSuccess") or {}
    failure = health.get("lastFailure") or {}
    now = datetime.now()

    def age_minutes(stamp) -> float:
        try:
            when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            if when.tzinfo is not None:
                when = when.astimezone().replace(tzinfo=None)
            return (now - when).total_seconds() / 60
        except (TypeError, ValueError):
            return float("inf")

    streaks = health.get("failStreak") or {}
    auth = health.get("authFailed") or {}
    try:
        st = workspace.config_path.stat()
        config_stamp = [st.st_mtime_ns, st.st_size]
    except OSError:
        config_stamp = None

    for kind in ("emails", "deadlines", "sync"):
        every = int(minutes.get(kind, 0) or 0)
        if every <= 0:
            continue
        if age_minutes(success.get(kind)) < every:
            continue
        # 서버가 로그인을 거절했으면 설정(비밀번호)이 바뀔 때까지 자동으로는 다시 하지 않는다.
        # 틀린 비밀번호로 5분마다 두드리면 학교 계정이 잠길 수 있다. 수동 새로고침은 그대로 된다.
        # 다만 학교 서버가 가끔 멀쩡한 비밀번호도 거절한다(9/26 성공 → 9/27 거절). 영영 멈추지 않고 2시간 뒤 한 번 더 본다.
        locked = auth.get(kind)
        if locked and locked.get("configStamp") == config_stamp and age_minutes(locked.get("at")) < 120:
            continue
        # 그 밖의 실패는 연속으로 실패할수록 간격을 두 배로 (최대 6시간)
        streak = int(streaks.get(kind, 0) or 0)
        wait = min(max(5, every) * (2 ** max(0, streak - 1)), 360) if streak else 0
        if failure.get("kind") == kind:
            wait = max(wait, max(5, every / 2))
        if wait and age_minutes((failure.get("at") if failure.get("kind") == kind else None) or success.get(kind)) < wait:
            continue
        return kind
    return None


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def existing_dashboard(host: str, port: int) -> bool:
    """포트를 점유한 프로세스가 이 앱(붕어빵)의 대시보드인지 확인.

    200 만 보면 안 된다. 다른 웹 서버도 /healthz 에 200 을 줄 수 있다.
    우리 서버만 돌려주는 모양(ok·mode)까지 본다.
    """
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/healthz", timeout=1.5) as resp:
            if resp.status != 200:
                return False
            body = resp.read(2048).decode("utf-8", "replace")
            return '"ok"' in body and '"mode"' in body
    except Exception:
        return False


# 8765 가 막혀 있으면 이 범위에서 빈 곳을 찾는다.
# (실제로 다른 개발 도구가 8765 에 웹 서버를 띄워 붕어빵이 "포트 사용 중" 으로 멈췄다)
PORT_CANDIDATES = [PORT] + [p for p in range(8766, 8786) if p != PORT]


class ExclusiveHTTPServer(ThreadingHTTPServer):
    """다른 프로그램과 같은 포트를 겹쳐 잡지 않는 서버.

    파이썬 기본 HTTP 서버는 SO_REUSEADDR 를 켜는데, Windows 에서는 이것이
    '이미 누가 쓰는 포트도 같이 잡기' 를 허락한다. 그러면 두 서버가 한 포트를
    나눠 가져 요청이 엉뚱한 쪽으로 간다. 혼자만 잡도록 막는다.
    """

    allow_reuse_address = False

    def server_bind(self) -> None:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        super().server_bind()


def start_server() -> ThreadingHTTPServer | None:
    """서버를 띄우고 반환. 이미 붕어빵 대시보드가 떠 있으면 None.

    쓰기로 한 포트는 전역 PORT 와 환경 변수에 적어 둔다
    (창 주소와 작업 프로세스가 같은 포트를 보게).
    """
    global PORT

    # 1) 이미 켜진 붕어빵이 있으면 서버를 또 띄우지 않고 그 창만 연다
    for port in PORT_CANDIDATES:
        if port_in_use(HOST, port) and existing_dashboard(HOST, port):
            PORT = port
            os.environ["AUTOSAVER_UI_PORT"] = str(port)
            return None

    # 2) 빈 포트에 띄운다
    web_ui.ensure_data_files(web_ui.workspace_for_user("local"))
    for port in PORT_CANDIDATES:
        if port_in_use(HOST, port):
            continue
        try:
            server = ExclusiveHTTPServer((HOST, port), web_ui.DashboardHandler)
        except OSError:
            continue
        PORT = port
        os.environ["AUTOSAVER_UI_PORT"] = str(port)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server

    raise RuntimeError(
        f"붕어빵이 쓸 포트를 찾지 못했습니다 ({PORT_CANDIDATES[0]}~{PORT_CANDIDATES[-1]} 모두 사용 중). "
        "다른 프로그램을 몇 개 닫고 다시 켜 주세요."
    )


def _bind_worker_output() -> None:
    """창 없는 EXE(console=False)는 sys.stdout 이 None 이다.

    그대로 두면 작업 로그를 찍는 print() 가 터지면서, 화면에는 이유 없이
    실패한 것처럼 보인다. 부모가 파이프를 물려 줬으면 그 손잡이를 다시 잡는다.
    """
    import io

    for name, fd in (("stdout", 1), ("stderr", 2)):
        current = getattr(sys, name, None)
        if current is not None:
            # 파이프가 붙어 있어도 인코딩은 시스템 기본(한국어 Windows 는 cp949)이라
            # 로그에 └ ─ 같은 글자가 하나 섞이면 UnicodeEncodeError 로 작업이 죽는다.
            # (playwright 가 안내문을 상자로 그려서 실제로 이렇게 터졌다)
            try:
                current.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
            continue
        try:
            stream = io.TextIOWrapper(
                open(fd, "wb", buffering=0), encoding="utf-8", errors="replace", write_through=True
            )
        except Exception:
            # 파이프도 없으면 조용히 버린다 (print 가 죽는 것만은 막는다)
            stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", write_through=True)
        setattr(sys, name, stream)


def run_worker(job: str) -> int:
    """새로고침·동기화 같은 하위 작업을 창 없이 실행한다.

    EXE 로 묶이면 sys.executable 이 '붕어빵.exe' 라서 `-c "..."` 방식이 통하지 않는다.
    그대로 두면 새로고침할 때마다 앱이 통째로 한 번 더 켜지고(창이 계속 늘어남),
    정작 크롤링은 시작도 못 한다. 그래서 EXE 는 이 함수로 들어온다.

    여기서는 서버도 창도 만들지 않는다. 로그는 표준출력으로 나가고,
    부르는 쪽(web_ui.run_process)이 그대로 읽어 화면에 보여 준다.
    """
    import asyncio

    _bind_worker_output()

    try:
        if job == "sync":
            import main as sync_main

            asyncio.run(sync_main.run_job())
        elif job == "deadlines":
            import lms_crawler

            asyncio.run(lms_crawler.crawl_deadlines_only())
        elif job == "emails":
            import email_reader

            email_reader.refresh_emails()
        elif job == "verify":
            import verify

            asyncio.run(verify.verify())
        elif job == "google-oauth":
            from drive_uploader import authorize_drive

            authorize_drive(force=True)
        else:
            print(f"알 수 없는 작업입니다: {job}")
            return 1
    except Exception as exc:
        # 하위 프로세스가 조용히 죽으면 화면에 아무 설명도 안 뜬다
        import traceback

        traceback.print_exc()
        print(f"작업이 실패했습니다: {exc}")
        return 1
    return 0


def main() -> None:
    set_app_user_model_id()  # 창을 만들기 전에 (작업표시줄 아이콘 반영의 핵심)
    import webview

    try:
        server = start_server()
    except RuntimeError as exc:
        if os.name == "nt":
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, str(exc), WINDOW_TITLE, 0x10)
        else:
            print(f"{WINDOW_TITLE}: {exc}", file=sys.stderr)
        return

    try:
        webview.settings["ALLOW_DOWNLOADS"] = True
    except Exception:
        pass

    # 이 프로세스가 서버 주인일 때만 스케줄러/알림 가동 (창만 띄운 경우 제외)
    if server is not None:
        threading.Thread(target=scheduler_loop, daemon=True).start()

        # 켤 때마다 띄우던 '48시간 마감 요약' 은 없앴다. 마감 알림(하루·3시간·1시간 전)이 대신한다.

    url = f"http://{HOST}:{PORT}"
    webview.create_window(
        WINDOW_TITLE,
        url,
        width=1320,
        height=880,
        min_size=(900, 640),
    )
    # 창이 뜬 뒤 아이콘을 입힌다 (pywebview는 Windows에서 아이콘 인자를 지원하지 않음)
    threading.Thread(target=apply_window_icon, daemon=True).start()
    try:
        webview.start()
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    # 작업 인자로 불렸으면 창을 만들지 않고 그 작업만 하고 끝낸다.
    # (web_ui.start_task 가 EXE 일 때 이 형태로 부른다)
    from runtime_config import WORKER_FLAG

    if len(sys.argv) >= 3 and sys.argv[1] == WORKER_FLAG:
        sys.exit(run_worker(sys.argv[2]))
    main()
