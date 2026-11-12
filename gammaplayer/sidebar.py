"""Sağ panel: YouTube'daki "Sıradaki" listesi gibi, açılan klasördeki tüm medya."""
import hashlib
import os

from PyQt6.QtCore import Qt, QAbstractListModel, QModelIndex, QRectF, QSize, pyqtSignal, QPoint
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics, QPainterPath, QLinearGradient
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListView, QStyledItemDelegate,
                             QStyle, QMenu, QAbstractItemView, QSizePolicy)

from . import icons
from .i18n import t
from .library import fmt_time, human_size
from .theme import theme, color, qcolor, accent, current_name
from .widgets import IconButton, Chip

THUMB_SIZES = {"small": (120, 68), "normal": (168, 94), "large": (212, 119)}


def thumb_size():
    from . import layout_prefs as lp
    return THUMB_SIZES.get(lp.get("thumb_size"), THUMB_SIZES["normal"])


class MediaModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.thumbs = {}       # path -> QPixmap
        self.current_path = None
        self.on_missing = None   # küçük resmi olmayan satır çizilince çağrılır (tembel yükleme)

    def rowCount(self, parent=QModelIndex()):
        return len(self.items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        it = self.items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return it.name
        if role == Qt.ItemDataRole.ToolTipRole:
            return it.path
        if role == Qt.ItemDataRole.UserRole:
            return it
        return None

    def set_items(self, items):
        self.beginResetModel()
        self.items = list(items)
        self.endResetModel()

    def set_thumb(self, path, pm):
        self.thumbs[path] = pm
        for r, it in enumerate(self.items):
            if it.path == path:
                idx = self.index(r)
                self.dataChanged.emit(idx, idx)
                break

    def refresh_row(self, path):
        for r, it in enumerate(self.items):
            if it.path == path:
                idx = self.index(r)
                self.dataChanged.emit(idx, idx)
                break

    def set_current(self, path):
        old = self.current_path
        self.current_path = path
        for r, it in enumerate(self.items):
            if it.path in (old, path):
                idx = self.index(r)
                self.dataChanged.emit(idx, idx)

    def row_of(self, path):
        for r, it in enumerate(self.items):
            if it.path == path:
                return r
        return -1


def _kind_label(it):
    return {"video": t("video"), "audio": t("audio"), "image": t("image"), "model": t("model")}.get(it.kind, "")


def _placeholder_color(name):
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:6], 16)
    hue = h % 360
    return QColor.fromHsl(hue, 120, 90), QColor.fromHsl((hue + 40) % 360, 140, 55)


