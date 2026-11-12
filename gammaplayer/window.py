"""Ana pencere: YouTube izleme sayfası düzeni + VLC oynatıcı + resim görüntüleyici."""
import ctypes
import os
import time
from ctypes import wintypes

from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, QEvent, QFileSystemWatcher, QObject
from PyQt6.QtGui import QGuiApplication, QCursor, QImage, QColor
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QFileDialog, QMessageBox, QMenu, QApplication, QLabel, QInputDialog)

from . import thumbs
from . import layout_prefs as lp
from .config import prefs, positions, sync_store
from .formats import SUBTITLE_EXT, ext_of, dialog_filter, is_media
from .i18n import t
from .image_viewer import ImageViewer
from .library import Library, fmt_time
from .overlay import PlayerOverlay
from .popup_menu import MenuPopup
from .sidebar import Sidebar
from .theme import theme, current_name
from .titlebar import TitleBar
from .views import HomeView, AudioView, InfoBar
from .vlc_engine import VLCEngine, VLC_ERROR

user32 = ctypes.windll.user32
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, wintypes.UINT]
HWND_TOPMOST, HWND_NOTOPMOST = wintypes.HWND(-1), wintypes.HWND(-2)
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, wintypes.UINT]
user32.GetWindowLongW.restype = ctypes.c_long
user32.MonitorFromWindow.restype = wintypes.HANDLE
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
GWL_STYLE = -16
WS_THICKFRAME, WS_CAPTION, WS_MAXIMIZEBOX, WS_MINIMIZEBOX, WS_SYSMENU = 0x40000, 0xC00000, 0x10000, 0x20000, 0x80000
WM_NCCALCSIZE, WM_NCHITTEST = 0x0083, 0x0084


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]
SWP_FLAGS = 0x0002 | 0x0001 | 0x0010  # NOMOVE | NOSIZE | NOACTIVATE

PAGE_HOME, PAGE_VIDEO, PAGE_AUDIO, PAGE_IMAGE, PAGE_MODEL = 0, 1, 2, 3, 4
SPEEDS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 3.0]
ASPECTS = [None, "16:9", "4:3", "1:1", "16:10", "21:9", "2.35:1", "9:16"]


class Toast(QLabel):
    """Resim/ana sayfa modunda kısa bildirimler."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setStyleSheet("background: rgba(0,0,0,0.78); color: white; border-radius: 16px;"
                           "padding: 7px 16px; font-size: 13px; font-weight: 600;")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_text(self, text, ms=1800):
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, 16)
        self.show()
        self.raise_()
        self._timer.start(ms)


class EdgeResizer(QObject):
    """Çerçevesiz pencerede kenarlardan yeniden boyutlandırma (Windows'un kendi boyutlandırmasıyla)."""
    M = 6

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self._override = False

    def _edges(self, gp):
        w = self.win
        if w.isMaximized() or w.isFullScreen() or not w.isVisible():
            return None
        g = w.frameGeometry()
        if not g.adjusted(-2, -2, 2, 2).contains(gp):
            return None
        e = Qt.Edge(0)
        if gp.x() <= g.left() + self.M:
            e |= Qt.Edge.LeftEdge
        if gp.x() >= g.right() - self.M:
            e |= Qt.Edge.RightEdge
        if gp.y() <= g.top() + self.M:
            e |= Qt.Edge.TopEdge
        if gp.y() >= g.bottom() - self.M:
            e |= Qt.Edge.BottomEdge
        return e if e != Qt.Edge(0) else None

    @staticmethod
    def _cursor(e):
        L, R, T, B = Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge
        if (e & L and e & T) or (e & R and e & B):
            return Qt.CursorShape.SizeFDiagCursor
        if (e & R and e & T) or (e & L and e & B):
            return Qt.CursorShape.SizeBDiagCursor
        if e & (L | R):
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor

    def eventFilter(self, obj, ev):
        et = ev.type()
        if et not in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.HoverMove):
            return False
        if not isinstance(obj, QWidget):
            return False
        top = obj.window()
        if top is not self.win and top is not getattr(self.win, "overlay", None):
            return False
        gp = QCursor.pos()
        e = self._edges(gp)
        if et == QEvent.Type.MouseButtonPress and e is not None and ev.button() == Qt.MouseButton.LeftButton:
            h = self.win.windowHandle()
            if h:
                self._restore()
                h.startSystemResize(e)
                return True
        if e is not None:
            if not self._override:
                QApplication.setOverrideCursor(self._cursor(e))
                self._override = True
            else:
                QApplication.changeOverrideCursor(self._cursor(e))
        else:
            self._restore()
        return False

    def _restore(self):
        if self._override:
            QApplication.restoreOverrideCursor()
            self._override = False


