"""DGIST 통근·순환 버스 시간표.

학교 공식홈의 셔틀버스 안내는 로그인이 필요 없고, 노선이
'정류장[시각] → 정류장[시각]' 형태로 적혀 있어 그대로 읽어 쓸 수 있다.

    상인역[08:08]→진천역[08:11]→테크노폴리스로→중흥S클래스정문건너편[08:40]→DGIST[08:45]

화살표로 끊고 대괄호 안을 시각으로 본다.
'테크노폴리스로', '성서IC경유'처럼 시각이 없는 칸은 '거쳐 가는 곳'으로 따로 표시한다.
"""
from __future__ import annotations

import re
import time
import urllib.request
from typing import Any

BASE = "https://www.dgist.ac.kr"
PAGES = [
    # (주소, 갈래 이름)
    ("/kor/sub05_04_05_01.do", "통근"),
    ("/kor/sub05_04_05_02.do", "순환"),
]

_TAG_RE = re.compile(r"<[^>]+>")
_TABLE_RE = re.compile(r"<table.*?</table>", re.S)
_CAPTION_RE = re.compile(r"<caption[^>]*>(.*?)</caption>", re.S)
_ROW_RE = re.compile(r"<tr\b.*?</tr>", re.S)
_CELL_RE = re.compile(r"<t[dh]\b.*?</t[dh]>", re.S)
# 정류장[08:08] / 정류장(08:08) 둘 다 받는다
_STOP_RE = re.compile(r"^(.*?)[\[(](\d{1,2}:\d{2})[\])]\s*$")


def _clean(html: str) -> str:
    """태그를 걷고 문자 코드를 푼다.

    예전에는 &nbsp; 같은 몇 개만 손으로 바꿨다. 2026년 9월 홈페이지가 화살표를
    '&rarr;' 로 적기 시작하자 노선을 한 칸도 못 끊어 시간표가 통째로 비었고,
    앱은 조용히 8월 캐시를 계속 보여 줬다. 모든 문자 코드를 표준대로 푼다.
    """
    import html as html_lib

    text = html_lib.unescape(_TAG_RE.sub(" ", html))
    return " ".join(text.replace("\xa0", " ").split())


def _repair_times(text: str) -> str:
    """'정문11:30]' 처럼 여는 대괄호가 빠진 시각을 '정문[11:30]' 으로 고친다."""
    return re.sub(r"(?<=[^\s\[\d:])(\d{1,2}:\d{2})\]", r"[\1]", text)


def _fetch(url: str, timeout: int = 20, tries: int = 3) -> str:
    """학교 홈페이지가 가끔 연결을 끊어서 몇 번 다시 시도한다."""
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Accept-Language": "ko-KR,ko;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as exc:
            last = exc
            if attempt < tries - 1:
                time.sleep(1.2 * (attempt + 1))
    raise last if last else RuntimeError("버스 시간표를 받지 못했습니다.")


def parse_route(text: str) -> list[dict[str, Any]]:
    """'A[08:08] → B → C[08:45]' 를 정류장 목록으로 바꾼다."""
    # 화살표 종류가 섞여 있고, 어떤 줄은 하이픈으로 이었다.
    #   두류역[08:00]-용산역[08:05]
    # 다만 'KTX-산천'처럼 이름 안의 하이픈은 끊으면 안 되므로,
    # 시각 뒤(] 또는 ))에 붙은 하이픈만 화살표로 바꾼다.
    text = re.sub(r"([\]\)])\s*[-–—]\s*", r"\1 → ", text)
    parts = re.split(r"→|➞|->|—>", text)
    stops: list[dict[str, Any]] = []
    for raw in parts:
        piece = raw.strip(" \t-–—")
        if not piece:
            continue
        m = _STOP_RE.match(piece)
        if m:
            # '＊현풍터미널건너' 의 별표는 홈페이지의 표시일 뿐 이름이 아니다
            name = m.group(1).strip(" \t-–—＊*")
            if name:
                stops.append({"name": name, "time": m.group(2), "via": False})
        else:
            # 시각이 없는 칸: '성서IC경유'처럼 거쳐만 가는 곳
            # 괄호 안 안내문(KTX 시간 등)은 너무 길어 노선도에 넣지 않는다
            if len(piece) <= 20 and not piece.startswith("("):
                stops.append({"name": piece, "time": "", "via": True})
    return stops


def _split_route_start(text: str) -> tuple[str, str]:
    """시간 칸과 노선이 한 칸에 붙어 온 경우 '앞 안내문' 과 '노선' 으로 가른다.

    '08:20 출발 - 동서울(08:55) R1[08:20]→E7건너→…' → ('08:20 출발 - 동서울(08:55)', 'R1[08:20]→…')
    """
    match = re.search(r"[^\s→]+\s*(?:\[\d{1,2}:\d{2}\])?\s*→", text)
    if not match or match.start() == 0:
        return "", text
    return text[: match.start()].strip(), text[match.start():].strip()


# 순환버스 '구분' 칸의 짧은 이름 → 사람이 알아볼 이름 (홈페이지 아래 설명 기준)
_LABELS = {
    "A": "테크노폴리스 A",
    "B": "테크노폴리스 B",
}


