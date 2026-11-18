import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cen import charts as C  # noqa: E402


def test_nombre_serie():
    assert C.nombre_serie("TARAPACA______220") == "TARAPACA 220"
    assert C.nombre_serie("P.MONTT_______220") == "P.MONTT 220"


def test_opciones_cmg_destaca_y_comparte_color_con_programado():
    ts = pd.to_datetime(["2026-11-17 00:00", "2026-11-17 00:15"])
    live = pd.DataFrame({"ts": list(ts) * 2, "serie": ["A", "A", "B", "B"], "usd_mwh": [1, 2, 3, None]})
    prog = pd.DataFrame({"ts": pd.to_datetime(["2026-11-18 00:00"]), "serie": ["A"], "usd_mwh": [5.0]})
    o = C.opciones_cmg(live, "usd_mwh", "USD/MWh", prog, separadores=[date(2026, 11, 17)])
    s = {x["id"]: x for x in o["series"]}
    assert set(s) == {"live-A", "live-B", "pcp-A", "separadores"}
    assert s["live-A"]["emphasis"]["focus"] == "series" and s["live-A"]["triggerLineEvent"]
    assert s["pcp-A"]["lineStyle"]["color"] == s["live-A"]["lineStyle"]["color"]
    assert s["pcp-A"]["lineStyle"]["type"] == "dashed"
    assert s["live-B"]["data"][1] == ["2026-11-17T00:15:00", None]
    assert o["legend"]["data"] == ["A", "B"]
    assert s["separadores"]["markLine"]["data"][0]["label"]["formatter"] == "17-11-2026"


COL = {"Solar": "#F2B701", "Térmica": "#6B6B6B", "BESS": "#7E57C2"}


def test_gen_tecnologia_apila_en_orden_y_marca_hora_incompleta():
    agg = pd.DataFrame({"ts": pd.to_datetime(["2026-11-17 10:00", "2026-11-17 10:00", "2026-11-17 11:00"]),
                        "tecnologia": ["Térmica", "Solar", "Solar"], "mw": [10.0, 20.0, 30.0]})
    o = C.opciones_gen_tecnologia(agg, COL, ["Solar", "Térmica"],
                                  incompleta=(pd.Timestamp("2026-11-17 11:00"), pd.Timestamp("2026-11-17 12:00")))
    s = [x for x in o["series"] if x["name"]]
    assert [x["name"] for x in s] == ["Solar", "Térmica"]
    assert all(x["stack"] == "gen" and x["emphasis"]["focus"] == "series" for x in s)
    assert s[1]["data"][1] == ["2026-11-17T11:00:00", 0.0]  # hora sin térmica = 0 (apilado continuo)
    assert "markArea" in o["series"][-1]


def test_top10_una_serie_por_tecnologia_con_datos_para_tooltip():
    top = pd.DataFrame({"central": ["A", "B", "C"], "propietario": ["X", "Y", "Z"],
                        "tecnologia": ["Solar", "BESS", "Solar"], "mw": [30, 20, 10],
                        "pct": [3.0, 2.0, 1.0], "pct_acum": [3.0, 5.0, 6.0]})
    o = C.opciones_top10(top, COL, "mw", "MW")
    assert o["yAxis"]["data"] == ["A", "B", "C"] and o["yAxis"]["inverse"]
    solar = next(x for x in o["series"] if x["name"] == "Solar")
    assert solar["data"][1] is None
    assert solar["data"][0] == {"value": 3.0, "propietario": "X", "mw": 30.0, "pct_acum": 3.0}


def test_demanda_serie_horaria_y_opciones():
    v = C.serie_horaria(pd.to_datetime(["2026-11-17 00:00", "2026-11-17 05:00"]), pd.Series([1.0, 2.0]))
    assert v[0] == 1.0 and v[5] == 2.0 and v[23] is None and len(v) == 24
    o = C.opciones_demanda([{"name": "hoy", "data": v, "color": "#1F5FA8", "area": True},
                            {"name": "est", "data": v, "color": "#1F5FA8", "estilo": "dashed"}])
    assert o["series"][0]["areaStyle"] and o["series"][1]["lineStyle"]["type"] == "dashed"
    assert o["xAxis"]["data"][0] == "00:00" and o["legend"]["data"] == ["hoy", "est"]


