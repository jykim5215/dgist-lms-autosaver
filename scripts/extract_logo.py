"""원본 사진에서 붕어빵만 오려내(누끼) 아이콘 세트를 만든다.

사용법:
    python scripts/extract_logo.py [원본이미지경로]

동작:
1) 붕어빵의 노란 몸통에서 출발해 '배경이 아닌 픽셀'을 이어붙여(flood fill)
   붕어빵 영역만 골라낸다. 이렇게 하면 마스코트(파란 발·크림 몸통)는 색으로
   막아 두어 넘어가지 않는다.
2) 잘라낸 뒤 정사각 캔버스 가운데에 여백을 두고 배치한다.
3) app.png / app.ico / app-logo-120.png / favicon 을 만든다.
"""
from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DOCS = ROOT / "docs"
DEFAULT_SRC = Path.home() / "Desktop" / "image-1785606731882.png"

BG_PAD = 0.10          # 캔버스 대비 여백 비율
CANVAS_BG = (250, 246, 236, 255)   # 아이콘 바탕 (크림)


def is_background(c) -> bool:
    r, g, b = c[:3]
    return r > 232 and g > 232 and b > 232


def is_blue(c) -> bool:
    """마스코트의 파란 발."""
    r, g, b = c[:3]
    return b > r + 22 and b > 115


def is_cream(c) -> bool:
    """마스코트 몸통의 크림/미색 (붕어빵 노랑보다 훨씬 옅고 파르스름)."""
    r, g, b = c[:3]
    return r > 215 and g > 210 and b > 195 and not is_background(c)


def extract_fish(src: Image.Image) -> Image.Image:
    """노란 몸통에서 번져 나가며 붕어빵(몸통+윤곽선)만 남긴다."""
    im = src.convert("RGBA")
    w, h = im.size
    px = im.load()

    # 1) 씨앗: 가장 노란 픽셀들의 무게중심
    yellows = [
        (x, y)
        for x in range(w)
        for y in range(h)
        if px[x, y][0] > 200 and px[x, y][1] > 140 and px[x, y][2] < 170
    ]
    if not yellows:
        raise SystemExit("노란 몸통을 찾지 못했습니다. 원본 이미지를 확인해 주세요.")
    cx = sum(p[0] for p in yellows) // len(yellows)
    cy = sum(p[1] for p in yellows) // len(yellows)

    # 2) 붕어빵으로 인정할 픽셀: 배경도, 파란 발도, 크림 몸통도 아닌 것
    def passable(x, y):
        c = px[x, y]
        return not (is_background(c) or is_blue(c) or is_cream(c))

    keep = [[False] * h for _ in range(w)]
    if not passable(cx, cy):
        cx, cy = yellows[len(yellows) // 2]
    q = deque([(cx, cy)])
    keep[cx][cy] = True
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not keep[nx][ny] and passable(nx, ny):
                keep[nx][ny] = True
                q.append((nx, ny))

    # 3) 마스코트 팔의 검은 윤곽선 걷어내기.
    #    붕어빵 윤곽선은 반드시 노란 몸통에 맞닿아 있지만,
    #    팔 윤곽선은 (크림 몸통을 지운 뒤라) 노랑에서 멀리 떨어져 홀로 남는다.
    def is_yellow(c):
        return c[0] > 195 and c[1] > 135 and c[2] < 175

    reach = max(3, int(min(w, h) * 0.035))  # 윤곽선 두께 정도만 인정
    yellow_mask = [[is_yellow(px[x, y]) and keep[x][y] for y in range(h)] for x in range(w)]

    # 노란 픽셀에서 reach 칸 이내인지 BFS로 한 번에 계산
    near = [[False] * h for _ in range(w)]
    q = deque()
    for x in range(w):
        for y in range(h):
            if yellow_mask[x][y]:
                near[x][y] = True
                q.append((x, y, 0))
    while q:
        x, y, d = q.popleft()
        if d >= reach:
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not near[nx][ny]:
                near[nx][ny] = True
                q.append((nx, ny, d + 1))

    final = [[keep[x][y] and near[x][y] for y in range(h)] for x in range(w)]

    # 4) 남은 부스러기 제거: 가장 큰 덩어리(=붕어빵)만 남긴다
    seen = [[False] * h for _ in range(w)]
    best: list[tuple[int, int]] = []
    for sx in range(w):
        for sy in range(h):
            if not final[sx][sy] or seen[sx][sy]:
                continue
            comp = []
            stack = [(sx, sy)]
            seen[sx][sy] = True
            while stack:
                x, y = stack.pop()
                comp.append((x, y))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and final[nx][ny] and not seen[nx][ny]:
                        seen[nx][ny] = True
                        stack.append((nx, ny))
            if len(comp) > len(best):
                best = comp

    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    op = out.load()
    for x, y in best:
        op[x, y] = px[x, y]
    return out


def square(img: Image.Image, size: int, with_bg: bool, radius_ratio: float = 0.22) -> Image.Image:
    """내용에 맞게 잘라 정사각형 캔버스 가운데 배치."""
    from PIL import ImageDraw

    art = img.crop(img.getbbox())
    inner = int(size * (1 - BG_PAD * 2))
    scale = min(inner / art.width, inner / art.height)
    art = art.resize((max(1, round(art.width * scale)), max(1, round(art.height * scale))), Image.LANCZOS)

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if with_bg:
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle(
            [0, 0, size - 1, size - 1], radius=int(size * radius_ratio), fill=CANVAS_BG
        )
        canvas.alpha_composite(layer)
    canvas.alpha_composite(art, ((size - art.width) // 2, (size - art.height) // 2))
    return canvas


def main() -> None:
    src_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    if not src_path.exists():
        raise SystemExit(f"원본을 찾을 수 없습니다: {src_path}")

    src = Image.open(src_path)
    # 작은 원본을 그대로 키우면 계단이 생기므로 먼저 크게 만든 뒤 오려낸다
    big = src.convert("RGB").resize((src.width * 8, src.height * 8), Image.LANCZOS)
    fish = extract_fish(big)

    WEB.mkdir(exist_ok=True)
    square(fish, 256, with_bg=True).save(WEB / "app.png")
    square(fish, 120, with_bg=True).save(WEB / "app-logo-120.png")
    square(fish, 512, with_bg=False).save(WEB / "logo-fish.png")  # 배경 없는 원본용
    square(fish, 256, with_bg=True).save(
        WEB / "app.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    for name in ("app.png", "app.ico", "app-logo-120.png", "logo-fish.png"):
        print(f"  {name}: {(WEB / name).stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
