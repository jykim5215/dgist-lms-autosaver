"""FGLP(Freshmen Global Leadership Program) 파견 대학 정보.

출처: DGIST 2026 UNDERGRADUATE ADMISSIONS GUIDE FOR INTERNATIONAL STUDENTS
      (학교가 낸 공식 안내서, 2025년 7월 배포) 12~15쪽.
      대학별 어학 기준과 GPA 기준까지 그 문서에 그대로 실려 있다.

기초학부 홈페이지(https://www.dgist.ac.kr/college/sub05_04.do)는 2026년 8월
현재까지도 '2023년 기준 6개 대학, 1인당 최대 1,000만원'으로 남아 있어 최신이
아니다. 둘이 어긋날 때는 더 최근 문서인 입학 안내서를 따른다.

정원(대학별 선발 인원)은 두 문서 어디에도 없다. 없는 숫자는 지어내지 않는다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

VERIFIED_ON = "2026-08-13"

SOURCE_LABEL = "DGIST 2026 학부 입학안내서 (2025.7)"
SOURCE_URL = "https://kecla.org/uploads/board/attach1/20250723134701.pdf"
OFFICIAL_URL = "https://www.dgist.ac.kr/college/sub05_04.do"
CONTACT = "국제협력팀 053-785-1163 / amatista@dgist.ac.kr"

# 공통 지원 자격: DGIST 학점 4.3 만점에 3.23 이상
GPA_REQUIREMENT = "DGIST 학점 3.23 / 4.3 이상"

# (이름, 국가, 도시, 위도, 경도, 어학 기준)
_FGLP = [
    ("Harvard University", "미국", "케임브리지(MA)", 42.377, -71.117, "TOEFL iBT 100 · IELTS 7.0"),
    ("Stanford University", "미국", "스탠퍼드", 37.428, -122.169, "TOEFL iBT 100 · IELTS 7.0"),
    ("Johns Hopkins University", "미국", "볼티모어", 39.329, -76.620, "TOEFL iBT 100 · IELTS 7.0"),
    ("University of Virginia", "미국", "샬러츠빌", 38.033, -78.508, "TOEFL iBT 90 · IELTS 7.0"),
    ("Boston University", "미국", "보스턴", 42.350, -71.105, "TOEFL iBT 84 · IELTS 7.0"),
    ("Purdue University", "미국", "웨스트라피엣", 40.425, -86.921, "TOEFL iBT 88 · IELTS 6.5"),
    ("UC Berkeley", "미국", "버클리", 37.872, -122.259, "TOEIC 800 · TOEFL iBT 80 · IELTS 6.5"),
    ("UCLA", "미국", "로스앤젤레스", 34.069, -118.445, "TOEIC 800 · TOEFL iBT 80 · IELTS 6.5"),
    ("University of Wisconsin–Madison", "미국", "매디슨", 43.077, -89.412, "TOEIC 800 · TOEFL iBT 80 · IELTS 6.5"),
    ("Arizona State University", "미국", "템피", 33.424, -111.928, "TOEIC 800 · TOEFL iBT 80 · IELTS 6.5"),
    ("University of Cambridge", "영국", "케임브리지", 52.204, 0.119, "TOEFL iBT 92 · IELTS 6.5"),
    ("Maastricht University", "네덜란드", "마스트리흐트", 50.848, 5.687, "TOEFL iBT 90 · IELTS 6.5"),
    ("HKUST", "홍콩", "칭수이완", 22.337, 114.263, "TOEFL iBT 90 · IELTS 6.0"),
    ("Chinese University of Hong Kong", "홍콩", "샤틴", 22.420, 114.207, "TOEFL iBT 71 · IELTS 6.0"),
    ("Nanyang Technological University", "싱가포르", "싱가포르", 1.348, 103.683, "TOEFL iBT 90 · IELTS 6.0"),
    ("Hokkaido University", "일본", "삿포로", 43.077, 141.340, "TOEIC 800 · TOEFL iBT 80 · IELTS 6.5"),
]

# 학점교류(Credit Exchange). 안내서에 '10개국 20개교'라 적혀 있고 그중 10곳만
# 이름이 나와 있다. 나머지 10곳은 문서에 없어 넣지 않았다.
_EXCHANGE = [
    ("INSA Lyon", "프랑스", "리옹", 45.783, 4.879),
    ("Aalto University", "핀란드", "에스포", 60.187, 24.828),
    ("University of Innsbruck", "오스트리아", "인스브루크", 47.264, 11.384),
    ("Ulm University", "독일", "울름", 48.422, 9.956),
    ("Koç University", "튀르키예", "이스탄불", 41.204, 29.061),
    ("University of Groningen", "네덜란드", "흐로닝언", 53.219, 6.562),
    ("Universiti Malaya", "말레이시아", "쿠알라룸푸르", 3.121, 101.654),
    ("National Yang Ming Chiao Tung University", "대만", "신주", 24.787, 120.997),
    ("Osaka University", "일본", "스이타", 34.822, 135.524),
    ("Dalian University of Technology", "중국", "다롄", 38.881, 121.529),
]


def _load_photos() -> dict:
    """tools/fetch_uni_photos.py 가 받아 둔 사진 정보.

    앱 안에 넣어 두었으므로 인터넷이 없어도 보이고, 어느 대학을 들여다보는지
    바깥에 알려지지도 않는다. 라이선스 표기는 화면에 같이 띄운다.
    """
    path = Path(__file__).resolve().parent / "uni_photos.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def get_fglp() -> dict:
    photos = _load_photos()

    def photo_of(name: str) -> dict:
        meta = photos.get(_slug(name))
        if not meta:
            return {}
        return {
            "photo": f"/img/uni/{meta['file']}",
            "photoBy": meta.get("author", ""),
            "photoLicense": meta.get("license", ""),
            "photoSource": meta.get("source", ""),
        }

    schools = [
        {
            "name": name,
            "country": country,
            "city": city,
            "lat": lat,
            "lon": lon,
            "kind": "fglp",
            "language": lang,
            **photo_of(name),
        }
        for (name, country, city, lat, lon, lang) in _FGLP
    ] + [
        {
            "name": name,
            "country": country,
            "city": city,
            "lat": lat,
            "lon": lon,
            "kind": "exchange",
            "language": "",
            **photo_of(name),
        }
        for (name, country, city, lat, lon) in _EXCHANGE
    ]

    return {
        "ok": True,
        "verifiedOn": VERIFIED_ON,
        "sourceLabel": SOURCE_LABEL,
        "sourceUrl": SOURCE_URL,
        "officialUrl": OFFICIAL_URL,
        "contact": CONTACT,
        "schools": schools,
        "program": {
            "name": "FGLP (Freshmen Global Leadership Program)",
            "summary": "여름방학에 해외 유수 대학의 정규 수업을 듣고 오는 기초학부 프로그램.",
            "target": "1·2학년(4학기 이내) 재학생",
            "gpa": GPA_REQUIREMENT,
            "period": "하계 방학 중",
            "support": "한 학기 최소 이수학점까지 수업료·기숙사비 전액 지원",
            "requirement": "대학마다 어학 기준이 다릅니다 (아래 참고)",
            "contact": CONTACT,
            "count": len(_FGLP),
        },
        "exchange": {
            "name": "학점교류 (Credit Exchange Program)",
            "summary": "한 학기~1년 동안 해외 대학에서 공부하고 학점을 옮겨 옵니다.",
            "support": "기간에 따라 150만~300만원 지원",
            "scale": "10개국 20개교 (안내서에 이름이 나온 10곳만 지도에 표시)",
        },
        "notes": [
            {
                "level": "info",
                "text": f"{SOURCE_LABEL} 기준입니다. 파견 대학 {len(_FGLP)}곳과 대학별 어학 기준이 이 문서에 실려 있습니다.",
            },
            {
                "level": "info",
                "text": f"공통 지원 자격: {GPA_REQUIREMENT}. 1·2학년(4학기 이내) 재학생.",
            },
            {
                "level": "warn",
                "text": "기초학부 홈페이지는 아직 2023년 기준(6개 대학·1인당 1,000만원)으로 남아 있어 서로 다릅니다.",
            },
            {
                "level": "warn",
                "text": "대학별 정원(선발 인원)은 두 문서 어디에도 없습니다. 지원 전에 국제협력팀에 확인하세요.",
            },
        ],
    }
