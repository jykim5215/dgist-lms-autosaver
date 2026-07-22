# ===== DGIST 학교 이메일 수집 + AI 분류 + 발송 =====
"""DGIST 메일서버(mail.dgist.ac.kr)에서 최근 메일을 IMAP으로 가져와
카테고리 분류와 관심사 기반 추천 점수를 매겨 emails.json에 저장하고,
SMTP(smtp.dgist.ac.kr)로 메일을 보낸다.

DGIST 메일은 구글 호스팅이 아니므로 Gmail API 대신 IMAP/SMTP를 쓴다.
IMAP 서버가 표준과 다른 응답을 보내 파이썬 imaplib이 실패하기 때문에
수신부는 필요한 명령만 직접 구현한 경량 클라이언트를 쓴다.
"""
from __future__ import annotations

import base64
import json
import os
import quopri
import re
import socket
import ssl
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime

from runtime_config import (
    AUTOSAVER_DATA_ROOT,
    EMAIL_INTERESTS,
    GEMINI_API_KEY,
    SCHOOL_EMAIL,
    SCHOOL_EMAIL_PASSWORD,
    SCHOOL_IMAP_HOST,
    SCHOOL_IMAP_PORT,
    SCHOOL_SMTP_HOST,
    SCHOOL_SMTP_PORT,
)

EMAILS_LOG = str(AUTOSAVER_DATA_ROOT / "emails.json")

CATEGORIES = [
    "답신",          # 내 메일에 대한 답장
    "교수님",        # 교수 개인 발신
    "학생회",        # 총학생회/학생회 공지
    "행정·학생팀",   # 학사/행정 부서 공지
    "세미나·행사",   # 세미나, 특강, 행사 안내
    "취업·진로",     # 채용, 인턴, 진로 프로그램
    "동아리·문화",   # 동아리, 공연, 음악 등
    "기타",
]


def imap_utf7_decode(s: str) -> str:
    """IMAP modified UTF-7 폴더명을 유니코드로 디코드."""
    res = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "&":
            j = s.find("-", i)
            if j == i + 1:  # "&-" => "&"
                res.append("&")
                i = j + 1
                continue
            if j == -1:
                res.append(s[i:])
                break
            chunk = s[i + 1:j].replace(",", "/")
            pad = "=" * (-len(chunk) % 4)
            try:
                res.append(base64.b64decode(chunk + pad).decode("utf-16-be"))
            except Exception:
                res.append(s[i:j + 1])
            i = j + 1
        else:
            res.append(c)
            i += 1
    return "".join(res)


