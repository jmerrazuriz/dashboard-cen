"""Cliente HTTP para las APIs del Coordinador Eléctrico Nacional (servicios SIP y Operación).

- Agrega ``user_key`` a cada request, con la clave del servicio (leída de ``.env``):
  SIP -> ``CEN_USER_KEY``; Operación -> ``CEN_OPERACION_KEY``.
- Throttle global: pausa mínima entre requests (las consultas van en secuencia).
- Reintenta 429 y 5xx con backoff exponencial (2, 4, 8, 16 s; máx. 5 intentos).
- Paginación para endpoints v4 (page desde 0, ``limit``) y v3 (page desde 1, ``pageSize``).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Iterator

import requests
from dotenv import load_dotenv

log = logging.getLogger(__name__)

BASE_URL = "https://sipub.api.coordinador.cl"
# servicio -> (URL base, variable de entorno con su clave). Ambos autentican con ?user_key=
SERVICIOS = {
    "sip": (BASE_URL, "CEN_USER_KEY"),
    "operacion": ("https://operacion.api.coordinador.cl", "CEN_OPERACION_KEY"),
}
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


class CENError(RuntimeError):
    pass


RE_CLAVE = re.compile(r"^[0-9a-fA-F]{32}$")  # las claves del CEN son 32 caracteres hexadecimales


def limpiar_clave(valor: str | None) -> str:
    """Quita espacios, saltos de línea y comillas/corchetes que se cuelan al pegar un secreto."""
    basura = chr(34) + chr(39) + chr(96) + "<>[]() " + chr(9) + chr(13) + chr(10)
    return str(valor or "").strip().strip(basura)


def revisar_clave(service: str) -> str | None:
    """None si la clave del servicio luce bien; si no, un mensaje con el problema.

    El mensaje nunca incluye la clave (ni parte de ella), solo su largo, para poder mostrarlo en pantalla.
    """
    var = SERVICIOS[service][1]
    v = limpiar_clave(os.getenv(var))
    if not v:
        return f"Falta la clave {var}: no está definida en los Secrets (o en .env)."
    if not RE_CLAVE.match(v):
        return (f"La clave {var} no tiene el formato esperado: tiene {len(v)} caracteres y debería tener 32, "
                "solo letras a–f y números. Vuelve a copiar el valor completo desde el portal del Coordinador, "
                "sin texto adicional.")
    return None


# ------------------------------------------------------------- prioridades
# Todas las consultas pasan de a una (límite de la API). Cuando varias esperan turno, pasa primero la de
# menor prioridad (0 = lo que la página necesita ya; 1 = descargas en segundo plano; 2 = lo que puede
# esperar: historial, días que ya no se están mirando). A igual prioridad, por orden de llegada.
PRIO_PAGINA, PRIO_FONDO, PRIO_BAJA = 0, 1, 2
_prio_local = threading.local()


def fijar_prioridad(prioridad) -> None:
    """Prioridad de las consultas del hilo actual: un entero o una función sin argumentos que lo devuelve
    (se evalúa mientras espera turno, así una descarga puede bajar de prioridad si el usuario cambia de día)."""
    _prio_local.valor = prioridad


def prioridad_actual() -> int:
    p = getattr(_prio_local, "valor", PRIO_PAGINA)
    return int(p() if callable(p) else p)


# Reservas: (hilo, función sin argumentos). Mientras una esté activa, solo pasan consultas de prioridad 0,
# salvo que ese hilo esté en pausa por un 429 (entonces las demás aprovechan el tiempo muerto).
_RESERVAS: set = set()
_EN_PAUSA: set[int] = set()


class reservar:
    """Mientras dure el bloque (y ``activa()`` dé True), las consultas de prioridad > 0 no empiezan:
    así la precarga del día que se mira no espera, entre consulta y consulta, a las descargas de fondo."""

    def __init__(self, activa=lambda: True):
        self.entrada = (threading.get_ident(), activa)

    def __enter__(self):
        self.entrada = (threading.get_ident(), self.entrada[1])
        _RESERVAS.add(self.entrada)
        return self

    def __exit__(self, *exc):
        _RESERVAS.discard(self.entrada)


def _reservado() -> bool:
    return any(hilo not in _EN_PAUSA and f() for hilo, f in list(_RESERVAS))


class ColaPrioridad:
    """Candado que, al liberarse, se lo entrega al que espera con menor prioridad (y luego al más antiguo)."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._ocupado = False
        self._esperando: list[tuple[int, object]] = []
        self._seq = 0

    def __enter__(self):
        valor = getattr(_prio_local, "valor", PRIO_PAGINA)
        fn = valor if callable(valor) else (lambda v=valor: v)
        with self._cond:
            self._seq += 1
            yo = (self._seq, fn)
            self._esperando.append(yo)
            try:
                # timeout: las prioridades dinámicas se reevalúan aunque nadie avise
                while (self._ocupado or min(self._esperando, key=lambda e: (int(e[1]()), e[0])) is not yo
                       or (int(fn()) > PRIO_PAGINA and _reservado())):
                    self._cond.wait(timeout=1.0)
            finally:
                self._esperando.remove(yo)
            self._ocupado = True
        return self

    def __exit__(self, *exc):
        with self._cond:
            self._ocupado = False
            self._cond.notify_all()


