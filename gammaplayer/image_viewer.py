"""Resim görüntüleyici: yakınlaştırma, kaydırma, animasyon (GIF/WebP/APNG) ve kırpma çerçevesi."""
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPixmap, QColor, QPen, QImage, QBrush
from PyQt6.QtWidgets import QWidget

from .theme import color


def _checker():
    pm = QPixmap(16, 16)
    pm.fill(QColor("#cfcfcf"))
    p = QPainter(pm)
    p.fillRect(0, 0, 8, 8, QColor("#9f9f9f"))
    p.fillRect(8, 8, 8, 8, QColor("#9f9f9f"))
    p.end()
    return pm


class ImageViewer(QWidget):
    zoom_changed = pyqtSignal(int)
    mouse_moved = pyqtSignal()
    crop_changed = pyqtSignal(QRectF)
    double_clicked = pyqtSignal()
    picked = pyqtSignal(QPointF)     # damlalık: görsel koordinatı
    context_requested = pyqtSignal(object)
    wheel_nav = pyqtSignal(int)

    HANDLE = 9

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self._frames = []        # QImage listesi
        self._pix = []           # QPixmap önbelleği
        self._durations = []
        self._frame = 0
        self._has_alpha = False
        self._fit = True
        self._scale = 1.0
        self._pan = QPointF(0, 0)
        self._rot = 0
        self._drag = None
        self._checker = None
        self.bg_override = None   # video düzenleyicide siyah arka plan için
        self.alpha_bg = "checker"  # saydam görsellerin altı: "checker" (dama) ya da "#rrggbb"
        self.allow_zoom = True
        # Kırpma
        self.crop_mode = False
        self.crop = QRectF()
        self.crop_ratio = None
        self._crop_drag = None
        self.anim_timer = QTimer(self)
        self.anim_timer.setSingleShot(True)
        self.anim_timer.timeout.connect(self._next_frame)

    # ---------------------------------------------------------------- içerik
    def set_frames(self, frames, durations=None, keep_view=False):
        self.anim_timer.stop()
        self._frames = [f for f in frames if f is not None and not f.isNull()]
        self._pix = [None] * len(self._frames)
        self._durations = durations or []
        self._frame = 0
        self._has_alpha = bool(self._frames) and self._frames[0].hasAlphaChannel()
        if not keep_view:
            self._fit = True
            self._pan = QPointF(0, 0)
            self._rot = 0
        if len(self._frames) > 1:
            self.anim_timer.start(self._durations[0] if self._durations else 100)
        self.update()
        self.zoom_changed.emit(self.zoom_percent())

    def has_alpha(self):
        return self._has_alpha

    def set_alpha_bg(self, value):
        self.alpha_bg = value or "checker"
        self.update()

    def set_image(self, img: QImage, keep_view=False):
        self.set_frames([img] if img is not None else [], keep_view=keep_view)

    def clear(self):
        self.set_frames([])

    def has_image(self):
        return bool(self._frames)

    def image(self) -> QImage:
        return self._frames[self._frame] if self._frames else QImage()

    def is_animated(self):
        return len(self._frames) > 1

    def _next_frame(self):
        if len(self._frames) < 2 or not self.isVisible():
            if len(self._frames) > 1:
                self.anim_timer.start(200)
            return
        self._frame = (self._frame + 1) % len(self._frames)
        d = self._durations[self._frame] if self._frame < len(self._durations) else 100
        self.anim_timer.start(max(16, d))
        self.update()

    def _pixmap(self):
        if not self._frames:
            return None
        pm = self._pix[self._frame]
        if pm is None:
            pm = QPixmap.fromImage(self._frames[self._frame])
            self._pix[self._frame] = pm
        return pm

    # ---------------------------------------------------------------- geometri
    def _img_size(self):
        if not self._frames:
            return 1, 1
        im = self._frames[0]
        return im.width(), im.height()

    def _eff_size(self):
        w, h = self._img_size()
        return (h, w) if self._rot % 180 else (w, h)

    def fit_scale(self):
        ew, eh = self._eff_size()
        aw, ah = max(1, self.width()), max(1, self.height())
        s = min(aw / ew, ah / eh)
        if self.crop_mode:
            s *= 0.92
        return min(s, 1.0) if not self.crop_mode else s

    def scale(self):
        return self.fit_scale() if self._fit else self._scale

    def zoom_percent(self):
        return int(round(self.scale() * 100))

    def _center(self):
        return QPointF(self.width() / 2 + self._pan.x(), self.height() / 2 + self._pan.y())

    def img_to_widget(self, pt: QPointF) -> QPointF:
        w, h = self._img_size()
        s = self.scale()
        c = self._center()
        return QPointF(c.x() + (pt.x() - w / 2) * s, c.y() + (pt.y() - h / 2) * s)

    def widget_to_img(self, pt: QPointF) -> QPointF:
        w, h = self._img_size()
        s = self.scale()
        c = self._center()
        return QPointF((pt.x() - c.x()) / s + w / 2, (pt.y() - c.y()) / s + h / 2)

    def crop_widget_rect(self) -> QRectF:
        return QRectF(self.img_to_widget(self.crop.topLeft()), self.img_to_widget(self.crop.bottomRight()))

    # ---------------------------------------------------------------- yakınlaştırma
    def set_zoom(self, s, anchor: QPointF = None):
        if not self._frames or not self.allow_zoom:
            return
        s = max(0.02, min(40.0, s))
        old = self.scale()
        if anchor is None:
            anchor = QPointF(self.width() / 2, self.height() / 2)
        c = self._center()
        rel = anchor - c
        self._fit = False
        self._scale = s
        f = s / old
        newc = anchor - rel * f
        self._pan = QPointF(newc.x() - self.width() / 2, newc.y() - self.height() / 2)
        self._clamp_pan()
        self.update()
        self.zoom_changed.emit(self.zoom_percent())

    def zoom_by(self, factor, anchor=None):
        self.set_zoom(self.scale() * factor, anchor)

    def fit(self):
        self._fit = True
        self._pan = QPointF(0, 0)
        self.update()
        self.zoom_changed.emit(self.zoom_percent())

    def actual_size(self):
        self.set_zoom(1.0)

    def rotate_view(self, deg):
        self._rot = (self._rot + deg) % 360
        self.fit()

    def _clamp_pan(self):
        if self._fit:
            self._pan = QPointF(0, 0)
            return
        ew, eh = self._eff_size()
        s = self.scale()
        dw, dh = ew * s, eh * s
        mx = max(0.0, (dw - self.width()) / 2 + 40)
        my = max(0.0, (dh - self.height()) / 2 + 40)
        self._pan = QPointF(max(-mx, min(mx, self._pan.x())), max(-my, min(my, self._pan.y())))

    # ---------------------------------------------------------------- kırpma
    def set_crop_mode(self, on, ratio=None):
        self.crop_mode = on
        self.crop_ratio = ratio
        if on:
            self._rot = 0
            w, h = self._img_size()
            self.crop = QRectF(0, 0, w, h)
            if ratio:
                self.apply_ratio(ratio)
            self.fit()
        self.update()

    def apply_ratio(self, ratio):
        self.crop_ratio = ratio
        w, h = self._img_size()
        if not ratio:
            self.update()
            self.crop_changed.emit(self.crop)
            return
        cw, ch = w, w / ratio
        if ch > h:
            ch, cw = h, h * ratio
        self.crop = QRectF((w - cw) / 2, (h - ch) / 2, cw, ch)
        self.update()
        self.crop_changed.emit(self.crop)

    def _hit_handle(self, pos: QPointF):
        r = self.crop_widget_rect()
        pts = {
            "tl": r.topLeft(), "tr": r.topRight(), "bl": r.bottomLeft(), "br": r.bottomRight(),
            "t": QPointF(r.center().x(), r.top()), "b": QPointF(r.center().x(), r.bottom()),
            "l": QPointF(r.left(), r.center().y()), "r": QPointF(r.right(), r.center().y()),
        }
        for k, p in pts.items():
            if abs(p.x() - pos.x()) <= self.HANDLE + 3 and abs(p.y() - pos.y()) <= self.HANDLE + 3:
                return k
        if r.contains(pos):
            return "move"
        return None

    def _apply_crop_drag(self, pos: QPointF):
        kind, start_img, start_rect = self._crop_drag
        cur = self.widget_to_img(pos)
        dx, dy = cur.x() - start_img.x(), cur.y() - start_img.y()
        w, h = self._img_size()
        r = QRectF(start_rect)
        if kind == "move":
            r.translate(dx, dy)
            r.moveLeft(max(0, min(w - r.width(), r.left())))
            r.moveTop(max(0, min(h - r.height(), r.top())))
        else:
            if "l" in kind:
                r.setLeft(min(r.right() - 8, max(0, r.left() + dx)))
            if "r" in kind:
                r.setRight(max(r.left() + 8, min(w, r.right() + dx)))
            if "t" in kind:
                r.setTop(min(r.bottom() - 8, max(0, r.top() + dy)))
            if "b" in kind:
                r.setBottom(max(r.top() + 8, min(h, r.bottom() + dy)))
            if self.crop_ratio:
                ratio = self.crop_ratio
                if kind in ("l", "r"):
                    nh = r.width() / ratio
                    cy = start_rect.center().y()
                    r.setTop(cy - nh / 2)
                    r.setHeight(nh)
                elif kind in ("t", "b"):
                    nw = r.height() * ratio
                    cx = start_rect.center().x()
                    r.setLeft(cx - nw / 2)
                    r.setWidth(nw)
                else:
                    nh = r.width() / ratio
                    if "t" in kind:
                        r.setTop(r.bottom() - nh)
                    else:
                        r.setHeight(nh)
                # sınır dışına taşmayı engelle
                if r.left() < 0 or r.top() < 0 or r.right() > w or r.bottom() > h:
                    return
        self.crop = r.normalized()
        self.update()
        self.crop_changed.emit(self.crop)

    # ---------------------------------------------------------------- olaylar
    def wheelEvent(self, e):
        if not self._frames:
            return
        d = e.angleDelta().y()
        if not self.allow_zoom:
            return
        if d:
            self.zoom_by(1.18 if d > 0 else 1 / 1.18, e.position())
        e.accept()

    def start_pick(self):
        self.pick_mode = True
        self.setCursor(Qt.CursorShape.CrossCursor)

    def mousePressEvent(self, e):
        pos = e.position()
        if getattr(self, "pick_mode", False) and e.button() == Qt.MouseButton.LeftButton:
            self.pick_mode = False
            self.unsetCursor()
            self.picked.emit(self.widget_to_img(pos))
            return
        if e.button() == Qt.MouseButton.RightButton:
            self.context_requested.emit(e.globalPosition().toPoint())
            return
        if self.crop_mode and e.button() == Qt.MouseButton.LeftButton:
            k = self._hit_handle(pos)
            if k:
                self._crop_drag = (k, self.widget_to_img(pos), QRectF(self.crop))
            return
        if e.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._drag = (pos, QPointF(self._pan))
            if not self._fit:
                self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        self.mouse_moved.emit()
        pos = e.position()
        if self.crop_mode:
            if self._crop_drag:
                self._apply_crop_drag(pos)
            else:
                k = self._hit_handle(pos)
                cur = {
                    "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
                    "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
                    "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
                    "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
                    "move": Qt.CursorShape.SizeAllCursor,
                }.get(k)
                if cur:
                    self.setCursor(cur)
                else:
                    self.unsetCursor()
            return
        if self._drag and not self._fit:
            start, pan0 = self._drag
            self._pan = pan0 + (pos - start)
            self._clamp_pan()
            self.update()
        elif not self._fit:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, e):
        self._drag = None
        self._crop_drag = None
        if not self.crop_mode:
            if not self._fit:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.unsetCursor()

    def mouseDoubleClickEvent(self, e):
        if self.crop_mode or e.button() != Qt.MouseButton.LeftButton:
            return
        # Çift tık: tam ekran aç/kapat (yakınlaştırma tekerlek, +/−, 0 ve 1 tuşlarıyla)
        self.double_clicked.emit()

    def resizeEvent(self, e):
        self._clamp_pan()
        super().resizeEvent(e)
        if self._fit:
            self.zoom_changed.emit(self.zoom_percent())

    # ---------------------------------------------------------------- çizim
    def paintEvent(self, e):
        p = QPainter(self)
        bg = QColor(self.bg_override) if self.bg_override else QColor(color("bg2") if not self.crop_mode else "#0b0b0b")
        p.fillRect(self.rect(), bg)
        pm = self._pixmap()
        if pm is None:
            return
        w, h = self._img_size()
        s = self.scale()
        c = self._center()
        p.save()
        p.translate(c)
        p.rotate(self._rot)
        target = QRectF(-w * s / 2, -h * s / 2, w * s, h * s)
        if self._has_alpha:
            if self.alpha_bg and self.alpha_bg != "checker":
                p.fillRect(target, QColor(self.alpha_bg))
            else:
                if self._checker is None:
                    self._checker = _checker()
                p.fillRect(target, QBrush(self._checker))
        smooth = s < 1.999
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, smooth)
        p.drawPixmap(target, pm, QRectF(pm.rect()))
        p.restore()
        if self.crop_mode:
            self._paint_crop(p)

    def _paint_crop(self, p):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.crop_widget_rect()
        full = QRectF(self.rect())
        shade = QColor(0, 0, 0, 150)
        p.fillRect(QRectF(full.left(), full.top(), full.width(), r.top() - full.top()), shade)
        p.fillRect(QRectF(full.left(), r.bottom(), full.width(), full.bottom() - r.bottom()), shade)
        p.fillRect(QRectF(full.left(), r.top(), r.left() - full.left(), r.height()), shade)
        p.fillRect(QRectF(r.right(), r.top(), full.right() - r.right(), r.height()), shade)
        p.setPen(QPen(QColor(255, 255, 255, 110), 1))
        for i in (1, 2):
            x = r.left() + r.width() * i / 3
            y = r.top() + r.height() * i / 3
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffffff"))
        hs = self.HANDLE
        for pt in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight(),
                   QPointF(r.center().x(), r.top()), QPointF(r.center().x(), r.bottom()),
                   QPointF(r.left(), r.center().y()), QPointF(r.right(), r.center().y())):
            p.drawRoundedRect(QRectF(pt.x() - hs / 2, pt.y() - hs / 2, hs, hs), 2, 2)
        # boyut etiketi
        txt = f"{int(self.crop.width())} × {int(self.crop.height())}"
        p.setPen(QColor("#ffffff"))
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(txt) + 14
        lab = QRectF(r.left(), max(2, r.top() - 26), tw, 22)
        p.setBrush(QColor(0, 0, 0, 170))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(lab, 4, 4)
        p.setPen(QColor("#ffffff"))
        p.drawText(lab, Qt.AlignmentFlag.AlignCenter, txt)