class MiniIMAP:
    """DGIST 메일서버의 비표준 응답을 견디는 최소 IMAP 클라이언트."""

    def __init__(self, host: str, port: int = 993, timeout: int = 20):
        raw = socket.create_connection((host, port), timeout=timeout)
        context = ssl.create_default_context()
        self.sock = context.wrap_socket(raw, server_hostname=host)
        self.file = self.sock.makefile("rb")
        self.tag_n = 0
        self.file.readline()  # 서버 인사말

    def cmd(self, command: str) -> tuple[str, list[tuple[bytes, bytes | None]]]:
        """명령 실행. (상태, [(응답줄, 리터럴 데이터 or None)]) 반환."""
        self.tag_n += 1
        tag = f"A{self.tag_n:03d}"
        self.sock.sendall(f"{tag} {command}\r\n".encode())
        lines: list[tuple[bytes, bytes | None]] = []
        while True:
            line = self.file.readline()
            if not line:
                raise ConnectionError("서버 연결이 끊겼습니다.")
            if line.startswith(tag.encode() + b" "):
                status = line.split(b" ", 2)[1].decode("ascii", "replace")
                return status, lines
            literal = None
            match = re.search(rb"\{(\d+)\}\r?\n$", line)
            if match:
                literal = self.file.read(int(match.group(1)))
            lines.append((line, literal))

    def login(self, user: str, password: str) -> None:
        quoted_user = '"' + user.replace('\\', '\\\\').replace('"', '\\"') + '"'
        quoted_pw = '"' + password.replace('\\', '\\\\').replace('"', '\\"') + '"'
        status, _ = self.cmd(f"LOGIN {quoted_user} {quoted_pw}")
        if status != "OK":
            raise PermissionError("학교 이메일 로그인에 실패했습니다. 설정에서 계정을 확인해 주세요.")

    def select_inbox(self) -> None:
        status, _ = self.cmd("SELECT INBOX")
        if status != "OK":
            raise RuntimeError("INBOX를 열 수 없습니다.")

    def list_folders(self) -> list[tuple[str, str]]:
        """[(raw_name, decoded_name)] 폴더 목록."""
        status, lines = self.cmd('LIST "" "*"')
        if status != "OK":
            return [("INBOX", "받은 편지함")]
        folders = []
        for line, _ in lines:
            text = line.decode("utf-8", "replace")
            # 마지막 따옴표 안의 이름 또는 마지막 토큰
            m = re.search(r'"([^"]*)"\s*$', text)
            raw = m.group(1) if m else text.split()[-1].strip()
            if raw:
                folders.append((raw, imap_utf7_decode(raw)))
        return folders

    def _quote(self, raw_name: str) -> str:
        return '"' + raw_name.replace('\\', '\\\\').replace('"', '\\"') + '"'

    def select_folder(self, raw_name: str) -> bool:
        status, _ = self.cmd(f"SELECT {self._quote(raw_name)}")
        return status == "OK"

    def find_folder(self, keyword: str) -> str | None:
        """디코드된 폴더명에 keyword가 포함된 첫 폴더의 raw 이름."""
        for raw, decoded in self.list_folders():
            if keyword in decoded:
                return raw
        return None

    def search_since(self, since: datetime) -> list[int]:
        """SINCE 이후 메일의 UID 목록 (안정적 식별자)."""
        date_str = since.strftime("%d-%b-%Y")
        status, lines = self.cmd(f"UID SEARCH SINCE {date_str}")
        if status != "OK":
            return []
        ids: list[int] = []
        for line, _ in lines:
            if line.upper().startswith(b"* SEARCH"):
                ids += [int(n) for n in line.split()[2:] if n.isdigit()]
        return sorted(ids)

    def search_unseen(self) -> list[int]:
        status, lines = self.cmd("UID SEARCH UNSEEN")
        if status != "OK":
            return []
        ids: list[int] = []
        for line, _ in lines:
            if line.upper().startswith(b"* SEARCH"):
                ids += [int(n) for n in line.split()[2:] if n.isdigit()]
        return ids

    def store_flag(self, uid: int, flag: str, add: bool = True) -> bool:
        op = "+FLAGS" if add else "-FLAGS"
        status, _ = self.cmd(f"UID STORE {uid} {op} ({flag})")
        return status == "OK"

    def copy_to(self, uid: int, raw_folder: str) -> bool:
        status, _ = self.cmd(f"UID COPY {uid} {self._quote(raw_folder)}")
        return status == "OK"

    def expunge(self) -> None:
        self.cmd("EXPUNGE")

    def fetch_message(self, msg_id: int) -> tuple[bytes, bytes, bool]:
        """UID로 (헤더 리터럴, 본문 첫 부분 리터럴, 읽음 여부)."""
        status, lines = self.cmd(
            f"UID FETCH {msg_id} (FLAGS BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID IN-REPLY-TO)] BODY.PEEK[1]<0.20000>)"
        )
        headers = body = b""
        seen = False
        for line, literal in lines:
            flags_match = re.search(rb"FLAGS \(([^)]*)\)", line)
            if flags_match and b"\\SEEN" in flags_match.group(1).upper():
                seen = True
            if literal is None:
                continue
            if b"HEADER.FIELDS" in line.upper():
                headers = literal
            else:
                body = literal
        return headers, body, seen

    def logout(self) -> None:
        try:
            self.cmd("LOGOUT")
        except Exception:
            pass


