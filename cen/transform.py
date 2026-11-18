"""Transformaciones puras (sin red): DataFrames listos para graficar."""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

TECNOLOGIAS = ["Solar", "Eólica", "Hidráulica", "Geotérmica", "BESS", "Térmica"]
RENOVABLES = {"Solar", "Eólica", "Hidráulica", "Geotérmica"}
COLORES_TEC = {
    "Solar": "#F2B701",
    "Eólica": "#3BA3D0",
    "Hidráulica": "#1F5FA8",
    "Geotérmica": "#B5523B",
    "BESS": "#7E57C2",
    "Térmica": "#6B6B6B",
    "Otra": "#BBBBBB",
}

# barra_transf de las 8 barras principales (verificar contra el catálogo; se usan como defecto)
BARRAS_DEFECTO_PATRONES = [
    "TARAPACA_220", "CRUCERO_220", "D.ALMAGRO_220", "CARDONES_220",
    "P.AZUCAR_220", "QUILLOTA_220", "CHARRUA_220", "P.MONTT_220",
]


# ------------------------------------------------------------------ helpers
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def limpiar_nombre_central(nombre: str) -> str:
    return re.sub(r"\s*\[EN_REVISION\]\s*", " ", str(nombre)).strip()


def normalizar_tecnologia(t: str | None) -> str:
    if not t:
        return "Otra"
    n = _norm(t)
    if n.startswith("TOTAL"):  # getDailySum: "TOTAL EÓLICAS", "TOTAL HIDRÁULICO", ...
        n = n[5:]
    for tec in TECNOLOGIAS:
        # tolera plural/género: EOLICAS, HIDRAULICO, TERMICAS
        if n == _norm(tec) or n.startswith(_norm(tec)[:-1]):
            return tec
    # nombres del programa de generación (PCP): "Hidroeléctricas", "Termoeléctricas"
    if "SOLAR" in n:
        return "Solar"
    if n.startswith("HIDRO"):
        return "Hidráulica"
    if n.startswith("TERMO"):
        return "Térmica"
    return str(t).strip().title()


# --------------------------------------------------------------- CMg
def cmg_df(rows: list[dict]) -> pd.DataFrame:
    """CMg en línea / real -> columnas: ts, barra_transf, barra_info, usd_mwh, clp_kwh, version."""
    cols = ["ts", "barra_transf", "barra_info", "usd_mwh", "clp_kwh", "version"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "ts": pd.to_datetime(df.get("fecha_minuto", df.get("fecha_hora"))),
        "barra_transf": df["barra_transf"],
        "barra_info": df.get("barra_info"),
        "usd_mwh": pd.to_numeric(df.get("cmg_usd_mwh_"), errors="coerce"),
        "clp_kwh": pd.to_numeric(df.get("cmg_clp_kwh_"), errors="coerce"),
        "version": df.get("version"),
    })
    return out.sort_values(["barra_transf", "ts"]).drop_duplicates(["barra_transf", "ts"], keep="last").reset_index(drop=True)


def cmg_8b_df(payload: dict) -> pd.DataFrame:
    """Endpoint de 8 barras (fechas en epoch ms, hora de Chile) -> ts, barra, usd_mwh."""
    recs = []
    for b in payload.get("barras", []) or []:
        for v in b.get("valores", []) or []:
            recs.append({"ts": v["fecha"], "barra": b["nombre"], "orden": b.get("orden"), "usd_mwh": v.get("valor")})
    if not recs:
        return pd.DataFrame(columns=["ts", "barra", "orden", "usd_mwh"])
    df = pd.DataFrame(recs)
    df["ts"] = (pd.to_datetime(df["ts"], unit="ms", utc=True)
                .dt.tz_convert("America/Santiago").dt.tz_localize(None))
    return df.sort_values(["orden", "ts"]).reset_index(drop=True)


def cmg_pcp_df(rows: list[dict]) -> pd.DataFrame:
    cols = ["ts", "llave_cmg", "nmb_barra_info", "usd_mwh", "zona", "region"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "ts": pd.to_datetime(df["fecha_hora"]),
        "llave_cmg": df["llave_cmg"],
        "nmb_barra_info": df.get("nmb_barra_info"),
        "usd_mwh": pd.to_numeric(df["cmg_usd_mwh"], errors="coerce"),
        "fecha_programa": pd.to_datetime(df.get("fecha_programa")),
        "zona": df.get("zona"),
        "region": df.get("region"),
    })
    # La API entrega el mismo día en varios programas (fecha_programa de los 7 días previos, con
    # valores distintos). Se usa el programa más reciente para cada barra y hora.
    out = out.sort_values(["llave_cmg", "ts", "fecha_programa"])
    return out.drop_duplicates(["llave_cmg", "ts"], keep="last").reset_index(drop=True)


