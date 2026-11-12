"""3D model okuma: STL, OBJ, PLY, OFF, glTF/GLB, 3MF.

Her şey numpy ile okunur; çıktı "üçgen çorbası"dır (her üçgenin 3 köşesi ayrı satır).
İş parçacığında çalışabilir (yalnızca numpy + QImage kullanılır).
Koordinatlar Y-yukarı olacak şekilde çevrilir (STL/3MF/PLY/OFF genelde Z-yukarıdır).
"""
import json
import os
import re
import struct
import zipfile
import base64
import xml.etree.ElementTree as ET

import numpy as np

MODEL_EXT = {".stl", ".obj", ".ply", ".off", ".glb", ".gltf", ".3mf", ".step", ".stp", ".iges", ".igs"}
# Bu biçimlerde yukarı ekseni genelde Z'dir (CAD / 3B yazıcı)
Z_UP_EXT = {".stl", ".ply", ".off", ".3mf", ".step", ".stp", ".iges", ".igs"}
DEFAULT_COLOR = (0.78, 0.78, 0.80, 1.0)


class ModelError(Exception):
    pass


class Part:
    """Tek malzemeli üçgen grubu."""
    __slots__ = ("pos", "nrm", "col", "uv", "texture", "color")

    def __init__(self, pos, nrm=None, col=None, uv=None, texture=None, color=None):
        self.pos = np.ascontiguousarray(pos, dtype=np.float32).reshape(-1, 3)
        self.nrm = None if nrm is None else np.ascontiguousarray(nrm, dtype=np.float32).reshape(-1, 3)
        self.col = None if col is None else np.ascontiguousarray(col, dtype=np.float32).reshape(-1, 3)
        self.uv = None if uv is None else np.ascontiguousarray(uv, dtype=np.float32).reshape(-1, 2)
        self.texture = texture          # QImage veya None
        self.color = tuple(color) if color is not None else DEFAULT_COLOR


