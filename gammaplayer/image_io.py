"""Her formatta resim okuma/yazma (JXL, HEIC, AVIF, WebP, ICO, GIF, SVG, PSD...).

Not: Bu modüldeki fonksiyonlar arka plan iş parçacıklarında çalışabilir; bu yüzden
QPixmap değil yalnızca QImage üretir (QPixmap sadece ana iş parçacığında kullanılabilir).
"""
import os

from PIL import Image, ImageOps, ImageSequence
from PyQt6.QtCore import Qt, QByteArray
from PyQt6.QtGui import QImage, QPainter

# HEIC ve JPEG XL kütüphaneleri ağırdır (~150 ms); yalnızca gerektiğinde yüklenir.
_heif_ready = False


def _ensure_heif():
    global _heif_ready
    if not _heif_ready:
        _heif_ready = True
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except Exception:
            pass


def _codecs():
    try:
        import imagecodecs
        return imagecodecs
    except Exception:
        return None


Image.MAX_IMAGE_PIXELS = 400_000_000

MAX_ANIM_FRAMES = 1500
MAX_ANIM_BYTES = 700 * 1024 * 1024


class LoadedImage:
    """Görüntülenecek resim: tek kare veya animasyon kareleri."""

    def __init__(self, frames, durations=None, info=None):
        self.frames = frames                 # list[QImage]
        self.durations = durations or []     # ms
        self.info = info or {}

    @property
    def animated(self):
        return len(self.frames) > 1

    @property
    def first(self):
        return self.frames[0] if self.frames else QImage()


def pil_to_qimage(img: Image.Image) -> QImage:
    if img.mode not in ("RGB", "RGBA"):
        has_alpha = "A" in img.mode or (img.mode in ("P", "L", "RGB") and "transparency" in img.info)
        img = img.convert("RGBA" if has_alpha else "RGB")
    if img.mode == "RGBA":
        data = img.tobytes("raw", "RGBA")
        q = QImage(data, img.width, img.height, img.width * 4, QImage.Format.Format_RGBA8888)
    else:
        data = img.tobytes("raw", "RGB")
        q = QImage(data, img.width, img.height, img.width * 3, QImage.Format.Format_RGB888)
    return q.copy()  # veri sahipliğini Qt'ye geçir


def qimage_to_pil(q: QImage) -> Image.Image:
    q = q.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = q.constBits()
    ptr.setsize(q.sizeInBytes())
    img = Image.frombuffer("RGBA", (q.width(), q.height()), bytes(ptr), "raw", "RGBA", q.bytesPerLine(), 1)
    return img.copy()


def _numpy_to_pil(arr) -> Image.Image:
    import numpy as np
    if arr.dtype != np.uint8:
        if arr.dtype in (np.float16, np.float32, np.float64):
            arr = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
        else:
            mx = 65535 if arr.dtype == np.uint16 else max(1, int(arr.max()))
            arr = (arr.astype(np.float32) / mx * 255).astype(np.uint8)
    if arr.ndim == 2:
        return Image.fromarray(arr, "L")
    if arr.ndim == 3 and arr.shape[2] == 1:
        return Image.fromarray(arr[:, :, 0], "L")
    if arr.ndim == 3 and arr.shape[2] == 2:
        return Image.fromarray(arr, "LA")
    if arr.ndim == 3 and arr.shape[2] == 3:
        return Image.fromarray(arr, "RGB")
    if arr.ndim == 3 and arr.shape[2] == 4:
        return Image.fromarray(arr, "RGBA")
    if arr.ndim == 4:  # animasyonlu jxl -> ilk kare
        return _numpy_to_pil(arr[0])
    raise ValueError("Desteklenmeyen dizi şekli")


def _render_svg(path: str, max_side: int = 2048) -> Image.Image:
    from PyQt6.QtSvg import QSvgRenderer
    if path.lower().endswith(".svgz"):
        import gzip
        with gzip.open(path, "rb") as f:
            data = f.read()
        r = QSvgRenderer(QByteArray(data))
    else:
        r = QSvgRenderer(path)
    if not r.isValid():
        raise ValueError("Geçersiz SVG")
    size = r.defaultSize()
    w, h = max(1, size.width()), max(1, size.height())
    scale = max_side / max(w, h)
    w, h = int(w * scale), int(h * scale)
    q = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    q.fill(Qt.GlobalColor.transparent)
    p = QPainter(q)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p)
    p.end()
    return qimage_to_pil(q)


