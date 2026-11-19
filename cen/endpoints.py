"""Funciones por endpoint, con caché en disco. Devuelven DataFrames listos (vía ``transform``)."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
import threading
from datetime import date, timedelta

import pandas as pd

from . import transform as T
from .cache import Cached, SinCache, cached, guardar, modo_solo_cache, peek, solo_cache_activo
from .client import PRIO_BAJA, PRIO_FONDO, PRIO_PAGINA, CENClient, default_client, fijar_prioridad, reservar

log = logging.getLogger(__name__)

P_CMG_ONLINE = "costo-marginal-online/v4/findByDate"
P_CMG_8B = "costos-marginales-online-8b/v4/findAll"
P_CMG_PCP = "cmg-programado-pcp/v4/findByDate"
P_CMG_REAL = "costo-marginal-real/v4/findByDate"
P_GEN_REAL = "generacion-real/v3/findByDate"
P_GEN_SUM = "generacion-real/v3/getDailySum"
P_DEM_NETA = "demanda-neta/v4/findByDate"
P_DEM_PROG = "demanda-programada-pcp/v4/findByDate"
P_CMG_PID = "cmg-programado-pid/v4/findByDate"
P_INSTR_CMG = "instrucciones-operacionales-cmg/v4/findByDate"
P_GEN_PCP = "generacion-programada-pcp/v4/findByDate"
P_EMBALSES = "embalse-real/v3/findLast"
P_UNIDADES = "unidades-generadoras/v4/findByDate"
P_DEM_PID = "demanda-programada-pid/v4/findByDate"
P_PRON_DEM = "pronosticos-demanda-mediano-plazo/v4/findByDate"
P_MANT = "programas-mantenimiento-mayor/v4/findByDate"
P_SOLIC = "solicitudes-trabajo/v4/findByDate"
OP_REPORTE_GEN = "reportes/v3/generation"   # servicio Operación
OP_SSCC = "servicios-complementarios/v1"     # servicio Operación

CATALOGO_PAGE = 2000  # filas por página al armar el catálogo de barras
CATALOGO_MAX_PAGES = 3


def _c(client: CENClient | None) -> CENClient:
    return client or default_client()


def _d(x: date | str) -> str:
    return x if isinstance(x, str) else x.isoformat()


def _es_pasado(d: date | str) -> bool:
    return date.fromisoformat(_d(d)) < date.today()


# ------------------------------------------------------------------- CMg
CMG_LIMIT = 2000  # filas por página: 20 días de una barra (96 cuartos de hora por día) en una consulta


def _dias(desde: date, hasta: date) -> list[date]:
    return [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]


def _cmg_dia_listo(d: date) -> bool:
    """Un día pasado se guarda para siempre cuando ya está completo (ayer, desde las 2 a. m.)."""
    from datetime import datetime
    return d < date.today() - timedelta(days=1) or (d < date.today() and datetime.now().hour >= 2)


def _cmg_cache_dias(barra: str, dias: list[date]) -> tuple[list[pd.DataFrame], list[float], list[date]]:
    """CMg guardado por día de ``barra``: (DataFrames, fechas de consulta, días que faltan)."""
    dfs, fechas, faltan = [], [], []
    for d in dias:
        r = peek("cmg_online_dia", f"{barra}_{d}", ttl=None)
        if r is None:
            faltan.append(d)
        else:
            dfs.append(r.value)
            fechas.append(r.fetched_at)
    return dfs, fechas, faltan


_CANDADOS_BARRA: dict[str, threading.Lock] = {}
_CANDADOS_LOCK = threading.Lock()


def _candado_barra(barra: str) -> threading.Lock:
    with _CANDADOS_LOCK:
        return _CANDADOS_BARRA.setdefault(barra, threading.Lock())


def cmg_online(barra: str, desde: date, hasta: date, client=None, force=False) -> Cached:
    """CMg en línea (15 min) de una barra entre ``desde`` y ``hasta``.

    La API no admite varias barras por consulta y limita las consultas por segundo, así que se pide lo
    mínimo: los días pasados se guardan uno por uno (para siempre) y los que falten se piden juntos en una
    sola consulta; el día de hoy se pide aparte y se renueva cada 15 min.
    """
    desde, hasta = date.fromisoformat(_d(desde)), date.fromisoformat(_d(hasta))
    pasados = [d for d in _dias(desde, hasta) if _cmg_dia_listo(d)]
    recientes = [d for d in _dias(desde, hasta) if not _cmg_dia_listo(d)]  # hoy (y ayer de madrugada)
    partes: list[Cached] = []
    dfs, fechas, faltan = _cmg_cache_dias(barra, pasados)
    if force:
        faltan = pasados
    if faltan:
        if solo_cache_activo():
            raise SinCache(f"CMg {barra} aún no descargado")
        # un hilo por barra a la vez: si otro ya la está descargando, se espera y se usa lo que guardó
        with _candado_barra(barra):
            if not force:
                dfs, fechas, faltan = _cmg_cache_dias(barra, pasados)
            if faltan:
                ini, fin = faltan[0], faltan[-1]

                def fetch_rango():
                    rows = _c(client).get_all_v4(P_CMG_ONLINE, limit=CMG_LIMIT, startDate=_d(ini),
                                                 endDate=_d(fin), bar_transf=barra)
                    df = T.cmg_df(rows)
                    por_dia = ({d: g.reset_index(drop=True) for d, g in df.groupby(df["ts"].dt.date)}
                               if not df.empty else {})
                    for d in _dias(ini, fin):
                        if d != ini:
                            guardar("cmg_online_dia", f"{barra}_{d}", por_dia.get(d, T.cmg_df([])))
                    return por_dia.get(ini, T.cmg_df([]))
                # una sola consulta para todos los días que faltan (con la caché negativa de ``cached``): el
                # primer día queda en su archivo y los demás los guarda ``fetch_rango``
                cached("cmg_online_dia", f"{barra}_{ini}", fetch_rango, ttl=None, force=force)
                dfs, fechas, faltan = _cmg_cache_dias(barra, pasados)
    if dfs:
        partes.append(Cached(pd.concat(dfs, ignore_index=True), min(fechas), from_cache=True))
    if recientes:
        def fetch_reciente():
            rows = _c(client).get_all_v4(P_CMG_ONLINE, limit=CMG_LIMIT, startDate=_d(recientes[0]),
                                         endDate=_d(recientes[-1]), bar_transf=barra)
            return T.cmg_df(rows)
        partes.append(cached("cmg_online", f"{barra}_{recientes[0]}_{recientes[-1]}", fetch_reciente,
                             force=force, background=True))
    if not partes:
        return Cached(T.cmg_df([]), time.time())
    valor = pd.concat([p.value for p in partes if not p.value.empty] or [T.cmg_df([])], ignore_index=True)
    return Cached(valor, min(p.fetched_at for p in partes), stale=any(p.stale for p in partes),
                  from_cache=all(p.from_cache for p in partes), refreshing=any(p.refreshing for p in partes))


def _cmg_en_cache(barra: str, desde: date, hasta: date) -> bool:
    """True si el CMg de la barra ya está guardado (aunque esté vencido): leerlo no consulta la API."""
    previo = solo_cache_activo()
    modo_solo_cache(True)
    try:
        cmg_online(barra, desde, hasta)
        return True
    except SinCache:
        return False
    finally:
        modo_solo_cache(previo)


_HILOS_CMG: dict[str, threading.Thread] = {}
_ERRORES_CMG: dict[str, str] = {}


def _cmg_vencido(barra: str, desde: date, hasta: date) -> bool:
    """True si la parte reciente (hoy) del CMg de la barra ya pasó su vigencia (o no está)."""
    rec = [d for d in _dias(date.fromisoformat(_d(desde)), date.fromisoformat(_d(hasta))) if not _cmg_dia_listo(d)]
    return bool(rec) and peek("cmg_online", f"{barra}_{rec[0]}_{rec[-1]}") is None


def cmg_actualizando() -> bool:
    """True si hay descargas de CMg en curso (para que la página se refresque sola al terminar)."""
    return any(h.is_alive() for h in list(_HILOS_CMG.values()))


def cmg_online_multi(barras: list[str], desde: date, hasta: date, client=None,
                     force=False) -> tuple[pd.DataFrame, float | None, list[str], list[str]]:
    """CMg de varias barras sin hacer esperar a la página: la página solo lee lo guardado.

    Lo que falta (p. ej. una barra recién agregada) o ya venció (el CMg de hoy, cada 15 min) se descarga en un
    hilo por barra, y aparece en el siguiente refresco. Mientras se actualiza, se muestra la copia anterior.
    Devuelve: df, fecha de la consulta más antigua, errores, barras que aún no tienen datos (descargándose).
    """
    dfs, errores, fetched, pendientes = [], [], [], []
    for b in barras:
        clave = f"{b}_{_d(desde)}_{_d(hasta)}"
        en_cache = _cmg_en_cache(b, desde, hasta)
        if not solo_cache_activo() and (force or not en_cache or _cmg_vencido(b, desde, hasta)):
            hilo = _HILOS_CMG.get(clave)
            if clave in _ERRORES_CMG and (hilo is None or not hilo.is_alive()):
                # falló: se informa una vez (si no hay copia que mostrar) y se reintenta en el siguiente refresco
                err = _ERRORES_CMG.pop(clave)
                _HILOS_CMG.pop(clave, None)
                if not en_cache:
                    errores.append(f"{b}: {err}")
            elif hilo is None or not hilo.is_alive():
                def run(b=b, clave=clave):
                    try:
                        cmg_online(b, desde, hasta, client=client, force=force)
                    except Exception as exc:
                        log.warning("CMg en línea %s: %s", b, exc)
                        _ERRORES_CMG[clave] = str(exc)
                _HILOS_CMG[clave] = threading.Thread(target=run, name=f"cmg-{clave}", daemon=True)
                _HILOS_CMG[clave].start()
                _HILOS_CMG[clave].join(0.3)  # si estaba casi listo, se muestra ya
                en_cache = en_cache or _cmg_en_cache(b, desde, hasta)
        if not en_cache:
            pendientes.append(b)
            continue
        previo = solo_cache_activo()
        modo_solo_cache(True)  # leer sin consultar la API, pase lo que pase
        try:
            r = cmg_online(b, desde, hasta)
            dfs.append(r.value)
            fetched.append(r.fetched_at)
        except SinCache:
            pendientes.append(b)
        except Exception as exc:  # una barra que falla no tumba el resto
            log.exception("CMg en línea %s", b)
            errores.append(f"{b}: {exc}")
        finally:
            modo_solo_cache(previo)
    df = pd.concat(dfs, ignore_index=True) if dfs else T.cmg_df([])
    return df, (min(fetched) if fetched else None), errores, pendientes


def cmg_8b(client=None, force=False) -> Cached:
    return cached("cmg_8b", "ultimo", lambda: T.cmg_8b_df(_c(client).get(P_CMG_8B)), force=force, background=True)


def cmg_pcp(dia: date, client=None, force=False) -> Cached:
    """CMg programado PCP de un día completo (todas las barras; se filtra localmente)."""
    def fetch():
        rows = _c(client).get_all_v4(P_CMG_PCP, limit=5000, first_page=1, startDate=_d(dia), endDate=_d(dia))
        return T.cmg_pcp_df(rows)
    return cached("cmg_pcp", _d(dia), fetch, force=force, background=True)


def cmg_real(barra: str, desde: date, hasta: date, tipo: str = "DEFINITIVO", client=None, force=False) -> Cached:
    def fetch():
        rows = _c(client).get_all_v4(P_CMG_REAL, limit=1000, startDate=_d(desde), endDate=_d(hasta),
                                     bar_transf=barra, type=tipo)
        return T.cmg_df(rows)
    return cached("cmg_real", f"{barra}_{tipo}_{_d(desde)}_{_d(hasta)}", fetch, force=force)


def catalogo_barras(client=None, force=False) -> Cached:
    """Catálogo barra_transf + barra_info, armado con el CMg en línea de ayer.

    Las filas vienen ordenadas por hora, así que las primeras ~1.654 filas (00:00) ya
    contienen todas las barras; se leen unas pocas páginas grandes y se corta ahí.
    """
    def fetch():
        ayer = date.today() - timedelta(days=1)
        rows: list[dict] = []
        vistos: set[str] = set()
        for data in _c(client).iter_pages(P_CMG_ONLINE, first_page=0, size_param="limit",
                                          page_size=CATALOGO_PAGE, max_pages=CATALOGO_MAX_PAGES,
                                          startDate=_d(ayer), endDate=_d(ayer)):
            nuevos = {r.get("barra_transf"): r for r in data if r.get("barra_transf") not in vistos}
            rows.extend(nuevos.values())
            vistos.update(nuevos)
            # si la página ya repite barras, se pasó al siguiente cuarto de hora: catálogo completo
            if len(nuevos) < len(data):
                break
        return T.catalogo_barras(rows)
    return cached("barras", "catalogo", fetch, force=force, background=True)


# ------------------------------------------------------------ generación
def gen_real(dia: date, client=None, force=False) -> Cached:
    """Generación real horaria por central de un día (todas las páginas)."""
    def fetch():
        rows = _c(client).get_all_v3(P_GEN_REAL, page_size=5000, startDate=_d(dia), endDate=_d(dia))
        return T.gen_df(rows)
    ns = "gen_real_pasado" if _es_pasado(dia) and dia < date.today() - timedelta(days=1) else "gen_real_hoy"
    return cached(ns, _d(dia), fetch, force=force, background=True)


def daily_sum(dia: date, client=None, force=False) -> Cached:
    return cached("daily_sum", _d(dia), lambda: _c(client).get(P_GEN_SUM, date=_d(dia)), force=force, background=True)


# --------------------------------------------------------------- demanda
def demanda_neta(desde: date, hasta: date, client=None, force=False) -> Cached:
    def fetch():
        # Este endpoint trata endDate como "ese día a las 00:00": se pide hasta+1 y se recorta.
        fin = date.fromisoformat(_d(hasta)) + timedelta(days=1)
        rows = _c(client).get_all_v4(P_DEM_NETA, limit=200, startDate=_d(desde), endDate=_d(fin))
        df = T.demanda_df(rows)
        return df[df["ts"] < pd.Timestamp(fin)].reset_index(drop=True)
    return cached("demanda_neta", f"{_d(desde)}_{_d(hasta)}", fetch, force=force, background=True)


def demanda_prog(dia: date, client=None, force=False) -> Cached:
    def fetch():
        rows = _c(client).get_all_v4(P_DEM_PROG, limit=5000, first_page=1, startDate=_d(dia), endDate=_d(dia))
        return T.demanda_prog_total(rows)
    return cached("demanda_prog", _d(dia), fetch, force=force, background=True)


# ------------------------------------------------- fuentes de la fase 3 (baterías)
# Verificadas en scripts/smoke_test_extra.py: todas numeran páginas desde 1.
def cmg_pid(dia: date, client=None, force=False) -> Cached:
    """CMg programado intradiario (PID) de las horas de ``dia``: última reprogramación por barra y hora.

    Hoy ~4.800 filas (1 página de 5.000); un día pasado ~33.000 (7 páginas).
    """
    def fetch():
        rows = _c(client).get_all_v4(P_CMG_PID, limit=5000, first_page=1, startDate=_d(dia), endDate=_d(dia))
        return T.cmg_pid_df(rows)
    ttl = "default" if not _es_pasado(dia) else 24 * 3600
    return cached("cmg_pid", _d(dia), fetch, ttl=ttl, force=force, background=True)


def instrucciones_cmg(dia: date, client=None, force=False) -> Cached:
    """Instrucciones operacionales por CMg de ``dia`` (se publican con ~1 día de atraso)."""
    def fetch():
        rows = _c(client).get_all_v4(P_INSTR_CMG, limit=5000, first_page=1, startDate=_d(dia), endDate=_d(dia))
        return T.instrucciones_df(rows)
    return cached("instrucciones_cmg", _d(dia), fetch, force=force, background=True)


def erv_programada(dia: date, client=None, force=False) -> Cached:
    """Generación programada PCP (publicado el ``dia``, 7 días hacia adelante) por hora y tecnología.

    Sirve de pronóstico ERV (``pronostico-erv`` no publica datos) y para comparar programado vs real por
    tecnología. Descarga pesada (~309.000 filas, ~62 páginas de 5.000): se procesa página a página en
    DataFrames compactos con solo las columnas necesarias.
    """
    campos = ("llave_gen", "tipo_tecnologia", "gen_programada_mw", "capacidad_disponible_mw", "fecha_hora",
              "fecha_programa")

    def fetch():
        partes: list[pd.DataFrame] = []
        for data in _c(client).iter_pages(P_GEN_PCP, first_page=1, size_param="limit", page_size=5000,
                                          startDate=_d(dia), endDate=_d(dia)):
            if data:
                partes.append(pd.DataFrame(data, columns=list(campos)))
        filas = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=list(campos))
        return T.gen_programada_erv(filas, tecnologias=None)
    return cached("gen_prog", _d(dia), fetch, force=force, background=True)


# ------------------------------------------------------ descarga en segundo plano
# Las descargas PCP pesan ~45.000 filas (9 páginas de ~14 s): no se hacen dentro de la página,
# sino en un hilo; mientras tanto la UI muestra "cargando" y las usa en el siguiente refresco.
_HILOS: dict[str, threading.Thread] = {}
_ERRORES: dict[str, str] = {}


def en_segundo_plano(namespace: str, key: str, fn, *args, **kwargs) -> tuple[Cached | None, str]:
    """Devuelve (datos, estado). estado: 'listo' | 'cargando' | 'error: ...'.

    Si la caché está vigente la devuelve; si no, lanza ``fn`` en un hilo (una sola vez).
    """
    r = peek(namespace, key)
    if r is not None:
        return r, "listo"
    if peek(namespace, key, ttl=None) is not None:
        # hay copia vencida: ``fn`` (con background=True) la devuelve y actualiza en un hilo
        return fn(*args, **kwargs), "listo"
    clave = f"{namespace}/{key}"
    hilo = _HILOS.get(clave)
    if hilo is not None and hilo.is_alive():
        return None, "cargando"
    if clave in _ERRORES and hilo is not None:
        err = _ERRORES.pop(clave)
        _HILOS.pop(clave, None)
        return None, f"error: {err}"

    def run():
        fijar_prioridad(PRIO_FONDO)  # cede el turno a la precarga del día que se está mirando
        try:
            fn(*args, **kwargs)
        except Exception as exc:  # se informa en la siguiente llamada
            log.exception("Descarga en segundo plano %s", clave)
            _ERRORES[clave] = str(exc)

    _HILOS[clave] = threading.Thread(target=run, name=f"bg-{clave}", daemon=True)
    _HILOS[clave].start()
    return None, "cargando"


def cmg_pcp_bg(dia: date) -> tuple[Cached | None, str]:
    return en_segundo_plano("cmg_pcp", _d(dia), cmg_pcp, dia)


def demanda_prog_bg(dia: date) -> tuple[Cached | None, str]:
    return en_segundo_plano("demanda_prog", _d(dia), demanda_prog, dia)


def cmg_pid_bg(dia: date) -> tuple[Cached | None, str]:
    return en_segundo_plano("cmg_pid", _d(dia), cmg_pid, dia)


def instrucciones_cmg_bg(dia: date) -> tuple[Cached | None, str]:
    return en_segundo_plano("instrucciones_cmg", _d(dia), instrucciones_cmg, dia)


def erv_programada_bg(dia: date) -> tuple[Cached | None, str]:
    return en_segundo_plano("gen_prog", _d(dia), erv_programada, dia)


# --------------------------------------------------- precarga de un día pasado
# Ver un día pasado por primera vez exige ~10–20 consultas (generación paginada, demanda, mix y una
# por barra), varios minutos con el límite de la API. Se descargan en un hilo, fuente por fuente
# (cada una queda en caché al terminar), mientras la página muestra lo que ya está listo.
@dataclass
class Precarga:
    dia: date
    total: int
    hechos: int = 0
    actual: str = ""
    errores: list[str] = field(default_factory=list)
    activo: bool = True
    fin: float | None = None


_PRECARGAS: dict[tuple, Precarga] = {}
_DIA_ACTIVO: list[date | None] = [None]  # día que se está mirando (el último elegido en la página)


def marcar_dia_activo(dia: date) -> None:
    """La página lo llama en cada ejecución: la precarga de ese día pasa primero; las de otros días esperan."""
    _DIA_ACTIVO[0] = dia
REINTENTO_PRECARGA = 5 * 60  # s: si terminó con errores, se reintenta pasado este tiempo
ESPERA_REINTENTO = 20  # s de pausa antes de reintentar las fuentes que fallaron


def _tareas_dia(dia: date, barras: list[str]) -> list[tuple]:
    ant = dia - timedelta(days=1)
    t = [("generación real", gen_real, (dia,)),
         ("demanda", demanda_neta, (ant, dia)),
         ("mix del día", daily_sum, (dia,))]
    # una consulta por barra trae el día y los 7 anteriores: así el historial de la pestaña Baterías y los
    # días previos (si luego se miran) ya quedan guardados, sin más consultas
    desde = dia - timedelta(days=DIAS_HISTORIAL)
    # al cambiar las barras elegidas, solo se descargan las que faltan (las demás ya están guardadas)
    t += [(f"CMg {b.split('_')[0]}", cmg_online, (b, desde, dia)) for b in barras
          if _cmg_cache_dias(b, [d for d in _dias(desde, dia) if _cmg_dia_listo(d)])[2]]
    return t


def precargar(clave: tuple, tareas: list[tuple], dia: date, espera: float = 0.6,
              prioridad: int = PRIO_PAGINA) -> Precarga:
    """Lanza (una vez por ``clave``) un hilo que ejecuta ``tareas`` = [(nombre, fn, args), ...] en orden.

    Cada tarea deja su resultado en caché. Las que fallan se reintentan una vez tras una pausa; si aún
    fallan, la precarga se puede relanzar pasados ``REINTENTO_PRECARGA`` segundos. Espera ``espera``
    segundos antes de volver: si todo estaba en caché, termina en ese lapso (la página no muestra progreso).
    """
    est = _PRECARGAS.get(clave)
    if est is not None and (est.activo or not est.errores or time.time() - (est.fin or 0) < REINTENTO_PRECARGA):
        return est
    est = Precarga(dia=dia, total=len(tareas))
    _PRECARGAS[clave] = est

    def prio() -> int:  # si el usuario cambió de día, esta precarga deja pasar a la del día nuevo
        return prioridad if _DIA_ACTIVO[0] in (None, dia) else PRIO_BAJA

    def run():
        fijar_prioridad(prio)
        # mientras sea el día que se mira, las descargas de fondo esperan a que termine
        with reservar(lambda: prio() == PRIO_PAGINA):
            _ejecutar()

    def _ejecutar():
        try:
            fallidas = []
            for nombre, fn, args in tareas:
                est.actual = nombre
                try:
                    fn(*args)
                    est.hechos += 1
                except Exception as exc:  # una fuente que falla no detiene las demás
                    log.warning("Precarga %s %s: %s", dia, nombre, exc)
                    fallidas.append((nombre, fn, args))
            if fallidas:  # un reintento tras una pausa (casi siempre son 429 por el límite de consultas)
                est.actual = "reintentando " + ", ".join(n for n, _, _ in fallidas)
                time.sleep(ESPERA_REINTENTO)
                for nombre, fn, args in fallidas:
                    try:
                        fn(*args)
                    except Exception as exc:
                        log.warning("Precarga %s %s (reintento): %s", dia, nombre, exc)
                        est.errores.append(f"{nombre}: {exc}")
                    est.hechos += 1
        finally:
            est.activo, est.actual, est.fin = False, "", time.time()

    hilo = threading.Thread(target=run, name=f"precarga-{clave[0]}-{dia}", daemon=True)
    hilo.start()
    hilo.join(espera)
    return est


def precargar_dia(dia: date, barras: list[str], espera: float = 0.6) -> Precarga:
    """Descarga en segundo plano todo lo que necesita la vista de ``dia`` (días pasados)."""
    return precargar((dia, tuple(barras)), _tareas_dia(dia, barras), dia, espera)


# ------------------------------------------------- historial de CMg (indicadores)
DIAS_HISTORIAL = 7


def historial_cmg(barras: list[str], hasta: date, dias: int = DIAS_HISTORIAL) -> tuple[pd.DataFrame, Precarga]:
    """CMg en línea de los ``dias`` días anteriores a ``hasta`` (sin incluirlo), para promedios de spread.

    Una consulta por barra, descargada en segundo plano. Devuelve lo que ya está en caché (puede faltar
    alguna barra mientras la precarga sigue activa) y el estado de la precarga.
    """
    desde, fin = hasta - timedelta(days=dias), hasta - timedelta(days=1)
    tareas = [(f"CMg {dias} días {b.split('_')[0]}", cmg_online, (b, desde, fin)) for b in barras]
    est = precargar(("historial", hasta, tuple(barras)), tareas, hasta, espera=0.3, prioridad=PRIO_BAJA)
    dfs = []
    for b in barras:
        dfs += [x for x in _cmg_cache_dias(b, _dias(desde, fin))[0] if not x.empty]
    return (pd.concat(dfs, ignore_index=True) if dfs else T.cmg_df([])), est


# ------------------------------------------------------------ fuentes de la fase 4
def embalses(client=None, force=False) -> Cached:
    """Cota actual de los principales embalses."""
    return cached("embalses", "ultimo", lambda: T.embalses_df(_c(client).get(P_EMBALSES)), force=force,
                  background=True)


def capacidad(client=None, force=False) -> Cached:
    """Capacidad instalada (potencia neta efectiva) por tecnología, desde unidades generadoras (~3.400)."""
    def fetch():
        hoy = date.today()
        rows = _c(client).get_all_v4(P_UNIDADES, limit=5000, first_page=1, startDate=_d(hoy), endDate=_d(hoy))
        return T.capacidad_por_tecnologia(rows)
    return cached("capacidad", "unidades", fetch, force=force, background=True)


def demanda_pid(dia: date, client=None, force=False) -> Cached:
    """Demanda programada intradiaria (PID) de ``dia``: total por hora, última reprogramación."""
    def fetch():
        rows = _c(client).get_all_v4(P_DEM_PID, limit=5000, first_page=1, startDate=_d(dia), endDate=_d(dia))
        return T.demanda_prog_total(rows)
    ttl = "default" if not _es_pasado(dia) else 24 * 3600
    return cached("demanda_pid", _d(dia), fetch, ttl=ttl, force=force, background=True)


def pronostico_demanda(dia: date, client=None, force=False) -> Cached:
    """Pronóstico de demanda de mediano plazo (SING + SIC) por hora. 48 filas por día."""
    def fetch():
        rows = _c(client).get_all_v4(P_PRON_DEM, limit=500, first_page=1, startDate=_d(dia), endDate=_d(dia))
        return T.pronostico_demanda_total(rows)
    return cached("pron_demanda", _d(dia), fetch, force=force, background=True)


def reporte_generacion(dia: date, force=False) -> Cached:
    """Generación del día, mes y año a la fecha por tecnología (servicio Operación; ~1 día de atraso)."""
    def fetch():
        return T.reporte_generacion_df(default_client("operacion").get(OP_REPORTE_GEN, date=_d(dia), page=0))
    return cached("reporte_gen", _d(dia), fetch, ttl=None if _es_pasado(dia) else 3600, force=force,
                  background=True)


def sscc_real(dia: date, force=False) -> Cached:
    """Activaciones reales de servicios complementarios de ``dia`` (servicio Operación).

    Este endpoint numera páginas desde 0 (page=1 es la segunda; pedir una página inexistente da 400).
    """
    def fetch():
        filas: list[dict] = []
        for data in default_client("operacion").iter_pages(OP_SSCC, first_page=0, size_param="pageSize",
                                                            page_size=1000, initDate=_d(dia), endDate=_d(dia)):
            filas.extend(data)
        return T.sscc_df(filas)
    return cached("sscc_real", _d(dia), fetch, ttl=None if dia < date.today() - timedelta(days=1) else 3600,
                  force=force, background=True)


def mantenimientos(dia: date, client=None, force=False) -> Cached:
    """Programas de mantenimiento mayor solicitados en los 60 días previos a ``dia`` (sin filtrar por día)."""
    def fetch():
        rows = _c(client).get_all_v4(P_MANT, limit=5000, first_page=1,
                                     startDate=_d(dia - timedelta(days=60)), endDate=_d(dia))
        return T.mantenimientos_df(rows)
    return cached("mantenimientos", _d(dia), fetch, ttl=6 * 3600, force=force, background=True)


def solicitudes(dia: date, client=None, force=False) -> Cached:
    """Solicitudes de trabajo creadas en los 30 días previos a ``dia`` (sin filtrar por día)."""
    def fetch():
        rows = _c(client).get_all_v4(P_SOLIC, limit=5000, first_page=1,
                                     startDate=_d(dia - timedelta(days=30)), endDate=_d(dia))
        return T.solicitudes_df(rows)
    return cached("solicitudes", _d(dia), fetch, ttl=6 * 3600, force=force, background=True)


def embalses_bg():
    return en_segundo_plano("embalses", "ultimo", embalses)


def capacidad_bg():
    return en_segundo_plano("capacidad", "unidades", capacidad)


def demanda_pid_bg(dia: date):
    return en_segundo_plano("demanda_pid", _d(dia), demanda_pid, dia)


def pronostico_demanda_bg(dia: date):
    return en_segundo_plano("pron_demanda", _d(dia), pronostico_demanda, dia)


def reporte_generacion_bg(dia: date):
    return en_segundo_plano("reporte_gen", _d(dia), reporte_generacion, dia)


def sscc_real_bg(dia: date):
    return en_segundo_plano("sscc_real", _d(dia), sscc_real, dia)


def mantenimientos_bg(dia: date):
    return en_segundo_plano("mantenimientos", _d(dia), mantenimientos, dia)


def solicitudes_bg(dia: date):
    return en_segundo_plano("solicitudes", _d(dia), solicitudes, dia)
