#!/usr/bin/env python3
"""
animacion.py - Animación de dibujo para el canal 11 Records
=============================================================
Toma CUALQUIER imagen (foto de jugador, escudo, estadio, PNG sin fondo...)
y genera un video donde se ve cómo se va dibujando.

Dos estilos:
  lapiz    -> 1) trazo a lápiz  2) sombreado  3) aparece la imagen a color
  pintura  -> dibuja el contorno y lo va PINTANDO con pincel hasta quedar la imagen

Uso rápido:
  python animacion.py foto.jpg                     # estilo lápiz, 12 s
  python animacion.py foto.jpg --modo pintura      # estilo pintura
  python animacion.py foto.jpg --modo ambos        # genera los dos videos
  python animacion.py carpeta/ --modo ambos        # TODAS las imágenes de la carpeta
"""
import argparse
import glob
import os
import subprocess
import sys

import cv2
import numpy as np

FORMATOS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------


def parse_color(txt):
    """'blanco' | 'papel' | 'negro' | '#RRGGBB' -> tupla BGR."""
    t = txt.strip().lower()
    base = {"blanco": (255, 255, 255), "papel": (232, 240, 245), "negro": (20, 20, 20)}
    if t in base:
        return base[t]
    if t.startswith("#") and len(t) == 7:
        r, g, b = int(t[1:3], 16), int(t[3:5], 16), int(t[5:7], 16)
        return (b, g, r)
    raise ValueError(f"Color no válido: {txt}")


def suave(t):
    t = float(np.clip(t, 0, 1))
    return t * t * (3 - 2 * t)


