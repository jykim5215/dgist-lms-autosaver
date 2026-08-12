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
    text = _TAG_RE.sub(" ", html)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        text = text.replace(a, b)
    return " ".join(text.split())


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
            name = m.group(1).strip(" \t-–—")
            if name:
                stops.append({"name": name, "time": m.group(2), "via": False})
        else:
            # 시각이 없는 칸: '성서IC경유'처럼 거쳐만 가는 곳
            # 괄호 안 안내문(KTX 시간 등)은 너무 길어 노선도에 넣지 않는다
            if len(piece) <= 20 and not piece.startswith("("):
                stops.append({"name": piece, "time": "", "via": True})
    return stops


def _routes_from_table(block: str, kind: str) -> list[dict[str, Any]]:
    caption = _clean(_CAPTION_RE.search(block).group(1)) if _CAPTION_RE.search(block) else ""
    # '출근버스(평일 운행) 45인승 - 연번, ...' → '출근버스'
    title = re.split(r"[(\-]", caption)[0].strip() or kind

    routes = []
    for row in _ROW_RE.findall(block):
        cells = [_clean(c) for c in _CELL_RE.findall(row)]
        if len(cells) < 3:
            continue
        # 연번 / 노선 이름 / 노선[시간] / 차량
        if not cells[0].isdigit():
            continue
        name, path = cells[1], cells[2]
        # 노선 뒤에 붙은 KTX·SRT 환승 안내는 정류장이 아니다.
        #   ... DGIST[08:45] KTX-산천(75호) 서울[06:03]→대전[07:14]
        # 여기서 끊지 않으면 서울·대전이 정류장으로 딸려 온다.
        extra = ""
        cut = re.search(r"\s*(KTX|SRT|\(R1)", path)
        if cut:
            extra = path[cut.start():].strip()
            path = path[: cut.start()]
        stops = parse_route(path)
        if len(stops) < 2:
            continue
        timed = [s for s in stops if s["time"]]
        routes.append(
            {
                "group": title,
                "kind": kind,
                "name": name,
                "stops": stops,
                "depart": timed[0]["time"] if timed else "",
                "arrive": timed[-1]["time"] if timed else "",
                "note": cells[3] if len(cells) > 3 else "",
                # 환승 안내는 따로 담아 노선도 아래에 한 줄로 보여 준다
                "extra": extra,
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
