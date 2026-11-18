"""Ventana principal de Animación."""
import copy
import os
import time
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QElapsedTimer, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QPushButton, QRadioButton, QSpinBox, QSplitter, QVBoxLayout,
                               QWidget, QMenu)

from .. import __version__, exportador
from ..config import Ajustes, Encuadre
from ..motor import colocar, reparto
from ..proyecto import EXT, ImagenProyecto, Proyecto
from ..trabajos import (CANCELADO, EN_COLA, ERROR, LISTO, PROCESANDO, Cola, Trabajo, render_desde)
from ..util import abrir_carpeta, es_imagen, leer_imagen
from .dialogos import DialogoPreferencias
from .hilos import HiloMiniaturas, HiloPreview, HiloSujeto, a_qimage, decodificar
from .panel import PanelAjustes
from .widgets import LineaTiempo, TablaCola, VistaPrevia

PREVIEW_LARGO = 960
PREVIEW_MAX_CUADROS = 3000


# ---------------------------------------------------------------------------
# Fuentes de fotogramas para el reproductor
# ---------------------------------------------------------------------------

class FuentePreview:
    def __init__(self, hilo, fps):
        self.hilo, self.fps = hilo, fps

    @property
    def total(self):
        return self.hilo.total

    @property
    def listos(self):
        return len(self.hilo.frames)

    def get(self, i):
        return decodificar(self.hilo.frames[i])


class FuenteVideo:
    def __init__(self, ruta):
        self.cap = cv2.VideoCapture(str(ruta))
        if not self.cap.isOpened():
            raise ValueError("No se pudo abrir el video.")
        self.total = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self.listos = self.total
        self._ult = -2

    def get(self, i):
        if i != self._ult + 1:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, img = self.cap.read()
        self._ult = i
        if not ok:
            raise ValueError("No se pudo leer el fotograma.")
        return img


class FuenteSecuencia:
    def __init__(self, carpeta, fps):
        self.archivos = sorted(Path(carpeta).glob("frame_*.png"))
        self.total = self.listos = len(self.archivos)
        self.fps = fps

    def get(self, i):
        return leer_imagen(self.archivos[i])


# ---------------------------------------------------------------------------

