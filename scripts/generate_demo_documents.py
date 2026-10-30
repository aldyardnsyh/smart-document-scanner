"""Render four synthetic document photos for the demo dataset.

All names, numbers and addresses are fictional. Output goes to dataset/demo_src/ and is
consumed by app.py, so the files must look like phone photos: a sheet lying on a desk,
slightly rotated, with sensor noise.
"""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

CANVAS = (1600, 1100)
BACKGROUND = (0x8A, 0x8F, 0x96)
DOC_SIZE = (1360, 860)
MARGIN = 90
FONT_DIR = Path(r"C:\Windows\Fonts")
OUT_DIR = Path(__file__).resolve().parents[1] / "dataset" / "demo_src"

# (text, size, bold, align) — align is "left", "center" or "right".
Line = tuple[str, int, bool, str]

DOCUMENTS: dict[str, list[Line]] = {
    "business_card": [
        ("AVERY LINDGREN", 64, True, "center"),
        ("PRINCIPAL ENGINEER", 34, False, "center"),
        ("NORTHLINE ANALYTICS", 40, True, "center"),
        ("Email: avery@northline.example", 30, False, "center"),
        ("Phone: +1 555 0142", 30, False, "center"),
        # Empty spacer line: an empty string has zero glyph height, so only the line gap is
        # added. It pushes the address away from the contact block without a second field.
        ("", 58, False, "center"),
        ("400 Harbor Street, Seattle, WA 98104", 26, False, "center"),
    ],
    "id_card": [
        ("KARTU TANDA PENDUDUK", 46, True, "center"),
        ("NIK : 0000000000000000", 34, False, "left"),
        ("Nama : BUDI SANTOSO", 34, False, "left"),
        ("Tanggal Lahir: 25-07-1990", 30, False, "left"),
        ("Golongan Darah: O", 30, False, "left"),
        ("Alamat : JL. MERDEKA NO. 42, BANDUNG", 30, False, "left"),
        ("Pekerjaan : KARYAWAN SWASTA", 30, False, "left"),
    ],
    "receipt": [
        ("HARBOR CAFE", 46, True, "center"),
        ("Merchant: HARBOR CAFE", 30, False, "center"),
        ("Ref: INV-2026-0042", 30, False, "center"),
        ("Date: 12/03/2026", 28, False, "center"),
        ("Espresso 32.000", 30, False, "left"),
        ("Croissant 45.000", 30, False, "left"),
        ("Sandwich 71.500", 30, False, "left"),
        ("TOTAL 148.500", 34, True, "left"),
        ("Thank you", 28, False, "center"),
    ],
    "paper_document": [
        ("MEMORANDUM OF UNDERSTANDING", 40, True, "center"),
        ("Document No. MOU-2026-117", 28, False, "center"),
        ("Date: 04 March 2026", 28, False, "center"),
        ("This memorandum records the terms agreed between", 26, False, "left"),
        ("Northline Analytics and Harbor Cafe for a twelve", 26, False, "left"),
        ("month analytics engagement.", 26, False, "left"),
        ("Both parties will review the scope every quarter.", 26, False, "left"),
    ],
}

_FONT_CACHE: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}


def load_font(size: int, bold: bool) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key not in _FONT_CACHE:
        name = "arialbd.ttf" if bold else "arial.ttf"
        _FONT_CACHE[key] = ImageFont.truetype(str(FONT_DIR / name), size)
    return _FONT_CACHE[key]


def render_document(lines: list[Line]) -> Image.Image:
    """Draw the sheet flat; rotation happens later so text stays crisp."""
    doc = Image.new("RGB", DOC_SIZE, "white")
    draw = ImageDraw.Draw(doc)
    metrics: list[tuple[int, int]] = []
    for text, size, bold, _ in lines:
        box = draw.textbbox((0, 0), text, font=load_font(size, bold))
        metrics.append((box[2] - box[0], box[3] - box[1]))
    total = sum(height for _, height in metrics) + sum(int(size * 0.55) for _, size, _, _ in lines)
    y = max(MARGIN // 2, (DOC_SIZE[1] - total) // 2)
    for (text, size, bold, align), (width, height) in zip(lines, metrics):
        if align == "center":
            x = (DOC_SIZE[0] - width) // 2
        elif align == "right":
            x = DOC_SIZE[0] - MARGIN - width
        else:
            x = MARGIN
        draw.text((x, y), text, font=load_font(size, bold), fill=(18, 18, 20))
        y += height + int(size * 0.55)
    return doc


def compose_photo(doc: Image.Image, seed: int) -> Image.Image:
    rng = random.Random(seed)
    width, height = CANVAS
    noise = np.random.default_rng(seed).integers(-7, 8, (height, width, 1), dtype=np.int16)
    pixels = np.clip(np.array(Image.new("RGB", CANVAS, BACKGROUND), dtype=np.int16) + noise, 0, 255)
    canvas = Image.fromarray(pixels.astype(np.uint8))
    angle = rng.choice((-1, 1)) * rng.uniform(2.0, 4.0)
    rotated = doc.convert("RGBA").rotate(angle, resample=Image.BICUBIC, expand=True)
    left = (width - rotated.width) // 2
    top = (height - rotated.height) // 2
    shadow = Image.new("RGBA", rotated.size, (0, 0, 0, 0))
    shadow.putalpha(rotated.getchannel("A").point(lambda value: int(value * 0.45)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    canvas.paste(shadow, (left + 12, top + 16), shadow)
    canvas.paste(rotated, (left, top), rotated)
    return canvas


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for index, (name, lines) in enumerate(DOCUMENTS.items(), start=1):
        photo = compose_photo(render_document(lines), seed=index)
        target = OUT_DIR / f"{name}.jpg"
        photo.save(target, format="JPEG", quality=92, subsampling=0)
        print(f"{target.name}: {photo.size[0]}x{photo.size[1]}, {target.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()