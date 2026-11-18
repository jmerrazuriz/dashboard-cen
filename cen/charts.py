"""Gráficos ECharts del dashboard, todos con el mismo estilo (inspirado en el gráfico de CMg del CEN).

- Curvas suavizadas con relleno degradado; leyenda inferior con íconos circulares.
- Al pasar el cursor por una serie (o su ítem en la leyenda) esa serie se destaca y las demás se opacan.
- Tooltip blanco con sombra, barra de zoom inferior en los gráficos de tiempo y botones para zoom/PNG.
"""
from __future__ import annotations

import re
from datetime import date

import pandas as pd

try:
    from streamlit_echarts import JsCode
except Exception:  # fuera de `streamlit run` (p. ej. pytest) el componente no se puede registrar
    class JsCode:  # type: ignore[no-redef]
        def __init__(self, js_code: str):
            self.js_code = js_code


PALETA = ["#F28E5C", "#F5B83D", "#3F5BA9", "#3CB89A", "#9B6BCF",
          "#2E6E73", "#E98CC0", "#5BC0F0", "#B5523B", "#7A8B99"]
GRIS = "#9AA0A6"


# =================================================================== helpers
def nombre_serie(barra_transf: str) -> str:
    """'TARAPACA______220' -> 'TARAPACA 220' (corto, único y legible)."""
    return re.sub(r"_+", " ", str(barra_transf)).strip()


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _degradado(c: str, arriba: float = 0.22, abajo: float = 0.0) -> dict:
    return {"type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
            "colorStops": [{"offset": 0, "color": _rgba(c, arriba)}, {"offset": 1, "color": _rgba(c, abajo)}]}


def _num(v, dec: int = 2):
    return None if v is None or pd.isna(v) else round(float(v), dec)


def _puntos(ts: pd.Series, val: pd.Series, dec: int = 2) -> list[list]:
    return [[t.strftime("%Y-%m-%dT%H:%M:%S"), _num(v, dec)] for t, v in zip(ts, val)]


# Destacar la serie bajo el cursor y opacar el resto
DESTACAR = {
    "emphasis": {"focus": "series", "lineStyle": {"width": 3.5}},
    "blur": {"lineStyle": {"opacity": 0.12}, "areaStyle": {"opacity": 0.03}, "itemStyle": {"opacity": 0.12},
             "label": {"opacity": 0.15}},
}
LINEA = {"type": "line", "smooth": 0.35, "showSymbol": False, "symbol": "circle", "symbolSize": 7,
         "triggerLineEvent": True, **DESTACAR}

TOOLTIP_ESTILO = {
    "confine": True, "backgroundColor": "rgba(255,255,255,0.97)", "borderColor": "#E5E7EB",
    "textStyle": {"color": "#1F2937", "fontSize": 12},
    "extraCssText": "box-shadow:0 4px 14px rgba(0,0,0,.12);border-radius:8px;padding:10px 12px;",
}