def open_pil(path: str) -> Image.Image:
    """Herhangi bir resmi PIL Image olarak açar (EXIF yönü uygulanmış)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".svg", ".svgz"):
        return _render_svg(path)
    if ext in (".heic", ".heif", ".hif", ".avif"):
        _ensure_heif()
    if ext == ".jxl" and _codecs() is not None:
        with open(path, "rb") as f:
            return _numpy_to_pil(_codecs().jpegxl_decode(f.read()))
    try:
        img = Image.open(path)
        img.load()
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass
        return img
    except Exception:
        _ensure_heif()
        if _codecs() is not None:
            return _numpy_to_pil(_codecs().imread(path))
        q = QImage(path)
        if q.isNull():
            raise
        return qimage_to_pil(q)


def load_image(path: str) -> LoadedImage:
    """Görüntüleyici için yükler: animasyonlu GIF/WebP/APNG/AVIF karelerini de çıkarır."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".heic", ".heif", ".hif", ".avif"):
        _ensure_heif()
    info = {}
    if ext not in (".svg", ".svgz", ".jxl"):
        try:
            img = Image.open(path)
            info = {"format": img.format, "mode": img.mode, "size": img.size}
            n = getattr(img, "n_frames", 1)
            if n > 1 and ext not in (".ico", ".icns", ".tif", ".tiff", ".psd", ".mpo", ".heic", ".heif"):
                frames, durs, total = [], [], 0
                for i, fr in enumerate(ImageSequence.Iterator(img)):
                    if i >= MAX_ANIM_FRAMES or total > MAX_ANIM_BYTES:
                        break
                    q = pil_to_qimage(fr.convert("RGBA"))
                    total += q.sizeInBytes()
                    frames.append(q)
                    d = fr.info.get("duration", img.info.get("duration", 100)) or 100
                    durs.append(max(20, int(d)))
                if len(frames) > 1:
                    return LoadedImage(frames, durs, info)
            if ext == ".ico":
                # En büyük ikon boyutunu seç
                try:
                    sizes = sorted(img.ico.sizes(), key=lambda s: s[0] * s[1])
                    if sizes:
                        img.size = sizes[-1]
                except Exception:
                    pass
            img.load()
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass
            return LoadedImage([pil_to_qimage(img)], info=info)
        except Exception:
            pass
    img = open_pil(path)
    info = info or {"format": ext.strip(".").upper(), "mode": img.mode, "size": img.size}
    return LoadedImage([pil_to_qimage(img)], info=info)


def make_thumbnail(path: str, max_w: int = 320, max_h: int = 180) -> QImage:
    ext = os.path.splitext(path)[1].lower()
    img = None
    if ext in (".jpg", ".jpeg", ".jpe", ".jfif"):
        try:
            img = Image.open(path)
            img.draft("RGB", (max_w * 2, max_h * 2))
            img.load()
            img = ImageOps.exif_transpose(img)
        except Exception:
            img = None
    if img is None:
        img = open_pil(path)
    if getattr(img, "n_frames", 1) > 1:
        try:
            img.seek(0)
        except Exception:
            pass
    img = img.convert("RGBA") if ("A" in img.mode or img.mode == "P") else img.convert("RGB")
    img.thumbnail((max_w * 2, max_h * 2), Image.Resampling.LANCZOS)
    return pil_to_qimage(img)


SAVE_FORMATS = {
    ".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP", ".bmp": "BMP",
    ".tif": "TIFF", ".tiff": "TIFF", ".gif": "GIF", ".ico": "ICO", ".avif": "AVIF",
    ".heic": "HEIF", ".heif": "HEIF", ".jxl": "JXL", ".tga": "TGA", ".qoi": "QOI",
}


# (etiket, uzantı, kayıplı mı)
OUTPUT_FORMATS = [("PNG", ".png", False), ("JPEG", ".jpg", True), ("WebP", ".webp", True), ("AVIF", ".avif", True),
                  ("HEIC", ".heic", True), ("JPEG XL", ".jxl", True), ("BMP", ".bmp", False), ("TIFF", ".tif", False),
                  ("GIF", ".gif", False), ("ICO", ".ico", False), ("QOI", ".qoi", False)]


def file_filter(first_ext=None):
    items = []
    for label, ext, _ in OUTPUT_FORMATS:
        pats = "*.jpg *.jpeg" if ext == ".jpg" else ("*.tif *.tiff" if ext == ".tif" else "*" + ext)
        items.append((ext, f"{label} ({pats})"))
    if first_ext:
        items.sort(key=lambda x: x[0] != first_ext)
    return ";;".join(f for _, f in items)


def is_writable_ext(ext):
    return ext.lower() in SAVE_FORMATS


def save_pil(img: Image.Image, path: str, quality: int = 92):
    ext = os.path.splitext(path)[1].lower()
    fmt = SAVE_FORMATS.get(ext, "PNG")
    if fmt == "HEIF":
        _ensure_heif()
    if fmt == "JXL":
        imagecodecs = _codecs()
        if imagecodecs is None:
            raise RuntimeError("JXL kodlayıcı yok")
        import numpy as np
        arr = np.asarray(img.convert("RGBA" if "A" in img.mode else "RGB"))
        data = imagecodecs.jpegxl_encode(arr, level=None, distance=max(0.1, (100 - quality) / 10.0))
        with open(path, "wb") as f:
            f.write(data)
        return
    if fmt in ("JPEG", "BMP") and img.mode not in ("RGB", "L"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[3])
        img = bg
    kw = {}
    if fmt in ("JPEG", "WEBP", "AVIF", "HEIF"):
        kw["quality"] = quality
    if fmt == "JPEG":
        kw["optimize"] = True
        kw["subsampling"] = 0 if quality >= 90 else 2
    if fmt == "ICO":
        # Simgeler kare olmalı: kare olmayan görseli saydam kenarlıkla ortala, 256'ya sığdır
        img = img.convert("RGBA")
        side = max(img.size)
        if img.width != img.height:
            sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
            sq.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
            img = sq
        if side > 256:
            img = img.resize((256, 256), Image.Resampling.LANCZOS)
            side = 256
        kw["sizes"] = [(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256) if s <= side] or [(side, side)]
    img.save(path, fmt, **kw)
