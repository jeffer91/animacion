#!/usr/bin/env python3
"""
animacion.py – versión por línea de comandos (usa el mismo motor que la app gráfica).

  python animacion.py foto.jpg                         # estilo lápiz, 12 s
  python animacion.py foto.jpg --modo pintura
  python animacion.py foto.jpg --modo ambos --formato 9:16
  python animacion.py fotos/ --modo ambos --quitar-fondo --fondo transparente
  python animacion.py foto.jpg --duracion 20 --calidad "4K" --fps 60

Para la interfaz gráfica:  python app.py
"""
import argparse
import sys
import threading
from pathlib import Path

from animacion_app.config import ASPECTOS, FPS_VALIDOS, LADO_CORTO, Ajustes, Encuadre
from animacion_app.trabajos import ERROR, Trabajo, procesar
from animacion_app.util import es_imagen


def main():
    ap = argparse.ArgumentParser(description="Animación de dibujo para 11 Records")
    ap.add_argument("entrada", help="Imagen o carpeta con imágenes")
    ap.add_argument("--modo", choices=["lapiz", "pintura", "ambos"], default="lapiz")
    ap.add_argument("--duracion", type=float, default=12.0, help="Segundos totales (3 a 300)")
    ap.add_argument("--final", type=float, default=2.0, help="Segundos del resultado final")
    ap.add_argument("--formato", choices=ASPECTOS, default="16:9")
    ap.add_argument("--calidad", choices=list(LADO_CORTO), default="Full HD")
    ap.add_argument("--fps", type=int, choices=FPS_VALIDOS, default=30)
    ap.add_argument("--fondo", default="papel",
                    help="papel | blanco | negro | transparente | #RRGGBB")
    ap.add_argument("--transparente-formato", choices=["mov", "png"], default="mov")
    ap.add_argument("--detalle", type=int, default=5, choices=range(1, 11), metavar="1-10")
    ap.add_argument("--velocidad", choices=["dinamica", "constante"], default="dinamica")
    ap.add_argument("--quitar-fondo", action="store_true", help="Elimina el fondo automáticamente")
    ap.add_argument("--rellenar", action="store_true", help="Rellena el encuadre (recorta) en vez de encajar")
    ap.add_argument("--salida", default="salida", help="Carpeta principal de exportación")
    ap.add_argument("--proyecto", default="CLI", help="Nombre de la subcarpeta del proyecto")
    args = ap.parse_args()

    a = Ajustes(estilo=args.modo, aspecto=args.formato, calidad=args.calidad, fps=args.fps,
                duracion=args.duracion, final=args.final, detalle=args.detalle, velocidad=args.velocidad,
                quitar_fondo=args.quitar_fondo, formato_transparente=args.transparente_formato)
    if args.fondo.startswith("#"):
        a.fondo, a.color_fondo = "color", args.fondo
    else:
        a.fondo = args.fondo
    a.validar()

    p = Path(args.entrada)
    imgs = sorted(x for x in p.iterdir() if x.is_file() and es_imagen(x)) if p.is_dir() else [p]
    if not imgs:
        sys.exit(f"No hay imágenes en {p}")
    estilos = ["lapiz", "pintura"] if a.estilo == "ambos" else [a.estilo]
    fallos = 0
    for img in imgs:
        for est in estilos:
            t = Trabajo(str(img), est, a, Encuadre("rellenar" if args.rellenar else "encajar"),
                        a.quitar_fondo, proyecto=args.proyecto, carpeta_exportacion=args.salida,
                        carpeta_temp=str(Path(args.salida) / ".temp"))
            print(f"-> {img.name} [{est}] ", end="", flush=True)

            def avance(t):
                print(f"\r-> {img.name} [{est}] {t.etapa:<22} {int(t.progreso * 100):3d}%", end="", flush=True)
            try:
                procesar(t, threading.Event(), avance)
                print(f"\r-> {img.name} [{est}] listo: {t.salida}" + " " * 10)
                for aviso in t.avisos:
                    print("   aviso:", aviso)
            except Exception as e:
                fallos += 1
                print(f"\r-> {img.name} [{est}] ERROR: {e}" + " " * 10)
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
