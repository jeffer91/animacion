#!/usr/bin/env python3
"""Animación – aplicación de escritorio. Ejecuta:  python app.py"""
import sys


def main():
    from PySide6.QtWidgets import QApplication      # primero Qt, luego OpenCV
    from PySide6.QtGui import QFont
    from animacion_app.ajustes import Preferencias
    from animacion_app.gui import tema
    from animacion_app.gui.principal import Principal

    app = QApplication(sys.argv)
    app.setApplicationName("Animación")
    app.setOrganizationName("11 Records")
    tema.aplicar(app)
    ventana = Principal(Preferencias())
    ventana.show()
    # permite abrir un proyecto o imágenes pasados como argumento
    for a in sys.argv[1:]:
        if a.endswith(".animproj"):
            ventana.abrir(a)
        else:
            ventana.importar_rutas([a])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
