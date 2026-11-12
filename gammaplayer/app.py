"""Uygulama girişi: tek pencere modu, tema, ana pencere."""
import ctypes
import os
import subprocess
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication

from .config import prefs, asset, BASE_DIR

SERVER_NAME = "gamma-player-single-instance-v2"


def _send_to_running(paths) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(300):
        return False
    try:
        ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
    except Exception:
        pass
    data = ("\n".join(os.path.abspath(p) for p in paths) or "\x00").encode("utf-8")
    sock.write(data)
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def _bring_to_front(win):
    if win.isMinimized():
        win.showNormal()
    win.show()
    win.raise_()
    win.activateWindow()
    try:
        hwnd = int(win.winId())
        ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def restart(win=None):
    args = [sys.executable]
    if not getattr(sys, "frozen", False):
        main_py = os.path.join(BASE_DIR, "main.py")
        args += [main_py] if os.path.exists(main_py) else ["-m", "gammaplayer"]
    if win is not None and win.current is not None:
        args.append(win.current.path)
    if win is not None:
        win.close()
    QApplication.instance().quit()
    subprocess.Popen(args, close_fds=True)


def main():
    # Kaynaktan çalışırken (python.exe) görev çubuğunda Python simgesi çıkmasın diye ayrı kimlik veriyoruz.
    # Kurulu exe'de VERMİYORUZ: açık kimliği olan pencerenin simgesini görev çubuğu o kimliği taşıyan bir
    # kısayoldan arıyor, bulamayınca düz pencere simgesi gösteriyordu. Kimlik verilmezse Windows gamma.exe'nin
    # kendi simgesini kullanır ve Başlat / masaüstü kısayollarıyla aynı düğmede toplar (sabitleme de düzgün).
    if not getattr(sys, "frozen", False):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("gamma.media.player")
        except Exception:
            pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)
    app = QApplication(sys.argv)
    app.setApplicationName("gamma")
    app.setOrganizationName("gamma")
    app.setQuitOnLastWindowClosed(True)
    f = QFont("Segoe UI Variable Text")
    f.setPointSizeF(9.5)
    app.setFont(f)
    ico = asset("logo.ico") if os.path.exists(asset("logo.ico")) else asset("logo.png")
    app.setWindowIcon(QIcon(ico))

    # Qt'nin hazır pencereleri (renk seçici, dosya iletişim kutusu düğmeleri) için çeviri
    try:
        from PyQt6.QtCore import QTranslator, QLibraryInfo
        if prefs.get("language", "tr") == "tr":
            tr = QTranslator(app)
            if tr.load("qtbase_tr", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
                app.installTranslator(tr)
    except Exception:
        pass

    paths = [a for a in sys.argv[1:] if not a.startswith("--")]

    server = None
    if prefs.get("single_instance", True) and "--new-window" not in sys.argv:
        if _send_to_running(paths):
            return 0
        QLocalServer.removeServer(SERVER_NAME)
        server = QLocalServer()
        server.listen(SERVER_NAME)

    from .theme import theme
    theme.apply()
    from .window import MainWindow
    win = MainWindow(paths)
    win.show()

    if server is not None:
        def on_conn():
            s = server.nextPendingConnection()
            if s is None:
                return

            def read():
                raw = bytes(s.readAll()).decode("utf-8", errors="ignore")
                got = [p for p in raw.split("\n") if p and p != "\x00"]
                _bring_to_front(win)
                if got:
                    win.open_paths(got)
            s.readyRead.connect(read)
            s.disconnected.connect(s.deleteLater)
        server.newConnection.connect(on_conn)

    return app.exec()
