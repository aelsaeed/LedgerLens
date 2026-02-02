from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUTPUT = Path("data/sample_invoice.png")


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (800, 600), "white")
    draw = ImageDraw.Draw(image)
    lines = [
        "Vendor: Acme Corp",
        "Invoice # INV-1001",
        "Date: 2024-01-15",
        "",
        "Item 1  Widget A",
        "Item 2  Widget B",
        "",
        "Total: 1299.99 USD",
    ]
    y = 40
    for line in lines:
        draw.text((40, y), line, fill="black")
        y += 30

    image.save(OUTPUT)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