class CENClient:
    def __init__(
        self,
        user_key: str | None = None,
        base_url: str | None = None,
        service: str = "sip",
        min_interval: float = float(os.getenv("CEN_MIN_INTERVAL", "1.5")),
        max_interval: float = 15.0,
        timeout: float = 90.0,
        max_retries: int = 5,
    ) -> None:
        if service not in SERVICIOS:
            raise CENError(f"Servicio desconocido: {service} (opciones: {', '.join(SERVICIOS)})")
        url_servicio, var_clave = SERVICIOS[service]
        self.service = service
        self.var_clave = var_clave
        self.user_key = limpiar_clave(user_key or os.getenv(var_clave))
        if not self.user_key:
            raise CENError(f"Falta {var_clave} (defínela en .env)")
        self.base_url = (base_url or url_servicio).rstrip("/")
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.interval = min_interval  # pausa actual (sube con cada 429, baja con cada éxito)
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self._lock = ColaPrioridad()  # consultas en secuencia, por prioridad
        self._last_request = 0.0
        # Ritmo por endpoint: algunos (p. ej. el CMg en línea) tienen un límite propio más estricto. Tras un
        # 429 solo ese endpoint se pausa y se espacia; los demás siguen.
        self._ruta_proxima: dict[str, float] = {}   # ruta -> instante (monotonic) desde el que se puede consultar
        self._ruta_intervalo: dict[str, float] = {}  # ruta -> separación mínima entre consultas (s)
        self.request_count = 0
        self.retry_count = 0

    # ------------------------------------------------------------------ core
    def request(self, path: str, **params: Any) -> requests.Response:
        """GET con throttle y reintentos (429 hasta ``max_retries``; 5xx una vez; errores de red).

        Devuelve la última respuesta tal cual (sin exigir 200): útil para pruebas de endpoints.
        """
        params = {k: v for k, v in params.items() if v is not None}
        params["user_key"] = self.user_key
        url = f"{self.base_url}/{path.lstrip('/')}"
        # El turno se toma por intento, no por consulta completa: durante la pausa de un reintento la cola
        # queda libre, y al terminar la pausa pasa primero lo más prioritario (no el que recibió el error).
        ruta = path.split("?")[0]
        delay = 2.0
        intentos_429 = 0
        attempt = 0
        while True:
            attempt += 1
            espera_ruta = self._ruta_proxima.get(ruta, 0.0) - time.monotonic()
            if espera_ruta > 0:  # pausa propia de este endpoint, fuera de la cola
                _EN_PAUSA.add(threading.get_ident())
                try:
                    time.sleep(espera_ruta)
                finally:
                    _EN_PAUSA.discard(threading.get_ident())
            pausa_propia = 0.0  # 5xx / red: solo esta consulta espera
            with self._lock:
                if self._ruta_proxima.get(ruta, 0.0) > time.monotonic():
                    # mientras esperaba turno, otra consulta a este endpoint recibió un 429: vuelve a esperar
                    # (fuera de la cola) en vez de consultar y provocar otro 429
                    attempt -= 1
                    continue
                wait = self.interval - (time.monotonic() - self._last_request)
                if wait > 0:
                    time.sleep(wait)
                self._last_request = time.monotonic()
                self.request_count += 1
                try:
                    resp = self.session.get(url, params=params, timeout=self.timeout)
                except requests.RequestException as exc:
                    if attempt >= self.max_retries:
                        raise CENError(f"Error de red en {path}: {exc}") from exc
                    log.warning("Error de red en %s (%s); reintento en %.0fs", path, exc, delay)
                    pausa_propia = delay
                else:
                    sep = self._ruta_intervalo.get(ruta, 0.0)
                    if resp.status_code == 200:
                        # relaja de a poco el throttle adaptativo (global y del endpoint)
                        self.interval = max(self.min_interval, self.interval * 0.9)
                        if sep:
                            self._ruta_intervalo[ruta] = sep = sep * 0.9 if sep > 1 else 0.0
                            self._ruta_proxima[ruta] = time.monotonic() + sep
                        return resp
                    if resp.status_code == 429:
                        # límite no documentado: se espacia ese endpoint (hasta 30 s entre consultas) y se
                        # reintenta con pausas crecientes (2, 4, 8, 16, 30, 30… s; hasta ~2 min en total)
                        intentos_429 += 1
                        self._ruta_intervalo[ruta] = min(30.0, max(sep * 1.5, 5.0))
                        if intentos_429 >= self.max_retries + 3:
                            return resp
                        log.warning("HTTP 429 en %s; reintento en %.0fs", path, delay)
                        self._ruta_proxima[ruta] = time.monotonic() + max(delay, self._ruta_intervalo[ruta])
                    elif resp.status_code < 500:
                        return resp  # 4xx distinto de 429: no tiene sentido reintentar
                    else:
                        # 5xx (p. ej. 502 cuando el servicio está caído): un solo reintento, no 5
                        if attempt >= min(2, self.max_retries):
                            return resp
                        log.warning("HTTP %s en %s; reintento en %.0fs", resp.status_code, path, delay)
                        pausa_propia = delay
                self.retry_count += 1
            if pausa_propia:
                time.sleep(pausa_propia)
            delay = min(delay * 2, 30.0)

    def get(self, path: str, **params: Any) -> Any:
        resp = self.request(path, **params)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 403:
            raise CENError(f"Autenticación rechazada (403) en {path}: {resp.text[:200]} "
                           f"[la clave de {self.service} cargada en {self.var_clave} tiene "
                           f"{len(self.user_key)} caracteres]")
        if resp.status_code == 429 or resp.status_code >= 500:
            raise CENError(f"HTTP {resp.status_code} en {path} tras reintentos")
        raise CENError(f"HTTP {resp.status_code} en {path}: {resp.text[:200]}")

    # ------------------------------------------------------------ paginación
    def iter_pages(
        self,
        path: str,
        *,
        first_page: int,
        size_param: str,
        page_size: int,
        max_pages: int | None = None,
        **params: Any,
    ) -> Iterator[list[dict]]:
        """Recorre todas las páginas y entrega la lista ``data`` de cada una."""
        page = first_page
        fetched = 0
        while True:
            payload = self.get(path, page=page, **{size_param: page_size}, **params)
            if isinstance(payload, dict):
                # SIP usa "data"; el servicio Operación, "content" (y algunos recursos v2, "results")
                clave = next((k for k in ("data", "content", "results") if k in payload), None)
                data = (payload.get(clave) or []) if clave else []
            else:
                data = payload
            yield data
            fetched += 1
            total = payload.get("totalPages") if isinstance(payload, dict) else None
            last_page = (first_page + total - 1) if total is not None else None
            if not data or (last_page is not None and page >= last_page):
                break
            if total is None and len(data) < page_size:
                break
            if max_pages is not None and fetched >= max_pages:
                break
            page += 1

    def get_all_v4(self, path: str, limit: int = 1000, first_page: int = 0, **params: Any) -> list[dict]:
        """Todas las páginas de un endpoint v4.

        Ojo: los endpoints PCP (cmg-programado-pcp, demanda-programada-pcp) numeran desde 1:
        en cmg-programado ``page=0`` da HTTP 502 y en demanda-programada repite la página 1.
        Por seguridad se descartan filas con ``id`` repetido.
        """
        rows: list[dict] = []
        vistos: set = set()
        for data in self.iter_pages(path, first_page=first_page, size_param="limit", page_size=limit, **params):
            for r in data:
                rid = r.get("id") if isinstance(r, dict) else None
                if rid is not None:
                    if rid in vistos:
                        continue
                    vistos.add(rid)
                rows.append(r)
        return rows

    def get_all_v3(self, path: str, page_size: int = 1000, **params: Any) -> list[dict]:
        rows: list[dict] = []
        for data in self.iter_pages(path, first_page=1, size_param="pageSize", page_size=page_size, **params):
            rows.extend(data)
        return rows


_clientes: dict[str, CENClient] = {}


def default_client(service: str = "sip") -> CENClient:
    """Un cliente compartido por servicio (cada uno con su clave, throttle y cola de consultas)."""
    if service not in _clientes:
        _clientes[service] = CENClient(service=service)
    return _clientes[service]
