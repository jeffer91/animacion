"""Pruebas del motor, exportación, cola y proyectos (REQ-24). Ejecutar: python -m unittest discover tests -v"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ANIMACION_MODELOS", str(Path(tempfile.gettempdir()) / "animacion_modelos_test"))

from animacion_app import exportador, fondo                       # noqa: E402
from animacion_app.config import Ajustes, Encuadre, tamano         # noqa: E402
from animacion_app.motor import Animador, Render, Sujeto, colocar, reparto   # noqa: E402
from animacion_app.proyecto import ImagenProyecto, Proyecto        # noqa: E402
from animacion_app.trabajos import (Cancelado, Cola, Trabajo, procesar, LISTO, ERROR, CANCELADO)  # noqa: E402
from animacion_app.util import escribir_imagen, leer_imagen        # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="anim_test_"))


def imagen_de_prueba(ruta, alpha=False):
    """Retrato sintético: fondo con degradado, 'cabeza' y 'camiseta'."""
    h, w = 360, 480
    img = np.zeros((h, w, 3), np.uint8)
    for x in range(w):
        img[:, x] = (60 + x * 0.2, 90, 160 - x * 0.1)
    cv2.rectangle(img, (130, 230), (350, 360), (30, 40, 200), -1)
    cv2.ellipse(img, (240, 150), (70, 90), 0, 0, 360, (150, 190, 230), -1)
    cv2.circle(img, (215, 135), 8, (20, 20, 20), -1)
    cv2.circle(img, (265, 135), 8, (20, 20, 20), -1)
    cv2.ellipse(img, (240, 185), (28, 14), 0, 0, 180, (30, 30, 120), 3)
    if alpha:
        a = np.zeros((h, w), np.uint8)
        cv2.rectangle(a, (130, 230), (350, 360), 255, -1)
        cv2.ellipse(a, (240, 150), (70, 90), 0, 0, 360, 255, -1)
        img = np.dstack([img, a])
    escribir_imagen(ruta, img)
    return ruta


def cfg(estilo="lapiz", **kw):
    base = dict(estilo=estilo, W=320, H=180, fps=12, duracion=3.0, final=1.0, fondo=(240, 240, 240))
    base.update(kw)
    return Render(**base)


class TestMotor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.jpg = imagen_de_prueba(str(TMP / "retrato.jpg"))
        cls.png = imagen_de_prueba(str(TMP / "recorte.png"), alpha=True)

    def test_reparto_duraciones_limite(self):
        for dur in (3, 12, 300):
            for est in ("lapiz", "pintura"):
                r = Render(estilo=est, duracion=dur, final=2, fps=30)
                total, ini, n1, n2, n3, fin, etapas = reparto(r)
                self.assertEqual(total, dur * 30)
                self.assertEqual(ini + n1 + n2 + n3 + fin, total)
                self.assertGreaterEqual(fin, 0)
                self.assertEqual(etapas[-1][2], total)

    def test_numero_de_cuadros_y_ultimo_es_original(self):
        suj = Sujeto.desde_archivo(self.jpg)
        for est in ("lapiz", "pintura"):
            c = cfg(est)
            an = Animador(suj, c)
            cuadros = list(an.cuadros())
            self.assertEqual(len(cuadros), an.total)
            self.assertEqual(cuadros[0].img.shape, (180, 320, 3))
            color, alpha = colocar(suj.recortado(), 320, 180, Encuadre())
            esperado = (color * alpha[..., None] + np.array(c.fondo, np.float32) * (1 - alpha[..., None]))
            diff = np.abs(cuadros[-1].img.astype(np.float32) - esperado).max()
            self.assertLessEqual(diff, 2, f"último fotograma ({est}) no coincide con la imagen original")

    def test_fotogramas_cambian_entre_etapas(self):
        suj = Sujeto.desde_archivo(self.jpg)
        an = Animador(suj, cfg("lapiz", duracion=4.0, fps=12))
        cs = list(an.cuadros())
        a, b = cs[len(cs) // 4].img, cs[len(cs) // 2].img
        self.assertGreater(np.abs(a.astype(int) - b.astype(int)).mean(), 0.1)

    def test_transparente_tiene_alfa_real(self):
        suj = Sujeto.desde_archivo(self.png)
        an = Animador(suj, cfg("pintura", fondo=None))
        cs = list(an.cuadros())
        ult = cs[-1].img
        self.assertEqual(ult.shape[2], 4)
        self.assertEqual(ult[0, 0, 3], 0)              # esquina transparente
        self.assertGreater(int(ult[..., 3].max()), 250)  # sujeto opaco
        self.assertEqual(int(cs[0].img[..., 3].max()), 0)  # el inicio está vacío

    def test_formatos_y_encuadre(self):
        suj = Sujeto.desde_archivo(self.jpg)
        for asp in ("1:1", "16:9", "9:16"):
            W, H = tamano(asp, "HD")
            self.assertEqual({"1:1": (720, 720), "16:9": (1280, 720), "9:16": (720, 1280)}[asp], (W, H))
        for enc in (Encuadre("encajar"), Encuadre("rellenar"), Encuadre("encajar", 1.5, 0.1, -0.1)):
            color, alpha = colocar(suj, 400, 300, enc)
            self.assertEqual(color.shape, (300, 400, 3))
            self.assertGreater(alpha.sum(), 0)
        # rellenar cubre todo el lienzo
        _, a = colocar(suj, 400, 300, Encuadre("rellenar"))
        self.assertTrue((a > 0.99).all())

    def test_sin_deformacion(self):
        suj = Sujeto.desde_archivo(self.jpg)
        _, a = colocar(suj, 1000, 300, Encuadre("encajar"))
        ys, xs = np.nonzero(a > 0.5)
        ratio = (xs.max() - xs.min() + 1) / (ys.max() - ys.min() + 1)
        self.assertAlmostEqual(ratio, 480 / 360, delta=0.03)

    def test_imagen_fuera_de_encuadre(self):
        suj = Sujeto.desde_archivo(self.jpg)
        an = Animador(suj, cfg(encuadre=Encuadre("encajar", 1.0, 5.0, 0.0)))
        with self.assertRaises(ValueError):
            an.preparar()


class TestArchivos(unittest.TestCase):
    def test_ruta_con_tildes_y_enie(self):
        d = TMP / "niño_canción"
        d.mkdir(exist_ok=True)
        r = imagen_de_prueba(str(d / "Cristiano Ronaldo ñandú.png"))
        self.assertEqual(leer_imagen(r).shape[2], 3)

    def test_archivo_danado(self):
        malo = TMP / "malo.jpg"
        malo.write_bytes(b"esto no es una imagen")
        with self.assertRaises(ValueError):
            leer_imagen(str(malo))
        vacio = TMP / "vacio.png"
        vacio.write_bytes(b"")
        with self.assertRaises(ValueError):
            leer_imagen(str(vacio))

    def test_ruta_unica_no_sobrescribe(self):
        d = TMP / "unica"
        d.mkdir(exist_ok=True)
        (d / "a.mp4").write_bytes(b"x")
        self.assertEqual(exportador.ruta_unica(d, "a", ".mp4").name, "a_v2.mp4")
        (d / "a_v2.mp4").write_bytes(b"x")
        self.assertEqual(exportador.ruta_unica(d, "a", ".mp4").name, "a_v3.mp4")
        self.assertEqual(exportador.ruta_unica(d, "a", ".mp4", "sobrescribir").name, "a.mp4")


def ffprobe(ruta):
    """Devuelve dict con codec_name, pix_fmt, width, height, nb_frames (o None sin ffprobe)."""
    import json
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    out = subprocess.run([exe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=codec_name,pix_fmt,width,height,nb_frames", "-of", "json", str(ruta)],
                         capture_output=True, text=True).stdout
    return json.loads(out)["streams"][0]


class TestExportacion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.jpg = imagen_de_prueba(str(TMP / "e_retrato.jpg"))
        cls.png = imagen_de_prueba(str(TMP / "e_recorte.png"), alpha=True)

    def trabajo(self, img, estilo="lapiz", **aj):
        a = Ajustes(duracion=3, final=1, fps=24, calidad="HD", **aj)
        return Trabajo(img, estilo, a, Encuadre(), False, proyecto="Prueba", carpeta_exportacion=str(TMP / "exp"),
                       carpeta_temp=str(TMP / "temp"))

    def test_mp4_con_fondo_todos_los_formatos(self):
        for asp, (w, h) in (("1:1", (720, 720)), ("16:9", (1280, 720)), ("9:16", (720, 1280))):
            t = self.trabajo(self.jpg, aspecto=asp, fondo="blanco")
            procesar(t, threading.Event())
            self.assertEqual(t.estado, LISTO)
            self.assertTrue(Path(t.salida).exists())
            self.assertFalse(Path(t.salida + ".parte").exists())
            info = ffprobe(t.salida)
            if info:
                self.assertEqual(info["codec_name"], "h264")
                self.assertEqual((int(info["width"]), int(info["height"])), (w, h))
                self.assertEqual(int(info["nb_frames"]), 72)         # 3 s a 24 fps

    def test_mov_prores_con_alfa(self):
        t = self.trabajo(self.png, "pintura", fondo="transparente", formato_transparente="mov")
        procesar(t, threading.Event())
        info = ffprobe(t.salida)
        if info:
            self.assertEqual(info["codec_name"], "prores")
            self.assertIn("yuva", info["pix_fmt"])               # canal alfa auténtico
        self.assertIn("transparente", t.salida)

    def test_secuencia_png_rgba(self):
        t = self.trabajo(self.png, fondo="transparente", formato_transparente="png")
        procesar(t, threading.Event())
        archivos = sorted(Path(t.salida).glob("frame_*.png"))
        self.assertEqual(len(archivos), 72)
        ult = leer_imagen(archivos[-1])
        self.assertEqual(ult.shape[2], 4)
        self.assertEqual(ult[0, 0, 3], 0)

    def test_no_sobrescribe_exportaciones(self):
        a = self.trabajo(self.jpg)
        b = self.trabajo(self.jpg)
        procesar(a, threading.Event())
        procesar(b, threading.Event())
        self.assertNotEqual(a.salida, b.salida)
        self.assertTrue(Path(a.salida).exists() and Path(b.salida).exists())

    def test_cancelacion_no_deja_archivos(self):
        t = self.trabajo(self.jpg)
        t.nombre = "cancelado"
        ev = threading.Event()
        n = [0]

        def notif(_t):
            n[0] += 1
            if n[0] > 3:
                ev.set()
        with self.assertRaises(Cancelado):
            procesar(t, ev, notif)
        carpeta = t.carpeta_destino()
        self.assertEqual([p.name for p in carpeta.glob("cancelado*")], [])

    def test_cola_un_fallo_no_detiene_a_los_demas(self):
        malo = TMP / "roto.jpg"
        malo.write_bytes(b"corrupto")
        hechos = threading.Event()
        cola = Cola(al_terminar=hechos.set)
        t1, t2, t3 = self.trabajo(self.jpg), self.trabajo(str(malo)), self.trabajo(self.jpg, "pintura")
        for t in (t1, t2, t3):
            cola.agregar(t)
        self.assertTrue(hechos.wait(120))
        self.assertEqual((t1.estado, t2.estado, t3.estado), (LISTO, ERROR, LISTO))
        self.assertTrue(t2.error)

    def test_cancelar_trabajo_en_cola(self):
        hechos = threading.Event()
        cola = Cola(al_terminar=hechos.set)
        t1, t2 = self.trabajo(self.jpg), self.trabajo(self.jpg, "pintura")
        cola.agregar(t1)
        cola.agregar(t2)
        cola.cancelar(t2.id)
        self.assertTrue(hechos.wait(120))
        self.assertEqual(t2.estado, CANCELADO)
        self.assertEqual(t1.estado, LISTO)


class TestFondo(unittest.TestCase):
    def test_grabcut_alternativo(self):
        img = leer_imagen(imagen_de_prueba(str(TMP / "f.jpg")))[:, :, :3]
        a = fondo._grabcut(img)
        self.assertEqual(a.shape, img.shape[:2])
        self.assertTrue(0 <= a.min() and a.max() <= 1)

    def test_recorte_con_cache(self):
        r = imagen_de_prueba(str(TMP / "f2.jpg"))
        a1, info = fondo.obtener_alpha(r, str(TMP / "temp"), "u2netp")
        a2, info2 = fondo.obtener_alpha(r, str(TMP / "temp"), "u2netp")
        self.assertTrue(np.allclose(a1, a2, atol=1 / 255))
        self.assertIn("cobertura", info)


class TestProyecto(unittest.TestCase):
    def test_guardar_abrir_duplicar_recuperar(self):
        p = Proyecto(nombre="Demo")
        p.ajustes = Ajustes(aspecto="9:16", duracion=20, fondo="negro", quitar_fondo=True)
        p.imagenes = [ImagenProyecto(str(TMP / "retrato.jpg"), encuadre=Encuadre("rellenar", 1.3, 0.1, 0.0))]
        ruta = TMP / "proys" / "Demo" / "Demo.animproj"
        p.guardar(ruta)
        q = Proyecto.abrir(ruta)
        self.assertEqual(q.ajustes.aspecto, "9:16")
        self.assertEqual(q.ajustes.duracion, 20)
        self.assertEqual(q.imagenes[0].encuadre.modo, "rellenar")
        self.assertFalse(Proyecto.recuperacion_pendiente(ruta))
        q.marcar()
        q.autoguardar(TMP)
        self.assertTrue(Proyecto.recuperacion_pendiente(ruta))
        copia = q.duplicar(TMP / "proys" / "Demo2" / "Demo2.animproj", "Demo2")
        self.assertEqual(copia.nombre, "Demo2")
        self.assertTrue((TMP / "proys" / "Demo2" / "Demo2.animproj").exists())

    def test_avisa_archivos_faltantes(self):
        p = Proyecto(nombre="X")
        p.imagenes = [ImagenProyecto(str(TMP / "no_existe.png"))]
        self.assertEqual(len(p.faltantes()), 1)

    def test_ajustes_validacion(self):
        a = Ajustes(duracion=1, final=99, detalle=50, fps=17).validar()
        self.assertEqual(a.duracion, 3.0)
        self.assertEqual(a.final, 1.5)
        self.assertEqual(a.detalle, 10)
        self.assertEqual(a.fps, 30)
        self.assertEqual(Ajustes(duracion=9999).validar().duracion, 300.0)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
