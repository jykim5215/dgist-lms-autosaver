# 붕어빵 기능 지도 (FEATURES.md)

DGIST 학생용 데스크톱 앱 "붕어빵"(저장소 이름 dgist-lms-autosaver)의 기능을 화면·백엔드·데이터 단위로 정리한 문서입니다.
작업 규칙과 명령어는 `CLAUDE.md`에 있습니다. 이 문서는 "무엇이 어디에 있는가"를 찾을 때 씁니다.

- 기준 버전: `VERSION` 1.11.0 (2026-09-22 기준 코드)
- 코드가 바뀌면 이 문서의 해당 절도 같이 고칩니다.

---

## 1. 한눈에 보기

앱의 핵심 목적은 **학교 생활에 필요한 정보를 자동으로 모아 한 화면에서 쓰게 하는 것**입니다.

| 모으는 것 | 출처 | 담당 모듈 |
|---|---|---|
| 강의자료 파일 | LMS (Blackboard Ultra REST API, Playwright 로그인) | `lms_crawler.py` |
| 과제 마감 | LMS | `lms_crawler.py` (`crawl_deadlines_only`) |
| 학교 메일 | DGIST 메일서버 IMAP (`mail.dgist.ac.kr:993`) | `email_reader.py` |
| 학사일정 | data.go.kr API + DGIST 홈페이지 | `academic_calendar.py`, `dgist_api.py` |
| 개설강좌·학점 | data.go.kr API + DGIST 조회 | `timetable_import.py`, `dgist_api.py` |
| 학교 공지 | DGIST 홈페이지 게시판 | `notice_board.py` |
| 셔틀 시간표 | DGIST 홈페이지 | `shuttle.py` |
| 조직도(주소록) | 사용자가 넣은 파일 | `directory.py` |
| FGLP 파견 대학 | 내장 데이터 | `fglp.py` |

모은 것을 보내는 곳은 Google Drive, Google Calendar, 삼성 노트, 내 컴퓨터(문서 폴더)입니다.

---

## 2. 실행 구조

```
붕어빵.exe (PyInstaller onedir, Python 3.14)
├─ 메인 스레드: pywebview 창 (WebView2) ─ http://127.0.0.1:<포트>
├─ 서버 스레드: ExclusiveHTTPServer + web_ui.DashboardHandler (API + 정적 파일)
├─ 스케줄러 스레드: app.scheduler_loop (30초마다 할 일 확인)
├─ 삼성 노트 스레드: web_ui.start_notes_job (요청 시)
└─ 작업 프로세스: 붕어빵.exe --autosaver-job <sync|deadlines|emails|verify|google-oauth>
```

- **포트**: 기본 8765. 다른 프로그램이 쓰고 있으면 8766~8785 중 빈 곳을 씁니다 (`app.start_server`). 이미 켜진 붕어빵은 `/healthz` 응답 모양(`ok`, `mode`)으로 알아보고 창만 엽니다.
- **작업 프로세스**: 무거운 일(LMS 크롤, 메일 수집)은 별도 프로세스로 돌립니다. EXE에서는 `sys.executable -c`를 쓰면 창이 새로 뜨므로 반드시 `--autosaver-job` 플래그(`runtime_config.WORKER_FLAG`)로 부릅니다. 진행 로그는 `task_states`에 쌓이고 `/api/task`로 화면에 갑니다.
- **공유 웹 모드**: `AUTOSAVER_MULTI_USER=1`이면 쿠키별 작업공간을 나눕니다 (`DEPLOYMENT.md`, Render). 데스크톱 앱은 단일 사용자 모드입니다.

---

## 3. 화면별 기능

화면은 `web/index.html`의 `#view-<이름>` 구간과 `web/app.js`의 렌더 함수로 이루어집니다.
`app.js`의 `RENDER_PARTS`가 "어느 화면에서 무엇을 그릴지"와 "값이 바뀌었는지 판단하는 서명"을 갖고 있어서, 보고 있지 않은 화면은 그리지 않습니다.

**목록을 고칠 때는 드래그가 기본입니다.** 대시보드 블록 순서, 내 폴더에 자료 담기, 메일 쓰기 첨부, 메일을 폴더로 옮기기가 끌어서 됩니다. 버튼과 메뉴는 키보드·좁은 화면을 위해 그대로 둡니다.
**시간표는 예외입니다.** 수업은 눌러서 편집 창으로 고칩니다 (사용자가 버튼 방식을 그대로 쓰기로 정함).

### 3.1 공통 (상단·사이드바)

| 기능 | 설명 | 코드 |
|---|---|---|
| 검색창 | 120ms 기다렸다가 지금 화면만 다시 그림 | `#searchInput` 핸들러 |
| 새로고침 버튼 | 화면마다 이름과 동작이 바뀜. 메일함·메일 쓰기에서는 숨김(메일함 안에 제 새로고침이 있다). 마지막 동기화 시각(`#lastSync`)과 한 알약(`.sync-pill`)에 묶임. 1280px 이하에서는 아이콘만. 검색은 Ctrl+K | `VIEW_REFRESH`, `runViewRefresh`, `updateRefreshButton` |
| 통합 검색 | 상단 검색창. 치는 동안 과목·자료·과제·메일·일정(메일 행사·내 일정·학사일정)·공지·설정을 무리별로 보여 주고 고르면 이동. 초성 검색, ↑↓/Enter/Esc, Ctrl+K. 과제·찾지 못한 자료는 그 화면을 이름으로 거름(검색창을 비우면 풀림) | `buildSearchResults`, `renderSearchPop`, `bindSearchPop`, `matchScore` |
| 마지막 동기화 표시 | "자동 · 마감 16시간 전 · 메일 1분 전" | `renderLastSync`, `/api/health` |
| 위쪽 진행 막대 | 동기화 단계 또는 삼성 노트 진행 | `showTopProgress`, `renderTask`, `watchNotesJob` |
| 테마 카드 | 누를 때마다 다음 테마 | `#themeFlip` |
| 시계·지금 수업 | 사이드바 위 시계, 시간표 기준 현재 수업 | `renderNowBar` (1초마다, 값이 같으면 DOM 안 건드림) |
| 동기화 경고 배너 | 연속 실패 또는 3일 이상 동기화 안 됨 | `renderHealth` |
| 화면 자동 갱신 | 작업 중 2초, 평소 12초, 창이 가려지면 쉼 | `refreshAll` 타이머 |
| 첫 실행 소개 | 처음 켜면 마스코트 달구가 메뉴를 하나씩 비추며 기능을 알려 줌(12단계, 건너뛰기·이전·다음, 키보드 ←→ Esc). 본 기록은 데이터 폴더 `tutorial.json`. 설정의 '앱 소개 다시 보기'로 다시 봄. 마치면 처음 쓰는 사람의 '새 업데이트' 점은 끔 | `TOUR_STEPS`, `startTour`, `/api/tutorial`, `/api/tutorial/done`, `web/img/dalgu/` |
| 업데이트 소식 | 새 버전일 때만 사이드바 아래 상태 카드 바로 위에 '새 업데이트' 카드가 붙음. 누르면 바뀐 내용 창, 한 번 보면 사라짐(지난 내용은 설정의 '업데이트 내용'). 본 기록은 데이터 폴더 `whats_new.json` | `loadWhatsNew`, `openWhatsNew`, `/api/whats-new`, `data/changelog.json` |

### 3.2 대시보드 (`dashboard`)

- 인사말: 명조체 한 줄 + 불꽃 표시, 이름(보낸 편지함의 내 이름에서 성을 뺌), 아래에 '오늘 남은 수업 · 7일 안 마감 · 안 읽은 메일'. 문장은 시간대별로 하루 동안 고정 (`setHeroGreeting`, `HERO_LINES`)
- 학사일정 D-day: 시험 → 정규 수강신청·변경·포기 → 그 밖(등록·성적확인·계절학기 등) 순서. 석 달 안에 시험·정규 수강신청이 있으면 그것 먼저, 아래에 다음 두 개 (`DDAY_TIERS`, `ddayTier`, `renderDday`). 대학원만의 일정은 뺌
- 지표 카드: 임박한 마감, 전체 자료, 강의 수, 새 메일
- **주간 시간표**: 수업을 눌러 편집 창에서 고치기(드래그로 옮기지 않음 — 사용자가 정한 방식), 에브리타임 링크 가져오기, 시간표 이미지 가져오기(Gemini 키 필요), 토요일 표시
  - 색: 과목(과목번호, 없으면 이름)마다 반드시 다른 색. 12가지(`TT_COLORS`, `.tone-*`). 그릴 때마다 `normalizeTtColors`가 겹친 과목만 다시 칠하고 바뀐 칸만 저장. 12과목을 넘을 때만 가장 적게 쓰인 색을 나눠 씀.