def decode_mime_words(value: str) -> str:
    parts = []
    for chunk, charset in decode_header(value or ""):
        if isinstance(chunk, bytes):
            try:
                parts.append(chunk.decode(charset or "utf-8", "replace"))
            except (LookupError, UnicodeDecodeError):
                parts.append(chunk.decode("utf-8", "replace"))
        else:
            parts.append(chunk)
    return "".join(parts).strip()


def parse_headers(raw: bytes) -> dict[str, str]:
    headers: dict[str, str] = {}
    current = None
    for line in raw.decode("utf-8", "replace").splitlines():
        if line[:1] in (" ", "\t") and current:
            headers[current] += " " + line.strip()
        elif ":" in line:
            name, _, value = line.partition(":")
            current = name.strip().lower()
            headers[current] = value.strip()
    return headers


def strip_mime_part_headers(raw: bytes) -> tuple[bytes, bytes, bytes]:
    """본문 조각 앞에 멀티파트 경계/파트 헤더가 붙어 있으면 분리.

    반환: (본문, 전송 인코딩, 문자셋)
    """
    encoding = b""
    charset = b""
    match = re.match(
        rb"\s*(?:--[^\r\n]*\r?\n)*((?:[A-Za-z][A-Za-z0-9-]*:[^\r\n]*(?:\r?\n[ \t][^\r\n]*)*\r?\n)+)\r?\n",
        raw,
    )
    if match and b"content-" in match.group(1).lower():
        headers = match.group(1).lower()
        enc_match = re.search(rb"content-transfer-encoding:\s*([a-z0-9-]+)", headers)
        if enc_match:
            encoding = enc_match.group(1)
        charset_match = re.search(rb'charset="?([a-z0-9_-]+)"?', headers)
        if charset_match:
            charset = charset_match.group(1)
        raw = raw[match.end():]
    # 남아 있는 경계 줄 제거
    raw = re.sub(rb"--+=?_?[A-Za-z0-9_.=+-]*--?\s*", b" ", raw)
    return raw, encoding, charset


def decode_body_snippet(raw: bytes, limit: int = 350) -> str:
    """인코딩 정보 없이 받은 본문 조각을 최대한 읽을 수 있게 디코드."""
    if not raw:
        return ""
    raw, encoding, part_charset = strip_mime_part_headers(raw)

    charsets = ["utf-8", "euc-kr", "cp949"]
    if part_charset:
        charsets.insert(0, part_charset.decode("ascii", "ignore"))

    text = ""
    if encoding == b"base64":
        try:
            stripped = re.sub(rb"\s+", b"", raw)
            decoded = base64.b64decode(stripped + b"=" * (-len(stripped) % 4), validate=False)
            for charset in charsets:
                try:
                    text = decoded.decode(charset)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
        except Exception:
            pass
    elif encoding == b"quoted-printable":
        try:
            decoded = quopri.decodestring(raw)
            for charset in charsets:
                try:
                    text = decoded.decode(charset)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
        except Exception:
            pass

    stripped = re.sub(rb"\s+", b"", raw)
    # 인코딩 명시가 없어도 base64로 보이면 디코드 시도
    if not text and stripped and re.fullmatch(rb"[A-Za-z0-9+/=]+", stripped):
        try:
            padded = stripped + b"=" * (-len(stripped) % 4)
            decoded = base64.b64decode(padded, validate=False)
            for charset in charsets:
                try:
                    text = decoded.decode(charset)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
        except Exception:
            pass
    if not text:
        candidate = raw
        if b"=3D" in raw or re.search(rb"=[0-9A-F]{2}", raw):
            try:
                candidate = quopri.decodestring(raw)
            except Exception:
                candidate = raw
        for charset in charsets:
            try:
                text = candidate.decode(charset)
                break
            except UnicodeDecodeError:
                continue
        if not text:
            text = candidate.decode("utf-8", "replace")
    return clean_html_to_text(text, limit)


