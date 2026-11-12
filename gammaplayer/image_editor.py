"""Görsel düzenleyici paneli (sağ tarafta açılır, önizleme ana alanda canlı görünür)."""
import copy
import os

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRectF
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton, QScrollArea,
                             QSpinBox, QCheckBox, QFileDialog, QMessageBox, QGridLayout, QComboBox, QButtonGroup)

from . import image_io, thumbs
from .i18n import t
from .widgets import IconButton, Chip, Pill, Divider

DEFAULT_STATE = dict(rot=0, flip_h=False, flip_v=False, crop=None, brightness=0, contrast=0, saturation=0,
                     sharpness=0, warmth=0, blur=0, vignette=0, filter="none", resize=None, bg=None)

FILTERS = ["none", "bw", "sepia", "vivid", "warm", "cool", "vintage", "dramatic", "invert", "fade"]
RATIOS = [("free", None), ("original", "orig"), ("1:1", 1.0), ("4:3", 4 / 3), ("3:2", 3 / 2), ("16:9", 16 / 9),
          ("9:16", 9 / 16), ("4:5", 4 / 5), ("21:9", 21 / 9)]


def render(img: Image.Image, st: dict, skip_crop=False, final=False) -> Image.Image:
    """Düzenleme adımlarını sırayla uygular."""
    rot = st["rot"] % 360
    if rot == 90:
        img = img.transpose(Image.Transpose.ROTATE_270)
    elif rot == 180:
        img = img.transpose(Image.Transpose.ROTATE_180)
    elif rot == 270:
        img = img.transpose(Image.Transpose.ROTATE_90)
    if st["flip_h"]:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if st["flip_v"]:
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    if st["crop"] and not skip_crop:
        x0, y0, x1, y1 = st["crop"]
        w, h = img.size
        box = (int(round(x0 * w)), int(round(y0 * h)), int(round(x1 * w)), int(round(y1 * h)))
        if box[2] - box[0] >= 2 and box[3] - box[1] >= 2:
            img = img.crop(box)

    if st.get("bg"):
        from .bgremove import remove_background
        b = st["bg"]
        img = remove_background(img, b.get("color"), b.get("tol", 20), b.get("edge", True), b.get("feather", 6))

    alpha = None
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        alpha = img.getchannel("A")
    rgb = img.convert("RGB")

    if st["brightness"]:
        rgb = ImageEnhance.Brightness(rgb).enhance(1 + st["brightness"] / 100.0)
    if st["contrast"]:
        rgb = ImageEnhance.Contrast(rgb).enhance(1 + st["contrast"] / 100.0)
    if st["saturation"]:
        rgb = ImageEnhance.Color(rgb).enhance(1 + st["saturation"] / 100.0)
    if st["warmth"]:
        wv = st["warmth"] / 100.0
        r, g, b = rgb.split()
        r = r.point(lambda v: min(255, int(v * (1 + 0.18 * wv))))
        b = b.point(lambda v: min(255, int(v * (1 - 0.18 * wv))))
        rgb = Image.merge("RGB", (r, g, b))
    if st["sharpness"]:
        rgb = ImageEnhance.Sharpness(rgb).enhance(1 + st["sharpness"] / 40.0)
    if st["blur"]:
        radius = st["blur"] / 100.0 * max(rgb.size) / 120.0
        if radius > 0.2:
            rgb = rgb.filter(ImageFilter.GaussianBlur(radius))
    rgb = _apply_filter(rgb, st["filter"])
    if st["vignette"]:
        rgb = _vignette(rgb, st["vignette"] / 100.0)

    if alpha is not None:
        rgb = rgb.convert("RGBA")
        rgb.putalpha(alpha)
    if final and st["resize"]:
        tw, th = st["resize"]
        if tw > 0 and th > 0 and (tw, th) != rgb.size:
            rgb = rgb.resize((int(tw), int(th)), Image.Resampling.LANCZOS)
    return rgb


