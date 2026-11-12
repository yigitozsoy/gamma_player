# gamma — Claude için proje notları

Bu dosya Claude Code'un her oturumda okuduğu proje belleği. Önceki uzun geliştirme sohbetinin özeti:
proje ne, nasıl çalışıyor, geliştirici nasıl çalışmayı seviyor, nelerde dikkatli olmak gerekiyor.
Yeni bir işe başlamadan önce baştan sona oku.

---

## 1. Proje nedir

**gamma**, Yiğit Özsoy'un Windows için yazdığı, **YouTube görünümlü, VLC motorlu evrensel medya oynatıcısı**.
Video, müzik ve görselleri tek pencerede açar; içinde görsel ve video düzenleyici vardır.

- Repo: https://github.com/yigitozsoy/gamma_player (herkese açık, GPL-3.0)
- Sürüm tek yerde: `gammaplayer/__init__.py` → `__version__`
- Dil: Python 3.13/3.14 · PyQt6 · python-vlc (libVLC 3.0.x) · Pillow + pillow-heif + imagecodecs (JPEG XL) ·
  imageio-ffmpeg (ffmpeg ikilisi) · numpy
- Yalnızca **Windows 10/11 64-bit** hedefleniyor. Win32 API'leri (ctypes) serbestçe kullanılıyor.
- Arayüz metinleri **Türkçe varsayılan**, İngilizce ikinci dil.

