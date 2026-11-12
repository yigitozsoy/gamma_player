"""Derleme öncesi üretilen dosyalar: exe sürüm bilgisi ve kurulumdaki dosya ilişkilendirme listesi.

Kullanım: python packaging/make_meta.py   (build.ps1 otomatik çalıştırır)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from gammaplayer import __version__  # noqa: E402
from gammaplayer.formats import VIDEO_EXT, AUDIO_EXT, IMAGE_EXT  # noqa: E402

parts = [int(p) for p in __version__.split(".")[:3]] + [0]
ver4 = tuple((parts + [0, 0, 0, 0])[:4])
ver_str = ".".join(map(str, ver4))

VERSION_INFO = f"""# UTF-8 — make_meta.py tarafından üretildi
VSVersionInfo(
  ffi=FixedFileInfo(filevers={ver4}, prodvers={ver4}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041F04B0', [
      StringStruct('CompanyName', 'Yiğit Özsoy'),
      StringStruct('FileDescription', 'gamma medya oynatıcı'),
      StringStruct('FileVersion', '{ver_str}'),
      StringStruct('InternalName', 'gamma'),
      StringStruct('LegalCopyright', '© Yiğit Özsoy — GPL-3.0'),
      StringStruct('OriginalFilename', 'gamma.exe'),
      StringStruct('ProductName', 'gamma'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1055, 1200])])
  ]
)
"""


def iss_extensions():
    lines = ["; make_meta.py tarafından üretildi — elle düzenlemeyin"]
    groups = (("video", VIDEO_EXT), ("audio", AUDIO_EXT), ("image", IMAGE_EXT))
    for kind, exts in groups:
        for e in sorted(exts):
            if e in (".txt",):
                continue
            prog = f"gamma.{kind}"
            lines.append(f'Root: HKA; Subkey: "Software\\Classes\\{e}\\OpenWithProgids"; '
                         f'ValueType: string; ValueName: "{prog}"; ValueData: ""; Flags: uninsdeletevalue')
            lines.append(f'Root: HKA; Subkey: "Software\\Classes\\Applications\\gamma.exe\\SupportedTypes"; '
                         f'ValueType: string; ValueName: "{e}"; ValueData: ""')
            lines.append(f'Root: HKA; Subkey: "Software\\gamma\\Capabilities\\FileAssociations"; '
                         f'ValueType: string; ValueName: "{e}"; ValueData: "{prog}"')
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    with open(os.path.join(HERE, "version_info.txt"), "w", encoding="utf-8") as f:
        f.write(VERSION_INFO)
    with open(os.path.join(HERE, "version.iss"), "w", encoding="utf-8-sig") as f:
        f.write(f'#define AppVersion "{__version__}"\n')
    with open(os.path.join(HERE, "extensions_registry.iss"), "w", encoding="utf-8-sig") as f:
        f.write(iss_extensions())
    print(__version__)
