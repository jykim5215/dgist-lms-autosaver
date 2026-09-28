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
    atomic_write_json,
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
        """SINCE 이후 메일의 UID 목록 (안정적 식별자).

        지운 표시(\\Deleted)가 붙은 메일은 뺀다. 이 서버는 UIDPLUS 가 없어서
        한 통만 골라 지울 수 없다(EXPUNGE 는 폴더의 지운 표시 전부를 날린다).
        그래서 앱은 표시만 남기고 실제 삭제는 하지 않는데, 여기서 걸러 주지
        않으면 지운 메일이 새로고침 때마다 되살아난다.
        """
        date_str = since.strftime("%d-%b-%Y")
        status, lines = self.cmd(f"UID SEARCH NOT DELETED SINCE {date_str}")
        if status != "OK":
            return []
        ids: list[int] = []
        for line, _ in lines:
            if line.upper().startswith(b"* SEARCH"):
                ids += [int(n) for n in line.split()[2:] if n.isdigit()]
        return sorted(ids)

    def search_flagged(self) -> list[int]:
        """별표(\\Flagged) 가 붙은 메일. 폰·웹메일에서 붙인 것도 여기서 보인다."""
        status, lines = self.cmd("UID SEARCH NOT DELETED FLAGGED")
        if status != "OK":
            return []
        ids: list[int] = []
        for line, _ in lines:
            if line.upper().startswith(b"* SEARCH"):
                ids += [int(n) for n in line.split()[2:] if n.isdigit()]
        return ids

    def search_unseen(self) -> list[int]:
        # 지운 메일까지 '안읽음'으로 세면 개수가 안 맞는다
        status, lines = self.cmd("UID SEARCH NOT DELETED UNSEEN")
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

    def capabilities(self) -> set[str]:
        """서버가 알려 주는 기능 목록. 한 번 물어보고 기억해 둔다."""
        if getattr(self, "_caps", None) is None:
            caps: set[str] = set()
            try:
                status, lines = self.cmd("CAPABILITY")
                if status == "OK":
                    # cmd 는 (응답줄, 리터럴) 짝을 돌려준다
                    for line, _literal in lines:
                        text = line.decode("ascii", "ignore")
                        if "CAPABILITY" in text.upper():
                            caps |= {w.upper() for w in text.split()}
            except Exception:
                caps = set()
            self._caps = caps
        return self._caps

    def expunge_uid(self, uid: int) -> bool:
        """지정한 메일 하나만 실제로 지운다.

        그냥 EXPUNGE 를 부르면 '그 폴더에서 \\Deleted 표시가 붙은 메일 전부'가
        지워진다. 웹메일에서 지웠다가 비우지 않은 메일이 남아 있으면, 여기서
        한 통을 지우는 순간 그것들까지 통째로 사라진다.
        UIDPLUS(RFC 4315)의 UID EXPUNGE 는 지정한 uid 만 지운다.

        서버가 UIDPLUS 를 모르면 지우지 않는다. \\Deleted 표시는 이미 붙어 있어
        화면에서는 사라지고, 실제 삭제는 사용자가 웹메일에서 직접 비울 때 일어난다.
        남의 메일까지 지우는 것보다 덜 지우는 쪽이 안전하다.
        """
        if "UIDPLUS" in self.capabilities():
            status, _ = self.cmd(f"UID EXPUNGE {int(uid)}")
            return status == "OK"
        return False

    def fetch_structure(self, msg_id: int) -> tuple[bytes, bool, list[dict]]:
        """(헤더, 읽음 여부, 파트 목록).

        어느 파트가 HTML 이고 어느 파트가 사진인지 먼저 물어본다.
        이걸 안 보고 파트 번호를 찍으면 엉뚱한 것을 받아 온다.
        """
        status, lines = self.cmd(
            f"UID FETCH {msg_id} (FLAGS "
            f"BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID IN-REPLY-TO)] "
            f"BODYSTRUCTURE)"
        )
        headers = b""
        seen = False
        joined = ""
        for line, literal in lines:
            flags_match = re.search(rb"FLAGS \(([^)]*)\)", line)
            if flags_match and rb"\SEEN" in flags_match.group(1).upper():
                seen = True
            text = line.decode("utf-8", "replace")
            if literal is not None:
                if b"HEADER.FIELDS" in line.upper():
                    headers = literal
                # 리터럴이 끼어 응답이 여러 줄로 쪼개져도 구조가 안 끊기게 이어 붙인다
                text = re.sub(r"\{\d+\}\s*$", '""', text.rstrip("\r\n"))
            joined += text
        index = joined.upper().find("BODYSTRUCTURE")
        parts = bodystructure_parts(parse_paren_list(joined[index:])) if index >= 0 else []
        return headers, seen, parts

    def fetch_parts(self, msg_id: int, wanted: list[tuple[str, int]]) -> dict[str, bytes]:
        """{파트번호: 원본 바이트}. wanted 는 (파트번호, 최대 바이트)."""
        if not wanted:
            return {}
        spec = " ".join(f"BODY.PEEK[{part}]<0.{limit}>" for part, limit in wanted)
        status, lines = self.cmd(f"UID FETCH {msg_id} ({spec})")
        out: dict[str, bytes] = {}
        for line, literal in lines:
            if literal is None:
                continue
            match = re.search(rb"BODY\[([0-9.]+)\]", line.upper())
            if match:
                out[match.group(1).decode("ascii")] = literal
        return out

    def fetch_message(self, msg_id: int) -> dict:
        """메일 한 통을 그 메일의 구조에 맞게 받는다.

        예전에는 BODY[1] 과 BODY[2] 를 무조건 받았다. 그래서
          - 94KB 짜리 HTML 이 20KB 에서 잘려 화면이 깨졌고 (주간소식이 그랬다)
          - multipart/related 메일에서는 BODY[2] 가 본문이 아니라 사진이라
            200KB 짜리 JPEG 를 통째로 받아 놓고 버렸다.
        이제 어느 파트가 무엇인지 보고 필요한 것만 받는다.
        """
        headers, seen, parts = self.fetch_structure(msg_id)

        def pick(mime: str) -> dict | None:
            for part in parts:
                if part["type"] == mime and part["disposition"] != "attachment":
                    return part
            return None

        text_part = pick("text/plain")
        html_part = pick("text/html")
        if parts:
            wanted = []
            if text_part:
                wanted.append((text_part["part"], PLAIN_FETCH_LIMIT))
            if html_part:
                wanted.append((html_part["part"], HTML_FETCH_LIMIT))
        else:
            # 구조를 못 읽는 서버를 만나면 예전 방식으로 되돌아간다
            wanted = [("1", PLAIN_FETCH_LIMIT), ("2", HTML_FETCH_LIMIT)]
        return {
            "headers": headers,
            "seen": seen,
            "parts": parts,
            "raw": self.fetch_parts(msg_id, wanted),
            "textPart": text_part,
            "htmlPart": html_part,
        }

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


