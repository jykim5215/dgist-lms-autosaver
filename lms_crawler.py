# ===== LMS 자동 로그인 + 파일 감지 =====
import asyncio
import os
import json
import re
import html as html_module
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright
from runtime_config import (
    DEADLINES_LOG,
    DOWNLOADED_FILES_LOG,
    DOWNLOAD_PATH,
    FILE_METADATA_LOG,
    LAST_SYNC_PATH,
    LMS_ID,
    LMS_PASSWORD,
    LOGIN_URL,
    LMS_URL,
    PLAYWRIGHT_HEADLESS,
    course_upload_enabled,
    extract_course_label,
    load_upload_selection,
)


def load_last_sync():
    """마지막 성공 동기화 시각 (없으면 None)."""
    from datetime import datetime as _dt
    if not os.path.exists(LAST_SYNC_PATH):
        return None
    try:
        with open(LAST_SYNC_PATH, 'r', encoding='utf-8-sig') as f:
            raw = json.load(f).get('lastSync')
        return _dt.fromisoformat(raw) if raw else None
    except Exception:
        return None


def save_last_sync():
    from datetime import datetime as _dt
    with open(LAST_SYNC_PATH, 'w', encoding='utf-8') as f:
        json.dump({'lastSync': _dt.now(timezone.utc).isoformat()}, f)


def is_modified_since(content, since):
    """콘텐츠가 since 이후 변경됐는지. 판단 불가 시 True(안전하게 처리)."""
    if since is None:
        return True
    raw = content.get('modified') or content.get('created')
    if not raw:
        return True
    try:
        modified = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    except ValueError:
        return True
    return modified >= since

def load_downloaded_files():
    if os.path.exists(DOWNLOADED_FILES_LOG):
        with open(DOWNLOADED_FILES_LOG, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    return []

def save_downloaded_files(files):
    with open(DOWNLOADED_FILES_LOG, 'w', encoding='utf-8') as f:
        json.dump(files, f, ensure_ascii=False, indent=2)

def load_file_metadata():
    if os.path.exists(FILE_METADATA_LOG):
        with open(FILE_METADATA_LOG, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    return {}

def save_file_metadata(metadata):
    with open(FILE_METADATA_LOG, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

# 전역 변수로 page 저장 (get_all_courses용)
_page = None
_last_courses = []

def sanitize_name(value, fallback="item", max_length=48):
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value or '').strip())
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' .')
    return (cleaned or fallback)[:max_length]

def resolve_download_target(file_name, course_name, folder_path, file_metadata):
    """Avoid overwriting same-named files from different courses."""
    original_name = sanitize_name(file_name, "file", 180)
    existing = file_metadata.get(original_name)
    base_path = os.path.join(DOWNLOAD_PATH, original_name)
    if not os.path.exists(base_path) and not existing:
        return base_path, original_name

    course_prefix = sanitize_name(course_name, "course", 36)
    stem, ext = os.path.splitext(original_name)
    local_name = f"{course_prefix}__{stem}{ext}"
    local_path = os.path.join(DOWNLOAD_PATH, local_name)
    counter = 2
    while os.path.exists(local_path) or local_name in file_metadata:
        local_name = f"{course_prefix}__{stem}-{counter}{ext}"
        local_path = os.path.join(DOWNLOAD_PATH, local_name)
        counter += 1
    return local_path, local_name

