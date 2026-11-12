"""LibVLC sarmalayıcısı. VLC olayları Qt sinyallerine (ana iş parçacığına) aktarılır."""
import os
import sys

from PyQt6.QtCore import QObject, pyqtSignal

# Önce kurulumla gelen gömülü VLC'yi (<uygulama>\vlc), yoksa sistemdeki VLC'yi kullan
if sys.platform == "win32" and "PYTHON_VLC_LIB_PATH" not in os.environ:
    _app_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else ""
    _cands = [os.path.join(_app_dir, "vlc")] if _app_dir else []
    _cands += [r"C:\Program Files\VideoLAN\VLC", r"C:\Program Files (x86)\VideoLAN\VLC"]
    for _cand in _cands:
        if os.path.exists(os.path.join(_cand, "libvlc.dll")):
            try:
                os.add_dll_directory(_cand)
            except (OSError, AttributeError):
                pass
            os.environ["PATH"] = _cand + os.pathsep + os.environ.get("PATH", "")
            os.environ.setdefault("PYTHON_VLC_MODULE_PATH", os.path.join(_cand, "plugins"))
            os.environ.setdefault("VLC_PLUGIN_PATH", os.path.join(_cand, "plugins"))
            os.environ["PYTHON_VLC_LIB_PATH"] = os.path.join(_cand, "libvlc.dll")
            break

try:
    import vlc  # noqa: E402
    VLC_ERROR = None
except Exception as e:  # pragma: no cover - VLC kurulu değilse
    vlc = None
    VLC_ERROR = str(e)

from .config import prefs  # noqa: E402


def _decode(b):
    if isinstance(b, bytes):
        return b.decode("utf-8", errors="replace")
    return str(b) if b is not None else ""


def _hex_to_int(h: str) -> int:
    try:
        return int(h.lstrip("#"), 16)
    except ValueError:
        return 0xFFFFFF


