"""Tercihler, medya bilgisi ve kısayollar pencereleri."""
import os
import shutil
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QSpinBox, QScrollArea, QLineEdit,
                             QWidget, QFileDialog, QPlainTextEdit, QGridLayout, QMessageBox, QApplication,
                             QListWidget, QListWidgetItem, QStackedWidget)

from . import __version__
from .config import prefs, CACHE_DIR, THUMB_DIR
from .i18n import t
from .library import human_size, fmt_time
from .theme import theme
from .widgets import ThemedDialog, ToggleSwitch
from . import thumbs


def _row(label, control, desc=""):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 6, 0, 6)
    col = QVBoxLayout()
    col.setSpacing(1)
    lbl = QLabel(label)
    lbl.setStyleSheet("font-size: 14px;")
    col.addWidget(lbl)
    if desc:
        d = QLabel(desc)
        d.setObjectName("Secondary")
        d.setWordWrap(True)
        d.setMinimumWidth(120)
        col.addWidget(d)
    lay.addLayout(col, 1)
    lay.addSpacing(16)
    if isinstance(control, (list, tuple)):
        for c in control:
            lay.addWidget(c)
    else:
        lay.addWidget(control)
    return w


def _subsection(title, desc=""):
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 18, 0, 6)
    v.setSpacing(2)
    a = QLabel(title)
    a.setStyleSheet("font-size: 14px; font-weight: 700;")
    v.addWidget(a)
    if desc:
        b = QLabel(desc)
        b.setObjectName("Secondary")
        b.setWordWrap(True)
        v.addWidget(b)
    return w


def _section(title):
    lbl = QLabel(title)
    lbl.setObjectName("SectionTitle")
    lbl.setContentsMargins(0, 14, 0, 2)
    return lbl


LAYOUT_LABELS = {
    "titlebar": {
        "prefs": ("Seçenekler", "Preferences"), "open_file": ("Dosya aç", "Open file"),
        "open_folder": ("Klasör aç", "Open folder"), "theme": ("Karanlık/aydınlık tema", "Dark/light theme"),
        "pin": ("Her zaman üstte", "Always on top"), "panel": ("Yan paneli aç/kapat", "Toggle side panel"),
    },
    "player": {
        "prev": ("Önceki", "Previous"), "play": ("Oynat / duraklat (her zaman görünür)", "Play / pause (always shown)"),
        "next": ("Sonraki", "Next"), "loop": ("Döngü", "Loop"), "volume": ("Ses", "Volume"),
        "time": ("Süre", "Time"), "autoplay": ("Otomatik oynatma anahtarı", "Autoplay switch"),
        "snapshot": ("Ekran görüntüsü", "Snapshot"), "stretch": ("16:9'a uzat", "Stretch to 16:9"),
        "cc": ("Altyazı (CC)", "Subtitles (CC)"), "settings": ("Ayarlar ⚙", "Settings ⚙"),
        "pip": ("Mini oynatıcı", "Miniplayer"), "theater": ("Sinema modu", "Theater mode"),
        "fullscreen": ("Tam ekran", "Full screen"),
    },
    "infobar": {
        "edit": ("Kes / Düzenle", "Cut / Edit"), "snapshot": ("Ekran görüntüsü", "Snapshot"),
        "subtitle": ("Altyazı ekle", "Add subtitle"), "reveal": ("Klasörde göster", "Show in folder"),
        "info": ("Bilgi", "Info"), "delete": ("Sil", "Delete"), "more": ("Diğer ⋮", "More ⋮"),
    },
}


def _lbl(pair):
    return pair[0] if prefs.get("language", "tr") == "tr" else pair[1]