def extract_body_files(body):
    """콘텐츠/공지 본문 HTML에서 첨부 파일 추출.

    Blackboard Ultra 문서는 파일을 attachments API가 아니라 본문에
    data-bbfile 속성이나 bbcswebdav 링크로 내장하므로 둘 다 파싱한다.
    반환: [(파일명, URL)], URL 기준 중복 제거.
    """
    from urllib.parse import unquote

    files = []
    seen_keys = set()
    seen_names = set()
    if not body:
        return files

    for match in re.findall(r'data-bbfile="([^"]+)"', body):
        try:
            info = json.loads(html_module.unescape(match))
        except (ValueError, TypeError):
            continue
        name = info.get('fileName') or info.get('linkName') or info.get('alternativeText') or ''
        url = info.get('resourceUrl') or ''
        if not name or not url:
            continue
        key = url.split('?')[0]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        seen_names.add(name)
        files.append((name, url))

    for href in re.findall(r'href="([^"]*?/bbcswebdav/[^"]+)"', body):
        url = html_module.unescape(href)
        key = url.split('?')[0]
        name = unquote(key.rstrip('/').split('/')[-1])
        # 같은 파일이 data-bbfile과 링크로 중복 등장하는 경우 스킵
        if not name or key in seen_keys or name in seen_names:
            continue
        seen_keys.add(key)
        seen_names.add(name)
        files.append((name, url))

    return files


def filename_from_disposition(header_value):
    """Content-Disposition 헤더에서 파일명 추출."""
    from urllib.parse import unquote

    if not header_value:
        return ''
    match = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", header_value, re.IGNORECASE)
    if match:
        return unquote(match.group(1).strip().strip('"'))
    match = re.search(r'filename="?([^";]+)"?', header_value, re.IGNORECASE)
    if match:
        return unquote(match.group(1).strip())
    return ''


async def download_lms_file(page, url, file_name, course_name, folder_path,
                            downloaded_files, new_files, file_metadata, indent=""):
    """파일 1개 다운로드 (중복/동영상 스킵 포함). 성공 시 True."""
    if file_name.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
        print(f"{indent}동영상 스킵: {file_name}")
        return False

    url_key = url.split('?')[0]
    if url_key in downloaded_files:
        return False

    full_url = url if url.startswith('http') else f"{LMS_URL}{url}"
    try:
        dl_resp = await page.request.get(full_url, timeout=60000)
        if dl_resp.status != 200:
            print(f"{indent}다운로드 실패 ({dl_resp.status}): {file_name}")
            return False

        # xid-1234_1 같은 내부 ID 이름이면 응답 헤더의 실제 파일명으로 교체
        if re.fullmatch(r'xid-\d+_\d+', file_name) or '.' not in file_name:
            better = filename_from_disposition(dl_resp.headers.get('content-disposition', ''))
            if better:
                if better.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                    print(f"{indent}동영상 스킵: {better}")
                    return False
                file_name = better
        save_path, local_name = resolve_download_target(
            file_name, course_name, folder_path, file_metadata
        )
        with open(save_path, 'wb') as f:
            f.write(await dl_resp.body())
        file_metadata[local_name] = {
            'course': course_name,
            'folder_path': list(folder_path),
            'original_name': file_name
        }
        new_files.append({
            'name': file_name,
            'local_name': local_name,
            'path': save_path,
            'course': course_name,
            'folder_path': list(folder_path),
            'url': url_key
        })
        downloaded_files.append(url_key)
        print(f"{indent}다운로드 완료: {file_name}")
        return True
    except Exception as e:
        print(f"{indent}다운로드 실패: {file_name} - {e}")
        return False


async def fetch_all_results(page, url, limit=100):
    """Collect paginated Blackboard API results across courses/content lists."""
    results = []
    seen_page_urls = set()
    seen_items = set()
    offset = 0
    next_url = url

    while next_url and next_url not in seen_page_urls:
        seen_page_urls.add(next_url)
        response = await page.request.get(next_url)
        if response.status != 200:
            return results, response.status

        data = await response.json()
        batch = data.get('results', [])
        new_count = 0
        for item in batch:
            item_key = item.get('id') or item.get('courseId') or json.dumps(item, sort_keys=True)
            if item_key in seen_items:
                continue
            seen_items.add(item_key)
            results.append(item)
            new_count += 1

        paging = data.get('paging', {}) if isinstance(data, dict) else {}
        next_page = paging.get('nextPage') or paging.get('next')
        if next_page:
            next_url = next_page if next_page.startswith('http') else f"{LMS_URL}{next_page}"
            continue

        if len(batch) < limit or new_count == 0:
            break

        offset += limit
        separator = '&' if '?' in url else '?'
        next_url = f"{url}{separator}offset={offset}"

    return results, 200