- 다가오는 마감, 다가오는 일정, 학교 공지, 학교 사이트 바로가기
- 화면 편집(블록 순서 끌어 옮기기), 모두 접기
- 과목 변경 감지 배너 → "확인했어요" (`/api/acknowledge-courses`)

### 3.3 과제 마감 (`deadlines`)

- LMS 과제 전체 목록, 과목·상태 필터, 목록에서 숨기기 (`upload_selection.json`의 `hiddenDeadlines`)
- 미제출 과제는 LMS 제출 페이지 열기 (`/api/assignment/open`)
- 캘린더 파일(.ics) 내보내기 (`/api/deadlines.ics`, `/api/export-ics`)

### 3.4 캘린더 (`calendar`)

- 월 달력에 과제 마감 + 학사일정 + 내 일정 + 공휴일 + **메일로 온 행사**
- 메일 행사: 공식 학사일정에는 달빛제 같은 행사가 없다. 메일 본문·제목에서 날짜를 규칙으로 뽑고(`email_reader.guess_event_date`, AI 불필요), 관심 분야와 맞는 세미나와 학교 전체 행사만 `calendar` 로 표시(`web_ui._mark_events`). 같은 날 같은 행사의 재공지는 하나로 합침. 구글 캘린더 동기화도 이 표시가 붙은 것만 보냄
- 색: 과제 마감 빨강(`cal-deadline`), 학교 행사 노랑(`cal-school`, `schoolEvent`), 관심 세미나 보라(`cal-event`), 제출 완료 초록, 내 일정 파랑, 학사일정 회색 띠. 칸 이름은 `app.js eventShortTitle` 이 날짜·연도·"개최 안내"를 떼고 영어 제목이면 [학과] 꼬리표로 만든다. 오른쪽 상세는 짧은 이름 + 메일 원래 제목 전체(`it.full`)를 줄바꿈해 보여 준다
- 상세에서 메일 일정을 누르면 메일함으로 가지 않고 그 칸이 펼쳐지며(`toggleDayMail`, `.day-item.open`) 본문 글(`mailPlainText`, 주소는 `linkifyText` → `/api/mail/open-link`)을 보여 준다. 읽는 동안 패널이 넓어짐(`.calendar-stage.reading`). '메일함에서 열기'는 보조 버튼
- 학사일정: 대학/대학원 구분, "학부만" 필터
- 내 일정 추가·수정·삭제 (`my_events.json`), 장소는 OpenStreetMap 검색 (`/api/place-search`)
- 구글 캘린더로 학사일정 올리기 (`/api/gcal/sync-academic`)

### 3.5 강의 (`courses`)

- 수강 과목 카드 (자료가 없는 과목도 `courses_state.json`에서 깔아 둠)
- 과목마다 학년·학기, 학점(개설강좌에서 채움, `_fill_missing_credits`), 강의계획서 바로가기
- 편집 모드로 과목 숨기기/복원
- 개설강좌 목록 (`/api/course-catalog`, `/api/course-terms`)

### 3.6 자료 (`files`)

도구줄: 보기 탭(과목 폴더 / 내 폴더 / 전체 목록, `.file-mode-tab`) · 과목 · 파일 상태(받은 파일/파일 없음) · ⋯ 정리 메뉴(`#filesMoreMenu`).
고른 자료가 있을 때만 그 아래에 '할 일' 막대(`#fileSelectBar`, `updateBulkSaveButton`)가 나타나고, ✕ 로 모두 푼다(`clearFileSelection`).

보기 방식 세 가지 (`state.fileMode`):

1. **리스트**: 전체 표. 체크, Shift+클릭 범위 선택, Ctrl+클릭 행 선택. 최대 400행. 클릭 리스너는 표에 하나만 (`bindFileTableOnce`).
2. **과목별 폴더 (LMS 구조)**: 과목 카드 → LMS와 같은 폴더 나무(예: 1주차 > Lecture 1 > 파일).
   - 폴더와 파일을 LMS에 올라온 순서(`lmsOrder`)대로 섞어 놓음. 순서를 모르면 사람이 읽는 순서("2주차" < "10주차").
   - 하위 폴더마다 전체 선택 체크박스, 일부만 고르면 반쯤 찬 상자.
   - 접힌 폴더는 펼칠 때 그림 (`fillLazyFolder`, `fillLazySubfolder`).
   - 코드: `renderFolderView`, `buildFolderTree`, `folderTreeHtml`, `subfolderHtml`, `compareLmsOrder`.
3. **내 폴더**: 사용자가 만든 폴더에 자료 담기 (`shelves.json`, `/api/shelves`, `/api/shelves/save`).

고른 자료에 하는 일 (`/api/files/bulk`의 `action`):

| 버튼 | action | 동작 |
|---|---|---|
| 내 컴퓨터에 저장 | (별도) `/api/save-local` | `문서\붕어빵 파일 정리\<과목>\`에 복사 |
| Drive에 올리기 | `drive` | 과목 폴더로 업로드, 이미 있으면 건너뜀 |
| 삼성 노트로 | `notes` | 뒤에서 넣기 시작, 즉시 응답 (4.4절) |
| 목록에서 빼기 | `hide` | 파일은 두고 목록에서만 뺌 (`hiddenFiles`) |

⋯ 메뉴: 학기·과목 폴더로 정리(`/api/organize-files`, 옮기고 중복 제거), 삼성 노트 폴더 정리(`/api/samsung-notes/organize`, 삼성 노트 있는 PC만), 숨긴 자료 되돌리기(뺀 게 있을 때만).
예전 보기 전환 버튼은 메일함과 같은 `.view-toggle-btn` 클래스라 메일함 클릭 처리기가 같이 걸려 `emailView`를 망가뜨렸다. 이제 `.file-mode-tab` 이다.
동기화 시작은 위쪽 '자료 새로고침' 하나뿐이다. `#runButton`은 작업 중에만 '작업 중지'로 나타난다. '검증' 버튼(`/api/verify`)은 화면에서 뺐다(설정의 '전체 다시 확인'과 겹쳐서). API 와 작업 종류는 그대로 있다.

### 3.7 메일함·메일 쓰기 (`emails`, `compose`)

메일 쓰기는 사이드바 메뉴가 아니라 메일함 안의 '메일 쓰기' 버튼으로 연다(`switchView("compose")`). 쓰는 동안 사이드바는 '메일함'이 켜진 채로 둔다.

목록:
- **삼성 이메일식 세 줄**: 메일함 꼬리표 · 보낸 사람 · 시각(오늘은 "오전 10:32", 지난 것은 "9월 7일") / 제목 / 미리보기 · 별표. 첨부가 있으면 클립 아이콘.
- **날짜 묶음**: 오늘, 어제, "9월 6일 일요일" (최신순일 때만). `emailListHtml`, `mailDayLabel`.
- **메일함 새로고침**: 메일함 제목 옆 버튼. 마지막으로 받은 때를 "3분 전 업데이트"로 표시 (`refreshMailNow`, `renderMailRefreshAgo`).
- 폴더: 받은/보낸/임시/휴지통/프로모션. 분류 탭: 기본, LMS·공지. 빠른 필터: 안읽음, 중요(별표), 첨부.
- 카드 보기와 목록 보기, 정렬(최신·오래된·보낸 사람·제목·관심도).
- 선택해서 읽음/안읽음/삭제/되돌리기, 모두 읽음.
- **드래그로 옮기기**: 메일 줄을 왼쪽 폴더로 끌어다 놓으면 받은 편지함·프로모션으로 이동, 휴지통으로 삭제, 중요로 별표. 고른 메일이 여럿이면 함께 옮겨집니다 (`bindMailDrag`, `dropMailsOnFolder`). 휴지통에서 받은 편지함으로 끌면 되돌리기.

