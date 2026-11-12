"""ffmpeg tabanlı yardımcılar: küçük resimler, süre okuma, kare yakalama, kapak resmi, dalga formu.

Tüm ağır işler arka plan iş parçacıklarında yapılır ve sonuçlar QImage olarak sinyallenir.
"""
import hashlib
import json
import os
import re
import subprocess
import threading
from collections import OrderedDict

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, QThread, QMutex, QWaitCondition, Qt
from PyQt6.QtGui import QImage

from .config import THUMB_DIR
from .formats import KIND_AUDIO, KIND_IMAGE, KIND_VIDEO
from . import image_io

def _find_ffmpeg():
    """imageio_ffmpeg'i içe aktarmadan (≈40 ms) paketle gelen ffmpeg.exe'yi bulur."""
    import glob
    import importlib.util
    import sys
    roots = []
    if getattr(sys, "frozen", False):
        roots.append(os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "imageio_ffmpeg"))
    try:
        spec = importlib.util.find_spec("imageio_ffmpeg")
        if spec and spec.submodule_search_locations:
            roots += list(spec.submodule_search_locations)
    except Exception:
        pass
    for r in roots:
        found = sorted(glob.glob(os.path.join(r, "binaries", "ffmpeg*.exe")))
        if found:
            return found[-1]
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


FFMPEG = _find_ffmpeg()

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_RES_RE = re.compile(r"Stream #\d+:\d+.*?Video:.*?(\d{2,5})x(\d{2,5})")


def run_ffmpeg(args, timeout=30, input_bytes=None):
    """ffmpeg'i konsol penceresi açmadan çalıştırır; (returncode, stdout, stderr) döndürür."""
    try:
        p = subprocess.run([FFMPEG, "-hide_banner", "-nostdin"] + args, capture_output=True,
                           timeout=timeout, creationflags=NO_WINDOW, input=input_bytes)
        return p.returncode, p.stdout, p.stderr.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return -1, b"", "timeout"
    except OSError as e:
        return -1, b"", str(e)


def parse_duration(stderr: str) -> int:
    m = _DUR_RE.search(stderr)
    if not m:
        return -1
    h, mi, s = m.groups()
    return int((int(h) * 3600 + int(mi) * 60 + float(s)) * 1000)


def parse_resolution(stderr: str):
    for m in _RES_RE.finditer(stderr):
        line_start = stderr.rfind("\n", 0, m.start())
        line = stderr[line_start:m.end() + 200]
        if "attached pic" in line:
            continue
        return int(m.group(1)), int(m.group(2))
    return 0, 0


_STREAM_AUDIO = re.compile(r"Stream #\d+:\d+.*?Audio:\s*([^,(]+)(?:\s*\([^)]*\))?.*?(\d+) Hz,\s*([^,]+)(?:,[^,]*)?(?:,\s*(\d+) kb/s)?")


def media_tags(path: str) -> dict:
    """Ses/video dosyasının etiketleri + ses akışı bilgisi (ffmpeg çıktısından)."""
    err = probe(path)
    tags, in_meta, info = {}, False, {}
    for line in err.splitlines():
        if line.startswith("  Metadata:") and not tags and not in_meta:
            in_meta = True
            continue
        if in_meta:
            if line.startswith("    ") and ":" in line:
                k, v = line.strip().split(":", 1)
                k = k.strip().lower()
                if k not in tags:
                    tags[k] = v.strip()
                continue
            in_meta = False
        if "Audio:" in line and "codec" not in info:
            m = _STREAM_AUDIO.search(line)
            if m:
                info["codec"] = m.group(1).strip()
                info["hz"] = int(m.group(2))
                info["channels"] = m.group(3).strip()
                if m.group(4):
                    info["kbps"] = int(m.group(4))
    m = re.search(r"bitrate:\s*(\d+) kb/s", err)
    if m and "kbps" not in info:
        info["kbps"] = int(m.group(1))
    info["duration"] = parse_duration(err)
    return {"tags": tags, "info": info}


def probe(path: str) -> str:
    """ffmpeg -i çıktısı (medya bilgisi)."""
    _, _, err = run_ffmpeg(["-i", path], timeout=15)
    return err


