"""달구(마스코트) 스티커 시트를 한 장씩 잘라 화면에서 쓸 그림으로 만든다.

    python scripts/slice_dalgu.py            # design/dalgu/sheet*.png → web/img/dalgu/*.png
    python scripts/slice_dalgu.py --all      # 48장 전부 design/dalgu/all/ 에 (고를 때 보기용)

시트(png·webp)는 4×4 칸이고 배경이 투명하다. 칸 사이의 '완전히 투명한 띠' 를 찾아 자르므로
칸 크기가 조금 달라도 그림이 잘리지 않는다(칸 경계에 그림이 걸치지 않는 것을 확인함).
자른 뒤 투명한 가장자리를 걷어 내고, 화면에서 2배로 선명하게 보이도록 긴 변 240px 로 줄인다.

Pillow 가 필요하다 (앱 실행에는 필요 없고, 그림을 다시 만들 때만 쓴다).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SHEETS = [
    ROOT / "design" / "dalgu" / "sheet0.png",
    ROOT / "design" / "dalgu" / "sheet1.png",
    # 2026-09-28 받은 시트: 옆·뒷모습과 걷기·달리기가 있어 첫 실행 소개에서 달구가 화면을 돌아다닐 때 쓴다
    ROOT / "design" / "dalgu" / "sheet2.webp",
]
OUT = ROOT / "web" / "img" / "dalgu"
MAX_SIDE = 240

# (시트, 행, 열) → 이름. 튜토리얼 단계마다 어울리는 포즈를 골랐다.
POSES = {
    "hello": (0, 0, 0),      # 붕어빵 들고 손 흔들기
    "bow": (0, 0, 1),        # 꾸벅 인사
    "cheer": (0, 0, 3),      # 신나서 뛰기
    "thumbs": (0, 1, 0),     # 엄지 척
    "wink": (0, 1, 1),       # 윙크 브이
    "heart": (0, 1, 2),      # 하트
    "fight": (0, 1, 3),      # 주먹 불끈
    "read": (0, 2, 0),       # 앉아서 책 읽기
    "search": (0, 2, 1),     # 돋보기
    "point": (0, 2, 2),      # 손가락으로 가리키기
    "sleep": (0, 3, 2),      # 쿨쿨
    "walk": (1, 0, 0),       # 걸어가기
    "run": (1, 0, 1),        # 달리기
    "eat": (1, 0, 2),        # 붕어빵 먹기
    "study": (1, 2, 0),      # 엎드려 책 읽기
    "offer": (1, 2, 1),      # 붕어빵 건네기
    # --- sheet2: 돌아다니는 달구 (옆모습 포즈는 방향을 적어 둔다: 화면에서 좌우를 뒤집을 때 씀) ---
    "trot": (2, 0, 0),       # 걷기 (왼쪽을 봄)
    "dash": (2, 0, 1),       # 달리기 (오른쪽을 봄)
    "munch": (2, 0, 2),      # 앉아서 붕어빵 먹기
    "reach": (2, 0, 3),      # 뒤돌아 위로 손 뻗기
    "sprout": (2, 1, 0),     # 새싹 보기
    "yay": (2, 1, 1),        # 신나서 폴짝
    "nap": (2, 1, 2),        # 웅크리고 자기
    "back": (2, 1, 3),       # 뒷모습
    "book": (2, 2, 0),       # 앉아서 책 읽기
    "give": (2, 2, 1),       # 붕어빵 내밀기
    "stretch": (2, 2, 2),    # 기지개
    "skip": (2, 2, 3),       # 깡충
    "laugh": (2, 3, 0),      # 앉아서 크게 웃기
    "reachup": (2, 3, 1),    # 옆으로 서서 위로 뻗기
    "shy": (2, 3, 2),        # 꾸벅, 쑥스러움
    "lounge": (2, 3, 3),     # 누워서 붕어빵
}


def gutters(values: list[int]) -> list[tuple[int, int]]:
    """0 이 3칸 이상 이어진 구간(빈 띠)들."""
    out, start = [], None
    for i, v in enumerate(values):
        if v == 0 and start is None:
            start = i
        if v != 0 and start is not None:
            if i - start >= 3:
                out.append((start, i - 1))
            start = None
    if start is not None and len(values) - start >= 3:
        out.append((start, len(values) - 1))
    return out


def cells(sheet: Image.Image) -> list[list[tuple[int, int, int, int]]]:
    """4×4 칸의 (왼, 위, 오른, 아래) 상자."""
    alpha = sheet.getchannel("A").point(lambda v: 255 if v > 16 else 0)
    w, h = sheet.size
    # 열·행마다 불투명 픽셀이 있는지 (줄여서 빠르게 본다)
    cols = [1 if alpha.crop((x, 0, x + 1, h)).getbbox() else 0 for x in range(w)]
    rows = [1 if alpha.crop((0, y, w, y + 1)).getbbox() else 0 for y in range(h)]

    def spans(values):
        gaps = gutters(values)
        edges = [(gaps[i][1] + 1, gaps[i + 1][0]) for i in range(len(gaps) - 1)]
        if len(edges) != 4:
            raise SystemExit(f"4칸으로 나뉘지 않습니다 (찾은 칸 {len(edges)}개)")
        return edges

    xs, ys = spans(cols), spans(rows)
    return [[(x0, y0, x1, y1) for (x0, x1) in xs] for (y0, y1) in ys]


def export(sheet: Image.Image, box: tuple[int, int, int, int], path: Path) -> None:
    piece = sheet.crop(box)
    trimmed = piece.crop(piece.getchannel("A").getbbox())
    scale = MAX_SIDE / max(trimmed.size)
    if scale < 1:
        trimmed = trimmed.resize(
            (round(trimmed.width * scale), round(trimmed.height * scale)), Image.LANCZOS
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    # 스티커 그림이라 색이 많지 않다. 256색 팔레트(투명도 유지)로 줄이면
    # 장당 65KB → 20KB 안팎이 되고 눈으로는 차이가 없다.
    trimmed.quantize(colors=256, method=Image.Quantize.FASTOCTREE).save(path, optimize=True)


def main() -> None:
    sheets = [Image.open(p).convert("RGBA") for p in SHEETS]
    grids = [cells(s) for s in sheets]
    if "--all" in sys.argv:
        for si, grid in enumerate(grids):
            for r, row in enumerate(grid):
                for c, box in enumerate(row):
                    export(sheets[si], box, ROOT / "design" / "dalgu" / "all" / f"s{si}_r{r}c{c}.png")
        print(f"{len(sheets) * 16}장을 design/dalgu/all/ 에 저장했습니다.")
        return
    total = 0
    for name, (si, r, c) in POSES.items():
        path = OUT / f"{name}.png"
        export(sheets[si], grids[si][r][c], path)
        total += path.stat().st_size
    print(f"{len(POSES)}장을 {OUT} 에 저장했습니다 (합계 {total // 1024}KB).")


if __name__ == "__main__":
    main()
