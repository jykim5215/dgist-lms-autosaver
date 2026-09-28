"""설치 화면(Inno Setup)에 쓰는 그림을 만든다.

설치 창 왼쪽 큰 그림: 달구(web/img/dalgu/hello.png) + '붕어빵' 글자, 배경은 투명.
  배경색은 .iss 의 WizardImageBackColor(밝은 모드)·…DynamicDark(어두운 모드)가 칠한다.
  그래서 그림 한 벌로 두 모드를 다 맞춘다(어두운 모드 전용 그림 설정은 Inno 에 없다).
오른쪽 위 작은 그림: 앱 로고.

화면 배율(100/125/150/200%)마다 크기를 따로 만들어 두면 Inno 가 맞는 것을 고른다.
실행: 시스템 파이썬(Pillow) — python scripts/make_installer_art.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "packaging" / "art"
OUT.mkdir(parents=True, exist_ok=True)

ACCENT = (192, 103, 74, 255)  # 앱의 --accent
SOFT = (192, 103, 74, 150)
FONT = Path(r"C:\Windows\Fonts\malgunbd.ttf")
# 앱 제목과 같은 명조(Noto Serif KR). 없는 PC 면 맑은 고딕 굵게로 대신한다
SERIF = Path(r"C:\Windows\Fonts\NotoSerifKR-VF.ttf")

dalgu = Image.open(ROOT / "web" / "img" / "dalgu" / "hello.png").convert("RGBA")
logo = Image.open(ROOT / "web" / "app-logo-120.png").convert("RGBA")

# 큰 그림: Inno 기본 164x314 를 기준으로 배율별
for scale in (100, 125, 150, 200):
    w, h = round(164 * scale / 100), round(314 * scale / 100)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if SERIF.exists():
        title = ImageFont.truetype(str(SERIF), round(26 * scale / 100))
        try:
            title.set_variation_by_axes([600])
        except Exception:
            pass
    else:
        title = ImageFont.truetype(str(FONT), round(24 * scale / 100))
    sub = ImageFont.truetype(str(FONT).replace("malgunbd", "malgun"), round(10.5 * scale / 100))
    y = round(34 * scale / 100)
    for text, font, color, gap in (("붕어빵", title, ACCENT, 8), ("DGIST 학생의 LMS 도우미", sub, SOFT, 0)):
        tw = draw.textbbox((0, 0), text, font=font)[2]
        draw.text(((w - tw) / 2, y), text, font=font, fill=color)
        y += font.size + round(gap * scale / 100)
    # 달구는 아래쪽에 크게
    target_w = round(w * 0.86)
    ratio = target_w / dalgu.width
    d = dalgu.resize((target_w, round(dalgu.height * ratio)), Image.LANCZOS)
    img.alpha_composite(d, ((w - d.width) // 2, h - d.height - round(18 * scale / 100)))
    img.save(OUT / f"wizard-{scale}.png")

# 작은 그림: 55x55 기준
for scale in (100, 125, 150, 200):
    s = round(55 * scale / 100)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    l = logo.resize((s, s), Image.LANCZOS)
    img.alpha_composite(l)
    img.save(OUT / f"small-{scale}.png")

print("ok", sorted(p.name for p in OUT.iterdir()))
