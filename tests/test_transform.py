import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cen import transform as T  # noqa: E402


def _gen_row(fh, central, tec, mw, sub=None):
    return {"fecha_hora": fh, "central": central, "tipo_tecnologia": tec, "subtipo_tecnologia": sub,
            "gen_real_mw": mw, "factor_ernc": 0.0}


def test_gen_por_tecnologia_suma_y_normaliza():
    rows = [
        _gen_row("2026-11-17 10:00:00", "PFV A", "Solar", 100),
        _gen_row("2026-11-17 10:00:00", "PFV B", "solar", 50),
        _gen_row("2026-11-17 10:00:00", "TER X [EN_REVISION]", "Térmica", 30, "Diésel"),
        _gen_row("2026-11-17 11:00:00", "PE C", "EÓLICA", 20),
    ]
    g = T.gen_df(rows)
    assert "TER X" in set(g["central"])
    agg = T.gen_por_tecnologia(g)
    h10 = agg[agg["ts"] == pd.Timestamp("2026-11-17 10:00")].set_index("tecnologia")["mw"]
    assert h10["Solar"] == 150
    assert h10["Térmica"] == 30
    assert list(h10.index) == ["Solar", "Térmica"]  # orden fijo de tecnologías
    assert set(agg["tecnologia"]) == {"Solar", "Térmica", "Eólica"}


def test_porcentaje_renovable():
    g = T.gen_df([
        _gen_row("2026-11-17 10:00:00", "A", "Solar", 75),
        _gen_row("2026-11-17 10:00:00", "B", "Térmica", 25),
    ])
    assert T.porcentaje_renovable(g, pd.Timestamp("2026-11-17 10:00")) == 75.0


def test_top_centrales_porcentaje():
    rows = [_gen_row("2026-11-17 10:00:00", f"C{i}", "Solar", mw) for i, mw in enumerate([50, 30, 10, 10])]
    rows.append(_gen_row("2026-11-17 11:00:00", "C0", "Solar", 100))
    g = T.gen_df(rows)
    top = T.top_centrales(g, pd.Timestamp("2026-11-17 10:00"), n=2)
    assert list(top["central"]) == ["C0", "C1"]
    assert list(top["pct"]) == [50.0, 30.0]
    assert top["pct_acum"].iloc[-1] == 80.0
    dia = T.top_centrales(g, None, n=1)  # todo el día: C0 = 150 de 200
    assert dia["mwh"].iloc[0] == 150 and dia["pct"].iloc[0] == 75.0


def test_top_centrales_muestra_propietario():
    rows = [
        dict(_gen_row("2026-11-17 10:00:00", "HE RALCO", "Hidráulica", 300), propietario="ENEL GENERACIÓN CHILE S.A."),
        dict(_gen_row("2026-11-17 10:00:00", "HE RALCO", "Hidráulica", 200), propietario="ENEL GENERACIÓN CHILE S.A."),
        dict(_gen_row("2026-11-17 10:00:00", "TER X", "Térmica", 100), propietario="A S.A."),
        dict(_gen_row("2026-11-17 10:00:00", "TER X", "Térmica", 50), propietario="B S.A."),
    ]
    top = T.top_centrales(T.gen_df(rows), pd.Timestamp("2026-11-17 10:00"))
    d = top.set_index("central")["propietario"]
    assert d["HE RALCO"] == "ENEL GENERACIÓN CHILE S.A."
    assert d["TER X"] == "A S.A. / B S.A."


def test_bess_sin_propietario_se_infiere_de_su_central():
    rows = [
        dict(_gen_row("2026-11-17 10:00:00", "PFV ESTELA SOLAR", "Solar", 200), propietario="TAMARUGAL SOLAR SPA"),
        dict(_gen_row("2026-11-17 10:00:00", "SAE PFV Estela Solar", "BESS", 150), propietario=None),
        dict(_gen_row("2026-11-17 10:00:00", "BESS Huatacondo", "BESS", 100), propietario=None),
    ]
    d = T.top_centrales(T.gen_df(rows), pd.Timestamp("2026-11-17 10:00")).set_index("central")["propietario"]
    assert d["SAE PFV Estela Solar"] == "TAMARUGAL SOLAR SPA *"
    assert d["BESS Huatacondo"] == T.SIN_DATO_EMPRESA


