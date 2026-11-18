import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cen import guia as G  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
# pestañas reales de app.py (se leen del código para que la prueba falle si se renombra alguna)
PESTANAS_APP = re.search(r"^PESTANAS = (\[.*\])", (RAIZ / "app.py").read_text(encoding="utf-8"), re.M)


def _pestanas() -> list[str]:
    assert PESTANAS_APP, "no se encontró PESTANAS en app.py"
    return eval(PESTANAS_APP.group(1))  # lista literal de strings


def test_cada_paso_esta_completo_y_enlaza_a_una_pestana_real():
    pestanas = _pestanas()
    assert "Guía" in pestanas
    for p in G.PASOS:
        for k in ("corto", "titulo", "que_hay", "como_usar", "limites", "pestana"):
            assert k in p, f"falta {k} en {p.get('corto')}"
        assert p["titulo"].strip() and p["que_hay"].strip()
        assert p["pestana"] is None or p["pestana"] in pestanas, p["pestana"]


def test_hay_un_paso_por_cada_pestana_de_datos():
    cubiertas = {p["pestana"] for p in G.PASOS if p["pestana"]}
    assert cubiertas == {t for t in _pestanas() if t != "Guía"}


def test_los_pasos_con_datos_explican_limites_del_coordinador():
    for p in G.PASOS:
        if p["pestana"] and p["pestana"] != "Resumen":
            assert p["limites"].strip(), f"{p['corto']} sin límites"


def test_nombres_cortos_unicos_y_tablas_no_vacias():
    cortos = [p["corto"] for p in G.PASOS]
    assert len(cortos) == len(set(cortos))
    assert G.ATRASOS and G.NO_DISPONIBLE and G.GLOSARIO
    assert all(len(f) == 3 for f in G.ATRASOS) and all(len(g) == 2 for g in G.GLOSARIO)


def test_la_guia_no_contiene_claves_ni_emojis():
    texto = " ".join(p["que_hay"] + p["como_usar"] + p["limites"] for p in G.PASOS)
    assert not re.search(r"\b[0-9a-f]{32}\b", texto)
    assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", texto)  # el dashboard no usa emojis
