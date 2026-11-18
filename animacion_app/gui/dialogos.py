"""Diálogo de preferencias (carpeta temporal, GPU, modelo de recorte, sobrescritura)."""
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from .. import exportador, fondo
from .hilos import HiloModelo


class DialogoPreferencias(QDialog):
    def __init__(self, prefs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajustes de la aplicación")
        self.setMinimumWidth(560)
        self.prefs = prefs
        self._hilo = None
        lay = QVBoxLayout(self)
        fl = QFormLayout()
        fila = QHBoxLayout()
        self.e_temp = QLineEdit(prefs["carpeta_temporal"])
        b = QPushButton("Elegir…")
        b.clicked.connect(self._elegir_temp)
        fila.addWidget(self.e_temp)
        fila.addWidget(b)
        fl.addRow("Carpeta temporal", fila)

        self.c_gpu = QComboBox()
        self.c_gpu.addItem("Automática (usar GPU si es compatible)", "auto")
        self.c_gpu.addItem("Solo CPU", "cpu")
        self.c_gpu.setCurrentIndex(max(0, self.c_gpu.findData(prefs["gpu"])))
        fl.addRow("Aceleración", self.c_gpu)

        self.c_sob = QComboBox()
        self.c_sob.addItem("Conservar versiones anteriores (nombre_v2…)", "versionar")
        self.c_sob.addItem("Sobrescribir si existe", "sobrescribir")
        self.c_sob.setCurrentIndex(max(0, self.c_sob.findData(prefs["sobrescribir"])))
        fl.addRow("Si el archivo existe", self.c_sob)

        self.c_mod = QComboBox()
        for m in fondo.MODELOS:
            self.c_mod.addItem(m, m)
        self.c_mod.setCurrentIndex(max(0, self.c_mod.findData(prefs["modelo_fondo"])))
        fl.addRow("Modelo de recorte", self.c_mod)
        lay.addLayout(fl)

        self.l_estado = QLabel("")
        self.l_estado.setObjectName("info")
        self.l_estado.setWordWrap(True)
        lay.addWidget(self.l_estado)
        fila = QHBoxLayout()
        self.b_desc = QPushButton("Descargar modelo seleccionado")
        self.b_desc.clicked.connect(self._descargar)
        fila.addWidget(self.b_desc)
        b = QPushButton("Limpiar archivos temporales")
        b.clicked.connect(self._limpiar)
        fila.addWidget(b)
        lay.addLayout(fila)
        self._refrescar()

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._aceptar)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _refrescar(self):
        e = fondo.estado()
        try:
            hw = exportador.info_hardware()
            ff = exportador.ruta_ffmpeg()
        except Exception as ex:
            hw, ff = str(ex), "no encontrado"
        rem = "instalado" if e["rembg"] else "NO instalado (pip install rembg onnxruntime)"
        mods = ", ".join(e["modelos"]) or "ninguno descargado"
        self.l_estado.setText(f"Recorte automático (rembg): {rem}\nModelos locales: {mods}\n"
                              f"FFmpeg: {ff}\n{hw}")

    def _elegir_temp(self):
        d = QFileDialog.getExistingDirectory(self, "Carpeta temporal", self.e_temp.text())
        if d:
            self.e_temp.setText(d)

    def _descargar(self):
        self.b_desc.setEnabled(False)
        self.l_estado.setText("Descargando modelo… (solo se necesita internet esta vez)")
        self._hilo = HiloModelo(self.c_mod.currentData(), self)
        self._hilo.terminado.connect(self._descargado)
        self._hilo.start()

    def _descargado(self, ok, msg):
        self.b_desc.setEnabled(True)
        self._refrescar()
        if not ok:
            QMessageBox.warning(self, "Modelo", f"No se pudo descargar el modelo:\n{msg}")

    def _limpiar(self):
        self.prefs["carpeta_temporal"] = self.e_temp.text()
        self.prefs.limpiar_temporales()
        QMessageBox.information(self, "Temporales", "Se limpió la caché temporal. Tus proyectos y exportaciones no se tocaron.")

    def _aceptar(self):
        self.prefs["carpeta_temporal"] = self.e_temp.text().strip() or self.prefs["carpeta_temporal"]
        self.prefs["gpu"] = self.c_gpu.currentData()
        self.prefs["sobrescribir"] = self.c_sob.currentData()
        self.prefs["modelo_fondo"] = self.c_mod.currentData()
        self.prefs.guardar()
        self.accept()