async def get_all_courses():
    """Drive 폴더 생성용 전체 과목 목록 반환"""
    global _page, _last_courses
    if _page is None:
        return _last_courses
    courses, status = await fetch_all_results(
        _page,
        f"{LMS_URL}/learn/api/public/v1/users/me/courses?limit=100&fields=courseId,course.name"
    )
    if status != 200:
        return []
    _last_courses = [r.get('course', {}).get('name', '') for r in courses if r.get('course', {}).get('name')]
    return _last_courses

async def login_lms(page, max_attempts=2):
    """SAML 로그인 후 LMS 세션 완성까지 진행. 실패 시 1회 재시도."""
    for attempt in range(1, max_attempts + 1):
        print(f"LMS 로그인 중... (시도 {attempt}/{max_attempts})")
        await page.goto(LOGIN_URL)
        await page.wait_for_load_state('networkidle')
        await page.fill('input[placeholder="Login ID"]', LMS_ID)
        await page.fill('input[type="password"]', LMS_PASSWORD)
        await page.click('button:has-text("Login")')
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(3)

        await page.goto(f"{LMS_URL}/ultra/institution-page")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(3)

        # 세션이 실제로 만들어졌는지 검증
        check = await page.request.get(f"{LMS_URL}/learn/api/public/v1/users/me")
        if check.status == 200:
            print("로그인 완료!")
            return
        print(f"로그인 검증 실패 (HTTP {check.status})")

    raise RuntimeError(
        "LMS 로그인에 실패했습니다. 설정에서 LMS ID/비밀번호를 확인해 주세요."
    )


async def fetch_course_list(page):
    """수강 중인 과목 [{'id', 'text'}] 목록."""
    courses_data, status = await fetch_all_results(
        page,
        f"{LMS_URL}/learn/api/public/v1/users/me/courses?limit=100&fields=courseId,course.name"
    )
    if status != 200:
        return []
    courses = []
    for enrollment in courses_data:
        course_id = enrollment.get('courseId', '')
        course_name = enrollment.get('course', {}).get('name', course_id)
        if course_id:
            courses.append({'text': course_name, 'id': course_id})
    return courses


