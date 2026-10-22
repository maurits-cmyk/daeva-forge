"""Draw the link-preview image (Open Graph / Twitter card, 1200x630) as app/og.png.

  python make_og.py   # needs Pillow and the Windows fonts Constantia + Segoe UI
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import make_favicon as mf

APP = Path(__file__).parent / 'app'
W, H, S = 1200, 630, 2                       # drawn at 2x, then scaled down for smooth edges
FONTS = Path('C:/Windows/Fonts')


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size * S)


img = Image.new('RGBA', (W * S, H * S), (0x08, 0x09, 0x0c, 255))
# soft slate glow behind the emblem, like the site's stage
glow = Image.new('RGBA', img.size)
ImageDraw.Draw(glow).ellipse([60 * S, 40 * S, 640 * S, 600 * S], fill=(60, 80, 105, 120))
img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(90 * S)))

mf.SS = 1024; mf.K = mf.SS / 40
emblem = mf.draw(ring_alpha=255).resize((300 * S, 300 * S), Image.LANCZOS)
img.alpha_composite(emblem, (110 * S, 165 * S))

d = ImageDraw.Draw(img)
x = 470 * S
d.text((x, 190 * S), 'Daeva Forge', font=font('constan.ttf', 96), fill=(232, 236, 242, 255))
d.line([(x, 318 * S), (x + 560 * S, 318 * S)], fill=(242, 196, 67, 255), width=2 * S)
tagline = 'AION 2 CRAFTING CALCULATOR'
tx = x
for ch in tagline:                           # letter-spaced capitals, like the site's headings
    d.text((tx, 342 * S), ch, font=font('segoeuib.ttf', 30), fill=(159, 212, 255, 255))
    tx += d.textlength(ch, font=font('segoeuib.ttf', 30)) + 5 * S
d.text((x, 398 * S), 'Real Kina cost from your server\'s market prices', font=font('segoeui.ttf', 30), fill=(160, 170, 182, 255))
d.text((x, 538 * S), 'daevaforge.com  ·  unofficial fan site', font=font('segoeui.ttf', 22), fill=(110, 120, 132, 255))

img.resize((W, H), Image.LANCZOS).convert('RGB').save(APP / 'og.png', optimize=True)
print('wrote app/og.png')