class LayoutEditor(QListWidget):
    """Onay kutulu, sürükle-bırak ile sıralanabilen düğme listesi."""

    def __init__(self, group, on_change, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QAbstractItemView
        from . import layout_prefs as lp
        self.group = group
        self.on_change = on_change
        self.lp = lp
        self.setObjectName("LayoutEditor")
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._loading = True
        required = lp.GROUPS[group][2]
        for key, vis in lp.layout(group):
            if key == lp.SEP:
                it = QListWidgetItem("⠿   ——  " + t("lay_right_side") + "  ——")
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                f = it.font()
                f.setItalic(True)
                it.setFont(f)
            else:
                it = QListWidgetItem("⠿   " + _lbl(LAYOUT_LABELS[group].get(key, (key, key))))
                fl = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
                if key not in required:
                    fl |= Qt.ItemFlag.ItemIsUserCheckable
                it.setFlags(fl)
                it.setCheckState(Qt.CheckState.Checked if vis else Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, key)
            self.addItem(it)
        self._loading = False
        self.itemChanged.connect(self._save)
        self.model().rowsMoved.connect(lambda *a: self._save())
        self._fit_height()

    def _fit_height(self):
        # Satır yükseklikleri ancak stil uygulandıktan sonra doğru ölçülür
        rows = sum(max(self.sizeHintForRow(i), 1) for i in range(self.count()))
        self.setFixedHeight(rows + 2 * self.frameWidth() + 10)

    def showEvent(self, e):
        super().showEvent(e)
        self._fit_height()

    def _save(self, *_):
        if self._loading:
            return
        items = []
        for i in range(self.count()):
            it = self.item(i)
            key = it.data(Qt.ItemDataRole.UserRole)
            vis = True if key == self.lp.SEP else it.checkState() == Qt.CheckState.Checked
            items.append([key, vis])
        self.lp.set_layout(self.group, items)
        self.on_change()


PREFS_QSS = """
QListWidget#PrefNav { background: transparent; border: none; outline: none; font-size: 14px; }
QListWidget#PrefNav::item { padding: 9px 14px; border-radius: 10px; margin: 1px 6px; }
QListWidget#PrefNav::item:hover { background: rgba(128,128,128,0.15); }
QListWidget#PrefNav::item:selected { background: rgba(128,128,128,0.28); color: palette(text); }
QListWidget#LayoutEditor { border: 1px solid rgba(128,128,128,0.35); border-radius: 10px; padding: 3px; outline: none; }
QListWidget#LayoutEditor::item { padding: 6px 8px; border-radius: 6px; }
QListWidget#LayoutEditor::item:hover { background: rgba(128,128,128,0.15); }
QListWidget#LayoutEditor::item:selected { background: rgba(128,128,128,0.25); color: palette(text); }
"""


class PreferencesDialog(ThemedDialog):
    PAGES = ["general", "appearance", "personal", "window", "playback", "subtitles", "files", "shortcuts", "about"]
    ICONS = {"general": "settings", "appearance": "palette", "personal": "tune", "window": "pip",
             "playback": "play", "subtitles": "subtitles", "files": "folder", "shortcuts": "keyboard", "about": "info"}

    def __init__(self, win, page=None):
        super().__init__(win, t("preferences"))
        self.win = win
        self.resize(900, 660)
        self.setStyleSheet(PREFS_QSS)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QHBoxLayout()
        body.setContentsMargins(8, 10, 0, 0)
        body.setSpacing(6)
        outer.addLayout(body, 1)
        self.nav = QListWidget()
        self.nav.setObjectName("PrefNav")
        self.nav.setFixedWidth(220)
        self.nav.setIconSize(QSize(20, 20))
        self.stack = QStackedWidget()
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        builders = {"general": self._page_general, "appearance": self._page_appearance,
                    "personal": self._page_personal, "window": self._page_window,
                    "playback": self._page_playback, "subtitles": self._page_subtitles,
                    "files": self._page_files, "shortcuts": self._page_shortcuts, "about": self._page_about}
        from . import icons
        from .theme import color
        for key in self.PAGES:
            it = QListWidgetItem(icons.icon(self.ICONS[key], color("text"), 20), "  " + t("cat_" + key))
            self.nav.addItem(it)
            self.stack.addWidget(self._scroll_page(builders[key]))
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(self.PAGES.index(page) if page in self.PAGES else 0)

        btns = QHBoxLayout()
        btns.setContentsMargins(20, 10, 20, 14)
        btns.addStretch(1)
        ok = QPushButton(t("close"))
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        btns.addWidget(ok)
        outer.addLayout(btns)

    # ---------------------------------------------------------------- yardımcılar
    def _scroll_page(self, builder):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(22, 4, 26, 20)
        lay.setSpacing(0)
        builder(lay)
        lay.addStretch(1)
        return scroll

    def _toggle(self, key, on_change=None, default=False):
        from . import layout_prefs as lp
        cur = lp.get(key) if key in lp.BEHAVIOR_DEFAULTS else prefs.get(key, default)
        sw = ToggleSwitch(bool(cur))

        def ch(v):
            prefs.set(key, v)
            if on_change:
                on_change(v)
        sw.toggled.connect(ch)
        return sw

    def _combo(self, key, options, on_change=None):
        from . import layout_prefs as lp
        cur = lp.get(key) if key in lp.BEHAVIOR_DEFAULTS else prefs.get(key)
        cmb = QComboBox()
        for label, value in options:
            cmb.addItem(label, value)
        idx = next((i for i, (_, v) in enumerate(options) if v == cur), 0)
        cmb.setCurrentIndex(idx)

        def ch(i):
            prefs.set(key, cmb.itemData(i))
            if on_change:
                on_change()
        cmb.currentIndexChanged.connect(ch)
        return cmb

    def _personal_changed(self, *_):
        self.win.apply_personalization()

    # ---------------------------------------------------------------- sayfalar
    def _page_general(self, lay):
        lay.addWidget(_section(t("cat_general")))
        self.cmb_lang = QComboBox()
        self.cmb_lang.addItem("Türkçe", "tr")
        self.cmb_lang.addItem("English", "en")
        self.cmb_lang.setCurrentIndex(0 if prefs.get("language") == "tr" else 1)
        self.cmb_lang.currentIndexChanged.connect(self._lang)
        lay.addWidget(_row(t("language"), self.cmb_lang, t("language_restart")))
        lay.addWidget(_row(t("single_instance"), self._toggle("single_instance", default=True),
                           t("single_instance_desc")))

    def _page_appearance(self, lay):
        lay.addWidget(_section(t("cat_appearance")))
        from .theme import VARIANTS, variant_label, current_variant
        self.cmb_theme = QComboBox()
        for fam, head in (("dark", t("dark_mode")), ("light", t("light_mode"))):
            for v, data in VARIANTS.items():
                if data[2] == fam:
                    self.cmb_theme.addItem(f"{head} — {variant_label(v)}", v)
        keys = [self.cmb_theme.itemData(i) for i in range(self.cmb_theme.count())]
        self.cmb_theme.setCurrentIndex(keys.index(current_variant()))
        self.cmb_theme.currentIndexChanged.connect(self._theme)
        lay.addWidget(_row(t("theme"), self.cmb_theme, t("theme_variants_desc")))
        lay.addWidget(_row(t("accent_color"), self._accent_swatches(), t("accent_desc")))

    def _page_personal(self, lay):
        lay.addWidget(_section(t("cat_personal")))
        intro = QLabel(t("personal_intro"))
        intro.setObjectName("Secondary")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        rb = QPushButton(t("personal_reset"))
        rb.setObjectName("Pill")
        rb.setFixedHeight(32)
        rb.clicked.connect(self._reset_personal)
        lay.addWidget(_row(t("personal_reset_label"), rb, t("personal_reset_desc")))

        for group, title_key, desc_key in (("titlebar", "lay_titlebar", "lay_titlebar_desc"),
                                           ("player", "lay_player", "lay_player_desc"),
                                           ("infobar", "lay_infobar", "lay_infobar_desc")):
            lay.addWidget(_subsection(t(title_key), t(desc_key)))
            lay.addWidget(LayoutEditor(group, self._personal_changed))

        lay.addWidget(_subsection(t("lay_panels"), ""))
        pc = self._personal_changed
        lay.addWidget(_row(t("p_sidebar_side"), self._combo("sidebar_side", [(t("right"), "right"), (t("left"), "left")], pc)))
        lay.addWidget(_row(t("p_sidebar_autoshow"), self._toggle("sidebar_autoshow"), t("p_sidebar_autoshow_desc")))
        lay.addWidget(_row(t("p_thumb_size"), self._combo("thumb_size", [(t("small"), "small"), (t("normal"), "normal"),
                                                                          (t("large"), "large")], pc)))
        lay.addWidget(_row(t("p_sidebar_meta"), self._toggle("sidebar_meta", lambda v: pc())))
        lay.addWidget(_row(t("p_show_infobar"), self._toggle("show_infobar", lambda v: pc()), t("p_show_infobar_desc")))
        lay.addWidget(_row(t("show_search"), self._toggle("show_search", lambda v: self.win.titlebar.set_search_visible(v)),
                           t("show_search_desc")))
        lay.addWidget(_row(t("p_show_recent"), self._toggle("show_recent", lambda v: pc())))

        lay.addWidget(_subsection(t("lay_player_behavior"), ""))
        lay.addWidget(_row(t("p_autohide"), self._combo("autohide_ms", [("1,5 sn", 1500), ("2,5 sn", 2600), ("4 sn", 4000),
                                                                         ("6 sn", 6000), (t("never"), 0)], pc)))
        lay.addWidget(_row(t("p_seek_preview"), self._toggle("seek_preview"), t("p_seek_preview_desc")))
        lay.addWidget(_row(t("p_mini_progress"), self._toggle("mini_progress", lambda v: pc()), t("p_mini_progress_desc")))
        lay.addWidget(_row(t("p_time_display"), self._combo("time_display", [(t("elapsed"), "elapsed"),
                                                                              (t("remaining"), "remaining")], pc)))
        lay.addWidget(_row(t("p_flash"), self._toggle("flash_anim"), t("p_flash_desc")))
        lay.addWidget(_row(t("p_title_fs"), self._toggle("show_title_fullscreen", lambda v: pc())))

        lay.addWidget(_subsection(t("lay_mouse_keys"), ""))
        lay.addWidget(_row(t("p_click"), self._combo("click_action", [(t("play_pause"), "play"), (t("nothing"), "none")])))
        lay.addWidget(_row(t("p_dblclick"), self._toggle("dblclick_fullscreen")))
        lay.addWidget(_row(t("p_right_speed"), self._toggle("right_speed"), t("p_right_speed_desc")))
        lay.addWidget(_row(t("p_wheel"), self._combo("wheel_action", [(t("volume"), "volume"), (t("seek"), "seek"),
                                                                       (t("nothing"), "none")])))
        lay.addWidget(_row(t("p_seek_step"), self._combo("seek_step", [("5 sn", 5), ("10 sn", 10), ("15 sn", 15),
                                                                        ("30 sn", 30)])))
        lay.addWidget(_row(t("p_confirm_delete"), self._toggle("confirm_delete")))
        lay.addWidget(_row(t("p_osd"), self._toggle("osd_messages"), t("p_osd_desc")))

    def _page_window(self, lay):
        win = self.win
        lay.addWidget(_section(t("cat_window")))
        sw = ToggleSwitch(win._pinned)
        sw.toggled.connect(lambda v: win.set_pinned(v))
        self.sw_pinned = sw
        lay.addWidget(_row(t("pin_tip"), sw, t("pin_desc")))
        sw = ToggleSwitch(bool(prefs.get("pin_enabled", True)))
        sw.toggled.connect(self._pin_feature)
        lay.addWidget(_row(t("pin_feature"), sw, t("pin_feature_desc")))
        sw = ToggleSwitch(bool(prefs.get("pip_enabled", True)))
        sw.toggled.connect(self._pip_feature)
        lay.addWidget(_row(t("pip_feature"), sw, t("pip_feature_desc")))
        b = QPushButton(t("pip_open_now"))
        b.setObjectName("Pill")
        b.setFixedHeight(32)
        b.clicked.connect(lambda: (self.accept(), QTimer.singleShot(100, win.toggle_pip)))
        b.setEnabled(win.current is not None)
        lay.addWidget(_row(t("pip_mode"), b, t("pip_desc")))

    def _page_playback(self, lay):
        win = self.win
        lay.addWidget(_section(t("cat_playback")))
        lay.addWidget(_row(t("autoplay"), self._toggle("autoplay", lambda v: win.overlay.set_autoplay(v), True),
                           t("autoplay_desc")))
        lay.addWidget(_row(t("resume"), self._toggle("resume", default=True), t("resume_desc")))
        sw = ToggleSwitch(bool(prefs.get("hw_decode", True)))
        sw.toggled.connect(self._hw)
        lay.addWidget(_row(t("hw_decode"), sw, t("hw_decode_desc")))
        sp = QSpinBox()
        sp.setRange(1, 60)
        sp.setSuffix(" sn" if prefs.get("language") == "tr" else " s")
        sp.setValue(int(prefs.get("slideshow_seconds", 4)))
        sp.valueChanged.connect(lambda v: prefs.set("slideshow_seconds", v))
        lay.addWidget(_row(t("slideshow_interval"), sp))

    def _page_subtitles(self, lay):
        lay.addWidget(_section(t("cat_subtitles")))
        from .player_menu import ENCODINGS, _enc_label
        self.cmb_enc = QComboBox()
        for enc, _ in ENCODINGS:
            self.cmb_enc.addItem(_enc_label(enc), enc)
        cur = prefs.get("sub_encoding", "auto")
        keys = [e for e, _ in ENCODINGS]
        self.cmb_enc.setCurrentIndex(keys.index(cur) if cur in keys else 0)
        self.cmb_enc.currentIndexChanged.connect(self._enc)
        lay.addWidget(_row(t("sub_encoding"), self.cmb_enc, t("sub_encoding_note")))
        lay.addWidget(_row(t("sub_style"), QLabel(""), t("sub_style_where")))

    def _page_files(self, lay):
        lay.addWidget(_section(t("cat_files")))
        from .widgets import ElidedLabel
        self.lbl_snap = ElidedLabel(prefs.get("snapshot_dir") or os.path.join(os.path.expanduser("~"), "Pictures", "gamma"))
        self.lbl_snap.setObjectName("Secondary")
        b = QPushButton(t("change"))
        b.setObjectName("Pill")
        b.setFixedHeight(32)
        b.clicked.connect(self._snapdir)
        lay.addWidget(_row(t("snapshot_dir"), b))
        lay.addWidget(self.lbl_snap)
        b1 = QPushButton(t("add"))
        b1.setObjectName("Pill")
        b1.setFixedHeight(32)
        b1.clicked.connect(lambda: self._shell(True))
        b2 = QPushButton(t("remove"))
        b2.setObjectName("Pill")
        b2.setFixedHeight(32)
        b2.clicked.connect(lambda: self._shell(False))
        lay.addWidget(_row(t("context_menu"), [b1, b2], t("context_menu_desc")))
        b = QPushButton(t("clear_cache"))
        b.setObjectName("Pill")
        b.setFixedHeight(32)
        b.clicked.connect(self._clear_cache)
        lay.addWidget(_row(t("thumb_cache"), b, self._cache_size()))

    def _page_shortcuts(self, lay):
        lay.addWidget(_section(t("cat_shortcuts")))
        from .shortcuts import SHORTCUTS
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 6, 0, 0)
        grid.setVerticalSpacing(8)
        grid.setHorizontalSpacing(18)
        for r, (keys, desc) in enumerate(SHORTCUTS):
            k = QLabel(keys)
            k.setStyleSheet("font-family: 'Cascadia Mono', Consolas, monospace; font-weight: 600;")
            d = QLabel(t(desc))
            d.setWordWrap(True)
            grid.addWidget(k, r, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(d, r, 1)
        grid.setColumnStretch(1, 1)
        lay.addWidget(box)

    def _page_about(self, lay):
        lay.addWidget(_section(t("about")))
        lay.addWidget(self._about_box())

    def _reset_personal(self):
        from . import layout_prefs as lp
        r = QMessageBox.question(self, t("personal_reset"), t("personal_reset_confirm"))
        if r != QMessageBox.StandardButton.Yes:
            return
        lp.reset_all()
        self.win.titlebar.set_search_visible(False)
        self.win.apply_personalization()
        win = self.win
        self.done(0)
        QTimer.singleShot(0, lambda: PreferencesDialog(win, "personal").exec())

    def _accent_swatches(self):
        """Renk kutusu (tıklayınca palet) + #RRGGBB kodu + varsayılana dön."""
        from PyQt6.QtGui import QRegularExpressionValidator
        from PyQt6.QtCore import QRegularExpression
        from .theme import accent
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.btn_color = QPushButton()
        self.btn_color.setFixedSize(40, 28)
        self.btn_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_color.setToolTip(t("pick_color"))
        self.btn_color.clicked.connect(self._pick_color)
        self.ed_color = QLineEdit()
        self.ed_color.setFixedWidth(86)
        self.ed_color.setPlaceholderText("#RRGGBB")
        self.ed_color.setValidator(QRegularExpressionValidator(QRegularExpression(r"#?[0-9A-Fa-f]{0,6}")))
        self.ed_color.editingFinished.connect(self._color_from_text)
        from .widgets import IconButton
        reset = IconButton("undo", t("default"), 30, 18)
        reset.clicked.connect(lambda: self._apply_accent("gray"))
        h.addWidget(self.btn_color)
        h.addWidget(self.ed_color)
        h.addWidget(reset)
        self._show_accent(accent())
        return box

    def _show_accent(self, col):
        self.btn_color.setStyleSheet(f"QPushButton {{ background: {col}; border: 1px solid rgba(128,128,128,0.6);"
                                     f" border-radius: 6px; }}")
        self.ed_color.setText(col.upper())

    def _pick_color(self):
        from PyQt6.QtWidgets import QColorDialog
        from PyQt6.QtGui import QColor
        from .theme import accent
        c = QColorDialog.getColor(QColor(accent()), self, t("pick_color"))
        if c.isValid():
            self._apply_accent(c.name())

    def _color_from_text(self):
        txt = self.ed_color.text().strip()
        if not txt.startswith("#"):
            txt = "#" + txt
        if len(txt) == 4:  # #abc -> #aabbcc
            txt = "#" + "".join(ch * 2 for ch in txt[1:])
        if len(txt) == 7:
            self._apply_accent(txt.lower())
        else:
            from .theme import accent
            self._show_accent(accent())

    def _apply_accent(self, value):
        from .theme import accent
        prefs.set("accent", value)
        theme.apply()
        self._show_accent(accent())
        self.win.overlay.seekbar.update()
        self.win.sidebar.view.viewport().update()
        for sw in self.findChildren(ToggleSwitch):
            sw.update()

    def _about_box(self):
        import platform
        from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
        from . import __author__
        rows = [(t("about_app"), f"gamma {__version__}"),
                (t("about_author"), __author__),
                (t("about_license"), "GNU GPL v3.0"),
                (t("about_desc_k"), t("about_line"))]
        engines = []
        try:
            from .vlc_engine import vlc
            if vlc is not None:
                engines.append(("VLC / libVLC", vlc.libvlc_get_version().decode(errors="ignore")))
        except Exception:
            pass
        try:
            import imageio_ffmpeg
            engines.append(("FFmpeg", imageio_ffmpeg.get_ffmpeg_version()))
        except Exception:
            pass
        engines.append(("Qt / PyQt6", f"{QT_VERSION_STR} / {PYQT_VERSION_STR}"))
        engines.append(("Python", platform.python_version()))
        for mod, label in (("PIL", "Pillow"), ("pillow_heif", "pillow-heif (HEIC/AVIF)"),
                           ("imagecodecs", "imagecodecs (JPEG XL)"), ("numpy", "NumPy")):
            try:
                m = __import__(mod)
                engines.append((label, getattr(m, "__version__", "")))
            except Exception:
                pass
        box = QWidget()
        g = QGridLayout(box)
        g.setContentsMargins(0, 6, 0, 0)
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(5)
        r = 0
        for k, v in rows:
            a = QLabel(k)
            a.setObjectName("Secondary")
            b = QLabel(v)
            b.setWordWrap(True)
            b.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            g.addWidget(a, r, 0, Qt.AlignmentFlag.AlignTop)
            g.addWidget(b, r, 1)
            r += 1
        head = QLabel(t("about_engines"))
        head.setStyleSheet("font-weight: 700; margin-top: 8px;")
        g.addWidget(head, r, 0, 1, 2)
        r += 1
        for k, v in engines:
            a = QLabel(k)
            a.setObjectName("Secondary")
            b = QLabel(str(v))
            b.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            g.addWidget(a, r, 0)
            g.addWidget(b, r, 1)
            r += 1
        note = QLabel(t("about_licenses_note"))
        note.setObjectName("Secondary")
        note.setWordWrap(True)
        g.addWidget(note, r, 0, 1, 2)
        g.setColumnStretch(1, 1)
        return box

    def _theme(self, i):
        theme.apply(self.cmb_theme.itemData(i))
        if self.win.current:
            self.win.info.set_details(self.win.current)

    def _lang(self, i):
        prefs.set("language", self.cmb_lang.itemData(i))
        r = QMessageBox.question(self, t("language"), t("restart_now"))
        if r == QMessageBox.StandardButton.Yes:
            from .app import restart
            restart(self.win)

    def _pin_feature(self, v):
        prefs.set("pin_enabled", v)
        self.win.apply_feature_toggles()
        if not v:
            self.sw_pinned.setChecked(False, emit=False)

    def _pip_feature(self, v):
        prefs.set("pip_enabled", v)
        self.win.apply_feature_toggles()

    def _hw(self, v):
        prefs.set("hw_decode", v)
        self.win._schedule_rebuild()

    def _enc(self, i):
        prefs.set("sub_encoding", self.cmb_enc.itemData(i))
        self.win._schedule_rebuild()

    def _snapdir(self):
        d = QFileDialog.getExistingDirectory(self, t("snapshot_dir"), self.lbl_snap.full_text())
        if d:
            prefs.set("snapshot_dir", d)
            self.lbl_snap.setText(d)

    def _shell(self, add):
        from . import shell
        try:
            if add:
                shell.register()
                QMessageBox.information(self, t("context_menu"), t("context_menu_added"))
            else:
                shell.unregister()
                QMessageBox.information(self, t("context_menu"), t("context_menu_removed"))
        except Exception as e:
            QMessageBox.warning(self, t("context_menu"), str(e))

    def _cache_size(self):
        total = 0
        for root, _, files in os.walk(CACHE_DIR):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        return human_size(total) or "0 B"

    def _clear_cache(self):
        shutil.rmtree(THUMB_DIR, ignore_errors=True)
        os.makedirs(THUMB_DIR, exist_ok=True)
        QMessageBox.information(self, t("thumb_cache"), t("cache_cleared"))


class MediaInfoDialog(ThemedDialog):
    def __init__(self, item, parent=None):
        super().__init__(parent, t("act_info"))
        self.resize(720, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(10)
        title = QLabel(item.name)
        title.setObjectName("VideoTitle")
        title.setWordWrap(True)
        lay.addWidget(title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)
        try:
            st = os.stat(item.path)
            created = datetime.fromtimestamp(st.st_ctime).strftime("%d.%m.%Y %H:%M")
            modified = datetime.fromtimestamp(st.st_mtime).strftime("%d.%m.%Y %H:%M")
            size = f"{human_size(st.st_size)} ({st.st_size:,} B)".replace(",", ".")
        except OSError:
            created = modified = size = "-"
        rows = [(t("path"), item.path), (t("type"), f"{t(item.kind)} • {item.ext.strip('.').upper()}"),
                (t("size"), size), (t("created"), created), (t("modified"), modified)]
        if item.width:
            rows.append((t("resolution"), f"{item.width} × {item.height}"))
        if item.duration and item.duration > 0 and not item.is_image:
            rows.append((t("duration"), fmt_time(item.duration)))
        for r, (k, v) in enumerate(rows):
            a = QLabel(k)
            a.setObjectName("Secondary")
            b = QLabel(v)
            b.setWordWrap(True)
            b.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(a, r, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(b, r, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText(t("loading"))
        lay.addWidget(self.text, 1)
        btns = QHBoxLayout()
        cp = QPushButton(t("copy"))
        cp.setObjectName("Pill")
        cp.clicked.connect(lambda: QApplication.clipboard().setText(self.text.toPlainText()))
        btns.addWidget(cp)
        btns.addStretch(1)
        ok = QPushButton(t("close"))
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        btns.addWidget(ok)
        lay.addLayout(btns)
        if item.is_image:
            thumbs.run_async(self._image_info, item.path, on_done=self._set)
        else:
            thumbs.run_async(thumbs.probe, item.path, on_done=self._set_probe)

    @staticmethod
    def _image_info(path):
        from PIL import Image
        from PIL.ExifTags import TAGS
        lines = []
        try:
            from . import image_io
            image_io._ensure_heif()
            with Image.open(path) as im:
                lines.append(f"Format: {im.format}  Mod: {im.mode}  Boyut: {im.size[0]}×{im.size[1]}")
                if getattr(im, "n_frames", 1) > 1:
                    lines.append(f"Kare sayısı: {im.n_frames}")
                for k, v in (im.info or {}).items():
                    if k in ("exif", "icc_profile", "xmp") or isinstance(v, (bytes, bytearray)):
                        continue
                    lines.append(f"{k}: {v}")
                exif = im.getexif()
                if exif:
                    lines.append("")
                    lines.append("EXIF")
                    for tag, val in exif.items():
                        name = TAGS.get(tag, tag)
                        if isinstance(val, bytes):
                            continue
                        lines.append(f"  {name}: {val}")
        except Exception as e:
            lines.append(str(e))
        return "\n".join(lines)

    def _set(self, text):
        self.text.setPlainText(text)

    def _set_probe(self, text):
        out = []
        for ln in text.splitlines():
            if ln.startswith("At least one output") or ln.startswith("Input #0"):
                continue
            out.append(ln)
        self.text.setPlainText("\n".join(out).strip())


class ShortcutsDialog(ThemedDialog):
    def __init__(self, parent=None):
        super().__init__(parent, t("shortcuts"))
        self.resize(560, 700)
        from .shortcuts import SHORTCUTS
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        grid = QGridLayout(body)
        grid.setContentsMargins(18, 14, 18, 14)
        grid.setVerticalSpacing(8)
        grid.setHorizontalSpacing(18)
        for r, (keys, desc) in enumerate(SHORTCUTS):
            k = QLabel(keys)
            k.setStyleSheet("font-family: 'Cascadia Mono', Consolas, monospace; font-weight: 600;")
            d = QLabel(t(desc))
            d.setWordWrap(True)
            grid.addWidget(k, r, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(d, r, 1)
        grid.setColumnStretch(1, 1)
        ok = QPushButton(t("close"))
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(ok)
        outer.addLayout(h)



class ConvertDialog(ThemedDialog):
    """Görseli düzenlemeden başka biçime dönüştürür (orijinal korunur)."""

    def __init__(self, item, parent=None, on_done=None):
        super().__init__(parent, t("convert_title"))
        from . import image_io
        self.item = item
        self.on_done = on_done
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(10)
        title = QLabel(item.name)
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        title.setWordWrap(True)
        lay.addWidget(title)
        self.cmb = QComboBox()
        src = item.ext
        for label, ext, lossy in image_io.OUTPUT_FORMATS:
            if ext == src or (ext == ".jpg" and src in (".jpeg", ".jpe", ".jfif")):
                continue
            self.cmb.addItem(label, (ext, lossy))
        self.cmb.currentIndexChanged.connect(self._fmt)
        lay.addWidget(_row(t("format"), self.cmb))
        self.cmb_q = QComboBox()
        for q in (100, 95, 92, 85, 75, 60):
            self.cmb_q.addItem(t("quality_n", n=q), q)
        self.cmb_q.setCurrentIndex(2)
        lay.addWidget(_row(t("quality"), self.cmb_q))
        self.lbl = QLabel("")
        self.lbl.setObjectName("Secondary")
        self.lbl.setWordWrap(True)
        lay.addWidget(self.lbl)
        btns = QHBoxLayout()
        btns.addStretch(1)
        c = QPushButton(t("cancel"))
        c.setObjectName("Flat")
        c.clicked.connect(self.reject)
        self.ok = QPushButton(t("convert"))
        self.ok.setObjectName("Primary")
        self.ok.clicked.connect(self._go)
        btns.addWidget(c)
        btns.addWidget(self.ok)
        lay.addLayout(btns)
        self._fmt()

    def _target(self):
        ext, _ = self.cmb.currentData()
        return os.path.splitext(self.item.path)[0] + ext

    def _fmt(self, *_):
        ext, lossy = self.cmb.currentData()
        self.cmb_q.setEnabled(lossy)
        self.lbl.setText(t("convert_note", name=os.path.basename(self._target())))

    def _go(self):
        from . import image_io
        target = self._target()
        if os.path.exists(target):
            r = QMessageBox.question(self, t("convert_title"), t("file_exists_overwrite"))
            if r != QMessageBox.StandardButton.Yes:
                return
        self.ok.setEnabled(False)
        self.ok.setText(t("loading"))
        q = self.cmb_q.currentData()
        src = self.item.path

        def work():
            img = image_io.open_pil(src)
            if getattr(img, "n_frames", 1) > 1:
                img.seek(0)
            tmp = target + ".gamma-tmp" + os.path.splitext(target)[1]
            image_io.save_pil(img, tmp, quality=q)
            os.replace(tmp, target)
            return target

        def done(p):
            if self.on_done:
                self.on_done(p)
            self.accept()

        def fail(msg):
            self.ok.setEnabled(True)
            self.ok.setText(t("convert"))
            QMessageBox.warning(self, t("convert_title"), t("save_failed") + "\n" + msg)
        thumbs.run_async(work, on_done=done, on_fail=fail)
