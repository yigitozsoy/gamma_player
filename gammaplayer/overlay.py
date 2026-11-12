"""YouTube tarzı oynatıcı kontrol katmanı.

VLC videoyu yerel (native) bir pencereye çizdiği için, üstüne normal Qt alt-widget'ları
koymak titreme/siyah kutu sorunlarına yol açar. Bu yüzden kontroller videonun üzerinde
duran ayrı, yarı saydam ve odak almayan bir üst-seviye pencerede çizilir.
"""

from PyQt6.QtCore import (Qt, pyqtSignal, QTimer, QRect, QRectF, QPoint, QPointF, QSize,
                          QVariantAnimation, QPropertyAnimation, pyqtProperty, QEasingCurve)
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QFont, QFontMetrics, QPainterPath, QCursor, QPen
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QStackedWidget,
                             QGraphicsOpacityEffect, QSizePolicy)

from . import icons
from .i18n import t
from .library import fmt_time
from .theme import accent
from .widgets import ToggleSwitch

WHITE = "#ffffff"


class OvButton(QPushButton):
    def __init__(self, name, tip="", parent=None, size=40, icon_size=24):
        super().__init__(parent)
        self.setObjectName("OvBtn")
        self.setFixedSize(size, size)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tip)
        self._isz = icon_size
        self.set_icon_name(name)

    def set_icon_name(self, name):
        self.setIcon(icons.icon(name, WHITE, self._isz))
        self.setIconSize(QSize(self._isz, self._isz))


class SeekBar(QWidget):
    seek = pyqtSignal(int, bool)        # ms, final
    scrub = pyqtSignal(bool)
    hover = pyqtSignal(int, int)        # x (overlay koordinatı), ms ; -1 ayrılınca

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(20)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.length = 0
        self.value = 0
        self._hover_x = -1
        self._drag = False
        self.ab = (None, None)

    def set_length(self, ms):
        self.length = max(0, int(ms))
        self.update()

    def set_value(self, ms):
        if not self._drag:
            self.value = max(0, int(ms))
            self.update()

    def _ms_at(self, x):
        if self.length <= 0:
            return 0
        return int(max(0.0, min(1.0, x / max(1, self.width()))) * self.length)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.length > 0:
            self._drag = True
            self.scrub.emit(True)
            self.value = self._ms_at(e.position().x())
            self.seek.emit(self.value, False)
            self.update()

    def mouseMoveEvent(self, e):
        x = e.position().x()
        self._hover_x = x
        gx = self.mapTo(self.window(), QPoint(int(x), 0)).x()
        self.hover.emit(gx, self._ms_at(x))
        if self._drag:
            self.value = self._ms_at(x)
            self.seek.emit(self.value, False)
        self.update()

    def mouseReleaseEvent(self, e):
        if self._drag and e.button() == Qt.MouseButton.LeftButton:
            self._drag = False
            self.value = self._ms_at(e.position().x())
            self.seek.emit(self.value, True)
            self.scrub.emit(False)
            self.update()

    def leaveEvent(self, e):
        self._hover_x = -1
        self.hover.emit(-1, -1)
        self.update()

    def is_dragging(self):
        return self._drag

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        active = self._hover_x >= 0 or self._drag
        th = 5.0 if active else 3.0
        cy = self.height() / 2.0
        top = cy - th / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 51))
        p.drawRect(QRectF(0, top, w, th))
        ratio = (self.value / self.length) if self.length > 0 else 0.0
        if self._hover_x >= 0 and not self._drag:
            p.setBrush(QColor(255, 255, 255, 90))
            p.drawRect(QRectF(0, top, self._hover_x, th))
        a, b = self.ab
        if a is not None and self.length > 0:
            xa = a / self.length * w
            xb = (b / self.length * w) if b is not None else xa + 2
            p.setBrush(QColor(62, 166, 255, 150))
            p.drawRect(QRectF(xa, top - 1, max(2, xb - xa), th + 2))
        p.setBrush(QColor(accent()))
        p.drawRect(QRectF(0, top, ratio * w, th))
        if active:
            r = 6.5
            p.drawEllipse(QPointF(max(r, min(w - r, ratio * w)), cy), r, r)


