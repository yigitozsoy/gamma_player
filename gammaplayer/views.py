"""Ana sayfa, müzik görünümü ve videonun altındaki bilgi alanı."""
import os

from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from PyQt6.QtGui import QPainter, QColor, QImage, QFont, QFontMetrics, QPainterPath, QLinearGradient
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout

from . import icons
from .config import prefs
from .formats import kind_of
from .i18n import t
from .theme import theme, tinted_logo
from .widgets import IconButton, Pill, ElidedLabel


class HomeView(QWidget):
    open_file = pyqtSignal()
    open_folder = pyqtSignal()
    open_recent = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 30, 40, 30)
        outer.addStretch(2)
        col = QVBoxLayout()
        col.setSpacing(10)
        col.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        logo = QLabel()
        theme.bind(logo, lambda l: l.setPixmap(tinted_logo(84, l.devicePixelRatioF())))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(logo)
        h = QLabel(t("welcome"))
        h.setStyleSheet("font-size: 26px; font-weight: 700;")
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(h)
        sub = QLabel(t("welcome_sub"))
        sub.setObjectName("Secondary")
        sub.setStyleSheet("font-size: 14px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        col.addWidget(sub)
        btns = QHBoxLayout()
        btns.setSpacing(10)
        btns.addStretch(1)
        b1 = QPushButton(t("open_file"))
        b1.setObjectName("Primary")
        b1.setCursor(Qt.CursorShape.PointingHandCursor)
        b1.clicked.connect(self.open_file.emit)
        theme.icon(b1, "file_open", "button_fg", 20)
        b2 = Pill("  " + t("open_folder"), "folder_open")
        b2.clicked.connect(self.open_folder.emit)
        btns.addWidget(b1)
        btns.addWidget(b2)
        btns.addStretch(1)
        col.addSpacing(10)
        col.addLayout(btns)
        outer.addLayout(col)
        outer.addSpacing(26)

        self.recent_title = QLabel(t("recent"))
        self.recent_title.setObjectName("SectionTitle")
        self.recent_title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(self.recent_title)
        self.recent_box = QWidget()
        self.recent_lay = QGridLayout(self.recent_box)
        self.recent_lay.setSpacing(8)
        wrap = QHBoxLayout()
        wrap.addStretch(1)
        wrap.addWidget(self.recent_box)
        wrap.addStretch(1)
        outer.addLayout(wrap)
        outer.addStretch(3)
        fmts = QLabel(t("formats_line"))
        fmts.setObjectName("Secondary")
        fmts.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fmts.setWordWrap(True)
        outer.addWidget(fmts)
        self.refresh_recent()

    def refresh_recent(self):
        while self.recent_lay.count():
            w = self.recent_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        from . import layout_prefs as lp
        rec = [p for p in prefs.get("recent", []) if os.path.exists(p)][:8] if lp.get("show_recent") else []
        self.recent_title.setVisible(bool(rec))
        for n, p in enumerate(rec):
            k = kind_of(p) or ("folder" if os.path.isdir(p) else "video")
            name = {"video": "movie", "audio": "music", "image": "image", "model": "view_in_ar"}.get(k, "folder")
            b = Pill("  " + os.path.basename(p) if len(os.path.basename(p)) < 38 else
                     "  " + os.path.basename(p)[:35] + "…", name)
            b.setToolTip(p)
            b.setMinimumWidth(260)
            b.clicked.connect(lambda _=False, path=p: self.open_recent.emit(path))
            self.recent_lay.addWidget(b, n // 2, n % 2)


class AudioView(QWidget):
    """Müzik çalarken: bulanık kapak arka planı, büyük kapak ve etiket bilgileri."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.cover = QImage()
        self.bg = QImage()
        self.title = ""
        self.artist = ""
        self.album = ""
        self.meta = {}

    def set_info(self, title, artist="", album=""):
        self.title, self.artist, self.album = title, artist, album
        self.update()

    def set_meta(self, tags: dict, info: dict):
        """ffmpeg etiketleri: title, artist, album, album_artist, date, genre, track, disc, composer..."""
        g = lambda *ks: next((tags.get(k) for k in ks if tags.get(k)), "")
        if g("title"):
            self.title = g("title")
        self.artist = g("artist", "album_artist", "performer") or self.artist
        self.album = g("album") or self.album
        year = g("date", "year", "tyer", "originaldate")
        year = year[:4] if year[:4].isdigit() else year
        self.meta = {
            "album_artist": g("album_artist"),
            "year": year,
            "genre": g("genre"),
            "track": g("track", "tracknumber"),
            "disc": g("disc", "discnumber"),
            "composer": g("composer"),
            "codec": info.get("codec", ""),
            "kbps": info.get("kbps"),
            "hz": info.get("hz"),
            "channels": info.get("channels", ""),
        }
        self.update()

    def clear_meta(self):
        self.meta = {}
        self.artist = self.album = ""

    def set_cover(self, img: QImage):
        self.cover = img if img is not None else QImage()
        self.bg = QImage()
        if not self.cover.isNull():
            small = self.cover.scaled(24, 24, Qt.AspectRatioMode.IgnoreAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
            self.bg = small.scaled(240, 240, Qt.AspectRatioMode.IgnoreAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        self.update()

    # ---------------------------------------------------------------- çizim
    def _chips(self):
        m = self.meta
        out = []
        if m.get("genre"):
            out.append(m["genre"])
        if m.get("track"):
            out.append(t("track_no", n=m["track"]))
        if m.get("disc") and m["disc"] not in ("1", "1/1"):
            out.append(t("disc_no", n=m["disc"]))
        q = []
        if m.get("codec"):
            q.append(m["codec"].upper().replace("FLOAT", ""))
        if m.get("kbps"):
            q.append(f"{m['kbps']} kbps")
        if m.get("hz"):
            q.append(f"{m['hz'] / 1000:g} kHz".replace(".", ","))
        if q:
            out.append(" · ".join(q))
        return out

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        if not self.bg.isNull():
            p.drawImage(r, self.bg)
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            g.setColorAt(0, QColor(0, 0, 0, 120))
            g.setColorAt(1, QColor(0, 0, 0, 200))
            p.fillRect(r, g)
        else:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor("#2a2a2a"))
            g.setColorAt(1, QColor("#0e0e0e"))
            p.fillRect(r, g)
        wide = r.width() >= 760 and r.height() >= 300
        if wide:
            side = min(r.height() * 0.62, r.width() * 0.34, 380)
            total_w = side + 40 + min(520, r.width() - side - 160)
            x0 = r.center().x() - total_w / 2
            cr = QRectF(x0, r.center().y() - side / 2 - 30, side, side)
            text_rect = QRectF(cr.right() + 40, cr.top(), total_w - side - 40, side)
        else:
            side = min(r.width() * 0.5, r.height() * 0.45, 300)
            cr = QRectF(r.center().x() - side / 2, r.center().y() - side / 2 - 80, side, side)
            text_rect = QRectF(30, cr.bottom() + 20, r.width() - 60, r.bottom() - cr.bottom() - 20)
        self._paint_cover(p, cr)
        self._paint_text(p, text_rect, center=not wide)

    def _paint_cover(self, p, cr):
        side = cr.width()
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(10):
            p.setBrush(QColor(0, 0, 0, 12))
            p.drawRoundedRect(cr.adjusted(-i, -i + 8, i, i + 8), 14 + i, 14 + i)
        path = QPainterPath()
        path.addRoundedRect(cr, 14, 14)
        p.setClipPath(path)
        if not self.cover.isNull():
            cw, ch = self.cover.width(), self.cover.height()
            s = max(side / cw, side / ch)
            p.drawImage(QRectF(cr.center().x() - cw * s / 2, cr.center().y() - ch * s / 2, cw * s, ch * s), self.cover)
        else:
            g = QLinearGradient(cr.topLeft(), cr.bottomRight())
            g.setColorAt(0, QColor("#5a5a5a"))
            g.setColorAt(1, QColor("#2a2a2a"))
            p.fillRect(cr, g)
            pm = icons.pixmap("music", "#ffffff", int(side * 0.4))
            p.drawPixmap(int(cr.center().x() - side * 0.2), int(cr.center().y() - side * 0.2), pm)
        p.restore()

    def _paint_text(self, p, tr, center):
        align = Qt.AlignmentFlag.AlignHCenter if center else Qt.AlignmentFlag.AlignLeft
        lines = []  # (metin, piksel, kalınlık, alfa, boşluk)
        lines.append((t("song").upper(), 12, QFont.Weight.DemiBold, 150, 6))
        lines.append((self.title, 30 if not center else 24, QFont.Weight.Bold, 255, 8))
        if self.artist:
            lines.append((self.artist, 19 if not center else 16, QFont.Weight.DemiBold, 230, 6))
        sub = " • ".join(s for s in (self.album, self.meta.get("year", "")) if s)
        if sub:
            lines.append((sub, 15, QFont.Weight.Normal, 190, 4))
        aa = self.meta.get("album_artist")
        if aa and aa != self.artist:
            lines.append((t("album_artist") + ": " + aa, 13, QFont.Weight.Normal, 160, 2))
        if self.meta.get("composer"):
            lines.append((t("composer") + ": " + self.meta["composer"], 13, QFont.Weight.Normal, 160, 2))
        heights = []
        for txt, px, wt, a, gap in lines:
            f = QFont(self.font())
            f.setPixelSize(px)
            f.setWeight(wt)
            heights.append(QFontMetrics(f).height() + gap)
        chips = self._chips()
        chip_h = 30 if chips else 0
        total = sum(heights) + (chip_h + 14 if chips else 0)
        y = tr.top() + max(0, (tr.height() - total) / 2) if not center else tr.top()
        for (txt, px, wt, a, gap), hgt in zip(lines, heights):
            f = QFont(self.font())
            f.setPixelSize(px)
            f.setWeight(wt)
            p.setFont(f)
            fm = p.fontMetrics()
            p.setPen(QColor(255, 255, 255, a))
            p.drawText(QRectF(tr.left(), y, tr.width(), fm.height()), align | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(txt, Qt.TextElideMode.ElideRight, int(tr.width())))
            y += hgt
        if chips:
            y += 14
            f = QFont(self.font())
            f.setPixelSize(12)
            f.setWeight(QFont.Weight.DemiBold)
            p.setFont(f)
            fm = p.fontMetrics()
            widths = [fm.horizontalAdvance(c) + 24 for c in chips]
            total_w = sum(widths) + 8 * (len(widths) - 1)
            x = tr.center().x() - total_w / 2 if center else tr.left()
            for c, cw in zip(chips, widths):
                if x + cw > tr.right() + 1 and not center:
                    break
                rr = QRectF(x, y, cw, 28)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, 38))
                p.drawRoundedRect(rr, 14, 14)
                p.setPen(QColor(255, 255, 255, 225))
                p.drawText(rr, Qt.AlignmentFlag.AlignCenter, c)
                x += cw + 8


class InfoBar(QWidget):
    """Oynatıcının altındaki tek satır: dosya adı + işlem düğmeleri (ayrıntılar "Bilgi" düğmesinde)."""
    action = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("InfoBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 10, 0, 4)
        row.setSpacing(8)
        self.title = ElidedLabel("")
        self.title.setObjectName("VideoTitle")
        row.addWidget(self.title, 1)
        self.btn_box = QHBoxLayout()
        self.btn_box.setSpacing(8)
        row.addLayout(self.btn_box)
        self.buttons = {}
        for key, ic in (("edit", "cut"), ("snapshot", "camera"), ("subtitle", "subtitles"),
                        # "Klasörde göster": klasör + ok (düz klasör simgesi "klasör aç" düğmeleriyle karışıyordu)
                        ("reveal", "drive_file_move"), ("info", "info"), ("delete", "delete")):
            b = Pill("  " + t("act_" + key), ic)
            b._label = t("act_" + key)
            b.setToolTip(b._label)
            b.clicked.connect(lambda _=False, k=key: self.action.emit(k))
            self.buttons[key] = b
        self.btn_more = IconButton("more", t("more"), 36, 22)
        self.btn_more.clicked.connect(lambda: self.action.emit("more"))
        self._kind = None
        self.apply_personalization()

    def _widget(self, key):
        return self.btn_more if key == "more" else self.buttons.get(key)

    def apply_personalization(self):
        from . import layout_prefs as lp
        while self.btn_box.count():
            self.btn_box.takeAt(0)
        self._uvis = {}
        for key, vis in lp.layout("infobar"):
            w = self._widget(key)
            if w is None:
                continue
            self.btn_box.addWidget(w)
            self._uvis[key] = bool(vis)
        self._apply_visibility()
        self._apply_labels()

    def _apply_visibility(self):
        kind = self._kind
        for key, vis in self._uvis.items():
            ok = vis
            if key in ("snapshot", "subtitle"):
                ok = ok and kind == "video"
            elif key == "edit":
                ok = ok and kind != "model"   # 3D modeller için düzenleyici yok
            self._widget(key).setVisible(ok)

    def _apply_labels(self):
        # Varsayılan: yalnız simge (adı fareyle üstüne gelince görünür); Tercihler'den adlar açılabilir
        from . import layout_prefs as lp
        compact = not lp.get("infobar_labels") or self.width() < 900
        for b in self.buttons.values():
            b.setText("" if compact else "  " + b._label)
            b.setToolTip(b._label)
            if compact:   # YouTube'daki gibi yuvarlak simge düğmesi
                b.setFixedWidth(36)
                b.setStyleSheet("QPushButton#Pill { padding: 0px; text-align: center; }")
            else:
                b.setMinimumWidth(0)
                b.setMaximumWidth(16777215)
                b.setStyleSheet("")

    def set_item(self, item, counts_text="", details=""):
        self.title.setText(item.title if item else "")
        self.title.setToolTip(item.path if item else "")
        self._kind = item.kind if item else None
        self.buttons["edit"]._label = t("act_edit_image") if self._kind == "image" else t("act_edit")
        theme.icon(self.buttons["edit"], "edit" if self._kind == "image" else "cut", "text", 20)
        self._apply_visibility()
        self._apply_labels()

    def set_details(self, item, details=""):
        pass

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_labels()