def test_ultima_hora_completa_ignora_hora_parcial():
    rows = []
    for h in range(10, 13):
        n = 10 if h < 12 else 3  # la hora 12 está a medio cargar
        rows += [_gen_row(f"2026-11-17 {h}:00:00", f"C{i}", "Solar", 1) for i in range(n)]
    g = T.gen_df(rows)
    assert T.ultima_hora_completa(g) == pd.Timestamp("2026-11-17 11:00")


def test_catalogo_y_defecto():
    rows = [
        {"barra_transf": "CRUCERO_______220", "barra_info": "BA S/E CRUCERO 220KV BP1"},
        {"barra_transf": "CRUCERO_______220", "barra_info": "BA S/E CRUCERO 220KV BP1"},
        {"barra_transf": "QUILLOTA______220", "barra_info": "BA S/E QUILLOTA 220KV B1"},
        {"barra_transf": "QUILLOTA______110", "barra_info": "BA S/E QUILLOTA 110KV B1"},
    ]
    cat = T.catalogo_barras(rows)
    assert len(cat) == 3
    d = T.barras_defecto(cat)
    assert "CRUCERO_______220" in d and "QUILLOTA______220" in d
    assert "QUILLOTA______110" not in d


def test_mapeo_barras_pcp():
    cat = pd.DataFrame({
        "barra_transf": ["DOMEYKO_______220", "A.BLANCAS_____066", "NADA__________110"],
        "barra_info": ["BA S/E DOMEYKO 220KV BP1", "BA S/E ARENAS BLANCAS 66KV B1", "BA S/E NADA 110KV"],
    })
    pcp = T.cmg_pcp_df([
        {"llave_cmg": "Domeyko220", "nmb_barra_info": "BA S/E DOMEYKO 220KV BP1", "cmg_usd_mwh": 1,
         "fecha_hora": "2026-11-18 00:00:00"},
        {"llave_cmg": "ArenasBlancas066", "nmb_barra_info": "BA S/E ARENAS BLANCAS 066KV B2", "cmg_usd_mwh": 1,
         "fecha_hora": "2026-11-18 00:00:00"},
    ])
    m = T.mapeo_barras_pcp(cat, pcp)
    assert m["DOMEYKO_______220"] == "Domeyko220"  # nombre exacto
    assert m["A.BLANCAS_____066"] == "ArenasBlancas066"  # por subestación + kV
    assert "NADA__________110" not in m


def test_cmg_pcp_usa_programa_mas_reciente():
    base = {"llave_cmg": "Crucero220", "nmb_barra_info": "BA S/E CRUCERO 220KV BP1", "fecha_hora": "2026-11-18 00:00:00"}
    rows = [dict(base, cmg_usd_mwh=v, fecha_programa=fp)
            for v, fp in [(29.5, "2026-11-12"), (59.7, "2026-11-18"), (53.9, "2026-11-17")]]
    df = T.cmg_pcp_df(rows)
    assert len(df) == 1 and df.iloc[0]["usd_mwh"] == 59.7


def test_demanda_prog_no_suma_programas_repetidos():
    rows = [{"llave_dem": b, "fecha_hora": "2026-11-18 00:00:00", "demanda_prog_mw": mw, "fecha_programa": fp}
            for b, mw, fp in [("A", 100, "2026-11-12"), ("A", 120, "2026-11-18"), ("B", 50, "2026-11-18")]]
    assert T.demanda_prog_total(rows)["mw"].tolist() == [170]


def test_demanda_combinada_completa_con_estimado():
    dem = T.demanda_df([
        {"fecha_hora": "2026-11-17 05:00:00", "gen_bruta_mwh": 9000},
        {"fecha_hora": "2026-11-17 06:00:00", "gen_bruta_mwh": 9100},
    ])
    gen_tot = pd.DataFrame({"ts": pd.to_datetime(["2026-11-17 06:00", "2026-11-17 07:00", "2026-11-17 08:00"]),
                            "mw": [9050, 9300, 9500]})
    c = T.demanda_combinada(dem, gen_tot)
    assert list(c["fuente"]) == ["oficial", "oficial", "estimado", "estimado"]
    assert c.iloc[1]["mwh"] == 9100  # la hora oficial manda


