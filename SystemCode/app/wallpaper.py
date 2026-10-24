"""A vintage, faded wallpaper of the seven Culture Pass event categories, drawn as one repeating SVG tile.

Motifs, each in its category's card colour: Heritage (shophouse facade), Visual Arts (palette and brush),
Theatre (comedy and tragedy masks), Music (musical notes), Dance (folding fan), Films (film reel) and
Literary Arts (open book and quill). Line art in faded colours on aged paper, with a light grain.
"""
import base64
import math

PAPER = "#F1E6D2"
STRIPE = "#EADCC3"
GOLD = "#B88A2E"      # Heritage
BLUE = "#3F5F8F"      # Visual Arts
PLUM = "#7E4A8E"      # Theatre
CORAL = "#B5483C"     # Music
ROSE = "#A84A72"      # Dance
SLATE = "#56626E"     # Films
JADE = "#2F7A70"      # Literary Arts


def _g(x, y, rot, colour, body, width=1.7):
    return (f'<g transform="translate({x},{y}) rotate({rot})" stroke="{colour}" stroke-width="{width}" '
            f'fill="none" stroke-linecap="round" stroke-linejoin="round">{body}</g>')


def heritage(x, y, rot):
    c = GOLD
    return _g(x, y, rot, c,
              f'<path d="M-2,14 L25,0 L52,14"/><rect x="0" y="14" width="50" height="48" fill="{c}" fill-opacity=".1"/>'
              '<path d="M7,34 v-9 a6,6 0 0 1 12,0 v9 z M31,34 v-9 a6,6 0 0 1 12,0 v9 z"/>'
              '<path d="M0,38 H50"/><path d="M5,62 v-12 a20,9 0 0 1 40,0 v12"/><path d="M13,22 v-3 M25,20 v-3 M37,22 v-3"/>')


def visual_arts(x, y, rot):
    c = BLUE
    dots = "".join(f'<circle cx="{px}" cy="{py}" r="4" fill="{col}" fill-opacity=".55" stroke="none"/>'
                   for px, py, col in [(30, 10, CORAL), (43, 15, GOLD), (49, 27, JADE), (39, 37, PLUM)])
    return _g(x, y, rot, c,
              f'<path d="M30,0 C52,0 62,18 54,34 C48,46 30,48 22,42 C16,38 22,30 14,30 C4,30 0,22 4,14 C8,4 18,0 30,0 Z" '
              f'fill="{c}" fill-opacity=".1"/><circle cx="16" cy="17" r="4"/>{dots}'
              '<path d="M44,58 L72,22"/><path d="M72,22 l4,-6 l-1,8 z" fill="#5B4636" stroke="#5B4636"/>')


def theatre(x, y, rot):
    c = PLUM
    mask = 'M0,0 Q20,-5 40,0 Q42,26 20,40 Q-2,26 0,0 Z'
    happy = (f'<path d="{mask}" fill="{c}" fill-opacity=".1"/><ellipse cx="12" cy="13" rx="4" ry="3"/>'
             '<ellipse cx="28" cy="13" rx="4" ry="3"/><path d="M11,24 Q20,33 29,24"/>')
    sad = (f'<path d="{mask}" fill="{c}" fill-opacity=".16"/><ellipse cx="12" cy="13" rx="4" ry="3"/>'
           '<ellipse cx="28" cy="13" rx="4" ry="3"/><path d="M11,30 Q20,22 29,30"/>')
    return _g(x, y, rot, c, f'<g>{happy}</g><g transform="translate(26,14) rotate(16)">{sad}</g>')


def music(x, y, rot, scale=1.0):
    c = CORAL
    return _g(x, y, rot, c,
              f'<g transform="scale({scale})">'
              f'<ellipse cx="0" cy="40" rx="7" ry="5" transform="rotate(-20 0 40)" fill="{c}" fill-opacity=".55"/>'
              f'<ellipse cx="26" cy="34" rx="7" ry="5" transform="rotate(-20 26 34)" fill="{c}" fill-opacity=".55"/>'
              f'<path d="M6,38 V6 M32,32 V0"/><path d="M6,6 L32,0 L32,7 L6,13 Z" fill="{c}" fill-opacity=".55"/></g>')


