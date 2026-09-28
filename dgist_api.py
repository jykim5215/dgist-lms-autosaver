"""DGIST 공공데이터 오픈API(data.go.kr, 기관코드 B552467) 클라이언트.

지금까지 개설과목·학사일정은 학교 홈페이지 HTML을 긁어 왔다.
화면이 바뀌면 그대로 빈 목록이 되기 때문에, 공식 API가 있으면 그쪽을 먼저 쓴다.
키가 없거나 API가 죽으면 기존 크롤링으로 되돌아간다. (부르는 쪽에서 처리)

세 서비스 모두 직접 확인한 실제 경로다:
    개설강좌정보    OpenLtService/UnivLtList
    학사일정정보    AcademicScheService/UnivSchisList
    세미나행사정보  EvtntcListService01/getNtcList01

인증키는 공공데이터포털에서 발급받아 config.py 의 DGIST_API_KEY 에 넣거나
환경변수 AUTOSAVER_DGIST_API_KEY 로 준다.
"""
from __future__ import annotations

import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from datetime import date, datetime
from typing import Any

BASE = "https://apis.data.go.kr/B552467"

COURSE_PATH = "OpenLtService/UnivLtList"
SCHEDULE_PATH = "AcademicScheService/UnivSchisList"     # 대학(학부)
SCHEDULE_GRAD_PATH = "AcademicScheService/GrscSchisList"  # 대학원
NOTICE_PATH = "EvtntcListService01/getNtcList01"

# 학기 코드: 앱 안에서 쓰는 'CMN17.xx' ↔ API 가 받는 두 자리 숫자
TERM_CODE_TO_SEMESTER = {
    "CMN17.10": "10",   # 1학기
    "CMN17.11": "11",   # 여름 계절학기
    "CMN17.20": "20",   # 2학기
    "CMN17.21": "21",   # 겨울 계절학기
}
SEMESTER_LABELS = {"10": "1학기", "11": "여름학기", "20": "2학기", "21": "겨울학기"}

# data.go.kr 오류코드 중 사람이 바로 고칠 수 있는 것들
_ERROR_HINTS = {
    "12": "해당 API 서비스가 없거나 폐기됐습니다.",
    "20": "서비스 접근이 거부됐습니다. 포털에서 활용신청이 승인됐는지 확인해 주세요.",
    "22": "오늘 호출 한도를 넘었습니다. 내일 다시 시도하거나 운영계정을 신청해 주세요.",
    "30": "등록되지 않은 인증키입니다. 키를 다시 확인해 주세요.",
    "31": "기한이 만료된 인증키입니다.",
}


class DgistApiError(RuntimeError):
    """API 가 오류를 돌려줬거나 응답을 읽지 못했을 때."""


# ===== 인증키 =====

def service_key() -> str:
    """설정에서 인증키를 읽는다. 없으면 빈 문자열.

    앱 설정 화면에서 넣은 값은 config.json 에 들어가고 runtime_config 가 읽는다.
    (예전에는 config.py 만 봐서, 화면에서 넣어도 안 먹었다)
    """
    key = (os.environ.get("AUTOSAVER_DGIST_API_KEY") or "").strip()
    if key:
        return key
    try:
        from runtime_config import DGIST_API_KEY

        if DGIST_API_KEY:
            return DGIST_API_KEY.strip()
    except Exception:
        pass
    try:
        import config  # type: ignore

        return (getattr(config, "DGIST_API_KEY", "") or "").strip()
    except Exception:
        return ""


def has_key() -> bool:
    return bool(service_key())


def _encoded_key(key: str) -> str:
    """포털은 인코딩키·디코딩키를 둘 다 주는데, 어느 쪽을 붙여넣어도 되게 한다.

    디코딩키에는 '+' '/' '=' 가 들어 있어서 그대로 쿼리에 붙이면 깨진다.
    이미 인코딩된 키('%2B' 같은 게 들어 있음)는 그대로 둔다.
    """
    if "%" in key:
        return key
    return urllib.parse.quote(key, safe="")