def _tooltip_eje(unidad: str, cabecera: str = "fecha_hora", decimales: int = 2, total: bool = False,
                 sufijos: dict[str, str] | None = None) -> dict:
    """Tooltip de eje: cabecera (fecha y hora, u "Hora HH:00") y una fila por serie con su valor.

    ``sufijos``: prefijo de id de serie -> texto tenue tras el nombre (p. ej. {'pcp-': '(prog.)'}).
    """
    sufijos_js = "{" + ",".join(f"'{k}':'{v}'" for k, v in (sufijos or {}).items()) + "}"
    js = """
function (params) {
  if (!params || !params.length) return '';
  const pad = n => String(n).padStart(2, '0');
  const fmt = v => v.toLocaleString('es-CL', {minimumFractionDigits: __DEC__, maximumFractionDigits: __DEC__});
  let cab;
  if ('__CAB__' === 'hora') { cab = 'Hora ' + params[0].axisValueLabel; }
  else if ('__CAB__' === 'categoria') { cab = params[0].axisValueLabel; }
  else { const d = new Date(params[0].axisValue);
         cab = pad(d.getDate()) + '-' + pad(d.getMonth() + 1) + '-' + d.getFullYear() + ', ' + pad(d.getHours()) + ':' + pad(d.getMinutes()); }
  const suf = __SUF__;
  let h = '<div style="font-weight:600;margin-bottom:6px">' + cab + '</div>', tot = 0, n = 0;
  for (const p of params) {
    const v = Array.isArray(p.value) ? p.value[1] : p.value;
    if (v === null || v === undefined || p.seriesName === '') continue;
    let s = '';
    for (const k in suf) { if (String(p.seriesId).indexOf(k) === 0) s = ' <span style="opacity:.55">' + suf[k] + '</span>'; }
    tot += v; n += 1;
    h += '<div style="display:flex;align-items:center;gap:6px;min-width:230px">' + p.marker
       + '<span style="flex:1">' + p.seriesName + s + '</span><b>' + fmt(v) + '</b>'
       + '<span style="opacity:.55;font-size:11px">(__UNIDAD__)</span></div>';
  }
  if (__TOTAL__ && n > 1) h += '<div style="border-top:1px solid #E5E7EB;margin-top:6px;padding-top:4px;display:flex">'
       + '<span style="flex:1">Total</span><b>' + fmt(tot) + '</b><span style="opacity:.55;font-size:11px;margin-left:6px">(__UNIDAD__)</span></div>';
  return h;
}"""
    js = (js.replace("__DEC__", str(decimales)).replace("__CAB__", cabecera).replace("__SUF__", sufijos_js)
            .replace("__UNIDAD__", unidad).replace("__TOTAL__", "true" if total else "false"))
    return {**TOOLTIP_ESTILO, "trigger": "axis",
            "axisPointer": {"type": "line", "lineStyle": {"type": "dashed", "color": GRIS}},
            "formatter": JsCode(js)}


def _leyenda(nombres: list[str]) -> dict:
    # "scroll": una sola línea (flechas si no cabe) para que nunca se monte sobre el eje
    return {"type": "scroll", "data": nombres, "bottom": 4, "icon": "circle", "itemWidth": 11, "itemHeight": 11,
            "itemGap": 18, "textStyle": {"fontSize": 12}}


def _toolbox(nombre_png: str, zoom: bool = True) -> dict:
    f: dict = {}
    if zoom:
        f["dataZoom"] = {"yAxisIndex": "none", "title": {"zoom": "Zoom", "back": "Deshacer zoom"}}
        f["restore"] = {"title": "Restablecer"}
    f["saveAsImage"] = {"title": "Descargar PNG", "name": nombre_png}
    return {"right": 12, "top": 0, "feature": f}


def _eje_tiempo() -> dict:
    # horas dentro del día; en el cambio de día (o en rangos largos) la fecha
    return {"type": "time", "boundaryGap": False,
            "axisLabel": {"formatter": {"year": "{yyyy}", "month": "{MM}-{yyyy}", "day": "{dd}-{MM}",
                                        "hour": "{HH}:{mm}", "minute": "{HH}:{mm}"}, "hideOverlap": True},
            "axisLine": {"lineStyle": {"color": "#CBD5E1"}}, "splitLine": {"show": False}}


def _eje_valor(nombre: str) -> dict:
    return {"type": "value", "name": nombre, "nameLocation": "middle", "nameGap": 52,
            "nameTextStyle": {"fontSize": 12}, "splitLine": {"lineStyle": {"color": "#EEF1F5"}}}


def _zoom_tiempo() -> list[dict]:
    return [
        # zoom con Ctrl + rueda: la rueda sola sigue desplazando la página
        {"type": "inside", "throttle": 50, "zoomOnMouseWheel": "ctrl", "moveOnMouseWheel": False,
         "moveOnMouseMove": True},
        {"type": "slider", "bottom": 36, "height": 22, "borderColor": "#E5E7EB",
         "fillerColor": "rgba(91,192,240,0.15)", "labelFormatter": JsCode(
             "function (v) { const d = new Date(v), p = n => String(n).padStart(2,'0');"
             " return p(d.getDate()) + '-' + p(d.getMonth()+1) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes()); }")},
    ]