def grab_frame(path: str, ms: int, width: int = 320, accurate: bool = False, timeout: float = 12) -> QImage:
    """Belirtilen zamandaki kareyi QImage olarak döndürür."""
    sec = max(0.0, ms / 1000.0)
    args = []
    if accurate and sec > 3:
        args += ["-ss", f"{sec - 3:.3f}", "-i", path, "-ss", "3"]
    else:
        args += ["-ss", f"{sec:.3f}", "-i", path]
    vf = f"scale={int(width)}:-2:flags=bilinear" if width else "null"
    args += ["-frames:v", "1", "-an", "-sn", "-vf", vf, "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "-"]
    _, out, _ = run_ffmpeg(args, timeout=timeout)
    img = QImage()
    if out:
        img.loadFromData(out)
    return img


def extract_cover(path: str, max_side: int = 600) -> QImage:
    _, out, _ = run_ffmpeg(["-i", path, "-an", "-frames:v", "1", "-vf",
                            f"scale='min({max_side},iw)':-2", "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "2", "-"],
                           timeout=10)
    img = QImage()
    if out:
        img.loadFromData(out)
    return img


def waveform(path: str, w: int = 1600, h: int = 120, color: str = "#ff4e45") -> QImage:
    _, out, _ = run_ffmpeg(["-i", path, "-filter_complex",
                            f"aformat=channel_layouts=mono,showwavespic=s={w}x{h}:colors={color}:scale=sqrt",
                            "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"], timeout=60)
    img = QImage()
    if out:
        img.loadFromData(out)
    return img


def _cache_key(path: str, size: int, mtime: float) -> str:
    raw = f"{os.path.normcase(path)}|{size}|{int(mtime)}|v4"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


class _ThumbSignals(QObject):
    ready = pyqtSignal(str, QImage, dict, int)   # path, resim, meta, nesil


class _ThumbJob(QRunnable):
    def __init__(self, svc, item, generation):
        super().__init__()
        self.svc = svc
        self.path = item.path
        self.kind = item.kind
        self.size = item.size
        self.mtime = item.mtime
        self.gen = generation
        self.setAutoDelete(True)

    def run(self):
        if self.gen != self.svc.generation:
            return
        key = _cache_key(self.path, self.size, self.mtime)
        jpg = os.path.join(THUMB_DIR, key + ".jpg")
        meta_f = os.path.join(THUMB_DIR, key + ".json")
        meta, img = {}, QImage()
        try:
            if os.path.exists(meta_f):
                with open(meta_f, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                if os.path.exists(jpg):
                    img = QImage(jpg)
                if not img.isNull() or meta.get("no_image"):
                    self.svc.signals.ready.emit(self.path, img, meta, self.gen)
                    return
        except Exception:
            meta = {}
        try:
            if self.kind == KIND_IMAGE:
                img = image_io.make_thumbnail(self.path)
                try:
                    from PIL import Image
                    with Image.open(self.path) as im:
                        w_, h_ = im.size
                        try:
                            if im.getexif().get(0x0112, 1) in (5, 6, 7, 8):
                                w_, h_ = h_, w_
                        except Exception:
                            pass
                        meta["w"], meta["h"] = w_, h_
                except Exception:
                    if not img.isNull():
                        meta["w"], meta["h"] = img.width(), img.height()
            elif self.kind == KIND_VIDEO:
                rc, out, err = run_ffmpeg(["-ss", "2", "-i", self.path, "-frames:v", "1", "-an", "-sn",
                                           "-vf", "thumbnail=24,scale=320:-2", "-f", "image2pipe",
                                           "-vcodec", "mjpeg", "-q:v", "3", "-"], timeout=25)
                dur = parse_duration(err)
                if not out:
                    rc, out, err2 = run_ffmpeg(["-i", self.path, "-frames:v", "1", "-an", "-sn",
                                                "-vf", "scale=320:-2", "-f", "image2pipe",
                                                "-vcodec", "mjpeg", "-q:v", "3", "-"], timeout=25)
                    if dur < 0:
                        dur = parse_duration(err2)
                if out:
                    img.loadFromData(out)
                meta["duration"] = dur
                meta["w"], meta["h"] = parse_resolution(err)
            elif self.kind == KIND_AUDIO:
                rc, out, err = run_ffmpeg(["-i", self.path, "-an", "-frames:v", "1", "-vf",
                                           "scale=320:-2", "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "-"],
                                          timeout=20)
                meta["duration"] = parse_duration(err)
                if out:
                    img.loadFromData(out)
        except Exception:
            pass
        if img.isNull():
            meta["no_image"] = True
        else:
            if img.width() > 640:
                img = img.scaledToWidth(640, Qt.TransformationMode.SmoothTransformation)
            try:
                img.save(jpg, "JPG", 88)
            except Exception:
                pass
        try:
            with open(meta_f, "w", encoding="utf-8") as f:
                json.dump(meta, f)
        except OSError:
            pass
        self.svc.signals.ready.emit(self.path, img, meta, self.gen)


class ThumbnailService(QObject):
    """Klasör öğeleri için küçük resim + süre üretir (önbellekli, 3 paralel iş)."""
    ready = pyqtSignal(str, QImage, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        self.generation = 0
        self.signals = _ThumbSignals()
        self.signals.ready.connect(self._on_ready, Qt.ConnectionType.QueuedConnection)
        self._requested = set()

    WINDOW = 40   # açılışta `first` çevresinde hazırlanan öğe sayısı (her yönde)

    def request(self, items, first=None):
        """Yeni klasör listesi: yalnızca `first` çevresini kuyruğa alır; diğerleri listede
        göründükçe `ensure()` ile istenir (büyük klasörlerde gereksiz ffmpeg işi olmaz)."""
        self.generation += 1
        self.pool.clear()
        self._requested = set()
        ordered = list(items)
        i = ordered.index(first) if first is not None and first in ordered else 0
        lo, hi = max(0, i - self.WINDOW), i + self.WINDOW + 1
        for it in ordered[i:hi] + ordered[lo:i][::-1]:
            self.ensure(it)

    def ensure(self, item):
        """Öğe için daha önce istenmediyse küçük resim işini kuyruğa alır."""
        if item.path in self._requested:
            return
        self._requested.add(item.path)
        self.pool.start(_ThumbJob(self, item, self.generation))

    def request_one(self, item):
        self.pool.start(_ThumbJob(self, item, self.generation), 10)

    def _on_ready(self, path, img, meta, gen):
        self.ready.emit(path, img, meta)

    def shutdown(self):
        self.generation += 1
        self.pool.clear()
        self.pool.waitForDone(1500)


class FrameGrabber(QThread):
    """Zaman çubuğu üzerinde gezinirken önizleme karesi üretir (her zaman en son isteği işler)."""
    frame = pyqtSignal(str, int, QImage)   # path, bucket, resim

    def __init__(self, parent=None, width=240, accurate=False):
        super().__init__(parent)
        self.width = width
        self.accurate = accurate
        self._mutex = QMutex()
        self._cond = QWaitCondition()
        self._pending = None
        self._quit = False
        self._cache = OrderedDict()
        self._lock = threading.Lock()

    def bucket_for(self, length_ms: int, ms: int) -> int:
        step = max(1000, length_ms // 300) if length_ms > 0 else 2000
        return int(ms // step) * step

    def cached(self, path, bucket):
        with self._lock:
            img = self._cache.get((path, bucket))
            if img is not None:
                self._cache.move_to_end((path, bucket))
            return img

    def nearest_cached(self, path, bucket):
        with self._lock:
            best, bd = None, None
            for (p, b), img in self._cache.items():
                if p != path:
                    continue
                d = abs(b - bucket)
                if bd is None or d < bd:
                    best, bd = img, d
            return best

    def request(self, path: str, bucket: int):
        self._mutex.lock()
        self._pending = (path, bucket)
        self._cond.wakeOne()
        self._mutex.unlock()

    def stop(self):
        self._mutex.lock()
        self._quit = True
        self._cond.wakeOne()
        self._mutex.unlock()
        self.wait(2000)

    def run(self):
        while True:
            self._mutex.lock()
            while self._pending is None and not self._quit:
                self._cond.wait(self._mutex)
            if self._quit:
                self._mutex.unlock()
                return
            path, bucket = self._pending
            self._pending = None
            self._mutex.unlock()
            if self.cached(path, bucket) is not None:
                continue
            img = grab_frame(path, bucket, self.width, accurate=self.accurate, timeout=10)
            if not img.isNull():
                with self._lock:
                    self._cache[(path, bucket)] = img
                    while len(self._cache) > 400:
                        self._cache.popitem(last=False)
                self.frame.emit(path, bucket, img)


class Task(QThread):
    """Herhangi bir fonksiyonu arka planda çalıştırıp sonucu sinyalle döndürür."""
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, *args, parent=None, **kwargs):
        super().__init__(parent)
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.finished.connect(self.deleteLater)

    def run(self):
        try:
            self.done.emit(self.fn(*self.args, **self.kwargs))
        except Exception as e:
            self.failed.emit(str(e))


_tasks = set()


def run_async(fn, *args, on_done=None, on_fail=None, **kwargs):
    t = Task(fn, *args, **kwargs)
    _tasks.add(t)
    if on_done:
        t.done.connect(on_done)
    if on_fail:
        t.failed.connect(on_fail)
    t.finished.connect(lambda: _tasks.discard(t))
    t.start()
    return t
