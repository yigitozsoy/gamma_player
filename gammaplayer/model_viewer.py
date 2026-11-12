"""3D model görüntüleyici (OpenGL).

Sol sürükle: döndür · Sağ / orta sürükle veya Shift+sol: kaydır · Tekerlek: yakınlaştır.
Ana pencerede ImageViewer ile aynı sinyalleri verir; böylece alttaki kontrol çubuğu ortak kullanılır.
"""
import math
import time

import numpy as np
from PyQt6.QtCore import Qt, QEvent, QPoint, QPointF, QRectF, QTimer, pyqtSignal
from PyQt6.QtGui import QMatrix4x4, QSurfaceFormat, QVector3D, QPainter, QFont, QColor, QPen, QImage, QGuiApplication
from PyQt6.QtOpenGL import (QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram, QOpenGLTexture,
                            QOpenGLVersionFunctionsFactory, QOpenGLVersionProfile,
                            QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat)
from PyQt6.QtOpenGL import QOpenGLWindow
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout

from .theme import qcolor

GL_FLOAT = 0x1406
GL_TRIANGLES, GL_LINES = 0x0004, 0x0001
GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT = 0x4000, 0x0100
GL_DEPTH_TEST, GL_BLEND, GL_MULTISAMPLE, GL_POLYGON_OFFSET_FILL = 0x0B71, 0x0BE2, 0x809D, 0x8037
GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA = 0x0302, 0x0303
GL_FRONT_AND_BACK, GL_LINE, GL_FILL = 0x0408, 0x1B01, 0x1B02
GL_LEQUAL = 0x0203

VERT = """
#version 120
attribute vec3 a_pos;
attribute vec3 a_nrm;
attribute vec3 a_col;
attribute vec2 a_uv;
uniform mat4 u_mvp;
uniform mat4 u_mv;
varying vec3 v_n;
varying vec3 v_c;
varying vec2 v_uv;
varying vec3 v_p;
void main() {
    v_n = (u_mv * vec4(a_nrm, 0.0)).xyz;
    v_p = (u_mv * vec4(a_pos, 1.0)).xyz;
    v_c = a_col;
    v_uv = a_uv;
    gl_Position = u_mvp * vec4(a_pos, 1.0);
}
"""

FRAG = """
#version 120
uniform vec4 u_color;
uniform int u_usecol;
uniform int u_usetex;
uniform int u_flat;
uniform sampler2D u_tex;
varying vec3 v_n;
varying vec3 v_c;
varying vec2 v_uv;
varying vec3 v_p;
void main() {
    if (u_flat == 1) { gl_FragColor = u_color; return; }
    vec3 n = normalize(v_n);
    vec3 V = normalize(-v_p);
    if (dot(n, V) < 0.0) n = -n;          // iki yüzlü: ters normalli ağlar da aydınlık görünür
    vec4 base = u_color;
    if (u_usecol == 1) base.rgb *= v_c;
    if (u_usetex == 1) base *= texture2D(u_tex, v_uv);
    vec3 L1 = normalize(vec3(0.45, 0.65, 0.75));
    vec3 L2 = normalize(vec3(-0.7, 0.15, 0.35));
    float hemi = mix(0.26, 0.40, n.y * 0.5 + 0.5);
    float diff = 0.45 * max(dot(n, L1), 0.0) + 0.15 * max(dot(n, L2), 0.0) + 0.32 * max(dot(n, V), 0.0);
    float spec = pow(max(dot(n, normalize(L1 + V)), 0.0), 48.0) * 0.15;
    gl_FragColor = vec4(base.rgb * (hemi + diff) + vec3(spec), base.a);
}
"""


