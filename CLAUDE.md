# CLAUDE.md — 붕어빵 (DGIST LMS AutoSaver) 작업 안내

DGIST 학생용 Windows 데스크톱 앱입니다. LMS 강의자료·과제 마감·학교 메일·학사일정·공지를 자동으로 모아
한 화면에서 보고, Google Drive·Google Calendar·삼성 노트·내 컴퓨터로 보냅니다.

- **기능 전체 지도, API 목록, 데이터 파일, 설정 키는 `FEATURES.md`** 에 있습니다. 기능을 고치기 전에 해당 절을 먼저 읽습니다.
- 사용자는 한국어로 말하고, 코드 주석과 화면 문구도 한국어입니다. 주석은 "왜 이렇게 했는지(실측·실제 겪은 일)"를 적는 스타일을 따릅니다.

## 1. 위치

| 무엇 | 경로 |
|---|---|
| 저장소 | `C:\Users\jykim\바탕화면\dgist-lms-autosaver-main\dgist-lms-autosaver-main` (git `main`, 원격 `jykim5215/dgist-lms-autosaver`) |
| 설치된 앱 | `%LOCALAPPDATA%\Programs\붕어빵\붕어빵.exe` |
| 사용자 데이터 | `C:\lms-autosaver\` (설치 앱과 개발 서버가 **함께** 씀) |
| 파이썬 | 저장소의 `.venv` (Python 3.14). 시스템 `python`이 아니라 `.venv\Scripts\python.exe`를 씁니다 |

## 2. 자주 쓰는 명령

```powershell
# 문법 검사
.venv\Scripts\python.exe -m py_compile app.py web_ui.py email_reader.py lms_crawler.py samsung_notes.py
node --check web\app.js

# 소스 그대로 화면 띄우기 (8794 포트, 설치 앱과 같은 데이터)
.venv\Scripts\python.exe scripts\dev_server.py
#   Claude 데스크톱 앱에서는 .claude/launch.json 의 "autosaver-src" 로 preview_start

# 설치 파일 만들기 / 만들고 이 PC에 설치·실행
powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1
powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1 -Install

