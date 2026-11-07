"""Renders weather/{sun,moon,clouds,rain}.svg: a fastfetch card with an ASCII-style landscape under the current weather."""
import html
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "weather"

W, H, P = 128, 102, 3  # glyph grid and its pitch in px
AX, AY = 28, 62  # art origin
HZ, LAKE_END = 60, 88  # waterline under the hills; the reflection is drawn down to LAKE_END and the meadow covers the rest
CARD_W, CARD_H = 760, 430
SIZES = (0.7, 1.2, 1.7, 2.3, 2.9)  # glyph weights, dim to bright

SCENES = {
    "sun": "sunny here now",
    "moon": "clear night here now",
    "clouds": "cloudy here now",
    "rain": "raining here now",
}

LOOKS = {
    "sun": dict(sky=[(0, (30, 20, 56)), (.35, (96, 44, 98)), (.62, (204, 92, 108)), (.84, (246, 150, 86)), (1, (255, 210, 136))],
                layers=[(176, 104, 128), (122, 66, 104), (76, 40, 74)], mist=(255, 196, 176), rim=(255, 214, 168),
                ground=(40, 26, 34), blades=[(150, 92, 72), (198, 128, 82), (118, 74, 66)], flowers=[(255, 190, 120), (255, 232, 170)],
                shimmer=(255, 216, 160), sway=3),
    "moon": dict(sky=[(0, (2, 4, 12)), (.6, (8, 16, 40)), (1, (26, 42, 86))],
                 layers=[(52, 66, 112), (34, 46, 84), (20, 28, 56)], mist=(70, 90, 140), rim=(150, 170, 230),
                 ground=(8, 12, 24), blades=[(34, 52, 82), (46, 68, 100), (26, 40, 66)], flowers=[(120, 130, 180)],
                 shimmer=(170, 190, 240), sway=2),
    "clouds": dict(sky=[(0, (26, 30, 40)), (.6, (60, 66, 82)), (1, (92, 98, 112))],
                   layers=[(92, 98, 114), (66, 72, 88), (44, 50, 62)], mist=(156, 162, 176), rim=(140, 146, 160),
                   ground=(16, 20, 22), blades=[(62, 80, 64), (80, 98, 76), (50, 64, 54)], flowers=[(170, 140, 150), (176, 176, 140)],
                   shimmer=(170, 178, 196), sway=5),
    "rain": dict(sky=[(0, (6, 8, 16)), (.7, (14, 18, 32)), (1, (26, 30, 50))],
                 layers=[(50, 54, 86), (34, 36, 62), (22, 24, 42)], mist=(76, 76, 118), rim=(96, 96, 150),
                 ground=(8, 10, 16), blades=[(32, 42, 56), (42, 54, 68), (26, 34, 46)], flowers=[(80, 80, 112)],
                 shimmer=(130, 136, 200), sway=7),
}


