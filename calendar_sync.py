"""구글 캘린더 동기화.

메일에서 뽑아낸 일정을 사용자의 구글 캘린더 안에 전용 캘린더(카테고리)를 만들어
자동으로 올린다. 같은 메일은 여러 번 올려도 중복되지 않도록
extendedProperties에 고유 키를 심어 upsert 방식으로 동작한다.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
from typing import Any, Iterable

from runtime_config import GOOGLE_CLIENT_SECRETS_PATH, GOOGLE_TOKEN_PATH

# Drive와 Calendar를 함께 쓰므로 두 스코프를 모두 요청한다.
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/calendar",
]

DEFAULT_CALENDAR_NAME = "DGIST 메일 일정"
TIMEZONE = "Asia/Seoul"
# 이 앱이 만든 일정임을 표시하는 키 (다른 일정과 섞이지 않도록)
_TAG = "dgist-autosaver"


def _credentials(token_path: str | None = None):
    """저장된 토큰으로 Credentials를 만든다. 만료 시 자동 갱신."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    path = str(token_path or GOOGLE_TOKEN_PATH)
    creds = Credentials.from_authorized_user_file(path, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(path, "w", encoding="utf-8") as fp:
                fp.write(creds.to_json())
        else:
            raise RuntimeError("구글 인증이 만료되었습니다. 설정에서 다시 연결해 주세요.")
    return creds


def get_calendar_service(token_path: str | None = None):
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=_credentials(token_path), cache_discovery=False)


def granted_scopes(token_path: str | None = None) -> set[str]:
    """토큰 파일에 '실제로 승인된' 스코프를 읽는다.

    주의: Credentials.from_authorized_user_file(path, SCOPES)로 읽으면
    creds.scopes가 '요청한' 스코프를 그대로 돌려주기 때문에
    권한 보유 여부 판단에 쓸 수 없다. 반드시 파일을 직접 봐야 한다.
    """
    import json

    path = str(token_path or GOOGLE_TOKEN_PATH)
    try:
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp)
        if isinstance(data, dict):
            return {str(s) for s in (data.get("scopes") or [])}
    except Exception:
        pass
    return set()


def has_calendar_scope(token_path: str | None = None) -> bool:
    """토큰이 캘린더 권한까지 가지고 있는지 확인 (없으면 재연결 필요)."""
    return "https://www.googleapis.com/auth/calendar" in granted_scopes(token_path)


def find_or_create_calendar(service, name: str | None = None) -> str:
    """이름이 같은 캘린더(카테고리)를 찾고, 없으면 새로 만든다."""
    target = (name or DEFAULT_CALENDAR_NAME).strip() or DEFAULT_CALENDAR_NAME
    page_token = None
    while True:
        resp = service.calendarList().list(pageToken=page_token).execute()
        for entry in resp.get("items", []):
            if (entry.get("summary") or "").strip() == target:
                return entry["id"]
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    created = service.calendars().insert(
        body={"summary": target, "timeZone": TIMEZONE}
    ).execute()
    return created["id"]


def _parse_dt(value: Any) -> _dt.datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return _dt.datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return _dt.datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def _event_key(mail: dict) -> str:
    raw = str(mail.get("id") or "") + "|" + str(mail.get("eventDate") or "")
    return _TAG + "-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def _build_event(mail: dict) -> dict[str, Any] | None:
    start = _parse_dt(mail.get("eventDate"))
    if not start:
        return None
    title = str(mail.get("summary") or mail.get("subject") or "제목 없는 일정").strip()
    sender = str(mail.get("fromName") or mail.get("fromEmail") or "").strip()

    # 시:분이 모두 0이면 종일 일정으로 취급
    all_day = start.hour == 0 and start.minute == 0 and start.second == 0
    if all_day:
        day = start.date()
        when = {
            "start": {"date": day.isoformat()},
            "end": {"date": (day + _dt.timedelta(days=1)).isoformat()},
        }
    else:
        end = start + _dt.timedelta(hours=1)
        when = {
            "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
            "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
        }

    description_parts = []
    if sender:
        description_parts.append(f"보낸 사람: {sender}")
    if mail.get("subject"):
        description_parts.append(f"메일 제목: {mail['subject']}")
    description_parts.append("(DGIST LMS AutoSaver가 메일에서 자동 등록한 일정입니다.)")

    body = {
        "summary": title[:250],
        "description": "\n".join(description_parts),
        "extendedProperties": {"private": {"autosaverKey": _event_key(mail), "source": _TAG}},
    }
    body.update(when)
    return body


def sync_email_events(
    emails: Iterable[dict],
    calendar_name: str | None = None,
    token_path: str | None = None,
) -> dict[str, Any]:
    """메일 일정들을 전용 캘린더에 upsert 한다.

    반환: {"ok", "created", "updated", "skipped", "calendar", "message"}
    """
    mails = [m for m in (emails or []) if m.get("eventDate")]
    if not mails:
        return {
            "ok": True,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "calendar": calendar_name or DEFAULT_CALENDAR_NAME,
            "message": "동기화할 메일 일정이 없습니다.",
        }

    service = get_calendar_service(token_path)
    calendar_id = find_or_create_calendar(service, calendar_name)

    created = updated = skipped = 0
    for mail in mails:
        body = _build_event(mail)
        if not body:
            skipped += 1
            continue
        key = body["extendedProperties"]["private"]["autosaverKey"]
        try:
            existing = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    privateExtendedProperty=f"autosaverKey={key}",
                    showDeleted=False,
                    maxResults=1,
                )
                .execute()
                .get("items", [])
            )
            if existing:
                service.events().update(
                    calendarId=calendar_id, eventId=existing[0]["id"], body=body
                ).execute()
                updated += 1
            else:
                service.events().insert(calendarId=calendar_id, body=body).execute()
                created += 1
        except Exception:
            skipped += 1

    return {
        "ok": True,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "calendar": calendar_name or DEFAULT_CALENDAR_NAME,
        "message": f"새 일정 {created}건, 갱신 {updated}건" + (f", 실패 {skipped}건" if skipped else ""),
    }
