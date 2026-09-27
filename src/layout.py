"""Layout reconstruction from detected text lines.

The parser cannot know that a line is a person's name by looking at the characters
alone. What actually separates a name from an organisation on a card is structure: font
size, column position, and proximity to anchored values such as an email or a telephone
label. This module turns detected line boxes into that structure.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .ocr_engine import TextUnit

# Typical printed character height ratios used to bucket typography into tiers.
TIER_PRIMARY = 1.28
TIER_SECONDARY = 1.10
TIER_TERTIARY = 0.88


@dataclass(frozen=True)
class LineBlock:
    """One visual text line, with its geometry and typographic measurements."""

    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float
    column: int
    tier: str
    word_count: int

    @property
    def center_y(self) -> float:
        return self.top + self.height / 2

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2

    @property
    def char_height(self) -> float:
        return self.height


@dataclass
class Layout:
    """All lines of one OCR variant plus the measurements derived from them."""

    lines: list[LineBlock] = field(default_factory=list)
    columns: int = 1
    page_width: int = 0
    page_height: int = 0
    median_char_height: float = 0.0

    def column_lines(self, column: int) -> list[LineBlock]:
        return [line for line in self.lines if line.column == column]

    def largest_lines(self, limit: int = 3) -> list[LineBlock]:
        return sorted(self.lines, key=lambda line: -line.char_height)[:limit]

    def bottom_lines(self, fraction: float = 0.35) -> list[LineBlock]:
        if not self.lines:
            return []
        cutoff = self.page_height * (1 - fraction)
        return [line for line in self.lines if line.center_y >= cutoff]


def _tier_for(height: float, median: float) -> str:
    if median <= 0:
        return "body"
    ratio = height / median
    if ratio >= TIER_PRIMARY:
        return "primary"
    if ratio >= TIER_SECONDARY:
        return "secondary"
    if ratio <= TIER_TERTIARY:
        return "tertiary"
    return "body"


def _assign_columns(units: list[TextUnit], page_width: int) -> dict[int, int]:
    """Split lines into columns by projecting every line box onto the horizontal axis.

    A column break is a vertical band of the page that no line crosses. The earlier version of
    this walked the lines in reading order and opened a new column whenever a line started far
    to the right of the previous one. That can only ever count columns upwards: on a card with
    a left block and a right block, reading order interleaves them, so the first line that
    jumped right switched the whole page to column 1 and nothing could switch back. Every line
    then shared one column, which is what truncated multi-line addresses.

    Projecting onto the x-axis is order-independent, so a line is assigned to whichever band its
    centre falls in regardless of where it appears in the reading order.
    """
    if page_width <= 0 or len(units) < 2:
        return {}

    origin = min(unit.left for unit in units)
    extent = max(unit.left + unit.width for unit in units) - origin
    if extent <= 0:
        return {}

    # Bins are small enough to resolve a gutter, large enough to stay cheap.
    bin_count = max(64, min(720, extent // 2))
    scale = bin_count / extent
    occupied = bytearray(bin_count)
    for unit in units:
        start = max(0, min(bin_count - 1, int((unit.left - origin) * scale)))
        end = max(start + 1, min(bin_count, int((unit.left + unit.width - origin) * scale)))
        for index in range(start, end):
            occupied[index] = 1

    heights = [unit.height for unit in units if unit.height > 0]
    median_height = statistics.median(heights) if heights else 0.0
    # A gutter on a business card is a modest fraction of the card width, and a long line in
    # the left block usually eats most of it, so the threshold is anchored on the content
    # width. Tying it tightly to line height rejects real gutters and collapses the page back
    # to a single column.
    min_gap = max(median_height * 0.75, extent * 0.035)

    # Column index for each bin, incremented at every sufficiently wide empty run.
    band_of_bin = [0] * bin_count
    band = 0
    run = 0
    for index in range(bin_count):
        if occupied[index]:
            run = 0
        else:
            run += 1
            if run * (extent / bin_count) >= min_gap:
                band += 1
                run = 0
        band_of_bin[index] = band

    assignment: dict[int, int] = {}
    for unit in units:
        centre = unit.left + unit.width / 2 - origin
        index = max(0, min(bin_count - 1, int(centre * scale)))
        assignment[unit.index] = band_of_bin[index]

    # Only keep the split when the bands are believable. A single stray outlier should not
    # become its own column, and a card with three or more text blocks is rare enough that
    # over-splitting is more likely to be a mistake than a real layout.
    counts: dict[int, int] = {}
    for value in assignment.values():
        counts[value] = counts.get(value, 0) + 1
    populated = sorted(counts)
    if len(populated) < 2 or len(populated) > 3:
        return {}
    if min(counts[band] for band in populated) < max(2, len(units) * 0.15):
        return {}
    return assignment


def build_layout(result, page_width: int = 0, page_height: int = 0) -> Layout:
    """Build a Layout from an OcrResult's detected lines.

    The engine already returns lines in reading order, so grouping is a matter of ordering
    and of deriving columns and typographic tiers. When only plain text is available (the
    backwards compatible `parse_fields` entry point) the lines are laid out on a synthetic
    grid so the same rules still apply.
    """
    units = [unit for unit in result.words if unit.text.strip()]
    layout = Layout(page_width=page_width, page_height=page_height)
    if not units:
        if result.text.strip():
            for index, raw in enumerate(result.text.splitlines()):
                text = " ".join(raw.split())
                if not text:
                    continue
                layout.lines.append(
                    LineBlock(
                        text=text,
                        left=0,
                        top=index * 20,
                        width=max(len(text) * 8, 1),
                        height=18,
                        confidence=result.confidence * 100,
                        column=0,
                        tier="body",
                        word_count=len(text.split()),
                    )
                )
            layout.median_char_height = 18.0
        return layout

    ordered = sorted(units, key=lambda unit: (unit.top, unit.left))
    column_of = _assign_columns(ordered, page_width)
    char_heights = [unit.char_height for unit in ordered if unit.char_height > 0]
    median_height = statistics.median(char_heights) if char_heights else 0.0
    layout.median_char_height = median_height
    layout.columns = (max(column_of.values()) + 1) if column_of else 1
    layout.lines = [
        LineBlock(
            text=unit.text,
            left=unit.left,
            top=unit.top,
            width=unit.width,
            height=unit.height,
            confidence=unit.confidence * 100,
            column=column_of.get(unit.index, 0),
            tier=_tier_for(unit.char_height, median_height),
            word_count=len(unit.text.split()),
        )
        for unit in ordered
    ]
    return layout
