"""Karanlık / aydınlık tema: renk paletleri, Qt stil sayfası ve temaya duyarlı ikonlar."""
import re
import weakref

from PyQt6.QtCore import QObject, pyqtSignal, QSize
from PyQt6.QtWidgets import QApplication

from . import icons
from .config import prefs

ACCENTS = {
    "gray": "#c4c4c4",
    "red": "#ff0033",
    "blue": "#3ea6ff",
    "green": "#2ecc71",
    "purple": "#a970ff",
    "orange": "#ff8a1f",
    "pink": "#ff4fa3",
    "teal": "#1fc7b6",
}


def accent() -> str:
    """Tema rengi: hazır ad (gray, red…) veya kullanıcı tanımlı #RRGGBB."""
    v = str(prefs.get("accent", "gray") or "gray")
    if re.fullmatch(r"#[0-9a-fA-F]{6}", v):
        return v.lower()
    return ACCENTS.get(v, ACCENTS["gray"])


ACCENT = ACCENTS["gray"]  # geriye dönük uyumluluk

PALETTES = {
    "dark": {
        "bg": "#000000",        # AMOLED siyah
        "bg2": "#000000",
        "surface": "#272727",
        "surface_hover": "#3f3f3f",
        "card": "#212121",
        "text": "#f1f1f1",
        "text2": "#aaaaaa",
        "text3": "#717171",
        "divider": "rgba(255,255,255,0.10)",
        "hover": "rgba(255,255,255,0.10)",
        "pressed": "rgba(255,255,255,0.18)",
        "selected": "rgba(255,255,255,0.14)",
        "chip_active_bg": "#f1f1f1",
        "chip_active_fg": "#0f0f0f",
        "input_bg": "#121212",
        "input_border": "#303030",
        "button_bg": "#f1f1f1",
        "button_fg": "#0f0f0f",
        "scroll": "rgba(255,255,255,0.22)",
        "video_bg": "#000000",
    },
    "light": {
        "bg": "#ffffff",
        "bg2": "#f9f9f9",
        "surface": "#f2f2f2",
        "surface_hover": "#e5e5e5",
        "card": "#ffffff",
        "text": "#0f0f0f",
        "text2": "#606060",
        "text3": "#909090",
        "divider": "rgba(0,0,0,0.10)",
        "hover": "rgba(0,0,0,0.05)",
        "pressed": "rgba(0,0,0,0.10)",
        "selected": "rgba(0,0,0,0.07)",
        "chip_active_bg": "#0f0f0f",
        "chip_active_fg": "#ffffff",
        "input_bg": "#ffffff",
        "input_border": "#d3d3d3",
        "button_bg": "#0f0f0f",
        "button_fg": "#ffffff",
        "scroll": "rgba(0,0,0,0.25)",
        "video_bg": "#000000",
    },
}


