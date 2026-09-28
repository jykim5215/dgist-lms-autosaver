"""화면 문구(한국어)를 뽑아 web/i18n/en.json 과 맞춰 본다.

영어 화면은 코드의 문구를 하나하나 바꾸지 않고, 화면에 그려진 글자를 번역표로 바꿔 보여 준다
(app.js 의 i18n 부분). 이 스크립트는 번역표에 빠진 문구를 찾아 준다.

  python scripts/i18n_extract.py           → 빠진 문구 수와 목록(scripts/i18n_missing.json)
  번역을 채운 뒤 다시 돌리면 0 이 되어야 한다.

뽑는 곳: index.html 의 글자·속성, app.js 의 문자열(주석 제외), web_ui.py 가 화면에 보내는 message.
문자열 속 ${...} 는 {0} {1} … 자리로 바꾼다. HTML 조각이면 태그 사이 글자만 따로 뽑는다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HANGUL = re.compile(r"[가-힣]")
TAG = re.compile(r"<[^>]*>")
ATTR = re.compile(r'(?:placeholder|title|aria-label|data-hint|alt)="([^"]*)"')


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def placeholders(s: str) -> str:
    """`${a} 개 ${b}` → '{0} 개 {1}'. 중첩 중괄호도 센다."""
    out, i, n = [], 0, 0
    while i < len(s):
        if s.startswith("${", i):
            depth, j = 1, i + 2
            while j < len(s) and depth:
                depth += {"{": 1, "}": -1}.get(s[j], 0)
                j += 1
            out.append("{%d}" % n)
            n += 1
            i = j
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def chunks_from_markup(s: str) -> set[str]:
    found = set()
    for attr in ATTR.findall(s):
        if HANGUL.search(attr):
            found.add(norm(attr))
    for part in TAG.split(s):
        part = norm(part.replace("&nbsp;", " "))
        if HANGUL.search(part):
            found.add(part)
    return found


def renumber(s: str) -> str:
    """조각마다 {n} 을 0 부터 다시 센다."""
    counter = iter(range(100))
    return re.sub(r"\{\d+\}", lambda m: "{%d}" % next(counter), s)


def js_strings(src: str) -> set[str]:
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"(?m)^\s*//.*$", "", src)
    src = re.sub(r"(?m)(?<=[;,{}()\s])//[^\n'\"`]*$", "", src)
    found = set()
    for quote, body in re.findall(r"""(["'`])((?:\\.|(?!\1)[^\\])*?)\1""", src):
        if not HANGUL.search(body):
            continue
        body = body.replace("\\n", "\n").replace("\\'", "'").replace('\\"', '"')
        text = placeholders(body) if quote == "`" else body
        for piece in chunks_from_markup(text) if "<" in text else {norm(text)}:
            for line in piece.split("\n"):
                line = renumber(norm(line))
                if HANGUL.search(line):
                    found.add(line)
    # ${ 조건 ? "메일 없음" : "…" } 처럼 틀 안에 숨은 따옴표 문구도 따로 뽑는다
    for quote, body in re.findall(r"""(["'])((?:\\.|(?!\1)[^\\\n])*?)\1""", src):
        if HANGUL.search(body) and "${" not in body and "`" not in body:
            body = body.replace("\\n", "\n")
            for piece in chunks_from_markup(body) if "<" in body else {norm(body)}:
                for line in piece.split("\n"):
                    line = norm(line)
                    if HANGUL.search(line):
                        found.add(line)
    return found


def is_code(s: str) -> bool:
    """틀을 잘못 잘라 생긴 코드 조각 (화면에 나오지 않는다)"""
    return bool(re.search(r"\$\{|=>|\);|\bconst\b|\breturn\b|\[/|escapeHtml|iconHtml|\]\s*,|`", s))


def html_strings(src: str) -> set[str]:
    src = re.sub(r"<!--[\s\S]*?-->", "", src)
    src = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", src)
    return chunks_from_markup(src)


def py_messages(src: str) -> set[str]:
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"(?m)#.*$", "", src)
    found = set()
    for quote, body in re.findall(r"""(["'])((?:\\.|(?!\1)[^\\])*?)\1""", src):
        if HANGUL.search(body):
            text = re.sub(r"\{[^{}]*\}", "{}", body)
            counter = iter(range(100))
            text = re.sub(r"\{\}", lambda m: "{%d}" % next(counter), text)
            found.add(norm(text))
    return found


def collect() -> list[str]:
    web = ROOT / "web"
    strings = set()
    strings |= html_strings((web / "index.html").read_text(encoding="utf-8"))
    strings |= js_strings((web / "app.js").read_text(encoding="utf-8"))
    strings |= py_messages((ROOT / "web_ui.py").read_text(encoding="utf-8"))
    # 로그·정규식·경로처럼 화면에 안 나오는 것은 뺀다
    drop = re.compile(r"^[\[\(]?[가-힣]+\]$|\\[dswb]|^\^|[가-힣]\|[가-힣]|^\s*$")
    return sorted(s for s in strings if not drop.search(s) and not is_code(s) and len(s) <= 300)


# 일부러 번역표에 넣지 않는 것
#   - 요일 괄호: app.js 의 날짜 규칙(I18N_DATE_MAP)이 바꾼다
#   - '{0}을 {1}', '[{0}] {1}': 너무 넓어 사용자 글(메일 제목)을 망가뜨린다
#   - 파일 이름·캘린더(.ics) 내용·정규식 조각: 화면 문구가 아니다
IGNORE = {
    "(월)", "(화)", "(수)", "(목)", "(금)", "(토)", "(일)",
    "{0}을 {1}", "[{0}] {1}", "가",
    "-비밀번호포함", "붕어빵-설정-{0}{1}.json",
    "DESCRIPTION:{0} 마감 하루 전", "X-WR-CALNAME:DGIST 과제 마감",
    "<[^>]*>|\\(today\\)|\\[today\\]|오늘",
    'title="LMS 제출 페이지 열기">제출하러 가기',
}


if __name__ == "__main__":
    all_strings = [s for s in collect() if s not in IGNORE]
    table_path = ROOT / "web" / "i18n" / "en.json"
    table = json.loads(table_path.read_text(encoding="utf-8")) if table_path.exists() else {}
    missing = [s for s in all_strings if s not in table]
    out = ROOT / "scripts" / "i18n_missing.json"
    out.write_text(json.dumps(missing, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"문구 {len(all_strings)}개, 번역표 {len(table)}개, 빠진 것 {len(missing)}개 → {out.name}")