def test_demanda_descarta_horas_oficiales_parciales():
    dem = T.demanda_df([
        {"fecha_hora": "2026-11-17 04:00:00", "gen_bruta_mwh": 7770},
        {"fecha_hora": "2026-11-17 05:00:00", "gen_bruta_mwh": 5230},  # parcial
        {"fecha_hora": "2026-11-17 06:00:00", "gen_bruta_mwh": 4600},  # parcial
    ])
    gen_tot = pd.DataFrame({"ts": pd.to_datetime(["2026-11-17 04:00", "2026-11-17 05:00", "2026-11-17 06:00"]),
                            "mw": [8700, 8460, 8530]})
    c = T.demanda_combinada(dem, gen_tot)
    assert list(c["fuente"]) == ["oficial", "estimado", "estimado"]
    assert list(c["mwh"]) == [7770, 8460, 8530]


def test_cmg_8b_epoch_a_hora_chile():
    payload = {"barras": [{"nombre": "Atacama 220 KV", "orden": 2,
                           "valores": [{"fecha": 1794848400000, "valor": 41.18}]}]}
    df = T.cmg_8b_df(payload)
    assert df.iloc[0]["usd_mwh"] == 41.18
    assert df["ts"].dt.tz is None


def test_daily_sum_normaliza_claves_reales():
    payload = {"fecha": "2026-11-17", "data": [
        {"key": "BESS", "value": 10}, {"key": "TOTAL EÓLICAS", "value": 20},
        {"key": "TOTAL HIDRÁULICO", "value": 30}, {"key": "TOTAL SOLAR", "value": 40},
        {"key": "TOTAL TÉRMICAS", "value": 50}, {"key": "TOTAL GENERACIÓN", "value": 150},
    ]}
    df = T.daily_sum_df(payload).set_index("tecnologia")["valor"]
    assert set(df.index) == {"BESS", "Eólica", "Hidráulica", "Solar", "Térmica"}
    assert df.sum() == 150


def test_cmg_df_dedup_y_resumen():
    rows = [
        {"barra_transf": "X", "barra_info": "BA X", "fecha_minuto": "2026-11-17 00:00", "cmg_usd_mwh_": 10, "cmg_clp_kwh_": 9},
        {"barra_transf": "X", "barra_info": "BA X", "fecha_minuto": "2026-11-17 00:15", "cmg_usd_mwh_": 30, "cmg_clp_kwh_": 27},
        {"barra_transf": "X", "barra_info": "BA X", "fecha_minuto": "2026-11-17 00:15", "cmg_usd_mwh_": 30, "cmg_clp_kwh_": 27},
    ]
    df = T.cmg_df(rows)
    assert len(df) == 2
    r = T.resumen_cmg(df).iloc[0]
    assert (r["mín"], r["máx"], r["promedio"], r["último"]) == (10, 30, 20, 30)


def test_nombre_corto():
    assert T.nombre_corto("BA S/E CRUCERO 220KV BP1") == "CRUCERO 220KV BP1"
    assert T.nombre_corto("CRUCERO_______220") == "CRUCERO_______220"


def _cmg_rows(barra, dia, valores, paso_min=15):
    base = pd.Timestamp(dia)
    return [{"barra_transf": barra, "barra_info": f"BA {barra}",
             "fecha_minuto": (base + pd.Timedelta(minutes=i * paso_min)).strftime("%Y-%m-%d %H:%M"),
             "cmg_usd_mwh_": v, "cmg_clp_kwh_": v} for i, v in enumerate(valores)]


def test_spread_diario_y_horas_cero():
    # 8 registros de 15 min: mínimo 0 (dos veces), máximo 80 a las 01:30
    rows = _cmg_rows("X", "2026-11-17", [10, 0, 0, 5, 20, 40, 80, 30])
    s = T.spread_diario(T.cmg_df(rows)).iloc[0]
    assert s["spread"] == 80 and s["max"] == 80 and s["min"] == 0
    assert pd.Timestamp(s["ts_max"]) == pd.Timestamp("2026-11-17 01:30")
    assert pd.Timestamp(s["ts_min"]) == pd.Timestamp("2026-11-17 00:15")  # primera ocurrencia
    assert s["horas_cero"] == 0.5  # 2 registros × 15 min


