"""Render the 1200x630 social preview (og:image) from the page posters."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W, H = 1200, 630
img = Image.new("RGB", (W, H), (255, 255, 255))
d = ImageDraw.Draw(img)


def font(size, bold=False):
    for path, idx in [("/System/Library/Fonts/HelveticaNeue.ttc", 1 if bold else 0),
                      ("/System/Library/Fonts/Helvetica.ttc", 1 if bold else 0)]:
        try:
            return ImageFont.truetype(path, size, index=idx)
        except OSError:
            continue
    return ImageFont.load_default()


d.rectangle([0, 0, W, 10], fill=(179, 192, 224))
d.text((64, 92), "RadWorld", font=font(92, True), fill=(28, 29, 34))
y = 208
for line in ["A World Foundation Model for", "3D Tomographic Medical Imaging"]:
    d.text((66, y), line, font=font(38), fill=(43, 46, 56))
    y += 48
d.text((66, 350), "Pretrained on 232,781 curated CT and MRI scans", font=font(26), fill=(85, 91, 107))
d.text((66, 388), "from 152 datasets across 23 countries", font=font(26), fill=(85, 91, 107))
d.text((66, 520), "Browse generated 3D volumes and take the visual Turing test", font=font(24), fill=(72, 72, 120))

tiles = ["assets/img/teaser/gen_abdomen_0_still.webp",
         "assets/img/poster/extra/pretrain_ct_0_axial.webp",
         "assets/img/poster/translation/mr2ct_mr2ct_radworld_axial.webp",
         "assets/img/poster/extra/pretrain_mr_0_axial.webp"]
S, G, X0, Y0 = 232, 12, 700, 75
for n, t in enumerate(tiles):
    im = Image.open(ROOT / t).convert("RGB")
    im.thumbnail((S, S))
    tile = Image.new("RGB", (S, S), (0, 0, 0))
    tile.paste(im, ((S - im.width) // 2, (S - im.height) // 2))
    x, yy = X0 + (n % 2) * (S + G), Y0 + (n // 2) * (S + G)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], 14, fill=255)
    img.paste(tile, (x, yy), mask)
out = ROOT / "assets/img/social.png"
img.save(out, optimize=True)
print(out, out.stat().st_size // 1024, "KB")