def _routes_from_table(block: str, kind: str) -> list[dict[str, Any]]:
    """표 하나를 노선 목록으로.

    머리줄에서 칸 이름을 읽어 어느 칸이 무엇인지 정한다. 홈페이지가
    '연번·노선 이름·노선[시간]·QR탑승권' (통근) 과 '연번·구분·시간·노선' (순환)
    두 가지 모양을 쓰고, 칸 순서를 바꿔도 따라가게 하기 위함이다.
    """
    cap_match = _CAPTION_RE.search(block)
    caption = _clean(cap_match.group(1)) if cap_match else ""
    head = caption.split(" - ")[0]                     # '출근버스(평일운행) 40인승'
    title = re.split(r"[(]", head)[0].strip() or kind   # '출근버스', '원내순환 버스'
    days_match = re.search(r"\(([^)]*)\)", head)
    days = days_match.group(1).replace("운행", "").strip() if days_match else ""
    seats_match = re.search(r"(\d+)\s*인승", head)
    group = title.replace(" 버스", "") + (f" ({days})" if days else "")

    rows = _ROW_RE.findall(block)
    if not rows:
        return []
    header = [_clean(c) for c in _CELL_RE.findall(rows[0])]

    def column(*names: str) -> int | None:
        for index, name in enumerate(header):
            if any(name.startswith(n) for n in names):
                return index
        return None

    name_col = column("노선 이름", "구분")
    time_col = column("시간")
    path_col = column("노선[", "노선")
    if path_col == name_col:
        path_col = next((i for i, n in enumerate(header) if n.startswith("노선") and i != name_col), None)
    qr_col = column("QR")

    routes = []
    for row in rows[1:]:
        cells = [_clean(c) for c in _CELL_RE.findall(row)]
        if len(cells) < 3:
            continue
        number = re.search(r"\d+", cells[0])
        if not number:
            continue
        # '＊ 17 금요일 미운행' 처럼 연번 칸에 붙은 안내
        row_note = re.sub(r"[＊*]?\s*\d+\s*", "", cells[0], count=1).strip()

        label = cells[name_col] if name_col is not None and name_col < len(cells) else ""
        # 노선은 화살표가 가장 많은 칸 (시간 칸과 한 칸으로 붙어 오는 줄이 있다)
        path_cell = max(cells[1:], key=lambda c: c.count("→"))
        time_text = cells[time_col] if time_col is not None and time_col < len(cells) else ""
        lead, path = _split_route_start(path_cell)
        if time_text == path_cell:
            time_text = lead
        elif lead and not time_text:
            time_text = lead
        path = _repair_times(path)

        # 노선 뒤에 붙은 KTX·SRT 환승 안내는 정류장이 아니다
        extra = ""
        cut = re.search(r"\s*(KTX|SRT|\(R1)", path)
        if cut:
            extra = path[cut.start():].strip()
            path = path[: cut.start()]
        stops = parse_route(path)
        if len(stops) < 2:
            continue

        depart_match = re.search(r"\d{1,2}:\d{2}", time_text)
        timed = [s for s in stops if s["time"]]
        if not timed:
            # 원내순환처럼 정류장에 시각이 없는 노선: 출발 시각만 첫 정류장에 붙인다
            for stop in stops:
                stop["via"] = False
            if depart_match:
                stops[0]["time"] = depart_match.group(0)
            timed = [s for s in stops if s["time"]]
        depart = depart_match.group(0) if depart_match else (timed[0]["time"] if timed else "")

        # 이름: 통근은 '노선 이름', 순환은 '구분' 을 알아보기 쉽게
        day_note = ""
        name = label
        day = re.search(r"\s*(매주\s.*|\S*요일만?\s*운행.*)$", name)
        if day:
            day_note = day.group(1).strip()
            name = name[: day.start()].strip()
        if name in _LABELS:
            name = _LABELS[name]
        elif name in ("출근", "퇴근"):
            name = f"광역 순환 {stops[0]['name']}→{stops[-1]['name']}"
        elif name.startswith("원내"):
            name = "원내 순환 " + name.replace("원내", "").strip(" ()")
        name = name or kind

        notes = [n for n in (day_note, row_note) if n]
        if seats_match:
            notes.append(f"{seats_match.group(1)}인승")
        if qr_col is not None and qr_col < len(cells) and cells[qr_col] and "→" not in cells[qr_col]:
            notes.append(f"QR탑승권 {cells[qr_col]}")
        # '08:20 출발 - 동서울(08:55)' 처럼 시각 칸에 붙은 안내는 따로 보여 준다
        time_extra = time_text if time_text and time_text != depart else ""

        routes.append(
            {
                "group": group,
                "kind": kind,
                "days": days,
                "name": name,
                "stops": stops,
                "depart": depart,
                "arrive": timed[-1]["time"] if timed else "",
                "note": " · ".join(notes),
                # 환승 안내나 시각 칸 안내는 노선도 아래에 한 줄로
                "extra": " ".join(x for x in (time_extra, extra) if x),
            }
        )
    return routes


def fetch_shuttle() -> dict[str, Any]:
    """모든 버스 노선. 학교 홈페이지가 막히면 실패를 알린다."""
    routes: list[dict[str, Any]] = []
    failed: list[str] = []
    for path, kind in PAGES:
        try:
            html = _fetch(BASE + path)
        except Exception:
            failed.append(kind)
            continue
        for block in _TABLE_RE.findall(html):
            routes.extend(_routes_from_table(block, kind))

    return {
        "ok": bool(routes),
        "count": len(routes),
        "routes": routes,
        "failed": failed,
        "source": BASE + PAGES[0][0],
    }


if __name__ == "__main__":
    data = fetch_shuttle()
    print(data["ok"], data["count"], "실패:", data["failed"])
    for r in data["routes"][:4]:
        line = " → ".join(f"{s['name']}{'(' + s['time'] + ')' if s['time'] else ''}" for s in r["stops"])
        print(f"[{r['group']}] {r['name']}: {line}")
