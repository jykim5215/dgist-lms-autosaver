"""DGIST 공식 홈페이지 공지 가져오기.

로그인이 필요 없는 게시판만 다룬다. 서버에서 HTML 표로 그려 주므로
Playwright 없이 받아서 읽으면 된다.

확인한 것(직접 열어 봄):
- 일반공지(_066), 보도자료(_080), 채용정보(_252) : 로그인 없이 열림
- 학사공지(_067) : 학교가 '접근 권한이 없습니다'로 막아 둠 → 포탈 로그인이 있어야 함

행 구조:
    <tr>
      <td class="subject"><button onclick="fn_search_detail('B000...')">
          <strong class="bbs-subject-txt">제목</strong></button></td>
      <td class="writer">작성자</td><td class="hit">조회수</td><td class="regDate">등록일</td>
    </tr>
"""
from __future__ import annotations

import re
import time
import urllib.request
from typing import Any

BASE = "https://www.dgist.ac.kr"

# 로그인 없이 볼 수 있는 게시판만 올린다.
BOARDS: dict[str, dict[str, str]] = {
    "general": {"code": "BBSMSTR_000000000066", "name": "일반공지"},
    "press": {"code": "BBSMSTR_000000000080", "name": "보도자료"},
    "jobs": {"code": "BBSMSTR_000000000252", "name": "채용정보"},
}

_TBODY_RE = re.compile(r"<tbody.*?</tbody>", re.S)
_ROW_RE = re.compile(r"<tr\b.*?</tr>", re.S)
_TITLE_RE = re.compile(r'<strong class="bbs-subject-txt">(.*?)</strong>', re.S)
_DETAIL_RE = re.compile(r"fn_search_detail\('([^']+)'\)")
_CELL_RE = re.compile(r'<td[^>]*class="([^"]*)"[^>]*>(.*?)</td>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


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
    raise last if last else RuntimeError("공지를 받지 못했습니다.")


def fetch_board(key: str, limit: int = 20) -> dict[str, Any]:
    """게시판 하나를 읽어 글 목록을 돌려준다."""
    board = BOARDS.get(key)
    if not board:
        return {"ok": False, "items": [], "message": f"모르는 게시판입니다: {key}"}

    url = f"{BASE}/bbs/{board['code']}/list.do"
    try:
        html = _fetch(url)
    except Exception as exc:
        return {"ok": False, "board": board["name"], "items": [], "message": f"공지를 받지 못했습니다: {exc}"}

    if "접근 권한이" in html:
        return {
            "ok": False,
            "board": board["name"],
            "items": [],
            "message": "학교가 로그인 없이 볼 수 없도록 막아 둔 게시판입니다.",
        }

    body = _TBODY_RE.search(html)
    if not body:
        return {"ok": False, "board": board["name"], "items": [], "message": "글 목록을 찾지 못했습니다."}

    items: list[dict[str, Any]] = []
    for row in _ROW_RE.findall(body.group(0)):
        title_m = _TITLE_RE.search(row)
        if not title_m:
            continue
        title = _clean(title_m.group(1))
        if not title:
            continue
        cells = {cls.strip(): _clean(val) for cls, val in _CELL_RE.findall(row)}
        detail = _DETAIL_RE.search(row)
        items.append(
            {
                "id": detail.group(1) if detail else title,
                "title": title,
                "writer": cells.get("writer", ""),
                "date": cells.get("regDate", ""),
                "hit": cells.get("hit", ""),
                # 상단 고정 공지는 목록에서 위로 올라와 있다
                "pinned": 'class="notice"' in row,
                "board": board["name"],
                "url": f"{BASE}/bbs/{board['code']}/list.do",
            }
        )
        if len(items) >= limit:
            break

    return {"ok": True, "board": board["name"], "count": len(items), "items": items}


def fetch_all(limit: int = 12) -> dict[str, Any]:
    """볼 수 있는 게시판을 모두 읽어 한 목록으로 합친다."""
    items: list[dict[str, Any]] = []
    failed: list[str] = []
    for key, board in BOARDS.items():
        result = fetch_board(key, limit)
        if result.get("ok"):
            items.extend(result["items"])
        else:
            failed.append(board["name"])
    # 고정 공지를 위로, 그 다음 최신순
    items.sort(key=lambda x: (not x["pinned"], x.get("date", "")), reverse=False)
    items.sort(key=lambda x: (x["pinned"], x.get("date", "")), reverse=True)
    return {"ok": bool(items), "count": len(items), "items": items, "failed": failed}


if __name__ == "__main__":
    result = fetch_all()
    print(result["ok"], result["count"], "실패:", result["failed"])
    for item in result["items"][:6]:
        print(" ", item["date"], "|", item["board"], "|", item["title"][:50])
