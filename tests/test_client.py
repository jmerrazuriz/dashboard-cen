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


# Las claves de estas pruebas son valores inventados (no son claves reales).
CLAVE_FALSA = "0123456789abcdef0123456789abcdef"


def test_limpiar_clave_quita_comillas_y_espacios():
    from cen.client import limpiar_clave
    assert limpiar_clave(f'  "{CLAVE_FALSA}"\n') == CLAVE_FALSA
    assert limpiar_clave(f"'{CLAVE_FALSA}' ") == CLAVE_FALSA
    assert limpiar_clave("<clave-oculta>") == "clave-oculta"
    assert limpiar_clave(None) == ""


def test_revisar_clave_detecta_formato_y_no_revela_el_valor(monkeypatch):
    from cen.client import revisar_clave
    monkeypatch.setenv("CEN_USER_KEY", "<clave-oculta>")
    msg = revisar_clave("sip")
    assert "CEN_USER_KEY" in msg and "32" in msg and "clave-oculta" not in msg  # solo el largo, no el valor
    monkeypatch.setenv("CEN_USER_KEY", CLAVE_FALSA + " ")  # espacio al final: se normaliza
    assert revisar_clave("sip") is None
    monkeypatch.delenv("CEN_USER_KEY")
    assert "Falta" in revisar_clave("sip")


def test_error_403_informa_el_largo_sin_la_clave(monkeypatch):
    monkeypatch.setenv("CEN_USER_KEY", CLAVE_FALSA)
    c = CENClient(service="sip")

    class Respuesta403:  # respuesta simulada, sin red
        status_code = 403
        text = "Authentication failed"

    monkeypatch.setattr(c, "request", lambda path, **kw: Respuesta403())
    with pytest.raises(CENError) as e:
        c.get("x")
    texto = str(e.value)
    assert "403" in texto and "32 caracteres" in texto and CLAVE_FALSA[:8] not in texto
