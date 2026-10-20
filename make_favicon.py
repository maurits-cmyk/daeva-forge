"""Draw the Daeva Forge favicon (same shapes as app/favicon.svg) as PNG/ICO with Pillow.

  python make_favicon.py   # writes app/favicon.ico (16/32/48) and app/apple-touch-icon.png (180)
"""
from pathlib import Path
from PIL import Image, ImageDraw

APP = Path(__file__).parent / 'app'
SS = 1024  # drawing size; downscaled for each icon
K = SS / 40  # svg units → pixels


def bezier(p0, p1, p2, p3, n=24):
    return [tuple((1-t)**3*a + 3*(1-t)**2*t*b + 3*(1-t)*t**2*c + t**3*d for a, b, c, d in zip(p0, p1, p2, p3))
            for t in (i / n for i in range(1, n + 1))]


def draw(background=None):
    img = Image.new('RGBA', (SS, SS), background or (0, 0, 0, 0))
    # disc with the radial gradient (#2b3340 → #0d1015), centre (20, 18.1), radius 20.6
    disc = Image.new('RGBA', (SS, SS))
    px = disc.load()
    cx, cy, r = 20 * K, 18.125 * K, 20.625 * K
    a, b = (0x2b, 0x33, 0x40), (0x0d, 0x10, 0x15)
    for y in range(SS):
        for x in range(SS):
            t = min(1, ((x - cx) ** 2 + (y - cy) ** 2) ** .5 / r)
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)
    mask = Image.new('L', (SS, SS))
    ImageDraw.Draw(mask).ellipse([(20 - 18.75) * K, (20 - 18.75) * K, (20 + 18.75) * K, (20 + 18.75) * K], fill=255)
    img.alpha_composite(Image.composite(disc, Image.new('RGBA', (SS, SS)), mask))
    # cyan ring: r 18.75, width 2.5, 85% opacity
    ring = Image.new('RGBA', (SS, SS))
    ImageDraw.Draw(ring).ellipse([0, 0, SS - 1, SS - 1], outline=(0x5f, 0xd6, 0xe8, 217), width=round(2.5 * K))
    img.alpha_composite(ring)
    d = ImageDraw.Draw(img)
    # anvil: the emblem path, scaled 1.13 and nudged (translate(-2.6 -1.4))
    pts = [(11, 18), (25, 18), (27, 15), (30, 15), (28, 20), (25, 20), (24, 22), (20, 22), (22, 27), (26, 27),
           (26, 29), (13, 29), (13, 27), (17, 27), (19, 22), (16, 22)] + bezier((16, 22), (13, 22), (11, 20), (11, 18))
    d.polygon([((x * 1.13 - 2.6) * K, (y * 1.13 - 1.4) * K) for x, y in pts], fill=(0xe7, 0xea, 0xee, 255))
    # cyan four-point sparkle
    star = [(30, 5.8), (31.1, 8.2), (33.5, 9.3), (31.1, 10.4), (30, 12.8), (28.9, 10.4), (26.5, 9.3), (28.9, 8.2)]
    d.polygon([(x * K, y * K) for x, y in star], fill=(0x5f, 0xd6, 0xe8, 255))
    return img


if __name__ == '__main__':
    icon = draw()
    icon.save(APP / 'favicon.ico', sizes=[(16, 16), (32, 32), (48, 48)])
    # iOS home screen: opaque, on the page's near-black stage with some breathing room
    touch = Image.new('RGBA', (180, 180), (0x08, 0x09, 0x0c, 255))
    touch.alpha_composite(icon.resize((150, 150), Image.LANCZOS), (15, 15))
    touch.convert('RGB').save(APP / 'apple-touch-icon.png')
    print('wrote favicon.ico, apple-touch-icon.png')
