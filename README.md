# Animación de dibujo – 11 Records

Convierte **cualquier imagen** (jugador, escudo, estadio, PNG sin fondo) en un video donde se ve cómo se va dibujando, para ponerlo mientras hablas.

## Estilos

| `--modo` | Qué hace |
|---|---|
| `lapiz` | 1) Trazo a lápiz del contorno → 2) sombreado de grafito → 3) aparece la imagen a color |
| `pintura` | Dibuja el contorno y lo **pinta con pincel** hasta quedar la imagen final |
| `ambos` | Genera los dos videos de cada imagen |

## Instalación

Necesitas Python 3.9+ y [ffmpeg](https://ffmpeg.org/download.html) instalado.

```bash
pip install -r requirements.txt
```

## Uso

```bash
python animacion.py messi.jpg                    # estilo lápiz, 12 s
python animacion.py messi.jpg --modo pintura
python animacion.py messi.jpg --modo ambos
python animacion.py fotos/ --modo ambos          # todas las imágenes de la carpeta
```

Los videos salen en la carpeta `salida/` como `messi_lapiz.mp4` y `messi_pintura.mp4`.

## Opciones útiles

| Opción | Para qué sirve | Por defecto |
|---|---|---|
| `--duracion 15` | Segundos totales (ajústalo a lo que dura tu explicación) | 12 |
| `--final 3` | Segundos que queda la imagen terminada al final | 2.5 |
| `--formato 9:16` | `16:9` YouTube, `9:16` Shorts, `1:1` | 16:9 |
| `--fondo blanco` | `papel`, `blanco`, `negro` o `#RRGGBB` | papel |
| `--detalle 8` | Cantidad de trazos, de 1 (pocos) a 10 (muchísimos) | 5 |
| `--fps 60` | Fotogramas por segundo | 30 |
| `--mano mano.png` | Tu propia mano/lápiz (PNG con transparencia) | lápiz dibujado |
| `--mano-punta 40,310` | Posición x,y de la punta dentro de ese PNG | esquina inferior izquierda |

## Consejos para que se vea mejor

- **PNG sin fondo** del jugador: queda lo más limpio, el contorno sale perfecto.
- Fotos con mucho público o césped: baja `--detalle` (3–4) para evitar trazos innecesarios.
- Fotos limpias con poco detalle: sube `--detalle` (7–9).
- Duración: pon `--duracion` un poco mayor a lo que hablas sobre el jugador y recorta en tu editor.
- En tu editor puedes ponerlo encima de tu video con modo de fusión, o usarlo como clip a pantalla completa.