def ruido(h, w, escala, rng):
    """Ruido suave 0..1 del tamaño (h,w)."""
    chico = rng.random((h // escala + 3, w // escala + 3)).astype(np.float32)
    grande = cv2.resize(chico, (w, h), interpolation=cv2.INTER_CUBIC)
    grande -= grande.min()
    grande /= max(grande.max(), 1e-6)
    return grande


def cargar_imagen(ruta, W, H, fondo, margen=0.92):
    """Devuelve (color_full, alpha_full, rect) en un lienzo W x H."""
    img = cv2.imread(ruta, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"No pude abrir {ruta}")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:
        alpha = img[:, :, 3].astype(np.float32) / 255.0
        bgr = img[:, :, :3]
    else:
        alpha = np.ones(img.shape[:2], np.float32)
        bgr = img
    h, w = bgr.shape[:2]
    esc = min(W * margen / w, H * margen / h)
    nw, nh = max(1, int(round(w * esc))), max(1, int(round(h * esc)))
    interp = cv2.INTER_AREA if esc < 1 else cv2.INTER_CUBIC
    bgr = cv2.resize(bgr, (nw, nh), interpolation=interp)
    alpha = cv2.resize(alpha, (nw, nh), interpolation=interp)
    x0, y0 = (W - nw) // 2, (H - nh) // 2

    lienzo = np.zeros((H, W, 3), np.float32)
    lienzo[:] = fondo
    a3 = alpha[:, :, None]
    lienzo[y0:y0 + nh, x0:x0 + nw] = (
        bgr.astype(np.float32) * a3 + lienzo[y0:y0 + nh, x0:x0 + nw] * (1 - a3)
    )
    alpha_full = np.zeros((H, W), np.float32)
    alpha_full[y0:y0 + nh, x0:x0 + nw] = alpha
    return lienzo.astype(np.uint8), alpha_full, (x0, y0, nw, nh)


# --------------------------------------------------------------------------
# Análisis de la imagen: trazos y boceto
# --------------------------------------------------------------------------


def hacer_boceto(color_full, fondo, rect, alpha_full):
    """Boceto a lápiz (grafito) de la imagen, sobre el color de fondo."""
    gris = cv2.cvtColor(color_full, cv2.COLOR_BGR2GRAY)
    desen = cv2.GaussianBlur(255 - gris, (0, 0), max(3.0, color_full.shape[1] / 200.0))
    boceto = cv2.divide(gris, 255 - desen, scale=256).astype(np.float32)
    g = np.clip((boceto - 90) / (255 - 90), 0, 1) ** 1.6      # 1 = papel, 0 = grafito
    fondo_img = np.zeros(color_full.shape, np.float32)
    fondo_img[:] = fondo
    if np.mean(fondo) > 110:                                   # fondo claro: grafito oscuro
        out = fondo_img * g[:, :, None]
    else:                                                      # fondo oscuro: tiza clara
        out = fondo_img + (255 - fondo_img) * (1 - g)[:, :, None]
    a3 = alpha_full[:, :, None]
    out = out * a3 + fondo_img * (1 - a3)
    return np.clip(out, 0, 255).astype(np.uint8)


def extraer_trazos(color_full, alpha_full, rect, detalle):
    """Devuelve (puntos Nx2, corte N bool) con el recorrido del lápiz."""
    x0, y0, w, h = rect
    gris = cv2.cvtColor(color_full, cv2.COLOR_BGR2GRAY)[y0:y0 + h, x0:x0 + w]
    suav = cv2.bilateralFilter(gris, 7, 40, 40)
    suav = cv2.GaussianBlur(suav, (0, 0), 1.2)

    lo = max(12, 120 - detalle * 10)
    hi = lo * 2.5
    bordes = cv2.Canny(suav, lo, hi, L2gradient=True)
    # contorno del recorte (PNG sin fondo)
    a8 = (alpha_full[y0:y0 + h, x0:x0 + w] * 255).astype(np.uint8)
    if a8.min() < 250:
        bordes |= cv2.Canny(cv2.GaussianBlur(a8, (0, 0), 1.0), 80, 200)

    bordes = cv2.dilate(bordes, np.ones((3, 3), np.uint8))
    esq = cv2.ximgproc.thinning(bordes)
    cont, _ = cv2.findContours(esq, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    min_len = max(8, (12 - detalle) * 6)
    cont = [c[:, 0, :] for c in cont if len(c) >= min_len]
    cont.sort(key=len, reverse=True)

    visitado = np.zeros((h, w), bool)
    pts, cortes = [], []
    for c in cont:
        nuevo = True
        for (px, py) in c:
            if visitado[py, px]:
                nuevo = True
                continue
            visitado[py, px] = True
            pts.append((px + x0, py + y0))
            cortes.append(nuevo)
            nuevo = False
    if not pts:
        raise RuntimeError("No encontré trazos. Prueba con --detalle más alto (ej. 8).")
    return np.array(pts, np.int32), np.array(cortes, bool)


# --------------------------------------------------------------------------
# Mapas de revelado por bandas (el pincel/lápiz va de lado a lado)
# --------------------------------------------------------------------------


class Bandas:
    def __init__(self, shape, rect, alto_banda, rng, suavidad=0.08):
        H, W = shape
        x0, y0, w, h = rect
        self.rect = rect
        self.alto = alto_banda
        self.n = max(1, int(np.ceil(h / alto_banda)))
        self.soft = suavidad / self.n
        ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
        ru = ruido(H, W, max(16, alto_banda // 2), rng) - 0.5
        ru2 = ruido(H, W, max(16, alto_banda // 3), rng) - 0.5
        yy = ys + ru * alto_banda * 0.7
        b = np.floor((yy - y0) / alto_banda)
        b = np.clip(b, 0, self.n - 1)
        fx = np.clip((xs - x0) / w + ru2 * 0.05, 0, 1)
        fx = np.where(b % 2 == 0, fx, 1 - fx)
        self.T = ((b + fx) / self.n).astype(np.float32)

    def mascara(self, t):
        tc = t * (1 + self.soft)
        return np.clip((tc - self.T) / self.soft, 0, 1)[:, :, None]

    def cursor(self, t):
        x0, y0, w, h = self.rect
        tin = np.clip(t, 0, 0.9999) * self.n
        b = int(tin)
        fr = tin - b
        fr = fr if b % 2 == 0 else 1 - fr
        x = x0 + fr * w
        y = y0 + (b + 0.5) * self.alto + np.sin(tin * 40) * self.alto * 0.25
        return int(x), int(min(y, y0 + h - 2))


class BarridoOrganico:
    """Barrido diagonal irregular, para que aparezca la imagen a color."""

    def __init__(self, shape, rng, suavidad=0.35):
        H, W = shape
        ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
        diag = (xs / W * 0.5 + ys / H * 0.5)
        ru = ruido(H, W, max(24, W // 14), rng)
        T = diag * 0.55 + ru * 0.45
        T -= T.min()
        T /= T.max()
        self.T = T
        self.soft = suavidad

    def mascara(self, t):
        tc = t * (1 + self.soft)
        return np.clip((tc - self.T) / self.soft, 0, 1)[:, :, None]


# --------------------------------------------------------------------------
# Lápiz / pincel (sprites dibujados con OpenCV)
# --------------------------------------------------------------------------


def _quad(p, d, n, a, b, ha, hb):
    return np.array([p + d * a + n * ha, p + d * b + n * hb,
                     p + d * b - n * hb, p + d * a - n * ha], np.int32)


def dibujar_herramienta(frame, x, y, tipo, escala, color_punta=(60, 60, 60), sprite=None):
    if sprite is not None:
        img, (ax, ay) = sprite
        _pegar(frame, img, x - ax, y - ay)
        return
    ang = np.deg2rad(-52)
    d = np.array([np.cos(ang), np.sin(ang)], np.float32)
    n = np.array([-d[1], d[0]], np.float32)
    p = np.array([x, y], np.float32)
    s = escala
    cont = (25, 25, 30)
    if tipo == "lapiz":
        capas = [
            (0, 70 * s, 0, 13 * s, (170, 205, 235)),       # madera
            (0, 24 * s, 0, 4.5 * s, (70, 70, 75)),          # grafito
            (70 * s, 330 * s, 13 * s, 13 * s, (40, 190, 245)),  # cuerpo amarillo
            (330 * s, 352 * s, 13 * s, 13 * s, (190, 190, 195)),  # virola
            (352 * s, 388 * s, 13 * s, 13 * s, (150, 150, 235)),  # goma
        ]
    else:
        capas = [
            (0, 55 * s, 2 * s, 11 * s, color_punta),       # cerdas
            (55 * s, 125 * s, 11 * s, 11 * s, (200, 200, 205)),  # virola
            (125 * s, 400 * s, 11 * s, 8 * s, (40, 60, 150)),    # mango
        ]
    for a, b, ha, hb, col in capas:
        q = _quad(p, d, n, a, b, ha, hb)
        cv2.fillPoly(frame, [q], col, cv2.LINE_AA)
        cv2.polylines(frame, [q], True, cont, 1, cv2.LINE_AA)


def _pegar(frame, img, x, y):
    h, w = img.shape[:2]
    H, W = frame.shape[:2]
    xa, ya = max(0, x), max(0, y)
    xb, yb = min(W, x + w), min(H, y + h)
    if xa >= xb or ya >= yb:
        return
    sub = img[ya - y:yb - y, xa - x:xb - x]
    if sub.shape[2] == 4:
        a = sub[:, :, 3:4].astype(np.float32) / 255
        frame[ya:yb, xa:xb] = (sub[:, :, :3] * a + frame[ya:yb, xa:xb] * (1 - a)).astype(np.uint8)
    else:
        frame[ya:yb, xa:xb] = sub


# --------------------------------------------------------------------------
# Escritor de video
# --------------------------------------------------------------------------


class Video:
    def __init__(self, salida, W, H, fps):
        os.makedirs(os.path.dirname(os.path.abspath(salida)), exist_ok=True)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
               "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", salida]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def add(self, frame):
        self.p.stdin.write(np.ascontiguousarray(frame).tobytes())

    def close(self):
        self.p.stdin.close()
        self.p.wait()


# --------------------------------------------------------------------------
# Generadores de animación
# --------------------------------------------------------------------------


class Pluma:
    """Va dibujando los trazos sobre un lienzo persistente."""

    def __init__(self, W, H, fondo, pts, cortes, grosor, color):
        self.lienzo = np.zeros((H, W, 3), np.uint8)
        self.lienzo[:] = fondo
        self.pts, self.cortes = pts, cortes
        self.n = len(pts)
        self.i = 0
        self.grosor, self.color = grosor, color

    def avanzar_hasta(self, k):
        k = int(min(self.n, k))
        if k <= self.i:
            return
        a = max(0, self.i - 1)
        seg = self.pts[a:k]
        cor = self.cortes[a:k].copy()
        cor[0] = True
        idx = np.flatnonzero(cor)
        for trozo in np.split(seg, idx[1:]):
            if len(trozo) == 1:
                cv2.circle(self.lienzo, tuple(int(v) for v in trozo[0]), self.grosor // 2,
                           self.color, -1, cv2.LINE_AA)
            else:
                cv2.polylines(self.lienzo, [trozo.reshape(-1, 1, 2)], False,
                              self.color, self.grosor, cv2.LINE_AA)
        self.i = k

    def punta(self):
        j = max(0, min(self.n - 1, self.i - 1))
        return int(self.pts[j][0]), int(self.pts[j][1])


def animar(ruta, salida, modo, args):
    W, H = FORMATOS[args.formato]
    fps = args.fps
    fondo = parse_color(args.fondo)
    rng = np.random.default_rng(7)
    esc = W / 1920.0 if W >= H else H / 1920.0

    color_full, alpha_full, rect = cargar_imagen(ruta, W, H, fondo)
    pts, cortes = extraer_trazos(color_full, alpha_full, rect, args.detalle)
    boceto = hacer_boceto(color_full, fondo, rect, alpha_full)

    sprite = None
    if args.mano:
        sp = cv2.imread(args.mano, cv2.IMREAD_UNCHANGED)
        if sp is None:
            raise FileNotFoundError(args.mano)
        ax, ay = (int(v) for v in args.mano_punta.split(",")) if args.mano_punta else (0, sp.shape[0] - 1)
        sprite = (sp, (ax, ay))

    total = int(round(args.duracion * fps))
    fin = int(round(args.final * fps))
    ini = int(round(0.3 * fps))
    dib = max(30, total - fin - ini)

    if modo == "lapiz":
        n1, n2 = int(dib * 0.50), int(dib * 0.25)
        n3 = dib - n1 - n2
        grosor, col_linea = max(2, int(round(2.2 * esc))), (55, 52, 50)
        sombra = Bandas((H, W), rect, max(30, int(52 * esc)), rng)
        color_wipe = BarridoOrganico((H, W), rng)
    else:
        n1 = int(dib * 0.33)
        n2 = int(dib * 0.57)
        n3 = dib - n1 - n2
        grosor, col_linea = max(2, int(round(2.6 * esc))), (38, 32, 30)
        pintar = Bandas((H, W), rect, max(50, int(95 * esc)), rng)

    pluma = Pluma(W, H, fondo, pts, cortes, grosor, col_linea)
    vid = Video(salida, W, H, fps)
    papel = np.zeros((H, W, 3), np.uint8)
    papel[:] = fondo

    for _ in range(ini):
        vid.add(papel)

    f_color = color_full.astype(np.float32)
    f_boc = boceto.astype(np.float32)

    # ---------------- Fase 1: trazos ----------------
    for f in range(n1):
        pluma.avanzar_hasta(pluma.n * suave_lineal(f + 1, n1))
        fr = pluma.lienzo.copy()
        if modo == "lapiz":
            x, y = pluma.punta()
            dibujar_herramienta(fr, x, y, "lapiz", esc, sprite=sprite)
        else:
            x, y = pluma.punta()
            dibujar_herramienta(fr, x, y, "lapiz", esc, sprite=sprite)
        vid.add(fr)
    pluma.avanzar_hasta(pluma.n)

    lineas = pluma.lienzo.astype(np.float32)

    if modo == "lapiz":
        # ---------------- Fase 2: sombreado ----------------
        for f in range(n2):
            t = (f + 1) / n2
            m = sombra.mascara(t)
            out = lineas * (1 - m) + f_boc * m
            fr = out.astype(np.uint8)
            x, y = sombra.cursor(t)
            dibujar_herramienta(fr, x, y, "lapiz", esc, sprite=sprite)
            vid.add(fr)
        # ---------------- Fase 3: aparece la imagen a color ----------------
        for f in range(n3):
            t = suave((f + 1) / n3)
            m = color_wipe.mascara(t)
            out = f_boc * (1 - m) + f_color * m
            vid.add(out.astype(np.uint8))
    else:
        # ---------------- Fase 2: pintar con pincel ----------------
        norm = np.clip(lineas / np.maximum(np.array(fondo, np.float32), 1), 0, 1)
        for f in range(n2):
            t = (f + 1) / n2
            m = pintar.mascara(t)
            base = papel.astype(np.float32) * (1 - m) + f_color * m
            out = base * norm            # las líneas quedan sobre la pintura
            fr = out.astype(np.uint8)
            x, y = pintar.cursor(t)
            xi = int(np.clip(x, 0, W - 1))
            yi = int(np.clip(y, 0, H - 1))
            col = tuple(int(v) for v in color_full[yi, xi])
            dibujar_herramienta(fr, x, y, "pincel", esc, color_punta=col, sprite=sprite)
            vid.add(fr)
        # ---------------- Fase 3: desaparece el contorno ----------------
        for f in range(n3):
            t = suave((f + 1) / n3)
            out = f_color * (norm ** (1 - t))
            vid.add(out.clip(0, 255).astype(np.uint8))

    final = color_full
    for _ in range(fin + (total - ini - dib - fin)):
        vid.add(final)
    vid.close()
    return salida


def suave_lineal(i, n):
    """Ritmo del trazo: arranca tranquilo, acelera un poco y termina rápido."""
    t = i / n
    return t ** 0.85


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def listar_entradas(ruta):
    if os.path.isdir(ruta):
        archivos = sorted(f for f in glob.glob(os.path.join(ruta, "*"))
                          if f.lower().endswith(EXT))
        if not archivos:
            sys.exit(f"No hay imágenes en {ruta}")
        return archivos
    return [ruta]


def main():
    ap = argparse.ArgumentParser(description="Animación de dibujo para 11 Records")
    ap.add_argument("entrada", help="Imagen o carpeta con imágenes")
    ap.add_argument("--modo", choices=["lapiz", "pintura", "ambos"], default="lapiz",
                    help="lapiz = lápiz y luego color | pintura = dibuja y pinta | ambos")
    ap.add_argument("--duracion", type=float, default=12.0,
                    help="Duración total en segundos (incluye el final)")
    ap.add_argument("--final", type=float, default=2.5,
                    help="Segundos que se queda la imagen terminada al final")
    ap.add_argument("--formato", choices=list(FORMATOS), default="16:9",
                    help="16:9 (YouTube), 9:16 (Shorts), 1:1")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--fondo", default="papel", help="papel | blanco | negro | #RRGGBB")
    ap.add_argument("--detalle", type=int, default=5, choices=range(1, 11),
                    metavar="1-10", help="Cantidad de trazos (1 = pocos, 10 = muchísimos)")
    ap.add_argument("--mano", help="PNG con transparencia de una mano/lápiz propio (opcional)")
    ap.add_argument("--mano-punta", help="x,y de la punta dentro del PNG (por defecto esquina inferior izquierda)")
    ap.add_argument("--salida", default="salida", help="Carpeta de salida")
    args = ap.parse_args()

    modos = ["lapiz", "pintura"] if args.modo == "ambos" else [args.modo]
    for ruta in listar_entradas(args.entrada):
        nombre = os.path.splitext(os.path.basename(ruta))[0]
        for m in modos:
            out = os.path.join(args.salida, f"{nombre}_{m}.mp4")
            print(f"-> {out}")
            animar(ruta, out, m, args)
    print("Listo.")


if __name__ == "__main__":
    main()
