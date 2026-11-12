"""Açılan klasördeki medya listesi (filtre, sıralama, arama, gezinme)."""
import ctypes
import functools
import os
import random
from datetime import datetime

from .formats import kind_of, KIND_VIDEO, KIND_AUDIO, KIND_IMAGE, KIND_MODEL, ext_of

try:
    _StrCmpLogicalW = ctypes.windll.shlwapi.StrCmpLogicalW
    _StrCmpLogicalW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    _StrCmpLogicalW.restype = ctypes.c_int

    def explorer_cmp(a: str, b: str) -> int:
        return _StrCmpLogicalW(a, b)
except Exception:  # Windows dışı
    import re

    def _nat(s):
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]

    def explorer_cmp(a, b):
        ka, kb = _nat(a), _nat(b)
        return (ka > kb) - (ka < kb)


class MediaItem:
    __slots__ = ("path", "name", "title", "ext", "kind", "size", "mtime", "duration", "width", "height")

    def __init__(self, path: str, size: int = 0, mtime: float = 0.0):
        self.path = os.path.abspath(path)
        self.name = os.path.basename(self.path)
        self.title, _ = os.path.splitext(self.name)
        self.ext = ext_of(self.path)
        self.kind = kind_of(self.path) or KIND_VIDEO
        self.size = size
        self.mtime = mtime
        self.duration = -1   # ms; -1 = bilinmiyor
        self.width = 0
        self.height = 0

    @property
    def is_video(self):
        return self.kind == KIND_VIDEO

    @property
    def is_audio(self):
        return self.kind == KIND_AUDIO

    @property
    def is_image(self):
        return self.kind == KIND_IMAGE

    @property
    def is_model(self):
        return self.kind == KIND_MODEL

    @property
    def is_playable(self):
        return self.kind in (KIND_VIDEO, KIND_AUDIO)

    def date_str(self):
        if not self.mtime:
            return ""
        return datetime.fromtimestamp(self.mtime).strftime("%d.%m.%Y")


def human_size(n: int) -> str:
    if n <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024.0
    return ""