읽기 화면:
- HTML 메일을 스크립트 막은 iframe(srcdoc)으로 그림. 밝은 테마에서는 본문 바탕을 투명하게 하고 메일 속 순백 바탕을 걷어 내 앱 배경 위에 앉힘(`blendMailBackground`). 다크 테마는 종이 카드 위에 올림(`mailOnPaper`). 남색 테마는 1.11.10부터 밝은 바탕 + 잉크 남색 강조(`#3e63a6`)라 밝은 테마로 친다. 본문 안 그림(`cid:`)은 `/api/mail-image`로 서빙. 긴 메일은 40,000px까지 높이 맞춤.
- 본문 링크는 기본 브라우저에서 열림(`bindMailLinks`, `/api/mail/open-link`). 메일 주소(mailto:)는 앱의 메일 쓰기로 열림. http·https 가 아닌 주소는 열지 않음.
- 답장, 전체 답장, 전달, 이전/다음 메일, 별표(서버 `\Flagged`), 삭제.
- ⋮ 메뉴: 읽지 않음으로 표시, 한국어로 번역, 다시 알림, 이메일 이동(폴더 만들기 포함), 인쇄, 파일로 저장(.eml), 일정 추가, 리마인드 메일 쓰기.
- 답장 안 온 보낸 메일 찾기 (`/api/mail/pending`) → 리마인드 초안 (`/api/mail/reminder`).

쓰기:
- 서식 도구, 서명, 인용, 주소 찾기(조직도 + 받은 주소 자동완성), 임시저장, 미리보기.
- 첨부: 내 PC, 사진, URL, Drive, "내 자료"(받아 둔 강의자료, 쓰기 창 아래에 펼침).
- 보내기: 학교 SMTP (`/api/send-email`, `smtp.dgist.ac.kr:465`).

### 3.8 창고 (`storage`)

- FGLP 파견 지도: 세계지도(`web/img/world.png`) 위 대학 핀, 대륙별 확대, FGLP/학점교류 탭 (`/api/fglp`)
  - 자료: `fglp.py`. 2027 국제학부 입학안내서(2026.6) 13·15쪽 기준. FGLP 28곳(TYPE 1 25, TYPE 2 3), 학점교류는 이름 나온 11곳. 안내서는 그림 PDF라 눈으로 옮겨 적음.
  - 핀의 기준점은 점 한가운데(`.wm-pin`은 점 크기, 이름표는 절대 위치). 덩어리 가운데를 맞추면 점이 이름표 폭 절반만큼 밀린다.
  - 대학 사진: `tools/fetch_uni_photos.py` (위키미디어, 작성자·라이선스 기록). 엉뚱한 사진이 골라진 곳은 `SKIP`.
- 셔틀버스 시간표 (`/api/shuttle`): 출근·퇴근·원내순환·원외순환·주말순환. 하루 캐시, 못 받으면 예전 시간표라고 표시. 해석은 `shuttle._routes_from_table`이 표 머리줄의 칸 이름을 읽어 정함

### 3.9 설정 (`settings`)

사용자가 바꿀 일이 있는 것만 둔다. 한 단짜리 카드(`.st-card`, 머리에 색 타일 + 한 줄 설명)를 위에서 아래로 읽는다.
긴 설명은 `?`(`.hint`, `data-hint`)에 숨긴다. 마우스를 올리거나 누르면 보이고, 다른 곳을 누르거나 Esc 로 닫힌다.
개발자용 칸(다운로드 경로·LMS 주소·로그인 주소)은 화면에서 뺐다. 폼에 없으면 `write_config`가 저장된 값을 그대로 둔다.

| 카드 | 내용 |
|---|---|
| 연결된 계정 | LMS·학교 메일·Google 줄마다 로고와 상태 알약(`renderAccountPills`, `renderGoogleSection`). 비밀번호는 DPAPI 암호화, 바꿀 때만 입력 |
| 강의자료 저장 | 저장 위치 카드 두 개: 구글 드라이브(`AUTO_DRIVE_UPLOAD`, 구글 미연결이면 '로그인 필요'), 내 컴퓨터(스위치 + 이번 학기/모든 과목 → `AUTO_LOCAL_SAVE`, 폴더 바꾸기, 지금 맞추기). `renderSaveDestinations` |
| └ 다른 클라우드 | OneDrive·Dropbox·iCloud Drive·네이버 MYBOX. 로그인 없이 PC 동기화 폴더 안 `붕어빵 강의자료\<과목>`에 넣는다 (`detect_cloud_roots`, `cloud_targets`, 설정 `CLOUD_SAVE`). 못 찾으면 '폴더 고르기'(`/api/pick-folder`)로 `path` 지정. '넣을 과목'(`SAVE_SCOPE`)과 '지금 맞추기'는 내 컴퓨터·클라우드 공통. 복사는 `autosave_local` → 위치마다 `_mirror_rows` (필기한 파일 보호 규칙 동일). 과목 아래는 LMS 하위 폴더(`lms_subfolders`) 그대로, 1.11.3까지 펼쳐 넣은 사본은 옮겨 놓는다 |
| └ 차지하는 공간 | 같은 카드 아래. 앱(프로그램 + LMS 로그인용 브라우저 + 메일·설정 데이터) / 강의자료 / 내 컴퓨터 사본을 한 막대로(`/api/storage`의 `app`·`localSave`). 접힌 '강의자료 정리하기'에서 학기·과목별 삭제(`/api/storage/cleanup`, 앱 보관함에서만) |
| 자동으로 가져오기 | 메일(기본 5분)·과제 마감(60분)·강의자료(180분) 주기, 하루 한 번 전체 확인 시각(`SCHEDULE_TIME`) |
| 구글 캘린더 | 머리의 스위치로 메일 일정 자동 등록, 캘린더 이름, 지금 넣기, 학사일정도 넣기 |
| 관심 있는 메일 | 관심 분야·활동 태그, 직접 적기, 끝난 행사 메일 숨기기 |
| 추가 기능 켜기 (접힘) | Gemini 키(번역·요약·시간표 사진), DGIST 공공데이터 키 |
| 앱 | 버전, 업데이트 내용, 전체 다시 확인, 설정 내보내기/불러오기(비밀번호 포함 여부) |

앱 크기에서 브라우저는 `chromium_headless_shell-*` 만 센다. 같은 `ms-playwright` 폴더의 일반 `chromium-*`(약 430MB)은 개발용이라 앱 몫이 아니다.
프로그램·브라우저 크기는 10분 동안 기억한다(`_FOOTPRINT_CACHE`). 프로그램 크기는 EXE 로 돌 때만 나온다.

GitHub 업데이트 확인 버튼은 뺐다. 설치형은 새 설치 파일로 업데이트하고, 저장소 버전이 뒤처져 있어 "최신"이라는 오답을 줬다(4.9절).

---

## 4. 기능별 동작 상세

### 4.1 LMS 자료 동기화 (`lms_crawler.py`)

1. `ensure_browser()`로 Chromium headless shell 확보 (`%LOCALAPPDATA%\ms-playwright`, 처음 한 번 내려받음)
2. `login_lms()`: SAML 로그인. `networkidle`을 쓰지 않고 선택자·URL·`/users/me` 응답으로 기다림.
3. 과목 목록 → 과목 4개씩 병렬 `crawl_course`
4. `process_content` 재귀:
   - Zoom·외부 링크·설문·"class recording" 건너뜀
   - 파일 항목(x-bb-file)의 첨부 + 문서(x-bb-document) 본문 안 파일(`extract_body_files`)
   - 폴더 경로 `folder_path`: 폴더 제목을 쌓음. `Weekly Schedule`, `ultraDocumentBody`는 넣지 않음 (`HIDDEN_FOLDER_TITLES`).
   - 여러 파일을 담은 문서는 문서 제목을 한 칸 더 둠
   - LMS 순서 `lms_order`: 각 단계의 위치 번호 목록