# Tema çeşitleri: kimlik -> (Türkçe ad, İngilizce ad, aile, temel paletin üzerine yazılan renkler)
VARIANTS = {
    "amoled": ("AMOLED siyah", "AMOLED black", "dark", {}),
    "dark_gray": ("Koyu gri", "Dark gray", "dark", {"bg": "#0f0f0f", "bg2": "#181818"}),
    "graphite": ("Grafit", "Graphite", "dark", {
        "bg": "#1c1c1e", "bg2": "#232326", "surface": "#2f2f33", "surface_hover": "#45454a", "card": "#2a2a2e",
        "input_bg": "#18181a", "input_border": "#3a3a3e"}),
    "midnight": ("Gece mavisi", "Midnight blue", "dark", {
        "bg": "#0d1117", "bg2": "#111723", "surface": "#1f2733", "surface_hover": "#2d3846", "card": "#161d29",
        "input_bg": "#0b0f16", "input_border": "#2a3442", "text2": "#9aa6b4"}),
    "mocha": ("Sıcak koyu", "Mocha", "dark", {
        "bg": "#17130f", "bg2": "#1e1914", "surface": "#2c251e", "surface_hover": "#3d342a", "card": "#241e18",
        "input_bg": "#120f0c", "input_border": "#3a3128", "text2": "#b0a594"}),
    "white": ("Beyaz", "White", "light", {}),
    "light_gray": ("Açık gri", "Light gray", "light", {
        "bg": "#f1f1f3", "bg2": "#e9e9ec", "surface": "#e2e2e6", "surface_hover": "#d5d5da", "card": "#fafafa"}),
    "cream": ("Krem", "Cream", "light", {
        "bg": "#faf6ef", "bg2": "#f3eee4", "surface": "#ece5d8", "surface_hover": "#e0d7c6", "card": "#fffdf8",
        "input_bg": "#fffdf8", "text2": "#6b6258"}),
    "ice": ("Buz mavisi", "Ice blue", "light", {
        "bg": "#f3f7fb", "bg2": "#e9f0f7", "surface": "#e1e9f2", "surface_hover": "#d3deea", "text2": "#56657a"}),
    "mint": ("Nane", "Mint", "light", {
        "bg": "#f2f8f4", "bg2": "#e7f2eb", "surface": "#dcebe2", "surface_hover": "#cde0d4", "text2": "#56695e"}),
}
_LEGACY = {"dark": "amoled", "light": "white"}


def current_variant() -> str:
    v = prefs.get("theme", "amoled")
    v = _LEGACY.get(v, v)
    return v if v in VARIANTS else "amoled"


def current_name() -> str:
    """Tema ailesi: "dark" veya "light"."""
    return VARIANTS[current_variant()][2]


def variant_label(v):
    name = VARIANTS[v]
    return name[0] if prefs.get("language", "tr") == "tr" else name[1]


def pal() -> dict:
    v = VARIANTS[current_variant()]
    d = dict(PALETTES[v[2]])
    d.update(v[3])
    return d


def color(role: str) -> str:
    if role == "accent":
        return accent()
    if role == "white":
        return "#ffffff"
    return pal().get(role, role)


def qcolor(role: str):
    """Rol adını (veya #hex / rgba(...) metnini) QColor'a çevirir."""
    from PyQt6.QtGui import QColor
    c = color(role)
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)", c)
    if m:
        r, g, b = (int(m.group(i)) for i in (1, 2, 3))
        a = float(m.group(4)) if m.group(4) is not None else 1.0
        return QColor(r, g, b, int(round(a * 255 if a <= 1 else a)))
    return QColor(c)