class MainWindow(QMainWindow):
    def __init__(self, paths=None):
        # VLC'nin yerel video penceresi yüzünden kardeş widget'lar da yerel pencereye dönüşmesin;
        # aksi halde başlık çubuğu ayrı HWND olur ve sürükleme/Snap ana pencereye ulaşmaz.
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window |
                            Qt.WindowType.WindowMinMaxButtonsHint)
        self.setWindowTitle("gamma")
        self.setAcceptDrops(True)
        self.setMinimumSize(760, 480)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.lib = Library()
        self.lib.filter = prefs.get("filter", "all")
        self.lib.sort = "explorer"
        self.current = None
        self._pinned = False
        self._pip = False
        self._pip_state = None
        self._fs_state = None
        self._theater = bool(prefs.get("theater", False))
        self._sidebar_visible = False
        self._scrubbing = False
        self._last_seek = 0.0
        self._pending_seek = None
        self._vt = (0, 0.0)            # (son vlc zamanı, perf zamanı)
        self._image_cache = {}
        self._image_order = []
        self._slideshow = False
        self._rotation = 0
        self._video_zoom = "fit"
        self._aspect = None
        self._crop = None
        self._deinterlace = False
        self._adjust = dict(brightness=1.0, contrast=1.0, saturation=1.0, hue=0.0, gamma=1.0)
        self._sleep_end_of_media = False
        self._ab = [None, None]
        self._hover_bucket = None
        self._edit_panel = None
        self._ended = False

        self.thumbs = thumbs.ThumbnailService(self)
        self.thumbs.ready.connect(self._on_thumb)
        self.grabber = thumbs.FrameGrabber(self)
        self.grabber.frame.connect(self._on_preview_frame)
        self.grabber.start()

        self._build_ui()
        self.overlay = PlayerOverlay(self)
        self._connect_overlay()
        self.menu = MenuPopup(self.overlay, 310)

        # VLC motoru pencere ekrana geldikten hemen sonra (veya ilk video/müzikte) başlatılır;
        # böylece açılış ve görsel görüntüleme beklemez.
        self.engine = None
        self._engine_tried = False
        self._vlc_error = None
        QTimer.singleShot(0, self._ensure_engine)

        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(30)
        self.ui_timer.timeout.connect(self._tick)
        self.ui_timer.start()
        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(400)
        self.sync_timer.timeout.connect(self.sync_overlay)
        self.sync_timer.start()
        self.save_timer = QTimer(self)
        self.save_timer.setInterval(5000)
        self.save_timer.timeout.connect(self._save_position)
        self.save_timer.start()
        self.slide_timer = QTimer(self)
        self.slide_timer.setSingleShot(True)
        self.slide_timer.timeout.connect(self._slide_next)
        self.sleep_timer = QTimer(self)
        self.sleep_timer.setSingleShot(True)
        self.sleep_timer.timeout.connect(self._sleep_fire)
        self.sub_rebuild_timer = QTimer(self)
        self.sub_rebuild_timer.setSingleShot(True)
        self.sub_rebuild_timer.setInterval(450)
        self.sub_rebuild_timer.timeout.connect(self._rebuild_engine)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(lambda _: self.folder_timer.start())
        self.folder_timer = QTimer(self)
        self.folder_timer.setSingleShot(True)
        self.folder_timer.setInterval(700)
        self.folder_timer.timeout.connect(self._folder_changed)

        self._apply_sidebar_side()
        self.resizer = EdgeResizer(self)
        QApplication.instance().installEventFilter(self.resizer)

        self._restore_geometry()
        self._apply_layout()
        self.overlay.set_autoplay(bool(prefs.get("autoplay", True)))
        self.overlay.set_loop(prefs.get("loop", "off"))
        self._update_volume_ui()
        self.overlay.set_pip_allowed(bool(prefs.get("pip_enabled", True)))
        self.titlebar.set_pin_allowed(bool(prefs.get("pin_enabled", True)))
        if prefs.get("pinned", False) and prefs.get("pin_enabled", True):
            QTimer.singleShot(300, lambda: self.set_pinned(True))
        self.show_page(PAGE_HOME)
        if paths:
            QTimer.singleShot(60, lambda: self.open_paths(paths))

    def _ensure_engine(self):
        if self.engine is not None or self._engine_tried:
            return self.engine
        self._engine_tried = True
        if not VLCEngine.available():
            self._vlc_error = VLC_ERROR
            return None
        try:
            self.engine = VLCEngine(int(self.video_host.winId()), self)
            self._connect_engine()
            self.engine.set_volume(int(prefs.get("volume", 100)))
            self.engine.set_muted(bool(prefs.get("muted", False)))
            self._update_volume_ui()
        except Exception as e:  # pragma: no cover
            self.engine = None
            self._vlc_error = str(e)
        return self.engine

    # ================================================================== arayüz
    def _build_ui(self):
        root = QWidget(self)
        root.setObjectName("Root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.titlebar = TitleBar(root)
        v.addWidget(self.titlebar)
        tb = self.titlebar
        tb.minimize.connect(self.showMinimized)
        tb.maximize.connect(self.toggle_maximize)
        tb.close.connect(self.close)
        tb.open_file.connect(self.open_file_dialog)
        tb.open_folder.connect(self.open_folder_dialog)
        tb.theme_clicked.connect(self.toggle_theme)
        tb.pin_clicked.connect(lambda: self.set_pinned(not self._pinned))
        tb.prefs_clicked.connect(self.show_preferences)
        tb.sidebar_clicked.connect(self.toggle_sidebar)
        tb.search_changed.connect(self._on_search)
        tb.home_clicked.connect(self.go_home)

        self.body = QWidget(root)
        self.body_lay = QHBoxLayout(self.body)
        self.body_lay.setContentsMargins(0, 0, 0, 0)
        self.body_lay.setSpacing(12)
        v.addWidget(self.body, 1)

        self.main_col = QWidget(self.body)
        self.main_col.setObjectName("MainArea")
        self.main_lay = QVBoxLayout(self.main_col)
        self.main_lay.setContentsMargins(0, 0, 0, 0)
        self.main_lay.setSpacing(0)

        self.player_area = QWidget(self.main_col)
        self.player_area.setObjectName("PlayerArea")
        self.player_area.setStyleSheet("#PlayerArea { background: #000000; }")
        self.player_area.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        pa = QVBoxLayout(self.player_area)
        pa.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget(self.player_area)
        pa.addWidget(self.stack)
        self.home = HomeView()
        self.home.open_file.connect(self.open_file_dialog)
        self.home.open_folder.connect(self.open_folder_dialog)
        self.home.open_recent.connect(lambda p: self.open_paths([p]))
        self.stack.addWidget(self.home)
        self.video_host = QWidget()
        self.video_host.setStyleSheet("background: #000000;")
        self.video_host.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.video_host.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.stack.addWidget(self.video_host)
        self.audio_view = AudioView()
        self.stack.addWidget(self.audio_view)
        self.viewer = ImageViewer()
        self.viewer.set_alpha_bg(lp.get("image_alpha_bg"))
        self.viewer.zoom_changed.connect(lambda z: self.overlay.set_zoom(z))
        self.viewer.mouse_moved.connect(self._on_image_mouse)
        self.viewer.double_clicked.connect(
            lambda: self._edit_panel is None and lp.get("dblclick_fullscreen") and self.toggle_fullscreen())
        self.viewer.context_requested.connect(self._image_context)
        self.stack.addWidget(self.viewer)
        # 3D görüntüleyici: OpenGL penceresi ilk modelde oluşturulur (açılışı yavaşlatmasın)
        self.model_host = QWidget()
        self._model_lay = QVBoxLayout(self.model_host)
        self._model_lay.setContentsMargins(0, 0, 0, 0)
        self.viewer3d = None
        self._model_cache = {}
        self.stack.addWidget(self.model_host)
        self.player_area.installEventFilter(self)
        self.toast = Toast(self.player_area)
        self.main_lay.addWidget(self.player_area, 1)

        self.info = InfoBar(self.main_col)
        self.info.action.connect(self._on_info_action)
        self.main_lay.addWidget(self.info)
        self.body_lay.addWidget(self.main_col, 1)

        self.right = QStackedWidget(self.body)
        self.right.setMinimumWidth(340)
        self.right.setMaximumWidth(460)
        self.sidebar = Sidebar(self.right)
        self.sidebar.model.on_missing = self.thumbs.ensure
        self.sidebar.item_activated.connect(self.play_item)
        self.sidebar.filter_changed.connect(self._on_filter)
        self.sidebar.sort_changed.connect(self._on_sort)
        self.sidebar.context_requested.connect(self._item_context)
        self.sidebar.open_folder_clicked.connect(self.open_folder_dialog)
        self.sidebar.close_clicked.connect(self.toggle_sidebar)
        self.sidebar.set_filter_visual(self.lib.filter)
        self.sidebar.set_sort(self.lib.sort)
        self.right.addWidget(self.sidebar)
        self.body_lay.addWidget(self.right)

    def _connect_overlay(self):
        o = self.overlay
        o.play_clicked.connect(self.toggle_play)
        o.next_clicked.connect(self.play_next)
        o.prev_clicked.connect(self.play_prev)
        o.seek_requested.connect(self._on_seek)
        o.scrubbing.connect(self._on_scrub)
        o.volume_changed.connect(self.set_volume)
        o.mute_clicked.connect(self.toggle_mute)
        o.cc_clicked.connect(self._on_cc)
        o.snapshot_clicked.connect(self.take_snapshot)
        o.loop_clicked.connect(self.cycle_loop)
        o.stretch_clicked.connect(self.toggle_stretch)
        o.settings_clicked.connect(self.show_player_menu)
        o.pip_clicked.connect(self.toggle_pip)
        o.theater_clicked.connect(self.toggle_theater)
        o.fullscreen_clicked.connect(self.toggle_fullscreen)
        o.autoplay_toggled.connect(lambda v: (prefs.set("autoplay", v), self.osd(t("autoplay") + ": " + (t("on") if v else t("off")))))
        o.slideshow_clicked.connect(self.toggle_slideshow)
        o.zoom_in_clicked.connect(lambda: self._active_viewer().zoom_by(1.25))
        o.zoom_out_clicked.connect(lambda: self._active_viewer().zoom_by(0.8))
        o.fit_clicked.connect(self._fit_toggle)
        o.rotate_clicked.connect(self._rotate_clicked)
        o.edit_clicked.connect(self.edit_current)
        o.video_clicked.connect(self._on_video_click)
        o.video_double_clicked.connect(self._on_video_double_click)
        o.hold_changed.connect(self._on_hold)
        o.wheel.connect(self._on_wheel)
        o.context_requested.connect(self._video_context)
        o.seek_hover.connect(self._on_seek_hover)
        o.files_dropped.connect(self.open_paths)

    def _connect_engine(self):
        e = self.engine
        e.playing.connect(self._on_playing)
        e.paused.connect(lambda: self._on_paused())
        e.stopped.connect(lambda: self._on_paused())
        e.ended.connect(self._on_ended)
        e.error.connect(self._on_error)
        e.length_changed.connect(self._on_length)
        e.vout_changed.connect(self._on_vout)

    def _warn_no_vlc(self):
        QMessageBox.warning(self, "gamma", t("no_vlc") + (f"\n\n{self._vlc_error}" if getattr(self, "_vlc_error", None) else ""))

    # ================================================================== düzen
    def _apply_layout(self):
        fs, pip = self.isFullScreen(), self._pip
        immersive = fs or pip
        self.titlebar.setVisible(not immersive)
        show_side = self._sidebar_visible and not self._theater and not immersive and bool(self.lib.folder)
        if self._edit_panel is not None and self.right.currentWidget() is self._edit_panel:
            show_side = not immersive
        self.right.setVisible(show_side)
        has_media = self.current is not None
        self.info.setVisible(has_media and not self._theater and not immersive and bool(lp.get("show_infobar")))
        self.titlebar.set_sidebar_checked(show_side)
        if immersive:
            self.body_lay.setContentsMargins(0, 0, 0, 0)
            self.main_lay.setContentsMargins(0, 0, 0, 0)
        elif self._theater:
            self.body_lay.setContentsMargins(0, 0, 0, 0)
            self.main_lay.setContentsMargins(0, 0, 0, 0)
        else:
            side_m = 8 if show_side else (16 if has_media else 0)
            main_m = 16 if has_media else 0
            if lp.get("sidebar_side") == "left":
                self.body_lay.setContentsMargins(side_m, 0, main_m, 8 if has_media else 0)
            else:
                self.body_lay.setContentsMargins(main_m, 0, side_m, 8 if has_media else 0)
            self.main_lay.setContentsMargins(0, 0, 0, 0)
        self.overlay.set_theater(self._theater)
        self.overlay.set_fullscreen(fs)
        QTimer.singleShot(0, self.sync_overlay)

    def apply_personalization(self):
        """Seçenekler › Kişiselleştirme değişince tüm arayüzü yeniden düzenler."""
        self.titlebar.apply_personalization()
        self.overlay.apply_personalization()
        self.info.apply_personalization()
        if self.current is not None:
            self.info.set_item(self.current)
        self._apply_sidebar_side()
        self.sidebar.view.reset()
        self.sidebar.view.doItemsLayout()
        self.home.refresh_recent()
        self._apply_layout()

    def _apply_sidebar_side(self):
        left = lp.get("sidebar_side") == "left"
        lay = self.body_lay
        lay.removeWidget(self.main_col)
        lay.removeWidget(self.right)
        if left:
            lay.addWidget(self.right)
            lay.addWidget(self.main_col, 1)
        else:
            lay.addWidget(self.main_col, 1)
            lay.addWidget(self.right)

    def show_page(self, page):
        self.stack.setCurrentIndex(page)
        mode = {PAGE_HOME: PlayerOverlay.MODE_NONE, PAGE_VIDEO: PlayerOverlay.MODE_VIDEO,
                PAGE_AUDIO: PlayerOverlay.MODE_AUDIO, PAGE_IMAGE: PlayerOverlay.MODE_IMAGE,
                PAGE_MODEL: PlayerOverlay.MODE_IMAGE}[page]
        self.overlay.set_model_mode(page == PAGE_MODEL)
        if page != PAGE_MODEL and self.viewer3d is not None:
            self.viewer3d.set_autorotate(False)
        self.player_area.setStyleSheet("#PlayerArea { background: %s; }" %
                                       ("#000000" if page in (PAGE_VIDEO, PAGE_AUDIO) else "transparent"))
        if self.overlay.mode != mode:
            self.overlay.set_mode(mode)
        self.sync_overlay()

    def sync_overlay(self):
        o = self.overlay
        if o.mode == PlayerOverlay.MODE_NONE or not self.isVisible() or self.isMinimized() \
                or not self.player_area.isVisible():
            if o.isVisible():
                o.hide()
            return
        tl = self.player_area.mapToGlobal(QPoint(0, 0))
        r = QRect(tl, self.player_area.size())
        if o.mode == PlayerOverlay.MODE_IMAGE:
            if self._edit_panel is not None and self.right.currentWidget() is self._edit_panel:
                o.hide()
                return
            h = 66
            r = QRect(r.left(), r.bottom() - h + 1, r.width(), h)
            if not o.controls_visible():
                if o.isVisible():
                    o.hide()
                return
        if o.geometry() != r:
            o.setGeometry(r)
        if not o.isVisible():
            o.show()

    def eventFilter(self, obj, ev):
        if obj is self.player_area and ev.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show):
            self.sync_overlay()
            if self._video_zoom != "fit":
                QTimer.singleShot(0, self._apply_video_zoom)
        return super().eventFilter(obj, ev)

    def moveEvent(self, e):
        super().moveEvent(e)
        self.sync_overlay()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.sync_overlay()

    def changeEvent(self, e):
        if e.type() == QEvent.Type.WindowStateChange:
            self.titlebar.set_maximized(self.isMaximized())
            if not self.isFullScreen():
                QTimer.singleShot(0, self._apply_native_frame)
            QTimer.singleShot(0, self._apply_corners)
            QTimer.singleShot(0, self.sync_overlay)
            if self._pinned:
                QTimer.singleShot(50, lambda: self._apply_topmost(True))
        elif e.type() == QEvent.Type.ActivationChange:
            QTimer.singleShot(0, self.sync_overlay)
        super().changeEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        self._apply_native_frame()
        self._apply_corners()
        QTimer.singleShot(0, self.sync_overlay)
        QTimer.singleShot(0, self.setFocus)

    def hideEvent(self, e):
        super().hideEvent(e)
        self.overlay.hide()

    # ================================================================== Windows Snap
    def _apply_native_frame(self):
        """Çerçevesiz pencereye Windows'un yeniden boyutlandırma/Snap/animasyon stillerini geri verir.
        Görünür çerçeve WM_NCCALCSIZE ile gizlenir; böylece kenara sürükleyince 1/2, 1/4 ve tam ekran
        yaslama, Win+ok tuşları ve küçültme/büyütme animasyonları çalışır."""
        if self.isFullScreen():
            return
        try:
            hwnd = int(self.winId())
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            want = style | WS_THICKFRAME | WS_CAPTION | WS_MAXIMIZEBOX | WS_MINIMIZEBOX | WS_SYSMENU
            if want != style:
                user32.SetWindowLongW(hwnd, GWL_STYLE, want)
                user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0004 | 0x0010 | 0x0020)
        except Exception:
            pass

    def _apply_corners(self):
        """Windows 11'de pencere köşelerini Tercihler penceresi gibi yuvarlak yapar (tam ekranda köşeli).
        Windows 10'da bu öznitelik yok, çağrı sessizce başarısız olur."""
        try:
            pref = ctypes.c_int(1 if self.isFullScreen() else 2)   # DWMWCP_DONOTROUND / DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), 33, ctypes.byref(pref), ctypes.sizeof(pref))
        except Exception:
            pass

    def nativeEvent(self, event_type, message):
        try:
            msg = wintypes.MSG.from_address(int(message))
        except Exception:
            return False, 0
        if msg.message == WM_NCCALCSIZE and msg.wParam:
            if user32.IsZoomed(msg.hWnd) and not self.isFullScreen():
                # Büyütülmüş pencere ekran dışına taşmasın: istemci alanını çalışma alanına eşitle
                params = NCCALCSIZE_PARAMS.from_address(msg.lParam)
                mon = user32.MonitorFromWindow(msg.hWnd, 2)
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                if user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
                    params.rgrc[0] = mi.rcWork
            return True, 0
        if msg.message == WM_NCHITTEST and not self.isFullScreen():
            gp = QCursor.pos()
            if not self.isMaximized() and not self._pip:
                g = self.frameGeometry()
                m = 6
                left, right = gp.x() <= g.left() + m, gp.x() >= g.right() - m
                top, bottom = gp.y() <= g.top() + m, gp.y() >= g.bottom() - m
                code = {(True, False, True, False): 13, (False, True, True, False): 14,
                        (True, False, False, True): 16, (False, True, False, True): 17}.get((left, right, top, bottom))
                if code is None:
                    code = 10 if left else 11 if right else 12 if top else 15 if bottom else None
                if code is not None:
                    return True, code
            tb = self.titlebar
            if tb.isVisible():
                local = tb.mapFromGlobal(gp)
                if tb.rect().contains(local):
                    child = tb.childAt(local)
                    if tb.is_drag_area(child):
                        return True, 2  # HTCAPTION
        return False, 0

    # ================================================================== açma
    def open_file_dialog(self):
        start = self.lib.folder or os.path.expanduser("~")
        files, _ = QFileDialog.getOpenFileNames(self, t("open_file"), start, dialog_filter(t))
        if files:
            self.open_paths(files)

    def open_folder_dialog(self):
        start = self.lib.folder or os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, t("open_folder"), start)
        if d:
            self.open_paths([d])

    def open_paths(self, paths):
        paths = [p for p in paths if p and os.path.exists(p)]
        if not paths:
            return
        # Video oynarken altyazı dosyası bırakılırsa ekle
        subs = [p for p in paths if ext_of(p) in SUBTITLE_EXT]
        if subs and self.current is not None and self.current.is_video and self.engine:
            for s in subs:
                if self.engine.add_subtitle(s):
                    self.osd(t("subtitle_added") + ": " + os.path.basename(s))
            paths = [p for p in paths if p not in subs]
            if not paths:
                return
        target = paths[0]
        if not os.path.isdir(target) and not is_media(target):
            # Bilinmeyen uzantı: VLC'ye video olarak dene
            pass
        if self._edit_panel is not None and not self._close_image_editor():
            return
        item = self.lib.open_path(target)
        self._after_folder_loaded()
        prefs.add_recent(target)
        if item is None:
            self.osd(t("no_media_in_folder"))
            return
        self.load_item(item)

    def _after_folder_loaded(self):
        try:
            if self.watcher.directories():
                self.watcher.removePaths(self.watcher.directories())
            if self.lib.folder:
                self.watcher.addPath(self.lib.folder)
        except Exception:
            pass
        self._image_cache.clear()
        self._image_order.clear()
        if lp.get("sidebar_autoshow"):
            self._sidebar_visible = len(self.lib.all_items) > 1
        self.lib.explorer_sort = "name"
        self._refresh_sidebar()
        folder = self.lib.folder
        if folder:
            from .library import explorer_sort_for
            thumbs.run_async(explorer_sort_for, folder, on_done=lambda m, f=folder: self._on_explorer_sort(f, m))
        self._request_thumbs(self.lib.current)

    def _on_explorer_sort(self, folder, mode):
        if not mode or folder != self.lib.folder or mode == self.lib.explorer_sort:
            return
        self.lib.explorer_sort = mode
        if self.lib.sort == "explorer":
            self.lib._rebuild()
            self.sidebar.set_items(self.lib.items, self.current)
            self._update_counter()
            self._request_thumbs(self.current or self.lib.current)

    def _request_thumbs(self, first):
        """Küçük resimleri listede görünen sırayla iste (filtre dışındakiler sona)."""
        shown = list(self.lib.items)
        seen = {it.path for it in shown}
        self.thumbs.request(shown + [it for it in self.lib.all_items if it.path not in seen], first)

    def _refresh_sidebar(self):
        self.sidebar.set_counts(self.lib.counts())
        if self.lib.folder:
            self.sidebar.set_folder(self.lib.folder, len(self.lib.all_items))
        self.sidebar.set_items(self.lib.items, self.current or self.lib.current)

    def _folder_changed(self):
        if self.lib.refresh():
            self._refresh_sidebar()
            self._request_thumbs(self.current)

    def _on_filter(self, f):
        prefs.set("filter", f)
        self.lib.set_filter(f)
        self.sidebar.set_items(self.lib.items, self.current)

    def _on_sort(self, s):
        self.lib.set_sort(s)
        self.sidebar.set_items(self.lib.items, self.current)
        self._update_counter()
        self._request_thumbs(self.current)   # yeni sıraya göre en yakın modeller değişir

    def _on_search(self, text):
        self.lib.set_query(text)
        self.sidebar.set_items(self.lib.items, self.current)
        if text and not self.right.isVisible() and not self._pip and not self.isFullScreen():
            self._sidebar_visible = True
            self._theater = False
            self._apply_layout()

    def _on_thumb(self, path, img, meta):
        it = Library.find(path, self.lib.all_items)
        if it is not None:
            d = meta.get("duration", -1)
            if d and d > 0 and (it.duration is None or it.duration <= 0):
                it.duration = d
            if meta.get("w") and not it.width:
                it.width, it.height = int(meta.get("w", 0)), int(meta.get("h", 0))
            if it is self.current:
                self.info.set_details(it)
        if not img.isNull():
            from PyQt6.QtGui import QPixmap
            self.sidebar.model.set_thumb(path, QPixmap.fromImage(img))
        else:
            self.sidebar.model.refresh_row(path)

    # ================================================================== yükleme
    def play_item(self, item):
        if item is None:
            return
        if item is self.current and item.is_playable and self.engine:
            if not self.engine.is_playing():
                self.toggle_play()
            return
        if self._edit_panel is not None and not self._close_image_editor():
            return
        self.load_item(item)

    def load_item(self, item, start_ms=None):
        self._save_position()
        prev = self.current
        self.current = item
        self.lib.current = item
        self._ended = False
        self._ab = [None, None]
        self.overlay.seekbar.ab = (None, None)
        self.sidebar.set_current(item)
        title = item.title
        self.setWindowTitle(f"{title} - gamma")
        self.overlay.set_title(title)
        self.info.set_item(item, t("n_items", n=len(self.lib.all_items)))
        if prev is None or prev.kind != item.kind or not item.is_playable:
            pass
        if item.is_playable:
            self._stop_slideshow()
            self._ensure_engine()
            if self.engine is None:
                self._warn_no_vlc()
                return
            if prev is None or os.path.normcase(prev.path) != os.path.normcase(item.path):
                self._rotation = 0
                if self._aspect == "16:9":
                    self._aspect = None
                self.overlay.set_stretched(False)
            if start_ms is None and prefs.get("resume", True) and item.is_video:
                pos = positions.get(item.path)
                if pos:
                    start_ms = pos
                    QTimer.singleShot(700, lambda p=pos: self.osd(t("resumed_at", time=fmt_time(p))))
            self.engine.load(item.path, self._media_options(), start_ms or 0)
            self._vt = (start_ms or 0, time.perf_counter())
            self.overlay.set_time(start_ms or 0, max(0, item.duration))
            self.show_page(PAGE_VIDEO if item.is_video else PAGE_AUDIO)
            if item.is_audio:
                self.audio_view.clear_meta()
                self.audio_view.set_info(item.title)
                self.audio_view.set_cover(QImage())
                thumbs.run_async(thumbs.media_tags, item.path,
                                 on_done=lambda d, p=item.path: self._on_tags(p, d))
                thumbs.run_async(thumbs.extract_cover, item.path, 700,
                                 on_done=lambda img, p=item.path: self._on_cover(p, img))
            self.engine.play()
            self.overlay.set_playing(True)
            self._apply_sync_for(item)
            self.overlay.set_cc(False)
            if item.is_video:   # görüntüsü olmayan video uzantılı dosya (ör. yalnızca ses içeren mp4)?
                QTimer.singleShot(1200, lambda p=item.path: self._check_audio_only(p))
        elif item.is_model:
            self._stop_slideshow()
            if self.engine:
                self.engine.stop()
            self.overlay.set_playing(False)
            self.show_page(PAGE_MODEL)
            self._load_model(item)
        else:
            if self.engine:
                self.engine.stop()
            self.overlay.set_playing(False)
            self.show_page(PAGE_IMAGE)
            self._load_image(item)
        self._update_counter()
        self._apply_layout()

    def _media_options(self):
        opts = []
        if self._rotation:
            opts += [":video-filter=transform", f":transform-type={self._rotation}"]
        return opts

    def _apply_sync_for(self, item):
        s = sync_store.get(item.path)
        if s:
            QTimer.singleShot(400, lambda: (self.engine.set_audio_delay(s.get("audio_delay", 0)),
                                            self.engine.set_sub_delay(s.get("sub_delay", 0))))

    def _on_tags(self, path, data):
        if self.current and self.current.path == path:
            self.audio_view.set_meta(data.get("tags", {}), data.get("info", {}))
            tags = data.get("tags", {})
            if tags.get("title") and tags.get("artist"):
                self.overlay.set_title(f"{tags['artist']} — {tags['title']}")

    def _on_cover(self, path, img):
        if self.current and self.current.path == path:
            self.audio_view.set_cover(img)

    def _update_counter(self):
        if self.current is None:
            return
        seq = self.lib.items if self.lib.index_of(self.current) >= 0 else self.lib.all_items
        if self.current.is_image or self.current.is_model:
            kind = self.current.kind
            imgs = [i for i in seq if i.kind == kind]
            try:
                n = next(k for k, i in enumerate(imgs) if i is self.current) + 1
            except StopIteration:
                n = 1
            self.overlay.set_counter(f"{n} / {len(imgs)}")

    # ---------------------------------------------------------------- 3D model
    def _ensure_viewer3d(self):
        if self.viewer3d is None:
            from .model_viewer import ModelViewer
            v = ModelViewer(self.model_host)
            v.zoom_changed.connect(lambda z: self.overlay.set_zoom(z))
            v.mouse_moved.connect(self._on_image_mouse)
            v.double_clicked.connect(lambda: lp.get("dblclick_fullscreen") and self.toggle_fullscreen())
            v.context_requested.connect(self._model_context)
            v.autorotate_changed.connect(self.overlay.set_slideshow)
            self._model_lay.addWidget(v)
            self.viewer3d = v
        self.viewer3d.set_grid(lp.get("model_grid"))
        self.viewer3d.set_dims(lp.get("model_dims"))
        return self.viewer3d

    def _active_viewer(self):
        if self.current is not None and self.current.is_model and self.viewer3d is not None:
            return self.viewer3d
        return self.viewer

    def _load_model(self, item):
        v = self._ensure_viewer3d()
        v.set_autorotate(False)
        cached = self._model_cache.get(item.path)
        if cached is not None:
            self._show_model(item, cached)
            return
        v.clear()
        self.toast.show_text(t("loading"))
        from .model_io import load_model

        def done(model, path=item.path):
            self._model_cache.pop(path, None)
            self._model_cache[path] = model
            # Bellekte en fazla 3 model / ~6 milyon üçgen tut
            while len(self._model_cache) > 3 or (
                    sum(m.triangles for m in self._model_cache.values()) > 6_000_000 and len(self._model_cache) > 1):
                self._model_cache.pop(next(iter(self._model_cache)))
            if self.current and self.current.path == path:
                self.toast.hide()
                self._show_model(self.current, model)
                if self.thumbs._skip_model(self.current):   # listede küçük resmi yoktu: şimdi çiz
                    self.thumbs.store_model_thumb(self.current, model)

        def fail(msg, path=item.path):
            if self.current and self.current.path == path:
                key = {"compressed": "model_compressed", "ply_points": "model_points",
                       "cad_missing": "model_cad_missing"}.get(str(msg), "cannot_open_model")
                self.osd(t(key))
        thumbs.run_async(load_model, item.path, on_done=done, on_fail=fail)

    def _show_model(self, item, model):
        v = self.viewer3d
        v.set_model(model)
        if lp.get("model_autorotate"):
            v.set_autorotate(True)
        self.overlay.set_zoom(v.zoom_pct())

    def _rotate_clicked(self):
        if self.current is not None and self.current.is_model and self.viewer3d is not None:
            self.viewer3d.rotate_model("x", -90)
        else:
            self.viewer.rotate_view(90)

    def _save_model_view(self, transparent=False):
        """Görünümü PNG kaydet; transparent=True: arka plansız, 2 kat çözünürlük, kenarları kırpılmış."""
        if self.viewer3d is None or self.current is None:
            return
        d = prefs.get("snapshot_dir") or os.path.join(os.path.expanduser("~"), "Pictures", "gamma")
        os.makedirs(d, exist_ok=True)
        base = os.path.join(d, self.current.title)
        path, n = base + ".png", 1
        while os.path.exists(path):
            n += 1
            path = f"{base} ({n}).png"
        title = t("save_view_transparent") if transparent else t("save_view")
        path, _ = QFileDialog.getSaveFileName(self, title.rstrip("…"), path, "PNG (*.png)")
        if path:
            self.viewer3d.image(transparent=transparent).save(path, "PNG")
            self.osd(t("saved_to", p=os.path.basename(path)))

    def _add_model_convert_menu(self, menu, item):
        """Sağ tık: 3D modeli STL / OBJ / 3MF / GLB / PLY olarak kaydet (orijinal korunur)."""
        from .model_io import EXPORT_FORMATS
        sm = menu.addMenu(t("convert_model"))
        for label, ext in EXPORT_FORMATS:
            if item.ext == ext:
                continue
            sm.addAction(t("convert_to", fmt=label), lambda e=ext: self.convert_model(item, e))

    def convert_model(self, item, ext):
        target = os.path.splitext(item.path)[0] + ext
        if os.path.exists(target):
            r = QMessageBox.question(self, t("convert_title"), t("file_exists_overwrite") + "\n" + os.path.basename(target))
            if r != QMessageBox.StandardButton.Yes:
                return
        src = item.path
        cached = self._model_cache.get(src)
        self.osd(t("converting"))

        def work():
            from .model_io import load_model, export_model
            return export_model(cached if cached is not None else load_model(src), target)

        def done(p):
            self.lib.refresh()
            self._refresh_sidebar()
            self._request_thumbs(self.current)
            self.osd(t("converted", name=os.path.basename(p)))
        thumbs.run_async(work, on_done=done,
                         on_fail=lambda m: QMessageBox.warning(self, t("convert_title"), t("save_failed") + "\n" + str(m)))

    def _model_context(self, gpos):
        if not self.current or not self.current.is_model or self.viewer3d is None:
            return
        v = self.viewer3d
        m = QMenu(self)
        a = m.addAction(t("stop_autorotate") if v.autorotate else t("autorotate"))
        a.triggered.connect(lambda: v.set_autorotate(not v.autorotate))
        m.addAction(t("reset_view"), v.reset_view)
        m.addAction(t("flip_model"), lambda: v.rotate_model("x", -90))
        m.addAction(t("turn_model"), lambda: v.rotate_model("z", 90))
        m.addSeparator()
        wf = m.addAction(t("wireframe"))
        wf.setCheckable(True)
        wf.setChecked(v.wireframe)
        wf.triggered.connect(v.set_wireframe)
        gr = m.addAction(t("floor_grid"))
        gr.setCheckable(True)
        gr.setChecked(v.show_grid)
        gr.triggered.connect(lambda c: (prefs.set("model_grid", bool(c)), v.set_grid(c)))
        dm = m.addAction(t("dimensions"))
        dm.setCheckable(True)
        dm.setChecked(v.show_dims)
        dm.triggered.connect(lambda c: (prefs.set("model_dims", bool(c)), v.set_dims(c)))
        m.addSeparator()
        m.addAction(t("copy_view"), lambda: (QApplication.clipboard().setImage(v.image()), self.osd(t("copied"))))
        m.addAction(t("save_view"), self._save_model_view)
        m.addAction(t("save_view_transparent"), lambda: self._save_model_view(transparent=True))
        self._add_model_convert_menu(m, self.current)
        m.addSeparator()
        m.addAction(t("act_info"), self.show_info)
        m.addAction(t("act_reveal"), lambda: self.reveal(self.current))
        m.addAction(t("copy_path"), lambda: QApplication.clipboard().setText(self.current.path))
        m.exec(gpos)

    # ---------------------------------------------------------------- resim
    def _load_image(self, item):
        cached = self._image_cache.get(item.path)
        if cached is not None:
            self._show_loaded(item, cached)
            self._prefetch()
            return
        self.viewer.clear()
        from .image_io import load_image

        def done(res, path=item.path):
            self._cache_image(path, res)
            if self.current and self.current.path == path:
                self._show_loaded(self.current, res)
                self._prefetch()

        def fail(msg, path=item.path):
            if self.current and self.current.path == path:
                self.osd(t("cannot_open_image"))
        thumbs.run_async(load_image, item.path, on_done=done, on_fail=fail)

    def _cache_image(self, path, res):
        self._image_cache[path] = res
        if path in self._image_order:
            self._image_order.remove(path)
        self._image_order.append(path)
        total = 0
        for p in reversed(self._image_order):
            r = self._image_cache.get(p)
            if r:
                total += sum(f.sizeInBytes() for f in r.frames)
        while len(self._image_order) > 6 or (total > 600 * 1024 * 1024 and len(self._image_order) > 1):
            old = self._image_order.pop(0)
            r = self._image_cache.pop(old, None)
            if r:
                total -= sum(f.sizeInBytes() for f in r.frames)

    def _show_loaded(self, item, res):
        self.viewer.set_frames(res.frames, res.durations)
        if res.frames and not item.width:
            w, h = res.info.get("size", (res.first.width(), res.first.height()))
            item.width, item.height = w, h
            self.info.set_details(item)
        if self._slideshow:
            self.slide_timer.start(int(prefs.get("slideshow_seconds", 4)) * 1000)

    def _prefetch(self):
        from .image_io import load_image
        for step in (1, -1):
            nb = self.lib.neighbor(step, kinds=("image",))
            if nb and nb.is_image and nb.path not in self._image_cache and nb.size < 60 * 1024 * 1024:
                thumbs.run_async(load_image, nb.path, on_done=lambda r, p=nb.path: self._cache_image(p, r))

    def _on_image_mouse(self):
        if self.overlay.mode == PlayerOverlay.MODE_IMAGE:
            if not self.overlay.controls_visible():
                self.overlay.show_controls()
            else:
                self.overlay.show_controls()
            self.sync_overlay()

    def _fit_toggle(self):
        if self.current is not None and self.current.is_model and self.viewer3d is not None:
            self.viewer3d.reset_view()
            return
        if self.viewer._fit:
            self.viewer.actual_size()
        else:
            self.viewer.fit()

    def toggle_slideshow(self):
        if self.current is not None and self.current.is_model:
            if self.viewer3d is not None:
                self.viewer3d.set_autorotate(not self.viewer3d.autorotate)
            return
        if self._slideshow:
            self._stop_slideshow()
            self.osd(t("slideshow_stopped"))
        else:
            self._slideshow = True
            self.overlay.set_slideshow(True)
            self.slide_timer.start(int(prefs.get("slideshow_seconds", 4)) * 1000)
            self.osd(t("slideshow_started", s=prefs.get("slideshow_seconds", 4)))

    def _stop_slideshow(self):
        self._slideshow = False
        self.slide_timer.stop()
        self.overlay.set_slideshow(False)

    def _slide_next(self):
        if not self._slideshow:
            return
        nxt = self.lib.neighbor(1, kinds=("image",), wrap=True, shuffle=prefs.get("shuffle", False))
        if nxt and nxt.is_image:
            self.load_item(nxt)
        else:
            self._stop_slideshow()

    # ================================================================== oynatma
    def toggle_play(self):
        if self.current is None:
            self.open_file_dialog()
            return
        if self.current.is_image:
            self.toggle_slideshow()
            return
        if not self.engine:
            return
        was = self.engine.is_playing()
        if self._ended:
            self._ended = False
            self.engine.stop()
            self.engine.play()
            self.overlay.flash("play")
            return
        self.engine.toggle()
        self.overlay.flash("pause" if was else "play")

    def _on_video_double_click(self, ratio):
        # Sağ üçte birlik alan: 2x hızı aç/kapat; diğer yerler: tam ekran
        if ratio >= 0.66 and self.current and self.current.is_playable and self.engine and lp.get("right_speed"):
            if abs(self.engine.rate() - 2.0) < 0.01:
                self.engine.set_rate(getattr(self, "_rate_before_2x", 1.0) or 1.0)
            else:
                self._rate_before_2x = self.engine.rate()
                self.engine.set_rate(2.0)
            r = self.engine.rate()
            self.osd(t("speed") + ": " + (t("normal") if abs(r - 1) < 0.01 else f"{r:g}x"))
            return
        if lp.get("dblclick_fullscreen"):
            self.toggle_fullscreen()

    def _on_hold(self, on, ratio):
        """Videonun sağ yarısına basılı tutunca geçici 2x (YouTube gibi)."""
        if not self.engine or not self.current or not self.current.is_playable or not lp.get("right_speed"):
            return
        if on:
            if ratio < 0.5 or not self.engine.is_playing():
                return
            self._hold_rate = self.engine.rate()
            self.engine.set_rate(2.0)
            self.overlay.set_badge("2x  ▶▶")
        elif getattr(self, "_hold_rate", None) is not None:
            self.engine.set_rate(self._hold_rate)
            self._hold_rate = None
            self.overlay.set_badge("")

    def _on_video_click(self):
        if lp.get("click_action") != "play":
            return
        if self.current and self.current.is_playable:
            self.toggle_play()

    def _on_playing(self):
        self._ended = False
        self.engine.on_playing_hook()
        self._vt = (self.engine.get_time(), time.perf_counter())
        self.overlay.set_playing(True)
        if self.current and self.current.is_audio:
            QTimer.singleShot(400, self._read_meta)
        if self._video_zoom != "fit" or self._aspect or self._crop:
            QTimer.singleShot(300, self._reapply_video_settings)
        QTimer.singleShot(600, self._update_cc_icon)

    def _reapply_video_settings(self):
        if not self.engine:
            return
        self.engine.set_aspect(self._aspect)
        self.engine.set_crop(self._crop)
        self._apply_video_zoom()
        if self._deinterlace:
            self.engine.set_deinterlace("yadif")
        self.engine.set_adjust(**self._adjust)

    def _on_paused(self):
        self.overlay.set_playing(False)
        if self.engine:
            self._vt = (self.engine.get_time(), time.perf_counter())

    def _read_meta(self):
        if not self.engine or not self.current or not self.current.is_audio:
            return
        if self.audio_view.meta:
            return  # ffmpeg etiketleri zaten yüklendi
        m = self.engine.read_meta()
        title = m.get("title") or self.current.title
        if title in (self.current.name, self.current.path):
            title = self.current.title
        self.audio_view.set_info(title, m.get("artist", ""), m.get("album", ""))

    def _on_vout(self, n):
        # Video uzantılı ama görüntüsü olmayan dosyalar (ör. sadece ses içeren mp4)
        if self.current and self.current.is_video and n == 0:
            QTimer.singleShot(1200, lambda p=self.current.path: self._check_audio_only(p))
        elif self.current and self.current.is_video and n > 0 and self.stack.currentIndex() == PAGE_AUDIO:
            self.show_page(PAGE_VIDEO)

    def _check_audio_only(self, path=None, tries=0):
        """Video uzantılı dosyada gerçekten görüntü yoksa müzik görünümüne geç.
        Yalnızca "görüntü penceresi açılmadı"ya bakmak yetmiyor: ağır videolarda ya da 3D / görselden dönüşte
        görüntü geç gelir. Bu yüzden dosyadaki görüntü kanalı da sorulur; bilinmiyorsa biraz sonra tekrar bakılır."""
        cur = self.current
        if not (self.engine and cur and cur.is_video) or (path and cur.path != path):
            return
        if self.engine.has_video():
            return
        n = self.engine.video_track_count()
        if n > 0:
            return                       # görüntü kanalı var: yalnızca geç açılıyor
        if n < 0 or not self.engine.is_playing():
            if tries < 4:                # henüz bilinmiyor / oynamaya başlamadı
                QTimer.singleShot(800, lambda p=cur.path, k=tries + 1: self._check_audio_only(p, k))
            return
        self.audio_view.set_info(cur.title)
        self.show_page(PAGE_AUDIO)

    def _on_length(self, ms):
        if self.current and ms > 0:
            if abs((self.current.duration or 0) - ms) > 500:
                self.current.duration = ms
                self.sidebar.model.refresh_row(self.current.path)
                self.info.set_details(self.current)

    def _on_error(self):
        self.osd(t("cannot_play"))
        self.overlay.set_playing(False)

    def _on_ended(self):
        self._ended = True
        if self.current:
            positions.set(self.current.path, 0, 0)
        if self._sleep_end_of_media:
            self._sleep_end_of_media = False
            self.overlay.set_ended()
            self.osd(t("sleep_done"))
            return
        loop = prefs.get("loop", "off")
        if loop == "one":
            QTimer.singleShot(0, self._restart)
            return
        if prefs.get("autoplay", True):
            nxt = self.lib.neighbor(1, kinds=("video", "audio"), wrap=(loop == "all"),
                                    shuffle=prefs.get("shuffle", False))
            if nxt is not None and nxt is not self.current and nxt.is_playable:
                QTimer.singleShot(0, lambda: self.load_item(nxt, start_ms=0))
                return
        if loop == "all":
            QTimer.singleShot(0, self._restart)
            return
        self.overlay.set_ended()
        length = self.engine.get_length() if self.engine else 0
        self.overlay.set_time(length, length)

    def _sleep_fire(self):
        if self.engine and self.engine.is_playing():
            self.engine.pause()
        self._stop_slideshow()
        self.osd(t("sleep_done"))

    def _restart(self):
        if self.engine:
            self._ended = False
            self.engine.stop()
            self.engine.play()

    def play_next(self):
        if self.current is None:
            return
        kinds = (self.current.kind,) if (self.current.is_image or self.current.is_model) else None
        nxt = self.lib.neighbor(1, kinds=kinds, wrap=prefs.get("loop", "off") == "all",
                                shuffle=prefs.get("shuffle", False) and kinds is None)
        if nxt:
            if self._edit_panel is not None and not self._close_image_editor():
                return
            self.load_item(nxt, start_ms=0 if nxt.is_playable else None)

    def play_prev(self):
        if self.current is None:
            return
        if self.current.is_playable and self.engine and self.engine.get_time() > 4000:
            self.seek_to(0)
            return
        kinds = (self.current.kind,) if (self.current.is_image or self.current.is_model) else None
        prv = self.lib.neighbor(-1, kinds=kinds, wrap=prefs.get("loop", "off") == "all")
        if prv:
            if self._edit_panel is not None and not self._close_image_editor():
                return
            self.load_item(prv, start_ms=0 if prv.is_playable else None)

    def seek_to(self, ms):
        if not self.engine or not self.current or not self.current.is_playable:
            return
        if self._ended:
            self._ended = False
            self.engine.stop()
            self.engine.play()
        self.engine.set_time(int(ms))
        self._vt = (int(ms), time.perf_counter())
        self.overlay.set_time(int(ms), self.engine.get_length())

    def seek_relative(self, delta_ms, bubble=True):
        if not self.engine or not self.current or not self.current.is_playable:
            return
        cur = self._display_time()
        length = self.engine.get_length()
        target = max(0, min(cur + delta_ms, length - 300 if length > 0 else cur + delta_ms))
        self.seek_to(target)
        if bubble:
            secs = abs(delta_ms) // 1000
            self.overlay.bubble("right" if delta_ms > 0 else "left", t("n_seconds", n=secs))

    def _on_seek(self, ms, final):
        now = time.perf_counter()
        if final or now - self._last_seek > 0.08:
            self._last_seek = now
            self.seek_to(ms)
        self.overlay.set_time(ms, self.engine.get_length() if self.engine else 0)

    def _on_scrub(self, on):
        self._scrubbing = on

    def _display_time(self):
        """VLC'nin zamanı ~250 ms aralıklarla ve titrek gelir; bunu yumuşak, tek yönlü bir saate çevirir."""
        if not self.engine:
            return 0
        vt = self.engine.get_time()
        now = time.perf_counter()
        base, at = self._vt
        if not self.engine.is_playing():
            self._vt = (vt, now)
            self._last_disp = vt
            return vt
        pred = base + (now - at) * 1000.0 * self.engine.rate()
        err = vt - pred
        if abs(err) > 450:
            # atlama/seek ya da takılma: saati yeniden hizala
            self._vt = (float(vt), now)
            pred = float(vt)
        elif abs(err) > 40:
            # küçük farkları kare başına en fazla 3 ms telafi et (gözle görülür sıçrama/yavaşlama olmaz)
            corr = max(-3.0, min(3.0, err * 0.03))
            self._vt = (base + corr, at)
            pred += corr
        last = getattr(self, "_last_disp", None)
        if last is not None and 0 < last - pred < 200:
            pred = last  # geri gitme
        self._last_disp = pred
        return int(pred)

    def _tick(self):
        if not self.engine or not self.current or not self.current.is_playable:
            return
        if self._scrubbing:
            return
        o = self.overlay
        if not o.isVisible() or not o.controls_visible():
            if int(time.perf_counter() * 4) % 4:
                return
        length = self.engine.get_length()
        cur = self._display_time()
        o.set_time(cur, length)
        a, b = self._ab
        if a is not None and b is not None and cur >= b and self.engine.is_playing():
            self.seek_to(a)

    def _save_position(self):
        if self.engine and self.current and self.current.is_video and not self._ended:
            length = self.engine.get_length()
            if length > 0:
                positions.set(self.current.path, self.engine.get_time(), length)

    # ---------------------------------------------------------------- önizleme
    def _on_seek_hover(self, ms):
        if not lp.get("seek_preview"):
            self._hover_bucket = None
            self.overlay.set_preview_image(None)
            return
        if ms < 0 or not self.current or not self.current.is_video or not self.engine:
            self._hover_bucket = None
            return
        length = self.engine.get_length() or self.current.duration
        b = self.grabber.bucket_for(length, ms)
        self._hover_bucket = b
        img = self.grabber.cached(self.current.path, b)
        if img is None:
            img = self.grabber.nearest_cached(self.current.path, b)
            self.grabber.request(self.current.path, b)
        self.overlay.set_preview_image(img)

    def _on_preview_frame(self, path, bucket, img):
        if self.current and self.current.path == path and self._hover_bucket == bucket:
            self.overlay.set_preview_image(img)

    # ---------------------------------------------------------------- ses
    def set_volume(self, v, osd=False):
        if not self.engine:
            return
        v = max(0, min(200, int(v)))
        self.engine.set_volume(v)
        if self.engine.muted() and v > 0:
            self.engine.set_muted(False)
        prefs.set("volume", v)
        prefs.set("muted", self.engine.muted())
        self._update_volume_ui()
        if osd:
            self.osd(t("volume_pct", v=v))

    def toggle_mute(self):
        if not self.engine:
            return
        m = not self.engine.muted()
        if not m and self.engine.volume() == 0:
            self.engine.set_volume(50)
        self.engine.set_muted(m)
        prefs.set("muted", m)
        self._update_volume_ui()
        self.osd(t("muted") if m else t("volume_pct", v=self.engine.volume()))

    def _update_volume_ui(self):
        if self.engine:
            self.overlay.set_volume(self.engine.volume(), self.engine.muted())

    def _on_wheel(self, delta, mods):
        if not self.current:
            return
        if self.current.is_playable and self.engine:
            if mods & Qt.KeyboardModifier.ControlModifier and self.current.is_video:
                self._zoom_step(1 if delta > 0 else -1)
                return
            action = lp.get("wheel_action")
            if action == "volume":
                self.set_volume(self.engine.volume() + (5 if delta > 0 else -5), osd=True)
            elif action == "seek":
                self.seek_relative(5000 if delta > 0 else -5000)

    # ---------------------------------------------------------------- altyazı
    def _on_cc(self):
        if not self.engine or not self.current or not self.current.is_video:
            return
        tracks = [tr for tr in self.engine.sub_tracks() if tr[0] != -1]
        cur = self.engine.get_sub_track()
        if not tracks:
            self.show_player_menu(page="subs")
            return
        if cur == -1:
            tid = getattr(self, "_last_sub", tracks[0][0])
            if tid not in [x[0] for x in tracks]:
                tid = tracks[0][0]
            self.engine.set_sub_track(tid)
            name = dict(tracks).get(tid, "")
            self.osd(t("subtitles") + ": " + name)
        else:
            self._last_sub = cur
            self.engine.set_sub_track(-1)
            self.osd(t("subtitles") + ": " + t("off"))
        QTimer.singleShot(150, self._update_cc_icon)

    def _update_cc_icon(self):
        if self.engine and self.current and self.current.is_video:
            self.overlay.set_cc(self.engine.get_sub_track() not in (-1, None))

    def add_subtitle_dialog(self):
        if not self.engine or not self.current or not self.current.is_video:
            return
        pat = " ".join("*" + e for e in sorted(SUBTITLE_EXT))
        f, _ = QFileDialog.getOpenFileName(self, t("add_subtitle"), os.path.dirname(self.current.path),
                                           f"{t('subtitle_files')} ({pat});;{t('all_files')} (*.*)")
        if f:
            if self.engine.add_subtitle(f):
                self.osd(t("subtitle_added") + ": " + os.path.basename(f))
                QTimer.singleShot(500, self._update_cc_icon)
            else:
                self.osd(t("subtitle_failed"))

    def adjust_sub_delay(self, d):
        if not self.engine:
            return
        v = self.engine.get_sub_delay() + d
        self.engine.set_sub_delay(v)
        self.osd(t("sub_delay_osd", v=f"{v:+d}"))
        return f"{v:+d} ms"

    def adjust_audio_delay(self, d):
        if not self.engine:
            return
        v = self.engine.get_audio_delay() + d
        self.engine.set_audio_delay(v)
        self.osd(t("audio_delay_osd", v=f"{v:+d}"))
        return f"{v:+d} ms"

    def _schedule_rebuild(self):
        self.sub_rebuild_timer.start()

    def _rebuild_engine(self):
        if not self.engine:
            return
        self.engine.rebuild()
        self._update_volume_ui()

    # ---------------------------------------------------------------- video
    def _zoom_step(self, direction):
        levels = ["fit", 1.25, 1.5, 2.0, 2.5, 3.0, 4.0]
        cur = self._video_zoom if self._video_zoom in levels else "fit"
        i = levels.index(cur) + direction
        i = max(0, min(len(levels) - 1, i))
        self._video_zoom = levels[i]
        self._apply_video_zoom()
        self.osd(t("zoom_fit") if self._video_zoom == "fit" else t("zoom_pct", v=int(self._video_zoom * 100)))

    def _apply_video_zoom(self):
        if not self.engine:
            return
        z = self._video_zoom
        if z == "fit":
            self.engine.set_scale(0)
            return
        vw, vh = self.engine.video_size()
        dpr = self.devicePixelRatioF()
        aw, ah = self.player_area.width() * dpr, self.player_area.height() * dpr
        if vw <= 0 or vh <= 0:
            return
        if z == "fill":
            s = max(aw / vw, ah / vh)
        elif z == "orig":
            s = 1.0
        else:
            s = min(aw / vw, ah / vh) * float(z)
        self.engine.set_scale(s)

    def set_rotation(self, deg):
        if not self.engine or not self.current or not self.current.is_video:
            return
        self._rotation = deg
        t_ = self.engine.get_time()
        playing = self.engine.is_playing()
        self.engine.load(self.current.path, self._media_options(), t_)
        self.engine.play()
        if not playing:
            self.engine._pause_after_start = True
        self.osd(t("rotation_osd", v=deg))

    def take_snapshot(self):
        if not self.engine or not self.current or not self.current.is_video:
            return
        d = prefs.get("snapshot_dir") or os.path.join(os.path.expanduser("~"), "Pictures", "gamma")
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            d = os.path.dirname(self.current.path)
        ms = self.engine.get_time()
        name = f"{self.current.title}_{fmt_time(ms).replace(':', '-')}.{ms % 1000:03d}.png"
        path = os.path.join(d, name)
        # VLC kareyi videonun orijinal çözünürlüğünde, kayıpsız PNG olarak yazar
        if self.engine.snapshot(path):
            self._last_snapshot = path
            self.overlay.flash("camera")
            QTimer.singleShot(350, lambda p=path, d=d: self._snapshot_to_clipboard(p, d))
        else:
            self.osd(t("snapshot_failed"))

    def _snapshot_to_clipboard(self, path, folder, tries=0):
        img = QImage(path)
        if img.isNull():
            if tries < 8:
                QTimer.singleShot(250, lambda: self._snapshot_to_clipboard(path, folder, tries + 1))
            else:
                self.osd(t("snapshot_saved", path=folder))
            return
        QApplication.clipboard().setImage(img)
        self.osd(t("snapshot_saved_clip", w=img.width(), h=img.height()))

    def cycle_loop(self):
        """Döngü: kapalı → klasörü tekrarla → bu medyayı tekrarla → kapalı"""
        order = ["off", "all", "one"]
        cur = prefs.get("loop", "off")
        nxt = order[(order.index(cur) + 1) % 3] if cur in order else "all"
        prefs.set("loop", nxt)
        self.overlay.set_loop(nxt)
        self.osd(t("loop") + ": " + t("loop_" + nxt))

    def toggle_stretch(self):
        """4:3 (veya başka oran) videoyu tek tıkla 16:9'a uzatır / geri alır."""
        if not self.engine or not self.current or not self.current.is_video:
            return
        self._aspect = None if self._aspect == "16:9" else "16:9"
        self.engine.set_aspect(self._aspect)
        self.overlay.set_stretched(self._aspect == "16:9")
        self.osd(t("stretched_on") if self._aspect else t("stretched_off"))

    def set_ab_point(self):
        if not self.engine or not self.current or not self.current.is_playable:
            return
        now = self.engine.get_time()
        a, b = self._ab
        if a is None:
            self._ab = [now, None]
            self.osd(t("ab_a_set", time=fmt_time(now)))
        elif b is None and now > a + 300:
            self._ab = [a, now]
            self.osd(t("ab_loop_on", a=fmt_time(a), b=fmt_time(now)))
        else:
            self._ab = [None, None]
            self.osd(t("ab_off"))
        self.overlay.seekbar.ab = tuple(self._ab)
        self.overlay.seekbar.update()

    # ================================================================== pencere modları
    def toggle_maximize(self):
        if self._pip:
            return
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def toggle_fullscreen(self):
        if self._pip:
            self.toggle_pip()
            return
        if self.isFullScreen():
            was_max = self._fs_state
            self._fs_state = None
            if was_max:
                self.showMaximized()
            else:
                self.showNormal()
        else:
            self._fs_state = self.isMaximized()
            self.showFullScreen()
        QTimer.singleShot(0, self._apply_layout)
        QTimer.singleShot(200, self._apply_layout)

    def toggle_theater(self):
        if self._pip or self.isFullScreen():
            return
        self._theater = not self._theater
        prefs.set("theater", self._theater)
        self._apply_layout()

    def toggle_sidebar(self):
        if self._pip or self.isFullScreen():
            return
        if self._theater:
            self._theater = False
            prefs.set("theater", False)
            self._sidebar_visible = True
        else:
            self._sidebar_visible = not self._sidebar_visible
        prefs.set("sidebar_visible", self._sidebar_visible)
        self._apply_layout()

    def go_home(self):
        if self._pip or self.isFullScreen():
            return
        if self.engine:
            self._save_position()
            self.engine.stop()
        if self._edit_panel is not None and not self._close_image_editor():
            return
        self._stop_slideshow()
        if self.viewer3d is not None:
            self.viewer3d.set_autorotate(False)
        self.current = None
        self.lib.current = None
        self.sidebar.set_current(None)
        self.home.refresh_recent()
        self.show_page(PAGE_HOME)
        self.setWindowTitle("gamma")
        self._apply_layout()

    def toggle_pip(self):
        if not prefs.get("pip_enabled", True) and not self._pip:
            self.osd(t("pip_disabled"))
            return
        if self._pip:
            self._exit_pip()
        else:
            self._enter_pip()

    def _enter_pip(self):
        if self.current is None:
            return
        if self.isFullScreen():
            self.showNormal()
        self._pip_state = {
            "geometry": self.geometry() if not self.isMaximized() else self.normalGeometry(),
            "maximized": self.isMaximized(),
            "pinned": self._pinned,
        }
        self._pip = True
        if self.isMaximized():
            self.showNormal()
        self.setMinimumSize(240, 136)
        scr = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        w = 480
        h = 270
        if self.engine and self.current and self.current.is_video:
            vw, vh = self.engine.video_size()
            if vw > 0 and vh > 0:
                h = int(w * vh / vw)
                h = max(150, min(h, 480))
        elif self.current and self.current.is_image and self.viewer.has_image():
            im = self.viewer.image()
            h = max(150, min(int(w * im.height() / max(1, im.width())), 480))
        self.overlay.set_pip(True)
        self._apply_layout()
        self.setGeometry(scr.right() - w - 24, scr.bottom() - h - 24, w, h)
        self._apply_topmost(True)
        QTimer.singleShot(50, self.sync_overlay)

    def _exit_pip(self):
        st = self._pip_state or {}
        self._pip = False
        self.overlay.set_pip(False)
        self.setMinimumSize(760, 480)
        self._apply_layout()
        if st.get("geometry"):
            self.setGeometry(st["geometry"])
        if st.get("maximized"):
            self.showMaximized()
        self._apply_topmost(bool(self._pinned))
        QTimer.singleShot(50, self.sync_overlay)

    def set_pinned(self, on):
        if on and not prefs.get("pin_enabled", True):
            self.osd(t("pin_disabled"))
            on = False
        self._pinned = bool(on)
        prefs.set("pinned", self._pinned)
        self.titlebar.set_pinned(self._pinned)
        self._apply_topmost(self._pinned or self._pip)
        self.osd(t("pinned_on") if self._pinned else t("pinned_off"))

    def _apply_topmost(self, on):
        try:
            user32.SetWindowPos(wintypes.HWND(int(self.winId())), HWND_TOPMOST if on else HWND_NOTOPMOST,
                                0, 0, 0, 0, SWP_FLAGS)
        except Exception:
            pass

    def toggle_theme(self):
        theme.apply("light" if current_name() == "dark" else "dark")
        self.osd(t("dark_mode") if current_name() == "dark" else t("light_mode"))
        if self.current:
            self.info.set_details(self.current)
        self.viewer.update()

    # ================================================================== bildirim
    def osd(self, text):
        if not lp.get("osd_messages"):
            return
        if self.overlay.mode in (PlayerOverlay.MODE_VIDEO, PlayerOverlay.MODE_AUDIO) and self.overlay.isVisible():
            self.overlay.osd(text)
        else:
            self.toast.show_text(text)

    # ================================================================== menüler
    def show_player_menu(self, page=None):
        if not self.current or not self.current.is_playable or not self.engine:
            return
        from .player_menu import build_root, build_subs

        def anchor():
            o = self.overlay
            g = o.geometry()
            bottom = g.bottom() - 62
            return g.right() - 12, bottom, g.height() - 90
        self.menu.open(build_subs(self) if page == "subs" else build_root(self), anchor)

    def _video_context(self, gpos):
        if not self.current:
            return
        m = QMenu(self)
        if self.current.is_playable:
            a = m.addAction(t("pause") if (self.engine and self.engine.is_playing()) else t("play"))
            a.triggered.connect(self.toggle_play)
            loop = m.addAction(t("loop_one"))
            loop.setCheckable(True)
            loop.setChecked(prefs.get("loop", "off") == "one")
            loop.triggered.connect(lambda c: (prefs.set("loop", "one" if c else "off"),
                                              self.overlay.set_loop(prefs.get("loop", "off"))))
            sh = m.addAction(t("shuffle"))
            sh.setCheckable(True)
            sh.setChecked(bool(prefs.get("shuffle", False)))
            sh.triggered.connect(lambda c: prefs.set("shuffle", c))
            m.addSeparator()
            if self.current.is_video:
                m.addAction(t("snapshot"), self.take_snapshot)
                m.addAction(t("add_subtitle") + "…", self.add_subtitle_dialog)
            m.addAction(t("ab_loop"), self.set_ab_point)
            m.addAction(t("act_edit") + "…", self.edit_current)
            m.addSeparator()
        m.addAction(t("act_info"), self.show_info)
        m.addAction(t("act_reveal"), lambda: self.reveal(self.current))
        m.addAction(t("copy_path"), lambda: QApplication.clipboard().setText(self.current.path))
        m.addSeparator()
        if prefs.get("pip_enabled", True):
            m.addAction(t("pip_exit") if self._pip else t("pip_tip"), self.toggle_pip)
        if prefs.get("pin_enabled", True):
            pa = m.addAction(t("pin_tip"))
            pa.setCheckable(True)
            pa.setChecked(self._pinned)
            pa.triggered.connect(self.set_pinned)
        m.addAction(t("exit_fullscreen_tip") if self.isFullScreen() else t("fullscreen_tip"), self.toggle_fullscreen)
        m.exec(gpos)

    ALPHA_BGS = (("bg_checker", "checker"), ("bg_black", "#000000"), ("bg_white", "#ffffff"),
                 ("bg_gray", "#808080"), ("bg_green", "#00b140"))

    def _add_alpha_bg_menu(self, menu):
        """Saydam görselin altında ne görünsün: dama, siyah, beyaz, gri, yeşil ya da özel renk (hatırlanır).
        Yalnızca görünümü değiştirir; dosyaya ve kopyalanan resme dokunmaz."""
        from PyQt6.QtGui import QActionGroup
        sub = menu.addMenu(t("alpha_bg"))
        grp = QActionGroup(sub)
        cur = self.viewer.alpha_bg
        known = False

        def apply(v):
            prefs.set("image_alpha_bg", v)
            self.viewer.set_alpha_bg(v)
        for key, val in self.ALPHA_BGS:
            a = sub.addAction(t(key), lambda v=val: apply(v))
            a.setCheckable(True)
            a.setChecked(cur.lower() == val)
            known = known or cur.lower() == val
            grp.addAction(a)
        sub.addSeparator()

        def custom():
            from PyQt6.QtWidgets import QColorDialog
            start = QColor(cur) if cur != "checker" else QColor("#00b140")
            c = QColorDialog.getColor(start, self, t("alpha_bg"))
            if c.isValid():
                apply(c.name())
        a = sub.addAction(t("bg_custom"), custom)
        a.setCheckable(True)
        a.setChecked(not known)
        grp.addAction(a)

    def _image_context(self, gpos):
        if not self.current or not self.current.is_image:
            return
        m = QMenu(self)
        m.addAction(t("act_edit_image"), self.edit_current)
        self._add_convert_menu(m, self.current)
        m.addAction(t("slideshow"), self.toggle_slideshow)
        m.addAction(t("rotate"), lambda: self.viewer.rotate_view(90))
        m.addAction(t("copy_image"), lambda: QApplication.clipboard().setImage(self.viewer.image()))
        if self.viewer.has_alpha():
            self._add_alpha_bg_menu(m)
        m.addSeparator()
        m.addAction(t("act_info"), self.show_info)
        m.addAction(t("act_reveal"), lambda: self.reveal(self.current))
        m.addAction(t("copy_path"), lambda: QApplication.clipboard().setText(self.current.path))
        if prefs.get("pip_enabled", True):
            m.addSeparator()
            m.addAction(t("pip_exit") if self._pip else t("pip_tip"), self.toggle_pip)
        m.exec(gpos)

    def _item_context(self, item, gpos):
        m = QMenu(self)
        m.addAction(t("open"), lambda: self.play_item(item))
        if not item.is_model:
            m.addAction(t("act_edit_image") if item.is_image else t("act_edit") + "…", lambda: self.edit_item(item))
        if item.is_image:
            self._add_convert_menu(m, item)
        elif item.is_model:
            self._add_model_convert_menu(m, item)
        m.addSeparator()
        m.addAction(t("act_info"), lambda: self.show_info(item))
        m.addAction(t("act_reveal"), lambda: self.reveal(item))
        m.addAction(t("copy_path"), lambda: QApplication.clipboard().setText(item.path))
        m.addAction(t("rename") + "…", lambda: self.rename_item(item))
        m.addSeparator()
        m.addAction(t("move_to_trash"), lambda: self.trash_item(item))
        m.exec(gpos)

    def _on_info_action(self, key):
        if key == "edit":
            self.edit_current()
        elif key == "snapshot":
            self.take_snapshot()
        elif key == "subtitle":
            self.add_subtitle_dialog()
        elif key == "reveal":
            self.reveal(self.current)
        elif key == "info":
            self.show_info()
        elif key == "delete" and self.current is not None:
            self.trash_item(self.current)
        elif key == "more":
            if self.current is not None and self.current.is_model:
                self._model_context(QCursor.pos())
            else:
                self._video_context(QCursor.pos())

    # ================================================================== dosya işlemleri
    def reveal(self, item):
        if not item:
            return
        import subprocess
        subprocess.Popen(["explorer", "/select,", os.path.normpath(item.path)])

    def rename_item(self, item):
        new, ok = QInputDialog.getText(self, t("rename"), t("new_name"), text=item.name)
        if not ok or not new or new == item.name:
            return
        dst = os.path.join(os.path.dirname(item.path), new)
        if os.path.exists(dst):
            QMessageBox.warning(self, t("rename"), t("file_exists"))
            return
        playing = item is self.current and item.is_playable and self.engine
        pos = self.engine.get_time() if playing else 0
        if playing:
            self.engine.stop()
        try:
            os.rename(item.path, dst)
        except OSError as e:
            QMessageBox.warning(self, t("rename"), str(e))
            if playing:
                self.engine.play()
            return
        self.lib.refresh()
        new_item = Library.find(dst, self.lib.all_items)
        self._refresh_sidebar()
        self._request_thumbs(new_item)
        if item is self.current and new_item:
            self.load_item(new_item, start_ms=pos if playing else None)

    def trash_item(self, item):
        if lp.get("confirm_delete"):
            r = QMessageBox.question(self, t("move_to_trash"), t("confirm_trash", name=item.name))
            if r != QMessageBox.StandardButton.Yes:
                return
        is_cur = item is self.current
        if is_cur:
            nxt = self.lib.neighbor(1) or self.lib.neighbor(-1)
            if self.engine:
                self.engine.stop()
                self.engine.mp.set_media(None)
        from PyQt6.QtCore import QFile
        ok = QFile.moveToTrash(item.path)
        if not ok:
            QMessageBox.warning(self, t("move_to_trash"), t("trash_failed"))
            return
        self._image_cache.pop(item.path, None)
        self._model_cache.pop(item.path, None)
        self.lib.remove(item)
        self._refresh_sidebar()
        if is_cur:
            if nxt and nxt is not item:
                self.load_item(nxt)
            else:
                self.go_home()

    def show_info(self, item=None):
        item = item or self.current
        if not item:
            return
        from .dialogs import MediaInfoDialog
        MediaInfoDialog(item, self).exec()

    def show_preferences(self):
        from .dialogs import PreferencesDialog
        dlg = PreferencesDialog(self)
        dlg.exec()

    def apply_feature_toggles(self):
        pin_ok = bool(prefs.get("pin_enabled", True))
        pip_ok = bool(prefs.get("pip_enabled", True))
        self.titlebar.set_pin_allowed(pin_ok)
        self.overlay.set_pip_allowed(pip_ok)
        if not pin_ok and self._pinned:
            self.set_pinned(False)
        if not pip_ok and self._pip:
            self._exit_pip()

    # ================================================================== düzenleme
    def edit_current(self):
        self.edit_item(self.current)

    def edit_item(self, item):
        if item is None or item.is_model:
            return
        if item.is_image:
            if item is not self.current:
                self.load_item(item)
            QTimer.singleShot(0, self._open_image_editor)
        else:
            from .video_editor import VideoEditorDialog
            start = 0
            if item is self.current and self.engine:
                start = self.engine.get_time()
                if self.engine.is_playing():
                    self.engine.pause()
            dlg = VideoEditorDialog(item, self, start_ms=start)
            dlg.exported.connect(self._on_exported)
            dlg.release_file.connect(self._release_file)
            dlg.exec()

    def _release_file(self, path):
        """Üzerine yazmadan önce VLC'nin dosyayı bırakması."""
        if self.current and os.path.normcase(self.current.path) == os.path.normcase(path) and self.engine:
            self._save_position()
            self.engine.stop()
            self.engine.mp.set_media(None)
            self._released = path

    def _on_exported(self, path):
        self.lib.refresh()
        it = Library.find(path, self.lib.all_items)
        if it is not None:
            try:
                st = os.stat(path)
                it.size, it.mtime, it.duration = st.st_size, st.st_mtime, -1
            except OSError:
                pass
        self._refresh_sidebar()
        self._request_thumbs(self.current)
        self.osd(t("export_done"))
        released = getattr(self, "_released", None)
        if released and it is not None and os.path.normcase(released) == os.path.normcase(path):
            self._released = None
            self.load_item(it, start_ms=0)

    def _add_convert_menu(self, menu, item):
        """Sağ tık: tek tıkla PNG / ICO / JPG / WebP'ye dönüştür (orijinal korunur)."""
        sm = menu.addMenu(t("convert_title"))
        for label, ext in (("PNG", ".png"), ("ICO (" + t("icon") + ")", ".ico"), ("JPEG", ".jpg"), ("WebP", ".webp")):
            if item.ext == ext or (ext == ".jpg" and item.ext in (".jpeg", ".jpe", ".jfif")):
                continue
            sm.addAction(t("convert_to", fmt=label), lambda e=ext: self.quick_convert(item, e))
        sm.addSeparator()
        sm.addAction(t("other_formats") + "…", lambda: self.convert_item(item))

    def quick_convert(self, item, ext):
        from . import image_io
        target = os.path.splitext(item.path)[0] + ext
        if os.path.exists(target):
            r = QMessageBox.question(self, t("convert_title"), t("file_exists_overwrite") + "\n" + os.path.basename(target))
            if r != QMessageBox.StandardButton.Yes:
                return
        src = item.path

        def work():
            img = image_io.open_pil(src)
            if getattr(img, "n_frames", 1) > 1:
                img.seek(0)
            tmp = target + ".gamma-tmp" + ext
            image_io.save_pil(img, tmp, quality=92)
            os.replace(tmp, target)
            return target

        def done(p):
            self.lib.refresh()
            self._refresh_sidebar()
            self._request_thumbs(self.current)
            self.osd(t("converted", name=os.path.basename(p)))
        thumbs.run_async(work, on_done=done, on_fail=lambda m: QMessageBox.warning(self, t("convert_title"), t("save_failed") + "\n" + m))

    def convert_item(self, item):
        from .dialogs import ConvertDialog

        def done(p):
            self.lib.refresh()
            self._refresh_sidebar()
            self._request_thumbs(self.current)
            self.osd(t("converted", name=os.path.basename(p)))
        ConvertDialog(item, self, on_done=done).exec()

    def _open_image_editor(self):
        if not self.current or not self.current.is_image or self._pip:
            return
        if self.isFullScreen():
            self.toggle_fullscreen()
        if self.viewer.is_animated():
            r = QMessageBox.question(self, t("act_edit_image"), t("anim_edit_warning"))
            if r != QMessageBox.StandardButton.Yes:
                return
        from .image_editor import ImageEditPanel
        self._stop_slideshow()
        panel = ImageEditPanel(self, self.current, self.viewer)
        panel.closed.connect(self._image_editor_closed)
        panel.saved.connect(self._on_image_saved)
        self._edit_panel = panel
        self.right.addWidget(panel)
        self.right.setCurrentWidget(panel)
        self._apply_layout()

    def _close_image_editor(self):
        p = self._edit_panel
        if p is None:
            return True
        return p.request_close()

    def _image_editor_closed(self):
        p = self._edit_panel
        self._edit_panel = None
        if p is not None:
            self.right.setCurrentWidget(self.sidebar)
            self.right.removeWidget(p)
            p.deleteLater()
        if self.current and self.current.is_image:
            self._image_cache.pop(self.current.path, None)
            self._load_image(self.current)
        self._apply_layout()

    def _on_image_saved(self, path):
        self._image_cache.pop(path, None)
        self.lib.refresh()
        self._refresh_sidebar()
        it = Library.find(path, self.lib.all_items)
        if it:
            self.thumbs.request_one(it)

    # ================================================================== sürükle-bırak
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.open_paths(paths)

    # ================================================================== klavye
    def keyPressEvent(self, e):
        if self.focusWidget() is self.titlebar.search:
            if e.key() == Qt.Key.Key_Escape:
                self.titlebar.search.clearFocus()
                if not prefs.get("show_search", False):
                    self.titlebar.set_search_visible(False)
            return super().keyPressEvent(e)
        from .shortcuts import handle_key
        if not handle_key(self, e):
            super().keyPressEvent(e)

    def mousePressEvent(self, e):
        if self.titlebar.search.hasFocus():
            self.titlebar.search.clearFocus()
        super().mousePressEvent(e)

    # ================================================================== kapanış
    def _restore_geometry(self):
        g = prefs.get("window_geometry")
        scr = QGuiApplication.primaryScreen().availableGeometry()
        if g and len(g) == 5:
            x, y, w, h, maxed = g
            r = QRect(x, y, w, h)
            if any(s.availableGeometry().intersects(r) for s in QGuiApplication.screens()):
                self.setGeometry(r)
                if maxed:
                    QTimer.singleShot(0, self.showMaximized)
                return
        w, h = min(1400, int(scr.width() * 0.8)), min(860, int(scr.height() * 0.82))
        self.setGeometry(scr.x() + (scr.width() - w) // 2, scr.y() + (scr.height() - h) // 2, w, h)

    def closeEvent(self, e):
        if self._edit_panel is not None and not self._close_image_editor():
            e.ignore()
            return
        self._save_position()
        if not self._pip and not self.isFullScreen():
            g = self.normalGeometry() if self.isMaximized() else self.geometry()
            prefs.set("window_geometry", [g.x(), g.y(), g.width(), g.height(), self.isMaximized()])
        elif self._pip and self._pip_state:
            g = self._pip_state["geometry"]
            prefs.set("window_geometry", [g.x(), g.y(), g.width(), g.height(), self._pip_state["maximized"]])
        self.ui_timer.stop()
        self.overlay.hide()
        self.menu.hide()
        if self.engine:
            self.engine.release()
        self.thumbs.shutdown()
        self.grabber.stop()
        super().closeEvent(e)
        QApplication.instance().quit()