def test_spread_por_dia_y_barra():
    rows = _cmg_rows("A", "2026-11-16", [1, 9]) + _cmg_rows("A", "2026-11-17", [2, 4]) + _cmg_rows("B", "2026-11-17", [0, 50])
    s = T.spread_diario(T.cmg_df(rows))
    d = {(r.barra_transf, str(r.dia)): r.spread for r in s.itertuples()}
    assert d == {("A", "2026-11-16"): 8, ("A", "2026-11-17"): 2, ("B", "2026-11-17"): 50}


def test_matriz_cmg_cero_minutos_por_hora():
    rows = _cmg_rows("A", "2026-11-17", [0.5] * 4 + [3, 0, 3, 3])  # hora 0: 60 min; hora 1: 15 min
    m = T.matriz_cmg_cero(T.cmg_df(rows), pd.Timestamp("2026-11-17").date())
    assert m.loc["A", 0] == 60 and m.loc["A", 1] == 15 and pd.isna(m.loc["A", 5])
    assert list(m.columns) == list(range(24))


def test_solar_horaria():
    g = T.gen_df([_gen_row("2026-11-17 12:00:00", "PFV", "Solar", 100), _gen_row("2026-11-17 12:00:00", "TER", "Térmica", 50)])
    v = T.solar_horaria(g, pd.Timestamp("2026-11-17").date())
    assert v[12] == 100 and v[0] is None


def test_cmg_pid_deja_la_ultima_reprogramacion():
    base = {"llave_cmg": "Crucero220", "nmb_barra_info": "BA S/E CRUCERO 220KV BP1", "fecha_hora": "2026-11-18 15:00:00"}
    rows = [dict(base, cmg_usd_mwh=v, fecha_programa=fp, hora_programa=hp)
            for v, fp, hp in [(50, "2026-11-17", 18), (40, "2026-11-18", 6), (45, "2026-11-18", 2)]]
    df = T.cmg_pid_df(rows)
    assert len(df) == 1 and df.iloc[0]["usd_mwh"] == 40
    assert df.iloc[0]["programa"] == pd.Timestamp("2026-11-18 06:00")


def test_instrucciones_filtra_almacenamiento():
    rows = [{"fecha": "2026-11-17 00:00:00", "hora": "13:00:00", "central": "SAE-CRCA-PFV-TAMARICO",
             "despacho": 0.0, "consigna": "EP", "instruccion_cmg": "EP", "motivo": "Termina descarga"},
            {"fecha": "2026-11-17 00:00:00", "hora": "14:00:00", "central": "BESS ANDES", "despacho": 20,
             "consigna": "D", "instruccion_cmg": "D", "motivo": "Descarga"},
            {"fecha": "2026-11-17 00:00:00", "hora": "13:00:00", "central": "TER ESPERANZA",
             "despacho": 5, "consigna": "P", "instruccion_cmg": "P", "motivo": None}]
    todo = T.instrucciones_df(rows)
    bess = T.instrucciones_df(rows, solo_almacenamiento=True)
    assert len(todo) == 3 and list(bess["central"]) == ["SAE-CRCA-PFV-TAMARICO", "BESS ANDES"]
    assert bess.iloc[0]["ts"] == pd.Timestamp("2026-11-17 13:00") and bess.iloc[1]["despacho_mw"] == 20


def test_gen_programada_erv_agrega_solar_y_eolica_con_ultimo_programa():
    def r(llave, tec, mw, disp, fp, fh="2026-11-18 12:00:00"):
        return {"llave_gen": llave, "tipo_tecnologia": tec, "gen_programada_mw": mw, "capacidad_disponible_mw": disp,
                "fecha_hora": fh, "fecha_programa": fp}
    rows = [r("PFV1", "Solares", 100, 120, "2026-11-17"), r("PFV1", "Solares", 90, 120, "2026-11-18"),
            r("PFV2", "Solares", 50, 50, "2026-11-18"), r("PE1", "Eólicas", 30, 40, "2026-11-18"),
            r("TER1", "Térmicas", 500, 500, "2026-11-18")]
    df = T.gen_programada_erv(rows).set_index("tecnologia")
    assert set(df.index) == {"Solar", "Eólica"}
    assert df.loc["Solar", "mw"] == 140 and df.loc["Solar", "disponible_mw"] == 170  # 90 (último) + 50
    assert df.loc["Eólica", "mw"] == 30