class MediaDelegate(QStyledItemDelegate):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), thumb_size()[1] + 8)

    def paint(self, p: QPainter, option, index):
        it = index.data(Qt.ItemDataRole.UserRole)
        if it is None:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = option.rect
        is_cur = it.path == self.model.current_path
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if is_cur or hovered:
            bg = qcolor("selected" if is_cur else "hover")
            path = QPainterPath()
            path.addRoundedRect(QRectF(r.adjusted(2, 1, -2, -1)), 10, 10)
            p.fillPath(path, bg)

        tw_, th_ = thumb_size()
        tr = QRectF(r.left() + 8, r.top() + 4, tw_, th_)
        clip = QPainterPath()
        clip.addRoundedRect(tr, 8, 8)
        pm = self.model.thumbs.get(it.path)
        if pm is None and self.model.on_missing is not None:
            self.model.on_missing(it)
        p.save()
        p.setClipPath(clip)
        if pm is not None and not pm.isNull():
            p.fillRect(tr, QColor("#000000"))
            # kırparak doldur (object-fit: cover) — resimler için, video karelerini sığdır
            sw, sh = pm.width() / pm.devicePixelRatio(), pm.height() / pm.devicePixelRatio()
            if it.is_image or it.is_audio:
                s = max(tr.width() / sw, tr.height() / sh)
            else:
                s = min(tr.width() / sw, tr.height() / sh)
                if abs(sw / sh - tr.width() / tr.height()) < 0.25:
                    s = max(tr.width() / sw, tr.height() / sh)
            dw, dh = sw * s, sh * s
            if it.is_audio:
                c1, c2 = _placeholder_color(it.name)
                p.fillRect(tr, c2.darker(160))
                side = tr.height()
                cover = QRectF(tr.center().x() - side / 2, tr.top(), side, side)
                s2 = max(side / sw, side / sh)
                p.drawPixmap(QRectF(cover.center().x() - sw * s2 / 2, cover.center().y() - sh * s2 / 2,
                                    sw * s2, sh * s2), pm, QRectF(pm.rect()))
            else:
                p.drawPixmap(QRectF(tr.center().x() - dw / 2, tr.center().y() - dh / 2, dw, dh), pm, QRectF(pm.rect()))
        else:
            c1, c2 = _placeholder_color(it.name)
            g = QLinearGradient(tr.topLeft(), tr.bottomRight())
            if it.is_audio:
                g.setColorAt(0, c1)
                g.setColorAt(1, c2)
            else:
                base = QColor(color("surface"))
                g.setColorAt(0, base)
                g.setColorAt(1, base.darker(115))
            p.fillRect(tr, g)
            name = {"video": "movie", "audio": "music", "image": "image", "model": "view_in_ar"}.get(it.kind, "file_open")
            ic = icons.pixmap(name, "#ffffff" if it.is_audio else color("text3"), 30)
            p.drawPixmap(int(tr.center().x() - 15), int(tr.center().y() - 15), ic)
        if is_cur:
            p.fillRect(tr, QColor(0, 0, 0, 110))
            # video / müzik çalıyor (ekolayzer); görsel ve 3D model yalnızca görüntüleniyor (göz)
            ic = icons.pixmap("equalizer" if it.kind in ("video", "audio") else "visibility", "#ffffff", 26)
            p.drawPixmap(int(tr.center().x() - 13), int(tr.center().y() - 13), ic)
        p.restore()

        # Süre / format rozeti
        badge = ""
        if it.kind in ("video", "audio") and it.duration and it.duration > 0:
            badge = fmt_time(it.duration)
        elif it.is_image or it.is_model:
            badge = it.ext.strip(".").upper()
        if badge:
            f = QFont(option.font)
            f.setPixelSize(12)
            f.setWeight(QFont.Weight.DemiBold)
            p.setFont(f)
            fm = QFontMetrics(f)
            bw = fm.horizontalAdvance(badge) + 8
            br = QRectF(tr.right() - bw - 4, tr.bottom() - 20 - 4, bw, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 205))
            p.drawRoundedRect(br, 4, 4)
            p.setPen(QColor("#ffffff"))
            p.drawText(br, Qt.AlignmentFlag.AlignCenter, badge)

        # Metinler
        x = tr.right() + 10
        tw = r.right() - x - 8
        f = QFont(option.font)
        f.setPixelSize(14)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        fm = QFontMetrics(f)
        p.setPen(QColor(color("text")))
        lines = self._wrap(it.title, fm, tw, 2)
        y = r.top() + 6
        for ln in lines:
            p.drawText(QRectF(x, y, tw, fm.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, ln)
            y += fm.height()
        f2 = QFont(option.font)
        f2.setPixelSize(12)
        p.setFont(f2)
        fm2 = QFontMetrics(f2)
        y += 3
        p.setPen(QColor(color("text2")))
        if it.is_image and it.width:
            meta1 = f"{_kind_label(it)} • {it.width}×{it.height}"
        else:
            meta1 = f"{_kind_label(it)} • {it.ext.strip('.').upper()}"
        p.drawText(QRectF(x, y, tw, fm2.height()), Qt.AlignmentFlag.AlignLeft,
                   fm2.elidedText(meta1, Qt.TextElideMode.ElideRight, int(tw)))
        y += fm2.height() + 1
        from . import layout_prefs as lp
        meta2 = " • ".join(s for s in (human_size(it.size), it.date_str()) if s) if lp.get("sidebar_meta") else ""
        if is_cur:
            ac = QColor(accent())
            if current_name() == "light" and ac.lightness() > 150:
                ac = QColor(color("text2"))
            p.setPen(ac)
            meta2 = t("now_playing" if it.kind in ("video", "audio") else "now_viewing")
        p.drawText(QRectF(x, y, tw, fm2.height()), Qt.AlignmentFlag.AlignLeft,
                   fm2.elidedText(meta2, Qt.TextElideMode.ElideRight, int(tw)))
        p.restore()

    @staticmethod
    def _wrap(text, fm, width, max_lines):
        width = int(width)
        lines, rest = [], text
        while rest and len(lines) < max_lines - 1:
            if fm.horizontalAdvance(rest) <= width:
                lines.append(rest)
                return lines
            n = len(rest)
            while n > 1 and fm.horizontalAdvance(rest[:n]) > width:
                n -= 1
            cut = max(rest.rfind(" ", 0, n + 1), rest.rfind("_", 0, n + 1), rest.rfind("-", 0, n + 1))
            if cut > n * 0.5:
                n = cut + 1
            lines.append(rest[:n].rstrip())
            rest = rest[n:].lstrip()
        if rest:
            lines.append(fm.elidedText(rest, Qt.TextElideMode.ElideRight, width))
        return lines


class Sidebar(QWidget):
    item_activated = pyqtSignal(object)
    filter_changed = pyqtSignal(str)
    sort_changed = pyqtSignal(str)
    context_requested = pyqtSignal(object, QPoint)
    open_folder_clicked = pyqtSignal()
    close_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(340)
        self.setMaximumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 0, 8, 0)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setContentsMargins(8, 6, 0, 0)
        tcol = QVBoxLayout()
        tcol.setSpacing(0)
        self.lbl_title = QLabel(t("in_this_folder"))
        self.lbl_title.setObjectName("SectionTitle")
        self.lbl_folder = QLabel("")
        self.lbl_folder.setObjectName("Secondary")
        self.lbl_folder.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        tcol.addWidget(self.lbl_title)
        tcol.addWidget(self.lbl_folder)
        head.addLayout(tcol, 1)
        self.btn_sort = IconButton("sort", t("sort_by"), 36, 20)
        self.btn_sort.clicked.connect(self._sort_menu)
        self.btn_folder = IconButton("folder_open", t("open_folder"), 36, 20)
        self.btn_folder.clicked.connect(self.open_folder_clicked.emit)
        self.btn_close = IconButton("close", t("hide_panel"), 36, 20)
        self.btn_close.clicked.connect(self.close_clicked.emit)
        for b in (self.btn_sort, self.btn_folder, self.btn_close):
            head.addWidget(b)
        lay.addLayout(head)

        chips = QHBoxLayout()
        chips.setContentsMargins(8, 4, 0, 4)
        chips.setSpacing(8)
        self.chips = {}
        for key in ("all", "video", "audio", "image", "model"):
            c = Chip(t("f_" + key))
            c.clicked.connect(lambda _=False, k=key: self._on_chip(k))
            chips.addWidget(c)
            self.chips[key] = c
        chips.addStretch(1)
        lay.addLayout(chips)

        self.model = MediaModel(self)
        self.view = QListView(self)
        self.view.setObjectName("UpNext")
        self.view.setModel(self.model)
        self.view.setItemDelegate(MediaDelegate(self.model, self.view))
        self.view.setMouseTracking(True)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.verticalScrollBar().setSingleStep(24)
        self.view.setUniformItemSizes(True)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._ctx)
        self.view.clicked.connect(lambda idx: self.item_activated.emit(idx.data(Qt.ItemDataRole.UserRole)))
        self.view.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        lay.addWidget(self.view, 1)

        self.empty = QLabel(t("empty_folder"))
        self.empty.setObjectName("Secondary")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.hide()
        lay.addWidget(self.empty)
        self._sort = "explorer"
        theme.changed.connect(lambda _: self.view.viewport().update())

    def _on_chip(self, key):
        self.set_filter_visual(key)
        self.filter_changed.emit(key)

    def set_filter_visual(self, key):
        for k, c in self.chips.items():
            c.setChecked(k == key)

    def set_counts(self, counts):
        for k, c in self.chips.items():
            n = counts.get(k, 0)
            c.setText(f"{t('f_' + k)}" + (f"  {n}" if n else ""))
            c.setVisible(k == "all" or n > 0)

    def set_folder(self, folder, total):
        name = os.path.basename(folder.rstrip("\\/")) or folder
        self.lbl_folder.setText(f"{name} • {t('n_items', n=total)}")
        self.lbl_folder.setToolTip(folder)

    def set_items(self, items, current):
        self.model.set_items(items)
        self.model.current_path = current.path if current else None
        self.empty.setVisible(not items)
        self.scroll_to_current()

    def set_current(self, item):
        self.model.set_current(item.path if item else None)
        self.scroll_to_current()

    def scroll_to_current(self):
        r = self.model.row_of(self.model.current_path)
        if r >= 0:
            self.view.scrollTo(self.model.index(r), QAbstractItemView.ScrollHint.EnsureVisible)

    def _sort_menu(self):
        m = QMenu(self)
        for key in ("explorer", "name", "name_desc", "date", "date_asc", "size", "size_asc", "type"):
            if key == "name":
                m.addSeparator()
            a = m.addAction(t("sort_" + key))
            a.setCheckable(True)
            a.setChecked(self._sort == key)
            a.triggered.connect(lambda _=False, k=key: self._set_sort(k))
        m.exec(self.btn_sort.mapToGlobal(QPoint(0, self.btn_sort.height())))

    def _set_sort(self, key):
        self._sort = key
        self.sort_changed.emit(key)

    def set_sort(self, key):
        self._sort = key

    def _ctx(self, pos):
        idx = self.view.indexAt(pos)
        if idx.isValid():
            self.context_requested.emit(idx.data(Qt.ItemDataRole.UserRole), self.view.viewport().mapToGlobal(pos))