def clean_html_to_text(text: str, limit: int = 4000) -> str:
    """HTML/CSS가 섞인 메일 본문을 읽을 수 있는 평문으로 정리.

    <style> 블록의 닫는 태그가 잘려나가도(unclosed) CSS가 새지 않도록,
    @import·주석·CSS 규칙 블록·조건부 주석까지 전부 제거한다.
    """
    import html as _html

    # 1) style/script/head 블록 제거 (닫는 태그 없으면 끝까지)
    text = re.sub(r"<style\b[\s\S]*?(?:</style>|$)", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<script\b[\s\S]*?(?:</script>|$)", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<head\b[\s\S]*?(?:</head>|$)", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<!--[\s\S]*?(?:-->|$)", " ", text)  # 조건부 주석 포함
    # 2) 줄바꿈이 될 만한 태그는 개행으로
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</\s*(p|div|tr|li|h[1-6])\s*>", "\n", text, flags=re.IGNORECASE)
    # 3) 나머지 태그 제거
    text = re.sub(r"<[^>]+>", " ", text)
    # 4) 태그가 제거되며 노출된 CSS 잔재 정리
    text = re.sub(r"/\*[\s\S]*?\*/", " ", text)                 # CSS 주석
    text = re.sub(r"@(?:import|media|font-face|charset)[^;{]*[;{]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[#.]?[A-Za-z][\w\-]*(?:\s*[,>+~\s]\s*[#.]?[\w\-]+)*\s*\{[^{}]*\}", " ", text)  # 규칙 블록(자손 결합자 포함)
    text = re.sub(r"\{[^{}]*\}", " ", text)                     # 남은 중괄호 블록
    text = re.sub(r"[a-zA-Z\-]+\s*:\s*[^;{}\n]+;", " ", text)   # 낱개 선언
    text = re.sub(r"#[A-Za-z][\w\-]*", " ", text)               # id 셀렉터 잔재
    # 5) HTML 엔티티 복원
    text = _html.unescape(text)
    # 6) 공백 정리 (문단 개행은 유지)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*", "\n\n", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    return text.strip()[:limit]


def classify_folder(decoded_name: str) -> str | None:
    """폴더명을 앱 내부 키로 매핑. 관심 없는 폴더는 None."""
    name = decoded_name.strip()
    low = name.lower()
    if name.upper() == "INBOX":
        return "inbox"
    if "보낸" in name:
        return "sent"
    if "광고" in name:
        return "promo"
    if "스팸" in name or "spam" in low:
        return "spam"
    if "임시" in name or "draft" in low:
        return "draft"
    if "지운" in name or "휴지" in name or "trash" in low or "deleted" in low:
        return "trash"
    return None


def _parse_one_message(client, msg_id: int, folder_key: str) -> dict | None:
    raw_headers, raw_body, seen = client.fetch_message(msg_id)
    headers = parse_headers(raw_headers)
    from_name, from_email = parseaddr(decode_mime_words(headers.get("from", "")))
    to_name, to_email = parseaddr(decode_mime_words(headers.get("to", "")))
    date_iso = ""
    try:
        date_iso = parsedate_to_datetime(headers.get("date", "")).isoformat()
    except Exception:
        pass
    full_body = decode_body_snippet(raw_body, limit=4000)
    return {
        "id": f"{folder_key}:{msg_id}",
        "uid": msg_id,
        "folder": folder_key,
        "messageId": headers.get("message-id", "").strip(),
        "subject": decode_mime_words(headers.get("subject", "(제목 없음)")),
        "fromName": from_name or from_email,
        "fromEmail": from_email,
        "toName": to_name or to_email,
        "toEmail": to_email,
        "date": date_iso,
        "isReply": bool(headers.get("in-reply-to")),
        "unread": not seen,
        "snippet": full_body[:300],
        "body": full_body,
    }


def build_contacts(emails: list[dict]) -> list[dict]:
    """메일함에서 본 주소로 자동완성용 연락처 목록 생성 (@dgist 우선, 빈도순)."""
    counts: dict[str, dict] = {}
    for mail in emails:
        pairs = [(mail.get("fromName"), mail.get("fromEmail"))]
        if mail.get("folder") == "sent":
            pairs.append((mail.get("toName"), mail.get("toEmail")))
        for name, addr in pairs:
            addr = (addr or "").strip().lower()
            if not addr or "@" not in addr:
                continue
            entry = counts.setdefault(addr, {"email": addr, "name": name or "", "count": 0})
            entry["count"] += 1
            if name and not entry["name"]:
                entry["name"] = name
    contacts = list(counts.values())
    # @dgist.ac.kr 먼저, 그다음 빈도 높은 순
    contacts.sort(key=lambda c: (0 if c["email"].endswith("dgist.ac.kr") else 1, -c["count"], c["email"]))
    return contacts[:300]


def fetch_school_emails(days: int = 21, max_count: int = 60) -> list[dict]:
    """받은편지함 + 보낸편지함 + 광고편지함을 각각 최근 메일 수집."""
    if not SCHOOL_EMAIL or not SCHOOL_EMAIL_PASSWORD:
        raise RuntimeError("설정에서 학교 이메일 계정을 먼저 입력해 주세요.")

    print(f"학교 메일 서버 접속 중... ({SCHOOL_IMAP_HOST})")
    client = MiniIMAP(SCHOOL_IMAP_HOST, SCHOOL_IMAP_PORT)
    client.login(SCHOOL_EMAIL, SCHOOL_EMAIL_PASSWORD)

    # 폴더 발견 및 분류
    targets = []  # (raw, key)
    seen_keys = set()
    for raw, decoded in client.list_folders():
        key = classify_folder(decoded)
        if key and key not in seen_keys:
            targets.append((raw, key))
            seen_keys.add(key)
    if "inbox" not in seen_keys:
        targets.insert(0, ("INBOX", "inbox"))

    since = datetime.now() - timedelta(days=days)
    emails = []
    for raw, key in targets:
        if not client.select_folder(raw):
            continue
        ids = client.search_since(since)[-max_count:]
        print(f"  [{key}] {len(ids)}건 수집 중...")
        for msg_id in reversed(ids):
            try:
                mail = _parse_one_message(client, msg_id, key)
                if mail:
                    emails.append(mail)
            except Exception as e:
                print(f"    메일 {key}:{msg_id} 처리 실패: {e}")
    client.logout()
    print(f"메일 {len(emails)}건 수집 완료 (폴더 {len(targets)}개)")
    return emails


def rule_based_category(mail: dict) -> str:
    subject = mail.get("subject", "")
    sender = f"{mail.get('fromName', '')} {mail.get('fromEmail', '')}"
    text = f"{subject} {sender}"
    if mail.get("isReply") or re.match(r"^\s*(re|답장|회신)\s*:", subject, re.IGNORECASE):
        return "답신"
    if "학생회" in text or "총학" in text:
        return "학생회"
    if "교수" in sender:
        return "교수님"
    if re.search(r"학생팀|학사|행정|지원팀|총무|등록|장학", text):
        return "행정·학생팀"
    if re.search(r"세미나|특강|콜로퀴움|워크숍|설명회|강연", text):
        return "세미나·행사"
    if re.search(r"채용|인턴|취업|진로|커리어|모집공고", text):
        return "취업·진로"
    if re.search(r"동아리|공연|음악|밴드|오케스트라|축제", text):
        return "동아리·문화"
    return "기타"


def classify_with_gemini(emails: list[dict], interests: str) -> tuple[list[dict], dict]:
    """Gemini로 카테고리/관심도/핵심정보 일괄 추출. 실패 시 규칙 기반으로 대체."""
    for mail in emails:
        mail["category"] = rule_based_category(mail)
        mail["score"] = 0
        mail["summary"] = ""
        mail["info"] = {}

    empty_briefing = {"intro": "", "todo": []}
    if not GEMINI_API_KEY or not emails:
        return emails, empty_briefing

    try:
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)
        compact = [
            {
                "id": mail["id"],
                "from": f"{mail['fromName']} <{mail['fromEmail']}>",
                "subject": mail["subject"],
                "snippet": mail["snippet"][:400],
            }
            for mail in emails
        ]
        today = datetime.now().strftime("%Y-%m-%d")
        prompt = f"""당신은 DGIST 학부생을 위한 AI 뉴스 에디터입니다.
각 이메일을 뉴스 카드로 만들 수 있게 핵심만 추출하세요. 오늘 날짜: {today}

학생의 관심사: {interests}

JSON으로만 답하세요:
{{
  "briefing": {{
    "intro": "메일함을 딱 한 문장으로 요약 (40자 이내, 담백하게. 예: '세미나 5건과 학생회 공지가 새로 왔어요.')",
    "todo": ["마감·신청·참석 등 놓치면 안 되는 것 (예: '~6/12 장학 신청'). 없으면 빈 배열, 최대 3개"]
  }},
  "emails": [{{
    "id": <id>,
    "category": "<카테고리>",
    "score": <0-10 관심사 관련도>,
    "summary": "<제목이 이미 명확하면 빈 문자열. 아니면 핵심만 20자 이내 명사형>",
    "info": {{"일시": "...", "장소": "...", "마감": "..."}},
    "eventDate": "<행사/마감 일시 ISO (예: 2026-06-10T15:30). 있을 때만>"
  }}]
}}

규칙 (간결함이 최우선):
- intro: 딱 한 문장, 40자 이내. 미사여구·수식어 금지.
- todo: 정말 급한 것만. 없으면 [].
- summary: 제목만 봐도 알면 "". 필요할 때만 20자 이내로 아주 짧게. "~합니다/~관련 메일" 같은 군더더기 절대 금지.
- info: 일시·장소·마감만, 실제 있을 때만. 값은 아주 짧게.
- category는 반드시 다음 중 하나: {", ".join(CATEGORIES)}
  ("답신"=학생이 보낸 메일에 대한 답장, "교수님"=교수 개인 발신)
- score: 관심사 관련도. 시스템 자동발송(강의평가·Blackboard 알림)은 0-2점.

이메일 목록:
{json.dumps(compact, ensure_ascii=False)}"""

        response = None
        last_error = None
        for model in ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                break
            except Exception as model_error:  # 쿼터 소진/미지원 모델이면 다음 모델 시도
                last_error = model_error
        if response is None:
            raise last_error
        data = json.loads(response.text)
        by_id = {item.get("id"): item for item in data.get("emails", [])}
        for mail in emails:
            item = by_id.get(mail["id"])
            if not item:
                continue
            category = str(item.get("category", ""))
            if category in CATEGORIES:
                mail["category"] = category
            try:
                mail["score"] = max(0, min(10, int(item.get("score", 0))))
            except (TypeError, ValueError):
                mail["score"] = 0
            mail["summary"] = str(item.get("summary", ""))[:60]
            info = item.get("info")
            if isinstance(info, dict):
                mail["info"] = {
                    str(k)[:10]: str(v)[:40]
                    for k, v in info.items()
                    if str(v).strip() and str(v).strip().lower() not in ("null", "none", "-")
                }
            event_date = str(item.get("eventDate", "") or "").strip()
            if event_date and event_date.lower() not in ("null", "none"):
                mail["eventDate"] = event_date[:25]

        raw_briefing = data.get("briefing")
        if isinstance(raw_briefing, dict):
            briefing = {
                "intro": str(raw_briefing.get("intro", ""))[:120],
                "todo": [
                    str(t)[:60]
                    for t in raw_briefing.get("todo", [])
                    if str(t).strip()
                ][:3],
            }
        else:
            briefing = {"intro": str(raw_briefing or "")[:120], "todo": []}
        print("Gemini 분류 완료")
        return emails, briefing
    except Exception as e:
        print(f"Gemini 분류 실패 (규칙 기반으로 대체): {e}")
        return emails, empty_briefing