### Geçmiş
Proje önce başka bir yapay zekâ aracıyla (Antigravity) başladı, sonra Claude ile baştan yeniden yazıldı.
Eski kod repoda değil, `C:\Users\yigit\OneDrive\Desktop\gamma_arsiv\` içinde (`_eski_kod`, örnek video).
O klasöre dokunma, kullanıcı istemedikçe silme.

---

## 2. Geliştiriciyle çalışma tarzı (EN ÖNEMLİ BÖLÜM)

### İletişim
- Kullanıcı **Türkçe**, gündelik ve hızlı yazar; yazım hataları olur, niyeti anla. Cevapları **Türkçe** ver.
- Genelde **ekran görüntüsü + kısa cümle** ile istek verir: "bu niye mor, youtubedaki böyle", "bunlar defaultta
  burda olmasın". Görüntüdeki **tam olarak işaret edilen yeri** değiştir, fazlasını yapma.
- Bir mesajda **çok sayıda istek** sıralar. Hepsini tek tek yap, hiçbirini atlama; sonunda madde madde neyin
  yapıldığını yaz. Yapamadığın ya da doğrulayamadığın bir şey varsa açıkça söyle.
- Teknik terim bilmeyebilir. Sonucu **kullanıcının gözünden** anlat ("artık sağ tık menüsünde ICO'ya çevir var"),
  iç detayları (fonksiyon adları, mimari) yalnızca gerekiyorsa kısaca.
- Soru sormak yerine **makul varsayılanla ilerle** ve ne seçtiğini söyle. Gerçekten kullanıcıya ait bir karar
  varsa (isim, herkese açık bir şey yayınlamak) sor.
- "Yok onu ben yaptım" gibi düzeltmeler gelir: test sırasında kullanıcı da uygulamayı elle kullanıyor olabilir,
  beklenmeyen bir durum görünce hemen kodu suçlama.

### Tasarım zevki
- **Referans her zaman YouTube**: düzen, zaman çubuğu, ses kaydırıcısı, tam ekran simgesi, duraklat/oynat
  animasyonu (ortada büyüyerek kaybolan daire), tooltip rengi, 2x hız (sağ tarafa basılı tutunca). Kullanıcı
  "YouTube'daki gibi" derse **birebir benzet**, yorum katma.
- **Sade varsayılanlar, her şey açılıp kapatılabilir.** Kullanıcının sevdiği desen:
  1. Yeni özellik eklenir,
  2. **varsayılanda gizli/kapalı** gelir (arama çubuğu, dosya aç düğmeleri, ekran görüntüsü / 16:9 germe düğmeleri),
  3. **Tercihler › Kişiselleştirme**'den açılır, yeri değiştirilebilir.
  Yani: *"çok fazla kişiselleştirme ekle ama default böyle gelsin."* Varsayılan görünümü bozma.
- Renk: **gri vurgu rengi** (kırmızı değil), AMOLED siyah koyu tema; 5 koyu + 5 açık tema çeşidi var.
  Mor/eflatun tonlar istemiyor (bir kez tooltip yanlışlıkla mor çıktı, şikâyet etti).
- Gereksiz tekrar sevmez: aynı düğme iki yerde olmasın (ör. "Düzenle" iki kez vardı, teke indirildi;
  dosya aç düğmeleri logoya basınca zaten çıkıyor, üst çubuktan kaldırıldı).
- Simgeler karışmasın: oynatıcı ayarları ⚙, uygulama tercihleri "•••" (gamma yazısıyla hizalı).
- Hizalama ve oran detaylarına dikkat eder (simge yazıyla ortalı mı, önizleme kutusu fazla büyük mü).
- Hızlı ve akıcı his ister: zaman sayacı takılmadan aksın, animasyonlar YouTube kadar yumuşak olsun.

### İş akışı kuralları
- **Her değişiklikten sonra kurulum dosyası DERLEME.** Derleme ~4-5 dk sürüyor ve kullanıcı arka arkaya
  istek veriyor. Kaynakta yap, test et, "derlenmedi" de. Kullanıcı "bitti / derle" deyince derle.
- Önce **gerçekten çalıştırıp doğrula**, sonra "oldu" de. Kullanıcı "test et, güzel oluyor mu bak" der.
- Commit/push **yalnızca istenince**. Herkese açık yayın (push, etiket, release) öncesi onay al.
- Kişisel bilgileri (e-posta vb.) koda, commit'e, dış servislere koyma. Commit kimliği bu repoda yerel
  olarak `Yiğit Özsoy <yigitozsoy@users.noreply.github.com>` ayarlı.

---

## 3. Klasör yapısı

```
main.py                 kaynaktan başlatıcı (python main.py [dosya|klasör])
gammaplayer/
  app.py                giriş: tek örnek (QLocalServer), --new-window, Türkçe Qt çevirisi, restart()
  window.py             MainWindow: düzen, oynatma, PiP, pin, tam ekran, Snap, dosya işlemleri (en büyük dosya)
  overlay.py            video üstü kontroller (ayrı saydam üst pencere, aşağıya bak)
  popup_menu.py         ⚙ menü altyapısı · player_menu.py menü sayfaları
  sidebar.py            sağdaki "Bu klasörde" listesi (model + delegate, küçük resimler)
  titlebar.py           özel başlık çubuğu (çerçevesiz pencere)
  views.py              ana sayfa, müzik görünümü (kapak + etiketler), alttaki bilgi çubuğu
  image_viewer.py       zoom/pan/kırpma/damlalık
  model_io.py           3D okuma (STL/OBJ/PLY/OFF/glTF/GLB/3MF, numpy) + yazılımla küçük resim çizimi
  model_viewer.py       3D görüntüleyici (QOpenGLWidget, GLSL 1.20; döndür/kaydır/yakınlaştır)
  image_editor.py       görsel düzenleyici paneli (render() saf fonksiyon, DEFAULT_STATE)
  video_editor.py       kes/kırp/filigran/altyazı gömme diyaloğu (ffmpeg komutu üretir)
  bgremove.py           arka plan kaldırma (numpy, kenara bağlı bölge yayılımı)
  watermark.py          yazı/logo filigranı (Qt ile PNG çizilir, ffmpeg overlay)
  vlc_engine.py         libVLC sarmalayıcı
  thumbs.py             ffmpeg: küçük resim, süre, kare önizleme, kapak, etiket, dalga formu; iş havuzu
  image_io.py           tüm görsel formatlarını okuma/yazma (HEIC/JXL tembel yüklenir)
  library.py            klasör tarama, sıralama (Gezgin sırası dahil), MediaItem
  config.py             yollar, Prefs (%LOCALAPPDATA%\gamma\preferences.json)
  layout_prefs.py       kişiselleştirme: düğme sırası/görünürlüğü, davranış ayarları
  theme.py              temalar, vurgu renkleri, stil sayfası
  icons.py              Material SVG yolları · i18n.py  t("anahtar") metinleri (tr, en)
  dialogs.py            Tercihler (kategorili), Medya bilgisi, Kısayollar, Dönüştür
  shortcuts.py · formats.py · shell.py (sağ tık menüsü kaydı) · widgets.py (ToggleSwitch vb.)
  assets/               logo.png (beyaz Γ, arayüzde renklendirilir), logo.ico
