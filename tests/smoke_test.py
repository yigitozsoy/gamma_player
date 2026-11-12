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


# ------------------------------------------------------------------ çekirdek
@check("dosya türleri tanınıyor")
def _formats():
    exp = {"video.mp4": "video", "video.avi": "video", "song.mp3": "audio", "tone.flac": "audio",
           "image.jxl": "image", "image.heic": "image", "image.ico": "image", "anim.gif": "image",
           "vector.svg": "image", "video.srt": None}
    for f, k in exp.items():
        assert kind_of(f) == k, (f, kind_of(f))


@check("tüm görsel biçimleri açılıyor")
def _images():
    for f in ("white_bg.jpg", "image.png", "image.webp", "image.bmp", "image.tiff", "image.ico", "anim.gif",
              "image.heic", "image.avif", "image.jxl", "vector.svg"):
        li = image_io.load_image(M(f))
        assert li is not None and not li.first.isNull(), f
    assert image_io.load_image(M("anim.gif")).animated


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

    @step(2500, "video oynatılıyor")
    def _():
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
