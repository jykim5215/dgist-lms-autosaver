# ===== LMS 자동 로그인 + 파일 감지 =====
import asyncio
import os
import json
import re
import html as html_module
from playwright.async_api import async_playwright
from runtime_config import (
    DOWNLOADED_FILES_LOG,
    DOWNLOAD_PATH,
    FILE_METADATA_LOG,
    LMS_ID,
    LMS_PASSWORD,
    LOGIN_URL,
    LMS_URL,
    PLAYWRIGHT_HEADLESS,
)

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

async def crawl_lms():
    global _page, _last_courses
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)
    downloaded_files = load_downloaded_files()
    file_metadata = load_file_metadata()
    print(f"[로드] 기존 다운로드 기록: {len(downloaded_files)}개")
    new_files = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        _page = page

        print("LMS 로그인 중...")
        await page.goto(LOGIN_URL)
        await page.wait_for_load_state('networkidle')
        await page.fill('input[placeholder="Login ID"]', LMS_ID)
        await page.fill('input[type="password"]', LMS_PASSWORD)
        await page.click('button:has-text("Login")')
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(3)
        print("로그인 완료!")

        await page.goto(f"{LMS_URL}/ultra/institution-page")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(3)

        print("강의 목록 수집 중...")
        unique_courses = []

        courses_data, courses_status = await fetch_all_results(
            page,
            f"{LMS_URL}/learn/api/public/v1/users/me/courses?limit=100&fields=courseId,course.name"
        )

        if courses_status == 200:
            for enrollment in courses_data:
                course_id = enrollment.get('courseId', '')
                course_name = enrollment.get('course', {}).get('name', course_id)
                if course_id:
                    unique_courses.append({
                        'text': course_name,
                        'id': course_id
                    })
            _last_courses = [course['text'] for course in unique_courses]
            print(f"API로 강의 {len(unique_courses)}개 발견!")

        for course in unique_courses:
            try:
                course_id = course['id']
                course_name = course['text']
                print(f"\n강의 확인 중: {course_name[:50]}")

                # 1. 콘텐츠 탐색
                contents, contents_status = await fetch_all_results(
                    page,
                    f"{LMS_URL}/learn/api/public/v1/courses/{course_id}/contents?limit=100"
                )

                if contents_status == 200:
                    print(f"  콘텐츠 {len(contents)}개 발견!")
                    for content in contents:
                        await process_content(
                            page, course_id, content, course_name,
                            downloaded_files, new_files, file_metadata,
                            folder_path=[], depth=0
                        )
                else:
                    print(f"  콘텐츠 API 실패 ({contents_status})")

                # 2. 공지사항 탐색
                await crawl_announcements(
                    page, course_id, course_name,
                    downloaded_files, new_files, file_metadata
                )

                save_downloaded_files(downloaded_files)
                save_file_metadata(file_metadata)

            except Exception as e:
                print(f"강의 처리 실패: {course['text'][:30]} - {e}")

        save_downloaded_files(downloaded_files)
        save_file_metadata(file_metadata)
        await browser.close()
        _page = None

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

    for ann in announces:
        ann_title = ann.get('title', '공지사항')
        body = ann.get('body', '')
        if not body:
            continue

        matches = re.findall(r'data-bbfile="([^"]+)"', body)
        for match in matches:
            try:
                decoded = html_module.unescape(match)
                file_info = json.loads(decoded)
                file_name = file_info.get('fileName', '') or file_info.get('linkName', '') or file_info.get('alternativeText', '')
                resource_url = file_info.get('resourceUrl', '')

                if not file_name or not resource_url:
                    continue

                if file_name.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                    print(f"    동영상 스킵: {file_name}")
                    continue

                url_key = resource_url.split('?')[0]

                if url_key in downloaded_files:
                    print(f"    이미 다운로드됨: {file_name}")
                    continue

                print(f"    📎 새 공지사항 파일: {file_name} ({ann_title})")
                try:
                    dl_resp = await page.request.get(resource_url, timeout=60000)
                    if dl_resp.status == 200:
                        folder_path = ['공지사항(Announcements)']
                        save_path, local_name = resolve_download_target(
                            file_name, course_name, folder_path, file_metadata
                        )
                        with open(save_path, 'wb') as f:
                            f.write(await dl_resp.body())
                        file_metadata[local_name] = {
                            'course': course_name,
                            'folder_path': folder_path,
                            'original_name': file_name
                        }
                        new_files.append({
                            'name': file_name,
                            'local_name': local_name,
                            'path': save_path,
                            'course': course_name,
                            'folder_path': folder_path,
                            'url': url_key
                        })
                        downloaded_files.append(url_key)
                        print(f"    다운로드 완료: {file_name}")
                    else:
                        print(f"    다운로드 실패 ({dl_resp.status}): {file_name}")
                except Exception as e:
                    print(f"    다운로드 실패: {file_name} - {e}")
            except Exception as e:
                print(f"    파싱 실패: {e}")