def test_demanda_pid_usa_ultima_reprogramacion():
    rows = [{"llave_dem": "A", "fecha_hora": "2026-11-18 10:00:00", "demanda_prog_mw": mw,
             "fecha_programa": "2026-11-18", "hora_programa": hp} for mw, hp in [(100, 2), (130, 8), (110, 5)]]
    assert T.demanda_prog_total(rows)["mw"].tolist() == [130]


def test_gen_programada_todas_las_tecnologias():
    rows = [{"llave_gen": "T1", "tipo_tecnologia": "Térmicas", "gen_programada_mw": 500, "capacidad_disponible_mw": 600,
             "fecha_hora": "2026-11-18 12:00:00", "fecha_programa": "2026-11-18"},
            {"llave_gen": "S1", "tipo_tecnologia": "Solares", "gen_programada_mw": 90, "capacidad_disponible_mw": 100,
             "fecha_hora": "2026-11-18 12:00:00", "fecha_programa": "2026-11-18"}]
    assert set(T.gen_programada_erv(rows, tecnologias=None)["tecnologia"]) == {"Térmica", "Solar"}
    assert set(T.gen_programada_erv(pd.DataFrame(rows))["tecnologia"]) == {"Solar"}


def test_embalses_y_desviacion():
    e = T.embalses_df([{"nombre": "Ralco", "fecha": 1794985200000, "cotaActual": 700.0, "cotaMax": 725,
                        "cotaMin": 692, "porcentajeActual": 40.0},
                       {"nombre": "Colbún", "fecha": 1794985200000, "cotaActual": 430.0, "cotaMax": 437,
                        "cotaMin": 397, "porcentajeActual": 80.0}])
    assert list(e["embalse"]) == ["Colbún", "Ralco"] and e["fecha"].dt.tz is None
    ts = pd.to_datetime(["2026-11-18 10:00", "2026-11-18 11:00"])
    d = T.desviacion(pd.DataFrame({"ts": ts, "mw": [100.0, 0.0]}), pd.DataFrame({"ts": ts, "mw": [110.0, 5.0]}))
    assert d["desv_mw"].tolist() == [10.0, 5.0] and d.loc[0, "desv_pct"] == 10.0 and pd.isna(d.loc[1, "desv_pct"])


def test_sscc_df():
    rows = [{"fecha": "2026-11-18", "inicioPeriodo": "08:40:00", "finPeriodo": "08:52:00", "instruccionSscc": "CTF(-)",
             "centralSubestacion": "RALCO", "centralUnidad": "RALCO-1", "baja": 11.0, "sube": None,
             "motivo": "Activación CTF (-)."}]
    s = T.sscc_df(rows).iloc[0]
    assert s["inicio"] == pd.Timestamp("2026-11-18 08:40") and s["unidad"] == "RALCO-1" and s["baja_mw"] == 11


def test_capacidad_y_factor_de_planta():
    unidades = [
        {"nombre_tecnologia": "Fotovoltaica", "pot_neta_efectiva": "100,5", "pot_max_bruta": "101"},
        {"nombre_tecnologia": "Fotovoltaica + SAE", "pot_neta_efectiva": None, "pot_max_bruta": "99,5"},
        {"nombre_tecnologia": "Motor de Combustión Interna", "pot_neta_efectiva": "50", "pot_max_bruta": "51"},
        {"nombre_tecnologia": "Sin Asignar", "pot_neta_efectiva": "9", "pot_max_bruta": "9"},
    ]
    cap = T.capacidad_por_tecnologia(unidades).set_index("tecnologia")
    assert cap.loc["Solar", "mw"] == 200 and cap.loc["Térmica", "mw"] == 50 and len(cap) == 2
    gen = T.gen_df([_gen_row("2026-11-18 10:00:00", "PFV", "Solar", 100), _gen_row("2026-11-18 11:00:00", "PFV", "Solar", 60),
                    _gen_row("2026-11-18 10:00:00", "TER", "Térmica", 25), _gen_row("2026-11-18 11:00:00", "TER", "Térmica", 25)])
    f = T.factor_planta(gen, cap.reset_index()).set_index("tecnologia")
    assert f.loc["Solar", "factor_pct"] == 40 and f.loc["Térmica", "factor_pct"] == 50