5. `download_lms_file`: 동영상 건너뜀. 이미 받은 URL이면 내려받지 않고 `remember_lms_place`로 경로·순서만 갱신. 같은 과목의 같은 파일명은 새 사본을 만들지 않고 덮어씀.
6. 공지사항 첨부도 받음 (`공지사항(Announcements)` 폴더)
7. 끝나면 `web_ui.organize_downloads`가 `downloads\<학기>\<과목>\`로 옮기고 `stored` 경로 기록

빠른 모드(`AUTOSAVER_SYNC_MODE=fast`, 기본)는 마지막 동기화 2일 전 이후 바뀐 파일만 확인합니다. 순서·경로가 비어 있는 옛 자료를 채우려면 전체 모드로 한 번 돌립니다. 지난 학기 과목은 LMS가 403으로 막아 순서가 안 채워집니다.

### 4.2 과제 마감

`crawl_deadlines_only` → `deadlines.json`. 과목별 과제, 기한, 내 제출 상태(`myStatus`). 캘린더·대시보드·마감 화면이 함께 씀.

### 4.3 학교 메일 (`email_reader.py`)

- 서버 특성: IMAP4rev1, XLIST, AUTH=LOGIN만. **IDLE·UIDPLUS·MOVE·CONDSTORE 없음** → 실시간 푸시 불가, 주기 확인.
- 증분 수집: 서버에는 UID 목록만 묻고, 이미 가진 메일은 재사용. 읽음·별표만 서버 기준으로 맞춤.
- **구조 기반 수신**: `BODYSTRUCTURE`를 먼저 읽어(`parse_paren_list`, `bodystructure_parts`) text/plain·text/html 파트 번호를 찾아 그것만 받음. HTML은 40만 바이트까지 받고 30만 자까지 저장.
- 본문 그림: `inlineImages` 메타만 저장 → 메일을 열 때 `fetch_inline_images`가 한 번의 접속으로 받아 `mail_images\`에 저장.
- 첨부: `attachments` 메타(이름·형식·크기), `hasAttachment`. 내려받기 기능은 아직 없음.
- `BODY_VERSION`(현재 3)이 올라가면 예전에 받은 메일을 한 번 다시 받음.
- quoted-printable 판별(`_looks_quoted_printable`), HTML→평문 정리(`clean_html_to_text`, 역추적 폭발 없는 정규식).
- 분류: 규칙 기반(`rule_based_category`), Gemini 키가 있으면 관심도·요약 추가.
- 번역(`translator.py`): Gemini 키가 있으면 Gemini, 없으면 로컬 Ollama(`qwen3:8b` 등, 생각 끔).
- 목록 API는 본문을 빼고 줌(`get_emails`, 파일 도장 기준 캐시). 본문은 `/api/email-body`로 한 통씩.

### 4.4 삼성 노트로 보내기 (`samsung_notes.py`)

삼성은 노트 생성 API를 주지 않습니다. Windows 삼성 노트 앱의 `.pdf` 파일 연결을 이용합니다.

1. 중복 확인: 노트 DB(`Storage.sqlite`, 읽기 전용)의 제목과 한 번에 대조. 삼성 노트는 긴 제목을 50자쯤에서 자르고 중복에 `_2`를 붙이므로 `_title_matches`로 맞춤.
2. 앱이 꺼져 있으면 먼저 띄워 준비될 때까지 기다림 (`_notes_ready`: 겉창 안에 CoreWindow가 붙었는지)
3. `HiddenNotesWindow`: 가져오는 동안 겉창(`ApplicationFrameWindow`)을 알파 0 + 클릭 통과로 붙잡아 둠. 초점을 가져가면 원래 창에 돌려줌.
4. 파일마다 WinRT `Launcher.launch_file_with_options_async`로 넘기고, 새 노트 줄(`Id > 시작 Id`, `IsSaving=0`)이 생길 때까지 0.2초 간격으로 확인 (최대 40초)
5. 정상 종료 요청(`WM_SYSCOMMAND SC_CLOSE`). 우리가 켠 앱이면 4초, 원래 켜져 있던 앱이면 20초 기다린 뒤 강제 종료.
6. 닫힌 뒤 `organize_uuids`: DB 백업 후, 이번에 생긴 노트(UUID로 특정)만 과목 이름 폴더로 옮김
7. 원래 켜 두었던 앱이면 다시 띄움

화면에서는 `start_notes_job`이 뒤에서 돌리고 `/api/samsung-notes/job`으로 진행을 알려 줍니다.
실측: 준비 약 4초, 파일당 저장 약 5.5초.

### 4.5 Google 연동

- OAuth: 앱에 들어 있는 데스크톱 클라이언트(`google_client.json`), 토큰은 `token.json`. 설치형 클라이언트라 루프백 포트가 바뀌어도 됩니다.
- Drive (`drive_uploader.py`): 루트 폴더 아래 과목 폴더, 업로드 선택(`upload_selection.json`의 `courses`)을 따름. 권한은 `drive.file`.
- Calendar (`calendar_sync.py`): 메일에서 뽑은 일정, 학사일정을 지정한 캘린더로.

### 4.6 DGIST 공공데이터 (`dgist_api.py`)

기관코드 B552467. `OpenLtService/UnivLtList`(개설강좌), `AcademicScheService/UnivSchisList`·`GrscSchisList`(학사일정), `EvtntcListService01/getNtcList01`(세미나·행사).
키 순서: 환경변수 `AUTOSAVER_DGIST_API_KEY` → 설정 `DGIST_API_KEY` → `config.py`. 오류 코드 30은 "경로는 맞고 키가 없음".
키가 없을 때를 위해 배포본에 씨앗 데이터(`data/seed_*.json`, `scripts/build_seed.py`)를 넣고 캐시 기한은 학사일정 7일, 개설강좌 14일입니다.

### 4.7 자동 실행 (`app.scheduler_loop`)

- 30초마다 확인. 켜고 45초는 쉼, 매일 동기화는 켜고 2분 뒤부터.
- **매일 예약 동기화**: `SCHEDULE_TIME`(기본 08:00)이 지났고 `last_sync.json`의 날짜가 오늘이 아니면 실행. 끝나면 Windows 알림.
- **주기 실행** (`next_due_job`): `health.json`의 마지막 성공 시각 기준으로 메일 → 마감 → 자료 순서로 하나만. 실패 직후에는 주기의 절반(최소 5분) 쉼.
- 결과는 `record_task_result`가 `health.json`에 기록 → 화면의 마지막 동기화 표시와 경고 배너.

### 4.8 내 컴퓨터에도 자동 저장 (`web_ui.autosave_local`)

Drive 자동 업로드처럼, 동기화로 받은 자료를 내 컴퓨터 저장 폴더(`<저장 폴더>\<과목>\<파일>`)에도 둡니다. 수동 "내 컴퓨터에 저장"과 같은 자리라 두 벌이 생기지 않습니다.

- 설정 `AUTO_LOCAL_SAVE`: `off`(기본) / `current`(가장 최근 학기 자료만) / `all`
- 실행 시점: 자료 동기화가 성공하고 학기 폴더 정리가 끝난 직후 (`run_process`). 설정에서 새로 켜면 곧바로 한 번 (`/api/local-autosave/run`, 뒤에서 실행).
- Drive와 같은 과목 선택(`upload_selection.json`의 `courses`)을 따릅니다.
- 이미 있는 파일 처리:
  - 크기가 원본과 같으면 건너뜀
  - 우리가 복사한 뒤 아무도 안 건드렸는데 LMS 자료가 바뀌었으면 새 것으로 교체
  - 사용자가 필기 등으로 고친 파일이면 그대로 두고 `이름 (LMS 새 버전).확장자`로 옆에 저장
  - "우리가 복사한 그대로인지"는 `local_autosave.json`에 적어 둔 크기·수정 시각으로 판단
- 260자가 넘는 경로도 확장 경로(`_long_path`)로 복사합니다.
- 실측: 이번 학기 80개 처음 1.2초, 다시 실행 0.25초. 모든 과목 추가 189개 5.2초.
- 문서 폴더가 OneDrive 아래면 복사한 자료가 OneDrive에도 올라갑니다.

### 4.9 자가 업데이트 (`updater.py`) — 제한 있음

GitHub raw에서 `UPDATE_FILES`를 모두 받은 뒤에만 덮어씁니다.
**설치형 EXE에서는 동작하지 않게 막아 두었습니다** (코드가 실행 파일에 묶여 있어 화면 파일만 바뀌면 앱이 깨짐). 저장소 버전이 더 새롭지 않으면 받지 않습니다.
현재 GitHub `main`은 1.8.6이라 로컬(1.10.1)보다 뒤처져 있습니다. 설치형 배포는 새 설치 파일로 합니다.

---

## 5. 모듈 지도

| 파일 | 책임 |
|---|---|
| `app.py` | 데스크톱 진입점. 서버 띄우기(포트 선택), pywebview 창, 스케줄러, 알림, 작업 프로세스 분기 |
| `web_ui.py` | HTTP 서버와 모든 API. 설정 읽기/쓰기(DPAPI), 작업 실행, 자료 목록, 메일 본문·그림, 삼성 노트 작업, 정리·저장·Drive |
| `runtime_config.py` | 작업 프로세스와 공유하는 설정 상수, 데이터 경로, `WORKER_FLAG`, `SECRET_KEYS` |
| `main.py` | `sync` 작업 본체: LMS 크롤 → Drive 폴더·업로드 → 알림 메일 |
| `lms_crawler.py` | LMS 로그인, 자료·공지·마감 수집, 폴더 경로·순서 기록 |
| `browser_setup.py` | Playwright Chromium 확보 |
| `email_reader.py` | IMAP 수집·구조 해석·본문·그림·분류, 읽음/별표/이동/삭제, SMTP 보내기, 리마인드 |
| `email_notifier.py` | 동기화 결과 알림 메일 (함수 이름 `send_kakao_message`는 옛 이름, 실제로는 메일) |
| `translator.py` | 메일 번역 (Gemini 또는 Ollama) |
| `samsung_notes.py` | 삼성 노트 넣기·숨김·폴더 정리 |
| `drive_uploader.py` | Google Drive 인증·폴더·업로드 |
| `calendar_sync.py` | Google Calendar 동기화 |
| `academic_calendar.py` | 학사일정 (API + 홈페이지 병합) |
| `dgist_api.py` | data.go.kr 클라이언트 |
| `timetable_import.py` | 에브리타임 링크, 시간표 이미지(Gemini), DGIST 개설과목 |
| `course_meta.py` | 과목명에서 학기·학년 뽑기, 강의계획서 판별 |
| `notice_board.py` | 홈페이지 공지 |
| `shuttle.py` | 셔틀 시간표 |
| `directory.py` | 조직도 검색 |
| `fglp.py` | FGLP 파견 대학 데이터 |
| `ai_summarizer.py` | Gemini 호출 공통 (모델 대체 순서) |
| `updater.py` | GitHub 자가 업데이트 (소스 실행에서만) |
| `verify.py` | LMS 목록과 받은 파일 대조 (`verify` 작업) |
| `setup.py`, `check_courses.py` | 옛 CLI 도구 |
| `scripts/dev_server.py` | 소스 그대로 8794 포트에 대시보드 |
| `scripts/build_seed.py` | 씨앗 데이터 만들기 |
| `scripts/make_icons.py`, `scripts/extract_logo.py` | 아이콘 만들기 |
| `bungeoppang.spec` | PyInstaller 설정 |
| `packaging/` | Inno Setup 스크립트와 빌드 스크립트 |
| `web/index.html`, `web/app.js`, `web/styles.css` | 화면 전부 (프레임워크 없음) |

---

## 6. API 목록

모든 경로는 `web_ui.DashboardHandler`에 있습니다. POST는 `Content-Type: application/json`이어야 합니다(CSRF 방어). 로컬 모드는 Host가 루프백일 때만 받습니다.
브라우저가 gzip을 받으면 1KB 넘는 JSON 응답과 js·css·html 파일을 압축해 보냅니다.

### GET

| 경로 | 내용 |
|---|---|
| `/healthz` | 살아 있는지 (`ok`, `mode`) |
| `/api/status` | 설정 존재, 구글 연결, 개수, 작업 상태 |
| `/api/task` | 실행 중 작업과 로그 |
| `/api/health` | 종류별 마지막 성공·실패 |
| `/api/config`, `/api/config/export` | 공개 설정, 백업 내보내기 |
| `/api/files` | 자료 목록 (`folderPath`, `lmsOrder`, 학기·학년, 상태) |
| `/api/file?name=` | 파일 내려받기 |
| `/api/selection` | 업로드 선택·숨김 목록 |
| `/api/shelves` | 내 폴더 |
| `/api/storage` | 저장 공간 사용량 |
| `/api/deadlines`, `/api/deadlines.ics` | 과제 마감, ics |
| `/api/course-state`, `/api/course-catalog`, `/api/course-terms` | 수강 과목, 개설강좌, 학기 목록 |
| `/api/timetable` | 시간표 |
| `/api/academic-calendar`, `/api/my-events` | 학사일정, 내 일정 |
| `/api/notices`, `/api/seminars` | 학교 공지, 세미나 |
| `/api/shuttle`, `/api/fglp`, `/api/directory` | 셔틀, FGLP, 조직도 |
| `/api/place-search?q=` | OpenStreetMap 장소 검색 |
| `/api/emails` | 메일 목록 (본문 없음) |
| `/api/email-body?id=` | 본문, HTML(cid 주소 치환), 첨부 메타 |
| `/api/mail-image?id=&n=` | 본문 그림 한 장 |
| `/api/mail/folders`, `/api/mail/pending`, `/api/mail/eml` | 메일함 목록, 답장 대기, eml |
| `/api/drive/list`, `/api/drive/get` | Drive 파일 (첨부용) |
| `/api/samsung-notes/status`, `/api/samsung-notes/job` | 설치 여부, 넣기 진행 |
| `/api/local-autosave/job` | 내 컴퓨터 자동 저장 진행 |
| `/api/dgist-api/status` | 공공데이터 키 확인 |
| `/api/update/check` | 업데이트 확인 |

### POST

| 경로 | 내용 |
|---|---|
| `/api/run` | 자료 동기화 (`mode`: fast/full) |
| `/api/refresh-deadlines`, `/api/refresh-emails`, `/api/verify`, `/api/stop` | 작업 시작·중지 |
| `/api/config`, `/api/config/import` | 설정 저장, 백업 불러오기 |
| `/api/google/connect`, `/api/google/disconnect`, `/api/google/credentials` | 구글 계정 |
| `/api/gcal/sync`, `/api/gcal/sync-academic` | 구글 캘린더 |
| `/api/selection`, `/api/acknowledge-courses` | 선택·숨김 저장, 과목 변경 확인 |
| `/api/files/bulk` | 일괄 작업 (`drive`, `notes`, `hide`) |
| `/api/save-local`, `/api/organize-files`, `/api/open-downloads`, `/api/pick-folder` | 로컬 저장·정리 |
| `/api/local-autosave/run` | 내 컴퓨터 자동 저장 지금 실행 (`mode`: current/all, 뒤에서) |
| `/api/shelves/save`, `/api/storage/cleanup` | 내 폴더, 저장 공간 정리 |
| `/api/samsung-notes/send`, `/api/samsung-notes/organize` | 한 개 넣기(뒤에서), 노트 폴더 정리 |
| `/api/timetable/save`, `/api/timetable/delete`, `/api/timetable/bulk`, `/api/timetable/import-link`, `/api/timetable/import-image` | 시간표 |
| `/api/my-events/save`, `/api/my-events/delete`, `/api/export-ics` | 내 일정, ics 저장 |
| `/api/mark-read`, `/api/mark-all-read`, `/api/delete-email`, `/api/restore-email` | 메일 상태 |
| `/api/mail/star`, `/api/mail/move`, `/api/mail/folder-create`, `/api/mail/reminder`, `/api/mail/translate` | 메일 기능 |
| `/api/mail/open-link` | 메일 본문 링크를 기본 브라우저로 (http·https 만) |
| `/api/send-email` | 메일 보내기 |
| `/api/directory/import` | 조직도 넣기 |
| `/api/assignment/open`, `/api/open-url` | 외부 페이지 열기 |
| `/api/update/apply`, `/api/restart` | 업데이트, 재시작 |

---

## 7. 데이터 파일 (`C:\lms-autosaver\`)

`AUTOSAVER_DATA_ROOT`로 바꿀 수 있습니다. 설치된 앱과 개발 서버가 **같은 폴더를 씁니다**.

| 파일·폴더 | 내용 |
|---|---|
| `config.json` | 설정. 비밀 값은 `dpapi:` 암호문 |
| `token.json`, `oauth_pending.json` | 구글 토큰, 로그인 중 상태 |
| `downloads\<학기>\<과목>\` | 받은 강의자료 |
| `file_metadata.json` | 파일별 `course`, `folder_path`, `lms_order`, `original_name`, `stored` |
| `downloaded_files.json` | 받은 URL 목록 (다시 받지 않기) |
| `courses_state.json` | 수강 과목, 추가·삭제 감지 |
| `deadlines.json` | 과제 마감 |
| `emails.json` | 메일 (본문·HTML·그림 메타·첨부 메타, `bodyVersion`) |
| `mail_images\` | 본문 그림 캐시 |
| `upload_selection.json` | Drive 과목 선택, 숨긴 과목·마감·자료 |
| `shelves.json` | 내 폴더 |
| `timetable.json`, `my_events.json` | 시간표, 내 일정 |
| `academic_calendar.json`, `notices.json`, `shuttle.json` | 캐시 |
| `last_sync.json` | 마지막 자료 동기화 시각 |
| `health.json` | 종류별 마지막 성공·실패 |
| `local_autosave.json` | 내 컴퓨터에 자동 복사한 파일의 크기·수정 시각 (사용자가 고쳤는지 판단용) |

그 밖의 위치:
- 설치 폴더: `%LOCALAPPDATA%\Programs\붕어빵`
- Playwright 브라우저: `%LOCALAPPDATA%\ms-playwright`
- 로컬 저장: `문서\붕어빵 파일 정리\<과목>\` (OneDrive 문서 폴더일 수 있음, `SHGetKnownFolderPath`로 찾음)
- 삼성 노트 DB: `%LOCALAPPDATA%\Packages\SAMSUNGELECTRONICSCoLtd.SamsungNotes_wyx1vj98g3asy\LocalState\Storage.sqlite` (백업은 같은 폴더의 `Storage.sqlite.붕어빵백업-*`)

---

## 8. 설정 키 (`config.json`)

| 키 | 뜻 | 기본 |
|---|---|---|
| `LMS_ID`, `LMS_PASSWORD`* | LMS 계정 | |
| `SCHOOL_EMAIL`, `SCHOOL_EMAIL_PASSWORD`*, `SCHOOL_IMAP_HOST` | 학교 메일 | `mail.dgist.ac.kr` |
| `EMAIL_ADDRESS`, `EMAIL_PASSWORD`*, `EMAIL_TO` | 동기화 결과 알림 메일 (선택) | |
| `GEMINI_API_KEY`* | 번역·분류·시간표 이미지 | |
| `DGIST_API_KEY`* | 공공데이터 인증키 | |
| `DOWNLOAD_PATH`, `LOCAL_SAVE_PATH` | 받는 곳, 내 컴퓨터 저장 위치 | 데이터 폴더\downloads, 문서\붕어빵 파일 정리 |
| `AUTO_LOCAL_SAVE` | 내 컴퓨터에도 자동 저장: off / current / all | off |
| `CLOUD_SAVE` | 클라우드 폴더 자동 저장 `{onedrive|dropbox|icloud|mybox: {on, path}}` (path 비면 자동으로 찾은 폴더) | 모두 꺼짐 |
| `SAVE_SCOPE` | 내 컴퓨터·클라우드에 넣을 과목: current / all (`AUTO_LOCAL_SAVE`가 켜져 있으면 그 값이 우선) | current |
| `AUTO_DRIVE_UPLOAD` | 동기화 때 구글 드라이브에도 올리기 (`runtime_config.DRIVE_UPLOAD`, 끄면 `main.run_job`이 받기만 함) | true |
| `SCHEDULE_TIME` | 매일 동기화 시각 | `08:00` |
| `AUTO_EMAIL_MINUTES`, `AUTO_DEADLINE_MINUTES`, `AUTO_SYNC_MINUTES` | 자동 주기(분), 0이면 끔 | 5, 60, 180 |
| `GCAL_SYNC_ENABLED`, `GCAL_CALENDAR_NAME` | 구글 캘린더 | 꺼짐, `DGIST 메일 일정` |
| `EMAIL_INTEREST_TAGS`, `EMAIL_INTERESTS_CUSTOM`, `EMAIL_HIDE_PAST` | 메일 관심사, 지난 일정 숨김 | |
| `LMS_URL`, `LOGIN_URL` | LMS 주소 | |

`*` 표시는 비밀 값입니다. `web_ui.SECRET_KEYS`와 `runtime_config.SECRET_KEYS` 두 곳에 모두 있어야 합니다.

환경 변수: `AUTOSAVER_DATA_ROOT`, `AUTOSAVER_CONFIG_PATH`, `AUTOSAVER_UI_PORT`, `AUTOSAVER_SYNC_MODE`, `AUTOSAVER_HEADLESS`, `AUTOSAVER_MULTI_USER`, `AUTOSAVER_DGIST_API_KEY`, `AUTOSAVER_OPEN_BROWSER`, `AUTOSAVER_DEV_PORT`.

---

## 9. 빌드·배포

| 단계 | 방법 |
|---|---|
| EXE | `.venv\Scripts\python.exe -m PyInstaller bungeoppang.spec --noconfirm` → `dist\붕어빵\` |
| 설치 파일 | `packaging\build_installer.ps1` → `packaging\out\bungeoppang-<버전>-win-x64-setup.exe` (약 54MB) |
| 이 PC에 설치 | `packaging\build_installer.ps1 -Install` |

설치 파일(Inno Setup)은 관리자 권한 없이 사용자 폴더에 설치하고, WebView2가 없으면 부트스트래퍼를 실행하고, .NET 4.7.2 미만이면 안내 후 중단합니다. zip 배포에서 생기던 "인터넷에서 받은 파일" 차단 문제를 피하려고 설치 파일로 바꿨습니다. 서명이 없어서 처음 실행 때 SmartScreen이 뜹니다.

설치 용량 약 167MB 중 88MB는 Playwright의 `node.exe`라 줄일 수 없습니다.

---

## 10. 알려진 한계·남은 일

- 메일 첨부 파일은 이름·아이콘까지만 나오고 내려받기는 아직 없음
- 지난 학기 과목은 LMS가 403을 줘서 LMS 순서를 못 채움 (이름순)
- 학교 메일서버에 IDLE이 없어 새 메일은 주기 확인으로만 앎
- 삼성 노트 넣기는 PDF만, 파일당 약 5.5초 (삼성 노트 자체 저장 시간)
- 설치형 앱의 자가 업데이트는 막혀 있음. 새 설치 파일로 배포해야 함
- GitHub에 올리지 않은 커밋과 변경이 많음 (`git status`로 확인). 푸시·릴리스는 사용자가 `gh auth login` 후 요청할 때
- 코드 서명 없음 (SmartScreen 경고)


### 공휴일·명절 인사 (`app.js`)

- 공휴일 표: `FIXED_HOLIDAYS`(양력) + `LUNAR_HOLIDAYS[연도]`(설·추석·부처님오신날, 대체공휴일·선거일도 여기에 적는다). 새 해가 오면 그해 줄을 추가한다.
- `specialDay(date)` → 공휴일이면 `{holiday, title, sub}`. 12월 31일처럼 공휴일이 아닌 기념일은 인사만.
- 나우바 `nowStatus`: 방학 다음, 시간표보다 먼저 공휴일을 본다 (`state: "holiday"`).
- 대시보드 `setHeroGreeting`: 새벽이 아니면 그날 인사로 바꾸고, `heroSummary`는 '오늘은 ○○, 수업 없어요'.

## 데이터 파일 쓰기와 화면 갱신 (2026-09-25)
- 데이터 JSON 은 모두 `runtime_config.atomic_write_text`/`atomic_write_json`(임시 파일 → `os.replace`)으로 쓴다. 제자리 쓰기는 읽는 쪽이 반쯤 쓰인 파일을 봐서 '자료 0개'가 됐다 (재현: 300번 읽기 중 223번 깨짐 → 0번).
- `web_ui.get_files`·`get_emails` 는 파일이 있는데 못 읽으면 직전 결과를 준다 (`_MetadataUnreadable`).
- 화면은 `pollLight`(작업 상태 + `/api/health`)만 12초(작업 중 2초, 끊김 5초)마다 묻고, `health.lastSuccess` 가 바뀌거나 작업이 끝나면, 또는 90초(작업 중 20초)마다 `refreshAll` 로 전부 받는다. 연결이 끊기면 `state.offline` 으로 한 번만 알린다.

## 받는 사람 자동완성 (2026-09-26)
- DGIST 메일은 보내는 이름을 `이름/직위/부서` 또는 `이름/학과 (학생)` 로 붙인다. `app.js splitAffiliation` 이 이를 이름·소속으로 쪼개고, `mailContacts` 가 모든 메일의 보낸이·받는이에서 연락처를 모은다(소속이 적힌 이름을 한 번이라도 보면 그걸 씀).
- 목록은 웹메일처럼 `이름/소속 <메일>` 한 줄, 친 글자에 밑줄(`acMark`). 조직도(`/api/directory`) 결과의 소속은 `directoryOrg`(직위/부서 또는 부서(신분)).
- 조직도 파일은 설정 › 학교 메일 아래 `#directoryImportButton` 으로 넣는다. CSV 머리줄(성명·이메일·소속·직급·구분 등)로 칸을 찾고, EUC-KR CSV 도 읽는다(`readTextSmart`). 포탈 SSO 가 필요해 자동으로 긁어 오지는 않는다.
- 조직도 채우는 법 (2026-09-27): 웹메일은 포탈 SSO(isign/auth.dgist.ac.kr) 뒤라 앱이 스스로 못 가져온다. 사용자가 로그인한 브라우저에서 웹메일 API 로 한 번 받아 `directory.json` 으로 넣었다.
  - `POST /mail/org/root/entries` (`_method=GET`): 최상위 1,305명. 부서 나무는 `GET /mail/org/dgist.ac.kr/groups/{id}` 의 `attributes.member` (하위 부서 `org-group-*` 과 사람 `org-user-*` 가 섞여 있음 — 부서만 따라 내려갈 것).
  - 부서 사람: `POST /mail/org/dgist.ac.kr/groups/{id}/entries` 본문 `_method=GET&perPage=500&currentPage=N`. 155개 부서, 약 160초, 4,824명.
  - 필드: `cn`(이름) `mail` `department` `title`/`jobname`(교원·직원·연구원) `identity`(학부생·대학원생…). 값은 모두 배열.
