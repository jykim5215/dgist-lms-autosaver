"""DGIST 조직도(주소록) 검색.

웹메일의 '주소찾기 → 조직도'에는 교직원·학생 1,200여 명이 들어 있는데,
그 화면은 포탈 SSO 로그인을 거쳐야만 열린다.
사용자가 포탈 비밀번호를 앱에 맡기지 않기로 했으므로, 로그인해서 매번
긁어 오는 대신 **한 번 가져온 목록을 파일로 두고 그 안에서 찾는다.**

- 목록 파일: <데이터 폴더>/directory.json
- 갱신: 사용자가 웹메일에서 내보내 이 파일을 바꿔 주거나,
  앱의 '조직도 가져오기'로 다시 넣는다.

검색은 웹메일과 비슷하게 이름·이메일·부서 어디에 걸려도 나오게 하고,
한글 초성('ㄱㄷㅈ' → 김동준)과 영문 이름 일부도 받는다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# 한글 음절 → 초성
_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_HANGUL_BASE = 0xAC00
_HANGUL_LAST = 0xD7A3


def initials(text: str) -> str:
    """'김동준' → 'ㄱㄷㅈ'. 한글이 아니면 그대로 둔다."""
    out = []
    for ch in text or "":
        code = ord(ch)
        if _HANGUL_BASE <= code <= _HANGUL_LAST:
            out.append(_CHO[(code - _HANGUL_BASE) // 588])
        else:
            out.append(ch)
    return "".join(out)


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def load_directory(path: Path) -> list[dict[str, Any]]:
    """저장된 조직도. 없으면 빈 목록."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        data = data.get("people") or data.get("entries") or []
    return [p for p in data if isinstance(p, dict) and p.get("email")]


def save_directory(path: Path, people: list[dict[str, Any]]) -> dict[str, Any]:
    """조직도를 저장한다. 이메일 기준으로 중복을 없앤다."""
    seen: dict[str, dict[str, Any]] = {}
    for p in people or []:
        email = str(p.get("email", "")).strip().lower()
        if not email or "@" not in email:
            continue
        seen[email] = {
            "name": str(p.get("name", "")).strip(),
            "email": email,
            "dept": str(p.get("dept", "")).strip(),
            "title": str(p.get("title", "")).strip(),
            "role": str(p.get("role", "")).strip(),
        }
    people = sorted(seen.values(), key=lambda x: (x["name"], x["email"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"count": len(people), "people": people}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return {"ok": True, "count": len(people)}


def search_directory(people: list[dict[str, Any]], query: str, limit: int = 8) -> list[dict[str, Any]]:
    """이름·이메일·부서로 찾는다. 한글 초성도 받는다.

    앞에서부터 맞는 것을 먼저 보여 준다. (webmail도 그렇게 정렬한다)
    """
    q = _norm(query)
    if not q:
        return []
    # 초성 검색은 자음만 쳤을 때만. '김동준'을 초성으로도 풀면
    # 초성이 같은 다른 사람(권동재, 김대진…)까지 딸려 나온다.
    q_is_initials = bool(q) and all(ch in _CHO for ch in q)

    scored: list[tuple[int, dict[str, Any]]] = []
    for p in people:
        name = _norm(p.get("name", ""))
        email = _norm(p.get("email", ""))
        dept = _norm(p.get("dept", ""))
        local = email.split("@", 1)[0]

        score = None
        if name.startswith(q) or local.startswith(q):
            score = 0
        elif q in name or q in email:
            score = 1
        elif q_is_initials and initials(name).startswith(q):
            # 'ㄱㄷㅈ' 같은 초성만 친 경우
            score = 2
        elif q in dept:
            score = 3

        if score is not None:
            scored.append((score, p))

    scored.sort(key=lambda x: (x[0], x[1].get("name", "")))
    return [p for _, p in scored[:limit]]
