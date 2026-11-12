"""Klavye kısayolları (YouTube uyumlu + VLC tarzı ekler)."""
from PyQt6.QtCore import Qt

from .i18n import t
from . import layout_prefs as lp

K = Qt.Key
CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier

SHORTCUTS = [
    ("Space / K", "sc_play"),
    ("J / L", "sc_seek10"),
    ("← / →", "sc_seek5"),
    ("Ctrl + ← / →", "sc_seek60"),
    ("↑ / ↓", "sc_volume"),
    ("M", "sc_mute"),
    ("F / {dblclick}", "sc_fullscreen"),
    ("T", "sc_theater"),
    ("I", "sc_pip"),
    ("C", "sc_cc"),
    ("G / H", "sc_subdelay"),
    ("Ctrl + J / Ctrl + K", "sc_audiodelay"),
    ("Shift + < / >", "sc_speed"),
    (". ({paused})", "sc_frame"),
    ("0 – 9", "sc_percent"),
    ("Home / End", "sc_homeend"),
    ("N / P  ·  PgDn / PgUp", "sc_nextprev"),
    ("S", "sc_snapshot"),
    ("B", "sc_ab"),
    ("A", "sc_stretch"),
    ("E", "sc_edit"),
    ("Ctrl + O / Ctrl + Shift + O", "sc_open"),
    ("Ctrl + T", "sc_pin"),
    ("Ctrl + D", "sc_theme"),
    ("Ctrl + {wheel}", "sc_zoom"),
    ("+ / − / 0 / 1 / R ({image})", "sc_image"),
    ("{drag} / {wheel} / 0 / R / W / G / D (3D)", "sc_model"),
    ("Delete", "sc_delete"),
    ("Esc", "sc_escape"),
    ("F1", "sc_help"),
]


def keys_text(keys):
    """Kısayol tablosundaki tuş adlarını seçili dile çevirir ({dblclick}, {wheel} ...)."""
    return keys.format(dblclick=t("k_dblclick"), paused=t("k_paused"), wheel=t("k_wheel"),
                       image=t("k_image"), drag=t("k_drag"))


