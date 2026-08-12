"""FGLP(Freshmen Global Leadership Program) 파견 대학 정보.

출처와 기준 연도를 함께 들고 다닌다. 학교 공식 페이지(기초학부 > 글로벌 프로그램)는
2026년 8월 현재까지도 '2023년 기준 6개 대학'으로 적혀 있고, 그 뒤 늘어난 학교는
학내 신문(DGIST DNA) 보도로만 확인된다. 화면에서 둘을 구분해 보여 주려고
대학마다 source 를 달아 둔다. 잘못된 정보를 확정처럼 보이게 두는 게 제일 나쁘다.

정원(선발인원)은 어느 공개 문서에도 대학별로 나와 있지 않다. 없는 숫자를 지어내지
않고, 확인된 범위(전체 규모·자격·지원 내용)만 싣는다.
"""

from __future__ import annotations

# 마지막으로 사람이 직접 확인한 날. 화면에 같이 띄운다.
VERIFIED_ON = "2026-08-13"

OFFICIAL_URL = "https://www.dgist.ac.kr/college/sub05_04.do"
CONTACT = "국제협력팀 053-785-1163 / amatista@dgist.ac.kr"

# source
#   official : 학교 공식 페이지에 이름이 적혀 있는 대학 (2023년 기준)
#   press    : 학내 신문 보도로만 확인된 대학 (2024년 추가분)
_FGLP = [
    # --- 공식 페이지에 실린 6곳 (2023년 기준) ---
    ("UC Berkeley", "미국", "버클리", 37.872, -122.259, 2023, "official"),
    ("UCLA", "미국", "로스앤젤레스", 34.069, -118.445, 2023, "official"),
    ("Stanford University", "미국", "스탠퍼드", 37.428, -122.169, 2023, "official"),
    ("Harvard University", "미국", "케임브리지(MA)", 42.377, -71.117, 2023, "official"),
    ("University of Wisconsin–Madison", "미국", "매디슨", 43.077, -89.412, 2023, "official"),
    ("Boston University", "미국", "보스턴", 42.350, -71.105, 2023, "official"),
    # --- 2024학년도에 더해진 8곳 (학내 신문 보도) ---
    ("Purdue University", "미국", "웨스트라피엣", 40.425, -86.921, 2024, "press"),
    ("University of Virginia", "미국", "샬러츠빌", 38.033, -78.508, 2024, "press"),
    ("University of Washington", "미국", "시애틀", 47.655, -122.308, 2024, "press"),
    ("Johns Hopkins University", "미국", "볼티모어", 39.329, -76.620, 2024, "press"),
    ("University of Cambridge", "영국", "케임브리지", 52.204, 0.119, 2024, "press"),
    ("Maastricht University", "네덜란드", "마스트리흐트", 50.848, 5.687, 2024, "press"),
    ("Chinese University of Hong Kong", "홍콩", "샤틴", 22.420, 114.207, 2024, "press"),
    ("Nanyang Technological University", "싱가포르", "싱가포르", 1.348, 103.683, 2024, "press"),
]

# 같은 공식 페이지에 나란히 실린 '해외대학 교환학생' 프로그램.
# FGLP 와는 다른 제도라 따로 묶는다.
_EXCHANGE = [
    ("INSA Lyon", "프랑스", "리옹", 45.783, 4.879, 2023, "official"),
    ("Maastricht University", "네덜란드", "마스트리흐트", 50.848, 5.687, 2023, "official"),
    ("Ulm University", "독일", "울름", 48.422, 9.956, 2023, "official"),
    ("Koç University", "튀르키예", "이스탄불", 41.204, 29.061, 2023, "official"),
]


def _pack(rows, kind):
    return [
        {
            "name": name,
            "country": country,
            "city": city,
            "lat": lat,
            "lon": lon,
            "since": since,
            "source": source,
            "kind": kind,
        }
        for (name, country, city, lat, lon, since, source) in rows
    ]


def get_fglp() -> dict:
    schools = _pack(_FGLP, "fglp")
    exchange = _pack(_EXCHANGE, "exchange")
    return {
        "ok": True,
        "verifiedOn": VERIFIED_ON,
        "officialUrl": OFFICIAL_URL,
        "contact": CONTACT,
        "schools": schools + exchange,
        "program": {
            "name": "FGLP (Freshmen Global Leadership Program)",
            "summary": "해외 유수대학의 여름학기 수업을 듣고 오는 기초학부 글로벌 프로그램.",
            "target": "1·2학년(4학기 이내) 재학생",
            "period": "하계 방학 중",
            "support": "수업료·기숙사비 지원 (항공료·비자 발급비는 본인 부담)",
            "requirement": "파견 대학별 어학성적 요건 등 상이",
            "contact": CONTACT,
        },
        # 화면에 그대로 띄울 단서들. 확정된 것과 아닌 것을 갈라 둔다.
        "notes": [
            {
                "level": "warn",
                "text": "학교 공식 페이지는 아직 2023년 기준(6개 대학, 1인당 최대 1,000만원)으로 적혀 있습니다.",
            },
            {
                "level": "info",
                "text": "2024학년도에 8개교가 더해져 14개교가 되었고 지원 상한선이 없어졌다는 것은 학내 신문(DGIST DNA) 보도로 확인한 내용입니다.",
            },
            {
                "level": "info",
                "text": "2025학년도에 일본이 파견 국가로 더해져 16개교가 되었다고 보도되었으나, 어느 대학인지는 공개된 자료에서 찾지 못해 지도에 넣지 않았습니다.",
            },
            {
                "level": "warn",
                "text": "대학별 정원(선발인원)은 공개된 문서에 없습니다. 지원 전에 국제협력팀에 확인하세요.",
            },
        ],
    }