def _looks_quoted_printable(raw: bytes) -> bool:
    """헤더에 표시가 없어도 quoted-printable 인지 판단.

    확실한 신호 두 가지만 본다.
      - 줄 끝의 '=' (소프트 줄바꿈). 평범한 HTML 에는 나올 일이 거의 없다.
      - '=3D' (인코딩된 '='). QP 로 감싼 HTML 이면 속성마다 나온다.
    잘못 짚으면 멀쩡한 본문이 깨지므로, 흔적이 여러 번 보일 때만 참으로 본다.
    """
    if not raw:
        return False
    soft_breaks = len(re.findall(rb"=\r?\n", raw))
    encoded_eq = raw.count(b"=3D")
    return soft_breaks >= 3 or encoded_eq >= 3


def decode_body_html(raw: bytes, limit: int = 200000) -> str:
    """HTML 메일의 원본을 그대로 돌려준다 (평문 변환 전).

    화면에서는 스크립트를 막은 iframe 안에 넣어 그린다. 여기서 태그를
    지우면 표·이미지·서식이 전부 사라져 '깨져 보인다'는 말이 된다.
    HTML 이 아니면 빈 문자열.
    """
    if not raw:
        return ""
    body, encoding, part_charset = strip_mime_part_headers(raw)

    charsets = ["utf-8", "euc-kr", "cp949"]
    if part_charset:
        charsets.insert(0, part_charset.decode("ascii", "ignore"))

    text = ""
    if encoding == b"base64":
        try:
            stripped = re.sub(rb"\s+", b"", body)
            decoded = base64.b64decode(stripped + b"=" * (-len(stripped) % 4), validate=False)
        except Exception:
            decoded = body
    elif encoding == b"quoted-printable":
        try:
            decoded = quopri.decodestring(body)
        except Exception:
            decoded = body
    else:
        decoded = body

    # 전송 인코딩이 헤더에 안 잡힐 때가 있다.
    # 멀티파트가 겹겹이 싸여 있으면 HTML 조각의 Content-Transfer-Encoding 이
    # 덩어리 맨 앞이 아니라 중간에 들어가서 strip_mime_part_headers 가 못 본다.
    # 헤더에 7bit 라고 적혀 있는데 실제로는 QP 인 경우도 있다.
    # 그러면 =EC=88=98 같은 글자가 화면에 그대로 나온다(실제로 그랬다).
    # 평문 경로에는 이미 이 되짚기가 있었는데 HTML 경로에만 빠져 있었다.
    # base64 는 이미 풀었으므로 건드리지 않고, 나머지는 '아직도 QP 로 보이면' 푼다.
    if encoding != b"base64" and _looks_quoted_printable(decoded):
        try:
            decoded = quopri.decodestring(decoded)
        except Exception:
            pass

    for charset in charsets:
        try:
            text = decoded.decode(charset)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if not text:
        text = decoded.decode("utf-8", "replace")

    if "<" not in text or not re.search(r"<(html|body|div|table|p|br|img)\b", text, re.I):
        return ""

    # 스크립트는 어차피 iframe 이 막지만, 아예 지워서 보낸다.
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.S | re.I)
    text = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", text, flags=re.I)
    return text[:limit]


