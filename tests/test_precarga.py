import sys
import time
from datetime import date
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
    assert list(df["barra_transf"]) == ["A"]  # B aún no descargada: no bloquea
    assert ("cmg_online", "A_2026-11-10_2026-11-16") in vistos  # 7 días previos, sin incluir el día
    for _ in range(40):
        if not est.activo:
            break
        time.sleep(0.05)
    assert len(llamadas) == 2 and est.total == 2
