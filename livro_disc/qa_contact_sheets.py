from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent / "qa_render"
pages = sorted(root.glob("page-*.png"))
for batch_no in range(0, len(pages), 9):
    batch = pages[batch_no:batch_no + 9]
    opened = [Image.open(p).convert("RGB") for p in batch]
    width = max(im.width for im in opened)
    height = max(im.height for im in opened)
    sheet = Image.new("RGB", (width * 3, (height + 34) * 3), "white")
    draw = ImageDraw.Draw(sheet)
    for idx, (path, im) in enumerate(zip(batch, opened)):
        x = (idx % 3) * width
        y = (idx // 3) * (height + 34)
        draw.text((x + 8, y + 8), path.stem, fill="black")
        sheet.paste(im, (x, y + 34))
    sheet.save(root / f"contact-{batch_no // 9 + 1}.jpg", quality=88)
