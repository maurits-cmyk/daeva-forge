"""Draw the link-preview images (Open Graph / Twitter card, 1200x630): the site's, app/og.png, and one per item
page, app/og/<item>.jpg (its name in its rarity colour; hosting.py uses it when it exists, else og.png).

  python make_og.py           # the site's image
  python make_og.py --items   # the item pages' images; run it again when items are added or renamed

Needs Pillow and the Windows fonts Constantia + Segoe UI, so it runs here, not in the hourly build.
"""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import make_favicon as mf

APP = Path(__file__).parent / 'app'
W, H, S = 1200, 630, 2                       # drawn at 2x, then scaled down for smooth edges
FONTS = Path('C:/Windows/Fonts')
GRADE = {'Common': (215, 218, 222), 'Rare': (95, 207, 108), 'Epic': (78, 168, 255), 'Legend': (78, 168, 255),
         'Unique': (242, 179, 61), 'Heroic': (255, 138, 61), 'Mythic': (192, 140, 255), 'Ancient': (192, 140, 255)}  # as in app/index.html
GOLD, BLUE, MUTED, DIM, INK = (242, 196, 67, 255), (159, 212, 255, 255), (160, 170, 182, 255), (110, 120, 132, 255), (232, 236, 242, 255)


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size * S)


def stage(glow_box):
    img = Image.new('RGBA', (W * S, H * S), (0x08, 0x09, 0x0c, 255))
    glow = Image.new('RGBA', img.size)   # soft slate glow, like the site's stage
    ImageDraw.Draw(glow).ellipse([v * S for v in glow_box], fill=(60, 80, 105, 120))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(90 * S)))
    return img


def emblem(size):
    mf.SS = 1024; mf.K = mf.SS / 40
    return mf.draw(ring_alpha=255).resize((size * S, size * S), Image.LANCZOS)


def spaced(d, xy, text, f, fill, gap):
    """Letter-spaced capitals, like the site's headings; returns the end x."""
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + gap * S
    return x


def site():
    img = stage((60, 40, 640, 600))
    img.alpha_composite(emblem(300), (110 * S, 165 * S))
    d = ImageDraw.Draw(img)
    x = 470 * S
    d.text((x, 190 * S), 'Daeva Forge', font=font('constan.ttf', 96), fill=INK)
    d.line([(x, 318 * S), (x + 560 * S, 318 * S)], fill=GOLD, width=2 * S)
    spaced(d, (x, 342 * S), 'AION 2 CRAFTING CALCULATOR', font('segoeuib.ttf', 30), BLUE, 5)
    d.text((x, 398 * S), 'Real Kina cost from your server\'s market prices', font=font('segoeui.ttf', 30), fill=MUTED)
    d.text((x, 538 * S), 'daevaforge.com  ·  unofficial fan site', font=font('segoeui.ttf', 22), fill=DIM)
    img.resize((W, H), Image.LANCZOS).convert('RGB').save(APP / 'og.png', optimize=True)
    print('wrote app/og.png')


def wrap(d, text, f, width):
    lines, line = [], ''
    for w in text.split():
        t = (line + ' ' + w).strip()
        if line and d.textlength(t, font=f) > width:
            lines.append(line); line = w
        else:
            line = t
    return lines + [line]


def item_image(p, out):
    img = stage((-120, -140, 520, 420))
    img.alpha_composite(emblem(96), (80 * S, 64 * S))
    d = ImageDraw.Draw(img)
    d.text((196 * S, 76 * S), 'Daeva Forge', font=font('constan.ttf', 46), fill=INK)
    spaced(d, (198 * S, 134 * S), 'AION 2 CRAFTING CALCULATOR', font('segoeuib.ttf', 17), BLUE, 3)
    # the item's name, as big as fits in two lines
    for size in (84, 76, 68, 60, 54):
        f = font('constan.ttf', size)
        lines = wrap(d, p['name'], f, 1040 * S)
        if len(lines) <= 2:
            break
    y, step = 205 * S, int(size * 1.18) * S
    if len(lines) == 1:
        y += step // 2
    for line in lines:
        d.text((80 * S, y), line, font=f, fill=GRADE.get(p['grade'], GRADE['Common']) + (255,))
        y += step
    y += 14 * S
    d.line([(80 * S, y), (640 * S, y)], fill=GOLD, width=2 * S)
    spaced(d, (80 * S, y + 18 * S), 'CRAFTING COST AND MATERIALS', font('segoeuib.ttf', 26), BLUE, 4)
    prof = ' · '.join(f'{k} {v[0]}' for k, v in sorted(p['profs'].items(), key=lambda kv: kv[1][1])[:2])
    races = p['races']
    who = '' if len(races) != 1 else ('  ·  Elyos' if 'Light' in races else '  ·  Asmodian')
    d.text((80 * S, y + 62 * S), prof + who, font=font('segoeui.ttf', 28), fill=MUTED)
    d.text((80 * S, 572 * S), 'daevaforge.com  ·  live market prices  ·  unofficial fan site', font=font('segoeui.ttf', 22), fill=DIM)
    img.resize((W, H), Image.LANCZOS).convert('RGB').save(out, quality=74, optimize=True, progressive=True)


def items():
    import hosting
    pages = hosting.item_pages(json.loads((APP / 'data.json').read_text(encoding='utf8')))
    (APP / 'og').mkdir(exist_ok=True)
    for slug, p in pages.items():
        item_image(p, APP / 'og' / f'{slug}.jpg')
    print(f'wrote {len(pages)} images to app/og/')


if __name__ == '__main__':
    items() if '--items' in sys.argv else site()