def dance(x, y, rot):
    c = ROSE
    cx, cy, r_out, r_in = 32, 50, 46, 14
    angles = [math.radians(a) for a in range(200, 341, 20)]
    pts = lambda r, a: (cx + r * math.cos(a), cy + r * math.sin(a))
    o0, o1 = pts(r_out, angles[0]), pts(r_out, angles[-1])
    i0, i1 = pts(r_in, angles[0]), pts(r_in, angles[-1])
    leaf = (f'M{i0[0]:.1f},{i0[1]:.1f} L{o0[0]:.1f},{o0[1]:.1f} A{r_out},{r_out} 0 0 1 {o1[0]:.1f},{o1[1]:.1f} '
            f'L{i1[0]:.1f},{i1[1]:.1f} A{r_in},{r_in} 0 0 0 {i0[0]:.1f},{i0[1]:.1f} Z')
    ribs = " ".join(f'M{cx},{cy} L{pts(r_out, a)[0]:.1f},{pts(r_out, a)[1]:.1f}' for a in angles)
    return _g(x, y, rot, c, f'<path d="{leaf}" fill="{c}" fill-opacity=".14"/><path d="{ribs}" stroke-width="1.1"/>'
                            f'<circle cx="{cx}" cy="{cy}" r="2.5" fill="{c}"/><path d="M{cx},{cy} q4,10 -2,16"/>')


def films(x, y, rot):
    c = SLATE
    holes = "".join(f'<circle cx="{24 + 13 * math.cos(math.radians(a)):.1f}" cy="{24 + 13 * math.sin(math.radians(a)):.1f}" r="5"/>'
                    for a in range(-90, 270, 72))
    sprockets = "".join(f'<rect x="{52 + i * 9}" y="38" width="4" height="3"/><rect x="{52 + i * 9}" y="49" width="4" height="3"/>'
                        for i in range(3))
    return _g(x, y, rot, c, f'<circle cx="24" cy="24" r="24" fill="{c}" fill-opacity=".1"/>{holes}<circle cx="24" cy="24" r="3"/>'
                            f'<path d="M40,42 H80 V56 H44" fill="{c}" fill-opacity=".1"/>{sprockets}')


def literary_arts(x, y, rot):
    c = JADE
    lines = "".join(f'<path d="M5,{14 + i * 6} Q16,{9 + i * 6} 28,{14 + i * 6}" stroke-width="1"/>'
                    f'<path d="M36,{14 + i * 6} Q48,{9 + i * 6} 59,{14 + i * 6}" stroke-width="1"/>' for i in range(4))
    return _g(x, y, rot, c,
              f'<path d="M0,8 Q16,0 32,8 L32,46 Q16,38 0,46 Z" fill="{c}" fill-opacity=".1"/>'
              f'<path d="M32,8 Q48,0 64,8 L64,46 Q48,38 32,46 Z" fill="{c}" fill-opacity=".1"/>{lines}'
              '<path d="M58,40 C66,24 76,10 88,2 C84,16 74,30 60,42 Z" fill="#E8DCC4" stroke="#5B4636"/>'
              '<path d="M60,42 L56,50" stroke="#5B4636"/>')


def _sprig(x, y):
    return (f'<g transform="translate({x},{y})" stroke="{GOLD}" stroke-width="1.2" stroke-opacity=".7">'
            '<path d="M-4,0 H4 M0,-4 V4"/></g>')


def tile_svg(size: int = 380) -> str:
    motifs = [
        visual_arts(30, 34, -8), heritage(215, 22, 4), theatre(112, 150, 8), music(282, 150, -6),
        dance(10, 232, 4), films(188, 262, -5), literary_arts(270, 300, 6), music(96, 318, 12, 0.7),
    ]
    sprigs = "".join(_sprig(px, py) for px, py in [(160, 70), (340, 96), (70, 190), (250, 118), (330, 250), (150, 240), (40, 350), (230, 360)])
    stripes = "".join(f'<rect x="{i}" y="0" width="22" height="{size}" fill="{STRIPE}" fill-opacity=".55"/>' for i in range(0, size, 63))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
            f'<defs><filter id="grain"><feTurbulence type="fractalNoise" baseFrequency=".85" numOctaves="2" seed="7"/>'
            f'<feColorMatrix values="0 0 0 0 .45  0 0 0 0 .36  0 0 0 0 .24  0 0 0 .09 0"/></filter></defs>'
            f'<rect width="{size}" height="{size}" fill="{PAPER}"/>{stripes}'
            f'<g opacity=".55">{"".join(motifs)}{sprigs}</g>'
            f'<rect width="{size}" height="{size}" filter="url(#grain)"/></svg>')


def css_background() -> str:
    data = base64.b64encode(tile_svg().encode()).decode()
    return (f'background-color: {PAPER}; '
            f'background-image: radial-gradient(ellipse at center, rgba(241,230,210,0) 55%, rgba(120,90,50,.16) 100%), '
            f'url("data:image/svg+xml;base64,{data}"); '
            f'background-size: 100% 100%, 380px 380px; background-attachment: fixed, scroll;')
