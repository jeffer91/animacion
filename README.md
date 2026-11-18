# Animación – 11 Records

Aplicación de escritorio para Windows que convierte cualquier imagen (jugadores, escudos, estadios, PNG sin fondo) en un video donde un **lápiz o un pincel** dibujan la imagen y termina convertida en la foto original a color.

## Cómo abrirla (Windows)

**Opción A – doble clic:** ejecuta `iniciar.bat`. La primera vez crea el entorno e instala todo.

**Opción B – Visual Studio Code:**
```powershell
cd D:\animacion
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
En VS Code también puedes pulsar **F5** y elegir «Animación (ventana)».

> FFmpeg: si no lo tienes instalado se usa el que trae `imageio-ffmpeg`. Para usar el tuyo, déjalo en el PATH o en la carpeta `bin\`.

## Uso

1. **Importa** imágenes (botón, arrastrar y soltar, o una carpeta completa).
2. Elige el **estilo**: Lápiz, Pintura o Ambos (genera dos videos).
3. Ajusta fondo, duración, formato y calidad en el panel derecho. La pestaña **Encuadre** permite mover (arrastrar) y ampliar (rueda) la imagen; **Animación** muestra la vista previa con línea de tiempo.
4. Pulsa **GENERAR ANIMACIÓN**. Los trabajos entran en una cola con progreso y se pueden cancelar; la ventana no se bloquea.

| Estilo | Qué hace |
|---|---|
| Lápiz | Contornos a lápiz → sombreado por hachurado → aparece la imagen a color |
| Pintura | Contorno → el pincel pinta zona por zona → queda la imagen original |

### Fondos y transparencia
- Fondo: papel, blanco, negro o color personalizado.
- **Eliminar fondo automáticamente** (local, sin internet tras descargar el modelo una vez desde *Herramientas → Ajustes*).
- **Transparente**: salida real con canal alfa, como **MOV ProRes 4444** (editores de video) o **secuencia PNG RGBA**.

### Exportación
`<carpeta de exportación>\<proyecto>\con_fondo\*.mp4` y `...\transparente\*.mov`.
Nunca sobrescribe: si el archivo existe crea `nombre_v2`, `nombre_v3`… (configurable). Los archivos se escriben como `.parte` y solo se publican si FFmpeg termina bien.

### Proyectos
Archivo → Nuevo / Abrir / Guardar / Duplicar. Autoguardado cada 60 s con recuperación tras un cierre inesperado. Los proyectos (`.animproj`) solo guardan referencias a tus imágenes originales, que nunca se modifican.

## Línea de comandos
```bash
python animacion.py foto.jpg --modo ambos --formato 9:16
python animacion.py fotos/ --quitar-fondo --fondo transparente
```

## Pruebas
```bash
python -m unittest discover tests -v
```

## Estructura
```
app.py                 ventana de la aplicación
animacion.py           línea de comandos
animacion_app/
  motor.py             animación (alfa real, lápiz/pincel, ritmo dinámico)
  recorrido.py         contornos, hachurado y trayectorias
  fondo.py             recorte automático local (rembg + alternativa GrabCut)
  exportador.py        MP4 / MOV ProRes 4444 / PNG RGBA, GPU si es compatible
  trabajos.py          cola de trabajos cancelable
  proyecto.py, ajustes.py, config.py, util.py
  gui/                 interfaz oscura (PySide6)
tests/                 pruebas automáticas
```

## Estado
Implementada la **etapa 1 y 2** de la especificación. Pendiente (etapa 3): instalador de Windows y versión portable.
