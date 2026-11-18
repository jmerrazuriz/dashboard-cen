import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cen import tablas as TB  # noqa: E402


def test_fmt_num_formato_chileno():
    assert TB.fmt_num(1234.56, 1) == "1.234,6"
    assert TB.fmt_num(1234567) == "1.234.567"
    assert TB.fmt_num(-0.5, 2) == "-0,50"
    assert TB.fmt_num(None) == "—" and TB.fmt_num(float("nan")) == "—"


def test_columnas_numericas_alineadas_y_barras_proporcionales():
    df = pd.DataFrame({"b": ["A", "B"], "v": [50.0, 100.0]})
    h = TB.tabla_html(df, [TB.Col("b", "Barra"), TB.Col("v", "Spread", "barra", dec=1, unidad="USD/MWh")])
    assert 'class="num"' in h and "width:50.0%" in h and "width:100.0%" in h
    assert "50,0" in h and "USD/MWh" in h


def test_delta_badge_tec_y_vacios():
    df = pd.DataFrame({"d": [5.0, -3.0, None], "e": ["Aprobado", "Pendiente", "Otro"], "t": ["Solar", "Eólica", None]})
    h = TB.tabla_html(df, [TB.Col("d", "Desv.", "delta", dec=1), TB.Col("e", "Estado", "badge", colores=TB.COLORES_ESTADO),
                           TB.Col("t", "Tec.", "tec", colores={"Solar": "#F2B701"})])
    assert 'class="sube">+5,0' in h and 'class="baja">-3,0' in h
    assert TB.VERDE[0] in h and TB.AMBAR[0] in h and TB.GRIS[0] in h  # «Otro» sin color definido: gris
    assert "#F2B701" in h and h.count('class="nd">—') >= 2


def test_escapa_html_y_texto_largo_con_ver_mas():
    df = pd.DataFrame({"x": ["<script>alert(1)</script> " + "palabra " * 80]})
    h = TB.tabla_html(df, [TB.Col("x", "Trabajo", "largo")], largo_max=100)
    assert "<script>" not in h and "&lt;script&gt;" in h
    # «ver más» / «ver menos»: casilla oculta + resto del texto + etiqueta enlazada a la casilla
    assert 'class="vm-chk"' in h and 'class="vm-resto"' in h and 'class="vm-btn"' in h
    uid = h.split('class="vm-chk"')[0].rsplit('id="', 1)[1].split('"')[0]
    assert f'for="{uid}"' in h
    assert 'content:" ver menos"' in TB.CSS and 'content:"… ver más"' in TB.CSS


def test_ids_de_ver_mas_unicos():
    df = pd.DataFrame({"x": ["palabra " * 80, "otra " * 80]})
    h = TB.tabla_html(df, [TB.Col("x", "Trabajo", "largo")], largo_max=50)
    ids = [p.split('"')[0] for p in h.split('id="')[1:]]
    assert len(ids) == 2 and len(set(ids)) == 2


def test_tabla_vacia_y_tipo_invalido():
    assert "Sin datos" in TB.tabla_html(pd.DataFrame({"a": []}), [TB.Col("a")])
    with pytest.raises(ValueError):
        TB.Col("a", tipo="otro")
