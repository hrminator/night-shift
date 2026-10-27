"""Generate the Baltic Print quote PDFs for the fictional test world.

- fixtures/baltic_quote_original.pdf: clean text PDF, quote Q-1187.
- fixtures/baltic_quote_Q-1187-B_text.pdf: same revised content as a text PDF.
- fixtures/baltic_quote_Q-1187-B.pdf: scan-styled PDF — the revised quote
  drawn as a raster image (slight rotation + noise), embedded as the only
  page content, with no text layer.

Run: uv run python scripts/make_fixtures.py
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

FIXTURES = Path("fixtures")

ORIGINAL_LINES = [
    "Baltic Print OÜ (fictional)",
    "Quote Q-1187 — 100 tote bags with your logo",
    "",
    "Price: NOK 18 per bag",
    "Freight: NOK 350",
    "Total: NOK 2,150",
    "",
    "Delivery: delivered to your address by 9 November.",
    "Valid until Nov 5.",
    "",
    "Contact: quotes@baltic-print.example.com (fictional)",
]

REVISED_LINES = [
    "Baltic Print OÜ (fictional)",
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
    "Contact: quotes@baltic-print.example.com (fictional)",
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


def scan_pdf(path: Path, lines: list[str], seed: int = 27) -> None:
    rng = random.Random(seed)
    page_w, page_h = A4
    scale = 3  # draw big, then downscale for smoother glyphs
    img = Image.new("RGB", (int(page_w) * scale, int(page_h) * scale), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=36)
    title_font = ImageFont.load_default(size=48)
    y = 220
    for i, line in enumerate(lines):
        draw.text((200, y), line, fill=(20, 20, 20),
                  font=title_font if i == 1 else font)
        y += 80
    img = img.rotate(0.8, resample=Image.BICUBIC, expand=False,
                     fillcolor="white")
    pixels = img.load()
    w, h = img.size
    for _ in range(w * h // 60):
        x, y = rng.randrange(w), rng.randrange(h)
        v = rng.randint(150, 235)
        pixels[x, y] = (v, v, v)
    img = img.resize((int(page_w), int(page_h)), Image.LANCZOS)
    tmp = path.with_suffix(".png")
    img.save(tmp)
    doc = canvas.Canvas(str(path), pagesize=A4)
    doc.drawImage(str(tmp), 0, 0, width=page_w, height=page_h)
    doc.showPage()
    doc.save()
    tmp.unlink()


def main() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    text_pdf(FIXTURES / "baltic_quote_original.pdf", ORIGINAL_LINES)
    text_pdf(FIXTURES / "baltic_quote_Q-1187-B_text.pdf", REVISED_LINES)
    scan_pdf(FIXTURES / "baltic_quote_Q-1187-B.pdf", REVISED_LINES)
    for name in ("baltic_quote_original.pdf",
                 "baltic_quote_Q-1187-B_text.pdf",
                 "baltic_quote_Q-1187-B.pdf"):
        blob = (FIXTURES / name).read_bytes()
        has_text = b"warehouse" in blob or b"address by 9" in blob
        print(f"{name}: {len(blob)} bytes, text-layer hit: {has_text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
