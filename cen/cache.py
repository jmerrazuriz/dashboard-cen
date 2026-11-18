"""Caché en disco con TTL por fuente.

Cada entrada se guarda como Parquet (DataFrames) o JSON (otros objetos) en ``.cache/``.
La antigüedad se toma del mtime del archivo. ``ttl=None`` significa permanente.
Si la API falla y hay una copia vencida, se devuelve la copia (con ``stale=True``).
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"

MIN = 60
HOUR = 3600
TTL = {
    "cmg_online": 15 * MIN,
    "cmg_8b": 15 * MIN,
    "cmg_pcp": 6 * HOUR,
    "cmg_real": 24 * HOUR,
    "gen_real_hoy": 30 * MIN,
    "gen_real_pasado": None,
    "daily_sum": 30 * MIN,
    "demanda_neta": HOUR,
    "demanda_prog": 6 * HOUR,
    "barras": 24 * HOUR,
    "cmg_pid": 30 * MIN,
    "instrucciones_cmg": 6 * HOUR,
    "erv_prog": 12 * HOUR,
    "gen_prog": 12 * HOUR,
    "embalses": HOUR,
    "capacidad": 24 * HOUR,
    "demanda_pid": 30 * MIN,
    "pron_demanda": 6 * HOUR,
}


# Caché negativa en memoria: tras un fallo, no se reintenta la misma fuente por unos minutos
FAIL_COOLDOWN = 5 * MIN
_FALLOS: dict[tuple[str, str], tuple[float, str]] = {}


# Modo "solo caché" (por hilo): mientras está activo, ``cached`` no consulta la API; devuelve la copia
# guardada (aunque esté vencida) o lanza ``SinCache``. Lo usa la página mientras un hilo en segundo
# plano descarga un día pasado, para mostrar lo que ya está listo sin quedar bloqueada.
_local = threading.local()


class SinCache(LookupError):
    """La fuente aún no está descargada (modo solo caché)."""


def modo_solo_cache(activo: bool) -> None:
    """Activa/desactiva el modo solo caché en el hilo actual (la página lo fija al inicio de cada
    ejecución, así un rerun interrumpido nunca lo deja activado por error)."""
    _local.solo = activo


class solo_cache:
    def __enter__(self):
        _local.solo = True

    def __exit__(self, *exc):
        _local.solo = False


@dataclass
class Cached:
    value: Any
    fetched_at: float  # epoch s
    stale: bool = False
    from_cache: bool = False
    refreshing: bool = False  # se devolvió la copia vencida y se está actualizando


def _path(namespace: str, key: str, ext: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in key)
    if len(safe) > 80:
        safe = safe[:60] + "_" + hashlib.sha1(key.encode()).hexdigest()[:12]
    return CACHE_DIR / namespace / f"{safe}.{ext}"


def _read(path: Path) -> Any:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if isinstance(value, pd.DataFrame):
        value.to_parquet(tmp, index=False)
    else:
        tmp.write_text(json.dumps(value, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def peek(namespace: str, key: str, ttl: float | None | str = "default") -> Cached | None:
    """Lee la caché sin consultar la API; None si no hay copia vigente."""
    if ttl == "default":
        ttl = TTL.get(namespace, 15 * MIN)
    for p in (_path(namespace, key, "parquet"), _path(namespace, key, "json")):
        if p.exists():
            age = time.time() - p.stat().st_mtime
            if ttl is None or age < ttl:
                return Cached(_read(p), p.stat().st_mtime, from_cache=True)
    return None


def _store(pq: Path, js: Path, value: Any) -> None:
    target = pq if isinstance(value, pd.DataFrame) else js
    _write(target, value)
    other = js if target is pq else pq
    if other.exists():
        other.unlink()


# Actualizaciones en segundo plano en curso (namespace, key) -> hilo
_REFRESCOS: dict[tuple[str, str], threading.Thread] = {}


def refrescando() -> list[str]:
    """Fuentes que se están actualizando en segundo plano ahora mismo."""
    return [f"{ns}/{k}" for (ns, k), h in list(_REFRESCOS.items()) if h.is_alive()]


def cached(namespace: str, key: str, fetch: Callable[[], Any], ttl: float | None | str = "default",
           force: bool = False, background: bool = False) -> Cached:
    """Devuelve el valor cacheado si está vigente; si no, llama ``fetch`` y lo guarda.

    ``background=True``: si hay una copia vencida, se devuelve al tiro (``refreshing=True``) y la
    actualización corre en un hilo; así la página no queda en blanco mientras la API responde.
    """
    if ttl == "default":
        ttl = TTL.get(namespace, 15 * MIN)
    pq, js = _path(namespace, key, "parquet"), _path(namespace, key, "json")
    existing = pq if pq.exists() else js if js.exists() else None
    now = time.time()
    if getattr(_local, "solo", False):
        if existing is None:
            raise SinCache(f"{namespace}/{key} aún no descargado")
        return Cached(_read(existing), existing.stat().st_mtime, from_cache=True)
    if existing is not None and not force:
        age = now - existing.stat().st_mtime
        if ttl is None or age < ttl:
            return Cached(_read(existing), existing.stat().st_mtime, from_cache=True)
    fallo = _FALLOS.get((namespace, key))
    if fallo and now - fallo[0] < FAIL_COOLDOWN and not force:
        if existing is not None:
            return Cached(_read(existing), existing.stat().st_mtime, stale=True, from_cache=True)
        raise RuntimeError(f"{fallo[1]} (reintento en {int(FAIL_COOLDOWN - (now - fallo[0]))} s)")

    if background and existing is not None and not force:
        clave = (namespace, key)
        hilo = _REFRESCOS.get(clave)
        if hilo is None or not hilo.is_alive():
            def run():
                try:
                    _store(pq, js, fetch())
                    _FALLOS.pop(clave, None)
                except Exception as exc:
                    _FALLOS[clave] = (time.time(), str(exc))
                    log.exception("Fallo al actualizar en segundo plano %s/%s", namespace, key)
            _REFRESCOS[clave] = threading.Thread(target=run, name=f"refresh-{namespace}-{key}", daemon=True)
            _REFRESCOS[clave].start()
        return Cached(_read(existing), existing.stat().st_mtime, from_cache=True, refreshing=True)

    try:
        value = fetch()
        _FALLOS.pop((namespace, key), None)
    except Exception as exc:
        _FALLOS[(namespace, key)] = (now, str(exc))
        if existing is not None:
            log.exception("Fallo al actualizar %s/%s; uso copia vencida", namespace, key)
            return Cached(_read(existing), existing.stat().st_mtime, stale=True, from_cache=True)
        raise
    _store(pq, js, value)
    return Cached(value, now)