def clean_html_to_text(text: str, limit: int = 4000) -> str:
    """HTML/CSS가 섞인 메일 본문을 읽을 수 있는 평문으로 정리.

    <style> 블록의 닫는 태그가 잘려나가도(unclosed) CSS가 새지 않도록,
    @import·주석·CSS 규칙 블록·조건부 주석까지 전부 제거한다.
    """
    import html as _html

    # 0) 먼저 자른다.
    # 결과는 어차피 limit 까지만 쓰는데, 예전에는 수백 KB짜리 HTML 본문 전체를
    # 아래 정규식 12개에 통과시킨 뒤 마지막에 잘랐다. 태그가 걷히면 길이가 크게
    # 줄기 때문에 넉넉히(limit 의 8배) 남겨 두고 시작해도 결과는 같다.
    if len(text) > limit * 8:
        text = text[: limit * 8]

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
    # 규칙 블록(자손 결합자 포함).
    # 예전 패턴은 `(?:\s*[,>+~\s]\s*[#.]?[\w\-]+)*` 였는데, 분리자 문자군에 \s 가
    # 들어 있어서 앞뒤 \s* 와 같은 공백을 서로 다르게 나눠 가질 수 있었다.
    # 그 상태에서 뒤의 \{ 를 못 찾으면 나눠 갖는 경우의 수를 전부 되짚느라
    # 사실상 끝나지 않는다(실제로 메일 새로고침이 여기서 멈췄다).
    # 분리자를 '기호' 와 '공백' 으로 갈라 한 가지로만 읽히게 하고, 반복도 묶어 둔다.
    if "{" in text:
        text = re.sub(
            r"[#.]?[A-Za-z][\w\-]*(?:(?:\s*[,>+~]\s*|\s+)[#.]?[\w\-]+){0,32}\s*\{[^{}]*\}",
            " ",
            text,
        )
        text = re.sub(r"\{[^{}]*\}", " ", text)                 # 남은 중괄호 블록
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


# 본문 저장 형식. 이 숫자가 올라가면 예전에 받아 둔 메일도 한 번 다시 받는다
# (20KB 에서 잘려 있던 HTML 을 온전한 것으로 바꾸기 위함).
BODY_VERSION = 3
PLAIN_FETCH_LIMIT = 40000
HTML_FETCH_LIMIT = 400000
HTML_STORE_LIMIT = 300000


def parse_paren_list(text: str) -> list:
    """IMAP 의 괄호 목록(BODYSTRUCTURE 응답)을 중첩 리스트로 푼다."""
    start = text.find("(")
    if start < 0:
        return []

    def parse(pos: int) -> tuple[list, int]:
        items: list = []
        pos += 1  # 여는 괄호 건너뛰기
        while pos < len(text):
            ch = text[pos]
            if ch == " ":
                pos += 1
            elif ch == ")":
                return items, pos + 1
            elif ch == "(":
                sub, pos = parse(pos)
                items.append(sub)
            elif ch == '"':
                buf = []
                pos += 1
                while pos < len(text) and text[pos] != '"':
                    if text[pos] == "\\" and pos + 1 < len(text):
                        buf.append(text[pos + 1])
                        pos += 2
                        continue
                    buf.append(text[pos])
                    pos += 1
                items.append("".join(buf))
                pos += 1
            else:
                end = pos
                while end < len(text) and text[end] not in ' ()"':
                    end += 1
                atom = text[pos:end]
                items.append(None if atom.upper() == "NIL" else atom)
                pos = end
        return items, pos

    items, _ = parse(start)
    return items


def _bs_params(raw) -> dict:
    """("CHARSET" "UTF-8") 같은 짝 목록을 사전으로."""
    out: dict[str, str] = {}
    if isinstance(raw, list):
        for i in range(0, len(raw) - 1, 2):
            out[str(raw[i] or "").lower()] = str(raw[i + 1] or "")
    return out


def _bs_part_info(node: list) -> dict:
    def get(i):
        return node[i] if i < len(node) else None

    mime_type = str(get(0) or "").lower()
    subtype = str(get(1) or "").lower()
    params = _bs_params(get(2))
    try:
        size = int(str(get(6) or 0))
    except ValueError:
        size = 0
    # TEXT 파트에는 '줄 수' 가 하나 더 끼어 있어 뒤 항목이 한 칸씩 밀린다
    disp = get(9 if mime_type == "text" else 8)
    disposition = ""
    filename = params.get("name", "")
    if isinstance(disp, list) and disp:
        disposition = str(disp[0] or "").lower()
        filename = _bs_params(disp[1] if len(disp) > 1 else None).get("filename", filename)
    return {
        "type": f"{mime_type}/{subtype}",
        "charset": params.get("charset", ""),
        "cid": str(get(3) or "").strip().strip("<>"),
        "encoding": str(get(5) or "").lower(),
        "size": size,
        "disposition": disposition,
        "filename": decode_mime_words(filename) if filename else "",
    }


