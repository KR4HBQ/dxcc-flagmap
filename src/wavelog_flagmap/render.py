"""Pillow renderers: Flag Counter-style grid and world map."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

from . import data
from .stats import EntityCount

THEMES = {
    "light": dict(bg=(200, 244, 255), fg=(20, 20, 20), ocean=(176, 216, 240), land=(222, 214, 190),
                  border=(60, 60, 60), line=(90, 90, 90)),
    "dark": dict(bg=(24, 28, 36), fg=(235, 235, 235), ocean=(18, 32, 56), land=(52, 66, 58),
                 border=(0, 0, 0), line=(200, 200, 200)),
}


@dataclass
class GridOptions:
    title: str = "Worked DXCC"
    metric: str = "qsos"
    rows: int = 8            # entries per column (Flag Counter uses 8)
    max_entries: int = 48
    theme: str = "light"
    flag_w: int = 40
    flag_h: int = 30
    scale: int = 2           # supersampling factor for crisp text on high-dpi pages
    footer: bool = True


@dataclass
class MapOptions:
    title: str = ""
    width: int = 1600
    theme: str = "light"
    flag_w: int = 30
    flag_h: int = 22
    lat_top: float = 84.0
    lat_bottom: float = -58.0
    max_flags: int = 400
    footer: bool = True
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

    pad, gap_x, gap_y = 10 * s, 26 * s, 6 * s
    fw, fh = opt.flag_w * s, opt.flag_h * s
    f_title, f_num = _font(24 * s, True), _font(17 * s)
    f_small = _font(11 * s)
    digits = max((len(f"{r.value(opt.metric):,}") for r in shown), default=1)
    num_w = int(digits * 10.5 * s) + 6 * s
    cell_w = fw + 8 * s + num_w
    title_h = 38 * s
    foot_h = 22 * s if opt.footer else 0
    w = pad * 2 + cols * cell_w + (cols - 1) * gap_x
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
        d.text((x + fw + 8 * s, y + fh // 2), f"{r.value(opt.metric):,}", font=f_num, fill=th["fg"], anchor="lm")
    if opt.footer:
        label = _summary(rows) + (" (confirmed)" if opt.metric == "confirmed" else "")
        d.text((pad, h - pad), label, font=f_small, fill=th["fg"], anchor="ld")
    return img.resize((img.width // s, img.height // s), Image.LANCZOS) if s > 1 else img


# --------------------------------------------------------------------------- map
def _project(lon: float, lat: float, w: int, top: float, bottom: float, h: int) -> tuple[float, float]:
    return (lon + 180.0) / 360.0 * w, (top - lat) / (top - bottom) * h


def _spread(points: list[list[float]], min_d: float, iters: int = 60) -> list[list[float]]:
    """Naive repulsion so flags in crowded regions (Europe) do not sit on top of each other."""
    pos = [p[:] for p in points]
    for _ in range(iters):
        moved = False
        for i in range(len(pos)):
            for j in range(i + 1, len(pos)):
                dx, dy = pos[j][0] - pos[i][0], pos[j][1] - pos[i][1]
                dist = math.hypot(dx, dy)
                if dist >= min_d:
                    continue
                if dist < 1e-6:
                    dx, dy, dist = 1.0, 0.3 * ((i + j) % 3 - 1), 1.0
                push = (min_d - dist) / 2 + 0.5
                ux, uy = dx / dist, dy / dist
                pos[i][0] -= ux * push
                pos[i][1] -= uy * push
                pos[j][0] += ux * push
                pos[j][1] += uy * push
                moved = True
        if not moved:
            break
    return pos


def render_map(rows: list[EntityCount], opt: MapOptions = MapOptions()) -> Image.Image:
    th = THEMES[opt.theme]
    w = opt.width
    h = int(w * (opt.lat_top - opt.lat_bottom) / 360.0)
    s = 2  # supersample
    img = Image.new("RGB", (w * s, h * s), th["ocean"])
    d = ImageDraw.Draw(img)
    for poly in data.land_polygons():
        pts = [_project(x, y, w * s, opt.lat_top, opt.lat_bottom, h * s) for x, y in poly]
        d.polygon(pts, fill=th["land"], outline=th["border"])
    img = img.resize((w, h), Image.LANCZOS)
    d = ImageDraw.Draw(img)

    shown = rows[: opt.max_flags]
    anchors = [list(_project(r.entity.lon, r.entity.lat, w, opt.lat_top, opt.lat_bottom, h)) for r in shown]
    placed = _spread(anchors, min_d=max(opt.flag_w, opt.flag_h) * 0.95)
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
    if opt.footer:
        d.text((12, h - 8), _summary(rows), font=_font(14), fill=th["fg"], anchor="ld")
    return img