tests/smoke_test.py     uçtan uca test (çekirdek + gerçek arayüz)
packaging/              build.ps1, gamma.spec (PyInstaller), installer.iss (Inno Setup), make_meta.py
.github/workflows/build.yml   v* etiketi gelince derleyip Releases'a koyar
docs/                   README ekran görüntüleri
```

---

## 4. Mimari ve bilinen tuzaklar

Bunlar zor bulunmuş şeyler. Değiştirmeden önce nedenini anla.

- **Overlay ayrı pencere:** VLC kendi yerel (native) HWND'sine çizer; Qt widget'ları üstünde görünmez
  ("airspace" sorunu). Bu yüzden video kontrolleri `Qt.Tool | WindowDoesNotAcceptFocus` olan **ayrı, çerçevesiz,
  saydam bir üst pencere** (`overlay.py`). Fare olaylarını yakalamak için alfa=1 dolgu kullanılıyor.
  Ana pencere taşınınca/boyutlanınca overlay'in konumu senkronlanır.
- **Native kardeş widget'lar:** `AA_DontCreateNativeWidgetSiblings` + video_host'ta `WA_NativeWindow` ve
  `WA_DontCreateNativeAncestors`. Bu olmazsa başlık çubuğu da native olur ve **pencere sürüklenemez**.
- **Windows Snap:** pencere çerçevesiz ama WS_THICKFRAME/WS_CAPTION stilleri ekli; `nativeEvent` içinde
  WM_NCCALCSIZE (büyütülünce çalışma alanı) ve WM_NCHITTEST (boş başlık çubuğu = HTCAPTION, kenarlar)
  işleniyor. Başlık çubuğunda ayrıca `startSystemMove` yedeği var.
- **VLC motoru tembel:** açılışı hızlandırmak için `_ensure_engine()` ile ilk event döngüsünde ya da ilk
  oynatılabilir dosyada oluşturulur. `self.engine` None olabilir, kullanmadan önce kontrol et.
- **Küçük resimler tembel:** `ThumbnailService.request()` yalnızca açık dosyanın ±40 komşusunu kuyruğa alır;
  geri kalanı sidebar satırı çizilince `ensure()` ile istenir.
- **Thread kuralı:** iş parçacıklarında yalnızca QImage/PIL; QPixmap'i ana iş parçacığında üret.
- **QSS renk tuzağı:** `#606060f0` Qt'de **#AARRGGBB** olarak okunur (tooltip mor çıktı). Saydam renk için
  `rgba(...)` yaz. `QColor("rgba(...)")` geçersiz, `theme.qcolor()` kullan.