FOLDER_RAW_CACHE: dict[str, str] = {}


def _connect() -> "MiniIMAP":
    if not SCHOOL_EMAIL or not SCHOOL_EMAIL_PASSWORD:
        raise RuntimeError("설정에서 학교 이메일 계정을 먼저 입력해 주세요.")
    client = MiniIMAP(SCHOOL_IMAP_HOST, SCHOOL_IMAP_PORT)
    client.login(SCHOOL_EMAIL, SCHOOL_EMAIL_PASSWORD)
    return client


def _folder_raw(client: "MiniIMAP", folder_key: str) -> str | None:
    """앱 폴더키를 서버 raw 폴더명으로."""
    if folder_key == "inbox":
        return "INBOX"
    keyword = {
        "sent": "보낸", "promo": "광고", "spam": "스팸",
        "draft": "임시", "trash": "지운",
    }.get(folder_key)
    if not keyword:
        return "INBOX"
    return client.find_folder(keyword)


def mark_read(uid: int, folder_key: str = "inbox", seen: bool = True) -> dict:
    """메일 읽음/안읽음 표시."""
    client = _connect()
    try:
        raw = _folder_raw(client, folder_key) or "INBOX"
        client.select_folder(raw)
        ok = client.store_flag(int(uid), "\\Seen", add=seen)
    finally:
        client.logout()
    return {"ok": ok, "uid": uid, "seen": seen}