class ModelViewer(QWidget):
    """3D görüntüleyicinin pencere içindeki yeri.

    Çizim QOpenGLWidget ile değil, kendi küçük yerel (native) penceresinde (QOpenGLWindow) yapılır. QOpenGLWidget
    ana pencereye ilk kez eklenince Qt bütün pencereyi OpenGL'li olarak YENİDEN OLUŞTURUYOR: pencere kapanıp
    açılıyor, VLC'nin çizdiği yer kayboluyor (videoya dönünce yalnızca ses), Snap stilleri gidiyordu. Ana pencereyi
    baştan OpenGL'li yapmak da açılışa ~0,7 sn ekliyordu. Video da aynı şekilde kendi yerel penceresinde çiziliyor.
    Dışarıya `_GLView`'in tüm yöntem ve sinyalleri aynen açılır.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.gl = _GLView()
        c = QWidget.createWindowContainer(self.gl, self)
        c.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)   # başlık çubuğu sürüklenebilir kalsın
        c.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        c.setMinimumSize(80, 60)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(c)
        self.container = c
        QApplication.instance().aboutToQuit.connect(self.gl.release_gl)

    def changeEvent(self, e):
        # tema değişince (uygulama stil sayfası) arka plan rengi yeniden çizilsin
        if e.type() in (QEvent.Type.StyleChange, QEvent.Type.PaletteChange):
            self.gl.update()
        super().changeEvent(e)

    def __getattr__(self, name):
        gl = self.__dict__.get("gl")
        if gl is None:
            raise AttributeError(name)
        return getattr(gl, name)


class _GLView(QOpenGLWindow):
    zoom_changed = pyqtSignal(float)
    mouse_moved = pyqtSignal()
    double_clicked = pyqtSignal()
    context_requested = pyqtSignal(QPoint)
    autorotate_changed = pyqtSignal(bool)

    FOV = 38.0
    DEF_YAW, DEF_PITCH = -35.0, 22.0

    def __init__(self):
        super().__init__()
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)
        self.setFormat(fmt)
        # tıklayınca odağı ana pencereden almasın (kısayollar çalışmaya devam etsin)
        self.setFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        self.model = None
        self._pending = None          # GL hazır olmadan gelen model
        self._gpu = []                # [(part, {attr: QOpenGLBuffer}, texture, count)]
        self._grid = None             # (buffer, count)
        self._grid_dirty = False
        self._gl = None
        self._prog = None
        self._gl_error = ""
        self.wireframe = False
        self.show_grid = True
        self.show_dims = False
        self._transparent = False     # saydam PNG için ekran dışı çizim
        self._offscreen = False       # image(): FBO'ya çiziliyor
        self.autorotate = False
        self._rot = QMatrix4x4()      # kullanıcının "çevir" dönüşleri
        self.reset_view(emit=False)
        self._drag = None
        self._press = None
        self._moved = False
        self._spin = QTimer(self)
        self._spin.setInterval(16)
        self._spin.timeout.connect(self._spin_tick)
        self._last_spin = 0.0

    # ------------------------------------------------------------------ dış arayüz
    def set_model(self, model):
        self.model = model
        self._rot = QMatrix4x4()
        self._pending = model
        self.reset_view(emit=True)
        self.update()

    def clear(self):
        self.model = None
        self._pending = None
        if self._gl is not None:
            self.makeCurrent()
            self._free()
            self.doneCurrent()
        self.update()

    def reset_view(self, emit=True):
        self.yaw, self.pitch = self.DEF_YAW, self.DEF_PITCH
        self.pan = QVector3D(0, 0, 0)
        self.dist = self._fit_dist()
        if emit:
            self.zoom_changed.emit(self.zoom_pct())
        self.update()

    def zoom_pct(self):
        return 100.0 * self._fit_dist() / max(1e-9, self.dist)

    def zoom_by(self, factor):
        self.dist = max(self._fit_dist() * 0.02, min(self._fit_dist() * 20, self.dist / factor))
        self.zoom_changed.emit(self.zoom_pct())
        self.update()

    def rotate_model(self, axis="x", deg=90):
        r = QMatrix4x4()
        r.rotate(deg, *( (1, 0, 0) if axis == "x" else (0, 0, 1) if axis == "z" else (0, 1, 0)))
        self._rot = r * self._rot
        self._grid_dirty = True
        self.update()

    def set_wireframe(self, on):
        self.wireframe = bool(on)
        self.update()

    def set_grid(self, on):
        self.show_grid = bool(on)
        self.update()

    def set_dims(self, on):
        self.show_dims = bool(on)
        self.update()

    def set_autorotate(self, on):
        on = bool(on)
        if on == self.autorotate:
            return
        self.autorotate = on
        if on:
            self._last_spin = time.perf_counter()
            self._spin.start()
        else:
            self._spin.stop()
        self.autorotate_changed.emit(on)

    def image(self, transparent=False, scale=2):
        """Görünen karenin resmi (kopyala / kaydet). Her zaman ekran dışında yeniden çizilir (ekrandaki son kare
        henüz güncellenmemiş olabilir).

        transparent=True: arka plan ve ızgara olmadan, `scale` kat çözünürlükte çizilir ve model çevresindeki
        boşluk kırpılır (saydam PNG).
        """
        if self._gl is None or not self.isExposed():
            return self.grabFramebuffer()
        dpr = self.devicePixelRatio()
        k = dpr * (scale if transparent else 1)
        w = max(1, int(self.width() * k))
        h = max(1, int(self.height() * k))
        self.makeCurrent()
        try:
            fmt = QOpenGLFramebufferObjectFormat()
            fmt.setAttachment(QOpenGLFramebufferObject.Attachment.CombinedDepthStencil)
            fmt.setSamples(4)
            fbo = QOpenGLFramebufferObject(w, h, fmt)
            if not fbo.isValid():
                return self.grabFramebuffer()
            fbo.bind()
            self._gl.glViewport(0, 0, w, h)
            self._offscreen = True
            self._transparent = transparent
            try:
                self.paintGL()
            finally:
                self._offscreen = False
                self._transparent = False
                fbo.release()
            img = fbo.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            fbo = None
        finally:
            self.doneCurrent()
        if self.show_dims and self.model is not None:
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.scale(w / max(1, self.width()), h / max(1, self.height()))
            # saydam PNG'de zemin bilinmiyor: her zeminde görünen gri
            self._paint_dims(p, self.width(), self.height(),
                             dark=None if transparent else qcolor("bg").lightness() < 128)
            p.end()
        if not transparent:
            return img.convertToFormat(QImage.Format.Format_RGB32)
        return _crop_alpha(img) if self.model is not None else img

    # ------------------------------------------------------------------ yardımcılar
    def _fit_dist(self):
        r = self.model.radius if self.model is not None else 1.0
        return r / math.sin(math.radians(self.FOV / 2)) * 1.08

    def _rotated_bounds(self):
        m = self.model
        c = m.center
        pts = []
        for x in (m.bmin[0], m.bmax[0]):
            for y in (m.bmin[1], m.bmax[1]):
                for z in (m.bmin[2], m.bmax[2]):
                    v = self._rot.map(QVector3D(float(x - c[0]), float(y - c[1]), float(z - c[2])))
                    pts.append((v.x(), v.y(), v.z()))
        a = np.array(pts)
        return a.min(axis=0), a.max(axis=0)

    def _spin_tick(self):
        now = time.perf_counter()
        dt = min(0.1, now - self._last_spin)
        self._last_spin = now
        self.yaw = (self.yaw + 30.0 * dt) % 360.0
        self.update()

    # ------------------------------------------------------------------ OpenGL
    def initializeGL(self):
        try:
            prof = QOpenGLVersionProfile()
            prof.setVersion(2, 1)
            self._gl = QOpenGLVersionFunctionsFactory.get(prof, self.context())
            if self._gl is None:
                raise RuntimeError("OpenGL 2.1")
            self._gl.initializeOpenGLFunctions()
            p = QOpenGLShaderProgram(self)
            ok = p.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, VERT)
            ok = ok and p.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, FRAG)
            p.bindAttributeLocation("a_pos", 0)
            p.bindAttributeLocation("a_nrm", 1)
            p.bindAttributeLocation("a_col", 2)
            p.bindAttributeLocation("a_uv", 3)
            if not ok or not p.link():
                raise RuntimeError(p.log() or "shader")
            self._prog = p
        except Exception as e:  # sürücü / donanım sorunu
            self._gl = None
            self._gl_error = str(e)
        self.context().aboutToBeDestroyed.connect(self._on_ctx_destroy)
        if self.model is not None:
            self._pending = self.model

    def _on_ctx_destroy(self):
        self.makeCurrent()
        self._free()
        self.doneCurrent()
        self._pending = self.model

    def release_gl(self):
        """Uygulama kapanırken GL kaynaklarını bağlam hâlâ yaşarken bırak; yoksa Python nesneleri sonradan
        yok edilirken sürücü içinde çökme olabiliyor (0xC0000409)."""
        if self._gl is None or self.context() is None:
            return
        try:
            self.context().aboutToBeDestroyed.disconnect(self._on_ctx_destroy)
        except (TypeError, RuntimeError):
            pass
        self.makeCurrent()
        try:
            self._free()
            if self._prog is not None:
                self._prog.removeAllShaders()
                self._prog.deleteLater()
                self._prog = None
        finally:
            self.doneCurrent()
        self._gl = None
        self._pending = self.model

    def _free(self):
        for part, bufs, tex, n in self._gpu:
            for b in bufs.values():
                b.destroy()
            if tex is not None:
                tex.destroy()
        self._gpu = []
        if self._grid is not None:
            self._grid[0].destroy()
            self._grid = None

    @staticmethod
    def _vbo(arr):
        b = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        b.create()
        b.bind()
        data = np.ascontiguousarray(arr, dtype=np.float32).tobytes()
        b.allocate(data, len(data))
        b.release()
        return b

    def _upload(self, model):
        self._free()
        for part in model.parts:
            bufs = {0: self._vbo(part.pos - model.center), 1: self._vbo(part.nrm)}
            if part.col is not None:
                bufs[2] = self._vbo(part.col)
            tex = None
            if part.texture is not None and part.uv is not None:
                bufs[3] = self._vbo(part.uv)
                # OpenGL'de t=0 ilk yüklenen satırdır; iç UV düzeni (OBJ gibi) v=0'ı resmin altı sayar
                tex = QOpenGLTexture(part.texture.flipped(Qt.Orientation.Vertical))
                tex.setMinificationFilter(QOpenGLTexture.Filter.LinearMipMapLinear)
                tex.setMagnificationFilter(QOpenGLTexture.Filter.Linear)
                tex.setWrapMode(QOpenGLTexture.WrapMode.Repeat)
            self._gpu.append((part, bufs, tex, len(part.pos)))
        self._grid = self._make_grid()

    def _make_grid(self):
        if self.model is None:
            return None
        lo, hi = self._rotated_bounds()
        span = max(hi[0] - lo[0], hi[2] - lo[2], 1e-6) * 1.6
        step = 10 ** math.floor(math.log10(span / 10.0))
        for m in (1, 2, 5, 10):
            if span / (step * m) <= 24:
                step *= m
                break
        n = int(math.ceil(span / step / 2))
        cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
        cx, cz = round(cx / step) * step, round(cz / step) * step
        y = lo[1] - 1e-4 * span
        e = n * step
        lines = []
        for i in range(-n, n + 1):
            lines += [(cx + i * step, y, cz - e), (cx + i * step, y, cz + e),
                      (cx - e, y, cz + i * step), (cx + e, y, cz + i * step)]
        if self._grid is not None:
            self._grid[0].destroy()
        return (self._vbo(np.array(lines)), len(lines))

    def resizeGL(self, w, h):
        pass

    def _matrices(self):
        w, h = max(1, self.width()), max(1, self.height())
        proj = QMatrix4x4()
        near = max(self.dist * 0.01, 1e-5)
        proj.perspective(self.FOV, w / h, near, self.dist * 10 + (self.model.radius * 4 if self.model else 10))
        view = QMatrix4x4()
        view.translate(self.pan)
        view.translate(0, 0, -self.dist)
        view.rotate(self.pitch, 1, 0, 0)
        view.rotate(self.yaw, 0, 1, 0)
        return proj, view

    def paintGL(self):
        gl = self._gl
        bg = qcolor("bg")
        if gl is None:
            p = QPainter(self)
            p.fillRect(QRectF(0, 0, self.width(), self.height()), bg)
            p.setPen(qcolor("text2"))
            f = QFont(QGuiApplication.font())
            f.setPixelSize(14)
            p.setFont(f)
            from .i18n import t
            p.drawText(QRectF(0, 0, self.width(), self.height()), Qt.AlignmentFlag.AlignCenter, t("m_no_gl"))
            p.end()
            return
        if not self._offscreen:   # ekran dışı çizimde görüntü alanını image() ayarlar
            dpr = self.devicePixelRatio()
            gl.glViewport(0, 0, max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)))
        if self._transparent:
            gl.glClearColor(0.0, 0.0, 0.0, 0.0)
        else:
            gl.glClearColor(bg.redF(), bg.greenF(), bg.blueF(), 1.0)
        gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if self._pending is not None:
            m, self._pending = self._pending, None
            try:
                self._upload(m)
            except Exception as e:
                self._gl_error = str(e)
                self._free()
        if not self._gpu:
            return
        if self._grid_dirty:
            self._grid_dirty = False
            self._grid = self._make_grid()
        gl.glEnable(GL_DEPTH_TEST)
        gl.glDepthFunc(GL_LEQUAL)
        gl.glEnable(GL_MULTISAMPLE)
        gl.glEnable(GL_BLEND)
        gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        proj, view = self._matrices()
        mv = view * self._rot
        mvp = proj * mv
        p = self._prog
        p.bind()
        p.setUniformValue("u_mvp", mvp)
        p.setUniformValue("u_mv", mv)
        p.setUniformValue("u_tex", 0)
        dark = bg.lightness() < 128   # çizgi rengi arka plana göre

        # ızgara (modelin altında)
        if self.show_grid and self._grid is not None and not self._transparent:
            gbuf, gn = self._grid
            p.setUniformValue("u_mvp", proj * view)   # ızgara dünyaya sabit, model dönüşünden etkilenmez
            p.setUniformValue("u_flat", 1)
            gc = (1.0, 1.0, 1.0, 0.10) if dark else (0.0, 0.0, 0.0, 0.13)
            p.setUniformValue("u_color", *gc)
            gbuf.bind()
            p.enableAttributeArray(0)
            p.setAttributeBuffer(0, GL_FLOAT, 0, 3, 0)
            gbuf.release()
            for a in (1, 2, 3):
                p.disableAttributeArray(a)
            gl.glDrawArrays(GL_LINES, 0, gn)
            p.setUniformValue("u_mvp", mvp)

        gl.glEnable(GL_POLYGON_OFFSET_FILL)
        gl.glPolygonOffset(1.0, 1.0)
        p.setUniformValue("u_flat", 0)
        # önce opak parçalar, sonra yarı saydamlar
        items = sorted(self._gpu, key=lambda g: g[0].color[3] < 0.99)
        for part, bufs, tex, n in items:
            self._bind_part(p, bufs)
            p.setUniformValue("u_color", *[float(c) for c in part.color])
            p.setUniformValue("u_usecol", 1 if 2 in bufs else 0)
            p.setUniformValue("u_usetex", 1 if tex is not None else 0)
            if tex is not None:
                tex.bind(0)
            gl.glDrawArrays(GL_TRIANGLES, 0, n)
            if tex is not None:
                tex.release(0)
        gl.glDisable(GL_POLYGON_OFFSET_FILL)

        if self.wireframe:
            gl.glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
            p.setUniformValue("u_flat", 1)
            wc = (1.0, 1.0, 1.0, 0.22) if dark else (0.0, 0.0, 0.0, 0.25)
            p.setUniformValue("u_color", *wc)
            for part, bufs, tex, n in self._gpu:
                self._bind_part(p, bufs, only_pos=True)
                gl.glDrawArrays(GL_TRIANGLES, 0, n)
            gl.glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        for a in range(4):
            p.disableAttributeArray(a)
        p.release()

        if self.show_dims and not self._offscreen:
            gl.glDisable(GL_DEPTH_TEST)
            qp = QPainter(self)
            qp.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint_dims(qp, self.width(), self.height(), dark)
            qp.end()

    # ------------------------------------------------------------------ ölçü kutusu
    def _paint_dims(self, qp, W, H, dark=True):
        """Modelin sınır kutusu ve genişlik / derinlik / yükseklik etiketleri (QPainter ile)."""
        from .model_io import dims_unit, fmt_num
        from .i18n import t
        m = self.model
        if m is None:
            return
        lo, hi = self._rotated_bounds()
        proj, view = self._matrices()
        pv = proj * view

        def scr(x, y, z):
            v = pv.map(QVector3D(float(x), float(y), float(z)))
            return QPointF((v.x() + 1) / 2 * W, (1 - v.y()) / 2 * H)

        xs, ys, zs = (lo[0], hi[0]), (lo[1], hi[1]), (lo[2], hi[2])
        # Kameraya en yakın alt köşe: ölçüler oradan çıkan üç kenara yazılır
        best = None
        for xi in (0, 1):
            for zi in (0, 1):
                vz = view.map(QVector3D(float(xs[xi]), float(ys[0]), float(zs[zi]))).z()
                if best is None or vz > best[0]:
                    best = (vz, xi, zi)
        _, xi, zi = best
        if dark is None:   # saydam PNG: zemin bilinmiyor, orta gri
            line, strong = QColor(128, 128, 128, 170), QColor(110, 110, 110, 240)
        else:
            line = QColor(255, 255, 255, 120) if dark else QColor(0, 0, 0, 120)
            strong = QColor(255, 255, 255, 230) if dark else QColor(0, 0, 0, 220)
        pen = QPen(line, 1.0)
        pen.setStyle(Qt.PenStyle.DashLine)
        qp.setPen(pen)
        corners = {(a, b, c): scr(xs[a], ys[b], zs[c]) for a in (0, 1) for b in (0, 1) for c in (0, 1)}
        for (a, b, c), pt in corners.items():
            for d in range(3):
                n = [a, b, c]
                if n[d] == 0:
                    n[d] = 1
                    qp.drawLine(pt, corners[tuple(n)])
        k, unit = dims_unit(m, max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]))
        lang = t("lang_code")
        c0 = corners[(xi, 0, zi)]
        center = scr((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2)
        edges = (((1 - xi, 0, zi), hi[0] - lo[0]), ((xi, 0, 1 - zi), hi[2] - lo[2]),
                 ((xi, 1, zi), hi[1] - lo[1]))
        f = QFont(QGuiApplication.font())
        f.setPixelSize(12)
        f.setBold(True)
        qp.setFont(f)
        fm = qp.fontMetrics()
        for key, length in edges:
            c1 = corners[key]
            qp.setPen(QPen(strong, 1.6))
            qp.drawLine(c0, c1)
            mid = (c0 + c1) / 2
            out = mid - center
            ln = max(1e-6, (out.x() ** 2 + out.y() ** 2) ** 0.5)
            mid = mid + out / ln * 16
            text = f"{fmt_num(length * k, lang)} {unit}"
            tw, th = fm.horizontalAdvance(text) + 14, fm.height() + 6
            r = QRectF(mid.x() - tw / 2, mid.y() - th / 2, tw, th)
            qp.setPen(Qt.PenStyle.NoPen)
            qp.setBrush(QColor(20, 20, 22, 210))
            qp.drawRoundedRect(r, th / 2, th / 2)
            qp.setPen(QColor(240, 240, 240))
            qp.drawText(r, Qt.AlignmentFlag.AlignCenter, text)

    @staticmethod
    def _bind_part(p, bufs, only_pos=False):
        sizes = {0: 3, 1: 3, 2: 3, 3: 2}
        for a in range(4):
            b = bufs.get(a) if (not only_pos or a == 0) else None
            if b is None:
                p.disableAttributeArray(a)
                if a == 2:
                    p.setAttributeValue(2, 1.0, 1.0, 1.0)
                continue
            b.bind()
            p.enableAttributeArray(a)
            p.setAttributeBuffer(a, GL_FLOAT, 0, sizes[a], 0)
            b.release()

    # ------------------------------------------------------------------ fare
    def mousePressEvent(self, e):
        self._press = e.position()
        self._last = e.position()
        self._moved = False
        b = e.button()
        shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if b == Qt.MouseButton.LeftButton:
            self._drag = "pan" if shift else "orbit"
        elif b in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self._drag = "pan"
        e.accept()

    def mouseMoveEvent(self, e):
        self.mouse_moved.emit()
        if self._drag is None:
            return
        pos = e.position()
        dx, dy = pos.x() - self._last.x(), pos.y() - self._last.y()
        self._last = pos
        if (pos - self._press).manhattanLength() > 3:
            self._moved = True
        if self._drag == "orbit":
            if self.autorotate:
                self.set_autorotate(False)
            self.yaw = (self.yaw + dx * 0.45) % 360.0
            self.pitch = max(-89.0, min(89.0, self.pitch + dy * 0.45))
        else:
            h = max(1, self.height())
            k = 2 * self.dist * math.tan(math.radians(self.FOV / 2)) / h
            self.pan += QVector3D(dx * k, -dy * k, 0)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton and not self._moved:
            self.context_requested.emit(e.globalPosition().toPoint())
        self._drag = None
        e.accept()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if d:
            self.zoom_by(1.0 + 0.12 * (d / 120.0) if d > 0 else 1.0 / (1.0 + 0.12 * (-d / 120.0)))
        self.mouse_moved.emit()
        e.accept()


def _crop_alpha(img, pad=0.04):
    """Saydam kenarları kırp (modelin etrafında küçük bir pay bırakarak)."""
    w, h = img.width(), img.height()
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    a = np.frombuffer(ptr, dtype=np.uint8).reshape(h, img.bytesPerLine())[:, 3:w * 4:4]
    ys, xs = np.nonzero(a > 4)
    if not len(xs):
        return img
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    p = int(max(x1 - x0, y1 - y0) * pad)
    x0, y0 = max(0, x0 - p), max(0, y0 - p)
    x1, y1 = min(w - 1, x1 + p), min(h - 1, y1 + p)
    return img.copy(int(x0), int(y0), int(x1 - x0 + 1), int(y1 - y0 + 1))