def _apply_filter(rgb, name):
    if name == "none":
        return rgb
    if name == "bw":
        return ImageOps.grayscale(rgb).convert("RGB")
    if name == "sepia":
        g = ImageOps.grayscale(rgb)
        return ImageOps.colorize(g, "#2b1d0e", "#f3e3c3", mid="#a67c52")
    if name == "vivid":
        rgb = ImageEnhance.Color(rgb).enhance(1.45)
        return ImageEnhance.Contrast(rgb).enhance(1.12)
    if name == "warm":
        r, g, b = rgb.split()
        return Image.merge("RGB", (r.point(lambda v: min(255, int(v * 1.1 + 8))), g, b.point(lambda v: int(v * 0.88))))
    if name == "cool":
        r, g, b = rgb.split()
        return Image.merge("RGB", (r.point(lambda v: int(v * 0.9)), g, b.point(lambda v: min(255, int(v * 1.1 + 8)))))
    if name == "vintage":
        rgb = ImageEnhance.Color(rgb).enhance(0.65)
        rgb = ImageEnhance.Contrast(rgb).enhance(0.88)
        r, g, b = rgb.split()
        rgb = Image.merge("RGB", (r.point(lambda v: min(255, int(v * 1.06 + 14))), g.point(lambda v: min(255, v + 6)),
                                  b.point(lambda v: int(v * 0.85 + 10))))
        return _vignette(rgb, 0.35)
    if name == "dramatic":
        rgb = ImageEnhance.Contrast(rgb).enhance(1.4)
        rgb = ImageEnhance.Color(rgb).enhance(0.75)
        return _vignette(rgb, 0.4)
    if name == "invert":
        return ImageOps.invert(rgb)
    if name == "fade":
        rgb = ImageEnhance.Contrast(rgb).enhance(0.75)
        return rgb.point(lambda v: int(30 + v * 0.85))
    return rgb


def _vignette(rgb, strength):
    w, h = rgb.size
    small = Image.radial_gradient("L").resize((w, h), Image.Resampling.BILINEAR)
    mask = small.point(lambda v: int(255 - min(255, v * strength * 1.2)))
    black = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(rgb, black, mask)


class _Slider(QWidget):
    def __init__(self, label, lo, hi, on_change, on_press):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(2)
        top = QHBoxLayout()
        self.lbl = QLabel(label)
        self.val = QLabel("0")
        self.val.setObjectName("Secondary")
        top.addWidget(self.lbl, 1)
        top.addWidget(self.val)
        lay.addLayout(top)
        self.s = QSlider(Qt.Orientation.Horizontal)
        self.s.setRange(lo, hi)
        self.s.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.s.valueChanged.connect(lambda v: (self.val.setText(f"{v:+d}" if lo < 0 else str(v)), on_change(v)))
        self.s.sliderPressed.connect(on_press)
        lay.addWidget(self.s)

    def set(self, v):
        self.s.blockSignals(True)
        self.s.setValue(int(v))
        self.s.blockSignals(False)
        self.val.setText(f"{int(v):+d}" if self.s.minimum() < 0 else str(int(v)))

    def mouseDoubleClickEvent(self, e):
        self.s.setValue(0)


