"""Düz / benzer renkli arka planı saydam yapma (ör. beyaz zeminli logo, ürün fotoğrafı).

Yöntem: arka plan rengine olan uzaklık hesaplanır; tolerans içindeki pikseller adaydır.
"Yalnızca kenara bağlı" seçiliyse adaylardan resmin kenarına bağlı olanlar silinir (nesnenin
içindeki aynı renkli kısımlar korunur). Kenarlar yumuşatılır ve arka plan rengi kenarlardan
temizlenir (beyaz hale kalmaz).
"""
import numpy as np
from PIL import Image


def border_color(img: Image.Image):
    """Kenar piksellerinin medyanı (otomatik arka plan rengi)."""
    a = np.asarray(img.convert("RGB"))
    b = np.concatenate([a[:2].reshape(-1, 3), a[-2:].reshape(-1, 3), a[:, :2].reshape(-1, 3), a[:, -2:].reshape(-1, 3)])
    return tuple(int(v) for v in np.median(b, axis=0))


def _connected_to_border(cand: np.ndarray) -> np.ndarray:
    """cand (bool HxW) içinde kenara bağlı bölgeyi döndürür (küçültülmüş ızgarada yayılım)."""
    H, W = cand.shape
    scale = max(1.0, max(H, W) / 360.0)
    if scale > 1:
        small = np.asarray(Image.fromarray(cand.astype(np.uint8) * 255).resize(
            (max(1, int(W / scale)), max(1, int(H / scale))), Image.Resampling.BOX)) > 127
    else:
        small = cand.copy()
    reach = np.zeros_like(small)
    reach[0, :], reach[-1, :], reach[:, 0], reach[:, -1] = small[0, :], small[-1, :], small[:, 0], small[:, -1]
    for _ in range(4000):
        grown = reach.copy()
        grown[1:, :] |= reach[:-1, :]
        grown[:-1, :] |= reach[1:, :]
        grown[:, 1:] |= reach[:, :-1]
        grown[:, :-1] |= reach[:, 1:]
        grown &= small
        if np.array_equal(grown, reach):
            break
        reach = grown
    if scale > 1:
        big = Image.fromarray(reach.astype(np.uint8) * 255).resize((W, H), Image.Resampling.BILINEAR)
        reach = np.asarray(big) > 40   # biraz geniş tut; ince kenarları tam çözünürlükteki aday maskesi belirler
    return reach & cand


def remove_background(img: Image.Image, color=None, tol=20, edge_only=True, feather=6) -> Image.Image:
    """RGBA döndürür. tol/feather: 0..100 ölçeğinde renk uzaklığı."""
    rgb = img.convert("RGB")
    a = np.asarray(rgb).astype(np.float32)
    bg = np.array(color if color else border_color(rgb), dtype=np.float32)
    dist = np.sqrt(((a - bg) ** 2).sum(axis=2)) / (np.sqrt(3) * 255.0) * 100.0
    feather = max(0.01, float(feather))
    cand = dist <= (tol + feather)
    region = _connected_to_border(cand) if edge_only else cand
    alpha = np.clip((dist - tol) / feather, 0.0, 1.0)
    alpha = np.where(region, alpha, 1.0)
    # Kenar renklerini arka plandan arındır (beyaz/renkli hale kalmasın)
    part = (alpha > 0.02) & (alpha < 0.98)
    if part.any():
        al = alpha[part][:, None]
        a[part] = np.clip((a[part] - bg * (1.0 - al)) / al, 0, 255)
    out = np.dstack([a.astype(np.uint8), (alpha * 255).astype(np.uint8)])
    res = Image.fromarray(out, "RGBA")
    if img.mode == "RGBA":
        old = np.asarray(img.getchannel("A"))
        res.putalpha(Image.fromarray(np.minimum(old, (alpha * 255).astype(np.uint8))))
    return res