async def process_content(page, course_id, content, course_name, downloaded_files, new_files, file_metadata, folder_path, depth=0):
    if depth > 8:
        return

    content_id = content.get('id', '')
    content_title = content.get('title', '')
    content_type = content.get('contentHandler', {}).get('id', '')

    skip_types = ['resource/x-bb-bltiplacement-Zoom', 'resource/x-bb-externallink', 'resource/x-bb-asmt-test-link']
    if content_type in skip_types:
        return

    if 'resource/x-bb-file' in content_type or 'resource/x-bb-document' in content_type:
        attach_url = f"{LMS_URL}/learn/api/public/v1/courses/{course_id}/contents/{content_id}/attachments"
        attach_resp = await page.request.get(attach_url)

        if attach_resp.status == 200:
            attach_data = await attach_resp.json()
            for attachment in attach_data.get('results', []):
                file_id = attachment.get('id', '')
                file_name = attachment.get('fileName', content_title)
                download_url = f"{LMS_URL}/learn/api/public/v1/courses/{course_id}/contents/{content_id}/attachments/{file_id}/download"

                if file_name.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
                    print(f"  {'  '*depth}동영상 스킵: {file_name}")
                    continue

                if download_url in downloaded_files:
                    print(f"  {'  '*depth}이미 다운로드됨: {file_name}")
                    continue

                print(f"  {'  '*depth}새 파일 발견: {file_name}")
                try:
                    dl_resp = await page.request.get(download_url, timeout=60000)
                    if dl_resp.status == 200:
                        save_path, local_name = resolve_download_target(
                            file_name, course_name, folder_path, file_metadata
                        )
                        with open(save_path, 'wb') as f:
                            f.write(await dl_resp.body())
                        file_metadata[local_name] = {
                            'course': course_name,
                            'folder_path': folder_path.copy(),
                            'original_name': file_name
                        }
                        new_files.append({
                            'name': file_name,
                            'local_name': local_name,
                            'path': save_path,
                            'course': course_name,
                            'folder_path': folder_path.copy(),
                            'url': download_url
                        })
                        downloaded_files.append(download_url)
                        print(f"  {'  '*depth}다운로드 완료: {file_name}")
                    else:
                        print(f"  {'  '*depth}다운로드 실패 ({dl_resp.status}): {file_name}")
                except Exception as e:
                    print(f"  {'  '*depth}다운로드 실패: {file_name} - {e}")
    else:
        if 'class recording' in content_title.lower():
            return
        if 'zoom' in content_title.lower():
            return

        try:
            sub_contents, children_status = await fetch_all_results(
                page,
                f"{LMS_URL}/learn/api/public/v1/courses/{course_id}/contents/{content_id}/children?limit=100"
            )
            if children_status == 200:
                if sub_contents:
                    print(f"  {'  '*depth}📁 {content_title}")
                    if content_title.lower() == 'weekly schedule':
                        new_path = folder_path
                    else:
                        new_path = folder_path + [content_title]
                    for sub_content in sub_contents:
                        await process_content(
                            page, course_id, sub_content, course_name,
                            downloaded_files, new_files, file_metadata,
                            folder_path=new_path, depth=depth+1
                        )
        except Exception:
            pass
