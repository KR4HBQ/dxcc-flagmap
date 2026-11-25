"""Pillow renderers: Flag Counter-style grid and world map."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

from . import data
from .stats import EntityCount

THEMES = {
    "light": dict(bg=(200, 244, 255), fg=(20, 20, 20), ocean=(176, 216, 240), land=(222, 214, 190),
                  border=(60, 60, 60), line=(90, 90, 90), muted=(70, 90, 105)),
    "dark": dict(bg=(24, 28, 36), fg=(235, 235, 235), ocean=(18, 32, 56), land=(52, 66, 58),
                 border=(0, 0, 0), line=(200, 200, 200), muted=(150, 160, 175)),
}


# Small "get your own" line in the footer (turn off with credit=False / --no-credit).
CREDIT = "Get your own: github.com/KR4HBQ/wavelog-flagmap"


@dataclass
class GridOptions:
    title: str = "Worked DXCC"
    metric: str = "qsos"
    rows: int = 8            # entries per column (Flag Counter uses 8)
    max_entries: int = 48
    theme: str = "light"
    flag_w: int = 44
    flag_h: int = 33
    scale: int = 2           # supersampling factor for crisp text on high-dpi pages
    labels: str = "prefix"   # text under each count: "prefix" (K, VE, DL...) | "none"
    footer: bool = True
    footer_text: str | None = None
    credit: bool = True


# Latitude ranges (top, bottom). "cropped" drops the empty polar strips so flags can be larger;
# entities beyond it (Svalbard, Franz Josef Land, Antarctica...) are pinned to the edge.
MAP_VIEWS = {"cropped": (78.0, -56.0), "full": (84.0, -58.0)}


@dataclass
class MapOptions:
    title: str = ""
    width: int = 1600
    theme: str = "light"
    flag_w: int = 36         # sized for a 1600 px map shown at ~800 px in a QRZ bio
    flag_h: int = 27
    view: str = "cropped"    # see MAP_VIEWS
    lat_top: float | None = None     # override the view's range
    lat_bottom: float | None = None
    max_flags: int = 400
    footer: bool = True
    footer_text: str | None = None
    credit: bool = True
    extra: dict = field(default_factory=dict)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in (("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
                 ("arialbd.ttf" if bold else "arial.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1 (FreeType)
    except TypeError:  # pragma: no cover - ancient Pillow
        return ImageFont.load_default()


def _flag(iso: str, w: int, h: int) -> Image.Image:
    p = data.flag_path(iso)
    if p is not None:
        return Image.open(p).convert("RGBA").resize((w, h), Image.LANCZOS)
    ph = Image.new("RGBA", (w, h), (150, 150, 150, 255))  # entities without a national flag
    d = ImageDraw.Draw(ph)
    d.line([(0, 0), (w, h)], fill=(90, 90, 90, 255), width=max(1, w // 20))
    return ph


def _summary(rows: list[EntityCount]) -> str:
    return f"{len(rows)} entities / {sum(r.qsos for r in rows):,} QSOs"


# --------------------------------------------------------------------------- grid
def render_grid(rows: list[EntityCount], opt: GridOptions = GridOptions()) -> Image.Image:
    th = THEMES[opt.theme]
    s = opt.scale
    shown = rows[: opt.max_entries]
    cols = max(1, math.ceil(len(shown) / opt.rows))
    nrows = min(opt.rows, max(1, len(shown)))

    pad, gap_x, gap_y = 10 * s, 24 * s, 8 * s
    fw, fh = opt.flag_w * s, opt.flag_h * s
    labels = opt.labels == "prefix"
    f_title = _font(24 * s, True)
    f_num = _font((17 if labels else 19) * s, labels)
    f_lab = _font(13 * s)
    f_small = _font(13 * s)
    digits = max((len(f"{r.value(opt.metric):,}") for r in shown), default=1)
    lab_chars = max((len(r.entity.prefix) for r in shown), default=1) if labels else 0
    num_w = max(int(digits * 11.5 * s), int(lab_chars * 9 * s)) + 6 * s
    cell_w = fw + 8 * s + num_w
    title_h = 40 * s
    credit = opt.footer and opt.credit
    foot_h = (24 * s if opt.footer else 0) + (18 * s if credit else 0)
    w = pad * 2 + cols * cell_w + (cols - 1) * gap_x
    if credit:
        w = max(w, pad * 2 + int(f_small.getlength(CREDIT)))
    h = pad * 2 + title_h + nrows * fh + (nrows - 1) * gap_y + foot_h

    img = Image.new("RGB", (max(w, 260 * s), h), th["bg"])
    d = ImageDraw.Draw(img)
    d.text((pad, pad), opt.title, font=f_title, fill=th["fg"])
    for i, r in enumerate(shown):
        col, row = divmod(i, opt.rows)
        x = pad + col * (cell_w + gap_x)
        y = pad + title_h + row * (fh + gap_y)
        img.paste(_flag(r.entity.iso, fw, fh), (x, y))
        d.rectangle([x, y, x + fw - 1, y + fh - 1], outline=th["border"], width=max(1, s // 2))
        tx = x + fw + 8 * s
        if labels:
            d.text((tx, y + fh // 2 - 1 * s), f"{r.value(opt.metric):,}", font=f_num, fill=th["fg"], anchor="ls")
            d.text((tx, y + fh // 2 + 3 * s), r.entity.prefix, font=f_lab, fill=th["muted"], anchor="lt")
        else:
            d.text((tx, y + fh // 2), f"{r.value(opt.metric):,}", font=f_num, fill=th["fg"], anchor="lm")
    if opt.footer:
        label = opt.footer_text or _summary(rows)
        if opt.metric == "confirmed":
            label += " - ranked by confirmed QSOs"
        d.text((pad, h - pad - (18 * s if credit else 0)), label, font=f_small, fill=th["fg"], anchor="ld")
        if credit:
            d.text((pad, h - pad), CREDIT, font=f_small, fill=th["muted"], anchor="ld")
    return img.resize((img.width // s, img.height // s), Image.LANCZOS) if s > 1 else img


# --------------------------------------------------------------------------- map
def _project(lon: float, lat: float, w: int, top: float, bottom: float, h: int) -> tuple[float, float]:
    return (lon + 180.0) / 360.0 * w, (top - lat) / (top - bottom) * h


def _spread(points: list[list[float]], box_w: float, box_h: float, iters: int = 300,
            pull: float = 0.03, bounds: tuple[float, float] | None = None) -> list[list[float]]:
    """Separate flag boxes in crowded regions (Europe, Caribbean).

    Overlapping boxes are pushed apart along the axis where they overlap least (so flags
    stack in rows/columns instead of drifting diagonally), and every flag is pulled
    gently back toward its true position so clusters stay compact.
    """
    anchors = [p[:] for p in points]
    pos = [p[:] for p in points]
    n = len(pos)
    for it in range(iters):
        moved = False
        if bounds:  # keep every flag fully inside the image, so edge crowds spread inward
            for p in pos:
                p[0] = min(max(p[0], box_w / 2), bounds[0] - box_w / 2)
                p[1] = min(max(p[1], box_h / 2), bounds[1] - box_h / 2)
        for i in range(n):
            for j in range(i + 1, n):
                dx, dy = pos[j][0] - pos[i][0], pos[j][1] - pos[i][1]
                ox, oy = box_w - abs(dx), box_h - abs(dy)
                if ox <= 0 or oy <= 0:
                    continue
                moved = True
                if abs(dx) < 1e-6 and abs(dy) < 1e-6:
                    dx = 1.0 if (i + j) % 2 else -1.0
                if ox / box_w < oy / box_h:
                    push, sx = ox / 2 + 0.25, 1.0 if dx >= 0 else -1.0
                    pos[i][0] -= sx * push
                    pos[j][0] += sx * push
                else:
                    push, sy = oy / 2 + 0.25, 1.0 if dy >= 0 else -1.0
                    pos[i][1] -= sy * push
                    pos[j][1] += sy * push
        if not moved and it > 0:
            break
        if moved and it < iters - 20:  # stop pulling near the end so overlaps resolve fully
            for p, a in zip(pos, anchors):
                p[0] += (a[0] - p[0]) * pull
                p[1] += (a[1] - p[1]) * pull
    return pos


def render_map(rows: list[EntityCount], opt: MapOptions = MapOptions()) -> Image.Image:
    th = THEMES[opt.theme]
    if opt.view not in MAP_VIEWS:
        raise ValueError(f"map view must be one of {', '.join(MAP_VIEWS)}")
    top = opt.lat_top if opt.lat_top is not None else MAP_VIEWS[opt.view][0]
    bottom = opt.lat_bottom if opt.lat_bottom is not None else MAP_VIEWS[opt.view][1]
    w = opt.width
    h = int(w * (top - bottom) / 360.0)
    s = 2  # supersample
    img = Image.new("RGB", (w * s, h * s), th["ocean"])
    d = ImageDraw.Draw(img)
    for poly in data.land_polygons():
        pts = [_project(x, y, w * s, top, bottom, h * s) for x, y in poly]
        d.polygon(pts, fill=th["land"], outline=th["border"])
    img = img.resize((w, h), Image.LANCZOS)
    d = ImageDraw.Draw(img)

    shown = rows[: opt.max_flags]
    anchors = [list(_project(r.entity.lon, r.entity.lat, w, top, bottom, h)) for r in shown]
    placed = _spread(anchors, opt.flag_w + 2, opt.flag_h + 2, bounds=(w, h))
    for a, p in zip(anchors, placed):  # leader lines first, flags on top
        if math.hypot(a[0] - p[0], a[1] - p[1]) > opt.flag_h * 0.6:
            d.line([tuple(a), tuple(p)], fill=th["line"], width=1)
            d.ellipse([a[0] - 2, a[1] - 2, a[0] + 2, a[1] + 2], fill=th["line"])
    for r, p in zip(shown, placed):
        fl = _flag(r.entity.iso, opt.flag_w, opt.flag_h)
        x, y = int(p[0] - opt.flag_w / 2), int(p[1] - opt.flag_h / 2)
        x = min(max(x, 0), w - opt.flag_w)
        y = min(max(y, 0), h - opt.flag_h)
        img.paste(fl, (x, y), fl)
        d.rectangle([x, y, x + opt.flag_w - 1, y + opt.flag_h - 1], outline=th["border"])

    if opt.title:
        d.text((12, 8), opt.title, font=_font(26, True), fill=th["fg"])
    if opt.footer:  # own strip under the map, so it never covers flags pinned to the bottom edge
        fs = max(14, w // 80)
        strip = Image.new("RGB", (w, h + fs + 12), th["bg"])
        strip.paste(img, (0, 0))
        sd = ImageDraw.Draw(strip)
        sd.text((12, h + 6), opt.footer_text or _summary(rows), font=_font(fs), fill=th["fg"], anchor="lt")
        if opt.credit:
            sd.text((w - 12, h + 6), CREDIT, font=_font(fs), fill=th["muted"], anchor="rt")
        img = strip
    return img
