"""강의·자료를 '몇 학년 무슨 학기' 로 갈라 주는 규칙.

두 가지 단서를 쓴다. 둘 다 이미 데이터 안에 들어 있어서 따로 받아올 게 없다.

학기
    LMS 가 주는 과목 이름에 학년도·학기가 붙어 있다.
        '일반화학Ⅱ (General Chemistry II )_02[ 2026_2학기 ]'
                                              ^^^^^^^^^^^

학년
    DGIST 과목번호는 첫 숫자가 학년이다. (개설강좌 180과목으로 확인:
    1xx 75개, 2xx 41개, 3xx 36개, 4xx 28개)
        BE101a → 1학년,  HSS221 → 2학년,  BS119 → 1학년
    과목번호는 LMS 자료에 없으므로, 과목 이름을 개설강좌 목록과 맞춰 찾는다.
"""
from __future__ import annotations

import re
from typing import Any

# '[ 2026_2학기 ]' 또는 '[2026_1학기]'
_TERM_RE = re.compile(r"\[\s*(\d{4})\s*[_\-/ ]\s*([1-4])\s*학기\s*\]")
# 'BE101a', 'HSS221', 'BS119' → 앞의 영문 + 첫 숫자
_COURSE_NO_RE = re.compile(r"^([A-Za-z]{2,6})\s*(\d)")

GRAD_LEVEL = 5  # 5xx 이상은 대학원 과목


def parse_term(label: Any) -> dict[str, Any]:
    """과목 이름에서 학년도·학기를 뽑는다. 못 찾으면 빈 값."""
    match = _TERM_RE.search(str(label or ""))
    if not match:
        return {"year": None, "term": None, "termLabel": ""}
    year, term = int(match.group(1)), int(match.group(2))
    return {"year": year, "term": term, "termLabel": f"{year}학년도 {term}학기"}


def level_from_course_no(course_no: Any) -> int | None:
    """과목번호에서 학년. 대학원 과목이면 GRAD_LEVEL."""
    match = _COURSE_NO_RE.match(str(course_no or "").strip())
    if not match:
        return None
    digit = int(match.group(2))
    if digit <= 0:
        return None
    return min(digit, GRAD_LEVEL)


def level_label(level: int | None) -> str:
    if level is None:
        return ""
    return "대학원" if level >= GRAD_LEVEL else f"{level}학년"


def _norm(title: Any) -> str:
    """과목 이름 맞추기용 정규화.

    LMS 이름은 '일반화학Ⅱ  (General Chemistry II )_02[...]' 처럼 지저분하다.
    괄호·분반·학기 표시를 떼고 공백을 줄여야 개설강좌 이름과 맞는다.
    """
    text = str(title or "")
    text = _TERM_RE.sub(" ", text)
    text = re.sub(r"\([^)]*\)", " ", text)      # 영문 병기 제거
    text = re.sub(r"_\d+\s*$", " ", text)        # 끝의 분반 번호
    text = re.sub(r"[\s ]+", "", text)      # 공백 전부 제거
    return text.strip().lower()


def build_level_index(courses: list[dict[str, Any]]) -> dict[str, int]:
    """개설강좌 목록 → {정규화한 과목이름: 학년}."""
    index: dict[str, int] = {}
    for course in courses or []:
        level = level_from_course_no(course.get("courseNo"))
        if level is None:
            continue
        key = _norm(course.get("title"))
        if key and key not in index:
            index[key] = level
        # 영문 이름으로도 찾을 수 있게
        key_en = _norm(course.get("titleEn"))
        if key_en and key_en not in index:
            index[key_en] = level
    return index


def guess_level(course_label: Any, index: dict[str, int]) -> int | None:
    """LMS 과목 이름을 개설강좌 목록과 맞춰 학년을 찾는다."""
    if not index:
        return None
    raw = str(course_label or "")

    # 이름 안에 과목번호가 그대로 들어 있는 경우가 가끔 있다
    inline = re.search(r"\b([A-Za-z]{2,6}\d{3}[a-z]?)\b", raw)
    if inline:
        level = level_from_course_no(inline.group(1))
        if level:
            return level

    key = _norm(raw)
    if key in index:
        return index[key]
    # 영문 병기만 남은 경우: 괄호 안쪽으로도 시도
    inside = re.search(r"\(([^)]*)\)", raw)
    if inside:
        key2 = _norm(inside.group(1))
        if key2 in index:
            return index[key2]
    return None


# ===== 강의계획서(실라버스) =====
# 파일 이름에 들어가는 말. 실제 자료에서 확인한 것:
#   'AE R&W (9) syllabus Autumn 2026.docx'
_SYLLABUS_WORDS = ("syllabus", "강의계획", "수업계획", "교수계획", "course outline")


def is_syllabus(name: Any) -> bool:
    """이 파일이 강의계획서인지."""
    text = str(name or "").lower()
    return any(word in text for word in _SYLLABUS_WORDS)


def describe(course_label: Any, index: dict[str, int] | None = None) -> dict[str, Any]:
    """과목 이름 하나를 {year, term, termLabel, level, levelLabel} 로."""
    info = parse_term(course_label)
    level = guess_level(course_label, index or {})
    info["level"] = level
    info["levelLabel"] = level_label(level)
    return info
