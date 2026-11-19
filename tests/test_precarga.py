import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cen import endpoints as E  # noqa: E402


def test_precarga_recorre_fuentes_tolera_errores_y_no_se_duplica(monkeypatch):
    hechas = []

    def lenta(nombre):
        time.sleep(0.2)
        hechas.append(nombre)

    def falla():
        raise RuntimeError("HTTP 429")

    tareas = [("a", lenta, ("a",)), ("b", falla, ()), ("c", lenta, ("c",))]
    monkeypatch.setattr(E, "_tareas_dia", lambda dia, barras: tareas)
    monkeypatch.setattr(E, "ESPERA_REINTENTO", 0)
    E._PRECARGAS.clear()

    est = E.precargar_dia(date(2026, 11, 9), ["X"], espera=0.05)
    assert est.activo and est.total == 3
    assert E.precargar_dia(date(2026, 11, 9), ["X"], espera=0) is est  # no lanza otra descarga
    for _ in range(50):
        if not est.activo:
            break
        time.sleep(0.05)
    assert not est.activo and est.hechos == 3 and hechas == ["a", "c"]
    assert len(est.errores) == 1 and "429" in est.errores[0]


def test_precarga_instantanea_si_todo_en_cache(monkeypatch):
    monkeypatch.setattr(E, "_tareas_dia", lambda dia, barras: [("a", lambda: None, ())])
    E._PRECARGAS.clear()
    est = E.precargar_dia(date(2026, 11, 8), [], espera=0.5)
    assert not est.activo and est.hechos == 1  # la página no muestra barra de progreso


def test_precarga_reintenta_una_vez_lo_que_fallo(monkeypatch):
    intentos = []

    def falla_una_vez():
        intentos.append(1)
        if len(intentos) == 1:
            raise RuntimeError("HTTP 429")

    monkeypatch.setattr(E, "_tareas_dia", lambda dia, barras: [("x", falla_una_vez, ())])
    monkeypatch.setattr(E, "ESPERA_REINTENTO", 0)
    E._PRECARGAS.clear()
    est = E.precargar_dia(date(2026, 11, 7), [], espera=1)
    assert not est.activo and est.hechos == 1 and est.errores == [] and len(intentos) == 2


def test_historial_cmg_lee_solo_cache(monkeypatch):
    import pandas as pd
    from cen import transform as T
    llamadas = []
    monkeypatch.setattr(E, "cmg_online", lambda *a, **k: llamadas.append(a))
    df_a = T.cmg_df([{"barra_transf": "A", "barra_info": "A", "fecha_minuto": "2026-11-10 00:00",
                      "cmg_usd_mwh_": 5, "cmg_clp_kwh_": 5}])
    vistos = []

    def falso_peek(ns, key, ttl="default"):
        vistos.append((ns, key))
        return E.Cached(df_a, 0) if key.startswith("A_") else None

    monkeypatch.setattr(E, "peek", falso_peek)
    E._PRECARGAS.clear()
    df, est = E.historial_cmg(["A", "B"], date(2026, 11, 17))
    assert set(df["barra_transf"]) == {"A"}  # B aún no descargada: no bloquea
    # 7 días previos (guardados uno por uno), sin incluir el día
    assert ("cmg_online_dia", "A_2026-11-10") in vistos and ("cmg_online_dia", "A_2026-11-16") in vistos
    assert ("cmg_online_dia", "A_2026-11-17") not in vistos
    for _ in range(40):
        if not est.activo:
            break
        time.sleep(0.05)
    assert len(llamadas) == 2 and est.total == 2


def test_cmg_online_guarda_por_dia_y_pide_solo_lo_que_falta(monkeypatch, tmp_path):
    """Una consulta trae varios días; cada uno queda guardado y luego no se vuelve a pedir."""
    from cen import cache as CA

    monkeypatch.setattr(CA, "CACHE_DIR", tmp_path)
    pedidos = []

    class Falso:
        def get_all_v4(self, path, limit, startDate, endDate, bar_transf, **k):
            pedidos.append((startDate, endDate))
            d0, d1 = date.fromisoformat(startDate), date.fromisoformat(endDate)
            return [{"barra_transf": bar_transf, "barra_info": "X", "cmg_usd_mwh_": 10, "cmg_clp_kwh_": 1,
                     "fecha_minuto": f"{d0 + timedelta(days=i)} {h:02d}:00"}
                    for i in range((d1 - d0).days + 1) for h in range(24)]

    cli = Falso()
    r = E.cmg_online("X", date(2026, 11, 1), date(2026, 11, 8), client=cli)
    assert pedidos == [("2026-11-01", "2026-11-08")] and len(r.value) == 8 * 24
    r = E.cmg_online("X", date(2026, 11, 7), date(2026, 11, 8), client=cli)   # ya guardado: sin consultas
    assert len(pedidos) == 1 and len(r.value) == 2 * 24
    r = E.cmg_online("X", date(2026, 10, 30), date(2026, 11, 2), client=cli)  # solo faltan 30 y 31
    assert pedidos[1] == ("2026-10-30", "2026-10-31") and len(r.value) == 4 * 24


def test_barra_nueva_no_hace_esperar_a_la_pagina(monkeypatch, tmp_path):
    """Al agregar una barra, las ya guardadas se devuelven al tiro y la nueva se descarga en segundo plano."""
    import threading
    from cen import cache as CA

    monkeypatch.setattr(CA, "CACHE_DIR", tmp_path)
    E._HILOS_CMG.clear()
    soltar = threading.Event()

    class Falso:
        def get_all_v4(self, path, limit, startDate, endDate, bar_transf, **k):
            if bar_transf == "NUEVA":
                soltar.wait(5)  # la API tarda en responder
            d0, d1 = date.fromisoformat(startDate), date.fromisoformat(endDate)
            return [{"barra_transf": bar_transf, "barra_info": "X", "cmg_usd_mwh_": 1, "cmg_clp_kwh_": 1,
                     "fecha_minuto": f"{d0 + timedelta(days=i)} 00:00"} for i in range((d1 - d0).days + 1)]

    cli = Falso()
    d0, d1 = date(2026, 11, 1), date(2026, 11, 2)
    E.cmg_online("VIEJA", d0, d1, client=cli)                    # ya guardada
    t = time.time()
    df, _, err, pend = E.cmg_online_multi(["VIEJA", "NUEVA"], d0, d1, client=cli)
    assert time.time() - t < 2 and pend == ["NUEVA"] and err == []
    assert set(df["barra_transf"]) == {"VIEJA"}
    soltar.set()
    E._HILOS_CMG[f"NUEVA_{d0}_{d1}"].join(5)
    df, _, err, pend = E.cmg_online_multi(["VIEJA", "NUEVA"], d0, d1, client=cli)
    assert pend == [] and set(df["barra_transf"]) == {"VIEJA", "NUEVA"}