def _serie_marcas(separadores: list[date] | None = None, zona_gris: tuple | None = None) -> dict | None:
    """Serie vacía que solo lleva separadores de día y/o una zona sombreada (no se opaca con el resto)."""
    if not separadores and not zona_gris:
        return None
    s: dict = {"type": "line", "id": "marcas", "name": "", "data": [], "silent": True}
    if separadores:
        s["markLine"] = {
            "silent": True, "symbol": "none", "lineStyle": {"type": "dashed", "color": GRIS, "width": 1},
            "label": {"position": "end", "color": "#6B7280", "fontSize": 11},
            "data": [{"xAxis": f"{d:%Y-%m-%d}T00:00:00", "label": {"formatter": f"{d:%d-%m-%Y}"}} for d in separadores],
        }
    if zona_gris:
        desde, hasta, texto = zona_gris
        s["markArea"] = {"silent": True, "itemStyle": {"color": "rgba(148,163,184,0.15)"},
                         "label": {"color": "#6B7280", "fontSize": 11, "position": "insideTop"},
                         "data": [[{"xAxis": f"{desde:%Y-%m-%dT%H:%M:%S}", "name": texto},
                                   {"xAxis": f"{hasta:%Y-%m-%dT%H:%M:%S}"}]]}
    return s


# =================================================================== CMg
def opciones_cmg(
    live: pd.DataFrame,
    col: str,
    unidad: str,
    programado: pd.DataFrame | None = None,
    separadores: list[date] | None = None,
    pid: pd.DataFrame | None = None,
) -> dict:
    """``live``: ts, serie, <col>. ``programado`` (PCP, línea discontinua) y ``pid`` (PID, punteada):
    ts, serie, usd_mwh; ambos con el mismo color que la barra en vivo."""
    programas = [(df, pref, estilo) for df, pref, estilo in ((programado, "pcp", "dashed"), (pid, "pid", "dotted"))
                 if df is not None and not df.empty]
    nombres = list(dict.fromkeys(live["serie"])) if not live.empty else []
    for df, _, _ in programas:
        nombres += [s for s in dict.fromkeys(df["serie"]) if s not in nombres]
    color = {s: PALETA[i % len(PALETA)] for i, s in enumerate(nombres)}

    series: list[dict] = []
    for s in nombres:
        d = live[live["serie"] == s].sort_values("ts") if not live.empty else live
        if d.empty:
            continue
        c = color[s]
        series.append({**LINEA, "id": f"live-{s}", "name": s, "data": _puntos(d["ts"], d[col]),
                       "lineStyle": {"width": 2.2, "color": c}, "itemStyle": {"color": c},
                       "areaStyle": {"color": _degradado(c)}})
    for df, pref, estilo in programas:
        for s in nombres:
            d = df[df["serie"] == s].sort_values("ts")
            if d.empty:
                continue
            c = color[s]
            series.append({**LINEA, "id": f"{pref}-{s}", "name": s, "data": _puntos(d["ts"], d["usd_mwh"]),
                           "lineStyle": {"width": 2, "type": estilo, "color": c}, "itemStyle": {"color": c}})
    m = _serie_marcas(separadores)
    if m:
        m["id"] = "separadores"
        series.append(m)

    return {
        "animationDuration": 400,
        "color": [color[s] for s in nombres],
        "grid": {"left": 64, "right": 24, "top": 44, "bottom": 96},
        "tooltip": _tooltip_eje(unidad, sufijos={"pcp-": "(PCP)", "pid-": "(PID)"}),
        "legend": _leyenda(nombres),
        "toolbox": _toolbox("cmg"),
        "xAxis": _eje_tiempo(),
        "yAxis": _eje_valor(f"CMg ({unidad})"),
        "dataZoom": _zoom_tiempo(),
        "series": series,
    }