def bodystructure_parts(tree: list) -> list[dict]:
    """BODYSTRUCTURE 트리를 [{part, type, encoding, ...}] 평면 목록으로."""

    def walk(node, num: str) -> list[dict]:
        if not isinstance(node, list) or not node:
            return []
        if isinstance(node[0], list):  # 멀티파트: 자식이 앞에 늘어선다
            out = []
            index = 1
            for child in node:
                if not isinstance(child, list):
                    break
                out.extend(walk(child, f"{num}.{index}" if num else str(index)))
                index += 1
            return out
        info = _bs_part_info(node)
        info["part"] = num or "1"
        return [info]

    return walk(tree, "")


def decode_part_bytes(raw: bytes, encoding: str) -> bytes:
    """전송 인코딩만 푼다 (구조에서 알려 준 값이라 짐작할 필요가 없다)."""
    if not raw:
        return b""
    enc = (encoding or "").lower()
    if enc == "base64":
        try:
            stripped = re.sub(rb"\s+", b"", raw)
            return base64.b64decode(stripped + b"=" * (-len(stripped) % 4), validate=False)
        except Exception:
            return raw
    if enc == "quoted-printable":
        try:
            return quopri.decodestring(raw)
        except Exception:
            return raw
    return raw


def decode_part_text(raw: bytes, encoding: str, charset: str = "") -> str:
    data = decode_part_bytes(raw, encoding)
    for cs in ([charset] if charset else []) + ["utf-8", "euc-kr", "cp949"]:
        try:
            return data.decode(cs)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", "replace")


def sanitize_mail_html(text: str, limit: int = HTML_STORE_LIMIT) -> str:
    """메일 HTML 에서 스크립트만 걷어낸다. 표·그림·서식은 그대로 둔다."""
    if not text or "<" not in text:
        return ""
    if not re.search(r"<(html|body|div|table|p|br|img|span|font)\b", text, re.I):
        return ""
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.S | re.I)
    text = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", text, flags=re.I)
    return text[:limit]