class VolumeSlider(QWidget):
    changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.value = 100
        self._drag = False

    def set_value(self, v):
        self.value = max(0, min(100, int(v)))
        self.update()

    def _from_x(self, x):
        pad = 6
        return int(round(max(0.0, min(1.0, (x - pad) / max(1, self.width() - 2 * pad))) * 100))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = True
            self.value = self._from_x(e.position().x())
            self.changed.emit(self.value)
            self.update()

    def mouseMoveEvent(self, e):
        if self._drag:
            self.value = self._from_x(e.position().x())
            self.changed.emit(self.value)
            self.update()

    def mouseReleaseEvent(self, e):
        self._drag = False

    def wheelEvent(self, e):
        step = 5 if e.angleDelta().y() > 0 else -5
        self.value = max(0, min(100, self.value + step))
        self.changed.emit(self.value)
        self.update()
        e.accept()

    def paintEvent(self, e):
        if self.width() < 8:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pad = 6
        w = self.width() - 2 * pad
        cy = self.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 80))
        p.drawRoundedRect(QRectF(pad, cy - 1.5, w, 3), 1.5, 1.5)
        x = pad + w * self.value / 100.0
        p.setBrush(QColor(WHITE))
        p.drawRoundedRect(QRectF(pad, cy - 1.5, x - pad, 3), 1.5, 1.5)
        p.drawEllipse(QPointF(x, cy), 6, 6)