# =================================================================== Generación
def opciones_gen_tecnologia(agg: pd.DataFrame, colores: dict[str, str], orden: list[str],
                            incompleta: tuple | None = None) -> dict:
    """Áreas apiladas por tecnología. ``agg``: ts, tecnologia, mw. ``incompleta``: (desde, hasta) sombreado."""
    presentes = [t for t in orden if t in set(agg["tecnologia"])]
    presentes += [t for t in dict.fromkeys(agg["tecnologia"]) if t not in presentes]
    piv = agg.pivot_table(index="ts", columns="tecnologia", values="mw", aggfunc="sum").sort_index()
    series = []
    for t in presentes:
        c = colores.get(t, GRIS)
        series.append({**LINEA, "id": f"tec-{t}", "name": t, "stack": "gen", "smooth": 0.3,
                       "data": _puntos(piv.index.to_series(), piv[t].fillna(0), 1),
                       "lineStyle": {"width": 1.2, "color": c}, "itemStyle": {"color": c},
                       "areaStyle": {"color": _degradado(c, 0.85, 0.45)}})
    m = _serie_marcas(zona_gris=(*incompleta, "hora incompleta") if incompleta else None)
    if m:
        series.append(m)
    return {
        "animationDuration": 400,
        "color": [colores.get(t, GRIS) for t in presentes],
        "grid": {"left": 64, "right": 24, "top": 40, "bottom": 96},
        "tooltip": _tooltip_eje("MW", decimales=0, total=True),
        "legend": _leyenda(presentes),
        "toolbox": _toolbox("generacion"),
        "xAxis": _eje_tiempo(),
        "yAxis": _eje_valor("Generación (MW)"),
        "dataZoom": _zoom_tiempo(),
        "series": series,
    }


def opciones_dona(ds: pd.DataFrame, colores: dict[str, str], unidad: str = "MWh") -> dict:
    """Mix del día. ``ds``: tecnologia, valor."""
    datos = [{"name": t, "value": _num(v, 0), "itemStyle": {"color": colores.get(t, GRIS)}}
             for t, v in zip(ds["tecnologia"], ds["valor"])]
    total = sum(d["value"] or 0 for d in datos)
    pct = {d["name"]: (d["value"] or 0) / total * 100 if total else 0 for d in datos}
    pct_js = "{" + ",".join(f"'{k}':{v:.1f}" for k, v in pct.items()) + "}"
    return {
        "tooltip": {**TOOLTIP_ESTILO, "trigger": "item", "formatter": JsCode(
            "function (p) { return p.marker + ' <b>' + p.name + '</b><br>' + p.value.toLocaleString('es-CL')"
            " + ' " + unidad + "' + '<br><span style=\"opacity:.6\">' + p.percent.toFixed(1) + ' % del día</span>'; }")},
        # leyenda con el % de cada tecnología (siempre legible, aunque la tajada sea angosta)
        "legend": {**_leyenda([d["name"] for d in datos]), "orient": "vertical", "left": "center", "bottom": 0,
                   "itemGap": 7, "textStyle": {"fontSize": 12, "color": "#374151"},
                   "formatter": JsCode("function (n) { const p = " + pct_js + "; return n + '   ' + "
                                       "(p[n] !== undefined ? p[n].toFixed(1).replace('.', ',') + ' %' : ''); }")},
        "toolbox": _toolbox("mix_del_dia", zoom=False),
        # total del día al centro de la dona
        "title": {"text": f"{total / 1000:,.1f}".replace(",", "X").replace(".", ",").replace("X", "."),
                  "subtext": "GWh del día", "left": "center", "top": "30%", "itemGap": 2,
                  "textStyle": {"fontSize": 17, "fontWeight": 700, "color": "#1F2937"},
                  "subtextStyle": {"fontSize": 11, "color": "#6B7280"}},
        "series": [{
            "type": "pie", "radius": ["34%", "52%"], "center": ["50%", "36%"], "avoidLabelOverlap": True,
            "itemStyle": {"borderRadius": 5, "borderColor": "#fff", "borderWidth": 2},
            # % fuera del anillo, en texto oscuro y con línea guía: se lee aunque la tajada sea chica
            "label": {"show": True, "position": "outside", "color": "#1F2937", "fontSize": 12, "fontWeight": 600,
                      "formatter": JsCode("function (p) { return p.percent.toFixed(1).replace('.', ',') + ' %'; }")},
            "labelLine": {"show": True, "length": 6, "length2": 6, "lineStyle": {"color": "#9CA3AF"}},
            "labelLayout": {"hideOverlap": True},
            "emphasis": {"focus": "self", "scale": True, "scaleSize": 6, "label": {"fontSize": 14}},
            "blur": {"itemStyle": {"opacity": 0.25}, "label": {"opacity": 0.3}},
            "data": datos,
        }],
    }


