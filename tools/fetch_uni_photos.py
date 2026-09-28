"""대학 대표 사진을 위키백과에서 받아 앱 안에 넣어 둔다.

왜 미리 받아 두는가
  화면에서 바로 외부 주소를 불러오면 인터넷이 없을 때 빈 칸이 되고,
  어느 대학을 들여다보는지도 바깥에 알려지게 된다. 한 번 받아 두면
  그 뒤로는 앱 안에서만 읽는다.

라이선스
  위키백과 문서 대표 이미지는 대부분 CC BY-SA 또는 퍼블릭 도메인이다.
  출처(작성자·라이선스)를 같이 적어 두고 화면에도 표시한다.

쓰는 법:  python tools/fetch_uni_photos.py
"""

from __future__ import annotations

import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# 윈도우 콘솔이 cp949 라 대학 이름의 en-dash 에서 죽는다
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "web" / "img" / "uni"
META_PATH = ROOT / "uni_photos.json"

UA = "bungeoppang-dgist-autosaver/1.0 (personal student app; contact: jykim5215@gmail.com)"
CTX = ssl.create_default_context()

# fglp.py 의 이름 → 위키백과 문서 제목
TITLES = {
    "Harvard University": "Harvard University",
    "Stanford University": "Stanford University",
    "Johns Hopkins University": "Johns Hopkins University",
    "University of Virginia": "University of Virginia",
    "Boston University": "Boston University",
    "Purdue University": "Purdue University",
    "UC Berkeley": "University of California, Berkeley",
    "UCLA": "University of California, Los Angeles",
    "University of Wisconsin–Madison": "University of Wisconsin–Madison",
    "Arizona State University": "Arizona State University",
    "University of Cambridge": "University of Cambridge",
    "Maastricht University": "Maastricht University",
    "HKUST": "Hong Kong University of Science and Technology",
    "Chinese University of Hong Kong": "Chinese University of Hong Kong",
    "Nanyang Technological University": "Nanyang Technological University",
    "Hokkaido University": "Hokkaido University",
    "INSA Lyon": "Institut national des sciences appliquées de Lyon",
    "Aalto University": "Aalto University",
    "University of Innsbruck": "University of Innsbruck",
    "Ulm University": "University of Ulm",
    "Koç University": "Koç University",
    "University of Groningen": "University of Groningen",
    "Universiti Malaya": "University of Malaya",
    "National Yang Ming Chiao Tung University": "National Yang Ming Chiao Tung University",
    "Osaka University": "Osaka University",
    "Dalian University of Technology": "Dalian University of Technology",
    # 2027 입학 안내서(2026.6)에서 새로 들어온 곳
    "UC Irvine": "University of California, Irvine",
    "University of British Columbia": "University of British Columbia",
    "Utrecht University": "Utrecht University",
    "RWTH Aachen University": "RWTH Aachen University",
    "ESME": "ESME Sudria",
    "National Taiwan University": "National Taiwan University",
    "Waseda University": "Waseda University",
    "University of Calgary": "University of Calgary",
    "Dublin City University": "Dublin City University",
    "RMIT University": "RMIT University",
    "Grenoble INP - UGA": "Grenoble Institute of Technology",
    "Polytechnic University of Valencia": "Polytechnic University of Valencia",
    "TU Wien": "TU Wien",
}