def resumen_cmg(df: pd.DataFrame, col: str = "usd_mwh") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["barra", "mín", "máx", "promedio", "último"])
    g = df.sort_values("ts").groupby("barra_info", dropna=False)[col]
    return pd.DataFrame({"mín": g.min(), "máx": g.max(), "promedio": g.mean(), "último": g.last()}) \
        .round(2).reset_index().rename(columns={"barra_info": "barra"})


# ------------------------------------------------------- catálogo de barras
def catalogo_barras(rows: list[dict] | pd.DataFrame) -> pd.DataFrame:
    """barra_transf únicas con su nombre legible (barra_info)."""
    df = pd.DataFrame(rows) if not isinstance(rows, pd.DataFrame) else rows
    if df.empty:
        return pd.DataFrame(columns=["barra_transf", "barra_info"])
    cat = (df[["barra_transf", "barra_info"]].dropna(subset=["barra_transf"])
           .drop_duplicates("barra_transf").sort_values("barra_info").reset_index(drop=True))
    cat["barra_info"] = cat["barra_info"].fillna(cat["barra_transf"])
    return cat


def barras_defecto(catalogo: pd.DataFrame) -> list[str]:
    """Busca en el catálogo las barras 220 kV equivalentes a las 8 principales."""
    if catalogo.empty:
        return []
    claves = {_norm(b): b for b in catalogo["barra_transf"]}
    out = []
    for patron in BARRAS_DEFECTO_PATRONES:
        nombre, kv = patron.rsplit("_", 1)
        objetivo = _norm(nombre)
        for k, original in claves.items():
            if k.startswith(objetivo) and k.endswith(kv):
                out.append(original)
                break
    return out


def _tokens_barra(nombre: str) -> tuple[str, str]:
    """De 'BA S/E DOMEYKO 220KV BP1' -> ('DOMEYKO', '220')."""
    s = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode().upper()
    s = re.sub(r"^BA\s+", "", s)
    s = re.sub(r"^S/E\s+", "", s)
    m = re.search(r"(\d{2,3})\s*KV", s)
    kv = m.group(1).lstrip("0") if m else ""
    base = s[: m.start()] if m else s
    return re.sub(r"[^A-Z0-9]", "", base), kv


def mapeo_barras_pcp(catalogo: pd.DataFrame, pcp: pd.DataFrame) -> dict[str, str]:
    """Mapea barra_transf -> llave_cmg comparando nombres de subestación + tensión.

    1) coincidencia exacta de ``barra_info`` con ``nmb_barra_info``;
    2) coincidencia de (subestación normalizada, kV).
    """
    if catalogo.empty or pcp.empty:
        return {}
    pcp_u = pcp[["llave_cmg", "nmb_barra_info"]].dropna().drop_duplicates("llave_cmg")
    por_nombre = {str(n).strip().upper(): k for k, n in zip(pcp_u["llave_cmg"], pcp_u["nmb_barra_info"])}
    por_tokens: dict[tuple[str, str], str] = {}
    for k, n in zip(pcp_u["llave_cmg"], pcp_u["nmb_barra_info"]):
        por_tokens.setdefault(_tokens_barra(n), k)
    out = {}
    for bt, bi in zip(catalogo["barra_transf"], catalogo["barra_info"]):
        key = por_nombre.get(str(bi).strip().upper())
        if key is None:
            key = por_tokens.get(_tokens_barra(bi))
        if key is not None:
            out[bt] = key
    return out


