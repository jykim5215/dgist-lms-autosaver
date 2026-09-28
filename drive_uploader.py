# ===== Google Drive 업로드 =====
import os
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from runtime_config import GOOGLE_CLIENT_SECRETS_PATH, GOOGLE_SCOPES, GOOGLE_TOKEN_PATH

# Drive만 쓰지만, 권한 목록은 앱 전체와 같아야 한다.
# 여기서 Drive 권한만 요청하면 로그인할 때 token.json이 덮어써져
# 캘린더 권한이 사라진다.
SCOPES = GOOGLE_SCOPES
CREDENTIALS_PATH = GOOGLE_CLIENT_SECRETS_PATH
TOKEN_PATH = GOOGLE_TOKEN_PATH
ROOT_FOLDER = "AutoSaver"


def drive_folder_name(course_name):
    """'일반화학Ⅰ (General chemistryⅠ )_03[ 2026_1학기 ]' → '일반화학Ⅰ'."""
    text = str(course_name or '').strip()
    if '(' in text:
        head = text.split('(', 1)[0].strip()
        if head:
            text = head
    if '[' in text:
        text = text.split('[', 1)[0].strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text).strip(' ._')
    return (text or '기타')[:60]

_service = None
_folder_cache = {}

class DriveLoginRequired(RuntimeError):
    """구글 로그인이 없거나 끊겨서, 창을 띄우지 않고는 드라이브를 쓸 수 없다."""


def authorize_drive(force=False, interactive=True):
    """Run the Google OAuth flow and save token.json for Drive uploads.

    interactive=False 이면 로그인 창을 열지 않고 DriveLoginRequired 를 던진다.
    뒤에서 도는 동기화 작업이 브라우저 로그인 창을 띄우고 하염없이 기다리면 안 된다.
    """
    global _service
    creds = None

    if not force and os.path.exists(TOKEN_PATH):
        # 파일에 실제로 담긴 권한 그대로 읽는다.
        # SCOPES를 넘기면 '요청한 권한'으로 덮어써져, 실제로 없는 권한도
        # 있는 것처럼 보인다.
        creds = Credentials.from_authorized_user_file(TOKEN_PATH)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:
            # 사용자가 구글 계정에서 권한을 해제했거나 오래 안 써서 만료된 경우
            if not interactive:
                raise DriveLoginRequired(f"구글 연결이 끊겼습니다: {exc}") from exc
            creds = None
    if not (creds and creds.valid):
        if not interactive:
            raise DriveLoginRequired("구글 계정에 로그인되어 있지 않습니다.")
        if not os.path.exists(CREDENTIALS_PATH):
            raise FileNotFoundError(
                f"Google OAuth credentials file not found: {CREDENTIALS_PATH}"
            )
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
        # PKCE: 매번 새로 만드는 검증값이 있어야 인증 코드를 토큰으로 바꿀 수 있다.
        # 데스크톱 앱은 client_secret 을 비밀로 지킬 수 없으므로, 보안이 여기에 기댄다.
        flow.autogenerate_code_verifier = True
        creds = flow.run_local_server(port=0)

    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, 'w', encoding='utf-8') as token:
        token.write(creds.to_json())
    _service = None
    print("Google Drive OAuth 연결 완료!")
    return creds

def get_drive_service(interactive=True):
    global _service
    if _service:
        return _service
    creds = authorize_drive(force=False, interactive=interactive)
    _service = build('drive', 'v3', credentials=creds)
    return _service

def get_or_create_folder(service, name, parent_id=None):
    cache_key = f"{parent_id}:{name}"
    if cache_key in _folder_cache:
        return _folder_cache[cache_key]

    query = f"name='{_q(name)}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    if files:
        _folder_cache[cache_key] = files[0]['id']
        return files[0]['id']

    metadata = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
    if parent_id:
        metadata['parents'] = [parent_id]
    folder = service.files().create(body=metadata, fields='id').execute()
    print(f"폴더 생성: {name}")
    _folder_cache[cache_key] = folder['id']
    return folder['id']

def _q(text):
    """Drive 검색어 안의 글자. ' 가 든 이름(예: Professor's notes.pdf)은 검색이 깨져 업로드가 조용히 실패했다."""
    return str(text).replace("\\", "\\\\").replace("'", "\\'")


_listing_cache = {}


def _folder_listing(service, folder_id):
    """폴더 안 파일 목록을 한 번만 받아 둔다 (이름 → 파일).
    이제 기록된 파일 전부(수백 개)를 확인하므로, 파일마다 검색하면 Drive 요청이 수백 번 나간다."""
    if folder_id not in _listing_cache:
        listing = {}
        token = None
        while True:
            res = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="nextPageToken, files(id, name, md5Checksum)",
                pageSize=1000, pageToken=token,
            ).execute()
            for f in res.get('files', []):
                listing.setdefault(f['name'], f)
            token = res.get('nextPageToken')
            if not token:
                break
        _listing_cache[folder_id] = listing
    return _listing_cache[folder_id]


def find_in_drive(service, file_name, folder_id):
    """폴더 안 같은 이름 파일 (id, md5). 없으면 None."""
    return _folder_listing(service, folder_id).get(file_name)


def file_exists_in_drive(service, file_name, folder_id):
    return find_in_drive(service, file_name, folder_id) is not None


def _md5(path):
    import hashlib
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def upload_to_drive_with_path(file_path, file_name, course_name, folder_path=None):
    """
    Drive 구조: 내 드라이브 / AutoSaver / 과목명 / 파일
    (주차 등 하위 폴더 없이 과목 폴더 바로 아래에 정리)
    """
    try:
        service = get_drive_service()

        root_id = get_or_create_folder(service, ROOT_FOLDER)
        course_clean = drive_folder_name(course_name)
        course_id = get_or_create_folder(service, course_clean, root_id)

        # Drive 에 같은 이름이 있으면: 내용이 같으면 건너뛰고, 다르면(교수가 고쳐 다시 올린 파일) 새 내용으로 바꾼다.
        # 예전에는 이름만 보고 건너뛰어, 고친 자료가 Drive 에는 옛 판으로 남았다.
        existing = find_in_drive(service, file_name, course_id)
        if existing:
            if existing.get('md5Checksum') and existing['md5Checksum'] == _md5(file_path):
                return 'exists'
            media = MediaFileUpload(file_path, resumable=True)
            updated = service.files().update(fileId=existing['id'], media_body=media, fields='id, md5Checksum').execute()
            _folder_listing(service, course_id)[file_name] = {**existing, **updated}
            print(f"Drive 새 판으로 바꿈: {file_name} → AutoSaver/{course_clean}")
            return 'updated'

        file_metadata = {'name': file_name, 'parents': [course_id]}
        media = MediaFileUpload(file_path, resumable=True)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink, md5Checksum'
        ).execute()
        _folder_listing(service, course_id)[file_name] = {'id': file.get('id'), 'name': file_name, 'md5Checksum': file.get('md5Checksum')}

        print(f"Drive 업로드 완료: {file_name} → AutoSaver/{course_clean}")
        return file.get('webViewLink', '')

    except Exception as e:
        print(f"Drive 업로드 실패 ({file_name}): {e}")
        return ''
