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
        self.user_key = user_key or os.getenv(var_clave)
        if not self.user_key:
            raise CENError(f"Falta {var_clave} (defínela en .env)")
        self.base_url = (base_url or url_servicio).rstrip("/")
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.interval = min_interval  # pausa actual (sube con cada 429, baja con cada éxito)
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self._lock = threading.Lock()  # garantiza consultas en secuencia
        self._last_request = 0.0
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
        with self._lock:
            delay = 2.0
            for attempt in range(1, self.max_retries + 1):
                wait = self.interval - (time.monotonic() - self._last_request)
                if wait > 0:
                    time.sleep(wait)
                self._last_request = time.monotonic()
                self.request_count += 1
                try:
                    resp = self.session.get(url, params=params, timeout=self.timeout)
                except requests.RequestException as exc:
                    if attempt == self.max_retries:
                        raise CENError(f"Error de red en {path}: {exc}") from exc
                    log.warning("Error de red en %s (%s); reintento en %.0fs", path, exc, delay)
                else:
                    if resp.status_code == 200:
                        # relaja de a poco el throttle adaptativo
                        self.interval = max(self.min_interval, self.interval * 0.9)
                        return resp
                    if resp.status_code == 429:
                        # throttle adaptativo: el límite real de la API no está documentado
                        self.interval = min(self.max_interval, max(self.interval * 1.5, 3.0))
                    elif resp.status_code < 500:
                        return resp  # 4xx distinto de 429: no tiene sentido reintentar
                    # 5xx (p. ej. 502 cuando el servicio está caído): un solo reintento, no 5
                    limite = self.max_retries if resp.status_code == 429 else min(2, self.max_retries)
                    if attempt >= limite:
                        return resp
                    log.warning("HTTP %s en %s; reintento en %.0fs", resp.status_code, path, delay)
                self.retry_count += 1
                time.sleep(delay)
                self._last_request = time.monotonic()
                delay *= 2
        raise CENError("inalcanzable")

    def get(self, path: str, **params: Any) -> Any:
        resp = self.request(path, **params)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 403:
            raise CENError(f"Autenticación rechazada (403) en {path}: {resp.text[:200]}")
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
