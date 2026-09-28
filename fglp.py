"""FGLP(Freshmen Global Leadership Program) 파견 대학 정보.

출처: DGIST 2027 UNDERGRADUATE ADMISSIONS GUIDE FOR INTERNATIONAL STUDENTS
      (국제학부 입학 안내서, 2026년 6월 게시) 13쪽 FGLP, 15쪽 학점교류.
      https://www.dgist.ac.kr/iuadm/sub03_01.do 에 올라온 PDF.
      안내서는 글자를 그림으로 넣은 PDF라 쪽을 그려서 눈으로 옮겨 적었다.

기초학부 홈페이지(https://www.dgist.ac.kr/college/sub05_04.do)와 영문 FGLP
안내(https://www.dgist.ac.kr/eng/sub06_04_01.do)는 2026년 9월에도 '2023년 기준'
으로 남아 있다. 어긋날 때는 가장 최근 문서인 2027 입학 안내서를 따른다.

정원(대학별 선발 인원)과 TYPE 1·2의 차이는 어느 문서에도 적혀 있지 않다.
없는 내용은 지어내지 않는다.

좌표는 각 대학 본 캠퍼스(여름학기 수업이 열리는 곳)의 위경도다. 2026-09-22 에
대학 하나하나 다시 찍었다. (지도에서 점이 한쪽으로 밀려 보이던 것은 좌표가
아니라 화면에서 핀 기준점을 잘못 잡은 탓이었다 — styles.css 의 .wm-pin 참고)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

VERIFIED_ON = "2026-09-22"

SOURCE_LABEL = "DGIST 2027 국제학부 입학안내서 (2026.6)"
SOURCE_URL = "https://www.dgist.ac.kr/iuadm/sub03_01.do"
OFFICIAL_URL = "https://www.dgist.ac.kr/eng/sub06_04_01.do"
CONTACT = "국제협력팀 053-785-1163 / amatista@dgist.ac.kr"

# 공통 학점 기준은 2027 안내서에 없다. 2026 안내서(2025.7)에 있던 값이다.
GPA_REQUIREMENT = "DGIST 학점 3.23 / 4.3 이상 (2026 안내서 기준)"

# (이름, 국가, 도시, 위도, 경도, 어학 기준, 구분)
_T800 = "TOEIC 800 · TOEFL iBT 80 · IELTS 6.5"
_FGLP = [
    # TYPE 1 — 안내서 순서 그대로
    ("UC Berkeley", "미국", "버클리", 37.8719, -122.2585, _T800, "TYPE 1"),
    ("UCLA", "미국", "로스앤젤레스", 34.0689, -118.4452, _T800, "TYPE 1"),
    ("UC Irvine", "미국", "어바인", 33.6405, -117.8443, _T800, "TYPE 1"),
    ("Stanford University", "미국", "스탠퍼드", 37.4275, -122.1697, "TOEFL iBT 100 · IELTS 7.0", "TYPE 1"),
    ("Harvard University", "미국", "케임브리지(MA)", 42.3770, -71.1167, "TOEFL iBT 100 · IELTS 7.0", "TYPE 1"),
    ("University of Wisconsin–Madison", "미국", "매디슨", 43.0766, -89.4125, _T800, "TYPE 1"),
    ("Boston University", "미국", "보스턴", 42.3505, -71.1054, "TOEFL iBT 84 · IELTS 7.0", "TYPE 1"),
    ("Purdue University", "미국", "웨스트라피엣", 40.4237, -86.9212, "TOEFL iBT 88 · IELTS 6.5", "TYPE 1"),
    ("University of Virginia", "미국", "샬러츠빌", 38.0336, -78.5080, "TOEFL iBT 90 · IELTS 7.0", "TYPE 1"),
    ("Johns Hopkins University", "미국", "볼티모어", 39.3299, -76.6205, "TOEFL iBT 100 · IELTS 7.0", "TYPE 1"),
    ("Arizona State University", "미국", "템피", 33.4242, -111.9281, "TOEFL iBT 80 · IELTS 6.5", "TYPE 1"),
    ("University of British Columbia", "캐나다", "밴쿠버", 49.2606, -123.2460, _T800, "TYPE 1"),
    ("Maastricht University", "네덜란드", "마스트리흐트", 50.8484, 5.6880, "TOEFL iBT 90 · IELTS 6.5", "TYPE 1"),
    ("Utrecht University", "네덜란드", "위트레흐트", 52.0853, 5.1741, _T800, "TYPE 1"),
    ("RWTH Aachen University", "독일", "아헨", 50.7780, 6.0775, _T800, "TYPE 1"),
    ("University of Cambridge", "영국", "케임브리지", 52.2043, 0.1149, "TOEFL iBT 92 · IELTS 6.5", "TYPE 1"),
    ("ESME", "프랑스", "파리(이브리쉬르센)", 48.8155, 2.3855, _T800, "TYPE 1"),
    ("INSA Lyon", "프랑스", "리옹(빌뢰르반)", 45.7837, 4.8778, _T800, "TYPE 1"),
    ("Aalto University", "핀란드", "에스포", 60.1867, 24.8277, _T800, "TYPE 1"),
    ("National Taiwan University", "대만", "타이베이", 25.0173, 121.5397, _T800, "TYPE 1"),
    ("Nanyang Technological University", "싱가포르", "싱가포르", 1.3483, 103.6831, "TOEFL iBT 90 · IELTS 6.0", "TYPE 1"),
    ("Hokkaido University", "일본", "삿포로", 43.0770, 141.3410, _T800, "TYPE 1"),
    ("Waseda University", "일본", "도쿄", 35.7090, 139.7196, _T800, "TYPE 1"),
    ("Chinese University of Hong Kong", "홍콩", "샤틴", 22.4196, 114.2068, "TOEFL iBT 71 · IELTS 6.0", "TYPE 1"),
    ("HKUST", "홍콩", "칭수이완", 22.3364, 114.2654, "TOEFL iBT 80 · IELTS 6.0", "TYPE 1"),
    # TYPE 2
    ("University of Calgary", "캐나다", "캘거리", 51.0784, -114.1337, "TOEIC 700", "TYPE 2"),
    ("Dublin City University", "아일랜드", "더블린", 53.3861, -6.2564, "TOEIC 700", "TYPE 2"),
    ("RMIT University", "호주", "멜버른", -37.8083, 144.9631, "TOEIC 700", "TYPE 2"),
]

# 학점교류(Credit Exchange). 안내서에 '11개국 27개교'라 적혀 있고 그중 11곳만
# 이름이 나와 있다. 나머지 16곳은 문서에 없어 넣지 않았다.
# 2026 안내서와 달라진 점: INSA Lyon 은 FGLP 로 옮겨 갔고, Innsbruck 대신 TU Wien,
# Grenoble INP-UGA 와 발렌시아 공대가 새로 들어왔다.
_EXCHANGE = [
    ("Ulm University", "독일", "울름", 48.4222, 9.9563),
    ("Grenoble INP - UGA", "프랑스", "그르노블", 45.1920, 5.7676),
    ("Polytechnic University of Valencia", "스페인", "발렌시아", 39.4815, -0.3435),
    ("University of Groningen", "네덜란드", "흐로닝언", 53.2194, 6.5627),
    ("Aalto University", "핀란드", "에스포", 60.1867, 24.8277),
    ("TU Wien", "오스트리아", "빈", 48.1990, 16.3699),
    ("Koç University", "튀르키예", "이스탄불", 41.2055, 29.0730),
    ("National Yang Ming Chiao Tung University", "대만", "신주", 24.7869, 120.9975),
    ("Osaka University", "일본", "스이타", 34.8222, 135.5245),
    ("Dalian University of Technology", "중국", "다롄", 38.8816, 121.5282),
    ("Universiti Malaya", "말레이시아", "쿠알라룸푸르", 3.1209, 101.6538),
]


def _load_photos() -> dict:
    """tools/fetch_uni_photos.py 가 받아 둔 사진 정보.

    앱 안에 넣어 두었으므로 인터넷이 없어도 보이고, 어느 대학을 들여다보는지
    바깥에 알려지지도 않는다. 라이선스 표기는 화면에 같이 띄운다.
    """
    # EXE 로 묶였을 때도 찾도록
    base = Path(getattr(sys, "_MEIPASS", "") or Path(__file__).resolve().parent)
    path = base / "uni_photos.json"
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
            "group": group,
            **photo_of(name),
        }
        for (name, country, city, lat, lon, lang, group) in _FGLP
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
            "target": "1·2학년(4학기 이내) 재학생 · 가을학기 입학 외국인 학생은 5학기 이내",
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
            "scale": "11개국 27개교 (안내서에 이름이 나온 11곳만 지도에 표시)",
        },
        "notes": [
            {
                "level": "info",
                "text": f"{SOURCE_LABEL} 기준입니다. 파견 대학 {len(_FGLP)}곳(TYPE 1 {sum(1 for x in _FGLP if x[6] == 'TYPE 1')}곳, TYPE 2 {sum(1 for x in _FGLP if x[6] == 'TYPE 2')}곳)과 대학별 어학 기준이 이 문서에 실려 있습니다.",
            },
            {
                "level": "info",
                "text": f"공통 지원 자격: {GPA_REQUIREMENT}. 1·2학년(4학기 이내) 재학생.",
            },
            {
                "level": "warn",
                "text": "기초학부·영문 홈페이지의 FGLP 안내는 아직 2023년 기준이라 대학 목록이 적습니다. 이 목록이 더 최신입니다.",
            },
            {
                "level": "warn",
                "text": "대학별 정원과 TYPE 1·2의 차이는 공개 문서에 없습니다. 지원 전에 국제협력팀에 확인하세요.",
            },
        ],
    }