def tidy_plain_text(text: str, limit: int = 4000) -> str:
    """진짜 평문 파트는 지울 태그가 없다. 공백만 정리한다."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*", "\n\n", text)
    return text.strip()[:limit]


def inline_image_parts(parts: list[dict]) -> list[dict]:
    """본문 안에 박힌 그림 (HTML 이 cid: 로 가리키는 것)."""
    return [
        {
            "part": part["part"],
            "cid": part["cid"],
            "type": part["type"],
            "encoding": part["encoding"],
            "size": part["size"],
        }
        for part in parts
        if part["type"].startswith("image/") and part["cid"]
    ]


def attachment_parts(parts: list[dict]) -> list[dict]:
    """따로 내려받는 첨부 파일."""
    out = []
    for part in parts:
        if part["disposition"] != "attachment" and not part["filename"]:
            continue
        if part["type"].startswith("text/") and not part["filename"]:
            continue
        out.append(
            {
                "part": part["part"],
                "name": part["filename"] or "첨부파일",
                "type": part["type"],
                "size": part["size"],
            }
        )
    return out


def _parse_one_message(client, msg_id: int, folder_key: str) -> dict | None:
    fetched = client.fetch_message(msg_id)
    headers = parse_headers(fetched["headers"])
    seen = fetched["seen"]
    from_name, from_email = parseaddr(decode_mime_words(headers.get("from", "")))
    to_name, to_email = parseaddr(decode_mime_words(headers.get("to", "")))
    date_iso = ""
    try:
        date_iso = parsedate_to_datetime(headers.get("date", "")).isoformat()
    except Exception:
        pass
    parts = fetched["parts"]
    raw = fetched["raw"]
    text_part, html_part = fetched["textPart"], fetched["htmlPart"]

    if parts:
        full_body = (
            tidy_plain_text(
                decode_part_text(raw.get(text_part["part"], b""), text_part["encoding"], text_part["charset"])
            )
            if text_part
            else ""
        )
        html_text = (
            decode_part_text(raw.get(html_part["part"], b""), html_part["encoding"], html_part["charset"])
            if html_part
            else ""
        )
        body_html = sanitize_mail_html(html_text)
        # text/html 이라고 적어 놓고 태그 하나 없는 메일이 있다(정원초과 알림이 그랬다).
        # 그런 메일은 HTML 로 그릴 게 없으니 평문으로 삼는다. 안 그러면 본문이 통째로 빈다.
        if not full_body.strip() and not body_html and html_text.strip():
            full_body = tidy_plain_text(html_text)
    else:
        # 구조를 못 읽은 경우에만 예전의 짐작 방식
        full_body = decode_body_snippet(raw.get("1", b""), limit=4000)
        body_html = decode_body_html(raw.get("2", b"")) or decode_body_html(raw.get("1", b""))

    if not full_body.strip() and body_html:
        # 그림·표뿐이라 평문이 비는 메일도 있다. 목록 미리보기가 비지 않게.
        full_body = clean_html_to_text(body_html, 4000)

    inline_images = inline_image_parts(parts)
    attachments = attachment_parts(parts)
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
        # 원본 HTML (있을 때만). 화면에서 스크립트 막은 iframe 으로 그린다.
        "bodyHtml": body_html,
        # 본문 안의 그림. 열어 볼 때 이 목록을 보고 따로 받아 온다.
        "inlineImages": inline_images,
        "attachments": attachments,
        "hasAttachment": bool(attachments),
        "bodyVersion": BODY_VERSION,
    }


def fetch_inline_images(
    uid: int,
    folder_key: str,
    images: list[dict],
    max_total: int = 12 * 1024 * 1024,
) -> dict[str, bytes]:
    """본문 그림들을 한 번의 접속으로 모두 받아 온다.

    그림마다 따로 접속하면 여섯 장짜리 주간소식 한 통에 로그인을 여섯 번 한다.
    """
    if not images:
        return {}
    if not SCHOOL_EMAIL or not SCHOOL_EMAIL_PASSWORD:
        raise RuntimeError("설정에서 학교 이메일 계정을 먼저 입력해 주세요.")

    client = MiniIMAP(SCHOOL_IMAP_HOST, SCHOOL_IMAP_PORT)
    try:
        client.login(SCHOOL_EMAIL, SCHOOL_EMAIL_PASSWORD)
        raw_name = None
        for raw, decoded in client.list_folders():
            if classify_folder(decoded) == folder_key:
                raw_name = raw
                break
        if not client.select_folder(raw_name or "INBOX"):
            return {}

        wanted = []
        budget = max_total
        for image in images:
            # base64 는 원본보다 4/3 커진다. 서버가 알려 준 크기 그대로 달라고 한다.
            size = min(int(image.get("size") or 0) or 2_000_000, budget)
            if size <= 0:
                break
            wanted.append((image["part"], size + 1024))
            budget -= size
        raw_parts = client.fetch_parts(uid, wanted)
        out: dict[str, bytes] = {}
        for image in images:
            blob = raw_parts.get(image["part"])
            if blob:
                out[image["cid"]] = decode_part_bytes(blob, image.get("encoding", ""))
        return out
    finally:
        client.logout()


# ===== 메일에서 행사 날짜 뽑기 (AI 없이) =====
# 행사 날짜(eventDate)는 원래 Gemini 가 뽑았다. 키가 없는 대부분의 사용자에게는 비어 있어서
# 달빛제·세미나·영화제 같은 학교 행사가 캘린더에 하나도 안 나왔다.
# 학교 안내 메일은 날짜를 거의 정해진 모양으로 쓴다:
#   '오는 9월 18일(금)에 개최되는' / '일시: 9월 22일(화), 16:30' / 제목의 '(Sep.22 (Tue), 16:30'
# 이런 모양만 골라 읽는다. 신청 기간·마감일을 행사일로 잘못 잡지 않도록
# '행사처럼 보이는 메일' 에서, '일시·개최·열리는' 같은 말 가까이의 날짜를 먼저 본다.

_EVENT_WORDS = (
    "행사", "축제", "달빛제", "세미나", "특강", "설명회", "공연", "영화제", "콘서트", "간담회",
    "워크숍", "워크샵", "박람회", "캠프", "페스티벌", "festival", "seminar", "colloquium",
    "콜로퀴움", "강연", "포럼", "시상식", "체육대회", "오픈하우스", "부스", "투어",
)
_MONTHS_EN = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
# 날짜 하나: 9월 18일 / 9/18 / 9.18( / 2026. 9. 18 / Sep.22 / September 22
_DATE_PATTERNS = [
    re.compile(r"(?:(20\d{2})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일"),
    re.compile(r"(?:(20\d{2})\s*[./-]\s*)?(\d{1,2})\s*[./]\s*(\d{1,2})(?=\s*[\(（]|\s*\(?[월화수목금토일]|\s*,|\s*~|\s*$|\s)"),
    re.compile(r"\b(?:(20\d{2})\s*)?(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*(\d{1,2})\b", re.I),
]
_TIME_RE = re.compile(r"(?:(오전|오후)\s*)?(\d{1,2})\s*[:시]\s*(\d{2})?(?:\s*분)?\s*(AM|PM|am|pm)?")
# 이 말 뒤에 오는 날짜가 행사일일 가능성이 높다
_EVENT_ANCHORS = re.compile(r"일\s*시|개최|열리는|열립니다|진행되는|진행합니다|Date|When|행사일|일정\s*:|날\s*짜")
# 이 말 가까이의 날짜는 행사일이 아니다 (신청·마감)
_NOT_EVENT = re.compile(r"신청\s*기간|접수\s*기간|마감|까지\s*신청|제출|deadline|~\s*\d", re.I)


def _date_from_match(match: re.Match, pattern_index: int, base: datetime) -> datetime | None:
    year_text, month_text, day_text = match.group(1), match.group(2), match.group(3)
    try:
        month = _MONTHS_EN[month_text[:3].lower()] if pattern_index == 2 else int(month_text)
        day = int(day_text)
        year = int(year_text) if year_text else base.year
        found = datetime(year, month, day)
    except (ValueError, KeyError, TypeError):
        return None
    # 연도를 안 적었는데 메일보다 두 달 넘게 앞이면 다음 해 이야기다
    if not year_text and found < base - timedelta(days=60):
        found = found.replace(year=found.year + 1)
    # 메일 날짜에서 너무 먼 것은 행사일이 아니다 (연혁·다른 해 이야기)
    if abs((found - base).days) > 200:
        return None
    return found


def _time_after(text: str, start: int) -> tuple[int, int] | None:
    """날짜 바로 뒤(40자 안)에 적힌 시각."""
    window = text[start:start + 40]
    match = _TIME_RE.search(window)
    if not match:
        return None
    hour = int(match.group(2))
    minute = int(match.group(3) or 0)
    half = match.group(1) or ""
    ampm = (match.group(4) or "").lower()
    if (half == "오후" or ampm == "pm") and hour < 12:
        hour += 12
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def guess_event_date(subject: str, body: str, mail_date: str = "") -> str:
    """행사 안내 메일이면 행사 날짜(ISO)를, 아니면 빈 문자열."""
    subject = subject or ""
    body = (body or "")[:6000]
    text_all = f"{subject}\n{body}"
    lowered = text_all.lower()
    if not any(word in lowered for word in _EVENT_WORDS):
        return ""
    try:
        base = datetime.fromisoformat(str(mail_date).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        base = datetime.now()

    def dates_in(text: str) -> list[tuple[int, datetime, int]]:
        found = []
        for index, pattern in enumerate(_DATE_PATTERNS):
            for match in pattern.finditer(text):
                when = _date_from_match(match, index, base)
                if when:
                    found.append((match.start(), when, match.end()))
        found.sort(key=lambda item: item[0])
        return found

    def with_time(text: str, item: tuple[int, datetime, int]) -> str:
        _, when, end = item
        clock = _time_after(text, end)
        if clock:
            when = when.replace(hour=clock[0], minute=clock[1])
            return when.isoformat(timespec="minutes")
        return when.date().isoformat()

    def usable(text: str, item: tuple[int, datetime, int]) -> bool:
        before = text[max(0, item[0] - 25):item[0]]
        return not _NOT_EVENT.search(before)

    # 1) 제목의 날짜 (세미나 메일은 제목에 날짜·시각을 넣는다)
    #    '4:30PM Sep 22' 처럼 시각이 날짜 앞에 오기도 한다
    for item in dates_in(subject):
        if usable(subject, item):
            found = with_time(subject, item)
            if "T" not in found:
                lead = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)", subject, re.I)
                if lead:
                    hour = int(lead.group(1)) % 12 + (12 if lead.group(3).upper() == "PM" else 0)
                    found = f"{found}T{hour:02d}:{lead.group(2)}"
            return found
    # 2) '일시·개최·열리는' 가까이의 날짜
    for anchor in _EVENT_ANCHORS.finditer(body):
        near = body[max(0, anchor.start() - 40):anchor.end() + 60]
        offset = max(0, anchor.start() - 40)
        for item in dates_in(near):
            shifted = (item[0] + offset, item[1], item[2] + offset)
            if usable(body, shifted):
                return with_time(body, shifted)
    return ""


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


def _load_cached_emails() -> dict[str, dict]:
    """지난번에 받아 둔 메일을 id 로 찾을 수 있게 펼친다."""
    try:
        with open(EMAILS_LOG, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    mails = data.get("emails") if isinstance(data, dict) else None
    if not isinstance(mails, list):
        return {}
    return {m["id"]: m for m in mails if isinstance(m, dict) and m.get("id")}


def fetch_school_emails(days: int = 21, max_count: int = 60) -> list[dict]:
    """받은편지함 + 보낸편지함 + 광고편지함을 각각 최근 메일 수집.

    예전에는 새로고침할 때마다 49통을 처음부터 다시 받았다. 한 통에 0.135초씩
    걸리니 그것만으로 6.6초다. 메일 목록은 대부분 그대로인데 매번 전부 다시
    받을 이유가 없다.

    이제 서버에는 'UID 목록'만 물어보고(0.08초), 이미 갖고 있는 UID 는
    저장해 둔 것을 그대로 쓴다. 새로 온 것만 받는다.
    읽음 여부는 바뀔 수 있으므로 그 부분만 따로 맞춘다.
    """
    if not SCHOOL_EMAIL or not SCHOOL_EMAIL_PASSWORD:
        raise RuntimeError("설정에서 학교 이메일 계정을 먼저 입력해 주세요.")

    print(f"학교 메일 서버 접속 중... ({SCHOOL_IMAP_HOST})")
    client = MiniIMAP(SCHOOL_IMAP_HOST, SCHOOL_IMAP_PORT)
    client.login(SCHOOL_EMAIL, SCHOOL_EMAIL_PASSWORD)

    cached = _load_cached_emails()

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
    reused_total = 0
    fetched_total = 0
    for raw, key in targets:
        if not client.select_folder(raw):
            continue
        ids = client.search_since(since)[-max_count:]
        unseen = set(client.search_unseen())
        flagged = set(client.search_flagged())

        def stale(msg_id: int) -> bool:
            """예전 방식으로 받아 둔 메일은 본문이 잘려 있어 한 번 다시 받는다."""
            mail = cached.get(f"{key}:{msg_id}")
            if not mail:
                return True
            return int(mail.get("bodyVersion", 1) or 1) < BODY_VERSION

        fresh = [i for i in ids if stale(i)]
        reused = len(ids) - len(fresh)
        reused_total += reused
        fetched_total += len(fresh)
        if fresh:
            print(f"  [{key}] 새 메일 {len(fresh)}건 받는 중 (이미 있는 {reused}건은 건너뜀)")
        else:
            print(f"  [{key}] 새 메일 없음 ({reused}건 그대로)")

        for msg_id in reversed(ids):
            mail_id = f"{key}:{msg_id}"
            if not stale(msg_id):
                mail = dict(cached[mail_id])
                # 본문은 그대로 두고 읽음·별표만 서버 기준으로 맞춘다
                mail["unread"] = msg_id in unseen
                mail["starred"] = msg_id in flagged
                emails.append(mail)
                continue
            try:
                mail = _parse_one_message(client, msg_id, key)
                if mail:
                    mail["starred"] = msg_id in flagged
                    emails.append(mail)
            except Exception as e:
                print(f"    메일 {key}:{msg_id} 처리 실패: {e}")

    client.logout()
    print(
        f"메일 {len(emails)}건 (새로 받은 것 {fetched_total}건, "
        f"그대로 쓴 것 {reused_total}건, 폴더 {len(targets)}개)"
    )
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


def pending_replies(emails: list[dict], days: int = 3) -> list[dict]:
    """내가 보냈는데 아직 답이 없는 메일.

    교수님께 수강 요청 같은 걸 보내 놓고 잊어버리는 일이 많다.
    보낸 메일 하나하나에 대해 '그 뒤로 그 사람에게서 온 메일이 있는지' 를 본다.
    받은 사람이 여럿이면 아무한테서나 답이 오면 답장이 온 것으로 친다.

    days: 보낸 지 이만큼 지난 것만 챙긴다 (어제 보낸 걸 재촉하면 실례다)
    """
    sent = [m for m in emails if m.get("folder") == "sent"]
    if not sent:
        return []

    # 받은 메일을 보낸사람별로 모아 둔다
    incoming: dict[str, list[str]] = {}
    for mail in emails:
        if mail.get("folder") == "sent":
            continue
        addr = (mail.get("fromEmail") or "").strip().lower()
        if addr:
            incoming.setdefault(addr, []).append(mail.get("date") or "")

    now = datetime.now()
    waiting = []
    for mail in sent:
        sent_at = mail.get("date") or ""
        try:
            when = datetime.fromisoformat(sent_at)
        except ValueError:
            continue
        if when.tzinfo is not None:
            when = when.replace(tzinfo=None)
        age = (now - when).days
        if age < days:
            continue

        targets = [a.strip().lower() for a in _split_addrs(mail.get("toEmail", "")) or []]
        if not targets:
            one = (mail.get("toEmail") or "").strip().lower()
            targets = [one] if one else []
        if not targets:
            continue

        replied = False
        for addr in targets:
            for got_at in incoming.get(addr, []):
                try:
                    got = datetime.fromisoformat(got_at)
                except ValueError:
                    continue
                if got.tzinfo is not None:
                    got = got.replace(tzinfo=None)
                if got > when:
                    replied = True
                    break
            if replied:
                break

        if not replied:
            waiting.append(
                {
                    "id": mail.get("id"),
                    "subject": mail.get("subject", ""),
                    "toName": mail.get("toName", ""),
                    "toEmail": mail.get("toEmail", ""),
                    "date": sent_at,
                    "days": age,
                    "messageId": mail.get("messageId", ""),
                }
            )

    waiting.sort(key=lambda x: x["days"], reverse=True)
    return waiting


def build_reminder(mail: dict) -> dict:
    """리마인드(재확인) 메일 초안.

    원문을 인용해 붙이고 제목에 [Reminder] 를 단다.
    In-Reply-To 를 넣어 받는 쪽 메일함에서 같은 대화로 묶이게 한다.
    """
    subject = str(mail.get("subject", "")).strip()
    if not re.match(r"^\s*\[?reminder\]?", subject, re.IGNORECASE):
        subject = f"[Reminder] {subject}"

    when = str(mail.get("date", ""))[:10]
    quoted = "\n".join(f"> {line}" for line in str(mail.get("body", "")).splitlines()[:40])
    body = (
        f"안녕하세요,\n\n"
        f"{when}에 보내 드린 아래 메일 관련하여 확인 부탁드리고자 다시 연락드립니다.\n"
        f"바쁘신 중에 번거롭게 해 드려 죄송합니다.\n\n"
        f"감사합니다.\n\n"
        f"--- 이전에 보낸 메일 ---\n{quoted}\n"
    )
    return {
        "to": mail.get("toEmail", ""),
        "subject": subject,
        "body": body,
        "inReplyTo": mail.get("messageId", ""),
    }


def star_message(uid: int, folder_key: str = "inbox", starred: bool = True) -> dict:
    """별표(\\Flagged). 예전에는 이 앱 안에만 기억해서 폰이나 웹메일에서는 안 보였다.
    서버 플래그로 붙이면 다른 기기에서도 똑같이 보인다. (서버 지원 확인함)"""
    client = _connect()
    try:
        raw = _folder_raw(client, folder_key) or "INBOX"
        client.select_folder(raw)
        ok = client.store_flag(int(uid), r"\Flagged", add=starred)
    finally:
        client.logout()
    return {"ok": ok, "uid": uid, "starred": starred}


def move_message(uid: int, folder_key: str, target_folder: str) -> dict:
    """메일을 다른 폴더로 옮긴다.

    이 서버는 MOVE 명령이 없어서 '복사한 뒤 원본에 지운 표시'로 흉내낸다.
    UIDPLUS 도 없어 원본을 실제로 지우지는 못한다(지우면 그 폴더의 지운 표시가
    붙은 메일이 전부 날아간다). 목록에서는 빠지고 서버에는 남는다.
    """
    client = _connect()
    try:
        raw = _folder_raw(client, folder_key) or "INBOX"
        if not client.select_folder(raw):
            raise RuntimeError("원래 폴더를 열지 못했습니다.")
        # target_folder 는 화면에서 고른 '실제 폴더 이름(raw)'
        if not client.copy_to(int(uid), target_folder):
            raise RuntimeError("옮길 폴더에 복사하지 못했습니다.")
        client.store_flag(int(uid), r"\Deleted", add=True)
        client.expunge_uid(int(uid))
    finally:
        client.logout()
    return {"ok": True, "uid": uid, "movedTo": target_folder}


def list_mail_folders() -> dict:
    """화면에서 고를 수 있는 폴더 목록."""
    client = _connect()
    try:
        folders = [
            {"raw": raw, "name": decoded, "key": classify_folder(decoded) or ""}
            for raw, decoded in client.list_folders()
        ]
    finally:
        client.logout()
    return {"ok": True, "folders": folders}


def create_mail_folder(name: str) -> dict:
    """새 폴더 만들기. (서버 지원 확인함)"""
    clean = str(name or "").strip()
    if not clean or any(ch in clean for ch in '"\\/'):
        raise ValueError("폴더 이름에 쓸 수 없는 글자가 있습니다.")
    client = _connect()
    try:
        status, _ = client.cmd(f'CREATE "{clean}"')
    finally:
        client.logout()
    if status != "OK":
        raise RuntimeError("폴더를 만들지 못했습니다. 같은 이름이 이미 있을 수 있습니다.")
    return {"ok": True, "name": clean}


def fetch_raw_message(uid: int, folder_key: str = "inbox") -> bytes:
    """메일 원본(.eml). '이메일을 파일로 저장' 에 쓴다."""
    client = _connect()
    try:
        raw = _folder_raw(client, folder_key) or "INBOX"
        client.select_folder(raw)
        status, lines = client.cmd(f"UID FETCH {int(uid)} (BODY.PEEK[])")
        if status != "OK":
            raise RuntimeError("메일 원본을 받지 못했습니다.")
        chunks = [literal for _line, literal in lines if literal]
    finally:
        client.logout()
    if not chunks:
        raise RuntimeError("메일 원본이 비어 있습니다.")
    return max(chunks, key=len)


def delete_message(uid: int, folder_key: str = "inbox", permanent: bool = False) -> dict:
    """메일을 휴지통으로 옮긴다.

    이미 휴지통에 있는 메일은 옮길 곳이 없다. 그대로 지우면 영영 사라지므로
    permanent=True 로 분명히 말했을 때만 지운다.
    """
    client = _connect()
    try:
        raw = _folder_raw(client, folder_key) or "INBOX"
        client.select_folder(raw)
        trash = client.find_folder("지운") or client.find_folder("Trash")
        in_trash = bool(trash) and trash == raw

        if in_trash and not permanent:
            return {
                "ok": False,
                "uid": uid,
                "needsConfirm": True,
                "message": "휴지통에서 지우면 되살릴 수 없습니다.",
            }

        if trash and not in_trash:
            client.copy_to(int(uid), trash)
        client.store_flag(int(uid), r"\Deleted", add=True)
        client.expunge_uid(int(uid))
    finally:
        client.logout()
    return {"ok": True, "uid": uid, "permanent": bool(permanent)}


def restore_message(uid: int, folder_key: str = "trash") -> dict:
    """휴지통에 있는 메일을 받은 편지함으로 되돌린다."""
    client = _connect()
    try:
        raw = _folder_raw(client, folder_key) or "INBOX"
        if not client.select_folder(raw):
            raise RuntimeError("휴지통을 찾지 못했습니다.")
        client.copy_to(int(uid), "INBOX")
        client.store_flag(int(uid), r"\Deleted", add=True)
        client.expunge_uid(int(uid))
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
    atomic_write_json(EMAILS_LOG, payload, ensure_ascii=False, indent=2)
    recommended = len([m for m in emails if m.get("score", 0) >= 6])
    print(f"저장 완료: 메일 {len(emails)}건, 추천 {recommended}건")
    return payload


if __name__ == "__main__":
    refresh_emails()
