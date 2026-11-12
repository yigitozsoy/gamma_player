"""Üst çubuk: solda logo, ortada (isteğe bağlı) arama, sağda işlem düğmeleri ve pencere kontrolleri."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QLineEdit, QToolButton, QSizePolicy

from .i18n import t
from .theme import theme, tinted_logo
from .widgets import IconButton


class TitleBar(QWidget):
    search_changed = pyqtSignal(str)
    open_file = pyqtSignal()
    open_folder = pyqtSignal()
    theme_clicked = pyqtSignal()
    pin_clicked = pyqtSignal()
    prefs_clicked = pyqtSignal()
    sidebar_clicked = pyqtSignal()
    home_clicked = pyqtSignal()
    minimize = pyqtSignal()
    maximize = pyqtSignal()
    close = pyqtSignal()

    HEIGHT = 56

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(self.HEIGHT)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 0, 0)
        lay.setSpacing(4)

        brand = QWidget(self)
        brand.setCursor(Qt.CursorShape.PointingHandCursor)
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(8, 0, 4, 0)
        bl.setSpacing(5)
        self.logo = QLabel()
        theme.bind(self.logo, lambda l: l.setPixmap(tinted_logo(24, l.devicePixelRatioF())))
        bl.addWidget(self.logo)
        self.wordmark = QLabel("gamma")
        self.wordmark.setObjectName("Wordmark")
        bl.addWidget(self.wordmark)
        brand.mousePressEvent = lambda e: self.home_clicked.emit()
        self.brand = brand
        lay.addWidget(brand)
        # Seçenekler: oynatıcının ⚙ düğmesiyle karışmasın diye ayar sürgüleri simgesi
        self.btn_prefs = IconButton("more_horiz", t("preferences"), 36, 24)
        self.btn_prefs.clicked.connect(self.prefs_clicked.emit)
        self.left_box = QHBoxLayout()
        self.left_box.setSpacing(4)
        # "gamma" küçük harflerinin görsel ortasıyla aynı hizada dursun
        self.left_box.setContentsMargins(0, 6, 0, 0)
        lay.addLayout(self.left_box)

        lay.addStretch(1)
        self.search = QLineEdit(self)
        self.search.setObjectName("SearchBox")
        self.search.setPlaceholderText(t("search_placeholder"))
        self.search.setFixedHeight(40)
        self.search.setMinimumWidth(180)
        self.search.setMaximumWidth(540)
        self.search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.search.setClearButtonEnabled(True)
        self.search.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.search.textChanged.connect(self.search_changed.emit)
        lay.addWidget(self.search, 3)
        self.btn_search = QToolButton(self)
        self.btn_search.setObjectName("SearchBtn")
        self.btn_search.setFixedSize(64, 40)
        self.btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_search.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_search.setToolTip(t("search"))
        theme.icon(self.btn_search, "search", "text", 22)
        self.btn_search.clicked.connect(lambda: self.search_changed.emit(self.search.text()))
        lay.addWidget(self.btn_search)
        lay.addStretch(1)

        self.btn_open = IconButton("file_open", t("open_file_tip"), 40, 22)
        self.btn_open.clicked.connect(self.open_file.emit)
        self.btn_folder = IconButton("folder_open", t("open_folder_tip"), 40, 22)
        self.btn_folder.clicked.connect(self.open_folder.emit)
        self.btn_theme = IconButton("moon", t("theme_tip"), 40, 22)
        self.btn_theme.clicked.connect(self.theme_clicked.emit)
        self.btn_pin = IconButton("pin_outline", t("pin_tip"), 40, 21, checkable=True)
        self.btn_pin.clicked.connect(self.pin_clicked.emit)
        self.btn_menu = IconButton("queue", t("toggle_panel"), 40, 22, checkable=True)
        self.btn_menu.clicked.connect(self.sidebar_clicked.emit)
        self.right_box = QHBoxLayout()
        self.right_box.setSpacing(4)
        lay.addLayout(self.right_box)
        self._tb_widgets = {"prefs": self.btn_prefs, "open_file": self.btn_open, "open_folder": self.btn_folder,
                            "theme": self.btn_theme, "pin": self.btn_pin, "panel": self.btn_menu}
        self._pin_allowed = True
        lay.addSpacing(10)

        self.btn_min = self._win_btn("win_min", "WinBtn", self.minimize)
        self.btn_max = self._win_btn("win_max", "WinBtn", self.maximize)
        self.btn_close = self._win_btn("close", "WinClose", self.close)
        for b in (self.btn_min, self.btn_max, self.btn_close):
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        self.update_theme_icon()
        theme.changed.connect(lambda _: self.update_theme_icon())
        from .config import prefs
        self.set_search_visible(bool(prefs.get("show_search", False)))
        self.apply_personalization()

    def apply_personalization(self):
        """Düğmelerin sol/sağ grup, sıra ve görünürlüğünü tercihlerden uygular."""
        from . import layout_prefs as lp
        for box in (self.left_box, self.right_box):
            while box.count():
                box.takeAt(0)
        box = self.left_box
        for key, vis in lp.layout("titlebar"):
            if key == lp.SEP:
                box = self.right_box
                continue
            w = self._tb_widgets.get(key)
            if w is None:
                continue
            box.addWidget(w)
            show = bool(vis) and (key != "pin" or self._pin_allowed)
            w.setVisible(show)

    def set_search_visible(self, on):
        self.search.setVisible(on)
        self.btn_search.setVisible(on)
        if not on and self.search.text():
            self.search.clear()

    def set_sidebar_checked(self, on):
        self.btn_menu.setChecked(on)

    def is_drag_area(self, widget):
        """Pencereyi sürüklemek / Windows Snap için başlık çubuğunun boş alanı mı?"""
        return widget is self or widget is None

    def _win_btn(self, icon_name, obj, sig):
        b = QToolButton(self)
        b.setObjectName(obj)
        b.setFixedSize(46, 34)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        theme.icon(b, icon_name, "text", 16)
        b.clicked.connect(sig.emit)
        return b

    def update_theme_icon(self):
        from .theme import current_name
        dark = current_name() == "dark"
        self.btn_theme.set_icon_name("sun" if dark else "moon")
        self.btn_theme.setToolTip(t("light_mode") if dark else t("dark_mode"))

    def set_pinned(self, on):
        self.btn_pin.setChecked(on)
        self.btn_pin.set_icon_name("pin" if on else "pin_outline")
        self.btn_pin.setToolTip(t("unpin_tip") if on else t("pin_tip"))

    def set_pin_allowed(self, allowed):
        self._pin_allowed = allowed
        self.apply_personalization()

    def set_maximized(self, on):
        theme.icon(self.btn_max, "win_restore" if on else "win_max", "text", 16)

    # Sürükleme, çift tıkla büyütme ve kenara yaslama (Snap) normalde Windows tarafından yapılır:
    # MainWindow.nativeEvent bu alan için HTCAPTION döndürür. Olay yine de buraya ulaşırsa
    # (ör. başlık ayrı bir yerel pencere olursa) aynı işi Qt üzerinden yap.
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self.window().isFullScreen():
            h = self.window().windowHandle()
            if h:
                h.startSystemMove()
                return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.maximize.emit()
            return
        super().mouseDoubleClickEvent(e)
