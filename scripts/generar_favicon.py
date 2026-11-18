"""Genera assets/favicon.png (y .svg): una lupa que mira un rayo.

Uso:  .venv\\Scripts\\python scripts\\generar_favicon.py
Se dibuja a 4x y se reduce para suavizar los bordes.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SALIDA = Path(__file__).resolve().parent.parent / "assets"
TAM = 256
ESC = 4  # factor de supersampling

AZUL = (31, 95, 168, 255)       # aro de la lupa
AZUL_OSC = (22, 58, 102, 255)   # mango
CRISTAL = (232, 244, 252, 255)  # interior de la lente
AMARILLO = (242, 183, 1, 255)   # rayo
BORDE_RAYO = (176, 125, 18, 255)

# Rayo en coordenadas de un lienzo de 100×100 (se escala y se centra en la lente)
RAYO = [(56, 8), (24, 54), (45, 54), (36, 92), (76, 40), (54, 40), (66, 8)]


def dibujar() -> Image.Image:
    n = TAM * ESC
    s = n / 100
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # mango (diagonal hacia abajo-derecha), redondeado
    d.line([(63 * s, 63 * s), (90 * s, 90 * s)], fill=AZUL_OSC, width=int(13 * s))
    for x, y in ((63, 63), (90, 90)):
        r = 6.5 * s
        d.ellipse([x * s - r, y * s - r, x * s + r, y * s + r], fill=AZUL_OSC)

    # lente: aro + cristal
    cx, cy, R = 40, 40, 33
    d.ellipse([(cx - R) * s, (cy - R) * s, (cx + R) * s, (cy + R) * s], fill=AZUL)
    r_int = R - 6
    d.ellipse([(cx - r_int) * s, (cy - r_int) * s, (cx + r_int) * s, (cy + r_int) * s], fill=CRISTAL)

    # brillo del cristal
    d.arc([(cx - r_int + 4) * s, (cy - r_int + 4) * s, (cx + r_int - 4) * s, (cy + r_int - 4) * s],
          start=200, end=250, fill=(255, 255, 255, 255), width=int(3 * s))

    # rayo dentro de la lente (escalado a ~60 % y centrado en el cristal)
    k = 0.58
    pts = [(cx + (x - 50) * k, cy + (y - 50) * k) for x, y in RAYO]
    pts = [(x * s, y * s) for x, y in pts]
    d.polygon(pts, fill=AMARILLO, outline=BORDE_RAYO)
    d.line(pts + [pts[0]], fill=BORDE_RAYO, width=int(1.2 * s), joint="curve")

    return img.resize((TAM, TAM), Image.LANCZOS)


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <line x1="63" y1="63" x2="90" y2="90" stroke="#163A66" stroke-width="13" stroke-linecap="round"/>
  <circle cx="40" cy="40" r="33" fill="#1F5FA8"/>
  <circle cx="40" cy="40" r="27" fill="#E8F4FC"/>
  <path d="M{p}" fill="#F2B701" stroke="#B07D12" stroke-width="1.2" stroke-linejoin="round"/>
</svg>
"""


def main() -> None:
    SALIDA.mkdir(exist_ok=True)
    dibujar().save(SALIDA / "favicon.png")
    k, cx, cy = 0.58, 40, 40
    pts = " L".join(f"{cx + (x - 50) * k:.1f},{cy + (y - 50) * k:.1f}" for x, y in RAYO) + " Z"
    (SALIDA / "favicon.svg").write_text(SVG.format(p=pts), encoding="utf-8")
    print("listo:", SALIDA / "favicon.png", "y", SALIDA / "favicon.svg")


if __name__ == "__main__":
    main()
