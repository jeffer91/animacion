"""Proyectos: guardado, autoguardado/recuperación, duplicado y avisos de archivos faltantes."""
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import Ajustes, Encuadre

VERSION = 1
EXT = ".animproj"


@dataclass
class ImagenProyecto:
    ruta: str
    quitar_fondo: bool | None = None          # None = usa el ajuste global
    encuadre: Encuadre | None = None          # None = usa el global
    nombre_salida: str = ""

    def a_dict(self):
        return {"ruta": self.ruta, "quitar_fondo": self.quitar_fondo,
                "encuadre": self.encuadre.a_dict() if self.encuadre else None,
                "nombre_salida": self.nombre_salida}

    @staticmethod
    def de_dict(d):
        return ImagenProyecto(d["ruta"], d.get("quitar_fondo"),
                              Encuadre.de_dict(d["encuadre"]) if d.get("encuadre") else None,
                              d.get("nombre_salida", ""))

    @property
    def nombre(self):
        return Path(self.ruta).stem


@dataclass
class Proyecto:
    nombre: str = "Proyecto sin título"
    ruta: str = ""                              # archivo .animproj ("" = aún sin guardar)
    imagenes: list = field(default_factory=list)
    ajustes: Ajustes = field(default_factory=Ajustes)
    carpeta_exportacion: str = ""
    modificado: bool = False
    creado: float = field(default_factory=time.time)

    # ------------------------------------------------------------------ datos
    def a_dict(self):
        return {"version": VERSION, "nombre": self.nombre, "creado": self.creado,
                "guardado": time.time(), "carpeta_exportacion": self.carpeta_exportacion,
                "ajustes": self.ajustes.a_dict(),
                "imagenes": [i.a_dict() for i in self.imagenes]}

    @staticmethod
    def de_dict(d, ruta=""):
        p = Proyecto(nombre=d.get("nombre", "Proyecto"), ruta=ruta,
                     ajustes=Ajustes.de_dict(d.get("ajustes")),
                     carpeta_exportacion=d.get("carpeta_exportacion", ""),
                     creado=d.get("creado", time.time()))
        p.imagenes = [ImagenProyecto.de_dict(i) for i in d.get("imagenes", [])]
        return p

    def faltantes(self):
        return [i.ruta for i in self.imagenes if not os.path.exists(i.ruta)]

    def marcar(self):
        self.modificado = True

    # ----------------------------------------------------------------- disco
    @staticmethod
    def _escribir(ruta, datos):
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = ruta.with_name(ruta.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)
        os.replace(tmp, ruta)

    def guardar(self, ruta=None):
        if ruta:
            self.ruta = str(ruta)
        if not self.ruta:
            raise ValueError("El proyecto no tiene ruta de guardado.")
        self._escribir(self.ruta, self.a_dict())
        Path(self.ruta_recuperacion()).unlink(missing_ok=True)
        self.modificado = False

    def ruta_recuperacion(self):
        return self.ruta + ".recuperacion" if self.ruta else ""

    def autoguardar(self, carpeta_fallback):
        """Copia de seguridad periódica (no toca el archivo del proyecto)."""
        destino = self.ruta_recuperacion() or str(Path(carpeta_fallback) / "sin_titulo.animproj.recuperacion")
        self._escribir(destino, self.a_dict())
        return destino

    def duplicar(self, nueva_ruta, nombre=None):
        """Copia del proyecto (las imágenes originales se referencian, no se copian)."""
        c = Proyecto.de_dict(json.loads(json.dumps(self.a_dict())), "")
        c.nombre = nombre or f"{self.nombre} (copia)"
        c.guardar(nueva_ruta)
        return c

    @staticmethod
    def abrir(ruta):
        with open(ruta, "r", encoding="utf-8") as f:
            d = json.load(f)
        if d.get("version", 1) > VERSION:
            raise ValueError("El proyecto fue creado con una versión más reciente de la aplicación.")
        p = Proyecto.de_dict(d, str(ruta))
        # intenta relocalizar imágenes junto al proyecto
        base = Path(ruta).parent
        for im in p.imagenes:
            if not os.path.exists(im.ruta):
                alt = base / Path(im.ruta).name
                if alt.exists():
                    im.ruta = str(alt)
        return p

    @staticmethod
    def recuperacion_pendiente(ruta):
        """True si existe un autoguardado más nuevo que el proyecto (cierre inesperado)."""
        rec = Path(str(ruta) + ".recuperacion")
        return rec.exists() and (not Path(ruta).exists() or rec.stat().st_mtime > Path(ruta).stat().st_mtime)
