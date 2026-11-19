"""Dashboard SEN: costos marginales, generación por tecnología y demanda.

Ejecutar:  .venv\\Scripts\\streamlit run app.py
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

# Favicon propio (lupa mirando un rayo); se regenera con scripts/generar_favicon.py
_FAVICON = Path(__file__).parent / "assets" / "favicon.png"
st.set_page_config(page_title="Dashboard SEN", layout="wide",
                   page_icon=str(_FAVICON) if _FAVICON.exists() else None)

# Oculta el indicador "Running" de Streamlit (silueta animada + botón Stop); va antes de los
# imports pesados para que se aplique de inmediato. El progreso se ve en los mensajes "Consultando…".
st.markdown('<style>[data-testid="stStatusWidget"]{display:none;}</style>', unsafe_allow_html=True)

import logging  # noqa: E402
import os  # noqa: E402
from datetime import date, datetime, timedelta  # noqa: E402

import pandas as pd  # noqa: E402

import importlib  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

# Módulos propios, en orden de dependencias (cada uno solo importa a los anteriores).
_MODULOS_CEN = ("cen.client", "cen.cache", "cen.transform", "cen.charts", "cen.endpoints", "cen.guia",
                "cen.tablas")


def _recargar_modulos_modificados() -> None:
    """Al recibir un push, Streamlit Cloud vuelve a ejecutar app.py pero puede seguir usando la versión
    anterior de los módulos de cen/ que ya tenía en memoria (y la app falla, p. ej. con AttributeError).
    Se recarga cada módulo cuyo archivo cambió después de importarse, o que no tiene la marca de carga
    (lo importó una versión anterior de esta app)."""
    for nombre in _MODULOS_CEN:
        m = sys.modules.get(nombre)
        if m is None or not getattr(m, "__file__", None):
            continue
        try:
            modificado = os.path.getmtime(m.__file__)
        except OSError:
            continue
        if modificado > getattr(m, "_cargado_en", 0):
            importlib.reload(m)
            m._cargado_en = time.time()


_recargar_modulos_modificados()

from cen import endpoints as E  # noqa: E402
from cen import transform as T  # noqa: E402
from cen import charts as CH  # noqa: E402
from cen.cache import SinCache, modo_solo_cache  # noqa: E402
from cen.client import revisar_clave  # noqa: E402
from cen import guia as G  # noqa: E402
from cen import tablas as TB  # noqa: E402

for _nombre in _MODULOS_CEN:  # marca de carga de los módulos recién importados (ver arriba)
    if _nombre in sys.modules and not hasattr(sys.modules[_nombre], "_cargado_en"):
        sys.modules[_nombre]._cargado_en = time.time()

modo_solo_cache(False)  # cada ejecución parte consultando normalmente (ver precarga más abajo)

from streamlit_echarts import st_echarts  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# ---- claves de la API: si faltan o tienen mal formato, se explica aquí en vez de fallar con 403 en cada consulta
_problema_sip = revisar_clave("sip")
if _problema_sip:
    st.error(f"**No se puede consultar la API del Coordinador.** {_problema_sip}")
    st.info("Corrígela en *Manage app → Settings → Secrets* (en local, en el archivo `.env`) y reinicia la app "
            "con *Manage app → Reboot app*.")
    st.stop()
_problema_op = revisar_clave("operacion")
# un solo contenedor al inicio de la página para avisar de claves rechazadas, sin repetir el error en cada bloque
AVISO_AUTH = st.container()
_auth_mostrado = False
if _problema_op:
    AVISO_AUTH.warning(f"{_problema_op} Las secciones que usan el servicio Operación no funcionarán "
                       "(reduccion, servicios complementarios, reporte de generación).")

# ECharts se dibuja con tamaño 0 si nace en una pestaña o expander oculto y no se redibuja solo al
# mostrarse. Este script observa los contenedores de gráficos y, cuando cambian de tamaño, emite un
# evento "resize" en la página (al que ECharts sí responde).
import streamlit.components.v1 as components  # noqa: E402

components.html("""
<script>
(function () {
  const w = window.parent, doc = w.document;
  if (w.__cenResizeFix) return;
  w.__cenResizeFix = true;
  let t = null;
  const avisar = () => { clearTimeout(t); t = setTimeout(() => w.dispatchEvent(new Event('resize')), 60); };
  const ro = new w.ResizeObserver(avisar);
  const vistos = new WeakSet();
  const escanear = () => doc.querySelectorAll('.echarts-container').forEach(el => {
    if (!vistos.has(el)) { vistos.add(el); ro.observe(el); }
  });
  new w.MutationObserver(escanear).observe(doc.body, {childList: true, subtree: true});
  escanear();
})();
</script>
""", height=0)

# Recorrido guiado: assets/recorrido.js se inserta en la página principal (no en el iframe del componente)
# y se inicia cada vez que st.session_state["tour_n"] aumenta (botón «Recorrido guiado» o aviso de bienvenida).
_MOTOR_TOUR = (Path(__file__).parent / "assets" / "recorrido.js").read_text(encoding="utf-8")
_HTML_TOUR = """<script>
(function () {
  var w = window.parent, d = w.document;
  if (!w.cenTour || w.cenTour.version !== 5) {
    var s = d.createElement("script");
    s.id = "cen-tour-js";
    s.textContent = __MOTOR__;
    d.head.appendChild(s);
  }
  if (!w.cenTour) return;
  w.cenTour.configurar(__PASOS__);
  var n = __N__;
  if (n > 0 && w.__cenTourN !== n) { w.__cenTourN = n; w.cenTour.iniciar(); }
})();
</script>"""


def recorrido_guiado() -> None:
    import json as _json
    html_tour = (_HTML_TOUR.replace("__MOTOR__", _json.dumps(_MOTOR_TOUR).replace("</", "<\\/"))
                 .replace("__PASOS__", G.pasos_json())
                 .replace("__N__", str(int(st.session_state.get("tour_n", 0)))))
    components.html(html_tour, height=0)


def abrir_guia() -> None:
    """Inicia el recorrido guiado (sobre el dashboard) y oculta el aviso de bienvenida."""
    st.session_state["tour_n"] = st.session_state.get("tour_n", 0) + 1
    st.session_state["guia_aviso"] = False


def cerrar_aviso_guia() -> None:
    st.session_state["guia_aviso"] = False


recorrido_guiado()

AUTOREFRESH_MS = 15 * 60 * 1000
# Despliegue público: oculta "Forzar actualización" y limita las barras por consulta, para que los
# visitantes no agoten el límite de consultas de la API (todos comparten las mismas claves).
MODO_PUBLICO = os.getenv("CEN_MODO_PUBLICO", "").strip().lower() in ("1", "true", "si", "sí", "yes")
MAX_BARRAS = 6 if MODO_PUBLICO else 10
HOY = date.today()
FECHA_MIN = date(2026, 1, 1)  # ajustado a lo que la API entrega (ver README)

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=AUTOREFRESH_MS, key="autorefresh")
except ImportError:  # pragma: no cover
    pass

# Descargas en segundo plano aún en curso (si hay, la página se refresca cada 15 s)
PENDIENTES: list[str] = []

# Estado de frescura de cada fuente: nombre -> (fetched_at epoch, último dato, nota)
FRESCURA: dict[str, tuple[float | None, object, str]] = {}


def registrar(nombre: str, fetched_at: float | None, ultimo_dato=None, nota: str = "") -> None:
    FRESCURA[nombre] = (fetched_at, ultimo_dato, nota)


def avisar_auth(detalle: str) -> None:
    """Avisa UNA vez por ejecución que la API rechazó la clave (403), con la explicación, arriba de la página."""
    global _auth_mostrado
    if _auth_mostrado:
        return
    _auth_mostrado = True
    AVISO_AUTH.error(
        f"**La API rechazó la clave (403).** {detalle}. Revisa que el valor de `CEN_USER_KEY` (y de "
        "`CEN_OPERACION_KEY`) en los Secrets sea el de su servicio —son claves distintas— y que se copió "
        "completo; luego haz *Reboot app*. Si el largo es 32 y el error persiste, la clave puede estar "
        "desactivada en el portal del Coordinador.")


def safe(nombre: str, fn, *args, opcional: bool = False, **kwargs):
    """Ejecuta una consulta; si falla, muestra aviso y devuelve None."""
    try:
        r = fn(*args, **kwargs)
        if getattr(r, "stale", False):
            st.warning(f"{nombre}: la API falló; se muestra la última copia guardada.")
        return r
    except SinCache:  # se está descargando en segundo plano (día pasado): se muestra al estar lista
        return None
    except Exception as exc:
        if "Autenticación rechazada" in str(exc):
            avisar_auth(str(exc))
            logging.error("%s: %s", nombre, exc)
            return None
        (st.info if opcional else st.error)(f"{nombre}: no disponible por ahora ({exc})")
        logging.exception(nombre)
        return None


def fmt_ts(ts) -> str:
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        return "—"
    return pd.Timestamp(ts).strftime("%d-%m %H:%M")


def atraso(ts) -> str:
    if ts is None:
        return "—"
    mins = (pd.Timestamp(datetime.now()) - pd.Timestamp(ts)).total_seconds() / 60
    if mins < 0:
        return "proyección"
    return f"{mins/60:.1f} h" if mins >= 90 else f"{mins:.0f} min"


# ============================================================== sidebar
force = False
with st.sidebar:
    st.title("Dashboard SEN")
    if st.session_state.get("fecha") is None:
        st.session_state["fecha"] = HOY

    def volver_a_hoy():
        st.session_state["fecha"] = HOY

    cf1, cf2 = st.columns([3, 1.3], vertical_alignment="bottom")
    DIA = cf1.date_input("Fecha", min_value=FECHA_MIN, max_value=HOY, format="DD-MM-YYYY", key="fecha",
                         help="Día a mostrar. Los días pasados quedan guardados: solo la primera vista "
                              "de cada día consulta la API (puede tardar 1–3 min por el límite de consultas).")
    cf2.button("Hoy", on_click=volver_a_hoy, disabled=DIA == HOY, width="stretch",
               help="Volver al día de hoy")
    st.button("Recorrido guiado", on_click=abrir_guia, width="stretch",
              help="Recorre cada parte del dashboard: qué muestra, cómo usarla y los límites de los datos.")
    if not MODO_PUBLICO and st.button(
            "Forzar actualización", help="Ignora la caché (respeta el límite de consultas: úsalo con moderación)"):
        force = True

    cat_r = safe("Catálogo de barras", E.catalogo_barras)
    catalogo = cat_r.value if cat_r else T.catalogo_barras([])
    opciones = catalogo["barra_transf"].tolist()
    etiquetas = dict(zip(catalogo["barra_transf"], catalogo["barra_info"]))
    defecto = T.barras_defecto(catalogo)[:MAX_BARRAS]

    barras = st.multiselect(
        f"Barras (máx. {MAX_BARRAS})",
        options=opciones,
        default=defecto,
        format_func=lambda b: f"{etiquetas.get(b, b)}  ·  {b}",
        max_selections=MAX_BARRAS,
        help="Buscar por nombre de subestación. Cada barra es una consulta a la API.",
    )
    moneda = st.radio("Moneda CMg", ["USD/MWh", "CLP/kWh"], horizontal=True)
    col_cmg = "usd_mwh" if moneda == "USD/MWh" else "clp_kwh"
    umbral_cero = st.number_input(
        "Umbral CMg ≈ 0 (USD/MWh)", min_value=0.0, max_value=20.0, value=T.UMBRAL_CMG_CERO, step=0.5,
        help="Bajo este valor el CMg se considera ~0 (exceso de energía renovable). Se usa en la pestaña "
             "Baterías y en los indicadores.")
    mostrar_pcp = st.checkbox("Superponer CMg programado", value=True,
                              help="PCP (discontinua) — hoy: el programa de mañana; días pasados: lo que se "
                                   "programó para ese día. PID (punteada, solo hoy): la reprogramación intradiaria.")
    st.caption(f"{len(catalogo)} barras en catálogo · autorefresco cada 15 min")

# ============================================================== día elegido
ES_HOY = DIA == HOY
DIA_ANT = DIA - timedelta(days=1)
DIA_SIG = DIA + timedelta(days=1)
PCP_DIA = DIA_SIG if ES_HOY else DIA  # hoy: programa de mañana; pasado: lo programado para ese día

# ============================================================== precarga de días pasados
# La primera vez que se abre un día pasado sus datos se descargan en segundo plano (varios minutos por
# el límite de la API). Mientras tanto la página no consulta la API: muestra lo que ya está guardado y
# se actualiza sola cada 15 s hasta completar.
CARGANDO_DIA = False
E.marcar_dia_activo(DIA)  # las consultas de este día pasan antes que las de días que ya no se miran
if not ES_HOY:
    precarga = E.precargar_dia(DIA, barras)
    if precarga.activo:
        CARGANDO_DIA = True
        modo_solo_cache(True)
        PENDIENTES.append(f"datos del {DIA:%d-%m}")
        st.progress(precarga.hechos / precarga.total,
                    text=f"Descargando datos del {DIA:%d-%m-%Y} en segundo plano: {precarga.hechos} de "
                         f"{precarga.total} fuentes listas (ahora: {precarga.actual or '…'}). "
                         "La página se actualiza sola; puedes cambiar de pestaña o de día sin perder lo descargado.")
    elif precarga.errores:
        st.warning(f"Algunos datos del {DIA:%d-%m} no se pudieron descargar (se reintentará en unos minutos): "
                   + "; ".join(precarga.errores))


def desde_bg(nombre: str, resultado) -> pd.DataFrame | None:
    """Muestra el estado de una fuente descargada en segundo plano y devuelve sus datos (o None)."""
    r, estado = resultado
    if estado == "cargando":
        PENDIENTES.append(nombre)
        st.caption(f"Descargando {nombre} en segundo plano…")
    elif estado.startswith("error"):
        st.caption(f"{nombre.capitalize()}: no disponible por ahora ({estado[7:]}).")
    return r.value if r is not None else None


def tabla(df: pd.DataFrame, cols: list, alto: int | None = None, tour: str | None = None, donde=None) -> None:
    """Tabla con estilo (cen/tablas.py). ``tour``: contenedor ``tour_<tour>`` que el recorrido enmarca.
    ``donde``: contenedor/columna de Streamlit donde dibujarla (por defecto, el actual)."""
    destino = donde if donde is not None else st
    html_t = TB.tabla_html(df, cols, alto=alto)
    if tour:
        destino.container(key=f"tour_{tour}").markdown(html_t, unsafe_allow_html=True)
    else:
        destino.markdown(html_t, unsafe_allow_html=True)


st.markdown(TB.CSS, unsafe_allow_html=True)
Col = TB.Col


def resumen_cmg_tabla(df: pd.DataFrame) -> pd.DataFrame:
    """Mínimo, máximo, promedio y último CMg por barra, con nombres cortos y el rango del día."""
    r = T.resumen_cmg(df, col_cmg)
    if not r.empty:
        r["barra"] = r["barra"].map(T.nombre_corto)
        r["rango"] = r["máx"] - r["mín"]
    return r


def cols_resumen_cmg() -> list:
    dec = 2 if moneda == "USD/MWh" else 3
    return [Col("barra", "Barra"),
            Col("mín", "Mínimo", "num", dec=dec, unidad=moneda), Col("máx", "Máximo", "num", dec=dec, unidad=moneda),
            Col("promedio", "Promedio", "barra", dec=dec, unidad=moneda),
            Col("rango", "Máx − mín", "barra", dec=dec, unidad=moneda, color_barra="#F28E5C"),
            Col("último", "Último", "num", dec=dec, unidad=moneda)]


def grafico(opciones: dict, height: str, key: str, tour: str | None = None) -> None:
    """st_echarts; con ``tour``, dentro de un contenedor ``tour_<tour>`` que el recorrido guiado enmarca."""
    if tour:
        with st.container(key=f"tour_{tour}"):
            st_echarts(opciones, height=height, key=key)
    else:
        st_echarts(opciones, height=height, key=key)


def aviso_sin_datos(texto: str) -> None:
    st.info(f"Descargando datos del {DIA:%d-%m}…" if CARGANDO_DIA else texto)


# ============================================================== carga de datos
with st.spinner(f"Consultando generación real del {DIA:%d-%m}…"):
    gen_hoy_r = safe("Generación real", E.gen_real, DIA, force=force)
gen_hoy = gen_hoy_r.value if gen_hoy_r else T.gen_df([])
ult_gen = T.ultima_hora_completa(gen_hoy)
registrar("Generación real", gen_hoy_r.fetched_at if gen_hoy_r else None, ult_gen)

with st.spinner("Consultando demanda…"):
    dem_r = safe("Demanda neta / gen. bruta", E.demanda_neta, DIA_ANT, DIA, force=force)
dem = dem_r.value if dem_r else T.demanda_df([])
# las últimas horas oficiales suelen venir a medio cargar: se recortan comparando con la generación real
_gen_tot_completa = T.gen_total_horaria(gen_hoy)
if ult_gen is not None:  # solo horas de generación completas (las últimas también llegan a medio cargar)
    _gen_tot_completa = _gen_tot_completa[_gen_tot_completa["ts"] <= ult_gen]
dem_valida = T.recortar_horas_parciales(dem, _gen_tot_completa) if not dem.empty else dem
registrar("Demanda (gen. bruta)", dem_r.fetched_at if dem_r else None,
          dem_valida["ts"].max() if not dem_valida.empty else None)

cmg = T.cmg_df([])
if barras:
    # no espera a la API: las barras recién agregadas se descargan en segundo plano y aparecen solas
    cmg, cmg_fetched, cmg_err, cmg_pend = E.cmg_online_multi(barras, DIA_ANT, DIA, force=force)
    if cmg_pend and not CARGANDO_DIA:
        PENDIENTES.append("CMg de " + ", ".join(CH.nombre_serie(b) for b in cmg_pend))
    elif E.cmg_actualizando() and not CARGANDO_DIA:
        PENDIENTES.append("actualizando el CMg en línea")
    for e in cmg_err:
        if "Autenticación rechazada" in e:
            avisar_auth(e)
        else:
            st.error(f"CMg en línea: {e}")
    registrar("CMg en línea", cmg_fetched, cmg["ts"].max() if not cmg.empty else None)

# ============================================================== KPIs
st.title("Sistema Eléctrico Nacional")


# Contenedor FIJO: si el aviso desaparece, los elementos de abajo no se corren de lugar (si se corrieran, las
# pestañas se reiniciarían en el navegador).
_ranura_aviso = st.empty()
if st.session_state.get("guia_aviso", True):
    with _ranura_aviso.container(border=True):
        ta, tb, tc = st.columns([6, 1.6, 1.2], vertical_alignment="center")
        ta.markdown("**¿Primera vez aquí?** Haz un recorrido de un par de minutos: qué hay en cada pestaña, cómo "
                    "usarla y qué límites tienen los datos del Coordinador Eléctrico Nacional.")
        tb.button("Hacer el recorrido", on_click=abrir_guia, type="primary", width="stretch")
        tc.button("Ahora no", on_click=cerrar_aviso_guia, width="stretch")

kpis: list[tuple[str, str, str, str]] = []  # (título, valor, unidad, detalle)
if not cmg.empty:
    ult_cmg = cmg["ts"].max()
    ultima_hora = cmg[cmg["ts"] > ult_cmg - pd.Timedelta(hours=1)]
    kpis.append(("CMg promedio", f"{ultima_hora[col_cmg].mean():,.2f}", moneda,
                 f"última hora, {len(barras)} barra(s) · hasta {fmt_ts(ult_cmg)}"))
else:
    kpis.append(("CMg promedio", "—", moneda, "descargando…" if CARGANDO_DIA and barras else "sin barras seleccionadas"))

if ult_gen is not None:
    tot = gen_hoy.loc[gen_hoy["ts"] == ult_gen, "mw"].sum()
    pr = T.porcentaje_renovable(gen_hoy, ult_gen)
    kpis.append(("Generación", f"{tot:,.0f}", "MW", f"hora {ult_gen:%H:%M}"))
    kpis.append(("Renovable", f"{pr:.1f}" if pr is not None else "—", "%",
                 f"hora {ult_gen:%H:%M} · solar, eólica, hidro, geo"))
else:
    kpis += [("Generación", "—", "MW", ""), ("Renovable", "—", "%", "")]

if not dem_valida.empty:
    u = dem_valida.iloc[-1]
    kpis.append(("Demanda (gen. bruta)", f"{u['gen_bruta_mwh']:,.0f}", "MWh",
                 f"oficial {u['ts']:%d-%m %H:%M}" + (" · ~10 h de atraso" if ES_HOY else "")))
else:
    kpis.append(("Demanda (gen. bruta)", "—", "MWh", ""))

# Indicadores para baterías del día elegido (en USD/MWh, a partir del CMg en línea ya descargado)
cmg_dia = cmg[(cmg["ts"] >= pd.Timestamp(DIA)) & (cmg["ts"] < pd.Timestamp(DIA_SIG))] if not cmg.empty else cmg
sp_dia = T.spread_diario(cmg_dia, "usd_mwh", umbral_cero)
if not sp_dia.empty:
    top_sp = sp_dia.iloc[0]
    hasta_txt = f" · hasta {fmt_ts(cmg_dia['ts'].max())}" if ES_HOY else ""
    kpis.append(("Spread promedio", f"{sp_dia['spread'].mean():,.1f}", "USD/MWh",
                 f"máx − mín del día, {len(sp_dia)} barra(s); mayor: {CH.nombre_serie(top_sp['barra_transf'])} "
                 f"{top_sp['spread']:,.0f}{hasta_txt}"))
    kpis.append(("Horas con CMg ≈ 0", f"{sp_dia['horas_cero'].mean():,.1f}", "h",
                 f"promedio por barra, CMg < {umbral_cero:g} USD/MWh{hasta_txt}"))

# Tarjetas propias en una grilla que se reacomoda (4 → 2 → 1 columnas) para que nada quede cortado
st.markdown(
    """
    <style>
    .kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:4px 0 18px}
    .kpi{border:1px solid rgba(128,128,128,.25);border-radius:10px;padding:12px 14px}
    .kpi .t{font-size:.85rem;opacity:.75}
    .kpi .v{font-size:clamp(1.4rem,2.2vw,2rem);font-weight:600;line-height:1.2;white-space:nowrap}
    .kpi .u{font-size:.9rem;font-weight:400;opacity:.75;margin-left:4px}
    .kpi .d{font-size:.75rem;opacity:.6;margin-top:2px}
    </style>
    """ + '<div class="kpi-grid">' + "".join(
        f'<div class="kpi"><div class="t">{t}</div><div class="v">{v}<span class="u">{un}</span></div>'
        f'<div class="d">{d}</div></div>' for t, v, un, d in kpis) + "</div>",
    unsafe_allow_html=True,
)

# ============================================================== preparación de gráficos
# Se arman una vez y se usan tanto en "Resumen" como en la pestaña de cada sección.

def programa_por_barra(prog_df: pd.DataFrame) -> pd.DataFrame | None:
    """Filtra un programa (PCP o PID, con llave_cmg) a las barras seleccionadas: ts, serie, usd_mwh."""
    mapa = T.mapeo_barras_pcp(catalogo[catalogo["barra_transf"].isin(barras)], prog_df)
    partes = [prog_df[prog_df["llave_cmg"] == mapa[b]][["ts", "usd_mwh"]].assign(serie=CH.nombre_serie(b))
              for b in barras if mapa.get(b)]
    return pd.concat(partes, ignore_index=True) if partes else None


def pid_del_dia(dia, notas: list[str]) -> pd.DataFrame | None:
    """CMg PID de las barras seleccionadas para ``dia`` (en segundo plano), con nota de su programa."""
    pid_r, estado = E.cmg_pid_bg(dia)
    if estado == "cargando":
        PENDIENTES.append("CMg PID")
        notas.append(f"Descargando el CMg intradiario (PID) del {dia:%d-%m} en segundo plano.")
    elif estado.startswith("error"):
        notas.append(f"CMg PID no disponible por ahora ({estado[7:]}).")
    if pid_r is None or pid_r.value.empty:
        return None
    pid = pid_r.value
    registrar("CMg programado PID", pid_r.fetched_at, pid["ts"].max(), "reprogramación")
    sel = programa_por_barra(pid)
    if sel is not None:
        prog_txt = pd.Timestamp(pid["programa"].max()).strftime("%d-%m %H:%M")
        notas.append(f"Línea punteada: CMg PID (reprogramación intradiaria; programa del {prog_txt}, "
                     f"cubre hasta las {pid['ts'].max():%H:%M} del {dia:%d-%m}).")
    return sel


def preparar_cmg() -> tuple[dict | None, list[str], str | None]:
    """(opciones ECharts, notas, mensaje si no hay gráfico)."""
    if not barras and not ES_HOY:
        return None, [], "Selecciona barras en la barra lateral (la vista de las 8 barras principales solo existe para hoy)."
    if not barras:
        r8 = safe("CMg 8 barras", E.cmg_8b, force=force)
        if r8 is None or r8.value.empty:
            return None, [], "Sin datos de CMg."
        registrar("CMg 8 barras", r8.fetched_at, r8.value["ts"].max())
        d8 = r8.value.rename(columns={"barra": "serie"})
        return (CH.opciones_cmg(d8, "usd_mwh", "USD/MWh", separadores=[HOY]),
                ["Sin barras seleccionadas: se muestran las 8 barras principales."], None)

    if cmg.empty:
        return None, [], "Sin datos de CMg para las barras seleccionadas."
    plot = cmg.copy()
    plot["serie"] = plot["barra_transf"].map(CH.nombre_serie)
    prog, notas = None, []
    if mostrar_pcp and moneda == "USD/MWh":
        pcp_r, pcp_estado = E.cmg_pcp_bg(PCP_DIA)
        if pcp_estado == "cargando":
            PENDIENTES.append("CMg programado")
            notas.append(f"Descargando el CMg programado del {PCP_DIA:%d-%m} en segundo plano (~2 min, "
                         "unas 45.000 filas). La línea discontinua aparecerá en el próximo refresco.")
        elif pcp_estado.startswith("error"):
            notas.append(f"CMg programado no disponible por ahora ({pcp_estado[7:]}).")
        if pcp_r is not None and not pcp_r.value.empty:
            pcp = pcp_r.value
            registrar("CMg programado PCP", pcp_r.fetched_at, pcp["ts"].max(), "programa")
            mapa = T.mapeo_barras_pcp(catalogo[catalogo["barra_transf"].isin(barras)], pcp)
            prog = programa_por_barra(pcp)
            if mapa:
                notas.append((f"Línea discontinua: CMg programado (PCP) para mañana {PCP_DIA:%d-%m}, "
                              "último programa publicado.") if ES_HOY else
                             (f"Línea discontinua: CMg que se programó (PCP) para el {PCP_DIA:%d-%m}, "
                              "para comparar con lo ocurrido."))
            sin_mapa = [etiquetas.get(b, b) for b in barras if b not in mapa]
            if sin_mapa:
                notas.append("Sin equivalencia en el programa PCP: " + ", ".join(sin_mapa))
    elif mostrar_pcp:
        notas.append("El CMg programado solo está disponible en USD/MWh.")
    pid = pid_del_dia(DIA, notas) if mostrar_pcp and moneda == "USD/MWh" and ES_HOY else None
    separadores = [DIA] + ([DIA_SIG] if prog is not None and ES_HOY else [])
    return CH.opciones_cmg(plot, col_cmg, moneda, prog, separadores=separadores, pid=pid), notas, None


def preparar_gen() -> dict | None:
    if gen_hoy.empty:
        return None
    agg = T.gen_por_tecnologia(gen_hoy)
    incompleta = (ult_gen, agg["ts"].max()) if ult_gen is not None and ult_gen < agg["ts"].max() else None
    return CH.opciones_gen_tecnologia(agg, T.COLORES_TEC, T.TECNOLOGIAS, incompleta)


comb_dem = pd.DataFrame(columns=["ts", "mwh", "fuente"])


def series_demanda_base() -> list[dict]:
    gen_tot = T.gen_total_horaria(gen_hoy)
    if ult_gen is not None:
        gen_tot = gen_tot[gen_tot["ts"] <= ult_gen]
    comb = T.demanda_combinada(dem, gen_tot)
    global comb_dem
    comb_dem = comb
    series = []
    for dia, color in [(DIA_ANT, "#9AA5B1"), (DIA, "#1F5FA8")]:
        d = comb[comb["ts"].dt.date == dia] if not comb.empty else comb
        if d.empty:
            continue
        of = d["fuente"] == "oficial"
        if of.any():
            series.append({"id": f"of-{dia}", "name": f"{dia:%d-%m} oficial", "color": color,
                           "data": CH.serie_horaria(d.loc[of, "ts"], d.loc[of, "mwh"]), "area": dia == DIA,
                           "ancho": 2.6 if dia == DIA else 2})
        if (~of).any():
            # el tramo estimado parte del último punto oficial para que la curva sea continua
            est = pd.concat([d[of].tail(1), d[~of]])
            series.append({"id": f"est-{dia}", "name": f"{dia:%d-%m} estimada",
                           "color": color, "estilo": "dashed", "data": CH.serie_horaria(est["ts"], est["mwh"])})
    return series


NOTA_DEMANDA = ("Demanda nacional = generación bruta (`gen_bruta_mwh`), con ~10 h de atraso. "
                "Las horas posteriores se completan con la suma de la generación real por central "
                "(~2–3 h de atraso), marcadas como **estimado**.")

# ============================================================== pestañas
PESTANAS = ["Resumen", "Baterías", "Costos marginales", "Generación por tecnología", "Demanda", "Operación"]


def ir_a(pestana: str) -> None:
    st.session_state["pestana"] = pestana


def titulo_enlace(texto: str, pestana: str, key: str) -> None:
    """Título de gráfico que, al hacer clic, abre la pestaña de esa sección."""
    st.button(f"{texto}  →", key=key, type="tertiary", on_click=ir_a, args=(pestana,),
              help=f"Ir a la pestaña «{pestana}»")


# Los botones-título se ven como subtítulos (Streamlit agrega la clase st-key-<key> a cada widget)
st.markdown("""
<style>
[class*="st-key-ir_"] button p { font-size: 1.3rem; font-weight: 600; }
[class*="st-key-ir_"] button:hover p { text-decoration: underline; }
</style>""", unsafe_allow_html=True)

# Pestañas con estado: "Resumen" por defecto; solo se dibuja la pestaña visible
tab_res, tab_bat, tab_cmg, tab_gen, tab_dem, tab_op = st.tabs(PESTANAS, key="pestana", on_change="rerun")

# ============================================================== Pestaña Resumen
if tab_res.open:
    with tab_res:
        titulo_enlace(f"Costos marginales — {DIA_ANT:%d-%m} y {DIA:%d-%m}", "Costos marginales", "ir_cmg")
        opt, notas, msg = preparar_cmg()
        if opt:
            grafico(opt, height="430px", key="res_cmg", tour="res_cmg")
            for n in notas:
                st.caption(n)
        else:
            aviso_sin_datos(msg)

        c1, c2 = st.columns(2, gap="large")
        with c1:
            titulo_enlace(f"Generación por tecnología — {DIA:%d-%m}", "Generación por tecnología", "ir_gen")
            opt = preparar_gen()
            if opt:
                st_echarts(opt, height="420px", key="res_gen")
            else:
                aviso_sin_datos("Sin datos de generación para este día.")
        with c2:
            titulo_enlace(f"Demanda — {DIA_ANT:%d-%m} y {DIA:%d-%m}", "Demanda", "ir_dem")
            sd = series_demanda_base()
            if sd:
                # la demanda real llega con ~10 h de atraso: se agrega el pronóstico del día completo (1 consulta)
                pron = desde_bg("pronóstico de demanda", E.pronostico_demanda_bg(DIA))
                if pron is not None and not pron.empty:
                    sd.append({"id": "pron", "name": f"{DIA:%d-%m} pronóstico", "color": "#E07B39",
                               "estilo": "dashed", "data": CH.serie_horaria(pron["ts"], pron["mw"])})
                st_echarts(CH.opciones_demanda(sd), height="420px", key="res_dem")
                st.caption("Demanda oficial = generación bruta horaria (~10 h de atraso); estimada = suma de la "
                           "generación real; pronóstico = CEN, mediano plazo.")
            else:
                aviso_sin_datos("Sin datos de demanda.")

# ============================================================== Pestaña Baterías
if tab_bat.open:
  with tab_bat:
    if not barras:
        st.info("Selecciona barras en la barra lateral para calcular el spread y las horas con CMg ≈ 0.")
    elif sp_dia.empty:
        aviso_sin_datos("Sin datos de CMg para las barras seleccionadas.")
    else:
        nombres = {b: CH.nombre_serie(b) for b in barras}
        hist, est_hist = E.historial_cmg(barras, DIA)
        if est_hist.activo:
            PENDIENTES.append(f"historial de CMg ({E.DIAS_HISTORIAL} días)")
        sp_hist = T.spread_diario(hist, "usd_mwh", umbral_cero)
        prom = (sp_hist.groupby("barra_transf")[["spread", "horas_cero"]].mean()
                if not sp_hist.empty else pd.DataFrame(columns=["spread", "horas_cero"]))

        # ---- tabla de spread
        st.subheader(f"Spread diario por barra — {DIA:%d-%m-%Y}")
        st.caption("Spread = CMg máximo − CMg mínimo del día: el margen bruto que capturaría una batería que carga "
                   "en la hora más barata y descarga en la más cara (antes de pérdidas y límites de energía). "
                   + (f"Hoy se calcula con los datos hasta las {cmg_dia['ts'].max():%H:%M}." if ES_HOY else ""))
        t_spread = pd.DataFrame({
            "barra": sp_dia["barra_transf"].map(nombres),
            "min": sp_dia["min"], "h_min": pd.to_datetime(sp_dia["ts_min"]).dt.strftime("%H:%M"),
            "max": sp_dia["max"], "h_max": pd.to_datetime(sp_dia["ts_max"]).dt.strftime("%H:%M"),
            "spread": sp_dia["spread"],
            "spread_7d": pd.to_numeric(sp_dia["barra_transf"].map(prom["spread"]), errors="coerce"),
            "cero": sp_dia["horas_cero"],
            "cero_7d": pd.to_numeric(sp_dia["barra_transf"].map(prom["horas_cero"]), errors="coerce"),
        })
        t_spread["dif"] = t_spread["spread"] - t_spread["spread_7d"]
        tabla(t_spread, [
            Col("barra", "Barra"),
            Col("min", "CMg mín", "num", dec=1, unidad="USD/MWh"), Col("h_min", "Hora"),
            Col("max", "CMg máx", "num", dec=1, unidad="USD/MWh"), Col("h_max", "Hora"),
            Col("spread", "Spread", "barra", dec=1, unidad="USD/MWh", color_barra="#F28E5C"),
            Col("spread_7d", "Prom. 7 días", "num", dec=1, unidad="USD/MWh"),
            Col("dif", "vs. 7 días", "delta", dec=1),
            Col("cero", "Horas CMg ≈ 0", "barra", dec=2, unidad="h", color_barra="#5BC0F0"),
            Col("cero_7d", "Prom. 7 días", "num", dec=1, unidad="h"),
        ], tour="bat_spread")
        if est_hist.activo:
            st.progress(est_hist.hechos / max(est_hist.total, 1),
                        text=f"Descargando el historial de {E.DIAS_HISTORIAL} días en segundo plano: "
                             f"{est_hist.hechos} de {est_hist.total} barras listas. Los promedios se completarán solos.")

        # ---- mapa de calor
        st.subheader("Horas con CMg ≈ 0 y generación solar")
        matriz = T.matriz_cmg_cero(cmg_dia, DIA, "usd_mwh", umbral_cero).reindex(barras)
        opt = CH.opciones_mapa_cero(matriz, nombres, T.solar_horaria(gen_hoy, DIA), umbral_cero,
                                    color_solar=T.COLORES_TEC["Solar"])
        alto = opt.pop("_alto")
        grafico(opt, height=f"{alto}px", key="bat_mapa", tour="bat_mapa")
        st.caption(f"Cada celda indica cuántos minutos de esa hora el CMg estuvo bajo {umbral_cero:g} USD/MWh "
                   "(más oscuro = más tiempo). Coinciden con las horas de mayor generación solar: son las horas "
                   "baratas para cargar.")

        # ---- tendencia del spread
        st.subheader(f"Spread diario: {E.DIAS_HISTORIAL} días anteriores y el día elegido")
        sp_todo = pd.concat([sp_hist, sp_dia], ignore_index=True)
        st_echarts(CH.opciones_spread_tendencia(sp_todo, nombres), height="420px", key="bat_tendencia")
        if ES_HOY:
            st.caption("El último punto (hoy) es parcial: el spread puede crecer a medida que avanza el día.")

        # ---- real vs programado (PCP y PID) del día elegido
        st.subheader(f"CMg real vs programado — {DIA:%d-%m-%Y}")
        notas_prog: list[str] = []
        pcp_r, pcp_estado = E.cmg_pcp_bg(DIA)
        if pcp_estado == "cargando":
            PENDIENTES.append("CMg PCP del día")
            notas_prog.append(f"Descargando el CMg PCP del {DIA:%d-%m} en segundo plano (~2 min).")
        pcp_sel = programa_por_barra(pcp_r.value) if pcp_r is not None and not pcp_r.value.empty else None
        pid_sel = pid_del_dia(DIA, notas_prog)
        real = cmg_dia.assign(serie=cmg_dia["barra_transf"].map(CH.nombre_serie))
        grafico(CH.opciones_cmg(real, "usd_mwh", "USD/MWh", pcp_sel, pid=pid_sel), height="460px",
                key="bat_prog", tour="bat_prog")
        st.caption("Línea continua: CMg real (en línea). Discontinua: lo que programó el PCP del día anterior. "
                   "Punteada: la reprogramación intradiaria (PID). La diferencia muestra cuánto se desvió el "
                   "precio de lo esperado.")
        for n in notas_prog:
            st.caption(n)

        # ---- pronóstico solar y eólico (programa PCP)
        st.subheader("Generación solar y eólica programada (pronóstico)")
        if st.checkbox("Cargar el programa de generación solar y eólica (7 días)", key="bat_erv",
                       help="La API no publica el pronóstico ERV; se usa la generación programada en el PCP. "
                            "Es una descarga pesada (~60 consultas, unos minutos) que se hace en segundo plano "
                            "y queda guardada 12 h."):
            erv_r, erv_estado = E.erv_programada_bg(DIA)
            if erv_estado == "cargando":
                PENDIENTES.append("programa solar y eólico")
                st.info("Descargando el programa de generación (unas 300.000 filas) en segundo plano. "
                        "El gráfico aparecerá solo cuando termine.")
            elif erv_estado.startswith("error"):
                st.warning(f"No se pudo descargar el programa de generación ({erv_estado[7:]}).")
            if erv_r is not None and not erv_r.value.empty:
                erv = erv_r.value
                erv = erv[erv["tecnologia"].isin(["Solar", "Eólica"])]
                registrar("Generación ERV programada", erv_r.fetched_at, erv["ts"].max(), "programa")
                real_erv = T.gen_por_tecnologia(gen_hoy)
                if ult_gen is not None:  # las horas posteriores aún no tienen todas las centrales: no se dibujan
                    real_erv = real_erv[real_erv["ts"] <= ult_gen]
                st_echarts(CH.opciones_erv(erv, real_erv, T.COLORES_TEC,
                                           separadores=[DIA, DIA_SIG]), height="460px", key="bat_erv_graf")
                st.caption("Áreas: generación solar y eólica programada por el CEN. Línea discontinua: capacidad "
                           "disponible. Línea oscura: generación real. Cuando lo programado queda bajo lo "
                           "disponible en horas de sol suele haber CMg ≈ 0 (energía que sobra: oportunidad de carga).")
        else:
            st.caption("Desactivado por defecto: la descarga es pesada por el límite de consultas de la API.")

        # ---- instrucciones a sistemas de almacenamiento
        dia_instr = DIA_ANT if ES_HOY else DIA
        st.subheader(f"Instrucciones del CEN a sistemas de almacenamiento — {dia_instr:%d-%m-%Y}")
        ins_r, ins_estado = E.instrucciones_cmg_bg(dia_instr)
        if ins_estado == "cargando":
            PENDIENTES.append("instrucciones operacionales")
            st.info("Descargando las instrucciones operacionales en segundo plano.")
        elif ins_estado.startswith("error"):
            st.warning(f"Instrucciones no disponibles por ahora ({ins_estado[7:]}).")
        if ins_r is not None:
            todas = ins_r.value
            if not todas.empty and "accion" not in todas:  # copia guardada antes de existir la columna
                todas = todas.assign(motivo=todas["motivo"].map(T.limpiar_motivo))
                todas = todas.assign(accion=todas["motivo"].map(T.accion_almacenamiento))
            ins = todas[todas["central"].str.contains(T.RE_ALMACENAMIENTO)] if not todas.empty else todas
            if ins.empty:
                st.info("Sin instrucciones a sistemas de almacenamiento ese día.")
            else:
                c1, c2 = st.container(key="tour_bat_bess_tablas").columns([2, 3])
                por_central = (ins.groupby("central").agg(instrucciones=("ts", "size"),
                                                          despacho_max_mw=("despacho_mw", "max"))
                               .sort_values("instrucciones", ascending=False).reset_index())
                tabla(por_central, [
                    Col("central", "Sistema"),
                    Col("instrucciones", "Instrucciones", "barra", color_barra="#9B6BCF"),
                    Col("despacho_max_mw", "Despacho máx.", "num", dec=1, unidad="MW"),
                ], alto=380, donde=c1)
                detalle = ins.assign(hora=ins["ts"].dt.strftime("%H:%M"),
                                     accion_txt=ins["accion"].fillna(ins["motivo"]))
                tabla(detalle, [
                    Col("hora", "Hora"), Col("central", "Sistema"), Col("consigna", "Consigna"),
                    Col("despacho_mw", "Despacho", "num", dec=1, unidad="MW"),
                    Col("accion_txt", "Acción", "badge", colores=TB.COLORES_ACCION),
                ], alto=380, donde=c2)
                # ¿a qué horas el CEN ordena cargar y descargar? (comparable con el mapa de CMg ≈ 0)
                inicio = ins[ins["accion"].isin(["Comienza carga", "Comienza descarga"])]
                if not inicio.empty:
                    cuenta = (inicio.assign(h=inicio["ts"].dt.hour).groupby(["h", "accion"]).size()
                              .unstack(fill_value=0).reindex(range(24), fill_value=0))
                    st.markdown("**Inicios de carga y descarga por hora**")
                    grafico(CH.opciones_barras_agrupadas(
                        CH.HORAS, {"Comienza carga": list(cuenta.get("Comienza carga", [0] * 24)),
                                   "Comienza descarga": list(cuenta.get("Comienza descarga", [0] * 24))},
                        {"Comienza carga": "#3CB89A", "Comienza descarga": "#F28E5C"}, "Instrucciones",
                        nombre_png="bess_carga_descarga"), height="300px", key="bat_bess_horas", tour="bat_bess")
                st.caption("Cargan en las horas de sol (CMg ≈ 0) y descargan al atardecer, cuando el CMg sube. "
                           f"{len(ins)} instrucciones a {ins['central'].nunique()} sistemas de almacenamiento "
                           f"(de {len(todas)} instrucciones en total). Se publican con ~1 día de atraso"
                           + (": por eso se muestra el día anterior." if ES_HOY else "."))

# ============================================================== Pestaña CMg
if tab_cmg.open:
  with tab_cmg:
    modo = st.radio("Vista", ["online", "real"], horizontal=True, label_visibility="collapsed", key="cmg_modo",
                    format_func=lambda m: (f"En línea ({DIA_ANT:%d-%m} y {DIA:%d-%m})" if m == "online"
                                           else "Histórico (CMg real)"))
    if modo == "online":
        opt, notas, msg = preparar_cmg()
        if not opt:
            aviso_sin_datos(msg)
        else:
            grafico(opt, height="520px", key="cmg_online", tour="cmg_online")
            st.caption("Pasa el cursor sobre una curva (o su nombre en la leyenda) para destacarla; "
                       "clic en la leyenda para ocultarla; arrastra la barra inferior o usa Ctrl + rueda para hacer zoom.")
            for n in notas:
                st.caption(n)
            if barras:
                st.subheader(f"Resumen ({DIA:%d-%m-%Y})")
                del_dia = cmg[(cmg["ts"] >= pd.Timestamp(DIA)) & (cmg["ts"] < pd.Timestamp(DIA_SIG))]
                tabla(resumen_cmg_tabla(del_dia), cols_resumen_cmg(), tour="cmg_resumen")
    else:
        c1, c2, c3 = st.columns([2, 1, 1])
        rango = c1.date_input("Rango", value=(HOY - timedelta(days=37), HOY - timedelta(days=30)),
                              max_value=HOY)
        tipo = c2.selectbox("Tipo", ["DEFINITIVO", "PRELIMINAR"])
        c3.caption("El CMg real se publica con semanas de atraso; para fechas recientes viene vacío.")
        if not barras:
            st.info("Selecciona barras en la barra lateral.")
        elif isinstance(rango, tuple) and len(rango) == 2:
            if (rango[1] - rango[0]).days > 31:
                st.warning("Usa rangos de hasta 31 días para no exceder el límite de consultas.")
            elif st.button("Consultar histórico"):
                dfs = []
                with st.spinner("Consultando CMg real…"):
                    for b in barras:
                        r = safe(f"CMg real {b}", E.cmg_real, b, rango[0], rango[1], tipo)
                        if r is not None:
                            dfs.append(r.value)
                hist = pd.concat(dfs, ignore_index=True) if dfs else T.cmg_df([])
                if hist.empty:
                    st.info("Sin datos para ese rango.")
                else:
                    hist["serie"] = hist["barra_transf"].map(CH.nombre_serie)
                    st_echarts(CH.opciones_cmg(hist, col_cmg, moneda), height="520px", key="cmg_hist")
                    tabla(resumen_cmg_tabla(hist), cols_resumen_cmg())

# ============================================================== Pestaña Generación
if tab_gen.open:
  with tab_gen:
    if gen_hoy.empty:
        aviso_sin_datos("Sin datos de generación para este día.")
    else:
        c1, c2 = st.columns([5, 2])
        with c1:
            st.subheader(f"Generación horaria por tecnología — {DIA:%d-%m-%Y}")
            grafico(preparar_gen(), height="500px", key="gen_tec", tour="gen_tec")
        with c2:
            st.subheader("Mix del día")
            ds_r = safe("Generación acumulada del día", E.daily_sum, DIA, force=force)
            if ds_r is not None:
                ds = T.daily_sum_df(ds_r.value)
                registrar("Mix del día (getDailySum)", ds_r.fetched_at, None, "acumulado del día")
                if not ds.empty:
                    st_echarts(CH.opciones_dona(ds, T.COLORES_TEC), height="460px", key="gen_mix")
                    st.caption(f"Total acumulado del día: {ds['valor'].sum():,.0f} MWh "
                               "(coincide con la suma horaria de la generación real)")

        ref = ult_gen if ult_gen is not None else gen_hoy["ts"].max()

        # ---------------- Top 10 centrales y su aporte
        st.subheader("Top 10 centrales")
        periodo = st.radio("Periodo", [f"Hora {ref:%H:%M}", "Acumulado del día"], horizontal=True,
                           label_visibility="collapsed", key="top_periodo")
        por_dia = periodo.startswith("Acumulado")
        top = T.top_centrales(gen_hoy, None if por_dia else ref, n=10)
        unidad, col_e = ("MWh", "mwh") if por_dia else ("MW", "mw")
        base = gen_hoy if por_dia else gen_hoy[gen_hoy["ts"] == ref]
        total = base["mw"].sum()
        share = top["pct"].sum()
        st.markdown(
            f"Las 10 mayores centrales aportan **{share:.1f} %** de la generación del SEN "
            f"({top[col_e].sum():,.0f} de {total:,.0f} {unidad}"
            + (f", hasta las {gen_hoy['ts'].max():%H:%M})" if por_dia else f", hora {ref:%H:%M})")
        )
        c1, c2 = st.container(), st.container()  # gráfico arriba, tabla abajo (ambos a lo ancho)
        with c1:
            grafico(CH.opciones_top10(top, T.COLORES_TEC, col_e, unidad), height="440px", tour="top10",
                       key=f"top10_{col_e}")
        with c2:
            t_top = top.assign(n=range(1, len(top) + 1))
            tabla(t_top, [
                Col("n", "#", "num"), Col("central", "Central"), Col("propietario", "Empresa (propietario)"),
                Col("tecnologia", "Tecnología", "tec", colores=T.COLORES_TEC),
                Col(col_e, "Generación", "num", dec=0, unidad=unidad),
                Col("pct", "% del total", "barra", dec=1, unidad="%", color_barra="#1F5FA8"),
                Col("pct_acum", "% acumulado", "pct", dec=1),
            ], tour="top10_tabla")
            st.caption("Empresa = propietario informado por el CEN. Los sistemas de almacenamiento (BESS) llegan "
                       "sin propietario; cuando su nombre es «SAE <central>» se muestra el dueño de esa central, "
                       "marcado con *.")

        with st.expander(f"Desglose por subtipo — {ref:%H:%M}"):
            c1 = st.container()
            with c1:
                sub = (gen_hoy[gen_hoy["ts"] == ref].assign(subtipo=lambda d: d["subtipo"].replace("", None).fillna(d["tecnologia"]))
                       .groupby(["tecnologia", "subtipo"], as_index=False)["mw"].sum()
                       .sort_values("mw", ascending=False))
                sub = sub[sub["mw"] > 0]
                st_echarts(CH.opciones_subtipo(sub, T.COLORES_TEC), height="440px", key="gen_subtipo")

        # ---------------- contexto: factor de planta, embalses, acumulados y programado vs real
        st.divider()
        c1, c2 = st.columns(2, gap="large")
        with c1.container(key="tour_factor"):
            st.subheader("Factor de planta del día")
            cap = desde_bg("capacidad instalada", E.capacidad_bg())
            if cap is not None and not cap.empty:
                fp = T.factor_planta(gen_hoy, cap, ult_gen)
                st_echarts(CH.opciones_barras_agrupadas(
                    list(fp["tecnologia"]), {"Factor de planta": list(fp["factor_pct"])},
                    {"Factor de planta": "#1F5FA8"}, "%", nombre_png="factor_planta"), height="300px", key="gen_fp")
                tabla(fp, [
                    Col("tecnologia", "Tecnología", "tec", colores=T.COLORES_TEC),
                    Col("gen_media_mw", "Gen. media", "num", unidad="MW"),
                    Col("capacidad_mw", "Capacidad", "num", unidad="MW"),
                    Col("factor_pct", "Factor de planta", "barra", dec=1, unidad="%", maximo=100,
                        color_barra="#1F5FA8"),
                    Col("horas", "Horas", "num"),
                ])
                g_usada = gen_hoy if ult_gen is None else gen_hoy[gen_hoy["ts"] <= ult_gen]
                h_ini, h_fin = g_usada["ts"].min(), g_usada["ts"].max()
                aviso_sol = (" Aún no hay horas de sol con datos: el factor solar sale ~0 y no es representativo."
                             if h_fin.hour < 9 else "")
                st.caption(f"Calculado con las horas {h_ini:%H:%M}–{h_fin:%H:%M} del {DIA:%d-%m} "
                           f"({g_usada['ts'].nunique()} h).{aviso_sol} Generación media ÷ potencia neta efectiva "
                           "instalada (unidades generadoras del CEN, incluye unidades en revisión). Sin BESS: no "
                           "figuran como unidades generadoras.")
        with c2.container(key="tour_embalses"):
            st.subheader("Embalses")
            emb = desde_bg("cota de embalses", E.embalses_bg())
            if emb is not None and not emb.empty:
                tabla(emb, [
                    Col("embalse", "Embalse"),
                    Col("pct", "Llenado", "barra", dec=0, unidad="%", maximo=100, color_barra="#1F5FA8"),
                    Col("cota", "Cota", "num", dec=1, unidad="msnm"),
                    Col("cota_min", "Mín", "num", dec=1, unidad="msnm"),
                    Col("cota_max", "Máx", "num", dec=1, unidad="msnm"),
                ])
                st.caption(f"Medición del {emb['fecha'].max():%d-%m %H:%M}. Llenado = posición de la cota entre "
                           "el mínimo y el máximo de operación.")

        dia_rep = DIA_ANT if ES_HOY else DIA
        st.subheader(f"Generación acumulada por tecnología — reporte del CEN al {dia_rep:%d-%m-%Y}")
        rep_gen = desde_bg("reporte de generación", E.reporte_generacion_bg(dia_rep))
        if rep_gen is not None and not rep_gen.empty:
            tot = rep_gen[["dia_gwh", "mes_gwh", "anio_gwh"]].sum()
            tabla(rep_gen.assign(pct_anio=rep_gen["anio_gwh"] / tot["anio_gwh"] * 100), [
                Col("tecnologia", "Tecnología", "tec", colores=T.COLORES_TEC),
                Col("dia_gwh", "Día", "num", dec=1, unidad="GWh"),
                Col("mes_gwh", "Mes a la fecha", "num", dec=1, unidad="GWh"),
                Col("anio_gwh", "Año a la fecha", "num", dec=0, unidad="GWh"),
                Col("pct_anio", "Participación en el año", "barra", dec=1, unidad="%", color_barra="#3CB89A"),
            ], tour="reporte")
            st.caption(f"Total del año a la fecha: {tot['anio_gwh']:,.0f} GWh. Fuente: servicio Operación del CEN "
                       "(se publica con ~1 día de atraso).")

        _gp_sec = st.container(key="tour_gen_prog")  # título y casilla (lo que enmarca el recorrido)
        _gp_sec.subheader(f"Programado vs real por tecnología — {DIA:%d-%m-%Y}")
        if _gp_sec.checkbox("Comparar con la generación programada (PCP)", key="gen_prog_chk",
                       help="Usa el programa de generación del CEN: descarga pesada (~60 consultas) en segundo "
                            "plano, guardada 12 h. Es la misma que usa el pronóstico solar/eólico de Baterías."):
            gp = desde_bg("programa de generación", E.erv_programada_bg(DIA))
            if gp is not None and not gp.empty:
                # se renormaliza al leer: copias guardadas antes podían traer "Hidroeléctricas"/"Termoeléctricas"
                gp = (gp.assign(tecnologia=gp["tecnologia"].map(T.normalizar_tecnologia))
                      .groupby(["ts", "tecnologia"], as_index=False)[["mw", "disponible_mw"]].sum())
                real_h = T.gen_por_tecnologia(gen_hoy)
                if ult_gen is not None:
                    real_h = real_h[real_h["ts"] <= ult_gen]
                prog_h = gp[gp["ts"].isin(real_h["ts"])]
                dv = T.desviacion(prog_h[["ts", "tecnologia", "mw"]], real_h, clave="tecnologia")
                if dv.empty:
                    st.info("El programa no cubre las horas con generación real de este día.")
                else:
                    tot = dv.groupby("tecnologia")[["programado", "real", "desv_mw"]].sum()
                    tot["desv_pct"] = (tot["desv_mw"] / tot["programado"].where(tot["programado"] > 0) * 100).astype(float)
                    tot = tot.sort_values("real", ascending=False)
                    st_echarts(CH.opciones_barras_agrupadas(
                        list(tot.index), {"Programado": list(tot["programado"]), "Real": list(tot["real"])},
                        {"Programado": "#9AA5B1", "Real": "#1F5FA8"}, "MWh", nombre_png="programado_vs_real"),
                        height="340px", key="gen_prog_real")
                    # sin programa (0 MWh) el % no aplica: la celda muestra «—»
                    tabla(tot.reset_index(), [
                        Col("tecnologia", "Tecnología", "tec", colores=T.COLORES_TEC),
                        Col("programado", "Programado", "num", unidad="MWh"),
                        Col("real", "Real", "num", unidad="MWh"),
                        Col("desv_mw", "Desviación (MWh)", "delta"),
                        Col("desv_pct", "Desviación (%)", "delta", dec=1),
                    ])
                    st.caption(f"Suma de las {dv['ts'].nunique()} horas con generación real"
                               + (f" (hasta las {ult_gen:%H:%M})" if ES_HOY and ult_gen is not None else "")
                               + ". Desviación = real − programado.")

# ============================================================== Pestaña Demanda
if tab_dem.open:
  with tab_dem:
    series_dem = series_demanda_base()
    if not series_dem:
        aviso_sin_datos("Sin datos de demanda.")
    else:
        if st.checkbox("Mostrar demanda neta (referencia)"):
            for dia, color in [(DIA_ANT, "#C9B37E"), (DIA, "#B07D12")]:
                d = dem[(dem["ts"].dt.date == dia)].dropna(subset=["demanda_neta_mwh"])
                series_dem.append({"id": f"neta-{dia}", "name": f"{dia:%d-%m} demanda neta", "color": color,
                                   "estilo": "dotted", "ancho": 1.8,
                                   "data": CH.serie_horaria(d["ts"], d["demanda_neta_mwh"])})
            st.caption("Demanda neta = gen. bruta − ERV − consumo propio: descuenta solar, eólica y pasada, "
                       "por lo que **no** es la demanda nacional.")
        if st.checkbox("Mostrar demanda programada de mañana (PCP)" if ES_HOY
                       else f"Mostrar demanda programada para el {DIA:%d-%m} (PCP)"):
            dp_r, dp_estado = E.demanda_prog_bg(PCP_DIA)
            if dp_estado == "cargando":
                PENDIENTES.append("demanda programada")
                st.caption("Descargando la demanda programada de mañana en segundo plano (~2 min); "
                           "aparecerá en el próximo refresco.")
            elif dp_estado.startswith("error"):
                st.caption(f"Demanda programada no disponible por ahora ({dp_estado[7:]}).")
            if dp_r is not None and not dp_r.value.empty:
                dp = dp_r.value
                registrar("Demanda programada PCP", dp_r.fetched_at, dp["ts"].max(), "proyección de mañana")
                series_dem.append({"id": "pcp", "name": f"{PCP_DIA:%d-%m} programada (PCP)", "color": "#2E8B57",
                                   "estilo": "dotted", "data": CH.serie_horaria(dp["ts"], dp["mw"])})

        if st.checkbox(f"Mostrar demanda programada intradiaria (PID) del {DIA:%d-%m}"):
            dpid = desde_bg("demanda PID", E.demanda_pid_bg(DIA))
            if dpid is not None and not dpid.empty:
                series_dem.append({"id": "pid", "name": f"{DIA:%d-%m} programada (PID)", "color": "#7E57C2",
                                   "estilo": "dotted", "data": CH.serie_horaria(dpid["ts"], dpid["mw"])})
        if st.checkbox(f"Mostrar pronóstico de demanda (mediano plazo) del {DIA:%d-%m}", value=True):
            pron = desde_bg("pronóstico de demanda", E.pronostico_demanda_bg(DIA))
            if pron is not None and not pron.empty:
                series_dem.append({"id": "pron", "name": f"{DIA:%d-%m} pronóstico",
                                   "color": "#E07B39", "estilo": "dashed",
                                   "data": CH.serie_horaria(pron["ts"], pron["mw"])})

        grafico(CH.opciones_demanda(series_dem), height="500px", key="demanda", tour="demanda")
        st.caption(NOTA_DEMANDA)

        _dv_sec = st.container(key="tour_dem_desv")  # título, programa y casilla (lo que enmarca el recorrido)
        _dv_sec.subheader(f"Desviación programado vs real — {DIA:%d-%m-%Y}")
        fuente_prog = _dv_sec.radio("Programa", ["PCP (día anterior)", "PID (intradiario)"], horizontal=True,
                                    key="dem_desv_fuente", label_visibility="collapsed")
        if _dv_sec.checkbox("Calcular desviación", key="dem_desv_chk",
                       help="Compara la demanda real (generación bruta oficial, completada con la estimación) con "
                            "la demanda programada por el CEN para el mismo día."):
            prog = desde_bg("demanda programada", E.demanda_prog_bg(DIA) if fuente_prog.startswith("PCP")
                            else E.demanda_pid_bg(DIA))
            real_d = comb_dem[comb_dem["ts"].dt.date == DIA][["ts", "mwh"]].rename(columns={"mwh": "mw"})
            if prog is not None and not prog.empty and not real_d.empty:
                dv = T.desviacion(prog[["ts", "mw"]], real_d)
                if dv.empty:
                    st.info("El programa no cubre las horas con demanda real de este día.")
                else:
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Desviación media", f"{dv['desv_mw'].mean():+,.0f} MW")
                    m2.metric("Error absoluto medio", f"{dv['desv_mw'].abs().mean():,.0f} MW",
                              f"{dv['desv_pct'].abs().mean():.1f} %", delta_color="off")
                    peor = dv.loc[dv["desv_mw"].abs().idxmax()]
                    m3.metric("Mayor desviación", f"{peor['desv_mw']:+,.0f} MW", f"a las {peor['ts']:%H:%M}",
                              delta_color="off")
                    tabla(dv.assign(hora=dv["ts"].dt.strftime("%H:%M")), [
                        Col("hora", "Hora"),
                        Col("programado", "Programado", "num", unidad="MW"),
                        Col("real", "Real", "num", unidad="MWh"),
                        Col("desv_mw", "Desviación (MW)", "delta"),
                        Col("desv_pct", "Desviación (%)", "delta", dec=1),
                    ], alto=320)
                    st.caption("Real = generación bruta horaria (incluye pérdidas y consumos propios), por lo que "
                               "suele quedar algo sobre la demanda programada por barra.")

# ============================================================== Pestaña Operación
if tab_op.open:
  with tab_op:
    st.subheader(f"Servicios complementarios activados — {DIA:%d-%m-%Y}")
    sc = desde_bg("servicios complementarios", E.sscc_real_bg(DIA))
    if sc is not None:
        if sc.empty:
            st.info("Sin activaciones registradas ese día.")
        else:
            resumen_sc = (sc.groupby("servicio").agg(activaciones=("inicio", "size"), baja_mw=("baja_mw", "sum"),
                                                     sube_mw=("sube_mw", "sum"), unidades=("unidad", "nunique"))
                          .sort_values("activaciones", ascending=False).reset_index())
            # servicio «(+)» sube la generación (verde) y «(-)» la baja (rojo)
            col_serv = {s: (TB.VERDE if "+" in str(s) else TB.ROJO if "-" in str(s) else TB.GRIS)
                        for s in sc["servicio"].dropna().unique()}
            c1, c2 = st.container(key="tour_op_sscc").columns([2, 3])
            tabla(resumen_sc, [
                Col("servicio", "Servicio", "badge", colores=col_serv),
                Col("activaciones", "Activaciones", "barra", color_barra="#9B6BCF"),
                Col("baja_mw", "Baja", "num", dec=1, unidad="MW"), Col("sube_mw", "Sube", "num", dec=1, unidad="MW"),
                Col("unidades", "Unidades", "num"),
            ], alto=380, donde=c1)
            tabla(sc.assign(hora=sc["inicio"].dt.strftime("%H:%M") + "–" + sc["fin"].dt.strftime("%H:%M")), [
                Col("hora", "Hora"), Col("servicio", "Servicio", "badge", colores=col_serv), Col("unidad", "Unidad"),
                Col("baja_mw", "Baja", "num", dec=1, unidad="MW"), Col("sube_mw", "Sube", "num", dec=1, unidad="MW"),
                Col("motivo", "Motivo", "largo"),
            ], alto=380, donde=c2)
            st.caption(f"{len(sc)} activaciones reales (control de frecuencia CPF/CSF/CTF y otros). "
                       "Fuente: servicio Operación del CEN (OpReal).")

    st.subheader(f"Mantenimientos mayores vigentes — {DIA:%d-%m-%Y}")
    mt = desde_bg("mantenimientos mayores", E.mantenimientos_bg(DIA))
    if mt is not None:
        act = T.activos_en(mt, DIA)
        if act.empty:
            st.info("Sin mantenimientos mayores vigentes ese día.")
        else:
            tabla(act.assign(periodo=act["inicio"].dt.strftime("%d-%m") + " → " + act["fin"].dt.strftime("%d-%m"),
                             inst=act["instalacion"].fillna("") + " · " + act["elemento"].fillna("")), [
                Col("periodo", "Periodo", ancho="9%"), Col("inst", "Instalación / elemento", ancho="20%"),
                Col("estado", "Estado", "badge", colores=TB.COLORES_ESTADO),
                Col("riesgo", "Riesgo", "badge", colores=TB.COLORES_RIESGO),
                Col("consumos", "Consumos", ancho="12%"), Col("descripcion", "Trabajo", "largo", ancho="40%"),
            ], alto=520, tour="op_mant")
            st.caption(f"{len(act)} programas de mantenimiento mayor que abarcan el día (solicitados en los 60 días "
                       "previos).")

    st.subheader(f"Trabajos y desconexiones programados — {DIA:%d-%m-%Y}")
    so = desde_bg("solicitudes de trabajo", E.solicitudes_bg(DIA))
    if so is not None:
        act = T.activos_en(so, DIA)
        act = act[~act["estado"].isin(["anulado", "borrador", "rechazado"])] if not act.empty else act
        if act.empty:
            st.info("Sin solicitudes de trabajo que abarquen ese día.")
        else:
            _trab = st.container(key="tour_op_trab")
            resumen_tr = (act.assign(elemento=act["elemento"].fillna("").str.replace("_", " "))
                          .groupby(["tipo", "elemento"]).size().rename("n").reset_index()
                          .sort_values("n", ascending=False))
            c1, _ = _trab.columns([2, 3])
            tabla(resumen_tr, [Col("tipo", "Tipo"), Col("elemento", "Elemento"),
                               Col("n", "Solicitudes", "barra", color_barra="#F5B83D")], donde=c1)
            tabla(act.assign(periodo=act["inicio"].dt.strftime("%d-%m %H:%M") + " → " + act["fin"].dt.strftime("%d-%m %H:%M"),
                             trabajo=act["tipo"].fillna("") + " · " + act["elemento"].fillna("").str.replace("_", " "),
                             consumo_txt=act["consumo"].fillna("").str.replace("_", " ")), [
                Col("periodo", "Periodo", ancho="17%"), Col("instalacion", "Instalación", ancho="25%"),
                Col("trabajo", "Trabajo", ancho="16%"), Col("empresa", "Empresa", ancho="20%"),
                Col("estado", "Estado", "badge", colores=TB.COLORES_ESTADO), Col("consumo_txt", "Consumo"),
            ], alto=420, donde=_trab)
            st.caption(f"{len(act)} solicitudes (desconexiones e intervenciones; sin anuladas, borradores ni "
                       "rechazadas) que abarcan el día, creadas en los "
                       "30 días previos.")

# ============================================================== Pie de página
st.divider()
_frescura = st.container(key="tour_frescura")
_frescura.caption("**Frescura de los datos** · Fuente: API SIP del Coordinador Eléctrico Nacional")
def _estado_frescura(ultimo) -> str:
    """Etiqueta según el atraso del último dato (solo cuando se mira hoy)."""
    if ultimo is None:
        return "Sin fecha"
    horas = (pd.Timestamp(datetime.now()) - pd.Timestamp(ultimo)).total_seconds() / 3600
    if horas < 0:
        return "Proyección"
    if not ES_HOY:
        return "Histórico"
    return "Al día" if horas <= 1 else "Con atraso" if horas <= 6 else "Atraso alto"


filas = []
for nombre, (fetched, ultimo, nota) in FRESCURA.items():
    filas.append({
        "fuente": nombre,
        "consultado": datetime.fromtimestamp(fetched).strftime("%d-%m %H:%M") if fetched else "—",
        "ultimo": fmt_ts(ultimo) if ultimo is not None else "—",
        "atraso": atraso(ultimo) if ultimo is not None else (nota or "—"),
        "estado": _estado_frescura(ultimo),
    })
if filas:
    tabla(pd.DataFrame(filas), [
        Col("fuente", "Fuente"), Col("consultado", "Consultado"), Col("ultimo", "Último dato"),
        Col("atraso", "Atraso"),
        Col("estado", "Estado", "badge", colores={"Al día": TB.VERDE, "Con atraso": TB.AMBAR,
                                                  "Atraso alto": TB.ROJO, "Proyección": TB.AZUL}),
    ], donde=_frescura)
from cen.cache import refrescando  # noqa: E402

if refrescando():
    PENDIENTES.append(f"actualizando {len(refrescando())} fuente(s); se muestran los datos anteriores")
if PENDIENTES:
    try:
        st_autorefresh(interval=15_000, key="bg_refresh")  # cada rerun es liviano: no espera a la API
    except NameError:  # pragma: no cover
        pass
    st.caption("En segundo plano: " + ", ".join(PENDIENTES) + " (la página se actualizará sola).")
st.caption(f"Página generada {datetime.now():%d-%m-%Y %H:%M:%S}")

modo_solo_cache(False)