def handle_key(w, e) -> bool:
    k = e.key()
    mods = e.modifiers()
    ctrl = bool(mods & CTRL)
    shift = bool(mods & SHIFT)
    cur = w.current
    playable = cur is not None and cur.is_playable and w.engine is not None
    image = cur is not None and cur.is_image

    ep = w._edit_panel
    if ep is not None:
        if ctrl and k == K.Key_Z:
            ep.undo()
            return True
        if ctrl and k == K.Key_Y:
            ep.redo()
            return True
        if ctrl and k == K.Key_S:
            ep.save_as()
            return True
        if k in (K.Key_Return, K.Key_Enter) and ep.cropping:
            ep._end_crop(True)
            return True
    if k == K.Key_F1:
        from .dialogs import ShortcutsDialog
        ShortcutsDialog(w).exec()
        return True
    if ctrl and k == K.Key_O:
        if shift:
            w.open_folder_dialog()
        else:
            w.open_file_dialog()
        return True
    if ctrl and k == K.Key_T:
        w.set_pinned(not w._pinned)
        return True
    if ctrl and k == K.Key_D:
        w.toggle_theme()
        return True
    if ctrl and k == K.Key_F:
        w.titlebar.set_search_visible(True)
        w.titlebar.search.setFocus()
        w.titlebar.search.selectAll()
        return True
    if ctrl and k == K.Key_Comma:
        w.show_preferences()
        return True
    if k == K.Key_Escape:
        if w.isFullScreen():
            w.toggle_fullscreen()
        elif w._pip:
            w.toggle_pip()
        elif w._edit_panel is not None:
            w._close_image_editor()
        return True
    if k in (K.Key_F, K.Key_F11):
        w.toggle_fullscreen()
        return True
    if k == K.Key_T and not ctrl:
        w.toggle_theater()
        return True
    if k == K.Key_I:
        w.toggle_pip()
        return True
    if k in (K.Key_N, K.Key_PageDown, K.Key_MediaNext):
        w.play_next()
        return True
    if k in (K.Key_P, K.Key_PageUp, K.Key_MediaPrevious):
        w.play_prev()
        return True
    if k == K.Key_E:
        w.edit_current()
        return True
    if k == K.Key_Delete and cur is not None:
        w.trash_item(cur)
        return True
    if k == K.Key_L and not playable and not image:
        w.toggle_sidebar()
        return True

    if cur is not None and cur.is_model:
        v = w.viewer3d
        if v is None:
            return False
        if k in (K.Key_Right, K.Key_Down):
            w.play_next()
        elif k in (K.Key_Left, K.Key_Up):
            w.play_prev()
        elif k in (K.Key_Plus, K.Key_Equal):
            v.zoom_by(1.25)
        elif k == K.Key_Minus:
            v.zoom_by(0.8)
        elif k in (K.Key_0, K.Key_1):
            v.reset_view()
        elif k == K.Key_R:
            v.rotate_model("z", 90) if shift else v.rotate_model("x", -90)
        elif k == K.Key_W:
            v.set_wireframe(not v.wireframe)
        elif k == K.Key_G:
            v.set_grid(not v.show_grid)
            lp.prefs.set("model_grid", v.show_grid)
        elif k == K.Key_D and not ctrl:
            v.set_dims(not v.show_dims)
            lp.prefs.set("model_dims", v.show_dims)
        elif k in (K.Key_Space, K.Key_K):
            v.set_autorotate(not v.autorotate)
        elif ctrl and k == K.Key_C:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setImage(v.image())
            w.osd(t("copied"))
        elif ctrl and k == K.Key_S:
            w._save_model_view(transparent=shift)
        else:
            return False
        return True

    if image:
        v = w.viewer
        if k in (K.Key_Right, K.Key_Down):
            w.play_next()
        elif k in (K.Key_Left, K.Key_Up):
            w.play_prev()
        elif k in (K.Key_Plus, K.Key_Equal):
            v.zoom_by(1.25)
        elif k == K.Key_Minus:
            v.zoom_by(0.8)
        elif k == K.Key_0:
            v.fit()
        elif k == K.Key_1:
            v.actual_size()
        elif k == K.Key_R:
            v.rotate_view(-90 if shift else 90)
        elif k in (K.Key_Space, K.Key_K):
            w.toggle_slideshow()
        elif k == K.Key_Home:
            items = [i for i in w.lib.items if i.is_image]
            if items:
                w.load_item(items[0])
        elif k == K.Key_End:
            items = [i for i in w.lib.items if i.is_image]
            if items:
                w.load_item(items[-1])
        elif ctrl and k == K.Key_C:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setImage(v.image())
            w.osd(t("copied"))
        else:
            return False
        return True

    if not playable:
        if k == K.Key_Space and cur is None:
            w.open_file_dialog()
            return True
        return False

    e_ = w.engine
    if k in (K.Key_Space, K.Key_K, K.Key_MediaPlay, K.Key_MediaTogglePlayPause, K.Key_MediaPause) and not ctrl:
        w.toggle_play()
    elif k == K.Key_K and ctrl:
        w.adjust_audio_delay(50)
    elif k == K.Key_J and ctrl:
        w.adjust_audio_delay(-50)
    elif k == K.Key_J:
        w.seek_relative(-10000)
    elif k == K.Key_L:
        w.seek_relative(10000)
    elif k == K.Key_Left:
        w.seek_relative(-60000 if ctrl else (-1000 if shift else -1000 * int(lp.get("seek_step") or 5)))
    elif k == K.Key_Right:
        w.seek_relative(60000 if ctrl else (1000 if shift else 1000 * int(lp.get("seek_step") or 5)))
    elif k == K.Key_Up:
        w.set_volume(e_.volume() + 5, osd=True)
    elif k == K.Key_Down:
        w.set_volume(e_.volume() - 5, osd=True)
    elif k == K.Key_M:
        w.toggle_mute()
    elif k == K.Key_C:
        w._on_cc()
    elif k == K.Key_G:
        w.adjust_sub_delay(-50)
    elif k == K.Key_H:
        w.adjust_sub_delay(50)
    elif k in (K.Key_Greater,) or (shift and k == K.Key_Period):
        r = min(4.0, round(e_.rate() + 0.25, 2))
        e_.set_rate(r)
        w.osd(t("speed") + f": {r:g}x")
    elif k in (K.Key_Less,) or (shift and k == K.Key_Comma):
        r = max(0.25, round(e_.rate() - 0.25, 2))
        e_.set_rate(r)
        w.osd(t("speed") + f": {r:g}x")
    elif k == K.Key_Period:
        if e_.is_playing():
            e_.pause()
        e_.next_frame()
    elif k == K.Key_Comma:
        if e_.is_playing():
            e_.pause()
        w.seek_relative(-40, bubble=False)
    elif K.Key_0 <= k <= K.Key_9 and not ctrl:
        n = int(k) - int(K.Key_0)
        length = e_.get_length()
        if length > 0:
            w.seek_to(length * n // 10)
            w.osd(f"{n * 10}%")
    elif k == K.Key_Home:
        w.seek_to(0)
    elif k == K.Key_End:
        length = e_.get_length()
        if length > 0:
            w.seek_to(length - 1000)
    elif k == K.Key_S and not ctrl:
        w.take_snapshot()
    elif k == K.Key_B:
        w.set_ab_point()
    elif k == K.Key_A and not ctrl:
        w.toggle_stretch()
    elif k == K.Key_V:
        w.add_subtitle_dialog()
    elif k == K.Key_Z:
        w._zoom_step(1)
    elif k == K.Key_X:
        w._zoom_step(-1)
    else:
        return False
    return True