# ===== 공통 호출 =====

def _request(path: str, params: dict[str, Any], timeout: int = 20, tries: int = 3) -> ET.Element:
    key = service_key()
    if not key:
        raise DgistApiError("DGIST 오픈API 인증키가 없습니다.")

    query = urllib.parse.urlencode(
        {k: v for k, v in params.items() if v not in (None, "")}, safe=""
    )
    url = f"{BASE}/{path}?serviceKey={_encoded_key(key)}&{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "DGIST-AutoSaver"})

    last: Exception | None = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            break
        except Exception as exc:  # 학교/포털 쪽이 가끔 끊는다
            last = exc
            if attempt < tries - 1:
                time.sleep(1.2 * (attempt + 1))
    else:
        raise DgistApiError(f"요청이 실패했습니다: {last}")

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise DgistApiError(f"응답을 읽지 못했습니다: {exc}") from exc

    _raise_for_error(root)
    return root


def _text(node: ET.Element | None, tag: str, default: str = "") -> str:
    if node is None:
        return default
    found = node.find(tag)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def _raise_for_error(root: ET.Element) -> None:
    """포털 공통 오류(<cmmMsgHeader>)와 서비스 오류(resultCode)를 사람 말로 바꾼다."""
    header = root.find(".//cmmMsgHeader")
    if header is not None:
        code = _text(header, "returnReasonCode")
        msg = _text(header, "returnAuthMsg") or _text(header, "errMsg")
        raise DgistApiError(_ERROR_HINTS.get(code, msg or f"오류코드 {code}"))

    code = _text(root.find(".//header"), "resultCode") or _text(root, ".//resultCode")
    if code and code not in ("0", "00", "000"):
        msg = _text(root.find(".//header"), "resultMsg") or _text(root, ".//resultMsg")
        raise DgistApiError(_ERROR_HINTS.get(code, msg or f"오류코드 {code}"))


def _items(root: ET.Element) -> list[ET.Element]:
    """<item> 목록. 서비스마다 감싸는 태그가 달라서 넓게 찾는다."""
    found = root.findall(".//item")
    if found:
        return found
    # item 이 없고 결과가 바로 나열되는 형태도 있다
    body = root.find(".//body") or root.find(".//items")
    return list(body) if body is not None else []


