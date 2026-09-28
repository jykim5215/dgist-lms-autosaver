"""강의자료 PDF 를 삼성 노트로 보낸다.

삼성은 서드파티가 노트를 만들 수 있는 API 를 주지 않는다. 대신 Windows 용
삼성 노트 앱이 '.pdf' 파일 연결을 등록해 둔다(직접 확인:
  windows.fileTypeAssociation → .sdocx, .sdoc, .pdf, .spd).
그래서 WinRT 의 Launcher 로 '이 파일을 삼성 노트로 열어라' 라고 시키면
삼성 노트가 그 PDF 를 가져와 노트로 만든다.

한계 (알고 쓰는 편이 낫다)
  - PDF 만 된다. pptx·docx·hwp 는 삼성 노트가 못 읽는다.
  - 삼성 노트가 파일 하나를 노트로 저장하는 데 몇 초씩 걸린다(실측 5.5초).
    그 사이 삼성 노트 창은 투명하게 붙잡아 두어 화면에 보이지 않는다.
  - 삼성 노트 Windows 앱이 깔린 PC 에서만 된다.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

# 이 PC 에서 확인한 값 (레지스트리 AppUserModelID 기준)
PACKAGE_FAMILY_NAME = "SAMSUNGELECTRONICSCoLtd.SamsungNotes_wyx1vj98g3asy"
APP_USER_MODEL_ID = f"{PACKAGE_FAMILY_NAME}!App"

SUPPORTED_SUFFIXES = {".pdf"}

_available_cache: dict[str, bool] = {}


def is_supported(path: str | os.PathLike) -> bool:
    """삼성 노트가 읽을 수 있는 형식인지."""
    return Path(path).suffix.lower() in SUPPORTED_SUFFIXES


def is_available(refresh: bool = False) -> bool:
    """이 PC 에 삼성 노트 Windows 앱이 깔려 있는지.

    PowerShell 로 앱 목록을 한 번만 물어보고 기억해 둔다.
    (화면을 그릴 때마다 부르면 느려진다)
    """
    if not refresh and "value" in _available_cache:
        return _available_cache["value"]
    if os.name != "nt":
        _available_cache["value"] = False
        return False
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                "if (Get-AppxPackage -Name 'SAMSUNGELECTRONICSCoLtd.SamsungNotes') { 'yes' } else { 'no' }",
            ],
            capture_output=True, text=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        ok = "yes" in (result.stdout or "").lower()
    except Exception:
        ok = False
    _available_cache["value"] = ok
    return ok


async def _launch(full_path: str) -> bool:
    from winrt.windows.storage import StorageFile
    from winrt.windows.system import Launcher, LauncherOptions

    file = await StorageFile.get_file_from_path_async(full_path)
    options = LauncherOptions()
    options.target_application_package_family_name = PACKAGE_FAMILY_NAME
    # 파이썬 투영에서는 옵션을 받는 오버로드 이름이 따로 있다
    return await Launcher.launch_file_with_options_async(file, options)


def note_exists(title: str) -> bool | None:
    """같은 제목의 노트가 이미 있는지.

    삼성 노트는 같은 PDF 를 두 번 넣어도 막지 않고 그냥 하나 더 만든다.
    그러면 새로고침할 때마다 같은 강의자료가 쌓인다. 보내기 전에 미리 본다.

    True/False, 확인할 수 없으면 None (그때는 막지 않고 그냥 보낸다 —
    확인이 안 된다고 못 보내게 하면 더 답답하다).
    """
    import sqlite3

    db_path = notes_db_path()
    if not db_path.exists():
        return None
    try:
        # 앱이 켜져 있어도 읽기는 된다.
        # 정확 일치만 보면 안 된다 — 삼성 노트가 긴 제목을 50자쯤에서 잘라
        # 저장하기 때문에, 잘린 제목과도 맞춰 봐야 같은 파일임을 알 수 있다.
        # (실제로 잘린 제목 하나가 중복 검사를 계속 통과해 두 벌이 됐다)
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
        try:
            for (note_title,) in db.execute(
                "SELECT Title FROM NoteDB WHERE DeletedStatus=0 AND Title<>''"
            ):
                if _title_matches(note_title, title):
                    return True
            return False
        finally:
            db.close()
    except Exception:
        return None


def send(path: str | os.PathLike, skip_duplicates: bool = True) -> dict:
    """PDF 한 개를 삼성 노트로 보낸다.

    skip_duplicates=True 면 같은 이름의 노트가 이미 있을 때 보내지 않는다.
    """
    target = Path(path)
    if not target.is_file():
        return {"ok": False, "message": "파일을 찾을 수 없습니다."}

    # 삼성 노트는 PDF 를 가져올 때 확장자를 뗀 파일 이름을 제목으로 쓴다
    title = target.stem
    if skip_duplicates and note_exists(title):
        return {
            "ok": True,
            "duplicate": True,
            "message": f"이미 삼성 노트에 있습니다: {title}",
        }
    if not is_supported(target):
        return {
            "ok": False,
            "message": "삼성 노트는 PDF 만 가져올 수 있습니다. "
                       f"({target.suffix or '확장자 없음'} 은 지원하지 않습니다)",
        }
    if not is_available():
        return {
            "ok": False,
            "needsApp": True,
            "message": "이 컴퓨터에 삼성 노트 앱이 없습니다. "
                       "Microsoft Store 에서 'Samsung Notes' 를 설치해 주세요.",
        }

    try:
        ok = asyncio.run(_launch(str(target.resolve())))
    except ImportError:
        return {"ok": False, "message": "삼성 노트로 보내는 기능을 불러오지 못했습니다."}
    except Exception as exc:
        return {"ok": False, "message": f"삼성 노트를 열지 못했습니다: {exc}"}

    if not ok:
        return {"ok": False, "message": "삼성 노트가 파일을 받지 않았습니다."}
    return {"ok": True, "message": f"삼성 노트로 보냈습니다: {target.name}"}


# ===== 보낸 노트를 과목 폴더로 정리 =====
# 삼성 노트는 '어느 폴더에 넣어라' 를 받지 않는다. 그래서 보낸 파일은 전부
# 최상위('폴더', 내부값 uncategorized:///)에 쌓인다.
#
# 노트 목록은 앱 폴더 안 Storage.sqlite 에 들어 있고, NoteDB.CategoryUUID 가
# 어느 폴더인지를 가리킨다. 이 값을 바꾸면 노트가 폴더로 옮겨진다.
# (실제로 확인함: 옮긴 뒤 앱을 켜니 그대로 있었고 IsCategoryDirty 가 0으로
#  내려가 삼성 노트가 변경을 받아들인 것을 확인했다)
#
# 조심할 것
#   - 삼성 노트가 켜져 있으면 건드리지 않는다. 앱이 메모리 값으로 덮어쓴다.
#   - 쓰기 전에 DB 를 통째로 백업한다.
#   - 우리가 보낸 파일과 이름이 같은 노트만 건드린다. 남의 노트는 그대로 둔다.

NOTES_PACKAGE_DIR = "SAMSUNGELECTRONICSCoLtd.SamsungNotes_wyx1vj98g3asy"
# '폴더' 화면 맨 위에 보이는 폴더들의 부모값. 다른 값을 쓰면 새 폴더가
# 남의 폴더 안쪽에 숨어 화면에 안 나온다. (직접 확인함)
ROOT_PARENT = "uncategorized:///"


def notes_db_path() -> Path:
    return (
        Path(os.environ.get("LOCALAPPDATA", Path.home()))
        / "Packages" / NOTES_PACKAGE_DIR / "LocalState" / "Storage.sqlite"
    )


def _process_ids(image: str) -> set[int]:
    """실행 파일 이름이 image 인 프로세스들의 PID.

    예전에는 tasklist 를 띄워 출력을 읽었다. 한 번에 0.2~0.5초가 들고,
    한국어 Windows 에서는 '일치하는 작업이 없습니다' 문구가 cp949 라
    출력 읽기가 깨지면 켜져 있어도 '꺼져 있다' 로 볼 위험이 있었다.
    (그 판단으로 켜진 앱의 DB 에 쓰면 정리가 되돌아간다)
    프로세스 목록을 직접 묻는다.
    """
    if os.name != "nt":
        return set()
    import ctypes
    import ctypes.wintypes as wt

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wt.DWORD),
            ("cntUsage", wt.DWORD),
            ("th32ProcessID", wt.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wt.DWORD),
            ("cntThreads", wt.DWORD),
            ("th32ParentProcessID", wt.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wt.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    kernel32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return set()
    found: set[int] = set()
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        target = image.lower()
        while ok:
            if entry.szExeFile.lower() == target:
                found.add(int(entry.th32ProcessID))
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return found


def is_running() -> bool:
    """삼성 노트 본체가 떠 있는지 (트레이 도우미는 제외)."""
    try:
        return bool(_process_ids("SamsungNotes.exe"))
    except Exception:
        return False


def list_note_uuids() -> set[str]:
    """지금 있는 노트의 UUID 집합 (읽기 전용).

    삼성 노트는 가져온 PDF 를 '마지막으로 열려 있던 폴더' 에 만든다
    (직접 실험으로 확인 — 영어 파일이 물리 폴더에 들어갔다).
    그래서 어느 폴더에 생겼는지는 믿을 수 없고, 보내기 전후의 UUID 차이로
    '방금 우리가 만든 노트' 를 특정한 뒤 제자리로 옮긴다.
    """
    import sqlite3

    db_path = notes_db_path()
    if not db_path.exists():
        return set()
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
        try:
            return {r[0] for r in db.execute("SELECT UUID FROM NoteDB WHERE DeletedStatus=0")}
        finally:
            db.close()
    except Exception:
        return set()


def wait_for_new_note(known: set[str], timeout: float = 25.0) -> set[str]:
    """known 에 없던 새 노트가 생길 때까지 기다렸다가 그 UUID 들을 돌려준다."""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        fresh = list_note_uuids() - known
        if fresh:
            return fresh
        time.sleep(1.0)
    return set()


def note_titles(uuids: set[str]) -> dict[str, str]:
    """{uuid: 제목} (읽기 전용)."""
    import sqlite3

    if not uuids:
        return {}
    db = sqlite3.connect(f"file:{notes_db_path()}?mode=ro", uri=True, timeout=3)
    try:
        marks = ",".join("?" * len(uuids))
        return {
            r[0]: (r[1] or "")
            for r in db.execute(
                f"SELECT UUID, Title FROM NoteDB WHERE UUID IN ({marks})", tuple(uuids)
            )
        }
    finally:
        db.close()


def organize_uuids(uuid_to_folder: dict[str, str]) -> dict:
    """지정한 노트들을 (지금 어느 폴더에 있든) 지정한 폴더로 옮긴다.

    UUID 로 특정된 '우리가 만든 노트' 에만 쓴다. 제목 추측이 아니라
    확실한 대상만 옮기므로, 삼성 노트가 엉뚱한 폴더에 넣어도 바로잡을 수 있다.
    """
    import sqlite3
    import time
    import uuid as uuidlib

    db_path = notes_db_path()
    if not db_path.exists():
        return {"ok": False, "message": "삼성 노트 저장소를 찾지 못했습니다."}
    if is_running():
        return {"ok": False, "needsClose": True,
                "message": "삼성 노트를 먼저 닫아 주세요."}
    if not uuid_to_folder:
        return {"ok": True, "moved": 0, "message": "옮길 노트가 없습니다."}

    backup = _backup_db(db_path)
    now_ms = int(time.time() * 1000)
    moved = made = 0

    db = sqlite3.connect(str(db_path))
    try:
        folder_ids: dict[str, str] = {}

        def folder_for(name: str) -> str:
            if name in folder_ids:
                return folder_ids[name]
            row = db.execute(
                "SELECT UUID FROM CategoryTreeDB WHERE DisplayName=? AND IsDeleted=0 LIMIT 1",
                (name,),
            ).fetchone()
            if row:
                folder_ids[name] = row[0]
                return row[0]
            new_uuid = str(uuidlib.uuid4())
            db.execute(
                "INSERT INTO CategoryTreeDB "
                "(UUID, ParentUUID, IsDeleted, IsDirty, DisplayName, CreatedAt, LastModifiedAt,"
                " ServerTimestamp, RecycleBinTimeMoved, RestorePath, DisplayNameColor,"
                " FolderState, IsSyncWithMS, Reorder) "
                "VALUES (?,?,0,1,?,?,?,0,0,'',0,0,0,1)",
                (new_uuid, ROOT_PARENT, name, now_ms, now_ms),
            )
            folder_ids[name] = new_uuid
            nonlocal made
            made += 1
            return new_uuid

        for note_uuid, folder_name in uuid_to_folder.items():
            cur = db.execute(
                "SELECT 1 FROM NoteDB WHERE UUID=? AND DeletedStatus=0", (note_uuid,)
            ).fetchone()
            if not cur:
                continue
            db.execute(
                "UPDATE NoteDB SET CategoryUUID=?, IsCategoryDirty=1, IsDirty=1, "
                "LastModifiedAt=? WHERE UUID=?",
                (folder_for(folder_name), now_ms, note_uuid),
            )
            moved += 1
        db.commit()
    except Exception as exc:
        db.rollback()
        return {"ok": False, "message": f"정리하지 못했습니다: {exc}", "backup": str(backup)}
    finally:
        db.close()

    return {"ok": True, "moved": moved, "created": made, "backup": str(backup),
            "message": f"노트 {moved}개를 제 폴더로 옮겼습니다."}


def wait_for_note(title: str, timeout: float = 20.0) -> bool:
    """보낸 PDF 가 노트로 등록될 때까지 기다린다.

    Launcher 는 '전달' 만 하고 끝나서, 삼성 노트가 실제로 가져왔는지는
    DB 에 제목이 생겼는지로 확인할 수밖에 없다. 등록 전에 앱을 닫으면
    그 노트는 사라진다.
    """
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if note_exists(title):
            return True
        time.sleep(1.0)
    return False


def close_app(timeout: float = 10.0) -> bool:
    """삼성 노트 본체를 닫는다 (정리는 닫힌 상태에서만 안전하다).

    예전에는 곧바로 강제 종료(taskkill /F)하고 3초를 무조건 기다렸다.
    강제 종료는 저장할 틈을 주지 않아 쓰던 노트를 날릴 수 있다.
    이제 창의 닫기 버튼을 누른 것처럼 정상 종료를 먼저 청한다
    (실측 0.7초). 그래도 안 닫힐 때만 강제로 닫는다.
    """
    import time

    if not is_running():
        return True
    try:
        import ctypes

        user32 = ctypes.WinDLL("user32")
        for hwnd in _notes_frames():
            user32.PostMessageW(hwnd, 0x0112, 0xF060, 0)  # WM_SYSCOMMAND, SC_CLOSE
    except Exception:
        pass

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_running():
            return True
        time.sleep(0.1)

    try:
        subprocess.run(
            ["taskkill", "/IM", "SamsungNotes.exe", "/F"],
            capture_output=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return False
    deadline = time.time() + 5
    while time.time() < deadline:
        if not is_running():
            return True
        time.sleep(0.1)
    return False


# ===== 가져오는 동안 삼성 노트 창을 안 보이게 =====
# 삼성 노트는 UWP 앱이다. 겉창(ApplicationFrameWindow, ApplicationFrameHost.exe)
# 안에 실제 화면(CoreWindow, SamsungNotes.exe)이 들어 있다.
#
# 최소화하면 안 된다. UWP 는 최소화되면 일시정지되어 가져오기가 멈출 수 있다.
# 대신 겉창을 완전히 투명하게(알파 0) 하고 클릭이 뚫고 지나가게 만든다.
# 앱은 '보이는 창' 으로 계속 돌아가니 가져오기는 그대로 진행되고,
# 화면에는 아무것도 안 보인다. (직접 스크린샷으로 확인함)

_WINDOW_TITLES = ("삼성 노트", "Samsung Notes")
_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020
_LWA_ALPHA = 0x2


def _notes_frames() -> list[int]:
    """삼성 노트의 겉창 핸들들."""
    if os.name != "nt":
        return []
    import ctypes
    import ctypes.wintypes as wt

    user32 = ctypes.WinDLL("user32")
    pids = _process_ids("SamsungNotes.exe")
    enum_proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    frames: list[int] = []

    def owned_by_notes(hwnd) -> bool:
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value in pids

    def on_top(hwnd, _):
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value != "ApplicationFrameWindow":
            return True
        title = ctypes.create_unicode_buffer(64)
        user32.GetWindowTextW(hwnd, title, 64)
        hit = [title.value in _WINDOW_TITLES]
        if not hit[0] and pids:
            def on_child(child, _):
                if owned_by_notes(child):
                    hit[0] = True
                    return False
                return True

            user32.EnumChildWindows(hwnd, enum_proc(on_child), 0)
        if hit[0]:
            frames.append(int(hwnd))
        return True

    user32.EnumWindows(enum_proc(on_top), 0)
    return frames


class HiddenNotesWindow:
    """with 블록 동안 삼성 노트 창을 계속 투명하게 붙잡아 둔다.

    파일을 하나 넘길 때마다 삼성 노트가 앞으로 나오려고 한다.
    그래서 한 번 숨기고 끝이 아니라 짧은 간격으로 계속 확인한다.
    초점을 가져가면 원래 쓰던 창에 돌려준다 — 안 그러면 사용자가 치는
    글자가 안 보이는 삼성 노트로 들어간다.
    """

    def __init__(self, interval: float = 0.03):
        import threading

        self.interval = interval
        self.original: dict[int, int] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.previous_foreground = 0

    def __enter__(self):
        if os.name == "nt":
            import ctypes

            self.previous_foreground = int(ctypes.WinDLL("user32").GetForegroundWindow() or 0)
            self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)
        return False

    def _hide(self, user32, hwnd: int) -> None:
        style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        if hwnd not in self.original:
            self.original[hwnd] = style
        want = style | _WS_EX_LAYERED | _WS_EX_TRANSPARENT
        if style != want:
            user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, want)
        user32.SetLayeredWindowAttributes(hwnd, 0, 0, _LWA_ALPHA)

    def _give_focus_back(self, user32, kernel32, frames: list[int]) -> None:
        foreground = int(user32.GetForegroundWindow() or 0)
        target = self.previous_foreground
        if foreground not in frames or not target or not user32.IsWindow(target):
            return
        mine = kernel32.GetCurrentThreadId()
        theirs = user32.GetWindowThreadProcessId(foreground, None)
        attached = bool(user32.AttachThreadInput(mine, theirs, True))
        try:
            user32.SetForegroundWindow(target)
        finally:
            if attached:
                user32.AttachThreadInput(mine, theirs, False)

    def _run(self) -> None:
        import ctypes

        user32 = ctypes.WinDLL("user32")
        kernel32 = ctypes.WinDLL("kernel32")
        user32.GetWindowLongW.restype = ctypes.c_long
        while not self._stop.is_set():
            try:
                frames = _notes_frames()
                for hwnd in frames:
                    self._hide(user32, hwnd)
                if frames:
                    self._give_focus_back(user32, kernel32, frames)
            except Exception:
                pass
            self._stop.wait(self.interval)

    def reveal(self) -> None:
        """닫지 못하고 끝났을 때, 투명한 채로 남겨 두지 않는다."""
        if os.name != "nt":
            return
        import ctypes

        user32 = ctypes.WinDLL("user32")
        for hwnd, style in self.original.items():
            if user32.IsWindow(hwnd):
                user32.SetLayeredWindowAttributes(hwnd, 0, 255, _LWA_ALPHA)
                user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, style)


def _relaunch_visible() -> None:
    """원래 켜 두었던 삼성 노트를 다시 띄워 준다."""
    try:
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{APP_USER_MODEL_ID}"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass


def _title_matches(note_title: str, stem: str) -> bool:
    """노트 제목이 이 파일에서 나온 것인지.

    삼성 노트는 그대로 두지 않는 경우가 있다 (직접 확인함):
      - 같은 파일을 두 번 받으면 '_2' 를 붙인다  → BS101_Syllabus_04_2
      - 긴 이름은 50자쯤에서 잘라 버린다        → 'USEFUL-...-PRESENTATIONS (2'
    그래서 정확 일치 외에 이 두 변형도 같은 파일로 본다.
    """
    import re

    if note_title == stem:
        return True
    # 중복 꼬리표: stem_2, stem_3 …
    if re.fullmatch(re.escape(stem) + r"_\d+", note_title):
        return True
    # 잘린 제목: 노트 제목이 stem 의 앞부분 그대로면서 충분히 길다
    if len(note_title) >= 45 and stem.startswith(note_title):
        return True
    return False


def _backup_db(db_path: Path) -> Path:
    import shutil
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = db_path.with_name(f"Storage.sqlite.붕어빵백업-{stamp}")
    shutil.copy2(db_path, backup)
    return backup


def organize_notes(mapping: dict[str, str]) -> dict:
    """{노트제목: 폴더이름} 대로 노트를 옮긴다.

    mapping 에 있는 제목과 정확히 일치하는 노트만 손댄다.
    이미 어떤 폴더에 들어 있는 노트는 건드리지 않는다(사용자가 직접 정리한 것일 수 있다).
    """
    import sqlite3
    import time
    import uuid as uuidlib

    db_path = notes_db_path()
    if not db_path.exists():
        return {"ok": False, "message": "삼성 노트 저장소를 찾지 못했습니다."}
    if is_running():
        return {
            "ok": False,
            "needsClose": True,
            "message": "삼성 노트를 먼저 닫아 주세요. 켜져 있으면 정리한 내용이 되돌아갑니다.",
        }
    if not mapping:
        return {"ok": True, "moved": 0, "message": "정리할 노트가 없습니다."}

    backup = _backup_db(db_path)
    now_ms = int(time.time() * 1000)
    moved, made, skipped = 0, 0, 0

    db = sqlite3.connect(str(db_path))
    try:
        folder_ids: dict[str, str] = {}

        def folder_for(name: str) -> str:
            if name in folder_ids:
                return folder_ids[name]
            row = db.execute(
                "SELECT UUID FROM CategoryTreeDB WHERE DisplayName=? AND IsDeleted=0 LIMIT 1",
                (name,),
            ).fetchone()
            if row:
                folder_ids[name] = row[0]
                return row[0]
            new_uuid = str(uuidlib.uuid4())
            db.execute(
                "INSERT INTO CategoryTreeDB "
                "(UUID, ParentUUID, IsDeleted, IsDirty, DisplayName, CreatedAt, LastModifiedAt,"
                " ServerTimestamp, RecycleBinTimeMoved, RestorePath, DisplayNameColor,"
                " FolderState, IsSyncWithMS, Reorder) "
                "VALUES (?,?,0,1,?,?,?,0,0,'',0,0,0,1)",
                (new_uuid, ROOT_PARENT, name, now_ms, now_ms),
            )
            folder_ids[name] = new_uuid
            nonlocal made
            made += 1
            return new_uuid

        # 최상위(미분류)에 있는 노트만 후보로 본다.
        # 사용자가 직접 다른 폴더에 넣어 둔 노트는 절대 건드리지 않는다.
        loose = db.execute(
            "SELECT UUID, Title FROM NoteDB WHERE DeletedStatus=0 "
            "AND (CategoryUUID='' OR CategoryUUID=?)",
            (ROOT_PARENT,),
        ).fetchall()

        matched_uuids: set[str] = set()
        for stem, folder_name in mapping.items():
            for note_uuid, note_title in loose:
                if note_uuid in matched_uuids:
                    continue
                if not _title_matches(note_title or "", stem):
                    continue
                db.execute(
                    "UPDATE NoteDB SET CategoryUUID=?, IsCategoryDirty=1, IsDirty=1, "
                    "LastModifiedAt=? WHERE UUID=?",
                    (folder_for(folder_name), now_ms, note_uuid),
                )
                matched_uuids.add(note_uuid)
                moved += 1

        db.commit()
    except Exception as exc:
        db.rollback()
        return {"ok": False, "message": f"정리하지 못했습니다: {exc}", "backup": str(backup)}
    finally:
        db.close()

    message = f"노트 {moved}개를 과목 폴더로 옮겼습니다."
    if made:
        message += f" (폴더 {made}개 새로 만듦)"
    if skipped:
        message += f" 이미 정리된 {skipped}개는 그대로 뒀습니다."
    return {"ok": True, "moved": moved, "created": made, "skipped": skipped,
            "backup": str(backup), "message": message}


# ===== 여러 PDF 를 한 번에, 안 보이게 =====

def _read_db(query: str, params: tuple = ()) -> list[tuple] | None:
    """읽기 전용 조회. 못 읽으면 None."""
    import sqlite3

    db_path = notes_db_path()
    if not db_path.exists():
        return None
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
        try:
            return db.execute(query, params).fetchall()
        finally:
            db.close()
    except Exception:
        return None


def _max_note_id() -> int:
    rows = _read_db("SELECT COALESCE(MAX(Id), 0) FROM NoteDB")
    return int(rows[0][0]) if rows else 0


# 한 파일이 노트로 저장되기를 기다리는 최대 시간.
# 앱이 켜져 있으면 보통 몇 초 안에 끝난다. 큰 PDF 를 생각해 넉넉히 둔다.
FILE_SAVE_TIMEOUT = 40.0


def _notes_ready() -> bool:
    """겉창 안에 실제 화면(CoreWindow)이 붙었는지 = 파일을 받을 준비가 됐는지."""
    if os.name != "nt":
        return False
    import ctypes
    import ctypes.wintypes as wt

    user32 = ctypes.WinDLL("user32")
    pids = _process_ids("SamsungNotes.exe")
    if not pids:
        return False
    enum_proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    for frame in _notes_frames():
        found = [False]

        def on_child(child, _):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(child, cls, 64)
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(child, ctypes.byref(pid))
            if cls.value == "Windows.UI.Core.CoreWindow" and pid.value in pids:
                found[0] = True
                return False
            return True

        user32.EnumChildWindows(frame, enum_proc(on_child), 0)
        if found[0]:
            return True
    return False


def import_pdfs(items: list[tuple[Path, str]], progress=None) -> dict:
    """PDF 들을 삼성 노트에 넣고, 새로 생긴 노트를 과목 폴더로 옮긴다.

    items: [(파일 경로, 폴더 이름)]
    progress(done=, total=, current=): 진행 알림 (선택)

    예전 흐름과 달라진 점
      - 파일마다 삼성 노트 창이 앞으로 튀어나왔다 → 창을 투명하게 붙잡아 둔다.
      - 파일마다 DB 를 통째로 읽어 중복을 봤다 → 한 번만 읽는다.
      - 새 노트를 1초 간격으로, 노트 UUID 전부를 읽어 찾았다
        → 0.2초 간격으로 '이번에 새로 생긴 줄(Id)' 만 본다.
      - 파일마다 asyncio 루프를 새로 만들었다 → 하나로 돌려 쓴다.
      - 끝나면 강제 종료 후 3초를 기다렸다 → 정상 종료를 청하고 닫히는 즉시 진행.
      - 원래 켜 두었던 삼성 노트는 정리가 끝나면 다시 띄워 준다.
    """
    import time

    report = progress or (lambda **_: None)

    missing, unsupported, duplicates, todo = [], [], [], []
    titles = _read_db("SELECT Title FROM NoteDB WHERE DeletedStatus=0 AND Title<>''")
    existing = [row[0] or "" for row in titles] if titles is not None else None
    queued: set[str] = set()
    for path, folder in items:
        path = Path(path)
        if not path.is_file():
            missing.append(path.name)
        elif not is_supported(path):
            unsupported.append(path.name)
        elif path.stem in queued or (
            existing is not None and any(_title_matches(t, path.stem) for t in existing)
        ):
            duplicates.append(path.name)
        else:
            queued.add(path.stem)
            todo.append((path, folder or "기타"))

    def summary(done: int, moved: int, failed: list[str], note: str = "") -> dict:
        parts = [f"삼성 노트에 {done}개 넣었습니다."]
        if moved:
            parts.append(f"과목 폴더로 {moved}개 정리했습니다.")
        if duplicates:
            parts.append(f"이미 있던 {len(duplicates)}개는 건너뛰었습니다.")
        if unsupported:
            parts.append(f"PDF 가 아닌 {len(unsupported)}개는 넣을 수 없습니다.")
        if failed or missing:
            parts.append(f"실패 {len(failed) + len(missing)}개.")
        if note:
            parts.append(note)
        return {
            "ok": True,
            "done": done,
            "moved": moved,
            "duplicates": len(duplicates),
            "unsupported": len(unsupported),
            "failed": len(failed) + len(missing),
            "message": " ".join(parts),
        }

    if not todo:
        report(done=0, total=0, current="")
        return summary(0, 0, [])
    if not is_available():
        return {"ok": False, "needsApp": True,
                "message": "이 컴퓨터에 삼성 노트 앱이 없습니다. "
                           "Microsoft Store 에서 'Samsung Notes' 를 설치해 주세요."}

    was_running = is_running()
    start_id = _max_note_id()
    pending: dict[str, str] = {}       # 파일이름줄기 → 폴더
    created: dict[str, str] = {}       # 노트 UUID → 폴더
    claimed: set[str] = set()
    failed: list[str] = []

    def collect() -> None:
        """이번에 새로 생긴 노트 중 저장이 끝난 것을 제 파일과 짝짓는다."""
        rows = _read_db(
            "SELECT UUID, Title, IsSaving, FilePath FROM NoteDB "
            "WHERE Id > ? AND DeletedStatus=0 ORDER BY Id",
            (start_id,),
        ) or []
        for note_uuid, title, saving, file_path in rows:
            if note_uuid in claimed or int(saving or 0):
                continue
            if file_path and not os.path.exists(file_path):
                continue
            for stem, folder in list(pending.items()):
                if _title_matches(title or "", stem):
                    created[note_uuid] = folder
                    claimed.add(note_uuid)
                    del pending[stem]
                    break

    loop = asyncio.new_event_loop()
    guard = HiddenNotesWindow()
    closed = True
    timings: dict[str, float] = {}
    started = time.time()
    try:
        with guard:
            # 1) 앱을 먼저 (안 보이게) 띄워 둔다.
            #    꺼진 앱에 곧바로 파일을 넘기면, 켜지는 도중에 받은 문서는
            #    한참 동안 저장이 안 된다 (실측: 45초 동안 DB 에 안 생김).
            if not was_running:
                _relaunch_visible()
                deadline = time.time() + 25
                while time.time() < deadline and not _notes_ready():
                    time.sleep(0.1)
                time.sleep(1.2)
                timings["warmup"] = round(time.time() - started, 1)

            # 2) 파일을 차례로 넘기고, 노트로 저장될 때까지 기다린다.
            #    저장되기 전에 다음 파일을 넘기거나 앱을 닫으면 그 문서는 사라진다
            #    (실측: 넘기고 5초 만에 닫았더니 노트가 안 생겼다).
            for index, (path, folder) in enumerate(todo):
                report(done=index, total=len(todo), current=path.name)
                try:
                    launched = loop.run_until_complete(_launch(str(path.resolve())))
                except Exception:
                    launched = False
                if not launched:
                    failed.append(path.name)
                    continue
                pending[path.stem] = folder
                handed = time.time()
                deadline = handed + FILE_SAVE_TIMEOUT
                while path.stem in pending and time.time() < deadline:
                    time.sleep(0.2)
                    collect()
                timings.setdefault("perFile", []).append(round(time.time() - handed, 1))
            report(done=len(todo), total=len(todo), current="")

            # 3) 다 저장됐으면 닫는다 (폴더 정리는 닫힌 상태에서만 안전하다)
            #    노트가 저장된 뒤에도 삼성 노트는 썸네일·본문 글자를 만드느라
            #    정상 종료에 15초쯤 걸린다(실측). 그건 다음에 앱을 열 때 다시
            #    만들어진다(실측: 강제로 닫힌 노트도 썸네일이 생겼다).
            #    우리가 켠 앱이면 짧게만 기다리고, 사용자가 켜 두었던 앱이면
            #    쓰던 내용이 저장되도록 넉넉히 기다린다.
            close_started = time.time()
            closed = close_app(timeout=20 if was_running else 4)
            timings["close"] = round(time.time() - close_started, 1)
        if not closed:
            guard.reveal()
    finally:
        loop.close()

    # 닫힌 뒤에 저장된 것까지 짝짓는다
    deadline = time.time() + 5
    while pending and time.time() < deadline:
        collect()
        if pending:
            time.sleep(0.3)
    failed.extend(f"{stem}.pdf" for stem in pending)
    timings["total"] = round(time.time() - started, 1)

    moved = 0
    note = ""
    if created and closed:
        result = organize_uuids(created)
        moved = int(result.get("moved", 0) or 0)
        if not result.get("ok"):
            note = f"(폴더 정리 실패: {result.get('message', '')})"
    elif created:
        note = "(삼성 노트가 닫히지 않아 폴더 정리는 다음에 합니다)"

    if was_running:
        _relaunch_visible()
    result = summary(len(created), moved, failed, note)
    result["timings"] = timings
    return result


if __name__ == "__main__":
    import sys

    print("삼성 노트 설치됨:", is_available(), "/ 실행 중:", is_running())
    if len(sys.argv) > 1:
        print(send(sys.argv[1]))