# 설치된 앱이 떠 있는 포트 찾기 (8765가 막혀 있으면 8766~8785)
Get-NetTCPConnection -OwningProcess (Get-Process 붕어빵).Id -State Listen
```

파이썬 모듈을 직접 불러 시험할 때는 데이터 경로를 넘깁니다.

```bash
AUTOSAVER_DATA_ROOT=C:/lms-autosaver AUTOSAVER_CONFIG_PATH=C:/lms-autosaver/config.json PYTHONPATH=. ./.venv/Scripts/python.exe -X utf8 -c "..."
```

테스트 스위트는 없습니다. 검증은 문법 검사 + 개발 서버에서 화면 확인 + 설치본에서 재확인으로 합니다.

## 3. 반드시 지킬 것

### 작업 완료의 기준
1. **파이썬 코드를 고쳤으면 설치 파일을 다시 만들고 설치해야 사용자 앱에 반영됩니다.** 소스만 고치고 "됐다"고 하지 않습니다. `build_installer.ps1 -Install` 후 설치본에서 확인합니다.
2. 화면 변경은 개발 서버에서 눈으로 확인(스크린샷·콘솔 오류)한 뒤 설치본에도 반영합니다.
3. 측정할 수 있는 것은 측정하고 숫자로 보고합니다. 추측으로 원인을 말하지 않습니다.

### 사용자 데이터와 계정
4. **비밀번호·API 키를 대신 입력하거나 파일·코드에 적지 않습니다.** 사용자가 채팅에 붙여 넣고 "넣어 달라"고 해도 설정 화면에서 직접 넣도록 안내합니다.
5. 비밀 설정 키는 `web_ui.SECRET_KEYS`와 `runtime_config.SECRET_KEYS` **두 곳 모두**에 있어야 합니다. 한쪽에만 있으면 작업 프로세스가 `dpapi:` 암호문을 그대로 씁니다.
6. 학교 포털 비밀번호 저장이 필요한 기능은 먼저 제안하지 않습니다.
7. 데이터 파일(`C:\lms-autosaver\*.json`)에 쓰는 시험을 할 때는 설치된 앱을 먼저 끄고, 시험 전에 해당 파일을 백업합니다.
8. 사용자 파일은 지우지 말고 휴지통으로 보내거나 옮깁니다.

### 메일 (IMAP)
9. **절대 일반 `EXPUNGE`를 보내지 않습니다.** 휴지통 전체가 영구 삭제됩니다(실제로 사고가 날 뻔했음). 서버에 UIDPLUS가 없으므로 `expunge_uid`는 아무것도 안 하고, 검색은 `NOT DELETED`로 합니다.
10. 서버에 IDLE·MOVE·CONDSTORE가 없습니다. 실시간 푸시를 전제로 설계하지 않습니다.
11. 메일 저장 형식을 바꿔 예전 메일을 다시 받아야 하면 `email_reader.BODY_VERSION`을 올립니다.

### 삼성 노트
12. **삼성 노트가 켜져 있을 때 `Storage.sqlite`에 쓰지 않습니다.** 앱이 메모리 값으로 덮어씁니다. 쓰기 전에는 반드시 DB를 백업합니다(`_backup_db`).
13. 옮기는 노트는 이번에 우리가 만든 것(UUID로 특정) 또는 파일 이름이 정확히 맞는 미분류 노트만입니다. 사용자가 정리한 노트는 건드리지 않습니다.
14. 가져오는 동안 창을 **최소화하지 않습니다.** UWP라 일시정지되어 가져오기가 멈춥니다. 투명화(`HiddenNotesWindow`)를 씁니다.
15. 저장되기 전에 다음 파일을 넘기거나 앱을 닫으면 그 노트는 사라집니다. 파일마다 DB에 줄이 생긴 것을 확인하고 넘어갑니다.
16. 삼성 노트 실험은 실제 노트를 만듭니다. 그 과목 강의자료처럼 들어가도 되는 파일로만 하고, 무엇이 들어갔는지 사용자에게 알립니다.

### EXE·Windows
17. EXE에서 작업 프로세스를 띄울 때 `sys.executable -c`를 쓰지 않습니다(창이 새로 뜸). `붕어빵.exe --autosaver-job <kind>`를 씁니다.
18. `console=False` EXE는 `sys.stdout`이 없고 한국어 Windows 기본 인코딩은 cp949입니다. 작업 출력은 `_bind_worker_output`이 UTF-8로 잡습니다.
19. PyInstaller 결과물에서 `pythonnet`의 `runtimes\*`를 지우지 않습니다(pywebview가 깨짐).
20. 한글이 든 `.ps1`은 **UTF-8 BOM**으로 저장합니다. BOM이 없으면 PowerShell 5.1이 구문 오류를 냅니다.
21. 포트 8765는 다른 도구가 잡고 있을 수 있습니다. 앱은 빈 포트로 옮겨 뜨고(`app.start_server`), 서버는 `SO_EXCLUSIVEADDRUSE`로 혼자 잡습니다. **내가 띄우지 않은 프로세스는 끄지 않습니다.**
22. 실행 파일 안의 파이썬 코드는 GitHub 파일 교체로 바뀌지 않습니다. 설치형 앱의 `updater.apply_update`는 막혀 있습니다.

### 화면 (web/)
23. 프레임워크 없는 단일 `app.js`입니다. 새 화면 부분은 `RENDER_PARTS`에 서명과 함께 넣어, 값이 안 바뀌면 다시 그리지 않게 합니다.
24. 전역 `[hidden] { display: none !important; }`가 있습니다. 요소를 숨길 때는 `el.hidden`을 씁니다.
25. 수백 줄짜리 목록은 아이콘을 `iconHtml()`로 처음부터 넣고, 리스너는 부모에 하나만 겁니다. 접힌 내용은 펼칠 때 그립니다.
26. 화면 문구는 사람 말로 짧게. 오류는 `humanError`로 바꿔 보여 줍니다.
26-1. **목록을 고치는 기능은 드래그를 기본으로 만듭니다.** 순서 바꾸기·옮기기·담기는 끌어 놓기로 되게 하고, 버튼·메뉴는 보조로만 남깁니다 (키보드와 좁은 화면 때문에 지우지는 않습니다).
26-5. **영어 화면**: 화면 문구를 새로 넣거나 고치면 `python scripts/i18n_extract.py` 를 돌려 `web/i18n/en.json` 에 영어를 채웁니다(빠진 것 0 이 되게). 사용자 자료(메일·과목명)는 번역하지 않습니다.
26-2. 다만 **주간 시간표는 버튼(편집 창) 방식을 지킵니다.** 사용자가 그렇게 정했습니다. 시간표에 드래그 이동을 다시 넣지 않습니다.

### 마스코트 달구·첫 실행 소개
26-3. 달구 그림은 `design/dalgu/sheet0.png`·`sheet1.png`·`sheet2.webp`(4×4 스티커 시트, sheet2 는 걷기·달리기·옆모습)에서 `scripts/slice_dalgu.py`로 잘라 `web/img/dalgu/`에 둡니다. 포즈를 바꾸려면 스크립트의 `POSES`를 고치고 다시 돌립니다(시스템 파이썬의 Pillow 사용, 앱에는 불필요). `design/`은 설치 파일에 들어가지 않습니다.
26-4. 첫 실행 소개(`TOUR_STEPS`)는 새 화면·메뉴를 만들면 함께 고칩니다. 비출 곳은 선택자로 적고, 못 찾으면 가운데 카드로 나옵니다. 어둡게 하는 막은 큰 `box-shadow` 대신 사각형 네 장(`.tour-dim`)을 씁니다 — WebView 가 큰 그림자를 그리지 않을 때가 있었습니다. 달구는 카드에 붙어 있지 않고 단계마다 비출 곳 옆으로 걸어갑니다(`placeBuddy`). 새 단계를 넣을 때 자리는 자동으로 고르니 `pose` 만 정하면 됩니다.

### 새 버전 내기
27. `VERSION`과 `data/changelog.json` 맨 위 항목을 같은 번호로 함께 올립니다. 앱 사이드바의 '업데이트 내용'이 이 파일을 보여 주고, 설치 파일 버전도 `VERSION`을 따릅니다.
27-1. **업데이트 내용은 한 줄씩 짧게** 씁니다. 항목 하나는 30자 안팎의 명사형·짧은 동사형("고쳐 올린 자료를 Drive에서도 새 판으로 교체"), 절마다 2~4개. 원인·수치·배경 설명은 넣지 않고 `FEATURES.md`에 적습니다. 사용자가 "줄글이라 읽기 힘들다"고 했습니다.

### Git
28. 커밋·푸시는 사용자가 요청할 때만 합니다. 원격보다 앞선 커밋과 커밋 안 한 변경이 많습니다. 푸시에는 `gh auth login`이 필요합니다.

## 4. 구조 요약

```
붕어빵.exe
├─ pywebview 창 ──HTTP──> web_ui.DashboardHandler (서버 스레드, 포트 8765~8785)
├─ app.scheduler_loop (매일 예약 동기화 + 메일 5분/마감 60분/자료 180분)
├─ web_ui.start_notes_job (삼성 노트, 뒤에서)
└─ 붕어빵.exe --autosaver-job sync|deadlines|emails|verify|google-oauth
     sync → main.run_job → lms_crawler.crawl_lms → Drive 업로드 → organize_downloads
