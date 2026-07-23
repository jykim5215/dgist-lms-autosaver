"""붕어빵 로고 아이콘 일괄 생성.

하나의 도형 정의에서 창 아이콘(app.png), 윈도우 바로가기(app.ico),
구글 동의화면용(app-logo-120.png)을 모두 만든다.
로고를 고칠 때는 이 파일의 좌표/색만 바꾸고 다시 실행하면 된다.

    python scripts/make_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

# 붕어빵 색 (실물 노릇한 껍질 톤)
BG = (242, 228, 205, 255)      # 베이지 바탕
BODY = (233, 156, 51, 255)     # 몸통
BODY_HI = (245, 191, 106, 255) # 윗면 하이라이트
LINE = (176, 96, 32, 255)      # 진한 테두리
SCORE = (176, 96, 32, 150)     # 표면 결


def _bez(p0, p1, p2, p3, n=150):
    out = []
    for i in range(1, n + 1):
        t = i / n
        m = 1 - t
        out.append(
            (
                m * m * m * p0[0] + 3 * m * m * t * p1[0] + 3 * m * t * t * p2[0] + t * t * t * p3[0],
                m * m * m * p0[1] + 3 * m * m * t * p1[1] + 3 * m * t * t * p2[1] + t * t * t * p3[1],
            )
        )
    return out


def _path(start, segs):
    pts = [start]
    for seg in segs:
        if seg[0] == "C":
            pts.extend(_bez(pts[-1], seg[1], seg[2], seg[3]))
        else:
            a, b = pts[-1], seg[1]
            pts.extend([(a[0] + (b[0] - a[0]) * i / 40, a[1] + (b[1] - a[1]) * i / 40) for i in range(1, 41)])
    return pts


# --- 24x24 좌표계 도형 정의 -------------------------------------------------
TAIL = _path((17.9, 10.8), [
    ("L", (21.4, 8.0)),
    ("C", (21.8, 7.7), (22.1, 8.0), (22.0, 8.4)),
    ("C", (21.5, 10.5), (21.5, 13.5), (22.0, 15.6)),
    ("C", (22.1, 16.0), (21.8, 16.3), (21.4, 16.0)),
    ("L", (17.9, 13.2)),
])
DORSAL = _path((9.0, 7.3), [
    ("C", (10.0, 5.3), (12.8, 4.9), (14.4, 5.9)),
    ("C", (12.7, 6.1), (10.6, 6.5), (9.4, 7.4)),
])
# 붕어빵답게 통통한 몸통
BODY_PATH = _path((2.4, 12.0), [
    ("C", (2.4, 9.0), (5.4, 6.5), (9.8, 6.5)),
    ("C", (13.5, 6.5), (16.6, 8.5), (17.9, 10.8)),
    ("C", (18.2, 11.3), (18.2, 12.7), (17.9, 13.2)),
    ("C", (16.6, 15.5), (13.5, 17.5), (9.8, 17.5)),
    ("C", (5.4, 17.5), (2.4, 15.0), (2.4, 12.0)),
])
PECTORAL = _path((8.2, 14.0), [
    ("C", (9.4, 14.9), (11.0, 15.0), (12.0, 14.4)),
    ("C", (11.4, 15.9), (9.2, 15.9), (8.2, 14.9)),
])
# 붕어빵 틀 자국처럼 몸통을 따라 흐르는 결
SCORES = [
    ((9.0, 10.2), (10.0, 11.0), (10.0, 13.0), (9.0, 13.8)),
    ((11.6, 9.8), (12.7, 10.8), (12.7, 13.2), (11.6, 14.2)),
    ((14.0, 10.4), (14.9, 11.2), (14.9, 12.8), (14.0, 13.6)),
    ((2.9, 13.0), (3.6, 13.5), (4.3, 13.6), (4.9, 13.4)),  # 입
]
EYE = (6.0, 10.4, 0.85)


TILT = 0  # 정면 (기울이지 않음)


def render(size: int, ss: int = 8, inset: float = 0.86, radius_ratio: float = 0.25,
           transparent_bg: bool = False) -> Image.Image:
    """붕어빵 아이콘 한 장을 그린다."""
    c = size * ss
    u = c / 24.0

    def T(p):
        x, y = p
        return ((12 + (x - 12) * inset) * u, (12 + (y - 12) * inset) * u)

    def poly(pts):
        return [T(p) for p in pts]

    # --- 붕어빵은 별도 레이어에 그린 뒤 통째로 기울인다 ---
    fish = Image.new("RGBA", (c, c), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fish)

    def stroke(dr, pts, color, w, close=True):
        r = max(w * ss / 2, 1)
        for p in (pts + [pts[0]] if close else pts):
            x, y = T(p)
            dr.ellipse([x - r, y - r, x + r, y + r], fill=color)

    def shape(pts, fill, w=0.95):
        fd.polygon(poly(pts), fill=fill)
        stroke(fd, pts, LINE, w)

    shape(TAIL, BODY)
    shape(DORSAL, BODY)
    shape(BODY_PATH, BODY)

    # 노릇하게 구워진 윗면
    hi = _path((4.4, 10.8), [
        ("C", (6.0, 8.2), (9.4, 7.3), (13.2, 7.9)),
        ("C", (9.6, 8.4), (6.6, 9.4), (4.4, 10.8)),
    ])
    fd.polygon(poly(hi), fill=BODY_HI)

    # --- 붕어빵 틀 자국: 몸통 안쪽에만 보이도록 마스크로 잘라낸다 ---
    body_mask = Image.new("L", (c, c), 0)
    ImageDraw.Draw(body_mask).polygon(poly(BODY_PATH), fill=255)
    grid = Image.new("RGBA", (c, c), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    step = 1.55 * inset * u
    lw = max(int(0.5 * ss), 1)
    y0 = 5.5 * inset * u
    x = 3.0 * inset * u
    while x < c:
        gd.line([(x, 0), (x - 3.2 * u, c)], fill=(176, 96, 32, 58), width=lw)
        x += step
    y = y0
    while y < c:
        gd.line([(0, y), (c, y - 1.1 * u)], fill=(176, 96, 32, 58), width=lw)
        y += step
    fish.alpha_composite(Image.composite(grid, Image.new("RGBA", (c, c), (0, 0, 0, 0)), body_mask))

    fd.polygon(poly(PECTORAL), fill=LINE)
    for s in SCORES:
        stroke(fd, [s[0]] + _bez(*s), SCORE, 0.8, close=False)

    ex, ey = T((EYE[0], EYE[1]))
    er = EYE[2] * inset * u
    fd.ellipse([ex - er, ey - er, ex + er, ey + er], fill=LINE)

    fish = fish.rotate(TILT, resample=Image.BICUBIC, center=(c / 2, c / 2))

    img = Image.new("RGBA", (c, c), (0, 0, 0, 0))
    if not transparent_bg:
        ImageDraw.Draw(img).rounded_rectangle(
            [0, 0, c - 1, c - 1], radius=int(c * radius_ratio), fill=BG
        )
    img.alpha_composite(fish)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    WEB.mkdir(parents=True, exist_ok=True)

    # 앱 창 아이콘 (pywebview)
    render(256).save(WEB / "app.png")
    # 윈도우 바로가기/작업표시줄 (여러 해상도 내장)
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    render(256).save(WEB / "app.ico", format="ICO",
                     sizes=[(s, s) for s in ico_sizes])
    # 구글 동의 화면
    render(120).save(WEB / "app-logo-120.png")

    for name in ("app.png", "app.ico", "app-logo-120.png"):
        p = WEB / name
        print(f"  {name}: {p.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
