from __future__ import annotations

from dataclasses import dataclass
from math import ceil, sqrt
from typing import Iterable, Sequence

from PIL import Image


@dataclass
class ComposeSettings:
    layout: str = "auto"
    fit_mode: str = "fit"
    background: str = "#2f2f2f"
    gap: int = 8
    margin: int = 8
    output_width_mode: str = "auto"
    custom_width: int = 2560
    custom_columns: int = 3


def _resolved_columns(layout: str, count: int, custom_columns: int) -> int:
    if count <= 0:
        return 1
    mapping = {
        "horizontal": count,
        "vertical": 1,
        "2x2": 2,
        "3x1": 3,
        "1x3": 1,
        "custom": max(1, custom_columns),
    }
    if layout in mapping:
        return min(count, max(1, mapping[layout]))
    # auto / masonry fallback
    return min(count, max(1, round(sqrt(count))))


def _target_width(settings: ComposeSettings) -> int | None:
    mode = settings.output_width_mode
    if mode == "1920":
        return 1920
    if mode == "2560":
        return 2560
    if mode == "3840":
        return 3840
    if mode == "custom":
        return max(1, int(settings.custom_width))
    return None


def _as_rgba(img: Image.Image) -> Image.Image:
    return img.convert("RGBA") if img.mode != "RGBA" else img


def _scale_for_cell(img_w: int, img_h: int, cell_w: int, cell_h: int, fit_mode: str, allow_upscale: bool) -> float:
    if fit_mode == "original":
        return 1.0
    if img_w <= 0 or img_h <= 0:
        return 1.0
    if fit_mode == "fill":
        scale = max(cell_w / img_w, cell_h / img_h)
    else:
        scale = min(cell_w / img_w, cell_h / img_h)
    if not allow_upscale:
        scale = min(scale, 1.0)
    return max(scale, 0.0001)


def _paste_centered(canvas: Image.Image, source: Image.Image, x: int, y: int, w: int, h: int) -> None:
    dest_x = x + (w - source.width) // 2
    dest_y = y + (h - source.height) // 2
    canvas.alpha_composite(source, (dest_x, dest_y))


def _compose_grid(images: Sequence[Image.Image], settings: ComposeSettings) -> Image.Image:
    count = len(images)
    cols = _resolved_columns(settings.layout, count, settings.custom_columns)
    rows = [images[i : i + cols] for i in range(0, count, cols)]

    target_width = _target_width(settings)
    allow_upscale = target_width is not None
    gap = max(0, int(settings.gap))
    margin = max(0, int(settings.margin))

    if target_width is None:
        col_widths = []
        for col_i in range(cols):
            widths = [row[col_i].width for row in rows if col_i < len(row)]
            col_widths.append(max(widths) if widths else 1)
    else:
        inner_w = max(1, target_width - 2 * margin - max(0, cols - 1) * gap)
        base_w = max(1, inner_w // cols)
        remainder = max(0, inner_w - base_w * cols)
        col_widths = [base_w + (1 if i < remainder else 0) for i in range(cols)]

    row_heights: list[int] = []
    for row in rows:
        heights = []
        for col_i, img in enumerate(row):
            cell_w = col_widths[col_i]
            scale = _scale_for_cell(img.width, img.height, cell_w, 10_000_000, "fit" if settings.fit_mode == "original" else settings.fit_mode, allow_upscale)
            heights.append(max(1, round(img.height * scale)))
        row_heights.append(max(heights) if heights else 1)

    canvas_w = sum(col_widths) + max(0, cols - 1) * gap + 2 * margin
    canvas_h = sum(row_heights) + max(0, len(rows) - 1) * gap + 2 * margin
    canvas = Image.new("RGBA", (max(1, canvas_w), max(1, canvas_h)), settings.background)

    y = margin
    for row_i, row in enumerate(rows):
        row_h = row_heights[row_i]
        x = margin
        for col_i, img in enumerate(row):
            cell_w = col_widths[col_i]
            image = _as_rgba(img)
            scale = _scale_for_cell(img.width, img.height, cell_w, row_h, settings.fit_mode, allow_upscale)
            resized = image.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.Resampling.LANCZOS)
            if settings.fit_mode == "fill":
                left = max(0, (resized.width - cell_w) // 2)
                top = max(0, (resized.height - row_h) // 2)
                resized = resized.crop((left, top, left + cell_w, top + row_h))
                canvas.alpha_composite(resized, (x, y))
            else:
                _paste_centered(canvas, resized, x, y, cell_w, row_h)
            x += cell_w + gap
        y += row_h + gap

    return canvas


def _compose_masonry(images: Sequence[Image.Image], settings: ComposeSettings) -> Image.Image:
    count = len(images)
    cols = _resolved_columns("auto", count, settings.custom_columns)
    target_width = _target_width(settings)
    gap = max(0, int(settings.gap))
    margin = max(0, int(settings.margin))

    if target_width is None:
        # keep source dimensions in auto mode and avoid upscaling
        average_width = max(1, round(sum(img.width for img in images) / count))
        col_w = average_width
        allow_upscale = False
        extra_right_space = 0
    else:
        inner_w = max(1, target_width - 2 * margin - max(0, cols - 1) * gap)
        col_w = max(1, inner_w // cols)
        extra_right_space = max(0, inner_w - col_w * cols)
        allow_upscale = True

    col_heights = [0] * cols
    placements: list[tuple[Image.Image, int, int, int, int]] = []

    for img in images:
        col = min(range(cols), key=lambda idx: col_heights[idx])
        scale = _scale_for_cell(img.width, img.height, col_w, 10_000_000, "fit" if settings.fit_mode == "original" else settings.fit_mode, allow_upscale)
        draw_w = max(1, round(img.width * scale))
        draw_h = max(1, round(img.height * scale))
        x = margin + col * (col_w + gap)
        y = margin + col_heights[col]
        placements.append((img, x, y, col_w, draw_h))
        col_heights[col] += draw_h + gap

    max_h = max(col_heights) - (gap if images else 0)
    canvas_w = cols * col_w + max(0, cols - 1) * gap + 2 * margin + extra_right_space
    canvas_h = max(1, max_h + 2 * margin)
    canvas = Image.new("RGBA", (max(1, canvas_w), max(1, canvas_h)), settings.background)

    for img, x, y, cell_w, cell_h in placements:
        image = _as_rgba(img)
        if settings.fit_mode == "original":
            draw = image
            _paste_centered(canvas, draw, x, y, cell_w, cell_h)
            continue
        scale = _scale_for_cell(img.width, img.height, cell_w, cell_h, settings.fit_mode, allow_upscale)
        draw = image.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.Resampling.LANCZOS)
        if settings.fit_mode == "fill":
            left = max(0, (draw.width - cell_w) // 2)
            top = max(0, (draw.height - cell_h) // 2)
            draw = draw.crop((left, top, left + cell_w, top + cell_h))
            canvas.alpha_composite(draw, (x, y))
        else:
            _paste_centered(canvas, draw, x, y, cell_w, cell_h)
    return canvas


def compose_image(images: Iterable[Image.Image], settings: ComposeSettings) -> Image.Image:
    image_list = [img.copy() for img in images]
    if not image_list:
        return Image.new("RGBA", (800, 600), settings.background)
    if settings.layout in {"auto", "masonry"}:
        return _compose_masonry(image_list, settings)
    return _compose_grid(image_list, settings)