def opciones_barras_h(df: pd.DataFrame, cat: str, val: str, grupo: str, colores: dict[str, str],
                      eje: str, etiqueta: str = "{c}", extra: list[str] | None = None,
                      tooltip_js: str | None = None, nombre_png: str = "barras") -> dict:
    """Barras horizontales coloreadas por ``grupo`` (una serie por grupo → destacar por tecnología).

    Categorías en el orden de ``df`` (la primera arriba). ``extra``: columnas que viajan en cada dato
    para el tooltip (``params.data.<col>``).
    """
    cats = list(df[cat])
    grupos = list(dict.fromkeys(df[grupo]))
    series = []
    for g in grupos:
        datos = []
        for _, r in df.iterrows():
            if r[grupo] != g:
                datos.append(None)
                continue
            d = {"value": _num(r[val])}
            for e in extra or []:
                v = r[e]
                d[e] = _num(v) if pd.api.types.is_number(v) else str(v)
            datos.append(d)
        c = colores.get(g, GRIS)
        series.append({"type": "bar", "id": f"g-{g}", "name": g, "stack": "uno", "data": datos,
                       "barMaxWidth": 26, "itemStyle": {"color": c, "borderRadius": [0, 4, 4, 0]},
                       "label": {"show": True, "position": "right", "formatter": etiqueta, "fontSize": 11,
                                 "color": "#4B5563"},
                       **{k: v for k, v in DESTACAR.items()}})
    tooltip = {**TOOLTIP_ESTILO, "trigger": "item"}
    if tooltip_js:
        tooltip["formatter"] = JsCode(tooltip_js)
    return {
        "animationDuration": 400,
        "grid": {"left": 12, "right": 64, "top": 36, "bottom": 44, "containLabel": True},
        "tooltip": tooltip,
        "legend": _leyenda(grupos),
        "toolbox": _toolbox(nombre_png, zoom=False),
        "xAxis": {**_eje_valor(eje), "nameGap": 28},
        "yAxis": {"type": "category", "data": cats, "inverse": True,
                  "axisTick": {"show": False}, "axisLine": {"lineStyle": {"color": "#CBD5E1"}},
                  "axisLabel": {"fontSize": 11}},
        "series": series,
    }


def opciones_top10(top: pd.DataFrame, colores: dict[str, str], col_e: str, unidad: str) -> dict:
    """``top``: central, propietario, tecnologia, <col_e>, pct, pct_acum."""
    js = ("function (p) { const d = p.data; return '<b>' + p.name + '</b><br>' + p.marker + ' ' + p.seriesName"
          " + '<br>Empresa: ' + d.propietario"
          " + '<br><b>' + d.value.toFixed(2) + ' %</b> del total SEN'"
          " + '<br>' + Number(d." + col_e + ").toLocaleString('es-CL', {maximumFractionDigits: 0}) + ' " + unidad + "'"
          " + '<br><span style=\"opacity:.6\">Acumulado top: ' + Number(d.pct_acum).toFixed(1) + ' %</span>'; }")
    return opciones_barras_h(top, "central", "pct", "tecnologia", colores, "% del total SEN",
                             etiqueta=JsCode("function (p) { return p.value.toFixed(1) + ' %'; }"),
                             extra=["propietario", col_e, "pct_acum"], tooltip_js=js, nombre_png="top10")


