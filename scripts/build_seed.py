"""배포본에 함께 넣을 '씨앗 데이터'를 만든다.

학사일정과 개설강좌는 학기 내내 거의 그대로다.
그런데 지금은 앱을 처음 켠 사람마다 학교 홈페이지를 새로 긁는다.
받아 오는 데 몇 초씩 걸리고, 학교 쪽이 느리면 빈 화면이 뜬다.

미리 받아서 data/ 에 넣어 두면 첫 화면이 네트워크 없이 즉시 뜬다.
그 뒤로는 예약 새로고침이 알아서 최신으로 바꿔 놓는다.

릴리스 빌드 직전에 한 번 돌린다:
    python scripts/build_seed.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"
CALENDAR_SEED = DATA_DIR / "seed_academic_calendar.json"
CATALOG_SEED = DATA_DIR / "seed_course_catalog.json"


def build_calendar(years: list[int]) -> dict:
    import academic_calendar

    out = {}
    for year in years:
        result = academic_calendar.fetch_academic_calendar(year)
        if result.get("ok") and result.get("events"):
            out[str(year)] = {
                "ok": True,
                "year": year,
                "count": result.get("count", 0),
                "events": result["events"],
                "source": result.get("source", ""),
            }
            print(f"  학사일정 {year}: {result.get('count')}건")
        else:
            print(f"  학사일정 {year}: 실패 — {result.get('message', '알 수 없음')}")
    return out


def build_catalog(terms: list[str]) -> dict:
    import timetable_import

    out = {}
    for term in terms:
        for undergraduate in (True, False):
            level = "under" if undergraduate else "grad"
            try:
                result = timetable_import.fetch_dgist_catalog(
                    year_term=term, undergraduate=undergraduate
                )
            except Exception as exc:
                print(f"  개설강좌 {term}/{level}: 실패 — {exc}")
                continue
            if result.get("ok") and result.get("courses"):
                out[f"{term}|{level}"] = result
                print(f"  개설강좌 {term}/{level}: {result.get('count')}과목")
            else:
                print(f"  개설강좌 {term}/{level}: 비어 있음")
    return out


def main() -> int:
    now = datetime.now()
    years = [now.year, now.year + 1] if now.month >= 11 else [now.year]
    # 이번 학기와 다음 학기
    terms = []
    for year in [now.year, now.year + 1]:
        for code in ("CMN17.10", "CMN17.20"):
            terms.append(f"{year}{code}")
    terms = terms[:3]

    DATA_DIR.mkdir(exist_ok=True)

    print("학사일정 받는 중...")
    calendar = build_calendar(years)
    print("개설강좌 받는 중...")
    catalog = build_catalog(terms)

    if not calendar and not catalog:
        print("\n받아 온 것이 없습니다. 씨앗 파일을 건드리지 않았습니다.")
        return 1

    stamp = now.isoformat(timespec="seconds")
    if calendar:
        CALENDAR_SEED.write_text(
            json.dumps({"builtAt": stamp, "years": calendar}, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n{CALENDAR_SEED.relative_to(ROOT)} 저장 ({CALENDAR_SEED.stat().st_size // 1024} KB)")
    if catalog:
        CATALOG_SEED.write_text(
            json.dumps({"builtAt": stamp, "terms": catalog}, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"{CATALOG_SEED.relative_to(ROOT)} 저장 ({CATALOG_SEED.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
