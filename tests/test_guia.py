import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cen import guia as G  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
APP = (RAIZ / "app.py").read_text(encoding="utf-8")
MOTOR = (RAIZ / "assets" / "recorrido.js").read_text(encoding="utf-8")


def _pestanas() -> list[str]:
    m = re.search(r"^PESTANAS = (\[.*\])", APP, re.M)
    assert m, "no se encontró PESTANAS en app.py"
    return eval(m.group(1))  # lista literal de strings


def test_cada_paso_esta_completo_y_su_pestana_existe():
    pestanas = _pestanas()
    assert "Guía" not in pestanas  # el recorrido va sobre el dashboard, no es una pestaña aparte
    for p in G.PASOS:
        for k in ("titulo", "html", "limites", "pestana", "objetivo"):
            assert k in p, f"falta {k} en {p.get('titulo')}"
        assert p["titulo"].strip() and p["html"].strip()
        assert p["pestana"] is None or p["pestana"] in pestanas, p["pestana"]


def test_el_recorrido_pasa_por_todas_las_pestanas():
    visitadas = {p["pestana"] for p in G.PASOS if p["pestana"]}
    assert visitadas == set(_pestanas())


def test_cada_seccion_que_busca_el_recorrido_esta_marcada_en_app():
    assert G.SECCIONES_MARCADAS  # hay secciones enmarcadas
    for sec in G.SECCIONES_MARCADAS:
        nombre = sec[len("tour_"):]
        marcada = f'tour="{nombre}"' in APP or f'key="{sec}"' in APP
        assert marcada, f"app.py no marca la sección {sec} (st.container(key=...) o grafico(..., tour=...))"


def test_pasos_de_datos_explican_limites_del_coordinador():
    con_limites = [p for p in G.PASOS if p["limites"].strip()]
    assert len(con_limites) >= 8
    for p in G.PASOS:
        if p["pestana"] in ("Baterías", "Costos marginales", "Demanda", "Operación"):
            assert p["limites"].strip(), p["titulo"]


def test_json_valido_y_seguro_para_insertar_en_script():
    js = G.pasos_json()
    datos = json.loads(js)
    assert len(datos) == len(G.PASOS)
    assert "</" not in js  # no puede cerrar el <script> donde se inserta


def test_motor_y_app_usan_la_misma_version():
    v_motor = re.search(r"version:\s*(\d+)", MOTOR).group(1)
    assert f"version !== {v_motor}" in APP


def test_la_guia_no_contiene_claves_ni_emojis():
    texto = " ".join(p["html"] + p["limites"] for p in G.PASOS)
    assert not re.search(r"\b[0-9a-f]{32}\b", texto)
    assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", texto)  # el dashboard no usa emojis
