"""Kişiselleştirme: düğme grupları için sıra + görünürlük ve davranış tercihleri.

Her grup, [anahtar, görünür] çiftlerinden oluşan bir listedir. "|" ayırıcıdır:
ayırıcının solundakiler sol tarafa, sağındakiler sağ tarafa yerleşir.
"""
from .config import prefs

SEP = "|"

# grup adı -> (tercih anahtarı, varsayılan düzen, zorunlu (gizlenemez) anahtarlar)
GROUPS = {
    "titlebar": ("tb_layout",
                 [["prefs", 1], [SEP, 1], ["open_file", 0], ["open_folder", 0], ["theme", 1], ["pin", 1], ["panel", 1]],
                 ()),
    "player": ("ov_layout",
               [["prev", 1], ["play", 1], ["next", 1], ["loop", 1], ["volume", 1], ["time", 1], [SEP, 1],
                ["autoplay", 1], ["snapshot", 0], ["stretch", 0], ["cc", 1], ["settings", 1], ["pip", 1],
                ["theater", 1], ["fullscreen", 1]],
               ("play",)),
    "infobar": ("info_layout",
                [["edit", 1], ["snapshot", 1], ["subtitle", 1], ["reveal", 1], ["info", 1], ["delete", 1], ["more", 1]],
                ()),
}

# Diğer kişiselleştirme tercihleri ve varsayılanları (şu anki görünüm)
BEHAVIOR_DEFAULTS = {
    "sidebar_side": "right",          # right | left
    "sidebar_autoshow": True,         # klasörde başka dosya varsa paneli aç
    "thumb_size": "normal",           # small | normal | large
    "sidebar_meta": True,             # boyut/tarih satırı
    "show_infobar": True,             # oynatıcının altındaki satır
    "seek_preview": True,             # zaman çubuğunda kare önizlemesi
    "autohide_ms": 2600,              # kontrollerin kaybolma süresi (0 = hiç)
    "flash_anim": True,               # ortada oynat/duraklat animasyonu
    "mini_progress": False,           # kontroller gizliyken ince ilerleme çizgisi
    "time_display": "elapsed",        # elapsed | remaining
    "show_title_fullscreen": True,    # tam ekranda üstte dosya adı
    "click_action": "play",           # play | none
    "dblclick_fullscreen": True,
    "right_speed": True,              # sağ tarafa basılı tut 2x, sağa çift tık 2x aç/kapa
    "wheel_action": "volume",         # volume | seek | none
    "seek_step": 5,                   # ←/→ adımı (sn)
    "confirm_delete": True,
    "osd_messages": True,             # kısa bildirimler
    "show_recent": True,              # ana sayfada son açılanlar
}

PERSONAL_KEYS = [g[0] for g in GROUPS.values()] + list(BEHAVIOR_DEFAULTS.keys())


def get(key):
    return prefs.get(key, BEHAVIOR_DEFAULTS.get(key))


def layout(group):
    """Grubun geçerli düzenini döndürür (bilinmeyenler atılır, eksikler varsayılan görünürlükle eklenir)."""
    pkey, default, required = GROUPS[group]
    saved = prefs.get(pkey)
    if not isinstance(saved, list) or not saved:
        saved = [list(x) for x in default]
        # Eski tekil anahtarlardan geçiş
        if group == "titlebar" and prefs.get("show_open_buttons", False):
            for x in saved:
                if x[0] in ("open_file", "open_folder"):
                    x[1] = 1
        if group == "player" and prefs.get("show_quick_buttons", False):
            for x in saved:
                if x[0] in ("snapshot", "stretch"):
                    x[1] = 1
    known = {k for k, _ in default}
    out, seen = [], set()
    for entry in saved:
        try:
            k, v = entry[0], int(bool(entry[1]))
        except (TypeError, IndexError, ValueError):
            continue
        if k in known and k not in seen:
            out.append([k, 1 if k in required or k == SEP else v])
            seen.add(k)
    for k, v in default:
        if k not in seen:
            out.append([k, v])
    return out


def set_layout(group, items):
    prefs.set(GROUPS[group][0], [[k, int(bool(v))] for k, v in items])


def visible(group, key):
    for k, v in layout(group):
        if k == key:
            return bool(v)
    return True


def sides(group):
    """(sol anahtarlar, sağ anahtarlar) — yalnızca görünür olanlar."""
    left, right, cur = [], [], None
    cur = left
    for k, v in layout(group):
        if k == SEP:
            cur = right
            continue
        if v:
            cur.append(k)
    return left, right


def order(group):
    """Ayırıcı hariç tüm anahtarlar sırayla (görünmezler dahil)."""
    return [k for k, _ in layout(group) if k != SEP]


def reset_all():
    for k in PERSONAL_KEYS + ["show_open_buttons", "show_quick_buttons"]:
        prefs.data.pop(k, None)
    prefs.save()