def mark_all_read(folder_key: str = "inbox") -> dict:
    """폴더의 안읽은 메일 전부 읽음 처리."""
    client = _connect()
    try:
        raw = _folder_raw(client, folder_key) or "INBOX"
        client.select_folder(raw)
        uids = client.search_unseen()
        for uid in uids:
            client.store_flag(uid, "\\Seen", add=True)
    finally:
        client.logout()
    return {"ok": True, "count": len(uids)}


def delete_message(uid: int, folder_key: str = "inbox") -> dict:
    """메일 삭제: 휴지통으로 이동 후 원본 제거."""
    client = _connect()
    try:
        raw = _folder_raw(client, folder_key) or "INBOX"
        client.select_folder(raw)
        trash = client.find_folder("지운") or client.find_folder("Trash")
        if trash and trash != raw:
            client.copy_to(int(uid), trash)
        client.store_flag(int(uid), "\\Deleted", add=True)
        client.expunge()
    finally:
        client.logout()
    return {"ok": True, "uid": uid}


def _split_addrs(value: str) -> list[str]:
    """쉼표/세미콜론으로 구분된 주소 문자열을 정리된 목록으로."""
    if not value:
        return []
    parts = re.split(r"[,;]+", value)
    return [p.strip() for p in parts if p.strip() and "@" in p]


