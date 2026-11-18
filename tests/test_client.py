import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cen.client import CENClient, CENError  # noqa: E402


def test_elige_clave_y_url_segun_servicio(monkeypatch):
    monkeypatch.setenv("CEN_USER_KEY", "clave-sip")
    monkeypatch.setenv("CEN_OPERACION_KEY", "clave-op")
    sip, op = CENClient(service="sip"), CENClient(service="operacion")
    assert (sip.user_key, sip.base_url) == ("clave-sip", "https://sipub.api.coordinador.cl")
    assert (op.user_key, op.base_url) == ("clave-op", "https://operacion.api.coordinador.cl")


def test_falta_clave_o_servicio_desconocido(monkeypatch):
    monkeypatch.delenv("CEN_OPERACION_KEY", raising=False)
    with pytest.raises(CENError, match="CEN_OPERACION_KEY"):
        CENClient(service="operacion")
    with pytest.raises(CENError, match="desconocido"):
        CENClient(service="otro")


def test_iter_pages_lee_content_de_operacion(monkeypatch):
    monkeypatch.setenv("CEN_OPERACION_KEY", "x")
    c = CENClient(service="operacion")
    respuestas = {0: {"page": 0, "totalPages": 2, "content": [{"a": 1}]}, 1: {"page": 1, "totalPages": 2, "content": [{"a": 2}]}}
    monkeypatch.setattr(c, "get", lambda path, page, **kw: respuestas[page])
    filas = [r for data in c.iter_pages("x", first_page=0, size_param="pageSize", page_size=1) for r in data]
    assert filas == [{"a": 1}, {"a": 2}]