def test_dona():
    ds = pd.DataFrame({"tecnologia": ["Solar", "BESS"], "valor": [100.0, 50.0]})
    o = C.opciones_dona(ds, COL)
    assert [d["name"] for d in o["series"][0]["data"]] == ["Solar", "BESS"]
    assert o["series"][0]["emphasis"]["focus"] == "self"


def test_mapa_cero_y_tendencia():
    m = pd.DataFrame({h: [None] * 2 for h in range(24)}, index=["A", "B"])
    m.loc["A", 13] = 45
    o = C.opciones_mapa_cero(m, {"A": "A 220", "B": "B 220"}, [None] * 12 + [900.0] + [None] * 11, 1.0)
    hm = o["series"][0]
    assert hm["type"] == "heatmap" and [13, 0, 45] in hm["data"] and [0, 1, None] in hm["data"]
    assert o["yAxis"][0]["data"] == ["A 220", "B 220"] and o["series"][1]["data"][12] == 900.0
    sp = pd.DataFrame({"barra_transf": ["A", "A", "B"], "dia": [date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 17)],
                       "spread": [10.0, 20.0, 5.0]})
    t = C.opciones_spread_tendencia(sp, {"A": "A 220"})
    assert t["xAxis"]["data"] == ["16-11", "17-11"]
    assert t["series"][0]["data"] == [10.0, 20.0] and t["series"][1]["data"] == [None, 5.0]
    assert t["series"][0]["emphasis"]["focus"] == "series"


def test_cmg_con_pcp_y_pid():
    ts = pd.to_datetime(["2026-11-18 00:00"])
    live = pd.DataFrame({"ts": ts, "serie": ["A"], "usd_mwh": [1.0]})
    pcp = pd.DataFrame({"ts": ts, "serie": ["A"], "usd_mwh": [2.0]})
    pid = pd.DataFrame({"ts": ts, "serie": ["A"], "usd_mwh": [3.0]})
    o = C.opciones_cmg(live, "usd_mwh", "USD/MWh", pcp, pid=pid)
    s = {x["id"]: x for x in o["series"]}
    assert s["pcp-A"]["lineStyle"]["type"] == "dashed" and s["pid-A"]["lineStyle"]["type"] == "dotted"
    assert s["pid-A"]["lineStyle"]["color"] == s["live-A"]["lineStyle"]["color"]


def test_opciones_erv():
    ts = pd.to_datetime(["2026-11-18 12:00", "2026-11-18 12:00"])
    erv = pd.DataFrame({"ts": ts, "tecnologia": ["Solar", "Eólica"], "mw": [900.0, 100.0], "disponible_mw": [1000.0, 150.0]})
    real = pd.DataFrame({"ts": ts[:1], "tecnologia": ["Solar"], "mw": [850.0]})
    o = C.opciones_erv(erv, real, {"Solar": "#F2B701", "Eólica": "#3BA3D0"})
    s = {x["id"]: x for x in o["series"]}
    assert s["prog-Solar"]["stack"] == "erv" and s["disp"]["data"][0][1] == 1150
    assert s["real"]["data"][0][1] == 850


def test_barras_agrupadas():
    o = C.opciones_barras_agrupadas(["Solar", "Térmica"], {"Programado": [10, 20], "Real": [12, None]},
                                    {"Programado": "#999999", "Real": "#1F5FA8"}, "MWh")
    assert o["xAxis"]["data"] == ["Solar", "Térmica"] and o["series"][1]["data"] == [12.0, None]
    assert o["series"][0]["emphasis"]["focus"] == "series"