def send_email(to_addr: str, subject: str, body: str,
               cc: str = "", bcc: str = "", html: bool = False,
               in_reply_to: str = "", references: str = "",
               attachments: list | None = None,
               account: str | None = None, password: str | None = None,
               host: str | None = None, port: int | None = None) -> dict:
    """SMTP(SSL)로 메일 발송. 참조(cc)/숨은참조(bcc)/첨부파일/HTML 지원.

    attachments: [{"filename": str, "content": base64 str}]
    html: True면 본문을 HTML로 전송.
    account/password/host/port를 넘기면 최신 설정 값을 쓰고, 없으면 config 기본값.
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders
    from email.utils import formatdate, make_msgid

    account = account or SCHOOL_EMAIL
    password = password or SCHOOL_EMAIL_PASSWORD
    host = host or SCHOOL_SMTP_HOST
    port = int(port or SCHOOL_SMTP_PORT)

    if not account or not password:
        raise RuntimeError("설정에서 학교 이메일 계정을 먼저 입력해 주세요.")
    to_list = _split_addrs(to_addr)
    cc_list = _split_addrs(cc)
    bcc_list = _split_addrs(bcc)
    if not to_list:
        raise ValueError("받는 사람 주소가 올바르지 않습니다.")

    subtype = "html" if html else "plain"
    attachments = attachments or []
    if attachments:
        msg = MIMEMultipart()
        msg.attach(MIMEText(body or "", subtype, "utf-8"))
        total = 0
        for att in attachments:
            filename = str(att.get("filename", "attachment"))
            try:
                raw = base64.b64decode(att.get("content", ""))
            except Exception:
                continue
            total += len(raw)
            if total > 20 * 1024 * 1024:  # 20MB 상한
                raise ValueError("첨부파일 총 용량은 20MB를 넘을 수 없습니다.")
            # 이미지면 image/*, 아니면 octet-stream
            import mimetypes
            guessed, _ = mimetypes.guess_type(filename)
            maintype, subtype2 = (guessed.split("/", 1) if guessed else ("application", "octet-stream"))
            part = MIMEBase(maintype, subtype2)
            part.set_payload(raw)
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition", "attachment",
                filename=("utf-8", "", filename),
            )
            msg.attach(part)
    else:
        msg = MIMEText(body or "", subtype, "utf-8")

    msg["From"] = account
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Subject"] = subject or "(제목 없음)"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=account.split("@")[-1] or "dgist.ac.kr")
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = (references + " " + in_reply_to).strip()

    recipients = to_list + cc_list + bcc_list  # bcc는 헤더에 안 넣고 수신자에만 포함
    print(f"메일 발송 중... → {len(recipients)}명, 첨부 {len(attachments)}개 ({host}:{port})")
    context = ssl.create_default_context()
    # local_hostname을 ASCII로 고정 (Windows PC 이름에 한글이 있으면 EHLO 인코딩 오류)
    with smtplib.SMTP_SSL(host, port, timeout=40, context=context, local_hostname="localhost") as server:
        server.login(account, password)
        server.sendmail(account, recipients, msg.as_string())
    print("메일 발송 완료")
    return {"ok": True, "to": ", ".join(to_list), "count": len(recipients), "subject": msg["Subject"]}


def refresh_emails() -> dict:
    emails = fetch_school_emails()
    interests = EMAIL_INTERESTS or "전공 탐색, 취업, 음악, 세미나"

    # 브리핑/AI 분류는 받은편지함 중심 (보낸·광고는 규칙 기반만)
    inbox_mails = [m for m in emails if m.get("folder") == "inbox"]
    _, briefing = classify_with_gemini(inbox_mails, interests)
    for m in emails:
        if m.get("folder") != "inbox":
            m["category"] = rule_based_category(m)
            m.setdefault("score", 0)
            m.setdefault("summary", "")
            m.setdefault("info", {})

    contacts = build_contacts(emails)
    payload = {
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
        "interests": interests,
        "briefing": briefing,
        "contacts": contacts,
        "emails": emails,
    }
    os.makedirs(os.path.dirname(EMAILS_LOG), exist_ok=True)
    with open(EMAILS_LOG, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    recommended = len([m for m in emails if m.get("score", 0) >= 6])
    print(f"저장 완료: 메일 {len(emails)}건, 추천 {recommended}건")
    return payload


if __name__ == "__main__":
    refresh_emails()