def _total_count(root: ET.Element) -> int:
    raw = _text(root, ".//totalCount")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _fetch_all(path: str, params: dict[str, Any], rows: int = 100, max_pages: int = 40) -> list[ET.Element]:
    """totalCount 를 보고 끝까지 받아 온다.

    첫 장을 받으면 전체 개수를 알 수 있으니, 남은 장은 한꺼번에 받는다.
    대학원 개설강좌가 900건이 넘어 열 장씩 나오는데, 한 장씩 줄 세우면
    왕복 시간이 그대로 열 배가 된다.
    """
    from concurrent.futures import ThreadPoolExecutor

    first = _request(path, {**params, "numOfRows": rows, "pageNo": 1})
    collected = _items(first)
    total = _total_count(first)

    if not collected or len(collected) < rows or total <= len(collected):
        return collected

    last_page = min(max_pages, -(-total // rows))  # 올림 나눗셈
    if last_page <= 1:
        return collected

    def page(no: int) -> list[ET.Element]:
        try:
            return _items(_request(path, {**params, "numOfRows": rows, "pageNo": no}))
        except DgistApiError:
            return []

    # 포털 쪽 부담을 생각해 동시 4개까지만
    with ThreadPoolExecutor(max_workers=4) as pool:
        for chunk in pool.map(page, range(2, last_page + 1)):
            collected.extend(chunk)
    return collected


# ===== 개설강좌정보 =====

def _split_year_term(year_term: str) -> tuple[int, str]:
    """'2026CMN17.10' → (2026, '10'). 형식이 아니면 오늘 기준으로 정한다."""
    text = (year_term or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        year = int(text[:4])
        code = text[4:]
        if code in TERM_CODE_TO_SEMESTER:
            return year, TERM_CODE_TO_SEMESTER[code]
        if code in SEMESTER_LABELS:
            return year, code
        return year, "10"
    now = datetime.now()
    return now.year, "10" if now.month <= 7 else "20"


def fetch_courses(year_term: str = "", undergraduate: bool = True, language: str = "ko") -> dict[str, Any]:
    """개설강좌 목록을 timetable_import 가 쓰는 모양으로 돌려준다.

    API 는 학부/대학원을 나눠 주지 않고 organization 필드로 표시하므로,
    받은 뒤에 걸러낸다.
    """
    from timetable_import import parse_dgist_slots

    year, semester = _split_year_term(year_term)
    nodes = _fetch_all(COURSE_PATH, {"year": year, "semester": semester, "language": language})

    wanted = "대학원" if not undergraduate else "대학"
    courses: list[dict[str, Any]] = []
    for node in nodes:
        org = _text(node, "organization")
        # '대학원'은 '대학'을 포함하므로 정확히 갈라야 한다
        is_grad = "대학원" in org
        if undergraduate and is_grad:
            continue
        if not undergraduate and not is_grad:
            continue

        when = _text(node, "timetable")
        courses.append(
            {
                "title": _text(node, "courseTitle"),
                "titleEn": "",
                "courseNo": _text(node, "courseNo"),
                "section": _text(node, "section"),
                "professor": _text(node, "instructor"),
                "professorEn": "",
                "credit": _text(node, "credit"),
                "dept": _text(node, "department"),
                "year": _text(node, "year"),
                "classification": _text(node, "classification") or _text(node, "courseType"),
                "raw": when,
                "slots": parse_dgist_slots(when),
            }
        )

    with_time = [c for c in courses if c["slots"]]
    return {
        "ok": True,
        "source": "openapi",
        "count": len(courses),
        "withTime": len(with_time),
        "yearTerm": year_term or f"{year}{'CMN17.10' if semester == '10' else 'CMN17.20'}",
        "undergraduate": undergraduate,
        "korean": language == "ko",
        "courses": courses,
        "organization": wanted,
    }


# ===== 학사일정정보 =====

def _iso(value: str) -> str:
    """'2021/06/07' → '2021-06-07'. 못 읽으면 빈 문자열."""
    text = (value or "").strip().replace(".", "/").replace("-", "/")
    parts = [p for p in text.split("/") if p]
    if len(parts) != 3:
        return ""
    try:
        return date(int(parts[0]), int(parts[1]), int(parts[2])).isoformat()
    except ValueError:
        return ""


def fetch_schedule(year: int | None = None, semester: str = "", include_grad: bool = True) -> dict[str, Any]:
    """학사일정을 academic_calendar 와 같은 모양({id,title,start,end,kind,source})으로.

    대학·대학원이 서로 다른 오퍼레이션이라 둘 다 받아서 합친다.
    대학원 쪽이 실패해도 대학 일정은 그대로 나온다.
    """
    year = int(year or date.today().year)
    params: dict[str, Any] = {"year": year}
    if semester:
        params["semester"] = semester

    nodes = _fetch_all(SCHEDULE_PATH, params)
    if include_grad:
        try:
            nodes = nodes + _fetch_all(SCHEDULE_GRAD_PATH, params)
        except DgistApiError:
            pass

    events: list[dict[str, Any]] = []
    for node in nodes:
        title = _text(node, "title")
        start = _iso(_text(node, "fromDate"))
        if not title or not start:
            continue
        end = _iso(_text(node, "toDate")) or start
        org = _text(node, "organization") or "공통"
        # 대학·대학원에 같은 이름의 일정이 따로 있을 수 있어 구분까지 넣어야 안 겹친다
        stamp = zlib.crc32(f"{title}|{org}".encode("utf-8")) % 100000
        events.append(
            {
                "id": f"acad-api-{start}-{stamp:05d}",
                "title": title,
                "start": start,
                "end": end,
                # 기존 화면이 '대학/대학원/공통'을 쓴다
                "kind": "대학원" if "대학원" in org else ("대학" if "대학" in org else "공통"),
                "source": "학사일정",
                "fromTime": _text(node, "fromTime"),
                "toTime": _text(node, "toTime"),
                "period": _text(node, "period"),
                "semester": _text(node, "semester"),
            }
        )

    # 같은 일정이 대학·대학원 양쪽에 똑같이 들어 있는 경우가 있다
    unique: dict[str, dict[str, Any]] = {}
    for event in events:
        unique.setdefault(event["id"], event)
    events = sorted(unique.values(), key=lambda e: (e["start"], e["title"]))
    return {"ok": True, "source": "openapi", "year": year, "count": len(events), "events": events}


# ===== 세미나·행사정보 =====

_TAG_RE = __import__("re").compile(r"<[^>]+>")


def _plain(html_text: str, limit: int = 400) -> str:
    text = _TAG_RE.sub(" ", html_text or "")
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        text = text.replace(a, b)
    text = " ".join(text.split())
    return text[:limit]


def fetch_notices(rows: int = 30, site_code: str = "") -> dict[str, Any]:
    """세미나·행사 공지. 매주 새로 올라오므로 목록 앞쪽만 본다."""
    params: dict[str, Any] = {"numOfRows": rows, "pageNo": 1}
    if site_code:
        params["siteCode"] = site_code
    root = _request(NOTICE_PATH, params)

    items: list[dict[str, Any]] = []
    for node in _items(root):
        title = _text(node, "title") or _text(node, "ntcTitle") or _text(node, "evtNm")
        if not title:
            continue
        posted = _iso(_text(node, "regDate") or _text(node, "registDate") or _text(node, "regdate"))
        items.append(
            {
                "id": f"evt-{zlib.crc32(title.encode('utf-8')) % 1000000:06d}",
                "title": title,
                "body": _plain(_text(node, "content") or _text(node, "ntcCn") or _text(node, "evtCn")),
                "author": _text(node, "writer") or _text(node, "author") or _text(node, "regUser"),
                "views": _text(node, "readCount") or _text(node, "viewCount") or _text(node, "inqCnt"),
                "date": posted,
                "source": "세미나·행사",
            }
        )

    items.sort(key=lambda e: e["date"], reverse=True)
    return {"ok": True, "source": "openapi", "count": len(items), "items": items}


# ===== 상태 점검 =====

def probe() -> dict[str, Any]:
    """세 서비스가 실제로 응답하는지 확인한다. 설정 화면에서 쓴다."""
    if not has_key():
        return {"ok": False, "hasKey": False, "message": "인증키가 설정되지 않았습니다.", "services": {}}

    # 살아 있는지만 보면 되므로 한 건씩만 달라고 한다.
    # 예전에는 여기서 fetch_courses() 를 그대로 불러 2천 과목을 전부 받았다.
    # 설정 화면을 열 때마다 그 짓을 하면 하루 호출 한도(개발계정 10,000)도 금방 닳는다.
    year, semester = _split_year_term("")
    checks = {
        "courses": (COURSE_PATH, {"year": year, "semester": semester}),
        "schedule": (SCHEDULE_PATH, {"year": year}),
        "notices": (NOTICE_PATH, {}),
    }

    def probe_one(item: tuple[str, dict[str, Any]]) -> dict[str, Any]:
        path, params = item
        try:
            root = _request(path, {**params, "numOfRows": 1, "pageNo": 1})
            return {"ok": True, "total": _total_count(root)}
        except DgistApiError as exc:
            return {"ok": False, "message": str(exc)}
        except Exception as exc:
            return {"ok": False, "message": f"예상치 못한 오류: {exc}"}

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(probe_one, checks.values()))
    services = dict(zip(checks.keys(), results))

    return {
        "ok": all(s["ok"] for s in services.values()),
        "hasKey": True,
        "services": services,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(probe(), ensure_ascii=False, indent=2))