def test_reporte_generacion():
    payload = {"content": [{"description": "Hidráulica", "dailyCurrent": 198.5, "monthlyCurrentTodate": 3306.2,
                            "annualCurrentTodate": 41668.3, "date": "2026-11-17"},
                           {"description": "BESS", "dailyCurrent": 37.2, "monthlyCurrentTodate": 687.4,
                            "annualCurrentTodate": 8824.3, "date": "2026-11-17"}]}
    r = T.reporte_generacion_df(payload)
    assert list(r["tecnologia"]) == ["Hidráulica", "BESS"] and r.loc[0, "mes_gwh"] == 3306.2


def test_mantenimientos_y_solicitudes_activos_en_el_dia():
    m = [{"fecha_inicio_programa": "2026-10-29 00:00:00.0", "fecha_fin_programa": "2026-12-22 23:59:59.0",
          "nombre_instalacion": "S/E FLORIDA", "descripcion_trabajo": "x"},
         {"fecha_inicio_programa": "2026-11-20 00:00:00.0", "fecha_fin_programa": "2026-11-21 23:59:59.0",
          "nombre_instalacion": "S/E ALTO JAHUEL", "descripcion_trabajo": "y"}]
    assert list(T.mantenimientos_df(m, pd.Timestamp("2026-11-18").date())["instalacion"]) == ["S/E FLORIDA"]
    s = [{"fecha_inicio": "2026-11-18 08:00:00", "fecha_fin": "2026-11-18 20:00:00", "instalacion_nombre": "L1",
          "empresa_nombre": "E", "tipo_solicitud": "desconexion", "type": "linea", "status": "pendiente", "consumo": "no"},
         {"fecha_inicio": "2026-12-02 08:00:00", "fecha_fin": "2026-12-02 20:00:00", "instalacion_nombre": "L2",
          "empresa_nombre": "E", "tipo_solicitud": "desconexion", "type": "linea", "status": "pendiente", "consumo": "no"}]
    assert list(T.solicitudes_df(s, pd.Timestamp("2026-11-18").date())["instalacion"]) == ["L1"]


def test_demanda_descarta_parciales_sin_generacion_para_comparar():
    # la generación real llega solo hasta las 04:00; las 05 y 06 oficiales caen bruscamente: son parciales
    dem = T.demanda_df([{"fecha_hora": f"2026-11-18 0{h}:00:00", "gen_bruta_mwh": v}
                        for h, v in [(3, 8341), (4, 8265), (5, 6073), (6, 5452)]])
    gen_tot = pd.DataFrame({"ts": pd.to_datetime(["2026-11-18 03:00", "2026-11-18 04:00"]), "mw": [9000.0, 8900.0]})
    assert list(T.recortar_horas_parciales(dem, gen_tot)["ts"].dt.hour) == [3, 4]
    # una bajada normal (nocturna, < 20 %) no se descarta
    dem2 = T.demanda_df([{"fecha_hora": f"2026-11-18 0{h}:00:00", "gen_bruta_mwh": v} for h, v in [(0, 9200), (1, 8800)]])
    assert len(T.recortar_horas_parciales(dem2, pd.DataFrame(columns=["ts", "mw"]))) == 2


def test_normaliza_nombres_del_programa_pcp():
    assert T.normalizar_tecnologia("Hidroeléctricas") == "Hidráulica"
    assert T.normalizar_tecnologia("Termoeléctricas") == "Térmica"
    assert T.normalizar_tecnologia("Termosolar") == "Solar"
    assert T.normalizar_tecnologia("Solares") == "Solar" and T.normalizar_tecnologia("BESS") == "BESS"


def test_motivo_y_accion_de_almacenamiento():
    assert T.limpiar_motivo("C omienza  descarga ") == "Comienza descarga"
    assert T.accion_almacenamiento("Comienza carga") == "Comienza carga"
    assert T.accion_almacenamiento("Termina  descarga") == "Termina descarga"
    assert T.accion_almacenamiento("P. Disp. = 0 MW; origen: SITR") is None
    df = T.instrucciones_df([{"fecha": "2026-11-17 00:00:00", "hora": "09:00:00", "central": "BESS X", "despacho": 10,
                              "consigna": "CI", "instruccion_cmg": "CI", "motivo": "C omienza carga"}])
    assert df.iloc[0]["accion"] == "Comienza carga" and df.iloc[0]["motivo"] == "Comienza carga"
