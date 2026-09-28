"""DGIST 학사일정 가져오기.

공식 홈페이지의 학사일정 페이지는 로그인이 필요 없고 서버에서 HTML로 그려 준다.
그래서 Playwright 없이 그냥 받아서 읽으면 된다.

실제 마크업(직접 확인함):
    <div class="li">
      <em><i class="ir ir-bage bage2">대학원</i></em>
      <b>01. 02 ~ 01. 05</b>
      <span class="subject">대학원 석‧박사 통합과정 전환 신청</span>
    </div>
"""
from __future__ import annotations

import re
import time
import urllib.request
import zlib
from datetime import date, timedelta
from typing import Any

CALENDAR_URL = "https://www.dgist.ac.kr/prog/schafsSchdul/kor/sub05_01_01/list.do"

# <div class="li"> … </div> 한 덩어리
_ITEM_RE = re.compile(r'<div class="li">(.*?)</div>', re.S)
_BADGE_RE = re.compile(r'<i[^>]*class="[^"]*ir-bage[^"]*"[^>]*>(.*?)</i>', re.S)
_PERIOD_RE = re.compile(r"<b>(.*?)</b>", re.S)
_SUBJECT_RE = re.compile(r'<span class="subject">(.*?)</span>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")

# '01. 02 ~ 01. 05' 또는 '02. 13'
_RANGE_RE = re.compile(r"(\d{1,2})\s*\.\s*(\d{1,2})(?:\s*~\s*(\d{1,2})\s*\.\s*(\d{1,2}))?")


def _clean(html: str) -> str:
    """태그를 걷고 문자 코드를 모두 푼다 ('&#039;27.2월 졸업생' 이 그대로 보였다)."""
    import html as html_lib

    text = html_lib.unescape(_TAG_RE.sub("", html))
    return " ".join(text.replace(" ", " ").split())


def _kind_of(title: str) -> str:
    """제목으로 학부/대학원 구분. 둘 다 해당하면 '공통'."""
    grad = "대학원" in title
    # '대학원'을 지운 뒤에도 '대학'이 남으면 학부 일정도 포함된 것
    under = "대학" in title.replace("대학원", "")
    if grad and under:
        return "공통"
    if grad:
        return "대학원"
    if under:
        return "대학"
    return "공통"


def _fetch(year: int, timeout: int = 20, tries: int = 3) -> str:
    """학교 홈페이지가 가끔 응답을 끊어서, 몇 번 다시 시도한다."""
    url = f"{CALENDAR_URL}?searchYear={year}"
    req = urllib.request.Request(url, headers={"User-Agent": "DGIST-AutoSaver"})
    last: Exception | None = None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            # 페이지는 UTF-8이지만, 혹시 몰라 실패해도 죽지 않게 한다.
            return raw.decode("utf-8", errors="replace")
        except Exception as exc:
            last = exc
            if attempt < tries - 1:
                time.sleep(1.2 * (attempt + 1))
    raise last if last else RuntimeError("학사일정을 받지 못했습니다.")


def _api_events(year: int) -> list[dict[str, Any]]:
    """공식 오픈API 쪽 학사일정. 키가 없거나 실패하면 빈 목록."""
    try:
        import dgist_api

        if not dgist_api.has_key():
            return []
        return dgist_api.fetch_schedule(year).get("events", []) or []
    except Exception:
        return []


def _merge_events(primary: list[dict[str, Any]], extra: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 날 같은 제목이면 한 건으로 본다. primary 쪽 값을 남긴다.

    API 는 시작·종료 '시각'까지 주고 홈페이지는 날짜만 준다.
    그래서 API 를 primary 로 두고, 홈페이지에만 있는 일정을 여기서 채운다.
    """
    seen = {(e.get("start", ""), e.get("title", "")) for e in primary}
    merged = list(primary)
    for event in extra:
        if (event.get("start", ""), event.get("title", "")) not in seen:
            merged.append(event)
    merged.sort(key=lambda e: (e["start"], e["title"]))
    return merged


def fetch_academic_calendar(year: int | None = None) -> dict[str, Any]:
    """학사일정을 {날짜, 제목, 구분} 목록으로 돌려준다.

    공식 오픈API가 먼저, 홈페이지 크롤링이 보조다.
    둘 중 하나만 살아 있어도 화면은 그대로 뜬다.
    """
    year = int(year or date.today().year)

    # 공식 API 와 홈페이지는 서로 다른 서버다. 줄 세울 이유가 없어서 같이 부른다.
    # (키가 없으면 _api_events 는 네트워크를 안 쓰고 바로 빈 목록을 준다)
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        api_future = pool.submit(_api_events, year)
        html_future = pool.submit(_fetch, year)
        from_api = api_future.result()
        html_error: Exception | None = None
        try:
            html = html_future.result()
        except Exception as exc:
            html_error = exc

    if html_error is not None:
        exc = html_error
        if from_api:
            return {"ok": True, "source": "openapi", "year": year,
                    "count": len(from_api), "events": from_api}
        return {"ok": False, "year": year, "events": [], "message": f"학사일정을 받지 못했습니다: {exc}"}

    events: list[dict[str, Any]] = []
    for block in _ITEM_RE.findall(html):
        subject = _SUBJECT_RE.search(block)
        period = _PERIOD_RE.search(block)
        if not subject or not period:
            continue
        title = _clean(subject.group(1))
        span = _clean(period.group(1))
        # 페이지의 배지는 전부 '대학원'으로 붙어 있어 구분에 쓸 수 없다.
        # 제목에 들어 있는 말로 학부/대학원을 가른다.
        kind = _kind_of(title)

        m = _RANGE_RE.search(span)
        if not m or not title:
            continue
        start_m, start_d, end_m, end_d = m.groups()
        start = f"{year}-{int(start_m):02d}-{int(start_d):02d}"
        if end_m and end_d:
            # 12월에 시작해 1월에 끝나면 해가 넘어간다
            end_year = year + 1 if int(end_m) < int(start_m) else year
            end = f"{end_year}-{int(end_m):02d}-{int(end_d):02d}"
        else:
            end = start

        events.append(
            {
                # hash()는 실행할 때마다 값이 달라 중복 판단에 못 쓴다
                "id": f"acad-{start}-{zlib.crc32(title.encode('utf-8')) % 100000:05d}",
                "title": title,
                "start": start,
                "end": end,
                "kind": kind,
                "source": "학사일정",
            }
        )

    events.sort(key=lambda e: (e["start"], e["title"]))
    if from_api:
        events = _merge_events(from_api, events)
        return {"ok": True, "source": "openapi+crawl", "year": year,
                "count": len(events), "events": events}
    return {"ok": True, "source": "crawl", "year": year, "count": len(events), "events": events}


if __name__ == "__main__":
    result = fetch_academic_calendar()
    print(result["ok"], result.get("count"))
    for item in result["events"][:8]:
        print(" ", item["start"], "~", item["end"], "|", item["kind"], "|", item["title"])


# ===== 학기 구간 =====
# 개강·종강 일정을 찾아 '지금이 몇 학기인지'를 정한다.
# 시간표·개설과목이 이 값에 맞춰 움직인다.
_TERM_CODES = {1: "CMN17.10", 2: "CMN17.20"}


def semester_windows(events: list[dict]) -> list[dict]:
    """[{year, term, start, end, label, code}] 를 학기 시작순으로 돌려준다."""
    opens: dict[tuple[int, int], str] = {}
    closes: dict[tuple[int, int], str] = {}
    for ev in events or []:
        title = ev.get("title", "")
        m = re.search(r"(\d{4})학년도\s*([12])학기\s*(개강|종강)", title)
        if not m:
            continue
        key = (int(m.group(1)), int(m.group(2)))
        (opens if m.group(3) == "개강" else closes)[key] = ev.get("start", "")

    windows = []
    for key in sorted(set(opens) | set(closes)):
        year, term = key
        start = opens.get(key, "")
        end = closes.get(key, "")
        if not start:
            continue
        windows.append(
            {
                "year": year,
                "term": term,
                "start": start,
                # 종강이 없으면 개강 + 16주로 본다
                "end": end or (date.fromisoformat(start) + timedelta(weeks=16)).isoformat(),
                "label": f"{year}학년도 {term}학기",
                "code": f"{year}{_TERM_CODES[term]}",
            }
        )
    return windows


def current_semester(events: list[dict], today: date | None = None) -> dict:
    """지금 학기. 방학 중이면 다음 학기를 '곧 시작'으로 알려 준다."""
    now = today or date.today()
    windows = semester_windows(events)
    if not windows:
        return {}

    for w in windows:
        start = date.fromisoformat(w["start"])
        end = date.fromisoformat(w["end"])
        if start <= now <= end:
            return {
                **w,
                "state": "during",
                "week": (now - start).days // 7 + 1,
                "daysLeft": (end - now).days,
            }

    upcoming = [w for w in windows if date.fromisoformat(w["start"]) > now]
    if upcoming:
        nxt = upcoming[0]
        return {**nxt, "state": "before", "daysUntil": (date.fromisoformat(nxt["start"]) - now).days}

    last = windows[-1]
    return {**last, "state": "after"}