def fmt_time(ms: int) -> str:
    """YouTube biçimi: 0:07, 12:34, 1:02:03"""
    if ms is None or ms < 0:
        ms = 0
    s = int(ms // 1000)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class Library:
    FILTERS = ("all", "video", "audio", "image", "model")
    SORTS = ("explorer", "name", "name_desc", "date", "date_asc", "size", "size_asc", "type")

    def __init__(self):
        self.folder = None
        self.all_items = []
        self.items = []          # filtrelenmiş görünüm
        self.current = None      # MediaItem
        self.filter = "all"
        self.sort = "explorer"
        self.explorer_sort = "name"   # Gezgin penceresinden okunan sıra (yoksa ada göre)
        self.query = ""
        self.extra_paths = []    # klasör dışından sürüklenen tekil dosyalar

    # ---------------------------------------------------------------- yükleme
    def scan_folder(self, folder: str):
        found = []
        try:
            with os.scandir(folder) as it:
                for e in it:
                    try:
                        if e.is_file() and kind_of(e.name):
                            st = e.stat()
                            found.append(MediaItem(e.path, st.st_size, st.st_mtime))
                    except OSError:
                        continue
        except OSError:
            pass
        return found

    def open_path(self, path: str):
        """Dosya verilirse klasörünü tarar ve dosyayı seçer; klasör verilirse ilk medyayı seçer."""
        path = os.path.abspath(path)
        if os.path.isdir(path):
            folder, target = path, None
        else:
            folder, target = os.path.dirname(path), path
        old = {os.path.normcase(i.path): i for i in self.all_items}
        self.folder = folder
        items = self.scan_folder(folder)
        # Önceden hesaplanmış süre/çözünürlük bilgilerini koru
        for it in items:
            prev = old.get(os.path.normcase(it.path))
            if prev:
                it.duration, it.width, it.height = prev.duration, prev.width, prev.height
        if target and not any(os.path.normcase(i.path) == os.path.normcase(target) for i in items):
            try:
                st = os.stat(target)
                items.append(MediaItem(target, st.st_size, st.st_mtime))
            except OSError:
                items.append(MediaItem(target))
        self.all_items = items
        cur = None
        if target:
            cur = self.find(target, items)
        self._rebuild()
        if cur is None and self.items:
            cur = self.items[0]
        self.current = cur
        return cur

    def refresh(self):
        """Klasördeki değişiklikleri (yeni kesilen video vb.) yeniden okur."""
        if not self.folder:
            return False
        cur_path = self.current.path if self.current else None
        old_set = {os.path.normcase(i.path) for i in self.all_items}
        old = {os.path.normcase(i.path): i for i in self.all_items}
        items = self.scan_folder(self.folder)
        new_set = {os.path.normcase(i.path) for i in items}
        if new_set == old_set:
            return False
        for it in items:
            prev = old.get(os.path.normcase(it.path))
            if prev:
                it.duration, it.width, it.height = prev.duration, prev.width, prev.height
        self.all_items = items
        self._rebuild()
        self.current = self.find(cur_path, self.all_items) if cur_path else None
        if self.current is None and cur_path and cur_path in old:
            self.current = old[cur_path]
        return True

    @staticmethod
    def find(path, items):
        if not path:
            return None
        key = os.path.normcase(os.path.abspath(path))
        for i in items:
            if os.path.normcase(i.path) == key:
                return i
        return None

    # ---------------------------------------------------------------- görünüm
    def set_filter(self, f):
        if f in self.FILTERS:
            self.filter = f
            self._rebuild()

    def set_sort(self, s):
        if s in self.SORTS:
            self.sort = s
            self._rebuild()

    def set_query(self, q):
        self.query = (q or "").strip().lower()
        self._rebuild()

    def _rebuild(self):
        items = list(self.all_items)
        if self.filter != "all":
            items = [i for i in items if i.kind == self.filter]
        if self.query:
            items = [i for i in items if self.query in i.name.lower()]
        name_key = functools.cmp_to_key(lambda a, b: explorer_cmp(a.name, b.name))
        mode = self.explorer_sort if self.sort == "explorer" else self.sort
        items.sort(key=name_key)
        if mode == "name_desc":
            items.reverse()
        elif mode == "date":
            items.sort(key=lambda i: -i.mtime)
        elif mode == "date_asc":
            items.sort(key=lambda i: i.mtime)
        elif mode == "size":
            items.sort(key=lambda i: -i.size)
        elif mode == "size_asc":
            items.sort(key=lambda i: i.size)
        elif mode in ("type", "type_desc"):
            items.sort(key=lambda i: i.ext, reverse=(mode == "type_desc"))
        self.items = items

    def index_of(self, item):
        if item is None:
            return -1
        for n, i in enumerate(self.items):
            if i is item:
                return n
        return -1

    def counts(self):
        c = {"all": len(self.all_items), "video": 0, "audio": 0, "image": 0, "model": 0}
        for i in self.all_items:
            c[i.kind] = c.get(i.kind, 0) + 1
        return c

    # ---------------------------------------------------------------- gezinme
    def _sequence(self):
        """Gezinme listesi: filtre görünümü; mevcut öğe görünümde yoksa tüm liste."""
        if self.current is not None and self.index_of(self.current) >= 0:
            return self.items
        seq = list(self.all_items)
        seq.sort(key=functools.cmp_to_key(lambda a, b: explorer_cmp(a.name, b.name)))
        return seq

    def neighbor(self, step: int, kinds=None, wrap=False, shuffle=False):
        seq = self._sequence()
        if kinds:
            seq_k = [i for i in seq if i.kind in kinds or i is self.current]
        else:
            seq_k = seq
        if not seq_k:
            return None
        if shuffle:
            pool = [i for i in seq_k if i is not self.current]
            return random.choice(pool) if pool else None
        try:
            idx = next(n for n, i in enumerate(seq_k) if i is self.current)
        except StopIteration:
            return seq_k[0]
        nidx = idx + step
        if 0 <= nidx < len(seq_k):
            return seq_k[nidx]
        if wrap and len(seq_k) > 1:
            return seq_k[nidx % len(seq_k)]
        return None

    def remove(self, item):
        self.all_items = [i for i in self.all_items if i is not item]
        self._rebuild()


_PROP_MAP = {
    "System.ItemNameDisplay": "name", "System.ItemNameDisplayWithoutExtension": "name", "System.FileName": "name",
    "System.ItemNameSortOverride": "name",
    "System.DateModified": "date", "System.DateCreated": "date", "System.ItemDate": "date",
    "System.DateAccessed": "date", "System.Photo.DateTaken": "date", "System.Media.DateEncoded": "date",
    "System.Size": "size", "System.ItemTypeText": "type", "System.ItemType": "type", "System.FileExtension": "type",
}


def explorer_sort_for(folder: str) -> str:
    """Bu klasör açık bir Gezgin penceresinde gösteriliyorsa oradaki sıralamayı döndürür.

    Dönüş: "name", "name_desc", "date" (yeni→eski), "date_asc", "size", "size_asc", "type", "type_desc";
    bulunamazsa "" döner. (Arka planda çağrılmalı; PowerShell üzerinden Shell COM sorgular.)
    """
    import subprocess
    script = (
        "$p=$env:GAMMA_FOLDER.TrimEnd('\');"
        "$s=New-Object -ComObject Shell.Application;"
        "foreach($w in $s.Windows()){try{"
        "if($w.Document.Folder.Self.Path.TrimEnd('\') -eq $p){$w.Document.SortColumns;break}"
        "}catch{}}"
    )
    env = dict(os.environ, GAMMA_FOLDER=os.path.abspath(folder))
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                             capture_output=True, text=True, timeout=8, env=env,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    except Exception:
        return ""
    # Örn: "prop:-System.DateModified;"  ("-" azalan demek)
    first = out.replace("prop:", "").split(";")[0].strip()
    if not first:
        return ""
    desc = first.startswith("-")
    kind = _PROP_MAP.get(first.lstrip("-"), "")
    if not kind:
        return ""
    if kind == "name":
        return "name_desc" if desc else "name"
    if kind == "date":
        return "date" if desc else "date_asc"
    if kind == "size":
        return "size" if desc else "size_asc"
    return "type_desc" if desc else "type"
