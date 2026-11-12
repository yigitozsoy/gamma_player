"""Videoya yazı / logo (filigran) bindirme.

Yazı ve logo Qt ile şeffaf bir görsele çizilir; önizlemede kareye, dışa aktarırken ffmpeg
"overlay" filtresiyle videoya bindirilir. Böylece önizlemede görülen ile çıktı birebir aynıdır.
Boyutlar karenin yüksekliğine/genişliğine oranla tutulur, çözünürlükten bağımsızdır.
"""
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QImage, QPainter, QColor, QFont, QFontMetricsF, QPainterPath, QPen

from .config import prefs

POSITIONS = ["tl", "tc", "tr", "ml", "mc", "mr", "bl", "bc", "br"]
FONTS = ["Segoe UI Semibold", "Segoe UI", "Bahnschrift", "Arial", "Arial Black", "Impact", "Georgia",
         "Times New Roman", "Consolas", "Comic Sans MS"]

DEFAULTS = {
    "wm_text_on": False, "wm_text": "", "wm_font": "Segoe UI Semibold", "wm_size": 6,   # % kare yüksekliği
    "wm_color": "#ffffff", "wm_opacity": 90, "wm_pos": "br", "wm_shadow": True, "wm_box": False,
    "wm_logo_on": False, "wm_logo": "", "wm_logo_size": 15,                               # % kare genişliği
    "wm_logo_pos": "tr", "wm_logo_opacity": 85,
}


def get(key):
    return prefs.get(key, DEFAULTS[key])


def active():
    return (get("wm_text_on") and bool(get("wm_text").strip())) or (get("wm_logo_on") and bool(get("wm_logo")))


def _place(pos, W, H, w, h, margin):
    col, row = pos[1], pos[0]
    x = margin if col == "l" else (W - w) / 2 if col == "c" else W - w - margin
    y = margin if row == "t" else (H - h) / 2 if row == "m" else H - h - margin
    return x, y


def render(W: int, H: int) -> QImage:
    """W×H boyutunda, yalnızca yazı/logo içeren şeffaf görsel."""
    W, H = max(2, int(W)), max(2, int(H))
    img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    if not active():
        return img
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    margin = 0.035 * min(W, H)

    if get("wm_logo_on") and get("wm_logo"):
        logo = QImage(get("wm_logo"))
        if not logo.isNull():
            lw = W * int(get("wm_logo_size")) / 100.0
            lh = lw * logo.height() / max(1, logo.width())
            x, y = _place(get("wm_logo_pos"), W, H, lw, lh, margin)
            p.setOpacity(int(get("wm_logo_opacity")) / 100.0)
            p.drawImage(QRectF(x, y, lw, lh), logo)
            p.setOpacity(1.0)

    text = get("wm_text").strip() if get("wm_text_on") else ""
    if text:
        f = QFont(get("wm_font"))
        f.setPixelSize(max(6, int(H * int(get("wm_size")) / 100.0)))
        fm = QFontMetricsF(f)
        lines = text.splitlines() or [text]
        tw = max(fm.horizontalAdvance(ln) for ln in lines)
        th = fm.height() * len(lines)
        pad = f.pixelSize() * 0.35 if get("wm_box") else 0
        x, y = _place(get("wm_pos"), W, H, tw + 2 * pad, th + 2 * pad, margin)
        p.setOpacity(int(get("wm_opacity")) / 100.0)
        if get("wm_box"):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawRoundedRect(QRectF(x, y, tw + 2 * pad, th + 2 * pad), pad * 0.8, pad * 0.8)
        path = QPainterPath()
        align = get("wm_pos")[1]
        for i, ln in enumerate(lines):
            lx = x + pad + (0 if align == "l" else (tw - fm.horizontalAdvance(ln)) / (2 if align == "c" else 1))
            path.addText(QPointF(lx, y + pad + fm.ascent() + i * fm.height()), f, ln)
        if get("wm_shadow") and not get("wm_box"):
            sh = max(1.0, f.pixelSize() * 0.06)
            p.save()
            p.translate(sh, sh)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawPath(path)
            p.restore()
            p.setPen(QPen(QColor(0, 0, 0, 170), max(1.0, f.pixelSize() * 0.06)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(get("wm_color")))
        p.drawPath(path)
        p.setOpacity(1.0)
    p.end()
    return img
