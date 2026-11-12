"""Windows Gezgini sağ tık menüsüne "gamma ile aç" ekleme/kaldırma (yalnızca geçerli kullanıcı)."""
import os
import sys
import winreg

from .config import BASE_DIR, asset
from .formats import ALL_MEDIA_EXT

KEY_NAME = "GammaPlayer"
ROOTS = [r"Software\Classes\SystemFileAssociations\video",
         r"Software\Classes\SystemFileAssociations\audio",
         r"Software\Classes\SystemFileAssociations\image",
         r"Software\Classes\Directory"]


def _command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" "%1"'
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):
        exe = pyw
    main_py = os.path.join(BASE_DIR, "main.py")
    if os.path.exists(main_py):
        return f'"{exe}" "{main_py}" "%1"'
    return f'"{exe}" -m gammaplayer "%1"'


def _all_roots():
    roots = list(ROOTS)
    roots += [rf"Software\Classes\SystemFileAssociations\{e}" for e in sorted(ALL_MEDIA_EXT)]
    return roots


MENU_TITLE = "Open with gamma player"


def register(title=MENU_TITLE):
    cmd = _command()
    ico = sys.executable if getattr(sys, "frozen", False) else asset("logo.ico")
    for root in _all_roots():
        key = rf"{root}\shell\{KEY_NAME}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, title)
            if os.path.exists(ico):
                winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, ico)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
    _notify()


def unregister():
    for root in _all_roots() + [r"Software\Classes\*"]:
        for name in (KEY_NAME, "VLCPlus"):
            key = rf"{root}\shell\{name}"
            for sub in (key + r"\command", key):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
                except OSError:
                    pass
    _notify()


def _notify():
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except Exception:
        pass