def diagnose_course_changes(courses):
    """수강 과목 변경(학기 변경/과목 추가·삭제)을 진단해 courses_state.json 갱신.

    사용자가 마지막으로 '확인'한 과목 목록(acknowledged)과 현재 수강 목록을
    비교해, 추가/사라진 과목이 있으면 pending=True로 표시한다.
    첫 실행이면 조용히 현재 목록을 기준으로 저장한다.
    """
    from runtime_config import COURSES_STATE_PATH

    current = [{'id': c['id'], 'name': c['text']} for c in courses]
    current_ids = {c['id'] for c in current}

    state = {}
    if os.path.exists(COURSES_STATE_PATH):
        try:
            with open(COURSES_STATE_PATH, 'r', encoding='utf-8-sig') as f:
                state = json.load(f)
        except Exception:
            state = {}

    acknowledged = state.get('acknowledged') if isinstance(state, dict) else None
    if not isinstance(acknowledged, list):
        acknowledged = None

    if acknowledged is None:
        # 첫 실행: 현재 목록을 기준선으로 저장 (알림 없음)
        new_state = {
            'acknowledged': current,
            'current': current,
            'added': [],
            'removed': [],
            'pending': False,
            'updatedAt': datetime.now().isoformat(timespec='seconds'),
        }
    else:
        ack_ids = {c.get('id') for c in acknowledged}
        added = [c for c in current if c['id'] not in ack_ids]
        removed = [c for c in acknowledged if c.get('id') not in current_ids]
        pending = bool(added or removed)
        new_state = {
            'acknowledged': acknowledged,
            'current': current,
            'added': added,
            'removed': removed,
            'pending': pending,
            'updatedAt': datetime.now().isoformat(timespec='seconds'),
        }
        if pending:
            print(f"[과목 변경 감지] 추가 {len(added)}개, 사라짐 {len(removed)}개")

    try:
        with open(COURSES_STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(new_state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[과목 변경] 저장 실패: {e}")
    return new_state


async def fetch_deadlines(page, courses):
    """과목별 과제 마감일 + 내 제출 상태 + 캘린더 일정을 deadlines.json에 저장."""
    print("\n[과제 마감일 수집]")
    items = []
    semaphore = asyncio.Semaphore(4)

    async def fetch_course_deadlines(course):
        course_id = course['id']
        course_name = course['text']
        async with semaphore:
            columns, status = await fetch_all_results(
                page,
                f"{LMS_URL}/learn/api/public/v2/courses/{course_id}/gradebook/columns?limit=100"
            )
        if status != 200:
            return
        count = 0
        for col in columns:
            due = (col.get('grading') or {}).get('due')
            if not due:
                continue
            entry = {
                'course': course_name,
                'courseLabel': extract_course_label(course_name),
                'courseId': course_id,
                'columnId': col.get('id'),
                'name': col.get('name', ''),
                'due': due,
                'scoreProvider': col.get('scoreProviderHandle', ''),
                'pointsPossible': (col.get('score') or {}).get('possible'),
                'myStatus': None,
                'myScore': None,
            }
            try:
                resp = await page.request.get(
                    f"{LMS_URL}/learn/api/public/v2/courses/{course_id}"
                    f"/gradebook/columns/{col.get('id')}/users/me"
                )
                if resp.status == 200:
                    attempt = await resp.json()
                    entry['myStatus'] = attempt.get('status') or None
                    entry['myScore'] = (attempt.get('displayGrade') or {}).get('score')
            except Exception:
                pass
            items.append(entry)
            count += 1
        if count:
            print(f"  {course_name[:40]}: 마감 {count}건")

    await asyncio.gather(*[fetch_course_deadlines(course) for course in courses])

    # 캘린더 일정 (API 제한: 16주 이내)
    events = []
    try:
        now = datetime.now(timezone.utc)
        since = (now - timedelta(weeks=1)).strftime('%Y-%m-%dT00:00:00Z')
        until = (now + timedelta(weeks=14)).strftime('%Y-%m-%dT00:00:00Z')
        cal_items, cal_status = await fetch_all_results(
            page,
            f"{LMS_URL}/learn/api/public/v1/calendars/items?since={since}&until={until}&limit=100"
        )
        if cal_status == 200:
            for ev in cal_items:
                events.append({
                    'id': ev.get('id'),
                    'type': ev.get('type'),
                    'title': ev.get('title'),
                    'calendarName': ev.get('calendarName'),
                    'location': ev.get('location'),
                    'start': ev.get('start'),
                    'end': ev.get('end'),
                })
    except Exception as e:
        print(f"  캘린더 수집 실패: {e}")

    # 수집 결과가 비어 있으면 기존 데이터를 덮어쓰지 않음 (일시적 실패 보호)
    if not items and not events and os.path.exists(DEADLINES_LOG):
        try:
            with open(DEADLINES_LOG, 'r', encoding='utf-8-sig') as f:
                existing = json.load(f)
            if existing.get('items') or existing.get('events'):
                print("[과제 마감일] 새 데이터가 비어 있어 기존 데이터를 유지합니다.")
                return existing
        except Exception:
            pass

    payload = {
        'updatedAt': datetime.now().isoformat(timespec='seconds'),
        'items': items,
        'events': events,
    }
    with open(DEADLINES_LOG, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[과제 마감일] {len(items)}건, 캘린더 {len(events)}건 저장")
    return payload


async def crawl_deadlines_only():
    """파일 다운로드 없이 마감일/캘린더만 갱신."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
        context = await browser.new_context()
        page = await context.new_page()
        await login_lms(page)
        courses = await fetch_course_list(page)
        print(f"과목 {len(courses)}개 발견")
        diagnose_course_changes(courses)
        payload = await fetch_deadlines(page, courses)
        await browser.close()
        return payload


async def crawl_course(page, course, downloaded_files, new_files, file_metadata,
                       fast_since, semaphore):
    """과목 1개 크롤 (병렬 실행 단위)."""
    async with semaphore:
        course_id = course['id']
        course_name = course['text']
        try:
            print(f"\n강의 확인 중: {course_name[:50]}")

            # 1. 콘텐츠 탐색
            contents, contents_status = await fetch_all_results(
                page,
                f"{LMS_URL}/learn/api/public/v1/courses/{course_id}/contents?limit=100"
            )
            if contents_status == 200:
                print(f"  [{course_name[:20]}] 콘텐츠 {len(contents)}개")
                for content in contents:
                    await process_content(
                        page, course_id, content, course_name,
                        downloaded_files, new_files, file_metadata,
                        folder_path=[], depth=0, fast_since=fast_since
                    )
            else:
                print(f"  [{course_name[:20]}] 콘텐츠 API 실패 ({contents_status})")

            # 2. 공지사항 탐색
            await crawl_announcements(
                page, course_id, course_name,
                downloaded_files, new_files, file_metadata
            )

            save_downloaded_files(downloaded_files)
            save_file_metadata(file_metadata)
        except Exception as e:
            print(f"강의 처리 실패: {course_name[:30]} - {e}")


async def crawl_lms(fast=None):
    """LMS 크롤. fast=True면 마지막 동기화 이후 변경분만 검사 (기본: 환경설정).

    과목들은 4개씩 병렬로 처리해 전체 소요 시간을 줄인다.
    """
    from runtime_config import SYNC_MODE

    global _page, _last_courses
    if fast is None:
        fast = SYNC_MODE != "full"

    os.makedirs(DOWNLOAD_PATH, exist_ok=True)
    downloaded_files = load_downloaded_files()
    file_metadata = load_file_metadata()
    upload_selection = load_upload_selection()
    print(f"[로드] 기존 다운로드 기록: {len(downloaded_files)}개")

    fast_since = None
    if fast:
        last_sync = load_last_sync()
        if last_sync:
            # 시계 오차/늦게 반영되는 수정에 대비해 2일 여유
            fast_since = last_sync - timedelta(days=2)
            print(f"[빠른 동기화] {fast_since.strftime('%Y-%m-%d %H:%M')} 이후 변경분만 검사")
        else:
            print("[빠른 동기화] 이전 동기화 기록이 없어 전체 검사로 진행")

    new_files = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        _page = page

        await login_lms(page)

        print("강의 목록 수집 중...")
        unique_courses = await fetch_course_list(page)
        _last_courses = [course['text'] for course in unique_courses]
        print(f"API로 강의 {len(unique_courses)}개 발견!")
        diagnose_course_changes(unique_courses)

        semaphore = asyncio.Semaphore(4)
        targets = []
        for course in unique_courses:
            if not course_upload_enabled(course['text'], upload_selection):
                print(f"[제외됨] {course['text'][:50]} - 사용자 선택으로 건너뜀")
                continue
            targets.append(course)

        await asyncio.gather(*[
            crawl_course(page, course, downloaded_files, new_files,
                         file_metadata, fast_since, semaphore)
            for course in targets
        ])

        save_downloaded_files(downloaded_files)
        save_file_metadata(file_metadata)

        try:
            await fetch_deadlines(page, unique_courses)
        except Exception as e:
            print(f"[과제 마감일] 수집 실패: {e}")

        await browser.close()
        _page = None

    save_last_sync()
    print(f"\n총 {len(new_files)}개 새 파일 발견!")
    return new_files

async def crawl_announcements(page, course_id, course_name, downloaded_files, new_files, file_metadata):
    announces, announce_status = await fetch_all_results(
        page,
        f"{LMS_URL}/learn/api/public/v1/courses/{course_id}/announcements?limit=100"
    )
    if announce_status != 200:
        return

    if not announces:
        return

    print(f"  📢 공지사항 {len(announces)}개 확인 중...")

    folder_path = ['공지사항(Announcements)']
    for ann in announces:
        ann_title = ann.get('title', '공지사항')
        for file_name, url in extract_body_files(ann.get('body', '')):
            url_key = url.split('?')[0]
            if url_key not in downloaded_files:
                print(f"    📎 공지사항 파일: {file_name} ({ann_title})")
            await download_lms_file(
                page, url, file_name, course_name, folder_path,
                downloaded_files, new_files, file_metadata, "    "
            )

async def process_content(page, course_id, content, course_name, downloaded_files, new_files, file_metadata, folder_path, depth=0, fast_since=None):
    if depth > 10:
        return

    content_id = content.get('id', '')
    content_title = content.get('title', '')
    content_type = content.get('contentHandler', {}).get('id', '')
    indent = f"  {'  ' * depth}"

    # 링크/줌/설문 등 파일이 없는 유형은 스킵
    skip_types = [
        'resource/x-bb-bltiplacement-Zoom',
        'resource/x-bb-externallink',
        'resource/x-bb-blti-link',
        'resource/x-bb-courselink',
        'resource/x-bb-asmt-survey-link',
    ]
    if content_type in skip_types:
        return
    title_lower = content_title.lower()
    if 'class recording' in title_lower or 'zoom' in title_lower:
        return

    # 빠른 동기화: 마지막 동기화 이후 변경 없는 파일/문서는 건너뜀
    # (폴더는 자식이 새로 생겨도 modified가 안 바뀔 수 있어 항상 재귀)
    is_leaf = 'resource/x-bb-file' in content_type or 'resource/x-bb-document' in content_type
    leaf_changed = is_modified_since(content, fast_since) if is_leaf else True

    # 1) 첨부파일 (x-bb-file 등)
    if is_leaf and leaf_changed:
        attach_resp = await page.request.get(
            f"{LMS_URL}/learn/api/public/v1/courses/{course_id}/contents/{content_id}/attachments"
        )
        if attach_resp.status == 200:
            attach_data = await attach_resp.json()
            for attachment in attach_data.get('results', []):
                file_id = attachment.get('id', '')
                file_name = attachment.get('fileName', content_title)
                download_url = (
                    f"{LMS_URL}/learn/api/public/v1/courses/{course_id}"
                    f"/contents/{content_id}/attachments/{file_id}/download"
                )
                await download_lms_file(
                    page, download_url, file_name, course_name, folder_path,
                    downloaded_files, new_files, file_metadata, indent
                )

    # 2) 본문 내장 파일 (Ultra 문서는 본문 HTML에 파일이 들어 있음)
    if leaf_changed:
        for file_name, url in extract_body_files(content.get('body', '')):
            await download_lms_file(
                page, url, file_name, course_name, folder_path,
                downloaded_files, new_files, file_metadata, indent
            )

    # 3) 하위 콘텐츠 재귀 (파일 단일 항목은 자식이 없으므로 제외)
    if 'resource/x-bb-file' in content_type:
        return
    try:
        sub_contents, children_status = await fetch_all_results(
            page,
            f"{LMS_URL}/learn/api/public/v1/courses/{course_id}/contents/{content_id}/children?limit=100"
        )
        if children_status == 200 and sub_contents:
            print(f"{indent}📁 {content_title}")
            if content_title.lower() == 'weekly schedule':
                new_path = folder_path
            else:
                new_path = folder_path + [content_title]
            for sub_content in sub_contents:
                await process_content(
                    page, course_id, sub_content, course_name,
                    downloaded_files, new_files, file_metadata,
                    folder_path=new_path, depth=depth+1, fast_since=fast_since
                )
    except Exception:
        pass