- `/api/directory?q=&limit=` 는 `limit`(최대 50)을 따르고, 조직도는 파일 도장이 바뀔 때만 다시 읽는다(`_directory_cache`).

## 화면 전환 성능 (2026-09-27)
- 메일함 진입 비용은 JS 가 아니라 배치(layout)였다: 메일 41통 = 요소 1,200개, 배치 한 번 24ms × 여러 번. `.email-list-row { content-visibility: auto; contain-intrinsic-size: auto 88px }` 로 163ms → 44ms(중앙값, 9회).
- View Transition 이름: 본문 `appview`, 사이드바 `sidebar`, 상단 막대 `topbar`. 셋 다 0.3s 같은 곡선. 스냅샷은 늘이지 않고(`object-fit: none`, 왼쪽 위) 틀로 자른다. 이름은 화면에 하나씩만 있어야 한다(겹치면 전환 전체가 취소됨).
- 개발 서버는 `http://localhost:8794` 로 열면 요청마다 30ms/270ms 로 들쭉날쭉하다(새로고침 650ms). `127.0.0.1` 로 열면 46ms. 설치 앱은 127.0.0.1 을 쓴다. 성능을 잴 때는 127.0.0.1 로 연다.

## 자료 → Drive 동기화 (2026-09-28)
- `main.run_job` 은 폴더 맨 위가 아니라 **메타데이터의 `stored` 자리**를 따라 파일을 찾는다 (정리 후 받은 파일·다시 받은 파일이 하위 폴더에 있음). 기록 없는 파일은 여전히 올리지 않는다.
- `drive_uploader.upload_to_drive_with_path`: 같은 이름이 있으면 md5 비교 → 같으면 `'exists'`, 다르면 `files().update` 로 새 판(`'updated'`). 폴더 목록은 실행마다 한 번만 받는다(`_folder_listing`). 검색어의 `'`·`\` 는 `_q` 로 이스케이프.
- 빠른 동기화(`fast`)는 `last_sync - 2일` 이후 바뀐 파일만 본다. 과목이 하나라도 실패하면(`_course_failures`) `last_sync` 를 앞당기지 않는다.
- 매일 전체 검사: `app.run_scheduled_sync` 가 `sync_mode="full"` 로 돌고, 오늘 했는지는 `last_full_sync.json`(전체 검사가 성공했을 때만 씀)으로 본다. 자료 화면 새로고침 버튼도 `mode: "full"`.
- 2026-09-28 실측: 이번 학기 파일 중 Drive 에 옛 판 13개, 없는 파일 3개, 같은 파일 269개.
- 큰 파일: `content-length` 가 300MB 를 넘거나 Playwright 가 'string longer than 0x1fffffe8' 로 실패하면 `_stream_to_file`(requests, 로그인 쿠키, 1MB 조각, `.part` → 교체)로 받는다. 예전 코드는 파일을 먼저 열어 실패 시 0바이트 파일을 남겼다.

## 사이드바 상태판 (2026-09-28)
- 예전 '설정 필요 / 매일 08:00 실행' 은 `requiredConfig`(lms·gemini·drive·gmail) 가 모두 참이어야 '완료' 였는데, Gemini(선택)·Gmail 알림(안 씀) 때문에 늘 '설정 필요' 였다.
- 지금은 `app.js renderStatusCard`: 불빛 `statusLights()`(LMS·메일·Drive: ok/warn/bad/off), 제목은 첫 문제(없으면 '모두 정상'), 둘째 줄은 진행 중인 작업 또는 `nextAutoJob()`(마지막 성공 + 주기). 누르면 문제 있으면 설정 계정(`#stAccounts`), 없으면 자동 가져오기(`#stAuto`).
- `/api/health` 에 `authFailed`, `failStreak`, `lastFullSync` 를 더 싣는다.