# 자동으로 고른 사진이 엉뚱했던 곳 (2026-09-22 눈으로 확인). 다시 받지 않는다.
SKIP = {
    "esme": "ESME 가 아니라 같은 그룹(IONIS) 의 릴 캠퍼스 사진",
    "national-taiwan-university": "캠퍼스가 아니라 자전거 더미 사진",
    "waseda-university": "항공 지도",
    "dublin-city-university": "도로 지도",
    "grenoble-inp-uga": "사진이 아니라 로고",
}


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25, context=CTX) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def commons_photo(name: str) -> tuple[str, str] | None:
    """커먼스에서 캠퍼스 사진을 찾는다. (썸네일 주소, 파일명)

    문서 대표 이미지는 대개 학교 문장(seal)이라 '대표 사진'이라 하기 어렵다.
    사진처럼 보이는 것(jpg)을 먼저 고른다.
    """
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{name} campus",
            "gsrnamespace": "6",
            "gsrlimit": "12",
            "prop": "imageinfo",
            "iiprop": "url|size",
            "iiurlwidth": "560",
            "format": "json",
        }
    )
    try:
        pages = get_json(url).get("query", {}).get("pages", {})
    except Exception:
        return None
    best = None
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        thumb = info.get("thumburl")
        title = page.get("title", "")
        if not thumb:
            continue
        low = title.lower()
        # 문장·지도·도표는 사진이 아니다
        if any(x in low for x in ("seal", "logo", "coat of arms", "map", "svg", "diagram", "chart")):
            continue
        if not low.endswith((".jpg", ".jpeg")):
            continue
        best = (thumb, title.replace("File:", ""))
        break
    return best


def page_image(title: str) -> tuple[str, str] | None:
    """(썸네일 주소, 원본 파일명) 또는 None."""
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "query",
            "titles": title,
            "prop": "pageimages",
            "piprop": "thumbnail|name",
            "pithumbsize": "560",
            "format": "json",
            "redirects": "1",
        }
    )
    pages = get_json(url).get("query", {}).get("pages", {})
    for page in pages.values():
        thumb = page.get("thumbnail", {}).get("source")
        if thumb:
            return thumb, page.get("pageimage", "")
    return None


def image_credit(file_name: str) -> dict:
    """이미지의 작성자와 라이선스를 알아 온다."""
    if not file_name:
        return {}
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "query",
            "titles": f"File:{file_name}",
            "prop": "imageinfo",
            "iiprop": "extmetadata",
            "format": "json",
        }
    )
    try:
        pages = get_json(url).get("query", {}).get("pages", {})
        for page in pages.values():
            meta = (page.get("imageinfo") or [{}])[0].get("extmetadata", {})
            strip = lambda s: re.sub(r"<[^>]+>", "", s or "").strip()
            return {
                "author": strip(meta.get("Artist", {}).get("value"))[:120],
                "license": strip(meta.get("LicenseShortName", {}).get("value"))[:60],
                "source": f"https://commons.wikimedia.org/wiki/File:{urllib.parse.quote(file_name)}",
            }
    except Exception:
        pass
    return {}


def download(url: str, dest: Path) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40, context=CTX) as resp:
            data = resp.read()
        if len(data) < 800:
            return False
        dest.write_bytes(data)
        return True
    except Exception as exc:
        print("   내려받기 실패:", exc)
        return False


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta: dict[str, dict] = {}
    if META_PATH.exists():
        meta = json.loads(META_PATH.read_text(encoding="utf-8"))

    for name, title in TITLES.items():
        key = slug(name)
        if key in SKIP:
            print("건너뜀 (알맞은 사진 없음):", name, "-", SKIP[key])
            continue
        if key in meta and (OUT_DIR / meta[key]["file"]).exists():
            print("건너뜀 (이미 있음):", name)
            continue
        print("받는 중:", name)
        try:
            hit = commons_photo(name) or page_image(title)
        except Exception as exc:
            print("   조회 실패:", exc)
            continue
        if not hit:
            print("   사진 없음")
            continue
        thumb, file_name = hit
        ext = ".jpg" if ".jpg" in thumb.lower() or ".jpeg" in thumb.lower() else ".png"
        dest = OUT_DIR / f"{key}{ext}"
        if not download(thumb, dest):
            continue
        credit = image_credit(file_name)
        meta[key] = {
            "file": dest.name,
            "title": title,
            **credit,
        }
        print(f"   저장 {dest.name} ({dest.stat().st_size // 1024}KB) · {credit.get('license', '?')}")
        time.sleep(0.4)  # 위키백과에 부담 주지 않게

    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum((OUT_DIR / m["file"]).stat().st_size for m in meta.values() if (OUT_DIR / m["file"]).exists())
    print(f"\n끝. {len(meta)}곳 · 모두 {total // 1024}KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
