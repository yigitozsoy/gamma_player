"""Video / ses düzenleyici: kes (A–B), kırp/oranla, döndür, çevir, ölçekle, hızlandır, dönüştür."""
import os
import re

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QProcess, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QImage, QTransform, QPen, QPainterPath
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QCheckBox,
                             QLineEdit, QFileDialog, QProgressBar, QMessageBox, QGridLayout, QSlider,
                             QButtonGroup, QScrollArea, QStackedWidget)

from . import thumbs
from .config import prefs
from .i18n import t
from .image_viewer import ImageViewer
from .library import fmt_time
from .widgets import ThemedDialog, Chip, IconButton, Divider

FORMATS = [
    # anahtar, etiket, uzantı, video_var
    ("mp4", "MP4 (H.264)", ".mp4", True),
    ("mp4_hevc", "MP4 (H.265 / HEVC)", ".mp4", True),
    ("webm", "WebM (VP9 + Opus)", ".webm", True),
    ("mkv", "MKV (H.264)", ".mkv", True),
    ("gif", "GIF", ".gif", True),
    ("mp3", "MP3", ".mp3", False),
    ("m4a", "M4A (AAC)", ".m4a", False),
    ("opus", "Opus", ".opus", False),
    ("flac", "FLAC", ".flac", False),
    ("wav", "WAV", ".wav", False),
]
CROP_RATIOS = [("none", None), ("free", "free"), ("16:9", 16 / 9), ("9:16", 9 / 16), ("1:1", 1.0),
               ("4:3", 4 / 3), ("4:5", 4 / 5), ("21:9", 21 / 9)]
SCALES = [("orig", 0), ("2160p", 2160), ("1440p", 1440), ("1080p", 1080), ("720p", 720), ("480p", 480), ("360p", 360)]
SPEEDS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0]


def parse_time(text):
    text = text.strip().replace(",", ".")
    if not text:
        return None
    parts = text.split(":")
    try:
        total = 0.0
        for p in parts:
            total = total * 60 + float(p)
        return int(total * 1000)
    except ValueError:
        return None


def fmt_precise(ms):
    ms = max(0, int(ms))
    s, msr = divmod(ms, 1000)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return (f"{h}:{m:02d}:{s:02d}.{msr // 10:02d}" if h else f"{m}:{s:02d}.{msr // 10:02d}")


def atempo_chain(speed):
    parts = []
    s = speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.4f}")
    return parts