## 테마 (2026-09-28)
- `THEMES` 맨 앞 `auto`(기본값): `prefers-color-scheme` 이 어두우면 `dark`, 밝으면 `claude`. `resolveTheme` 로 실제 테마를 정한다.
- 시스템 설정이 바뀌면 `followSystemTheme`: change 이벤트 + 창 focus + 3초마다 비교 (이벤트가 안 오는 경우가 있었음).
- 고른 테마는 `ui_prefs.json`(`GET/POST /api/ui-prefs`)에 둔다. 앱 창 저장소는 끌 때마다 지워져 예전에는 켤 때마다 '기본' 으로 돌아갔다. localStorage 키는 `autosaver-theme-v2`(옛 키는 고르지 않아도 '기본' 이 적혀 있어 무시).
- 설정의 '조직도 파일 넣기' 줄은 사용자 요청으로 뺐다(2026-09-28). 조직도(`directory.json`)와 자동완성은 그대로. 다시 넣으려면 `index.html` 에 `#directoryImportButton`·`#directoryFileInput`·`#directoryStatus` 를 두면 `bindDirectory` 가 붙는다.
- 대시보드 첫 줄(`setHeroGreeting`)은 인사말 대신 '9월 28일 월요일' (쉬는 날은 ' · 추석' 처럼 이름). 사용자가 인사 문구를 오글거린다고 해서 뺐다(2026-09-28). 둘째 줄 `heroSummary` 는 그대로.
- 저장 위치 스위치(드라이브·내 컴퓨터·범위·클라우드)는 바꾸는 즉시 `/api/config` 에 저장한다(`saveSavePlaceSoon`, 250ms 묶음). 예전에는 '설정 저장' 을 눌러야 해서, 설정 화면을 다시 열 때 `populateSettings` 가 저장된 값(off)으로 되돌려 '켰다 꺼졌다' 했다(2026-09-28).


