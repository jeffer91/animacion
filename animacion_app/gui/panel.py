"""Panel derecho: configuración del efecto, fondo, duración, resolución y formato."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSlider,
                               QVBoxLayout, QWidget, QButtonGroup)

from ..config import (ASPECTOS, DURACION_MAX, DURACION_MIN, FPS_VALIDOS, LADO_CORTO, PERFILES, Ajustes)

FONDOS = (("Papel", "papel"), ("Blanco", "blanco"), ("Negro", "negro"),
          ("Color personalizado…", "color"), ("Transparente", "transparente"))


class PanelAjustes(QScrollArea):
    cambiado = Signal()
    encuadre_modo = Signal(str)
    encuadre_zoom = Signal(float)
    encuadre_centrar = Signal()
    encuadre_todas = Signal()
    perfil_guardar = Signal()
    quitar_fondo_cambiado = Signal(bool)

    def __init__(self, prefs, parent=None):
        super().__init__(parent)
        self.prefs = prefs
        self._bloq = False
        self.color_fondo = "#F5F0E8"
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        cont = QWidget()
        cont.setObjectName("panel")
        self.setWidget(cont)
        lay = QVBoxLayout(cont)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # ---- perfiles
        g = QGroupBox("Perfil")
        f = QHBoxLayout(g)
        self.c_perfil = QComboBox()
        self.c_perfil.setMinimumWidth(110)
        f.addWidget(self.c_perfil, 1)
        b = QPushButton("Guardar")
        b.setToolTip("Guarda la configuración actual como perfil")
        b.clicked.connect(self.perfil_guardar)
        f.addWidget(b)
        b2 = QPushButton("Restaurar")
        b2.setToolTip("Valores predeterminados")
        b2.clicked.connect(self.restaurar)
        f.addWidget(b2)
        lay.addWidget(g)
        self.c_perfil.activated.connect(self._aplicar_perfil)

        # ---- fondo
        g = QGroupBox("Fondo")
        v = QVBoxLayout(g)
        self.k_quitar = QCheckBox("Eliminar fondo automáticamente")
        self.k_quitar.setToolTip("Aísla al sujeto con un modelo local (sin internet una vez instalado)")
        v.addWidget(self.k_quitar)
        fila = QHBoxLayout()
        self.c_fondo = QComboBox()
        for t, k in FONDOS:
            self.c_fondo.addItem(t, k)
        fila.addWidget(self.c_fondo, 1)
        self.b_color = QPushButton("Color")
        self.b_color.clicked.connect(self._elegir_color)
        fila.addWidget(self.b_color)
        v.addLayout(fila)
        self.c_transp = QComboBox()
        self.c_transp.addItem("Transparente: MOV ProRes 4444", "mov")
        self.c_transp.addItem("Transparente: secuencia PNG", "png")
        v.addWidget(self.c_transp)
        lay.addWidget(g)

        # ---- efecto
        g = QGroupBox("Efecto y tiempo")
        fl = QFormLayout(g)
        self.s_dur = QDoubleSpinBox()
        self.s_dur.setRange(DURACION_MIN, DURACION_MAX)
        self.s_dur.setSingleStep(1)
        self.s_dur.setSuffix(" s")
        self.s_dur.setDecimals(1)
        fl.addRow("Duración", self.s_dur)
        self.s_fin = QDoubleSpinBox()
        self.s_fin.setRange(0, 150)
        self.s_fin.setSingleStep(0.5)
        self.s_fin.setSuffix(" s")
        self.s_fin.setDecimals(1)
        fl.addRow("Resultado final", self.s_fin)
        self.c_vel = QComboBox()
        self.c_vel.addItem("Dinámica", "dinamica")
        self.c_vel.addItem("Constante", "constante")
        fl.addRow("Velocidad", self.c_vel)
        fila = QHBoxLayout()
        self.sl_det = QSlider(Qt.Horizontal)
        self.sl_det.setRange(1, 10)
        self.l_det = QLabel("5")
        self.l_det.setFixedWidth(18)
        fila.addWidget(self.sl_det)
        fila.addWidget(self.l_det)
        fl.addRow("Detalle", fila)
        lay.addWidget(g)

        # ---- salida
        g = QGroupBox("Salida")
        v = QVBoxLayout(g)
        fila = QHBoxLayout()
        self.grupo_asp = QButtonGroup(self)
        self.b_asp = {}
        for a, nombre, tip in (("1:1", "1:1", "Cuadrado · redes sociales"), ("16:9", "16:9", "Horizontal · YouTube"),
                               ("9:16", "9:16", "Vertical · TikTok, Reels y Shorts")):
            b = QPushButton(nombre)
            b.setToolTip(tip)
            b.setCheckable(True)
            b.setProperty("aspecto", a)
            self.grupo_asp.addButton(b)
            self.b_asp[a] = b
            fila.addWidget(b)
        self.grupo_asp.setExclusive(True)
        v.addLayout(fila)
        fl = QFormLayout()
        self.c_cal = QComboBox()
        for k in LADO_CORTO:
            self.c_cal.addItem(k)
        fl.addRow("Calidad", self.c_cal)
        self.c_fps = QComboBox()
        for k in FPS_VALIDOS:
            self.c_fps.addItem(f"{k} FPS", k)
        fl.addRow("Fotogramas", self.c_fps)
        v.addLayout(fl)
        self.l_info = QLabel("")
        self.l_info.setObjectName("info")
        self.l_info.setWordWrap(True)
        v.addWidget(self.l_info)
        self.l_aviso = QLabel("")
        self.l_aviso.setObjectName("aviso")
        self.l_aviso.setWordWrap(True)
        self.l_aviso.hide()
        v.addWidget(self.l_aviso)
        lay.addWidget(g)

        # ---- encuadre
        g = QGroupBox("Encuadre de la imagen")
        v = QVBoxLayout(g)
        fila = QHBoxLayout()
        self.b_encajar = QPushButton("Encajar")
        self.b_rellenar = QPushButton("Rellenar")
        for b in (self.b_encajar, self.b_rellenar):
            b.setCheckable(True)
            fila.addWidget(b)
        v.addLayout(fila)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Zoom"))
        self.sl_zoom = QSlider(Qt.Horizontal)
        self.sl_zoom.setRange(20, 400)
        self.sl_zoom.setValue(100)
        fila.addWidget(self.sl_zoom)
        self.l_zoom = QLabel("100%")
        self.l_zoom.setFixedWidth(44)
        fila.addWidget(self.l_zoom)
        v.addLayout(fila)
        fila = QHBoxLayout()
        b = QPushButton("Centrar")
        b.clicked.connect(self.encuadre_centrar)
        fila.addWidget(b)
        b = QPushButton("Aplicar a todas")
        b.clicked.connect(self.encuadre_todas)
        fila.addWidget(b)
        v.addLayout(fila)
        nota = QLabel("En la pestaña Encuadre: arrastra para mover y usa la rueda para ampliar.")
        nota.setObjectName("info")
        nota.setWordWrap(True)
        v.addWidget(nota)
        lay.addWidget(g)
        lay.addStretch(1)

        # ---- señales
        for w in (self.k_quitar,):
            w.toggled.connect(self._cambio)
        self.k_quitar.toggled.connect(lambda x: None if self._bloq else self.quitar_fondo_cambiado.emit(x))
        for w in (self.c_fondo, self.c_transp, self.c_vel, self.c_cal, self.c_fps):
            w.currentIndexChanged.connect(self._cambio)
        self.c_fondo.activated.connect(self._fondo_elegido)
        self.s_dur.valueChanged.connect(self._cambio)
        self.s_fin.valueChanged.connect(self._cambio)
        self.sl_det.valueChanged.connect(lambda v: (self.l_det.setText(str(v)), self._cambio()))
        self.grupo_asp.buttonClicked.connect(lambda _b: self._cambio())
        self.b_encajar.clicked.connect(lambda: self._modo("encajar"))
        self.b_rellenar.clicked.connect(lambda: self._modo("rellenar"))
        self.sl_zoom.valueChanged.connect(self._zoom)
        self.recargar_perfiles()

    # ---------------------------------------------------------------- helpers
    def _cambio(self, *_):
        if self._bloq:
            return
        self._actualizar_visibilidad()
        self.cambiado.emit()

    def _actualizar_visibilidad(self):
        k = self.c_fondo.currentData()
        self.b_color.setVisible(k == "color")
        self.c_transp.setVisible(k == "transparente")

    def _fondo_elegido(self, _i):
        if self.c_fondo.currentData() == "color":
            self._elegir_color()

    def _elegir_color(self):
        c = QColorDialog.getColor(QColor(self.color_fondo), self, "Color de fondo")
        if c.isValid():
            self.color_fondo = c.name().upper()
            self._pintar_boton()
            self._cambio()

    def _pintar_boton(self):
        self.b_color.setStyleSheet(f"background:{self.color_fondo}; color:#000;")

    def _modo(self, m):
        self.b_encajar.setChecked(m == "encajar")
        self.b_rellenar.setChecked(m == "rellenar")
        self.encuadre_modo.emit(m)

    def _zoom(self, v):
        self.l_zoom.setText(f"{v}%")
        if not self._bloq:
            self.encuadre_zoom.emit(v / 100.0)

    def recargar_perfiles(self):
        self.c_perfil.blockSignals(True)
        self.c_perfil.clear()
        self.c_perfil.addItem("— Perfil —", None)
        for n in PERFILES:
            self.c_perfil.addItem(n, ("pre", n))
        for n in self.prefs["perfiles"]:
            self.c_perfil.addItem(f"★ {n}", ("usr", n))
        self.c_perfil.blockSignals(False)

    def _aplicar_perfil(self, i):
        d = self.c_perfil.itemData(i)
        if not d:
            return
        datos = PERFILES[d[1]] if d[0] == "pre" else self.prefs["perfiles"][d[1]]
        a = self.leer()
        for k, v in datos.items():
            if k != "encuadre" and hasattr(a, k):
                setattr(a, k, v)
        self.escribir(a)
        self.cambiado.emit()

    def restaurar(self):
        a = Ajustes()
        a.estilo = self.leer().estilo
        self.escribir(a)
        self.cambiado.emit()

    # ---------------------------------------------------------------- datos
    def leer(self, base: Ajustes | None = None) -> Ajustes:
        a = base or Ajustes()
        a.quitar_fondo = self.k_quitar.isChecked()
        a.fondo = self.c_fondo.currentData()
        a.color_fondo = self.color_fondo
        a.formato_transparente = self.c_transp.currentData()
        a.duracion = self.s_dur.value()
        a.final = self.s_fin.value()
        a.velocidad = self.c_vel.currentData()
        a.detalle = self.sl_det.value()
        a.calidad = self.c_cal.currentText()
        a.fps = self.c_fps.currentData()
        for k, b in self.b_asp.items():
            if b.isChecked():
                a.aspecto = k
        return a

    def escribir(self, a: Ajustes):
        self._bloq = True
        try:
            self.k_quitar.setChecked(a.quitar_fondo)
            self.c_fondo.setCurrentIndex(max(0, self.c_fondo.findData(a.fondo)))
            self.color_fondo = a.color_fondo
            self._pintar_boton()
            self.c_transp.setCurrentIndex(max(0, self.c_transp.findData(a.formato_transparente)))
            self.s_dur.setValue(a.duracion)
            self.s_fin.setValue(a.final)
            self.c_vel.setCurrentIndex(max(0, self.c_vel.findData(a.velocidad)))
            self.sl_det.setValue(a.detalle)
            self.l_det.setText(str(a.detalle))
            self.c_cal.setCurrentText(a.calidad)
            self.c_fps.setCurrentIndex(max(0, self.c_fps.findData(a.fps)))
            for k, b in self.b_asp.items():
                b.setChecked(k == a.aspecto)
            self._actualizar_visibilidad()
        finally:
            self._bloq = False

    def escribir_encuadre(self, enc):
        self._bloq = True
        try:
            self.b_encajar.setChecked(enc.modo == "encajar")
            self.b_rellenar.setChecked(enc.modo == "rellenar")
            self.sl_zoom.setValue(int(round(enc.zoom * 100)))
            self.l_zoom.setText(f"{int(round(enc.zoom * 100))}%")
        finally:
            self._bloq = False

    def mostrar_info(self, texto, aviso=None):
        self.l_info.setText(texto)
        self.l_aviso.setVisible(bool(aviso))
        self.l_aviso.setText(aviso or "")
