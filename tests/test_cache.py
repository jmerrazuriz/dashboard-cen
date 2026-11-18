import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cen import cache as C  # noqa: E402


def _envejecer(ns, key, seg):
    for ext in ("json", "parquet"):
        p = C._path(ns, key, ext)
        if p.exists():
            t = time.time() - seg
            os.utime(p, (t, t))


def test_background_devuelve_copia_vencida_y_actualiza(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "CACHE_DIR", tmp_path)
    assert C.cached("t", "k", lambda: {"v": 1}, ttl=60, background=True).value == {"v": 1}  # sin copia: síncrono
    _envejecer("t", "k", 120)

    r = C.cached("t", "k", lambda: (time.sleep(0.3), {"v": 2})[1], ttl=60, background=True)
    assert r.value == {"v": 1} and r.refreshing  # devuelve la copia vencida al tiro
    C._REFRESCOS[("t", "k")].join(5)
    assert C.cached("t", "k", lambda: {"v": 3}, ttl=60).value == {"v": 2}  # el hilo guardó el valor nuevo


def test_fallo_reciente_no_reintenta(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "CACHE_DIR", tmp_path)
    llamadas = []

    def falla():
        llamadas.append(1)
        raise RuntimeError("HTTP 502")

    for _ in range(2):
        try:
            C.cached("f", "k", falla)
        except RuntimeError:
            pass
    assert len(llamadas) == 1
    C._FALLOS.clear()


def test_modo_solo_cache_no_consulta(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "CACHE_DIR", tmp_path)
    llamadas = []
    C.cached("s", "a", lambda: {"v": 1}, ttl=60)
    _envejecer("s", "a", 120)  # vencida
    C.modo_solo_cache(True)
    try:
        r = C.cached("s", "a", lambda: llamadas.append(1) or {"v": 2}, ttl=60)
        assert r.value == {"v": 1} and not llamadas  # copia vencida, sin consultar
        try:
            C.cached("s", "nuevo", lambda: llamadas.append(1) or {"v": 3})
            assert False, "debía lanzar SinCache"
        except C.SinCache:
            pass
        assert not llamadas
    finally:
        C.modo_solo_cache(False)
    assert C.cached("s", "nuevo", lambda: {"v": 3}).value == {"v": 3}  # fuera del modo, consulta normal
