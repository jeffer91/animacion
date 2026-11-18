"""Hilos de trabajo: la ventana nunca se bloquea con tareas pesadas."""
import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from .. import fondo as modulo_fondo
from ..motor import Animador
from ..trabajos import cargar_sujeto
from ..util import leer_imagen


def codificar(img):
    """Comprime un fotograma para guardarlo en memoria: (jpg, png_alfa|None)."""
    if img.shape[2] == 4:
        _, c = cv2.imencode(".jpg", img[:, :, :3], [cv2.IMWRITE_JPEG_QUALITY, 88])
        _, a = cv2.imencode(".png", img[:, :, 3], [cv2.IMWRITE_PNG_COMPRESSION, 1])
        return c.tobytes(), a.tobytes()
    _, c = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return c.tobytes(), None


def decodificar(par):
    bgr = cv2.imdecode(np.frombuffer(par[0], np.uint8), cv2.IMREAD_COLOR)
    if par[1] is None:
        return bgr
    a = cv2.imdecode(np.frombuffer(par[1], np.uint8), cv2.IMREAD_GRAYSCALE)
    return np.dstack([bgr, a])


def a_qimage(img):
    """numpy BGR/BGRA -> QImage (copia independiente)."""
    h, w = img.shape[:2]
    if img.shape[2] == 4:
        rgba = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA))
        return QImage(rgba.data, w, h, w * 4, QImage.Format_RGBA8888).copy()
    bgr = np.ascontiguousarray(img)
    return QImage(bgr.data, w, h, w * 3, QImage.Format_BGR888).copy()


class HiloPreview(QThread):
    """Genera la vista previa (resolución reducida) cuadro a cuadro."""
    progreso = Signal(int, int)        # listos, total
    terminado = Signal(bool, str)

    def __init__(self, sujeto, cfg, parent=None):
        super().__init__(parent)
        self.sujeto, self.cfg = sujeto, cfg
        self.frames = []
        self.etapas = []
        self.total = 0
        self.transparente = cfg.fondo is None
        self._parar = False

    def parar(self):
        self._parar = True

    def run(self):
        try:
            an = Animador(self.sujeto, self.cfg)
            self.etapas, self.total = an.etapas, an.total
            an.preparar()
            import time
            ult = 0
            for c in an.cuadros():
                if self._parar:
                    return
                self.frames.append(codificar(c.img))
                if time.time() - ult > 0.12:
                    ult = time.time()
                    self.progreso.emit(len(self.frames), self.total)
            self.progreso.emit(len(self.frames), self.total)
            self.terminado.emit(True, "")
        except Exception as e:
            self.terminado.emit(False, str(e) or e.__class__.__name__)


class HiloSujeto(QThread):
    """Carga la imagen y, si procede, elimina el fondo (con caché)."""
    listo = Signal(object, list)
    error = Signal(str)
    etapa = Signal(str)

    def __init__(self, ruta, quitar, carpeta_temp, modelo, parent=None):
        super().__init__(parent)
        self.ruta, self.quitar, self.temp, self.modelo = ruta, quitar, carpeta_temp, modelo

    def run(self):
        try:
            avisos = []
            s = cargar_sujeto(self.ruta, self.quitar, self.temp, self.modelo, avisos,
                              lambda t: self.etapa.emit(t))
            self.listo.emit(s, avisos)
        except Exception as e:
            self.error.emit(str(e) or e.__class__.__name__)


class HiloMiniaturas(QThread):
    miniatura = Signal(str, object)    # ruta, QImage|None

    def __init__(self, rutas, lado=104, parent=None):
        super().__init__(parent)
        self.rutas, self.lado = list(rutas), lado
        self._parar = False

    def parar(self):
        self._parar = True

    def run(self):
        for r in self.rutas:
            if self._parar:
                return
            try:
                img = leer_imagen(r)
                h, w = img.shape[:2]
                esc = self.lado / max(h, w)
                img = cv2.resize(img, (max(1, int(w * esc)), max(1, int(h * esc))), interpolation=cv2.INTER_AREA)
                self.miniatura.emit(r, a_qimage(img))
            except Exception:
                self.miniatura.emit(r, None)


class HiloModelo(QThread):
    terminado = Signal(bool, str)

    def __init__(self, nombre, parent=None):
        super().__init__(parent)
        self.nombre = nombre

    def run(self):
        try:
            modulo_fondo.descargar_modelo(self.nombre)
            self.terminado.emit(True, self.nombre)
        except Exception as e:
            self.terminado.emit(False, str(e))
