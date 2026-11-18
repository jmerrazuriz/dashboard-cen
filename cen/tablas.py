"""Tablas con estilo para el dashboard (HTML generado aquí; funciones puras, sin Streamlit).

Reemplazan a ``st.dataframe`` donde importa la lectura: encabezado fijo, filas alternadas, resaltado al pasar
el cursor, números alineados con formato chileno (1.234,5), barras dentro de la celda para comparar de un
vistazo, etiquetas de color para estados y el color de cada tecnología (el mismo de los gráficos).

Uso:
    html = tabla_html(df, [Col("barra", "Barra"), Col("spread", "Spread", "barra", dec=1, unidad="USD/MWh")])
"""
from __future__ import annotations

import html as _html
import itertools
import math
from dataclasses import dataclass, field

import pandas as pd

TIPOS = {"texto", "num", "pct", "barra", "delta", "badge", "tec", "largo"}
_IDS = itertools.count(1)  # ids únicos para los «ver más» de la página

# etiquetas de color: (fondo, texto)
VERDE = ("#E7F6EE", "#166534")
AMBAR = ("#FEF3C7", "#92400E")
ROJO = ("#FDE8E8", "#9B1C1C")
GRIS = ("#F1F5F9", "#475569")
AZUL = ("#E8F1FB", "#1E4E8C")


@dataclass
class Col:
    """Columna de una tabla.

    tipo: texto · num (número) · pct (número con %) · barra (número con barra proporcional) ·
          delta (número con signo, verde si sube y rojo si baja) · badge (etiqueta de color según ``colores``) ·
          tec (punto con el color de la tecnología) · largo (texto largo con «ver más»).
    """
    nombre: str
    titulo: str | None = None
    tipo: str = "texto"
    dec: int = 0
    unidad: str = ""
    ancho: str | None = None
    colores: dict = field(default_factory=dict)  # badge: valor -> (fondo, texto); tec: tecnología -> color
    maximo: float | None = None                   # barra: valor que llena la barra (por defecto, el máximo)
    color_barra: str = "#5BC0F0"

    def __post_init__(self):
        if self.tipo not in TIPOS:
            raise ValueError(f"tipo de columna desconocido: {self.tipo}")


def fmt_num(v, dec: int = 0) -> str:
    """Número con formato chileno: punto de miles y coma decimal. NaN/None -> «—»."""
    if v is None or (isinstance(v, float) and math.isnan(v)) or pd.isna(v):
        return "—"
    s = f"{float(v):,.{dec}f}"                     # 12,345.6 (formato inglés)
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _vacio(v) -> bool:
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _celda(col: Col, v, maximo: float | None, largo_max: int) -> tuple[str, str]:
    """(clase CSS de la celda, contenido HTML)."""
    if col.tipo in ("num", "pct", "barra", "delta"):
        if _vacio(v):
            return "num", '<span class="nd">—</span>'
        x = float(v)
        txt = fmt_num(x, col.dec) + (" %" if col.tipo == "pct" else "")
        if col.tipo == "delta":
            signo = "+" if x > 0 else ""
            clase = "sube" if x > 0 else "baja" if x < 0 else ""
            return "num", f'<span class="{clase}">{signo}{txt}{" " + col.unidad if col.unidad else ""}</span>'
        if col.tipo == "barra":
            ancho = 0 if not maximo else max(0.0, min(100.0, x / maximo * 100))
            return "num", (f'<div class="bc"><span style="width:{ancho:.1f}%;background:{col.color_barra}"></span>'
                           f"<b>{txt}</b></div>")
        return "num", txt
    if _vacio(v) or str(v).strip() == "":
        return "", '<span class="nd">—</span>'
    t = str(v)
    if col.tipo == "badge":
        fondo, texto = col.colores.get(t, GRIS)
        return "", f'<span class="badge" style="background:{fondo};color:{texto}">{_html.escape(t)}</span>'
    if col.tipo == "tec":
        color = col.colores.get(t, "#9AA0A6")
        return "", f'<span class="tec" style="background:{color}"></span>{_html.escape(t)}'
    if col.tipo == "largo" and len(t) > largo_max:
        # «ver más» / «ver menos» solo con HTML y CSS: una casilla oculta controla si se ve el resto del texto,
        # y la etiqueta (siempre al final) cambia de texto según el estado.
        corte = t.rfind(" ", 0, largo_max)
        corte = corte if corte > 0 else largo_max
        uid = f"vm{next(_IDS)}"
        return "", (f'{_html.escape(t[:corte])}<input type="checkbox" id="{uid}" class="vm-chk">'
                    f'<span class="vm-resto">{_html.escape(t[corte:])}</span>'
                    f'<label for="{uid}" class="vm-btn" role="button"></label>')
    return "", _html.escape(t)