# ---------------------------------------------------------- generación
def gen_df(rows: list[dict]) -> pd.DataFrame:
    cols = ["ts", "central", "tecnologia", "subtipo", "mw", "factor_ernc", "propietario", "coordinado"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    return pd.DataFrame({
        "ts": pd.to_datetime(df["fecha_hora"]),
        "central": df["central"].map(limpiar_nombre_central),
        "tecnologia": df["tipo_tecnologia"].map(normalizar_tecnologia),
        "subtipo": df.get("subtipo_tecnologia"),
        "mw": pd.to_numeric(df["gen_real_mw"], errors="coerce").fillna(0.0),
        "factor_ernc": pd.to_numeric(df.get("factor_ernc"), errors="coerce").fillna(0.0),
        # empresa dueña de la unidad y empresa coordinada ante el CEN (pueden diferir)
        "propietario": df.get("propietario"),
        "coordinado": df.get("coordinado"),
    })


SIN_DATO_EMPRESA = "Sin dato en la API"


def completar_propietarios(gen: pd.DataFrame) -> pd.DataFrame:
    """Los BESS llegan sin propietario. Si su nombre es 'SAE <central>' (almacenamiento asociado a
    una central, p. ej. 'SAE PFV Estela Solar'), se usa el dueño de esa central, marcado con '*'.
    """
    if gen.empty or "propietario" not in gen:
        return gen
    con = gen.dropna(subset=["propietario"]).drop_duplicates("central")
    dueno = {_norm(c): p for c, p in zip(con["central"], con["propietario"])}
    falta = gen["propietario"].isna()
    if not falta.any():
        return gen

    def inferir(central: str):
        base = re.sub(r"^\s*(SAE|BESS)\s+", "", str(central), flags=re.I)
        p = dueno.get(_norm(base))
        return f"{p} *" if p else SIN_DATO_EMPRESA

    gen = gen.copy()
    gen.loc[falta, "propietario"] = gen.loc[falta, "central"].map(inferir)
    return gen


def _unir_empresas(s: pd.Series) -> str:
    vals = [v.strip() for v in s.dropna().astype(str) if v.strip()]
    return " / ".join(dict.fromkeys(vals)) or "—"  # únicos, en orden


def gen_por_tecnologia(gen: pd.DataFrame) -> pd.DataFrame:
    """Suma MW por hora y tecnología (formato largo: ts, tecnologia, mw)."""
    if gen.empty:
        return pd.DataFrame(columns=["ts", "tecnologia", "mw"])
    out = gen.groupby(["ts", "tecnologia"], as_index=False)["mw"].sum()
    orden = {t: i for i, t in enumerate(TECNOLOGIAS)}
    out["_o"] = out["tecnologia"].map(lambda t: orden.get(t, 99))
    return out.sort_values(["ts", "_o"]).drop(columns="_o").reset_index(drop=True)


def gen_total_horaria(gen: pd.DataFrame) -> pd.DataFrame:
    if gen.empty:
        return pd.DataFrame(columns=["ts", "mw"])
    return gen.groupby("ts", as_index=False)["mw"].sum().sort_values("ts").reset_index(drop=True)


def ultima_hora_completa(gen: pd.DataFrame, min_fraccion: float = 0.8) -> pd.Timestamp | None:
    """Última hora con un número de registros parecido al de las horas previas (evita horas a medio cargar)."""
    if gen.empty:
        return None
    cnt = gen.groupby("ts").size().sort_index()
    ref = cnt.median()
    ok = cnt[cnt >= min_fraccion * ref]
    return ok.index.max() if not ok.empty else cnt.index.max()


def porcentaje_renovable(gen: pd.DataFrame, ts: pd.Timestamp) -> float | None:
    h = gen[gen["ts"] == ts]
    tot = h["mw"].sum()
    if tot <= 0:
        return None
    return float(h.loc[h["tecnologia"].isin(RENOVABLES), "mw"].sum() / tot * 100)


def daily_sum_df(payload: dict) -> pd.DataFrame:
    data = (payload or {}).get("data") or []
    if not data:
        return pd.DataFrame(columns=["tecnologia", "valor"])
    df = pd.DataFrame(data).rename(columns={"key": "tecnologia", "value": "valor"})
    df = df[~df["tecnologia"].map(_norm).str.startswith("TOTALGENERACI")]  # fila de total
    df["tecnologia"] = df["tecnologia"].map(normalizar_tecnologia)
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    return df.groupby("tecnologia", as_index=False)["valor"].sum().sort_values("valor", ascending=False)


def top_centrales(gen: pd.DataFrame, ts: pd.Timestamp | None = None, n: int = 10) -> pd.DataFrame:
    """Mayores centrales y su aporte porcentual al total del SEN.

    ``ts`` = una hora (columna ``mw``) o ``None`` = todo el día (suma horaria → ``mwh``).
    Columnas: central, propietario, tecnologia, mw|mwh, pct (% del total), pct_acum.
    Una central con unidades de distintos dueños muestra ambos separados por " / ".
    """
    if "propietario" not in gen:  # caché antigua sin la columna
        gen = gen.assign(propietario=None)
    gen = completar_propietarios(gen)
    h = gen if ts is None else gen[gen["ts"] == ts]
    col = "mwh" if ts is None else "mw"
    total = h["mw"].sum()
    out = (h.groupby(["central", "tecnologia"], as_index=False)
           .agg(mw=("mw", "sum"), propietario=("propietario", _unir_empresas))
           .sort_values("mw", ascending=False).head(n).reset_index(drop=True))
    out = out[["central", "propietario", "tecnologia", "mw"]]
    out["pct"] = out["mw"] / total * 100 if total > 0 else 0.0
    out["pct_acum"] = out["pct"].cumsum()
    return out.rename(columns={"mw": col})


# ------------------------------------------------------------- demanda
def demanda_df(rows: list[dict]) -> pd.DataFrame:
    cols = ["ts", "gen_bruta_mwh", "gen_erv_mwh", "cons_propio_mwh", "demanda_neta_mwh"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    out = pd.DataFrame({"ts": pd.to_datetime(df["fecha_hora"])})
    for c in cols[1:]:
        out[c] = pd.to_numeric(df.get(c), errors="coerce")
    return out.sort_values("ts").drop_duplicates("ts", keep="last").reset_index(drop=True)


def recortar_horas_parciales(dem: pd.DataFrame, gen_total: pd.DataFrame, umbral: float = 0.8) -> pd.DataFrame:
    """Quita las últimas horas oficiales que aún están a medio cargar.

    Se observó que las horas más recientes de ``gen_bruta_mwh`` llegan incompletas (p. ej. 4.600
    cuando la generación real de esa hora suma 8.500). Se descartan, desde el final, las horas cuyo
    ``gen_bruta_mwh`` es menor que ``umbral`` × generación real total de la misma hora. Si esa hora aún no
    tiene generación real (la generación también llega con atraso), se compara con la hora oficial anterior:
    una caída mayor a ``1 − umbral`` de una hora a la siguiente se considera hora a medio cargar.
    """
    d = dem.dropna(subset=["gen_bruta_mwh"]).sort_values("ts")
    if d.empty:
        return d.reset_index(drop=True)
    ref = gen_total.set_index("ts")["mw"] if not gen_total.empty else pd.Series(dtype=float)
    # nivel de referencia para horas sin generación real: la última hora oficial que sí tiene con qué compararse
    con_ref = d[d["ts"].isin(ref.index)]
    nivel = con_ref.iloc[-1]["gen_bruta_mwh"] if not con_ref.empty else None
    while len(d) > 1:
        u = d.iloc[-1]
        g = ref.get(u["ts"])
        if g is None or pd.isna(g) or g <= 0:
            # sin generación real para comparar: el nivel de referencia, o la hora oficial anterior
            g = nivel if nivel is not None and u["ts"] > con_ref.iloc[-1]["ts"] else d.iloc[-2]["gen_bruta_mwh"]
        if u["gen_bruta_mwh"] < umbral * g:
            d = d.iloc[:-1]
        else:
            break
    return d.reset_index(drop=True)


def demanda_combinada(dem: pd.DataFrame, gen_total: pd.DataFrame) -> pd.DataFrame:
    """Serie de demanda: oficial (gen_bruta_mwh) + horas posteriores estimadas con la generación real.

    Columnas: ts, mwh, fuente ('oficial' | 'estimado').
    """
    partes = []
    ultimo_oficial = None
    if not dem.empty:
        d = recortar_horas_parciales(dem, gen_total)
        partes.append(pd.DataFrame({"ts": d["ts"], "mwh": d["gen_bruta_mwh"], "fuente": "oficial"}))
        ultimo_oficial = d["ts"].max() if not d.empty else None
    if not gen_total.empty:
        g = gen_total if ultimo_oficial is None else gen_total[gen_total["ts"] > ultimo_oficial]
        partes.append(pd.DataFrame({"ts": g["ts"], "mwh": g["mw"], "fuente": "estimado"}))
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame(columns=["ts", "mwh", "fuente"])
    return pd.concat(partes, ignore_index=True).sort_values("ts").reset_index(drop=True)


def demanda_prog_total(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["ts", "mw"])
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["fecha_hora"])
    df["mw"] = pd.to_numeric(df["demanda_prog_mw"], errors="coerce")
    if "fecha_programa" in df and "llave_dem" in df:
        # igual que el CMg programado: varios programas por día (PCP) o reprogramaciones (PID);
        # sumar todos multiplicaría la demanda: se deja el más reciente por barra y hora
        if "hora_programa" in df:
            df["hora_programa"] = pd.to_numeric(df["hora_programa"], errors="coerce").fillna(0)
        df = _ultimo_programa(df, ["llave_dem", "ts"])
    return df.groupby("ts", as_index=False)["mw"].sum().sort_values("ts").reset_index(drop=True)


def nombre_corto(barra_info: str) -> str:
    """'BA S/E CRUCERO 220KV BP1' -> 'CRUCERO 220KV BP1' (para leyendas)."""
    return re.sub(r"^\s*BA\s+S/E\s+", "", str(barra_info)).strip()


# ------------------------------------------------------ indicadores para baterías
UMBRAL_CMG_CERO = 1.0  # USD/MWh: bajo esto se considera "CMg ≈ 0" (vertimiento / exceso renovable)


def _intervalo_horas(cmg: pd.DataFrame) -> float:
    """Duración de cada registro en horas (CMg en línea: 15 min → 0,25)."""
    dif = cmg.sort_values("ts").groupby("barra_transf")["ts"].diff().dropna()
    if dif.empty:
        return 0.25
    h = dif.median().total_seconds() / 3600
    return h if 0 < h <= 1 else 0.25


def spread_diario(cmg: pd.DataFrame, col: str = "usd_mwh", umbral: float = UMBRAL_CMG_CERO) -> pd.DataFrame:
    """Por barra y día: CMg mínimo y máximo con su hora, spread (máx − mín) y horas con CMg < umbral.

    El spread es el margen bruto que podría capturar una batería que carga en la hora más barata y
    descarga en la más cara del día (antes de pérdidas y restricciones de energía/potencia).
    """
    cols = ["barra_transf", "barra_info", "dia", "min", "ts_min", "max", "ts_max", "spread", "horas_cero", "n"]
    d = cmg.dropna(subset=[col]) if not cmg.empty else cmg
    if d.empty:
        return pd.DataFrame(columns=cols)
    d = d.assign(dia=d["ts"].dt.date)
    paso = _intervalo_horas(d)
    g = d.groupby(["barra_transf", "dia"])
    i_min, i_max = g[col].idxmin(), g[col].idxmax()
    out = pd.DataFrame({
        "barra_info": g["barra_info"].first(),
        "min": d.loc[i_min.values, col].values, "ts_min": d.loc[i_min.values, "ts"].values,
        "max": d.loc[i_max.values, col].values, "ts_max": d.loc[i_max.values, "ts"].values,
        "horas_cero": g[col].apply(lambda s: float((s < umbral).sum()) * paso),
        "n": g.size(),
    }, index=i_min.index).reset_index()
    out["spread"] = out["max"] - out["min"]
    return out[cols].sort_values(["dia", "spread"], ascending=[True, False]).reset_index(drop=True)


def matriz_cmg_cero(cmg: pd.DataFrame, dia, col: str = "usd_mwh",
                    umbral: float = UMBRAL_CMG_CERO) -> pd.DataFrame:
    """Barra × hora (0–23) con los minutos de esa hora en que el CMg estuvo bajo el umbral.

    NaN donde no hay datos (p. ej. horas que aún no ocurren hoy).
    """
    horas = list(range(24))
    d = cmg[cmg["ts"].dt.date == dia].dropna(subset=[col]) if not cmg.empty else cmg
    if d.empty:
        return pd.DataFrame(columns=horas)
    paso_min = _intervalo_horas(d) * 60
    d = d.assign(hora=d["ts"].dt.hour, cero=(d[col] < umbral).astype(float) * paso_min)
    m = d.pivot_table(index="barra_transf", columns="hora", values="cero", aggfunc="sum")
    return m.reindex(columns=horas)


def solar_horaria(gen: pd.DataFrame, dia) -> list:
    """Generación solar (MW) por hora del día, 24 valores (None sin dato)."""
    out: list = [None] * 24
    if gen.empty:
        return out
    s = gen[(gen["tecnologia"] == "Solar") & (gen["ts"].dt.date == dia)].groupby("ts")["mw"].sum()
    for ts, v in s.items():
        out[int(ts.hour)] = round(float(v), 1)
    return out


# ------------------------------------------------------------- programas PID
def _ultimo_programa(df: pd.DataFrame, claves: list[str]) -> pd.DataFrame:
    """Para cada combinación de ``claves`` deja la fila del programa más reciente.

    PID reprograma varias veces al día: el mismo ``fecha_hora`` aparece en programas con distinta
    ``fecha_programa``/``hora_programa``; vale el último.
    """
    orden = [c for c in ("fecha_programa", "hora_programa") if c in df]
    return df.sort_values(claves + orden).drop_duplicates(claves, keep="last")


def cmg_pid_df(rows: list[dict]) -> pd.DataFrame:
    """CMg programado intradiario (PID): última reprogramación por barra y hora."""
    cols = ["ts", "llave_cmg", "nmb_barra_info", "usd_mwh", "programa"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"])
    df["fecha_programa"] = pd.to_datetime(df.get("fecha_programa"))
    df["hora_programa"] = pd.to_numeric(df.get("hora_programa"), errors="coerce").fillna(0)
    df = _ultimo_programa(df, ["llave_cmg", "fecha_hora"])
    return pd.DataFrame({
        "ts": df["fecha_hora"], "llave_cmg": df["llave_cmg"], "nmb_barra_info": df.get("nmb_barra_info"),
        "usd_mwh": pd.to_numeric(df["cmg_usd_mwh"], errors="coerce"),
        "programa": df["fecha_programa"] + pd.to_timedelta(df["hora_programa"], unit="h"),
    }).sort_values(["llave_cmg", "ts"]).reset_index(drop=True)


# ----------------------------------------------- instrucciones operacionales
RE_ALMACENAMIENTO = re.compile(r"\b(?:SAE|BESS)\b|ALMACENAMIENTO", re.I)


def limpiar_motivo(m: str) -> str:
    """Normaliza espacios y erratas frecuentes del CEN ("C omienza descarga", dobles espacios)."""
    m = re.sub(r"\s+", " ", str(m)).strip()
    return re.sub(r"^C\s+omienza", "Comienza", m, flags=re.I)


def accion_almacenamiento(motivo: str) -> str | None:
    """'Comienza carga' -> 'Comienza carga'; ... ; None si el motivo no es de carga/descarga."""
    m = _norm(motivo)
    fase = "Comienza" if m.startswith("COMIENZA") else "Termina" if m.startswith("TERMINA") else None
    tipo = "descarga" if "DESCARGA" in m else "carga" if "CARGA" in m else None
    return f"{fase} {tipo}" if fase and tipo else None


def instrucciones_df(rows: list[dict], solo_almacenamiento: bool = False) -> pd.DataFrame:
    """Instrucciones operacionales del CEN (despacho por CMg). ``solo_almacenamiento``: solo SAE/BESS."""
    cols = ["ts", "central", "consigna", "instruccion", "despacho_mw", "motivo"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    fecha = pd.to_datetime(df["fecha"]).dt.normalize()
    hora = pd.to_timedelta(df.get("hora", "00:00:00").astype(str))
    out = pd.DataFrame({
        "ts": fecha + hora, "central": df["central"].astype(str).str.strip(),
        "consigna": df.get("consigna"), "instruccion": df.get("instruccion_cmg"),
        "despacho_mw": pd.to_numeric(df.get("despacho"), errors="coerce"),
        "motivo": df.get("motivo").fillna("").astype(str).map(limpiar_motivo),
    })
    out["accion"] = out["motivo"].map(accion_almacenamiento)
    if solo_almacenamiento:
        out = out[out["central"].str.contains(RE_ALMACENAMIENTO)]
    return out.sort_values(["ts", "central"]).reset_index(drop=True)


# ------------------------------------------- generación ERV programada (pronóstico)
def gen_programada_erv(rows, tecnologias: tuple[str, ...] | None = ("Solar", "Eólica")) -> pd.DataFrame:
    """Generación programada PCP agregada por hora y tecnología (solo ``tecnologias``).

    Sustituye al pronóstico ERV (``pronostico-erv`` no publica datos). Usa el programa más reciente de
    cada unidad y hora. Columnas: ts, tecnologia, mw (programada), disponible_mw (capacidad disponible).
    """
    cols = ["ts", "tecnologia", "mw", "disponible_mw"]
    if rows is None or len(rows) == 0:
        return pd.DataFrame(columns=cols)
    df = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    df["tecnologia"] = df["tipo_tecnologia"].map(normalizar_tecnologia)
    if tecnologias is not None:
        df = df[df["tecnologia"].isin(tecnologias)]
    if df.empty:
        return pd.DataFrame(columns=cols)
    df = df.assign(fecha_hora=pd.to_datetime(df["fecha_hora"]))
    df = _ultimo_programa(df, ["llave_gen", "fecha_hora"])
    df["mw"] = pd.to_numeric(df["gen_programada_mw"], errors="coerce").fillna(0)
    df["disponible_mw"] = pd.to_numeric(df.get("capacidad_disponible_mw"), errors="coerce").fillna(0)
    out = df.groupby(["fecha_hora", "tecnologia"], as_index=False)[["mw", "disponible_mw"]].sum()
    return out.rename(columns={"fecha_hora": "ts"}).sort_values(["ts", "tecnologia"]).reset_index(drop=True)



# ---------------------------------------------------------------- embalses
def embalses_df(rows: list[dict]) -> pd.DataFrame:
    """Cota actual de los principales embalses (``embalse-real/v3/findLast``)."""
    cols = ["embalse", "fecha", "cota", "cota_min", "cota_max", "pct"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    if pd.api.types.is_numeric_dtype(df["fecha"]):
        fecha = (pd.to_datetime(df["fecha"], unit="ms", utc=True)
                 .dt.tz_convert("America/Santiago").dt.tz_localize(None))
    else:
        fecha = pd.to_datetime(df["fecha"])
    return pd.DataFrame({
        "embalse": df["nombre"], "fecha": fecha,
        "cota": pd.to_numeric(df["cotaActual"], errors="coerce"),
        "cota_min": pd.to_numeric(df.get("cotaMin"), errors="coerce"),
        "cota_max": pd.to_numeric(df.get("cotaMax"), errors="coerce"),
        "pct": pd.to_numeric(df.get("porcentajeActual"), errors="coerce"),
    }).sort_values("pct", ascending=False).reset_index(drop=True)


# ------------------------------------------------- pronóstico y desviaciones
def pronostico_demanda_total(rows: list[dict]) -> pd.DataFrame:
    """Pronóstico de demanda (mediano plazo): suma de los sistemas por hora. Columnas ts, mw."""
    if not rows:
        return pd.DataFrame(columns=["ts", "mw"])
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["fecha_hora"])
    df["mw"] = pd.to_numeric(df["energia_mwh"], errors="coerce")
    return df.groupby("ts", as_index=False)["mw"].sum().sort_values("ts").reset_index(drop=True)


def desviacion(prog: pd.DataFrame, real: pd.DataFrame, clave: str | None = None) -> pd.DataFrame:
    """Programado vs real por hora (y por ``clave``, p. ej. tecnología): MW y % sobre lo programado.

    ``prog`` y ``real``: columnas ts, mw (+ clave). Solo horas presentes en ambos.
    """
    k = ["ts"] + ([clave] if clave else [])
    cols = k + ["programado", "real", "desv_mw", "desv_pct"]
    if prog.empty or real.empty:
        return pd.DataFrame(columns=cols)
    m = prog[k + ["mw"]].merge(real[k + ["mw"]], on=k, suffixes=("_p", "_r"))
    m = m.rename(columns={"mw_p": "programado", "mw_r": "real"})
    m["desv_mw"] = m["real"] - m["programado"]
    m["desv_pct"] = m["desv_mw"] / m["programado"].where(m["programado"].abs() > 1e-9) * 100
    return m[cols].sort_values(k).reset_index(drop=True)


# ------------------------------------------------- servicios complementarios
def sscc_df(rows: list[dict]) -> pd.DataFrame:
    """Activaciones reales de servicios complementarios (Operación ``servicios-complementarios/v1``)."""
    cols = ["inicio", "fin", "servicio", "unidad", "baja_mw", "sube_mw", "motivo"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    fecha = pd.to_datetime(df["fecha"])
    unidad = df["centralUnidad"] if "centralUnidad" in df else pd.Series([None] * len(df))
    if "centralSubestacion" in df:
        unidad = unidad.fillna(df["centralSubestacion"])
    out = pd.DataFrame({
        "inicio": fecha + pd.to_timedelta(df["inicioPeriodo"].fillna("00:00:00").astype(str)),
        "fin": fecha + pd.to_timedelta(df["finPeriodo"].fillna("00:00:00").astype(str)),
        "servicio": df.get("instruccionSscc"), "unidad": unidad,
        "baja_mw": pd.to_numeric(df.get("baja"), errors="coerce"),
        "sube_mw": pd.to_numeric(df.get("sube"), errors="coerce"),
        "motivo": df["motivo"].fillna("").astype(str).str.strip() if "motivo" in df else "",
    })
    return out.sort_values("inicio").reset_index(drop=True)



# ------------------------------------------------- capacidad y factor de planta
# nombre_tecnologia de unidades-generadoras -> tecnología del dashboard
_TEC_UNIDAD = [
    ("FOTOVOLTAICA", "Solar"), ("TERMOSOLAR", "Solar"), ("EOLICA", "Eólica"),
    ("HIDRO", "Hidráulica"), ("MINIHIDRO", "Hidráulica"), ("GEOTERMICA", "Geotérmica"),
    ("TERMOELECTRICA", "Térmica"), ("COMBUSTION", "Térmica"), ("COGENERACION", "Térmica"),
]


def tecnologia_unidad(nombre: str | None) -> str | None:
    n = _norm(nombre or "")
    for clave, tec in _TEC_UNIDAD:
        if clave in n:
            return tec
    return None  # "Sin Asignar" u otras: no se cuentan


def _num_coma(v) -> float:
    """'1,9944' -> 1.9944 (la API usa coma decimal en las potencias)."""
    if v is None:
        return float("nan")
    try:
        return float(str(v).replace(".", "").replace(",", ".") if "," in str(v) else v)
    except ValueError:
        return float("nan")


def capacidad_por_tecnologia(rows: list[dict]) -> pd.DataFrame:
    """Potencia neta efectiva instalada (MW) por tecnología, desde ``unidades-generadoras/v4``."""
    if not rows:
        return pd.DataFrame(columns=["tecnologia", "mw", "unidades"])
    df = pd.DataFrame(rows)
    df["tecnologia"] = df["nombre_tecnologia"].map(tecnologia_unidad)
    pot = df["pot_neta_efectiva"].map(_num_coma)
    df["mw"] = pot.fillna(df["pot_max_bruta"].map(_num_coma))
    df = df.dropna(subset=["tecnologia", "mw"])
    return (df.groupby("tecnologia").agg(mw=("mw", "sum"), unidades=("mw", "size")).reset_index()
            .sort_values("mw", ascending=False).reset_index(drop=True))


def factor_planta(gen: pd.DataFrame, cap: pd.DataFrame, hasta: pd.Timestamp | None = None) -> pd.DataFrame:
    """Factor de planta del día por tecnología = generación media (MW) / capacidad instalada (MW).

    Usa las horas con datos hasta ``hasta`` (hoy, la última hora completa). Sin BESS (no está en la
    capacidad de unidades generadoras).
    """
    cols = ["tecnologia", "gen_media_mw", "capacidad_mw", "factor_pct", "horas"]
    if gen.empty or cap.empty:
        return pd.DataFrame(columns=cols)
    g = gen if hasta is None else gen[gen["ts"] <= hasta]
    porhora = g.groupby(["ts", "tecnologia"])["mw"].sum().reset_index()
    media = porhora.groupby("tecnologia").agg(gen_media_mw=("mw", "mean"), horas=("ts", "nunique")).reset_index()
    out = media.merge(cap[["tecnologia", "mw"]].rename(columns={"mw": "capacidad_mw"}), on="tecnologia")
    out["factor_pct"] = out["gen_media_mw"] / out["capacidad_mw"] * 100
    return out[cols].sort_values("factor_pct", ascending=False).reset_index(drop=True)


# ------------------------------------------------- reporte de generación (Operación)
def reporte_generacion_df(payload: dict) -> pd.DataFrame:
    """``reportes/v3/generation``: generación del día, mes y año a la fecha por tecnología (GWh)."""
    data = (payload or {}).get("content") or []
    if not data:
        return pd.DataFrame(columns=["tecnologia", "dia_gwh", "mes_gwh", "anio_gwh", "fecha"])
    df = pd.DataFrame(data)
    return pd.DataFrame({
        "tecnologia": df["description"].map(normalizar_tecnologia),
        "dia_gwh": pd.to_numeric(df.get("dailyCurrent"), errors="coerce"),
        "mes_gwh": pd.to_numeric(df.get("monthlyCurrentTodate"), errors="coerce"),
        "anio_gwh": pd.to_numeric(df.get("annualCurrentTodate"), errors="coerce"),
        "fecha": pd.to_datetime(df.get("date")),
    }).sort_values("anio_gwh", ascending=False).reset_index(drop=True)


# ------------------------------------------------- mantenimientos y solicitudes
def _activos(df: pd.DataFrame, ini: str, fin: str, dia) -> pd.DataFrame:
    d0, d1 = pd.Timestamp(dia), pd.Timestamp(dia) + pd.Timedelta(days=1)
    return df[(df[ini] < d1) & (df[fin].isna() | (df[fin] >= d0))]


def mantenimientos_df(rows: list[dict], dia=None) -> pd.DataFrame:
    """Programas de mantenimiento mayor; con ``dia``, solo los que abarcan ese día."""
    cols = ["inicio", "fin", "instalacion", "elemento", "estado", "riesgo", "consumos", "descripcion"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "inicio": pd.to_datetime(df["fecha_inicio_programa"], errors="coerce"),
        "fin": pd.to_datetime(df["fecha_fin_programa"], errors="coerce"),
        "instalacion": df.get("nombre_instalacion"), "elemento": df.get("nombre_sub_instalacion"),
        "estado": df.get("estado"), "riesgo": df.get("riesgo"), "consumos": df.get("consumos_afectados"),
        "descripcion": df.get("descripcion_trabajo").fillna("").astype(str).str.strip(),
    })
    if dia is not None:
        out = _activos(out, "inicio", "fin", dia)
    return out.sort_values("inicio").reset_index(drop=True)


def solicitudes_df(rows: list[dict], dia=None) -> pd.DataFrame:
    """Solicitudes de trabajo (desconexiones/intervenciones); con ``dia``, las que abarcan ese día."""
    cols = ["inicio", "fin", "instalacion", "empresa", "tipo", "elemento", "estado", "consumo"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "inicio": pd.to_datetime(df["fecha_inicio"], errors="coerce"),
        "fin": pd.to_datetime(df["fecha_fin"], errors="coerce"),
        "instalacion": df.get("instalacion_nombre"), "empresa": df.get("empresa_nombre"),
        "tipo": df.get("tipo_solicitud"), "elemento": df.get("type"), "estado": df.get("status"),
        "consumo": df.get("consumo"),
    })
    if dia is not None:
        out = _activos(out, "inicio", "fin", dia)
    return out.drop_duplicates().sort_values("inicio").reset_index(drop=True)



def activos_en(df: pd.DataFrame, dia) -> pd.DataFrame:
    """Filas (con columnas inicio/fin) cuyo periodo abarca ``dia``."""
    if df.empty:
        return df
    return _activos(df, "inicio", "fin", dia).reset_index(drop=True)
