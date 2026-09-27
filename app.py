import argparse
import json
import sys
from pathlib import Path

from src.config import OUTPUT_DIR
from src.pipeline import ScanOptions, process_image

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

FIGLET = (
    "  ____  ____  ____  ",
    " / ___||  _ \\/ ___| ",
    " \\___ \\| | | \\___ \\ ",
    "  ___) | |_| |___) |",
    " |____/|____/|____/  ",
)

# The tagline sits to the right of the art, one line per row. The art is 21 columns at its
# widest, so the text starts three columns past that to clear the strokes.
TAGS = (
    "Smart Document Scanner",
    "detect - correct - enhance - read - parse",
    "document detection and structured extraction",
)


def render_banner() -> str:
    """Compose the header, indented two columns from the left margin.

    Only the first three rows carry a tagline, so only those are padded out to a common width.
    Padding the remaining rows too left a long trail of meaningless trailing spaces under the
    art.
    """
    indent = " "
    rows: list[str] = []
    for index, line in enumerate(FIGLET):
        if index < len(TAGS):
            rows.append((line + " " * 3 + TAGS[index]).rstrip())
        else:
            rows.append(line.rstrip())
    return "\n" + "\n".join(indent + row for row in rows) + "\n"


BANNER = render_banner()

RULE = "-" * 62


def print_banner(input_path: Path, count: int, output_path: Path) -> None:
    """Print a short startup banner so a batch run reads as a session, not a bare loop."""
    stream = sys.stdout
    if stream.isatty():
        stream.write(BANNER)
        stream.write(f"\n  SDS  input : {input_path}\n")
        stream.write(f"  SDS  images: {count}\n")
        stream.write(f"  SDS  output: {output_path}\n")
        stream.write(RULE + "\n")
    else:
        # Piped or redirected: keep the output machine-readable.
        stream.write(f"Smart Document Scanner: {count} image(s) from {input_path}\n")


def collect_images(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() in IMAGE_EXTENSIONS else []
    return sorted(
        path
        for path in input_path.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch process documents with Smart Document Scanner"
    )
    parser.add_argument("--input", required=True, type=Path, help="Image file or directory")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR, help="Output directory")
    parser.add_argument(
        "--doc-type",
        choices=("auto", "business_card", "id_card", "receipt", "paper_document"),
        default="auto",
    )
    parser.add_argument("--fast-denoise", action="store_true")
    parser.add_argument("--no-cpp", action="store_true")
    parser.add_argument("--ocr-language", default="eng+ind")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.input.exists():
        raise SystemExit(f"Input path does not exist: {args.input}")
    images = collect_images(args.input)
    if not images:
        raise SystemExit("No supported images found")
    print_banner(args.input, len(images), args.output)
    options = ScanOptions(
        document_type=args.doc_type,
        fast_denoise=args.fast_denoise,
        cpp_acceleration=not args.no_cpp,
        ocr_language=args.ocr_language,
    )
    results: list[dict] = []
    for index, image_path in enumerate(images, start=1):
        job_id = f"cli-{index:03d}-{image_path.stem}"
        print(f"[{index}/{len(images)}] Processing {image_path}")
        result = process_image(
            image_path,
            args.output,
            job_id,
            options,
            lambda stage, percent, message: print(f"  {percent:3d}% {stage}: {message}"),
        )
        results.append(result)
    summary_path = args.output / "batch_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Processed {len(results)} image(s). Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
