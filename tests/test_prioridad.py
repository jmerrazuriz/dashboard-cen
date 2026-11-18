import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cen import client as C  # noqa: E402


def test_cola_entrega_el_turno_por_prioridad_y_orden_de_llegada():
    cola = C.ColaPrioridad()
    orden: list[str] = []

    def trabajo(nombre, prio):
        C.fijar_prioridad(prio)
        with cola:
            orden.append(nombre)

    with cola:  # ocupada mientras llegan los demás
        hilos = []
        for nombre, prio in [("fondo1", 1), ("baja", 2), ("fondo2", 1), ("pagina", 0)]:
            h = threading.Thread(target=trabajo, args=(nombre, prio))
            h.start()
            hilos.append(h)
            time.sleep(0.05)
    for h in hilos:
        h.join(5)
    assert orden == ["pagina", "fondo1", "fondo2", "baja"]


def test_prioridad_dinamica_se_reevalua():
    cola = C.ColaPrioridad()
    orden: list[str] = []
    estado = {"p": 0}

    def trabajo(nombre, prio):
        C.fijar_prioridad(prio)
        with cola:
            orden.append(nombre)

    with cola:
        a = threading.Thread(target=trabajo, args=("dinamica", lambda: estado["p"]))
        b = threading.Thread(target=trabajo, args=("fija", 1))
        a.start(); time.sleep(0.05); b.start(); time.sleep(0.05)
        estado["p"] = 2  # p. ej. el usuario cambió de día: esa descarga pasa a esperar
    a.join(5); b.join(5)
    assert orden == ["fija", "dinamica"]


def test_prioridad_por_defecto_es_la_de_la_pagina():
    resultado = []
    h = threading.Thread(target=lambda: resultado.append(C.prioridad_actual()))
    h.start(); h.join()
    assert resultado == [C.PRIO_PAGINA]


def test_reserva_frena_las_descargas_de_fondo_pero_no_la_pagina():
    cola = C.ColaPrioridad()
    orden: list[str] = []
    activa = {"v": True}

    def trabajo(nombre, prio):
        C.fijar_prioridad(prio)
        with cola:
            orden.append(nombre)

    with C.reservar(lambda: activa["v"]):
        fondo = threading.Thread(target=trabajo, args=("fondo", C.PRIO_FONDO))
        fondo.start(); time.sleep(0.1)
        assert orden == []                      # la cola está libre, pero hay una reserva activa
        trabajo("pagina", C.PRIO_PAGINA)        # la página pasa igual
        assert orden == ["pagina"]
    fondo.join(5)                               # al terminar la reserva, la de fondo sigue
    assert orden == ["pagina", "fondo"]
