"""Widgets propios: vista previa con encuadre, línea de tiempo y tabla de cola."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QProgressBar, QPushButton, QTableWidget,
                               QTableWidgetItem, QWidget, QAbstractItemView)

from . import tema

COLORES_ETAPA = {"Inicio": "#4a5160", "Dibujo": "#4f8cff", "Sombreado": "#9a6bff",
                 "Pintura": "#f08a4b", "Color": "#46c28a", "Imagen final": "#2fa5a5"}


def tablero(ancho, alto, celda=14):
    pm = QPixmap(ancho, alto)
    p = QPainter(pm)
    for y in range(0, alto, celda):
        for x in range(0, ancho, celda):
            c = "#3a3f4a" if ((x // celda) + (y // celda)) % 2 else "#2a2e37"
            p.fillRect(x, y, celda, celda, QColor(c))
    p.end()
    return pm


class VistaPrevia(QWidget):
    """Muestra un fotograma con la proporción de salida; permite mover y ampliar el encuadre."""
    encuadre_cambiado = Signal(float, float, float)     # zoom, dx, dy
    rueda_vista = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 220)
        self.setMouseTracking(True)
        self.imagen = None                  # QImage
        self.proporcion = 16 / 9
        self.fondo = QColor("#f5f0e8")      # None => tablero (transparente)
        self.transparente = False
        self.editable = False               # modo encuadre
        self.zoom, self.dx, self.dy = 1.0, 0.0, 0.0
        self.zoom_vista = 1.0
        self.pan = QPointF(0, 0)
        self._arrastre = None
        self.mensaje = "Importa una imagen para empezar"
        self._tablero = None

    # --- estado
    def fijar_formato(self, w, h, fondo_hex=None, transparente=False):
        self.proporcion = w / h
        self.transparente = transparente
        self.fondo = QColor(fondo_hex) if fondo_hex else QColor("#f5f0e8")
        self.update()

    def mostrar(self, qimg, mensaje=None):
        self.imagen = qimg
        if mensaje is not None:
            self.mensaje = mensaje
        self.update()

    def fijar_encuadre(self, zoom, dx, dy):
        self.zoom, self.dx, self.dy = zoom, dx, dy

    def restablecer_vista(self):
        self.zoom_vista, self.pan = 1.0, QPointF(0, 0)
        self.update()

    # --- geometría
    def _marco(self):
        m = 14
        aw, ah = self.width() - 2 * m, self.height() - 2 * m
        if aw / ah > self.proporcion:
            h = ah
            w = h * self.proporcion
        else:
            w = aw
            h = w / self.proporcion
        w, h = w * self.zoom_vista, h * self.zoom_vista
        cx, cy = self.width() / 2 + self.pan.x(), self.height() / 2 + self.pan.y()
        return QRectF(cx - w / 2, cy - h / 2, w, h)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(tema.BG))
        r = self._marco()
        p.setClipRect(self.rect())
        if self.imagen is None:
            p.setPen(QColor(tema.TEXTO2))
            p.setFont(QFont(self.font().family(), 12))
            p.drawText(self.rect(), Qt.AlignCenter, self.mensaje)
            return
        if self.transparente:
            if self._tablero is None:
                self._tablero = tablero(1600, 1200)
            p.save()
            p.setClipRect(r)
            p.drawPixmap(int(r.left()), int(r.top()), self._tablero)
            p.restore()
        else:
            p.fillRect(r, self.fondo)
        p.drawImage(r, self.imagen)
        p.setPen(QPen(QColor("#3b4252"), 1))
        p.drawRect(r)
        if self.editable:
            p.setPen(QPen(QColor(255, 255, 255, 40), 1, Qt.DashLine))
            p.drawLine(QPointF(r.center().x(), r.top()), QPointF(r.center().x(), r.bottom()))
            p.drawLine(QPointF(r.left(), r.center().y()), QPointF(r.right(), r.center().y()))

    # --- ratón
    def mousePressEvent(self, e):
        if e.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._arrastre = e.position()

    def mouseMoveEvent(self, e):
        if self._arrastre is None:
            return
        d = e.position() - self._arrastre
        self._arrastre = e.position()
        if self.editable and self.imagen is not None:
            r = self._marco()
            self.dx += d.x() / r.width()
            self.dy += d.y() / r.height()
            self.encuadre_cambiado.emit(self.zoom, self.dx, self.dy)
        else:
            self.pan += d
            self.update()

    def mouseReleaseEvent(self, _):
        self._arrastre = None

    def wheelEvent(self, e):
        paso = 1.1 ** (e.angleDelta().y() / 120.0)
        if self.editable:
            self.zoom = max(0.2, min(6.0, self.zoom * paso))
            self.encuadre_cambiado.emit(self.zoom, self.dx, self.dy)
        else:
            self.zoom_vista = max(0.5, min(6.0, self.zoom_vista * paso))
            if self.zoom_vista <= 1.001:
                self.pan = QPointF(0, 0)
            self.rueda_vista.emit(self.zoom_vista)
            self.update()

    def mouseDoubleClickEvent(self, _):
        self.restablecer_vista()


class LineaTiempo(QWidget):
    """Etapas (Dibujo > Sombreado/Pintura > Color > Imagen final) con cabezal arrastrable."""
    buscar = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(58)
        self.setCursor(Qt.PointingHandCursor)
        self.etapas, self.total, self.pos, self.listos, self.fps = [], 1, 0, 0, 30

    def fijar(self, etapas, total, fps):
        self.etapas, self.total, self.fps = etapas, max(1, total), fps
        self.update()

    def fijar_pos(self, pos, listos=None):
        self.pos = pos
        if listos is not None:
            self.listos = listos
        self.update()

    def _x(self, f):
        return 8 + (self.width() - 16) * f / self.total

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        y, h = 18, 20
        p.setFont(QFont(self.font().family(), 9))
        for nombre, a, b in self.etapas:
            if b <= a:
                continue
            c = QColor(COLORES_ETAPA.get(nombre, "#555"))
            r = QRectF(self._x(a), y, self._x(b) - self._x(a) - 2, h)
            c2 = QColor(c)
            c2.setAlpha(70)
            p.setBrush(QBrush(c2))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(r, 4, 4)
            # parte ya generada
            if self.listos > a:
                rr = QRectF(r.left(), y, min(r.width(), self._x(min(self.listos, b)) - r.left()), h)
                p.setBrush(QBrush(c))
                p.drawRoundedRect(rr, 4, 4)
            p.setPen(QColor(tema.TEXTO2))
            if r.width() > 50:
                p.drawText(QRectF(r.left(), y + h + 2, r.width(), 16), Qt.AlignLeft | Qt.AlignVCenter, nombre)
        x = self._x(self.pos)
        p.setPen(QPen(QColor("white"), 2))
        p.drawLine(QPointF(x, 10), QPointF(x, y + h + 4))
        p.setBrush(QColor("white"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(x, 10), 5, 5)

    def _desde_x(self, x):
        f = (x - 8) / max(1, self.width() - 16) * self.total
        self.buscar.emit(int(max(0, min(self.total - 1, f))))

    def mousePressEvent(self, e):
        self._desde_x(e.position().x())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._desde_x(e.position().x())


class TablaCola(QTableWidget):
    """Cola de trabajos con progreso por trabajo."""
    cancelar = Signal(int)
    ver = Signal(int)
    abrir = Signal(int)

    COLS = ("Trabajo", "Estado", "Etapa", "Progreso", "")

    def __init__(self, parent=None):
        super().__init__(0, len(self.COLS), parent)
        self.setHorizontalHeaderLabels(self.COLS)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setShowGrid(False)
        h = self.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for i, w in ((1, 90), (2, 130), (3, 170), (4, 150)):
            h.setSectionResizeMode(i, QHeaderView.Fixed)
            self.setColumnWidth(i, w)
        self._filas = {}
        self.cellDoubleClicked.connect(lambda r, _c: self.ver.emit(self._id_de_fila(r)))

    def _id_de_fila(self, r):
        return int(self.item(r, 0).data(Qt.UserRole))

    def actualizar(self, t):
        r = self._filas.get(t.id)
        if r is None:
            r = self.rowCount()
            self.insertRow(r)
            self._filas[t.id] = r
            it = QTableWidgetItem(t.titulo)
            it.setData(Qt.UserRole, t.id)
            self.setItem(r, 0, it)
            for c in (1, 2):
                self.setItem(r, c, QTableWidgetItem(""))
            barra = QProgressBar()
            barra.setRange(0, 100)
            self.setCellWidget(r, 3, barra)
            caja = QWidget()
            lay = QHBoxLayout(caja)
            lay.setContentsMargins(4, 0, 4, 0)
            lay.setSpacing(4)
            for txt, sig, tip in (("✕", self.cancelar, "Cancelar"), ("▶", self.ver, "Revisar"),
                                  ("📁", self.abrir, "Abrir carpeta")):
                b = QPushButton(txt)
                b.setToolTip(tip)
                b.setFixedSize(30, 24)
                b.clicked.connect(lambda _=False, s=sig, i=t.id: s.emit(i))
                lay.addWidget(b)
            self.setCellWidget(r, 4, caja)
            self.setRowHeight(r, 30)
        self.item(r, 1).setText(t.estado)
        col = {"Listo": tema.OK, "Error": tema.PELIGRO, "Cancelado": tema.AVISO}.get(t.estado, tema.TEXTO)
        self.item(r, 1).setForeground(QColor(col))
        self.item(r, 2).setText(t.etapa if t.estado != "Error" else t.error[:60])
        self.item(r, 2).setToolTip(t.error or t.etapa)
        self.cellWidget(r, 3).setValue(int(t.progreso * 100))

    def reiniciar(self):
        self.setRowCount(0)
        self._filas.clear()
