"""시간표 가져오기: 에브리타임 공유 링크 / DGIST 개설과목 조회.

두 사이트 모두 화면을 자바스크립트로 그리기 때문에 단순 요청으로는 표가 비어 있다.
이미 앱에 들어 있는 Playwright로 실제 렌더링한 뒤 값을 읽는다.

에브리타임 공유 페이지 규칙(직접 확인함):
- 요일 열은 .tablebody .cols 순서 (0=월)
- 각 수업 블록 .subject 의 style.top 이 '자정부터 몇 분'인지를 그대로 나타내고,
  style.height 가 '수업 길이 + 1분' 이다. (예: top 540 → 09:00, height 121 → 120분)
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

DAY_TO_INDEX = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
    "월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6,
}

EVERYTIME_URL_RE = re.compile(r"^https?://(www\.)?everytime\.kr/@[A-Za-z0-9]+/?$")
DGIST_CATALOG_URL = "https://welcome.dgist.ac.kr/ucs/ucsqProfRespSbjtInq/index.do"

# 'Tue18:00-19:30(E7 - 241)' 한 덩어리
DGIST_SLOT_RE = re.compile(
    r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun|월|화|수|목|금|토|일)\s*"
    r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*(?:\(([^)]*)\))?",
    re.IGNORECASE,
)


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_dgist_slots(text: str) -> list[dict[str, Any]]:
    """'Tue18:00-19:30(E7 - 241), Thu18:00-19:30(E7 - 241)' → 슬롯 목록."""
    slots = []
    for day, start, end, room in DGIST_SLOT_RE.findall(str(text or "")):
        idx = DAY_TO_INDEX.get(day.lower())
        if idx is None or idx > 5:  # 일요일 수업은 시간표에 넣지 않는다
            continue
        h, m = start.split(":")
        h2, m2 = end.split(":")
        slots.append(
            {
                "day": idx,
                "start": f"{int(h):02d}:{m}",
                "end": f"{int(h2):02d}:{m2}",
                "room": (room or "").strip(),
            }
        )
    return slots


async def _fetch_everytime(url: str, timeout_ms: int = 25000) -> list[dict[str, Any]]:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            # .cols 는 크기가 0이라 'visible'로는 못 기다린다. 붙기만 하면 값은 읽을 수 있다.
            await page.wait_for_selector(".tablebody .cols", state="attached", timeout=timeout_ms)
            # 수업 블록이 실제로 채워질 때까지 (빈 시간표면 그냥 넘어감)
            try:
                await page.wait_for_function(
                    "() => document.querySelectorAll('.tablebody .cols .subject').length > 0",
                    timeout=8000,
                )
            except Exception:
                pass
            return await page.evaluate(
                """() => {
                    const cols = [...document.querySelectorAll('.tablebody .cols')];
                    const out = [];
                    cols.forEach((col, day) => {
                        col.querySelectorAll('.subject').forEach(s => {
                            const top = parseFloat(s.style.top);
                            const h = parseFloat(s.style.height);
                            if (!isFinite(top) || !isFinite(h)) return;
                            out.push({
                                day,
                                startMin: Math.round(top),
                                endMin: Math.round(top + h - 1),
                                title: (s.querySelector('h3')||{}).textContent || '',
                                prof: (s.querySelector('em')||{}).textContent || '',
                                room: (s.querySelector('span')||{}).textContent || ''
                            });
                        });
                    });
                    return out;
                }"""
            )
        finally:
            await browser.close()


def import_everytime(url: str) -> dict[str, Any]:
    """에브리타임 공유 링크에서 시간표를 읽어 온다.

    주의: 에브리타임은 자동 접속을 막아 두어 대부분 실패한다.
    그 경우 사용자에게 '시간표 캡처 이미지'로 가져오도록 안내한다.
    """
    url = (url or "").strip()
    if not EVERYTIME_URL_RE.match(url):
        raise ValueError(
            "에브리타임 공유 주소를 넣어 주세요. 예: https://everytime.kr/@AbCdEf123"
        )

    try:
        raw = asyncio.run(_fetch_everytime(url))
    except Exception:
        raise ValueError(
            "에브리타임이 자동 접속을 막고 있어 링크로는 가져올 수 없습니다.\n"
            "시간표를 캡처해서 '이미지로 가져오기'를 이용해 주세요."
        )
    entries = []
    for item in raw:
        if item["day"] > 5:
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        entries.append(
            {
                "title": title,
                "day": int(item["day"]),
                "start": _hhmm(int(item["startMin"])),
                "end": _hhmm(int(item["endMin"])),
                "room": str(item.get("room", "")).strip(),
                "professor": str(item.get("prof", "")).strip(),
            }
        )
    if not entries:
        raise ValueError(
            "시간표를 찾지 못했습니다. 공유 링크가 맞는지, 시간표가 비어 있지 않은지 확인해 주세요."
        )
    return {"ok": True, "entries": entries, "count": len(entries)}


def import_timetable_image(image_base64: str, mime: str = "image/png") -> dict[str, Any]:
    """시간표 캡처 이미지에서 수업을 읽어 온다 (Gemini 사용).

    에브리타임이 자동 접속을 막고 있어, 링크 대신 캡처 이미지를 쓰는 경로다.
    """
    from runtime_config import GEMINI_API_KEY

    if not GEMINI_API_KEY:
        raise ValueError("설정에서 Gemini API 키를 먼저 입력해 주세요. (이미지 인식에 사용합니다)")
    if not image_base64:
        raise ValueError("이미지를 선택해 주세요.")

    import base64 as _b64
    import json as _json

    from google import genai
    from google.genai import types

    prompt = (
        "이 이미지는 대학교 주간 시간표입니다. 모든 수업 칸을 빠짐없이 읽어 JSON 배열로만 답하세요.\n"
        "각 원소는 다음 키를 가집니다:\n"
        '  title: 과목명 (칸에 적힌 그대로)\n'
        '  day: 요일 (월=0, 화=1, 수=2, 목=3, 금=4, 토=5)\n'
        '  start: 시작 시각 "HH:MM" (24시간제)\n'
        '  end: 끝 시각 "HH:MM"\n'
        '  room: 강의실 (없으면 "")\n'
        "규칙:\n"
        "- 세로축 숫자는 시각입니다. 1~6은 오후(13~18시)로 해석하세요.\n"
        "- 칸의 위/아래 끝을 보고 시작·끝 시각을 정확히 정하세요.\n"
        "- 같은 과목이 여러 요일에 있으면 각각 별도 원소로 만드세요.\n"
        "- 설명이나 코드블록 없이 JSON 배열만 출력하세요."
    )

    client = genai.Client(api_key=GEMINI_API_KEY)
    raw = _b64.b64decode(image_base64.split(",")[-1])
    contents = [types.Part.from_bytes(data=raw, mime_type=mime or "image/png"), prompt]

    # 앱의 다른 기능과 같은 모델 순서로 시도 (할당량 소진 시 다음 모델로)
    try:
        from ai_summarizer import GEMINI_MODELS
    except Exception:
        GEMINI_MODELS = ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash")

    result = None
    last_error = None
    for model in GEMINI_MODELS:
        try:
            result = client.models.generate_content(model=model, contents=contents)
            break
        except Exception as exc:
            last_error = exc
    if result is None:
        msg = str(last_error or "")
        if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
            raise ValueError(
                "Gemini 사용량이 한도에 걸렸습니다. 잠시 후 다시 시도하거나 다른 API 키를 써 주세요."
            )
        raise ValueError(f"이미지 인식에 실패했습니다: {msg[:150]}")

    text = (result.text or "").strip()
    # ```json ... ``` 으로 감싸 오는 경우 정리
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("이미지에서 시간표를 읽지 못했습니다. 더 선명한 캡처로 시도해 주세요.")

    try:
        parsed = _json.loads(text[start : end + 1])
    except _json.JSONDecodeError:
        raise ValueError("이미지 인식 결과를 해석하지 못했습니다. 다시 시도해 주세요.")

    entries = []
    for item in parsed if isinstance(parsed, list) else []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        try:
            day = int(item.get("day", -1))
        except (TypeError, ValueError):
            continue
        start_t = str(item.get("start", "")).strip()
        end_t = str(item.get("end", "")).strip()
        if not title or not 0 <= day <= 5:
            continue
        if not re.fullmatch(r"\d{1,2}:\d{2}", start_t) or not re.fullmatch(r"\d{1,2}:\d{2}", end_t):
            continue
        h, m = start_t.split(":")
        h2, m2 = end_t.split(":")
        entries.append(
            {
                "title": title[:60],
                "day": day,
                "start": f"{int(h):02d}:{m}",
                "end": f"{int(h2):02d}:{m2}",
                "room": str(item.get("room", "")).strip()[:40],
            }
        )
    if not entries:
        raise ValueError("이미지에서 수업을 찾지 못했습니다. 시간표 전체가 나오게 캡처해 주세요.")
    return {"ok": True, "entries": entries, "count": len(entries)}


# 조직분류 코드
ORG_UNDERGRAD = "CMN12.03"   # 대학(학부)
ORG_GRADUATE = "CMN12.02"    # 대학원

# 학기 코드
TERM_CODES = {"spring": "CMN17.10", "summer": "CMN17.11", "fall": "CMN17.20", "winter": "CMN17.21"}
TERM_LABELS = {"CMN17.10": "1학기", "CMN17.11": "여름학기", "CMN17.20": "2학기", "CMN17.21": "겨울학기"}


async def _fetch_dgist(
    year_term: str = "", org: str = ORG_UNDERGRAD, timeout_ms: int = 45000
) -> list[dict[str, Any]]:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(DGIST_CATALOG_URL, wait_until="networkidle", timeout=timeout_ms)
            # 조회 조건을 걸고 다시 검색한다.
            # 화면에 보이는 쪽(...Dcd2)을 반드시 설정해야 필터가 먹는다.
            await page.evaluate(
                """([org, yearTerm]) => {
                    // 조직분류(학부/대학원)는 change를 보내야 반영된다.
                    // 화면에 보이는 쪽(...Dcd2)까지 함께 설정해야 한다.
                    const setWithChange = (name, val) => {
                        const el = document.querySelector(`[name=${name}]`);
                        if (!el || !val) return;
                        el.value = val;
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    };
                    setWithChange('searchOrgnClsfDcd1', org);
                    setWithChange('searchOrgnClsfDcd2', org);

                }""",
                [org, year_term],
            )
            await page.wait_for_timeout(900)
            # 학기는 반대다. change를 보내면 사이트 핸들러가 '현재 학기'로 되돌리므로
            # 값만 넣고, 조직 변경 핸들러가 되돌리지 못하도록 검색 직전에 설정한다.
            await page.evaluate(
                """(yearTerm) => {
                    const term = document.querySelector('[name=selectYearTerm]');
                    if (term && yearTerm) term.value = yearTerm;
                }""",
                year_term,
            )
            await page.click("#btn_Search")
            await page.wait_for_timeout(4000)
            # 표가 채워질 때까지
            await page.wait_for_function(
                "() => [...document.querySelectorAll('table')].some(t => t.rows.length > 3)",
                timeout=timeout_ms,
            )
            return await page.evaluate(
                """() => {
                    const tables = [...document.querySelectorAll('table')];
                    const hdrTable = tables.find(t => t.querySelectorAll('th').length > 5);
                    const big = tables.find(t => t.rows.length > 20);
                    if (!hdrTable || !big) return [];
                    const headers = [...hdrTable.querySelectorAll('th')].map(h => h.textContent.trim());
                    const col = (name) => headers.indexOf(name);
                    const idx = {
                        year: col('학년도'), term: col('학기'),
                        dept: col('Department'), no: col('CourseNumber'),
                        section: col('Section'), title: col('Course Title'),
                        prof: col('Instructor'), credit: col('Credit'),
                        when: col('Day/Time/Class Room'),
                        classification: col('Classification')
                    };
                    const rows = [];
                    [...big.rows].forEach(r => {
                        const c = [...r.cells].map(x => x.textContent.trim());
                        if (!c.length || !c[idx.title]) return;
                        rows.push({
                            year: c[idx.year] || '', term: c[idx.term] || '',
                            dept: c[idx.dept] || '', courseNo: c[idx.no] || '',
                            section: c[idx.section] || '', title: c[idx.title] || '',
                            professor: c[idx.prof] || '', credit: c[idx.credit] || '',
                            when: c[idx.when] || '', classification: c[idx.classification] || ''
                        });
                    });
                    return rows;
                }"""
            )
        finally:
            await browser.close()


def available_terms(back_years: int = 4) -> list[dict[str, str]]:
    """선택 가능한 학기 목록 (최근 것부터)."""
    from datetime import datetime

    this_year = datetime.now().year
    out = []
    for year in range(this_year, this_year - back_years, -1):
        for key in ("fall", "summer", "spring"):
            code = TERM_CODES[key]
            out.append(
                {
                    "value": f"{year}{code}",
                    "label": f"{year}년 {TERM_LABELS[code]}",
                    "year": str(year),
                }
            )
    return out


def current_term_value() -> str:
    """오늘 기준으로 가장 그럴듯한 학기 코드."""
    from datetime import datetime

    now = datetime.now()
    if now.month <= 2:
        return f"{now.year - 1}{TERM_CODES['winter']}"
    if now.month <= 6:
        return f"{now.year}{TERM_CODES['spring']}"
    if now.month <= 8:
        return f"{now.year}{TERM_CODES['summer']}"
    return f"{now.year}{TERM_CODES['fall']}"


def fetch_dgist_catalog(year_term: str = "", undergraduate: bool = True) -> dict[str, Any]:
    """DGIST 개설과목 목록을 가져와 요일·시간까지 풀어 놓는다.

    year_term: '2026CMN17.10' 형태. 비우면 오늘 기준 학기.
    undergraduate: True면 학부(대학) 과목만.
    """
    year_term = (year_term or "").strip() or current_term_value()
    org = ORG_UNDERGRAD if undergraduate else ORG_GRADUATE
    rows = asyncio.run(_fetch_dgist(year_term=year_term, org=org))
    courses = []
    for row in rows:
        slots = parse_dgist_slots(row.get("when", ""))
        courses.append(
            {
                "title": row.get("title", ""),
                "courseNo": row.get("courseNo", ""),
                "section": row.get("section", ""),
                "professor": row.get("professor", ""),
                "credit": row.get("credit", ""),
                "dept": row.get("dept", ""),
                "year": row.get("year", ""),
                "classification": row.get("classification", ""),
                "raw": row.get("when", ""),
                "slots": slots,
            }
        )
    with_time = [c for c in courses if c["slots"]]
    return {
        "ok": True,
        "count": len(courses),
        "withTime": len(with_time),
        "yearTerm": year_term,
        "undergraduate": undergraduate,
        "courses": courses,
    }
