"""gamma için hızlı uçtan uca duman testi.

Çalıştırma:   python tests/smoke_test.py          (çekirdek + arayüz)
              python tests/smoke_test.py --no-gui (yalnızca çekirdek)

Gerçek tercihlere dokunmaz: LOCALAPPDATA geçici bir klasöre yönlendirilir. Test medyası ffmpeg ile
geçici klasörde üretilir ve sonunda silinir.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

TMP = tempfile.mkdtemp(prefix="gamma_test_")
os.environ["LOCALAPPDATA"] = os.path.join(TMP, "appdata")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                   # noqa: E402
from PIL import Image, ImageDraw                     # noqa: E402
from PyQt6.QtCore import QTimer                      # noqa: E402
from PyQt6.QtWidgets import QApplication             # noqa: E402

app = QApplication(sys.argv[:1])

from gammaplayer import image_io, thumbs, watermark  # noqa: E402
from gammaplayer.bgremove import remove_background   # noqa: E402
from gammaplayer.config import prefs                 # noqa: E402
from gammaplayer.formats import kind_of              # noqa: E402
from gammaplayer.image_editor import DEFAULT_STATE, render  # noqa: E402
from gammaplayer.library import Library              # noqa: E402

prefs.data["single_instance"] = False
MEDIA = os.path.join(TMP, "media")
os.makedirs(MEDIA)
results = []


def check(name):
    def deco(fn):
        t0 = time.perf_counter()
        try:
            fn()
            results.append((True, name, int((time.perf_counter() - t0) * 1000), ""))
        except Exception:
            results.append((False, name, 0, traceback.format_exc(limit=3)))
        return fn
    return deco


def ff(*a):
    subprocess.run([thumbs.FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *a], check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def M(name):
    return os.path.join(MEDIA, name)


# ------------------------------------------------------------------ test medyası
@check("ffmpeg bulundu ve medya üretildi")
def _make_media():
    assert thumbs.FFMPEG and os.path.exists(thumbs.FFMPEG), thumbs.FFMPEG
    ff("-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25", "-f", "lavfi", "-i", "sine=frequency=440",
       "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", M("video.mp4"))
    ff("-f", "lavfi", "-i", "testsrc=size=320x240:rate=25", "-t", "3", "-c:v", "mpeg4", M("video.avi"))
    ff("-f", "lavfi", "-i", "sine=frequency=330", "-f", "lavfi", "-i", "testsrc=size=300x300", "-t", "5",
       "-map", "0:a", "-map", "1:v", "-frames:v", "1", "-c:a", "libmp3lame", "-c:v", "mjpeg",
       "-disposition:v", "attached_pic", "-metadata", "title=Deneme Şarkı", "-metadata", "artist=Sanatçı",
       M("song.mp3"))
    ff("-f", "lavfi", "-i", "sine=frequency=550", "-t", "3", "-c:a", "flac", M("tone.flac"))
    ff("-f", "lavfi", "-i", "sine=frequency=660", "-t", "8", "-c:a", "aac", M("audio_only.mp4"))
    open(M("video.srt"), "w", encoding="utf-8").write("1\n00:00:00,500 --> 00:00:04,000\nMerhaba ş ğ ı\n")
    im = Image.new("RGB", (800, 500), (255, 255, 255))
    ImageDraw.Draw(im).ellipse([250, 100, 550, 400], fill=(220, 30, 60))
    ImageDraw.Draw(im).rectangle([380, 230, 420, 270], fill=(255, 255, 255))   # içteki beyaz delik
    im.save(M("white_bg.jpg"), quality=95)
    im.save(M("image.png"))
    im.save(M("image.webp"))
    im.save(M("image.bmp"))
    im.save(M("image.tiff"))
    im.save(M("image.ico"), sizes=[(16, 16), (48, 48), (256, 256)])
    frames = [Image.new("RGB", (120, 90), (i * 20, 40, 90)) for i in range(6)]
    frames[0].save(M("anim.gif"), save_all=True, append_images=frames[1:], duration=80, loop=0)
    import pillow_heif
    pillow_heif.register_heif_opener()
    im.save(M("image.heic"), quality=70)
    im.save(M("image.avif"), quality=70)
    import imagecodecs
    open(M("image.jxl"), "wb").write(imagecodecs.jpegxl_encode(np.asarray(im)))
    open(M("vector.svg"), "w").write('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
                                     '<circle cx="32" cy="32" r="30" fill="#3ea6ff"/></svg>')


def _write_models():
    """Küçük bir küpü desteklenen tüm 3D biçimlerinde yazar (yalnızca numpy)."""
    import json
    import struct
    import zipfile
    V = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)], dtype=np.float32)
    F = np.array([[0, 2, 3], [0, 3, 1], [4, 5, 7], [4, 7, 6], [0, 1, 5], [0, 5, 4],
                  [2, 6, 7], [2, 7, 3], [0, 4, 6], [0, 6, 2], [1, 3, 7], [1, 7, 5]], dtype=np.int64)
    tri = V[F]
    with open(M("cube.stl"), "wb") as f:
        f.write(b"\0" * 80 + struct.pack("<I", len(F)))
        for t_ in tri:
            f.write(struct.pack("<12fH", 0, 0, 0, *t_.reshape(-1), 0))
    with open(M("cube_ascii.stl"), "w") as f:
        f.write("solid c\n")
        for t_ in tri:
            f.write("facet normal 0 0 0\nouter loop\n" + "".join(f"vertex {a} {b} {c}\n" for a, b, c in t_)
                    + "endloop\nendfacet\n")
        f.write("endsolid c\n")
    open(M("cube.mtl"), "w").write("newmtl red\nKd 0.9 0.1 0.1\n")
    with open(M("cube.obj"), "w") as f:
        f.write("mtllib cube.mtl\nusemtl red\n" + "".join(f"v {a} {b} {c}\n" for a, b, c in V))
        f.write("".join(f"f {a + 1} {b + 1} {c + 1}\n" for a, b, c in F))
    with open(M("cube.ply"), "wb") as f:
        f.write(f"ply\nformat binary_little_endian 1.0\nelement vertex {len(V)}\nproperty float x\n"
                f"property float y\nproperty float z\nelement face {len(F)}\n"
                f"property list uchar int vertex_indices\nend_header\n".encode())
        f.write(V.tobytes())
        for a, b, c in F:
            f.write(struct.pack("<B3i", 3, a, b, c))
    with open(M("cube.off"), "w") as f:
        f.write(f"OFF\n{len(V)} {len(F)} 0\n" + "".join(f"{a} {b} {c}\n" for a, b, c in V)
                + "".join(f"3 {a} {b} {c}\n" for a, b, c in F))
    idx = F.astype(np.uint16).tobytes()
    binb = idx + b"\0" * (-len(idx) % 4) + V.tobytes()
    js = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
          "nodes": [{"mesh": 0, "translation": [5, 0, 0]}],
          "meshes": [{"primitives": [{"attributes": {"POSITION": 1}, "indices": 0, "material": 0}]}],
          "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [0.1, 0.4, 0.9, 1]}}],
          "buffers": [{"byteLength": len(binb)}],
          "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(idx)},
                          {"buffer": 0, "byteOffset": len(idx) + (-len(idx) % 4), "byteLength": V.nbytes}],
          "accessors": [{"bufferView": 0, "componentType": 5123, "count": F.size, "type": "SCALAR"},
                        {"bufferView": 1, "componentType": 5126, "count": len(V), "type": "VEC3",
                         "min": [0, 0, 0], "max": [1, 1, 1]}]}
    jb = json.dumps(js).encode()
    jb += b" " * (-len(jb) % 4)
    with open(M("cube.glb"), "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(jb) + 8 + len(binb)))
        f.write(struct.pack("<I4s", len(jb), b"JSON") + jb)
        f.write(struct.pack("<I4s", len(binb), b"BIN\0") + binb)
    xml = ('<?xml version="1.0" encoding="UTF-8"?><model xmlns="http://schemas.microsoft.com/3dmanufacturing/'
           'core/2015/02"><resources><object id="1" type="model"><mesh><vertices>'
           + "".join(f'<vertex x="{a}" y="{b}" z="{c}"/>' for a, b, c in V) + "</vertices><triangles>"
           + "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in F)
           + '</triangles></mesh></object></resources><build><item objectid="1"/></build></model>')
    with zipfile.ZipFile(M("cube.3mf"), "w") as z:
        z.writestr("3D/3dmodel.model", xml)


MODEL_FILES = ("cube.stl", "cube_ascii.stl", "cube.obj", "cube.ply", "cube.off", "cube.glb", "cube.3mf")


@check("3D modeller üretildi")
def _models_written():
    _write_models()


# ------------------------------------------------------------------ çekirdek
@check("dosya türleri tanınıyor")
def _formats():
    exp = {"video.mp4": "video", "video.avi": "video", "song.mp3": "audio", "tone.flac": "audio",
           "image.jxl": "image", "image.heic": "image", "image.ico": "image", "anim.gif": "image",
           "vector.svg": "image", "video.srt": None, "cube.stl": "model", "x.GLB": "model", "x.gltf": "model",
           "cube.3mf": "model", "cube.obj": "model", "cube.ply": "model"}
    for f, k in exp.items():
        assert kind_of(f) == k, (f, kind_of(f))


@check("tüm görsel biçimleri açılıyor")
def _images():
    for f in ("white_bg.jpg", "image.png", "image.webp", "image.bmp", "image.tiff", "image.ico", "anim.gif",
              "image.heic", "image.avif", "image.jxl", "vector.svg"):
        li = image_io.load_image(M(f))
        assert li is not None and not li.first.isNull(), f
    assert image_io.load_image(M("anim.gif")).animated


@check("3D biçimleri açılıyor (stl/obj/ply/off/glb/3mf) + küçük resim")
def _models():
    from gammaplayer.model_io import load_model, render_preview
    for f in MODEL_FILES:
        m = load_model(M(f))
        assert m.triangles == 12, (f, m.triangles)
        assert np.allclose(m.size, 1.0, atol=1e-4), (f, m.size)
    assert load_model(M("cube.stl")).vertices == 8
    assert load_model(M("cube.obj")).parts[0].color[:3] == (0.9, 0.1, 0.1)
    assert abs(load_model(M("cube.glb")).bmin[0] - 5) < 1e-5     # düğüm dönüşümü uygulandı
    img = render_preview(load_model(M("cube.glb")), 160, 90)
    assert img.width() == 160 and img.pixelColor(80, 45) != img.pixelColor(2, 2), "küçük resim boş"


@check("3D dönüştürme (stl/obj/3mf/glb/ply) ve ölçüler")
def _model_export():
    from gammaplayer.model_io import load_model, export_model, dims_text, dims_values, EXPORT_FORMATS

    def mm(model):   # fiziksel boy (mm): birimler farklı olsa da aynı kalmalı
        w, d, h, unit = dims_values(model)
        k = {"mm": 1, "cm": 10, "m": 1000}[unit]
        return np.array([w, d, h]) * k
    out = os.path.join(TMP, "model_export")   # medya klasörünü kirletmesin
    os.makedirs(out, exist_ok=True)
    assert dims_text(load_model(M("cube.stl")), "tr") == "1 × 1 × 1 mm"
    assert dims_text(load_model(M("cube.glb")), "en") == "1 × 1 × 1 m"    # glTF birimi metre
    for src in ("cube.stl", "cube.glb", "cube.obj"):
        m = load_model(M(src))
        for _label, ext in EXPORT_FORMATS:
            dst = os.path.join(out, src.replace(".", "_") + ext)
            export_model(m, dst)
            m2 = load_model(dst)
            assert m2.triangles == 12, (src, ext, m2.triangles)
            assert np.allclose(mm(m2), mm(m), rtol=1e-4), (src, ext, dims_text(m2), dims_text(m))
    # hacim / alan / kapalılık: 1 mm küp
    from gammaplayer.model_io import model_stats
    st = model_stats(load_model(M("cube.stl")))
    assert abs(st["volume"] - 1) < 1e-6 and abs(st["area"] - 6) < 1e-6 and st["closed"] is True, st
    st = model_stats(load_model(M("cube.glb")))
    assert abs(st["volume"] - 1e9) < 1 and st["closed"] is True, st   # 1 m³ = 1e9 mm³
    from gammaplayer.model_io import Model, Part
    open_box = Model([Part(load_model(M("cube.stl")).parts[0].pos[:-3])], "STL")   # bir üçgeni eksik
    assert model_stats(open_box)["closed"] is False
    # renk korunuyor (OBJ'deki kırmızı malzeme → GLB)
    m2 = load_model(os.path.join(out, "cube_obj.glb"))
    assert np.allclose(m2.parts[0].color[:3], (0.9, 0.1, 0.1), atol=1e-3), m2.parts[0].color


@check("3MF hızlı okuma: boya öznitelikleri, üçgen renkleri, önekli ad alanı")
def _3mf_variants():
    import zipfile
    from gammaplayer.model_io import load_model
    base = load_model(M("cube.3mf"))
    V = [(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)]
    F = [(0, 2, 3), (0, 3, 1), (4, 5, 7), (4, 7, 6), (0, 1, 5), (0, 5, 4),
         (2, 6, 7), (2, 7, 3), (0, 4, 6), (0, 6, 2), (1, 3, 7), (1, 7, 5)]
    ns = 'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
    verts = "".join(f'<vertex x="{a}" y="{b}" z="{c}"/>' for a, b, c in V)

    def write(name, tris, pre="", res=""):
        xml = (f'<?xml version="1.0"?><{pre}model {ns.replace("xmlns", "xmlns:m") if pre else ns}><{pre}resources>{res}'
               f'<{pre}object id="1" type="model"><{pre}mesh><{pre}vertices>'
               + verts.replace("<vertex", f"<{pre}vertex") + f"</{pre}vertices><{pre}triangles>" + tris
               + f'</{pre}triangles></{pre}mesh></{pre}object></{pre}resources><{pre}build><{pre}item objectid="1"/>'
               f'</{pre}build></{pre}model>')
        with zipfile.ZipFile(M(name), "w") as z:
            z.writestr("3D/3dmodel.model", xml)
        return load_model(M(name))
    # Bambu: yalnızca bazı üçgenlerde paint_color
    m = write("paint.3mf", "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"' + (' paint_color="4"' if i % 3 == 0 else "")
                                   + "/>" for i, (a, b, c) in enumerate(F)))
    assert m.triangles == 12 and np.allclose(m.parts[0].pos, base.parts[0].pos), "paint_color"
    # üçgen başına renk (p1)
    res = '<basematerials id="5"><base name="r" displaycolor="#FF0000"/><base name="b" displaycolor="#0000FF"/></basematerials>'
    m = write("p1.3mf", "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}" pid="5" p1="{i % 2}"/>'
                                for i, (a, b, c) in enumerate(F)), res=res)
    assert m.triangles == 12 and m.parts[0].col is not None, "p1"
    assert np.allclose(m.parts[0].col[0], (1, 0, 0)) and np.allclose(m.parts[0].col[3], (0, 0, 1)), m.parts[0].col[:6]
    # ad alanı önekli yazım (m:mesh)
    m = write("prefix.3mf", "".join(f'<m:triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in F), pre="m:")
    assert m.triangles == 12 and np.allclose(m.size, 1.0), "önek"
    for f in ("paint.3mf", "p1.3mf", "prefix.3mf"):
        os.remove(M(f))


@check("3D küçük resim sınırları (dosya sayısı / MB)")
def _model_thumb_limits():
    from gammaplayer.library import MediaItem
    from gammaplayer import layout_prefs as lp
    svc = thumbs.ThumbnailService()
    svc.ensure = lambda it: None
    items = []
    for i in range(30):
        it = MediaItem.__new__(MediaItem)
        it.path, it.kind, it.size, it.mtime = f"C:/x/m{i:02}.stl", "model", 1024 * 1024, 0
        items.append(it)
    items[16].size = 30 * 1024 * 1024
    svc.request(items, items[15])
    skipped = [i for i, it in enumerate(items) if svc._skip_model(it)]
    assert len(skipped) == 11 and 16 in skipped and 15 not in skipped, skipped   # 20 yakın + 1 büyük dosya
    assert 0 in skipped and 29 in skipped, skipped
    lp.prefs.data["model_thumb_count"], lp.prefs.data["model_thumb_mb"] = 0, 0
    svc.request(items, items[15])
    assert not any(svc._skip_model(it) for it in items)
    del lp.prefs.data["model_thumb_count"], lp.prefs.data["model_thumb_mb"]


@check("STEP / IGES (gmsh varsa): açılış, tam hacim, Türkçe yol")
def _step():
    from gammaplayer.model_io import cad_available, load_model, model_stats, dims_text
    if not cad_available():
        print("  (gmsh kurulu değil, STEP testi atlandı)")
        return
    # 10 × 20 × 30 mm kutu + r=5 silindir; ayrı süreçte üretilir (gmsh tek örnekli, uygulamanınkini bozmasın)
    step = os.path.join(MEDIA, "küp şekil.step")
    raw = os.path.join(TMP, "cad.step")
    code = ("import gmsh,sys; gmsh.initialize(interruptible=False); gmsh.option.setNumber('General.Terminal',0);"
            "gmsh.model.occ.addBox(0,0,0,10,20,30); gmsh.model.occ.addCylinder(50,0,0,0,0,10,5);"
            "gmsh.model.occ.synchronize(); gmsh.write(sys.argv[1]); gmsh.finalize()")
    subprocess.run([sys.executable, "-c", code, raw], check=True, timeout=60,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    shutil.copy(raw, step)
    m = load_model(step)
    assert m.fmt == "STEP" and m.triangles > 12, (m.fmt, m.triangles)
    st = model_stats(m)
    exp = 10 * 20 * 30 + np.pi * 25 * 10
    assert abs(st["volume"] - exp) < 1e-3 * exp and st["closed"] is True, st
    assert dims_text(m, "tr").endswith("mm"), dims_text(m, "tr")
    m2 = load_model(step)   # önbellekten: aynı sonuç, dönüşüm iki kez uygulanmamalı
    assert np.allclose(m2.size, m.size), (m2.size, m.size)


@check("görsel dönüştürme (png/jpg/webp/bmp/tiff/ico)")
def _convert():
    src = image_io.open_pil(M("white_bg.jpg"))
    for ext in ("png", "jpg", "webp", "bmp", "tiff", "ico"):
        out = os.path.join(TMP, "conv." + ext)
        image_io.save_pil(src, out)
        assert os.path.getsize(out) > 0, ext
        Image.open(out).load()
    ico = Image.open(os.path.join(TMP, "conv.ico"))
    assert ico.size[0] == ico.size[1], ico.size          # kare simge


@check("arka plan kaldırma (beyaz zemin, iç delik korunur)")
def _bgremove():
    src = image_io.open_pil(M("white_bg.jpg"))
    out = remove_background(src, None, 20, True, 6)
    a = np.asarray(out.getchannel("A"))
    assert a[5, 5] == 0 and a[-5, -5] == 0, "köşeler saydam değil"
    assert a[150, 400] == 255, "nesne silinmiş"
    assert a[250, 400] == 255, "nesnenin içindeki beyaz delik silinmiş (yalnızca kenar modu)"
    out2 = remove_background(src, (255, 255, 255), 20, False, 6)
    assert np.asarray(out2.getchannel("A"))[250, 400] == 0
    st = dict(DEFAULT_STATE, bg={"color": None, "tol": 20, "edge": True, "feather": 6})
    r = render(src, st, final=True)
    assert r.mode == "RGBA"
    image_io.save_pil(r, os.path.join(TMP, "nobg.ico"))
    ico = Image.open(os.path.join(TMP, "nobg.ico")).convert("RGBA")
    assert ico.getpixel((0, 0))[3] == 0, "ICO saydam değil"


@check("ffmpeg: süre, çözünürlük, kare, kapak, etiket, dalga formu")
def _ffmpeg():
    err = thumbs.probe(M("video.mp4"))
    assert 5500 <= thumbs.parse_duration(err) <= 6500
    assert thumbs.parse_resolution(err) == (640, 360)
    assert not thumbs.grab_frame(M("video.mp4"), 2000, 320).isNull()
    assert not thumbs.grab_frame(M("video.mp4"), 4000, 320, accurate=True).isNull()
    assert not thumbs.extract_cover(M("song.mp3")).isNull()
    tg = thumbs.media_tags(M("song.mp3"))
    assert tg["tags"].get("title") == "Deneme Şarkı", tg
    assert tg["info"].get("hz"), tg
    assert not thumbs.waveform(M("tone.flac"), 400, 60).isNull()


@check("klasör tarama ve sıralama")
def _library():
    lib = Library()
    lib.open_path(M("video.mp4"))
    assert lib.current is not None and lib.current.name == "video.mp4"
    assert not any(i.path.endswith(".srt") for i in lib.all_items)
    for s in Library.SORTS:
        lib.set_sort(s)
        assert len(lib.items) == len(lib.all_items), s


@check("filigran çizimi")
def _watermark():
    prefs.data.update(wm_text_on=True, wm_text="gamma", wm_pos="br")
    img = watermark.render(640, 360)
    prefs.data.update(wm_text_on=False)
    arr = img.constBits().asstring(img.sizeInBytes())
    assert any(arr[3::4]), "yazı çizilmedi"


@check("çeviri anahtarları tanımlı")
def _i18n():
    import glob
    import re
    from gammaplayer.i18n import S
    used = set()
    for f in glob.glob(os.path.join(ROOT, "gammaplayer", "*.py")):
        used |= set(re.findall(r'\bt\(\s*"([a-z0-9_]+[a-z0-9])"', open(f, encoding="utf-8").read()))
    missing = sorted(k for k in used - set(S) if not k.endswith("_") and k != "anahtar")
    assert not missing, missing


# ------------------------------------------------------------------ arayüz
def gui_tests(done):
    from gammaplayer.theme import theme
    theme.apply()
    from gammaplayer.window import MainWindow
    from gammaplayer import dialogs
    w = MainWindow([M("video.mp4")])
    w.show()
    steps = []

    def step(delay, name):
        def deco(fn):
            steps.append((delay, name, fn))
            return fn
        return deco

    state = {}

    @step(2500, "video oynatılıyor")
    def _():
        state["hwnd"] = int(w.winId())
        assert w.engine is not None, "VLC motoru yok"
        assert w.engine.is_playing(), "oynatılmıyor"
        assert w.engine.get_length() > 5000

    @step(10, "ileri sarma ve duraklatma")
    def _():
        w.engine.set_time(3000)
        w.toggle_play()

    @step(1000, "duraklatıldı / döngü modları")
    def _():
        assert not w.engine.is_playing(), "duraklatılamadı"
        w.cycle_loop()
        w.cycle_loop()
        w.cycle_loop()

    @step(10, "videodan görsele geçiş (<1 sn)")
    def _():
        t0 = time.perf_counter()
        w.play_item(w.lib.find(M("white_bg.jpg"), w.lib.all_items))
        ms = (time.perf_counter() - t0) * 1000
        assert ms < 1000, f"{ms:.0f} ms"

    @step(1200, "görsel gösteriliyor")
    def _():
        assert w.current.name == "white_bg.jpg"

    @step(10, "görsel düzenleyici açılıyor")
    def _():
        w._open_image_editor()
        assert w._edit_panel is not None, "düzenleyici açılmadı"

    @step(1500, "görsel düzenleyici: damlalıkla arka plan kaldırma")
    def _():
        from PyQt6.QtCore import QPointF
        p = w._edit_panel
        assert p.proxy is not None, "görsel yüklenmedi"
        p._bg_pick()
        assert getattr(w.viewer, "pick_mode", False)
        w.viewer.picked.emit(QPointF(3, 3))               # köşedeki beyaz piksel
        assert p.state["bg"] and tuple(p.state["bg"]["color"]) == (255, 255, 255), p.state["bg"]
        assert p._target_ext() == ".png", p._target_ext()   # jpg saydamlık için png olur
        p._save(os.path.join(TMP, "editor_out.png"))

    @step(2000, "düzenleyici çıktısı saydam PNG")
    def _():
        out = Image.open(os.path.join(TMP, "editor_out.png"))
        assert out.mode == "RGBA" and out.getpixel((2, 2))[3] == 0
        p = w._edit_panel
        p.state = dict(DEFAULT_STATE)
        p.history.clear()
        w._close_image_editor()

    @step(10, "hızlı dönüştürme: ICO")
    def _():
        w.quick_convert(w.current, ".ico")

    @step(1500, "ICO dosyası oluştu")
    def _():
        assert os.path.exists(M("white_bg.ico"))

    @step(10, "saydam görselin zemin rengi (sağ tık)")
    def _():
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QImage, QColor
        img = QImage(40, 40, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        w.viewer.set_image(img)
        assert w.viewer.has_alpha()
        m = QMenu()
        w._add_alpha_bg_menu(m)
        acts = [a for a in m.actions()[0].menu().actions() if a.text()]
        assert acts[0].isChecked(), "varsayılan dama değil"
        acts[1].trigger()                                   # siyah
        assert prefs.get("image_alpha_bg") == "#000000" and w.viewer.alpha_bg == "#000000"
        g = w.viewer.grab().toImage()
        assert g.pixelColor(g.width() // 2, g.height() // 2).name() == "#000000"
        acts[0].trigger()
        assert w.viewer.alpha_bg == "checker"
        w._load_image(w.current)

    @step(10, "tercihler penceresi tüm kategoriler")
    def _():
        d = dialogs.PreferencesDialog(w)
        d.show()
        for i in range(d.nav.count()):
            d.nav.setCurrentRow(i)
            QApplication.processEvents()
        d.reject()

    @step(10, "tema değişimi")
    def _():
        theme.apply("light")
        theme.apply("dark")

    @step(10, "ses dosyası ve etiketler")
    def _():
        w.play_item(w.lib.find(M("song.mp3"), w.lib.all_items))

    @step(3000, "ses oynatılıyor")
    def _():
        assert w.engine.is_playing()

    @step(10, "3D model açılıyor")
    def _():
        w.play_item(w.lib.find(M("cube.glb"), w.lib.all_items))
        assert w.stack.currentIndex() == 4, w.stack.currentIndex()

    @step(1500, "3D model çiziliyor (OpenGL)")
    def _():
        v = w.viewer3d
        assert v is not None and v.model is not None, "model yüklenmedi"
        img = v.image()
        assert v._gl is not None, "OpenGL yok: " + v._gl_error
        assert v._gpu, "GPU'ya yüklenmedi"
        c = img.pixelColor(img.width() // 2, img.height() // 2)
        assert c != img.pixelColor(3, 3), "model görünmüyor"
        w.toggle_slideshow()
        assert v.autorotate
        w._fit_toggle()
        w._rotate_clicked()
        v.set_wireframe(True)
        v.image()
        w.toggle_slideshow()
        assert not v.autorotate

    @step(10, "3D: ölçü kutusu ve saydam PNG")
    def _():
        v = w.viewer3d
        v.set_wireframe(False)
        plain = v.image()
        v.set_dims(True)
        with_dims = v.image()
        assert plain.size() == with_dims.size()
        assert plain != with_dims, "ölçü kutusu çizilmedi"
        tr = v.image(transparent=True)
        assert tr.hasAlphaChannel() and tr.pixelColor(0, 0).alpha() == 0, "arka plan saydam değil"
        assert tr.pixelColor(tr.width() // 2, tr.height() // 2).alpha() > 200, "model yok"
        v.set_dims(False)

    @step(10, "3D: sonraki model ve bilgi")
    def _():
        cur = w.current
        w.play_next()
        assert w.current is not cur and w.current.is_model, w.current.name
        d = dialogs.MediaInfoDialog(w.current, w)
        d.show()
        d.reject()

    @step(1200, "3D modelden videoya dönüş")
    def _():
        w.play_item(w.lib.find(M("video.mp4"), w.lib.all_items))
        assert w.stack.currentIndex() == 1 and not w.viewer3d.autorotate

    @step(2500, "3D'den sonra video görüntüsü var, pencere yeniden oluşmadı")
    def _():
        assert int(w.winId()) == state["hwnd"], "ana pencere yeniden oluşturuldu (3D görüntüleyici)"
        assert w.engine.is_playing() and w.engine.has_video(), "görüntü yok (yalnızca ses)"
        assert w.stack.currentIndex() == 1, w.stack.currentIndex()

    @step(10, "yalnızca ses içeren mp4")
    def _():
        w.play_item(w.lib.find(M("audio_only.mp4"), w.lib.all_items))

    @step(3500, "yalnızca ses içeren mp4 müzik görünümünde")
    def _():
        assert w.stack.currentIndex() == 2, w.stack.currentIndex()

    @step(10, "video düzenleyici açılıyor")
    def _():
        from gammaplayer.video_editor import VideoEditorDialog
        d = VideoEditorDialog(w.lib.find(M("video.mp4"), w.lib.all_items), w)
        d.show()
        QApplication.processEvents()
        args = d.build_args()
        assert args, "ffmpeg argümanları boş"
        d.reject()

    def run(i=0):
        if i >= len(steps):
            w.close()
            done()
            return
        d, name, fn = steps[i]

        def go():
            t0 = time.perf_counter()
            try:
                fn()
                results.append((True, "arayüz: " + name, int((time.perf_counter() - t0) * 1000), ""))
            except Exception:
                results.append((False, "arayüz: " + name, 0, traceback.format_exc(limit=3)))
            run(i + 1)
        QTimer.singleShot(d, go)
    QTimer.singleShot(500, run)


def finish():
    ok = sum(1 for r in results if r[0])
    for passed, name, ms, err in results:
        print(("  OK  " if passed else " FAIL ") + f"{name}" + (f"  ({ms} ms)" if passed else ""))
        if err:
            print("       " + err.strip().replace("\n", "\n       "))
    print(f"\n{ok}/{len(results)} başarılı")
    shutil.rmtree(TMP, ignore_errors=True)
    sys.stdout.flush()
    os._exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if "--no-gui" in sys.argv:
        finish()
    QTimer.singleShot(60000, lambda: (results.append((False, "zaman aşımı", 0, "")), finish()))
    gui_tests(finish)
    app.exec()
