"""Uygulama yolları, kalıcı tercihler ve kaldığın yerden devam kayıtları."""
import json
import os
import sys
import threading

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    RES_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RES_DIR = BASE_DIR

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "gamma")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
THUMB_DIR = os.path.join(CACHE_DIR, "thumbs")
PREFS_FILE = os.path.join(DATA_DIR, "preferences.json")
POSITIONS_FILE = os.path.join(DATA_DIR, "positions.json")
SYNC_FILE = os.path.join(DATA_DIR, "media_sync.json")

for _d in (DATA_DIR, CACHE_DIR, THUMB_DIR):
    os.makedirs(_d, exist_ok=True)


def asset(name: str) -> str:
    return os.path.join(ASSETS_DIR, name)


DEFAULTS = {
    "language": "tr",
    "theme": "dark",            # dark | light
    "volume": 100,
    "muted": False,
    "autoplay": True,
    "loop": "off",              # off | all | one
    "shuffle": False,
    "resume": True,
    "pinned": False,
    "pip_enabled": True,        # Mini oynatıcı (PiP) özelliği açık mı
    "pin_enabled": True,        # Sabitleme özelliği açık mı
    "sidebar_visible": True,
    "theater": False,
    "sort": "explorer",         # explorer | name | name_desc | date | date_asc | size | size_asc | type
    "filter": "all",            # all | video | audio | image
    "slideshow_seconds": 4,
    "hw_decode": True,
    "single_instance": True,
    "sub_size": 100,            # %
    "sub_color": "#ffffff",
    "sub_bg": 0,                # 0..255 arka plan opaklığı
    "sub_outline": 4,           # 0, 2, 4, 6
    "sub_bold": False,
    "sub_margin": 24,
    "sub_encoding": "auto",
    "sub_font": "Segoe UI Semibold",
    "recent": [],
    "window_geometry": None,
    "snapshot_dir": "",
    "accent": "gray",
    "show_search": False,
    "show_open_buttons": False,
    "show_quick_buttons": False,
}


class _JsonStore:
    def __init__(self, path, defaults=None):
        self.path = path
        self.data = dict(defaults or {})
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except (OSError, ValueError):
            pass

    def save(self):
        with self._lock:
            tmp = self.path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=1)
                os.replace(tmp, self.path)
            except OSError:
                pass


class Prefs(_JsonStore):
    def __init__(self):
        super().__init__(PREFS_FILE, DEFAULTS)

    def get(self, key, default=None):
        if key in self.data:
            return self.data[key]
        return DEFAULTS.get(key, default)

    def set(self, key, value):
        if self.data.get(key) == value:
            return
        self.data[key] = value
        self.save()

    def add_recent(self, path: str):
        rec = [p for p in self.get("recent", []) if os.path.normcase(p) != os.path.normcase(path)]
        rec.insert(0, path)
        self.set("recent", rec[:12])


class PositionStore(_JsonStore):
    """Uzun videolarda kaldığın yerden devam (YouTube gibi)."""
    MAX = 400

    def __init__(self):
        super().__init__(POSITIONS_FILE)

    def get(self, path):
        return self.data.get(os.path.normcase(path))

    def set(self, path, ms, length):
        key = os.path.normcase(path)
        if length <= 0 or length < 120_000 or ms < 15_000 or ms > length - 20_000:
            if key in self.data:
                del self.data[key]
                self.save()
            return
        self.data.pop(key, None)
        self.data[key] = int(ms)
        if len(self.data) > self.MAX:
            for k in list(self.data.keys())[: len(self.data) - self.MAX]:
                del self.data[k]
        self.save()


class SyncStore(_JsonStore):
    """Dosyaya özel ses/altyazı gecikmesi."""

    def __init__(self):
        super().__init__(SYNC_FILE)

    def get(self, path):
        return self.data.get(os.path.normcase(path))

    def set(self, path, audio_ms, sub_ms):
        self.data[os.path.normcase(path)] = {"audio_delay": int(audio_ms), "sub_delay": int(sub_ms)}
        self.save()


prefs = Prefs()
positions = PositionStore()
sync_store = SyncStore()