### 구글 로그인이 없을 때 (`main.run_job`)

- 드라이브 저장은 기본 켜짐이지만, 로그인(token.json)이 없거나 새로 고침이 거절되면 `get_drive_service(interactive=False)`가 `DriveLoginRequired`를 던지고 드라이브만 건너뛴다.
- 1.11.4까지는 이때 동기화 작업이 실패로 끝나, 뒤따르는 폴더 정리·자동 저장도 건너뛰었다. 뒤에서 도는 작업은 절대 로그인 창(run_local_server)을 열지 않는다.

## 첫 실행 소개: 돌아다니는 달구 (2026-09-28)
- 그림: `design/dalgu/sheet2.webp`(옆·뒷모습, 걷기 `trot`=왼쪽을 봄, 달리기 `dash`=오른쪽을 봄 등 16장)를 `scripts/slice_dalgu.py` 가 `web/img/dalgu/*.png` 로 자른다. 기존 16장과 합쳐 32장.
- 달구(`#tourBuddy`)는 카드 밖에 따로 있다. `placeTourCard` 가 카드 자리를 잡은 뒤 `placeBuddy` → `buddySpot` 으로 비출 곳 둘레(아래·오른쪽·왼쪽·위, 비좁으면 카드 옆)에서 화면 안이고 카드와 안 겹치는 자리를 고른다.
- 옮길 때: 거리 360px 넘으면 `dash`, 아니면 `trot` 그림으로 좌우를 가는 쪽에 맞춰 뒤집고(`--face`), 거리에 비례한 시간(0.35~1.1초) 동안 `left/top` 이 움직인다. 도착하면 단계 `pose` 로 바뀐다. 첫 단계는 화면 왼쪽 밖에서 뛰어 들어온다.
- 시작·끝 단계(비출 곳 없음)는 카드가 크게(`.tour-card.hero`), 달구도 176px 로 카드 왼쪽에 선다.