def opciones_subtipo(sub: pd.DataFrame, colores: dict[str, str]) -> dict:
    """``sub``: subtipo, tecnologia, mw (ordenado de mayor a menor)."""
    js = ("function (p) { return '<b>' + p.name + '</b><br>' + p.marker + ' ' + p.seriesName + '<br><b>'"
          " + p.value.toLocaleString('es-CL', {maximumFractionDigits: 0}) + '</b> MW'; }")
    return opciones_barras_h(sub, "subtipo", "mw", "tecnologia", colores, "MW",
                             etiqueta=JsCode("function (p) { return Math.round(p.value).toLocaleString('es-CL'); }"),
                             tooltip_js=js, nombre_png="subtipo")


# =================================================================== Demanda
HORAS = [f"{h:02d}:00" for h in range(24)]


def serie_horaria(ts: pd.Series, val: pd.Series) -> list:
    """Valores en una lista de 24 posiciones (una por hora del día); None donde no hay dato."""
    out: list = [None] * 24
    for t, v in zip(ts, val):
        out[int(pd.Timestamp(t).hour)] = _num(v, 1)
    return out


def opciones_demanda(series_def: list[dict]) -> dict:
    """``series_def``: dicts con name, data (24 valores), color y opcionalmente
    estilo ('solid'|'dashed'|'dotted'), area (bool), id."""
    nombres = [s["name"] for s in series_def]
    series = []
    for i, s in enumerate(series_def):
        c = s["color"]
        d = {**LINEA, "id": s.get("id", f"dem-{i}"), "name": s["name"], "data": s["data"],
             "connectNulls": False, "showSymbol": True, "symbolSize": 5,
             "lineStyle": {"width": s.get("ancho", 2.2), "color": c, "type": s.get("estilo", "solid")},
             "itemStyle": {"color": c}}
        if s.get("estilo") in ("dashed", "dotted"):
            d["symbol"] = "emptyCircle"
        if s.get("area"):
            d["areaStyle"] = {"color": _degradado(c, 0.25, 0.0)}
        series.append(d)
    return {
        "animationDuration": 400,
        "color": [s["color"] for s in series_def],
        "grid": {"left": 64, "right": 24, "top": 40, "bottom": 64},
        "tooltip": _tooltip_eje("MWh", cabecera="hora", decimales=0),
        "legend": _leyenda(nombres),
        "toolbox": _toolbox("demanda", zoom=False),
        "xAxis": {"type": "category", "data": HORAS, "boundaryGap": False,
                  "axisLine": {"lineStyle": {"color": "#CBD5E1"}},
                  # ECharts decide cuántas horas caben; las que se topan se ocultan (gráfico angosto en Resumen)
                  "axisLabel": {"interval": "auto", "hideOverlap": True, "fontSize": 11}},
        "yAxis": {**_eje_valor("Demanda (MWh)"), "scale": True},
        "series": series,
    }