class ImageEditPanel(QWidget):
    closed = pyqtSignal()
    saved = pyqtSignal(str)

    def __init__(self, win, item, viewer):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.win = win
        self.item = item
        self.viewer = viewer
        self.state = copy.deepcopy(DEFAULT_STATE)
        self.history = []
        self.redo_stack = []
        self.full = None
        self.proxy = None
        self.cropping = False
        self._saving = False
        self._build()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(25)
        self._timer.timeout.connect(self._render_preview)
        self._set_enabled(False)
        thumbs.run_async(image_io.open_pil, item.path, on_done=self._loaded, on_fail=self._load_failed)

    # ---------------------------------------------------------------- arayüz
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 4, 8, 8)
        outer.setSpacing(6)
        head = QHBoxLayout()
        title = QLabel(t("edit_image_title"))
        title.setObjectName("SectionTitle")
        head.addWidget(title, 1)
        self.btn_undo = IconButton("undo", t("undo") + " (Ctrl+Z)", 36, 20)
        self.btn_undo.clicked.connect(self.undo)
        self.btn_redo = IconButton("redo", t("redo") + " (Ctrl+Y)", 36, 20)
        self.btn_redo.clicked.connect(self.redo)
        btn_close = IconButton("close", t("close"), 36, 20)
        btn_close.clicked.connect(self.request_close)
        for b in (self.btn_undo, self.btn_redo, btn_close):
            head.addWidget(b)
        outer.addLayout(head)
        self.lbl_size = QLabel("")
        self.lbl_size.setObjectName("Secondary")
        outer.addWidget(self.lbl_size)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        self.body = body
        lay = QVBoxLayout(body)
        lay.setContentsMargins(4, 4, 10, 4)
        lay.setSpacing(8)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # Kırp & döndür
        lay.addWidget(self._title(t("crop_rotate")))
        row = QHBoxLayout()
        row.setSpacing(4)
        for name, tip, fn in (("rotate_left", t("rotate_left"), lambda: self._rotate(-90)),
                              ("rotate_right", t("rotate_right"), lambda: self._rotate(90)),
                              ("flip_h", t("flip_h"), lambda: self._flip("flip_h")),
                              ("flip_v", t("flip_v"), lambda: self._flip("flip_v"))):
            b = IconButton(name, tip, 40, 22)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        self.btn_crop = Pill("  " + t("crop"), "crop", checkable=True)
        self.btn_crop.clicked.connect(self._toggle_crop)
        row.addWidget(self.btn_crop)
        lay.addLayout(row)

        self.crop_box = QWidget()
        cb = QVBoxLayout(self.crop_box)
        cb.setContentsMargins(0, 0, 0, 0)
        grid = QGridLayout()
        grid.setSpacing(6)
        self.ratio_group = QButtonGroup(self)
        for n, (key, val) in enumerate(RATIOS):
            c = Chip(t("ratio_" + key) if key in ("free", "original") else key)
            self.ratio_group.addButton(c)
            c.clicked.connect(lambda _=False, v=val: self._set_ratio(v))
            if key == "free":
                c.setChecked(True)
            grid.addWidget(c, n // 3, n % 3)
        cb.addLayout(grid)
        crow = QHBoxLayout()
        crow.addStretch(1)
        b_cancel = QPushButton(t("cancel"))
        b_cancel.setObjectName("Flat")
        b_cancel.clicked.connect(lambda: self._end_crop(False))
        b_apply = QPushButton(t("apply"))
        b_apply.setObjectName("Accent")
        b_apply.clicked.connect(lambda: self._end_crop(True))
        crow.addWidget(b_cancel)
        crow.addWidget(b_apply)
        cb.addLayout(crow)
        self.crop_box.hide()
        lay.addWidget(self.crop_box)
        lay.addWidget(Divider())

        # Ayarlar
        lay.addWidget(self._title(t("adjustments")))
        self.sliders = {}
        for key, lo, hi in (("brightness", -100, 100), ("contrast", -100, 100), ("saturation", -100, 100),
                            ("warmth", -100, 100), ("sharpness", -100, 100), ("blur", 0, 100), ("vignette", 0, 100)):
            s = _Slider(t(key), lo, hi, lambda v, k=key: self._set(k, v), self._push)
            self.sliders[key] = s
            lay.addWidget(s)
        lay.addWidget(Divider())

        # Filtreler
        lay.addWidget(self._title(t("filters")))
        fgrid = QGridLayout()
        fgrid.setSpacing(6)
        self.filter_group = QButtonGroup(self)
        self.filter_btns = {}
        for n, f in enumerate(FILTERS):
            c = Chip(t("flt_" + f))
            self.filter_group.addButton(c)
            c.clicked.connect(lambda _=False, f=f: self._set_filter(f))
            self.filter_btns[f] = c
            fgrid.addWidget(c, n // 3, n % 3)
        self.filter_btns["none"].setChecked(True)
        lay.addLayout(fgrid)
        lay.addWidget(Divider())

        # Boyut
        lay.addWidget(self._title(t("bg_remove")))
        self.chk_bg = QCheckBox(t("bg_remove_on"))
        self.chk_bg.toggled.connect(self._bg_toggled)
        lay.addWidget(self.chk_bg)
        brow = QHBoxLayout()
        self.lbl_bgcol = QLabel()
        self.lbl_bgcol.setFixedSize(26, 26)
        self.lbl_bgcol.setToolTip(t("bg_color"))
        b_auto = QPushButton(t("automatic"))
        b_auto.setObjectName("Pill")
        b_auto.setFixedHeight(30)
        b_auto.clicked.connect(lambda: self._bg_set(color=None))
        b_pick = IconButton("colorize", t("bg_pick"), 34, 20)
        b_pick.setToolTip(t("bg_pick"))
        b_pick.clicked.connect(self._bg_pick)
        brow.addWidget(self.lbl_bgcol)
        brow.addWidget(b_auto)
        brow.addWidget(b_pick)
        brow.addStretch(1)
        lay.addLayout(brow)
        self.sl_bgtol = _Slider(t("bg_tolerance"), 1, 60, lambda v: self._bg_set(tol=v), self._push)
        self.sl_bgtol.set(20)
        lay.addWidget(self.sl_bgtol)
        self.sl_bgfe = _Slider(t("bg_feather"), 0, 30, lambda v: self._bg_set(feather=v), self._push)
        self.sl_bgfe.set(6)
        lay.addWidget(self.sl_bgfe)
        self.chk_bgedge = QCheckBox(t("bg_edge_only"))
        self.chk_bgedge.setChecked(True)
        self.chk_bgedge.setToolTip(t("bg_edge_only_tip"))
        self.chk_bgedge.toggled.connect(lambda v: self._bg_set(edge=v))
        lay.addWidget(self.chk_bgedge)
        note = QLabel(t("bg_note"))
        note.setObjectName("Secondary")
        note.setWordWrap(True)
        lay.addWidget(note)
        self._bg_color_ui(None)
        lay.addWidget(Divider())

        lay.addWidget(self._title(t("resize")))
        rrow = QHBoxLayout()
        self.sp_w = QSpinBox()
        self.sp_h = QSpinBox()
        for sp in (self.sp_w, self.sp_h):
            sp.setRange(1, 30000)
            sp.setFixedWidth(92)
        self.chk_lock = QCheckBox(t("keep_ratio"))
        self.chk_lock.setChecked(True)
        rrow.addWidget(self.sp_w)
        rrow.addWidget(QLabel("×"))
        rrow.addWidget(self.sp_h)
        rrow.addStretch(1)
        lay.addLayout(rrow)
        lay.addWidget(self.chk_lock)
        prow = QHBoxLayout()
        for pct in (25, 50, 75, 100):
            c = Chip(f"%{pct}", checkable=False)
            c.clicked.connect(lambda _=False, p=pct: self._resize_pct(p))
            prow.addWidget(c)
        prow.addStretch(1)
        lay.addLayout(prow)
        self.sp_w.valueChanged.connect(lambda v: self._resize_changed("w", v))
        self.sp_h.valueChanged.connect(lambda v: self._resize_changed("h", v))
        lay.addStretch(1)

        # Alt butonlar
        foot = QHBoxLayout()
        b_reset = QPushButton(t("reset"))
        b_reset.setObjectName("Flat")
        b_reset.clicked.connect(self.reset)
        foot.addWidget(b_reset)
        foot.addStretch(1)
        self.cmb_fmt = QComboBox()
        src_ext = os.path.splitext(self.item.path)[1].lower()
        self.cmb_fmt.addItem(t("keep_format") + (f" ({src_ext.strip('.').upper()})" if image_io.is_writable_ext(src_ext) else ""), None)
        for label, ext, _ in image_io.OUTPUT_FORMATS:
            self.cmb_fmt.addItem(label, ext)
        if not image_io.is_writable_ext(src_ext):
            self.cmb_fmt.setCurrentIndex(1)
        self.cmb_fmt.setToolTip(t("format"))
        self.cmb_fmt.currentIndexChanged.connect(self._fmt_changed)
        foot.addWidget(self.cmb_fmt)
        self.cmb_q = QComboBox()
        for q in (100, 95, 92, 85, 75, 60):
            self.cmb_q.addItem(t("quality_n", n=q), q)
        self.cmb_q.setCurrentIndex(2)
        self.cmb_q.setToolTip(t("quality"))
        foot.addWidget(self.cmb_q)
        outer.addLayout(foot)
        foot2 = QHBoxLayout()
        self.b_saveas = QPushButton(t("save_as"))
        self.b_saveas.setObjectName("Pill")
        self.b_saveas.clicked.connect(self.save_as)
        self.b_save = QPushButton(t("save"))
        self.b_save.setObjectName("Primary")
        self.b_save.clicked.connect(self.save_overwrite)
        foot2.addStretch(1)
        foot2.addWidget(self.b_saveas)
        foot2.addWidget(self.b_save)
        outer.addLayout(foot2)

    def _title(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        return lbl

    def _set_enabled(self, on):
        self.body.setEnabled(on)
        self.b_save.setEnabled(on)
        self.b_saveas.setEnabled(on)

    # ---------------------------------------------------------------- yükleme
    def _loaded(self, img):
        if getattr(img, "n_frames", 1) > 1:
            try:
                img.seek(0)
            except Exception:
                pass
        img.load()
        self.full = img
        self.proxy = img.copy()
        self.proxy.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
        self._set_enabled(True)
        self._sync_resize_fields()
        self._fmt_changed()
        self._render_preview()

    def _load_failed(self, msg):
        QMessageBox.warning(self, t("edit_image_title"), t("cannot_open_image") + "\n" + msg)
        self.closed.emit()

    # ---------------------------------------------------------------- durum
    def dirty(self):
        return self.state != DEFAULT_STATE

    def _push(self):
        self.history.append(copy.deepcopy(self.state))
        self.redo_stack.clear()
        if len(self.history) > 60:
            self.history.pop(0)

    def undo(self):
        if self.history:
            self.redo_stack.append(copy.deepcopy(self.state))
            self.state = self.history.pop()
            self._sync_controls()
            self._schedule()

    def redo(self):
        if self.redo_stack:
            self.history.append(copy.deepcopy(self.state))
            self.state = self.redo_stack.pop()
            self._sync_controls()
            self._schedule()

    def reset(self):
        self._push()
        self.state = copy.deepcopy(DEFAULT_STATE)
        if self.cropping:
            self._end_crop(False)
        self._sync_controls()
        self._schedule()

    # ---------------------------------------------------------------- arka plan
    def _bg_color_ui(self, col):
        if col:
            self.lbl_bgcol.setStyleSheet(f"background: rgb{tuple(col)}; border: 1px solid #888; border-radius: 13px;")
            self.lbl_bgcol.setToolTip(t("bg_color") + f": #{col[0]:02X}{col[1]:02X}{col[2]:02X}")
        else:
            self.lbl_bgcol.setStyleSheet("border: 2px dashed #888; border-radius: 13px;")
            self.lbl_bgcol.setToolTip(t("bg_color") + ": " + t("automatic"))

    def _bg_toggled(self, on):
        self._push()
        if on:
            self.state["bg"] = {"color": None, "tol": self.sl_bgtol.s.value(), "feather": self.sl_bgfe.s.value(),
                                "edge": self.chk_bgedge.isChecked()}
        else:
            self.state["bg"] = None
        self._fmt_changed()
        self._schedule()

    def _bg_set(self, **kw):
        if "color" in kw:
            self._bg_color_ui(kw["color"])
        if not self.state.get("bg"):
            if "color" in kw:
                self.chk_bg.setChecked(True)
                self.state["bg"]["color"] = kw["color"]
                self._schedule()
            return
        b = dict(self.state["bg"])
        b.update(kw)
        self.state["bg"] = b
        self._schedule()

    def _bg_pick(self):
        """Görsele tıklayarak arka plan rengini seç (damlalık)."""
        if self.proxy is None:
            return
        try:
            self.viewer.picked.disconnect()
        except TypeError:
            pass
        self.viewer.picked.connect(self._bg_picked)
        self.viewer.start_pick()
        self.win.osd(t("bg_pick_hint"))

    def _bg_picked(self, pt):
        st = dict(DEFAULT_STATE, rot=self.state["rot"], flip_h=self.state["flip_h"], flip_v=self.state["flip_v"],
                  crop=self.state["crop"])
        base = render(self.proxy, st).convert("RGB")
        x = int(max(0, min(base.width - 1, pt.x() * base.width / max(1, self.viewer._img_size()[0]))))
        y = int(max(0, min(base.height - 1, pt.y() * base.height / max(1, self.viewer._img_size()[1]))))
        col = base.getpixel((x, y))[:3]
        self._push()
        self._bg_set(color=list(col))

    def _sync_controls(self):
        for k, s in self.sliders.items():
            s.set(self.state[k])
        self.filter_btns.get(self.state["filter"], self.filter_btns["none"]).setChecked(True)
        bg = self.state.get("bg")
        self.chk_bg.blockSignals(True)
        self.chk_bg.setChecked(bool(bg))
        self.chk_bg.blockSignals(False)
        self._bg_color_ui(bg.get("color") if bg else None)
        self._fmt_changed()
        self._sync_resize_fields()

    def _set(self, key, v):
        self.state[key] = v
        self._schedule()

    def _set_filter(self, f):
        self._push()
        self.state["filter"] = f
        self._schedule()

    def _rotate(self, d):
        if self.cropping:
            self._end_crop(False)
        self._push()
        # Tek eksende çevrilmişse görsel yön tersine döner
        eff = d if self.state["flip_h"] == self.state["flip_v"] else -d
        self.state["rot"] = (self.state["rot"] + eff) % 360
        if self.state["crop"]:
            x0, y0, x1, y1 = self.state["crop"]
            if d == 90:
                self.state["crop"] = (1 - y1, x0, 1 - y0, x1)
            else:
                self.state["crop"] = (y0, 1 - x1, y1, 1 - x0)
        self._sync_resize_fields()
        self._schedule()

    def _flip(self, key):
        if self.cropping:
            self._end_crop(False)
        self._push()
        self.state[key] = not self.state[key]
        if self.state["crop"]:
            x0, y0, x1, y1 = self.state["crop"]
            self.state["crop"] = (1 - x1, y0, 1 - x0, y1) if key == "flip_h" else (x0, 1 - y1, x1, 1 - y0)
        self._schedule()

    # ---------------------------------------------------------------- kırpma
    def _toggle_crop(self):
        if self.cropping:
            self._end_crop(True)
        else:
            self._start_crop()

    def _start_crop(self):
        if self.proxy is None:
            return
        self.cropping = True
        self.btn_crop.setChecked(True)
        self.crop_box.show()
        base = render(self.proxy, self.state, skip_crop=True)
        self.viewer.set_image(image_io.pil_to_qimage(base))
        self.viewer.set_crop_mode(True)
        if self.state["crop"]:
            x0, y0, x1, y1 = self.state["crop"]
            w, h = base.size
            self.viewer.crop = QRectF(x0 * w, y0 * h, (x1 - x0) * w, (y1 - y0) * h)
            self.viewer.update()
        btn = self.ratio_group.buttons()[0]
        btn.setChecked(True)

    def _set_ratio(self, v):
        if not self.cropping:
            self._start_crop()
        if v == "orig":
            base_w, base_h = self.viewer._img_size()
            v = base_w / base_h
        self.viewer.apply_ratio(v)

    def _end_crop(self, apply):
        if not self.cropping:
            return
        if apply:
            w, h = self.viewer._img_size()
            r = self.viewer.crop
            if r.width() >= 2 and r.height() >= 2 and not (r.width() >= w - 1 and r.height() >= h - 1):
                self._push()
                self.state["crop"] = (r.left() / w, r.top() / h, r.right() / w, r.bottom() / h)
            elif r.width() >= w - 1 and r.height() >= h - 1 and self.state["crop"]:
                self._push()
                self.state["crop"] = None
        self.cropping = False
        self.btn_crop.setChecked(False)
        self.crop_box.hide()
        self.viewer.set_crop_mode(False)
        self._sync_resize_fields()
        self._render_preview(reset_view=True)

    # ---------------------------------------------------------------- boyut
    def _output_size(self):
        if self.full is None:
            return 0, 0
        w, h = self.full.size
        if self.state["rot"] in (90, 270):
            w, h = h, w
        if self.state["crop"]:
            x0, y0, x1, y1 = self.state["crop"]
            w, h = int(round((x1 - x0) * w)), int(round((y1 - y0) * h))
        return max(1, w), max(1, h)

    def _sync_resize_fields(self):
        w, h = self._output_size()
        if self.state["resize"]:
            rw, rh = self.state["resize"]
        else:
            rw, rh = w, h
        for sp, v in ((self.sp_w, rw), (self.sp_h, rh)):
            sp.blockSignals(True)
            sp.setValue(int(v))
            sp.blockSignals(False)
        txt = f"{t('original')}: {self.full.size[0]}×{self.full.size[1]}  →  {rw}×{rh}" if self.full else ""
        self.lbl_size.setText(txt)

    def _resize_changed(self, which, v):
        w, h = self._output_size()
        if not w or not h:
            return
        rw, rh = self.sp_w.value(), self.sp_h.value()
        if self.chk_lock.isChecked():
            if which == "w":
                rh = max(1, int(round(v * h / w)))
            else:
                rw = max(1, int(round(v * w / h)))
        self.state["resize"] = None if (rw, rh) == (w, h) else (rw, rh)
        self._sync_resize_fields()

    def _resize_pct(self, p):
        w, h = self._output_size()
        rw, rh = max(1, w * p // 100), max(1, h * p // 100)
        self.state["resize"] = None if p == 100 else (rw, rh)
        self._sync_resize_fields()

    # ---------------------------------------------------------------- önizleme
    def _schedule(self):
        if not self.cropping:
            self._timer.start()

    def _render_preview(self, reset_view=False):
        if self.proxy is None or self.cropping:
            return
        out = render(self.proxy, self.state)
        self.viewer.set_image(image_io.pil_to_qimage(out), keep_view=not reset_view)
        self.btn_undo.setEnabled(bool(self.history))
        self.btn_redo.setEnabled(bool(self.redo_stack))
        self._sync_resize_fields()

    # ---------------------------------------------------------------- kaydet
    def _target_ext(self):
        ext = self.cmb_fmt.currentData()
        src = os.path.splitext(self.item.path)[1].lower()
        if self.state.get("bg") and (ext or src) in (".jpg", ".jpeg", ".jpe", ".jfif", ".bmp"):
            return ".png"  # saydamlık için
        if ext is None:
            return src if image_io.is_writable_ext(src) else ".png"
        if ext == ".jpg" and src in (".jpg", ".jpeg", ".jpe", ".jfif"):
            return src
        if ext == ".tif" and src == ".tiff":
            return src
        return ext

    def _fmt_changed(self, *_):
        lossy = {e for _, e, l in image_io.OUTPUT_FORMATS if l}
        self.cmb_q.setEnabled(self._target_ext() in lossy | {".jpeg", ".jpe", ".jfif"})
        same = self._target_ext() == os.path.splitext(self.item.path)[1].lower()
        self.b_save.setText(t("save") if same else t("convert_save"))

    def save_overwrite(self):
        ext = self._target_ext()
        base, src = os.path.splitext(self.item.path)
        if ext == src.lower():
            r = QMessageBox.question(self, t("save"), t("confirm_overwrite", name=self.item.name))
            if r == QMessageBox.StandardButton.Yes:
                self._save(self.item.path)
            return
        # Biçim değişti: orijinal korunur, yanına yeni uzantıyla kaydedilir
        target = base + ext
        msg = t("convert_confirm", name=os.path.basename(target))
        if os.path.exists(target):
            msg += "\n\n" + t("file_exists_overwrite")
        r = QMessageBox.question(self, t("convert_save"), msg)
        if r == QMessageBox.StandardButton.Yes:
            self._save(target)

    def save_as(self):
        base, _ = os.path.splitext(self.item.path)
        ext = self._target_ext()
        default = base + "_" + t("edited_suffix") + ext
        path, chosen = QFileDialog.getSaveFileName(self, t("save_as"), default, image_io.file_filter(
            ".jpg" if ext in (".jpeg", ".jpe", ".jfif") else (".tif" if ext == ".tiff" else ext)))
        if not path:
            return
        if not os.path.splitext(path)[1]:
            ext = chosen.split("*")[1].split(" ")[0].rstrip(")") if "*" in chosen else ".png"
            path += ext
        self._save(path)

    def _save(self, path):
        if self.full is None or self._saving:
            return
        self._saving = True
        self._set_enabled(False)
        q = self.cmb_q.currentData()
        st = copy.deepcopy(self.state)
        full = self.full

        def work():
            out = render(full, st, final=True)
            tmp = path + ".gamma-tmp" + os.path.splitext(path)[1]
            image_io.save_pil(out, tmp, quality=q)
            os.replace(tmp, path)
            return path

        def done(p):
            self._saving = False
            self._set_enabled(True)
            self.win.osd(t("image_saved"))
            self.saved.emit(p)
            if os.path.normcase(p) == os.path.normcase(self.item.path):
                # Orijinal güncellendi: düzenlemeyi yeni temel kabul et
                self.state = copy.deepcopy(DEFAULT_STATE)
                self.history.clear()
                self.closed.emit()

        def fail(msg):
            self._saving = False
            self._set_enabled(True)
            QMessageBox.warning(self, t("save"), t("save_failed") + "\n" + msg)
        thumbs.run_async(work, on_done=done, on_fail=fail)

    # ---------------------------------------------------------------- kapanış
    def request_close(self):
        if self._saving:
            return False
        if self.dirty():
            box = QMessageBox(self)
            box.setWindowTitle(t("edit_image_title"))
            box.setText(t("unsaved_changes"))
            bs = box.addButton(t("save_as"), QMessageBox.ButtonRole.AcceptRole)
            bd = box.addButton(t("discard"), QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(t("cancel"), QMessageBox.ButtonRole.RejectRole)
            box.exec()
            c = box.clickedButton()
            if c is bs:
                self.save_as()
                return False
            if c is not bd:
                return False
        if self.cropping:
            self.viewer.set_crop_mode(False)
        self.closed.emit()
        return True

    def keyPressEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if e.key() == Qt.Key.Key_Z:
                self.undo()
                return
            if e.key() == Qt.Key.Key_Y:
                self.redo()
                return
            if e.key() == Qt.Key.Key_S:
                self.save_as()
                return
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.cropping:
            self._end_crop(True)
            return
        super().keyPressEvent(e)
