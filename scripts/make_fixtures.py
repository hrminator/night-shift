"""Generate the Rannavere Print quote PDFs for the fictional test world.

- fixtures/baltic_quote_original.pdf: clean text PDF, quote Q-1187.
- fixtures/baltic_quote_Q-1187-B_text.pdf: same revised content as a text PDF.
- fixtures/baltic_quote_Q-1187-B.pdf: scan-styled PDF — the revised quote
  drawn as a raster image (slight rotation + noise), embedded as the only
  page content, with no text layer.
- fixtures/baltic_quote_Q-1187-B.png: the exact raster placed in the
  scan-styled PDF (post-rotation, post-noise), kept for the pages.
- fixtures/baltic_quote_Q-1187-B@2x.png: the same page at exactly twice
  the pixel size (1190x1682), same rotation and noise, as sent to the
  grounding call; its bands are the 1x bands times 2.
- fixtures/baltic_quote_Q-1187-B.lines.json: scale metadata plus one entry
  per rendered line
  with its text and its 1x pixel band (y_top, y_bottom, x_left, x_right)
  in the 1x PNG's coordinates; scale 1 recorded at the top.

Run: uv run python scripts/make_fixtures.py
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

FIXTURES = Path("fixtures")

SCAN_SCALE = 3  # draw big, then downscale for smoother glyphs
SCAN_X = 200
SCAN_Y0 = 220
SCAN_STEP = 80
SCAN_ROTATION_DEGREES = 0.8
SCAN_SEED = 27

ORIGINAL_LINES = [
    "Rannavere Print OÜ (fictional)",
    "Quote Q-1187 — 100 tote bags with your logo",
    "",
    "Price: NOK 18 per bag",
    "Freight: NOK 350",
    "Total: NOK 2,150",
    "",
    "Delivery: delivered to your address by 9 November.",
    "Valid until Nov 5.",
    "",
    "Contact: quotes@rannavere-print.example.com (fictional)",
]

REVISED_LINES = [
    "Rannavere Print OÜ (fictional)",
    "Quote Q-1187-B — 100 tote bags with your logo",
    "",
    "This quote replaces quote Q-1187.",
    "",
    "Price: NOK 18 per bag",
    "Freight: NOK 350",
    "Total: NOK 2,150",
    "",
    "Delivery: Goods will leave our warehouse by 10 November.",
    "",
    "Contact: quotes@rannavere-print.example.com (fictional)",
]


def text_pdf(path: Path, lines: list[str]) -> None:
    doc = canvas.Canvas(str(path), pagesize=A4)
    text = doc.beginText(25 * mm, 260 * mm)
    text.setFont("Helvetica", 12)
    text.setLeading(18)
    for line in lines:
        text.textLine(line)
    doc.drawText(text)
    doc.showPage()
    doc.save()


def line_bands(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    title_font: ImageFont.FreeTypeFont,
    final_size: tuple[int, int],
    big_size: tuple[int, int],
) -> list[dict]:
    """One pixel band per rendered line, in the final PNG's coordinates.

    Each band comes from the draw position and the font metrics at draw
    scale. The 0.8 degree rotation is not modelled exactly: the band is
    widened, top and bottom, by the rotation's vertical displacement
    across the line's width (width times sin(0.8)), then downscaled to
    PNG pixels (floor for top/left, ceil for bottom/right).
    """
    final_w, final_h = final_size
    big_w, big_h = big_size
    bands = []
    for i, line in enumerate(lines):
        use = title_font if i == 1 else font
        y = SCAN_Y0 + SCAN_STEP * i
        if line:
            left, top, right, bottom = draw.textbbox(
                (SCAN_X, y), line, font=use)
        else:
            _, top, _, bottom = draw.textbbox((SCAN_X, y), "X", font=use)
            left = right = SCAN_X
        slant = (right - left) * math.sin(
            math.radians(SCAN_ROTATION_DEGREES))
        top -= slant
        bottom += slant
        bands.append({
            "text": line,
            "y_top": max(0, min(final_h, math.floor(
                top * final_h / big_h))),
            "y_bottom": max(0, min(final_h, math.ceil(
                bottom * final_h / big_h))),
            "x_left": max(0, min(final_w, math.floor(
                left * final_w / big_w))),
            "x_right": max(0, min(final_w, math.ceil(
                right * final_w / big_w))),
        })
    return bands


def render_scan_page(
    lines: list[str], seed: int = SCAN_SEED
) -> tuple[Image.Image, Image.Image, list[dict]]:
    """Draw the scan-styled page; return (1x image, 2x image, 1x bands)."""
    rng = random.Random(seed)
    page_w, page_h = A4
    big = Image.new(
        "RGB",
        (int(page_w) * SCAN_SCALE, int(page_h) * SCAN_SCALE),
        "white",
    )
    draw = ImageDraw.Draw(big)
    font = ImageFont.load_default(size=36)
    title_font = ImageFont.load_default(size=48)
    y = SCAN_Y0
    for i, line in enumerate(lines):
        draw.text((SCAN_X, y), line, fill=(20, 20, 20),
                  font=title_font if i == 1 else font)
        y += SCAN_STEP
    final_size = (int(page_w), int(page_h))
    bands = line_bands(draw, lines, font, title_font, final_size, big.size)
    img = big.rotate(SCAN_ROTATION_DEGREES, resample=Image.BICUBIC,
                     expand=False, fillcolor="white")
    pixels = img.load()
    w, h = img.size
    for _ in range(w * h // 60):
        x, y = rng.randrange(w), rng.randrange(h)
        v = rng.randint(150, 235)
        pixels[x, y] = (v, v, v)
    img_1x = img.resize(final_size, Image.LANCZOS)
    img_2x = img.resize((final_size[0] * 2, final_size[1] * 2), Image.LANCZOS)
    return img_1x, img_2x, bands


def scan_pdf(path: Path, lines: list[str], seed: int = SCAN_SEED) -> list[dict]:
    """Write the scan-styled PDF plus its 1x and 2x PNGs; return 1x bands.

    The PNG kept next to the PDF is the same image object placed in the
    PDF (post-rotation, post-noise), pixel for pixel. The @2x PNG is the
    same rotated noisy page at exactly twice the size, so its bands are
    the 1x bands times 2.
    """
    img, img_2x, bands = render_scan_page(lines, seed)
    png_path = path.with_suffix(".png")
    img.save(png_path)
    img_2x.save(png_path.with_name(png_path.stem + "@2x.png"))
    page_w, page_h = A4
    doc = canvas.Canvas(str(path), pagesize=A4)
    doc.drawImage(str(png_path), 0, 0, width=page_w, height=page_h)
    doc.showPage()
    doc.save()
    return bands


def main() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    text_pdf(FIXTURES / "baltic_quote_original.pdf", ORIGINAL_LINES)
    text_pdf(FIXTURES / "baltic_quote_Q-1187-B_text.pdf", REVISED_LINES)
    bands = scan_pdf(FIXTURES / "baltic_quote_Q-1187-B.pdf", REVISED_LINES)
    with Image.open(FIXTURES / "baltic_quote_Q-1187-B.png") as _shot:
        _size_1x = [_shot.size[0], _shot.size[1]]
    _doc = {"png": "baltic_quote_Q-1187-B.png", "png_size": _size_1x,
            "scale": 1, "lines": bands}
    (FIXTURES / "baltic_quote_Q-1187-B.lines.json").write_text(
        json.dumps(_doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for name in ("baltic_quote_original.pdf",
                 "baltic_quote_Q-1187-B_text.pdf",
                 "baltic_quote_Q-1187-B.pdf"):
        blob = (FIXTURES / name).read_bytes()
        has_text = b"warehouse" in blob or b"address by 9" in blob
        print(f"{name}: {len(blob)} bytes, text-layer hit: {has_text}")
    png = FIXTURES / "baltic_quote_Q-1187-B.png"
    with Image.open(png) as shot:
        print(f"{png.name}: {png.stat().st_size} bytes, "
              f"{shot.size[0]}x{shot.size[1]}, {len(bands)} line bands")
    png_2x = FIXTURES / "baltic_quote_Q-1187-B@2x.png"
    with Image.open(png_2x) as shot_2x:
        print(f"{png_2x.name}: {png_2x.stat().st_size} bytes, "
              f"{shot_2x.size[0]}x{shot_2x.size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