class VLCEngine(QObject):
    playing = pyqtSignal()
    paused = pyqtSignal()
    stopped = pyqtSignal()
    ended = pyqtSignal()
    error = pyqtSignal()
    length_changed = pyqtSignal(int)
    vout_changed = pyqtSignal(int)      # video çıkışı sayısı
    meta_ready = pyqtSignal(dict)

    def __init__(self, hwnd: int, parent=None):
        super().__init__(parent)
        self.hwnd = hwnd
        self.path = None
        self.media_options = []
        self._volume = 100
        self._muted = False
        self._rate = 1.0
        self._eq_index = -1
        self._create()

    # ------------------------------------------------------------------ kurulum
    @staticmethod
    def available() -> bool:
        return vlc is not None

    def _instance_args(self):
        args = [
            "--no-video-title-show",
            "--no-mouse-events",
            "--no-keyboard-events",
            "--no-snapshot-preview",
            "--file-caching=800",
            "--network-caching=1500",
            "--quiet",
            "--avcodec-hw=" + ("any" if prefs.get("hw_decode", True) else "none"),
            f"--sub-text-scale={int(prefs.get('sub_size', 100))}",
            f"--freetype-color={_hex_to_int(prefs.get('sub_color', '#ffffff'))}",
            f"--freetype-background-opacity={int(prefs.get('sub_bg', 0))}",
            "--freetype-background-color=0",
            f"--freetype-outline-thickness={int(prefs.get('sub_outline', 4))}",
            f"--sub-margin={int(prefs.get('sub_margin', 0))}",
        ]
        if prefs.get("sub_bold", False):
            args.append("--freetype-bold")
        font = prefs.get("sub_font", "")
        if font:
            args.append(f"--freetype-font={font}")
        enc = prefs.get("sub_encoding", "auto")
        if enc and enc != "auto":
            args.append(f"--subsdec-encoding={enc}")
        return args

    def _create(self):
        self.instance = vlc.Instance(self._instance_args())
        self.mp = self.instance.media_player_new()
        self.mp.set_hwnd(self.hwnd)
        self.mp.video_set_mouse_input(False)
        self.mp.video_set_key_input(False)
        em = self.mp.event_manager()
        E = vlc.EventType
        # Referansları tut (python-vlc callback'leri çöpe gitmesin)
        self._cbs = {
            E.MediaPlayerPlaying: lambda e: self.playing.emit(),
            E.MediaPlayerPaused: lambda e: self.paused.emit(),
            E.MediaPlayerStopped: lambda e: self.stopped.emit(),
            E.MediaPlayerEndReached: lambda e: self.ended.emit(),
            E.MediaPlayerEncounteredError: lambda e: self.error.emit(),
            E.MediaPlayerLengthChanged: lambda e: self.length_changed.emit(int(e.u.new_length)),
            E.MediaPlayerVout: lambda e: self.vout_changed.emit(int(e.u.new_count)),
        }
        for et, cb in self._cbs.items():
            em.event_attach(et, cb)

    def rebuild(self):
        """Altyazı stili gibi örnek seviyesindeki ayarlar değişince motoru yeniden kurar."""
        path, opts = self.path, list(self.media_options)
        was_playing = self.is_playing()
        t = self.get_time()
        a_delay, s_delay = self.get_audio_delay(), self.get_sub_delay()
        sub_track = self.get_sub_track()
        self.release()
        self._create()
        if path:
            self.load(path, opts, start_ms=max(0, t))
            self.play()
            self.set_audio_delay(a_delay)
            self.set_sub_delay(s_delay)
            self._pending_sub = sub_track
            if not was_playing:
                self._pause_after_start = True

    def release(self):
        try:
            em = self.mp.event_manager()
            for et in self._cbs:
                em.event_detach(et)
        except Exception:
            pass
        try:
            self.mp.stop()
            self.mp.release()
            self.instance.release()
        except Exception:
            pass

    # ------------------------------------------------------------------ medya
    def load(self, path: str, options=None, start_ms: int = 0):
        self.path = path
        self.media_options = list(options or [])
        media = self.instance.media_new_path(path)
        for o in self.media_options:
            media.add_option(o)
        if start_ms and start_ms > 0:
            media.add_option(f":start-time={start_ms / 1000.0:.3f}")
        self.mp.set_media(media)
        media.release()
        self._pending_sub = None
        self._pause_after_start = False

    def on_playing_hook(self):
        """Oynatma başladığında çağrılır: ses ayarlarını yeniden uygula."""
        self.mp.audio_set_volume(self._volume)
        self.mp.audio_set_mute(self._muted)
        if abs(self._rate - 1.0) > 0.001:
            self.mp.set_rate(self._rate)
        if self._eq_index >= 0:
            self.set_equalizer(self._eq_index)
        if getattr(self, "_pending_sub", None) is not None:
            self.set_sub_track(self._pending_sub)
            self._pending_sub = None
        if getattr(self, "_pause_after_start", False):
            self._pause_after_start = False
            self.mp.set_pause(1)

    def read_meta(self) -> dict:
        m = self.mp.get_media()
        if not m:
            return {}
        M = vlc.Meta
        out = {}
        for key, mk in (("title", M.Title), ("artist", M.Artist), ("album", M.Album),
                        ("date", M.Date), ("genre", M.Genre), ("artwork", M.ArtworkURL)):
            try:
                v = m.get_meta(mk)
                if v:
                    out[key] = _decode(v)
            except Exception:
                pass
        return out

    # ------------------------------------------------------------------ oynatma
    def play(self):
        self.mp.play()

    def pause(self):
        self.mp.set_pause(1)

    def toggle(self):
        st = self.mp.get_state()
        if st == vlc.State.Playing:
            self.mp.set_pause(1)
        elif st in (vlc.State.Ended, vlc.State.Stopped, vlc.State.Error):
            self.mp.stop()
            self.mp.play()
        else:
            self.mp.play()

    def stop(self):
        self.mp.stop()

    def is_playing(self) -> bool:
        return bool(self.mp.is_playing())

    def state_ended(self) -> bool:
        return self.mp.get_state() == vlc.State.Ended

    def get_time(self) -> int:
        return int(self.mp.get_time() or 0)

    def set_time(self, ms: int):
        length = self.get_length()
        if length > 0:
            ms = max(0, min(ms, length - 200))
        self.mp.set_time(int(max(0, ms)))

    def get_length(self) -> int:
        return int(self.mp.get_length() or 0)

    def is_seekable(self) -> bool:
        return bool(self.mp.is_seekable())

    def next_frame(self):
        self.mp.next_frame()

    # ------------------------------------------------------------------ ses
    def set_volume(self, v: int):
        self._volume = max(0, min(200, int(v)))
        self.mp.audio_set_volume(self._volume)

    def volume(self) -> int:
        return self._volume

    def set_muted(self, m: bool):
        self._muted = bool(m)
        self.mp.audio_set_mute(self._muted)

    def muted(self) -> bool:
        return self._muted

    def set_rate(self, r: float):
        self._rate = max(0.25, min(4.0, float(r)))
        self.mp.set_rate(self._rate)

    def rate(self) -> float:
        return self._rate

    def audio_tracks(self):
        return [(int(i), _decode(n)) for i, n in (self.mp.audio_get_track_description() or [])]

    def get_audio_track(self) -> int:
        return self.mp.audio_get_track()

    def set_audio_track(self, i: int):
        self.mp.audio_set_track(i)

    def get_audio_delay(self) -> int:
        return int(self.mp.audio_get_delay() // 1000)

    def set_audio_delay(self, ms: int):
        self.mp.audio_set_delay(int(ms) * 1000)

    def get_channel(self) -> int:
        return self.mp.audio_get_channel()

    def set_channel(self, c: int):
        self.mp.audio_set_channel(c)

    @staticmethod
    def equalizer_presets():
        if vlc is None:
            return []
        n = vlc.libvlc_audio_equalizer_get_preset_count()
        return [(i, _decode(vlc.libvlc_audio_equalizer_get_preset_name(i))) for i in range(n)]

    def set_equalizer(self, index: int):
        self._eq_index = index
        if index < 0:
            self.mp.set_equalizer(None)
            return
        self._eq = vlc.libvlc_audio_equalizer_new_from_preset(index)
        self.mp.set_equalizer(self._eq)

    def equalizer_index(self) -> int:
        return self._eq_index

    # ------------------------------------------------------------------ altyazı
    def sub_tracks(self):
        return [(int(i), _decode(n)) for i, n in (self.mp.video_get_spu_description() or [])]

    def get_sub_track(self) -> int:
        return self.mp.video_get_spu()

    def set_sub_track(self, i: int):
        self.mp.video_set_spu(i)

    def add_subtitle(self, path: str) -> bool:
        uri = "file:///" + os.path.abspath(path).replace("\\", "/")
        return self.mp.add_slave(vlc.MediaSlaveType.subtitle, uri, True) == 0

    def get_sub_delay(self) -> int:
        return int(self.mp.video_get_spu_delay() // 1000)

    def set_sub_delay(self, ms: int):
        self.mp.video_set_spu_delay(int(ms) * 1000)

    # ------------------------------------------------------------------ görüntü
    def video_size(self):
        try:
            w, h = self.mp.video_get_size(0)
            return int(w), int(h)
        except Exception:
            return 0, 0

    def has_video(self) -> bool:
        try:
            return self.mp.has_vout() > 0
        except Exception:
            return False

    def set_aspect(self, ratio):
        self.mp.video_set_aspect_ratio(ratio)

    def set_crop(self, geometry):
        self.mp.video_set_crop_geometry(geometry)

    def set_scale(self, s: float):
        self.mp.video_set_scale(s)

    def set_deinterlace(self, mode):
        self.mp.video_set_deinterlace(mode)

    def set_adjust(self, brightness=1.0, contrast=1.0, saturation=1.0, hue=0.0, gamma=1.0):
        O = vlc.VideoAdjustOption
        neutral = (abs(brightness - 1) < 1e-3 and abs(contrast - 1) < 1e-3 and abs(saturation - 1) < 1e-3
                   and abs(hue) < 1e-3 and abs(gamma - 1) < 1e-3)
        self.mp.video_set_adjust_int(O.Enable, 0 if neutral else 1)
        if not neutral:
            self.mp.video_set_adjust_float(O.Brightness, float(brightness))
            self.mp.video_set_adjust_float(O.Contrast, float(contrast))
            self.mp.video_set_adjust_float(O.Saturation, float(saturation))
            self.mp.video_set_adjust_float(O.Hue, float(hue))
            self.mp.video_set_adjust_float(O.Gamma, float(gamma))

    def snapshot(self, path: str) -> bool:
        return self.mp.video_take_snapshot(0, path, 0, 0) == 0