```

| 하고 싶은 일 | 볼 곳 |
|---|---|
| 새 API | `web_ui.py`의 `do_GET`/`do_POST` (`route ==` 분기) |
| 새 설정 칸 | `index.html` 설정 폼 → `app.js` `loadConfig`·저장 핸들러 → `web_ui.write_config`·`safe_public_config` → 필요하면 `runtime_config` |
| 자동 실행 주기 | `web_ui.auto_minutes`, `app.next_due_job` |
| LMS 수집 규칙 | `lms_crawler.process_content`, `download_lms_file` |
| 자료 목록 필드 | `web_ui._build_file_rows` (캐시: `_files_cache`, 메타데이터 파일 도장 기준) |
| 메일 수신 | `email_reader.MiniIMAP.fetch_structure`/`fetch_parts`, `_parse_one_message` |
| 메일 화면 | `app.js` `renderEmails`, `emailListRow`, `renderMailBody`, `mailFrameDoc` |
| 폴더 나무 | `app.js` `renderFolderView`, `buildFolderTree`, `folderTreeHtml` |
| 삼성 노트 | `samsung_notes.import_pdfs` |

## 5. 알아 두면 시간을 아끼는 사실

- LMS 로그인에서 `wait_for_load_state("networkidle")`은 시간 초과가 잦아 쓰지 않습니다.
- LMS 콘텐츠 API는 지난 학기 과목에 403을 줍니다. 오류가 아니라 정상입니다.
- 메일 HTML은 파트 번호를 찍어 받으면 안 됩니다. multipart/related에서는 2번 파트가 사진입니다. `BODYSTRUCTURE`를 먼저 읽습니다.
- quoted-printable이 헤더에 안 적혀 있는 메일이 있습니다(`_looks_quoted_printable`).
- HTML→평문 정규식에서 공백을 두 군데서 나눠 가질 수 있게 쓰면 역추적 폭발로 메일 새로고침이 멈춥니다.
- data.go.kr 오류 코드 30은 "경로는 맞고 키가 없음"입니다.
- 삼성 노트는 긴 제목을 약 50자에서 자르고 중복에 `_2`를 붙입니다. 가져온 노트는 "마지막으로 열린 폴더"에 생깁니다.
- 삼성 노트 정상 종료는 노트를 막 가져온 직후엔 썸네일을 만드느라 약 15초 걸립니다. 강제로 닫아도 썸네일은 다음 실행 때 다시 만들어집니다.
- Windows에서 파이썬 기본 HTTP 서버는 이미 쓰이는 포트도 같이 잡을 수 있습니다(SO_REUSEADDR).
- 설치형 앱의 문서 폴더는 OneDrive 아래일 수 있습니다. 경로는 `SHGetKnownFolderPath`로 찾습니다.
- Claude 데스크톱의 스크린샷 도구는 허용하지 않은 앱 창을 검은 사각형으로 가립니다. 그 사각형을 앱 창으로 착각하지 않습니다.