def tabla_html(df: pd.DataFrame, cols: list[Col], alto: int | None = None, largo_max: int = 350) -> str:
    """Tabla HTML con estilo. ``alto``: altura máxima en px (desplazamiento interno, encabezado fijo)."""
    maximos = {}
    for c in cols:
        if c.tipo == "barra":
            serie = pd.to_numeric(df[c.nombre], errors="coerce") if c.nombre in df else pd.Series(dtype=float)
            m = c.maximo if c.maximo is not None else (serie.abs().max() if not serie.dropna().empty else None)
            maximos[c.nombre] = float(m) if m else None
    cab = []
    for c in cols:
        der = c.tipo in ("num", "pct", "barra", "delta")
        estilo = f"width:{c.ancho};" if c.ancho else ""
        tit = _html.escape(c.titulo if c.titulo is not None else c.nombre)
        uni = f'<span class="u">{_html.escape(c.unidad)}</span>' if c.unidad and c.tipo != "delta" else ""
        cab.append(f'<th class="{"num" if der else ""}" style="{estilo}">{tit}{uni}</th>')
    filas = []
    for _, r in df.iterrows():
        celdas = []
        for c in cols:
            clase, contenido = _celda(c, r[c.nombre] if c.nombre in r else None, maximos.get(c.nombre), largo_max)
            celdas.append(f'<td class="{clase}">{contenido}</td>')
        filas.append("<tr>" + "".join(celdas) + "</tr>")
    if not filas:
        filas = [f'<tr><td colspan="{len(cols)}" class="nd">Sin datos</td></tr>']
    alto_css = f"max-height:{alto}px;" if alto else ""
    return (f'<div class="tcen" style="{alto_css}"><table><thead><tr>{"".join(cab)}</tr></thead>'
            f'<tbody>{"".join(filas)}</tbody></table></div>')


CSS = """
<style>
.tcen{overflow:auto;border:1px solid #E5E7EB;border-radius:10px;margin:2px 0 8px;
  box-shadow:0 1px 2px rgba(15,23,42,.04);background:#fff}
.tcen table{width:100%;border-collapse:separate;border-spacing:0;font-size:.86rem;
  font-variant-numeric:tabular-nums;table-layout:auto}
.tcen th{position:sticky;top:0;z-index:1;background:#F8FAFC;color:#475569;font-weight:600;font-size:.72rem;
  text-transform:uppercase;letter-spacing:.04em;text-align:left;padding:9px 12px;
  border-bottom:1px solid #E5E7EB;white-space:nowrap}
.tcen th .u{display:block;font-weight:400;text-transform:none;letter-spacing:0;color:#94A3B8;font-size:.7rem}
.tcen td{padding:8px 12px;border-bottom:1px solid #F1F5F9;color:#1F2937;vertical-align:top;
  overflow-wrap:break-word;word-break:normal;line-height:1.4}
.tcen tbody tr:nth-child(even) td{background:#FBFCFE}
.tcen tbody tr:hover td{background:#EEF6FD}
.tcen tbody tr:last-child td{border-bottom:none}
.tcen .num{text-align:right;white-space:nowrap}
.tcen .nd{color:#94A3B8}
.tcen .sube{color:#047857;font-weight:600}.tcen .baja{color:#B91C1C;font-weight:600}
.tcen .badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.74rem;font-weight:600;
  white-space:nowrap}
.tcen .tec{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:1px}
.tcen .bc{position:relative;min-width:96px;height:20px;border-radius:5px;background:#F1F5F9;overflow:hidden}
.tcen .bc span{position:absolute;left:0;top:0;bottom:0;opacity:.55;border-radius:5px}
.tcen .bc b{position:relative;display:block;padding:1px 7px;font-weight:600;font-size:.8rem;line-height:18px}
.tcen .vm-chk{display:none}
.tcen .vm-resto{display:none}
.tcen .vm-chk:checked + .vm-resto{display:inline}
.tcen .vm-btn{cursor:pointer;color:#1F5FA8;font-weight:600;white-space:nowrap;user-select:none}
.tcen .vm-btn:hover{text-decoration:underline}
.tcen .vm-btn::after{content:"… ver más"}
.tcen .vm-chk:checked ~ .vm-btn::after{content:" ver menos"}
</style>"""

# Colores para etiquetas frecuentes
COLORES_ESTADO = {
    "Aprobado": VERDE, "aprobado": VERDE, "ejecucion_exitosa": VERDE,
    "Pendiente": AMBAR, "pendiente": AMBAR, "En ejecución": AZUL,
    "Rechazado": ROJO, "rechazado": ROJO, "Anulado": GRIS, "anulado": GRIS,
}
COLORES_RIESGO = {"Riesgo Alto": ROJO, "Riesgo Medio": AMBAR, "Riesgo Bajo": VERDE, "Sin Riesgo": GRIS}
COLORES_ACCION = {"Comienza carga": VERDE, "Termina carga": AZUL, "Comienza descarga": AMBAR,
                  "Termina descarga": ROJO}
