"""YouTube oynatıcısındaki dişli menüsüne benzeyen, sayfalı açılır ayarlar menüsü."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame, QSlider, QPushButton)

from . import icons
from .i18n import t
from .widgets import ToggleSwitch

MENU_QSS = """
#MenuCard { background: transparent; }
QLabel { color: #eeeeee; background: transparent; font-size: 13px; }
QLabel#MValue { color: #aaaaaa; }
QLabel#MHeader { font-size: 14px; font-weight: 600; }
QWidget#MRow { background: transparent; border-radius: 0px; }
QWidget#MRow:hover { background: rgba(255,255,255,0.10); }
QPushButton#MStep {
    background: rgba(255,255,255,0.10); color: #fff; border: none; border-radius: 14px;
    min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; font-size: 15px; font-weight: 600;
}
QPushButton#MStep:hover { background: rgba(255,255,255,0.20); }
QPushButton#MSmall {
    background: rgba(255,255,255,0.10); color: #fff; border: none; border-radius: 12px;
    padding: 3px 10px; font-size: 12px;
}
QPushButton#MSmall:hover { background: rgba(255,255,255,0.20); }
QPushButton#MSwatch { border: 2px solid transparent; border-radius: 11px; min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; }
QPushButton#MSwatch:checked { border: 2px solid #3ea6ff; }
QSlider::groove:horizontal { height: 4px; background: rgba(255,255,255,0.25); border-radius: 2px; }
QSlider::sub-page:horizontal { background: #ffffff; border-radius: 2px; }
QSlider::handle:horizontal { background: #ffffff; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: rgba(255,255,255,0.3); border-radius: 4px; min-height: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""


class _Row(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None, clickable=True):
        super().__init__(parent)
        self.setObjectName("MRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumHeight(40)
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(14, 0, 14, 0)
        self.lay.setSpacing(12)

    def mouseReleaseEvent(self, e):
        if self._clickable and e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()


def _icon_label(name, size=22):
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    if name:
        lbl.setPixmap(icons.pixmap(name, "#ffffff", size))
    return lbl


class PageBuilder:
    def __init__(self, menu, layout, is_root):
        self.menu = menu
        self.lay = layout
        self.is_root = is_root

    def header(self, title, extra=None):
        row = _Row(clickable=not self.is_root)
        row.setMinimumHeight(46)
        if not self.is_root:
            row.lay.addWidget(_icon_label("chevron_left", 20))
            row.clicked.connect(self.menu.back)
        lbl = QLabel(title)
        lbl.setObjectName("MHeader")
        row.lay.addWidget(lbl, 1)
        if extra:
            row.lay.addWidget(extra)
        self.lay.addWidget(row)
        self.separator()

    def separator(self):
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: rgba(255,255,255,0.15);")
        self.lay.addWidget(line)

    def nav(self, icon_name, text, value, builder):
        row = _Row()
        row.lay.addWidget(_icon_label(icon_name))
        row.lay.addWidget(QLabel(text), 1)
        v = QLabel(value or "")
        v.setObjectName("MValue")
        row.lay.addWidget(v)
        row.lay.addWidget(_icon_label("chevron_right", 18))
        row.clicked.connect(lambda: self.menu.push(builder))
        self.lay.addWidget(row)
        return row

    def action(self, icon_name, text, callback, close=True, value=""):
        row = _Row()
        row.lay.addWidget(_icon_label(icon_name))
        row.lay.addWidget(QLabel(text), 1)
        if value:
            v = QLabel(value)
            v.setObjectName("MValue")
            row.lay.addWidget(v)

        def go():
            if close:
                self.menu.close_menu()
            callback()
        row.clicked.connect(go)
        self.lay.addWidget(row)
        return row

    def toggle(self, icon_name, text, checked, callback):
        row = _Row()
        row.lay.addWidget(_icon_label(icon_name))
        row.lay.addWidget(QLabel(text), 1)
        sw = ToggleSwitch(checked, on_dark=True)
        sw.toggled.connect(callback)
        row.lay.addWidget(sw)
        row.clicked.connect(lambda: sw.setChecked(not sw.isChecked()))
        self.lay.addWidget(row)
        return sw

    def option(self, text, checked, callback, back=True, sub=""):
        row = _Row()
        row.setMinimumHeight(38)
        row.lay.addWidget(_icon_label("check" if checked else None, 20))
        lbl = QLabel(text)
        if checked:
            lbl.setStyleSheet("font-weight: 600;")
        row.lay.addWidget(lbl, 1)
        if sub:
            s = QLabel(sub)
            s.setObjectName("MValue")
            row.lay.addWidget(s)

        def go():
            callback()
            if back:
                self.menu.back()
            else:
                self.menu.refresh()
        row.clicked.connect(go)
        self.lay.addWidget(row)
        return row

    def stepper(self, label, value_text, on_minus, on_plus, on_reset=None):
        row = _Row(clickable=False)
        row.lay.addWidget(QLabel(label), 1)
        bm = QPushButton("−")
        bm.setObjectName("MStep")
        bm.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        val = QLabel(value_text)
        val.setMinimumWidth(70)
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bp = QPushButton("+")
        bp.setObjectName("MStep")
        bp.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        def mk(fn):
            def go():
                txt = fn()
                if txt is not None:
                    val.setText(txt)
            return go
        bm.clicked.connect(mk(on_minus))
        bp.clicked.connect(mk(on_plus))
        bm.setAutoRepeat(True)
        bp.setAutoRepeat(True)
        row.lay.addWidget(bm)
        row.lay.addWidget(val)
        row.lay.addWidget(bp)
        if on_reset:
            br = QPushButton(t("reset"))
            br.setObjectName("MSmall")
            br.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            br.clicked.connect(mk(on_reset))
            row.lay.addWidget(br)
        self.lay.addWidget(row)
        return val

    def slider(self, label, lo, hi, value, callback, fmt=lambda v: str(v)):
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(14, 6, 14, 6)
        bl.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(QLabel(label), 1)
        vl = QLabel(fmt(value))
        vl.setObjectName("MValue")
        top.addWidget(vl)
        bl.addLayout(top)
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(int(value))
        s.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        def ch(v):
            vl.setText(fmt(v))
            callback(v)
        s.valueChanged.connect(ch)
        bl.addWidget(s)
        self.lay.addWidget(box)
        return s

    def swatches(self, label, colors, current, callback):
        row = _Row(clickable=False)
        row.lay.addWidget(QLabel(label), 1)
        btns = []
        for c in colors:
            b = QPushButton()
            b.setObjectName("MSwatch")
            b.setCheckable(True)
            b.setChecked(c.lower() == (current or "").lower())
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QPushButton#MSwatch {{ background: {c}; }}")
            btns.append(b)

            def go(_=False, col=c, me=b):
                for o in btns:
                    o.setChecked(o is me)
                callback(col)
            b.clicked.connect(go)
            row.lay.addWidget(b)
        self.lay.addWidget(row)

    def note(self, text):
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: #aaaaaa; font-size: 12px; padding: 4px 14px 8px 14px;")
        self.lay.addWidget(lbl)


class MenuPopup(QWidget):
    closed = pyqtSignal()

    def __init__(self, parent=None, width=300):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(MENU_QSS)
        self._width = width
        self._stack = []
        self._anchor = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self.scroll)
        self.page = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, self.width() - 1, self.height() - 1, 12, 12)
        p.fillPath(path, QColor(28, 28, 28, 235))

    def open(self, builder, anchor_fn):
        """anchor_fn() -> (sağ_x, alt_y, maks_yükseklik) global koordinatlar."""
        self._stack = [builder]
        self._anchor = anchor_fn
        self._render()
        self.show()
        self.raise_()

    def push(self, builder):
        self._stack.append(builder)
        self._render()

    def back(self):
        if len(self._stack) > 1:
            self._stack.pop()
            self._render()
        else:
            self.close_menu()

    def refresh(self):
        self._render()

    def close_menu(self):
        self.hide()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.closed.emit()

    def _render(self):
        page = QWidget()
        page.setObjectName("MenuCard")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 8, 0, 8)
        lay.setSpacing(0)
        builder = self._stack[-1]
        builder(PageBuilder(self, lay, len(self._stack) == 1))
        lay.addStretch(1)
        old = self.scroll.takeWidget()
        if old:
            old.deleteLater()
        self.scroll.setWidget(page)
        page.setFixedWidth(self._width)
        page.adjustSize()
        h = page.sizeHint().height()
        right, bottom, max_h = self._anchor()
        h = min(h, max(160, max_h))
        self.setFixedSize(self._width + (10 if h < page.sizeHint().height() else 0), h)
        self.move(int(right - self.width()), int(bottom - self.height()))