# =================================================================== Baterías
def opciones_mapa_cero(matriz: pd.DataFrame, nombres: dict[str, str], solar: list,
                       umbral: float, color_solar: str = "#F2B701") -> dict:
    """Mapa de calor barra × hora (minutos con CMg < umbral) con la generación solar debajo.

    ``matriz``: índice barra_transf, columnas 0–23 (NaN = sin dato). ``nombres``: barra_transf → etiqueta.
    """
    barras = list(matriz.index)
    etiquetas = [nombres.get(b, b) for b in barras]
    datos = []
    for y, b in enumerate(barras):
        for x in range(24):
            v = matriz.loc[b, x] if x in matriz.columns else None
            datos.append([x, y, None if v is None or pd.isna(v) else round(float(v))])
    js_tooltip = ("function (p) { if (p.seriesType === 'heatmap') { const v = p.value[2];"
                  " return '<b>' + p.name + '</b> · ' + String(p.value[0]).padStart(2,'0') + ':00<br>'"
                  " + (v === null ? 'sin dato' : v + ' min con CMg &lt; " + f"{umbral:g}" + " USD/MWh'); }"
                  " return p.marker + ' Solar ' + p.name + ': <b>' + (p.value === null ? '–' : "
                  "Math.round(p.value).toLocaleString('es-CL')) + '</b> MW'; }")
    alto_mapa = max(140, 26 * len(barras))
    return {
        "animationDuration": 300,
        "tooltip": {**TOOLTIP_ESTILO, "trigger": "item", "formatter": JsCode(js_tooltip)},
        "toolbox": _toolbox("horas_cmg_cero", zoom=False),
        "visualMap": {"min": 0, "max": 60, "calculable": False, "orient": "horizontal", "right": 40, "top": 0,
                      "itemWidth": 12, "itemHeight": 120, "text": ["60 min", "0"], "textStyle": {"fontSize": 11},
                      "inRange": {"color": ["#F8FAFC", "#CFEAF8", "#5BC0F0", "#1F5FA8"]}, "seriesIndex": 0},
        "grid": [{"left": 130, "right": 24, "top": 36, "height": alto_mapa},
                 {"left": 130, "right": 24, "top": 36 + alto_mapa + 34, "height": 90}],
        "xAxis": [{"type": "category", "data": HORAS, "gridIndex": 0, "splitArea": {"show": True},
                   "axisLabel": {"show": False}, "axisTick": {"show": False}},
                  {"type": "category", "data": HORAS, "gridIndex": 1, "axisLabel": {"interval": 1, "fontSize": 11},
                   "axisLine": {"lineStyle": {"color": "#CBD5E1"}}}],
        "yAxis": [{"type": "category", "data": etiquetas, "gridIndex": 0, "inverse": True,
                   "axisLabel": {"fontSize": 11}, "axisTick": {"show": False}},
                  {"type": "value", "gridIndex": 1, "name": "Solar (MW)", "nameLocation": "middle", "nameGap": 52,
                   "nameTextStyle": {"fontSize": 11}, "splitNumber": 2,
                   "splitLine": {"lineStyle": {"color": "#EEF1F5"}}}],
        "series": [
            {"type": "heatmap", "name": "CMg ≈ 0", "xAxisIndex": 0, "yAxisIndex": 0, "data": datos,
             "itemStyle": {"borderColor": "#fff", "borderWidth": 1, "borderRadius": 2},
             "emphasis": {"itemStyle": {"borderColor": "#1F2937", "borderWidth": 1.5}}},
            {"type": "line", "name": "Solar", "xAxisIndex": 1, "yAxisIndex": 1, "data": solar, "smooth": 0.3,
             "showSymbol": False, "lineStyle": {"color": color_solar, "width": 2}, "itemStyle": {"color": color_solar},
             "areaStyle": {"color": _degradado(color_solar, 0.45, 0.05)}},
        ],
        "_alto": alto_mapa + 36 + 34 + 90 + 40,  # alto sugerido en px (no es opción de ECharts; se quita al usarlo)
    }


def opciones_spread_tendencia(sp: pd.DataFrame, nombres: dict[str, str]) -> dict:
    """Spread diario por barra a lo largo de los días. ``sp``: barra_transf, dia, spread."""
    dias = sorted(sp["dia"].unique()) if not sp.empty else []
    cats = [pd.Timestamp(d).strftime("%d-%m") for d in dias]
    barras = list(dict.fromkeys(sp["barra_transf"])) if not sp.empty else []
    color = {b: PALETA[i % len(PALETA)] for i, b in enumerate(barras)}
    series = []
    for b in barras:
        d = sp[sp["barra_transf"] == b].set_index("dia")["spread"]
        c = color[b]
        series.append({**LINEA, "id": f"sp-{b}", "name": nombres.get(b, b), "showSymbol": True, "symbolSize": 6,
                       "data": [_num(d.get(x)) for x in dias],
                       "lineStyle": {"width": 2.2, "color": c}, "itemStyle": {"color": c}})
    return {
        "animationDuration": 400,
        "color": [color[b] for b in barras],
        "grid": {"left": 64, "right": 24, "top": 40, "bottom": 64},
        "tooltip": _tooltip_eje("USD/MWh", cabecera="categoria", decimales=1),
        "legend": _leyenda([nombres.get(b, b) for b in barras]),
        "toolbox": _toolbox("spread_diario", zoom=False),
        "xAxis": {"type": "category", "data": cats, "boundaryGap": False,
                  "axisLine": {"lineStyle": {"color": "#CBD5E1"}}},
        "yAxis": _eje_valor("Spread (USD/MWh)"),
        "series": series,
    }


