"""Deterministic original figures for the fictional demonstration thesis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin


@dataclass(frozen=True, slots=True)
class Figure:
    """A thesis figure and its accessible description."""

    number: str
    path: str
    alt_text: str
    caption: str = ""


_WIDTH = 1800
_HEIGHT = 1200
_INK = "#243447"
_GREEN = "#4F7D4A"
_LIGHT_GREEN = "#DCEBD8"
_GOLD = "#D99B2B"
_BLUE = "#4B78A8"
_LIGHT_BLUE = "#DFEAF5"


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size, index=0)
    return ImageFont.load_default()


def _centered_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    *,
    fill: str = _INK,
) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(
        (xy[0] - (box[2] - box[0]) / 2, xy[1] - (box[3] - box[1]) / 2),
        text,
        fill=fill,
        font=font,
    )


def _save(image: Image.Image, path: Path, description: str) -> None:
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Description", description)
    image.save(path, format="PNG", compress_level=9, optimize=False, pnginfo=metadata)


def _draw_crown_sampling(path: Path) -> None:
    image = Image.new("RGB", (_WIDTH, _HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    title_font = _font(58)
    label_font = _font(38)
    small_font = _font(30)

    _centered_text(draw, (900, 70), "树冠分层与方位抽样示意图（模拟）", title_font)
    draw.line((900, 180, 900, 1060), fill="#795548", width=38)
    draw.ellipse((400, 165, 1400, 950), fill=_LIGHT_GREEN, outline=_GREEN, width=8)
    draw.line((410, 445, 1390, 445), fill=_GREEN, width=5)
    draw.line((410, 700, 1390, 700), fill=_GREEN, width=5)
    draw.line((900, 180, 900, 950), fill=_GREEN, width=4)
    draw.line((500, 300, 1300, 850), fill="#7CA874", width=3)
    draw.line((1300, 300, 500, 850), fill="#7CA874", width=3)

    layer_labels = (("上层", 300), ("中层", 565), ("下层", 820))
    for text, y in layer_labels:
        draw.rounded_rectangle(
            (235, y - 45, 375, y + 45),
            radius=18,
            fill="white",
            outline=_GREEN,
            width=4,
        )
        _centered_text(draw, (305, y), text, label_font)

    directions = (
        ("北", (900, 145)),
        ("东", (1455, 570)),
        ("南", (900, 995)),
        ("西", (345, 570)),
    )
    for text, center in directions:
        _centered_text(draw, center, text, label_font, fill=_BLUE)

    points = (
        (690, 300),
        (1110, 300),
        (620, 565),
        (1180, 565),
        (700, 820),
        (1100, 820),
    )
    for index, (x, y) in enumerate(points, start=1):
        draw.ellipse((x - 28, y - 28, x + 28, y + 28), fill=_GOLD, outline=_INK, width=3)
        _centered_text(draw, (x, y), str(index), small_font)

    draw.rounded_rectangle(
        (1280, 890, 1710, 1100),
        radius=24,
        fill=_LIGHT_BLUE,
        outline=_BLUE,
        width=4,
    )
    draw.ellipse((1325, 935, 1375, 985), fill=_GOLD, outline=_INK, width=3)
    draw.text((1400, 936), "样方中心", fill=_INK, font=small_font)
    draw.line((1325, 1035, 1380, 1035), fill=_GREEN, width=5)
    draw.text((1400, 1012), "分层边界", fill=_INK, font=small_font)
    _save(
        image,
        path,
        "模拟苹果树冠按上中下三层及东南西北方位布设六个样方的示意图。",
    )


def _draw_workflow(path: Path) -> None:
    image = Image.new("RGB", (_WIDTH, _HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    title_font = _font(58)
    label_font = _font(35)
    small_font = _font(29)

    _centered_text(draw, (900, 70), "单株叶片数量估算流程（模拟）", title_font)
    boxes = (
        (90, 290, 390, 520, "树冠分层\n与编号"),
        (470, 290, 770, 520, "样方叶片\n人工计数"),
        (850, 290, 1150, 520, "可见面积\n比例校正"),
        (1230, 290, 1530, 520, "分层外推\n与合计"),
    )
    colors = (_LIGHT_GREEN, _LIGHT_BLUE, "#F8EACB", "#E8E0F2")
    for box, color in zip(boxes, colors, strict=True):
        x1, y1, x2, y2, text = box
        draw.rounded_rectangle(
            (x1, y1, x2, y2), radius=30, fill=color, outline=_INK, width=5
        )
        first, second = text.split("\n")
        _centered_text(draw, ((x1 + x2) // 2, y1 + 85), first, label_font)
        _centered_text(draw, ((x1 + x2) // 2, y1 + 145), second, label_font)

    for x1, x2 in ((390, 470), (770, 850), (1150, 1230)):
        draw.line((x1 + 12, 405, x2 - 18, 405), fill=_BLUE, width=10)
        draw.polygon(
            ((x2 - 18, 385), (x2 - 18, 425), (x2 + 5, 405)),
            fill=_BLUE,
        )

    draw.rounded_rectangle(
        (340, 700, 1460, 1010),
        radius=35,
        fill="#F6F8FA",
        outline=_GREEN,
        width=5,
    )
    _centered_text(draw, (900, 765), "误差评估与结果报告", label_font, fill=_GREEN)
    items = (
        "重复抽样差异",
        "遮挡校正不确定性",
        "分层权重敏感性",
        "置信区间与适用范围",
    )
    for index, text in enumerate(items):
        x = 470 + (index % 2) * 560
        y = 850 + (index // 2) * 90
        draw.ellipse((x - 22, y - 22, x + 22, y + 22), fill=_GOLD, outline=_INK, width=2)
        draw.text((x + 42, y - 22), text, fill=_INK, font=small_font)

    draw.line((1380, 520, 1380, 645, 900, 645, 900, 700), fill=_BLUE, width=8)
    draw.polygon(((880, 680), (920, 680), (900, 708)), fill=_BLUE)
    _save(
        image,
        path,
        "模拟数据从树冠分层、样方计数、面积校正到分层外推，并进入误差评估的流程图。",
    )


def generate_demo_figures(output_dir: str | Path = "build/demo-assets") -> tuple[Path, Path]:
    """Generate both original PNG figures and return their paths."""

    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    crown_path = directory / "crown-layer-sampling.png"
    workflow_path = directory / "leaf-count-estimation-workflow.png"
    _draw_crown_sampling(crown_path)
    _draw_workflow(workflow_path)
    return crown_path, workflow_path