- **pyqtProperty adı** `pos` gibi QWidget metotlarıyla çakışmasın (ToggleSwitch'te `knob`).
- **Filigran WYSIWYG:** önizlemede ve çıktıda aynı Qt PNG'si kullanılır (`scale2ref` + `overlay`).
- **Altyazı gömme:** `setpts=PTS+A/TB,subtitles=...,setpts=PTS-STARTPTS` (kesilen parçada zamanlama doğru kalsın).
  Windows yolunda iki nokta kaçışı: `C\:/...`.
- **Gezgin sırası:** varsayılan sıralama, klasörün Windows Gezgini'ndeki sırası (PowerShell Shell.Application COM).
- **ffmpeg yolu:** `thumbs._find_ffmpeg()` imageio_ffmpeg'i import etmeden ikiliyi bulur (donmuş exe'de `_MEIPASS`).
- **Donmuş (PyInstaller) exe:** VLC `<exe>\vlc\` içine gömülü; önce oraya, sonra Program Files VLC'ye bakılır.
- **3D (3.0):** `ModelViewer` ilk modelde oluşturulur (PAGE_MODEL = 4, `model_host` içinde). Alttaki kontrol
  satırı resim satırıyla ortak (`overlay.set_model_mode`): slayt düğmesi = otomatik döndür, sığdır = görünümü
  sıfırla, döndür = modeli çevir. **QOpenGLWidget KULLANMA:** ana pencereye ilk eklenince Qt bütün pencereyi
  yeniden oluşturuyor (HWND değişir → pencere kapanıp açılır, VLC görüntüsü kaybolur, Snap stilleri gider).
  Çizim `_GLView(QOpenGLWindow)` içinde, `createWindowContainer` ile (WA_DontCreateNativeAncestors); `ModelViewer`
  bir QWidget sarmalayıcıdır ve `__getattr__` ile her şeyi `_GLView`'e aktarır. `QT_WIDGETS_RHI` ile baştan
  OpenGL'li pencere de çözer ama açılışa ~0,7 sn ekliyor. `image()` her zaman FBO'ya yeniden çizer; kapanışta
  `release_gl` (aboutToQuit). Smoke test 3D'den sonra pencere kimliğinin değişmediğini denetler.
- **Yalnızca ses içeren mp4:** VLC "vout 0" olayını her zaman göndermiyor; `load_item` her videoda 1,2 sn sonra
  `_check_audio_only` çağırır. Karar `has_vout` + `video_track_count()` ile verilir (görüntü geç gelse de yanılmaz).
- **Kapanışta çökme:** küçük resim işi (büyük model) uygulama kapanırken sürüyorsa silinmiş sinyale emit → PyQt
  abort (0xC0000409). `_ThumbJob._emit` + `ThumbnailService.closed` (aboutToQuit'te shutdown) bunu engeller. Modeller Y-yukarıya çevrilir (STL/PLY/OFF/3MF Z-yukarı kabul edilir).
  `gamma.spec`'te QtOpenGL / QtOpenGLWidgets artık hariç tutulmamalı.
  İç UV düzeni OBJ gibidir (v=0 resmin altı); glTF okurken 1-v yapılır, GL'ye doku `flipped(Vertical)` yüklenir.
  Ölçüler (`D`, `model_dims`, varsayılan kapalı): glTF metre, diğerleri mm kabul edilir (`dims_unit`).
  Saydam PNG: `ModelViewer.image(transparent=True)` ekran dışı FBO'da 2 kat çizer, boşluğu kırpar.
  Dönüştürme: `model_io.export_model` → STL/OBJ(+mtl+png)/3MF(renkli)/GLB/PLY; metre↔mm ve Y↔Z-yukarı çevrilir.
- **3MF okuma hızı:** `<mesh>` blokları ElementTree'ye verilmez (`_cut_meshes`); köşe/üçgenler tırnak içi
  değerlerden numpy ile okunur (`_quoted_cols`), Bambu'nun `paint_color` gibi öznitelikleri önce atılır, olmazsa
  düzenli ifade yoluna düşülür. Kullanıcı gömülü 3MF önizleme resmini istemedi (kendi çizimimiz kalsın).
- **3D küçük resim sınırları:** `model_thumb_count` (açık dosyaya en yakın N model, listede görünen sıraya göre,
  varsayılan 20) ve `model_thumb_mb` (varsayılan 20 MB). Sınır dışı model önbelleğe "resim yok" yazılmadan simgeyle
  gösterilir; açılınca yüklü modelden çizilir (`store_model_thumb`). Model küçük resimleri `_MODEL_LOCK` ile tek tek.
- **STEP / IGES (isteğe bağlı):** motor gmsh (OpenCASCADE içinde, tek ~85 MB DLL). Exe'ye gömülmez
  (`gamma.spec` EXCLUDES "gmsh"); build.ps1 `gmsh.py` + DLL'i `build\dist\gamma\step\` içine kopyalar, kurulumda
  "step" görevi (Ek bileşenler, varsayılan tikli) seçilmezse klasör kurulmaz/silinir ve CAD uzantıları kaydedilmez.
  `model_io.load_cad`: `occ.importShapes` + `mesh.importStl()` (hızlı BRepMesh; `generate` çok yavaş), renk yüzey →
  hacim sırasıyla, hacim/alan `occ.getMass` ile kesin (üçgenler kapalı değil). gmsh iş parçacığı güvenli değil →
  kilit; Türkçe/Unicode yolu açamaz → geçici ASCII kopya; tek girişlik önbellek her çağrıda yeni Part döndürür
  (Z-yukarı çevirisi iki kez uygulanmasın). gmsh yoksa `ModelError("cad_missing")`. Gezgin küçük resmi yok.
- **Gezgin küçük resimleri (STL/OBJ/PLY/OFF/GLB/glTF):** `packaging/thumbnail/GammaThumbs.cs` — .NET Framework 4
  COM sunucusu, build.ps1 Windows'taki `csc.exe` ile derler (`/r:System.Drawing.dll`, doku çözmek için).
  İki sınıf: `Provider` (IInitializeWithStream; .stl .obj .ply .off .glb) ve `FileProvider` (IInitializeWithFile,
  CLSID {437a1563…}; .gltf — harici .bin/doku yan klasörden okunur). Biçim içerikten tanınır. GLB/glTF'de
  malzeme rengi + PNG/JPEG doku (512 px'e küçültülür), PLY/OFF'ta renkler çizilir; Draco/meshopt atlanır.
  Kurulum, regasm olmadan HKCU CLSID (mscoree.dll + CodeBase) ve `SystemFileAssociations\.<uzantı>\ShellEx\{e357fccd…}` yazar.
- **Kurulumdaki "Dosya türleri" sayfası:** installer.iss [Code] içinde TNewCheckListBox (gruplar + tek tek uzantılar,
  hepsi tikli). Liste `make_meta.py` → `extensions_code.iss`; kayıtlar `Check: AssocSel('.mp4')`. Güncellemede
  yalnızca kaldırılan tikler `AssocOff` olarak saklanır (yeni türler tikli gelir).
  Köşedeki uygulama simgesini Gezgin kendisi ekler (varsayılan uygulamanın simgesi). 3MF'nin kendi gömülü
  önizlemesi var, ona dokunulmuyor. C# 5 sözdizimi kullan (csc 4.x eski).
  `DisableProcessIsolation=1` şart: yalıtılmış önizleme işlemi (dllhost) HKCU COM kayıtlarını görmüyor
  (REGDB_E_CLASSNOTREG). Bu yüzden DLL Gezgin'in içinde çalışır; 200 MB üstü dosyalar atlanır, bellek idareli
  kullanılır. Gezgin DLL'i kilitler, yeniden derlemede dosya meşgul olabilir. Kurulum bu yüzden
  `CloseApplicationsFilter=*.exe` kullanır (yoksa Gezgin'i kapatmayı öneriyor, kapatınca masaüstü gidiyor) ve
  ssInstall'da kilitli DLL'in adını `GammaThumbs.dll.N.old` yapıp yenisini yazar (`MoveAsideThumbDll`). Kullanıcının bilgisayarında
  test için `build\thumbnail\GammaThumbs.dll` HKCU'ya kayıtlı (2026-11-12); kurulum bunu kurulum klasörüne çevirir.

### Kod yazım alışkanlıkları
- Yorumlar ve docstring'ler **Türkçe**. Kullanıcıya görünen her metin `i18n.py`'de `(tr, en)` çifti olarak
  eklenir ve `t("anahtar")` ile kullanılır; düz metin yazma.
- Yeni tercih: `config.DEFAULTS` (veya kişiselleştirme ise `layout_prefs`) + Tercihler arayüzü + i18n.
- Yeni düğme: kişiselleştirme listesine ekle ki kullanıcı gizleyip taşıyabilsin.
- Python yama betiği yazarken heredoc içindeki `"\n"` / `"\\"` kaçışlarına dikkat: daha önce dosyalara gerçek
  satır sonu ve bozuk karakter girdi. Çok satırlı değişikliklerde Edit aracını tercih et.

---

## 5. Test

```powershell
python tests/smoke_test.py            # çekirdek + gerçek arayüz, ~15 sn, 30 adım
python tests/smoke_test.py --no-gui   # yalnızca çekirdek
```

- Test **gerçek tercihlere dokunmaz**: `LOCALAPPDATA` geçici klasöre yönlendirilir; medyayı ffmpeg ile üretir.
- Kendi test/sürücü betiklerinde de **mutlaka** `os.environ["LOCALAPPDATA"]` değerini geçici bir klasöre
  ayarla. Bir kez test betiği gerçek tercihlere `single_instance=False` yazmıştı.
- Görsel doğrulama için `widget.grab()` veya VLC anlık görüntüsü kullan. **Ekranın bir bölgesini yakalama**:
  kullanıcının diğer pencereleri (tarayıcı vb.) görüntüye girdi. Yanlışlıkla girerse dosyayı sil ve içeriğini anlatma.
- **VLC:** VLC şu an bilgisayarda kurulu. Kullanıcı, gamma'yı bir süre kullanıp sorunlar giderildikten sonra
  kaldırmayı düşünüyor. Kaynaktan çalıştırma, testler ve yerel derleme `C:\Program Files\VideoLAN\VLC`
  gerektirir. Kaldırılmışsa önce
  `winget install VideoLAN.VLC` ile kur (kurulu gamma'nın kendi gömülü VLC'si var, ona dokunma).
- Lint: `python -m pyflakes gammaplayer` temiz olmalı.
- Yeni özellik eklenince `tests/smoke_test.py`'ye bir adım eklemek iyi olur.

---

## 6. Derleme ve sürüm yayınlama

**Yerel derleme** (yalnızca kullanıcı isteyince):
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build.ps1
```
Çıktı: `build\installer\gamma-setup-<sürüm>.exe` ve `gamma-portable-<sürüm>.zip`.
Inno Setup kullanıcı başına kurulu: `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`.