- 폴더 선택(`/api/pick-folder`)은 `pick_folder_dialog`: 앱 창(pywebview)의 FOLDER 창. 설치 파일은 tkinter 를 빼고 묶어서(1.11.6까지) 설치형에서 늘 실패했다.


### 앱 업데이트 (`updater.py`, GitHub 릴리스)

- 확인: `/api/update/check` → api.github.com `releases/latest` 의 태그(v1.2.3)와 `VERSION` 비교. 켤 때 4초 뒤, 그 뒤 6시간마다 (`checkForUpdate`).
- 설치: `/api/update/apply` → 첨부 `bungeoppang-<버전>-win-x64-setup.exe` 를 %TEMP%ungeoppang-update 에 받고, GitHub 자산 digest(SHA-256)와 맞을 때만
  `/SILENT /CLOSEAPPLICATIONS /RELAUNCH=1` 로 실행, 앱은 2초 뒤 스스로 끈다. 설치 스크립트 `ShouldRelaunch` 가 끝나고 앱을 다시 켠다. 진행은 `/api/update/job`.
- 새 버전 내기: VERSION·changelog 올리고 빌드 → `gh release create v<버전> packaging/out/bungeoppang-<버전>-win-x64-setup.exe` (본문은 '- ' 줄로 짧게).
- 예전 방식(저장소 main 의 VERSION·raw 파일 교체)은 설치형에서 동작하지 않았고, main 이 1.8.6 에 멈춰 늘 '최신' 이었다.
- 화면 전환(2026-09-28): 옛 화면을 먼저 지우고 0.1초 뒤 새 화면을 들이던 방식은 한 번 비어 보여 '깜빡임'으로 느껴졌다. 이제 `appview`·`sidebar`·`topbar` 모두 옛/새를 동시에 0.26~0.3초 겹쳐 바꾸고 `mix-blend-mode: plus-lighter` + `isolation` 으로 같은 부분의 밝기가 꺼지지 않게 한다(`vt-soft-*`). 실측: 모든 옛/새 애니메이션 delay 0.

## 알림 (2026-09-28)
- `app.scheduler_loop` 가 30초마다 `check_deadline_alerts`·`check_new_file_alerts` 를 부른다. 알림은 `app.notify`(winotify).
- 마감: 안 낸 과제가 24h·3h·1h 안으로 들어오면 그 순간 가장 가까운 칸 하나만 알린다(늦게 켜져도 몰아서 안 뜸). 열쇠에 마감 시각을 넣어 마감이 바뀌면 다시 알린다. 기록은 `alerts.json` 의 `sent`(지난 지 3일 지나면 지움).
- 새 자료: 작업이 돌지 않을 때 메타데이터의 파일 크기 목록을 `alerts.json` 의 `files` 와 비교. 새 이름 = 새 자료, 크기 바뀜 = 새 판. 처음에는 기억만 하고 알리지 않는다.
- 설정 키 `NOTIFY_DEADLINES`, `NOTIFY_NEW_FILES`(기본 켜짐, 화면 `notifyDeadlines`/`notifyNewFiles`, 누르는 즉시 저장). 예전의 '자동 동기화 완료/새 자료가 없습니다' 와 켤 때 48시간 요약 알림은 없앴다.
- 메일함 ↔ 다른 화면 전환은 `html.vt-quick` 로 0.15초, 크기 변화 없이(`view-transition-group` 0초).

- 설치 창 디자인: `bungeoppang.iss` 의 WizardStyle(modern dynamic windows11 hidebevels)·WizardBackColor(앱 --bg)·WizardImageFile(+DynamicDark). 그림은 `scripts/make_installer_art.py` (시스템 파이썬 Pillow, Noto Serif KR 제목 + 달구) → `packaging/art/`. 단계는 환영 → 추가 옵션 → 설치 → 완료 (언어·위치·준비됨 창은 뺐다). 문구는 [Messages] 에 앱 말투로.
- 앱 안 업데이트 화면: `#updateDialog` 카드(`setUpdateStep`, 확인→내려받기→검사→설치). 설치는 /VERYSILENT 라 윈도우 설치 창이 안 뜬다. 설치 직전 `update_done.json`(데이터 폴더)에 from/to 를 적고, 다시 켜진 앱은 `/api/whats-new` 의 `justUpdated` 로 '업데이트를 마쳤어요' 카드를 연다(본 뒤 지운다).


### 영어 화면 (i18n)

- 코드의 문구는 한국어 그대로 두고, 화면에 그려진 글자를 번역표 `web/i18n/en.json`(한국어 → 영어)으로 바꿔 보여 준다 (`app.js` 앞부분 `I18N`, `tr`, `i18nTranslateTree`, MutationObserver).
- 표에 정확히 있는 문구만 바꾼다. `{0}` 이 든 틀은 빈자리를 옮겨 넣는다. 고정 한글이 두 글자 이하인 틀은 빈자리까지 모두 영어가 될 때만 쓴다(메일 제목 등 사용자 글 보호). 한글 없는 틀은 무시한다.
- ` · ` 로 이어 붙인 줄은 마디마다 옮긴다. 날짜(`(월)`, `오후 4:18`, `2026년 9월`)는 규칙으로 바꾼다.
- 알림·확인창(`confirm`/`alert`)과 토스트도 같은 표를 쓴다. 속성은 placeholder·title·aria-label·data-hint·alt.
- 언어는 `ui_prefs.json` 의 `lang`(ko/en), 없으면 윈도우 언어(한국어가 아니면 영어). 바꾸면 화면을 다시 불러온다. 번역하지 않을 곳은 `data-no-i18n`.
- **새 화면 문구를 넣으면** `python scripts/i18n_extract.py` 로 빠진 문구를 찾아 `en.json` 에 채운다. 업데이트 내용(changelog)은 한국어로만 쓴다.