def px(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def X(x):
    return px(AX + (x + 0.5) * P)


def Y(y):
    return px(AY + (y + 0.5) * P)


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def add(a, b, k):
    return tuple(min(255, round(a[i] + b[i] * k)) for i in range(3))


def ramp(stops, t):
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if t <= p1:
            return mix(c0, c1, (t - p0) / (p1 - p0))
    return stops[-1][1]


def shore(x):
    return 84 + 1.5 * math.sin(x / 13 + 1) + 0.8 * math.sin(x / 5)


def water(x, y):
    return HZ <= y < shore(x)


def ridge(base, amp, a, b, x):
    return base + amp * math.sin(x / 15 + a) + amp * 0.45 * math.sin(x / 6 + b) + amp * .2 * math.sin(x / 2.5 + a * b)


def glow(img, cx, cy, radius, color, strength=1.0, power=2.0):
    """Adds light around a point, fading to nothing at radius."""
    for y in range(max(0, int(cy - radius)), min(img.height, int(cy + radius) + 2)):
        for x in range(max(0, int(cx - radius)), min(img.width, int(cx + radius) + 2)):
            d = math.hypot(x - cx, y - cy) / radius
            if d < 1:
                p = img.getpixel((x, y))
                img.putpixel((x, y), add(p[:3], color, strength * (1 - d) ** power) + p[3:])


def tile_noise(seed):
    """Fractal value noise in [0, 1] that wraps around horizontally, so drifting layers loop seamlessly."""
    rnd = random.Random(seed)
    octaves = [(cell, [[rnd.random() for _ in range(W // cell)] for _ in range(H // cell + 2)]) for cell in (16, 8, 4)]

    def smooth(t):
        return t * t * (3 - 2 * t)

    def f(x, y):
        value = total = 0.0
        for i, (cell, grid) in enumerate(octaves):
            n, gx, gy = len(grid[0]), x / cell, max(0.0, y / cell)
            x0, y0 = int(gx), int(gy)
            tx, ty = smooth(gx - x0), smooth(gy - y0)
            top = grid[y0][x0 % n] + (grid[y0][(x0 + 1) % n] - grid[y0][x0 % n]) * tx
            low = grid[y0 + 1][x0 % n] + (grid[y0 + 1][(x0 + 1) % n] - grid[y0 + 1][x0 % n]) * tx
            value += 0.5 ** i * (top + (low - top) * ty)
            total += 0.5 ** i
        return value / total

    return f


def glyphs(img, floor=0.012, dash=lambda x, y: False):
    """Turns an image into glyphs: dots, or horizontal dashes where dash(x, y) says the cell is water.

    Brightness sets the glyph weight and the pixel sets its hue; black or clear cells stay empty.
    """
    groups, alpha = {}, img.mode == "RGBA"
    for y in range(img.height):
        for x in range(img.width):
            p = img.getpixel((x, y))
            a = p[3] / 255 if alpha else 1
            r, g, b = p[:3]
            lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 * a
            if lum < floor:
                continue
            level = min(len(SIZES) - 1, int(lum ** 0.7 * len(SIZES)))
            boost = 0.45 + 0.55 * min(2.5, 235 / (max(r, g, b) or 1))  # brightness lives in the weight, so keep hue vivid
            color = "#" + "".join(f"{min(248, round(c * boost)) // 8 * 8:02x}" for c in (r, g, b))
            if dash(x, y):
                length, width = 1.4 + level * .3, px(SIZES[level] * .55)
                groups.setdefault((width, color), []).append(f"M{px(AX + (x + .5) * P - length / 2)} {Y(y)}h{px(length)}")
            else:
                groups.setdefault((px(SIZES[level]), color), []).append(f"M{X(x)} {Y(y)}h0")
    return [f'<path stroke="{c}" stroke-width="{s}" d="{"".join(d)}"/>' for (s, c), d in sorted(groups.items())]


def layer():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def group(cls, paths, style=""):
    attr = f' style="{style}"' if style else ""
    return f'<g class="{cls}"{attr}>{"".join(paths)}</g>'


def timed(rnd, low, high):
    dur = rnd.uniform(low, high)
    return f"animation-duration:{dur:.2f}s;animation-delay:-{rnd.uniform(0, dur):.2f}s"


def twinkle(rnd, img, parts=3):
    """Splits a layer into a few groups that pulse out of step."""
    pieces = [layer() for _ in range(parts)]
    for y in range(H):
        for x in range(W):
            p = img.getpixel((x, y))
            if p[3]:
                pieces[rnd.randrange(parts)].putpixel((x, y), p)
    return [group("tw", glyphs(piece, dash=water), timed(rnd, 1.6, 3.6)) for piece in pieces]


def drifting(img, period, cls="drift"):
    """A layer that glides left, with a copy behind it so it wraps without a seam."""
    paths = "".join(glyphs(img, dash=water))
    return f'<g class="{cls}" style="animation-duration:{period}s">{paths}<g transform="translate({W * P} 0)">{paths}</g></g>'


def backing(img):
    """Black rects behind the opaque cells of a layer, so whatever drifts behind it stays hidden."""
    rects = []
    for y in range(H):
        x = 0
        while x < W:
            if img.getpixel((x, y))[3]:
                start = x
                while x < W and img.getpixel((x, y))[3]:
                    x += 1
                rects.append(f'<rect x="{px(AX + start * P)}" y="{px(AY + y * P)}" width="{(x - start) * P}" height="{P}"/>')
            x += 1
    return rects


def clouds_layer(seed, top, bottom, dark, light, coverage, flat=1.5, alpha=1.0):
    """Cloud masses lit from above; a higher flat gives them the level bases of cumulus."""
    noise, img, floor = tile_noise(seed), layer(), 1 - coverage
    for y in range(top, bottom):
        fade = 1 - ((y - top) / (bottom - top)) ** flat
        for x in range(W):
            n = noise(x, y)
            d = (n - floor) / coverage * fade
            if d > 0:
                rim = (noise(x, y + 2) - n) * 6  # brighter where the mass begins, darker toward its belly
                img.putpixel((x, y), mix(dark, light, d * 1.3 + rim) + (round(min(1, d * 4) * 255 * alpha),))
    return img


def mirror_into_lake(img):
    """Copies everything above the waterline into the lake, darker, bluer and broken by small waves."""
    for y in range(HZ, LAKE_END):
        src, wave = 2 * HZ - 1 - y, (y // 2) % 2
        for x in range(W):
            p = img.getpixel((min(W - 1, x + wave), src))
            if len(p) == 4 and not p[3]:
                continue
            k = .5 if y % 2 else .4
            img.putpixel((x, y), (round(p[0] * k), round(p[1] * k), min(255, round(p[2] * k * 1.2))) + p[3:])
    return img


def sky_image(look):
    sky = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(sky)
    for y in range(HZ):
        d.line([(0, y), (W - 1, y)], fill=ramp(look["sky"], y / (HZ - 1)))
    return sky


def lake_sky(sky, *cloud_layers):
    """Sky with clouds baked in, mirrored into the lake; uniform across, so it can drift as one piece."""
    sky = sky.convert("RGBA")
    for clouds in cloud_layers:
        sky = Image.alpha_composite(sky, clouds)
    sky = mirror_into_lake(sky)
    for y in range(LAKE_END, H):
        for x in range(W):
            sky.putpixel((x, y), (0, 0, 0, 0))
    return sky


def landscape(look, rnd):
    """Three ranges fading into the haze, mirrored on the lake, and the meadow's soil in front."""
    img = layer()
    ranges = [(42, 7, 1, 2), (49, 5, 3, 5), (55, 2.5, 4, 1)]
    for (base, amp, a, b), color in zip(ranges, look["layers"]):
        for x in range(W):
            top = ridge(base, amp, a, b, x)
            for y in range(math.ceil(top), HZ):
                fog = (y - top) / max(1, HZ - top)
                c = mix(color, look["mist"], fog * .45)
                if base == 55 and (y + x // 9) % 2:
                    c = mix(c, look["layers"][1], .4)  # rows of crops on the nearest hills
                img.putpixel((x, y), c)
            img.putpixel((x, math.ceil(top)), mix(color, look["rim"], .6))
    mirror_into_lake(img)
    for x in range(W):
        for y in range(math.ceil(shore(x)), H):
            img.putpixel((x, y), mix(look["ground"], look["blades"][0], .25 if rnd.random() < .3 else .05))
    return img


def grass(look, rnd):
    """Blades of grass leaning with the wind, taller toward the viewer, in three groups that sway out of step."""
    groups = [{} for _ in range(3)]
    bias = look["sway"] * .25
    for x in range(W):
        edge = shore(x)
        for y in range(math.ceil(edge), H):
            if rnd.random() > .55:
                continue
            t = (y - edge) / (H - edge)
            height, lean = 4 + t * 16 + rnd.uniform(-2, 2), rnd.uniform(-1.5, 1.5) + bias
            color = mix(rnd.choice(look["blades"]), look["ground"], .45 * (1 - t))
            hexc = "#" + "".join(f"{c // 8 * 8:02x}" for c in color)
            base_x, base_y = AX + (x + rnd.random()) * P, AY + (y + .9) * P
            g = groups[rnd.randrange(3)]
            g.setdefault(hexc, []).append(f"M{px(base_x)} {px(base_y)}l{px(lean)} -{px(height)}")
            if rnd.random() < .04:
                tip = rnd.choice(look["flowers"])
                g.setdefault(f"tip#{''.join(f'{c:02x}' for c in tip)}", []).append(f"M{px(base_x + lean)} {px(base_y - height)}h0")
    out = []
    for i, g in enumerate(groups):
        paths = [f'<path stroke="{k[3:]}" stroke-width="1.6" d="{"".join(d)}"/>' if k.startswith("tip") else
                 f'<path stroke="{k}" stroke-width=".8" d="{"".join(d)}"/>' for k, d in sorted(g.items())]
        out.append(group("blades", paths, f"animation-duration:{3.5 + i * .9:.1f}s;animation-delay:-{i * 1.3:.1f}s"))
    return out


def bolt(rnd, x, top, bottom):
    """A jagged lightning path with a couple of short forks."""
    cells, y, forks = set(), top, []
    while y < bottom:
        cells.add((round(x), y))
        if rnd.random() < 0.12:
            forks.append((x, y))
        x += rnd.choice((-1, -1, 0, 1, 1, 2, -2)) * 0.8
        y += 1
    for fx, fy in forks[:3]:
        dx = rnd.choice((-1, 1))
        for _ in range(rnd.randint(5, 10)):
            fx, fy = fx + dx * rnd.uniform(.5, 1.5), fy + 1
            cells.add((round(fx), fy))
    img = layer()
    for cx, cy in cells:
        for ox in (-1, 0, 1):
            if 0 <= cx + ox < W and 0 <= cy < H:
                img.putpixel((cx + ox, cy), (240, 236, 255, 255) if ox == 0 else (130, 120, 220, 150))
    return img


def column(rnd, cx, spread, color, chance):
    """Sparkles on the water under a light source, spreading toward the viewer."""
    img = layer()
    for y in range(HZ + 1, LAKE_END):
        half = spread + (y - HZ) * .25
        for x in range(round(cx - half), round(cx + half) + 1):
            if 0 <= x < W and water(x, y) and rnd.random() < chance * (1 - abs(x - cx) / (half + 1)):
                img.putpixel((x, y), color + (230,))
    return img


def sunrise(look, rnd, sky):
    sx, sy = 30, 45
    for y in range(HZ):
        for x in range(W):
            angle = math.atan2(sy - y, x - sx)
            if 0 < angle < math.pi and math.sin(angle * 14) > .82:  # rays fanning out above the horizon
                sky.putpixel((x, y), add(sky.getpixel((x, y)), (255, 170, 110), .1 * max(0, 1 - math.hypot(x - sx, y - sy) / 90)))
    glow(sky, sx, sy, 50, (255, 140, 70), .65, 1.6)
    glow(sky, sx, sy, 14, (255, 230, 170), .8, 1.2)
    for y in range(sy - 8, sy + 9):
        for x in range(sx - 8, sx + 9):
            if math.hypot(x - sx, y - sy) <= 6.5:
                sky.putpixel((x, y), (255, 246, 220))
    behind = [drifting(clouds_layer(21, 4, 36, (120, 56, 100), (255, 180, 150), .3), 140)]
    front = twinkle(rnd, column(rnd, sx, 2, (255, 226, 168), .45))
    for i in range(3):
        y, dur = 16 + i * 6, 30 + i * 8
        front.append(f'<path class="bird" d="M{AX - 12} {px(AY + y * P)}l2.4 1.8l2.4-1.8" '
                     f'style="animation-duration:{dur}s;animation-delay:-{i * 11}s"/>')
    return behind, front, []


def starry_night(look, rnd, sky):
    noise = tile_noise(77)
    for y in range(HZ):
        for x in range(W):
            dist = abs(y - (50 - x * .36)) / 10  # the Milky Way, rising to the right
            if dist < 1:
                k = (1 - dist) ** 1.6 * (.4 + noise(x, y) * .9)
                sky.putpixel((x, y), add(sky.getpixel((x, y)), (86, 74, 140), k * .7))
                if rnd.random() < k * .12:
                    sky.putpixel((x, y), mix((110, 120, 180), (220, 226, 255), rnd.random()))
    for _ in range(140):
        x, y = rnd.randrange(W), rnd.randrange(HZ - 6)
        sky.putpixel((x, y), mix((60, 80, 130), (230, 238, 255), rnd.random()))
    mx, my = 20, 14
    glow(sky, mx, my, 22, (44, 56, 100), .9)
    for y in range(my - 7, my + 8):
        for x in range(mx - 7, mx + 8):
            dist = math.hypot(x - mx, y - my)
            if dist <= 6:
                crater = (x, y) in {(18, 12), (22, 16), (21, 11), (17, 16)}
                sky.putpixel((x, y), (206, 202, 186) if crater else mix((252, 248, 228), (214, 210, 194), dist / 6))
    behind = [drifting(clouds_layer(31, 20, 44, (16, 24, 50), (60, 80, 128), .2), 200)]
    stars = layer()
    for _ in range(34):
        stars.putpixel((rnd.randrange(W), rnd.randrange(HZ - 8)), (255, 255, 255, 255))
    front = twinkle(rnd, stars) + twinkle(rnd, column(rnd, mx, 1.5, (236, 232, 206), .4))
    for i in range(16):
        x, y = AX + rnd.uniform(6, 122) * P, AY + rnd.uniform(78, 99) * P
        front.append(f'<g class="firefly f{i % 3}" style="{timed(rnd, 3, 6)}">'
                     f'<circle cx="{px(x)}" cy="{px(y)}" r="3.4" fill="#d6ec78" fill-opacity=".18"/>'
                     f'<circle cx="{px(x)}" cy="{px(y)}" r="1.1" fill="#eaf8a0"/></g>')
    streak = layer()
    for k in range(7):
        streak.putpixel((96 - k * 2, 6 + k), (255, 255, 255, 255 - k * 34))
    front.append(group("meteor", glyphs(streak)))
    keyframes = [
        "@keyframes f0 { 0%, 100% { transform: translate(0, 0); opacity: .2; } 50% { transform: translate(5px, -4px); opacity: 1; } }",
        "@keyframes f1 { 0%, 100% { transform: translate(0, 0); opacity: 1; } 50% { transform: translate(-6px, 3px); opacity: .15; } }",
        "@keyframes f2 { 0%, 100% { transform: translate(0, 0); opacity: .4; } 50% { transform: translate(3px, 5px); opacity: 1; } }",
    ]
    return behind, front, keyframes


def scene_svg(scene):
    rnd, look = random.Random(scene), LOOKS[scene]
    land = landscape(look, random.Random(3))
    sky = sky_image(look)
    art, front, keyframes = [], [], []

    if scene == "sun":
        behind, front, keyframes = sunrise(look, rnd, sky)
        art += [*glyphs(mirror_into_lake(sky.convert("RGBA")), dash=water), *behind]
    if scene == "moon":
        behind, front, keyframes = starry_night(look, rnd, sky)
        art += [*glyphs(mirror_into_lake(sky.convert("RGBA")), dash=water), *behind]
    if scene == "clouds":
        art.append(drifting(lake_sky(sky, clouds_layer(11, 0, 52, (70, 76, 94), (150, 156, 172), .55)), 150))
        art.append(drifting(clouds_layer(12, 2, 40, (118, 124, 142), (244, 246, 250), .42, flat=4), 70))
    if scene == "rain":
        art.append(drifting(lake_sky(sky, clouds_layer(7, 0, 50, (40, 36, 76), (200, 192, 255), .6)), 100))

    art += ['<g fill="#000">', *backing(land), "</g>", *glyphs(land, dash=water)]
    mist = clouds_layer(41, HZ - 9, HZ + 4, look["mist"], mix(look["mist"], (255, 255, 255), .3), .5, alpha=.45)
    art.append(drifting(mist, 90, "drift mist"))
    if scene != "sun":
        shimmer = layer()
        for _ in range(110):
            x, y = rnd.randrange(W), rnd.randrange(HZ + 1, LAKE_END)
            if water(x, y):
                shimmer.putpixel((x, y), look["shimmer"] + (110,))
        front += twinkle(rnd, shimmer)
    art += grass(look, random.Random(8))

    if scene == "rain":
        fall = 60 * P
        for _ in range(170):
            x0, dur = rnd.uniform(0, W * P + fall * .35), rnd.uniform(.5, .8)
            front.append(f'<path class="dr" d="M{px(AX + x0)} {px(AY + 22 * P)}l-1.6 4.5" '
                         f'style="animation-duration:{dur:.2f}s;animation-delay:-{rnd.uniform(0, dur):.2f}s"/>')
        for _ in range(26):
            x = rnd.uniform(2, W - 2)
            y = rnd.uniform(HZ + 3, shore(x) - 1)
            front.append(f'<ellipse class="ripple" cx="{px(AX + x * P)}" cy="{px(AY + y * P)}" rx="2.2" ry=".8" '
                         f'style="{timed(rnd, 1.1, 2.2)}"/>')
        for i, (x, period, delay) in enumerate([(24, 7.0, 1.5), (100, 11.0, 5.0)]):
            flash = f"animation-duration:{period}s;animation-delay:{delay}s"
            front.append(f'<rect class="flash sky" x="{AX}" y="{AY}" width="{W * P}" height="{H * P}" style="{flash}"/>')
            front.append(group("flash", glyphs(bolt(random.Random(i), x, 24, 46)), flash))
        keyframes.append(f"@keyframes fall {{ to {{ transform: translate(-{px(fall * .35)}px, {fall}px); }} }}")

    sway = look["sway"]
    keyframes.append(f"@keyframes sway {{ 0%, 100% {{ transform: skewX(-{sway * .3:.1f}deg); }} 50% {{ transform: skewX(-{sway:.1f}deg); }} }}")
    return card(SCENES[scene], [*art, *front], keyframes)


def card(weather_text, art, keyframes):
    info = [("role", "full-stack developer"), ("based", "são paulo, brazil"), ("os", "omarchy"), ("wm", "hyprland"),
            ("shell", "bash"), ("stack", "typescript · react · node"), ("now", "onne"), ("weather", weather_text),
            ("web", "allankayan.com")]
    ix, vx = 444, 520
    esc = html.escape
    lines = [f'<g class="o" style="animation-delay:{1.80 + i * 0.05:.2f}s"><text class="k" x="{ix}" y="{124 + i * 24}">{k}</text>'
             f'<text x="{vx}" y="{124 + i * 24}">{esc(v)}</text></g>' for i, (k, v) in enumerate(info)]
    blocks = [f'<rect x="{ix + i * 25.2:.1f}" y="340" width="25.2" height="17" fill="{color}"/>'
              for i, color in enumerate(["#505050", "#a4a4a4", "#b6b6b6", "#cecece", "#8d8d8d", "#9b9b9b", "#b0b0b0", "#ffffff"])]
    prompt = '<tspan class="g">allan@kayan</tspan><tspan>:</tspan><tspan class="b">~</tspan><tspan>$</tspan>'
    art_w, art_h = W * P, H * P
    nl = "\n  "
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_W}" height="{CARD_H}" viewBox="0 0 {CARD_W} {CARD_H}" fill="#ececec">
  <style>
    text {{ font: 14px 'JetBrains Mono', 'JetBrainsMono Nerd Font', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', 'Liberation Mono', monospace; }}
    .g {{ fill: #b6b6b6; }} .b {{ fill: #ffffff; font-weight: 700; }} .k {{ fill: #8d8d8d; font-weight: 700; }} .m {{ fill: #505050; }}
    .typing {{ animation: hide .01s 1.6s forwards; }}
    .type {{ animation: type .9s steps(9, end) .5s forwards; }}
    .cur {{ animation: blink 1.1s step-end infinite; }}
    .o {{ opacity: 0; animation: show .01s forwards; }}
    .cover {{ animation: wipe .6s steps(34, end) 1.65s forwards; }}
    .drift {{ animation: drift 120s linear infinite; }}
    .mist {{ opacity: .8; }}
    .blades {{ transform-box: view-box; transform-origin: 0 {AY + art_h}px; animation: sway 4s ease-in-out infinite; }}
    .dr {{ stroke: #7d8cc8; stroke-width: .7; stroke-opacity: .75; animation: fall .7s linear infinite; }}
    .ripple {{ fill: none; stroke: #9aa6e0; stroke-width: .6; opacity: 0; transform-box: fill-box; transform-origin: center; animation: ripple 1.6s ease-out infinite; }}
    .flash {{ opacity: 0; animation: flash 7s step-end infinite; }}
    .sky {{ fill: #c4bcff; fill-opacity: .12; }}
    .tw {{ animation: pulse 2.4s step-end infinite; }}
    .firefly {{ animation: f0 4s ease-in-out infinite; }} .f1 {{ animation-name: f1; }} .f2 {{ animation-name: f2; }}
    .meteor {{ opacity: 0; animation: meteor 13s linear 4s infinite; }}
    .bird {{ fill: none; stroke: #2a1730; stroke-width: .9; animation: fly 30s linear infinite; }}
    @keyframes hide {{ to {{ opacity: 0; }} }}
    @keyframes type {{ to {{ transform: translateX(75.6px); }} }}
    @keyframes blink {{ 50% {{ opacity: 0; }} }}
    @keyframes show {{ to {{ opacity: 1; }} }}
    @keyframes wipe {{ to {{ transform: translateY({art_h}px); }} }}
    @keyframes drift {{ to {{ transform: translateX(-{W * P}px); }} }}
    @keyframes ripple {{ 0% {{ opacity: .9; transform: scale(.3); }} 100% {{ opacity: 0; transform: scale(2.4); }} }}
    @keyframes flash {{ 0% {{ opacity: 1; }} 1.2% {{ opacity: 0; }} 2.4% {{ opacity: 1; }} 3.4% {{ opacity: 0; }} }}
    @keyframes pulse {{ 0% {{ opacity: 1; }} 50% {{ opacity: .25; }} }}
    @keyframes meteor {{ 0% {{ opacity: 1; transform: translate(0, 0); }} 6% {{ opacity: 0; transform: translate(-90px, 45px); }} 100% {{ opacity: 0; }} }}
    @keyframes fly {{ to {{ transform: translateX({W * P + 30}px); }} }}
    {nl.join(keyframes)}
    @media (prefers-reduced-motion: reduce) {{
      .typing, .cover {{ display: none; }}
      .o {{ animation: none; opacity: 1; }}
      .cur, .drift, .blades, .dr, .ripple, .flash, .tw, .firefly, .meteor, .bird {{ animation-play-state: paused; }}
    }}
  </style>
  <defs><clipPath id="clip"><rect x="{AX}" y="{AY}" width="{art_w}" height="{art_h}"/></clipPath></defs>

  <rect x="1" y="1" width="{CARD_W - 2}" height="{CARD_H - 2}" rx="10" fill="#000000" stroke="#8d8d8d" stroke-opacity=".5" stroke-width="2"/>

  <text x="28" y="48" textLength="117.6">{prompt}</text>
  <text x="154" y="48" textLength="75.6">fastfetch</text>
  <g class="typing">
    <g class="type">
      <rect x="154" y="33" width="90" height="21" fill="#000000"/>
      <rect class="cur" x="154" y="35" width="8.4" height="17" fill="#ffffff"/>
    </g>
  </g>

  <g clip-path="url(#clip)" stroke-linecap="round" fill="none">
  {nl.join(art)}
  <rect class="cover" x="{AX}" y="{AY}" width="{art_w}" height="{art_h}" fill="#000000"/>
  </g>

  <text class="o" style="animation-delay:1.70s" x="{ix}" y="80"><tspan class="b">allan</tspan><tspan>@</tspan><tspan class="b">kayan</tspan></text>
  <text class="o m" style="animation-delay:1.75s" x="{ix}" y="101">───────────</text>
  {nl.join(lines)}

  <g class="o" style="animation-delay:2.30s">
    {(nl + "  ").join(blocks)}
  </g>

  <g class="o" style="animation-delay:2.50s">
    <text x="28" y="408" textLength="117.6">{prompt}</text>
    <rect class="cur" x="154" y="395" width="8.4" height="17" fill="#ffffff"/>
  </g>
</svg>
"""


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name in SCENES:
        svg = scene_svg(name)
        (OUT / f"{name}.svg").write_text(svg)
        print(f"{name}.svg {len(svg) // 1024} KB")