**Yeni sürüm yayınlama** (kullanıcı "yayınla" deyince):
1. Değişikliği yap, `python tests/smoke_test.py` geçsin.
2. `gammaplayer/__init__.py` içinde sürümü artır (hata düzeltmesi 2.0.1, yeni özellik 2.1.0).
3. Commit → `git push` → `git tag vX.Y.Z` → `git push origin vX.Y.Z`.
4. GitHub Actions (~5 dk) kurulumu derleyip Releases'a ekler. Durum, kimlik doğrulamasız API ile izlenebilir:
   `https://api.github.com/repos/yigitozsoy/gamma_player/actions/runs?per_page=1`
   (`gh` CLI kurulu değil.)

Kurulum programı aynı AppId ile **üstüne kurar**, ayarlar (`%LOCALAPPDATA%\gamma`) korunur. Uygulamada
otomatik güncelleme yok; kullanıcılar yeni kurulumu indirir.

Kurulum `PrivilegesRequired=lowest` (yönetici izni yok); "Birlikte aç" / Varsayılan uygulamalar kaydı
(RegisteredApplications/Capabilities) ve isteğe bağlı "Open with gamma player" sağ tık menüsü ekler.
Windows programın kendini varsayılan yapmasına izin vermez; kullanıcı Ayarlar › Varsayılan uygulamalar'dan seçer.
Exe imzasız, bu yüzden SmartScreen "Yine de çalıştır" uyarısı normal.

---

## 7. Açık işler / fikirler

- `build.yml` içindeki actions sürümleri Node.js 20 uyarısı veriyor (checkout, setup-python, upload-artifact,
  action-gh-release). Yeni (Node 24) sürümlerine yükselt.
- Kurulum dosyası adını sürümsüz yapmak (`gamma-setup.exe`) → web sitesindeki
  `releases/latest/download/...` linki hiç değişmez. Kullanıcıya önerildi, karar verilmedi.
- Uygulama içi "yeni sürüm var" bildirimi (GitHub Releases API) — önerildi, yapılmadı.
- `docs/` ekran görüntüleri eski arayüzden (eski logo, ⚙ tercih simgesi); güncellenebilir.
