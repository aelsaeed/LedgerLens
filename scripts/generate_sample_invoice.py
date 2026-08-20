from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from invoice_scanner.sample import DEMO_INVOICE_TEXT

DEFAULT_OUTPUT = Path("data/sample_invoice.png")
PAGE_SIZE = (1200, 1500)
INK = "#14213d"
ACCENT = "#2563eb"
MUTED = "#64748b"


def render_sample_invoice(output: Path) -> Path:
    """Render the shared demo invoice as a high-contrast PNG."""

    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", PAGE_SIZE, "#f1f5f9")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.load_default(size=46)
    body_font = ImageFont.load_default(size=28)
    small_font = ImageFont.load_default(size=22)
    total_font = ImageFont.load_default(size=34)

    draw.rounded_rectangle(
        (55, 50, 1145, 1450), radius=18, fill="white", outline="#cbd5e1", width=2
    )
    draw.rectangle((55, 50, 1145, 64), fill=ACCENT)

    lines = DEMO_INVOICE_TEXT.splitlines()
    draw.text((105, 115), lines[0], fill=INK, font=title_font)
    draw.text((105, 180), "INVOICE", fill=ACCENT, font=small_font)
    draw.line((105, 235, 1095, 235), fill="#e2e8f0", width=3)

    y = 285
    for line in lines[1:]:
        if not line:
            y += 30
            continue

        is_total = line.startswith("Total ")
        if line.startswith("Description"):
            draw.rounded_rectangle((90, y - 12, 1110, y + 52), radius=8, fill="#eff6ff")
        if line.startswith("Subtotal"):
            draw.line((710, y - 20, 1095, y - 20), fill="#cbd5e1", width=2)

        draw.text(
            (105, y),
            line,
            fill=ACCENT if is_total else INK,
            font=total_font if is_total else body_font,
        )
        y += 76 if is_total else 60

    draw.line((105, 1340, 1095, 1340), fill="#e2e8f0", width=2)
    draw.text(
        (105, 1370),
        "Generated locally for the LedgerLens portfolio demo",
        fill=MUTED,
        font=small_font,
    )

    image.save(output, format="PNG", optimize=True)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the deterministic invoice image used by the LedgerLens demo."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        metavar="PATH",
        help=f"destination PNG path (default: {DEFAULT_OUTPUT})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.output.suffix.lower() != ".png":
        parser.error("--output must use a .png extension")

    output = render_sample_invoice(args.output)
    print(f"Wrote sample invoice to {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