class Principal(QMainWindow):
    sig_trabajo = Signal(int)
    sig_cola_vacia = Signal()

    def __init__(self, prefs):
        super().__init__()
        self.prefs = prefs
        self.proyecto = Proyecto()
        self.proyecto.ajustes = Ajustes.de_dict(prefs["ultimos_ajustes"])
        self.actual: ImagenProyecto | None = None
        self.sujeto = None
        self._cache_sujetos: dict = {}
        self._clave_sujeto = None
        self._hilo_sujeto = None
        self._hilos_viejos = []
        self.hilo_preview = None
        self._token_preview = 0
        self.fuente = None
        self.pos = 0
        self.reproduciendo = False
        self._reloj = QElapsedTimer()
        self._pos0 = 0
        self.danados = set()
        self._miniaturas = None
        self._ultimo_trabajo = None
        self._bloqueo_ui = False

        self.t_preview = QTimer(self, singleShot=True, interval=650)
        self.t_preview.timeout.connect(self._lanzar_preview)
        self.t_reproduccion = QTimer(self, interval=15)
        self.t_reproduccion.timeout.connect(self._tick)
        self.t_auto = QTimer(self, interval=60000)
        self.t_auto.timeout.connect(self._autoguardar)
        self.t_auto.start()

        self.setWindowTitle("Animación")
        self.resize(1480, 900)
        self.setAcceptDrops(True)
        self._construir_menu()
        self._construir_ui()

        self.cola = Cola(lambda t: self.sig_trabajo.emit(t.id), lambda: self.sig_cola_vacia.emit())
        self.sig_trabajo.connect(self._trabajo_cambio)
        self.sig_cola_vacia.connect(lambda: self.statusBar().showMessage("Cola de trabajos terminada", 6000))

        self._proyecto_a_ui()
        QTimer.singleShot(400, self._buscar_recuperacion)

    # ====================================================================== UI
    def _construir_menu(self):
        mb = self.menuBar()
        m = mb.addMenu("&Archivo")
        for txt, atajo, fn in (("Nuevo proyecto", "Ctrl+N", self.nuevo), ("Abrir proyecto…", "Ctrl+O", self.abrir),
                               ("Guardar", "Ctrl+S", self.guardar), ("Guardar como…", "Ctrl+Shift+S", self.guardar_como),
                               ("Duplicar proyecto…", None, self.duplicar)):
            a = QAction(txt, self)
            if atajo:
                a.setShortcut(QKeySequence(atajo))
            a.triggered.connect(fn)
            m.addAction(a)
        self.m_recientes = m.addMenu("Proyectos recientes")
        m.addSeparator()
        a = QAction("Importar imágenes…", self, shortcut=QKeySequence("Ctrl+I"))
        a.triggered.connect(self.importar_archivos)
        m.addAction(a)
        a = QAction("Importar carpeta…", self)
        a.triggered.connect(self.importar_carpeta)
        m.addAction(a)
        m.addSeparator()
        a = QAction("Salir", self, shortcut=QKeySequence("Ctrl+Q"))
        a.triggered.connect(self.close)
        m.addAction(a)
        m = mb.addMenu("&Herramientas")
        a = QAction("Ajustes de la aplicación…", self)
        a.triggered.connect(self.abrir_preferencias)
        m.addAction(a)
        a = QAction("Abrir carpeta de resultados", self)
        a.triggered.connect(self.abrir_resultados)
        m.addAction(a)
        m = mb.addMenu("A&yuda")
        a = QAction("Acerca de", self)
        a.triggered.connect(lambda: QMessageBox.about(
            self, "Animación", f"Animación {__version__}\nVideos de dibujo progresivo para 11 Records."))
        m.addAction(a)

    def _titulo(self, txt):
        l = QLabel(txt.upper())
        l.setObjectName("titulo")
        return l

    def _construir_ui(self):
        # ------- izquierda
        izq = QWidget()
        izq.setObjectName("panel")
        li = QVBoxLayout(izq)
        li.setContentsMargins(10, 10, 10, 10)
        li.addWidget(self._titulo("Imágenes"))
        fila = QHBoxLayout()
        b = QPushButton("Importar imágenes")
        b.clicked.connect(self.importar_archivos)
        fila.addWidget(b)
        b = QPushButton("Carpeta…")
        b.clicked.connect(self.importar_carpeta)
        fila.addWidget(b)
        li.addLayout(fila)
        self.lista = QListWidget()
        self.lista.setViewMode(QListWidget.IconMode)
        self.lista.setIconSize(QSize(104, 104))
        self.lista.setGridSize(QSize(124, 138))
        self.lista.setResizeMode(QListWidget.Adjust)
        self.lista.setMovement(QListWidget.Static)
        self.lista.setWordWrap(True)
        self.lista.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.lista.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu_lista)
        self.lista.itemSelectionChanged.connect(self._seleccion_cambio)
        li.addWidget(self.lista, 1)
        fila = QHBoxLayout()
        b = QPushButton("Quitar")
        b.clicked.connect(self.quitar_seleccion)
        fila.addWidget(b)
        b = QPushButton("Reemplazar…")
        b.clicked.connect(self.reemplazar)
        fila.addWidget(b)
        li.addLayout(fila)

        li.addWidget(self._titulo("Estilo"))
        self.grupo_estilo = QButtonGroup(self)
        self.r_estilo = {}
        for k, t in (("lapiz", "Lápiz  (trazo → sombreado → color)"), ("pintura", "Pintura  (contorno → pincel)"),
                     ("ambos", "Ambos  (dos videos)")):
            r = QRadioButton(t)
            self.grupo_estilo.addButton(r)
            self.r_estilo[k] = r
            r.toggled.connect(lambda on, k=k: on and self._estilo_cambio(k))
            li.addWidget(r)
        li.addWidget(self._titulo("Proyectos recientes"))
        self.l_recientes = QListWidget()
        self.l_recientes.setMaximumHeight(120)
        self.l_recientes.itemDoubleClicked.connect(lambda it: self.abrir(it.data(Qt.UserRole)))
        li.addWidget(self.l_recientes)

        # ------- centro
        cen = QWidget()
        lc = QVBoxLayout(cen)
        lc.setContentsMargins(6, 8, 6, 6)
        fila = QHBoxLayout()
        self.b_tab_enc = QPushButton("Encuadre")
        self.b_tab_ani = QPushButton("Animación")
        for b in (self.b_tab_enc, self.b_tab_ani):
            b.setCheckable(True)
            fila.addWidget(b)
        self.b_tab_enc.setChecked(True)
        self.b_tab_enc.clicked.connect(lambda: self._modo_vista("encuadre"))
        self.b_tab_ani.clicked.connect(lambda: self._modo_vista("animacion"))
        fila.addStretch(1)
        self.c_ver = QComboBox()
        self.c_ver.addItem("Ver: Lápiz", "lapiz")
        self.c_ver.addItem("Ver: Pintura", "pintura")
        self.c_ver.currentIndexChanged.connect(lambda _i: self._programar_preview())
        fila.addWidget(self.c_ver)
        self.k_auto = QCheckBox("Vista previa automática")
        self.k_auto.setChecked(True)
        fila.addWidget(self.k_auto)
        b = QPushButton("Actualizar vista previa")
        b.clicked.connect(lambda: self._lanzar_preview(reproducir=True))
        fila.addWidget(b)
        lc.addLayout(fila)

        self.vista = VistaPrevia()
        self.vista.editable = True
        self.vista.encuadre_cambiado.connect(self._encuadre_arrastrado)
        lc.addWidget(self.vista, 1)

        fila = QHBoxLayout()
        self.b_stop = QPushButton("⏹")
        self.b_atras = QPushButton("⏮")
        self.b_play = QPushButton("▶")
        self.b_adel = QPushButton("⏭")
        for b, tip in ((self.b_stop, "Detener"), (self.b_atras, "Fotograma anterior"),
                       (self.b_play, "Reproducir / Pausar (Espacio)"), (self.b_adel, "Fotograma siguiente")):
            b.setToolTip(tip)
            b.setFixedWidth(44)
            fila.addWidget(b)
        self.b_stop.clicked.connect(self.detener)
        self.b_atras.clicked.connect(lambda: self._paso(-1))
        self.b_adel.clicked.connect(lambda: self._paso(1))
        self.b_play.clicked.connect(self.alternar_reproduccion)
        self.l_tiempo = QLabel("0.0 / 0.0 s")
        self.l_tiempo.setMinimumWidth(110)
        fila.addWidget(self.l_tiempo)
        fila.addWidget(QLabel("Fotograma"))
        self.s_frame = QSpinBox()
        self.s_frame.setRange(1, 1)
        self.s_frame.valueChanged.connect(lambda v: None if self._bloqueo_ui else self._ir_a(v - 1))
        fila.addWidget(self.s_frame)
        fila.addStretch(1)
        self.l_vista = QLabel("Rueda: ampliar vista · doble clic: restablecer")
        self.l_vista.setObjectName("info")
        fila.addWidget(self.l_vista)
        lc.addLayout(fila)

        # ------- derecha
        der = QWidget()
        der.setObjectName("panel")
        ld = QVBoxLayout(der)
        ld.setContentsMargins(0, 0, 0, 8)
        self.panel = PanelAjustes(self.prefs)
        ld.addWidget(self.panel, 1)
        caja = QWidget()
        lb = QVBoxLayout(caja)
        lb.setContentsMargins(10, 0, 10, 0)
        fila = QHBoxLayout()
        self.e_export = QLineEdit(self.prefs["carpeta_exportacion"])
        self.e_export.setToolTip("Carpeta principal de exportación")
        fila.addWidget(self.e_export, 1)
        b = QPushButton("Carpeta…")
        b.clicked.connect(self.elegir_exportacion)
        fila.addWidget(b)
        lb.addLayout(fila)
        self.e_nombre = QLineEdit()
        self.e_nombre.setPlaceholderText("Nombre del video: {imagen}_{estilo}")
        lb.addWidget(self.e_nombre)
        self.k_todas = QCheckBox("Procesar todas las imágenes (lote)")
        lb.addWidget(self.k_todas)
        self.b_generar = QPushButton("GENERAR ANIMACIÓN")
        self.b_generar.setObjectName("primario")
        self.b_generar.clicked.connect(self.generar)
        lb.addWidget(self.b_generar)
        fila = QHBoxLayout()
        self.b_reproducir = QPushButton("Reproducir video")
        self.b_reproducir.clicked.connect(self.reproducir_resultado)
        fila.addWidget(self.b_reproducir)
        b = QPushButton("Abrir carpeta")
        b.clicked.connect(self.abrir_resultados)
        fila.addWidget(b)
        lb.addLayout(fila)
        ld.addWidget(caja)

        sup = QSplitter(Qt.Horizontal)
        sup.addWidget(izq)
        sup.addWidget(cen)
        sup.addWidget(der)
        sup.setStretchFactor(0, 0)
        sup.setStretchFactor(1, 1)
        sup.setStretchFactor(2, 0)
        sup.setSizes([270, 700, 410])
        sup.setChildrenCollapsible(False)

        # ------- inferior
        inf = QWidget()
        inf.setObjectName("panel")
        lf = QVBoxLayout(inf)
        lf.setContentsMargins(10, 6, 10, 6)
        fila = QHBoxLayout()
        fila.addWidget(self._titulo("Línea de tiempo"))
        fila.addStretch(1)
        self.l_estado_prev = QLabel("")
        self.l_estado_prev.setObjectName("info")
        fila.addWidget(self.l_estado_prev)
        lf.addLayout(fila)
        self.linea = LineaTiempo()
        self.linea.buscar.connect(self._ir_a)
        lf.addWidget(self.linea)
        fila = QHBoxLayout()
        fila.addWidget(self._titulo("Cola de trabajos"))
        fila.addStretch(1)
        b = QPushButton("Cancelar todo")
        b.setObjectName("peligro")
        b.clicked.connect(self.cancelar_todo)
        fila.addWidget(b)
        b = QPushButton("Limpiar terminados")
        b.clicked.connect(self.limpiar_cola)
        fila.addWidget(b)
        lf.addLayout(fila)
        self.tabla = TablaCola()
        self.tabla.cancelar.connect(lambda i: self.cola.cancelar(i))
        self.tabla.ver.connect(self.revisar_trabajo)
        self.tabla.abrir.connect(self.abrir_carpeta_trabajo)
        lf.addWidget(self.tabla, 1)

        vert = QSplitter(Qt.Vertical)
        vert.addWidget(sup)
        vert.addWidget(inf)
        vert.setStretchFactor(0, 1)
        vert.setSizes([650, 250])
        vert.setChildrenCollapsible(False)
        self.setCentralWidget(vert)
        self.statusBar().showMessage("Listo")

        self.panel.cambiado.connect(self._ajustes_cambiaron)
        self.panel.quitar_fondo_cambiado.connect(lambda _x: self._cargar_sujeto())
        self.panel.encuadre_modo.connect(self._enc_modo)
        self.panel.encuadre_zoom.connect(self._enc_zoom)
        self.panel.encuadre_centrar.connect(self._enc_centrar)
        self.panel.encuadre_todas.connect(self._enc_todas)
        self.panel.perfil_guardar.connect(self._guardar_perfil)
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self.alternar_reproduccion)
        QShortcut(QKeySequence(Qt.Key_Delete), self, activated=self.quitar_seleccion)
        self._modo_vista("encuadre")

    # ============================================================= proyecto/UI
    def _proyecto_a_ui(self):
        self._bloqueo_ui = True
        a = self.proyecto.ajustes.validar()
        self.panel.escribir(a)
        self.r_estilo.get(a.estilo, self.r_estilo["lapiz"]).setChecked(True)
        self.c_ver.setVisible(a.estilo == "ambos")
        self.lista.clear()
        self.danados.clear()
        for im in self.proyecto.imagenes:
            self._agregar_item(im)
        self._lanzar_miniaturas([i.ruta for i in self.proyecto.imagenes])
        self.e_export.setText(self.proyecto.carpeta_exportacion or self.prefs["carpeta_exportacion"])
        self._bloqueo_ui = False
        self._refrescar_recientes()
        self._actualizar_titulo()
        faltan = self.proyecto.faltantes()
        if faltan:
            QMessageBox.warning(self, "Archivos originales no encontrados",
                                "No se encontraron estos archivos:\n\n" + "\n".join(faltan[:12]) +
                                ("\n…" if len(faltan) > 12 else ""))
        if self.proyecto.imagenes:
            self.lista.setCurrentRow(0)
        else:
            self.actual, self.sujeto = None, None
            self._seleccion_cambio()
        self._ajustes_cambiaron(solo_ui=True)

    def _ui_a_proyecto(self):
        a = self.panel.leer(self.proyecto.ajustes)
        for k, r in self.r_estilo.items():
            if r.isChecked():
                a.estilo = k
        a.validar()
        self.proyecto.carpeta_exportacion = self.e_export.text().strip()
        return a

    def _actualizar_titulo(self):
        self.setWindowTitle(f"Animación — {self.proyecto.nombre}{' *' if self.proyecto.modificado else ''}")

    def _marcar(self):
        self.proyecto.marcar()
        self._actualizar_titulo()

    def _refrescar_recientes(self):
        self.l_recientes.clear()
        self.m_recientes.clear()
        for r in self.prefs.recientes_existentes():
            it = QListWidgetItem(Path(r).stem)
            it.setData(Qt.UserRole, r)
            it.setToolTip(r)
            self.l_recientes.addItem(it)
            a = QAction(r, self)
            a.triggered.connect(lambda _=False, r=r: self.abrir(r))
            self.m_recientes.addAction(a)
        self.m_recientes.setEnabled(self.m_recientes.actions() != [])

    # ----------------------------------------------------------- importación
    def _agregar_item(self, im: ImagenProyecto):
        it = QListWidgetItem(im.nombre)
        it.setData(Qt.UserRole, im.ruta)
        it.setToolTip(im.ruta)
        pm = QPixmap(104, 104)
        pm.fill(QColor("#22262f"))
        it.setIcon(QIcon(pm))
        if not os.path.exists(im.ruta):
            it.setForeground(QColor("#ef5a5a"))
            it.setToolTip("Archivo original no encontrado: " + im.ruta)
        self.lista.addItem(it)

    def importar_archivos(self):
        rutas, _ = QFileDialog.getOpenFileNames(
            self, "Importar imágenes", self.prefs.d.get("ultima_carpeta_imagenes", str(Path.home())),
            "Imágenes (*.jpg *.jpeg *.png *.webp *.bmp)")
        if rutas:
            self.prefs["ultima_carpeta_imagenes"] = str(Path(rutas[0]).parent)
            self.importar_rutas(rutas)

    def importar_carpeta(self):
        d = QFileDialog.getExistingDirectory(self, "Importar carpeta de imágenes",
                                             self.prefs.d.get("ultima_carpeta_imagenes", str(Path.home())))
        if d:
            self.prefs["ultima_carpeta_imagenes"] = d
            self.importar_rutas([d])

    def importar_rutas(self, rutas):
        existentes = {i.ruta for i in self.proyecto.imagenes}
        nuevas, ignoradas = [], []
        for r in rutas:
            p = Path(r)
            if p.is_dir():
                cand = sorted(x for x in p.iterdir() if x.is_file())
            else:
                cand = [p]
            for c in cand:
                if not es_imagen(c):
                    if not p.is_dir():
                        ignoradas.append(c.name)
                    continue
                s = str(c)
                if s not in existentes:
                    existentes.add(s)
                    nuevas.append(s)
        for s in nuevas:
            im = ImagenProyecto(s, encuadre=copy.deepcopy(self.proyecto.ajustes.encuadre))
            self.proyecto.imagenes.append(im)
            self._agregar_item(im)
        if nuevas:
            self._marcar()
            self._lanzar_miniaturas(nuevas)
            if self.actual is None:
                self.lista.setCurrentRow(0)
            self.statusBar().showMessage(f"{len(nuevas)} imagen(es) importada(s)", 5000)
        if ignoradas:
            QMessageBox.warning(self, "Formato no compatible",
                                "Estos archivos no se importaron (formatos admitidos: JPG, PNG, WEBP, BMP):\n\n"
                                + "\n".join(ignoradas[:15]))

    def _lanzar_miniaturas(self, rutas):
        if not rutas:
            return
        if self._miniaturas and self._miniaturas.isRunning():
            self._miniaturas.parar()
            self._hilos_viejos.append(self._miniaturas)
        self._miniaturas = HiloMiniaturas(rutas)
        self._miniaturas.miniatura.connect(self._miniatura)
        self._miniaturas.start()

    def _miniatura(self, ruta, qimg):
        for i in range(self.lista.count()):
            it = self.lista.item(i)
            if it.data(Qt.UserRole) == ruta:
                if qimg is None:
                    self.danados.add(ruta)
                    it.setForeground(QColor("#ef5a5a"))
                    it.setToolTip("Archivo dañado o formato incompatible")
                else:
                    it.setIcon(QIcon(QPixmap.fromImage(qimg)))

    def quitar_seleccion(self):
        if not self.lista.selectedItems():
            return
        rutas = {it.data(Qt.UserRole) for it in self.lista.selectedItems()}
        self.proyecto.imagenes = [i for i in self.proyecto.imagenes if i.ruta not in rutas]
        for it in self.lista.selectedItems():
            self.lista.takeItem(self.lista.row(it))
        self._marcar()
        if not self.proyecto.imagenes:
            self.actual, self.sujeto = None, None
            self._seleccion_cambio()

    def reemplazar(self):
        it = self.lista.currentItem()
        if it is None:
            return
        ruta, _ = QFileDialog.getOpenFileName(self, "Reemplazar imagen", str(Path(it.data(Qt.UserRole)).parent),
                                              "Imágenes (*.jpg *.jpeg *.png *.webp *.bmp)")
        if not ruta:
            return
        for im in self.proyecto.imagenes:
            if im.ruta == it.data(Qt.UserRole):
                im.ruta = ruta
        it.setData(Qt.UserRole, ruta)
        it.setText(Path(ruta).stem)
        it.setToolTip(ruta)
        it.setForeground(QColor("#e8eaee"))
        self.danados.discard(ruta)
        self._marcar()
        self._lanzar_miniaturas([ruta])
        self._cache_sujetos.clear()
        self._seleccion_cambio()

    def _menu_lista(self, pos):
        m = QMenu(self)
        m.addAction("Quitar del proyecto", self.quitar_seleccion)
        m.addAction("Reemplazar…", self.reemplazar)
        m.addAction("Mostrar en carpeta", lambda: abrir_carpeta(Path(self.lista.currentItem().data(Qt.UserRole)).parent)
                    if self.lista.currentItem() else None)
        m.exec(self.lista.mapToGlobal(pos))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        rutas = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if rutas:
            self.importar_rutas(rutas)

    # ------------------------------------------------------------ selección
    def _imagen_de_item(self, it):
        r = it.data(Qt.UserRole)
        return next((i for i in self.proyecto.imagenes if i.ruta == r), None)

    def _seleccion_cambio(self):
        items = self.lista.selectedItems()
        self.detener()
        if not items:
            if not self.proyecto.imagenes:
                self.actual = None
                self.vista.mostrar(None, "Importa una imagen para empezar")
                self.panel.mostrar_info("")
            return
        self.actual = self._imagen_de_item(items[-1])
        if self.actual is None:
            return
        self.panel.escribir_encuadre(self.actual.encuadre or self.proyecto.ajustes.encuadre)
        self._cargar_sujeto()

    # ------------------------------------------------------------- sujeto
    def _cargar_sujeto(self):
        im = self.actual
        if im is None:
            return
        a = self._ui_a_proyecto()
        clave = (im.ruta, a.quitar_fondo)
        self._clave_sujeto = clave
        self.panel.mostrar_info(self._texto_info(a))
        if clave in self._cache_sujetos:
            self.sujeto, avisos = self._cache_sujetos[clave]
            self._sujeto_ok(avisos)
            return
        if im.ruta in self.danados or not os.path.exists(im.ruta):
            self.sujeto = None
            self.vista.mostrar(None, "No se puede abrir esta imagen (dañada o no encontrada)")
            return
        self.sujeto = None
        self.vista.mostrar(None, "Quitando el fondo…" if a.quitar_fondo else "Cargando imagen…")
        if self._hilo_sujeto and self._hilo_sujeto.isRunning():
            self._hilos_viejos.append(self._hilo_sujeto)
        h = HiloSujeto(im.ruta, a.quitar_fondo, self.prefs["carpeta_temporal"], self.prefs["modelo_fondo"])
        self._hilo_sujeto = h
        h.etapa.connect(lambda t, h=h: self.statusBar().showMessage(t + "…") if h is self._hilo_sujeto else None)
        h.listo.connect(lambda s, av, h=h, c=clave: self._sujeto_listo(h, c, s, av))
        h.error.connect(lambda msg, h=h: self._sujeto_error(h, msg))
        h.start()

    def _sujeto_listo(self, h, clave, sujeto, avisos):
        if h is not self._hilo_sujeto:
            return
        if len(self._cache_sujetos) > 5:
            self._cache_sujetos.pop(next(iter(self._cache_sujetos)))
        self._cache_sujetos[clave] = (sujeto, avisos)
        self.sujeto = sujeto
        self._sujeto_ok(avisos)

    def _sujeto_ok(self, avisos):
        a = self.proyecto.ajustes
        self.panel.mostrar_info(self._texto_info(a), "\n".join(avisos) if avisos else None)
        self.statusBar().showMessage("Imagen lista", 3000)
        self._refrescar_vista_estatica()
        self._programar_preview()

    def _sujeto_error(self, h, msg):
        if h is not self._hilo_sujeto:
            return
        self.sujeto = None
        self.vista.mostrar(None, f"No se pudo abrir la imagen:\n{msg}")

    # ----------------------------------------------------------- ajustes
    def _texto_info(self, a: Ajustes):
        w, h = a.tamano()
        n = int(round(a.duracion * a.fps))
        mb = {"mp4": w * h * a.fps * a.duracion * 0.12, "mov": w * h * a.fps * a.duracion * 1.1}.get(
            "mov" if a.transparente and a.formato_transparente == "mov" else "mp4")
        if a.transparente and a.formato_transparente == "png":
            mb = w * h * a.fps * a.duracion * 1.6
        txt = f"{w}×{h} · {n} fotogramas · ≈ {mb / 1e6:,.0f} MB"
        if a.calidad == "4K":
            txt += "\n4K: la generación es más lenta y usa más memoria."
        return txt

    def _ajustes_cambiaron(self, solo_ui=False):
        if self._bloqueo_ui:
            return
        a = self._ui_a_proyecto()
        self.prefs["ultimos_ajustes"] = a.a_dict()
        self.c_ver.setVisible(a.estilo == "ambos")
        self.panel.mostrar_info(self._texto_info(a))
        self._formato_vista(a)
        estilo = self._estilo_vista(a)
        cfg = render_desde(a, estilo, Encuadre(), *self._tam_preview(a))
        pf = self._fps_preview(a)
        cfg.fps = pf
        self.linea.fijar(reparto(cfg)[6], reparto(cfg)[0], pf)
        if not solo_ui:
            self._marcar()
            if self.sujeto is not None:
                self._refrescar_vista_estatica()
                self._programar_preview()

    def _estilo_cambio(self, k):
        if self._bloqueo_ui:
            return
        self._ajustes_cambiaron()

    def _estilo_vista(self, a):
        return self.c_ver.currentData() if a.estilo == "ambos" else a.estilo

    def _tam_preview(self, a):
        W, H = a.tamano()
        k = PREVIEW_LARGO / max(W, H)
        return max(2, int(round(W * k / 2)) * 2), max(2, int(round(H * k / 2)) * 2)

    def _fps_preview(self, a):
        return int(min(a.fps, max(6, PREVIEW_MAX_CUADROS // max(1, int(a.duracion)))))

    def _formato_vista(self, a):
        W, H = a.tamano()
        bgr = a.fondo_bgr()
        hexa = None if bgr is None else "#%02x%02x%02x" % (bgr[2], bgr[1], bgr[0])
        self.vista.fijar_formato(W, H, hexa, a.transparente)

    # ------------------------------------------------------------- encuadre
    def _enc_actual(self):
        if self.actual is None:
            return None
        if self.actual.encuadre is None:
            self.actual.encuadre = copy.deepcopy(self.proyecto.ajustes.encuadre)
        return self.actual.encuadre

    def _enc_modo(self, m):
        e = self._enc_actual()
        if e:
            e.modo, e.zoom, e.dx, e.dy = m, 1.0, 0.0, 0.0
            self._encuadre_cambio()

    def _enc_zoom(self, z):
        e = self._enc_actual()
        if e:
            e.zoom = z
            self._encuadre_cambio()

    def _enc_centrar(self):
        e = self._enc_actual()
        if e:
            e.zoom, e.dx, e.dy = 1.0, 0.0, 0.0
            self.panel.escribir_encuadre(e)
            self._encuadre_cambio()

    def _enc_todas(self):
        e = self._enc_actual()
        if e:
            for im in self.proyecto.imagenes:
                im.encuadre = copy.deepcopy(e)
            self.proyecto.ajustes.encuadre = copy.deepcopy(e)
            self._marcar()
            self.statusBar().showMessage("Encuadre aplicado a todas las imágenes", 4000)

    def _encuadre_arrastrado(self, z, dx, dy):
        e = self._enc_actual()
        if e:
            e.zoom, e.dx, e.dy = z, dx, dy
            self.panel.escribir_encuadre(e)
            self._encuadre_cambio()

    def _encuadre_cambio(self):
        self._marcar()
        self._refrescar_vista_estatica()
        self._programar_preview()

    def _refrescar_vista_estatica(self):
        """Composición del resultado final con el encuadre actual (pestaña Encuadre)."""
        if self.sujeto is None or self.actual is None:
            return
        a = self.proyecto.ajustes
        e = self._enc_actual()
        W, H = self._tam_preview(a)
        color, alpha = colocar(self.sujeto.recortado(), W, H, e)
        bgr = a.fondo_bgr()
        if bgr is None:
            img = np.dstack([color, (alpha * 255).astype(np.uint8)])
        else:
            img = (color * alpha[..., None] + np.array(bgr, np.float32) * (1 - alpha[..., None])).astype(np.uint8)
        self._formato_vista(a)
        self.vista.fijar_encuadre(e.zoom, e.dx, e.dy)
        if self.b_tab_enc.isChecked():
            self.vista.mostrar(a_qimage(img))
        self._estatica = img

    # ------------------------------------------------------- vista previa
    def _modo_vista(self, modo):
        enc = modo == "encuadre"
        self.b_tab_enc.setChecked(enc)
        self.b_tab_ani.setChecked(not enc)
        self.vista.editable = enc
        self.vista.restablecer_vista()
        if enc:
            self.detener()
            if getattr(self, "_estatica", None) is not None and self.sujeto is not None:
                self.vista.mostrar(a_qimage(self._estatica))
        elif self.fuente is not None:
            self._ir_a(self.pos)
        else:
            self.vista.mostrar(None, "Pulsa «Actualizar vista previa» para ver la animación")
            if self.sujeto is not None:
                self._lanzar_preview()

    def _programar_preview(self):
        if self.k_auto.isChecked() and self.sujeto is not None:
            self.t_preview.start()
            self.l_estado_prev.setText("Vista previa desactualizada…")

    def _lanzar_preview(self, reproducir=False):
        self.t_preview.stop()
        if self.sujeto is None or self.actual is None:
            return
        a = self._ui_a_proyecto()
        self._hilos_viejos = [h for h in self._hilos_viejos if h.isRunning()]
        if self.hilo_preview and self.hilo_preview.isRunning():
            self.hilo_preview.parar()
            self._hilos_viejos.append(self.hilo_preview)
        W, H = self._tam_preview(a)
        cfg = render_desde(a, self._estilo_vista(a), self._enc_actual(), W, H)
        cfg.fps = self._fps_preview(a)
        h = HiloPreview(self.sujeto, cfg)
        self.hilo_preview = h
        self._token_preview += 1
        tok = self._token_preview
        h.progreso.connect(lambda n, t, tok=tok: self._preview_progreso(tok, n, t))
        h.terminado.connect(lambda ok, msg, tok=tok: self._preview_fin(tok, ok, msg))
        self.fuente = FuentePreview(h, cfg.fps)
        tot, _, _, _, _, _, etapas = reparto(cfg)
        self.linea.fijar(etapas, tot, cfg.fps)
        self.pos = 0
        self._formato_vista(a)
        self._quiere_reproducir = reproducir
        self.l_estado_prev.setText("Generando vista previa… 0 %")
        self.s_frame.setRange(1, max(1, tot))
        h.start()
        if reproducir:
            self._modo_vista("animacion")

    def _preview_progreso(self, tok, n, total):
        if tok != self._token_preview:
            return
        self.l_estado_prev.setText(f"Generando vista previa… {100 * n // max(1, total)} %")
        self.linea.fijar_pos(self.pos, n)
        if n and self.b_tab_ani.isChecked() and not self.reproduciendo and self.pos < n and self.vista.imagen is None:
            self._ir_a(self.pos)
        if getattr(self, "_quiere_reproducir", False) and n > 2 and not self.reproduciendo:
            self._quiere_reproducir = False
            self.reproducir()

    def _preview_fin(self, tok, ok, msg):
        if tok != self._token_preview:
            return
        if ok:
            self.l_estado_prev.setText("Vista previa lista")
            self.linea.fijar_pos(self.pos, self.fuente.total)
            if self.b_tab_ani.isChecked() and not self.reproduciendo:
                self._ir_a(min(self.pos, self.fuente.listos - 1))
        else:
            self.l_estado_prev.setText("")
            self.vista.mostrar(None, f"No se pudo generar la vista previa:\n{msg}")

    # --------------------------------------------------------- reproductor
    def _count(self):
        return self.fuente.total if self.fuente else 0

    def _ir_a(self, i):
        if self.fuente is None:
            return
        i = int(max(0, min(i, self.fuente.total - 1)))
        if i >= self.fuente.listos:
            i = self.fuente.listos - 1
        if i < 0:
            return
        self.pos = i
        try:
            self.vista.mostrar(a_qimage(self.fuente.get(i)))
        except Exception:
            return
        self.linea.fijar_pos(i, self.fuente.listos)
        self._bloqueo_ui = True
        self.s_frame.setRange(1, max(1, self.fuente.total))
        self.s_frame.setValue(i + 1)
        self._bloqueo_ui = False
        self.l_tiempo.setText(f"{i / self.fuente.fps:0.1f} / {self.fuente.total / self.fuente.fps:0.1f} s")

    def _paso(self, d):
        self.pausar()
        self._modo_vista("animacion") if not self.b_tab_ani.isChecked() else None
        self._ir_a(self.pos + d)

    def reproducir(self):
        if self.fuente is None:
            return
        if not self.b_tab_ani.isChecked():
            self._modo_vista("animacion")
        if self.pos >= self.fuente.total - 1:
            self.pos = 0
        self.reproduciendo = True
        self.b_play.setText("⏸")
        self._pos0 = self.pos
        self._reloj.restart()
        self.t_reproduccion.start()

    def pausar(self):
        self.reproduciendo = False
        self.t_reproduccion.stop()
        self.b_play.setText("▶")

    def alternar_reproduccion(self):
        if self.reproduciendo:
            self.pausar()
        else:
            if self.fuente is None and self.sujeto is not None:
                self._lanzar_preview(reproducir=True)
            else:
                self.reproducir()

    def detener(self):
        self.pausar()
        if self.fuente is not None and self.b_tab_ani.isChecked():
            self._ir_a(0)
        else:
            self.pos = 0

    def _tick(self):
        if self.fuente is None:
            return
        objetivo = self._pos0 + int(self._reloj.elapsed() / 1000.0 * self.fuente.fps)
        if objetivo >= self.fuente.total - 1:
            self._ir_a(self.fuente.total - 1)
            self.pausar()
            return
        if objetivo >= self.fuente.listos:           # todavía generándose
            self._ir_a(self.fuente.listos - 1)
            self._pos0, _ = self.fuente.listos - 1, self._reloj.restart()
            return
        if objetivo != self.pos:
            self._ir_a(objetivo)

    # ------------------------------------------------------------ generación
    def elegir_exportacion(self):
        d = QFileDialog.getExistingDirectory(self, "Carpeta principal de exportación", self.e_export.text())
        if d:
            self.e_export.setText(d)
            self.prefs["carpeta_exportacion"] = d
            self.prefs.guardar()
            self._marcar()

    def generar(self):
        if not self.proyecto.imagenes:
            QMessageBox.information(self, "Sin imágenes", "Importa al menos una imagen para generar la animación.")
            return
        a = self._ui_a_proyecto()
        self.prefs["ultimos_ajustes"] = a.a_dict()
        if self.k_todas.isChecked():
            imgs = list(self.proyecto.imagenes)
        else:
            sel = [self._imagen_de_item(i) for i in self.lista.selectedItems()]
            imgs = [i for i in sel if i] or ([self.actual] if self.actual else [])
        carpeta = self.e_export.text().strip()
        if not carpeta:
            self.elegir_exportacion()
            carpeta = self.e_export.text().strip()
            if not carpeta:
                return
        self.prefs["carpeta_exportacion"] = carpeta
        self.prefs.guardar()
        estilos = ["lapiz", "pintura"] if a.estilo == "ambos" else [a.estilo]
        plantilla = self.e_nombre.text().strip() or "{imagen}_{estilo}"
        n = omitidas = 0
        for im in imgs:
            if im.ruta in self.danados or not os.path.exists(im.ruta):
                omitidas += 1
                continue
            for est in estilos:
                try:
                    nombre = plantilla.format(imagen=im.nombre, estilo=est, proyecto=self.proyecto.nombre,
                                              formato=a.aspecto.replace(":", "x"))
                except (KeyError, IndexError, ValueError):
                    nombre = f"{im.nombre}_{est}"
                if (len(imgs) * len(estilos) > 1) and "{" not in plantilla and plantilla:
                    nombre = f"{plantilla}_{im.nombre}_{est}"
                t = Trabajo(imagen=im.ruta, estilo=est, ajustes=copy.deepcopy(a),
                            encuadre=copy.deepcopy(im.encuadre or a.encuadre),
                            quitar_fondo=a.quitar_fondo, proyecto=self.proyecto.nombre, nombre=nombre,
                            carpeta_exportacion=carpeta, carpeta_temp=self.prefs["carpeta_temporal"],
                            gpu=self.prefs["gpu"], politica=self.prefs["sobrescribir"],
                            modelo_fondo=self.prefs["modelo_fondo"])
                self.tabla.actualizar(t)
                self.cola.agregar(t)
                n += 1
        msg = f"{n} trabajo(s) añadido(s) a la cola"
        if omitidas:
            msg += f" · {omitidas} imagen(es) omitida(s) (dañadas o no encontradas)"
        self.statusBar().showMessage(msg, 7000)

    def _trabajo_cambio(self, tid):
        t = next((x for x in self.cola.trabajos if x.id == tid), None)
        if t is None:
            return
        self.tabla.actualizar(t)
        if t.estado == LISTO:
            self._ultimo_trabajo = t
            aviso = f" · {t.avisos[0]}" if t.avisos else ""
            self.statusBar().showMessage(f"Terminado: {Path(t.salida).name}{aviso}", 8000)
        elif t.estado == ERROR:
            self.statusBar().showMessage(f"Falló «{t.titulo}»: {t.error}", 10000)

    def cancelar_todo(self):
        self.cola.cancelar_todo()

    def limpiar_cola(self):
        self.cola.limpiar_terminados()
        self.tabla.reiniciar()
        for t in self.cola.trabajos:
            self.tabla.actualizar(t)

    def _trabajo(self, tid):
        return next((x for x in self.cola.trabajos if x.id == tid), None)

    def abrir_carpeta_trabajo(self, tid):
        t = self._trabajo(tid)
        if t:
            abrir_carpeta(t.salida and Path(t.salida).parent or t.carpeta_destino())

    def abrir_resultados(self):
        t = self._ultimo_trabajo
        abrir_carpeta(Path(t.salida).parent if t and t.salida else self.e_export.text() or Path.home())

    def reproducir_resultado(self):
        if self._ultimo_trabajo is None:
            QMessageBox.information(self, "Sin resultados", "Aún no hay videos terminados en esta sesión.")
            return
        self.revisar_trabajo(self._ultimo_trabajo.id)

    def revisar_trabajo(self, tid):
        t = self._trabajo(tid)
        if t is None or t.estado != LISTO or not os.path.exists(t.salida):
            self.statusBar().showMessage("Ese trabajo todavía no tiene un resultado disponible", 5000)
            return
        try:
            if t.formato == "mp4":
                src = FuenteVideo(t.salida)
            elif t.formato == "png":
                src = FuenteSecuencia(t.salida, t.ajustes.fps)
            else:
                QMessageBox.information(
                    self, "MOV con transparencia",
                    "El MOV ProRes 4444 se abre en tu editor de video (DaVinci Resolve, Premiere, After Effects…).\n"
                    "La pestaña «Animación» ya muestra la transparencia con el tablero de cuadros.")
                abrir_carpeta(Path(t.salida).parent)
                return
        except Exception as e:
            QMessageBox.warning(self, "Revisar resultado", str(e))
            return
        self.pausar()
        self.fuente = src
        self.linea.fijar([("Video", 0, src.total)], src.total, src.fps)
        a = t.ajustes
        self.vista.fijar_formato(*a.tamano(), None if a.transparente else "#000000", a.transparente)
        self._modo_vista("animacion")
        self._ir_a(0)
        self.reproducir()

    # --------------------------------------------------------------- perfiles
    def _guardar_perfil(self):
        from PySide6.QtWidgets import QInputDialog
        nombre, ok = QInputDialog.getText(self, "Guardar perfil", "Nombre del perfil:")
        if ok and nombre.strip():
            a = self._ui_a_proyecto()
            d = a.a_dict()
            d.pop("encuadre", None)
            d.pop("estilo", None)
            self.prefs["perfiles"][nombre.strip()] = d
            self.prefs.guardar()
            self.panel.recargar_perfiles()

    # -------------------------------------------------------------- proyectos
    def _confirmar_perder(self):
        if self.cola.activo():
            r = QMessageBox.question(self, "Hay trabajos en curso",
                                     "Se están generando videos. ¿Cancelarlos y continuar?")
            if r != QMessageBox.Yes:
                return False
            self.cola.cancelar_todo()
        if self.proyecto.modificado:
            r = QMessageBox.question(self, "Cambios sin guardar", "¿Guardar los cambios del proyecto?",
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                return False
            if r == QMessageBox.Save:
                return self.guardar()
        return True

    def nuevo(self):
        if not self._confirmar_perder():
            return
        self.proyecto = Proyecto()
        self.proyecto.ajustes = Ajustes.de_dict(self.prefs["ultimos_ajustes"])
        self._cache_sujetos.clear()
        self.fuente = None
        self.tabla.reiniciar()
        self._proyecto_a_ui()

    def guardar(self):
        self._ui_a_proyecto()
        if not self.proyecto.ruta:
            return self.guardar_como()
        try:
            self.proyecto.guardar()
        except Exception as e:
            QMessageBox.critical(self, "No se pudo guardar", str(e))
            return False
        self.prefs.agregar_reciente(self.proyecto.ruta)
        self._refrescar_recientes()
        self._actualizar_titulo()
        self.statusBar().showMessage("Proyecto guardado", 4000)
        return True

    def guardar_como(self):
        self._ui_a_proyecto()
        base = Path(self.prefs["carpeta_proyectos"])
        sug = base / self.proyecto.nombre / f"{self.proyecto.nombre}{EXT}"
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar proyecto", str(sug), f"Proyecto Animación (*{EXT})")
        if not ruta:
            return False
        if not ruta.endswith(EXT):
            ruta += EXT
        self.proyecto.nombre = Path(ruta).stem
        self.proyecto.ruta = ruta
        self.prefs["carpeta_proyectos"] = str(Path(ruta).parent.parent)
        return self.guardar()

    def duplicar(self):
        self._ui_a_proyecto()
        sug = Path(self.proyecto.ruta).parent / f"{self.proyecto.nombre} (copia){EXT}" if self.proyecto.ruta \
            else Path(self.prefs["carpeta_proyectos"]) / f"{self.proyecto.nombre} (copia){EXT}"
        ruta, _ = QFileDialog.getSaveFileName(self, "Duplicar proyecto como", str(sug), f"Proyecto Animación (*{EXT})")
        if not ruta:
            return
        if not ruta.endswith(EXT):
            ruta += EXT
        try:
            copia = self.proyecto.duplicar(ruta, Path(ruta).stem)
        except Exception as e:
            QMessageBox.critical(self, "No se pudo duplicar", str(e))
            return
        self.prefs.agregar_reciente(ruta)
        self.proyecto = copia
        self._proyecto_a_ui()
        self.statusBar().showMessage("Proyecto duplicado", 4000)

    def abrir(self, ruta=None):
        if not ruta or ruta is False:
            ruta, _ = QFileDialog.getOpenFileName(self, "Abrir proyecto", self.prefs["carpeta_proyectos"],
                                                  f"Proyecto Animación (*{EXT})")
            if not ruta:
                return
        if not self._confirmar_perder():
            return
        try:
            if Proyecto.recuperacion_pendiente(ruta):
                r = QMessageBox.question(self, "Recuperación",
                                         "Se encontró una copia de seguridad más reciente de este proyecto "
                                         "(cierre inesperado). ¿Recuperarla?")
                if r == QMessageBox.Yes:
                    p = Proyecto.abrir(ruta + ".recuperacion")
                    p.ruta = ruta
                    p.modificado = True
                    self._cargar(p)
                    return
            self._cargar(Proyecto.abrir(ruta))
        except Exception as e:
            QMessageBox.critical(self, "No se pudo abrir el proyecto", str(e))

    def _cargar(self, p):
        self.proyecto = p
        self._cache_sujetos.clear()
        self.fuente = None
        self.tabla.reiniciar()
        if p.ruta:
            self.prefs.agregar_reciente(p.ruta)
        self._proyecto_a_ui()

    def _autoguardar(self):
        if self.proyecto.modificado:
            try:
                self._ui_a_proyecto()
                self.proyecto.autoguardar(self.prefs.ruta.parent)
                self.statusBar().showMessage("Copia de seguridad automática guardada", 2500)
            except Exception:
                pass

    def _buscar_recuperacion(self):
        sin = self.prefs.ruta.parent / "sin_titulo.animproj.recuperacion"
        if sin.exists():
            r = QMessageBox.question(self, "Recuperar trabajo",
                                     "Se encontró un proyecto sin guardar de una sesión anterior. ¿Recuperarlo?")
            try:
                if r == QMessageBox.Yes:
                    p = Proyecto.abrir(sin)
                    p.ruta = ""
                    p.modificado = True
                    self._cargar(p)
            except Exception as e:
                QMessageBox.warning(self, "Recuperación", str(e))
            sin.unlink(missing_ok=True)
        for rc in self.prefs.recientes_existentes()[:5]:
            if Proyecto.recuperacion_pendiente(rc) and rc != self.proyecto.ruta:
                r = QMessageBox.question(
                    self, "Recuperar trabajo",
                    f"Hay una copia de seguridad más reciente de «{Path(rc).stem}» (cierre inesperado).\n"
                    "¿Abrir el proyecto y recuperarla?")
                if r == QMessageBox.Yes:
                    self.abrir(rc)
                break

    def abrir_preferencias(self):
        if DialogoPreferencias(self.prefs, self).exec():
            self.e_export.setText(self.prefs["carpeta_exportacion"])
            self._cache_sujetos.clear()
            self._cargar_sujeto()

    # ----------------------------------------------------------------- cierre
    def closeEvent(self, e):
        if not self._confirmar_perder():
            e.ignore()
            return
        self._ui_a_proyecto()
        self.prefs["ultimos_ajustes"] = self.proyecto.ajustes.a_dict()
        self.prefs["carpeta_exportacion"] = self.e_export.text().strip() or self.prefs["carpeta_exportacion"]
        self.prefs.guardar()
        self.cola.cancelar_todo()
        for h in [self.hilo_preview, self._hilo_sujeto, self._miniaturas] + self._hilos_viejos:
            try:
                if h is not None and h.isRunning():
                    if hasattr(h, "parar"):
                        h.parar()
                    h.wait(4000)
            except Exception:
                pass
        # sin proyecto pendiente: elimina copias de seguridad
        if self.proyecto.ruta:
            Path(self.proyecto.ruta_recuperacion()).unlink(missing_ok=True)
        (self.prefs.ruta.parent / "sin_titulo.animproj.recuperacion").unlink(missing_ok=True)
        e.accept()