class VolumeControl(QWidget):
    volume_changed = pyqtSignal(int)
    mute_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.btn = OvButton("volume", t("mute_tip"), self)
        self.btn.clicked.connect(self.mute_clicked.emit)
        lay.addWidget(self.btn)
        self.slider = VolumeSlider(self)
        self.slider.setFixedWidth(0)
        self.slider.changed.connect(self.volume_changed.emit)
        lay.addWidget(self.slider)
        self._w = 0
        self._anim = QPropertyAnimation(self, b"sw", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _get(self):
        return self._w

    def _set(self, v):
        self._w = int(v)
        self.slider.setFixedWidth(self._w)

    sw = pyqtProperty(int, _get, _set)

    def enterEvent(self, e):
        self._anim.stop()
        self._anim.setStartValue(self._w)
        self._anim.setEndValue(64)
        self._anim.start()

    def leaveEvent(self, e):
        if self.slider._drag:
            return
        self._anim.stop()
        self._anim.setStartValue(self._w)
        self._anim.setEndValue(0)
        self._anim.start()

    def set_state(self, volume, muted):
        self.slider.set_value(0 if muted else min(100, volume))
        if muted or volume == 0:
            self.btn.set_icon_name("volume_off")
        elif volume < 50:
            self.btn.set_icon_name("volume_low")
        else:
            self.btn.set_icon_name("volume")


class TimeLabel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("0:00 / 0:00", parent)
        self.setStyleSheet("color: #ffffff; font-size: 13px; padding: 0 8px; background: transparent;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        self.clicked.emit()


OVERLAY_QSS = """
QWidget#OvRoot, QWidget#OvControls, QWidget#OvTop { background: transparent; }
QPushButton#OvBtn { background: transparent; border: none; border-radius: 20px; }
QPushButton#OvBtn:hover { background: rgba(255,255,255,0.12); }
QPushButton#OvBtn:pressed { background: rgba(255,255,255,0.22); }
QPushButton#OvBtn:disabled { background: transparent; }
QLabel { color: #ffffff; background: transparent; }
QLabel#OvTitle { font-size: 17px; font-weight: 500; }
QLabel#OvCounter { font-size: 13px; padding: 0 6px; }
QToolTip { background: rgba(97,97,97,0.92); color: #fff; border: none; padding: 5px 8px; border-radius: 4px; }
"""


class PlayerOverlay(QWidget):
    """Video alanının üstünde yüzen kontrol penceresi."""
    # oynatma
    play_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    prev_clicked = pyqtSignal()
    seek_requested = pyqtSignal(int, bool)
    scrubbing = pyqtSignal(bool)
    volume_changed = pyqtSignal(int)
    mute_clicked = pyqtSignal()
    # sağ grup
    cc_clicked = pyqtSignal()
    snapshot_clicked = pyqtSignal()
    loop_clicked = pyqtSignal()
    stretch_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    pip_clicked = pyqtSignal()
    theater_clicked = pyqtSignal()
    fullscreen_clicked = pyqtSignal()
    autoplay_toggled = pyqtSignal(bool)
    # resim modu
    slideshow_clicked = pyqtSignal()
    zoom_in_clicked = pyqtSignal()
    zoom_out_clicked = pyqtSignal()
    fit_clicked = pyqtSignal()
    rotate_clicked = pyqtSignal()
    edit_clicked = pyqtSignal()
    # fare
    video_clicked = pyqtSignal()
    video_double_clicked = pyqtSignal(float)   # tıklanan x oranı (0..1)
    hold_changed = pyqtSignal(bool, float)     # basılı tutma başladı/bitti, x oranı
    wheel = pyqtSignal(int, object)          # delta, modifiers
    context_requested = pyqtSignal(QPoint)
    seek_hover = pyqtSignal(int)             # ms; -1 = ayrıldı
    files_dropped = pyqtSignal(list)
    activity = pyqtSignal()

    MODE_NONE, MODE_VIDEO, MODE_AUDIO, MODE_IMAGE = "none", "video", "audio", "image"

    def __init__(self, owner):
        super().__init__(owner, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.NoDropShadowWindowHint)
        self.owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("OvRoot")
        self.setStyleSheet(OVERLAY_QSS)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.mode = self.MODE_NONE
        self.pip = False
        self.fullscreen = False
        self.playing = False
        self.title = ""
        self._ctrl_opacity = 1.0
        self._controls_visible = True
        self._hover_ms = -1
        self._hover_x = -1
        self._preview = None
        self._remaining = False
        self._osd_text = ""
        self._osd_alpha = 0.0
        self._flash_icon = None
        self._flash_t = 1.0
        self._bubble = None       # ("left"/"right", text)
        self._bubble_t = 1.0
        self._press_pos = None
        self._press_global = None
        self._moved = False
        self._loading = False

        self._build()

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(self._autohide_ms if getattr(self, "_autohide_ms", 0) > 0 else 2600)
        self.hide_timer.timeout.connect(self._auto_hide)

        self.hold_timer = QTimer(self)
        self.hold_timer.setSingleShot(True)
        self.hold_timer.setInterval(380)
        self.hold_timer.timeout.connect(self._hold_start)
        self._holding = False
        self._badge = ""

        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.setInterval(230)
        self.click_timer.timeout.connect(self.video_clicked.emit)

        self._fade = QVariantAnimation(self)
        self._fade.setDuration(220)
        self._fade.valueChanged.connect(self._on_fade)

        self._osd_anim = QVariantAnimation(self)
        self._osd_anim.setDuration(1400)
        self._osd_anim.setKeyValueAt(0.0, 1.0)
        self._osd_anim.setKeyValueAt(0.75, 1.0)
        self._osd_anim.setKeyValueAt(1.0, 0.0)
        self._osd_anim.valueChanged.connect(self._on_osd_anim)

        self._flash_anim = QVariantAnimation(self)
        self._flash_anim.setDuration(500)
        self._flash_anim.setStartValue(0.0)
        self._flash_anim.setEndValue(1.0)
        self._flash_anim.valueChanged.connect(self._on_flash)

        self._bubble_anim = QVariantAnimation(self)
        self._bubble_anim.setDuration(750)
        self._bubble_anim.setStartValue(0.0)
        self._bubble_anim.setEndValue(1.0)
        self._bubble_anim.valueChanged.connect(self._on_bubble)

    # ------------------------------------------------------------------ yapı
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Üst şerit (tam ekran / mini oynatıcı)
        self.top = QWidget(self)
        self.top.setObjectName("OvTop")
        tl = QHBoxLayout(self.top)
        tl.setContentsMargins(16, 10, 10, 0)
        tl.setSpacing(4)
        self.btn_pip_restore = OvButton("pip_exit", t("pip_exit"), self.top)
        self.btn_pip_restore.clicked.connect(self.pip_clicked.emit)
        tl.addWidget(self.btn_pip_restore)
        self.lbl_title = QLabel("", self.top)
        self.lbl_title.setObjectName("OvTitle")
        self.lbl_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        tl.addWidget(self.lbl_title, 1)
        self.btn_pip_close = OvButton("close", t("close"), self.top)
        self.btn_pip_close.clicked.connect(self.pip_clicked.emit)
        tl.addWidget(self.btn_pip_close)
        root.addWidget(self.top)
        root.addStretch(1)

        # Alt kontroller
        self.controls = QWidget(self)
        self.controls.setObjectName("OvControls")
        cl = QVBoxLayout(self.controls)
        cl.setContentsMargins(12, 0, 12, 2)
        cl.setSpacing(0)
        self.seekbar = SeekBar(self.controls)
        self.seekbar.seek.connect(self.seek_requested.emit)
        self.seekbar.scrub.connect(self.scrubbing.emit)
        self.seekbar.hover.connect(self._on_seek_hover)
        cl.addWidget(self.seekbar)

        self.rows = QStackedWidget(self.controls)
        self.rows.setFixedHeight(44)
        cl.addWidget(self.rows)

        # --- video/ses satırı
        vrow = QWidget()
        vl = QHBoxLayout(vrow)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)
        self.btn_prev = OvButton("prev", t("prev_tip"))
        self.btn_play = OvButton("play", t("play_tip"), size=44, icon_size=30)
        self.btn_next = OvButton("next", t("next_tip"))
        self.btn_loop = OvButton("loop", t("loop_tip_off"), size=40, icon_size=22)
        self.btn_loop.clicked.connect(self.loop_clicked.emit)
        self.btn_prev.clicked.connect(self.prev_clicked.emit)
        self.btn_play.clicked.connect(self.play_clicked.emit)
        self.btn_next.clicked.connect(self.next_clicked.emit)
        self.volume = VolumeControl()
        self.volume.volume_changed.connect(self.volume_changed.emit)
        self.volume.mute_clicked.connect(self.mute_clicked.emit)
        self.lbl_time = TimeLabel()
        self.lbl_time.clicked.connect(self._toggle_remaining)
        self._vrow_layout = vl
        self.sw_autoplay = ToggleSwitch(True, on_dark=True)
        self.sw_autoplay.setToolTip(t("autoplay"))
        self.sw_autoplay.toggled.connect(self.autoplay_toggled.emit)
        self.btn_snap = OvButton("camera", t("snapshot_tip"))
        self.btn_snap.clicked.connect(self.snapshot_clicked.emit)
        self.btn_stretch = OvButton("aspect", t("stretch_tip"))
        self.btn_stretch.clicked.connect(self.stretch_clicked.emit)
        self.btn_cc = OvButton("cc_off", t("subtitles_tip"))
        self.btn_settings = OvButton("settings", t("settings"))
        self.btn_pip = OvButton("pip", t("pip_tip"))
        self.btn_theater = OvButton("theater", t("theater_tip"))
        self.btn_fullscreen = OvButton("fullscreen", t("fullscreen_tip"))
        self.btn_cc.clicked.connect(self.cc_clicked.emit)
        self.btn_settings.clicked.connect(self.settings_clicked.emit)
        self.btn_pip.clicked.connect(self.pip_clicked.emit)
        self.btn_theater.clicked.connect(self.theater_clicked.emit)
        self.btn_fullscreen.clicked.connect(self.fullscreen_clicked.emit)
        self._ov_widgets = {
            "prev": self.btn_prev, "play": self.btn_play, "next": self.btn_next, "loop": self.btn_loop,
            "volume": self.volume, "time": self.lbl_time, "autoplay": self.sw_autoplay,
            "snapshot": self.btn_snap, "stretch": self.btn_stretch, "cc": self.btn_cc,
            "settings": self.btn_settings, "pip": self.btn_pip, "theater": self.btn_theater,
            "fullscreen": self.btn_fullscreen,
        }
        self.rows.addWidget(vrow)
        self.apply_personalization()

        # --- resim satırı
        irow = QWidget()
        il = QHBoxLayout(irow)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(0)
        self.btn_iprev = OvButton("prev", t("prev_image"))
        self.btn_slideshow = OvButton("play", t("slideshow"), size=44, icon_size=30)
        self.btn_inext = OvButton("next", t("next_image"))
        self.btn_iprev.clicked.connect(self.prev_clicked.emit)
        self.btn_slideshow.clicked.connect(self.slideshow_clicked.emit)
        self.btn_inext.clicked.connect(self.next_clicked.emit)
        self.lbl_counter = QLabel("")
        self.lbl_counter.setObjectName("OvCounter")
        for w in (self.btn_iprev, self.btn_slideshow, self.btn_inext, self.lbl_counter):
            il.addWidget(w)
        il.addStretch(1)
        self.btn_zoom_out = OvButton("zoom_out", t("zoom_out"))
        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setFixedWidth(52)
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_zoom_in = OvButton("zoom_in", t("zoom_in"))
        self.btn_fit = OvButton("fit", t("fit"))
        self.btn_rotate = OvButton("rotate_right", t("rotate"))
        self.btn_edit = OvButton("edit", t("edit"))
        self.btn_ifull = OvButton("fullscreen", t("fullscreen_tip"))
        self.btn_zoom_out.clicked.connect(self.zoom_out_clicked.emit)
        self.btn_zoom_in.clicked.connect(self.zoom_in_clicked.emit)
        self.btn_fit.clicked.connect(self.fit_clicked.emit)
        self.btn_rotate.clicked.connect(self.rotate_clicked.emit)
        self.btn_edit.clicked.connect(self.edit_clicked.emit)
        self.btn_ifull.clicked.connect(self.fullscreen_clicked.emit)
        self.btn_edit.hide()  # düzenleme alttaki satırda
        for w in (self.btn_zoom_out, self.lbl_zoom, self.btn_zoom_in, self.btn_fit, self.btn_rotate,
                  self.btn_ifull):
            il.addWidget(w)
        self.rows.addWidget(irow)

        root.addWidget(self.controls)
        self._opacity_fx = QGraphicsOpacityEffect(self.controls)
        self._opacity_fx.setOpacity(1.0)
        self.controls.setGraphicsEffect(self._opacity_fx)
        self._top_fx = QGraphicsOpacityEffect(self.top)
        self.top.setGraphicsEffect(self._top_fx)
        self._update_layout_mode()

    # ------------------------------------------------------------------ durum
    def set_mode(self, mode):
        self.mode = mode
        self._update_layout_mode()
        self.show_controls()

    def set_pip(self, on):
        self.pip = on
        self._hover_ms = -1
        self._preview = None
        self._update_layout_mode()

    def set_fullscreen(self, on):
        self.fullscreen = on
        self.btn_fullscreen.set_icon_name("fullscreen_exit" if on else "fullscreen")
        self.btn_ifull.set_icon_name("fullscreen_exit" if on else "fullscreen")
        self.btn_fullscreen.setToolTip(t("exit_fullscreen_tip") if on else t("fullscreen_tip"))
        self._update_layout_mode()

    def set_theater(self, on):
        self.btn_theater.set_icon_name("theater_off" if on else "theater")
        self.btn_theater.setToolTip(t("default_view_tip") if on else t("theater_tip"))

    def apply_personalization(self):
        """Kişiselleştirme tercihlerini (düğme sırası/görünürlük, süreler) uygular."""
        from . import layout_prefs as lp
        vl = self._vrow_layout
        while vl.count():
            vl.takeAt(0)
        left_done = False
        for key, vis in lp.layout("player"):
            if key == lp.SEP:
                vl.addStretch(1)
                left_done = True
                continue
            w = self._ov_widgets.get(key)
            if w is None:
                continue
            vl.addWidget(w)
            if key == "autoplay":
                vl.addSpacing(6)
        if not left_done:
            vl.addStretch(1)
        self._uvis = {k: bool(v) for k, v in lp.layout("player")}
        ms = int(lp.get("autohide_ms") or 0)
        self._autohide_ms = ms
        if hasattr(self, "hide_timer"):
            self.hide_timer.setInterval(ms if ms > 0 else 2600)
        self._remaining = lp.get("time_display") == "remaining"
        self._update_layout_mode()

    def _update_layout_mode(self):
        image = self.mode == self.MODE_IMAGE
        self.rows.setCurrentIndex(1 if image else 0)
        self.seekbar.setVisible(not image)
        audio = self.mode == self.MODE_AUDIO
        u = getattr(self, "_uvis", {})

        def show(key, cond=True):
            self._ov_widgets[key].setVisible(bool(cond) and u.get(key, True))
        show("cc", not audio and not self.pip)
        show("snapshot", not audio and not self.pip)
        show("stretch", not audio and not self.pip)
        show("autoplay", not self.pip)
        show("theater", not self.pip and not self.fullscreen)
        show("fullscreen", not self.pip)
        show("prev", not self.pip)
        show("loop", not self.pip)
        show("next")
        show("volume")
        show("time")
        show("settings")
        show("pip", not self.fullscreen and getattr(self, "_pip_allowed", True))
        self.btn_play.setVisible(True)
        self.btn_pip.set_icon_name("pip_exit" if self.pip else "pip")
        self.btn_pip.setToolTip(t("pip_exit") if self.pip else t("pip_tip"))
        from . import layout_prefs as lp
        show_top = (self.fullscreen and lp.get("show_title_fullscreen")) or self.pip
        self.top.setVisible(bool(show_top) and not image)
        self.btn_pip_restore.setVisible(self.pip)
        self.btn_pip_close.setVisible(False)
        self.lbl_title.setStyleSheet("font-size: %dpx;" % (13 if self.pip else 18))
        self.update()

    def set_pip_allowed(self, allowed):
        self._pip_allowed = allowed
        self._update_layout_mode()

    def set_title(self, text):
        self.title = text
        self.lbl_title.setText(text)

    def set_playing(self, playing):
        self.playing = playing
        self.btn_play.set_icon_name("pause" if playing else "play")
        self.btn_play.setToolTip(t("pause_tip") if playing else t("play_tip"))
        if not playing:
            self.show_controls(keep=True)
        else:
            self.show_controls()

    def set_ended(self):
        self.playing = False
        self.btn_play.set_icon_name("replay")
        self.btn_play.setToolTip(t("replay"))
        self.show_controls(keep=True)

    def set_slideshow(self, running):
        model = getattr(self, "_model_mode", False)
        self.btn_slideshow.set_icon_name("pause" if running else ("rotate_360" if model else "slideshow"))
        if model:
            self.btn_slideshow.setToolTip(t("stop_autorotate") if running else t("autorotate"))
        else:
            self.btn_slideshow.setToolTip(t("stop_slideshow") if running else t("slideshow"))

    def set_model_mode(self, on):
        """Resim satırı 3D model için de kullanılır; yalnızca simge ve ipuçları değişir."""
        on = bool(on)
        prev = getattr(self, "_model_mode", None)
        if prev == on:
            return
        self._model_mode = on
        if on:
            self.set_slideshow(False)
        elif prev:
            # resim satırının ilk görünümüne dön
            self.btn_slideshow.set_icon_name("play")
            self.btn_slideshow.setToolTip(t("slideshow"))
        self.btn_iprev.setToolTip(t("prev_model") if on else t("prev_image"))
        self.btn_inext.setToolTip(t("next_model") if on else t("next_image"))
        self.btn_fit.setToolTip(t("reset_view") if on else t("fit"))
        self.btn_rotate.setToolTip(t("flip_model") if on else t("rotate"))

    def set_time(self, cur, length):
        self.seekbar.set_length(length)
        self.seekbar.set_value(cur)
        if not self._controls_visible and length > 0:
            px = int(self.width() * cur / length)
            if px != getattr(self, "_mini_px", -1):
                self._mini_px = px
                from . import layout_prefs as lp
                if lp.get("mini_progress"):
                    self.update(0, self.height() - 3, self.width(), 3)
        if self._remaining and length > 0:
            txt = f"-{fmt_time(length - cur)} / {fmt_time(length)}"
        else:
            txt = f"{fmt_time(cur)} / {fmt_time(length)}" if length > 0 else fmt_time(cur)
        if self.lbl_time.text() != txt:
            self.lbl_time.setText(txt)

    def _toggle_remaining(self):
        self._remaining = not self._remaining
        self.set_time(self.seekbar.value, self.seekbar.length)

    def set_volume(self, v, muted):
        self.volume.set_state(v, muted)

    def set_cc(self, on, available=True):
        self.btn_cc.set_icon_name("cc" if on else "cc_off")
        self.btn_cc.setEnabled(True)

    def set_loop(self, mode):
        """mode: off | all | one"""
        self.btn_loop.set_icon_name("loop_one" if mode == "one" else "loop")
        self.btn_loop.setStyleSheet("" if mode == "off" else
                                    "QPushButton#OvBtn { background: rgba(255,255,255,0.22); }")
        self.btn_loop.setToolTip(t("loop_tip_" + mode))

    def set_stretched(self, on):
        self.btn_stretch.setStyleSheet("QPushButton#OvBtn { background: rgba(255,255,255,0.22); }" if on else "")
        self.btn_stretch.setToolTip(t("stretch_off_tip") if on else t("stretch_tip"))

    def set_autoplay(self, on):
        self.sw_autoplay.setChecked(on, emit=False)

    def set_counter(self, text):
        self.lbl_counter.setText(text)

    def set_zoom(self, pct):
        self.lbl_zoom.setText(f"{int(pct)}%")

    def set_preview_image(self, img):
        self._preview = img
        if self._hover_ms >= 0:
            self.update()

    # ------------------------------------------------------------------ göster/gizle
    def controls_visible(self):
        return self._controls_visible

    def show_controls(self, keep=False):
        self.activity.emit()
        if not self._controls_visible:
            self._controls_visible = True
            self._fade.stop()
            self._fade.setStartValue(self._ctrl_opacity)
            self._fade.setEndValue(1.0)
            self._fade.start()
            self.controls.show()
        self.unsetCursor()
        self.hide_timer.stop()
        if not keep and self._should_autohide():
            self.hide_timer.start()

    def _should_autohide(self):
        if getattr(self, "_autohide_ms", 2600) <= 0:
            return False
        if self.mode == self.MODE_IMAGE:
            return True
        return self.playing and not self.seekbar.is_dragging()

    def _auto_hide(self):
        if not self._should_autohide():
            return
        # Fare kontrollerin üzerindeyse gizleme
        if self.mode != self.MODE_IMAGE:
            local = self.mapFromGlobal(QCursor.pos())
            if self.rect().contains(local) and self.controls.geometry().contains(local):
                self.hide_timer.start()
                return
        self.hide_controls()

    def hide_controls(self):
        if not self._controls_visible:
            return
        self._controls_visible = False
        self._fade.stop()
        self._fade.setStartValue(self._ctrl_opacity)
        self._fade.setEndValue(0.0)
        self._fade.start()
        self._hover_ms = -1
        if self.fullscreen and self.mode != self.MODE_IMAGE:
            self.setCursor(Qt.CursorShape.BlankCursor)

    def _on_fade(self, v):
        self._ctrl_opacity = float(v)
        self._opacity_fx.setOpacity(self._ctrl_opacity)
        self._top_fx.setOpacity(self._ctrl_opacity)
        if self._ctrl_opacity <= 0.01 and not self._controls_visible:
            self.controls.hide()
            if self.mode == self.MODE_IMAGE:
                self.hide()
        self.update()

    # ------------------------------------------------------------------ OSD / animasyonlar
    def osd(self, text):
        self._osd_text = text
        self._osd_anim.stop()
        self._osd_anim.start()

    def _on_osd_anim(self, v):
        self._osd_alpha = float(v)
        self.update()

    def flash(self, icon_name):
        from . import layout_prefs as lp
        if not lp.get("flash_anim"):
            return
        self._flash_icon = icon_name
        self._flash_anim.stop()
        self._flash_anim.start()

    def _on_flash(self, v):
        self._flash_t = float(v)
        self.update()

    def bubble(self, side, text):
        self._bubble = (side, text)
        self._bubble_anim.stop()
        self._bubble_anim.start()

    def _on_bubble(self, v):
        self._bubble_t = float(v)
        self.update()

    def _on_seek_hover(self, x, ms):
        self._hover_x = x
        self._hover_ms = ms
        self.seek_hover.emit(ms)
        self.update()

    # ------------------------------------------------------------------ çizim
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        full_area = self.mode in (self.MODE_VIDEO, self.MODE_AUDIO)
        # Fare olaylarını yakalamak için neredeyse görünmez taban
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))
        a = self._ctrl_opacity
        if a > 0.01 and self.controls.isVisible():
            gh = min(h, 170 if not self.pip else 110)
            g = QLinearGradient(0, h - gh, 0, h)
            g.setColorAt(0.0, QColor(0, 0, 0, 0))
            g.setColorAt(0.55, QColor(0, 0, 0, int(95 * a)))
            g.setColorAt(1.0, QColor(0, 0, 0, int(175 * a)))
            p.fillRect(QRect(0, h - gh, w, gh), g)
            if self.top.isVisible():
                th = 110 if not self.pip else 70
                g2 = QLinearGradient(0, 0, 0, th)
                g2.setColorAt(0.0, QColor(0, 0, 0, int(150 * a)))
                g2.setColorAt(1.0, QColor(0, 0, 0, 0))
                p.fillRect(QRect(0, 0, w, th), g2)
            if self.pip and full_area:
                p.fillRect(self.rect(), QColor(0, 0, 0, int(70 * a)))

        if full_area and not self._controls_visible and self._ctrl_opacity < 0.05 and self.seekbar.length > 0:
            from . import layout_prefs as lp
            if lp.get("mini_progress"):
                from .theme import accent as _acc
                ratio = self.seekbar.value / max(1, self.seekbar.length)
                p.fillRect(QRect(0, h - 3, w, 3), QColor(255, 255, 255, 50))
                p.fillRect(QRect(0, h - 3, int(w * ratio), 3), QColor(_acc()))
        if full_area:
            self._paint_center(p, w, h)
            self._paint_bubble(p, w, h)
        self._paint_osd(p, w, h)
        self._paint_badge(p, w, h)
        if self._hover_ms >= 0 and self.mode != self.MODE_IMAGE and self._controls_visible:
            self._paint_preview(p, w, h)

    def _paint_center(self, p, w, h):
        if self._loading:
            pass
        if self._flash_icon and self._flash_t < 1.0:
            # YouTube "bezel": 52 px yarı saydam daire + 36 px simge; 0,5 sn'de 2 katına büyüyüp söner
            t_ = self._flash_t
            scale = 1.0 + t_
            alpha = 1.0 - t_
            c = QPointF(w / 2, h / 2)
            r = 26 * scale
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, int(128 * alpha)))
            p.drawEllipse(c, r, r)
            isz = 36 * scale
            pm = icons.pixmap(self._flash_icon, WHITE, 72)
            p.setOpacity(alpha)
            p.drawPixmap(QRectF(c.x() - isz / 2, c.y() - isz / 2, isz, isz), pm, QRectF(pm.rect()))
            p.setOpacity(1.0)

    def _paint_bubble(self, p, w, h):
        if not self._bubble or self._bubble_t >= 1.0:
            return
        side, text = self._bubble
        alpha = 1.0 - max(0.0, (self._bubble_t - 0.5) * 2)
        cx = w * (0.18 if side == "left" else 0.82)
        cy = h / 2
        r = min(70, h * 0.18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, int(110 * alpha)))
        p.drawEllipse(QPointF(cx, cy), r, r)
        # Üç ok
        pm = icons.pixmap("play", WHITE, 18)
        p.setOpacity(alpha)
        for i in range(3):
            phase = (self._bubble_t * 3 - i * 0.35) % 1.0
            p.setOpacity(alpha * (0.35 + 0.65 * (1 - abs(phase - 0.5) * 2)))
            x = cx - 27 + i * 18 if side == "right" else cx + 9 - i * 18
            if side == "left":
                p.save()
                p.translate(x + 9, cy - 16 + 9)
                p.scale(-1, 1)
                p.drawPixmap(-9, -9, pm)
                p.restore()
            else:
                p.drawPixmap(int(x), int(cy - 16), pm)
        p.setOpacity(alpha)
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(WHITE))
        p.drawText(QRectF(cx - r, cy + 8, 2 * r, 22), Qt.AlignmentFlag.AlignCenter, text)
        p.setOpacity(1.0)

    def _paint_badge(self, p, w, h):
        if not self._badge:
            return
        f = QFont(self.font())
        f.setPixelSize(14)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        fm = QFontMetrics(f)
        tw = fm.horizontalAdvance(self._badge) + 30
        r = QRectF((w - tw) / 2, 18, tw, 32)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawRoundedRect(r, 16, 16)
        p.setPen(QColor(WHITE))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self._badge)

    def _paint_osd(self, p, w, h):
        if self._osd_alpha <= 0.01 or not self._osd_text:
            return
        f = QFont(self.font())
        f.setPixelSize(15 if not self.pip else 12)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        fm = QFontMetrics(f)
        tw = fm.horizontalAdvance(self._osd_text) + 28
        th = fm.height() + 14
        y = 56 if (self.top.isVisible() and self._controls_visible) else 22
        if self.mode == self.MODE_IMAGE:
            y = 10
        r = QRectF((w - tw) / 2, y, tw, th)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, int(165 * self._osd_alpha)))
        p.drawRoundedRect(r, th / 2, th / 2)
        p.setPen(QColor(255, 255, 255, int(255 * self._osd_alpha)))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self._osd_text)

    def _paint_preview(self, p, w, h):
        img = self._preview
        # Önizleme bir kutuya sığdırılır: yatay videolarda en fazla 176 px genişlik,
        # dikey videolarda en fazla ~120 px yükseklik (oynatıcı yüksekliğinin de en fazla %30'u)
        box_w, box_h = (176, 120) if not self.pip else (110, 62)
        box_h = max(50, min(box_h, int(h * 0.30)))
        pw, ph = box_w, int(box_w * 9 / 16)
        if img is not None and not img.isNull() and img.width() > 0 and img.height() > 0:
            s = min(box_w / img.width(), box_h / img.height())
            pw, ph = max(30, int(img.width() * s)), max(30, int(img.height() * s))
        bar_y = self.controls.geometry().top() + self.seekbar.geometry().top()
        x = max(8, min(w - pw - 8, self._hover_x - pw / 2))
        txt = fmt_time(self._hover_ms)
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        if self.mode == self.MODE_AUDIO or img is None or img.isNull():
            fm = QFontMetrics(f)
            tw = fm.horizontalAdvance(txt) + 16
            tx = max(8, min(w - tw - 8, self._hover_x - tw / 2))
            r = QRectF(tx, bar_y - 30, tw, 24)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(28, 28, 28, 230))
            p.drawRoundedRect(r, 4, 4)
            p.setPen(QColor(WHITE))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, txt)
            return
        y = bar_y - ph - 30
        rect = QRectF(x, y, pw, ph)
        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)
        p.save()
        p.setClipPath(path)
        p.drawImage(rect, img)
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 230), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 8, 8)
        p.setPen(QColor(WHITE))
        tr = QRectF(x, y + ph + 4, pw, 20)
        sh = QColor(0, 0, 0, 200)
        p.setPen(sh)
        p.drawText(tr.translated(1, 1), Qt.AlignmentFlag.AlignCenter, txt)
        p.setPen(QColor(WHITE))
        p.drawText(tr, Qt.AlignmentFlag.AlignCenter, txt)

    # ------------------------------------------------------------------ fare
    def mouseMoveEvent(self, e):
        self.show_controls()
        if self._press_pos is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            if (e.globalPosition().toPoint() - self._press_global).manhattanLength() > 6 and not self._moved:
                self._moved = True
                self.click_timer.stop()
                self.hold_timer.stop()
                if self.pip or not (self.owner.isMaximized() or self.owner.isFullScreen()):
                    if self.pip:
                        h = self.owner.windowHandle()
                        if h:
                            h.startSystemMove()

    def mousePressEvent(self, e):
        self.show_controls()
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = e.position().toPoint()
            self._press_global = e.globalPosition().toPoint()
            self._moved = False
            if self.mode in (self.MODE_VIDEO, self.MODE_AUDIO) and not self.controls.geometry().contains(self._press_pos):
                self.hold_timer.start()
        elif e.button() == Qt.MouseButton.RightButton:
            self.context_requested.emit(e.globalPosition().toPoint())
        elif e.button() == Qt.MouseButton.MiddleButton:
            self.fullscreen_clicked.emit()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._press_pos is not None:
            self.hold_timer.stop()
            if self._holding:
                self._holding = False
                self.hold_changed.emit(False, e.position().x() / max(1, self.width()))
            elif not self._moved and self.mode in (self.MODE_VIDEO, self.MODE_AUDIO):
                self.click_timer.start()
            self._press_pos = None

    def _hold_start(self):
        if self._press_pos is None or self._moved:
            return
        self._holding = True
        self.click_timer.stop()
        self.hold_changed.emit(True, self._press_pos.x() / max(1, self.width()))

    def set_badge(self, text):
        """Üstte kalıcı küçük hap (ör. basılı tutarken "2x ▶▶")."""
        self._badge = text or ""
        self.update()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.click_timer.stop()
            self.hold_timer.stop()
            self.video_double_clicked.emit(e.position().x() / max(1, self.width()))

    def wheelEvent(self, e):
        self.show_controls()
        self.wheel.emit(e.angleDelta().y(), e.modifiers())
        e.accept()

    def leaveEvent(self, e):
        if self.playing and self.mode != self.MODE_IMAGE:
            self.hide_timer.start(900)
        self._hover_ms = -1
        self.update()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
