"""La app completa debe ejecutarse sin excepciones (sin red: la API se simula con respuestas vacías)."""
import sys
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


@pytest.fixture
def app_sin_red(monkeypatch):
    from cen import cache as K
    from cen import client as C

    monkeypatch.setenv("CEN_USER_KEY", "0123456789abcdef0123456789abcdef")  # inventadas
    monkeypatch.setenv("CEN_OPERACION_KEY", "fedcba9876543210fedcba9876543210")
    monkeypatch.setattr(K, "CACHE_DIR", Path(tempfile.mkdtemp(prefix="cache_test_")))

    class Vacia:  # toda consulta responde 200 sin datos
        status_code = 200
        text = "{}"

        def json(self):
            return {"data": [], "totalPages": 0}

    monkeypatch.setattr(C.CENClient, "request", lambda self, path, **kw: Vacia())

    # Otras pruebas ya importaron módulos de cen/ (sin la marca de carga que pone app.py). Se marcan como
    # recién cargados para que app.py no los recargue: una recarga crearía clases nuevas (p. ej. CENError)
    # distintas de las que esas pruebas guardaron.
    import time
    for nombre, modulo in list(sys.modules.items()):
        if nombre.startswith("cen.") and not hasattr(modulo, "_cargado_en"):
            monkeypatch.setattr(modulo, "_cargado_en", time.time(), raising=False)


def test_la_app_corre_sin_excepciones(app_sin_red):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
    botones = [b.label for b in at.button]
    assert "Recorrido guiado" in botones and "Hacer el recorrido" in botones


def test_recarga_un_modulo_viejo_que_quedo_en_memoria(app_sin_red):
    """Reproduce lo que pasó en Streamlit Cloud tras un push: app.py nuevo con cen/guia.py viejo en memoria."""
    from streamlit.testing.v1 import AppTest

    AppTest.from_file(str(RAIZ / "app.py"), default_timeout=120).run()  # carga normal
    viejo = sys.modules["cen.guia"]
    del viejo.pasos_json                      # la versión anterior no tenía esta función
    if hasattr(viejo, "_cargado_en"):
        del viejo._cargado_en                 # ni la marca de carga

    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
    assert hasattr(sys.modules["cen.guia"], "pasos_json")  # se recargó la versión del disco