def opciones_erv(erv: pd.DataFrame, real: pd.DataFrame | None, colores: dict[str, str],
                 separadores: list[date] | None = None) -> dict:
    """Generación solar/eólica programada (áreas apiladas) + capacidad disponible y real (líneas).

    ``erv``: ts, tecnologia, mw, disponible_mw. ``real``: ts, tecnologia, mw (generación real horaria).
    """
    techs = [t for t in ("Solar", "Eólica") if t in set(erv["tecnologia"])]
    piv = erv.pivot_table(index="ts", columns="tecnologia", values="mw", aggfunc="sum").sort_index()
    disp = erv.groupby("ts")["disponible_mw"].sum().sort_index()
    series: list[dict] = []
    for t in techs:
        c = colores.get(t, GRIS)
        series.append({**LINEA, "id": f"prog-{t}", "name": f"{t} programada", "stack": "erv", "smooth": 0.3,
                       "data": _puntos(piv.index.to_series(), piv[t].fillna(0), 0),
                       "lineStyle": {"width": 1.2, "color": c}, "itemStyle": {"color": c},
                       "areaStyle": {"color": _degradado(c, 0.75, 0.35)}})
    series.append({**LINEA, "id": "disp", "name": "Capacidad disponible ERV", "smooth": 0.3,
                   "data": _puntos(disp.index.to_series(), disp, 0),
                   "lineStyle": {"width": 1.6, "type": "dashed", "color": "#64748B"}, "itemStyle": {"color": "#64748B"}})
    if real is not None and not real.empty:
        r = real[real["tecnologia"].isin(techs)].groupby("ts")["mw"].sum().sort_index()
        series.append({**LINEA, "id": "real", "name": "Solar + eólica real", "smooth": 0.3,
                       "data": _puntos(r.index.to_series(), r, 0),
                       "lineStyle": {"width": 2.4, "color": "#1F2937"}, "itemStyle": {"color": "#1F2937"}})
    m = _serie_marcas(separadores)
    if m:
        series.append(m)
    nombres = [x["name"] for x in series if x.get("name")]
    return {
        "animationDuration": 400,
        "grid": {"left": 64, "right": 24, "top": 44, "bottom": 96},
        "tooltip": _tooltip_eje("MW", decimales=0),
        "legend": _leyenda(nombres),
        "toolbox": _toolbox("erv_programada"),
        "xAxis": _eje_tiempo(),
        "yAxis": _eje_valor("MW"),
        "dataZoom": _zoom_tiempo(),
        "series": series,
    }


def opciones_barras_agrupadas(categorias: list[str], series: dict[str, list], colores: dict[str, str],
                              unidad: str, nombre_png: str = "comparacion") -> dict:
    """Barras verticales agrupadas (p. ej. programado vs real por tecnología), con destacado al pasar."""
    sers = []
    for nombre, vals in series.items():
        c = colores.get(nombre, GRIS)
        sers.append({"type": "bar", "id": f"b-{nombre}", "name": nombre, "data": [_num(v, 1) for v in vals],
                     "barMaxWidth": 34, "itemStyle": {"color": c, "borderRadius": [4, 4, 0, 0]}, **DESTACAR})
    return {
        "animationDuration": 400,
        "grid": {"left": 64, "right": 24, "top": 40, "bottom": 64},
        "tooltip": {**_tooltip_eje(unidad, cabecera="categoria", decimales=0), "axisPointer": {"type": "shadow"}},
        "legend": _leyenda(list(series)),
        "toolbox": _toolbox(nombre_png, zoom=False),
        "xAxis": {"type": "category", "data": categorias, "axisLine": {"lineStyle": {"color": "#CBD5E1"}}},
        "yAxis": _eje_valor(unidad),
        "series": sers,
    }