class Model:
    def __init__(self, parts, fmt="", vertices=0):
        self.parts = [p for p in parts if len(p.pos) >= 3]
        if not self.parts:
            raise ModelError("empty")
        for p in self.parts:
            if p.nrm is None or len(p.nrm) != len(p.pos):
                p.nrm = face_normals(p.pos)
            else:
                p.nrm = _normalize(p.nrm)
        allp = np.concatenate([p.pos for p in self.parts])
        good = np.isfinite(allp).all(axis=1)
        if not good.all():
            allp = allp[good]
        if not len(allp):
            raise ModelError("empty")
        self.bmin = allp.min(axis=0)
        self.bmax = allp.max(axis=0)
        self.triangles = sum(len(p.pos) // 3 for p in self.parts)
        self.vertices = vertices or len(allp)
        self.fmt = fmt

    @property
    def center(self):
        return (self.bmin + self.bmax) / 2.0

    @property
    def size(self):
        return self.bmax - self.bmin

    @property
    def radius(self):
        return float(np.linalg.norm(self.size) / 2.0) or 1.0


# ------------------------------------------------------------------ yardımcılar
def _normalize(v):
    n = np.linalg.norm(v, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (v / n).astype(np.float32)


def face_normals(pos):
    """Düz (flat) gölgeleme için yüz normalleri, her köşeye kopyalanmış."""
    tri = pos.reshape(-1, 3, 3)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n = _normalize(n)
    return np.repeat(n, 3, axis=0)


def smooth_normals(pos, idx):
    """İndeksli ağ için köşe normalleri (alan ağırlıklı)."""
    tri = pos[idx]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    vn = np.zeros_like(pos)
    for k in range(3):
        np.add.at(vn, idx[:, k], fn)
    return _normalize(vn)


def _zup_to_yup(a):
    if a is None:
        return None
    out = np.empty_like(a)
    out[:, 0] = a[:, 0]
    out[:, 1] = a[:, 2]
    out[:, 2] = -a[:, 1]
    return out


def _fan(poly):
    """Çokgeni üçgen yelpazesine böler (indeks listesi)."""
    return [(poly[0], poly[i], poly[i + 1]) for i in range(1, len(poly) - 1)]


def _load_qimage(data=None, path=None):
    try:
        from PyQt6.QtGui import QImage
        img = QImage()
        if data is not None:
            img.loadFromData(data)
        elif path and os.path.exists(path):
            img.load(path)
        if img.isNull():
            return None
        if max(img.width(), img.height()) > 4096:
            from PyQt6.QtCore import Qt
            img = img.scaled(4096, 4096, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        return img.convertToFormat(QImage.Format.Format_RGBA8888)
    except Exception:
        return None


# ------------------------------------------------------------------ STL
def load_stl(path):
    with open(path, "rb") as f:
        data = f.read()
    if len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if 84 + n * 50 == len(data) or (n > 0 and 84 + n * 50 <= len(data) and not data[:5].lower() == b"solid"):
            rec = np.frombuffer(data, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]),
                                count=n, offset=84)
            pos = rec["v"].reshape(-1, 3).astype(np.float32)
            return [Part(pos)], _unique_count(pos)
    text = data.decode("latin-1", "ignore")
    nums = re.findall(r"vertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)", text)
    if not nums:
        raise ModelError("stl")
    pos = np.array(nums, dtype=np.float32)
    pos = pos[: len(pos) // 3 * 3]
    return [Part(pos)], _unique_count(pos)


def _unique_count(pos):
    """STL köşeleri tekrar eder; gerçek köşe sayısı (çok büyük dosyalarda tahmin edilmez)."""
    if len(pos) > 3_000_000:
        return len(pos)
    try:
        return int(len(np.unique(pos, axis=0)))
    except Exception:
        return len(pos)


# ------------------------------------------------------------------ OBJ
def _read_mtl(path):
    mats, cur = {}, None
    base = os.path.dirname(path)
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                s = line.strip().split()
                if not s:
                    continue
                if s[0] == "newmtl":
                    cur = " ".join(s[1:])
                    mats[cur] = {"Kd": None, "map": None, "d": 1.0}
                elif cur is None:
                    continue
                elif s[0] == "Kd" and len(s) >= 4:
                    try:
                        mats[cur]["Kd"] = tuple(float(x) for x in s[1:4])
                    except ValueError:
                        pass
                elif s[0] == "d" and len(s) >= 2:
                    try:
                        mats[cur]["d"] = float(s[1])
                    except ValueError:
                        pass
                elif s[0] == "map_Kd" and len(s) >= 2:
                    # seçenekler (-s 1 1 1 vb.) atlanır, son parça dosya adıdır
                    name = s[-1].replace("\\", "/")
                    mats[cur]["map"] = os.path.join(base, name)
    except OSError:
        pass
    return mats


def load_obj(path):
    v, vt, vn, vc = [], [], [], []
    groups = {}      # malzeme adı -> [(vi, ti, ni) ...] köşe üçlüleri
    mtllibs = []
    cur = ""
    order = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line or line[0] == "#":
                continue
            c0 = line[:2]
            if c0 == "v ":
                s = line.split()
                v.append((float(s[1]), float(s[2]), float(s[3])))
                if len(s) >= 7:
                    vc.append((float(s[4]), float(s[5]), float(s[6])))
            elif c0 == "vt":
                s = line.split()
                vt.append((float(s[1]), float(s[2]) if len(s) > 2 else 0.0))
            elif c0 == "vn":
                s = line.split()
                vn.append((float(s[1]), float(s[2]), float(s[3])))
            elif c0 == "f ":
                s = line.split()[1:]
                poly = []
                for tok in s:
                    p = tok.split("/")
                    vi = int(p[0])
                    ti = int(p[1]) if len(p) > 1 and p[1] else 0
                    ni = int(p[2]) if len(p) > 2 and p[2] else 0
                    vi = vi - 1 if vi > 0 else len(v) + vi
                    ti = ti - 1 if ti > 0 else (len(vt) + ti if ti < 0 else -1)
                    ni = ni - 1 if ni > 0 else (len(vn) + ni if ni < 0 else -1)
                    poly.append((vi, ti, ni))
                if len(poly) >= 3:
                    g = groups.get(cur)
                    if g is None:
                        g = groups[cur] = []
                        order.append(cur)
                    for tri in _fan(poly):
                        g.extend(tri)
            elif line.startswith("usemtl"):
                cur = line[6:].strip()
            elif line.startswith("mtllib"):
                mtllibs.append(line[6:].strip())
    if not v or not groups:
        raise ModelError("obj")
    V = np.array(v, dtype=np.float32)
    VT = np.array(vt, dtype=np.float32) if vt else None
    VN = np.array(vn, dtype=np.float32) if vn else None
    VC = np.array(vc, dtype=np.float32) if len(vc) == len(v) else None
    if VC is not None and VC.max() > 1.0:
        VC = VC / 255.0
    mats = {}
    base = os.path.dirname(path)
    for lib in mtllibs:
        mats.update(_read_mtl(os.path.join(base, lib)))
    tex_cache = {}
    parts = []
    for name in order:
        idx = np.array(groups[name], dtype=np.int64).reshape(-1, 3)
        vi = np.clip(idx[:, 0], 0, len(V) - 1)
        pos = V[vi]
        nrm = None
        if VN is not None and (idx[:, 2] >= 0).all():
            nrm = VN[np.clip(idx[:, 2], 0, len(VN) - 1)]
        uv = None
        if VT is not None and (idx[:, 1] >= 0).all():
            uv = VT[np.clip(idx[:, 1], 0, len(VT) - 1)]
        col = VC[vi] if VC is not None else None
        m = mats.get(name, {})
        color = DEFAULT_COLOR
        if m.get("Kd") is not None:
            color = (*m["Kd"], float(m.get("d", 1.0)))
        tex = None
        if m.get("map") and uv is not None:
            p = m["map"]
            if p not in tex_cache:
                tex_cache[p] = _load_qimage(path=p)
            tex = tex_cache[p]
            if tex is not None:
                # Doku varken Kd çoğu programda yok sayılır (dışa aktarıcılar genelde gri yazar)
                color = (1.0, 1.0, 1.0, color[3])
        parts.append(Part(pos, nrm, col, uv, tex, color))
    return parts, len(V)


# ------------------------------------------------------------------ PLY
_PLY_T = {"char": "i1", "int8": "i1", "uchar": "u1", "uint8": "u1", "short": "i2", "int16": "i2",
          "ushort": "u2", "uint16": "u2", "int": "i4", "int32": "i4", "uint": "u4", "uint32": "u4",
          "float": "f4", "float32": "f4", "double": "f8", "float64": "f8"}


def load_ply(path):
    with open(path, "rb") as f:
        data = f.read()
    end = data.find(b"end_header")
    if not data.startswith(b"ply") or end < 0:
        raise ModelError("ply")
    nl = data.find(b"\n", end)
    header = data[:end].decode("latin-1").splitlines()
    body = data[nl + 1:]
    fmt = "ascii"
    elements = []   # [ad, sayı, [(ad, tip, liste_say_tipi)]]
    for ln in header:
        s = ln.split()
        if not s:
            continue
        if s[0] == "format":
            fmt = s[1]
        elif s[0] == "element":
            elements.append([s[1], int(s[2]), []])
        elif s[0] == "property" and elements:
            if s[1] == "list":
                elements[-1][2].append((s[4], _PLY_T.get(s[3], "u1"), _PLY_T.get(s[2], "u1")))
            else:
                elements[-1][2].append((s[2], _PLY_T.get(s[1], "f4"), None))
    verts, faces = None, None
    if fmt == "ascii":
        tokens = body.split()
        pos = 0
        for name, count, props in elements:
            if all(p[2] is None for p in props):
                n = len(props)
                arr = np.array(tokens[pos:pos + n * count], dtype=np.float64).reshape(count, n)
                pos += n * count
                if name == "vertex":
                    verts = {p[0]: arr[:, i] for i, p in enumerate(props)}
            else:
                rows = []
                for _ in range(count):
                    row = []
                    for pn, pt, lt in props:
                        if lt is None:
                            row.append(float(tokens[pos]))
                            pos += 1
                        else:
                            k = int(tokens[pos])
                            row.append([int(x) for x in tokens[pos + 1:pos + 1 + k]])
                            pos += 1 + k
                    rows.append(row)
                if name == "face":
                    li = next(i for i, p in enumerate(props) if p[2] is not None)
                    faces = [r[li] for r in rows]
    else:
        endian = "<" if "little" in fmt else ">"
        off = 0
        for name, count, props in elements:
            if all(p[2] is None for p in props):
                dt = np.dtype([(p[0], endian + p[1]) for p in props])
                arr = np.frombuffer(body, dtype=dt, count=count, offset=off)
                off += dt.itemsize * count
                if name == "vertex":
                    verts = {p[0]: arr[p[0]].astype(np.float64) for p in props}
            else:
                # Hızlı yol: tek liste özelliği ve hepsi üçgen
                if len(props) == 1 and count:
                    pn, it_, ct = props[0]
                    csz = np.dtype(ct).itemsize
                    isz = np.dtype(it_).itemsize
                    first = np.frombuffer(body, dtype=endian + ct, count=1, offset=off)[0]
                    dt = np.dtype([("c", endian + ct), ("i", endian + it_, (int(first),))])
                    if off + dt.itemsize * count <= len(body):
                        arr = np.frombuffer(body, dtype=dt, count=count, offset=off)
                        if (arr["c"] == first).all():
                            off += dt.itemsize * count
                            if name == "face":
                                faces = arr["i"].astype(np.int64)
                            continue
                    # Yavaş yol: karışık çokgenler
                    rows = []
                    for _ in range(count):
                        k = int(np.frombuffer(body, dtype=endian + ct, count=1, offset=off)[0])
                        off += csz
                        rows.append(np.frombuffer(body, dtype=endian + it_, count=k, offset=off).tolist())
                        off += isz * k
                    if name == "face":
                        faces = rows
                    continue
                rows = []
                for _ in range(count):
                    row = []
                    for pn, pt, lt in props:
                        if lt is None:
                            sz = np.dtype(pt).itemsize
                            row.append(np.frombuffer(body, dtype=endian + pt, count=1, offset=off)[0])
                            off += sz
                        else:
                            k = int(np.frombuffer(body, dtype=endian + lt, count=1, offset=off)[0])
                            off += np.dtype(lt).itemsize
                            row.append(np.frombuffer(body, dtype=endian + pt, count=k, offset=off).tolist())
                            off += np.dtype(pt).itemsize * k
                    rows.append(row)
                if name == "face":
                    li = next(i for i, p in enumerate(props) if p[2] is not None)
                    faces = [r[li] for r in rows]
    if verts is None or "x" not in verts:
        raise ModelError("ply")
    V = np.stack([verts["x"], verts["y"], verts["z"]], axis=1).astype(np.float32)
    col = None
    for r, g, b in (("red", "green", "blue"), ("r", "g", "b"), ("diffuse_red", "diffuse_green", "diffuse_blue")):
        if r in verts and g in verts and b in verts:
            col = np.stack([verts[r], verts[g], verts[b]], axis=1).astype(np.float32)
            if col.max() > 1.0:
                col /= 255.0
            break
    if faces is None or len(faces) == 0:
        raise ModelError("ply_points")
    if isinstance(faces, np.ndarray):
        idx = faces
        if idx.shape[1] > 3:
            idx = np.concatenate([idx[:, [0, i, i + 1]] for i in range(1, idx.shape[1] - 1)])
    else:
        tris = []
        for poly in faces:
            if len(poly) >= 3:
                tris.extend(_fan(poly))
        idx = np.array(tris, dtype=np.int64).reshape(-1, 3)
    idx = np.clip(idx, 0, len(V) - 1)
    nrm = None
    if "nx" in verts and "ny" in verts and "nz" in verts:
        N = np.stack([verts["nx"], verts["ny"], verts["nz"]], axis=1).astype(np.float32)
        nrm = N[idx.reshape(-1)]
    pos = V[idx.reshape(-1)]
    c = col[idx.reshape(-1)] if col is not None else None
    return [Part(pos, nrm, c, color=(1, 1, 1, 1) if c is not None else None)], len(V)


# ------------------------------------------------------------------ OFF
def load_off(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [ln.split("#")[0].strip() for ln in f]
    lines = [ln for ln in lines if ln]
    if not lines:
        raise ModelError("off")
    head = lines[0]
    i = 1
    if head.upper().endswith("OFF") and len(head.split()) == 1:
        counts = lines[1].split()
        i = 2
    else:
        counts = head[3:].split() if head.upper().startswith("OFF") else head.split()
    nv, nf = int(counts[0]), int(counts[1])
    V = np.array([[float(x) for x in lines[i + k].split()[:3]] for k in range(nv)], dtype=np.float32)
    tris, cols = [], []
    for k in range(nf):
        s = lines[i + nv + k].split()
        n = int(s[0])
        poly = [int(x) for x in s[1:1 + n]]
        tris.extend(_fan(poly))
        if len(s) >= 1 + n + 3:
            c = [float(x) for x in s[1 + n:1 + n + 3]]
            cols.extend([c] * (3 * (n - 2)))
    idx = np.clip(np.array(tris, dtype=np.int64).reshape(-1), 0, nv - 1)
    col = None
    if cols and len(cols) == len(idx):
        col = np.array(cols, dtype=np.float32)
        if col.max() > 1.0:
            col /= 255.0
    return [Part(V[idx], col=col, color=(1, 1, 1, 1) if col is not None else None)], nv


# ------------------------------------------------------------------ glTF / GLB
_GL_CT = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
_GL_N = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


def _quat_mat(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0],
        [0, 0, 0, 1]], dtype=np.float64)


def load_gltf(path):
    with open(path, "rb") as f:
        data = f.read()
    bin_chunk = None
    if data[:4] == b"glTF":
        off = 12
        js = None
        while off + 8 <= len(data):
            ln, typ = struct.unpack_from("<II", data, off)
            chunk = data[off + 8: off + 8 + ln]
            if typ == 0x4E4F534A:
                js = json.loads(chunk.decode("utf-8"))
            elif typ == 0x004E4942:
                bin_chunk = chunk
            off += 8 + ln
        if js is None:
            raise ModelError("glb")
    else:
        js = json.loads(data.decode("utf-8"))
    base = os.path.dirname(path)
    ext_req = set(js.get("extensionsRequired", []))
    if ext_req & {"KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_mesh_quantization"}:
        raise ModelError("compressed")

    buffers = []
    for b in js.get("buffers", []):
        uri = b.get("uri")
        if uri is None:
            buffers.append(bin_chunk or b"")
        elif uri.startswith("data:"):
            buffers.append(base64.b64decode(uri.split(",", 1)[1]))
        else:
            from urllib.parse import unquote
            try:
                with open(os.path.join(base, unquote(uri)), "rb") as f:
                    buffers.append(f.read())
            except OSError:
                buffers.append(b"")

    views = js.get("bufferViews", [])
    accs = js.get("accessors", [])

    def view_bytes(vi):
        bv = views[vi]
        buf = buffers[bv.get("buffer", 0)]
        o = bv.get("byteOffset", 0)
        return buf[o: o + bv["byteLength"]], bv.get("byteStride")

    acc_cache = {}

    def accessor(ai):
        if ai in acc_cache:
            return acc_cache[ai]
        a = accs[ai]
        ct = _GL_CT[a["componentType"]]
        n = _GL_N[a["type"]]
        cnt = a["count"]
        if "bufferView" in a:
            raw, stride = view_bytes(a["bufferView"])
            o = a.get("byteOffset", 0)
            isz = np.dtype(ct).itemsize
            if stride and stride != isz * n:
                arr = np.lib.stride_tricks.as_strided(
                    np.frombuffer(raw, dtype=np.uint8, offset=o),
                    shape=(cnt, isz * n), strides=(stride, 1)).copy()
                arr = arr.view(ct).reshape(cnt, n)
            else:
                arr = np.frombuffer(raw, dtype=ct, count=cnt * n, offset=o).reshape(cnt, n)
        else:
            arr = np.zeros((cnt, n), dtype=ct)
        arr = arr.astype(np.float64) if ct != "<u4" else arr.astype(np.int64)
        if a.get("normalized") and ct in ("u1", "<u2"):
            arr = arr / (255.0 if ct == "u1" else 65535.0)
        elif a.get("normalized") and ct in ("i1", "<i2"):
            arr = np.maximum(arr / (127.0 if ct == "i1" else 32767.0), -1.0)
        sp = a.get("sparse")
        if sp:
            arr = arr.copy()
            ii = sp["indices"]
            raw, _ = view_bytes(ii["bufferView"])
            sidx = np.frombuffer(raw, dtype=_GL_CT[ii["componentType"]], count=sp["count"],
                                 offset=ii.get("byteOffset", 0)).astype(np.int64)
            vv = sp["values"]
            raw, _ = view_bytes(vv["bufferView"])
            sval = np.frombuffer(raw, dtype=ct, count=sp["count"] * n, offset=vv.get("byteOffset", 0))
            arr[sidx] = sval.reshape(-1, n)
        acc_cache[ai] = arr
        return arr

    tex_cache = {}

    def texture(ti):
        if ti in tex_cache:
            return tex_cache[ti]
        img = None
        try:
            tex = js["textures"][ti]
            src = tex.get("source")
            if src is None:
                for ext in tex.get("extensions", {}).values():
                    src = ext.get("source", src)
            im = js["images"][src]
            if "bufferView" in im:
                raw, _ = view_bytes(im["bufferView"])
                img = _load_qimage(data=bytes(raw))
            elif im.get("uri", "").startswith("data:"):
                img = _load_qimage(data=base64.b64decode(im["uri"].split(",", 1)[1]))
            elif im.get("uri"):
                from urllib.parse import unquote
                img = _load_qimage(path=os.path.join(base, unquote(im["uri"])))
        except Exception:
            img = None
        tex_cache[ti] = img
        return img

    mats = js.get("materials", [])
    parts = []
    nverts = [0]

    def add_mesh(mi, M):
        mesh = js["meshes"][mi]
        R = M[:3, :3]
        try:
            NR = np.linalg.inv(R).T
        except np.linalg.LinAlgError:
            NR = R
        flip = np.linalg.det(R) < 0
        for prim in mesh.get("primitives", []):
            mode = prim.get("mode", 4)
            at = prim.get("attributes", {})
            if "POSITION" not in at or mode not in (4, 5, 6):
                continue
            P = accessor(at["POSITION"])[:, :3]
            nverts[0] += len(P)
            if "indices" in prim:
                idx = accessor(prim["indices"]).reshape(-1).astype(np.int64)
            else:
                idx = np.arange(len(P), dtype=np.int64)
            if mode == 5:   # şerit
                k = np.arange(len(idx) - 2)
                tri = np.stack([idx[k], idx[k + 1], idx[k + 2]], axis=1)
                odd = (k % 2) == 1
                tri[odd] = tri[odd][:, [1, 0, 2]]
                idx = tri.reshape(-1)
            elif mode == 6:   # yelpaze
                k = np.arange(1, len(idx) - 1)
                idx = np.stack([np.full_like(k, idx[0]), idx[k], idx[k + 1]], axis=1).reshape(-1)
            idx = idx[: len(idx) // 3 * 3]
            idx = np.clip(idx, 0, len(P) - 1)
            if flip:
                idx = idx.reshape(-1, 3)[:, [0, 2, 1]].reshape(-1)
            Pw = P @ R.T + M[:3, 3]
            pos = Pw[idx]
            nrm = None
            if "NORMAL" in at:
                N = accessor(at["NORMAL"])[:, :3] @ NR.T
                nrm = N[idx]
            uv = None
            if "TEXCOORD_0" in at:
                uv = accessor(at["TEXCOORD_0"])[:, :2][idx]
            col = None
            if "COLOR_0" in at:
                col = accessor(at["COLOR_0"])[:, :3][idx]
            color, tex = (1.0, 1.0, 1.0, 1.0), None
            mat = mats[prim["material"]] if "material" in prim and prim["material"] < len(mats) else None
            if mat is not None:
                pbr = mat.get("pbrMetallicRoughness", {})
                color = tuple(pbr.get("baseColorFactor", [1, 1, 1, 1]))
                bct = pbr.get("baseColorTexture")
                if bct is None:
                    sg = mat.get("extensions", {}).get("KHR_materials_pbrSpecularGlossiness")
                    if sg:
                        color = tuple(sg.get("diffuseFactor", [1, 1, 1, 1]))
                        bct = sg.get("diffuseTexture")
                if bct is not None and uv is not None:
                    tex = texture(bct.get("index", 0))
            elif col is None:
                color = DEFAULT_COLOR
            if tex is not None:
                uv = uv.copy()
                uv[:, 1] = 1.0 - uv[:, 1]   # glTF: üst sol köşe orijin
            parts.append(Part(pos, nrm, col, uv if tex is not None else None, tex, color))

    nodes = js.get("nodes", [])

    def node_matrix(nd):
        if "matrix" in nd:
            return np.array(nd["matrix"], dtype=np.float64).reshape(4, 4).T
        T = np.eye(4)
        if "translation" in nd:
            T[:3, 3] = nd["translation"]
        Rm = _quat_mat(nd["rotation"]) if "rotation" in nd else np.eye(4)
        S = np.diag(list(nd.get("scale", [1, 1, 1])) + [1])
        return T @ Rm @ S

    def walk(ni, parent, depth=0):
        if depth > 64 or ni >= len(nodes):
            return
        nd = nodes[ni]
        M = parent @ node_matrix(nd)
        if "mesh" in nd:
            add_mesh(nd["mesh"], M)
        for c in nd.get("children", []):
            walk(c, M, depth + 1)

    scenes = js.get("scenes", [])
    if scenes:
        sc = scenes[js.get("scene", 0) if js.get("scene", 0) < len(scenes) else 0]
        for ni in sc.get("nodes", []):
            walk(ni, np.eye(4))
    if not parts:
        for mi in range(len(js.get("meshes", []))):
            add_mesh(mi, np.eye(4))
    if not parts:
        raise ModelError("gltf")
    return parts, nverts[0]


# ------------------------------------------------------------------ 3MF
# <mesh> blokları ElementTree'ye verilmez (milyonlarca öğe çok yavaş ve çok bellek); düzenli ifadeyle okunur
_RX_MESH = re.compile(rb"<(?:[\w.-]+:)?mesh\b[^>]*?(?:/>|>(.*?)</(?:[\w.-]+:)?mesh\s*>)", re.S)
_RX_VERTS = re.compile(rb"<(?:[\w.-]+:)?vertices\b[^>]*>(.*?)</(?:[\w.-]+:)?vertices\s*>", re.S)
_RX_TRIS = re.compile(rb"<(?:[\w.-]+:)?triangles\b[^>]*>(.*?)</(?:[\w.-]+:)?triangles\s*>", re.S)
_RX_TRI = re.compile(rb"<(?:[\w.-]+:)?triangle\b([^>]*)>")


def _rx_attr(name):
    return re.compile(rb"\s" + name + rb"\s*=\s*[\"']([^\"']*)[\"']")


_RX_PAINT = [re.compile(rb" " + a + rb"=\"[^\"]*\"") for a in
             (b"paint_color", b"paint_supports", b"paint_seam", b"face_property",
              b"slic3rpe:mmu_segmentation", b"slic3rpe:custom_supports", b"slic3rpe:custom_seam")]
_RX_A = {k: _rx_attr(k) for k in (b"x", b"y", b"z", b"v1", b"v2", b"v3", b"pid", b"p1")}


def _between(data, tag, start=0):
    """`<tag ...>` ile `</tag>` arasındaki baytlar (düz arama, düzenli ifadeden çok daha hızlı); yoksa None."""
    i = data.find(b"<" + tag, start)
    while i >= 0 and data[i + 1 + len(tag):i + 2 + len(tag)] not in (b">", b" ", b"\n", b"\r", b"\t"):
        i = data.find(b"<" + tag, i + 1)
    if i < 0:
        return None
    j = data.find(b">", i)
    k = data.find(b"</" + tag, j)
    if j < 0 or k < 0:
        return None
    return data[j + 1:k]


def _cut_meshes(data, meshes):
    """<mesh>…</mesh> bloklarını `meshes` listesine alır, yerlerine <mesh gamma_mesh="i"/> bırakır."""
    out, pos = [], 0
    while True:
        i = data.find(b"<mesh", pos)
        if i < 0:
            break
        c = data[i + 5:i + 6]
        if c not in (b">", b" ", b"\n", b"\r", b"\t", b"/"):
            pos = i + 5
            continue
        j = data.find(b">", i)
        if j < 0:
            break
        if data[j - 1:j] == b"/":
            body, end = b"", j + 1
        else:
            k = data.find(b"</mesh", j)
            if k < 0:
                break
            body, end = data[j + 1:k], data.find(b">", k) + 1
        out.append(data[pos:i])
        out.append(b'<mesh gamma_mesh="%d"/>' % len(meshes))
        meshes.append(body)
        pos = end
    if not out:
        return _RX_MESH.sub(lambda m: (meshes.append(m.group(1) or b""),
                                       b'<mesh gamma_mesh="%d"/>' % (len(meshes) - 1))[1], data)
    out.append(data[pos:])
    return b"".join(out)


def _quoted_cols(block, tag, attrs, dtype):
    """Hızlı yol: her öğe yalnızca `attrs` özniteliklerini aynı sırayla taşıyorsa (yazıcı yazılımlarının
    hepsi böyle yazar) tırnak içindeki değerler sırayla alınır. Biçim uymazsa None (yavaş yola düşülür)."""
    n = block.count(b"<" + tag)
    q = block.count(b'"')
    if n == 0 or q % (2 * n):
        return None
    k = q // (2 * n)          # öğe başına öznitelik sayısı (fazladan olanlar, ör. paint_color, atlanır)
    if any(block.count(b" " + a + b'="') != n for a in attrs):
        return None
    pieces = block.split(b'"')
    names = [p.rsplit(None, 1)[-1].rstrip(b"=") if p.strip() else b"" for p in pieces[0:2 * k:2]]
    try:
        cols = [names.index(a) for a in attrs]
        vals = np.array(pieces[1::2], dtype=np.bytes_).reshape(n, k)
        return vals[:, cols].astype(dtype)
    except ValueError:
        return None


def _3mf_mesh(block):
    """Bir <mesh> bloğunun içeriği → (köşeler Nx3, üçgenler Mx3, üçgen başına (pid, p1) ya da None)."""
    vb, tb = _between(block, b"vertices"), _between(block, b"triangles")
    if vb is None or tb is None:
        vb, tb = _RX_VERTS.search(block), _RX_TRIS.search(block)   # ad alanı önekli yazım (m:vertices)
        if not vb or not tb:
            return None
        vb, tb = vb.group(1), tb.group(1)
    V = _quoted_cols(vb, b"vertex", (b"x", b"y", b"z"), np.float64)
    if V is None:
        xs, ys, zs = (_RX_A[k].findall(vb) for k in (b"x", b"y", b"z"))
        n = min(len(xs), len(ys), len(zs))
        V = np.empty((n, 3), dtype=np.float64)
        for j, col in enumerate((xs, ys, zs)):
            V[:, j] = np.array(col[:n], dtype=np.bytes_).astype(np.float64)
    if b"p1" not in tb:
        T = _quoted_cols(tb, b"triangle", (b"v1", b"v2", b"v3"), np.int64)
        if T is None:
            # Dilimleyicilerin yalnızca bazı üçgenlere yazdığı boya öznitelikleri hızlı yolu bozar: at, yeniden dene
            for rx in _RX_PAINT:
                tb = rx.sub(b"", tb)
            T = _quoted_cols(tb, b"triangle", (b"v1", b"v2", b"v3"), np.int64)
        if T is not None:
            return V, T, None
    if b"p1" in tb:   # üçgen başına renk var: öğe öğe oku (sıra bozulmasın)
        T, props = [], []
        for m in _RX_TRI.finditer(tb):
            a = m.group(1)
            vs = [_RX_A[k].search(a) for k in (b"v1", b"v2", b"v3")]
            if not all(vs):
                continue
            T.append([int(v.group(1)) for v in vs])
            pid, p1 = _RX_A[b"pid"].search(a), _RX_A[b"p1"].search(a)
            props.append((pid.group(1).decode() if pid else None, p1.group(1).decode() if p1 else None))
        return V, np.array(T, dtype=np.int64).reshape(-1, 3), props
    cols = [_RX_A[k].findall(tb) for k in (b"v1", b"v2", b"v3")]
    m_ = min(len(c) for c in cols)
    T = np.empty((m_, 3), dtype=np.int64)
    for j, col in enumerate(cols):
        T[:, j] = np.array(col[:m_], dtype=np.bytes_).astype(np.int64)
    return V, T, None


def load_3mf(path):
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise ModelError("3mf")
    names = [n for n in z.namelist() if n.lower().endswith(".model")]
    if not names:
        raise ModelError("3mf")
    main = next((n for n in names if n.lower() == "3d/3dmodel.model"), names[0])

    def strip(tag):
        return tag.rsplit("}", 1)[-1]

    objects, colors = {}, {}
    meshes = []

    def parse_model(name):
        root = ET.fromstring(_cut_meshes(z.read(name), meshes))
        for el in root.iter():
            tg = strip(el.tag)
            if tg in ("basematerials", "colorgroup"):
                lst = []
                for c in el:
                    hexc = c.get("displaycolor") or c.get("color") or "#C8C8CC"
                    hexc = hexc.lstrip("#")
                    try:
                        rgb = tuple(int(hexc[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
                    except ValueError:
                        rgb = DEFAULT_COLOR[:3]
                    lst.append(rgb)
                colors[el.get("id")] = lst
        for ob in root.iter():
            if strip(ob.tag) != "object":
                continue
            oid = ob.get("id")
            entry = {"mesh": None, "components": [], "pid": ob.get("pid"), "pindex": ob.get("pindex")}
            for ch in ob:
                tg = strip(ch.tag)
                if tg == "mesh":
                    k = ch.get("gamma_mesh")
                    entry["mesh"] = _3mf_mesh(meshes[int(k)]) if k is not None else None
                elif tg == "components":
                    for c in ch:
                        entry["components"].append((c.get("objectid"), _3mf_mat(c.get("transform"))))
            objects[oid] = entry
        build = []
        for it in root.iter():
            if strip(it.tag) == "item":
                build.append((it.get("objectid"), _3mf_mat(it.get("transform"))))
        return build

    for n in names:
        if n != main:
            try:
                parse_model(n)
            except ET.ParseError:
                pass
    build = parse_model(main)
    parts = []
    nverts = [0]

    def emit(oid, M, depth=0):
        ob = objects.get(oid)
        if ob is None or depth > 32:
            return
        if ob["mesh"]:
            V, idx, props = ob["mesh"]
            if len(V) and len(idx):
                V = V @ M[:3, :3].T + M[:3, 3]
                nverts[0] += len(V)
                idx = np.clip(idx, 0, len(V) - 1)
                pos = V[idx.reshape(-1)]
                col = None
                base_col = DEFAULT_COLOR
                grp = colors.get(ob["pid"]) if ob["pid"] else None
                if grp:
                    try:
                        k = int(ob["pindex"] or 0)
                    except ValueError:
                        k = 0
                    base_col = (*grp[min(k, len(grp) - 1)], 1.0)
                if props and any(p[1] is not None for p in props):
                    fc = []
                    for pid, p1 in props:
                        g = colors.get(pid or ob["pid"])
                        if g and p1 is not None and p1.isdigit():
                            fc.append(g[min(int(p1), len(g) - 1)])
                        else:
                            fc.append(base_col[:3])
                    col = np.repeat(np.array(fc, dtype=np.float32), 3, axis=0)
                parts.append(Part(pos, col=col, color=(1, 1, 1, 1) if col is not None else base_col))
        for cid, CM in ob["components"]:
            emit(cid, M @ CM, depth + 1)

    for oid, M in (build or [(k, np.eye(4)) for k in objects]):
        emit(oid, M)
    if not parts:
        raise ModelError("3mf")
    return parts, nverts[0]


def _3mf_mat(s):
    M = np.eye(4)
    if s:
        try:
            v = [float(x) for x in s.split()]
            if len(v) == 12:
                # 3MF: m00 m01 m02 m10 m11 m12 m20 m21 m22 m30 m31 m32 (satır vektörü)
                A = np.array(v).reshape(4, 3)
                M[:3, :3] = A[:3].T
                M[:3, 3] = A[3]
        except ValueError:
            pass
    return M


# ------------------------------------------------------------------ STEP / IGES (CAD)
# CAD dosyalarında hazır üçgen yoktur (B-rep: matematiksel yüzeyler). OpenCASCADE çekirdeği (gmsh
# paketinin içinde, tek DLL) bunları görüntüleme için üçgenler. İsteğe bağlıdır: kurulumda "STEP desteği"
# seçilirse <exe>\step\ klasörüne gelir; yalnızca ilk CAD dosyası açılınca yüklenir (açılışı yavaşlatmaz).
CAD_EXT = {".step", ".stp", ".iges", ".igs"}
_cad_lock = None
_cad_ready = False
_cad_cache = {}   # (yol, değişme zamanı, boyut) → (parçalar, köşe sayısı); küçük resim + görüntüleyici çift iş yapmasın


def _cad_dir():
    import sys
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else None
    return os.path.join(base, "step") if base else None


def cad_available():
    """STEP motoru (gmsh) kurulu mu? Modülü yüklemeden bakar."""
    d = _cad_dir()
    if d and os.path.isfile(os.path.join(d, "gmsh.py")):
        return True
    import importlib.util
    try:
        return importlib.util.find_spec("gmsh") is not None
    except (ImportError, ValueError):
        return False


def _gmsh():
    global _cad_ready
    d = _cad_dir()
    if d and os.path.isdir(d):
        import sys
        if d not in sys.path:
            sys.path.insert(0, d)
    try:
        import gmsh
    except Exception:
        raise ModelError("cad_missing")
    if not _cad_ready:
        gmsh.initialize(interruptible=False)   # iş parçacığında: sinyal işleyici kurmasın
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.Verbosity", 1)
        _cad_ready = True
    return gmsh


def load_cad(path):
    global _cad_lock
    import threading
    if _cad_lock is None:
        _cad_lock = threading.Lock()
    st = os.stat(path)
    key = (os.path.normcase(os.path.abspath(path)), st.st_mtime, st.st_size)
    with _cad_lock:   # gmsh tek bir genel durum tutar; aynı anda tek dosya
        res = _cad_cache.get(key)
        if res is None:
            res = _load_cad_locked(path)
            _cad_cache.clear()   # yalnızca sonuncusu (bellek)
            _cad_cache[key] = res
    parts, n, stats = res
    # load_model parçaları yerinde çevirdiği için her çağrıya yeni Part nesneleri (diziler paylaşılır)
    return [Part(p.pos, p.nrm, color=p.color) for p in parts], n, (dict(stats) if stats else None)


def _load_cad_locked(path):
    gmsh = _gmsh()
    src, tmp = path, None
    if not path.isascii():
        # gmsh dosya yolunu ANSI ile açıyor; Türkçe / Unicode adlarda geçici ASCII kopya
        import tempfile
        import shutil
        fd, tmp = tempfile.mkstemp(prefix="gamma_cad_", suffix=os.path.splitext(path)[1])
        os.close(fd)
        shutil.copyfile(path, tmp)
        src = tmp
    try:
        gmsh.clear()
        gmsh.option.setNumber("Geometry.OCCImportLabels", 1)          # renkler ve adlar
        # Görüntüleme üçgenlemesi (BRepMesh): sapma model boyutuna göre; CAD programlarının kullandığı yol
        gmsh.option.setNumber("Mesh.StlLinearDeflectionRelative", 1)
        gmsh.option.setNumber("Mesh.StlLinearDeflection", 0.0015)
        gmsh.option.setNumber("Mesh.StlAngularDeflection", 0.35)
        try:
            gmsh.model.occ.importShapes(src, highestDimOnly=True)
            gmsh.model.occ.synchronize()
            gmsh.model.mesh.importStl()
        except Exception as e:
            raise ModelError("cad:" + str(e))
        tags, coords, _ = gmsh.model.mesh.getNodes()
        if not len(tags):
            raise ModelError("empty")
        tags = np.asarray(tags, dtype=np.int64)
        lut = np.zeros(int(tags.max()) + 1, dtype=np.int64)
        lut[tags] = np.arange(len(tags))
        X = np.asarray(coords, dtype=np.float64).reshape(-1, 3)
        groups = {}   # renk → [(pos, nrm)]

        def color_of(tag):
            r, g, b, a = gmsh.model.getColor(2, tag)
            if a == 0:   # yüzeyde renk yoksa katının rengi
                up, _ = gmsh.model.getAdjacencies(2, tag)
                for v in up:
                    r, g, b, a = gmsh.model.getColor(3, int(v))
                    if a:
                        break
            if a == 0:
                return DEFAULT_COLOR
            return (r / 255.0, g / 255.0, b / 255.0, max(a, 1) / 255.0)

        for _dim, tag in gmsh.model.getEntities(2):
            types, _, nodes = gmsh.model.mesh.getElements(2, tag)
            for ty, nd in zip(types, nodes):
                if ty != 2 or not len(nd):
                    continue
                idx = lut[np.asarray(nd, dtype=np.int64)].reshape(-1, 3)
                # Yüz içinde yumuşak, yüzler arası keskin gölgeleme: normaller yalnızca bu yüzden
                u, inv = np.unique(idx.reshape(-1), return_inverse=True)
                P = X[u].astype(np.float32)
                li = inv.reshape(-1, 3)
                nrm = smooth_normals(P, li)[li.reshape(-1)]
                groups.setdefault(color_of(tag), []).append((P[li.reshape(-1)], nrm))
        parts = [Part(np.concatenate([g[0] for g in v]), np.concatenate([g[1] for g in v]), color=c)
                 for c, v in groups.items()]
        if not parts:
            raise ModelError("empty")
        # Hacim / alan: üçgenlerden değil, CAD yüzeylerinden tam hesap. Görüntüleme üçgenlemesi yüzler arasında
        # birebir örtüşmediği için "kapalı mı" sorusunun cevabı da katı (solid) olup olmamasından gelir.
        stats = None
        vols = gmsh.model.getEntities(3)
        if vols:
            try:
                vol = sum(abs(gmsh.model.occ.getMass(3, t)) for _d, t in vols)
                area = sum(abs(gmsh.model.occ.getMass(2, t)) for _d, t in gmsh.model.getEntities(2))
                stats = {"volume": float(vol), "area": float(area), "closed": True}
            except Exception:
                stats = None
        return parts, len(tags), stats
    finally:
        try:
            gmsh.clear()
        except Exception:
            pass
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass


# ------------------------------------------------------------------ giriş noktası
_LOADERS = {".stl": load_stl, ".obj": load_obj, ".ply": load_ply, ".off": load_off,
            ".glb": load_gltf, ".gltf": load_gltf, ".3mf": load_3mf,
            ".step": load_cad, ".stp": load_cad, ".iges": load_cad, ".igs": load_cad}


def load_model(path):
    """Dosyayı okuyup Model döndürür (hata durumunda ModelError)."""
    ext = os.path.splitext(path)[1].lower()
    fn = _LOADERS.get(ext)
    if fn is None:
        raise ModelError("format")
    stats = None
    try:
        res = fn(path)
        parts, nverts = res[0], res[1]
        if len(res) > 2:   # CAD: tam hacim / alan
            stats = res[2]
    except ModelError:
        raise
    except Exception as e:  # bozuk dosya
        raise ModelError(str(e) or e.__class__.__name__)
    if ext in Z_UP_EXT:
        for p in parts:
            p.pos = _zup_to_yup(p.pos)
            if p.nrm is not None:
                p.nrm = _zup_to_yup(p.nrm)
    fmt = {".stp": "STEP", ".igs": "IGES"}.get(ext, ext.strip(".").upper())
    model = Model(parts, fmt, nverts)
    if stats:
        model._stats = stats
    return model


# ------------------------------------------------------------------ yazılım çizici (küçük resim)
def render_preview(model, w=320, h=240, yaw=-35.0, pitch=25.0, bg=((44, 44, 46), (20, 20, 21)), ss=2):
    """GPU olmadan, numpy ile z-tamponlu basit bir çizim (QImage döner). İş parçacığında güvenli."""
    from PyQt6.QtGui import QImage
    from PyQt6.QtCore import Qt
    W, H = w * ss, h * ss
    pos = np.concatenate([p.pos for p in model.parts]).astype(np.float64)
    tri_col = []
    for p in model.parts:
        n = len(p.pos) // 3
        base = np.array(p.color[:3], dtype=np.float64)
        if p.col is not None:
            c = p.col.reshape(-1, 3, 3).mean(axis=1) * base
        elif p.texture is not None and p.uv is not None:
            c = _sample_texture(p.texture, p.uv.reshape(-1, 3, 2).mean(axis=1)) * base
        else:
            c = np.tile(base, (n, 1))
        tri_col.append(c)
    col = np.concatenate(tri_col)
    good = np.isfinite(pos).all(axis=1).reshape(-1, 3).all(axis=1)
    tri = (pos - model.center).reshape(-1, 3, 3)[good]
    col = col[good]
    # görünüm dönüşümü
    cy, sy = np.cos(np.radians(yaw)), np.sin(np.radians(yaw))
    cp, sp = np.cos(np.radians(pitch)), np.sin(np.radians(pitch))
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    R = Rx @ Ry
    v = tri @ R.T
    # yüz normali ve ışık
    fn = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    ln = np.linalg.norm(fn, axis=1)
    ln[ln == 0] = 1
    fn /= ln[:, None]
    light = np.array([0.35, 0.55, 0.75])
    light /= np.linalg.norm(light)
    d = np.abs(fn @ light)
    rim = np.abs(fn[:, 2])
    shade = 0.28 + 0.55 * d + 0.22 * rim
    rgb = np.clip(col * shade[:, None], 0, 1)
    # ortografik izdüşüm (biraz pay bırakılır)
    xy = v[:, :, :2]
    ext = np.abs(v.reshape(-1, 3)[:, :2]).max(axis=0) if len(v) else np.array([1.0, 1.0])
    s = 0.86 * min(W / (2 * max(ext[0], 1e-9)), H / (2 * max(ext[1], 1e-9)))
    px = xy[:, :, 0] * s + W / 2
    py = -xy[:, :, 1] * s + H / 2
    pz = v[:, :, 2]
    img = np.empty((H, W, 3), dtype=np.float64)
    g = np.linspace(0, 1, H)[:, None]
    for k in range(3):
        img[:, :, k] = (bg[0][k] * (1 - g) + bg[1][k] * g) / 255.0
    zbuf = np.full(H * W, -np.inf)
    cbuf = np.zeros((H * W, 3))
    x0 = np.clip(np.floor(px.min(axis=1)), 0, W - 1).astype(np.int64)
    x1 = np.clip(np.ceil(px.max(axis=1)), 0, W - 1).astype(np.int64)
    y0 = np.clip(np.floor(py.min(axis=1)), 0, H - 1).astype(np.int64)
    y1 = np.clip(np.ceil(py.max(axis=1)), 0, H - 1).astype(np.int64)
    bw = x1 - x0 + 1
    bh = y1 - y0 + 1
    area = bw * bh
    order = np.arange(len(area))
    budget = 4_000_000
    start = 0
    while start < len(order):
        cs = np.cumsum(area[start:])
        stop = start + max(1, int(np.searchsorted(cs, budget)))
        sel = order[start:stop]
        start = stop
        a = area[sel]
        rep = np.repeat(sel, a)
        if not len(rep):
            continue
        offs = np.arange(len(rep)) - np.repeat(np.cumsum(a) - a, a)
        X = x0[rep] + offs % bw[rep] + 0.5
        Y = y0[rep] + offs // bw[rep] + 0.5
        ax, ay = px[rep, 0], py[rep, 0]
        bx, by = px[rep, 1], py[rep, 1]
        cx, cy_ = px[rep, 2], py[rep, 2]
        den = (by - cy_) * (ax - cx) + (cx - bx) * (ay - cy_)
        den[den == 0] = 1e-12
        l1 = ((by - cy_) * (X - cx) + (cx - bx) * (Y - cy_)) / den
        l2 = ((cy_ - ay) * (X - cx) + (ax - cx) * (Y - cy_)) / den
        l3 = 1 - l1 - l2
        eps = -1e-6
        inside = (l1 >= eps) & (l2 >= eps) & (l3 >= eps)
        if not inside.any():
            continue
        rep, X, Y = rep[inside], X[inside], Y[inside]
        z = l1[inside] * pz[rep, 0] + l2[inside] * pz[rep, 1] + l3[inside] * pz[rep, 2]
        pix = (Y.astype(np.int64)) * W + X.astype(np.int64)
        o = np.lexsort((-z, pix))
        pix, z, rep = pix[o], z[o], rep[o]
        first = np.ones(len(pix), dtype=bool)
        first[1:] = pix[1:] != pix[:-1]
        pix, z, rep = pix[first], z[first], rep[first]
        better = z > zbuf[pix]
        zbuf[pix[better]] = z[better]
        cbuf[pix[better]] = rgb[rep[better]]
    mask = np.isfinite(zbuf).reshape(H, W)
    img[mask] = cbuf.reshape(H, W, 3)[mask]
    arr = np.ascontiguousarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    q = QImage(arr.data, W, H, W * 3, QImage.Format.Format_RGB888).copy()
    if ss > 1:
        q = q.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return q


def _sample_texture(qimg, uv):
    try:
        w, h = qimg.width(), qimg.height()
        ptr = qimg.constBits()
        ptr.setsize(qimg.sizeInBytes())
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape(h, qimg.bytesPerLine())[:, :w * 4].reshape(h, w, 4)
        u = np.clip((uv[:, 0] % 1.0) * (w - 1), 0, w - 1).astype(np.int64)
        # İç UV düzeni OBJ'deki gibidir (v=0 resmin altı)
        v = np.clip((1.0 - uv[:, 1] % 1.0) * (h - 1), 0, h - 1).astype(np.int64)
        return arr[v, u, :3].astype(np.float64) / 255.0
    except Exception:
        return np.full((len(uv), 3), 0.8)


def model_info_text(model, t):
    """Medya bilgisi penceresi için kısa özet (iş parçacığında çağrılır; hacim hesabı burada yapılır)."""
    lang = t("lang_code")

    def n(v):
        s = f"{v:,}"
        return s.replace(",", ".") if lang == "tr" else s
    st = model_stats(model)
    lines = [f"{t('m_format')}: {model.fmt}",
             f"{t('m_size')}: {dims_text(model, lang)}"]
    if st["closed"] is False:
        lines.append(f"{t('m_volume')}: ≈ {fmt_volume(st['volume'], lang)}  ({t('m_open_note')})")
    else:
        lines.append(f"{t('m_volume')}: {fmt_volume(st['volume'], lang)}")
    lines.append(f"{t('m_area')}: {fmt_area(st['area'], lang)}")
    if st["closed"] is not None:
        lines.append(f"{t('m_closed')}: {t('m_closed_yes') if st['closed'] else t('m_closed_no')}")
    lines += [f"{t('m_triangles')}: {n(model.triangles)}",
              f"{t('m_vertices')}: {n(model.vertices)}",
              f"{t('m_parts')}: {len(model.parts)}"]
    ntex = len({id(p.texture) for p in model.parts if p.texture is not None})
    if ntex:
        lines.append(f"{t('m_textures')}: {ntex}")
    return "\n".join(lines)


# ------------------------------------------------------------------ hacim / alan / kapalılık
CLOSED_CHECK_LIMIT = 2_000_000   # bundan büyük modellerde kapalılık denetimi atlanır (bellek / süre)


def model_stats(model):
    """Hacim (mm³), yüzey alanı (mm²) ve kapalı (su geçirmez) olup olmadığı. Sonuç modelde saklanır.

    Hacim, her parçanın işaretli dört yüzlü toplamının mutlak değeridir; yüzey kapalı değilse yaklaşıktır.
    Birim: glTF metre olduğu için mm'ye çevrilir.
    """
    cached = getattr(model, "_stats", None)
    if cached is not None:
        return cached
    k = 1000.0 if model.fmt in METER_FMTS else 1.0
    vol = area = 0.0
    for p in model.parts:
        tri = p.pos.astype(np.float64).reshape(-1, 3, 3) * k
        tri = tri[np.isfinite(tri).all(axis=(1, 2))]
        a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
        vol += abs(float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0)
        area += float(np.linalg.norm(np.cross(b - a, c - a), axis=1).sum()) / 2.0
    closed = None
    if model.triangles <= CLOSED_CHECK_LIMIT:
        closed = all(_is_closed(p.pos, float(np.linalg.norm(model.size)) or 1.0) for p in model.parts)
    model._stats = {"volume": vol, "area": area, "closed": closed}
    return model._stats


def _is_closed(pos, scale):
    """Her kenarı tam iki üçgen paylaşıyorsa yüzey kapalıdır (3B baskıya uygun)."""
    q = np.round(pos.astype(np.float64) / (scale * 1e-6)).astype(np.int64)   # çok yakın köşeleri birleştir
    _, vid = np.unique(q, axis=0, return_inverse=True)
    t = vid.reshape(-1, 3)
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    e = e[e[:, 0] != e[:, 1]]
    e.sort(axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return bool(len(counts)) and bool((counts == 2).all())


def fmt_volume(mm3, lang="tr"):
    if mm3 < 1000:
        return f"{fmt_num(mm3, lang)} mm³"
    if mm3 < 1e9:
        return f"{fmt_num(mm3 / 1000, lang)} cm³"
    return f"{fmt_num(mm3 / 1e9, lang)} m³"


def fmt_area(mm2, lang="tr"):
    if mm2 < 100:
        return f"{fmt_num(mm2, lang)} mm²"
    if mm2 < 1e6:
        return f"{fmt_num(mm2 / 100, lang)} cm²"
    return f"{fmt_num(mm2 / 1e6, lang)} m²"


# ------------------------------------------------------------------ ölçüler
# glTF'nin birimi metredir; STL / 3MF / PLY / OFF / OBJ (3B yazıcı, CAD) milimetre kabul edilir.
METER_FMTS = {"GLB", "GLTF"}


def dims_unit(model, largest):
    """Model birimini okunaklı birime çeviren (çarpan, birim adı)."""
    if model.fmt in METER_FMTS:
        if largest < 0.01:
            return 1000.0, "mm"
        return (100.0, "cm") if largest < 1.0 else (1.0, "m")
    return 1.0, "mm"


def dims_values(model):
    """(genişlik, derinlik, yükseklik, birim) — okunaklı birime çevrilmiş."""
    sx, sy, sz = (float(x) for x in model.size)
    w, d, h = sx, sz, sy   # iç düzen Y-yukarı
    k, unit = dims_unit(model, max(w, d, h))
    return w * k, d * k, h * k, unit


def fmt_num(v, lang="tr"):
    if abs(v) >= 1000:
        s = f"{v:.0f}"
    elif abs(v) < 1e-3:
        s = f"{v:.2g}" if v else "0"
    else:
        s = f"{v:.4g}"
    return s.replace(".", ",") if lang == "tr" else s


def dims_text(model, lang="tr"):
    w, d, h, unit = dims_values(model)
    return f"{fmt_num(w, lang)} × {fmt_num(d, lang)} × {fmt_num(h, lang)} {unit}"


# ------------------------------------------------------------------ yazma (dönüştürme)
EXPORT_FORMATS = (("STL", ".stl"), ("OBJ", ".obj"), ("3MF", ".3mf"), ("GLB", ".glb"), ("PLY", ".ply"))


def _yup_to_zup(a):
    out = np.empty_like(a)
    out[:, 0] = a[:, 0]
    out[:, 1] = -a[:, 2]
    out[:, 2] = a[:, 1]
    return out


def _weld(*cols):
    """Aynı köşeleri birleştir: (benzersiz satırlar, her eski satırın yeni indeksi)."""
    data = np.ascontiguousarray(np.concatenate([c.reshape(len(c), -1) for c in cols], axis=1), dtype=np.float32)
    if not len(data):
        return data, np.zeros(0, dtype=np.int64)
    row = np.dtype((np.void, data.dtype.itemsize * data.shape[1]))
    _, first, inv = np.unique(data.view(row).ravel(), return_index=True, return_inverse=True)
    return data[first], inv.reshape(-1).astype(np.int64)


def _png_bytes(qimg):
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    qimg.save(buf, "PNG")
    buf.close()
    return bytes(ba.data())


def _vertex_colors(p):
    """Parçanın köşe renkleri (0..1, N×3): köşe rengi × malzeme rengi, doku varsa dokudan örneklenir."""
    base = np.array(p.color[:3], dtype=np.float32)
    if p.col is not None:
        return np.clip(p.col * base, 0, 1)
    if p.texture is not None and p.uv is not None:
        return np.clip(_sample_texture(p.texture, p.uv).astype(np.float32) * base, 0, 1)
    return np.tile(base, (len(p.pos), 1))


def _part_display_color(p):
    """Parçanın tek rengi (3MF malzemesi için): dokuluysa ortalama doku rengi."""
    return _vertex_colors(p).mean(axis=0) if len(p.pos) else np.array(p.color[:3])


def _has_color(model):
    return any(p.col is not None or p.texture is not None or tuple(p.color[:3]) != DEFAULT_COLOR[:3]
               for p in model.parts)


def export_model(model, path):
    """Modeli uzantıya göre STL / OBJ / 3MF / GLB / PLY olarak yazar (iş parçacığında çalışabilir).

    glTF metre, diğerleri milimetre kabul edildiği için gerekirse ×1000 / ÷1000 ölçeklenir.
    Z-yukarı biçimlere (STL / 3MF / PLY) geri çevrilerek yazılır.
    """
    ext = os.path.splitext(path)[1].lower()
    src_m = model.fmt in METER_FMTS
    dst_m = ext in (".glb", ".gltf")
    scale = 1000.0 if (src_m and not dst_m) else 0.001 if (dst_m and not src_m) else 1.0
    zup = ext in Z_UP_EXT
    parts = []
    for p in model.parts:
        pos = p.pos.astype(np.float64) * scale
        nrm = p.nrm
        if zup:
            pos = _yup_to_zup(pos)
            nrm = _yup_to_zup(nrm) if nrm is not None else None
        parts.append((p, pos.astype(np.float32), nrm))
    tmp = path + ".gamma-tmp"
    writer = {".stl": _write_stl, ".obj": _write_obj, ".3mf": _write_3mf, ".glb": _write_glb,
              ".ply": _write_ply}.get(ext)
    if writer is None:
        raise ModelError("format")
    try:
        writer(model, parts, tmp, path)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def _write_stl(model, parts, tmp, final):
    pos = np.concatenate([q[1] for q in parts]).reshape(-1, 3, 3)
    fn = np.cross(pos[:, 1] - pos[:, 0], pos[:, 2] - pos[:, 0])
    ln = np.linalg.norm(fn, axis=1)
    ln[ln == 0] = 1
    fn = (fn / ln[:, None]).astype(np.float32)
    rec = np.zeros(len(pos), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"] = fn
    rec["v"] = pos
    with open(tmp, "wb") as f:
        head = b"gamma STL export"
        f.write(head + b"\0" * (80 - len(head)))
        f.write(struct.pack("<I", len(pos)))
        f.write(rec.tobytes())


def _write_obj(model, parts, tmp, final):
    base = os.path.splitext(os.path.basename(final))[0]
    folder = os.path.dirname(final)
    mtl_name = base + ".mtl"
    allpos = np.concatenate([q[1] for q in parts])
    V, vi = _weld(allpos)
    has_uv = any(p.uv is not None and p.texture is not None for p, _, _ in parts)
    uvs = np.concatenate([p.uv if (p.uv is not None and p.texture is not None) else np.zeros((len(p.pos), 2), np.float32)
                          for p, _, _ in parts]) if has_uv else None
    VT, ti = _weld(uvs) if has_uv else (None, None)
    nrms = np.concatenate([q[2] if q[2] is not None else face_normals(q[1]) for q in parts])
    VN, ni = _weld(np.round(nrms, 4))
    mtl = []
    tex_files = {}
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# gamma OBJ export\nmtllib {mtl_name}\n")
        np.savetxt(f, V, fmt="v %.6g %.6g %.6g")
        if VT is not None:
            np.savetxt(f, VT, fmt="vt %.6g %.6g")
        np.savetxt(f, VN, fmt="vn %.4g %.4g %.4g")
        off = 0
        for k, (p, pos, _) in enumerate(parts):
            n = len(pos)
            r, g, b, a = (float(c) for c in p.color)
            mtl.append(f"newmtl m{k}\nKd {r:.4g} {g:.4g} {b:.4g}\nd {a:.4g}\n")
            if p.texture is not None and p.uv is not None:
                # Aynı dokuyu paylaşan parçalar için tek dosya
                tex_name = tex_files.get(id(p.texture))
                if tex_name is None:
                    tex_name = f"{base}_{len(tex_files) + 1}.png"
                    p.texture.save(os.path.join(folder, tex_name), "PNG")
                    tex_files[id(p.texture)] = tex_name
                mtl.append(f"map_Kd {tex_name}\n")
            f.write(f"o part{k}\nusemtl m{k}\n")
            sl = slice(off, off + n)
            if VT is not None:
                cols = np.stack([vi[sl], ti[sl], ni[sl]], axis=1).reshape(-1, 9) + 1
                np.savetxt(f, cols, fmt="f %d/%d/%d %d/%d/%d %d/%d/%d")
            else:
                cols = np.stack([vi[sl], ni[sl]], axis=1).reshape(-1, 6) + 1
                np.savetxt(f, cols, fmt="f %d//%d %d//%d %d//%d")
            off += n
    with open(os.path.join(folder, mtl_name), "w", encoding="utf-8", newline="\n") as f:
        f.write("# gamma OBJ export\n" + "".join(mtl))


def _write_ply(model, parts, tmp, final):
    allpos = np.concatenate([q[1] for q in parts])
    color = _has_color(model)
    if color:
        cols = np.concatenate([_vertex_colors(p) for p, _, _ in parts])
        cols = np.round(cols * 255).astype(np.float32)
        W, idx = _weld(allpos, cols)
    else:
        W, idx = _weld(allpos)
    nv, nf = len(W), len(idx) // 3
    head = ["ply", "format binary_little_endian 1.0", "comment gamma PLY export", f"element vertex {nv}",
            "property float x", "property float y", "property float z"]
    if color:
        head += ["property uchar red", "property uchar green", "property uchar blue"]
    head += [f"element face {nf}", "property list uchar int vertex_indices", "end_header"]
    vt = [("p", "<f4", 3)] + ([("c", "u1", 3)] if color else [])
    vrec = np.zeros(nv, dtype=vt)
    vrec["p"] = W[:, :3]
    if color:
        vrec["c"] = np.clip(W[:, 3:6], 0, 255).astype(np.uint8)
    frec = np.zeros(nf, dtype=[("n", "u1"), ("i", "<i4", 3)])
    frec["n"] = 3
    frec["i"] = idx.reshape(-1, 3)
    with open(tmp, "wb") as f:
        f.write(("\n".join(head) + "\n").encode("ascii"))
        f.write(vrec.tobytes())
        f.write(frec.tobytes())


def _write_3mf(model, parts, tmp, final):
    allpos = np.concatenate([q[1] for q in parts])
    V, idx = _weld(allpos)
    tri = idx.reshape(-1, 3)
    pid = np.concatenate([np.full(len(q[1]) // 3, k, dtype=np.int64) for k, q in enumerate(parts)])
    # 3MF'de dejenere (aynı köşeli) üçgenlere izin verilmez
    ok = (tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])
    tri, pid = tri[ok], pid[ok]
    color = _has_color(model)
    out = ['<?xml version="1.0" encoding="UTF-8"?>\n'
           '<model unit="millimeter" xml:lang="en-US" '
           'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
           '<metadata name="Application">gamma</metadata>\n<resources>\n']
    if color:
        out.append('<basematerials id="1">\n')
        for k, (p, _, _) in enumerate(parts):
            c = np.clip(_part_display_color(p) * 255, 0, 255).astype(int)
            out.append(f'<base name="m{k}" displaycolor="#{c[0]:02X}{c[1]:02X}{c[2]:02X}" />\n')
        out.append("</basematerials>\n")
    oid = 2
    attr = ' pid="1" pindex="0"' if color else ""
    out.append(f'<object id="{oid}" type="model"{attr}>\n<mesh>\n<vertices>\n')
    body = ["".join(out)]
    body.append("\n".join(f'<vertex x="{x:.6g}" y="{y:.6g}" z="{z:.6g}" />' for x, y, z in V[:, :3].tolist()))
    body.append("\n</vertices>\n<triangles>\n")
    if color:
        body.append("\n".join(f'<triangle v1="{a}" v2="{b}" v3="{c}" pid="1" p1="{k}" />'
                              for (a, b, c), k in zip(tri.tolist(), pid.tolist())))
    else:
        body.append("\n".join(f'<triangle v1="{a}" v2="{b}" v3="{c}" />' for a, b, c in tri.tolist()))
    body.append(f"\n</triangles>\n</mesh>\n</object>\n</resources>\n<build>\n<item objectid=\"{oid}\" />\n"
                "</build>\n</model>\n")
    ctypes = ('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />'
              '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml" />'
              '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel" /></Relationships>')
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", "".join(body))


def _write_glb(model, parts, tmp, final):
    blob = bytearray()
    views, accs, meshes_prims, mats, textures, images = [], [], [], [], [], []

    def add_view(data, target=None):
        while len(blob) % 4:
            blob.append(0)
        v = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)}
        if target:
            v["target"] = target
        blob.extend(data)
        views.append(v)
        return len(views) - 1

    def add_acc(arr, typ, ctype=5126, target=34962, minmax=False):
        arr = np.ascontiguousarray(arr)
        a = {"bufferView": add_view(arr.tobytes(), target), "componentType": ctype,
             "count": int(len(arr)), "type": typ}
        if minmax:
            a["min"] = [float(x) for x in arr.min(axis=0)]
            a["max"] = [float(x) for x in arr.max(axis=0)]
        accs.append(a)
        return len(accs) - 1

    tex_ids = {}
    for p, pos, nrm in parts:
        if nrm is None:
            nrm = face_normals(pos)
        textured = p.texture is not None and p.uv is not None
        cols = [pos, np.round(nrm, 5)]
        if textured:
            uv = p.uv.copy()
            uv[:, 1] = 1.0 - uv[:, 1]   # glTF: üst sol köşe orijin
            cols.append(uv)
        if p.col is not None:
            cols.append(p.col)
        W, idx = _weld(*cols)
        attrs = {"POSITION": add_acc(W[:, 0:3], "VEC3", minmax=True)}
        n = W[:, 3:6]
        ln = np.linalg.norm(n, axis=1)
        ln[ln == 0] = 1
        attrs["NORMAL"] = add_acc((n / ln[:, None]).astype(np.float32), "VEC3")
        c = 6
        if textured:
            attrs["TEXCOORD_0"] = add_acc(W[:, c:c + 2], "VEC2")
            c += 2
        if p.col is not None:
            attrs["COLOR_0"] = add_acc(np.clip(W[:, c:c + 3], 0, 1), "VEC3")
        ind = add_acc(idx.astype(np.uint32), "SCALAR", ctype=5125, target=34963)
        mat = {"pbrMetallicRoughness": {"baseColorFactor": [float(x) for x in p.color],
                                        "metallicFactor": 0.0, "roughnessFactor": 0.8},
               "doubleSided": True}
        if p.color[3] < 0.99:
            mat["alphaMode"] = "BLEND"
        if textured:
            key = id(p.texture)
            if key not in tex_ids:
                images.append({"bufferView": add_view(_png_bytes(p.texture)), "mimeType": "image/png"})
                textures.append({"source": len(images) - 1})
                tex_ids[key] = len(textures) - 1
            mat["pbrMetallicRoughness"]["baseColorTexture"] = {"index": tex_ids[key]}
        mats.append(mat)
        meshes_prims.append({"attributes": attrs, "indices": ind, "material": len(mats) - 1})
    while len(blob) % 4:
        blob.append(0)
    js = {"asset": {"version": "2.0", "generator": "gamma"}, "scene": 0, "scenes": [{"nodes": [0]}],
          "nodes": [{"mesh": 0}], "meshes": [{"primitives": meshes_prims}], "materials": mats,
          "buffers": [{"byteLength": len(blob)}], "bufferViews": views, "accessors": accs}
    if images:
        js["images"] = images
        js["textures"] = textures
    jb = json.dumps(js, separators=(",", ":")).encode("utf-8")
    jb += b" " * (-len(jb) % 4)
    with open(tmp, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(jb) + 8 + len(blob)))
        f.write(struct.pack("<I4s", len(jb), b"JSON") + jb)
        f.write(struct.pack("<I4s", len(blob), b"BIN\0") + bytes(blob))


__all__ = ["MODEL_EXT", "Model", "Part", "ModelError", "load_model", "render_preview", "model_info_text",
           "dims_text", "dims_values", "export_model", "EXPORT_FORMATS"]
