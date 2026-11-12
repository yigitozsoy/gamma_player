"""Derleme öncesi üretilen dosyalar: exe sürüm bilgisi ve kurulumdaki dosya ilişkilendirme listesi.

Kullanım: python packaging/make_meta.py   (build.ps1 otomatik çalıştırır)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from gammaplayer import __version__  # noqa: E402
from gammaplayer.formats import VIDEO_EXT, AUDIO_EXT, IMAGE_EXT, MODEL_EXT  # noqa: E402

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


GROUPS = (("video", "AssocVideo", VIDEO_EXT), ("audio", "AssocAudio", AUDIO_EXT),
          ("image", "AssocImage", IMAGE_EXT), ("model", "AssocModel", MODEL_EXT))

# Kurulumdaki listede en üstte görünecek yaygın türler; gerisi alfabetik
COMMON = [".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv", ".m4v", ".ts", ".mpg", ".mpeg", ".3gp",
          ".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus", ".aac", ".wma",
          ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic", ".heif", ".avif", ".tif", ".tiff",
          ".svg", ".ico", ".jxl", ".psd",
          ".stl", ".obj", ".glb", ".gltf", ".3mf", ".step", ".stp", ".ply", ".off", ".iges", ".igs"]


# Bu türler isteğe bağlı STEP motoruna bağlı: kurulumda "step" görevi seçilmediyse hiç kaydedilmez
CAD_EXT = {".step", ".stp", ".iges", ".igs"}


def ordered(exts):
    exts = [e for e in exts if e not in (".txt",)]
    return sorted(exts, key=lambda e: (COMMON.index(e) if e in COMMON else len(COMMON), e))


def iss_code():
    """Kurulumdaki "Dosya türleri" sayfasının listesini dolduran Pascal yordamı."""
    lines = ["// make_meta.py tarafından üretildi — elle düzenlemeyin",
             "procedure AddAssocItems(L: TNewCheckListBox; E: TStringList);",
             "begin"]
    for kind, msg, exts in GROUPS:
        lines.append(f"  L.AddCheckBox(CustomMessage('{msg}'), '', 0, True, True, False, True, nil); E.Add('');")
        for e in ordered(exts):
            note = "CustomMessage('AssocNeedsStep')" if e in CAD_EXT else "''"
            lines.append(f"  L.AddCheckBox('{e}', {note}, 1, True, True, False, True, nil); E.Add('{e}');")
    lines.append("end;")
    return "\n".join(lines) + "\n"


def iss_extensions():
    lines = ["; make_meta.py tarafından üretildi — elle düzenlemeyin",
             # Önceki kurulumda seçilip bu kez seçilmeyen türler kalmasın
             'Root: HKA; Subkey: "Software\\gamma\\Capabilities\\FileAssociations"; Flags: deletekey']
    for kind, _msg, exts in GROUPS:
        for e in ordered(exts):
            prog = f"gamma.{kind}"
            cad = e in CAD_EXT
            only = "; Check: WizardIsTaskSelected('step')" if cad else ""   # Check'i olmayan satırlar için
            also = " and WizardIsTaskSelected('step')" if cad else ""       # Check'i olan satırlar için
            lines.append(f'Root: HKA; Subkey: "Software\\Classes\\{e}\\OpenWithProgids"; '
                         f'ValueType: string; ValueName: "{prog}"; ValueData: ""; Flags: uninsdeletevalue{only}')
            lines.append(f'Root: HKA; Subkey: "Software\\Classes\\Applications\\gamma.exe\\SupportedTypes"; '
                         f'ValueType: string; ValueName: "{e}"; ValueData: ""{only}')
            # Kurulumdaki "Dosya türleri" sayfasında bu uzantı tikliyse:
            #  - Varsayılan uygulamalar sayfasında gamma'nın türü olur ("Varsayılan olarak ayarla" hepsini uygular)
            #  - Kullanıcı o tür için başka bir uygulama seçmemişse doğrudan gamma ile açılır
            lines.append(f'Root: HKA; Subkey: "Software\\gamma\\Capabilities\\FileAssociations"; '
                         f"ValueType: string; ValueName: \"{e}\"; ValueData: \"{prog}\"; Check: AssocSel('{e}'){also}")
            lines.append(f'Root: HKA; Subkey: "Software\\Classes\\{e}"; ValueType: string; ValueData: "{prog}"; '
                         f"Check: AssocSel('{e}'){also}")
            if kind == "model":
                # 3D dosyaların Windows'ta "algılanan türü" yok; sağ tık menüsü uzantı başına eklenir
                key = f"Software\\Classes\\SystemFileAssociations\\{e}\\shell\\GammaPlayer"
                lines.append(f'Root: HKA; Subkey: "{key}"; ValueType: string; ValueData: "{{cm:OpenWith}}"; '
                             f'Tasks: contextmenu; Flags: uninsdeletekey{only}')
                lines.append(f'Root: HKA; Subkey: "{key}"; ValueType: string; ValueName: "Icon"; '
                             f'ValueData: "{{app}}\\{{#AppExe}}"; Tasks: contextmenu{only}')
                lines.append(f'Root: HKA; Subkey: "{key}\\command"; ValueType: string; '
                             f'ValueData: """{{app}}\\{{#AppExe}}"" ""%1"""; Tasks: contextmenu{only}')
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    with open(os.path.join(HERE, "version_info.txt"), "w", encoding="utf-8") as f:
        f.write(VERSION_INFO)
    with open(os.path.join(HERE, "version.iss"), "w", encoding="utf-8-sig") as f:
        f.write(f'#define AppVersion "{__version__}"\n')
    with open(os.path.join(HERE, "extensions_registry.iss"), "w", encoding="utf-8-sig") as f:
        f.write(iss_extensions())
    with open(os.path.join(HERE, "extensions_code.iss"), "w", encoding="utf-8-sig") as f:
        f.write(iss_code())
    print(__version__)
