# ===== Google Drive 업로드 =====
import os
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from runtime_config import GOOGLE_CLIENT_SECRETS_PATH, GOOGLE_TOKEN_PATH

SCOPES = ['https://www.googleapis.com/auth/drive.file']
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

def authorize_drive(force=False):
    """Run the Google OAuth flow and save token.json for Drive uploads."""
    global _service
    creds = None

    if not force and os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not os.path.exists(CREDENTIALS_PATH):
            raise FileNotFoundError(
                f"Google OAuth credentials file not found: {CREDENTIALS_PATH}"
            )
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
        creds = flow.run_local_server(port=0)

    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, 'w', encoding='utf-8') as token:
        token.write(creds.to_json())
    _service = None
    print("Google Drive OAuth 연결 완료!")
    return creds

def get_drive_service():
    global _service
    if _service:
        return _service
    creds = authorize_drive(force=False)
    _service = build('drive', 'v3', credentials=creds)
    return _service

def get_or_create_folder(service, name, parent_id=None):
    cache_key = f"{parent_id}:{name}"
    if cache_key in _folder_cache:
        return _folder_cache[cache_key]

    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
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

def file_exists_in_drive(service, file_name, folder_id):
    query = f"name='{file_name}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id)").execute()
    return len(results.get('files', [])) > 0

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

        # Drive에 이미 있으면 스킵
        if file_exists_in_drive(service, file_name, course_id):
            print(f"Drive에 이미 존재: {file_name}")
            return 'exists'

        file_metadata = {'name': file_name, 'parents': [course_id]}
        media = MediaFileUpload(file_path, resumable=True)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()

        print(f"Drive 업로드 완료: {file_name} → AutoSaver/{course_clean}")
        return file.get('webViewLink', '')

    except Exception as e:
        print(f"Drive 업로드 실패 ({file_name}): {e}")
        return ''