def tinted_logo(height: int, dpr: float = 1.0):
    """Logoyu tema metin rengine boyar (aydınlık temada görünür olsun diye)."""
    from PyQt6.QtGui import QPixmap, QPainter
    from PyQt6.QtCore import Qt
    from .config import asset
    pm = QPixmap(asset("logo.png"))
    if pm.isNull():
        return pm
    pm = pm.scaledToHeight(int(height * dpr), Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(pm.size())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.drawPixmap(0, 0, pm)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(out.rect(), qcolor("text"))
    p.end()
    out.setDevicePixelRatio(dpr)
    return out


def stylesheet() -> str:
    c = pal()
    return f"""
* {{
    font-family: "Segoe UI Variable Text", "Segoe UI", "Roboto", sans-serif;
    font-size: 13px;
    outline: none;
}}
QMainWindow, #Root, #MainArea, #HomeView, #InfoBar, QDialog#ThemedDialog {{
    background: {c['bg']};
    color: {c['text']};
}}
QWidget {{ color: {c['text']}; }}
QToolTip {{
    background: rgba(97,97,97,0.92);
    color: #ffffff;
    border: none;
    padding: 5px 8px;
    border-radius: 4px;
    font-size: 12px;
}}
#TitleBar {{ background: {c['bg']}; }}
#Wordmark {{ font-size: 19px; font-weight: 700; letter-spacing: -0.6px; color: {c['text']}; }}

QToolButton#IconBtn, QPushButton#IconBtn {{
    background: transparent; border: none; border-radius: 18px; padding: 0px;
}}
QToolButton#IconBtn:hover, QPushButton#IconBtn:hover {{ background: {c['hover']}; }}
QToolButton#IconBtn:pressed, QPushButton#IconBtn:pressed {{ background: {c['pressed']}; }}
QToolButton#IconBtn:checked {{ background: {c['selected']}; }}
QToolButton#WinBtn {{ background: transparent; border: none; border-radius: 0px; }}
QToolButton#WinBtn:hover {{ background: {c['hover']}; }}
QToolButton#WinClose {{ background: transparent; border: none; border-radius: 0px; }}
QToolButton#WinClose:hover {{ background: #e81123; }}

/* YouTube arama kutusu */
#SearchBox {{
    background: {c['input_bg']};
    border: 1px solid {c['input_border']};
    border-right: none;
    border-top-left-radius: 20px; border-bottom-left-radius: 20px;
    padding: 0px 16px; font-size: 14px; color: {c['text']};
    selection-background-color: #3ea6ff;
}}
#SearchBox:focus {{ border: 1px solid #1c62b9; border-right: none; }}
QToolButton#SearchBtn {{
    background: {c['surface']};
    border: 1px solid {c['input_border']};
    border-top-right-radius: 20px; border-bottom-right-radius: 20px;
}}
QToolButton#SearchBtn:hover {{ background: {c['surface_hover']}; }}

/* Çipler (YouTube filtre butonları) */
QPushButton#Chip {{
    background: {c['surface']}; color: {c['text']}; border: none;
    border-radius: 8px; padding: 6px 12px; font-size: 13px; font-weight: 500;
}}
QPushButton#Chip:hover {{ background: {c['surface_hover']}; }}
QPushButton#Chip:checked {{ background: {c['chip_active_bg']}; color: {c['chip_active_fg']}; }}

/* Hap butonlar (Beğen / Paylaş satırı gibi) */
QPushButton#Pill {{
    background: {c['surface']}; color: {c['text']}; border: none;
    border-radius: 18px; padding: 0px 14px; height: 36px; font-size: 13px; font-weight: 500;
    text-align: left;
}}
QPushButton#Pill:hover {{ background: {c['surface_hover']}; }}
QPushButton#Pill:checked {{ background: rgba(62,166,255,0.22); color: {c['text']}; }}
QPushButton#Primary {{
    background: {c['button_bg']}; color: {c['button_fg']}; border: none;
    border-radius: 18px; padding: 0px 18px; height: 36px; font-size: 14px; font-weight: 600;
}}
QPushButton#Primary:hover {{ background: {'#d9d9d9' if current_name() == 'dark' else '#272727'}; }}
QPushButton#Primary:disabled {{ background: {c['surface']}; color: {c['text3']}; }}
QPushButton#Accent {{
    background: #3ea6ff; color: #0f0f0f; border: none; border-radius: 18px;
    padding: 0px 18px; height: 36px; font-size: 14px; font-weight: 600;
}}
QPushButton#Accent:hover {{ background: #65b8ff; }}
QPushButton#Flat {{
    background: transparent; color: {c['text']}; border: none; border-radius: 18px;
    padding: 0px 14px; height: 36px; font-weight: 500;
}}
QPushButton#Flat:hover {{ background: {c['hover']}; }}

#VideoTitle {{ font-size: 19px; font-weight: 700; color: {c['text']}; }}
#Secondary {{ color: {c['text2']}; font-size: 12px; }}
#SectionTitle {{ font-size: 16px; font-weight: 700; color: {c['text']}; }}
#DescBox {{ background: {c['surface']}; border-radius: 12px; }}
#DescText {{ color: {c['text']}; font-size: 13px; }}
#Divider {{ background: {c['divider']}; }}

/* Yan panel */
#Sidebar {{ background: {c['bg']}; }}
QListView#UpNext {{ background: transparent; border: none; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {c['input_bg']}; color: {c['text']};
    border: 1px solid {c['input_border']}; border-radius: 8px; padding: 5px 8px;
    selection-background-color: #3ea6ff;
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {c['card']}; color: {c['text']}; border: 1px solid {c['divider']};
    selection-background-color: {c['surface_hover']}; selection-color: {c['text']}; padding: 4px;
}}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 2px solid {c['text2']}; }}
QCheckBox::indicator:checked {{ background: #3ea6ff; border-color: #3ea6ff; }}

QSlider::groove:horizontal {{ height: 4px; background: {c['surface_hover']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {c['text']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {c['text']}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}

QProgressBar {{ background: {c['surface']}; border: none; border-radius: 3px; height: 6px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {accent()}; border-radius: 3px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c['scroll']}; border-radius: 4px; min-height: 30px; margin: 2px; }}
QScrollBar::handle:vertical:hover {{ background: {c['text3']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {c['scroll']}; border-radius: 4px; min-width: 30px; margin: 2px; }}

QMenu {{
    background: {c['card']}; color: {c['text']}; border: 1px solid {c['divider']};
    border-radius: 12px; padding: 8px 0px;
}}
QMenu::item {{ padding: 8px 36px 8px 16px; font-size: 13px; }}
QMenu::item:selected {{ background: {c['hover']}; }}
QMenu::item:disabled {{ color: {c['text3']}; }}
QMenu::separator {{ height: 1px; background: {c['divider']}; margin: 6px 0px; }}
QMenu::icon {{ padding-left: 12px; }}

QTabBar::tab {{
    background: transparent; color: {c['text2']}; padding: 8px 14px; border: none;
    border-bottom: 2px solid transparent; font-weight: 600;
}}
QTabBar::tab:selected {{ color: {c['text']}; border-bottom: 2px solid {c['text']}; }}
QTabWidget::pane {{ border: none; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QPlainTextEdit, QTextEdit {{
    background: {c['bg2']}; color: {c['text']}; border: 1px solid {c['divider']}; border-radius: 8px;
    font-family: "Cascadia Mono", "Consolas", monospace; font-size: 12px;
}}
"""


class ThemeManager(QObject):
    changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._bindings = []  # (weakref(widget), callable)

    def apply(self, name: str = None):
        """name: tema çeşidi kimliği ya da "dark"/"light" (o ailenin son seçilen çeşidi)."""
        if name in ("dark", "light"):
            name = prefs.get(name + "_variant") or ("amoled" if name == "dark" else "white")
        if name in VARIANTS:
            prefs.set("theme", name)
            prefs.set(VARIANTS[name][2] + "_variant", name)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet())
        alive = []
        for ref, fn in self._bindings:
            w = ref()
            if w is None:
                continue
            try:
                fn(w)
                alive.append((ref, fn))
            except RuntimeError:
                pass
        self._bindings = alive
        self.changed.emit(current_name())

    def bind(self, widget, fn):
        """Tema her değiştiğinde fn(widget) çağrılır (ilk çağrı hemen yapılır)."""
        self._bindings.append((weakref.ref(widget), fn))
        fn(widget)

    def icon(self, button, name: str, role: str = "text", size: int = 20):
        """Butona temaya duyarlı ikon atar; tekrar çağrılırsa ikonu günceller."""
        button._ticon = (name, role, size)

        def _apply(b):
            n, r, s = b._ticon
            b.setIcon(icons.icon(n, color(r), s))
            b.setIconSize(QSize(s, s))

        if getattr(button, "_tbound", False):
            _apply(button)
        else:
            button._tbound = True
            self.bind(button, _apply)


theme = ThemeManager()