class Timeline(QWidget):
    """Film şeridi / dalga formu üzerinde A–B tutamaçları ve oynatma imleci."""
    changed = pyqtSignal(int, int)      # a, b
    scrubbed = pyqtSignal(int)          # imleç ms

    def __init__(self, length, parent=None):
        super().__init__(parent)
        self.length = max(1, length)
        self.a, self.b = 0, self.length
        self.head = 0
        self.strip = []          # QImage listesi
        self.wave = None
        self.setMinimumHeight(86)
        self.setMouseTracking(True)
        self._drag = None

    def _x(self, ms):
        pad = 12
        return pad + (self.width() - 2 * pad) * ms / self.length

    def _ms(self, x):
        pad = 12
        return int(max(0, min(self.length, (x - pad) / max(1, self.width() - 2 * pad) * self.length)))

    def set_range(self, a, b):
        self.a, self.b = max(0, a), min(self.length, b)
        self.update()

    def set_head(self, ms):
        self.head = ms
        self.update()

    def mousePressEvent(self, e):
        x = e.position().x()
        xa, xb = self._x(self.a), self._x(self.b)
        if abs(x - xa) < 12:
            self._drag = "a"
        elif abs(x - xb) < 12:
            self._drag = "b"
        else:
            self._drag = "head"
            self.head = self._ms(x)
            self.scrubbed.emit(self.head)
        self.update()

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self._drag is None:
            xa, xb = self._x(self.a), self._x(self.b)
            self.setCursor(Qt.CursorShape.SizeHorCursor if min(abs(x - xa), abs(x - xb)) < 12
                           else Qt.CursorShape.PointingHandCursor)
            return
        ms = self._ms(x)
        if self._drag == "a":
            self.a = min(ms, self.b - 100)
            self.head = self.a
            self.changed.emit(self.a, self.b)
            self.scrubbed.emit(self.a)
        elif self._drag == "b":
            self.b = max(ms, self.a + 100)
            self.head = self.b
            self.changed.emit(self.a, self.b)
            self.scrubbed.emit(self.b)
        else:
            self.head = ms
            self.scrubbed.emit(ms)
        self.update()

    def mouseReleaseEvent(self, e):
        self._drag = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pad = 12
        r = QRectF(pad, 14, self.width() - 2 * pad, self.height() - 28)
        clip = QPainterPath()
        clip.addRoundedRect(r, 6, 6)
        p.save()
        p.setClipPath(clip)
        p.fillRect(r, QColor("#1f1f1f"))
        if self.wave is not None and not self.wave.isNull():
            p.drawImage(r, self.wave)
        elif self.strip:
            n = len(self.strip)
            cw = r.width() / n
            for i, img in enumerate(self.strip):
                if img is None or img.isNull():
                    continue
                cell = QRectF(r.left() + i * cw, r.top(), cw + 0.5, r.height())
                s = max(cell.width() / img.width(), cell.height() / img.height())
                w, h = img.width() * s, img.height() * s
                p.save()
                p.setClipRect(cell)
                p.drawImage(QRectF(cell.center().x() - w / 2, cell.center().y() - h / 2, w, h), img)
                p.restore()
        # seçili olmayan bölgeleri karart
        xa, xb = self._x(self.a), self._x(self.b)
        p.fillRect(QRectF(r.left(), r.top(), xa - r.left(), r.height()), QColor(0, 0, 0, 170))
        p.fillRect(QRectF(xb, r.top(), r.right() - xb, r.height()), QColor(0, 0, 0, 170))
        p.restore()
        # seçim çerçevesi
        sel = QRectF(xa, r.top() - 2, xb - xa, r.height() + 4)
        p.setPen(QPen(QColor("#ffd400"), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(sel, 6, 6)
        for x in (xa, xb):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#ffd400"))
            p.drawRoundedRect(QRectF(x - 5, r.top() - 4, 10, r.height() + 8), 4, 4)
            p.setBrush(QColor("#1f1f1f"))
            p.drawRoundedRect(QRectF(x - 1, r.center().y() - 8, 2, 16), 1, 1)
        # imleç
        xh = self._x(self.head)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawLine(QPointF(xh, 2), QPointF(xh, self.height() - 2))
        p.setBrush(QColor("#ffffff"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(xh, 6), 5, 5)


class VideoEditorDialog(ThemedDialog):
    exported = pyqtSignal(str)
    release_file = pyqtSignal(str)     # üzerine yazmadan önce oynatıcı dosyayı bıraksın

    def __init__(self, item, parent=None, start_ms=0):
        super().__init__(parent, t("editor_title") + " — " + item.name)
        self.item = item
        self.is_video = item.is_video
        self.length = item.duration if item.duration and item.duration > 0 else 0
        self.proc = None
        self.out_path = ""
        self.rotation = 0
        self.flip = False
        self.crop_norm = None
        self._frame = QImage()
        self._expected_ms = 1
        self.resize(1180, 780)
        self.setMinimumSize(900, 640)
        self.grabber = thumbs.FrameGrabber(self, width=960, accurate=True)
        self.grabber.frame.connect(self._on_frame)
        self.grabber.start()
        self._head = max(0, start_ms)
        self._build()
        if self.length <= 0:
            thumbs.run_async(lambda: thumbs.parse_duration(thumbs.probe(item.path)), on_done=self._got_length)
        else:
            self._init_timeline()

    # ---------------------------------------------------------------- arayüz
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(10)
        self.preview = ImageViewer()
        self.preview.allow_zoom = False
        self.preview.bg_override = "#000000"
        self.preview.setMinimumSize(560, 315)
        # Oynatırken VLC'nin çizdiği yerel video alanı; duraklayınca kare/kırpma görünümü
        self.video_box = QWidget()
        self.video_box.setStyleSheet("background: #000000;")
        self.video_box.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.video_box.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.pstack = QStackedWidget()
        self.pstack.addWidget(self.preview)
        self.pstack.addWidget(self.video_box)
        left.addWidget(self.pstack, 1)
        self._peng = None
        self._ptimer = QTimer(self)
        self._ptimer.setInterval(40)
        self._ptimer.timeout.connect(self._preview_tick)
        self.preview.crop_changed.connect(self._on_crop_changed)

        trow = QHBoxLayout()
        self.lbl_head = QLabel("0:00.00")
        self.lbl_head.setStyleSheet("font-family: 'Cascadia Mono', Consolas, monospace; font-size: 13px;")
        b_back = IconButton("prev", t("frame_back"), 36, 20)
        b_back.clicked.connect(lambda: self._nudge(-1000))
        b_fwd = IconButton("next", t("frame_fwd"), 36, 20)
        b_fwd.clicked.connect(lambda: self._nudge(1000))
        b_seta = QPushButton(t("set_start"))
        b_seta.setObjectName("Pill")
        b_seta.clicked.connect(lambda: self._set_a(self._head))
        b_setb = QPushButton(t("set_end"))
        b_setb.setObjectName("Pill")
        b_setb.clicked.connect(lambda: self._set_b(self._head))
        self.b_play = IconButton("play", t("preview_play") + " (Space)", 40, 26)
        self.b_play.clicked.connect(self.toggle_preview)
        trow.addWidget(self.b_play)
        trow.addWidget(b_back)
        trow.addWidget(self.lbl_head)
        trow.addWidget(b_fwd)
        trow.addStretch(1)
        b_frame = IconButton("camera", t("save_frame"), 36, 20)
        b_frame.clicked.connect(self._save_frame)
        if self.is_video:
            trow.addWidget(b_frame)
        trow.addWidget(b_seta)
        trow.addWidget(b_setb)
        left.addLayout(trow)
        self.timeline_holder = QVBoxLayout()
        self.lbl_loading = QLabel(t("loading"))
        self.lbl_loading.setObjectName("Secondary")
        self.timeline_holder.addWidget(self.lbl_loading)
        left.addLayout(self.timeline_holder)
        root.addLayout(left, 1)

        # Sağ panel
        side_w = QWidget()
        side_w.setFixedWidth(340)
        side = QVBoxLayout(side_w)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(8)
        scroll.setWidget(body)
        side.addWidget(scroll, 1)

        lay.addWidget(self._title(t("trim")))
        g = QGridLayout()
        g.setHorizontalSpacing(8)
        self.ed_a = QLineEdit("0:00.00")
        self.ed_b = QLineEdit("0:00.00")
        self.ed_a.editingFinished.connect(lambda: self._edit_time("a"))
        self.ed_b.editingFinished.connect(lambda: self._edit_time("b"))
        g.addWidget(QLabel(t("start")), 0, 0)
        g.addWidget(self.ed_a, 0, 1)
        g.addWidget(QLabel(t("end")), 1, 0)
        g.addWidget(self.ed_b, 1, 1)
        self.lbl_dur = QLabel("")
        self.lbl_dur.setObjectName("Secondary")
        g.addWidget(self.lbl_dur, 2, 0, 1, 2)
        lay.addLayout(g)

        if self.is_video:
            lay.addWidget(Divider())
            lay.addWidget(self._title(t("crop_ratio")))
            cg = QGridLayout()
            cg.setSpacing(6)
            self.crop_group = QButtonGroup(self)
            for n, (key, val) in enumerate(CROP_RATIOS):
                c = Chip(t("ratio_" + key) if key in ("none", "free") else key)
                self.crop_group.addButton(c)
                c.clicked.connect(lambda _=False, v=val: self._set_crop_ratio(v))
                if key == "none":
                    c.setChecked(True)
                cg.addWidget(c, n // 4, n % 4)
            lay.addLayout(cg)
            rrow = QHBoxLayout()
            b1 = IconButton("rotate_left", t("rotate_left"), 38, 22)
            b1.clicked.connect(lambda: self._rotate(-90))
            b2 = IconButton("rotate_right", t("rotate_right"), 38, 22)
            b2.clicked.connect(lambda: self._rotate(90))
            b3 = IconButton("flip_h", t("flip_h"), 38, 22, checkable=True)
            b3.clicked.connect(self._toggle_flip)
            self.lbl_rot = QLabel("0°")
            self.lbl_rot.setObjectName("Secondary")
            for w in (b1, b2, b3, self.lbl_rot):
                rrow.addWidget(w)
            rrow.addStretch(1)
            lay.addLayout(rrow)
            self.chk_stretch = QCheckBox(t("stretch_169"))
            self.chk_stretch.toggled.connect(lambda _: (self._show_frame(), self._update_mode()))
            lay.addWidget(self.chk_stretch)
            srow = QHBoxLayout()
            srow.addWidget(QLabel(t("resolution")))
            self.cmb_scale = QComboBox()
            for key, h in SCALES:
                self.cmb_scale.addItem(t("original") if key == "orig" else key, h)
            self.cmb_scale.currentIndexChanged.connect(self._update_mode)
            srow.addWidget(self.cmb_scale, 1)
            lay.addLayout(srow)
            lay.addWidget(Divider())
            lay.addWidget(self._title(t("subtitles")))
            self.cmb_sub = QComboBox()
            self.cmb_sub.addItem(t("none"), None)
            self._sub_streams = []
            base = os.path.splitext(self.item.path)[0]
            from .formats import SUBTITLE_EXT
            for e in sorted(SUBTITLE_EXT):
                if os.path.exists(base + e) and e in (".srt", ".ass", ".ssa", ".vtt"):
                    self.cmb_sub.addItem(os.path.basename(base + e), ("file", base + e))
            self.cmb_sub.addItem(t("sub_from_file") + "…", ("pick", None))
            self.cmb_sub.currentIndexChanged.connect(self._sub_changed)
            lay.addWidget(self.cmb_sub)
            self.cmb_sub_mode = QComboBox()
            self.cmb_sub_mode.addItem(t("sub_burn"), "burn")
            self.cmb_sub_mode.addItem(t("sub_soft"), "soft")
            self.cmb_sub_mode.setToolTip(t("sub_mode_tip"))
            self.cmb_sub_mode.currentIndexChanged.connect(lambda _: self._update_mode())
            lay.addWidget(self.cmb_sub_mode)
            thumbs.run_async(thumbs.probe, self.item.path, on_done=self._fill_sub_streams)
            self._build_watermark(lay)

        lay.addWidget(Divider())
        lay.addWidget(self._title(t("speed_audio")))
        sprow = QHBoxLayout()
        sprow.addWidget(QLabel(t("speed")))
        self.cmb_speed = QComboBox()
        for s in SPEEDS:
            self.cmb_speed.addItem(t("normal") if s == 1.0 else f"{s:g}x", s)
        self.cmb_speed.setCurrentIndex(SPEEDS.index(1.0))
        self.cmb_speed.currentIndexChanged.connect(self._update_mode)
        sprow.addWidget(self.cmb_speed, 1)
        lay.addLayout(sprow)
        vrow = QHBoxLayout()
        vrow.addWidget(QLabel(t("volume")))
        self.sl_vol = QSlider(Qt.Orientation.Horizontal)
        self.sl_vol.setRange(0, 300)
        self.sl_vol.setValue(100)
        self.lbl_vol = QLabel("100%")
        self.lbl_vol.setFixedWidth(44)
        self.sl_vol.valueChanged.connect(lambda v: (self.lbl_vol.setText(f"{v}%"), self._update_mode()))
        vrow.addWidget(self.sl_vol, 1)
        vrow.addWidget(self.lbl_vol)
        lay.addLayout(vrow)
        self.chk_mute = QCheckBox(t("remove_audio"))
        self.chk_mute.toggled.connect(self._update_mode)
        if self.is_video:
            lay.addWidget(self.chk_mute)
        self.chk_fade = QCheckBox(t("fade_in_out"))
        self.chk_fade.toggled.connect(self._update_mode)
        lay.addWidget(self.chk_fade)
        self.chk_norm = QCheckBox(t("normalize_audio"))
        self.chk_norm.setToolTip(t("normalize_audio_tip"))
        self.chk_norm.toggled.connect(self._update_mode)
        lay.addWidget(self.chk_norm)

        lay.addWidget(Divider())
        lay.addWidget(self._title(t("output")))
        frow = QHBoxLayout()
        frow.addWidget(QLabel(t("format")))
        self.cmb_fmt = QComboBox()
        src_ext = self.item.ext
        for key, label, ext, has_v in FORMATS:
            if has_v and not self.is_video:
                continue
            self.cmb_fmt.addItem(label, key)
        if not self.is_video:
            for i in range(self.cmb_fmt.count()):
                k = self.cmb_fmt.itemData(i)
                if "." + k == src_ext or (k == "m4a" and src_ext in (".m4a", ".aac")) or (k == "opus" and src_ext in (".opus", ".ogg")):
                    self.cmb_fmt.setCurrentIndex(i)
        elif src_ext == ".webm":
            self.cmb_fmt.setCurrentIndex(2)
        elif src_ext == ".mkv":
            self.cmb_fmt.setCurrentIndex(3)
        self.cmb_fmt.currentIndexChanged.connect(self._format_changed)
        frow.addWidget(self.cmb_fmt, 1)
        lay.addLayout(frow)
        qrow = QHBoxLayout()
        qrow.addWidget(QLabel(t("quality")))
        self.cmb_q = QComboBox()
        self.cmb_q.addItem(t("q_high"), 18)
        self.cmb_q.addItem(t("q_good"), 22)
        self.cmb_q.addItem(t("q_small"), 27)
        self.cmb_q.setCurrentIndex(1)
        qrow.addWidget(self.cmb_q, 1)
        lay.addLayout(qrow)
        self.chk_fast = QCheckBox(t("fast_copy"))
        self.chk_fast.setChecked(True)
        self.chk_fast.setToolTip(t("fast_copy_tip"))
        self.chk_fast.toggled.connect(self._update_mode)
        lay.addWidget(self.chk_fast)
        self.lbl_mode = QLabel("")
        self.lbl_mode.setObjectName("Secondary")
        self.lbl_mode.setWordWrap(True)
        lay.addWidget(self.lbl_mode)
        lay.addStretch(1)

        self.lbl_out = QLabel("")
        self.lbl_out.setObjectName("Secondary")
        self.lbl_out.setWordWrap(True)
        self.lbl_out.hide()
        side.addWidget(self.lbl_out)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.hide()
        side.addWidget(self.progress)
        brow = QHBoxLayout()
        self.b_cancel = QPushButton(t("close"))
        self.b_cancel.setObjectName("Flat")
        self.b_cancel.clicked.connect(self._cancel_or_close)
        self.b_saveas = QPushButton(t("save_as"))
        self.b_saveas.setObjectName("Pill")
        self.b_saveas.clicked.connect(self._save_as)
        self.b_export = QPushButton(t("save"))
        self.b_export.setObjectName("Primary")
        self.b_export.setToolTip(t("save_overwrite_tip"))
        self.b_export.clicked.connect(self._save_overwrite)
        brow.addStretch(1)
        brow.addWidget(self.b_cancel)
        brow.addWidget(self.b_saveas)
        brow.addWidget(self.b_export)
        side.addLayout(brow)
        root.addWidget(side_w)
        self._format_changed()

    def _title(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        return lbl

    # ---------------------------------------------------------------- yükleme
    def _got_length(self, ms):
        self.length = max(1, ms if ms and ms > 0 else 1)
        self.item.duration = self.length
        self._init_timeline()

    def _init_timeline(self):
        self.lbl_loading.hide()
        self.timeline = Timeline(self.length)
        self.timeline.changed.connect(self._on_range)
        self.timeline.scrubbed.connect(self._seek_preview)
        self.timeline_holder.addWidget(self.timeline)
        self.a, self.b = 0, self.length
        self._head = min(self._head, self.length)
        self.timeline.set_head(self._head)
        self._sync_fields()
        self._seek_preview(self._head)
        path = self.item.path
        if self.is_video:
            n = 14
            length = self.length

            def strip():
                return [thumbs.grab_frame(path, int(length * (i + 0.5) / n), 160, timeout=8) for i in range(n)]
            thumbs.run_async(strip, on_done=self._on_strip)
        else:
            thumbs.run_async(thumbs.waveform, path, 1600, 140, "#3ea6ff", on_done=self._on_wave)
            thumbs.run_async(thumbs.extract_cover, path, 700, on_done=self._on_cover)

    def _on_strip(self, imgs):
        if hasattr(self, "timeline"):
            self.timeline.strip = imgs
            self.timeline.update()

    def _on_wave(self, img):
        if hasattr(self, "timeline"):
            self.timeline.wave = img
            self.timeline.update()
        if self._frame.isNull():
            self.preview.set_image(img)

    def _on_cover(self, img):
        if not img.isNull():
            self._frame = img
            self.preview.set_image(img)

    # ---------------------------------------------------------------- önizleme
    def _seek_preview(self, ms):
        self._head = ms
        self.lbl_head.setText(fmt_precise(ms))
        if hasattr(self, "timeline"):
            self.timeline.set_head(ms)
        if self.is_video:
            img = self.grabber.cached(self.item.path, ms)
            if img is not None:
                self._on_frame(self.item.path, ms, img)
            else:
                self.grabber.request(self.item.path, ms)

    def _on_frame(self, path, ms, img):
        if ms != self._head and abs(ms - self._head) > 1500:
            return
        self._frame = img
        self._show_frame(keep_crop=True)

    def _show_frame(self, keep_crop=True):
        if self._frame.isNull():
            return
        img = self._frame
        if self.rotation or self.flip:
            tr = QTransform()
            if self.rotation:
                tr.rotate(self.rotation)
            img = img.transformed(tr)
            if self.flip:
                img = img.mirrored(True, False)
        if self._stretch() and img.height() > 0:
            img = img.scaled(int(img.height() * 16 / 9), img.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        if self._wm_on():
            img = self._composite_wm(img)
        crop_on = self.preview.crop_mode
        size_changed = self.preview.has_image() and (self.preview.image().size() != img.size())
        self.preview.set_image(img, keep_view=True)
        if crop_on:
            ratio = self.preview.crop_ratio
            if size_changed or self.crop_norm is None:
                self.preview.set_crop_mode(True, ratio)
                self._on_crop_changed(self.preview.crop)
            else:
                w, h = img.width(), img.height()
                x0, y0, x1, y1 = self.crop_norm
                self.preview.crop = QRectF(x0 * w, y0 * h, (x1 - x0) * w, (y1 - y0) * h)
                self.preview.update()

    def _nudge(self, d):
        self._seek_preview(max(0, min(self.length, self._head + d)))

    # ---------------------------------------------------------------- aralık
    def _on_range(self, a, b):
        self.a, self.b = a, b
        self._sync_fields()

    def _set_a(self, ms):
        if not hasattr(self, "timeline"):
            return
        self.a = max(0, min(ms, self.b - 100))
        self.timeline.set_range(self.a, self.b)
        self._sync_fields()

    def _set_b(self, ms):
        if not hasattr(self, "timeline"):
            return
        self.b = min(self.length, max(ms, self.a + 100))
        self.timeline.set_range(self.a, self.b)
        self._sync_fields()

    def _edit_time(self, which):
        ed = self.ed_a if which == "a" else self.ed_b
        ms = parse_time(ed.text())
        if ms is None:
            self._sync_fields()
            return
        if which == "a":
            self._set_a(ms)
            self._seek_preview(self.a)
        else:
            self._set_b(ms)
            self._seek_preview(self.b)

    def _sync_fields(self):
        if not hasattr(self, "a"):
            return
        self.ed_a.setText(fmt_precise(self.a))
        self.ed_b.setText(fmt_precise(self.b))
        sp = self.cmb_speed.currentData() or 1.0
        out = (self.b - self.a) / sp
        self.lbl_dur.setText(t("selected_duration", d=fmt_time(self.b - self.a)) +
                             ("" if sp == 1.0 else "  →  " + fmt_time(out)))
        self._update_mode()

    # ---------------------------------------------------------------- görüntü
    def _set_crop_ratio(self, v):
        for btn, (_, val) in zip(self.crop_group.buttons(), CROP_RATIOS):
            if val == v:
                btn.setChecked(True)
        if v is None:
            self.preview.set_crop_mode(False)
            self.crop_norm = None
        else:
            if self._frame.isNull():
                return
            self.preview.set_crop_mode(True, None if v == "free" else v)
            self._on_crop_changed(self.preview.crop)
        self._update_mode()

    def _on_crop_changed(self, r):
        w, h = self.preview._img_size()
        if w <= 1 or h <= 1:
            return
        self.crop_norm = (r.left() / w, r.top() / h, r.right() / w, r.bottom() / h)
        self._update_mode()
        if self._wm_on():
            self._wm_timer.start()

    def _rotate(self, d):
        self.rotation = (self.rotation + d) % 360
        self.lbl_rot.setText(f"{self.rotation}°")
        self.crop_norm = None
        self._show_frame()
        self._update_mode()

    def _toggle_flip(self):
        self.flip = not self.flip
        if self.crop_norm:
            x0, y0, x1, y1 = self.crop_norm
            self.crop_norm = (1 - x1, y0, 1 - x0, y1)
        self._show_frame()
        self._update_mode()

    # ---------------------------------------------------------------- mod
    def _fmt(self):
        key = self.cmb_fmt.currentData()
        for k, label, ext, has_v in FORMATS:
            if k == key:
                return k, ext, has_v
        return "mp4", ".mp4", True

    def _stretch(self):
        return self.is_video and hasattr(self, "chk_stretch") and self.chk_stretch.isChecked()

    def _needs_encode(self):
        k, ext, has_v = self._fmt()
        if self.is_video:
            if k in ("gif", "mp4_hevc", "webm") or not has_v:
                return True
            if self.crop_norm is not None or self.rotation or self.flip or (self.cmb_scale.currentData() or 0)                     or self._stretch():
                return True
        else:
            if ext != self.item.ext:
                return True
        if (self.cmb_speed.currentData() or 1.0) != 1.0 or self.sl_vol.value() != 100 or self.chk_fade.isChecked() \
                or self.chk_norm.isChecked() or self._sub_choice()[0] == "burn" or self._wm_on():
            return True
        return False

    def _update_mode(self):
        if not hasattr(self, "chk_fast"):
            return
        need = self._needs_encode()
        k, ext, has_v = self._fmt()
        self.chk_fast.setEnabled(not need)
        if need:
            self.lbl_mode.setText(t("mode_encode"))
        elif self.chk_fast.isChecked():
            self.lbl_mode.setText(t("mode_copy"))
        else:
            self.lbl_mode.setText(t("mode_encode"))
        self.cmb_q.setEnabled(need or not self.chk_fast.isChecked())
        if hasattr(self, "a"):
            self._refresh_out_default()

    def _format_changed(self):
        self._refresh_out_default(force=True)
        self._update_mode()

    def _refresh_out_default(self, force=False):
        if self.out_path and not force and not getattr(self, "_auto_out", True):
            return
        k, ext, has_v = self._fmt()
        if k == "mkv" and self.item.ext != ".mkv":
            ext = ".mkv"
        if hasattr(self, "chk_fast") and not self._needs_encode() and self.chk_fast.isChecked()                 and has_v == self.is_video:
            # Kayıpsız kesimde kaynak kapsayıcıyı koru (codec uyumsuzluğunu önler)
            ext = self.item.ext
        base = os.path.join(os.path.dirname(self.item.path), self.item.title + "_" + t("cut_suffix"))
        path = base + ext
        n = 2
        while os.path.exists(path):
            path = f"{base}_{n}{ext}"
            n += 1
        self.out_path = path
        self._auto_out = True
        self._show_out()

    def _show_out(self):
        folder = os.path.basename(os.path.dirname(self.out_path)) or os.path.dirname(self.out_path)
        self.lbl_out.setText(f"{t('save_to')}: {folder} › {os.path.basename(self.out_path)}")
        self.lbl_out.setToolTip(self.out_path)

    # ---------------------------------------------------------------- dışa aktar
    def build_args(self):
        k, ext, has_v = self._fmt()
        a, b = self.a, self.b
        dur = (b - a) / 1000.0
        speed = self.cmb_speed.currentData() or 1.0
        q = self.cmb_q.currentData() or 22
        args = ["-y", "-hide_banner", "-nostdin", "-progress", "pipe:1", "-nostats",
                "-ss", f"{a / 1000.0:.3f}", "-t", f"{dur:.3f}", "-i", self.item.path]
        copy_mode = not self._needs_encode() and self.chk_fast.isChecked()
        out_ext = os.path.splitext(self.out_path)[1].lower()
        sub_mode, sub_src, sub_si = self._sub_choice()
        soft_args = []
        n_inputs = 1
        if sub_mode == "soft" and out_ext in (".mp4", ".m4v", ".mov", ".mkv", ".webm"):
            scodec = {".mkv": "srt", ".webm": "webvtt"}.get(out_ext, "mov_text")
            if sub_src:  # dış dosya: kesim başlangıcı kadar öne kaydır
                args += ["-itsoffset", f"{-a / 1000.0:.3f}", "-i", sub_src]
                n_inputs += 1
                soft_args = ["-map", "1:0", "-c:s", scodec, "-metadata:s:s:0", "title=" + os.path.basename(sub_src)]
            elif sub_si is not None:
                soft_args = ["-map", f"0:s:{sub_si}", "-c:s", scodec]
        if copy_mode:
            args += ["-map", "0:v?", "-map", "0:a?"]
            if out_ext in (".mkv", ".webm"):
                args += ["-map", "0:s?"]
            if self.chk_mute.isChecked():
                args += ["-an"]
            args += ["-c", "copy", "-avoid_negative_ts", "make_zero", "-map_metadata", "0"]
            if soft_args:
                args += soft_args
            if out_ext in (".mp4", ".m4v", ".mov"):
                args += ["-movflags", "+faststart"]
            args.append(self.out_path)
            return args, dur / speed

        vf, af = [], []
        if self.is_video and has_v:
            if self.rotation == 90:
                vf.append("transpose=1")
            elif self.rotation == 180:
                vf += ["hflip", "vflip"]
            elif self.rotation == 270:
                vf.append("transpose=2")
            if self.flip:
                vf.append("hflip")
            if self._stretch():
                # Kenarlara yayarak 16:9'a uzat (yükseklik aynı, genişlik ölçeklenir)
                vf.append("scale=trunc(ih*16/9/2)*2:ih,setsar=1")
            if self.crop_norm:
                x0, y0, x1, y1 = self.crop_norm
                fw, fh = max(0.01, x1 - x0), max(0.01, y1 - y0)
                vf.append(f"crop=trunc(iw*{fw:.5f}/2)*2:trunc(ih*{fh:.5f}/2)*2:trunc(iw*{x0:.5f}):trunc(ih*{y0:.5f})")
            if sub_mode == "burn":
                vf += self._burn_filters(a, sub_src, sub_si)
            sh = self.cmb_scale.currentData() or 0
            if k == "gif":
                gif_h = sh or 480
                vf.append(f"fps=15,scale=-2:'min({gif_h},ih)':flags=lanczos")
            elif sh:
                vf.append(f"scale=-2:'min({sh},ih)':flags=lanczos")
            if speed != 1.0:
                vf.append(f"setpts=PTS/{speed}")
            if self.chk_fade.isChecked() and k != "gif":
                od = (b - a) / 1000.0 / speed
                fd = min(1.0, od / 4)
                vf += [f"fade=t=in:st=0:d={fd:.2f}", f"fade=t=out:st={max(0, od - fd):.2f}:d={fd:.2f}"]
            if k != "gif":
                vf.append("format=yuv420p")
        audio = not (self.chk_mute.isChecked() and self.is_video) and k != "gif"
        if audio:
            if speed != 1.0:
                af += atempo_chain(speed)
            if self.sl_vol.value() != 100:
                af.append(f"volume={self.sl_vol.value() / 100:.2f}")
            if self.chk_norm.isChecked():
                af.append("loudnorm=I=-16:TP=-1.5:LRA=11")
            if self.chk_fade.isChecked():
                od = (b - a) / 1000.0 / speed
                fd = min(1.0, od / 4)
                af += [f"afade=t=in:st=0:d={fd:.2f}", f"afade=t=out:st={max(0, od - fd):.2f}:d={fd:.2f}"]

        ov_idx = None
        if self._wm_on() and has_v and not copy_mode:
            from . import watermark as wm
            rw, rh = self._final_region()
            ow = 1920
            oh = max(2, int(round(ow * rh / rw)))
            from .config import CACHE_DIR
            self._wm_tmp = os.path.join(CACHE_DIR, f"watermark_{os.getpid()}.png")
            wm.render(ow, oh).save(self._wm_tmp, "PNG")
            args += ["-loop", "1", "-i", self._wm_tmp]
            ov_idx = n_inputs
            n_inputs += 1
            if vf and vf[-1] == "format=yuv420p":
                vf = vf[:-1]

        def with_overlay(chain):
            if ov_idx is None:
                return f"[0:v]{chain or 'null'}"
            return (f"[0:v]{chain or 'null'}[wb];[{ov_idx}:v][wb]scale2ref[wo][wb2];"
                    f"[wb2][wo]overlay=0:0:shortest=1")

        if k == "gif":
            chain = ",".join(vf) if vf else "fps=15"
            args += ["-filter_complex", f"{with_overlay(chain)},split[s0][s1];[s0]palettegen=stats_mode=diff[p];"
                                        f"[s1][p]paletteuse=dither=bayer:bayer_scale=4", "-an", "-loop", "0"]
        else:
            if has_v and self.is_video and ov_idx is not None:
                args += ["-filter_complex", with_overlay(",".join(vf)) + ",format=yuv420p[vout]", "-map", "[vout]"]
            elif has_v and self.is_video:
                args += ["-map", "0:v:0"]
                if vf:
                    args += ["-vf", ",".join(vf)]
            if has_v and self.is_video:
                if k == "mp4_hevc":
                    args += ["-c:v", "libx265", "-preset", "medium", "-crf", str(q + 4), "-tag:v", "hvc1"]
                elif k == "webm":
                    args += ["-c:v", "libvpx-vp9", "-crf", str(q + 12), "-b:v", "0", "-row-mt", "1",
                             "-deadline", "good", "-cpu-used", "4"]
                else:
                    args += ["-c:v", "libx264", "-preset", "medium", "-crf", str(q)]
            else:
                args += ["-vn"]
            if audio:
                args += ["-map", "0:a?"]
                if af:
                    args += ["-af", ",".join(af)]
                if k == "webm" or k == "opus":
                    args += ["-c:a", "libopus", "-b:a", "160k"]
                elif k == "mp3":
                    args += ["-c:a", "libmp3lame", "-q:a", "2" if q <= 22 else "4"]
                elif k == "flac":
                    args += ["-c:a", "flac"]
                elif k == "wav":
                    args += ["-c:a", "pcm_s16le"]
                else:
                    args += ["-c:a", "aac", "-b:a", "192k" if q <= 22 else "128k"]
            else:
                args += ["-an"]
            if soft_args and k not in ("mp3", "m4a", "opus", "flac", "wav"):
                args += soft_args
            else:
                args += ["-sn"]
            args += ["-map_metadata", "0"]
            if out_ext in (".mp4", ".m4a", ".mov"):
                args += ["-movflags", "+faststart"]
        args.append(self.out_path)
        return args, dur / speed

    # ---------------------------------------------------------------- yazı / filigran
    def _build_watermark(self, lay):
        from . import watermark as wm
        from PyQt6.QtWidgets import QPlainTextEdit
        self._wm_timer = QTimer(self)
        self._wm_timer.setSingleShot(True)
        self._wm_timer.setInterval(120)
        self._wm_timer.timeout.connect(lambda: (self._show_frame(), self._update_mode()))
        lay.addWidget(Divider())
        lay.addWidget(self._title(t("wm_title")))

        def setp(key, val):
            prefs.set(key, val)
            self._wm_timer.start()

        def slider(lo, hi, key, fmt):
            row = QHBoxLayout()
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(lo, hi)
            sl.setValue(int(wm.get(key)))
            lb = QLabel(fmt(sl.value()))
            lb.setFixedWidth(44)
            sl.valueChanged.connect(lambda v: (lb.setText(fmt(v)), setp(key, v)))
            row.addWidget(sl, 1)
            row.addWidget(lb)
            return row

        def pos_combo(key):
            c = QComboBox()
            for p in wm.POSITIONS:
                c.addItem(t("pos_" + p), p)
            c.setCurrentIndex(wm.POSITIONS.index(wm.get(key)) if wm.get(key) in wm.POSITIONS else 8)
            c.currentIndexChanged.connect(lambda i: setp(key, c.itemData(i)))
            return c

        def labeled(text, w):
            row = QHBoxLayout()
            lb = QLabel(text)
            lb.setFixedWidth(78)
            row.addWidget(lb)
            if isinstance(w, QHBoxLayout):
                row.addLayout(w, 1)
            else:
                row.addWidget(w, 1)
            return row

        # --- yazı
        chk = QCheckBox(t("wm_add_text"))
        chk.setChecked(bool(wm.get("wm_text_on")))
        chk.toggled.connect(lambda v: setp("wm_text_on", v))
        lay.addWidget(chk)
        self.ed_wm = QPlainTextEdit(wm.get("wm_text"))
        self.ed_wm.setPlaceholderText(t("wm_text_ph"))
        self.ed_wm.setFixedHeight(54)
        self.ed_wm.textChanged.connect(lambda: setp("wm_text", self.ed_wm.toPlainText()))
        lay.addWidget(self.ed_wm)
        fc = QComboBox()
        for f in wm.FONTS:
            fc.addItem(f, f)
        if wm.get("wm_font") in wm.FONTS:
            fc.setCurrentIndex(wm.FONTS.index(wm.get("wm_font")))
        fc.currentIndexChanged.connect(lambda i: setp("wm_font", fc.itemData(i)))
        lay.addLayout(labeled(t("sub_font"), fc))
        lay.addLayout(labeled(t("wm_size"), slider(2, 25, "wm_size", lambda v: f"%{v}")))
        self.btn_wm_color = QPushButton()
        self.btn_wm_color.setFixedHeight(26)
        self.btn_wm_color.setCursor(Qt.CursorShape.PointingHandCursor)

        def paint_color():
            self.btn_wm_color.setStyleSheet(f"background: {wm.get('wm_color')}; border: 1px solid #777; border-radius: 6px;")

        def pick():
            from PyQt6.QtWidgets import QColorDialog
            from PyQt6.QtGui import QColor as _QC
            c = QColorDialog.getColor(_QC(wm.get("wm_color")), self, t("pick_color"))
            if c.isValid():
                setp("wm_color", c.name())
                paint_color()
        paint_color()
        self.btn_wm_color.clicked.connect(pick)
        lay.addLayout(labeled(t("sub_color"), self.btn_wm_color))
        lay.addLayout(labeled(t("wm_position"), pos_combo("wm_pos")))
        lay.addLayout(labeled(t("wm_opacity"), slider(10, 100, "wm_opacity", lambda v: f"%{v}")))
        row = QHBoxLayout()
        c1 = QCheckBox(t("wm_shadow"))
        c1.setChecked(bool(wm.get("wm_shadow")))
        c1.toggled.connect(lambda v: setp("wm_shadow", v))
        c2 = QCheckBox(t("wm_box"))
        c2.setChecked(bool(wm.get("wm_box")))
        c2.toggled.connect(lambda v: setp("wm_box", v))
        row.addWidget(c1)
        row.addWidget(c2)
        row.addStretch(1)
        lay.addLayout(row)

        # --- logo
        chk2 = QCheckBox(t("wm_add_logo"))
        chk2.setChecked(bool(wm.get("wm_logo_on")))
        chk2.toggled.connect(lambda v: setp("wm_logo_on", v))
        lay.addWidget(chk2)
        lrow = QHBoxLayout()
        self.lbl_logo = QLabel(os.path.basename(wm.get("wm_logo")) or t("none"))
        self.lbl_logo.setObjectName("Secondary")
        bl = QPushButton(t("choose"))
        bl.setObjectName("Pill")
        bl.setFixedHeight(30)

        def choose_logo():
            p, _ = QFileDialog.getOpenFileName(self, t("wm_add_logo"), os.path.dirname(wm.get("wm_logo") or self.item.path),
                                               t("images_filter") + " (*.png *.jpg *.jpeg *.webp *.bmp *.svg)")
            if p:
                self.lbl_logo.setText(os.path.basename(p))
                chk2.setChecked(True)
                setp("wm_logo", p)
        bl.clicked.connect(choose_logo)
        lrow.addWidget(self.lbl_logo, 1)
        lrow.addWidget(bl)
        lay.addLayout(lrow)
        lay.addLayout(labeled(t("wm_size"), slider(3, 60, "wm_logo_size", lambda v: f"%{v}")))
        lay.addLayout(labeled(t("wm_position"), pos_combo("wm_logo_pos")))
        lay.addLayout(labeled(t("wm_opacity"), slider(10, 100, "wm_logo_opacity", lambda v: f"%{v}")))

    def _wm_on(self):
        from . import watermark as wm
        return self.is_video and wm.active()

    def _final_region(self):
        """Kırpma/döndürme/uzatma sonrası son karenin (genişlik, yükseklik) oranı için ölçüler."""
        if not self._frame.isNull():
            w, h = self._frame.width(), self._frame.height()
        else:
            w, h = (self.item.width or 1920), (self.item.height or 1080)
        if self.rotation in (90, 270):
            w, h = h, w
        if self._stretch():
            w = h * 16 / 9
        if self.crop_norm:
            x0, y0, x1, y1 = self.crop_norm
            w, h = w * (x1 - x0), h * (y1 - y0)
        return max(1.0, w), max(1.0, h)

    def _composite_wm(self, img):
        from . import watermark as wm
        from PyQt6.QtGui import QPainter as _QP
        out = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        W, H = out.width(), out.height()
        if self.crop_norm:
            x0, y0, x1, y1 = self.crop_norm
            rect = QRectF(x0 * W, y0 * H, (x1 - x0) * W, (y1 - y0) * H)
        else:
            rect = QRectF(0, 0, W, H)
        ov = wm.render(int(rect.width()), int(rect.height()))
        p = _QP(out)
        p.drawImage(rect.topLeft(), ov)
        p.end()
        return out

    # ---------------------------------------------------------------- altyazı
    def _fill_sub_streams(self, err):
        """ffmpeg çıktısından gömülü (metin tabanlı) altyazı parçalarını listeye ekler."""
        import re as _re
        idx = 0
        insert_at = 1
        for line in err.splitlines():
            m = _re.search(r"Stream #\d+:\d+(?:\[[^]]*\])?(?:\((\w+)\))?: Subtitle: (\w+)", line)
            if not m:
                continue
            lang, codec = m.group(1) or "", m.group(2)
            text_based = codec in ("subrip", "srt", "ass", "ssa", "mov_text", "webvtt", "text")
            label = t("sub_embedded", n=idx + 1) + (f" ({lang})" if lang else "") + f" — {codec}"
            if text_based:
                self.cmb_sub.insertItem(insert_at, label, ("embedded", idx))
                insert_at += 1
            idx += 1

    def _sub_changed(self, i):
        data = self.cmb_sub.itemData(i)
        if data and data[0] == "pick":
            p, _ = QFileDialog.getOpenFileName(self, t("sub_from_file"), os.path.dirname(self.item.path),
                                               f"{t('subtitle_files')} (*.srt *.ass *.ssa *.vtt)")
            self.cmb_sub.blockSignals(True)
            if p:
                self.cmb_sub.insertItem(1, os.path.basename(p), ("file", p))
                self.cmb_sub.setCurrentIndex(1)
            else:
                self.cmb_sub.setCurrentIndex(0)
            self.cmb_sub.blockSignals(False)
        self._update_mode()

    def _sub_choice(self):
        """(mod, dış dosya yolu, gömülü parça sırası) — mod: None | burn | soft"""
        if not self.is_video or not hasattr(self, "cmb_sub"):
            return None, None, None
        data = self.cmb_sub.currentData()
        if not data or data[0] == "pick":
            return None, None, None
        mode = self.cmb_sub_mode.currentData()
        if data[0] == "file":
            return mode, data[1], None
        return mode, None, data[1]

    @staticmethod
    def _ff_path(p):
        """Yolu ffmpeg filtre seçeneği olarak yazılabilir hâle getirir (tırnaksız kullanılır).
        ffmpeg iki kez çözer: önce filtre grafiği ( \\ ' [ ] , ; ), sonra seçenek ( \\ ' : ). Bu yüzden iki kat
        kaçış gerekir; yoksa adında ' [ ] , ; olan dosyalarda (ör. "Yiğit's video.srt") altyazı gömme bozulur."""
        p = os.path.abspath(p).replace("\\", "/")
        p = re.sub(r"([\\':])", r"\\\1", p)          # seçenek düzeyi
        return re.sub(r"([\\'\[\],;])", r"\\\1", p)  # filtre grafiği düzeyi

    def _burn_filters(self, a_ms, src, si):
        """Altyazıyı görüntüye yakar; kesim başlangıcına göre zamanlamayı korur. Görünüm, oynatıcıdaki
        altyazı ayarlarından (yazı tipi, boyut, renk, arka plan) alınır."""
        from .config import prefs
        font = prefs.get("sub_font") or "Segoe UI Semibold"
        size = max(8, int(20 * int(prefs.get("sub_size", 100)) / 100))
        col = (prefs.get("sub_color") or "#ffffff").lstrip("#")
        prim = f"&H00{col[4:6]}{col[2:4]}{col[0:2]}"
        bg = int(prefs.get("sub_bg", 0))
        outline = int(prefs.get("sub_outline", 4))
        if bg > 0:
            style = (f"FontName={font},FontSize={size},PrimaryColour={prim},BorderStyle=3,Outline=1,Shadow=0,"
                     f"OutlineColour=&H{255 - bg:02X}000000,MarginV={20 + int(prefs.get('sub_margin', 24)) // 2}")
        else:
            style = (f"FontName={font},FontSize={size},PrimaryColour={prim},BorderStyle=1,"
                     f"Outline={max(0, outline // 2)},Shadow=1,OutlineColour=&H00000000,"
                     f"MarginV={20 + int(prefs.get('sub_margin', 24)) // 2}")
        if src:
            target = f"filename={self._ff_path(src)}"
        else:
            target = f"filename={self._ff_path(self.item.path)}:si={si}"
        off = a_ms / 1000.0
        return [f"setpts=PTS+{off:.3f}/TB", f"subtitles={target}:force_style='{style}'", "setpts=PTS-STARTPTS"]

    # ---------------------------------------------------------------- oynatarak önizleme
    def toggle_preview(self):
        if self._ptimer.isActive():
            self._pause_preview()
        else:
            self._start_preview()

    def _start_preview(self):
        if not hasattr(self, "a"):
            return
        from .vlc_engine import VLCEngine
        if not VLCEngine.available():
            return
        if self._peng is None:
            self._peng = VLCEngine(int(self.video_box.winId()), self)
            vol = getattr(self.parent(), "engine", None)
            self._peng.set_volume(vol.volume() if vol else 100)
        start = self._head if self.a <= self._head < self.b - 300 else self.a
        self.pstack.setCurrentIndex(1)
        self._peng.load(self.item.path, [], start)
        self._peng.play()
        sp = self.cmb_speed.currentData() or 1.0
        if sp != 1.0:
            QTimer.singleShot(300, lambda: self._peng and self._peng.set_rate(sp))
        self._ptimer.start()
        self.b_play.set_icon_name("pause")

    def _pause_preview(self, at=None):
        self._ptimer.stop()
        if self._peng is not None:
            ms = self._peng.get_time() if at is None else at
            self._peng.stop()
        else:
            ms = self._head
        self.b_play.set_icon_name("play")
        self.pstack.setCurrentIndex(0)
        self._seek_preview(max(0, ms))

    def _preview_tick(self):
        if self._peng is None:
            return
        ms = self._peng.get_time()
        if ms <= 0:
            return
        self._head = ms
        self.lbl_head.setText(fmt_precise(ms))
        if hasattr(self, "timeline"):
            self.timeline.set_head(ms)
        if ms >= self.b or self._peng.state_ended():
            self._pause_preview(at=self.b)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not isinstance(self.focusWidget(), QLineEdit):
            self.toggle_preview()
            return
        super().keyPressEvent(e)

    def _save_frame(self):
        """Şu anki kareyi videonun tam çözünürlüğünde PNG olarak kaydeder."""
        ms = self._head
        base = os.path.splitext(self.item.path)[0]
        default = f"{base}_{fmt_time(ms).replace(':', '-')}.png"
        p, _ = QFileDialog.getSaveFileName(self, t("save_frame"), default, "PNG (*.png);;JPEG (*.jpg)")
        if not p:
            return

        def work():
            rc, out, err = thumbs.run_ffmpeg(["-y", "-ss", f"{max(0, ms / 1000.0 - 2):.3f}", "-i", self.item.path,
                                              "-ss", f"{min(2.0, ms / 1000.0):.3f}", "-frames:v", "1", p], timeout=30)
            if not os.path.exists(p):
                raise RuntimeError(err[-300:])
            return p
        thumbs.run_async(work, on_done=lambda path: self.exported.emit(path),
                         on_fail=lambda m: QMessageBox.warning(self, t("save_frame"), m))

    def _overwrite_possible(self):
        k, ext, has_v = self._fmt()
        if not self._needs_encode() and self.chk_fast.isChecked():
            return True
        return ext == self.item.ext or (k == "mkv" and self.item.ext == ".mkv")

    def _save_as(self):
        if not hasattr(self, "a"):
            return
        self._refresh_out_default(force=True)
        k, ext, _ = self._fmt()
        start_ext = os.path.splitext(self.out_path)[1]
        p, _ = QFileDialog.getSaveFileName(self, t("save_as"), self.out_path, f"*{start_ext}")
        if not p:
            return
        if not os.path.splitext(p)[1]:
            p += start_ext
        if os.path.normcase(os.path.abspath(p)) == os.path.normcase(self.item.path):
            self._save_overwrite()
            return
        self.out_path = p
        self._overwrite_target = None
        self._export()

    def _save_overwrite(self):
        if not hasattr(self, "a"):
            return
        if not self._overwrite_possible():
            QMessageBox.information(self, t("save_overwrite"), t("overwrite_format_mismatch"))
            return
        r = QMessageBox.question(self, t("save_overwrite"), t("confirm_overwrite", name=self.item.name))
        if r != QMessageBox.StandardButton.Yes:
            return
        base, ext = os.path.splitext(self.item.path)
        self.out_path = base + ".gamma-tmp" + ext
        self._overwrite_target = self.item.path
        self._export()

    def _export(self):
        if not hasattr(self, "a"):
            return
        if os.path.normcase(os.path.abspath(self.out_path)) == os.path.normcase(self.item.path):
            QMessageBox.warning(self, t("export"), t("same_file_error"))
            return
        args, out_dur = self.build_args()
        self._expected_ms = max(1, int(out_dur * 1000))
        self.proc = QProcess(self)
        self.proc.setProgram(thumbs.FFMPEG)
        self.proc.setArguments(args)
        self.proc.readyReadStandardOutput.connect(self._on_progress)
        self.proc.finished.connect(self._on_finished)
        self._stderr = b""
        self.proc.readyReadStandardError.connect(self._on_stderr)
        self.progress.setValue(0)
        self.progress.show()
        self.b_export.setEnabled(False)
        self.b_saveas.setEnabled(False)
        self.b_cancel.setText(t("cancel"))
        self.proc.start()

    def _on_stderr(self):
        self._stderr = (self._stderr + bytes(self.proc.readAllStandardError()))[-6000:]

    def _on_progress(self):
        data = bytes(self.proc.readAllStandardOutput()).decode(errors="ignore")
        for m in re.finditer(r"out_time_(?:us|ms)=(\d+)", data):
            us = int(m.group(1))
            self.progress.setValue(min(1000, int(us / 1000 / self._expected_ms * 1000)))

    def _on_finished(self, code, status):
        tmp = getattr(self, "_wm_tmp", None)
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass
            self._wm_tmp = None
        self.proc = None
        self.b_export.setEnabled(True)
        self.b_saveas.setEnabled(True)
        self.b_cancel.setText(t("close"))
        if getattr(self, "_cancelled", False):
            self._cancelled = False
            self._overwrite_target = None
            self.progress.hide()
            try:
                os.remove(self.out_path)
            except OSError:
                pass
            return
        if code == 0 and os.path.exists(self.out_path) and getattr(self, "_overwrite_target", None):
            target, tmp = self._overwrite_target, self.out_path
            self._overwrite_target = None
            self.release_file.emit(target)
            import time
            err = None
            for _ in range(20):
                try:
                    os.replace(tmp, target)
                    err = None
                    break
                except OSError as e:
                    err = e
                    QApplication.processEvents()
                    time.sleep(0.15)
            if err is not None:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                self.progress.hide()
                QMessageBox.warning(self, t("save_overwrite"), t("save_failed") + "\n" + str(err))
                return
            self.progress.setValue(1000)
            self.out_path = target
            self.exported.emit(target)
            QMessageBox.information(self, t("save_overwrite"), t("overwrite_done"))
            self.accept()
            return
        if code == 0 and os.path.exists(self.out_path):
            self.progress.setValue(1000)
            self.exported.emit(self.out_path)
            box = QMessageBox(self)
            box.setWindowTitle(t("export"))
            box.setText(t("export_done") + "\n" + self.out_path)
            bo = box.addButton(t("show_in_folder"), QMessageBox.ButtonRole.ActionRole)
            box.addButton(t("ok"), QMessageBox.ButtonRole.AcceptRole)
            box.exec()
            if box.clickedButton() is bo:
                import subprocess
                subprocess.Popen(["explorer", "/select,", os.path.normpath(self.out_path)])
            self._refresh_out_default(force=True)
        else:
            self.progress.hide()
            err = self._stderr.decode(errors="ignore").strip().splitlines()[-6:]
            QMessageBox.warning(self, t("export"), t("export_failed") + "\n\n" + "\n".join(err))

    def _cancel_or_close(self):
        if self.proc is not None:
            self._cancelled = True
            self.proc.kill()
        else:
            self.reject()

    def done(self, r):
        self._ptimer.stop()
        if self._peng is not None:
            self._peng.release()
            self._peng = None
        if self.proc is not None:
            self._cancelled = True
            self.proc.kill()
            self.proc.waitForFinished(2000)
        self.grabber.stop()
        super().done(r)
