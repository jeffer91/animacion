"""Prueba de humo de la ventana (sin pantalla): importar, vista previa, generar, guardar."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                           # pragma: no cover
    QApplication = None

from tests.test_motor import imagen_de_prueba                  # noqa: E402


@unittest.skipIf(QApplication is None, "PySide6 no instalado")
class TestVentana(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from animacion_app.ajustes import Preferencias
        from animacion_app.gui import tema
        from animacion_app.gui.principal import Principal
        cls.tmp = Path(tempfile.mkdtemp(prefix="anim_gui_"))
        cls.app = QApplication.instance() or QApplication([])
        tema.aplicar(cls.app)
        p = Preferencias(cls.tmp / "prefs.json")
        p["carpeta_exportacion"] = str(cls.tmp / "exp")
        p["carpeta_temporal"] = str(cls.tmp / "temp")
        cls.w = Principal(p)
        cls.w.show()
        cls.img = imagen_de_prueba(str(cls.tmp / "foto.jpg"))

    def esperar(self, cond, t=90):
        t0 = time.time()
        while time.time() - t0 < t:
            self.app.processEvents()
            time.sleep(0.02)
            if cond():
                return True
        return False

    def test_flujo_completo(self):
        w = self.w
        with mock.patch("animacion_app.gui.principal.QMessageBox.warning") as aviso:
            w.importar_rutas([self.img, str(self.tmp / "texto.txt")])  # el .txt se ignora y se avisa
            self.assertTrue(aviso.called)
        self.assertEqual(len(w.proyecto.imagenes), 1)
        self.assertTrue(self.esperar(lambda: w.sujeto is not None, 30))
        # vista previa generada en segundo plano
        w.panel.s_dur.setValue(3)
        w.panel.s_fin.setValue(1)
        w._lanzar_preview()
        self.assertTrue(self.esperar(lambda: w.fuente is not None and w.fuente.total > 0
                                     and w.fuente.listos >= w.fuente.total))
        w._ir_a(10)
        self.assertEqual(w.pos, 10)
        # generar ambos estilos en cola, sin bloquear la ventana
        w.r_estilo["ambos"].setChecked(True)
        w.panel.c_cal.setCurrentText("HD")
        w.generar()
        self.assertEqual(len(w.cola.trabajos), 2)
        self.assertTrue(self.esperar(lambda: all(t.estado in ("Listo", "Error", "Cancelado")
                                                 for t in w.cola.trabajos), 180))
        self.assertEqual([t.estado for t in w.cola.trabajos], ["Listo", "Listo"])
        for t in w.cola.trabajos:
            self.assertTrue(Path(t.salida).exists())
        # guardar y reabrir proyecto
        w.proyecto.ruta = str(self.tmp / "p" / "demo.animproj")
        w.proyecto.nombre = "demo"
        self.assertTrue(w.guardar())
        self.assertTrue(Path(w.proyecto.ruta).exists())
        # revisar el MP4 dentro de la app
        w.revisar_trabajo(w.cola.trabajos[0].id)
        self.assertGreater(w.fuente.total, 10)
        w.pausar()

    @classmethod
    def tearDownClass(cls):
        cls.w.cola.cancelar_todo()
        cls.w.proyecto.modificado = False
        cls.w.close()
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
